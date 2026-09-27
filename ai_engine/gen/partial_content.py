"""B6: 节点级局部重生成。

在 /gen/content 的基础上支持 mode=partial：
  - 只重新生成 target_node_ids 指定的节点
  - 保留其他节点的内容与引用关系不变
  - 样式类修改（restyle）不触发 RAG 检索，只改呈现层
  - 内容类修改（simplify/expand/rewrite）触发局部 RAG 检索，
    把命中的知识块作为「参考材料」注入重生成提示词

关于「局部 RAG」的 scope（原实现在这里是错的）
--------------------------------------------
原 docstring 写的是 scope=target_node，但 ai_engine/rag/retrieve.py 的
`_matches_scope` 只认 course / node / page 三个值，传 `target_node` 会直接
走到 `return False` → 零结果；而 scope=node 要求 chunk.metadata 里带 node_id，
知识库上传的 chunk 只带 knowledge_base_id（rag/router.py 的 knowledge_upload），
所以走 node 作用域同样是零结果。

因此这里的「局部」落在**查询侧**：用节点自身的标题/摘要/核心要点构造检索查询，
再以 course 作用域全库检索。精度来自查询词而不是元数据过滤 —— 这与前端
`buildIntentEvidenceQuery` 的构造方式一致。

不新建独立端点——而是在 _run_content_pipeline 里分支调用，
避免改变前端既有 /gen/content 调用路径。
"""

from __future__ import annotations

import logging
from typing import Any

from .node import NodeGenerator

logger = logging.getLogger(__name__)

# ---- 局部 RAG 参数（与 rag/router.py 的 /rag/evidence 取值对齐）----
_EVIDENCE_TOP_K = 20
"""候选池大小。"""

_EVIDENCE_RERANK_TOP_K = 5
"""重排后真正注入提示词的条数。"""

_EVIDENCE_MIN_SCORE = 0.3
"""候选池阈值，此阶段刻意放宽，交给重排收敛。"""

_EVIDENCE_SNIPPET_CHARS = 200
"""单条参考材料的截断长度，与 outline.py 的 _format_evidence 保持一致。"""

_EVIDENCE_QUERY_CHARS = 300
"""检索查询的最大长度，避免整段摘要把查询词稀释掉。"""


# ---- 局部 RAG 辅助 ----

def _as_text(value: Any) -> str:
    """把节点字段拍平成可检索的文本。

    core_points 之类的字段多数是字符串，但快照里也出现过
    `{"text": ...}` / `{"point": ...}` 形态，这里统一取正文，取不到就跳过，
    避免把整个 dict 的 repr 塞进查询词把语义稀释掉。
    """
    if isinstance(value, dict):
        for key in ("text", "content", "point", "title", "name"):
            if value.get(key):
                return str(value[key]).strip()
        return ""
    return str(value or "").strip()


def node_evidence_query(node: dict[str, Any]) -> str:
    """用节点自身信息构造检索查询。

    节点里没有现成的「查询词」，但标题 + 摘要 + 核心要点已经是最贴近这一页
    知识范围的表述 —— 比拿整篇课件的 topic 去查精确得多（main.py 的服务端
    兜底取证用的就是后者，那是课件级粒度）。
    """
    parts: list[str] = []
    for value in (node.get("title"), node.get("summary")):
        text = _as_text(value)
        if text:
            parts.append(text)
    for field in ("core_points", "key_points", "key_difficulties", "examples"):
        raw = node.get(field)
        if isinstance(raw, (list, tuple)):
            parts.extend(text for text in (_as_text(item) for item in raw) if text)
        else:
            text = _as_text(raw)
            if text:
                parts.append(text)

    # dict.fromkeys 去重且保持顺序（标题与要点常重复出现）
    return "；".join(dict.fromkeys(parts))[:_EVIDENCE_QUERY_CHARS]


def format_evidence(results: list[Any]) -> str:
    """把检索结果格式化成提示词里的「参考材料」块。

    格式与 ai_engine/gen/outline.py 的 `_format_evidence` 保持一致（每条截断
    200 字），让「证据进提示词」在全文生成与局部修改两条路径上形态统一。
    """
    lines: list[str] = []
    for item in results:
        text = str(getattr(item, "content", "") or "").strip()
        if text:
            lines.append(f"- {text[:_EVIDENCE_SNIPPET_CHARS]}")
    return "\n".join(lines)


def get_evidence_retriever():
    """惰性获取全局检索器；不可用时返回 None。

    检索器只在有待重生成节点时初始化一次，循环内复用 ——
    `_get_retriever()` 每次都会重建 BM25 索引（rag/router.py:79-82），
    在批量循环里重复调用纯属浪费。
    """
    try:
        from ai_engine.rag.router import _get_retriever

        return _get_retriever()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[partial] 检索器初始化失败，局部重生成将不带参考材料: %s", exc)
        return None


def retrieve_node_evidence(query: str, retriever: Any) -> tuple[str, list[str]]:
    """检索该节点的参考材料，返回 (参考材料文本, 命中的 chunk_id 列表)。

    任何一步失败都降级为「无证据」，不影响局部重生成本身 ——
    局部修改的价值在于改得快，不该因为知识库不可用就整体失败。
    """
    if not query or retriever is None:
        return "", []

    try:
        from ai_engine.rag.router import _reranker

        candidates = retriever.search(
            query=query,
            top_k=_EVIDENCE_TOP_K,
            min_score=_EVIDENCE_MIN_SCORE,
        )
        if not candidates:
            return "", []
        reranked = _reranker.rerank(
            query=query,
            candidates=candidates,
            top_k=_EVIDENCE_RERANK_TOP_K,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[partial] 节点证据检索失败，降级为无参考材料: %s", exc)
        return "", []

    chunk_ids = [str(getattr(item, "chunk_id", "") or "") for item in reranked]
    return format_evidence(reranked), [cid for cid in chunk_ids if cid]


def run_partial_pipeline(
    nodes: list[dict[str, Any]],
    target_node_ids: list[str],
    modify_action: str,
    modify_constraints: list[str],
    context_markdown: str,
    course_name: str,
    generator: NodeGenerator | None = None,
) -> list[dict[str, Any]]:
    """局部重生成：只改目标节点，其余原样保留。

    Args:
        nodes: 当前完整节点列表（含已有内容）
        target_node_ids: 需要重新生成的节点 ID
        modify_action: simplify / expand / rewrite / restyle / delete / add / reorder
        modify_constraints: 教师约束（来自 B5 解析结果）
        context_markdown: 课件级参考材料（S2 资料 / 前端 evidence packet 的合成文本），
                          与节点级检索结果合并后注入提示词
        course_name: 课件名

    Returns:
        更新后的完整节点列表（目标节点内容已重新生成，其余不变）
    """
    if not nodes:
        return []

    # restyle 不需要内容重生成——只改呈现层，由前端样式层处理
    if modify_action == "restyle":
        logger.info("[partial] restyle 动作不触发内容重生成，跳过")
        return nodes

    target_set = set(target_node_ids)
    gen = generator or NodeGenerator()

    # 局部重生成要基于知识库证据，而不是凭空重写。检索器只初始化一次，
    # 循环内按节点各自的查询词复用（store 在循环期间不会被写入）。
    # 目标节点一个都不在列表里时不必重建 BM25 索引。
    has_target = any(str(n.get("node_id") or "") in target_set for n in nodes)
    retriever = get_evidence_retriever() if has_target else None

    # 构建修改指令 prompt（按 action 差异化）
    action_prompts = {
        "simplify": "请精简该节点的内容：减少冗余文字、保留核心知识点，使表述更简洁有力。",
        "expand": "请扩充该节点的内容：在保留现有要点的基础上增加更多细节、案例或讲解。",
        "rewrite": "请重写该节点的讲稿内容：保持核心知识点不变，用更清晰的方式重新表述。",
        "delete": "",  # delete 在上层处理（从列表移除），不进入重生成
        "add": "",  # add 在上层处理（追加新节点），不进入重生成
        "reorder": "",  # reorder 在上层处理（换位），不进入重生成
    }

    base_prompt = action_prompts.get(modify_action, action_prompts["rewrite"])
    constraints_text = ""
    if modify_constraints:
        constraints_text = "\n教师要求：" + "；".join(modify_constraints)

    # 收集相邻节点上下文（保持逻辑连贯）
    def _get_neighbors(idx: int) -> tuple[dict | None, dict | None]:
        prev_node = nodes[idx - 1] if idx > 0 else None
        next_node = nodes[idx + 1] if idx < len(nodes) - 1 else None
        return prev_node, next_node

    updated = []
    for idx, node in enumerate(nodes):
        node_id = node.get("node_id", "")

        if node_id in target_set:
            # 局部重生成该节点
            prev_node, next_node = _get_neighbors(idx)
            context_parts = []
            if prev_node:
                context_parts.append(f"上一节：{prev_node.get('title', '')}")
            if next_node:
                context_parts.append(f"下一节：{next_node.get('title', '')}")
            neighbor_context = "\n".join(context_parts)

            modify_instruction = base_prompt
            if neighbor_context:
                modify_instruction += f"\n上下文：{neighbor_context}"
            if constraints_text:
                modify_instruction += constraints_text

            # 局部 RAG：按该节点自身的信息取证。上层传入的 context_markdown 是
            # 课件级材料，语义更宽，作为兜底与节点级证据一起带上。
            evidence_text, evidence_ids = retrieve_node_evidence(
                node_evidence_query(node), retriever
            )
            reference = "\n".join(
                part for part in ((context_markdown or "").strip(), evidence_text) if part
            )

            try:
                new_script = gen.generate_single(
                    node,
                    course_name=course_name,
                    extra_instruction=modify_instruction,
                    context_markdown=reference,
                )
                if isinstance(new_script, dict) and new_script.get("script"):
                    updated_node = dict(node)
                    updated_node["script"] = new_script.get("script", "")
                    # segments 缺失时不覆盖。前端 ModifyPanel 的契约是「缺失字段保留
                    # 当前 PPT 内容」，后端若发一个显式的 [] 反而会把分段清空。
                    # generate_single 现在恒带该字段，这里只兜住自定义 generator。
                    if "segments" in new_script:
                        updated_node["segments"] = new_script.get("segments") or []
                    # point_details 走与 segments 完全相同的口径：key 在就覆盖，缺席就
                    # 保留。generate_single 现在恒带该字段，这里只兜住自定义 generator。
                    # 不回写的话，教师改第 2 页时展开说明会停在旧内容上 —— 幻灯片上看
                    # 起来就是"改了等于没改"。
                    if "point_details" in new_script:
                        updated_node["point_details"] = new_script.get("point_details") or []
                    # 引用关系：原有 refs 全部保留，追加本次实际检索到的证据
                    # （去重保序）。否则内容已经改自新证据、引用却还指向旧资料，
                    # 证据追溯会对不上。与 main.py 的 /gen/modify 回填方式一致。
                    if evidence_ids:
                        updated_node["source_chunk_ids"] = list(dict.fromkeys([
                            *(updated_node.get("source_chunk_ids") or []),
                            *evidence_ids,
                        ]))
                    updated.append(updated_node)
                else:
                    updated.append(node)
            except Exception as exc:
                logger.warning("[partial] 节点 %s 重生成失败: %s", node_id, exc)
                updated.append(node)  # 失败时保留原内容
        else:
            # 非目标节点：原样保留，内容与引用关系不变
            updated.append(node)

    return updated
