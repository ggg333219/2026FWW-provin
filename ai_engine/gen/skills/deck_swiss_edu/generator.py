"""
deck-swiss-edu generator — 教学专用 HTML 幻灯片生成器

职责：
  读取 SKILL.md 布局规范，接收 intent + evidence，
  调用 LLM 生成 slides JSON，渲染为单文件 HTML，
  上传 MinIO/本地存储，返回预览 URL。

流程：
  1. 读取 SKILL.md 正文（布局规范 + 设计铁律）
  2. 构建 LLM prompt（注入布局池 + 内容映射规则）
  3. 调用 LLM 生成 slides JSON
  4. 渲染为 index.html（键盘翻页、响应式、16:9）
  5. 保存到上传目录，返回 URL
"""

import json
import re
import uuid
from pathlib import Path
from typing import Any, Optional

import sys
from pathlib import Path as _Path

_PROJECT_ROOT = _Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ai_engine.core.llm import LLMClient


# ---------------------------------------------------------------------------
# 布局渲染器（纯函数，每个布局一个渲染方法）
# ---------------------------------------------------------------------------

PALETTE = {
    "klein-blue": {
        "accent": "#002FA7",
        "paper": "#fafaf8",
        "ink": "#0a0a0a",
        "light": "#e8e8ec",
    },
    "lemon-yellow": {
        "accent": "#FFD500",
        "paper": "#f7f5ee",
        "ink": "#0a0a0a",
        "light": "#f0edda",
    },
    "neon-green": {
        "accent": "#C5E003",
        "paper": "#f7f5ee",
        "ink": "#0a0a0a",
        "light": "#eef5d8",
    },
    "safety-orange": {
        "accent": "#FF6B35",
        "paper": "#f7f5ee",
        "ink": "#ffffff",
        "light": "#fde8df",
    },
}


def _render_slide(slide: dict[str, Any], palette: dict[str, str], slide_index: int, total: int) -> str:
    """根据 layout 代号分发到对应渲染方法。"""
    layout = str(slide.get("layout", "S03"))
    handlers = {
        "S01": _render_cover,
        "S02": _render_timeline,
        "S03": _render_statement,
        "S04": _render_six_cells,
        "S05": _render_three_sub_cards,
        "S06": _render_kpi_tower,
        "S23": _render_concept_definition,
        "S24": _render_quiz,
        "S26": _render_section_divider,
    }
    handler = handlers.get(layout, _render_content)
    return handler(slide, palette, slide_index, total)


def _render_cover(slide: dict, palette: dict, idx: int, total: int) -> str:
    accent = palette["accent"]
    paper = palette["paper"]
    ink = palette["ink"]
    title = _esc(slide.get("title", ""))
    subtitle = _esc(slide.get("subtitle", ""))
    meta = slide.get("meta", {})
    date = meta.get("date", "")
    topic = meta.get("topic", "")
    return f"""<section class="slide" data-slide-id="{idx}" style="background:{accent};color:{paper};">
  <div class="slide-inner">
    <div class="folio">№{idx}/{total}</div>
    <div class="topic-tag">{_esc(topic)}</div>
    <h1 class="cover-title">{title}</h1>
    <p class="cover-subtitle">{subtitle}</p>
    <div class="meta-row">{date}</div>
  </div>
</section>"""


def _render_statement(slide: dict, palette: dict, idx: int, total: int) -> str:
    accent = palette["accent"]
    paper = palette["paper"]
    ink = palette["ink"]
    title = _esc(slide.get("title", ""))
    content = _esc(slide.get("content", ""))
    return f"""<section class="slide" data-slide-id="{idx}" style="background:{paper};">
  <div class="slide-inner">
    <div class="folio">№{idx}/{total}</div>
    <div class="statement-text">{title}</div>
    <div class="hairline" style="background:{accent}"></div>
    <p class="statement-body">{content}</p>
  </div>
</section>"""


def _render_six_cells(slide: dict, palette: dict, idx: int, total: int) -> str:
    accent = palette["accent"]
    paper = palette["paper"]
    ink = palette["ink"]
    items = slide.get("items", [])
    cells = "".join(
        f'<div class="cell"><span class="cell-num">{i+1}</span><h3>{_esc(item.get("title",""))}</h3><p>{_esc(item.get("desc",""))}</p></div>'
        for i, item in enumerate(items[:6])
    )
    return f"""<section class="slide" data-slide-id="{idx}" style="background:{paper};">
  <div class="slide-inner">
    <div class="folio">№{idx}/{total}</div>
    <h2 class="section-title">{_esc(slide.get("title",""))}</h2>
    <div class="six-grid">{cells}</div>
  </div>
</section>"""


def _render_kpi_tower(slide: dict, palette: dict, idx: int, total: int) -> str:
    accent = palette["accent"]
    paper = palette["paper"]
    ink = palette["ink"]
    kpis = slide.get("kpis", [])
    bars = "".join(
        f'<div class="kpi-bar" style="height:{min(k.get("value",50),100)}%"><span class="kpi-num">{k.get("value","")}</span><span class="kpi-label">{_esc(k.get("label",""))}</span></div>'
        for k in kpis[:4]
    )
    return f"""<section class="slide" data-slide-id="{idx}" style="background:{paper};">
  <div class="slide-inner">
    <div class="folio">№{idx}/{total}</div>
    <h2 class="section-title">{_esc(slide.get("title",""))}</h2>
    <div class="kpi-tower">{bars}</div>
  </div>
</section>"""


def _render_concept_definition(slide: dict, palette: dict, idx: int, total: int) -> str:
    accent = palette["accent"]
    paper = palette["paper"]
    ink = palette["ink"]
    title = _esc(slide.get("title", ""))
    content = _esc(slide.get("content", ""))
    examples = slide.get("examples", [])
    key_points = slide.get("key_points", [])
    ex_html = "".join(f'<li><code>{_esc(e)}</code></li>' for e in examples) if examples else ""
    kp_html = "".join(f"<li>{_esc(k)}</li>" for k in key_points) if key_points else ""
    return f"""<section class="slide" data-slide-id="{idx}" style="background:{paper};">
  <div class="slide-inner">
    <div class="folio">№{idx}/{total}</div>
    <h2 class="concept-title" style="color:{accent}">{title}</h2>
    <p class="concept-body">{content}</p>
    <div class="two-col">
      <div class="col">
        <h4>示例</h4>
        <ul class="code-list">{ex_html}</ul>
      </div>
      <div class="col">
        <h4>要点</h4>
        <ul>{kp_html}</ul>
      </div>
    </div>
  </div>
</section>"""


def _render_quiz(slide: dict, palette: dict, idx: int, total: int) -> str:
    accent = palette["accent"]
    paper = palette["paper"]
    ink = palette["ink"]
    title = _esc(slide.get("title", "互动问答"))
    questions = slide.get("questions", ["思考一下？"])
    q_html = "".join(f"<li>❓ {_esc(q)}</li>" for q in questions)
    return f"""<section class="slide" data-slide-id="{idx}" style="background:{paper};border-left:4px solid {accent};">
  <div class="slide-inner">
    <div class="folio">№{idx}/{total}</div>
    <h2 style="color:{accent}">💡 {title}</h2>
    <ol class="quiz-list">{q_html}</ol>
  </div>
</section>"""


def _render_section_divider(slide: dict, palette: dict, idx: int, total: int) -> str:
    accent = palette["accent"]
    paper = palette["paper"]
    title = _esc(slide.get("title", "新章节"))
    return f"""<section class="slide divider" data-slide-id="{idx}" style="background:{accent};color:{paper};">
  <div class="slide-inner center">
    <div class="folio" style="color:rgba(255,255,255,0.5)">№{idx}/{total}</div>
    <h2 class="divider-title">{title}</h2>
  </div>
</section>"""


def _render_timeline(slide: dict, palette: dict, idx: int, total: int) -> str:
    accent = palette["accent"]
    paper = palette["paper"]
    ink = palette["ink"]
    title = _esc(slide.get("title", ""))
    events = slide.get("events", [])
    ev_html = "".join(
        f'<div class="timeline-event"><span class="tl-year">{_esc(e.get("year",""))}</span><span class="tl-dot"></span><div class="tl-desc">{_esc(e.get("desc",""))}</div></div>'
        for e in events
    )
    return f"""<section class="slide" data-slide-id="{idx}" style="background:{paper};">
  <div class="slide-inner">
    <div class="folio">№{idx}/{total}</div>
    <h2 class="section-title">{title}</h2>
    <div class="timeline">{ev_html}</div>
  </div>
</section>"""


def _render_three_sub_cards(slide: dict, palette: dict, idx: int, total: int) -> str:
    accent = palette["accent"]
    paper = palette["paper"]
    ink = palette["ink"]
    title = _esc(slide.get("title", ""))
    cards = slide.get("cards", [])
    c_html = "".join(
        f'<div class="sub-card"><h4>{_esc(c.get("title",""))}</h4><p>{_esc(c.get("desc",""))}</p></div>'
        for c in cards[:3]
    )
    return f"""<section class="slide" data-slide-id="{idx}" style="background:{paper};">
  <div class="slide-inner">
    <div class="folio">№{idx}/{total}</div>
    <h2 class="section-title hero-left">{title}</h2>
    <div class="three-cards">{c_html}</div>
  </div>
</section>"""


def _render_content(slide: dict, palette: dict, idx: int, total: int) -> str:
    """默认内容页。"""
    accent = palette["accent"]
    paper = palette["paper"]
    title = _esc(slide.get("title", f"第{idx}页"))
    content = _esc(slide.get("content", ""))
    return f"""<section class="slide" data-slide-id="{idx}" style="background:{paper};">
  <div class="slide-inner">
    <div class="folio">№{idx}/{total}</div>
    <h2 class="section-title">{title}</h2>
    <p class="body-text">{content}</p>
  </div>
</section>"""


def _esc(s: str) -> str:
    """基础 HTML 转义。"""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# HTML 渲染入口
# ---------------------------------------------------------------------------

def render_html(slides: list[dict[str, Any]], palette_key: str = "klein-blue") -> str:
    """将 slides JSON 渲染为完整单文件 HTML。"""
    palette = PALETTE.get(palette_key, PALETTE["klein-blue"])
    accent = palette["accent"]
    paper = palette["paper"]
    total = len(slides)
    slides_html = "\n".join(
        _render_slide(s, palette, i + 1, total) for i, s in enumerate(slides)
    )
    # NOTE: CSS 用双 {{}} 转义，JS 用双 {{}} 转义，slides_html 是变量用单层 {}
    css = (
        f"  * {{ margin:0; padding:0; box-sizing:border-box; }}\n"
        f"  body {{ background:#0a0a0a; font-family:'Inter','Noto Sans SC',sans-serif; }}\n"
        f"  .presentation {{ display:flex; flex-direction:column; gap:24px; padding:24px; }}\n"
        f"  .slide {{ width:100%; max-width:1280px; aspect-ratio:16/9; "
        f"position:relative; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,0.3); margin:0 auto; }}\n"
        f"  .slide.divider {{ display:flex; align-items:center; justify-content:center; }}\n"
        f"  .slide-inner {{ padding:48px; height:100%; display:flex; flex-direction:column; }}\n"
        f"  .center {{ align-items:center; text-align:center; justify-content:center; }}\n"
        f"  .folio {{ position:absolute; bottom:16px; right:24px; font-size:11px; color:#999; letter-spacing:.05em; }}\n"
        f"  .topic-tag {{ position:absolute; top:16px; left:24px; font-size:11px; "
        f"text-transform:uppercase; letter-spacing:.1em; color:#666; }}\n"
        f"  .cover-title {{ font-size:5vw; font-weight:700; letter-spacing:-.02em; margin-top:auto; }}\n"
        f"  .cover-subtitle {{ font-size:1.5vw; opacity:.7; margin-top:16px; }}\n"
        f"  .meta-row {{ font-size:11px; opacity:.5; margin-top:32px; }}\n"
        f"  .section-title {{ font-size:2vw; font-weight:700; margin-bottom:24px; "
        f"border-left:4px solid {accent}; padding-left:16px; }}\n"
        f"  .hero-left {{ border-left:none; padding-left:0; "
        f"border-bottom:2px solid {accent}; padding-bottom:12px; margin-bottom:32px; }}\n"
        f"  .statement-text {{ font-size:5vw; font-weight:800; line-height:1.1; "
        f"letter-spacing:-.03em; margin:auto 0; }}\n"
        f"  .hairline {{ height:2px; width:60px; margin:24px 0; }}\n"
        f"  .statement-body {{ font-size:1.1vw; line-height:1.6; color:#444; max-width:70%; }}\n"
        f"  .six-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; flex:1; }}\n"
        f"  .cell {{ border:1px solid #e0e0e0; padding:20px; }}\n"
        f"  .cell-num {{ font-size:11px; font-weight:700; color:{accent}; display:block; margin-bottom:8px; }}\n"
        f"  .cell h3 {{ font-size:1.1vw; font-weight:700; margin-bottom:6px; }}\n"
        f"  .cell p {{ font-size:.9vw; color:#555; line-height:1.5; }}\n"
        f"  .kpi-tower {{ display:flex; gap:32px; align-items:flex-end; flex:1; padding-top:24px; }}\n"
        f"  .kpi-bar {{ flex:1; background:{accent}; "
        f"display:flex; flex-direction:column; align-items:center; justify-content:flex-end; min-height:40px; }}\n"
        f"  .kpi-num {{ font-size:2vw; font-weight:800; color:{paper}; padding:8px; }}\n"
        f"  .kpi-label {{ font-size:.8vw; color:{paper}; text-align:center; padding:4px 8px 12px; }}\n"
        f"  .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:32px; flex:1; }}\n"
        f"  .col h4 {{ font-size:.9vw; text-transform:uppercase; letter-spacing:.08em; "
        f"color:{accent}; margin-bottom:12px; }}\n"
        f"  .code-list {{ list-style:none; }}\n"
        f"  .code-list li {{ font-family:'JetBrains Mono',monospace; "
        f"font-size:.85vw; background:#f4f4f4; padding:8px 12px; margin-bottom:6px; }}\n"
        f"  .concept-title {{ font-size:2.5vw; font-weight:800; margin-bottom:16px; }}\n"
        f"  .concept-body {{ font-size:1vw; line-height:1.7; color:#333; margin-bottom:24px; }}\n"
        f"  .quiz-list {{ list-style:none; font-size:1.1vw; line-height:2; }}\n"
        f"  .quiz-list li {{ padding:8px 0; border-bottom:1px solid #eee; }}\n"
        f"  .divider-title {{ font-size:5vw; font-weight:800; letter-spacing:-.02em; }}\n"
        f"  .timeline {{ display:flex; flex-direction:column; gap:16px; flex:1; }}\n"
        f"  .timeline-event {{ display:flex; align-items:center; gap:16px; }}\n"
        f"  .tl-year {{ font-size:.9vw; font-weight:700; color:{accent}; min-width:60px; }}\n"
        f"  .tl-dot {{ width:10px; height:10px; background:{accent}; border-radius:0; flex-shrink:0; }}\n"
        f"  .tl-desc {{ font-size:1vw; color:#333; border-left:1px solid #ddd; padding-left:16px; flex:1; }}\n"
        f"  .three-cards {{ display:grid; grid-template-columns:repeat(3,1fr); gap:20px; }}\n"
        f"  .sub-card {{ background:#f5f5f5; padding:20px; }}\n"
        f"  .sub-card h4 {{ font-size:1vw; font-weight:700; margin-bottom:8px; }}\n"
        f"  .sub-card p {{ font-size:.85vw; color:#555; line-height:1.5; }}\n"
        f"  .body-text {{ font-size:1.1vw; line-height:1.7; color:#333; flex:1; }}\n"
        "  @media (max-width:768px) {\n"
        "    .slide { aspect-ratio:auto; min-height:480px; }\n"
        "    .six-grid,.two-col,.three-cards { grid-template-columns:1fr; }\n"
        "    .kpi-tower { flex-wrap:wrap; }\n"
        "  }\n"
    )
    js = (
        "  const slides = document.querySelectorAll('.slide');\n"
        "  let current = 0;\n"
        "  function show(n) {\n"
        "    slides.forEach((s,i)=>s.style.display=i===n?'flex':'none');\n"
        "    current = n;\n"
        "    location.hash = n;\n"
        "  }\n"
        "  document.addEventListener('keydown', e => {\n"
        "    if(e.key==='ArrowRight'||e.key==='ArrowDown') show(Math.min(current+1,slides.length-1));\n"
        "    if(e.key==='ArrowLeft'||e.key==='ArrowUp') show(Math.max(current-1,0));\n"
        "    if(e.key==='Home') show(0);\n"
        "    if(e.key==='End') show(slides.length-1);\n"
        "  });\n"
        "  const saved = parseInt(location.hash.slice(1));\n"
        "  if(!isNaN(saved)&&saved>=0&&saved<slides.length) show(saved);\n"
        "  else show(0);\n"
    )
    return (
        "<!doctype html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"UTF-8\">\n"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "<title>课件预览</title>\n<style>\n" + css + "</style>\n</head>\n<body>\n"
        "<div class=\"presentation\">\n" + slides_html + "\n</div>\n"
        "<script>\n" + js + "</script>\n</body>\n</html>"
    )


# ---------------------------------------------------------------------------
# Deck Generator 主类
# ---------------------------------------------------------------------------

class DeckGenerator:
    """deck-swiss-edu 生成器。"""

    # 内嵌的 SKILL.md 布局规范（generator.py 不依赖外部文件）
    SKILL_BODY = Path(__file__).read_text(encoding="utf-8")

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm = llm_client

    def generate(
        self,
        intent: dict[str, Any],
        evidence_packet: Optional[dict[str, Any]] = None,
        nodes: Optional[list[dict[str, Any]]] = None,
        palette: str = "klein-blue",
    ) -> dict[str, Any]:
        """
        主入口：intent + evidence → slides JSON

        若传入 nodes（已有节点树），直接将节点渲染为幻灯片，跳过 LLM 调用。

        Returns:
            {
              "slides": [...],          # 幻灯片数组
              "palette": str,          # 配色方案
              "html_url": str,         # 保存后的 URL（可选）
              "html_path": str,        # 本地路径（可选）
            }
        """
        # 有节点树 → 直接渲染，跳过 LLM
        if nodes:
            slides = self._nodes_to_slides(nodes)
        else:
            # 1. 构建 prompt
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(intent, evidence_packet)

            # 2. 调用 LLM
            slides = []
            try:
                llm = self._get_llm()
                result = llm.chat_json(
                    system_prompt,
                    user_prompt,
                    temperature=0.3,
                )
                # 成功时 result 应为 {"slides": [...]}；若含 error 键说明 API 调用失败
                if isinstance(result, dict) and "error" in result:
                    import sys as _sys
                    _sys.stderr.write(f"[DeckGenerator] LLM API error: {result.get('error')}\n")
                    slides = self._fallback_slides(intent)
                else:
                    slides = result.get("slides") if isinstance(result, dict) else result
                    if not isinstance(slides, list):
                        slides = self._fallback_slides(intent)
            except Exception as e:
                import sys as _sys, traceback
                _sys.stderr.write(f"[DeckGenerator] LLM exception: {e}\n{traceback.format_exc()}\n")
                slides = self._fallback_slides(intent)

        # 3. 保存 HTML
        html = render_html(slides, palette)
        # 始终使用 ASCII 安全文件名，避免 URL 编码问题
        ascii_title = str(intent.get("title", "course"))
        safe_name = ascii_title.encode("ascii", "ignore").decode("ascii") or "course"
        safe_name = "".join(c if c.isalnum() else "_" for c in safe_name).strip("_") or "course"
        output_dir = Path("uploads/previews")
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{safe_name}_{uuid.uuid4().hex[:8]}.html"
        output_path = output_dir / filename
        output_path.write_text(html, encoding="utf-8")

        return {
            "slides": slides,
            "palette": palette,
            "html_path": str(output_path),
            "html_url": f"/previews/{filename}",
            "page_count": len(slides),
        }

    def _nodes_to_slides(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将已有节点树直接转换为幻灯片数据，跳过 LLM 生成。"""
        slides = []
        # 封面
        slides.append({
            "layout": "S01",
            "title": "课件",
            "subtitle": "AI 智课课件",
        })
        # 每个节点一页
        layouts = ["S23", "S06", "S10", "S14", "S18"]
        for i, node in enumerate(nodes):
            title = node.get("title") or node.get("node_id") or f"第{i+1}节"
            content = node.get("summary") or node.get("content") or node.get("script") or ""
            slides.append({
                "layout": layouts[i % len(layouts)],
                "title": title,
                "content": content,
                "key_points": [],
                "examples": [],
            })
        # 结尾页
        slides.append({"layout": "S26", "title": "课程小结"})
        return slides

    def _get_llm(self) -> LLMClient:
        if self._llm is not None:
            return self._llm
        return LLMClient(temperature=0.3)

    def _build_system_prompt(self) -> str:
        return (
            "你是教学幻灯片生成专家。严格按以下 JSON Schema 输出，"
            "不允许输出 JSON 以外的任何内容。\n\n"
            '格式: {"slides": [{"layout": "S01".."S26", "title": "...", "content": "...", ...}]}\n\n'
            f"{self.SKILL_BODY}"
        )

    def _build_user_prompt(self, intent: dict[str, Any], evidence: Optional[dict[str, Any]]) -> str:
        title = intent.get("title", "未命名课程")
        description = intent.get("description", "")
        key_points = intent.get("key_points", [])
        kp_text = "\n".join(f"- {kp}" for kp in key_points) if key_points else "（无明确要点）"

        evidence_text = ""
        if evidence:
            chunks = evidence.get("chunks", []) or evidence.get("relevant_chunks", [])
            if chunks:
                evidence_text = "\n参考材料：\n" + "\n".join(
                    f"- {str(c.get('content', ''))[:200]}" for c in chunks[:5]
                )

        return (
            f"课程标题：{title}\n"
            f"课程描述：{description}\n"
            f"核心知识点：\n{kp_text}\n"
            f"{evidence_text}\n\n"
            "请根据以上信息生成教学幻灯片 JSON，布局代号必须从 S01-S26 中选择，"
            "每个知识点对应 1-2 张幻灯片，保持内容简洁专业。"
        )

    def _fallback_slides(self, intent: dict[str, Any]) -> list[dict[str, Any]]:
        """LLM 不可用时的兜底幻灯片。"""
        title = str(intent.get("title", "课件"))
        kps = intent.get("key_points", [title])
        slides = [
            {"layout": "S01", "title": title, "subtitle": "AI 智能生成课件", "meta": {"topic": title}},
        ]
        for i, kp in enumerate(kps[:8], start=1):
            slides.append({
                "layout": "S23",
                "title": str(kp),
                "content": f"围绕「{kp}」进行讲授。",
                "examples": [],
                "key_points": [f"掌握 {kp} 的核心概念", f"理解 {kp} 的应用场景"],
            })
        slides.append({"layout": "S26", "title": "课程小结"})
        return slides
