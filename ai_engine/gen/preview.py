"""
预览渲染模块 — S4 个性化满足

职责：
  结构化节点数组 → HTML 预览（教师审阅界面可用）

流程：
  nodes → preview_renderer → HTML（可嵌入前端 iframe / 独立页面）

渲染分工（改动后）
-----------------
每页保留 `<div class="slide xxx-slide">` 外壳（页码、页型 class），**页内内容由
gen/svg_renderer.py 渲染的 SVG 承载**。内容该画哪些字段不再由本模块决定 ——
那是 gen/page_spec.py 的职责；本模块只负责「外壳 class 与整页 CSS」。

这样做的原因：此前预览、PPTX 导出、SVG 三个渲染器各自去 node 里挑字段，
同一个页面三处内容对不上，局部修改只在预览里可见。字段挑选收敛到 page_spec
之后，渲染器之间只剩下摆版差异。

兼容规则：
  - 页面类型双字段识别：优先读 type，兜底读 node_type，均缺失时默认 content
    （实现已移到 page_spec.resolve_kind，这里保留同名方法转发）
  - 要点字段双向兼容、分段兜底标签、script 缺失不产生空区块等规则
    同样收敛到 page_spec，见该模块文档
"""

import html
from dataclasses import dataclass
from typing import Any

from .page_spec import build_page_spec, resolve_kind
from .polish import polish_nodes
from .presentation import (
    DENSITY_PADDING,
    FALLBACK_DENSITY_PADDING,
    FALLBACK_FONT_STACK,
    FALLBACK_PALETTE,
    FONT_STACKS,
    PALETTES,
    presentation_from_nodes,
    theme_from_palette,
)
from .svg_renderer import render_page_spec_to_svg
from .templates import PPTTheme


@dataclass
class PreviewConfig:
    """预览渲染配置"""
    template_dir: str = ""


#: 页面类型 → slide 外壳的 class（顺序即 HTML 上的 class 顺序，勿改）
_SLIDE_CLASSES = {
    "cover": "cover-slide",
    "section": "section-slide",
    "quiz": "quiz-slide",
    "interactive": "quiz-slide interactive-slide",
    "summary": "summary-slide",
    "content": "content-slide",
}


class PreviewRenderer:
    """结构化节点 → HTML 预览渲染器

    每次 render / render_node 都会按该批节点的样式层重算主题，
    因此「改完样式 → 重新渲染」时 SVG 的配色与整页 CSS 同步变化。
    """

    def __init__(self) -> None:
        #: 当前批次的主题；未经过 render 直接调 _render_slide 时用默认调色板兜底
        self._theme = theme_from_palette(FALLBACK_PALETTE)

    def render(self, nodes: list[dict[str, Any]], course_name: str = "课件预览") -> str:
        """生成完整 HTML 预览页面

        Args:
            nodes: 结构化节点数组
            course_name: 课程名称

        Returns:
            HTML 字符串（可直接嵌入 iframe 或保存为 .html）
        """
        polished_nodes = polish_nodes(nodes)
        presentation = self._presentation_from_nodes(polished_nodes)
        self._theme = self._theme_from_presentation(presentation)
        slides_html = self._build_slides(polished_nodes)
        return self._wrap_html(course_name, slides_html, presentation)

    @staticmethod
    def _presentation_from_nodes(nodes: list[dict[str, Any]]) -> dict[str, str]:
        """读取前端样式层写入节点 metadata 的全局呈现配置。

        映射表与 PPTX 导出共用 gen/presentation.py，保证两端取值不会漂移。
        """
        return presentation_from_nodes(nodes)[0]

    @staticmethod
    def _theme_from_presentation(presentation: dict[str, str]) -> PPTTheme:
        """样式层 → SVG 用的主题令牌。

        预览的默认调色板历来是 classic（`_wrap_html` 的 `PALETTES[FALLBACK_PALETTE]`），
        所以这里直接用 `theme_from_palette` 而不是 `presentation_to_theme` ——
        后者的 catalog 兜底（2D5F58）是导出侧的默认，会给历史课件换色。
        两个函数都在 presentation.py 里，调色板取值仍是同一张表。
        """
        palette = presentation.get("palette", FALLBACK_PALETTE)
        font_family = presentation.get("font_family", "system")
        return theme_from_palette(
            palette if palette in PALETTES else FALLBACK_PALETTE,
            font_family if font_family in FONT_STACKS else "system",
        )

    def render_node(self, node: dict[str, Any], index: int = 1) -> str:
        """生成单个节点的预览 HTML"""
        self._theme = self._theme_from_presentation(self._presentation_from_nodes([node]))
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
        """双字段识别页面类型（实现见 page_spec.resolve_kind）。

        兼容 Pydantic 枚举（NodeType.SECTION）与纯字符串两种形态。
        """
        return resolve_kind(node)

    def _render_slide(self, node: dict[str, Any], index: int) -> str:
        node_type = self._resolve_type(node)
        slide_class = _SLIDE_CLASSES.get(node_type, _SLIDE_CLASSES["content"])
        # 页型同步传给 build_page_spec，避免在这里与 _resolve_type 各判一次
        spec = build_page_spec(node, index, node_type)
        svg = render_page_spec_to_svg(spec, self._theme)
        return f"""<div class="slide {slide_class}">
  <div class="slide-num">{index}</div>
  {svg}
</div>"""

    # ── HTML 包装 ──

    def _wrap_html(self, title: str, slides_html: str, presentation: dict[str, str] | None = None) -> str:
        presentation = presentation or self._presentation_from_nodes([])
        palette = presentation.get("palette", "classic")
        layout = presentation.get("layout", "balanced")
        font_family = presentation.get("font_family", "system")
        density = presentation.get("density", "comfortable")
        # 取值来自 gen/presentation.py，与 PPTX 导出共用同一张表
        palette_css = PALETTES.get(palette, PALETTES[FALLBACK_PALETTE])
        font_css = FONT_STACKS.get(font_family, FALLBACK_FONT_STACK)
        padding_css = DENSITY_PADDING.get(density, FALLBACK_DENSITY_PADDING)
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

  /* ── 页内 SVG：内容由 svg_renderer 摆版，随 slide 宽度等比缩放 ── */
  .slide > svg {{ display: block; width: 100%; height: auto; }}
  .svg-block {{ overflow: hidden; }}
  /* 次要区块（要点 / 讲稿原文）降一档字重与饱和度，让分段占据视觉主位 */
  .svg-block-secondary {{ font-size: 93%; opacity: .92; }}
  .svg-block-secondary .key-points li {{ padding: 7px 12px 7px 34px; background: rgba(0,0,0,.02);
                                         border: 1px dashed rgba(0,0,0,.09); }}
  .svg-block-secondary .key-points li::before {{ content: "·"; top: 6px; }}
  .svg-block-secondary .script-block {{ border-left-width: 3px; background: rgba(0,0,0,.015); }}

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
