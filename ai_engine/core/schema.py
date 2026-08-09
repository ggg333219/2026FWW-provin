"""
跨 Skill 共享数据结构定义 (core/schema.py)

所有 4 个 Skill 模块从这里导入共享数据结构，确保字段名称和类型一致。
团队成员并行开发时引用同一份定义，联调时不会出现字段对不上的问题。

设计原则：
  1. 每个结构用 Pydantic BaseModel 定义，自动获得验证 + FastAPI OpenAPI 文档
  2. 可选字段显式标注 Optional，必填字段不放 Optional
  3. 所有时间字段用 datetime，所有 ID 字段用 str
  4. 枚举用 Python StrEnum/IntEnum

使用方式：
    from ai_engine.core.schema import (
        IntentSummary, SessionStatus,
        Chunk, MaterialAsset,
        EvidencePacket, SearchResult,
        TeachingNode, GenerationTask,
        ModifyCommand, GenerationVersion, ExportJob,
    )

    intent = IntentSummary(topic="排序算法", duration_minutes=45)
    assert intent.is_complete  # 检查必填字段是否齐备
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# 枚举
# =============================================================================

class SessionStatus(str, Enum):
    """S1 会话状态机状态。"""
    COLLECTING = "collecting"
    CLARIFYING = "clarifying"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    LOCKED = "locked"


class TurnType(str, Enum):
    """S1 对话轮次类型。"""
    INITIAL = "initial"
    CLARIFYING_QUESTION = "clarifying_question"
    CLARIFYING_ANSWER = "clarifying_answer"
    CONFIRMATION = "confirmation"
    SYSTEM = "system"


class GenerationStatus(str, Enum):
    """S3 生成任务状态。"""
    PENDING = "pending"
    GENERATING = "generating"
    PREVIEW = "preview"
    MODIFYING = "modifying"
    DONE = "done"
    FAILED = "failed"


class GenerationStage(str, Enum):
    """S3 生成管道内部阶段。"""
    INTENT_LOCKED = "intent_locked"
    EVIDENCE_GATHERING = "evidence_gathering"
    STRUCTURING = "structuring"
    GENERATING = "generating"
    PREVIEW = "preview"
    MODIFYING = "modifying"
    DONE = "done"


class NodeType(str, Enum):
    """S3 课件节点类型。"""
    SLIDE = "slide"
    SECTION = "section"
    QUIZ = "quiz"
    INTERACTIVE = "interactive"
    COVER = "cover"
    DIVIDER = "divider"


class ModifyCommandType(str, Enum):
    """S4 修改命令类型。"""
    UPDATE_NODE = "update_node"
    SWAP_NODES = "swap_nodes"
    ADD_NODE = "add_node"
    DELETE_NODE = "delete_node"
    CHANGE_TEMPLATE = "change_template"
    MERGE_NODES = "merge_nodes"
    SPLIT_NODE = "split_node"


class SourceType(str, Enum):
    """S2/KB 资料来源类型。"""
    PDF = "pdf"
    PPTX = "pptx"
    DOCX = "docx"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"


class ParseStatus(str, Enum):
    """S2 解析状态。"""
    UPLOADED = "uploaded"
    PARSING = "parsing"
    CHUNKED = "chunked"
    INDEXED = "indexed"
    DONE = "done"
    FAILED = "failed"


class ExportFormat(str, Enum):
    """S4 导出格式。"""
    PPTX = "pptx"
    DOCX = "docx"
    BOTH = "both"
    INTERACTIVE = "interactive"
    PDF = "pdf"


class ExportStatus(str, Enum):
    """S4 导出任务状态。"""
    PENDING = "pending"
    EXPORTING = "exporting"
    DONE = "done"
    FAILED = "failed"


# =============================================================================
# S1: 意图理解
# =============================================================================

_FIELD_PRIORITY = ["topic", "duration_minutes", "style", "target_student"]
_REQUIRED_FIELDS = ["topic", "duration_minutes"]


class IntentSummary(BaseModel):
    """
    结构化教学意图摘要。

    S1 从多轮对话中提取此结构，作为输出传递给 S3。
    S3 据此生成课件大纲和内容。
    """
    topic: Optional[str] = None
    """教学主题（如"排序算法""Python 基础"）"""

    duration_minutes: Optional[int] = None
    """期望时长（分钟）"""

    style: Optional[str] = None
    """教学风格（"讲练结合""案例驱动""项目制""理论为主"等）"""

    target_student: Optional[str] = None
    """目标学生（"大一计算机专业""高三学生"等）"""

    knowledge_points: list[str] = Field(default_factory=list)
    """知识点列表"""

    output_format: list[str] = Field(default_factory=list)
    """期望输出格式（"ppt"/"doc"/"both"/"interactive"）"""

    with_interactive: bool = False
    """是否需要互动环节（测验/投票/讨论）"""

    key_difficulties: list[str] = Field(default_factory=list)
    """重点/难点"""

    expected_outcomes: list[str] = Field(default_factory=list)
    """预期学习成果"""

    missing_fields: list[str] = Field(default_factory=list)
    """当前对话中尚未收集到的字段名列表"""

    @property
    def is_complete(self) -> bool:
        """所有必填字段是否已填。"""
        for field in _REQUIRED_FIELDS:
            if getattr(self, field, None) is None:
                return False
        return True

    @property
    def completion_pct(self) -> float:
        """必填字段填充百分比（0.0 ~ 1.0）。"""
        filled = sum(1 for f in _REQUIRED_FIELDS if getattr(self, f, None) is not None)
        return filled / len(_REQUIRED_FIELDS) if _REQUIRED_FIELDS else 1.0

    def next_field_to_collect(self) -> Optional[str]:
        """按优先级返回下一个需收集的字段名。"""
        for f in _FIELD_PRIORITY:
            if getattr(self, f, None) is None and f not in self.missing_fields:
                return f
        for f in _FIELD_PRIORITY:
            if getattr(self, f, None) is None:
                return f
        return None


class DialogueTurn(BaseModel):
    """S1 对话轮次。"""
    turn_id: str = ""
    session_id: str = ""
    role: str = ""  # "teacher" | "assistant" | "system"
    content: str = ""
    turn_type: TurnType = TurnType.INITIAL
    created_at: datetime = Field(default_factory=datetime.now)


class ConversationSession(BaseModel):
    """S1 会话。"""
    session_id: str = ""
    status: SessionStatus = SessionStatus.COLLECTING
    intent: IntentSummary = Field(default_factory=IntentSummary)
    turn_count: int = 0
    max_turns: int = 8  # 最多 8 轮澄清
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    timeout_minutes: int = 30  # 超时 30 分钟自动终止

    @property
    def is_timed_out(self) -> bool:
        if not self.updated_at:
            return False
        elapsed = (datetime.now() - self.updated_at).total_seconds()
        return elapsed > self.timeout_minutes * 60

    @property
    def can_collect(self) -> bool:
        return self.status in (SessionStatus.COLLECTING, SessionStatus.CLARIFYING)

    @property
    def is_locked(self) -> bool:
        return self.status == SessionStatus.LOCKED


# =============================================================================
# S2: 多模态交互
# =============================================================================

class MaterialAsset(BaseModel):
    """S2 参考资料元信息。"""
    asset_id: str = ""
    session_id: str = ""
    file_name: str = ""
    file_url: str = ""
    file_size: int = 0
    source_type: SourceType = SourceType.TEXT
    parse_status: ParseStatus = ParseStatus.UPLOADED
    page_count: Optional[int] = None
    duration_sec: Optional[int] = None  # 视频/音频时长
    mime_type: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """
    标准解析块。

    S2 的输出 → KB 的输入。
    所有格式（PDF/PPTX/DOCX/图片/视频）都归一为 Chunk。
    """
    chunk_id: str = ""
    source_type: SourceType = SourceType.TEXT
    source_ref: str = ""  # 来源标识（如 "doc_xxx/p3"）
    content: str = ""
    page_ref: Optional[int] = None
    seq_index: int = 0  # 在文档中的顺序索引
    metadata: dict[str, Any] = Field(default_factory=dict)
    """额外元数据：如 bounding_box（图片）、timestamp_range（视频）、table_structure 等"""
    embedding: Optional[list[float]] = None  # 向量化后填充


# =============================================================================
# KB: 知识库 RAG
# =============================================================================

class SearchResult(BaseModel):
    """KB 搜索单条结果。"""
    chunk_id: str = ""
    content: str = ""
    score: float = 0.0
    source: dict[str, Any] = Field(default_factory=dict)
    """{"file_name": "...", "page": 3, "url": "minio://..."}"""
    metadata: dict[str, Any] = Field(default_factory=dict)
    """{"node_ref": "...", "type": "text|table|image"}"""


class Citation(BaseModel):
    """证据引用。"""
    chunk_id: str = ""
    text_snippet: str = ""
    source_ref: str = ""


class EvidencePacket(BaseModel):
    """
    证据融合包。

    KB 的输出 → S3 的输入。
    S3 的每个生成调用接收此包作为上下文。
    """
    relevant_chunks: list[Chunk] = Field(default_factory=list)
    synthesized_context: str = ""
    """LLM 合成后的浓缩上下文"""
    citations: list[Citation] = Field(default_factory=list)
    query: str = ""
    """触发此次检索的原始查询"""


class DocumentIndex(BaseModel):
    """KB 知识库文档索引记录。"""
    doc_id: str = ""
    file_name: str = ""
    source_type: SourceType = SourceType.TEXT
    chunk_count: int = 0
    status: ParseStatus = ParseStatus.UPLOADED
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# S3: 课件生成
# =============================================================================

class OutlineNode(BaseModel):
    """S3 大纲节点。"""
    node_id: str = ""
    title: str = ""
    node_type: NodeType = NodeType.SLIDE
    summary: str = ""
    estimated_duration_minutes: float = 5.0
    children: list[str] = Field(default_factory=list)
    """子节点 ID 列表"""
    prerequisites: list[str] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(default_factory=list)


class TeachingNode(BaseModel):
    """S3 生成的完整教学节点。"""
    node_id: str = ""
    title: str = ""
    node_type: NodeType = NodeType.SLIDE
    content: str = ""
    """完整的节点内容（markdown / html）"""
    summary: str = ""
    page_ref: Optional[int] = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    core_points: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    key_difficulties: list[str] = Field(default_factory=list)
    expected_outcomes: list[str] = Field(default_factory=list)
    estimated_duration_minutes: float = 5.0
    interactive_questions: list[str] = Field(default_factory=list)
    citation_refs: list[str] = Field(default_factory=list)
    """引用的 chunk_id 列表"""
    next_node_id: Optional[str] = None
    prev_node_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationTask(BaseModel):
    """S3 生成任务。"""
    task_id: str = ""
    session_id: str = ""
    generation_id: str = ""
    status: GenerationStatus = GenerationStatus.PENDING
    stage: GenerationStage = GenerationStage.INTENT_LOCKED
    progress_pct: float = 0.0
    current_node: str = ""
    intent: IntentSummary = Field(default_factory=IntentSummary)
    evidence: Optional[EvidencePacket] = None
    template_id: str = "default"
    nodes: list[TeachingNode] = Field(default_factory=list)
    node_count: int = 0
    file_urls: dict[str, str] = Field(default_factory=dict)
    """{"ppt": "minio://...", "doc": "minio://..."}"""
    citation_refs: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# S4: 个性化满足 & 版本 & 导出
# =============================================================================

class ModifyCommand(BaseModel):
    """S4 修改命令。"""
    command_type: ModifyCommandType = ModifyCommandType.UPDATE_NODE
    node_id: Optional[str] = None
    target_node_ids: list[str] = Field(default_factory=list)
    """swap/merge 时涉及的多个节点 ID"""
    content: Optional[str] = None
    """update/add 的内容"""
    after_node_id: Optional[str] = None
    """add 时插入位置"""
    template_id: Optional[str] = None
    """change_template 时目标模板"""
    split_point: Optional[str] = None
    """split 的拆分位置描述"""
    regenerate: bool = False
    """是否触发 LLM 重写"""


class GenerationVersion(BaseModel):
    """S4 版本快照。"""
    id: str = ""
    generation_id: str = ""
    version_number: int = 1
    nodes_snapshot: list[TeachingNode] = Field(default_factory=list)
    summary: str = ""
    """版本的变更摘要（如"修改第3页内容"）"""
    parent_version: Optional[int] = None
    locked: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExportJob(BaseModel):
    """S4 导出任务。"""
    job_id: str = ""
    generation_id: str = ""
    version: int = 1
    format: ExportFormat = ExportFormat.PPTX
    status: ExportStatus = ExportStatus.PENDING
    minio_path: Optional[str] = None
    download_url: Optional[str] = None
    file_size: Optional[int] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


# =============================================================================
# API 请求/响应体
# =============================================================================

# ---- S1 ----

class IntentExtractRequest(BaseModel):
    """POST /api/v1/intent/extract 请求"""
    session_id: str = ""
    messages: list[DialogueTurn] = Field(default_factory=list)


class IntentExtractResponse(BaseModel):
    code: int = 200
    data: Optional[dict[str, Any]] = None


class IntentConfirmRequest(BaseModel):
    """POST /api/v1/intent/confirm 请求"""
    session_id: str = ""


class IntentConfirmResponse(BaseModel):
    confirmed: bool = False
    intent_summary: Optional[IntentSummary] = None
    session_status: SessionStatus = SessionStatus.CONFIRMING


# ---- S2 ----

class ParseProcessRequest(BaseModel):
    """POST /api/v1/parse/process 请求

    与 Go 端 AIEngine.ParseProcessRequest 保持一致。
    file_paths 可以是本地路径或 minio:// 协议的远程路径。
    """
    session_id: str = ""
    intent_id: Optional[str] = None
    """关联的教学意图 ID（可选，留空则纯解析不映射）"""
    file_paths: list[str] = Field(default_factory=list)


class ParseVideoRequest(BaseModel):
    """POST /api/v1/parse/video 请求"""
    session_id: str = ""
    file_path: str = ""
    language: str = ""
    """ASR 语言代码，如 "zh"、"en"，空字符串自动检测"""


class ParseProcessResponse(BaseModel):
    task_id: str = ""
    status: str = "pending"
    assets: list[MaterialAsset] = Field(default_factory=list)


class ParseStatusResponse(BaseModel):
    task_id: str = ""
    status: ParseStatus = ParseStatus.PARSING
    chunks: list[Chunk] = Field(default_factory=list)
    error: Optional[str] = None


# ---- KB ----

class SearchRequest(BaseModel):
    query: str = ""
    knowledge_base_ids: list[str] = Field(default_factory=list)
    top_k: int = 5
    min_score: float = 0.6


class SearchResponse(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)
    total_chunks: int = 0


class EvidenceRequest(BaseModel):
    query: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    knowledge_base_ids: list[str] = Field(default_factory=list)


class EvidenceResponse(BaseModel):
    evidence_packet: Optional[EvidencePacket] = None


# ---- S3 ----

class GenerationCreateRequest(BaseModel):
    session_id: str = ""
    course_id: str = ""
    title: str = ""
    markdown: str = ""
    intent: IntentSummary = Field(default_factory=IntentSummary)
    evidence_packet: Optional[EvidencePacket] = None
    template_id: str = "default"


class GenerationCreateResponse(BaseModel):
    task_id: str = ""
    generation_id: str = ""
    status: GenerationStatus = GenerationStatus.PENDING
    generation_type: str = "ppt"


class GenerationStatusResponse(BaseModel):
    task_id: str = ""
    status: GenerationStatus = GenerationStatus.PENDING
    stage: GenerationStage = GenerationStage.INTENT_LOCKED
    progress_pct: float = 0.0
    current_node: str = ""
    nodes: list[TeachingNode] = Field(default_factory=list)
    preview_url: Optional[str] = None
    error: Optional[str] = None
    # 前端兼容字段（由后端填充）
    progress: float = 0.0
    stage_text: str = ""


# ---- S4 ----

class ModifyRequest(BaseModel):
    commands: list[ModifyCommand] = Field(default_factory=list)


class ModifyResponse(BaseModel):
    task_id: str = ""
    new_version: int = 1
    status: str = "regenerating"


class VersionHistoryResponse(BaseModel):
    versions: list[GenerationVersion] = Field(default_factory=list)


class RollbackRequest(BaseModel):
    target_version: int = 1


class ExportRequest(BaseModel):
    format: ExportFormat = ExportFormat.PPTX
    version: int = 1


class ExportStatusResponse(BaseModel):
    job_id: str = ""
    status: ExportStatus = ExportStatus.PENDING
    download_url: Optional[str] = None
    error: Optional[str] = None
