package service

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"
)

type OutlineStatus string

const (
	OutlineStatusDraft     OutlineStatus = "draft"
	OutlineStatusConfirmed OutlineStatus = "confirmed"
)

var (
	ErrOutlineNotFound        = errors.New("outline not found")
	ErrOutlineVersionConflict = errors.New("outline version conflict")
	ErrOutlineConfirmed       = errors.New("confirmed outline cannot be overwritten")
	ErrOutlineNotConfirmed    = errors.New("outline is not confirmed")
	ErrOutlineInvalid         = errors.New("outline is invalid")
)

type OutlineNode struct {
	NodeID                   string         `json:"node_id"`
	Order                    int            `json:"order"`
	Title                    string         `json:"title"`
	Summary                  string         `json:"summary"`
	NodeType                 string         `json:"node_type"`
	KeyPoints                []string       `json:"key_points"`
	EstimatedDurationMinutes float64        `json:"estimated_duration_minutes"`
	SourceChunkIDs           []string       `json:"source_chunk_ids"`
	InteractivePlan          map[string]any `json:"interactive_plan,omitempty"`
}

type OutlineGenerateRequest struct {
	Intent         map[string]any  `json:"intent"`
	EvidencePacket *EvidencePacket `json:"evidence_packet,omitempty"`
	Markdown       string          `json:"markdown,omitempty"`
	CourseName     string          `json:"course_name,omitempty"`
}

type OutlineGenerateResponse struct {
	Nodes        []OutlineNode `json:"nodes"`
	UsedFallback bool          `json:"used_fallback"`
}

type OutlineReviseAIRequest struct {
	Nodes   []OutlineNode `json:"nodes"`
	Message string        `json:"message"`
}

type OutlineReviseAIResponse struct {
	OutlineVersion int           `json:"outline_version"`
	Nodes          []OutlineNode `json:"nodes"`
	ChangeSummary  []string      `json:"change_summary"`
}

type OutlineAI interface {
	GenerateOutline(context.Context, OutlineGenerateRequest) (*OutlineGenerateResponse, error)
	ReviseOutline(context.Context, OutlineReviseAIRequest) (*OutlineReviseAIResponse, error)
}

type OutlineCreateRequest struct {
	SessionID      string          `json:"session_id"`
	IntentID       string          `json:"intent_id"`
	Intent         map[string]any  `json:"intent"`
	EvidencePacket *EvidencePacket `json:"evidence_packet,omitempty"`
	Markdown       string          `json:"markdown,omitempty"`
}

type OutlineSaveRequest struct {
	BaseVersion int           `json:"base_version"`
	Nodes       []OutlineNode `json:"nodes"`
}

type OutlineReviseRequest struct {
	Message     string `json:"message"`
	BaseVersion int    `json:"base_version"`
	AutoApply   bool   `json:"auto_apply"`
}

type Outline struct {
	OutlineID      string        `json:"outline_id"`
	OutlineVersion int           `json:"outline_version"`
	Status         OutlineStatus `json:"status"`
	Title          string        `json:"title"`
	SessionID      string        `json:"session_id"`
	IntentID       string        `json:"intent_id"`
	Nodes          []OutlineNode `json:"nodes"`
	ConfirmedAt    string        `json:"confirmed_at,omitempty"`
}

// OutlineService owns outline workflow state. AI only computes candidate nodes.
type OutlineService struct {
	mu       sync.RWMutex
	ai       OutlineAI
	versions map[string][]Outline
}

func NewOutlineService(aiClient any) *OutlineService {
	ai, _ := aiClient.(OutlineAI)
	return &OutlineService{ai: ai, versions: make(map[string][]Outline)}
}

func (s *OutlineService) Create(ctx context.Context, req OutlineCreateRequest) (*Outline, error) {
	if s.ai == nil {
		return nil, errors.New("AI client does not support outline generation")
	}
	generated, err := s.ai.GenerateOutline(ctx, OutlineGenerateRequest{
		Intent: req.Intent, EvidencePacket: req.EvidencePacket, Markdown: req.Markdown,
		CourseName: outlineStringValue(req.Intent["topic"]),
	})
	if err != nil {
		return nil, err
	}
	nodes, err := normalizeOutlineNodes(generated.Nodes)
	if err != nil {
		return nil, err
	}
	outline := Outline{
		OutlineID: fmt.Sprintf("outline_%d", time.Now().UnixNano()), OutlineVersion: 1,
		Status: OutlineStatusDraft, Title: outlineStringValue(req.Intent["topic"]),
		SessionID: req.SessionID, IntentID: req.IntentID, Nodes: nodes,
	}
	s.mu.Lock()
	s.versions[outline.OutlineID] = []Outline{cloneOutline(outline)}
	s.mu.Unlock()
	result := cloneOutline(outline)
	return &result, nil
}

func (s *OutlineService) Get(outlineID string, version int) (*Outline, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := s.versions[outlineID]
	if len(items) == 0 {
		return nil, ErrOutlineNotFound
	}
	if version <= 0 {
		result := cloneOutline(items[len(items)-1])
		return &result, nil
	}
	for _, item := range items {
		if item.OutlineVersion == version {
			result := cloneOutline(item)
			return &result, nil
		}
	}
	return nil, ErrOutlineNotFound
}

func (s *OutlineService) Save(outlineID string, req OutlineSaveRequest) (*Outline, error) {
	nodes, err := normalizeOutlineNodes(req.Nodes)
	if err != nil {
		return nil, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	items := s.versions[outlineID]
	if len(items) == 0 {
		return nil, ErrOutlineNotFound
	}
	latest := items[len(items)-1]
	if latest.Status == OutlineStatusConfirmed {
		return nil, ErrOutlineConfirmed
	}
	if req.BaseVersion != latest.OutlineVersion {
		return nil, ErrOutlineVersionConflict
	}
	next := cloneOutline(latest)
	next.OutlineVersion++
	next.Nodes = nodes
	next.Status = OutlineStatusDraft
	items = append(items, cloneOutline(next))
	s.versions[outlineID] = items
	result := cloneOutline(next)
	return &result, nil
}

func (s *OutlineService) Revise(ctx context.Context, outlineID string, req OutlineReviseRequest) (*OutlineReviseAIResponse, error) {
	if strings.TrimSpace(req.Message) == "" {
		return nil, ErrOutlineInvalid
	}
	latest, err := s.Get(outlineID, 0)
	if err != nil {
		return nil, err
	}
	if req.BaseVersion != latest.OutlineVersion {
		return nil, ErrOutlineVersionConflict
	}
	current, err := s.Get(outlineID, req.BaseVersion)
	if err != nil {
		return nil, err
	}
	if current.Status == OutlineStatusConfirmed {
		return nil, ErrOutlineConfirmed
	}
	if s.ai == nil {
		return nil, errors.New("AI client does not support outline revision")
	}
	result, err := s.ai.ReviseOutline(ctx, OutlineReviseAIRequest{Nodes: current.Nodes, Message: req.Message})
	if err != nil {
		return nil, err
	}
	result.Nodes, err = normalizeOutlineNodes(result.Nodes)
	result.OutlineVersion = current.OutlineVersion + 1
	return result, err
}

func (s *OutlineService) Confirm(outlineID string, version int) (*Outline, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := s.versions[outlineID]
	if len(items) == 0 {
		return nil, ErrOutlineNotFound
	}
	latest := &items[len(items)-1]
	if version != latest.OutlineVersion {
		return nil, ErrOutlineVersionConflict
	}
	if _, err := normalizeOutlineNodes(latest.Nodes); err != nil {
		return nil, err
	}
	latest.Status = OutlineStatusConfirmed
	latest.ConfirmedAt = time.Now().UTC().Format(time.RFC3339)
	s.versions[outlineID] = items
	result := cloneOutline(*latest)
	return &result, nil
}

func (s *OutlineService) GetConfirmed(outlineID string, version int) (*Outline, error) {
	outline, err := s.Get(outlineID, version)
	if err != nil {
		return nil, err
	}
	if outline.Status != OutlineStatusConfirmed {
		return nil, ErrOutlineNotConfirmed
	}
	return outline, nil
}

func normalizeOutlineNodes(nodes []OutlineNode) ([]OutlineNode, error) {
	if len(nodes) == 0 {
		return nil, ErrOutlineInvalid
	}
	seen := make(map[string]struct{}, len(nodes))
	result := cloneNodes(nodes)
	for i := range result {
		node := &result[i]
		if strings.TrimSpace(node.NodeID) == "" || strings.TrimSpace(node.Title) == "" {
			return nil, ErrOutlineInvalid
		}
		// AI 输出可能省略摘要；保留节点并用标题作为最小可展示摘要，
		// 避免 Python 侧允许的空 summary 在 Go 边界被整体判为无效大纲。
		if strings.TrimSpace(node.Summary) == "" {
			node.Summary = node.Title
		}
		if _, exists := seen[node.NodeID]; exists {
			return nil, ErrOutlineInvalid
		}
		seen[node.NodeID] = struct{}{}
		node.Order = i + 1
		if node.NodeType == "" {
			node.NodeType = "content"
		}
		if node.EstimatedDurationMinutes <= 0 {
			node.EstimatedDurationMinutes = 5
		}
	}
	return result, nil
}

func cloneOutline(value Outline) Outline {
	value.Nodes = cloneNodes(value.Nodes)
	return value
}

func cloneNodes(nodes []OutlineNode) []OutlineNode {
	result := make([]OutlineNode, len(nodes))
	copy(result, nodes)
	for i := range result {
		result[i].KeyPoints = append([]string(nil), nodes[i].KeyPoints...)
		result[i].SourceChunkIDs = append([]string(nil), nodes[i].SourceChunkIDs...)
		if nodes[i].InteractivePlan != nil {
			result[i].InteractivePlan = make(map[string]any, len(nodes[i].InteractivePlan))
			for k, v := range nodes[i].InteractivePlan {
				result[i].InteractivePlan[k] = v
			}
		}
	}
	return result
}

func outlineStringValue(value any) string {
	text, _ := value.(string)
	return strings.TrimSpace(text)
}
