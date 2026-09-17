"""
大纲构建模块 — S3 课件生成的第一步

职责：
  intent + evidence → 结构化大纲 → 节点树

流程：
  [INTENT_LOCKED] → [EVIDENCE_GATHERING] → [STRUCTURING] → 节点树

现有基础：
  从 generator.py 的 _run_stage2_node_tree / _fallback_pipeline 重构而来
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from ..schema import (
    DEFAULT_TOTAL_DURATION_MINUTES,
    build_stage2_node_tree_schema,
    extract_nodes_payload,
    normalize_duration_minutes,
    normalize_stage2_nodes,
    to_outline_contract_nodes,
)
from ..core.llm import LLMClient


@dataclass
class OutlineConfig:
    """大纲构建配置"""
    model: str = ""
    temperature: float = 0.2
    max_nodes: int = 20  # 节点上限


class OutlineBuilder:
    """从教师意图 + 证据包构建课件大纲与节点树"""

    def __init__(self, config: OutlineConfig | None = None, llm_client: Optional[LLMClient] = None):
        self.config = config or OutlineConfig()
        self._llm = llm_client  # 可注入，供测试用

    # ── 公开入口 ──

    def build(self, intent: dict[str, Any], evidence_packet: dict[str, Any] | None = None) -> dict[str, Any]:
        """主入口：intent + 证据 → 节点树

        Args:
            intent: 结构化意图（来自 S1），至少含 title / description / key_points
            evidence_packet: 知识库证据包（可选），含引用块列表

        Returns:
            {"nodes": [...], "used_fallback": bool}
        """
        # S1 意图使用 topic/knowledge_points 字段，而大纲生成器使用 title/description/key_points。
        # 这里做一次字段归一，避免 S1→S3 断链导致大纲退化为"未命名课件"空提示。
        intent = intent or {}
        title = str(intent.get("title") or intent.get("topic") or "未命名课件")
        description = str(intent.get("description") or intent.get("subtitle") or "")
        key_points = intent.get("key_points") or intent.get("knowledge_points") or []
        # 意图课时：决定节点时长均分基准；缺失时留 None，走每节点默认时长。
        total_duration = self._intent_duration_minutes(intent)
        evidence_text = self._format_evidence(evidence_packet)

        markdown = self._build_markdown_context(
            title, description, key_points, evidence_text, total_duration
        )
        fallback = self._fallback_outline(title, key_points, total_duration)

        try:
            nodes = self._run_node_tree_generation(markdown, key_points, total_duration)
            if not nodes:
                nodes = fallback["nodes"]
            return {"nodes": self._finalize(nodes, total_duration), "used_fallback": False}
        except Exception:
            return {"nodes": self._finalize(fallback["nodes"], total_duration), "used_fallback": True}

    def build_from_markdown(self, markdown: str, course_name: str | None = None) -> dict[str, Any]:
        """从已有 Markdown 构建节点树（兼容旧接口）"""
        # 无 intent 时没有课时来源，用默认总课时，保证输出仍可被 Go 大纲确认接受。
        total_duration = DEFAULT_TOTAL_DURATION_MINUTES
        fallback = self._fallback_outline(course_name or "未命名课程", None, total_duration)
        try:
            nodes = self._run_node_tree_generation(markdown, [], total_duration)
            if not nodes:
                nodes = fallback["nodes"]
<<<<<<< HEAD
            return {"nodes": nodes, "used_fallback": False}
        except Exception:
            return {"nodes": fallback["nodes"], "used_fallback": True}
=======
            return {"nodes": self._finalize(nodes, total_duration), "used_fallback": False}
        except Exception:
            return {"nodes": self._finalize(fallback["nodes"], total_duration), "used_fallback": True}
>>>>>>> origin/main

    def revise(self, nodes: list[dict[str, Any]], message: str) -> dict[str, Any]:
        """按教师指令生成修订候选；既有节点 ID 由服务边界强制保持稳定。"""
        system_prompt = (
            "你是教学大纲修改助手。只修改教师指令涉及的内容，输出完整 nodes 数组；"
            "不得生成讲稿正文。尽量保持节点顺序和 node_id。"
<<<<<<< HEAD
=======
            "每个节点必须输出 estimated_duration_minutes（单位分钟，必须是大于 0 的数字）；"
            "教师未要求调整时长的节点，沿用输入中的原时长。"
>>>>>>> origin/main
        )
        user_prompt = (
            f"当前大纲：\n{json.dumps(nodes, ensure_ascii=False)}\n\n"
            f"教师修改指令：{message}"
        )
        result = self._get_llm().chat_with_schema(
            system_prompt,
            user_prompt,
            build_stage2_node_tree_schema(),
            temperature=self.config.temperature,
        )
<<<<<<< HEAD
        # 类型容错：降级链③（纯 prompt 约束）下 LLM 可能直接返回顶层数组 [{...}]
        # 而非 {"nodes": [...]}；此前 result.get 对 list 崩溃（'list' object has no attribute 'get'）。
        if isinstance(result, dict):
            raw_nodes = result.get("nodes")
        else:
            raw_nodes = result
        revised = normalize_stage2_nodes(raw_nodes if isinstance(raw_nodes, list) else [])
        if not revised:
            revised = normalize_stage2_nodes(nodes)

        used_ids: set[str] = set()
        for index, node in enumerate(revised):
            if not isinstance(node, dict):
                continue
            prev = nodes[index] if index < len(nodes) else None
            if isinstance(prev, dict) and prev.get("node_id"):
                node["node_id"] = str(prev["node_id"])
=======
        raw_nodes = extract_nodes_payload(result)
        # 修订不带总课时做均分：优先沿用节点自带时长，只对缺失/非法值补默认，
        # 避免把教师手工调过的单节点时长抹平成平均分。
        revised = normalize_stage2_nodes(raw_nodes)
        if not revised:
            revised = normalize_stage2_nodes(nodes)

        # 保留原节点时长：LLM 未给出合法时长时，沿用原大纲同位置节点的时长。
        # 新增节点在 normalize_stage2_nodes 里已补 DEFAULT_NODE_DURATION_MINUTES。
        for index, node in enumerate(revised):
            llm_duration = None
            if index < len(raw_nodes) and isinstance(raw_nodes[index], dict):
                llm_duration = normalize_duration_minutes(
                    raw_nodes[index].get("estimated_duration_minutes")
                )
            if llm_duration is None and index < len(nodes) and isinstance(nodes[index], dict):
                llm_duration = normalize_duration_minutes(
                    nodes[index].get("estimated_duration_minutes")
                )
            if llm_duration is not None:
                node["estimated_duration_minutes"] = max(1, round(llm_duration))

        used_ids: set[str] = set()
        for index, node in enumerate(revised):
            if index < len(nodes) and nodes[index].get("node_id"):
                node["node_id"] = str(nodes[index]["node_id"])
>>>>>>> origin/main
            candidate = str(node.get("node_id") or f"node_{index + 1:03d}")
            while candidate in used_ids:
                candidate = f"node_{index + 1:03d}_{len(used_ids) + 1}"
            node["node_id"] = candidate
            used_ids.add(candidate)

<<<<<<< HEAD
        return {"nodes": revised, "change_summary": [message.strip() or "已按教师指令修订大纲"]}
=======
        return {
            "nodes": to_outline_contract_nodes(revised),
            "change_summary": [message.strip() or "已按教师指令修订大纲"],
        }
>>>>>>> origin/main

    # ── LLM 节点树生成 ──

    def _run_node_tree_generation(
        self,
        markdown: str,
        key_points: list[str],
        total_duration_minutes: float | None = None,
    ) -> list[dict[str, Any]]:
        """调用 LLM 从 markdown 生成节点树"""
        duration_rule = (
            "7. 每个节点必须输出 estimated_duration_minutes（单位：分钟），必须是大于 0 的数字；\n"
            f"   全节点时长之和应接近课程总时长 {int(total_duration_minutes)} 分钟。\n"
            if total_duration_minutes
            else "7. 每个节点必须输出 estimated_duration_minutes（单位：分钟），必须是大于 0 的数字。\n"
        )
        system_prompt = (
            "你是教学设计助手，负责将课件 Markdown 切分为结构化的可讲授节点树。\n"
            "【强制约束】\n"
            "1. 每个节点只需输出：node_id / title / node_type / summary / key_points（≤4条）/ estimated_duration_minutes。不要输出 source_span / prerequisites / segments / 讲稿正文——由后续管线生成。\n"
            "2. node_type 仅允许：slide（默认）| section（章节）| quiz（测验）| interactive（互动）| cover（封面）| divider（分隔）。\n"
            "3. title 最多 60 字符，summary 最多 60 字符，每个 key_point 最多 100 字符。\n"
            "4. node_id 格式：node_001 / node_002 …，必须与 title 含义相关，保持稳定。\n"
            "5. 仅当 Markdown 某段落明显为章节入口（## 开头且无详细内容）时才用 section 类型。\n"
            "6. 输出严格遵循 JSON Schema，additionalProperties=False，不得输出 schema 外字段。\n"
            + duration_rule
        )
        user_prompt = (
            f"课件 Markdown:\n{markdown}\n\n"
            f"关键点:\n{json.dumps(key_points, ensure_ascii=False)}\n\n"
            "请按上述约束输出 nodes 数组。node_id 示例：node_001 / node_002。\n"
            "每个节点的 key_points 从对应段落中提取 2-6 条核心要点。"
        )
        llm = self._get_llm()
        schema = build_stage2_node_tree_schema()
        result = llm.chat_with_schema(system_prompt, user_prompt, schema,
                                       temperature=self.config.temperature)
        # LLM 返回后仍统一归一化时长，不信任模型直接满足正数约束。
        return normalize_stage2_nodes(extract_nodes_payload(result), total_duration_minutes)

    def _get_llm(self) -> LLMClient:
        """获取 LLM 客户端（懒创建，支持注入）"""
        if self._llm is not None:
            return self._llm
        return LLMClient(temperature=self.config.temperature, model=self.config.model or None)

    # ── 工具方法 ──

    @staticmethod
    def _intent_duration_minutes(intent: dict[str, Any]) -> float | None:
        """从 intent 读取课时（分钟）；无合法值返回 None。

        S1 意图使用 duration_minutes，这里同时兼容历史/别名写法。
        """
        for key in ("duration_minutes", "estimated_duration_minutes", "duration"):
            value = normalize_duration_minutes((intent or {}).get(key))
            if value is not None:
                return value
        return None

    @staticmethod
    def _finalize(nodes: list[dict[str, Any]], total_duration_minutes: float | None) -> list[dict[str, Any]]:
        """统一出口：引擎归一化 + 收敛到 Go 大纲契约（node_type / summary / 时长）。"""
        return to_outline_contract_nodes(normalize_stage2_nodes(nodes, total_duration_minutes))

    @staticmethod
    def _build_markdown_context(title: str, description: str,
                                key_points: list[str], evidence_text: str,
                                total_duration_minutes: float | None = None) -> str:
        lines = [f"# {title}", ""]
        if total_duration_minutes:
            lines.append(f"课程总时长：{int(total_duration_minutes)} 分钟\n")
        if description:
            lines.append(f"{description}\n")
        if key_points:
            lines.append("## 关键点")
            for kp in key_points:
                lines.append(f"- {kp}")
            lines.append("")
        if evidence_text:
            lines.append("## 参考材料")
            lines.append(evidence_text)
        return "\n".join(lines)

    @staticmethod
    def _format_evidence(evidence_packet: dict[str, Any] | None) -> str:
        if not evidence_packet:
            return ""
        # 兼容两种字段名：
        #   KB 返回: "relevant_chunks" (EvidencePacket.model_dump())
        #   S3 期望: "chunks" (OutlineBuilder 旧约定)
        chunks = evidence_packet.get("chunks") or evidence_packet.get("relevant_chunks") or []
        lines = []
        for c in chunks[:10]:
            text = str(c.get("content") or "").strip()
            if text:
                lines.append(f"- {text[:200]}")
        return "\n".join(lines)

    def _fallback_outline(
        self,
        title: str,
        key_points: list[str] | None = None,
        total_duration_minutes: float | None = None,
    ) -> dict[str, Any]:
        """LLM 不可用时的兜底大纲。

        兜底结果同样要能通过 Go 大纲确认校验，因此显式写入正数时长并按课时分配；
        未提供课时时由 assign_node_durations 补每节点默认时长。
        """
        points = key_points or ["核心概念", "关键应用", "总结过渡"]
        nodes = []
        for idx, kp in enumerate(points[:self.config.max_nodes], start=1):
            node_id = f"node_{idx:03d}"
            nodes.append({
                "node_id": node_id,
                "title": kp,
                "summary": f"围绕「{kp}」进行讲授，结合定义、示例与常见误区。",
                "node_type": "slide",
                "source_span": kp,
                "prerequisites": [f"node_{idx - 1:03d}"] if idx > 1 else [],
            })
        return {"nodes": normalize_stage2_nodes(nodes, total_duration_minutes)}
