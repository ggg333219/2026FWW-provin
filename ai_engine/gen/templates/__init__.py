"""教学 PPT 模板注册表。

模板不依赖位图背景；导出器使用原生 PowerPoint 形状和文本框应用这些设计令牌，
因此 Office/WPS 中的全部内容都可以继续编辑。
"""

from .catalog import PPTTheme, available_themes, get_theme

__all__ = ["PPTTheme", "available_themes", "get_theme"]
