"""
⚠️ DEPRECATED — 此文件已废弃，请使用 ai_engine/gen/ 子包替代。

迁移指南:
  大纲构建     → gen.outline.OutlineBuilder
  节点生成     → gen.node.NodeGenerator
  PPT 导出     → gen.export_ppt.PPTExporter
  DOCX 导出    → gen.export_doc.DOCExporter
  预览渲染     → gen.preview.PreviewRenderer
  命令解析     → gen.commands.CommandParser
  节点修补     → gen.patch.NodePatcher
  互动内容     → gen.interactive.InteractiveBuilder

保留此文件仅为兼容旧代码调用，新代码禁止引用。
"""

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable
from dotenv import load_dotenv

try:
    from .qa import resolve_llm_base_url
except ImportError:
    from qa import resolve_llm_base_url

try:
    from .core.llm import extract_json, resolve_llm_timeout
    from .core.config import resolve_llm_gen_chunk_size, resolve_llm_gen_max_workers
except ImportError:  # 直接以脚本方式运行时的回退导入
    from core.llm import extract_json, resolve_llm_timeout
    from core.config import resolve_llm_gen_chunk_size, resolve_llm_gen_max_workers

try:
    from .schema import (
        build_node_script_schema,
        build_stage1_markdown_schema,
        build_stage2_node_tree_schema,
        build_stage3_script_schema,
        build_enhanced_script_schema,
        extract_list_payload,
        extract_nodes_payload,
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
        extract_list_payload,
        extract_nodes_payload,
        normalize_stage2_nodes,
        normalize_stage3_scripts,
    )

load_dotenv()


def format_evidence_for_prompt(evidence: dict[str, Any] | None) -> str:
    """把 S2 证据包格式化为 LLM prompt 的「知识库证据参考」段落。

    契约与前端 mockBackend 一致：EvidencePacket 含
    synthesized_context（LLM 综合摘要）与 relevant_chunks[].content（原始切片）。
    """
    if not evidence:
        return ""
    parts: list[str] = []
    synthesized = str(evidence.get("synthesized_context") or "").strip()
    if synthesized:
        parts.append(f"📋 证据上下文：{synthesized}")
    chunks = evidence.get("relevant_chunks") or []
    if isinstance(chunks, list):
        chunk_texts: list[str] = []
        for chunk in chunks:
            content = str((chunk or {}).get("content") or "").strip()
            if content:
                chunk_texts.append(content)
        if chunk_texts:
            parts.append("参考资料：")
            parts.extend(f"- {text}" for text in chunk_texts[:5])
    return "\n".join(parts).strip()


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

    def generate(self, parsed_document: dict[str, Any], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        pages = parsed_document.get("parsed_pages", [])
        outputs: list[dict[str, Any]] = []

        for page_item in pages:
            page = page_item["page"]
            content = page_item["content"]
            generated = self._generate_llm(page, content, evidence)

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

    def generate_from_markdown_enhanced(
        self,
        markdown: str,
        course_name: str | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
        preset_nodes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """增强版三阶段生成（向后兼容：progress_cb 为可选参数，旧调用点无需改动）。

        progress_cb: 可选回调，接收 (pct: float 0-100, message: str)。
        会在 Stage1 完成(55)、Stage2 完成(60)、每个 Stage3 分块完成(60→78 线性)时被调用；
        回调可能来自工作线程，实现方需自行保证线程安全，回调异常不会中断生成。

        Stage1 跳过优化：当输入 markdown「已规整」（长度 ≥300 字符且含 ≥2 个二级标题）
        时跳过 Stage1 LLM 清洗，原文直接进入 Stage2（省一次 LLM 调用约 50s）；
        跳过时立即触发 55 进度回调（消息标注“跳过”），保证进度单调不减。
        非规整输入保留原 Stage1 清洗路径。
        """
        normalized_markdown = self._prepare_content(markdown or "")
        if not normalized_markdown:
            normalized_markdown = "# 未命名课件\n\n- 内容为空"
        fallback = self._fallback_pipeline(normalized_markdown)
        enhanced = self._build_enhanced_fallback(normalized_markdown)
        try:
            client = self._build_llm_client()
            if preset_nodes:
                # 调用方已提供节点树（如 pipeline 的 outline 结果）：跳过 Stage1/Stage2，
                # 避免同一请求重复生成两套互不匹配的节点树（实测出现过 outline 8 节点、
                # 内部 Stage2 19 节点，多余节点的讲稿全部浪费且 node_id 对不上）。
                stage1_md = normalized_markdown
                stage1_points = self._derive_key_points_from_headings(stage1_md)
                stage2_nodes = preset_nodes
                self._notify_progress(progress_cb, 55.0, "复用调用方节点树（跳过 Stage1/Stage2）")
                self._notify_progress(progress_cb, 60.0, "节点树就绪（preset_nodes）")
            elif self._is_regular_markdown(normalized_markdown):
                # 规整输入：跳过 Stage1 清洗，原文直进 Stage2
                stage1_md = normalized_markdown
                stage1_points = self._derive_key_points_from_headings(stage1_md)
                self._notify_progress(progress_cb, 55.0, "Stage1 跳过（输入已规整，直接进入节点树构建）")
                stage2_nodes = self._run_stage2_node_tree(client, stage1_md, stage1_points)
                if not stage2_nodes:
                    stage2_nodes = fallback["node_tree"]["nodes"]
                self._notify_progress(progress_cb, 60.0, "Stage2 节点树构建完成")
            else:
                stage1 = self._run_stage1_markdown_understanding(client, normalized_markdown)
                stage1_md = str(stage1.get("normalized_markdown") or normalized_markdown).strip() or normalized_markdown
                stage1_points = [str(item).strip() for item in (stage1.get("key_points") or []) if str(item).strip()]
                self._notify_progress(progress_cb, 55.0, "Stage1 markdown 理解完成")
                stage2_nodes = self._run_stage2_node_tree(client, stage1_md, stage1_points)
                if not stage2_nodes:
                    stage2_nodes = fallback["node_tree"]["nodes"]
                self._notify_progress(progress_cb, 60.0, "Stage2 节点树构建完成")
            enhanced_scripts = self._run_stage3_enhanced_scripts(client, stage1_md, stage2_nodes, course_name, progress_cb)
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

    @staticmethod
    def _notify_progress(progress_cb: Callable[[float, str], None] | None, pct: float, message: str) -> None:
        """进度回调安全封装：回调缺失直接跳过，回调异常吞掉（进度上报绝不能打断生成）。"""
        if progress_cb is None:
            return
        try:
            progress_cb(float(pct), str(message or ""))
        except Exception:
            pass

    @staticmethod
    def _is_regular_markdown(markdown: str) -> bool:
        """判定 markdown 是否「已规整」可跳过 Stage1 清洗。

        标准：长度 ≥300 字符，且含 ≥2 个二级标题（'\n## '；
        文档以 '## ' 开头时该标题额外计入 1 次，避免漏判首标题）。
        判定在 _prepare_content 截断归一之后进行，与 Stage2 实际消费的文本一致。
        """
        if not markdown or len(markdown) < 300:
            return False
        h2_count = markdown.count("\n## ")
        if markdown.startswith("## "):
            h2_count += 1
        return h2_count >= 2

    @staticmethod
    def _derive_key_points_from_headings(markdown: str, limit: int = 8) -> list[str]:
        """跳过 Stage1 时从二级标题本地提取关键点（无 LLM 开销），供 Stage2 prompt 锚定。"""
        points: list[str] = []
        for line in (markdown or "").splitlines():
            stripped = line.strip()
            if not stripped.startswith("## "):
                continue
            title = stripped[3:].strip()
            if title and title not in points:
                points.append(title)
            if len(points) >= limit:
                break
        return points

    def _run_stage3_enhanced_scripts(
        self,
        client,
        markdown: str,
        nodes: list,
        course_name: str | None,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> list:
        """Stage3 讲稿生成（每节点粒度并行版）。

        将节点按 LLM_GEN_CHUNK_SIZE（默认 1 = 每块 1 个节点）切块，用
        ThreadPoolExecutor 以 LLM_GEN_MAX_WORKERS（默认 4）个 worker 并行调用 LLM；
        每块独立 client（规避 OpenAI 客户端并发隐患）、独立重试与失败语义：
        某块彻底失败只对该块节点降级为 fallback，不影响其他块。
        默认每节点一次 LLM 调用：粒度最细、失败影响面最小、总耗时 ≈ max(单节点耗时)。
        进度按「每块完成」线性推进（块数=节点数时即每节点粒度），单调不减。
        """
        if not nodes:
            return []
        chunk_size = resolve_llm_gen_chunk_size()
        max_workers = resolve_llm_gen_max_workers()
        chunks = [nodes[i : i + chunk_size] for i in range(0, len(nodes), chunk_size)]
        total = len(chunks)
        results: dict[int, list] = {}
        progress_lock = threading.Lock()
        completed = 0

        def _run_chunk(idx: int, chunk_nodes: list) -> None:
            nonlocal completed
            try:
                # 保守起见每个工作线程独立创建 LLM client，避免共享 OpenAI client 的线程安全问题
                try:
                    chunk_client = self._build_llm_client()
                except Exception:
                    chunk_client = client  # 新建失败（如离线测试环境）回退共用 client
                scripts = self._run_stage3_chunk(chunk_client, markdown, chunk_nodes, course_name, all_nodes=nodes)
                if not scripts:
                    scripts = self._build_enhanced_fallback_scripts_for_nodes(chunk_nodes)
                results[idx] = scripts
            except Exception:
                # 本块重试后仍失败：只对本块节点走 fallback，其他块结果不受影响
                results[idx] = self._build_enhanced_fallback_scripts_for_nodes(chunk_nodes)
            finally:
                with progress_lock:
                    completed += 1
                    done = completed
                self._notify_progress(progress_cb, 60.0 + (done / total) * 18.0, f"Stage3 讲稿分块完成 {done}/{total}")

        worker_count = min(max_workers, total)
        if worker_count <= 1:
            for i, chunk_nodes in enumerate(chunks):
                _run_chunk(i, chunk_nodes)
        else:
            with ThreadPoolExecutor(max_workers=worker_count) as pool:
                futures = [pool.submit(_run_chunk, i, chunk_nodes) for i, chunk_nodes in enumerate(chunks)]
                for future in futures:
                    future.result()  # _run_chunk 内部已兜底，不会抛出

        merged: list = []
        for i in range(total):
            merged.extend(results.get(i) or [])
        return merged

    def _run_stage3_chunk(self, client, markdown: str, chunk_nodes: list, course_name: str | None, all_nodes: list | None = None) -> list:
        """单个分块的讲稿生成：prompt 复用原格式，但只要求输出本块节点的 scripts。

        单节点场景（默认 chunk_size=1）prompt 适配：
        - 上下文带上整棵节点树的标题列表（仅作前后衔接参考，禁止为其生成内容）；
        - 附本块节点完整信息；强调只输出本块节点。
        """
        chunk_ids = [str(n.get("node_id") or "").strip() for n in chunk_nodes]
        chunk_ids = [nid for nid in chunk_ids if nid]
        context_nodes = all_nodes if all_nodes else chunk_nodes
        title_lines = [
            f"- {n.get('node_id')}: {n.get('title')}"
            for n in context_nodes
            if isinstance(n, dict) and (n.get("node_id") or n.get("title"))
        ]
        titles_text = "\n".join(title_lines) if title_lines else "（无）"
        system_prompt = (
            "你是课堂讲稿生成助手（增强版）。只输出JSON。\n"
            "格式: {\"scripts\": [{\"node_id\":\"...\",\"title\":\"...\",\"script\":\"...\",\"segments\":[...]}]}\n\n"
            "每个segment必须包含:\n"
            "  - segment_id, text, node_id (必填)\n"
            "  - segment_type: opening/exclamation/example/interaction/transition/summary (必填)\n"
            "  - estimated_seconds: 整数15-120 (必填)\n"
            "  - interaction_hint: 具体教师话术 (必填)\n"
            "  - knowledge_card: {\"term\":\"术语\",\"definition\":\"定义\",\"formula\":\"公式或空串\",\"tags\":[\"标签，最多3个\"]} (必填)\n"
            "  - difficulty: easy/medium/hard (必填)\n"
            "使用节点树中的node_id值，不要编造。\n"
            "⚠️ 只输出本块 node_id 对应的内容，不要输出其他节点的脚本。"
        )
        user_prompt = (
            f"课程名: {course_name or '未命名课程'}\n原始MD:\n{markdown}\n\n"
            f"整棵节点树标题列表（仅作前后衔接参考，禁止为其生成讲稿）:\n{titles_text}\n\n"
            f"本块节点 node_id 列表: {json.dumps(chunk_ids, ensure_ascii=False)}\n"
            f"本块节点完整信息:\n{json.dumps(chunk_nodes, ensure_ascii=False)}\n\n"
            "只生成本块节点的讲稿，不要输出其他节点。"
            "每个节点输出3-4个segments: 开场->讲解->互动->过渡。node_id必须用本块节点树中的值。"
        )
        raw = self._request_llm_payload(client, system_prompt, user_prompt)
        data = self._extract_json(raw)
        scripts = extract_list_payload(data, "scripts")
        valid_ids = set(chunk_ids)
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

    def _build_enhanced_fallback_scripts_for_nodes(self, nodes: list) -> list:
        """为指定节点列表构造增强版 fallback 讲稿（结构与 _build_enhanced_fallback 一致）。"""
        scripts = []
        for idx, node in enumerate(nodes, start=1):
            nid = str(node.get("node_id") or f"node_{idx:03d}")
            title = str(node.get("title") or nid)
            st = f"讲解节点 {nid}：{title}。"
            scripts.append({
                "node_id": nid, "title": title, "script": st,
                "segments": [{
                    "segment_id": f"seg_{nid}_{idx}_1", "text": st, "node_id": nid,
                    "segment_type": "explanation", "estimated_seconds": 45,
                    "difficulty": "medium",
                    "interaction_hint": f"提问：你对{title}有什么理解？",
                    "knowledge_card": {"term": title, "definition": f"关于{title}的核心知识", "formula": "", "tags": ["core"]},
                }],
            })
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

    def _generate_llm(self, page: int, content: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized_content = self._prepare_content(content)
        outline = self._build_outline(normalized_content)

        evidence_text = format_evidence_for_prompt(evidence)

        system_prompt = (
            "你是高校教师讲稿生成助手。"
            "你的任务是把课件页面内容改写成可直接讲授的中文讲稿。"
            "必须准确覆盖原文关键信息，不要编造课件中不存在的结论、数据或公式。"
            "输出只能是 JSON 对象，且只包含 script 与 mindmap_markdown 两个字段。"
        )
        evidence_block = f"\n知识库证据参考:\n{evidence_text}\n" if evidence_text else ""
        user_prompt = (
            f"页面: {page}\n"
            f"原始内容:\n{normalized_content}\n\n"
            f"提炼要点:\n{outline}\n\n"
            f"{evidence_block}"
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

    def generate_node_script(self, teaching_node: dict[str, Any], course_name: str | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
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

        evidence_text = format_evidence_for_prompt(evidence)
        fallback = self._fallback_node_script(node_id, title, summary, core_points, examples, confusions, evidence)

        try:
            client = self._build_llm_client()
            system_prompt = (
                "你是高校课程智能讲授编排助手。"
                "请根据讲授节点信息生成适合互动式课堂的讲授内容。"
                "输出严格 JSON。"
                "必须包含 script、mindmap_markdown、interactive_questions、reteach_script、transition。"
                "可选包含 structured_markdown、knowledge_nodes、script_segments。"
            )
            evidence_block = f"\n知识库证据参考:\n{evidence_text}\n" if evidence_text else ""
            user_prompt = (
                f"课程名: {course_name or '未提供'}\n"
                f"节点标题: {title}\n"
                f"节点摘要: {summary}\n"
                f"核心要点: {json.dumps(core_points, ensure_ascii=False)}\n"
                f"示例: {json.dumps(examples, ensure_ascii=False)}\n"
                f"易错点: {json.dumps(confusions, ensure_ascii=False)}\n"
                f"补充内容: {assembled_content}\n"
                f"{evidence_block}"
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
        return OpenAI(api_key=api_key, base_url=base_url, timeout=resolve_llm_timeout())

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
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        details = "；".join(core_points[:3]) if core_points else summary or title
        example_text = examples[0] if examples else f"可以结合 {title} 的典型应用场景帮助学生理解。"
        reteach_focus = confusions[0] if confusions else f"重新解释 {title} 的核心概念"
        evidence_text = format_evidence_for_prompt(evidence)
        evidence_note = f"可参考知识库证据：“{evidence_text[:80]}”。" if evidence_text else ""
        script = (
            f"这一部分我们围绕“{title}”来讲。"
            f"先抓住几个关键点：{details}。"
            f"讲到这里时，可以用“{example_text}”作为课堂例子，让学生把抽象概念和真实情境对应起来。"
            f"{evidence_note}"
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
    def _extract_json(text: str) -> Any:
        """兼容旧调用点：委托给 core.llm.extract_json。

        旧实现在此复制了一份「只认 {} 区间」的解析逻辑，模型返回裸数组
        （nodes / scripts 列表）时会抛 ValueError，整段生成退化成兜底内容。
        统一走共享实现，根为数组时同样可解析。
        """
        return extract_json(text)

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
        return normalize_stage2_nodes(extract_nodes_payload(data))

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
        return normalize_stage3_scripts(extract_list_payload(data, "scripts"), node_ids)

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
