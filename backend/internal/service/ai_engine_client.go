package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"strings"
	"time"
)

type AIEngine interface {
	ParseDocument(ctx context.Context, file *multipart.FileHeader) (*ParseDocumentResponse, error)
	ReconstructDocument(ctx context.Context, req ReconstructDocumentRequest) (*ReconstructDocumentResponse, error)
	GenerateNodeScript(ctx context.Context, req GenerateNodeScriptRequest) (*GenerateNodeScriptResponse, error)
	GenerateFromMarkdown(ctx context.Context, req GenerateFromMarkdownRequest) (*GenerateFromMarkdownResponse, error)
	GenerateScript(ctx context.Context, req GenerateScriptRequest) (*GenerateScriptResponse, error)
	GenerateAudio(ctx context.Context, req GenerateAudioRequest) (*GenerateAudioResponse, error)
	AskWithContext(ctx context.Context, req AskWithContextRequest) (*AskWithContextResponse, error)
	ParseKnowledge(ctx context.Context, req ParseKnowledgeRequest) (*ParseKnowledgeResponse, error)
}

type aiEngineClient struct {
	baseURL string
	client  *http.Client
}

type GenerateScriptRequest struct {
	Page       int    `json:"page"`
	Content    string `json:"content"`
	CourseName string `json:"course_name"`
	Mode       string `json:"mode"`
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
	TeachingNode map[string]any `json:"teaching_node"`
	CourseName   string         `json:"course_name"`
	Mode         string         `json:"mode"`
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
	Page            int    `json:"page"`
	Script          string `json:"script"`
	MindmapMarkdown string `json:"mindmap_markdown"`
	UseEnhancedSchema bool   `json:"use_enhanced_schema"`
	Scripts         []any  `json:"scripts,omitempty"`
}

type GenerateEnhancedRequest struct {
	Markdown   string `json:"markdown"`
	CourseName string `json:"course_name"`
	Mode       string `json:"mode"`
}

type GenerateEnhancedResponse struct {
	CourseName       string `json:"course_name"`
	SourceMarkdown   string `json:"source_markdown"`
	KeyPoints        []string `json:"key_points"`
	NodeTree         map[string]any `json:"node_tree"`
	Scripts          []any `json:"scripts"`
	UseEnhancedSchema bool `json:"use_enhanced_schema"`
	UsedFallback     bool   `json:"used_fallback"`
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
		return fmt.Errorf("AI引擎返回异常状态: %d", resp.StatusCode)
	}

	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return fmt.Errorf("解析AI引擎响应失败: %w", err)
	}
	return nil
}
