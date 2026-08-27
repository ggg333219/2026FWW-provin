"""三套教学专用 PPT 主题及兼容别名。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PPTTheme:
    """用于原生 PPTX 形状的稳定设计令牌。"""

    template_id: str
    display_name: str
    primary: str
    secondary: str
    accent: str
    background: str
    surface: str
    text: str
    muted: str
    inverse: str
    title_font: str = "Microsoft YaHei"
    body_font: str = "Microsoft YaHei"


_THEMES = {
    "default": PPTTheme(
        template_id="default",
        display_name="通用教学",
        primary="245B78",
        secondary="2F7E83",
        accent="E89B52",
        background="F5F8FA",
        surface="FFFFFF",
        text="183042",
        muted="627987",
        inverse="FFFFFF",
    ),
    "academic": PPTTheme(
        template_id="academic",
        display_name="学术教学",
        primary="17365D",
        secondary="315B7D",
        accent="B9975B",
        background="F5F3EE",
        surface="FFFFFF",
        text="17263B",
        muted="667284",
        inverse="FFFFFF",
        title_font="Microsoft YaHei",
        body_font="SimSun",
    ),
    "minimal": PPTTheme(
        template_id="minimal",
        display_name="简约教学",
        primary="202124",
        secondary="5F6368",
        accent="1A73E8",
        background="FFFFFF",
        surface="F7F8F9",
        text="202124",
        muted="6B7075",
        inverse="FFFFFF",
    ),
}

_ALIASES = {
    "compact": "minimal",
    "widescreen": "default",
}


def get_theme(template_id: str | None) -> PPTTheme:
    """返回主题；历史模板 ID 自动映射，未知 ID 安全回退到 default。"""

    normalized = str(template_id or "default").strip().lower()
    normalized = _ALIASES.get(normalized, normalized)
    return _THEMES.get(normalized, _THEMES["default"])


def available_themes() -> tuple[str, ...]:
    """返回对外稳定的教学模板 ID。"""

    return tuple(_THEMES)
