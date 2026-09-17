package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

// =============================================================================
// S3: 大纲（Outline）业务服务 —— Go 网关侧状态管理。
//
// 职责边界（对齐《文档/S3数据与接口规范.md》v1.0 §6 + Python main.py:673 docstring）：
//   Python AI Engine 对大纲完全无状态（/gen/outline 与 /gen/outline/revise 均为纯函数），
//   大纲草稿 / 确认 / 版本链的持久化由本服务承担。
//
// 状态机（规范 §2.3）：draft → confirmed → superseded
//   确认后不得原地覆盖；对 confirmed 大纲的修改生成新 outline_version，旧版本保留。
// =============================================================================

// Outline 状态常量（规范 §2.3，仅允许三态；"confirming" 是前端本地过渡态，不落库）。
const (
	OutlineStatusDraft      = "draft"
	OutlineStatusConfirmed  = "confirmed"
	OutlineStatusSuperseded = "superseded"
)

// OutlineNode 节点类型常量（规范 §2.1 枚举）。
const (
	OutlineNodeTypeContent    = "content"
	OutlineNodeTypeSection    = "section"
	OutlineNodeTypeQuiz       = "quiz"
	OutlineNodeTypeInteractive = "interactive"
	OutlineNodeTypeSummary    = "summary"
)

// Outline 领域实体 —— outline_id + outline_version 唯一确定一份大纲内容（规范 §6）。
type Outline struct {
	OutlineID    string        `json:"outline_id"`
	OutlineVersion int         `json:"outline_version"`
	SessionID    string        `json:"session_id"`
	IntentID     string        `json:"intent_id"`
	Title        string        `json:"title"`
	Status       string        `json:"status"` // draft | confirmed | superseded
	Nodes        []OutlineNode `json:"nodes"`
	CreatedAt    time.Time     `json:"created_at"`
	UpdatedAt    time.Time     `json:"updated_at"`
	ConfirmedAt  *time.Time    `json:"confirmed_at,omitempty"`
}

// 哨兵错误 —— generation_handler.go:43 通过 errors.Is(err, service.ErrOutlineNotFound) 判 404。
var (
	ErrOutlineNotFound       = errors.New("大纲不存在")
	ErrOutlineVersionConflict = errors.New("大纲版本冲突")
	ErrOutlineNotConfirmed   = errors.New("大纲尚未确认")
	ErrInvalidOutline        = errors.New("大纲结构校验失败")
)

// =============================================================================
// OutlineStore —— 持久化抽象（db 可用走 Postgres，S1 standalone 走进程内存）。
// =============================================================================

type OutlineStore interface {
	// Create 写入首个版本（outline_version=1）。
	Create(ctx context.Context, o *Outline) error
	// GetLatest 取指定 outline_id 的最新版本。
	GetLatest(ctx context.Context, outlineID string) (*Outline, error)
	// GetVersion 取指定 outline_id + outline_version。
	GetVersion(ctx context.Context, outlineID string, version int) (*Outline, error)
	// SaveVersion 以新的 outline_version 追加一个版本（旧版本保留，不可覆盖）。
	SaveVersion(ctx context.Context, o *Outline) error
	// UpdateStatus 更新某版本的状态（draft→confirmed / superseded）。
	UpdateStatus(ctx context.Context, outlineID string, version int, status string, confirmedAt *time.Time) error
	// ListVersions 列出全部版本（按 version 升序）。
	ListVersions(ctx context.Context, outlineID string) ([]*Outline, error)
}

// ---- memOutlineStore：进程内存实现（S1 standalone 降级，重启即失）----

type memOutlineStore struct {
	mu      sync.RWMutex
	byID    map[string][]*Outline // outline_id -> 按 version 升序的版本链
}

func newMemOutlineStore() *memOutlineStore {
	return &memOutlineStore{byID: make(map[string][]*Outline)}
}

func (s *memOutlineStore) Create(_ context.Context, o *Outline) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.byID[o.OutlineID]; exists {
		return fmt.Errorf("%w: 大纲已存在", ErrOutlineVersionConflict)
	}
	cp := cloneOutline(o)
	cp.OutlineVersion = 1
	s.byID[o.OutlineID] = []*Outline{cp}
	return nil
}

func (s *memOutlineStore) GetLatest(_ context.Context, outlineID string) (*Outline, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	chain := s.byID[outlineID]
	if len(chain) == 0 {
		return nil, ErrOutlineNotFound
	}
	return cloneOutline(chain[len(chain)-1]), nil
}

func (s *memOutlineStore) GetVersion(_ context.Context, outlineID string, version int) (*Outline, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, o := range s.byID[outlineID] {
		if o.OutlineVersion == version {
			return cloneOutline(o), nil
		}
	}
	return nil, ErrOutlineNotFound
}

func (s *memOutlineStore) SaveVersion(_ context.Context, o *Outline) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	chain := s.byID[o.OutlineID]
	if len(chain) == 0 {
		return ErrOutlineNotFound
	}
	// 新版本号必须在当前链末之后；防止并发冲突
	if o.OutlineVersion <= chain[len(chain)-1].OutlineVersion {
		return fmt.Errorf("%w: 当前版本为 %d，不能保存版本 %d",
			ErrOutlineVersionConflict, chain[len(chain)-1].OutlineVersion, o.OutlineVersion)
	}
	cp := cloneOutline(o)
	s.byID[o.OutlineID] = append(chain, cp)
	return nil
}

func (s *memOutlineStore) UpdateStatus(_ context.Context, outlineID string, version int, status string, confirmedAt *time.Time) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, o := range s.byID[outlineID] {
		if o.OutlineVersion == version {
			o.Status = status
			o.ConfirmedAt = confirmedAt
			return nil
		}
	}
	return ErrOutlineNotFound
}

func (s *memOutlineStore) ListVersions(_ context.Context, outlineID string) ([]*Outline, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	chain := s.byID[outlineID]
	if len(chain) == 0 {
		return nil, ErrOutlineNotFound
	}
	out := make([]*Outline, 0, len(chain))
	for _, o := range chain {
		out = append(out, cloneOutline(o))
	}
	return out, nil
}

func cloneOutline(o *Outline) *Outline {
	if o == nil {
		return nil
	}
	cp := *o
	cp.Nodes = make([]OutlineNode, len(o.Nodes))
	copy(cp.Nodes, o.Nodes)
	if o.ConfirmedAt != nil {
		t := *o.ConfirmedAt
		cp.ConfirmedAt = &t
	}
	return &cp
}

// ---- gormOutlineStore：Postgres 实现（完整模式，跨重启持久化）----

// outlineVersionRow —— outlines 版本链表行（一个 outline_id 多行，每行一个版本）。
// Nodes 以 JSON 文本列存储（沿用 course.go json.Marshal 先例）。
type outlineVersionRow struct {
	OutlineID      string     `gorm:"column:outline_id;size:64;primaryKey"`
	OutlineVersion int        `gorm:"column:outline_version;primaryKey"`
	SessionID      string     `gorm:"column:session_id;size:64"`
	IntentID       string     `gorm:"column:intent_id;size:64"`
	Title          string     `gorm:"column:title;size:500"`
	Status         string     `gorm:"column:status;size:20;index"`
	NodesJSON      string     `gorm:"column:nodes_json;type:text"`
	CreatedAt      time.Time  `gorm:"column:created_at"`
	UpdatedAt      time.Time  `gorm:"column:updated_at"`
	ConfirmedAt    *time.Time `gorm:"column:confirmed_at"`
}

// TableName 指定表名（规范语义：outline_id + outline_version 复合主键）。
func (outlineVersionRow) TableName() string { return "outline_versions" }

type gormOutlineStore struct {
	db *gorm.DB
}

func newGormOutlineStore(db *gorm.DB) *gormOutlineStore {
	return &gormOutlineStore{db: db}
}

func (s *gormOutlineStore) Create(_ context.Context, o *Outline) error {
	o.OutlineVersion = 1
	row, err := marshalOutlineRow(o)
	if err != nil {
		return err
	}
	if err := s.db.Create(row).Error; err != nil {
		if strings.Contains(err.Error(), "duplicate") || strings.Contains(err.Error(), "unique") {
			return fmt.Errorf("%w: 大纲已存在", ErrOutlineVersionConflict)
		}
		return fmt.Errorf("创建大纲失败: %w", err)
	}
	return nil
}

func (s *gormOutlineStore) GetLatest(ctx context.Context, outlineID string) (*Outline, error) {
	var row outlineVersionRow
	if err := s.db.WithContext(ctx).Where("outline_id = ?", outlineID).
		Order("outline_version DESC").First(&row).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrOutlineNotFound
		}
		return nil, fmt.Errorf("读取大纲失败: %w", err)
	}
	return unmarshalOutlineRow(&row)
}

func (s *gormOutlineStore) GetVersion(ctx context.Context, outlineID string, version int) (*Outline, error) {
	var row outlineVersionRow
	if err := s.db.WithContext(ctx).Where("outline_id = ? AND outline_version = ?", outlineID, version).
		First(&row).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrOutlineNotFound
		}
		return nil, fmt.Errorf("读取大纲失败: %w", err)
	}
	return unmarshalOutlineRow(&row)
}

func (s *gormOutlineStore) SaveVersion(ctx context.Context, o *Outline) error {
	// 校验新版本号紧接当前链末（乐观并发控制）
	var currentMax int
	if err := s.db.WithContext(ctx).Model(&outlineVersionRow{}).
		Where("outline_id = ?", o.OutlineID).
		Select("COALESCE(MAX(outline_version), 0)").Scan(&currentMax).Error; err != nil {
		return fmt.Errorf("读取当前版本失败: %w", err)
	}
	if o.OutlineVersion <= currentMax {
		return fmt.Errorf("%w: 当前版本为 %d，不能保存版本 %d",
			ErrOutlineVersionConflict, currentMax, o.OutlineVersion)
	}
	row, err := marshalOutlineRow(o)
	if err != nil {
		return err
	}
	if err := s.db.WithContext(ctx).Create(row).Error; err != nil {
		return fmt.Errorf("保存大纲版本失败: %w", err)
	}
	return nil
}

func (s *gormOutlineStore) UpdateStatus(ctx context.Context, outlineID string, version int, status string, confirmedAt *time.Time) error {
	updates := map[string]any{"status": status, "updated_at": time.Now()}
	if confirmedAt != nil {
		updates["confirmed_at"] = confirmedAt
	}
	res := s.db.WithContext(ctx).Model(&outlineVersionRow{}).
		Where("outline_id = ? AND outline_version = ?", outlineID, version).Updates(updates)
	if res.Error != nil {
		return fmt.Errorf("更新大纲状态失败: %w", res.Error)
	}
	if res.RowsAffected == 0 {
		return ErrOutlineNotFound
	}
	return nil
}

func (s *gormOutlineStore) ListVersions(ctx context.Context, outlineID string) ([]*Outline, error) {
	var rows []outlineVersionRow
	if err := s.db.WithContext(ctx).Where("outline_id = ?", outlineID).
		Order("outline_version ASC").Find(&rows).Error; err != nil {
		return nil, fmt.Errorf("列出大纲版本失败: %w", err)
	}
	if len(rows) == 0 {
		return nil, ErrOutlineNotFound
	}
	out := make([]*Outline, 0, len(rows))
	for i := range rows {
		o, err := unmarshalOutlineRow(&rows[i])
		if err != nil {
			return nil, err
		}
		out = append(out, o)
	}
	return out, nil
}

func marshalOutlineRow(o *Outline) (*outlineVersionRow, error) {
	nodesJSON, err := json.Marshal(o.Nodes)
	if err != nil {
		return nil, fmt.Errorf("序列化大纲节点失败: %w", err)
	}
	return &outlineVersionRow{
		OutlineID:      o.OutlineID,
		OutlineVersion: o.OutlineVersion,
		SessionID:      o.SessionID,
		IntentID:       o.IntentID,
		Title:          o.Title,
		Status:         o.Status,
		NodesJSON:      string(nodesJSON),
		CreatedAt:      o.CreatedAt,
		UpdatedAt:      o.UpdatedAt,
		ConfirmedAt:    o.ConfirmedAt,
	}, nil
}

func unmarshalOutlineRow(row *outlineVersionRow) (*Outline, error) {
	o := &Outline{
		OutlineID:      row.OutlineID,
		OutlineVersion: row.OutlineVersion,
		SessionID:      row.SessionID,
		IntentID:       row.IntentID,
		Title:          row.Title,
		Status:         row.Status,
		CreatedAt:      row.CreatedAt,
		UpdatedAt:      row.UpdatedAt,
		ConfirmedAt:    row.ConfirmedAt,
	}
	if row.NodesJSON != "" {
		if err := json.Unmarshal([]byte(row.NodesJSON), &o.Nodes); err != nil {
			return nil, fmt.Errorf("解析大纲节点失败: %w", err)
		}
	}
	if o.Nodes == nil {
		o.Nodes = []OutlineNode{}
	}
	return o, nil
}

// =============================================================================
// OutlineService —— 业务门面。
// =============================================================================

type OutlineService struct {
	aiClient AIEngine
	store    OutlineStore
}

// NewOutlineService —— 单参构造（S1 standalone / 无 db 时使用进程内存存储）。
// 签名兼容 cmd/teacher/main.go:130 与 :199 的既有装配。
func NewOutlineService(aiClient AIEngine) *OutlineService {
	return &OutlineService{aiClient: aiClient, store: newMemOutlineStore()}
}

// NewOutlineServiceWithDB —— db 就绪的完整模式：Postgres 持久化。
func NewOutlineServiceWithDB(aiClient AIEngine, db *gorm.DB) *OutlineService {
	return &OutlineService{aiClient: aiClient, store: newGormOutlineStore(db)}
}

// CreateOutline 生成大纲草稿（version=1, status=draft）。
// 无 markdown 时调 Python /gen/outline（OutlineBuilder.build）；有 markdown 走 build_from_markdown。
func (s *OutlineService) CreateOutline(ctx context.Context, req OutlineGenerateRequest) (*Outline, error) {
	if req.SessionID == "" {
		return nil, fmt.Errorf("session_id 不能为空")
	}
	resp, err := s.aiClient.GenerateOutline(ctx, req)
	if err != nil {
		return nil, err
	}
	// 若无 markdown 且 intent.topic 存在，回填标题
	title := ""
	if req.Markdown == "" && req.Intent != nil && req.Intent.Topic != nil {
		title = *req.Intent.Topic
	}
	outlineID := "outline_" + uuid.NewString()[:12]
	now := time.Now()
	outline := &Outline{
		OutlineID:      outlineID,
		OutlineVersion: 0, // Create 时 store 置为 1
		SessionID:      req.SessionID,
		IntentID:       req.IntentID,
		Title:          title,
		Status:         OutlineStatusDraft,
		Nodes:          normalizeOutlineNodes(resp.Nodes),
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	if err := s.store.Create(ctx, outline); err != nil {
		return nil, err
	}
	outline.OutlineVersion = 1
	return outline, nil
}

// GetOutline 读取指定版本大纲；version<=0 时返回最新版本（前端缺省 GET）。
func (s *OutlineService) GetOutline(ctx context.Context, outlineID string, version int) (*Outline, error) {
	if version <= 0 {
		return s.store.GetLatest(ctx, outlineID)
	}
	return s.store.GetVersion(ctx, outlineID, version)
}

// SaveOutlineVersion 手动编辑保存（PUT /outlines/:id）。规范 §3.4：
//   - base_version 必须等于当前版本，否则 409
//   - node_id 不重复、order 从 1 连续
//   - 保留原 node_id
//   - 保存后生成新 outline_version
// 对 confirmed 大纲的修改：旧版本置 superseded，新版本以 draft 起（可重新确认）。
func (s *OutlineService) SaveOutlineVersion(ctx context.Context, outlineID string, baseVersion int, nodes []OutlineNode) (*Outline, error) {
	current, err := s.store.GetLatest(ctx, outlineID)
	if err != nil {
		return nil, err
	}
	if current.OutlineVersion != baseVersion {
		return nil, fmt.Errorf("%w: 当前版本为 %d", ErrOutlineVersionConflict, current.OutlineVersion)
	}
	if err := validateOutlineNodes(nodes); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidOutline, err)
	}
	now := time.Now()
	newVersion := &Outline{
		OutlineID:      outlineID,
		OutlineVersion: current.OutlineVersion + 1,
		SessionID:      current.SessionID,
		IntentID:       current.IntentID,
		Title:          current.Title,
		Status:         OutlineStatusDraft, // 修改后重新进入草稿态，可再次确认
		Nodes:          normalizeOutlineNodes(nodes),
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	if current.Status == OutlineStatusConfirmed {
		// 确认大纲被修改 → 旧版本 superseded（规范 §2.3）
		_ = s.store.UpdateStatus(ctx, outlineID, current.OutlineVersion, OutlineStatusSuperseded, current.ConfirmedAt)
	}
	if err := s.store.SaveVersion(ctx, newVersion); err != nil {
		return nil, err
	}
	return newVersion, nil
}

// ReviseOutline AI 修订（POST /outlines/:id/revise）。auto_apply=false 时返回待确认候选，不落库。
// 若 auto_apply=true，则把修订结果作为新版本保存。
func (s *OutlineService) ReviseOutline(ctx context.Context, outlineID string, message string, baseVersion int, autoApply bool) (*Outline, error) {
	base, err := s.store.GetVersion(ctx, outlineID, baseVersion)
	if err != nil {
		return nil, err
	}
	resp, err := s.aiClient.ReviseOutline(ctx, OutlineReviseAIRequest{
		Nodes:   base.Nodes,
		Message: message,
	})
	if err != nil {
		return nil, err
	}
	revised := &Outline{
		OutlineID:      outlineID,
		OutlineVersion: base.OutlineVersion + 1,
		SessionID:      base.SessionID,
		IntentID:       base.IntentID,
		Title:          base.Title,
		Status:         OutlineStatusDraft,
		Nodes:          normalizeOutlineNodes(resp.Nodes),
		CreatedAt:      time.Now(),
		UpdatedAt:      time.Now(),
	}
	if !autoApply {
		// 待确认候选：version 预置为下一个号但未落库，由后续 PUT base_version=候选号 提交
		return revised, nil
	}
	if err := s.store.SaveVersion(ctx, revised); err != nil {
		return nil, err
	}
	return revised, nil
}

// ConfirmOutline 确认大纲（POST /outlines/:id/confirm）。规范 §3.5 校验通过后 status→confirmed。
func (s *OutlineService) ConfirmOutline(ctx context.Context, outlineID string, version int) (*Outline, error) {
	o, err := s.store.GetVersion(ctx, outlineID, version)
	if err != nil {
		return nil, err
	}
	if err := validateOutlineNodes(o.Nodes); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidOutline, err)
	}
	if len(o.Nodes) == 0 {
		return nil, fmt.Errorf("%w: 节点数量为 0", ErrInvalidOutline)
	}
	now := time.Now()
	if err := s.store.UpdateStatus(ctx, outlineID, version, OutlineStatusConfirmed, &now); err != nil {
		return nil, err
	}
	o.Status = OutlineStatusConfirmed
	o.ConfirmedAt = &now
	return o, nil
}

// GetConfirmed 读取指定版本且必须为 confirmed 状态的大纲。
// 供 GenerationHandler.Create 在携带 outline_id 时取确认大纲节点注入生成任务（generation_handler.go:43）。
func (s *OutlineService) GetConfirmed(ctx context.Context, outlineID string, version int) (*Outline, error) {
	o, err := s.store.GetVersion(ctx, outlineID, version)
	if err != nil {
		return nil, err
	}
	if o.Status != OutlineStatusConfirmed {
		return nil, fmt.Errorf("%w: 当前状态为 %s", ErrOutlineNotConfirmed, o.Status)
	}
	return o, nil
}

// ListVersions 列出大纲全部版本。
func (s *OutlineService) ListVersions(ctx context.Context, outlineID string) ([]*Outline, error) {
	return s.store.ListVersions(ctx, outlineID)
}

// =============================================================================
// 校验与归一
// =============================================================================

// validateOutlineNodes —— 规范 §3.4/§3.5 校验：
//   - 非空
//   - node_id 不重复且非空
//   - order 从 1 连续编号且不重复
//   - title / summary 非空
//   - estimated_duration_minutes > 0
//   - node_type 合法
func validateOutlineNodes(nodes []OutlineNode) error {
	if len(nodes) == 0 {
		return fmt.Errorf("节点数量为 0")
	}
	seenID := make(map[string]bool, len(nodes))
	for i, n := range nodes {
		if n.NodeID == "" {
			return fmt.Errorf("第 %d 个节点缺少 node_id", i+1)
		}
		if seenID[n.NodeID] {
			return fmt.Errorf("node_id 重复: %s", n.NodeID)
		}
		seenID[n.NodeID] = true
		if n.Order != i+1 {
			return fmt.Errorf("order 必须从 1 连续编号: 期望 %d 实际 %d", i+1, n.Order)
		}
		if strings.TrimSpace(n.Title) == "" {
			return fmt.Errorf("节点 %s 标题为空", n.NodeID)
		}
		if strings.TrimSpace(n.Summary) == "" {
			return fmt.Errorf("节点 %s 摘要为空", n.NodeID)
		}
		if n.EstimatedDurationMin <= 0 {
			return fmt.Errorf("节点 %s 时长必须大于 0", n.NodeID)
		}
		switch n.NodeType {
		case OutlineNodeTypeContent, OutlineNodeTypeSection, OutlineNodeTypeQuiz,
			OutlineNodeTypeInteractive, OutlineNodeTypeSummary:
		case "":
			return fmt.Errorf("节点 %s 缺少 node_type", n.NodeID)
		default:
			return fmt.Errorf("节点 %s node_type 非法: %s", n.NodeID, n.NodeType)
		}
	}
	return nil
}

// normalizeOutlineNodes —— 兜底归一：node_id 缺失时补生成、order 重排连续。
func normalizeOutlineNodes(nodes []OutlineNode) []OutlineNode {
	if nodes == nil {
		return []OutlineNode{}
	}
	out := make([]OutlineNode, 0, len(nodes))
	seenID := make(map[string]bool, len(nodes))
	for i, n := range nodes {
		if n.NodeID == "" || seenID[n.NodeID] {
			n.NodeID = fmt.Sprintf("node_%03d", i+1)
		}
		seenID[n.NodeID] = true
		n.Order = i + 1
		if n.NodeType == "" {
			n.NodeType = OutlineNodeTypeContent
		}
		if n.KeyPoints == nil {
			n.KeyPoints = []string{}
		}
		out = append(out, n)
	}
	return out
}
