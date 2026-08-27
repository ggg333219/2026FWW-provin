"""
预览渲染模块 — S4 个性化满足

职责：
  结构化节点数组 → HTML 预览（教师审阅界面可用）

流程：
  nodes → preview_renderer → HTML（可嵌入前端 iframe / 独立页面）
"""

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PreviewConfig:
    """预览渲染配置"""
    template_dir: str = ""


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
        return self._wrap_html(course_name, slides_html)

    def render_node(self, node: dict[str, Any], index: int = 1) -> str:
        """生成单个节点的预览 HTML"""
        return self._render_slide(node, index)

    # ── 幻灯片构建 ──

    def _build_slides(self, nodes: list[dict[str, Any]]) -> str:
        slides = []
        for idx, node in enumerate(nodes, start=1):
            slides.append(self._render_slide(node, idx))
        return "\n".join(slides)

    def _render_slide(self, node: dict[str, Any], index: int) -> str:
        node_type = node.get("type") or node.get("node_type") or "content"
        title = html.escape(str(node.get("title") or f"第{index}页"))
        templates = {
            "title": self._slide_title,
            "section": self._slide_section,
            "content": self._slide_content,
            "quiz": self._slide_quiz,
            "summary": self._slide_summary,
        }
        renderer = templates.get(node_type, self._slide_content)
        return renderer(node, index, title)

    def _slide_title(self, node: dict, index: int, title: str) -> str:
        subtitle = html.escape(str(node.get("content") or node.get("summary") or ""))
        return f"""<div class="slide title-slide">
  <div class="slide-num">{index}</div>
  <h1>{title}</h1>
  {f'<p class="subtitle">{subtitle}</p>' if subtitle else ''}
</div>"""

    def _slide_section(self, node: dict, index: int, title: str) -> str:
        return f"""<div class="slide section-slide">
  <div class="slide-num">{index}</div>
  <h2>{title}</h2>
  <div class="divider"></div>
</div>"""

    def _slide_content(self, node: dict, index: int, title: str) -> str:
        body_parts = []
        for key in ("content", "script", "summary"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                body_parts.append(f"<p>{html.escape(val)}</p>")
            elif isinstance(val, list):
                for item in val:
                    body_parts.append(f"<li>{html.escape(str(item))}</li>")
                if val:
                    body_parts = ["<ul>"] + body_parts + ["</ul>"]

        segments_html = ""
        segments = node.get("segments") or []
        if segments:
            seg_items = []
            for s in segments:
                text = html.escape(str(s.get("text") or ""))
                seg_type = s.get("segment_type", "")
                badge = f'<span class="badge badge-{seg_type}">{seg_type}</span>' if seg_type else ""
                dur = s.get("estimated_seconds", 0)
                dur_str = f' <span class="dur">{dur}s</span>' if dur else ""
                seg_items.append(f"<li>{badge} {text}{dur_str}</li>")
            segments_html = "<h4>讲授分段</h4><ol class='segments'>" + "".join(seg_items) + "</ol>"

        return f"""<div class="slide content-slide">
  <div class="slide-num">{index}</div>
  <h2>{title}</h2>
  <div class="body">{"".join(body_parts)}</div>
  {segments_html}
</div>"""

    def _slide_quiz(self, node: dict, index: int, title: str) -> str:
        questions = node.get("questions") or node.get("interactive_questions") or []
        items = "".join(
            f"<li>❓ {html.escape(str(q))}</li>" for q in questions
        )
        return f"""<div class="slide quiz-slide">
  <div class="slide-num">{index}</div>
  <h2>💡 {title}</h2>
  <ol class="questions">{items}</ol>
</div>"""

    def _slide_summary(self, node: dict, index: int, title: str) -> str:
        points = node.get("key_points") or node.get("core_points") or node.get("content", "").split("\n") or []
        items = "".join(f"<li>✅ {html.escape(str(p))}</li>" for p in points[:6] if p.strip())
        return f"""<div class="slide summary-slide">
  <div class="slide-num">{index}</div>
  <h2>📌 本节小结</h2>
  <ul class="key-points">{items}</ul>
</div>"""

    # ── HTML 包装 ──

    def _wrap_html(self, title: str, slides_html: str) -> str:
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
  .slide {{ background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);
           padding: 40px; margin-bottom: 24px; position: relative; min-height: 300px; }}
  .slide-num {{ position: absolute; top: 12px; right: 16px; font-size: 13px; color: #999; }}
  h1 {{ font-size: 32px; text-align: center; margin-top: 80px; }}
  h2 {{ font-size: 24px; margin-bottom: 16px; color: #1a1a2e; }}
  .subtitle {{ text-align: center; font-size: 18px; color: #666; margin-top: 16px; }}
  .divider {{ width: 60px; height: 4px; background: #4361ee; margin: 20px 0; }}
  .body {{ font-size: 15px; line-height: 1.8; color: #333; }}
  .body p {{ margin-bottom: 8px; }}
  .body ul {{ padding-left: 20px; }}
  .body li {{ margin-bottom: 4px; }}
  .segments {{ margin-top: 16px; padding-left: 20px; }}
  .segments li {{ margin-bottom: 8px; font-size: 14px; line-height: 1.6; }}
  .badge {{ display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 10px;
           margin-right: 6px; font-weight: 600; }}
  .badge-opening {{ background: #e3f2fd; color: #1565c0; }}
  .badge-explanation {{ background: #f3e5f5; color: #7b1fa2; }}
  .badge-example {{ background: #e8f5e9; color: #2e7d32; }}
  .badge-interaction {{ background: #fff3e0; color: #e65100; }}
  .badge-transition {{ background: #fce4ec; color: #c62828; }}
  .badge-summary {{ background: #e8eaf6; color: #283593; }}
  .dur {{ font-size: 12px; color: #999; }}
  .title-slide {{ background: linear-gradient(135deg, #4361ee, #7209b7); color: #fff; }}
  .title-slide h1 {{ color: #fff; }}
  .title-slide .subtitle {{ color: #ddd; }}
  .section-slide {{ background: linear-gradient(135deg, #f72585, #b5179e); color: #fff; }}
  .section-slide h2 {{ color: #fff; }}
  .quiz-slide {{ border-left: 4px solid #f72585; }}
  .summary-slide {{ border-left: 4px solid #4361ee; background: #f8f9ff; }}
  .questions li {{ margin-bottom: 8px; font-size: 15px; }}
  .key-points li {{ margin-bottom: 6px; font-size: 15px; }}
</style>
</head>
<body>
<div class="presentation">
{slides_html}
</div>
</body>
</html>"""
