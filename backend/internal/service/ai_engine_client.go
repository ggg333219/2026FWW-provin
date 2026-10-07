package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"strconv"
	"strings"
	"time"
)

const (
	intentExtractRequestTimeout = 120 * time.Second
	outlineRequestTimeout       = 120 * time.Second
)

// AIEngine 定义所有向后端 AI Engine 的调用契约。
// 旧接口继续保持向后兼容，新 Skill 接口按功能域分组。
type AIEngine interface {
	// ---- 旧接口（向后兼容） ----
	ParseDocument(ctx context.Context, file *multipart.FileHeader) (*ParseDocumentResponse, error)
	ReconstructDocument(ctx context.Context, req ReconstructDocumentRequest) (*ReconstructDocumentResponse, error)
	GenerateNodeScript(ctx context.Context, req GenerateNodeScriptRequest) (*GenerateNodeScriptResponse, error)
	GenerateFromMarkdown(ctx context.Context, req GenerateFromMarkdownRequest) (*GenerateFromMarkdownResponse, error)
	GenerateScript(ctx context.Context, req GenerateScriptRequest) (*GenerateScriptResponse, error)
	GenerateAudio(ctx context.Context, req GenerateAudioRequest) (*GenerateAudioResponse, error)
	AskWithContext(ctx context.Context, req AskWithContextRequest) (*AskWithContextResponse, error)
	ParseKnowledge(ctx context.Context, req ParseKnowledgeRequest) (*ParseKnowledgeResponse, error)

	// ---- S1: 意图理解 ----
	IntentExtract(ctx context.Context, req IntentExtractRequest) (*IntentExtractResponse, error)
	IntentConfirm(ctx context.Context, req IntentConfirmRequest) (*IntentConfirmResponse, error)

	// ---- S2: 多模态解析 ----
	ParseProcess(ctx context.Context, req *ParseProcessRequest) (*ParseProcessResponse, error)
	ParseStatus(ctx context.Context, taskID string) (*ParseStatusResponse, error)
	ParseVideo(ctx context.Context, req *ParseVideoRequest) (*ParseProcessResponse, error)

	// ---- KB: 知识库 RAG ----
	RAGSearch(ctx context.Context, req RAGSearchRequest) (*RAGSearchResponse, error)
	RAGEvidence(ctx context.Context, req RAGEvidenceRequest) (*RAGEvidenceResponse, error)
	KnowledgeUpload(ctx context.Context, req *KnowledgeUploadRequest) (*KnowledgeUploadResponse, error)

	// ---- S3: 课件生成 ----
	GenerationCreate(ctx context.Context, req GenerationCreateRequest) (*GenerationCreateResponse, error)
	GenerationStatus(ctx context.Context, taskID string) (*GenerationStatusResponse, error)

	// ---- S3: 大纲构建与 AI 修订（Python 无状态端点 /gen/outline、/gen/outline/revise）----
	GenerateOutline(ctx context.Context, req OutlineGenerateRequest) (*OutlineGenerateResponse, error)
	ReviseOutline(ctx context.Context, req OutlineReviseAIRequest) (*OutlineReviseAIResponse, error)

	// ---- B5: 修改意图理解（Python /api/v1/ai/parse_modify）----
	ParseModify(ctx context.Context, req ParseModifyRequest) (*ModifyIntent, error)

	// ---- P1: S3 大纲 → 内容生成（独立阶段）----
	GenerateContent(ctx context.Context, req GenContentRequest) (*GenContentStatusResponse, error)
	ContentStatus(ctx context.Context, contentID string) (*GenContentStatusResponse, error)

	// ---- S4: 个性化 & 版本 & 导出 ----
	GenerationModify(ctx context.Context, req GenerationModifyRequest) (*GenerationModifyResponse, error)
	VersionHistory(ctx context.Context, genID string) (*VersionHistoryResponse, error)
	VersionLoad(ctx context.Context, genID string, versionNumber int) (*VersionSnapshot, error)
	VersionRollback(ctx context.Context, genID string, req VersionRollbackRequest) (*VersionRollbackResponse, error)
	VersionLock(ctx context.Context, genID string) (*VersionLockResponse, error)
	ExportCreate(ctx context.Context, genID string, req ExportCreateRequest) (*ExportCreateResponse, error)
	ExportStatus(ctx context.Context, jobID string) (*ExportStatusResponse, error)

	// ---- S3 生成终稿：从确认内容 → 版本快照（PPT 步骤）----
	GenerationFinalize(ctx context.Context, req GenerationFinalizeRequest) (*GenerationFinalizeResponse, error)
}

type aiEngineClient struct {
	baseURL string
	client  *http.Client
}

type GenerateScriptRequest struct {
	Page       int             `json:"page"`
	Content    string          `json:"content"`
	CourseName string          `json:"course_name"`
	Mode       string          `json:"mode"`
	Evidence   *EvidencePacket `json:"evidence,omitempty"`
}

type ParsedPage struct {
	Page          int    `json:"page"`
	Content       string `json:"content"`
	ContentLength int    `json:"content_length"`
}

type ParseDocumentResponse struct {
	DocID       string       `json:"doc_id"`
	DocName     string       `json:"doc_name"`
	DocType     string       `json:"doc_type"`
	TotalPages  int          `json:"total_pages"`
	ParsedPages []ParsedPage `json:"parsed_pages"`
}

type ReconstructDocumentRequest struct {
	ParsedDocument map[string]any `json:"parsed_document"`
	Mode           string         `json:"mode"`
}

type ReconstructedChapter struct {
	ChapterID string   `json:"chapter_id"`
	Title     string   `json:"title"`
	NodeIDs   []string `json:"node_ids"`
}

type ReconstructedTeachingNode struct {
	NodeID                      string   `json:"node_id"`
	Title                       string   `json:"title"`
	SourcePages                 []int    `json:"source_pages"`
	Summary                     string   `json:"summary"`
	CorePoints                  []string `json:"core_points"`
	Examples                    []string `json:"examples"`
	CommonConfusions            []string `json:"common_confusions"`
	RecommendedExplanationOrder []string `json:"recommended_explanation_order"`
	EstimatedDuration           int      `json:"estimated_duration"`
	NextNodeID                  string   `json:"next_node_id"`
}

type ReconstructDocumentResponse struct {
	DocID         string                      `json:"doc_id"`
	DocName       string                      `json:"doc_name"`
	DocType       string                      `json:"doc_type"`
	Chapters      []ReconstructedChapter      `json:"chapters"`
	TeachingNodes []ReconstructedTeachingNode `json:"teaching_nodes"`
}

type GenerateNodeScriptRequest struct {
	TeachingNode map[string]any  `json:"teaching_node"`
	CourseName   string          `json:"course_name"`
	Mode         string          `json:"mode"`
	Evidence     *EvidencePacket `json:"evidence,omitempty"`
}

type GenerateNodeScriptResponse struct {
	NodeID               string                 `json:"node_id"`
	Title                string                 `json:"title"`
	Script               string                 `json:"script"`
	MindmapMarkdown      string                 `json:"mindmap_markdown"`
	InteractiveQuestions []string               `json:"interactive_questions"`
	ReteachScript        string                 `json:"reteach_script"`
	Transition           string                 `json:"transition"`
	StructuredMarkdown   string                 `json:"structured_markdown"`
	KnowledgeNodes       []KnowledgeNodeProfile `json:"knowledge_nodes"`
	ScriptSegments       []ScriptSegment        `json:"script_segments"`
}

type GenerateFromMarkdownRequest struct {
	Markdown   string `json:"markdown"`
	CourseName string `json:"course_name"`
	Mode       string `json:"mode"`
}

type PipelineNode struct {
	NodeID        string   `json:"node_id"`
	Title         string   `json:"title"`
	Summary       string   `json:"summary"`
	SourceSpan    string   `json:"source_span"`
	Prerequisites []string `json:"prerequisites"`
}

type PipelineNodeTree struct {
	Nodes []PipelineNode `json:"nodes"`
}

type PipelineScriptSegment struct {
	SegmentID string `json:"segment_id"`
	Text      string `json:"text"`
	NodeID    string `json:"node_id"`
}

type PipelineNodeScript struct {
	NodeID   string                  `json:"node_id"`
	Title    string                  `json:"title"`
	Script   string                  `json:"script"`
	Segments []PipelineScriptSegment `json:"segments"`
}

type GenerateFromMarkdownResponse struct {
	CourseName     string               `json:"course_name"`
	SourceMarkdown string               `json:"source_markdown"`
	KeyPoints      []string             `json:"key_points"`
	NodeTree       PipelineNodeTree     `json:"node_tree"`
	Scripts        []PipelineNodeScript `json:"scripts"`
	UsedFallback   bool                 `json:"used_fallback"`
}

type KnowledgeNodeProfile struct {
	NodeID        string   `json:"node_id"`
	ParentID      string   `json:"parent_id"`
	Level         int      `json:"level"`
	Title         string   `json:"title"`
	Tags          []string `json:"tags"`
	Prerequisites []string `json:"prerequisites"`
	Difficulty    string   `json:"difficulty"`
	CoverageSpan  []string `json:"coverage_span"`
}

type ScriptSegment struct {
	SegmentID      string   `json:"segment_id"`
	Text           string   `json:"text"`
	NodeIDs        []string `json:"node_ids"`
	Confidence     float64  `json:"confidence"`
	ManualOverride bool     `json:"manual_override"`
}

type GenerateScriptResponse struct {
	Page              int    `json:"page"`
	Script            string `json:"script"`
	MindmapMarkdown   string `json:"mindmap_markdown"`
	UseEnhancedSchema bool   `json:"use_enhanced_schema"`
	Scripts           []any  `json:"scripts,omitempty"`
}

type GenerateEnhancedRequest struct {
	Markdown   string `json:"markdown"`
	CourseName string `json:"course_name"`
	Mode       string `json:"mode"`
}

type GenerateEnhancedResponse struct {
	CourseName        string         `json:"course_name"`
	SourceMarkdown    string         `json:"source_markdown"`
	KeyPoints         []string       `json:"key_points"`
	NodeTree          map[string]any `json:"node_tree"`
	Scripts           []any          `json:"scripts"`
	UseEnhancedSchema bool           `json:"use_enhanced_schema"`
	UsedFallback      bool           `json:"used_fallback"`
}

type GenerateAudioNode struct {
	NodeID      string `json:"node_id"`
	Title       string `json:"title"`
	Text        string `json:"text"`
	DurationSec int    `json:"duration_sec"`
	StartSec    int    `json:"start_sec"`
	EndSec      int    `json:"end_sec"`
	AudioURL    string `json:"audio_url,omitempty"`
}

type GenerateAudioRequest struct {
	CourseID   string              `json:"course_id"`
	Page       int                 `json:"page"`
	VoiceType  string              `json:"voice_type"`
	Format     string              `json:"format"`
	Provider   string              `json:"provider"`
	Nodes      []GenerateAudioNode `json:"nodes"`
	PlaybackID string              `json:"playback_id,omitempty"`
}

type GenerateAudioResponse struct {
	AudioID       string              `json:"audio_id"`
	AudioURL      string              `json:"audio_url"`
	Provider      string              `json:"provider"`
	VoiceType     string              `json:"voice_type"`
	Format        string              `json:"format"`
	Status        string              `json:"status"`
	TotalDuration int                 `json:"total_duration_sec"`
	PlaybackMode  string              `json:"playback_mode"`
	GeneratedAt   string              `json:"generated_at"`
	Sections      []GenerateAudioNode `json:"sections"`
}

type ConversationTurn struct {
	Question string `json:"question"`
	Answer   string `json:"answer"`
	Page     int    `json:"page,omitempty"`
	NodeID   string `json:"node_id,omitempty"`
}

type AskWithContextRequest struct {
	Question       string             `json:"question"`
	CurrentPage    int                `json:"current_page"`
	Context        string             `json:"context"`
	Mode           string             `json:"mode"`
	SessionID      string             `json:"session_id,omitempty"`
	HistorySummary string             `json:"history_summary,omitempty"`
	RecentTurns    []ConversationTurn `json:"recent_turns,omitempty"`
}

type AskWithContextResponse struct {
	Question           string `json:"question"`
	SourcePage         int    `json:"source_page"`
	SourceExcerpt      string `json:"source_excerpt"`
	Answer             string `json:"answer"`
	UsedFallback       bool   `json:"used_fallback"`
	FallbackReason     string `json:"fallback_reason"`
	ResumePage         int    `json:"resume_page"`
	ResumeNodeID       string `json:"resume_node_id"`
	ResumeSec          int    `json:"resume_sec"`
	FollowUpSuggestion string `json:"follow_up_suggestion"`
	Intent             struct {
		NeedReteach        bool   `json:"need_reteach"`
		UnderstandingLevel string `json:"understanding_level"`
		Reason             string `json:"reason"`
	} `json:"intent"`
}

type ParseKnowledgeRequest struct {
	Text string `json:"text"`
	Mode string `json:"mode"`
}

type KnowledgeNode struct {
	Name     string          `json:"name"`
	Children []KnowledgeNode `json:"children,omitempty"`
}

type ParseKnowledgeResponse struct {
	Structure []KnowledgeNode `json:"structure"`
}

// =============================================================================
// S1: 意图理解 — 请求/响应类型
// =============================================================================

// SessionStatus 会话状态（映射 Python SessionStatus 枚举）
type SessionStatus string

const (
	SessionStatusCollecting SessionStatus = "collecting"
	SessionStatusClarifying SessionStatus = "clarifying"
	SessionStatusConfirming SessionStatus = "confirming"
	SessionStatusConfirmed  SessionStatus = "confirmed"
	SessionStatusLocked     SessionStatus = "locked"
)

// IntentSummary 结构化教学意图摘要
//
// 注意：本结构目前**只透传、不落库** —— outline 行上只有 intent_id（指向 AI 引擎的
// 意图会话），意图摘要本身没有对应的表。因此「按 outline_id 反查意图」在服务端做
// 不到；要让表达规划器拿到意图，只能由客户端在请求里带上。
type IntentSummary struct {
	Topic            *string  `json:"topic,omitempty"`
	DurationMinutes  *int     `json:"duration_minutes,omitempty"`
	Style            *string  `json:"style,omitempty"`
	TargetStudent    *string  `json:"target_student,omitempty"`
	KnowledgePoints  []string `json:"knowledge_points,omitempty"`
	OutputFormat     []string `json:"output_format,omitempty"`
	WithInteractive  bool     `json:"with_interactive"`
	KeyDifficulties  []string `json:"key_difficulties,omitempty"`
	ExpectedOutcomes []string `json:"expected_outcomes,omitempty"`
	MissingFields    []string `json:"missing_fields,omitempty"`
}

type DialogueTurn struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type IntentExtractRequest struct {
	SessionID string         `json:"session_id"`
	Messages  []DialogueTurn `json:"messages,omitempty"`
}

type IntentExtractResponse struct {
	SessionID      string         `json:"session_id"`
	IntentSummary  *IntentSummary `json:"intent_summary"`
	SessionStatus  SessionStatus  `json:"session_status"`
	Response       string         `json:"response,omitempty"`
	NeedFollowup   bool           `json:"need_followup"`
	FollowupQs     []string       `json:"followup_questions,omitempty"`
	HumanSummary   string         `json:"human_summary,omitempty"`
	CompletionPct  int            `json:"completion_pct"`
	TurnCount      int            `json:"turn_count"`
	MaxTurns       int            `json:"max_turns"`
	CanConfirm     bool           `json:"can_confirm"`
	Engine         string         `json:"engine,omitempty"`
	UsedFallback   bool           `json:"used_fallback"`
	FallbackReason string         `json:"fallback_reason,omitempty"`
}

type IntentConfirmRequest struct {
	SessionID string `json:"session_id"`
}

type IntentConfirmResponse struct {
	SessionID     string         `json:"session_id"`
	IntentID      string         `json:"intent_id"`
	Confirmed     bool           `json:"confirmed"`
	IntentSummary *IntentSummary `json:"intent_summary"`
	SessionStatus SessionStatus  `json:"session_status"`
	CompletionPct int            `json:"completion_pct"`
	NextStep      string         `json:"next_step"`
}

// =============================================================================
// S2: 多模态解析 — 请求/响应类型
// =============================================================================

type ParseProcessRequest struct {
	SessionID string   `json:"session_id"`
	FilePaths []string `json:"file_paths,omitempty"`
}

type MaterialAsset struct {
	AssetID     string `json:"asset_id"`
	FileName    string `json:"file_name"`
	SourceType  string `json:"source_type"`
	ParseStatus string `json:"parse_status"`
	FileSize    int    `json:"file_size"`
}

type ParseProcessResponse struct {
	TaskID string          `json:"task_id"`
	Status string          `json:"status"`
	Assets []MaterialAsset `json:"assets,omitempty"`
}

type ParseStatusResponse struct {
	TaskID string      `json:"task_id"`
	Status string      `json:"status"`
	Chunks []ChunkItem `json:"chunks,omitempty"`
	Error  string      `json:"error,omitempty"`
}

type ChunkItem struct {
	ChunkID    string `json:"chunk_id"`
	Content    string `json:"content"`
	SourceType string `json:"source_type"`
	PageRef    int    `json:"page_ref,omitempty"`
	SeqIndex   int    `json:"seq_index"`
}

type ParseVideoRequest struct {
	SessionID string `json:"session_id"`
	FilePath  string `json:"file_path"`
	Language  string `json:"language,omitempty"` // ASR 语言
}

// =============================================================================
// KB: 知识库 RAG — 请求/响应类型
// =============================================================================

type RAGSearchRequest struct {
	Query            string   `json:"query"`
	KnowledgeBaseIDs []string `json:"knowledge_base_ids,omitempty"`
	TopK             int      `json:"top_k,omitempty"`
	Offset           int      `json:"offset,omitempty"`
	MinScore         float64  `json:"min_score,omitempty"`
}

type RAGSearchResponse struct {
	Results      []SearchResultItem `json:"results"`
	TotalChunks  int                `json:"total_chunks"`
	TotalResults int                `json:"total_results"`
}

type SearchResultItem struct {
	ChunkID  string         `json:"chunk_id"`
	Content  string         `json:"content"`
	Score    float64        `json:"score"`
	Source   map[string]any `json:"source,omitempty"`
	Metadata map[string]any `json:"metadata,omitempty"`
}

type RAGEvidenceRequest struct {
	Query            string         `json:"query"`
	Context          map[string]any `json:"context,omitempty"`
	KnowledgeBaseIDs []string       `json:"knowledge_base_ids,omitempty"`
	SelectedChunkIDs []string       `json:"selected_chunk_ids,omitempty"`
}

type EvidencePacket struct {
	RelevantChunks     []ChunkItem    `json:"relevant_chunks"`
	SynthesizedContext string         `json:"synthesized_context"`
	Citations          []CitationItem `json:"citations"`
}

type CitationItem struct {
	ChunkID     string `json:"chunk_id"`
	TextSnippet string `json:"text_snippet"`
	SourceRef   string `json:"source_ref"`
}

type RAGEvidenceResponse struct {
	EvidencePacket *EvidencePacket `json:"evidence_packet"`
}

type KnowledgeUploadRequest struct {
	SessionID       string   `json:"session_id"`
	KnowledgeBaseID string   `json:"knowledge_base_id,omitempty"`
	Files           []string `json:"files,omitempty"`
	Texts           []string `json:"texts,omitempty"`
}

type KnowledgeUploadResponse struct {
	TaskID     string `json:"task_id"`
	Status     string `json:"status"`
	ChunkCount int    `json:"chunk_count"`
	DocumentID string `json:"document_id,omitempty"`
}

// =============================================================================
// S3: 课件生成 — 请求/响应类型
// =============================================================================

// 任务状态 / 阶段 / 导出状态枚举锚点 —— 与 ai_engine/core/schema.py 一一对应。
// 4 个 Skill 各自实现时禁止再发明新字符串，统一引用此处常量（P0 状态统一）。
const (
	GenerationStatusPending    = "pending"
	GenerationStatusGenerating = "generating"
	GenerationStatusPreview    = "preview"
	GenerationStatusModifying  = "modifying"
	GenerationStatusDone       = "done"
	GenerationStatusFailed     = "failed"

	GenerationStageIntentLocked   = "intent_locked"
	GenerationStageEvidenceGather = "evidence_gathering"
	GenerationStageStructuring    = "structuring"
	GenerationStageGenerating     = "generating"
	GenerationStagePreview        = "preview"
	GenerationStageModifying      = "modifying"
	GenerationStageDone           = "done"

	ExportStatusPending   = "pending"
	ExportStatusExporting = "exporting"
	ExportStatusDone      = "done"
	ExportStatusFailed    = "failed"
)

// =============================================================================
// S3: 大纲（Outline）领域 —— Go 网关侧 DTO。
// 字段契约来源：
//   1) 《文档/S3数据与接口规范.md》v1.0 §2.1 OutlineNode / §2.3 Outline；
//   2) ai_engine/main.py:657 /gen/outline（GenOutlineRequest）与 :671 /gen/outline/revise；
//   3) 前端 frontend/teacher/src/services/v1/outlineApi.js + stores/outlineStore.js。
// Python AI Engine 侧无大纲状态持久化（main.py:673 docstring："版本和确认态仍由 Go 后端管理"），
// 大纲草稿/确认/版本链的持久化是 Go OutlineService 的职责（见 outline_service.go）。
// =============================================================================

// OutlineInteractivePlan —— 大纲节点的互动规划（规范 §2.2）。仅声明规划，不承载题目。
type OutlineInteractivePlan struct {
	Enabled       bool   `json:"enabled"`
	Kind          string `json:"kind"` // quiz | flashcard | poll | game
	DurationMin   int    `json:"duration_minutes"`
	QuestionCount int    `json:"question_count,omitempty"`
	AutoGrading   bool   `json:"auto_grading,omitempty"`
	Delivery      string `json:"delivery"` // html5_link | ppt_native | standalone_html
}

// OutlineNode —— 大纲节点（规范 §2.1）。只描述"准备讲什么"，不含完整讲稿正文。
// 禁止字段：script / segments / interactive_items（规范 §2.1 明确禁止）。
type OutlineNode struct {
	NodeID               string                  `json:"node_id"`
	Order                int                     `json:"order"` // 从 1 开始连续编号
	Title                string                  `json:"title"`
	Summary              string                  `json:"summary"`
	NodeType             string                  `json:"node_type"` // content | section | quiz | interactive | summary
	KeyPoints            []string                `json:"key_points"`
	EstimatedDurationMin float64                 `json:"estimated_duration_minutes"` // 单位统一为分钟
	SourceChunkIDs       []string                `json:"source_chunk_ids,omitempty"`
	InteractivePlan      *OutlineInteractivePlan `json:"interactive_plan,omitempty"`
}

// OutlineGenerateRequest —— POST /gen/outline 请求（Python GenOutlineRequest 镜像）。
type OutlineGenerateRequest struct {
	SessionID                string          `json:"session_id,omitempty"`
	IntentID                 string          `json:"intent_id,omitempty"`
	Intent                   *IntentSummary  `json:"intent,omitempty"`
	EvidencePacket           *EvidencePacket `json:"evidence_packet,omitempty"`
	GenerationInstructionSet map[string]any  `json:"generation_instruction_set,omitempty"`
	Markdown                 string          `json:"markdown,omitempty"`
	CourseName               string          `json:"course_name,omitempty"`
}

// OutlineGenerateResponse —— POST /gen/outline 响应（Python 返回裸 {"nodes": [...], "used_fallback": ...}）。
type OutlineGenerateResponse struct {
	Nodes          []OutlineNode `json:"nodes"`
	UsedFallback   bool          `json:"used_fallback,omitempty"`
	FallbackReason string        `json:"fallback_reason,omitempty"`
}

// OutlineReviseAIRequest —— POST /gen/outline/revise 请求（Python GenOutlineReviseRequest 镜像）。
type OutlineReviseAIRequest struct {
	Nodes   []OutlineNode `json:"nodes"`
	Message string        `json:"message"`
}

// OutlineReviseAIResponse —— POST /gen/outline/revise 响应（Python 返回 {"nodes", "change_summary"}）。
type OutlineReviseAIResponse struct {
	Nodes         []OutlineNode `json:"nodes"`
	ChangeSummary []string      `json:"change_summary,omitempty"`
}

// TeachingNodeItem —— 引擎 TeachingNode 的 Go 镜像（字段=ai_engine/core/schema.py）。
// 字段只增不删：node 由 S3 生成 → S4 版本快照 / 导出 / 前端渲染全链路共用本结构。
type TeachingNodeItem struct {
	NodeID               string         `json:"node_id"`
	Title                string         `json:"title"`
	NodeType             string         `json:"node_type,omitempty"` // 引擎枚举渲染类型（slide/section/quiz/cover/...）
	Content              string         `json:"content"`             // 完整节点内容（markdown / html）
	Summary              string         `json:"summary"`
	PageRef              int            `json:"page_ref,omitempty"`
	SourceChunkIDs       []string       `json:"source_chunk_ids"` // 引用证据 chunk 列表
	CorePoints           []string       `json:"core_points"`
	KeyPoints            []string       `json:"key_points"` // 与 core_points 等效（兼容主流 AI-PPT 规范）
	Examples             []string       `json:"examples"`
	KeyDifficulties      []string       `json:"key_difficulties"`
	ExpectedOutcomes     []string       `json:"expected_outcomes"`
	DurationMin          float64        `json:"estimated_duration_minutes"` // 单位统一为分钟
	InteractiveQuestions []string       `json:"interactive_questions"`      // 与 questions 等效
	CitationRefs         []string       `json:"citation_refs"`
	NextNodeID           string         `json:"next_node_id,omitempty"`
	PrevNodeID           string         `json:"prev_node_id,omitempty"`
	Metadata             map[string]any `json:"metadata"`
	// 透传字段：版本快照 / 预览返回节点带有的讲授分段与互动问答等元数据。
	// Questions 引擎侧已归一为 list[str]（normalize_text_list 产出，见 schema.py 注释）；
	// Go 侧用 interface 透传仅为兼容历史 dict 缓存，收到的一律是字符串列表。
	// 注意：content/summary/core_points 等为 canonical 非 Optional 字段，禁加 omitempty——
	//   引擎 Pydantic 空值时键仍在，Go 加 omitempty 会把空键整体丢弃，导致网关响应缺 canonical 字段。
	Segments  []map[string]interface{} `json:"segments"`
	Questions []interface{}            `json:"questions"`
	Script    string                   `json:"script"`
	// type 为引擎侧字符串渲染类型（与 node_type 等效），透传给前端渲染层。
	Type string `json:"type,omitempty"`
	// 排版元数字段（对齐主流 AI-PPT 规范）：layout_hint / font_size_hint / text_alignment / slide_background。
	// PPT 图文并茂导出（A12 4a）与前端渲染层据此布局，须随 node 快照透传。
	LayoutHint      string `json:"layout_hint,omitempty"`
	FontSizeHint    string `json:"font_size_hint,omitempty"`
	TextAlignment   string `json:"text_alignment,omitempty"`
	SlideBackground string `json:"slide_background,omitempty"`
	// 教学内容表达字段（教学表达规划器链路）。Go 的 encoding/json 反序列化到本结构时
	// 会忽略未声明字段，因此引擎侧每新增一个节点字段，这里不同步就等于在网关这一跳丢弃。
	// PointDetails 不带 omitempty：与 segments/questions 同为引擎恒定输出的列表字段。
	// 其余三个是真正可选的（只有拿到规划的页才有），omitempty 与引擎的「缺失即降级」一致。
	PointDetails  []map[string]any `json:"point_details"`
	Figure        map[string]any   `json:"figure,omitempty"`
	KeyConclusion string           `json:"key_conclusion,omitempty"`
	TeachingPlan  map[string]any   `json:"teaching_plan,omitempty"`
}

type GenerationCreateRequest struct {
	SessionID                string          `json:"session_id"`
	CourseID                 string          `json:"course_id,omitempty"`
	Title                    string          `json:"title,omitempty"`
	Markdown                 string          `json:"markdown,omitempty"`
	Intent                   *IntentSummary  `json:"intent,omitempty"`
	EvidencePacket           *EvidencePacket `json:"evidence_packet,omitempty"`
	GenerationInstructionSet map[string]any  `json:"generation_instruction_set,omitempty"`
	TemplateID               string          `json:"template_id,omitempty"`
	OutlineID                string          `json:"outline_id,omitempty"`
	OutlineVersion           int             `json:"outline_version,omitempty"`
	OutlineConfirmed         bool            `json:"outline_confirmed,omitempty"`
	OutlineNodes             []OutlineNode   `json:"outline_nodes,omitempty"`
	GenerateMode             string          `json:"generate_mode,omitempty"`
	GenerationScope          string          `json:"generation_scope,omitempty"`
	ProjectID                string          `json:"project_id,omitempty"`
}

type GenerationCreateResponse struct {
	TaskID         string `json:"task_id"`
	GenerationID   string `json:"generation_id"`
	Status         string `json:"status"`
	GenerationType string `json:"generation_type,omitempty"`
	OutlineID      string `json:"outline_id,omitempty"`
	OutlineVersion int    `json:"outline_version,omitempty"`
}

// GenerationStatusResponse —— S3 任务状态响应。
// 状态口径（P0 统一）：Status 取值见上方 GenerationStatus* 常量；Stage 见 GenerationStage* 常量；
// 进度 canonical 为 ProgressPct（0~100 百分制，前端 generationStore 优先读它）；
// Progress 为引擎历史遗留的 0~1 小数副本，仅作前端兼容保留，禁止新逻辑读写。
type GenerationStatusResponse struct {
	TaskID                   string             `json:"task_id"`
	GenerationID             string             `json:"generation_id,omitempty"`
	OutlineID                string             `json:"outline_id,omitempty"`
	OutlineVersion           int                `json:"outline_version,omitempty"`
	Status                   string             `json:"status"`
	Stage                    string             `json:"stage,omitempty"`
	ProgressPct              float64            `json:"progress_pct"`
	CurrentNode              string             `json:"current_node,omitempty"`
	Nodes                    []TeachingNodeItem `json:"nodes,omitempty"`
	GenerationInstructionSet map[string]any     `json:"generation_instruction_set,omitempty"`
	PreviewURL               string             `json:"preview_url,omitempty"`
	Error                    string             `json:"error,omitempty"` // 失败原因纯文本（结构化 error_code/message 属 P1，暂不引入）
	// 引擎侧前端兼容字段（progress 为 0~1 小数、stage_text 为阶段文案），透传给前端。
	Progress  float64 `json:"progress,omitempty"`
	StageText string  `json:"stage_text,omitempty"`
}

type GenerationPreviewRequest struct {
	// omitempty：仅传 gen_id 做版本快照预览时 Nodes 为 nil，直接省略而非发 "nodes":null，
	// 避免引擎 PreviewRequest(nodes: list[dict]=[]) 收到 null 触发 422。
	Nodes      []TeachingNodeItem `json:"nodes,omitempty"`
	CourseName string             `json:"course_name,omitempty"`
	// 版本快照预览：只传 gen_id（可带 version）时由 AI 引擎按版本恢复节点渲染，
	// 供前端预览持久化（restorePreview）跳过节点树直接拉取历史版本预览。
	GenID   string `json:"gen_id,omitempty"`
	Version *int   `json:"version,omitempty"`
}

type GenerationPreviewResponse struct {
	HTML          string             `json:"html"`
	NodeCount     int                `json:"node_count"`
	GenerationID  string             `json:"generation_id,omitempty"`
	VersionNumber int                `json:"version_number,omitempty"`
	Nodes         []TeachingNodeItem `json:"nodes,omitempty"`
}

// =============================================================================
// S4: 个性化 & 版本 & 导出 — 请求/响应类型
// =============================================================================

type ModifyCommandItem struct {
	// 引擎侧 CommandParser 读取 cmd["type"]（其余键作为 params），前端也发送 type；
	// json tag 必须为 "type" 才能让命令两端对齐（此前 command_type 导致命令类型丢失）。
	CommandType   string   `json:"type"`
	NodeID        string   `json:"node_id,omitempty"`
	TargetNodeIDs []string `json:"target_node_ids,omitempty"`
	Content       string   `json:"content,omitempty"`
	AfterNodeID   string   `json:"after_node_id,omitempty"`
	TemplateID    string   `json:"template_id,omitempty"`
	SplitPoint    string   `json:"split_point,omitempty"`
	Regenerate    bool     `json:"regenerate"`
}

type GenerationModifyRequest struct {
	GenerationID string              `json:"generation_id"`
	Commands     []ModifyCommandItem `json:"commands"`
	Nodes        []interface{}       `json:"nodes,omitempty"`
	CourseName   string              `json:"course_name,omitempty"`
	Regenerate   bool                `json:"regenerate"`
	// 契约 v1.0 模块1 接口3：页面级局部修改的证据约束（字段只增不删，向后兼容）。
	// PageID 对应大纲节点 ID（node_id == page_id）；EvidenceRefs 为空时保持现有全库行为。
	PageID          string   `json:"page_id,omitempty"`
	EvidenceRefs    []string `json:"evidence_refs,omitempty"`
	UserInstruction string   `json:"user_instruction,omitempty"`
}

type GenerationModifyResponse struct {
	Status          string        `json:"status"`
	Nodes           []interface{} `json:"nodes,omitempty"`
	VersionNumber   int           `json:"version_number,omitempty"`
	CommandsApplied []string      `json:"commands_applied,omitempty"`
	Errors          []string      `json:"errors,omitempty"`
	// 契约 v1.0 模块1：本次修改实际使用的证据 chunk（"用了哪些证据"）。
	CitationRefs []string `json:"citation_refs,omitempty"`
	EvidenceUsed []string `json:"evidence_used,omitempty"`
}

type VersionSnapshot struct {
	ID            string             `json:"id"`
	GenerationID  string             `json:"generation_id"`
	VersionNumber int                `json:"version_number"`
	NodesSnapshot []TeachingNodeItem `json:"nodes_snapshot,omitempty"`
	PageBindings  []map[string]any   `json:"page_bindings,omitempty"`
	Presentation  map[string]any     `json:"presentation,omitempty"`
	Metadata      map[string]any     `json:"metadata,omitempty"`
	Summary       string             `json:"summary,omitempty"`
	Locked        bool               `json:"locked"`
	CreatedAt     string             `json:"created_at"`
}

type VersionHistoryResponse struct {
	Versions []VersionSnapshot `json:"versions"`
}

type VersionRollbackRequest struct {
	TargetVersion int `json:"target_version"`
}

type VersionRollbackResponse struct {
	CurrentVersion int                `json:"current_version"`
	Status         string             `json:"status"`
	Nodes          []TeachingNodeItem `json:"nodes,omitempty"`
	PageBindings   []map[string]any   `json:"page_bindings,omitempty"`
	Presentation   map[string]any     `json:"presentation,omitempty"`
}

type VersionLockResponse struct {
	Version    int               `json:"version"`
	Locked     bool              `json:"locked"`
	ExportURLs map[string]string `json:"export_urls,omitempty"`
}

type ExportCreateRequest struct {
	Format                   string             `json:"format"`
	Version                  int                `json:"version"`
	VersionID                string             `json:"version_id,omitempty"`
	Formats                  []string           `json:"formats,omitempty"`
	CoursewareTitle          string             `json:"courseware_title,omitempty"`
	Nodes                    []TeachingNodeItem `json:"nodes,omitempty"`
	GenerationInstructionSet map[string]any     `json:"generation_instruction_set,omitempty"`
}

type ExportCreateResponse struct {
	JobID           string   `json:"job_id"`
	Filename        string   `json:"filename,omitempty"`
	Status          string   `json:"status"`
	CoursewareTitle string   `json:"courseware_title,omitempty"`
	Version         int      `json:"version,omitempty"`
	VersionNo       int      `json:"version_no,omitempty"`
	Formats         []string `json:"formats,omitempty"`
}

type ExportStatusResponse struct {
	JobID        string `json:"job_id"`
	GenerationID string `json:"generation_id,omitempty"`
	Filename     string `json:"filename,omitempty"`
	Status       string `json:"status"`
	DownloadURL  string `json:"download_url,omitempty"`
	Error        string `json:"error,omitempty"`
	// 引擎侧导出产物上传状态等扩展字段（字段只增不删），透传给前端。
	UploadStatus    string               `json:"upload_status,omitempty"`
	MinioPath       string               `json:"minio_path,omitempty"`
	FileSize        int64                `json:"file_size,omitempty"`
	CoursewareTitle string               `json:"courseware_title,omitempty"`
	Version         int                  `json:"version,omitempty"`
	VersionNo       int                  `json:"version_no,omitempty"`
	Files           map[string]string    `json:"files,omitempty"`
	QualityReport   *ExportQualityReport `json:"quality_report,omitempty"`
}

type ExportQualityFinding struct {
	Code        string `json:"code"`
	Severity    string `json:"severity"`
	Message     string `json:"message"`
	SlideNumber *int   `json:"slide_number,omitempty"`
}

type ExportQualityReport struct {
	Status     string                 `json:"status"`
	SlideCount int                    `json:"slide_count"`
	Findings   []ExportQualityFinding `json:"findings"`
}

// =============================================================================
// S3 生成终稿：从确认内容 → 版本快照（PPT 步骤）
// =============================================================================

type GenerationFinalizeRequest struct {
	GenerationID             string             `json:"generation_id,omitempty"`
	Nodes                    []TeachingNodeItem `json:"nodes"`
	CourseName               string             `json:"course_name,omitempty"`
	Summary                  string             `json:"summary,omitempty"`
	OutlineID                string             `json:"outline_id,omitempty"`
	OutlineVersion           int                `json:"outline_version,omitempty"`
	PageBindings             []map[string]any   `json:"page_bindings,omitempty"`
	Presentation             map[string]any     `json:"presentation,omitempty"`
	GenerationInstructionSet map[string]any     `json:"generation_instruction_set,omitempty"`
}

type GenerationFinalizeResponse struct {
	GenerationID  string `json:"generation_id"`
	VersionNumber int    `json:"version_number"`
	Status        string `json:"status"`
}

func (c *aiEngineClient) GenerationFinalize(ctx context.Context, req GenerationFinalizeRequest) (*GenerationFinalizeResponse, error) {
	var result GenerationFinalizeResponse
	if err := c.postJSON(ctx, "/api/v1/gen/finalize", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// =============================================================================
// P1: S3 大纲 → 内容生成（独立阶段）
// =============================================================================

type GenContentRequest struct {
	Nodes           []TeachingNodeItem `json:"nodes"`
	ContextMarkdown string             `json:"context_markdown"`
	CourseName      string             `json:"course_name"`
	Mode            string             `json:"mode"`
	Enhanced        bool               `json:"enhanced"`
	OutlineID       string             `json:"outline_id"`
	OutlineVersion  int                `json:"outline_version"`
	// B6: 局部重生成（mode=partial 时生效）
	TargetNodeIDs     []string `json:"target_node_ids,omitempty"`
	ModifyAction      string   `json:"modify_action,omitempty"`
	ModifyConstraints []string `json:"modify_constraints,omitempty"`
	// 契约 v1.0 模块1：目标页绑定的证据 chunk_id，由 Python 侧解析成原文注入提示词
	EvidenceRefs []string `json:"evidence_refs,omitempty"`
	// 教学意图摘要。Python 侧的表达规划器靠它决定「这一页该怎么教」；不传是合法
	// 输入（规划器退化为只从节点自身推断），因此用 omitempty + 指针。
	//
	// 注意：IntentSummary 目前在 Go 侧**没有落库**（只在 intent 抽取 → 大纲 → 节点
	// 之间透传），所以这里补不了「按 outline_id 反查」—— 客户端带着 intent 发
	// /gen/content 时才能填上。详见 IntentSummary 的注释。
	Intent *IntentSummary `json:"intent,omitempty"`
}

type GenContentStatusResponse struct {
	ContentID      string             `json:"content_id"`
	Status         string             `json:"status"`
	ProgressPct    float64            `json:"progress_pct"`
	CurrentNodeID  string             `json:"current_node_id"`
	TotalNodes     int                `json:"total_nodes"`
	CompletedNodes int                `json:"completed_nodes"`
	Nodes          []TeachingNodeItem `json:"nodes,omitempty"`
	Error          string             `json:"error,omitempty"`
}

type ModifyIntentRequest struct {
	ProjectID       string             `json:"project_id"`
	Instruction     string             `json:"instruction"`
	Nodes           []TeachingNodeItem `json:"nodes"`
	ModifySessionID string             `json:"modify_session_id,omitempty"`
}

type ModifyIntentResponse struct {
	ProjectID           string   `json:"project_id,omitempty"`
	TargetType          string   `json:"target_type"`
	TargetIDs           []string `json:"target_ids"`
	Action              string   `json:"action"`
	Actions             []string `json:"actions,omitempty"`
	Constraints         []string `json:"constraints"`
	Confidence          float64  `json:"confidence"`
	ClarificationNeeded bool     `json:"clarification_needed"`
	Clarification       string   `json:"clarification,omitempty"`
}

func (c *aiEngineClient) GenerateContent(ctx context.Context, req GenContentRequest) (*GenContentStatusResponse, error) {
	var result GenContentStatusResponse
	if err := c.postJSON(ctx, "/gen/content", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) ContentStatus(ctx context.Context, contentID string) (*GenContentStatusResponse, error) {
	var result GenContentStatusResponse
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		c.baseURL+"/gen/content/status/"+contentID, nil)
	if err != nil {
		return nil, fmt.Errorf("构造内容状态请求失败: %w", err)
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("查询内容生成状态失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
		return nil, fmt.Errorf("查询内容状态返回异常: %d %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("解析内容状态响应失败: %w", err)
	}
	return &result, nil
}

// =============================================================================
// Client 构造函数
// =============================================================================

func NewAIEngineClient(baseURL string, timeout time.Duration) AIEngine {
	if strings.TrimSpace(baseURL) == "" {
		baseURL = "http://127.0.0.1:8000"
	}
	if timeout <= 0 {
		timeout = 120 * time.Second
	}

	return &aiEngineClient{
		baseURL: strings.TrimRight(baseURL, "/"),
		client:  &http.Client{Timeout: timeout},
	}
}

func (c *aiEngineClient) ParseDocument(ctx context.Context, file *multipart.FileHeader) (*ParseDocumentResponse, error) {
	if file == nil {
		return nil, fmt.Errorf("文件不能为空")
	}

	src, err := file.Open()
	if err != nil {
		return nil, fmt.Errorf("打开上传文件失败: %w", err)
	}
	defer src.Close()

	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("file", file.Filename)
	if err != nil {
		return nil, fmt.Errorf("构造 multipart 请求失败: %w", err)
	}
	if _, err := io.Copy(part, src); err != nil {
		return nil, fmt.Errorf("写入 multipart 文件失败: %w", err)
	}
	if err := writer.Close(); err != nil {
		return nil, fmt.Errorf("关闭 multipart writer 失败: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/parse-document", &body)
	if err != nil {
		return nil, fmt.Errorf("构造解析请求失败: %w", err)
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("调用AI解析接口失败: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("AI解析接口返回异常状态: %d", resp.StatusCode)
	}

	var result ParseDocumentResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("解析文档响应失败: %w", err)
	}
	return &result, nil
}

func (c *aiEngineClient) ReconstructDocument(ctx context.Context, req ReconstructDocumentRequest) (*ReconstructDocumentResponse, error) {
	var result ReconstructDocumentResponse
	if err := c.postJSON(ctx, "/reconstruct-document", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) GenerateNodeScript(ctx context.Context, req GenerateNodeScriptRequest) (*GenerateNodeScriptResponse, error) {
	var result GenerateNodeScriptResponse
	if err := c.postJSON(ctx, "/generate-node-script", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) GenerateFromMarkdown(ctx context.Context, req GenerateFromMarkdownRequest) (*GenerateFromMarkdownResponse, error) {
	var result GenerateFromMarkdownResponse
	if err := c.postJSON(ctx, "/generate-from-markdown", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) GenerateScript(ctx context.Context, req GenerateScriptRequest) (*GenerateScriptResponse, error) {
	var result GenerateScriptResponse
	if err := c.postJSON(ctx, "/generate-script", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) GenerateEnhanced(ctx context.Context, req GenerateEnhancedRequest) (*GenerateEnhancedResponse, error) {
	var result GenerateEnhancedResponse
	if err := c.postJSON(ctx, "/generate-enhanced", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) GenerateAudio(ctx context.Context, req GenerateAudioRequest) (*GenerateAudioResponse, error) {
	var result GenerateAudioResponse
	if err := c.postJSON(ctx, "/generate-audio", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) AskWithContext(ctx context.Context, req AskWithContextRequest) (*AskWithContextResponse, error) {
	var result AskWithContextResponse
	if err := c.postJSON(ctx, "/ask-with-context", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) ParseKnowledge(ctx context.Context, req ParseKnowledgeRequest) (*ParseKnowledgeResponse, error) {
	var result ParseKnowledgeResponse
	if err := c.postJSON(ctx, "/parse-knowledge", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// ---- S1: 意图理解 ----

func (c *aiEngineClient) IntentExtract(ctx context.Context, req IntentExtractRequest) (*IntentExtractResponse, error) {
	var result IntentExtractResponse
	if err := c.postJSONWithTimeout(ctx, "/api/v1/intent/extract", req, &result, intentExtractRequestTimeout); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) IntentConfirm(ctx context.Context, req IntentConfirmRequest) (*IntentConfirmResponse, error) {
	var result IntentConfirmResponse
	if err := c.postJSON(ctx, "/api/v1/intent/confirm", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// ---- S2: 多模态解析 ----

func (c *aiEngineClient) ParseProcess(ctx context.Context, req *ParseProcessRequest) (*ParseProcessResponse, error) {
	var result ParseProcessResponse
	if err := c.postJSON(ctx, "/api/v1/parse/process", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) ParseStatus(ctx context.Context, taskID string) (*ParseStatusResponse, error) {
	var result ParseStatusResponse
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/v1/parse/status/"+taskID, nil)
	if err != nil {
		return nil, fmt.Errorf("构造解析状态请求失败: %w", err)
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("查询解析状态失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("查询解析状态返回异常: %d", resp.StatusCode)
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("解析状态响应失败: %w", err)
	}
	return &result, nil
}

func (c *aiEngineClient) ParseVideo(ctx context.Context, req *ParseVideoRequest) (*ParseProcessResponse, error) {
	var result ParseProcessResponse
	if err := c.postJSON(ctx, "/api/v1/parse/video", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// ---- KB: 知识库 RAG ----

func (c *aiEngineClient) RAGSearch(ctx context.Context, req RAGSearchRequest) (*RAGSearchResponse, error) {
	var result RAGSearchResponse
	if err := c.postJSON(ctx, "/api/v1/rag/search", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) RAGEvidence(ctx context.Context, req RAGEvidenceRequest) (*RAGEvidenceResponse, error) {
	var result RAGEvidenceResponse
	if err := c.postJSON(ctx, "/api/v1/rag/evidence", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) KnowledgeUpload(ctx context.Context, req *KnowledgeUploadRequest) (*KnowledgeUploadResponse, error) {
	var result KnowledgeUploadResponse
	if err := c.postJSON(ctx, "/api/v1/knowledge/upload", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// ---- S3: 课件生成 ----

func (c *aiEngineClient) GenerationCreate(ctx context.Context, req GenerationCreateRequest) (*GenerationCreateResponse, error) {
	var result GenerationCreateResponse
	if err := c.postJSON(ctx, "/api/v1/gen/create", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) GenerateOutline(ctx context.Context, req OutlineGenerateRequest) (*OutlineGenerateResponse, error) {
	var result OutlineGenerateResponse
	if err := c.postJSONWithTimeout(ctx, "/gen/outline", req, &result, outlineRequestTimeout); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) ReviseOutline(ctx context.Context, req OutlineReviseAIRequest) (*OutlineReviseAIResponse, error) {
	var result OutlineReviseAIResponse
	if err := c.postJSONWithTimeout(ctx, "/gen/outline/revise", req, &result, outlineRequestTimeout); err != nil {
		return nil, err
	}
	return &result, nil
}

// ParseModify [B5] 调 Python /api/v1/ai/parse_modify 解析修改意图。
func (c *aiEngineClient) ParseModify(ctx context.Context, req ParseModifyRequest) (*ModifyIntent, error) {
	var result struct {
		ModifyIntent
	}
	// Python 返回扁平 intent 对象，直接反序列化
	if err := c.postJSON(ctx, "/api/v1/ai/parse_modify", req, &result); err != nil {
		return nil, err
	}
	return &result.ModifyIntent, nil
}

func (c *aiEngineClient) GenerationStatus(ctx context.Context, taskID string) (*GenerationStatusResponse, error) {
	var result GenerationStatusResponse
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/v1/gen/status/"+taskID, nil)
	if err != nil {
		return nil, fmt.Errorf("构造生成状态请求失败: %w", err)
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("查询生成状态失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("查询生成状态返回异常: %d", resp.StatusCode)
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("解析生成状态响应失败: %w", err)
	}
	// P3: 防御性验证 nodes 数组，防止畸形 LLM 输出进入版本化/导出流程
	if result.Nodes != nil {
		validNodes := make([]TeachingNodeItem, 0, len(result.Nodes))
		for _, n := range result.Nodes {
			if n.NodeID != "" {
				validNodes = append(validNodes, n)
			}
		}
		result.Nodes = validNodes
	}
	return &result, nil
}

func (c *aiEngineClient) GenerationPreview(ctx context.Context, req GenerationPreviewRequest) (*GenerationPreviewResponse, error) {
	var result GenerationPreviewResponse
	if err := c.postJSON(ctx, "/api/v1/gen/preview", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// GetPreview GET /api/v1/gen/preview/{gen_id} — 按版本快照恢复预览（前端刷新后恢复持久化预览）。
func (c *aiEngineClient) GetPreview(ctx context.Context, genID string, version *int) (*GenerationPreviewResponse, error) {
	path := "/api/v1/gen/preview/" + genID
	if version != nil {
		path += "?version=" + strconv.Itoa(*version)
	}
	var result GenerationPreviewResponse
	if err := c.getJSON(ctx, path, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// ---- S4: 个性化 & 版本 & 导出 ----

func (c *aiEngineClient) GenerationModify(ctx context.Context, req GenerationModifyRequest) (*GenerationModifyResponse, error) {
	var result GenerationModifyResponse
	if err := c.postJSON(ctx, "/api/v1/gen/modify", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) VersionHistory(ctx context.Context, genID string) (*VersionHistoryResponse, error) {
	var result VersionHistoryResponse
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/v1/version/"+genID+"/history", nil)
	if err != nil {
		return nil, fmt.Errorf("构造版本历史请求失败: %w", err)
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("查询版本历史失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("查询版本历史返回异常: %d", resp.StatusCode)
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("解析版本历史响应失败: %w", err)
	}
	return &result, nil
}

func (c *aiEngineClient) VersionLoad(ctx context.Context, genID string, versionNumber int) (*VersionSnapshot, error) {
	var result VersionSnapshot
	path := "/api/v1/version/" + genID
	if versionNumber > 0 {
		path += "?v=" + strconv.Itoa(versionNumber)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return nil, fmt.Errorf("构造版本加载请求失败: %w", err)
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("版本加载请求失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("版本加载返回异常: %d", resp.StatusCode)
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("解析版本加载响应失败: %w", err)
	}
	return &result, nil
}

func (c *aiEngineClient) VersionRollback(ctx context.Context, genID string, req VersionRollbackRequest) (*VersionRollbackResponse, error) {
	var result VersionRollbackResponse
	if err := c.postJSON(ctx, "/api/v1/version/"+genID+"/rollback", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) VersionLock(ctx context.Context, genID string) (*VersionLockResponse, error) {
	var result VersionLockResponse
	if err := c.postJSON(ctx, "/api/v1/version/"+genID+"/lock", nil, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) ExportCreate(ctx context.Context, genID string, req ExportCreateRequest) (*ExportCreateResponse, error) {
	var result ExportCreateResponse
	if err := c.postJSON(ctx, "/api/v1/export/"+genID, req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *aiEngineClient) ExportStatus(ctx context.Context, jobID string) (*ExportStatusResponse, error) {
	var result ExportStatusResponse
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/v1/export/status/"+jobID, nil)
	if err != nil {
		return nil, fmt.Errorf("构造导出状态请求失败: %w", err)
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("查询导出状态失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("查询导出状态返回异常: %d", resp.StatusCode)
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("解析导出状态响应失败: %w", err)
	}
	return &result, nil
}

// ExportDownloadURL returns the AI Engine's local download URL for a completed job.
// The teacher gateway wraps this URL so browsers do not need to know the AI Engine address.
func (c *aiEngineClient) ExportDownloadURL(jobID, extension string) string {
	return c.baseURL + "/download/" + jobID + "." + extension
}

func (c *aiEngineClient) postJSON(ctx context.Context, path string, reqBody any, out any) error {
	return c.postJSONWithTimeout(ctx, path, reqBody, out, 0)
}

func (c *aiEngineClient) postJSONWithTimeout(ctx context.Context, path string, reqBody any, out any, timeout time.Duration) error {
	bodyBytes, err := json.Marshal(reqBody)
	if err != nil {
		return fmt.Errorf("序列化请求失败: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewBuffer(bodyBytes))
	if err != nil {
		return fmt.Errorf("构造请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	client := c.client
	if timeout > 0 {
		clientCopy := *c.client
		clientCopy.Timeout = timeout
		client = &clientCopy
	}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("调用AI引擎失败: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
		detail := strings.TrimSpace(string(body))
		var payload struct {
			Detail any `json:"detail"`
		}
		if json.Unmarshal(body, &payload) == nil && payload.Detail != nil {
			switch value := payload.Detail.(type) {
			case string:
				detail = value
			default:
				if encoded, marshalErr := json.Marshal(value); marshalErr == nil {
					detail = string(encoded)
				}
			}
		}
		return &AIEngineHTTPError{StatusCode: resp.StatusCode, Detail: detail}
	}

	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return fmt.Errorf("解析AI引擎响应失败: %w", err)
	}
	return nil
}

func (c *aiEngineClient) getJSON(ctx context.Context, path string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return fmt.Errorf("构造请求失败: %w", err)
	}
	req.Header.Set("Accept", "application/json")

	resp, err := c.client.Do(req)
	if err != nil {
		return fmt.Errorf("调用AI引擎失败: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
		detail := strings.TrimSpace(string(body))
		var payload struct {
			Detail any `json:"detail"`
		}
		if json.Unmarshal(body, &payload) == nil && payload.Detail != nil {
			switch value := payload.Detail.(type) {
			case string:
				detail = value
			default:
				if encoded, marshalErr := json.Marshal(value); marshalErr == nil {
					detail = string(encoded)
				}
			}
		}
		return &AIEngineHTTPError{StatusCode: resp.StatusCode, Detail: detail}
	}

	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return fmt.Errorf("解析AI引擎响应失败: %w", err)
	}
	return nil
}

// AIEngineHTTPError 保留 Python AI Engine 的 HTTP 状态与错误详情，供 Handler 精确映射。
type AIEngineHTTPError struct {
	StatusCode int
	Detail     string
}

func (e *AIEngineHTTPError) Error() string {
	if e.Detail == "" {
		return fmt.Sprintf("AI引擎返回异常状态: %d", e.StatusCode)
	}
	return fmt.Sprintf("AI引擎返回异常状态 %d: %s", e.StatusCode, e.Detail)
}
