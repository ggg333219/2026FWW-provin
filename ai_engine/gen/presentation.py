"""S3 课件样式层（metadata.presentation）的单一事实来源。

预览 HTML（gen/preview.py）与 PPTX 导出（gen/export_ppt.py）共用本模块的映射表，
避免两侧各持一份取值而再次漂移 —— 历史上正是"只有预览读样式层、导出不读"
导致了"预览是新样式、导出的 PPT 还是老样式"。

样式来自节点 metadata.presentation，由前端在 S3 页面选择后写入，
Go 侧（internal/service/courseware_service.go）负责落库与回填。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

from .templates import PPTTheme, get_theme

PRESENTATION_KEYS = ("palette", "layout", "font_family", "density")

PRESENTATION_DEFAULTS: dict[str, str] = {
    "palette": "classic",
    "layout": "balanced",
    "font_family": "system",
    "density": "comfortable",
}

# 5 元组顺序与 preview.py 的 CSS 变量一一对应：
# (--preview-accent, --preview-page-bg, --preview-ink, --preview-accent-soft, --preview-deep)
PALETTES: dict[str, tuple[str, str, str, str, str]] = {
    "classic": ("#168f82", "#eef3f1", "#18322f", "#d9ebe6", "#0b4f49"),
    "klein-blue": ("#315fd4", "#eef2f8", "#17253f", "#dce5f6", "#203f98"),
    # 以下三套取自 skills/deck_swiss_edu/pptx_renderer.py 的 PALETTES。
    # 该技能里的 ink 是"压在强调色上的文字色"（safety-orange 甚至是纯白），
    # 直接当正文色会在浅底上不可读，故此处统一改用深色 ink；
    # accent / paper / light 沿用技能原值，paper 与 light 兼作浅底与浅色面。
    "lemon-yellow": ("#FFD500", "#F7F5EE", "#0A0A0A", "#F0EDDA", "#B89400"),
    "neon-green": ("#C5E003", "#F7F5EE", "#0A0A0A", "#EEF5D8", "#7E8F02"),
    "safety-orange": ("#FF6B35", "#F7F5EE", "#1A1A1A", "#FDE8DF", "#C2431A"),
}

FALLBACK_PALETTE = "classic"

PALETTE_NAMES = {
    "classic": "经典教学",
    "klein-blue": "瑞士教育风 · 克莱因蓝",
    "lemon-yellow": "瑞士教育风 · 柠檬黄",
    "neon-green": "瑞士教育风 · 荧光绿",
    "safety-orange": "瑞士教育风 · 安全橙",
}

FONT_STACKS = {
    "system": "-apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif",
    "source-han": "'Source Han Sans SC', 'Noto Sans CJK SC', sans-serif",
    "serif": "'Songti SC', 'STSong', 'SimSun', serif",
}
FALLBACK_FONT_STACK = FONT_STACKS["system"]

# CSS 字体栈不能直接交给 python-pptx（它要一个具体字体名）。
# 这里取各栈里 Windows/Office 上真实可用的那一个，按栈内回退顺序就近选择。
PPTX_FONTS = {
    "system": "Microsoft YaHei",
    "source-han": "Source Han Sans SC",
    "serif": "SimSun",
}
FALLBACK_PPTX_FONT = PPTX_FONTS["system"]

DENSITY_PADDING = {
    "minimal": "56px 64px 60px",
    "compact": "36px 44px 40px",
    "comfortable": "44px 52px 48px",
}
FALLBACK_DENSITY_PADDING = DENSITY_PADDING["comfortable"]


@dataclass(frozen=True)
class DensityProfile:
    """Shared content typography for HTML preview and editable PPTX export."""

    body_text_pt: int
    body_point_pt: int
    conclusion_pt: int
    key_point_max_pt: int
    preview_body_px: int
    preview_point_px: int
    preview_conclusion_px: int
    card_gap_px: int
    card_padding_px: int


DENSITY_PROFILES = {
    "compact": DensityProfile(13, 12, 20, 15, 13, 13, 19, 6, 5),
    "comfortable": DensityProfile(15, 14, 22, 17, 15, 15, 21, 10, 7),
    "minimal": DensityProfile(17, 16, 24, 19, 17, 17, 23, 14, 9),
}


def density_profile(value: str | None) -> DensityProfile:
    return DENSITY_PROFILES.get(str(value or "").strip().lower(), DENSITY_PROFILES["comfortable"])


@dataclass(frozen=True)
class ContentGeometry:
    """Content-slide panel bounds in inches, shared by SVG and PPTX."""

    left: tuple[float, float]
    right: tuple[float, float]
    top: float
    height: float
    figure_height: float
    body: tuple[float, float]

    @property
    def wide_right(self) -> tuple[float, float]:
        return (self.left[0], round(self.right[0] + self.right[1] - self.left[0], 2))


CONTENT_GEOMETRIES = {
    "compact": ContentGeometry((0.48, 3.20), (3.88, 8.96), 1.30, 5.58, 2.30, (3.76, 3.12)),
    "comfortable": ContentGeometry((0.72, 3.60), (4.52, 8.08), 1.42, 5.35, 2.45, (4.01, 2.76)),
    "minimal": ContentGeometry((1.10, 3.52), (5.02, 7.20), 1.58, 5.05, 2.20, (3.94, 2.69)),
}


def content_geometry(value: str | None, layout: str | None = "balanced") -> ContentGeometry:
    base = CONTENT_GEOMETRIES.get(str(value or "").strip().lower(), CONTENT_GEOMETRIES["comfortable"])
    mode = str(layout or "balanced").strip().lower()
    if mode not in ("visual", "text"):
        return base
    # Both modes widen the main column; visual additionally gives the figure
    # more vertical space, while text mode suppresses the figure at render time.
    shift = 0.65 if mode == "visual" else 0.50
    figure_extra = 0.50 if mode == "visual" else 0.0
    return replace(
        base,
        left=(base.left[0], base.left[1] - shift),
        right=(base.right[0] - shift, base.right[1] + shift),
        figure_height=base.figure_height + figure_extra,
        body=(base.body[0] + figure_extra, base.body[1] - figure_extra),
    )

# 选了模板但没显式给 palette 时，用该模板自带的默认配色兜底
TEMPLATE_DEFAULT_PALETTE = {"deck-swiss-edu": "klein-blue"}


def presentation_from_nodes(nodes: Iterable[Any]) -> tuple[dict[str, str], set[str]]:
    """读取节点样式层，返回 (补齐默认值后的配置, 用户显式给出的键集合)。

    与 Go 侧 presentationFromNodes 一致，只看首个 dict 节点：
    metadata.presentation 优先，节点顶层 presentation 兜底。
    """
    values = dict(PRESENTATION_DEFAULTS)
    explicit: set[str] = set()
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        metadata = node.get("metadata") or {}
        presentation = metadata.get("presentation") or node.get("presentation") or {}
        if isinstance(presentation, dict):
            for key in PRESENTATION_KEYS:
                value = str(presentation.get(key) or "").strip()
                if value:
                    values[key] = value
                    explicit.add(key)
            break
    return values, explicit


def apply_export_presentation(nodes: list[dict[str, Any]],
                              presentation: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Attach a version's global style to the first export node without mutating its snapshot."""
    if not nodes or not isinstance(presentation, dict) or not presentation:
        return nodes
    first = dict(nodes[0])
    metadata = dict(first.get("metadata") or {})
    current = metadata.get("presentation")
    metadata["presentation"] = {
        **(current if isinstance(current, dict) else {}), **presentation,
    }
    first["metadata"] = metadata
    return [first, *nodes[1:]]


def _luminance(value: str) -> float:
    """WCAG 相对亮度，用于决定压在主色上的文字取白还是取黑。"""
    channels = []
    for i in (0, 2, 4):
        raw = int(value.lstrip("#")[i:i + 2], 16) / 255
        channels.append(raw / 12.92 if raw <= 0.03928 else ((raw + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _norm(value: str) -> str:
    """统一为主题令牌写法：不带 # 的大写十六进制（与 catalog.py 一致）。"""
    return value.lstrip("#").upper()


def _mix(color: str, toward: str, ratio: float) -> str:
    """与 export_ppt.PPTExporter._blend 同一算法，供本模块独立构建令牌。

    返回不带 # 的十六进制，与 catalog.py 里主题令牌的写法保持一致。
    """
    source, target = color.lstrip("#"), toward.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        base, other = int(source[i:i + 2], 16), int(target[i:i + 2], 16)
        channels.append(max(0, min(255, round(base * (1 - ratio) + other * ratio))))
    return "{:02X}{:02X}{:02X}".format(*channels)


def theme_from_palette(palette_key: str, font_family: str = "system") -> PPTTheme:
    """把预览调色板映射为 PPTX 主题令牌。

    primary / secondary / accent 都取调色板自身的强调色与深色版，
    inverse 按主色亮度自动选白或近黑（柠檬黄这类亮色上必须用深色字）。
    """
    key = palette_key if palette_key in PALETTES else FALLBACK_PALETTE
    accent, page_bg, ink, accent_soft, deep = PALETTES[key]
    font = PPTX_FONTS.get(font_family, FALLBACK_PPTX_FONT)
    return PPTTheme(
        template_id=key,
        display_name=PALETTE_NAMES.get(key, key),
        primary=_norm(accent),
        secondary=_norm(deep),
        accent=_norm(deep),
        background=_norm(page_bg),
        surface=_norm(accent_soft),
        text=_norm(ink),
        muted=_mix(ink, page_bg, 0.45),
        inverse=_norm("#FFFFFF" if _luminance(accent) < 0.45 else "#0A0A0A"),
        title_font=font,
        body_font=font,
    )


def presentation_to_theme(
    values: dict[str, str],
    explicit: set[str],
    template_id: str | None = None,
) -> tuple[PPTTheme, bool]:
    """样式层 → PPTX 主题。返回 (主题, 是否启用了样式层)。

    取值顺序与预览完全一致（见 preview.PreviewRenderer._theme_from_presentation）：
    用户显式选的 palette → 模板自带的 palette → 默认调色板 classic。

    这里以前在没有 palette 时回落到 catalog 主题（primary 2D5F58、accent E89B52），
    而预览从来不用 catalog —— 于是"没选样式"的课件，预览是亮青绿的 classic，
    导出是暗墨绿的 catalog.default，八个令牌没一个对得上。预览是样式的单一事实
    来源，导出跟着它走，两边才会是同一页。

    `styled` 保留在返回值里供调用方判断"是否套用了调色板"；现在这条路径恒为 True
    —— 预览从不以"无样式"渲染，导出也不该。
    """
    palette_key = values.get("palette") if "palette" in explicit else None
    if not palette_key:
        palette_key = TEMPLATE_DEFAULT_PALETTE.get(str(template_id or "").strip().lower())
    font_family = values.get("font_family") if "font_family" in explicit else "system"

    if palette_key in PALETTES:
        return theme_from_palette(palette_key, font_family or "system"), True

    # 自带配色的 catalog 主题（academic / minimal）继续保留，只有 default 让位给 classic
    theme = get_theme(template_id)
    if theme.template_id != "default":
        if "font_family" in explicit:
            font = PPTX_FONTS.get(values.get("font_family") or "")
            if font:
                theme = replace(theme, title_font=font, body_font=font)
        return theme, True

    return theme_from_palette(FALLBACK_PALETTE, font_family or "system"), True
