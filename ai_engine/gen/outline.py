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
from typing import Any

from openai import OpenAI

from ..schema import build_stage2_node_tree_schema, normalize_stage2_nodes


@dataclass
class OutlineConfig:
    """大纲构建配置"""
    model: str = ""
    temperature: float = 0.2
    max_nodes: int = 20  # 节点上限


class OutlineBuilder:
    """从教师意图 + 证据包构建课件大纲与节点树"""

    def __init__(self, config: OutlineConfig | None = None):
        self.config = config or OutlineConfig()

    # ── 公开入口 ──

    def build(self, intent: dict[str, Any], evidence_packet: dict[str, Any] | None = None) -> dict[str, Any]:
        """主入口：intent + 证据 → 节点树

        Args:
            intent: 结构化意图（来自 S1），至少含 title / description / key_points
            evidence_packet: 知识库证据包（可选），含引用块列表

        Returns:
            {"nodes": [...], "used_fallback": bool}
        """
        title = str(intent.get("title") or "未命名课件")
        description = str(intent.get("description") or "")
        key_points = intent.get("key_points") or []
        evidence_text = self._format_evidence(evidence_packet)

        markdown = self._build_markdown_context(title, description, key_points, evidence_text)
        fallback = self._fallback_outline(title, key_points)

        try:
            client = self._build_llm_client()
            nodes = self._run_node_tree_generation(client, markdown, key_points)
            if not nodes:
                nodes = fallback["nodes"]
            return {"nodes": nodes, "used_fallback": False}
        except Exception:
            return {"nodes": fallback["nodes"], "used_fallback": True}

    def build_from_markdown(self, markdown: str, course_name: str | None = None) -> dict[str, Any]:
        """从已有 Markdown 构建节点树（兼容旧接口）"""
        fallback = self._fallback_outline(course_name or "未命名课程")
        try:
            client = self._build_llm_client()
            nodes = self._run_node_tree_generation(client, markdown, [])
            if not nodes:
                nodes = fallback["nodes"]
            return {"nodes": nodes, "used_fallback": False}
        except Exception:
            return {"nodes": fallback["nodes"], "used_fallback": True}

    # ── LLM 节点树生成 ──

    def _run_node_tree_generation(self, client: OpenAI, markdown: str, key_points: list[str]) -> list[dict[str, Any]]:
        """调用 LLM 从 markdown 生成节点树"""
        system_prompt = (
            "你是教学设计助手。"
            "任务是把课件 Markdown 划分为可讲授的知识节点树。"
            "每个节点必须包含 node_id / title / summary / source_span / prerequisites。"
            "输出必须严格符合给定 JSON Schema。"
        )
        user_prompt = (
            f"课件 Markdown:\n{markdown}\n\n"
            f"关键点:\n{json.dumps(key_points, ensure_ascii=False)}\n\n"
            "请输出 nodes 数组。node_id 必须稳定、可读，例如 node_001。"
        )
        raw = self._request_llm_json(client, system_prompt, user_prompt,
                                     json_schema=build_stage2_node_tree_schema())
        data = self._extract_json(raw)
        return normalize_stage2_nodes(data.get("nodes") or [])

    # ── LLM 客户端 ──

    def _build_llm_client(self) -> OpenAI:
        from ..qa import resolve_llm_base_url
        import os
        api_key = os.getenv("AI_API_KEY")
        if not api_key:
            raise RuntimeError("缺少环境变量 AI_API_KEY，无法调用大模型。")
        model = self.config.model or os.getenv("AI_MODEL", "qwen-turbo")
        base_url, _ = resolve_llm_base_url(model)
        return OpenAI(api_key=api_key, base_url=base_url)

    def _request_llm_json(self, client: OpenAI, system_prompt: str, user_prompt: str,
                          json_schema: dict[str, Any] | None = None) -> str:
        from ..qa import resolve_llm_base_url
        import os
        model = self.config.model or os.getenv("AI_MODEL", "qwen-turbo")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            if json_schema:
                resp = client.chat.completions.create(
                    model=model, temperature=self.config.temperature,
                    messages=messages,
                    response_format={"type": "json_schema", "json_schema": json_schema},
                )
            else:
                resp = client.chat.completions.create(
                    model=model, temperature=self.config.temperature,
                    messages=messages, response_format={"type": "json_object"},
                )
        except Exception:
            resp = client.chat.completions.create(
                model=model, temperature=self.config.temperature,
                messages=messages,
            )
        return resp.choices[0].message.content or ""

    # ── 工具方法 ──

    @staticmethod
    def _build_markdown_context(title: str, description: str,
                                key_points: list[str], evidence_text: str) -> str:
        lines = [f"# {title}", ""]
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
        chunks = evidence_packet.get("chunks") or []
        lines = []
        for c in chunks[:10]:
            text = str(c.get("content") or "").strip()
            if text:
                lines.append(f"- {text[:200]}")
        return "\n".join(lines)

    def _fallback_outline(self, title: str, key_points: list[str] | None = None) -> dict[str, Any]:
        """LLM 不可用时的兜底大纲"""
        points = key_points or ["核心概念", "关键应用", "总结过渡"]
        nodes = []
        for idx, kp in enumerate(points[:self.config.max_nodes], start=1):
            node_id = f"node_{idx:03d}"
            nodes.append({
                "node_id": node_id,
                "title": kp,
                "summary": f"围绕「{kp}」进行讲授，结合定义、示例与常见误区。",
                "source_span": kp,
                "prerequisites": [f"node_{idx - 1:03d}"] if idx > 1 else [],
            })
        return {"nodes": nodes}

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, count=1).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("模型返回内容中未找到有效 JSON")
        return json.loads(cleaned[start: end + 1])
