import json
from pathlib import Path
from .catalog import get_theme, available_themes, PPTTheme

_LAYOUTS_DIR = Path(__file__).parent / "layouts"
_cached_layouts: dict[str, dict] = {}

def get_layout(layout_id: str) -> dict:
    """从layouts目录加载版式配置，带缓存。"""
    if layout_id in _cached_layouts:
        return _cached_layouts[layout_id]
    layout_path = _LAYOUTS_DIR / f"{layout_id}.json"
    if not layout_path.exists():
        layout_path = _LAYOUTS_DIR / "content_left_right.json"
    with open(layout_path, "r", encoding="utf-8") as f:
        layout = json.load(f)
    _cached_layouts[layout_id] = layout
    return layout

__all__ = ["get_theme", "available_themes", "PPTTheme", "get_layout"]
