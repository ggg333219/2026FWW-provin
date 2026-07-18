import json
import os
import re
from dataclasses import dataclass
from typing import Any
from dotenv import load_dotenv

try:
    from .qa import resolve_llm_base_url
except ImportError:
    from qa import resolve_llm_base_url

try:
    from .schema import (
        build_node_script_schema,
        build_stage1_markdown_schema,
        build_stage2_node_tree_schema,
        build_stage3_script_schema,
        build_enhanced_script_schema,
        normalize_stage2_nodes,
        normalize_stage3_scripts,
    )
except ImportError:
    from schema import (
        build_node_script_schema,
        build_stage1_markdown_schema,
        build_stage2_node_tree_schema,
        build_stage3_script_schema,
        build_enhanced_script_schema,
        normalize_stage2_nodes,
        normalize_stage3_scripts,
    )

load_dotenv()


@dataclass
class GenerationConfig:
    mode: str = "llm"  # 默认使用真实模型
    model: str = os.getenv("AI_MODEL", "qwen-turbo")
    temperature: float = 0.2
    max_content_chars: int = 3500


class LessonGenerator:
    """根据解析后的页级文本，生成讲稿与思维导图结构。"""

    def __init__(self, config: GenerationConfig | None = None):
        self.config = config or GenerationConfig(
            mode=os.getenv("AI_GEN_MODE", "llm"),
            model=os.getenv("AI_MODEL", "qwen-turbo"),
            temperature=float(os.getenv("AI_TEMPERATURE", "0.2")),
            max_content_chars=int(os.getenv("AI_MAX_CONTENT_CHARS", "3500")),
        )

    def generate(self, parsed_document: dict[str, Any]) -> dict[str, Any]:
        pages = parsed_document.get("parsed_pages", [])
        outputs: list[dict[str, Any]] = []

        for page_item in pages:
            page = page_item["page"]
            content = page_item["content"]
            generated = self._generate_llm(page, content)

            outputs.append(generated)

        return {
            "doc_id": parsed_document.get("doc_id"),
            "doc_name": parsed_document.get("doc_name"),
            "generator": {
                "mode": self.config.mode,
                "model": self.config.model,
                "temperature": self.config.temperature,
            },
            "lessons": outputs,
        }

    def generate_from_markdown(self, markdown: str, course_name: str | None = None) -> dict[str, Any]:
        normalized_markdown = self._prepare_content(markdown or "")
        if not normalized_markdown:
            normalized_markdown = "# 未命名课件\n\n- 内容为空"

        fallback = self._fallback_pipeline(normalized_markdown)

        try:
            client = self._build_llm_client()

            stage1 = self._run_stage1_markdown_understanding(client, normalized_markdown)
            stage1_markdown = str(stage1.get("normalized_markdown") or normalized_markdown).strip() or normalized_markdown
            stage1_points = [str(item).strip() for item in (stage1.get("key_points") or []) if str(item).strip()]

            stage2_nodes = self._run_stage2_node_tree(client, stage1_markdown, stage1_points)
            if not stage2_nodes:
                stage2_nodes = fallback["node_tree"]["nodes"]

            stage3_scripts = self._run_stage3_scripts(client, stage1_markdown, stage2_nodes, course_name)
            if not stage3_scripts:
                stage3_scripts = fallback["scripts"]

            node_ids = {item["node_id"] for item in stage2_nodes}
            cleaned_scripts = normalize_stage3_scripts(stage3_scripts, node_ids)
            if not cleaned_scripts:
                cleaned_scripts = normalize_stage3_scripts(fallback["scripts"], node_ids)

            return {
                "course_name": course_name or "未命名课程",
                "source_markdown": stage1_markdown,
                "key_points": stage1_points,
                "node_tree": {"nodes": stage2_nodes},
                "scripts": cleaned_scripts,
                "used_fallback": False,
            }
        except Exception as error:
            result = dict(fallback)
            result["generation_error"] = str(error)
            result["used_fallback"] = True
            return result

    def generate_from_markdown_enhanced(self, markdown: str, course_name: str | None = None) -> dict[str, Any]:
        normalized_markdown = self._prepare_content(markdown or "")
        if not normalized_markdown:
            normalized_markdown = "# 未命名课件\n\n- 内容为空"
        fallback = self._fallback_pipeline(normalized_markdown)
        enhanced = self._build_enhanced_fallback(normalized_markdown)
        try:
            client = self._build_llm_client()
            stage1 = self._run_stage1_markdown_understanding(client, normalized_markdown)
            stage1_md = str(stage1.get("normalized_markdown") or normalized_markdown).strip() or normalized_markdown
            stage1_points = [str(item).strip() for item in (stage1.get("key_points") or []) if str(item).strip()]
            stage2_nodes = self._run_stage2_node_tree(client, stage1_md, stage1_points)
            if not stage2_nodes:
                stage2_nodes = fallback["node_tree"]["nodes"]
            enhanced_scripts = self._run_stage3_enhanced_scripts(client, stage1_md, stage2_nodes, course_name)
            if not enhanced_scripts:
                enhanced_scripts = enhanced["scripts"]
            node_ids = {item["node_id"] for item in stage2_nodes}
            cleaned = self._normalize_enhanced_scripts(enhanced_scripts, node_ids)
            if not cleaned:
                cleaned = enhanced["scripts"]
            return {
                "course_name": course_name or "未命名课程",
                "source_markdown": stage1_md,
                "key_points": stage1_points,
                "node_tree": {"nodes": stage2_nodes},
                "scripts": cleaned,
                "use_enhanced_schema": True,
                "used_fallback": False,
            }
        except Exception as error:
            result = dict(enhanced)
            result["generation_error"] = str(error)
            result["used_fallback"] = True
            return result

    def _run_stage3_enhanced_scripts(self, client, markdown: str, nodes: list, course_name: str | None) -> list:
        system_prompt = (
            "你是课堂讲稿生成助手（增强版）。只输出JSON。\n"
            "格式: {\"scripts\": [{\"node_id\":\"...\",\"title\":\"...\",\"script\":\"...\",\"segments\":[...]}]}\n\n"
            "每个segment必须包含:\n"
            "  - segment_id, text, node_id (必填)\n"
            "  - segment_type: opening/exclamation/example/interaction/transition/summary (必填)\n"
            "  - estimated_seconds: 整数15-120 (必填)\n"
            "  - interaction_hint: 具体教师话术 (必填)\n"
            "  - knowledge_card: {\"term\":\"术语\",\"definition\":\"定义\",\"formula\":\"公式或空串\",\"tags\":[\"标签\"]} (必填)\n"
            "  - difficulty: easy/medium/hard (必填)\n"
            "使用节点树中的node_id值，不要编造。"
        )
        user_prompt = (
            f"课程名: {course_name or '未命名课程'}\n原始MD:\n{markdown}\n\n节点树:\n{json.dumps(nodes, ensure_ascii=False)}\n\n"
            "每个节点至少2-4个segments: 开场->讲解->互动->过渡。node_id必须用节点树中的值。"
        )
        raw = self._request_llm_payload(client, system_prompt, user_prompt)
        with open("/tmp/enhanced_raw.json", "w") as f:
            f.write(raw)
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

    @staticmethod
    def _resolve_seg_node_id(seg, node_id: str, valid_node_ids: set) -> str:
        raw = str((seg or {}).get("node_id") or "").strip()
        if not raw:
            raw_arr = (seg or {}).get("node_ids") or []
            if raw_arr:
                raw = str(raw_arr[0]).strip()
        if not raw or raw not in valid_node_ids:
            raw = node_id
        return raw

    @staticmethod
    def _resolve_script_node_id(item, valid_node_ids: set) -> str:
        raw = str((item or {}).get("node_id") or "").strip()
        if not raw:
            raw_arr = (item or {}).get("node_ids") or []
            if raw_arr:
                raw = str(raw_arr[0]).strip()
        if raw in valid_node_ids:
            return raw
        if valid_node_ids:
            return sorted(valid_node_ids)[0]
        return "node_unknown"

    @staticmethod
    def _normalize_enhanced_scripts(scripts: list, valid_node_ids: set) -> list:
        _resolve_script_node_id = __class__._resolve_script_node_id
        _resolve_seg_node_id = __class__._resolve_seg_node_id
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
                seg_nid = _resolve_seg_node_id(seg, node_id, valid_node_ids)
                seg_type = str((seg or {}).get("segment_type") or "explanation").strip()
                est_sec = int((seg or {}).get("estimated_seconds") or 30)
                segments.append({
                    "segment_id": seg_id, "text": text, "node_id": seg_nid,
                    "segment_type": seg_type, "estimated_seconds": est_sec,
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
                "script": script_text,
                "segments": segments,
            })
        return normalized

    def _build_enhanced_fallback(self, markdown: str) -> dict:
        fallback = self._fallback_pipeline(markdown)
        scripts = []
        for idx, node in enumerate(fallback["node_tree"]["nodes"], start=1):
            nid = node["node_id"]
            title = node["title"]
            st = f"讲解节点 {nid}：{title}。"
            scripts.append({
                "node_id": nid, "title": title, "script": st,
                "segments": [{
                    "segment_id": f"seg_{idx}_1", "text": st, "node_id": nid,
                    "segment_type": "explanation", "estimated_seconds": 45,
                    "difficulty": "medium",
                    "interaction_hint": f"提问：你对{title}有什么理解？",
                    "knowledge_card": {"term": title, "definition": f"关于{title}的核心知识", "formula": "", "tags": ["core"]},
                }],
            })
        return {
            "course_name": fallback.get("course_name", "未命名课程"),
            "source_markdown": fallback.get("source_markdown", markdown),
            "key_points": fallback.get("key_points", []),
            "node_tree": fallback.get("node_tree", {"nodes": []}),
            "scripts": scripts, "use_enhanced_schema": True,
            "generation_error": "enhanced_fallback", "used_fallback": True,
        }

    def _generate_llm(self, page: int, content: str) -> dict[str, Any]:
        normalized_content = self._prepare_content(content)
        outline = self._build_outline(normalized_content)

        system_prompt = (
            "你是高校教师讲稿生成助手。"
            "你的任务是把课件页面内容改写成可直接讲授的中文讲稿。"
            "必须准确覆盖原文关键信息，不要编造课件中不存在的结论、数据或公式。"
            "输出只能是 JSON 对象，且只包含 script 与 mindmap_markdown 两个字段。"
        )
        user_prompt = (
            f"页面: {page}\n"
            f"原始内容:\n{normalized_content}\n\n"
            f"提炼要点:\n{outline}\n\n"
            "请生成：\n"
            "1. script: 220-420 字，口语化、按老师上课讲述方式展开，包含开场点题、核心解释、必要举例和本页收束。\n"
            "2. mindmap_markdown: 使用 Markdown 列表，第一行为本页主题，下面给出 3-6 个要点分支。\n"
            "如果原始内容较少，优先解释已有信息，不要用空泛套话补字数。\n"
            "请返回 JSON: {\"script\": \"...\", \"mindmap_markdown\": \"...\"}"
        )

        try:
            client = self._build_llm_client()
            raw_content = self._request_llm_payload(client, system_prompt, user_prompt)
            data = self._extract_json(raw_content)
            return {
                "page": page,
                "script": self._clean_generated_text(data.get("script")) or self._fallback_script(page, normalized_content),
                "mindmap_markdown": self._clean_generated_text(data.get("mindmap_markdown")) or self._fallback_mindmap(page, normalized_content),
                "source_excerpt": normalized_content[:120].strip(),
            }
        except Exception as e:
            return self._fallback_generation(page, normalized_content, str(e))

    def generate_node_script(self, teaching_node: dict[str, Any], course_name: str | None = None) -> dict[str, Any]:
        node_id = str(teaching_node.get("node_id") or "node_unknown")
        title = str(teaching_node.get("title") or "未命名节点")
        core_points = teaching_node.get("core_points") or []
        examples = teaching_node.get("examples") or []
        confusions = teaching_node.get("common_confusions") or []
        summary = str(teaching_node.get("summary") or "")

        assembled_content = "\n".join(
            [
                title,
                summary,
                *[f"要点：{item}" for item in core_points],
                *[f"例子：{item}" for item in examples],
                *[f"易错点：{item}" for item in confusions],
            ]
        ).strip()

        fallback = self._fallback_node_script(node_id, title, summary, core_points, examples, confusions)

        try:
            client = self._build_llm_client()
            system_prompt = (
                "你是高校课程智能讲授编排助手。"
                "请根据讲授节点信息生成适合互动式课堂的讲授内容。"
                "输出严格 JSON。"
                "必须包含 script、mindmap_markdown、interactive_questions、reteach_script、transition。"
                "可选包含 structured_markdown、knowledge_nodes、script_segments。"
            )
            user_prompt = (
                f"课程名: {course_name or '未提供'}\n"
                f"节点标题: {title}\n"
                f"节点摘要: {summary}\n"
                f"核心要点: {json.dumps(core_points, ensure_ascii=False)}\n"
                f"示例: {json.dumps(examples, ensure_ascii=False)}\n"
                f"易错点: {json.dumps(confusions, ensure_ascii=False)}\n"
                f"补充内容: {assembled_content}\n"
                "请输出适合老师直接讲授、并支持后续追问的结果。\n"
                "要求：\n"
                "1) script 语言要像真实教师课堂讲解，不要机械罗列。\n"
                "2) structured_markdown 需包含标题、要点、公式占位（如有）、图表说明占位（如有）。\n"
                "3) knowledge_nodes 至少包含当前节点，并给出 level/tags/prerequisites/difficulty/coverage_span。\n"
                "4) script_segments 用于段落映射，每段包含 segment_id/text/node_ids/confidence/manual_override。\n"
                "5) 若信息不足，可简化可选字段，但必须返回合法 JSON。"
            )
            raw_content = self._request_llm_payload(client, system_prompt, user_prompt)
            data = self._extract_json(raw_content)
            script = self._clean_generated_text(data.get("script")) or fallback["script"]
            return build_node_script_schema(
                node_id=node_id,
                title=title,
                script=script,
                mindmap_markdown=self._clean_generated_text(data.get("mindmap_markdown")) or fallback["mindmap_markdown"],
                interactive_questions=data.get("interactive_questions") or fallback["interactive_questions"],
                reteach_script=self._clean_generated_text(data.get("reteach_script")) or fallback["reteach_script"],
                transition=self._clean_generated_text(data.get("transition")) or fallback["transition"],
                structured_markdown=self._clean_generated_text(data.get("structured_markdown")),
                knowledge_nodes=data.get("knowledge_nodes") or [],
                script_segments=data.get("script_segments") or self._build_segments_from_script(script, node_id),
            )
        except Exception:
            return fallback

    def _build_llm_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("当前环境缺少 openai 依赖，请先安装 requirements.txt 后重试。") from error

        api_key = os.getenv("AI_API_KEY")
        if not api_key:
            raise RuntimeError("缺少环境变量 AI_API_KEY，无法调用大模型。")

        base_url, _ = resolve_llm_base_url(self.config.model)
        return OpenAI(api_key=api_key, base_url=base_url)

    def _request_llm_payload(self, client: Any, system_prompt: str, user_prompt: str, json_schema: dict[str, Any] | None = None) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            if json_schema:
                response = client.chat.completions.create(
                    model=self.config.model,
                    temperature=self.config.temperature,
                    messages=messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": json_schema,
                    },
                )
            else:
                response = client.chat.completions.create(
                    model=self.config.model,
                    temperature=self.config.temperature,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
        except Exception:
            try:
                response = client.chat.completions.create(
                    model=self.config.model,
                    temperature=self.config.temperature,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
            except Exception:
                response = client.chat.completions.create(
                    model=self.config.model,
                    temperature=self.config.temperature,
                    messages=messages,
                )

        return response.choices[0].message.content or ""

    def _prepare_content(self, content: str) -> str:
        normalized = re.sub(r"\n{3,}", "\n\n", (content or "").strip())
        if len(normalized) <= self.config.max_content_chars:
            return normalized

        head = normalized[: int(self.config.max_content_chars * 0.7)].strip()
        tail = normalized[-int(self.config.max_content_chars * 0.2) :].strip()
        return f"{head}\n\n[中间内容已截断，保留首尾关键信息]\n\n{tail}".strip()

    def _build_outline(self, content: str) -> str:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return "- 本页缺少可用文本，需基于标题或截图补充信息"

        outline_lines: list[str] = []
        for line in lines[:6]:
            candidate = re.sub(r"^[\-•*\d.、\s]+", "", line)
            if candidate:
                outline_lines.append(f"- {candidate[:80]}")

        return "\n".join(outline_lines) if outline_lines else "- 本页内容较少，请围绕现有文本讲解"

    @staticmethod
    def _clean_generated_text(value: Any) -> str:
        return re.sub(r"\n{3,}", "\n\n", str(value or "").strip())

    def _fallback_generation(self, page: int, content: str, error_message: str) -> dict[str, Any]:
        return {
            "page": page,
            "script": self._fallback_script(page, content),
            "mindmap_markdown": self._fallback_mindmap(page, content),
            "source_excerpt": content[:120].strip(),
            "generation_error": error_message,
            "used_fallback": True,
        }

    def _fallback_script(self, page: int, content: str) -> str:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        title = lines[0] if lines else f"第{page}页内容"
        key_points = [re.sub(r"^[\-•*\d.、\s]+", "", line) for line in lines[1:4]]
        key_points = [item for item in key_points if item]

        segments = [f"这一页我们先抓住“{title}”这个主题。"]
        if key_points:
            segments.append("重点有：" + "；".join(key_points) + "。")
        segments.append("讲解时可以先说明概念，再结合课堂中的典型场景或例子帮助学生建立理解。")
        segments.append("最后要把本页结论和上一页、下一页的逻辑关系串起来，方便学生形成完整知识链。")
        return "".join(segments)

    def _fallback_mindmap(self, page: int, content: str) -> str:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        title = lines[0] if lines else f"第{page}页主题"
        children = lines[1:5] if len(lines) > 1 else ["核心概念", "关键解释", "课堂例子", "本页总结"]
        rows = [f"- {title}"]
        for item in children:
            cleaned = re.sub(r"^[\-•*\d.、\s]+", "", item).strip()
            if cleaned:
                rows.append(f"  - {cleaned}")
        return "\n".join(rows)

    def _fallback_node_script(
        self,
        node_id: str,
        title: str,
        summary: str,
        core_points: list[str],
        examples: list[str],
        confusions: list[str],
    ) -> dict[str, Any]:
        details = "；".join(core_points[:3]) if core_points else summary or title
        example_text = examples[0] if examples else f"可以结合 {title} 的典型应用场景帮助学生理解。"
        reteach_focus = confusions[0] if confusions else f"重新解释 {title} 的核心概念"
        script = (
            f"这一部分我们围绕“{title}”来讲。"
            f"先抓住几个关键点：{details}。"
            f"讲到这里时，可以用“{example_text}”作为课堂例子，让学生把抽象概念和真实情境对应起来。"
            "最后再回到本节点结论，帮助学生形成完整理解。"
        )
        mindmap = "\n".join([f"- {title}"] + [f"  - {item}" for item in (core_points[:4] or [summary or "核心内容"])])
        interactive_questions = [
            f"你觉得“{title}”最关键的点是什么？",
            f"如果把“{title}”放到真实场景里，它会怎么用？",
            f"你现在最不确定的是哪一步？",
        ]
        reteach_script = f"如果你还没完全听懂，我们就换个角度重讲，重点放在：{reteach_focus}。"
        transition = f"理解完“{title}”之后，我们就可以继续进入下一个知识节点。"
        structured_markdown = "\n".join(
            [
                f"# {title}",
                "",
                "## 核心要点",
                *[f"- {point}" for point in (core_points[:4] or [summary or "核心内容"])],
                "",
                "## 课堂讲解提示",
                f"- 示例：{example_text}",
                f"- 易错点：{reteach_focus}",
            ]
        )
        return build_node_script_schema(
            node_id,
            title,
            script,
            mindmap,
            interactive_questions,
            reteach_script,
            transition,
            structured_markdown=structured_markdown,
            knowledge_nodes=[
                {
                    "node_id": node_id,
                    "parent_id": "",
                    "level": 1,
                    "title": title,
                    "tags": ["core"],
                    "prerequisites": [],
                    "difficulty": "medium",
                    "coverage_span": ["seg_1"],
                }
            ],
            script_segments=self._build_segments_from_script(script, node_id),
        )

    @staticmethod
    def _build_segments_from_script(script: str, node_id: str) -> list[dict[str, Any]]:
        text = (script or "").strip()
        if not text:
            return []

        rough_segments = [seg.strip() for seg in re.split(r"(?<=[。！？])", text) if seg.strip()]
        if not rough_segments:
            rough_segments = [text]

        segments: list[dict[str, Any]] = []
        for idx, seg in enumerate(rough_segments, start=1):
            segments.append(
                {
                    "segment_id": f"seg_{idx}",
                    "text": seg,
                    "node_ids": [node_id],
                    "confidence": 0.8,
                    "manual_override": False,
                }
            )
        return segments

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
        return json.loads(cleaned[start : end + 1])

    def _run_stage1_markdown_understanding(self, client: Any, markdown: str) -> dict[str, Any]:
        system_prompt = (
            "你是课件结构化预处理助手。"
            "请保留原始语义，提炼可用于后续节点划分的关键信息。"
            "输出必须严格符合给定 JSON Schema。"
        )
        user_prompt = (
            f"输入课件 Markdown:\n{markdown}\n\n"
            "请输出：\n"
            "1) normalized_markdown：整理后的 Markdown（不改结论、不编造）\n"
            "2) key_points：5-12条关键点"
        )
        raw = self._request_llm_payload(client, system_prompt, user_prompt, json_schema=build_stage1_markdown_schema())
        data = self._extract_json(raw)
        return {
            "normalized_markdown": str(data.get("normalized_markdown") or "").strip(),
            "key_points": [str(item).strip() for item in (data.get("key_points") or []) if str(item).strip()],
        }

    def _run_stage2_node_tree(self, client: Any, markdown: str, key_points: list[str]) -> list[dict[str, Any]]:
        system_prompt = (
            "你是教学设计助手。"
            "任务是把课件 Markdown 划分为可讲授的知识节点树。"
            "输出必须严格符合给定 JSON Schema，并且每个节点都必须有 node_id。"
        )
        user_prompt = (
            f"课件 Markdown:\n{markdown}\n\n"
            f"关键点:\n{json.dumps(key_points, ensure_ascii=False)}\n\n"
            "请输出 nodes 数组，每个节点包含 node_id/title/summary/source_span/prerequisites。"
            "node_id 必须稳定、可读，例如 node_001。"
        )
        raw = self._request_llm_payload(client, system_prompt, user_prompt, json_schema=build_stage2_node_tree_schema())
        data = self._extract_json(raw)
        return normalize_stage2_nodes(data.get("nodes") or [])

    def _run_stage3_scripts(
        self,
        client: Any,
        markdown: str,
        nodes: list[dict[str, Any]],
        course_name: str | None,
    ) -> list[dict[str, Any]]:
        system_prompt = (
            "你是课堂讲稿生成助手。"
            "请严格按节点输出可直接讲授的脚本，每条脚本必须绑定 node_id。"
            "输出必须严格符合给定 JSON Schema。"
        )
        user_prompt = (
            f"课程名: {course_name or '未命名课程'}\n"
            f"原始 Markdown:\n{markdown}\n\n"
            f"节点树:\n{json.dumps(nodes, ensure_ascii=False)}\n\n"
            "请输出 scripts 数组；每个元素包含 node_id/title/script/segments。"
            "segments 中每一段必须给 segment_id/text/node_id。"
        )
        raw = self._request_llm_payload(client, system_prompt, user_prompt, json_schema=build_stage3_script_schema())
        data = self._extract_json(raw)
        node_ids = {item["node_id"] for item in nodes}
        return normalize_stage3_scripts(data.get("scripts") or [], node_ids)

    def _fallback_pipeline(self, markdown: str) -> dict[str, Any]:
        lines = [line.strip() for line in (markdown or "").splitlines() if line.strip()]
        headings = [line.lstrip("# ").strip() for line in lines if line.startswith("#")]
        if not headings:
            headings = ["课件主题", "核心概念", "总结过渡"]

        nodes: list[dict[str, Any]] = []
        scripts: list[dict[str, Any]] = []
        for idx, title in enumerate(headings, start=1):
            node_id = f"node_{idx:03d}"
            summary = f"围绕“{title}”进行讲授。"
            node = {
                "node_id": node_id,
                "title": title,
                "summary": summary,
                "source_span": title,
                "prerequisites": [f"node_{idx - 1:03d}"] if idx > 1 else [],
            }
            script_text = (
                f"接下来讲解节点 {node_id}：{title}。"
                f"这一段重点是：{summary}"
                "请同学们先理解定义，再结合一个具体场景进行应用。"
            )
            scripts.append(
                {
                    "node_id": node_id,
                    "title": title,
                    "script": script_text,
                    "segments": [
                        {
                            "segment_id": f"seg_{idx}_1",
                            "text": script_text,
                            "node_id": node_id,
                        }
                    ],
                }
            )
            nodes.append(node)

        return {
            "course_name": "未命名课程",
            "source_markdown": markdown,
            "key_points": headings[:8],
            "node_tree": {"nodes": nodes},
            "scripts": scripts,
            "used_fallback": True,
        }
