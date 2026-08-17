"""gen — AI Engine 生成模块（S3 课件生成 + S4 个性化满足）

替代原有单块 generator.py，按业务域拆分。

使用方法：
    from ai_engine.gen import (
        OutlineBuilder, OutlineConfig,
        NodeGenerator, NodeGenConfig,
        PPTExporter, ExportPPTConfig,
        DOCExporter, ExportDocConfig,
        PreviewRenderer,
        CommandParser, EditCommand, CommandType,
        NodePatcher,
        InteractiveBuilder,
        get_version_manager,
    )
"""

# S3 课件生成
from .outline import OutlineBuilder, OutlineConfig
from .node import NodeGenerator, NodeGenConfig
from .export_ppt import PPTExporter, ExportPPTConfig
from .export_doc import DOCExporter, ExportDocConfig
from .interactive import InteractiveBuilder

# S4 个性化满足
from .preview import PreviewRenderer
from .commands import CommandParser, EditCommand, CommandType
from .patch import NodePatcher
from .version import get_version_manager

__all__ = [
    # S3
    "OutlineBuilder", "OutlineConfig",
    "NodeGenerator", "NodeGenConfig",
    "PPTExporter", "ExportPPTConfig",
    "DOCExporter", "ExportDocConfig",
    "InteractiveBuilder",
    # S4
    "PreviewRenderer",
    "CommandParser", "EditCommand", "CommandType",
    "NodePatcher",
    "get_version_manager",
]