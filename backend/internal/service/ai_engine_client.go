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

	// ---- S4: 个性化 & 版本 & 导出 ----
	GenerationModify(ctx context.Context, genID string, req GenerationModifyRequest) (*GenerationModifyResponse, error)
	VersionHistory(ctx context.Context, genID string) (*VersionHistoryResponse, error)
	VersionLoad(ctx context.Context, genID string, versionNumber int) (*VersionSnapshot, error)
	VersionRollback(ctx context.Context, genID string, req VersionRollbackRequest) (*VersionRollbackResponse, error)
	VersionLock(ctx context.Context, genID string) (*VersionLockResponse, error)
	ExportCreate(ctx context.Context, genID string, req ExportCreateRequest) (*ExportCreateResponse, error)
	ExportStatus(ctx context.Context, jobID string) (*ExportStatusResponse, error)
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
	SessionID     string         `json:"session_id"`
	IntentSummary *IntentSummary `json:"intent_summary"`
	SessionStatus SessionStatus  `json:"session_status"`
	Response      string         `json:"response,omitempty"`
	NeedFollowup  bool           `json:"need_followup"`
	FollowupQs    []string       `json:"followup_questions,omitempty"`
	HumanSummary  string         `json:"human_summary,omitempty"`
	CompletionPct int            `json:"completion_pct"`
	TurnCount     int            `json:"turn_count"`
	MaxTurns      int            `json:"max_turns"`
	CanConfirm    bool           `json:"can_confirm"`
	Engine        string         `json:"engine,omitempty"`
	UsedFallback  bool           `json:"used_fallback"`
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
	MinScore         float64  `json:"min_score,omitempty"`
}

type RAGSearchResponse struct {
	Results     []SearchResultItem `json:"results"`
	TotalChunks int                `json:"total_chunks"`
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

type TeachingNodeItem struct {
	NodeID       string   `json:"node_id"`
	Title        string   `json:"title"`
	NodeType     string   `json:"node_type,omitempty"`
	Content      string   `json:"content,omitempty"`
	Summary      string   `json:"summary,omitempty"`
	PageRef      int      `json:"page_ref,omitempty"`
	CorePoints   []string `json:"core_points,omitempty"`
	Examples     []string `json:"examples,omitempty"`
	DurationMin  float64  `json:"estimated_duration_minutes,omitempty"`
	CitationRefs []string `json:"citation_refs,omitempty"`
	NextNodeID   string   `json:"next_node_id,omitempty"`
}

type GenerationCreateRequest struct {
	SessionID      string          `json:"session_id"`
	CourseID       string          `json:"course_id,omitempty"`
	Title          string          `json:"title,omitempty"`
	Markdown       string          `json:"markdown,omitempty"`
	Intent         *IntentSummary  `json:"intent,omitempty"`
	EvidencePacket *EvidencePacket `json:"evidence_packet,omitempty"`
	TemplateID     string          `json:"template_id,omitempty"`
}

type GenerationCreateResponse struct {
	TaskID         string `json:"task_id"`
	GenerationID   string `json:"generation_id"`
	Status         string `json:"status"`
	GenerationType string `json:"generation_type,omitempty"`
}

type GenerationStatusResponse struct {
	TaskID      string             `json:"task_id"`
	Status      string             `json:"status"`
	Stage       string             `json:"stage,omitempty"`
	ProgressPct float64            `json:"progress_pct"`
	CurrentNode string             `json:"current_node,omitempty"`
	Nodes       []TeachingNodeItem `json:"nodes,omitempty"`
	PreviewURL  string             `json:"preview_url,omitempty"`
	Error       string             `json:"error,omitempty"`
}

type GenerationPreviewRequest struct {
	Nodes      []TeachingNodeItem `json:"nodes"`
	CourseName string             `json:"course_name,omitempty"`
}

type GenerationPreviewResponse struct {
	HTML      string `json:"html"`
	NodeCount int    `json:"node_count"`
}

// =============================================================================
// S4: 个性化 & 版本 & 导出 — 请求/响应类型
// =============================================================================

type ModifyCommandItem struct {
	CommandType   string   `json:"command_type"`
	NodeID        string   `json:"node_id,omitempty"`
	TargetNodeIDs []string `json:"target_node_ids,omitempty"`
	Content       string   `json:"content,omitempty"`
	AfterNodeID   string   `json:"after_node_id,omitempty"`
	TemplateID    string   `json:"template_id,omitempty"`
	SplitPoint    string   `json:"split_point,omitempty"`
	Regenerate    bool     `json:"regenerate"`
}

type GenerationModifyRequest struct {
	Commands []ModifyCommandItem `json:"commands"`
}

type GenerationModifyResponse struct {
	TaskID     string `json:"task_id"`
	NewVersion int    `json:"new_version"`
	Status     string `json:"status"`
}

type VersionSnapshot struct {
	ID            string             `json:"id"`
	GenerationID  string             `json:"generation_id"`
	VersionNumber int                `json:"version_number"`
	NodesSnapshot []TeachingNodeItem `json:"nodes_snapshot,omitempty"`
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
	CurrentVersion int    `json:"current_version"`
	Status         string `json:"status"`
}

type VersionLockResponse struct {
	Version    int               `json:"version"`
	Locked     bool              `json:"locked"`
	ExportURLs map[string]string `json:"export_urls,omitempty"`
}

type ExportCreateRequest struct {
	Format  string `json:"format"`
	Version int    `json:"version"`
}

type ExportCreateResponse struct {
	JobID  string `json:"job_id"`
	Status string `json:"status"`
}

type ExportStatusResponse struct {
	JobID       string `json:"job_id"`
	Status      string `json:"status"`
	DownloadURL string `json:"download_url,omitempty"`
	Error       string `json:"error,omitempty"`
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
	if err := c.postJSON(ctx, "/api/v1/intent/extract", req, &result); err != nil {
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
			if n.ID != "" {
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

// ---- S4: 个性化 & 版本 & 导出 ----

func (c *aiEngineClient) GenerationModify(ctx context.Context, genID string, req GenerationModifyRequest) (*GenerationModifyResponse, error) {
	var result GenerationModifyResponse
	if err := c.postJSON(ctx, "/api/v1/gen/modify/"+genID, req, &result); err != nil {
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
	bodyBytes, err := json.Marshal(reqBody)
	if err != nil {
		return fmt.Errorf("序列化请求失败: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewBuffer(bodyBytes))
	if err != nil {
		return fmt.Errorf("构造请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

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
