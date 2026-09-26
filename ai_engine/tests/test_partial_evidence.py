"""局部重生成的证据链路测试 (test_partial_evidence.py)

覆盖 ai_engine/gen/partial_content.py 的局部 RAG：
  - 查询词由节点自身信息构造（不是课件级 topic）
  - 检到的知识块作为「参考材料」进提示词
  - 检索不可用时降级为无证据，而不是让局部修改整体失败

以及 ai_engine/gen/node.py 的 generate_single 承接 context_markdown。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_engine.core.schema import SearchResult
from ai_engine.gen import partial_content
from ai_engine.gen.partial_content import (
    format_evidence,
    node_evidence_query,
    retrieve_node_evidence,
    run_partial_pipeline,
)


# =============================================================================
# 1. 查询构造
# =============================================================================

def test_query_uses_node_own_fields() -> None:
    """查询词来自节点自身：标题 + 摘要 + 核心要点，而不是整篇课件的 topic。"""
    node = {
        "node_id": "node_2",
        "title": "冒泡排序",
        "summary": "相邻比较，逆序交换",
        "core_points": ["每轮确定一个最大值", "时间复杂度 O(n^2)"],
    }
    query = node_evidence_query(node)

    assert query.startswith("冒泡排序")
    assert "相邻比较" in query
    assert "时间复杂度 O(n^2)" in query
    assert query.count("；") == 3  # 4 段 → 3 个分隔符


def test_query_dedupes_and_truncates() -> None:
    """重复项去重且保序，超长截断，避免把查询词稀释掉。"""
    node = {"title": "冒泡排序", "summary": "冒泡排序", "core_points": ["X" * 400]}
    query = node_evidence_query(node)

    assert query.count("冒泡排序") == 1
    assert len(query) <= partial_content._EVIDENCE_QUERY_CHARS


def test_query_handles_dict_shaped_points() -> None:
    """要点是 dict 时取正文，而不是把整个 repr 塞进查询词。"""
    node = {"title": "快速排序", "core_points": [{"text": "分治思想"}, {"point": "基准选取"}]}
    query = node_evidence_query(node)

    assert "分治思想" in query
    assert "基准选取" in query
    assert "{" not in query


def test_query_empty_node_yields_empty_string() -> None:
    assert node_evidence_query({"node_id": "n1"}) == ""


# =============================================================================
# 2. 证据格式化 / 检索
# =============================================================================

def test_format_evidence_matches_outline_shape() -> None:
    """每条 `- 内容`，单条截断 —— 与 outline.py 的 _format_evidence 同形。"""
    results = [
        SearchResult(chunk_id="c1", content="冒泡排序每轮把最大值冒到末尾。"),
        SearchResult(chunk_id="c2", content="Y" * 500),
        SearchResult(chunk_id="c3", content="   "),  # 空白内容跳过
    ]
    text = format_evidence(results)

    assert text.startswith("- 冒泡排序")
    assert text.count("\n") == 1  # 两条有效内容
    assert len(text.splitlines()[1]) == 2 + partial_content._EVIDENCE_SNIPPET_CHARS


class _StubRetriever:
    """按查询词返回固定候选，并记录收到的查询。"""

    def __init__(self, candidates: list[SearchResult], boom: bool = False) -> None:
        self._candidates = candidates
        self._boom = boom
        self.queries: list[str] = []

    def search(self, query, top_k=5, min_score=0.6, **kwargs):
        self.queries.append(query)
        if self._boom:
            raise RuntimeError("检索后端挂了")
        return self._candidates


def test_retrieve_returns_text_and_chunk_ids(monkeypatch) -> None:
    from importlib import import_module

    # _reranker 在函数体内从 rag.router 惰性导入，所以要替换 router 的模块属性
    monkeypatch.setattr(import_module("ai_engine.rag.router"), "_reranker", _StubReranker())
    stub = _StubRetriever([SearchResult(chunk_id="chunk_a", content="冒泡排序的相邻比较规则")])

    text, ids = retrieve_node_evidence("冒泡排序", stub)

    assert ids == ["chunk_a"]
    assert "冒泡排序的相邻比较规则" in text
    assert stub.queries == ["冒泡排序"]


class _StubReranker:
    def rerank(self, query, candidates, top_k=5):
        return candidates[:top_k]


def test_retrieve_degrades_when_search_raises() -> None:
    """检索抛错 → 返回空证据，不向上抛 —— 局部修改不该因知识库挂掉而整体失败。"""
    text, ids = retrieve_node_evidence("冒泡排序", _StubRetriever([], boom=True))
    assert (text, ids) == ("", [])


def test_retrieve_no_retriever_or_query() -> None:
    assert retrieve_node_evidence("冒泡排序", None) == ("", [])
    assert retrieve_node_evidence("", _StubRetriever([])) == ("", [])


# =============================================================================
# 3. 管线端到端（打桩生成器，不调 LLM）
# =============================================================================

class _RecordingGenerator:
    """记录每次重生成的 extra_instruction 与 context_markdown。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_single(self, node, course_name=None, max_attempts=None,
                        extra_instruction="", context_markdown=""):
        self.calls.append({
            "node_id": node.get("node_id"),
            "extra_instruction": extra_instruction,
            "context_markdown": context_markdown,
        })
        return {**node, "script": f"重生成:{node.get('node_id')}", "segments": []}


@pytest.fixture()
def _stub_rag(monkeypatch):
    """把检索器与重排器都换成内存替身。"""
    from importlib import import_module

    retriever = _StubRetriever([SearchResult(chunk_id="chunk_a", content="冒泡排序的相邻比较规则")])
    monkeypatch.setattr(partial_content, "get_evidence_retriever", lambda: retriever)
    monkeypatch.setattr(import_module("ai_engine.rag.router"), "_reranker", _StubReranker())
    return retriever


_NODES = [
    {"node_id": "node_1", "title": "引言", "summary": "导入", "script": "原始1"},
    {"node_id": "node_2", "title": "冒泡排序", "summary": "相邻比较",
     "core_points": ["每轮确定最大值"], "script": "原始2"},
    {"node_id": "node_3", "title": "快速排序", "summary": "分治", "script": "原始3"},
]


def test_partial_injects_retrieved_evidence(_stub_rag) -> None:
    """目标节点拿到「参考材料」，非目标节点完全不受影响。"""
    gen = _RecordingGenerator()
    updated = run_partial_pipeline(
        nodes=[dict(n) for n in _NODES],
        target_node_ids=["node_2"],
        modify_action="expand",
        modify_constraints=["增加案例"],
        context_markdown="",
        course_name="排序算法",
        generator=gen,
    )

    assert [c["node_id"] for c in gen.calls] == ["node_2"], "只应重生成目标节点"
    assert "冒泡排序的相邻比较规则" in gen.calls[0]["context_markdown"]
    # 查询用的是该节点自己的字段
    assert _stub_rag.queries == ["冒泡排序；相邻比较；每轮确定最大值"]

    # 引用关系：原有 refs 保留，追加本次用上的证据
    assert updated[1]["script"] == "重生成:node_2"
    assert updated[1]["source_chunk_ids"] == ["chunk_a"]
    assert updated[0]["script"] == "原始1" and updated[2]["script"] == "原始3"


def test_partial_merges_course_level_context(_stub_rag) -> None:
    """课件级 context_markdown 与节点级证据合并后一起注入。"""
    gen = _RecordingGenerator()
    run_partial_pipeline(
        nodes=[dict(n) for n in _NODES],
        target_node_ids=["node_2"],
        modify_action="simplify",
        modify_constraints=[],
        context_markdown="课件级材料：本章讲排序",
        course_name="排序算法",
        generator=gen,
    )
    context = gen.calls[0]["context_markdown"]
    assert "课件级材料：本章讲排序" in context
    assert "冒泡排序的相邻比较规则" in context


def test_partial_keeps_existing_refs(_stub_rag) -> None:
    """已有 source_chunk_ids 不被覆盖，只做去重追加。"""
    nodes = [dict(n) for n in _NODES]
    nodes[1]["source_chunk_ids"] = ["chunk_old", "chunk_a"]

    gen = _RecordingGenerator()
    updated = run_partial_pipeline(
        nodes=nodes, target_node_ids=["node_2"], modify_action="rewrite",
        modify_constraints=[], context_markdown="", course_name="排序算法",
        generator=gen,
    )
    assert updated[1]["source_chunk_ids"] == ["chunk_old", "chunk_a"]


def test_partial_without_retriever_still_regenerates(monkeypatch) -> None:
    """知识库不可用时仍能局部重生成，只是不带参考材料。"""
    monkeypatch.setattr(partial_content, "get_evidence_retriever", lambda: None)
    gen = _RecordingGenerator()
    updated = run_partial_pipeline(
        nodes=[dict(n) for n in _NODES], target_node_ids=["node_2"],
        modify_action="rewrite", modify_constraints=[], context_markdown="",
        course_name="排序算法", generator=gen,
    )
    assert gen.calls[0]["context_markdown"] == ""
    assert updated[1]["script"] == "重生成:node_2"


def test_restyle_skips_regeneration(_stub_rag) -> None:
    gen = _RecordingGenerator()
    nodes = [dict(n) for n in _NODES]
    result = run_partial_pipeline(
        nodes=nodes, target_node_ids=["node_2"], modify_action="restyle",
        modify_constraints=[], context_markdown="", course_name="排序算法",
        generator=gen,
    )
    assert gen.calls == []
    assert result == nodes


def test_no_matching_target_skips_retriever_init(monkeypatch) -> None:
    """目标 id 都不在节点列表里时，不该白白重建 BM25 索引。"""
    def _explode():
        raise AssertionError("不应初始化检索器")

    monkeypatch.setattr(partial_content, "get_evidence_retriever", _explode)
    gen = _RecordingGenerator()
    updated = run_partial_pipeline(
        nodes=[dict(n) for n in _NODES], target_node_ids=["node_missing"],
        modify_action="rewrite", modify_constraints=[], context_markdown="",
        course_name="排序算法", generator=gen,
    )
    assert gen.calls == []
    assert len(updated) == 3


# =============================================================================
# 4. node.generate_single 承接 context_markdown
# =============================================================================

def test_generate_single_prompt_includes_context_and_stays_backward_compatible() -> None:
    """有参考材料时进 prompt；不传时 prompt 与旧版逐字相同。"""
    from ai_engine.gen.node import NodeGenerator

    captured: list[str] = []

    class _LLM:
        """只记录 prompt 的假客户端（NodeGenerator 支持 llm_client 注入）。"""

        def chat_json(self, system_prompt, user_prompt, temperature=None):
            captured.append(user_prompt)
            return {"script": "讲稿"}

    gen = NodeGenerator(llm_client=_LLM())
    node = {"node_id": "n1", "title": "冒泡排序", "summary": "相邻比较"}

    gen.generate_single(node, "排序算法", extra_instruction="精简")
    baseline = captured[-1]
    assert "【参考材料】" not in baseline

    gen.generate_single(node, "排序算法", extra_instruction="精简",
                        context_markdown="- 冒泡排序的相邻比较规则")
    with_context = captured[-1]

    assert "【参考材料】" in with_context
    assert "冒泡排序的相邻比较规则" in with_context
    # 旧内容一字不动，参考材料追加在末尾
    assert with_context.startswith(baseline)


# =============================================================================
# 5. generate_single 回传 segments（此前只回 script，导致局部修改清空分段）
# =============================================================================

class _PayloadLLM:
    """返回固定 JSON 的假客户端。"""

    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def chat_json(self, system_prompt, user_prompt, temperature=None):
        return self.payload


class _BoomLLM:
    def chat_json(self, system_prompt, user_prompt, temperature=None):
        raise RuntimeError("LLM 挂了")


_NODE = {"node_id": "n1", "title": "冒泡排序", "summary": "相邻比较"}


def _gen_with(payload: Any) -> Any:
    from ai_engine.gen.node import NodeGenerator

    return NodeGenerator(llm_client=_PayloadLLM(payload))


def test_generate_single_returns_normalized_segments() -> None:
    """模型给的 segments 必须回传 —— 局部重生成靠它落库。"""
    gen = _gen_with({
        "script": "讲稿正文",
        "segments": [{
            "segment_id": "seg_001", "text": "开场白", "node_id": "n1",
            "segment_type": "opening", "estimated_seconds": 30,
        }],
    })
    result = gen.generate_single(_NODE)

    assert result["script"] == "讲稿正文"
    assert len(result["segments"]) == 1
    seg = result["segments"][0]
    assert seg["segment_id"] == "seg_001"
    assert seg["text"] == "开场白"
    assert seg["segment_type"] == "opening"
    assert seg["estimated_seconds"] == 30


def test_generate_single_repairs_segment_ids_and_drops_garbage() -> None:
    """缺 id 补号、非 dict/空文本丢弃、node_id 用权威值覆盖、时长钳制。"""
    gen = _gen_with({
        "script": "讲稿",
        "segments": [
            {"text": "开场"},                                              # 缺 id → seg_001
            "不是 dict",                                                   # 跳过
            {"segment_id": "seg_009", "text": "   "},                      # 空文本 → 跳过
            {"segment_id": "自定义", "text": "讲解",
             "node_id": "模型瞎写的", "estimated_seconds": 999},            # 覆盖 + 钳制
        ],
    })
    segments = gen.generate_single(_NODE)["segments"]

    assert [s["segment_id"] for s in segments] == ["seg_001", "自定义"]
    assert all(s["node_id"] == "n1" for s in segments)
    assert segments[0]["segment_type"] == "explanation"   # 缺省类型
    assert segments[1]["estimated_seconds"] == 120        # 999 → 钳到上限
    assert all(isinstance(s["knowledge_card"], dict) for s in segments)


def test_generate_single_builds_script_from_segments_when_omitted() -> None:
    """prompt 约定 script = 各 segments.text 拼接；模型漏给 script 时补齐。"""
    gen = _gen_with({"segments": [{"text": "第一段"}, {"text": "第二段"}]})
    result = gen.generate_single(_NODE)

    assert result["script"] == "第一段第二段"


def test_generate_single_fallback_is_self_consistent() -> None:
    """LLM 整批失败走兜底时，script 与 segments 必须互相对得上。"""
    from ai_engine.gen.node import NodeGenerator

    gen = NodeGenerator(llm_client=_BoomLLM())
    result = gen.generate_single(_NODE)

    segments = result["segments"]
    assert segments, "兜底也必须带分段，否则预览的分段区块会空"
    assert result["script"] == "".join(s["text"] for s in segments)
    for index, seg in enumerate(segments, start=1):
        assert seg["segment_id"] == f"seg_{index:03d}"
        assert seg["node_id"] == "n1"
        assert seg["segment_type"]
        assert 15 <= seg["estimated_seconds"] <= 120


def test_generate_single_malformed_segments_do_not_mix_in_fallback() -> None:
    """模型给了 script 但 segments 全是脏数据 → 不回填兜底分段。

    否则预览里「讲授文本」是模型的、「分段」是罐头文本，各说各话比没有更糟。
    """
    gen = _gen_with({"script": "模型写的讲稿", "segments": ["脏", {"no_text": 1}]})
    result = gen.generate_single(_NODE)

    assert result["script"] == "模型写的讲稿"
    assert result["segments"] == []


def test_partial_lands_segments_on_target_node(_stub_rag) -> None:
    """局部重生成真的把新分段写回节点（前端 ModifyPanel 依赖这个字段存在）。"""
    class _SegmentGenerator:
        def generate_single(self, node, course_name=None, max_attempts=None,
                            extra_instruction="", context_markdown=""):
            return {**node, "script": "新讲稿", "segments": [
                {"segment_id": "seg_001", "text": "新开场", "node_id": node["node_id"]},
            ]}

    nodes = [dict(n) for n in _NODES]
    nodes[1]["segments"] = [{"segment_id": "seg_001", "text": "旧开场"}]

    updated = run_partial_pipeline(
        nodes=nodes, target_node_ids=["node_2"], modify_action="rewrite",
        modify_constraints=[], context_markdown="", course_name="排序算法",
        generator=_SegmentGenerator(),
    )
    assert updated[1]["segments"][0]["text"] == "新开场"
    assert updated[0].get("segments") is None  # 非目标节点不被动过


def test_partial_keeps_segments_when_generator_omits_field(_stub_rag) -> None:
    """generator 不返回 segments 字段时保留原分段，而不是清成空列表。"""
    class _NoSegmentGenerator:
        def generate_single(self, node, course_name=None, max_attempts=None,
                            extra_instruction="", context_markdown=""):
            return {"node_id": node["node_id"], "script": "只有讲稿"}

    nodes = [dict(n) for n in _NODES]
    nodes[1]["segments"] = [{"segment_id": "seg_001", "text": "原分段"}]

    updated = run_partial_pipeline(
        nodes=nodes, target_node_ids=["node_2"], modify_action="rewrite",
        modify_constraints=[], context_markdown="", course_name="排序算法",
        generator=_NoSegmentGenerator(),
    )
    assert updated[1]["script"] == "只有讲稿"
    assert updated[1]["segments"] == [{"segment_id": "seg_001", "text": "原分段"}]
