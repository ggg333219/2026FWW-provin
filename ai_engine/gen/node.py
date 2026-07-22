"""
节点生成模块 — S3 课件生成的第二步

职责：
  大纲节点 → LLM 逐节点生成讲稿内容（可并行）

流程：
  节点树 → [GENERATING] → 每个节点产出 script / segments / interactive_questions

现有基础：
  从 generator.py 的 generate_node_script / _run_stage3_scripts 重构而来
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from ..schema import build_stage3_script_schema, normalize_stage3_scripts, build_enhanced_script_schema


@dataclass
class NodeGenConfig:
    """节点生成配置"""
    model: str = ""
    temperature: float = 0.2
    max_content_chars: int = 3500


class NodeGenerator:
    """根据节点树逐节点生成讲稿内容"""

    def __init__(self, config: NodeGenConfig | None = None):
        self.config = config or NodeGenConfig()

    # ── 公开入口 ──

    def generate_all(self, nodes: list[dict[str, Any]],
                     context_markdown: str = "",
                     course_name: str | None = None) -> dict[str, Any]:
        """生成所有节点的讲稿

        Args:
            nodes: 节点树（outline.py 产出的 nodes 列表）
            context_markdown: 原始上下文 Markdown
            course_name: 课程名称

        Returns:
            {"scripts": [...], "used_fallback": bool}
        """
        fallback = self._fallback_scripts(nodes, course_name)
        try:
            client = self._build_llm_client()
            scripts = self._run_batch_generation(client, context_markdown, nodes, course_name)
            if not scripts:
                scripts = fallback["scripts"]
            node_ids = {n["node_id"] for n in nodes}
            scripts = normalize_stage3_scripts(scripts, node_ids)
            return {"scripts": scripts or fallback["scripts"], "used_fallback": False}
        except Exception:
            return {"scripts": fallback["scripts"], "used_fallback": True}

    def generate_enhanced(self, nodes: list[dict[str, Any]],
                          context_markdown: str = "",
                          course_name: str | None = None) -> dict[str, Any]:
        """增强版生成：带 segment_type / estimated_seconds / interaction_hint / knowledge_card"""
        fallback = self._enhanced_fallback(nodes, course_name)
        try:
            client = self._build_llm_client()
            scripts = self._run_enhanced_batch(client, context_markdown, nodes, course_name)
            if not scripts:
                scripts = fallback["scripts"]
            node_ids = {n["node_id"] for n in nodes}
            scripts = self._normalize_enhanced_scripts(scripts, node_ids)
            return {"scripts": scripts or fallback["scripts"], "used_fallback": False}
        except Exception:
            return {"scripts": fallback["scripts"], "used_fallback": True}

    def generate_single(self, node: dict[str, Any], course_name: str | None = None) -> dict[str, Any]:
        """生成单个节点的讲稿（供 S4 修补时部分重生成使用）"""
        node_id = str(node.get("node_id") or "node_unknown")
        title = str(node.get("title") or "未命名节点")
        core_points = node.get("core_points") or []
        examples = node.get("examples") or []
        confusions = node.get("common_confusions") or []
        summary = str(node.get("summary") or "")

        fallback = self._single_fallback(node_id, title, summary, core_points, examples, confusions)
        try:
            client = self._build_llm_client()
            assembled = "\n".join([
                title, summary,
                *[f"要点: {item}" for item in core_points],
                *[f"例子: {item}" for item in examples],
                *[f"易错点: {item}" for item in confusions],
            ]).strip()
            system_prompt = (
                "你是高校课程智能讲授编排助手。"
                "请根据讲授节点信息生成适合互动式课堂的讲授内容。"
                "输出严格 JSON，必须包含 script / mindmap_markdown / interactive_questions / reteach_script / transition。"
            )
            user_prompt = (
                f"课程名: {course_name or '未提供'}\n"
                f"节点标题: {title}\n摘要: {summary}\n"
                f"核心要点: {json.dumps(core_points, ensure_ascii=False)}\n"
                f"示例: {json.dumps(examples, ensure_ascii=False)}\n"
                f"易错点: {json.dumps(confusions, ensure_ascii=False)}\n"
            )
            raw = self._request_llm(client, system_prompt, user_prompt)
            data = self._extract_json(raw)
            return {
                "node_id": node_id, "title": title,
                "script": self._clean_text(data.get("script")) or fallback["script"],
                "mindmap_markdown": self._clean_text(data.get("mindmap_markdown")) or fallback["mindmap_markdown"],
                "interactive_questions": data.get("interactive_questions") or fallback["interactive_questions"],
                "reteach_script": self._clean_text(data.get("reteach_script")) or fallback["reteach_script"],
                "transition": self._clean_text(data.get("transition")) or fallback["transition"],
            }
        except Exception:
            return fallback

    # ── 批量生成 ──

    def _run_batch_generation(self, client: OpenAI, markdown: str,
                              nodes: list[dict], course_name: str | None) -> list[dict]:
        system_prompt = "你是课堂讲稿生成助手。请严格按节点输出可直接讲授的脚本，每条脚本必须绑定 node_id。"
        user_prompt = (
            f"课程名: {course_name or '未命名课程'}\n"
            f"原始 Markdown:\n{markdown}\n\n"
            f"节点树:\n{json.dumps(nodes, ensure_ascii=False)}\n\n"
            "请输出 scripts 数组；每个元素包含 node_id/title/script/segments。"
        )
        raw = self._request_llm(client, system_prompt, user_prompt,
                                json_schema=build_stage3_script_schema())
        data = self._extract_json(raw)
        node_ids = {n["node_id"] for n in nodes}
        return normalize_stage3_scripts(data.get("scripts") or [], node_ids)

    def _run_enhanced_batch(self, client: OpenAI, markdown: str,
                            nodes: list[dict], course_name: str | None) -> list[dict]:
        system_prompt = (
            "你是课堂讲稿生成助手（增强版）。只输出JSON。\n"
            "格式: {\"scripts\": [{\"node_id\":\"...\",\"title\":\"...\",\"script\":\"...\",\"segments\":[...]}]}\n\n"
            "每个segment必须包含:\n"
            "  - segment_id, text, node_id (必填)\n"
            "  - segment_type: opening/exclamation/example/interaction/transition/summary (必填)\n"
            "  - estimated_seconds: 整数15-120 (必填)\n"
            "  - interaction_hint: 具体教师话术 (必填)\n"
            '  - knowledge_card: [term, definition, formula, tags] (必填)\n'
            "  - difficulty: easy/medium/hard (必填)\n"
            "使用节点树中的node_id值，不要编造。"
        )
        user_prompt = (
            f"课程名: {course_name or '未命名课程'}\n原始MD:\n{markdown}\n\n"
            f"节点树:\n{json.dumps(nodes, ensure_ascii=False)}\n\n"
            "每个节点至少2-4个segments: 开场->讲解->互动->过渡。node_id必须用节点树中的值。"
        )
        raw = self._request_llm(client, system_prompt, user_prompt,
                                json_schema=build_enhanced_script_schema())
        data = self._extract_json(raw)
        scripts = data if isinstance(data, list) else data.get("scripts") or []
        valid_ids = {n["node_id"] for n in nodes}
        valid_list = sorted(valid_ids)
        for idx, script in enumerate(scripts):
            raw_id = str(script.get("node_id") or "").strip()
            if raw_id in valid_ids:
                continue
            mapped = valid_list[idx] if idx < len(valid_list) else (valid_list[-1] if valid_list else None)
            if mapped:
                script["node_id"] = mapped
                for seg in script.get("segments") or []:
                    seg["node_id"] = mapped
        return scripts

    # ── LLM 客户端 ──

    def _build_llm_client(self) -> OpenAI:
        from ..qa import resolve_llm_base_url
        api_key = os.getenv("AI_API_KEY")
        if not api_key:
            raise RuntimeError("缺少环境变量 AI_API_KEY")
        model = self.config.model or os.getenv("AI_MODEL", "qwen-turbo")
        base_url, _ = resolve_llm_base_url(model)
        return OpenAI(api_key=api_key, base_url=base_url)

    def _request_llm(self, client: OpenAI, system_prompt: str, user_prompt: str,
                     json_schema: dict[str, Any] | None = None) -> str:
        model = self.config.model or os.getenv("AI_MODEL", "qwen-turbo")
        messages = [{"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}]
        try:
            if json_schema:
                resp = client.chat.completions.create(
                    model=model, temperature=self.config.temperature, messages=messages,
                    response_format={"type": "json_schema", "json_schema": json_schema})
            else:
                resp = client.chat.completions.create(
                    model=model, temperature=self.config.temperature, messages=messages,
                    response_format={"type": "json_object"})
        except Exception:
            resp = client.chat.completions.create(
                model=model, temperature=self.config.temperature, messages=messages)
        return resp.choices[0].message.content or ""

    # ── 兜底 ──

    def _fallback_scripts(self, nodes: list[dict], course_name: str | None) -> dict[str, Any]:
        """LLM 不可用时的兜底讲稿"""
        scripts = []
        for idx, node in enumerate(nodes, start=1):
            nid = node["node_id"]
            title = node["title"]
            summary = node.get("summary") or title
            script_text = f"接下来讲解节点 {nid}: {title}。这段重点是: {summary}。请同学们先理解概念，再结合实际场景加以应用。"
            scripts.append({
                "node_id": nid, "title": title, "script": script_text,
                "segments": [{"segment_id": f"seg_{idx}_1", "text": script_text, "node_id": nid}],
            })
        return {"scripts": scripts}

    def _enhanced_fallback(self, nodes: list[dict], course_name: str | None) -> dict[str, Any]:
        fallback = self._fallback_scripts(nodes, course_name)
        scripts = []
        for idx, node in enumerate(nodes, start=1):
            nid = node["node_id"]
            title = node["title"]
            st = f"讲解节点 {nid}: {title}。"
            scripts.append({
                "node_id": nid, "title": title, "script": st,
                "segments": [{
                    "segment_id": f"seg_{idx}_1", "text": st, "node_id": nid,
                    "segment_type": "explanation", "estimated_seconds": 45,
                    "difficulty": "medium", "interaction_hint": f"提问: 你对{title}有什么理解?",
                    "knowledge_card": {"term": title, "definition": f"关于{title}的核心知识",
                                       "formula": "", "tags": ["core"]},
                }],
            })
        return {"scripts": scripts}

    def _single_fallback(self, node_id: str, title: str, summary: str,
                         core_points: list, examples: list, confusions: list) -> dict:
        details = "; ".join(core_points[:3]) if core_points else summary or title
        example_text = examples[0] if examples else f"可以结合{title}的典型应用场景帮助学生理解。"
        script = (
            f"这一部分我们围绕「{title}」来讲。"
            f"先抓住几个关键点: {details}。"
            f"讲到这里时，可以用「{example_text}」作为课堂例子。"
            "最后再回到本节点结论，帮助学生形成完整理解。"
        )
        return {
            "node_id": node_id, "title": title, "script": script,
            "mindmap_markdown": f"- {title}",
            "interactive_questions": [f"你觉得「{title}」最关键的点是什么？"],
            "reteach_script": f"重新解释{title}的核心概念。",
            "transition": f"理解完「{title}」之后，进入下一个知识节点。",
        }

    # ── 工具 ──

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, count=1).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("未找到有效 JSON")
        return json.loads(cleaned[start: end + 1])

    @staticmethod
    def _clean_text(value: Any) -> str:
        return re.sub(r"\n{3,}", "\n\n", str(value or "").strip())

    @staticmethod
    def _normalize_enhanced_scripts(scripts: list, valid_node_ids: set) -> list:
        normalized = []
        for item in scripts or []:
            node_id = _resolve_script_node_id(item, valid_node_ids)
            if not node_id:
                continue
            segments = []
            for seg in (item or {}).get("segments") or []:
                seg_id = str((seg or {}).get("segment_id") or "").strip()
                text = str((seg or {}).get("text") or "").strip()
                if not seg_id or not text:
                    continue
                segments.append({
                    "segment_id": seg_id, "text": text,
                    "node_id": _resolve_seg_node_id(seg, node_id, valid_node_ids),
                    "segment_type": str((seg or {}).get("segment_type") or "explanation").strip(),
                    "estimated_seconds": int((seg or {}).get("estimated_seconds") or 30),
                    "difficulty": str((seg or {}).get("difficulty") or "medium").strip(),
                    "interaction_hint": str((seg or {}).get("interaction_hint") or "").strip(),
                    "knowledge_card": (seg or {}).get("knowledge_card") or {},
                })
            script_text = str((item or {}).get("script") or "").strip()
            if not script_text and segments:
                script_text = "".join(s["text"] for s in segments)
            normalized.append({
                "node_id": node_id,
                "title": str((item or {}).get("title") or node_id).strip() or node_id,
                "script": script_text, "segments": segments,
            })
        return normalized


def _resolve_script_node_id(item: dict, valid_node_ids: set) -> str:
    raw = str((item or {}).get("node_id") or "").strip()
    if not raw:
        arr = (item or {}).get("node_ids") or []
        if arr:
            raw = str(arr[0]).strip()
    if raw in valid_node_ids:
        return raw
    if valid_node_ids:
        return sorted(valid_node_ids)[0]
    return ""


def _resolve_seg_node_id(seg: dict, node_id: str, valid_node_ids: set) -> str:
    raw = str((seg or {}).get("node_id") or "").strip()
    if not raw:
        arr = (seg or {}).get("node_ids") or []
        if arr:
            raw = str(arr[0]).strip()
    if not raw or raw not in valid_node_ids:
        raw = node_id
    return raw
