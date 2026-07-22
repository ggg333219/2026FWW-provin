"""
ai_engine/core — 共享基础设施

所有 Skill 模块 (intent/, gen/, rag/, parse/) 从这里导入共享能力，
而非各自从 qa.py / schema.py 复制粘贴。

向后兼容说明：
  - 现有代码 (qa.py, generator.py, main.py, parser.py, recommender.py)
    不受影响，继续使用原有导入路径。
  - 新 Skill 代码统一使用 core/ 模块。
"""

from .config import settings
from .llm import LLMClient, resolve_llm_base_url, extract_json
from .schema import (
    # 枚举
    SessionStatus,
    TurnType,
    GenerationStatus,
    GenerationStage,
    NodeType,
    ModifyCommandType,
    SourceType,
    ParseStatus,
    ExportFormat,
    ExportStatus,
    # S1
    IntentSummary,
    DialogueTurn,
    ConversationSession,
    # S2
    MaterialAsset,
    Chunk,
    # KB
    SearchResult,
    Citation,
    EvidencePacket,
    DocumentIndex,
    # S3
    OutlineNode,
    TeachingNode,
    GenerationTask,
    # S4
    ModifyCommand,
    GenerationVersion,
    ExportJob,
    # API 请求/响应
    IntentExtractRequest,
    IntentExtractResponse,
    IntentConfirmRequest,
    IntentConfirmResponse,
    ParseProcessRequest,
    ParseProcessResponse,
    ParseStatusResponse,
    ParseVideoRequest,
    SearchRequest,
    SearchResponse,
    EvidenceRequest,
    EvidenceResponse,
    GenerationCreateRequest,
    GenerationCreateResponse,
    GenerationStatusResponse,
    ModifyRequest,
    ModifyResponse,
    VersionHistoryResponse,
    RollbackRequest,
    ExportRequest,
    ExportStatusResponse,
)

__all__ = [
    "settings",
    "LLMClient",
    "resolve_llm_base_url",
    "extract_json",
    # 枚举
    "SessionStatus",
    "TurnType",
    "GenerationStatus",
    "GenerationStage",
    "NodeType",
    "ModifyCommandType",
    "SourceType",
    "ParseStatus",
    "ExportFormat",
    "ExportStatus",
    # S1
    "IntentSummary",
    "DialogueTurn",
    "ConversationSession",
    # S2
    "MaterialAsset",
    "Chunk",
    # KB
    "SearchResult",
    "Citation",
    "EvidencePacket",
    "DocumentIndex",
    # S3
    "OutlineNode",
    "TeachingNode",
    "GenerationTask",
    # S4
    "ModifyCommand",
    "GenerationVersion",
    "ExportJob",
    # API
    "IntentExtractRequest",
    "IntentExtractResponse",
    "IntentConfirmRequest",
    "IntentConfirmResponse",
    "ParseProcessRequest",
    "ParseProcessResponse",
    "ParseStatusResponse",
    "ParseVideoRequest",
    "SearchRequest",
    "SearchResponse",
    "EvidenceRequest",
    "EvidenceResponse",
    "GenerationCreateRequest",
    "GenerationCreateResponse",
    "GenerationStatusResponse",
    "ModifyRequest",
    "ModifyResponse",
    "VersionHistoryResponse",
    "RollbackRequest",
    "ExportRequest",
    "ExportStatusResponse",
]
