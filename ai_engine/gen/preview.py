"""
预览渲染模块 — S4 个性化满足

职责：
  结构化节点数组 → HTML 预览（教师审阅界面可用）

流程：
  nodes → preview_renderer → HTML（可嵌入前端 iframe / 独立页面）

兼容规则：
  - 页面类型双字段识别：优先读 type，兜底读 node_type，均缺失时默认 content
  - 要点字段双向兼容：key_points 优先，core_points / key_difficulties 兜底，
    最后按正文（content / script / summary）拆分兜底
  - 分段字段：segments 讲授分段（segment_type / estimated_seconds /
    difficulty / interaction_hint / knowledge_card），segment_type 未知/缺失时
    使用兜底标签（未知→"其他"，缺失→"段落"）
  - script 字段：渲染为独立"讲授文本"标签区块，与正文视觉区分；缺失时不产生空区块
  - quiz / interactive：专属渲染分支，支持题目对象（question/options/answer/explanation）
    与纯字符串题目两种形态
"""

import html
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class PreviewConfig:
    """预览渲染配置"""
    template_dir: str = ""


# 页面类型别名：union 老版 type 模板值（title/content/quiz/summary）与
# 标准化 node_type 枚举（cover/section/quiz/interactive/divider）的并集。
# 命中后统一收敛为 5 套布局：cover / section / quiz / summary / content。
_TYPE_ALIASES = {
    # 封面
    "cover": "cover",
    "title": "cover",
    # 目录 / 章节
    "section": "section",
    "divider": "section",
    "toc": "section",
    "chapter": "section",
    # 问答 / 互动（quiz 与 interactive 分开渲染，布局不同）
    "quiz": "quiz",
    "qa": "quiz",
    "question": "quiz",
    "interactive": "interactive",
    "activity": "interactive",
    # 总结
    "summary": "summary",
    "recap": "summary",
    # 通用
    "content": "content",
    "slide": "content",
}

# 讲授分段类型 → 中文语义标签（预览展示用）
_SEGMENT_TYPE_LABELS = {
    "opening": "导入",
    "explanation": "讲解",
    "example": "示例",
    "interaction": "互动",
    "transition": "过渡",
    "summary": "小结",
}

# 讲授分段难度 → 可视化图标
_SEGMENT_DIFF_ICONS = {
    "easy": "🟢",
    "medium": "🟡",
    "hard": "🔴",
}

# 讲授分段兜底标签：未知类型 / 缺失类型，保证任何分段都有中文语义标签
_SEG_LABEL_UNKNOWN = "其他"
_SEG_LABEL_MISSING = "段落"

# 正文兜底时要截取的最大句数
_MAX_FALLBACK_POINTS = 8
_MAX_DISPLAY_POINTS = 10


class PreviewRenderer:
    """结构化节点 → HTML 预览渲染器"""

    def render(self, nodes: list[dict[str, Any]], course_name: str = "课件预览") -> str:
        """生成完整 HTML 预览页面

        Args:
            nodes: 结构化节点数组
            course_name: 课程名称

        Returns:
            HTML 字符串（可直接嵌入 iframe 或保存为 .html）
        """
        slides_html = self._build_slides(nodes)
        return self._wrap_html(course_name, slides_html, self._presentation_from_nodes(nodes))

    @staticmethod
    def _presentation_from_nodes(nodes: list[dict[str, Any]]) -> dict[str, str]:
        """读取前端样式层写入节点 metadata 的全局呈现配置。"""
        defaults = {
            "palette": "classic",
            "layout": "balanced",
            "font_family": "system",
            "density": "comfortable",
        }
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            metadata = node.get("metadata") or {}
            presentation = metadata.get("presentation") or node.get("presentation") or {}
            if isinstance(presentation, dict):
                for key in defaults:
                    value = str(presentation.get(key) or "").strip()
                    if value:
                        defaults[key] = value
                break
        return defaults

    def render_node(self, node: dict[str, Any], index: int = 1) -> str:
        """生成单个节点的预览 HTML"""
        return self._render_slide(node, index)

    # ── 幻灯片构建 ──

    def _build_slides(self, nodes: list[dict[str, Any]]) -> str:
        slides = []
        for idx, node in enumerate(nodes, start=1):
            slides.append(self._render_slide(node, idx))
        if not slides:
            return '<div class="empty-state">暂无节点数据，请先完成 S3 讲稿生成。</div>'
        return "\n".join(slides)

    def _resolve_type(self, node: dict[str, Any]) -> str:
        """双字段识别页面类型：type 优先，node_type 兜底，缺省 content。

        兼容 Pydantic 枚举（NodeType.SECTION）与纯字符串两种形态。
        """
        raw = node.get("type")
        if raw is None or str(raw).strip() == "":
            raw = node.get("node_type")
        if raw is None or str(raw).strip() == "":
            return "content"
        if hasattr(raw, "value"):  # Pydantic 枚举
            raw = raw.value
        key = str(raw).strip().lower()
        return _TYPE_ALIASES.get(key, "content")

    def _render_slide(self, node: dict[str, Any], index: int) -> str:
        node_type = self._resolve_type(node)
        title = html.escape(str(node.get("title") or f"第{index}页"))
        renderers = {
            "cover": self._slide_cover,
            "section": self._slide_section,
            "quiz": self._slide_quiz,
            "interactive": self._slide_interactive,
            "summary": self._slide_summary,
            "content": self._slide_content,
        }
        renderer = renderers.get(node_type, self._slide_content)
        return renderer(node, index, title)

    # ── 封面 ──

    def _slide_cover(self, node: dict, index: int, title: str) -> str:
        subtitle = html.escape(str(node.get("subtitle") or node.get("content") or node.get("summary") or "").strip())
        points = self._extract_key_points(node)
        points_html = self._render_key_points(points, cls="cover-points") if points else ""
        return f"""<div class="slide cover-slide">
  <div class="slide-num">{index}</div>
  <div class="cover-inner">
    <h1>{title}</h1>
    {f'<p class="subtitle">{subtitle}</p>' if subtitle else ''}
    {points_html}
  </div>
</div>"""

    # ── 目录 / 章节 ──

    def _slide_section(self, node: dict, index: int, title: str) -> str:
        subtitle = html.escape(str(node.get("content") or node.get("summary") or "").strip())
        # 目录项优先取 children（子节点标题），其次取要点
        children = self._as_list(node.get("children"))
        items = children or self._extract_key_points(node)
        list_html = self._render_key_points(items, cls="section-list", with_index=True) if items else ""
        return f"""<div class="slide section-slide">
  <div class="slide-num">{index}</div>
  <div class="section-inner">
    <h2>{title}</h2>
    <div class="divider"></div>
    {f'<p class="section-sub">{subtitle}</p>' if subtitle else ''}
    {list_html}
  </div>
</div>"""

    # ── 问答 / 互动 ──

    def _slide_quiz(self, node: dict, index: int, title: str) -> str:
        questions = self._as_raw_list(node.get("questions") or node.get("interactive_questions"))
        if not questions:
            questions = self._extract_key_points(node) or self._split_content_into_points(
                str(node.get("content") or "").strip()
            )
        items = "".join(self._render_question(q) for q in questions)
        script_html = self._render_script_block(node)
        segments_html = self._render_segments(node)
        return f"""<div class="slide quiz-slide">
  <div class="slide-num">{index}</div>
  <h2>💡 {title}</h2>
  <ol class="questions">{items}</ol>
  {script_html}
  {segments_html}
</div>"""

    def _slide_interactive(self, node: dict, index: int, title: str) -> str:
        """interactive 类型专属布局：与 quiz 同源但视觉区分（绿色系、互动感）。"""
        questions = self._interactive_questions(node)
        if not questions:
            questions = self._extract_key_points(node) or self._split_content_into_points(
                str(node.get("content") or "").strip()
            )
        items = "".join(self._render_question(q) for q in questions)
        script_html = self._render_script_block(node)
        segments_html = self._render_segments(node)
        return f"""<div class="slide quiz-slide interactive-slide">
  <div class="slide-num">{index}</div>
  <h2>🎯 {title}</h2>
  <ol class="questions">{items}</ol>
  {script_html}
  {segments_html}
</div>"""

    def _interactive_questions(self, node: dict[str, Any]) -> list[Any]:
        """从结构化互动素材中提取题目，供预览与导出共用节点数据。"""
        questions = self._as_raw_list(node.get("questions") or node.get("interactive_questions"))
        if questions:
            return questions
        flattened: list[Any] = []
        for item in node.get("interactive_items") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").lower() == "quiz":
                flattened.extend(self._as_raw_list(item.get("questions")))
        return flattened

    @staticmethod
    def _as_raw_list(value: Any) -> list[Any]:
        """取原始列表（保留 dict 元素，供题目对象渲染）；字符串退化为单元素列表。"""
        if isinstance(value, list):
            return [v for v in value if v]
        if isinstance(value, str) and value.strip():
            return [line.strip() for line in value.split("\n") if line.strip()]
        return []

    def _render_question(self, q: Any) -> str:
        """单题渲染：字符串题直接输出；dict 题展示题干 + 选项 + 答案 + 解析。"""
        if isinstance(q, dict):
            text = html.escape(str(q.get("question") or q.get("title") or "").strip())
            options = q.get("options")
            answer = str(q.get("answer") or "").strip()
            explanation = str(q.get("explanation") or "").strip()

            opt_html = ""
            if isinstance(options, list) and options:
                letters = "ABCDEFGH"
                opt_items = []
                for i, opt in enumerate(options[: len(letters)]):
                    letter = letters[i]
                    is_answer = bool(answer) and letter == answer.strip().upper()
                    ans_cls = " q-option-answer" if is_answer else ""
                    opt_items.append(
                        f'<li class="q-option{ans_cls}">'
                        f'<span class="q-opt-letter">{letter}</span>{html.escape(str(opt))}</li>'
                    )
                opt_html = f'<ul class="q-options">{"".join(opt_items)}</ul>'

            exp_html = f'<p class="q-explanation">解析：{html.escape(explanation)}</p>' if explanation else ""
            return f'<li class="q-item"><p class="q-text">{text}</p>{opt_html}{exp_html}</li>'
        return f'<li class="q-item"><p class="q-text">{html.escape(str(q))}</p></li>'

    # ── 总结 ──

    def _slide_summary(self, node: dict, index: int, title: str) -> str:
        points = self._extract_key_points(node)
        points_html = self._render_key_points(points) if points else ""
        script_html = self._render_script_block(node)
        segments_html = self._render_segments(node)
        return f"""<div class="slide summary-slide">
  <div class="slide-num">{index}</div>
  <h2>📌 {title}</h2>
  {points_html}
  {script_html}
  {segments_html}
</div>"""

    # ── 通用 ──

    def _slide_content(self, node: dict, index: int, title: str) -> str:
        points = self._extract_key_points(node)
        points_html = self._render_key_points(points) if points else ""

        body_parts = []
        for key in ("content", "summary"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                body_parts.append(f"<p>{html.escape(val)}</p>")
            elif isinstance(val, list) and val:
                body_parts.append("<ul>")
                for item in val:
                    body_parts.append(f"<li>{html.escape(str(item))}</li>")
                body_parts.append("</ul>")
        body_html = f'<div class="body">{"".join(body_parts)}</div>' if body_parts else ""

        script_html = self._render_script_block(node)
        segments_html = self._render_segments(node)
        return f"""<div class="slide content-slide">
  <div class="slide-num">{index}</div>
  <h2>{title}</h2>
  {points_html}
  {body_html}
  {script_html}
  {segments_html}
</div>"""

    # ── 要点提取 ──

    def _extract_key_points(self, node: dict[str, Any]) -> list[str]:
        """要点字段双向兼容读取。

        优先级：key_points → core_points → key_difficulties → expected_outcomes
        → 正文（content / script / summary）拆分兜底。
        """
        for key in ("key_points", "core_points", "key_difficulties", "expected_outcomes"):
            points = self._as_list(node.get(key))
            if points:
                return points
        content = str(node.get("content") or node.get("script") or node.get("summary") or "").strip()
        return self._split_content_into_points(content)

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        """把 list / 换行字符串统一转成干净的字符串列表。"""
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [line.strip() for line in value.split("\n") if line.strip()]
        return []

    @staticmethod
    def _split_content_into_points(content: str, limit: int = _MAX_FALLBACK_POINTS) -> list[str]:
        """正文兜底：先按行拆，再按句拆，保证得到尽量短小的要点。"""
        if not content:
            return []
        lines = [ln.strip().lstrip("•-*#· ").strip() for ln in content.split("\n") if ln.strip()]
        if len(lines) >= 2:
            return [ln for ln in lines if ln][:limit]
        sentences = [s.strip() for s in re.split(r"[。；;！？!?]\s*", content) if s.strip()]
        return sentences[:limit]

    # ── 要点渲染 ──

    @staticmethod
    def _render_key_points(points: list[str], cls: str = "key-points", with_index: bool = False) -> str:
        items = []
        for i, p in enumerate(points[:_MAX_DISPLAY_POINTS], start=1):
            idx = f'<span class="kp-idx">{i}</span>' if with_index else ""
            # 要点视觉高亮：kp-item 列表项 + kp-highlight 文本（纯 CSS，不依赖外部资源）
            items.append(
                f'<li class="kp-item">{idx}<span class="kp-highlight">{html.escape(str(p))}</span></li>'
            )
        return f'<ul class="{cls}">{"".join(items)}</ul>'

    # ── 讲授文本区块 ──

    @staticmethod
    def _render_script_block(node: dict[str, Any]) -> str:
        """script 字段 → "讲授文本" 标签区块，与正文视觉区分。

        向后兼容：script 缺失或为空白时返回空串，不产生空区块。
        """
        script = node.get("script")
        if not isinstance(script, str) or not script.strip():
            return ""
        return (
            '<section class="script-block"><h4>讲授文本</h4>'
            f'<div class="script-body">{html.escape(script.strip())}</div></section>'
        )

    # ── 分段渲染 ──

    def _render_segments(self, node: dict[str, Any]) -> str:
        segments = node.get("segments") or []
        if not segments:
            return ""
        items = []
        for s in segments:
            if not isinstance(s, dict):
                s = {"text": s}
            text = str(s.get("text") or "").strip()
            if not text:
                continue
            seg_type = str(s.get("segment_type") or "").strip().lower()
            # 兜底标签：已知类型用映射，未知类型用"其他"，缺失类型用"段落"
            seg_label = _SEGMENT_TYPE_LABELS.get(
                seg_type, _SEG_LABEL_UNKNOWN if seg_type else _SEG_LABEL_MISSING
            )
            badge_cls = seg_type if seg_type else "default"
            badge = f'<span class="seg-badge seg-badge-{html.escape(badge_cls)}">{html.escape(seg_label)}</span>'

            dur = int(s.get("estimated_seconds") or 0)
            dur_html = f'<span class="seg-dur">⏱ {dur}秒</span>' if dur else ""

            diff = str(s.get("difficulty") or "").strip().lower()
            diff_icon = _SEGMENT_DIFF_ICONS.get(diff, "")
            diff_html = f'<span class="seg-diff diff-{html.escape(diff)}">{diff_icon}</span>' if diff_icon else ""

            hint = str(s.get("interaction_hint") or "").strip()
            hint_html = f'<p class="seg-hint">💬 {html.escape(hint)}</p>' if hint else ""

            kc_html = self._render_knowledge_card(s.get("knowledge_card"))

            items.append(
                f'<li class="seg-item">{badge}{dur_html}{diff_html}'
                f'<p class="seg-text">{html.escape(text)}</p>{hint_html}{kc_html}</li>'
            )
        if not items:
            return ""
        return (
            '<section class="segments-block"><h4>讲授分段</h4>'
            f'<ol class="segments">{"".join(items)}</ol></section>'
        )

    @staticmethod
    def _render_knowledge_card(kc: Any) -> str:
        """知识卡片渲染：term / definition / formula / tags。"""
        if not isinstance(kc, dict):
            return ""
        term = str(kc.get("term") or "").strip()
        definition = str(kc.get("definition") or "").strip()
        formula = str(kc.get("formula") or "").strip()
        tags = [html.escape(str(t).strip()) for t in (kc.get("tags") or []) if str(t).strip()]
        if not any([term, definition, formula, tags]):
            return ""
        parts = []
        if definition:
            parts.append(f'<p class="kc-def">{html.escape(definition)}</p>')
        if formula:
            parts.append(f'<pre class="kc-formula">{html.escape(formula)}</pre>')
        if tags:
            parts.append(f'<div class="kc-tags">{"".join(f"<span>{t}</span>" for t in tags)}</div>')
        return f'<div class="knowledge-card"><strong class="kc-term">📘 {html.escape(term or "知识卡片")}</strong>{"".join(parts)}</div>'

    # ── HTML 包装 ──

    def _wrap_html(self, title: str, slides_html: str, presentation: dict[str, str] | None = None) -> str:
        presentation = presentation or self._presentation_from_nodes([])
        palette = presentation.get("palette", "classic")
        layout = presentation.get("layout", "balanced")
        font_family = presentation.get("font_family", "system")
        density = presentation.get("density", "comfortable")
        palette_css = {
            "classic": ("#168f82", "#eef3f1", "#18322f", "#d9ebe6", "#0b4f49"),
            "klein-blue": ("#315fd4", "#eef2f8", "#17253f", "#dce5f6", "#203f98"),
        }.get(palette, ("#168f82", "#eef3f1", "#18322f", "#d9ebe6", "#0b4f49"))
        font_css = {
            "system": "-apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif",
            "source-han": "'Source Han Sans SC', 'Noto Sans CJK SC', sans-serif",
            "serif": "'Songti SC', 'STSong', 'SimSun', serif",
        }.get(font_family, "-apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif")
        padding_css = {
            "minimal": "56px 64px 60px",
            "compact": "36px 44px 40px",
            "comfortable": "44px 52px 48px",
        }.get(density, "44px 52px 48px")
        body_padding = "28px" if layout == "visual" else ("16px" if layout == "text" else "20px")
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
          background: #f0f2f5; color: #1a1a2e; padding: 20px; }}
  .presentation {{ max-width: 1100px; margin: 0 auto; }}
  .slide {{ background: #fff; border-radius: 14px; box-shadow: 0 2px 14px rgba(0,0,0,0.08);
           padding: 44px 52px 48px; margin-bottom: 24px; position: relative;
           min-height: 320px; overflow: hidden; }}
  /* 页码：绝对定位右上角，标题加右侧内边距避免重叠 */
  .slide-num {{ position: absolute; top: 16px; right: 20px; z-index: 2;
                font-size: 13px; color: rgba(0,0,0,0.4);
                background: rgba(0,0,0,0.06); padding: 2px 10px; border-radius: 999px; }}
  .slide h1, .slide h2 {{ padding-right: 52px; }}
  h1 {{ font-size: 34px; line-height: 1.3; }}
  h2 {{ font-size: 24px; margin-bottom: 16px; color: #1a1a2e; line-height: 1.4; }}

  /* ── 封面 ── */
  .cover-slide, .title-slide {{ background: linear-gradient(135deg, #4361ee 0%, #7209b7 100%);
                                 color: #fff; display: flex; align-items: center;
                                 justify-content: center; text-align: center; }}
  .cover-slide .slide-num, .title-slide .slide-num {{ color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.16); }}
  .cover-inner {{ max-width: 720px; margin: 0 auto; }}
  .cover-slide h1, .title-slide h1 {{ color: #fff; margin-bottom: 18px; }}
  .cover-slide .subtitle, .title-slide .subtitle {{ font-size: 19px; color: rgba(255,255,255,0.85); }}
  .cover-points {{ list-style: none; margin: 28px auto 0; display: grid; gap: 10px; max-width: 520px; }}
  .cover-points li {{ background: rgba(255,255,255,0.14); border-radius: 10px; padding: 10px 18px;
                      font-size: 15px; line-height: 1.6; }}

  /* ── 目录 / 章节 ── */
  .section-slide {{ background: linear-gradient(135deg, #f72585 0%, #b5179e 100%); color: #fff; }}
  .section-slide .slide-num {{ color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.16); }}
  .section-inner {{ max-width: 720px; margin: 0 auto; }}
  .section-slide h2 {{ color: #fff; }}
  .section-slide .divider {{ width: 60px; height: 4px; background: rgba(255,255,255,0.9);
                             margin: 20px 0; border-radius: 2px; }}
  .section-sub {{ font-size: 16px; color: rgba(255,255,255,0.85); margin-bottom: 18px; line-height: 1.6; }}
  .section-list {{ list-style: none; display: grid; gap: 10px; margin-top: 8px; }}
  .section-list li {{ display: flex; align-items: center; gap: 12px; background: rgba(255,255,255,0.14);
                      border-radius: 10px; padding: 10px 16px; font-size: 15px; line-height: 1.5; }}
  .section-list .kp-idx {{ flex-shrink: 0; width: 24px; height: 24px; border-radius: 50%;
                           background: #fff; color: #b5179e; font-weight: 700; font-size: 12px;
                           display: flex; align-items: center; justify-content: center; }}

  /* ── 问答 ── */
  .quiz-slide {{ border-left: 5px solid #f72585; background: linear-gradient(180deg, #fff, #fff5f9); }}
  .questions {{ list-style: none; counter-reset: q; margin-top: 8px; display: grid; gap: 12px; }}
  .questions .q-item {{ counter-increment: q; position: relative; padding: 14px 18px 14px 52px;
                        background: #fff; border: 1px solid #f0d7e6; border-radius: 12px;
                        font-size: 15px; line-height: 1.6; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  .questions .q-item::before {{ content: counter(q); position: absolute; left: 16px; top: 14px;
                                width: 24px; height: 24px; border-radius: 50%; background: #f72585;
                                color: #fff; font-weight: 700; font-size: 13px;
                                display: flex; align-items: center; justify-content: center; }}
  .q-text {{ font-weight: 600; color: #2a1a2e; }}
  .q-options {{ list-style: none; margin: 10px 0 0; display: grid; gap: 6px; }}
  .q-option {{ display: flex; align-items: center; gap: 8px; padding: 6px 10px;
               background: #faf5f8; border-radius: 8px; font-size: 14px; line-height: 1.5; }}
  .q-option-answer {{ background: #e6f9ee; border: 1px solid #b7e4c7; }}
  .q-opt-letter {{ flex-shrink: 0; width: 20px; height: 20px; border-radius: 50%;
                   background: #fce3ef; color: #b5179e; font-size: 11px; font-weight: 700;
                   display: flex; align-items: center; justify-content: center; }}
  .q-option-answer .q-opt-letter {{ background: #2e7d32; color: #fff; }}
  .q-explanation {{ margin-top: 8px; font-size: 13px; color: #6b5b66;
                    background: #fbf3f7; padding: 6px 10px; border-radius: 8px; }}

  /* ── 互动（与 quiz 同源，绿色系视觉区分） ── */
  .interactive-slide {{ border-left-color: #2a9d5c; background: linear-gradient(180deg, #fff, #f2fbf6); }}
  .interactive-slide .q-item::before {{ background: #2a9d5c; }}
  .interactive-slide .q-item {{ border-color: #d2eadc; }}
  .interactive-slide .q-opt-letter {{ background: #dff3e6; color: #217a43; }}

  /* ── 总结 ── */
  .summary-slide {{ border-left: 5px solid #4361ee; background: linear-gradient(180deg, #f8f9ff, #fff); }}
  .key-points {{ list-style: none; display: grid; gap: 10px; margin-top: 12px; }}
  .key-points li {{ position: relative; padding: 10px 16px 10px 40px; background: #eef1ff;
                    border-radius: 10px; font-size: 15px; line-height: 1.6; }}
  .key-points li::before {{ content: "✓"; position: absolute; left: 14px; top: 10px; color: #4361ee;
                            font-weight: 700; }}
  /* 要点高亮：kp-item + kp-highlight（纯 CSS 视觉强调，不依赖外部资源） */
  .kp-highlight {{ color: #2743b8; font-weight: 600; }}

  /* ── 通用 ── */
  .body {{ font-size: 15px; line-height: 1.85; color: #333; margin-top: 10px; }}
  .body p {{ margin-bottom: 8px; }}
  .body ul {{ padding-left: 22px; }}
  .body li {{ margin-bottom: 4px; }}

  /* ── 讲授文本区块 ── */
  .script-block {{ margin-top: 16px; padding: 14px 16px; background: #f7f9fc;
                   border: 1px solid #e2e8f2; border-left: 4px solid #4361ee; border-radius: 10px; }}
  .script-block h4 {{ font-size: 13px; color: #4361ee; margin-bottom: 8px; letter-spacing: 0.04em;
                      display: flex; align-items: center; gap: 6px; }}
  .script-block h4::before {{ content: "🎤"; font-size: 14px; }}
  .script-body {{ font-size: 14px; line-height: 1.8; color: #3a4356; white-space: pre-wrap; }}

  /* ── 讲授分段 ── */
  .segments-block {{ margin-top: 20px; padding-top: 16px; border-top: 1px dashed #d4d9e4; }}
  .segments-block h4 {{ font-size: 14px; color: #5f6c84; margin-bottom: 10px; letter-spacing: 0.02em; }}
  .segments {{ list-style: none; display: grid; gap: 10px; }}
  .seg-item {{ padding: 12px 16px; background: #f6f8fb; border-radius: 10px;
               border-left: 3px solid #a9b4c8; }}
  .seg-badge {{ display: inline-block; font-size: 11px; padding: 2px 10px; border-radius: 999px;
                font-weight: 600; text-transform: capitalize; }}
  .seg-badge-opening {{ background: #e3f2fd; color: #1565c0; }}
  .seg-badge-explanation {{ background: #f3e5f5; color: #7b1fa2; }}
  .seg-badge-example {{ background: #e8f5e9; color: #2e7d32; }}
  .seg-badge-interaction {{ background: #fff3e0; color: #e65100; }}
  .seg-badge-transition {{ background: #fce4ec; color: #c62828; }}
  .seg-badge-summary {{ background: #e8eaf6; color: #283593; }}
  .seg-badge-default {{ background: #eceff3; color: #5f6c84; }}
  .seg-dur {{ display: inline-block; font-size: 12px; color: #667; margin-left: 8px; }}
  .seg-diff {{ display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 999px;
               margin-left: 6px; text-transform: capitalize; }}
  .diff-easy {{ background: #e8f5e9; color: #2e7d32; }}
  .diff-medium {{ background: #fff8e1; color: #f57f17; }}
  .diff-hard {{ background: #ffebee; color: #c62828; }}
  .seg-text {{ margin-top: 6px; font-size: 14px; line-height: 1.7; color: #2b3140; }}
  .seg-hint {{ margin-top: 6px; font-size: 12px; color: #7a5b00; background: #fff8e1;
               display: inline-block; padding: 3px 10px; border-radius: 8px; }}

  /* ── 知识卡片 ── */
  .knowledge-card {{ margin-top: 8px; padding: 10px 12px; background: #fff;
                     border: 1px solid #dfe6f0; border-radius: 10px; }}
  .kc-term {{ font-size: 13px; color: #2f5d8f; display: block; margin-bottom: 4px; }}
  .kc-def {{ font-size: 13px; color: #445; line-height: 1.6; }}
  .kc-formula {{ font-size: 12px; background: #f4f6fa; padding: 6px 10px; border-radius: 6px;
                 overflow-x: auto; margin-top: 4px; }}
  .kc-tags {{ display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap; }}
  .kc-tags span {{ font-size: 11px; background: #eef3fa; color: #445; padding: 1px 8px;
                   border-radius: 999px; }}

  /* ── 空态 ── */
  .empty-state {{ text-align: center; padding: 60px 20px; color: #94a3b8; font-size: 15px; }}

  /* ── S3 样式层：由节点 metadata.presentation 驱动，保证修改后预览实时可见 ── */
  :root {{ --preview-accent: {palette_css[0]}; --preview-page-bg: {palette_css[1]};
           --preview-ink: {palette_css[2]}; --preview-accent-soft: {palette_css[3]};
           --preview-deep: {palette_css[4]}; --preview-slide-padding: {padding_css}; }}
  body {{ font-family: {font_css}; background: radial-gradient(circle at 8% 0%, #ffffff 0, var(--preview-page-bg) 42%, #e6ecea 100%); padding: {body_padding}; color: var(--preview-ink); }}
  .presentation {{ max-width: 1180px; }}
  .slide {{ padding: var(--preview-slide-padding); border: 1px solid rgba(24,50,47,.10); border-radius: 22px;
            box-shadow: 0 18px 42px rgba(24,50,47,.09); min-height: 380px; }}
  .slide h2 {{ color: var(--preview-ink); font-weight: 760; letter-spacing: -.025em; }}
  .slide-num {{ color: var(--preview-accent); background: var(--preview-accent-soft); font-weight: 700; }}
  .content-slide {{ border-top: 5px solid var(--preview-accent); background: rgba(255,255,255,.94); }}
  .content-slide .key-points li, .content-slide .body {{ color: var(--preview-ink); }}
  .content-slide .key-points li {{ background: linear-gradient(105deg, #fff, var(--preview-accent-soft)); border: 1px solid rgba(24,50,47,.07); }}
  .cover-slide, .title-slide {{ background: linear-gradient(135deg, var(--preview-deep) 0%, var(--preview-accent) 100%); min-height: 460px; }}
  .section-slide {{ background: linear-gradient(135deg, var(--preview-deep) 0%, var(--preview-accent) 100%); }}
  .quiz-slide {{ border-left: 5px solid var(--preview-accent); border-top: 0; background: linear-gradient(145deg, #fff, var(--preview-accent-soft)); }}
  .quiz-slide .questions .q-item {{ border-color: rgba(24,50,47,.10); box-shadow: 0 6px 16px rgba(24,50,47,.06); }}
  .quiz-slide .questions .q-item::before {{ background: var(--preview-accent); }}
  .script-block {{ border-left-color: var(--preview-accent); background: rgba(255,255,255,.72); }}
  .script-block h4 {{ color: var(--preview-accent); }}
  .presentation[data-layout="visual"] .slide {{ min-height: 430px; }}
  .presentation[data-layout="visual"] .content-slide .key-points {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
  .presentation[data-layout="text"] .slide {{ max-width: 920px; margin-left: auto; margin-right: auto; }}
  .presentation[data-density="minimal"] .slide h2 {{ font-size: 28px; }}
  .presentation[data-density="compact"] .slide {{ border-radius: 16px; }}
</style>
</head>
<body>
<div class="presentation" data-palette="{html.escape(palette)}" data-layout="{html.escape(layout)}" data-density="{html.escape(density)}">
{slides_html}
</div>
</body>
</html>"""
