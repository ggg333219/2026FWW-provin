package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

// =============================================================================
// 课件项目（courseware_projects）+ 修改对话与版本快照（A6/A7）
//
// 依赖链：A6 挂在 courseware_projects 上；本文件同时提供 A1 的最小基础
// （项目 CRUD），供中间页"我的课件"（R3/R4）后续复用。
//
// 版本快照模型（courseware_versions）：
//   每次 modify 前自动快照修改前的完整状态，版本号自增 v1→v2→v3；
//   回滚（A7）= 克隆目标版本为新版本，不覆盖历史。
// =============================================================================

var (
	ErrProjectNotFound = errors.New("课件项目不存在")
	ErrVersionNotFound = errors.New("课件版本不存在")
)

// CoursewareProject —— 课件项目（A1 最小基础，契约 §3.8.3）。
type CoursewareProject struct {
	ProjectID   string    `json:"project_id"`
	OwnerID     string    `json:"owner_id"`
	Title       string    `json:"title"`
	CurrentStep string    `json:"current_step"` // s1_intent / s2_material / s3_studio / s4_version
	GenID       string    `json:"gen_id,omitempty"`
	Status      string    `json:"status"` // draft / generating / done / locked
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// coursewareProjectRow —— gorm 表映射。
type coursewareProjectRow struct {
	// ID is the canonical key used by the persistent project workspace (A1-A5).
	// The former A6/A7 project_id column is not present in the current schema.
	ID          string    `gorm:"column:id;size:36;primaryKey"`
	OwnerID     string    `gorm:"column:owner_id;size:64;index"`
	Title       string    `gorm:"column:title;size:500"`
	CurrentStep string    `gorm:"column:current_step;size:20"`
	GenID       string    `gorm:"column:gen_id;size:64"`
	Status      string    `gorm:"column:status;size:20"`
	CreatedAt   time.Time `gorm:"column:created_at"`
	UpdatedAt   time.Time `gorm:"column:updated_at"`
}

func (coursewareProjectRow) TableName() string { return "courseware_projects" }

// CoursewareVersion —— 版本快照（A6）。
type CoursewareVersion struct {
	VersionID          string    `json:"version_id"`
	ProjectID          string    `json:"project_id"`
	VersionNo          int       `json:"version_no"`
	ParentVersionID    string    `json:"parent_version_id,omitempty"`
	NodesJSON          string    `json:"-"` // 原始 JSON（内部）
	BeforeSnapshotJSON string    `json:"-"`
	PresentationJSON   string    `json:"-"` // 修改前的 PPT 呈现层快照
	SnapshotJSON       string    `json:"-"` // 完整快照：节点、样式、页面证据绑定
	ModifyInstr        string    `json:"modify_instruction"`
	VersionSummary     string    `json:"version_summary"`
	CreatedAt          time.Time `json:"created_at"`

	// 契约 v1.0 模块 1：本次修改命中的页面 + 用户提供的证据 + AI 回写的引用。
	// 仅在 modify 路径（POST /api/v1/gen/modify / courseware Modify）下被填充；
	// 快照/回滚路径为空。
	GenerationID string   `json:"generation_id,omitempty"`
	PageID       string   `json:"page_id,omitempty"`
	EvidenceRefs []string `json:"evidence_refs,omitempty"`
	CitationRefs []string `json:"citation_refs,omitempty"`
	EvidenceUsed []string `json:"evidence_used,omitempty"`
}

type coursewareVersionRow struct {
	// ID is the legacy physical primary key already present in deployed
	// courseware_versions. Keep it populated even though the public contract
	// exposes version_id as the business identifier.
	ID                 string    `gorm:"column:id;size:64;primaryKey"`
	VersionID          string    `gorm:"column:version_id;size:64"`
	ProjectID          string    `gorm:"column:project_id;size:64;index"`
	OwnerID            string    `gorm:"column:owner_id;size:64"`
	VersionNo          int       `gorm:"column:version_no"`
	ParentVersionID    string    `gorm:"column:parent_version_id;size:64;index"`
	NodesJSON          string    `gorm:"column:nodes_snapshot;type:text"`
	BeforeSnapshotJSON string    `gorm:"column:before_snapshot_json;type:text"`
	PresentationJSON   string    `gorm:"column:presentation_snapshot;type:text"`
	SnapshotJSON       string    `gorm:"column:snapshot_json;type:text"`
	ModifyInstr        string    `gorm:"column:modify_instruction;size:1000"`
	VersionSummary     string    `gorm:"column:version_summary;size:1000"`
	CreatedAt          time.Time `gorm:"column:created_at"`
	GenerationID       string    `gorm:"column:generation_id;size:64;index"`
	PageID             string    `gorm:"column:page_id;size:64"`
	EvidenceRefs       string    `gorm:"column:evidence_refs;type:text"` // JSON: ["chunk_001", ...]
	CitationRefs       string    `gorm:"column:citation_refs;type:text"` // JSON: AI 回写
	EvidenceUsed       string    `gorm:"column:evidence_used;type:text"` // JSON: AI 回写
}

func (coursewareVersionRow) TableName() string { return "courseware_versions" }

// versionToRow 把内存模型投影到 gorm 行；带 JSON 编码的证据字段。
// 返回的行指针可直接 Create。
func versionToRow(v *CoursewareVersion) *coursewareVersionRow {
	row := &coursewareVersionRow{
		ID: v.VersionID, VersionID: v.VersionID, ProjectID: v.ProjectID, VersionNo: v.VersionNo,
		ParentVersionID: v.ParentVersionID, NodesJSON: v.NodesJSON, BeforeSnapshotJSON: v.BeforeSnapshotJSON,
		PresentationJSON: v.PresentationJSON, SnapshotJSON: v.SnapshotJSON,
		ModifyInstr: v.ModifyInstr, VersionSummary: v.VersionSummary, CreatedAt: v.CreatedAt,
		GenerationID: v.GenerationID, PageID: v.PageID,
	}
	if len(v.EvidenceRefs) > 0 {
		if b, err := json.Marshal(v.EvidenceRefs); err == nil {
			row.EvidenceRefs = string(b)
		}
	}
	if len(v.CitationRefs) > 0 {
		if b, err := json.Marshal(v.CitationRefs); err == nil {
			row.CitationRefs = string(b)
		}
	}
	if len(v.EvidenceUsed) > 0 {
		if b, err := json.Marshal(v.EvidenceUsed); err == nil {
			row.EvidenceUsed = string(b)
		}
	}
	return row
}

// rowToVersion 把 gorm 行提升到内存模型；带 JSON 解码的证据字段。
// 字段为空字符串时返回空切片（而不是 nil），便于前端判断。
func rowToVersion(r coursewareVersionRow) *CoursewareVersion {
	v := &CoursewareVersion{
		VersionID: r.VersionID, ProjectID: r.ProjectID, VersionNo: r.VersionNo,
		ParentVersionID: r.ParentVersionID, NodesJSON: r.NodesJSON, BeforeSnapshotJSON: r.BeforeSnapshotJSON,
		PresentationJSON: r.PresentationJSON, SnapshotJSON: r.SnapshotJSON,
		ModifyInstr: r.ModifyInstr, VersionSummary: r.VersionSummary, CreatedAt: r.CreatedAt,
		GenerationID: r.GenerationID, PageID: r.PageID,
	}
	if r.EvidenceRefs != "" {
		_ = json.Unmarshal([]byte(r.EvidenceRefs), &v.EvidenceRefs)
	}
	if v.EvidenceRefs == nil {
		v.EvidenceRefs = []string{}
	}
	if r.CitationRefs != "" {
		_ = json.Unmarshal([]byte(r.CitationRefs), &v.CitationRefs)
	}
	if v.CitationRefs == nil {
		v.CitationRefs = []string{}
	}
	if r.EvidenceUsed != "" {
		_ = json.Unmarshal([]byte(r.EvidenceUsed), &v.EvidenceUsed)
	}
	if v.EvidenceUsed == nil {
		v.EvidenceUsed = []string{}
	}
	return v
}

// ---- 草稿（A2 最小内联：draft_json 存于 projects 表的扩展列）----
// A2 的独立接口在原分配中属 A；这里内联最小实现供 A6 modify 后更新草稿。
type coursewareDraftRow struct {
	ProjectID string    `gorm:"column:project_id;size:64;primaryKey"`
	DraftJSON string    `gorm:"column:draft_json;type:text"`
	UpdatedAt time.Time `gorm:"column:updated_at"`
}

func (coursewareDraftRow) TableName() string { return "courseware_drafts" }

// PageEvidenceBinding —— 页面级证据绑定（契约 v1.0 §4.1 PageEvidenceBinding）。
// 一个课件项目内每页一行，记录该页局部修改时可引用的证据 chunk 列表。
type PageEvidenceBinding struct {
	PageID       string    `json:"page_id"`
	EvidenceRefs []string  `json:"evidence_refs"`
	AutoBound    bool      `json:"auto_bound"`
	BoundBy      string    `json:"bound_by"` // "system:intent_keyword" | "user:<teacher_id>"
	BoundAt      time.Time `json:"bound_at"`
}

// coursewarePageBindingRow —— gorm 表映射（courseware_page_bindings）。
// 复合主键 (project_id, page_id)：绑定是当前项目的活动状态，按项目+页存最新一份。
type coursewarePageBindingRow struct {
	ProjectID    string    `gorm:"column:project_id;size:64;primaryKey"`
	PageID       string    `gorm:"column:page_id;size:64;primaryKey"`
	EvidenceRefs string    `gorm:"column:evidence_refs;type:text"` // JSON 字符串：["chunk_001", ...]
	AutoBound    bool      `gorm:"column:auto_bound"`
	BoundBy      string    `gorm:"column:bound_by;size:120"`
	BoundAt      time.Time `gorm:"column:bound_at"`
	UpdatedAt    time.Time `gorm:"column:updated_at"`
}

func (coursewarePageBindingRow) TableName() string { return "courseware_page_bindings" }

// =============================================================================
// ModifyIntent —— B5 解析结果（与 Python /api/v1/ai/parse_modify 响应对齐）
// =============================================================================

type ModifyIntent struct {
	TargetType            string            `json:"target_type"` // node | page | global | style
	TargetIDs             []string          `json:"target_ids"`
	TargetElementIDs      []string          `json:"target_element_ids"`
	Action                string            `json:"action"` // simplify|expand|delete|add|reorder|restyle|rewrite
	SecondaryActions      []string          `json:"secondary_actions"`
	Constraints           []string          `json:"constraints"`
	Confidence            float64           `json:"confidence"`
	ClarificationNeeded   bool              `json:"clarification_needed"`
	ClarificationQuestion string            `json:"clarification_question"`
	RiskLevel             string            `json:"risk_level"`
	ConfirmationRequired  bool              `json:"confirmation_required"`
	Candidates            []map[string]any  `json:"candidates,omitempty"`
	Presentation          map[string]string `json:"presentation"`
}

// ParseModifyRequest / Response —— Go→Python 调用 DTO。
type ParseModifyRequest struct {
	ProjectID   string             `json:"project_id"`
	Instruction string             `json:"instruction"`
	Nodes       []TeachingNodeItem `json:"nodes"`
	// ActiveNodeID 是教师界面上当前选中的页面。老师说「这页」时靠它定位，
	// 不让模型从标题里猜；为空表示未选中，行为与加这个字段之前一致。
	ActiveNodeID string `json:"active_node_id,omitempty"`
}

type ParseModifyResponse struct {
	Intent ModifyIntent `json:"data"`
}

// =============================================================================
// CoursewareService —— 门面
// =============================================================================

// modifyClient —— CoursewareService 实际依赖的 AI 能力窄接口。
// 只调用意图解析、局部内容生成与内容状态查询三个端点；窄接口便于测试注入桩。
//
// ContentStatus 不是可选项：/gen/content 是异步任务，GenerateContent 返回时
// nodes 恒为空，结果只能靠轮询取回（见 waitContentResult）。
type modifyClient interface {
	ParseModify(ctx context.Context, req ParseModifyRequest) (*ModifyIntent, error)
	GenerateContent(ctx context.Context, req GenContentRequest) (*GenContentStatusResponse, error)
	ContentStatus(ctx context.Context, contentID string) (*GenContentStatusResponse, error)
}

type CoursewareService struct {
	aiClient modifyClient
	store    coursewareStore
}

// coursewareStore —— 持久化抽象（mem 降级 + gorm）。
type coursewareStore interface {
	CreateProject(ctx context.Context, p *CoursewareProject) error
	GetProject(ctx context.Context, projectID string) (*CoursewareProject, error)
	GetProjectByGenID(ctx context.Context, genID string) (*CoursewareProject, error)
	ListProjects(ctx context.Context, ownerID string) ([]*CoursewareProject, error)
	DeleteProject(ctx context.Context, projectID string) error
	UpdateProjectStep(ctx context.Context, projectID, step string) error
	UpdateProjectGenID(ctx context.Context, projectID, genID string) error
	UpdateProjectStatus(ctx context.Context, projectID, status string) error

	SaveDraft(ctx context.Context, projectID, draftJSON string) error
	GetDraft(ctx context.Context, projectID string) (string, error)

	NextVersionNo(ctx context.Context, projectID string) (int, error)
	SaveVersion(ctx context.Context, v *CoursewareVersion) error
	GetVersion(ctx context.Context, projectID string, versionNo int) (*CoursewareVersion, error)
	GetVersionByID(ctx context.Context, projectID, versionID string) (*CoursewareVersion, error)
	ListVersions(ctx context.Context, projectID string) ([]*CoursewareVersion, error)

	SetPageBindings(ctx context.Context, projectID string, bindings []PageEvidenceBinding) ([]string, error)
	GetPageBindings(ctx context.Context, projectID string) (map[string]PageEvidenceBinding, error)
}

// CoursewareVersionSnapshot 是模块3的完整版本边界，显式保留页面证据绑定。
type CoursewareVersionSnapshot struct {
	Nodes        []TeachingNodeItem `json:"nodes"`
	Presentation map[string]string  `json:"presentation,omitempty"`
	PageBindings interface{}        `json:"page_bindings,omitempty"`
}

// ContractVersionSnapshot is the public v1 version snapshot shape. The
// internal nodes/presentation representation remains supported while callers
// migrate to this canonical contract.
type ContractVersionSnapshot struct {
	Outline      interface{} `json:"outline"`
	Content      interface{} `json:"content"`
	PageBindings interface{} `json:"page_bindings"`
	Style        interface{} `json:"style"`
}

func NewCoursewareService(aiClient modifyClient) *CoursewareService {
	return &CoursewareService{aiClient: aiClient, store: newMemCoursewareStore()}
}

func NewCoursewareServiceWithDB(aiClient modifyClient, db *gorm.DB) *CoursewareService {
	return &CoursewareService{aiClient: aiClient, store: newGormCoursewareStore(db)}
}

// AutoMigrateCourseware 注册课件项目/版本/草稿/页面绑定表迁移。
//
// courseware_projects 是遗留表：主键建在 id 上，而本模块的主键是 project_id。
// gorm 无法在同一张表上迁移主键（SQLSTATE 42P16），且这次 AutoMigrate 一旦报错
// 就整体中断——连带 courseware_versions / courseware_drafts / courseware_page_bindings
// 都不会被创建，模块1 的"绑定刷新后仍在"和模块2/3 的版本持久化在真实库里全部失效。
// 因此子表单独迁移，遗留表降级为只补齐缺失列。
func AutoMigrateCourseware(db *gorm.DB) error {
	// courseware_projects is owned by CoursewareProjectService and its existing
	// schema uses a UUID id primary key. Do not let the legacy A6/A7 row model
	// rewrite that table; only create the version/draft/binding tables here.
	// coursewarePageBindingRow is added by 模块 1（契约 v1.0 页面级资料绑定）。
	return db.AutoMigrate(&coursewareVersionRow{}, &coursewareDraftRow{}, &coursewarePageBindingRow{})
}

// ---- A1 最小基础 ----

// CreateProject 新建课件项目。
func (s *CoursewareService) CreateProject(ctx context.Context, ownerID, title string) (*CoursewareProject, error) {
	if strings.TrimSpace(ownerID) == "" {
		return nil, fmt.Errorf("owner_id 不能为空")
	}
	p := &CoursewareProject{
		ProjectID:   "proj_" + uuid.NewString()[:12],
		OwnerID:     ownerID,
		Title:       title,
		CurrentStep: "s1_intent",
		Status:      "draft",
		CreatedAt:   time.Now(),
		UpdatedAt:   time.Now(),
	}
	if err := s.store.CreateProject(ctx, p); err != nil {
		return nil, err
	}
	return p, nil
}

// GetProject 读取项目。
func (s *CoursewareService) GetProject(ctx context.Context, projectID string) (*CoursewareProject, error) {
	return s.store.GetProject(ctx, projectID)
}

// ListProjects 我的课件列表。
func (s *CoursewareService) ListProjects(ctx context.Context, ownerID string) ([]*CoursewareProject, error) {
	return s.store.ListProjects(ctx, ownerID)
}

// DeleteProject 删除项目及其草稿、版本快照。
func (s *CoursewareService) DeleteProject(ctx context.Context, projectID string) error {
	return s.store.DeleteProject(ctx, projectID)
}

// UpdateStep 持久化当前步骤。
func (s *CoursewareService) UpdateStep(ctx context.Context, projectID, step string) error {
	switch step {
	case "s1_intent", "s2_material", "s3_studio", "s4_version":
	default:
		return fmt.Errorf("非法 step: %s", step)
	}
	return s.store.UpdateProjectStep(ctx, projectID, step)
}

// ---- A2 最小草稿 ----

// SaveDraft 保存草稿 JSON。
func (s *CoursewareService) SaveDraft(ctx context.Context, projectID, draftJSON string) error {
	if _, err := s.store.GetProject(ctx, projectID); err != nil {
		return err
	}
	return s.store.SaveDraft(ctx, projectID, draftJSON)
}

// GetDraft 读取草稿 JSON。
func (s *CoursewareService) GetDraft(ctx context.Context, projectID string) (string, error) {
	return s.store.GetDraft(ctx, projectID)
}

// ElementSnapshot returns the normalized element layer from the current
// project draft. It is the read seam used by the candidate-confirmation UI.
func (s *CoursewareService) ElementSnapshot(ctx context.Context, projectID string) ([]map[string]any, error) {
	raw, err := s.store.GetDraft(ctx, projectID)
	if err != nil {
		return nil, err
	}
	var envelope map[string]any
	if json.Unmarshal([]byte(raw), &envelope) != nil {
		return []map[string]any{}, nil
	}
	content := envelope["generation"]
	if content == nil {
		content = envelope["content"]
	}
	contentMap, _ := content.(map[string]any)
	var rawNodes any = contentMap["nodes"]
	if rawNodes == nil {
		rawNodes = envelope["nodes"]
	}
	nodesJSON, _ := json.Marshal(rawNodes)
	var nodes []TeachingNodeItem
	if json.Unmarshal(nodesJSON, &nodes) != nil {
		return []map[string]any{}, nil
	}
	nodes = ensureElementMetadata(nodes)
	result := make([]map[string]any, 0)
	for _, node := range nodes {
		if elements, ok := node.Metadata["elements"].([]map[string]any); ok {
			result = append(result, elements...)
		}
	}
	return result, nil
}

// SavePageBindings 保存页面级证据绑定（upsert 语义：只更新传入的页面，其余页面保持不变）。
// 返回实际被写入的 page_id 列表。项目不存在返回 ErrProjectNotFound。
func (s *CoursewareService) SavePageBindings(ctx context.Context, projectID string, bindings []PageEvidenceBinding) ([]string, error) {
	if _, err := s.store.GetProject(ctx, projectID); err != nil {
		return nil, err
	}
	updated := make([]string, 0, len(bindings))
	if len(bindings) == 0 {
		return updated, nil
	}
	for i := range bindings {
		b := &bindings[i]
		if strings.TrimSpace(b.PageID) == "" {
			return nil, fmt.Errorf("page_id 不能为空")
		}
		// 契约示例里 page_id 由 map key 给出，请求体内的 page_id 可省略——以 key 为准。
		if b.EvidenceRefs == nil {
			b.EvidenceRefs = []string{}
		}
		if b.BoundBy == "" {
			b.BoundBy = "user:unknown"
		}
		if b.BoundAt.IsZero() {
			b.BoundAt = time.Now().UTC()
		}
		updated = append(updated, b.PageID)
	}
	if _, err := s.store.SetPageBindings(ctx, projectID, bindings); err != nil {
		return nil, err
	}
	return updated, nil
}

// GetPageBindings 读取项目当前的页面级证据绑定，key 为 page_id。
// 项目不存在返回 ErrProjectNotFound；无绑定时返回空 map（非 nil），便于前端直接消费。
func (s *CoursewareService) GetPageBindings(ctx context.Context, projectID string) (map[string]PageEvidenceBinding, error) {
	if _, err := s.store.GetProject(ctx, projectID); err != nil {
		return nil, err
	}
	return s.store.GetPageBindings(ctx, projectID)
}

// targetEvidenceRefs 收集目标页在页面级绑定里的证据 chunk_id（契约 v1.0 模块1）。
//
// 绑定以 page_id 为 key，而 S3 的页面即节点（page_001 ↔ node_001），
// 因此直接按 target id 取。未绑定的目标返回 nil。
// 绑定表读不到时同样返回 nil —— 证据是增强项，不该让局部修改整体失败。
func (s *CoursewareService) targetEvidenceRefs(ctx context.Context, projectID string, targetIDs []string) []string {
	if len(targetIDs) == 0 {
		return nil
	}
	bindings, err := s.store.GetPageBindings(ctx, projectID)
	if err != nil {
		return nil
	}
	var refs []string
	seen := make(map[string]bool, len(targetIDs))
	for _, id := range targetIDs {
		binding, ok := bindings[id]
		if !ok {
			continue
		}
		for _, ref := range binding.EvidenceRefs {
			if ref == "" || seen[ref] {
				continue
			}
			seen[ref] = true
			refs = append(refs, ref)
		}
	}
	return refs
}

// ---- A6: 修改编排 + 版本快照 ----

// ModifyResult —— modify 响应。
type ModifyResult struct {
	ModifiedNodes        []TeachingNodeItem `json:"modified_nodes"`
	AllNodes             []TeachingNodeItem `json:"all_nodes"`
	Intent               ModifyIntent       `json:"intent"`
	PreviousVersionID    string             `json:"previous_version_id"`
	PreviousVersionNo    int                `json:"previous_version_no"`
	NewVersionNo         int                `json:"new_version_no"`
	Clarification        string             `json:"clarification,omitempty"`
	Presentation         map[string]string  `json:"presentation,omitempty"`
	ModifiedElementIDs   []string           `json:"modified_element_ids,omitempty"`
	RequiresConfirmation bool               `json:"requires_confirmation,omitempty"`
	RiskLevel            string             `json:"risk_level,omitempty"`
	Candidates           []map[string]any   `json:"candidates,omitempty"`
}

// Modify 修改编排：解析意图 → （低置信度则追问）→ 局部生成 → 更新草稿 → 版本快照。
func (s *CoursewareService) Modify(ctx context.Context, projectID, instruction string, nodes []TeachingNodeItem) (*ModifyResult, error) {
	return s.ModifyWithOptions(ctx, projectID, instruction, nodes, false)
}

// ModifyWithOptions adds the explicit confirmation boundary required for
// destructive, media, structural, and batch element operations.
func (s *CoursewareService) ModifyWithOptions(ctx context.Context, projectID, instruction string, nodes []TeachingNodeItem, confirmed bool) (*ModifyResult, error) {
	project, err := s.store.GetProject(ctx, projectID)
	if err != nil {
		return nil, err
	}
	if strings.TrimSpace(instruction) == "" {
		return nil, fmt.Errorf("instruction 不能为空")
	}

	nodes = ensureElementMetadata(nodes)

	// 1) B5: 解析意图
	intentPtr, err := s.aiClient.ParseModify(ctx, ParseModifyRequest{
		ProjectID:    projectID,
		Instruction:  instruction,
		Nodes:        nodes,
		ActiveNodeID: activeNodeID,
	})
	if err != nil {
		return nil, fmt.Errorf("意图解析失败: %w", err)
	}
	intent := *intentPtr

	// 2) 低置信度 → 返回追问，不执行修改
	if intent.ClarificationNeeded {
		q := intent.ClarificationQuestion
		if q == "" {
			q = "能否更具体地描述修改目标（例如“第三页减少文字”）？"
		}
		return &ModifyResult{
			ModifiedNodes: nil,
			AllNodes:      nodes,
			Intent:        intent,
			Clarification: q,
			Candidates:    intent.Candidates,
		}, nil
	}
	if intent.ConfirmationRequired && !confirmed {
		return &ModifyResult{
			AllNodes:             nodes,
			Intent:               intent,
			RequiresConfirmation: true,
			RiskLevel:            intent.RiskLevel,
			Candidates:           intent.Candidates,
		}, nil
	}

	// 3) 结构类动作（delete/add/reorder）在 Go 侧直接操作节点列表，不调 Python
	updatedNodes, modifiedIDs, err := s.applyStructuralAction(intent, nodes)
	if err != nil {
		return nil, err
	}

	// 4) 内容类动作（simplify/expand/rewrite）→ B6 局部重生成
	switch intent.Action {
	case "simplify", "expand", "rewrite":
		// CourseName 与 EvidenceRefs 都必须显式带上：Python 侧靠它们决定
		// 「基于哪份材料改」。此前只传 nodes，局部修改等于凭空重写，
		// 与 S3 大纲/内容生成走 RAG 的行为不一致。
		resp, err := s.aiClient.GenerateContent(ctx, GenContentRequest{
			Nodes:             updatedNodes,
			Mode:              "partial",
			CourseName:        project.Title,
			TargetNodeIDs:     intent.TargetIDs,
			ModifyAction:      intent.Action,
			ModifyConstraints: intent.Constraints,
			EvidenceRefs:      s.targetEvidenceRefs(ctx, projectID, intent.TargetIDs),
		})
		if err != nil {
			return nil, fmt.Errorf("局部重生成失败: %w", err)
		}
		resp, err = s.waitForPartialContent(ctx, resp)
		if err != nil {
			return nil, fmt.Errorf("局部重生成失败: %w", err)
		}
		updatedNodes = mergePartialResult(updatedNodes, resp.Nodes, intent.TargetIDs)
		if intent.Action == "expand" && !hasVisibleTargetChange(nodes, updatedNodes, intent.TargetIDs) {
			return nil, fmt.Errorf("AI 引擎没有生成可见的课件内容，请重试或明确指定要添加的内容")
		}
		modifiedIDs = intent.TargetIDs
	}
	if wantsRemoveTeachingText(instruction, intent.Constraints) {
		updatedNodes = clearTeachingText(updatedNodes, intent.TargetIDs)
	}
	if intent.Action == "restyle" {
		updatedNodes = applyPresentationToNodes(updatedNodes, intent.Presentation)
	}
	updatedNodes = ensureElementMetadata(updatedNodes)
	updatedNodes = syncElementContent(updatedNodes)
	// restyle：仅样式层，不改内容；样式字段由 AI 解析后透传给前端。

	// 5) 保存修改前后完整快照。NodesJSON/SnapshotJSON 表示新版本内容；
	// BeforeSnapshotJSON 保留修改前状态，供撤销、审计和差异展示使用。
	prevNo, err := s.store.NextVersionNo(ctx, projectID)
	if err != nil {
		return nil, err
	}
	beforeNodesJSON, _ := json.Marshal(nodes)
	afterNodesJSON, _ := json.Marshal(updatedNodes)
	snap := &CoursewareVersion{
		VersionID:          "ver_" + uuid.NewString()[:12],
		ProjectID:          projectID,
		VersionNo:          prevNo,
		NodesJSON:          string(afterNodesJSON),
		BeforeSnapshotJSON: string(beforeNodesJSON),
		PresentationJSON:   presentationJSON(presentationFromNodes(updatedNodes)),
		SnapshotJSON:       snapshotJSON(updatedNodes, presentationFromNodes(updatedNodes), nil),
		ModifyInstr:        instruction,
		VersionSummary:     instruction,
		CreatedAt:          time.Now(),
	}
	if err := s.store.SaveVersion(ctx, snap); err != nil {
		return nil, err
	}

	// 6) 更新草稿。保留项目草稿的其它上下文，只替换 generation.nodes；
	// 直接把节点数组写入 draft 会导致 S3 刷新时无法恢复生成内容、意图和呈现配置。
	_ = s.saveGenerationDraft(ctx, projectID, updatedNodes)
	_ = s.store.UpdateProjectStatus(ctx, projectID, "done")

	var modifiedNodes []TeachingNodeItem
	for _, n := range updatedNodes {
		for _, id := range modifiedIDs {
			if n.NodeID == id {
				modifiedNodes = append(modifiedNodes, n)
			}
		}
	}

	return &ModifyResult{
		ModifiedNodes:      modifiedNodes,
		AllNodes:           updatedNodes,
		Intent:             intent,
		PreviousVersionID:  snap.VersionID,
		PreviousVersionNo:  snap.VersionNo,
		NewVersionNo:       snap.VersionNo, // 快照即新版本号
		Presentation:       intent.Presentation,
		ModifiedElementIDs: append([]string(nil), intent.TargetElementIDs...),
		RiskLevel:          intent.RiskLevel,
	}, nil
}

func hasVisibleTargetChange(before, after []TeachingNodeItem, targetIDs []string) bool {
	targets := make(map[string]bool, len(targetIDs))
	for _, id := range targetIDs {
		targets[id] = true
	}
	old := make(map[string]TeachingNodeItem, len(before))
	for _, node := range before {
		old[node.NodeID] = node
	}
	for _, node := range after {
		if !targets[node.NodeID] {
			continue
		}
		previous, ok := old[node.NodeID]
		if !ok || node.Title != previous.Title || node.Content != previous.Content || node.Summary != previous.Summary ||
			!reflect.DeepEqual(node.KeyPoints, previous.KeyPoints) || !reflect.DeepEqual(node.PointDetails, previous.PointDetails) ||
			!reflect.DeepEqual(node.Questions, previous.Questions) {
			return true
		}
	}
	return false
}

func (s *CoursewareService) waitForPartialContent(ctx context.Context, resp *GenContentStatusResponse) (*GenContentStatusResponse, error) {
	if resp == nil {
		return nil, fmt.Errorf("AI 引擎未返回内容生成任务")
	}
	ctx, cancel := context.WithTimeout(ctx, 3*time.Minute)
	defer cancel()
	for {
		switch resp.Status {
		case "done":
			if len(resp.Nodes) == 0 {
				return nil, fmt.Errorf("AI 引擎完成任务但未返回修改节点")
			}
			return resp, nil
		case "failed":
			return nil, fmt.Errorf("AI 引擎内容生成失败: %s", resp.Error)
		case "generating", "pending", "processing":
			if resp.ContentID == "" {
				return nil, fmt.Errorf("AI 引擎未返回内容生成任务 ID")
			}
		case "":
			return nil, fmt.Errorf("AI 引擎未返回内容生成状态")
		default:
			return nil, fmt.Errorf("AI 引擎返回未知内容生成状态: %s", resp.Status)
		}
		select {
		case <-ctx.Done():
			return nil, fmt.Errorf("等待 AI 引擎内容生成超时: %w", ctx.Err())
		case <-time.After(300 * time.Millisecond):
		}
		var err error
		resp, err = s.aiClient.ContentStatus(ctx, resp.ContentID)
		if err != nil {
			return nil, err
		}
		if resp == nil {
			return nil, fmt.Errorf("AI 引擎未返回内容生成状态")
		}
	}
}

func wantsRemoveTeachingText(instruction string, constraints []string) bool {
	text := strings.ToLower(strings.Join(append([]string{instruction}, constraints...), " "))
	for _, phrase := range []string{
		"去掉讲授文本", "删除讲授文本", "移除讲授文本", "不要讲授文本", "隐藏讲授文本",
		"去除讲稿", "删除讲稿", "移除讲稿", "不要讲稿", "隐藏讲稿",
	} {
		if strings.Contains(text, phrase) {
			return true
		}
	}
	return false
}

func clearTeachingText(nodes []TeachingNodeItem, targetIDs []string) []TeachingNodeItem {
	targetSet := make(map[string]struct{}, len(targetIDs))
	for _, id := range targetIDs {
		targetSet[id] = struct{}{}
	}
	cleared := make([]TeachingNodeItem, len(nodes))
	copy(cleared, nodes)
	for i := range cleared {
		if len(targetSet) == 0 {
			cleared[i].Script = ""
			cleared[i].Segments = nil
			continue
		}
		if _, ok := targetSet[cleared[i].NodeID]; ok {
			cleared[i].Script = ""
			cleared[i].Segments = nil
		}
	}
	return cleared
}

func (s *CoursewareService) saveGenerationDraft(ctx context.Context, projectID string, nodes []TeachingNodeItem) error {
	draft := map[string]interface{}{}
	if raw, err := s.store.GetDraft(ctx, projectID); err == nil && strings.TrimSpace(raw) != "" {
		var existing map[string]interface{}
		if json.Unmarshal([]byte(raw), &existing) == nil && existing != nil {
			draft = existing
		}
	}

	generation := map[string]interface{}{}
	if existing, ok := draft["generation"].(map[string]interface{}); ok {
		generation = existing
	}
	generation["nodes"] = nodes
	draft["generation"] = generation

	encoded, err := json.Marshal(draft)
	if err != nil {
		return err
	}
	return s.store.SaveDraft(ctx, projectID, string(encoded))
}

func presentationJSON(p map[string]string) string {
	if len(p) == 0 {
		return "{}"
	}
	raw, err := json.Marshal(p)
	if err != nil {
		return "{}"
	}
	return string(raw)
}

func snapshotJSON(nodes []TeachingNodeItem, presentation map[string]string, pageBindings interface{}) string {
	raw, err := json.Marshal(CoursewareVersionSnapshot{Nodes: nodes, Presentation: presentation, PageBindings: pageBindings})
	if err != nil {
		return "{}"
	}
	return string(raw)
}

func presentationFromNodes(nodes []TeachingNodeItem) map[string]string {
	if len(nodes) == 0 || nodes[0].Metadata == nil {
		return map[string]string{}
	}
	raw, ok := nodes[0].Metadata["presentation"].(map[string]interface{})
	if !ok {
		if typed, ok := nodes[0].Metadata["presentation"].(map[string]string); ok {
			return typed
		}
		return map[string]string{}
	}
	out := make(map[string]string, len(raw))
	for key, value := range raw {
		if text, ok := value.(string); ok {
			out[key] = text
		}
	}
	return out
}

// applyStructuralAction —— delete/add/reorder 的节点列表操作（Go 侧本地执行）。
func (s *CoursewareService) applyStructuralAction(intent ModifyIntent, nodes []TeachingNodeItem) ([]TeachingNodeItem, []string, error) {
	switch intent.Action {
	case "delete":
		targetSet := make(map[string]bool, len(intent.TargetIDs))
		for _, id := range intent.TargetIDs {
			targetSet[id] = true
		}
		out := make([]TeachingNodeItem, 0, len(nodes))
		for _, n := range nodes {
			if !targetSet[n.NodeID] {
				out = append(out, n)
			}
		}
		return renumberNodes(out), intent.TargetIDs, nil

	case "reorder":
		if len(intent.TargetIDs) < 2 {
			return nodes, nil, nil
		}
		a, b := intent.TargetIDs[0], intent.TargetIDs[1]
		idxA, idxB := -1, -1
		for i, n := range nodes {
			if n.NodeID == a {
				idxA = i
			}
			if n.NodeID == b {
				idxB = i
			}
		}
		if idxA < 0 || idxB < 0 {
			return nodes, nil, nil
		}
		nodes[idxA], nodes[idxB] = nodes[idxB], nodes[idxA]
		return renumberNodes(nodes), intent.TargetIDs, nil

	default:
		// add：无目标内容可生成，退化为在末尾追加占位节点由教师编辑；
		// 内容类与样式类不在本函数处理。
		return nodes, nil, nil
	}
}

// renumberNodes 按列表顺序重建 Next/Prev 链（TeachingNodeItem 用链表表达顺序，无 Order 字段）。
func renumberNodes(nodes []TeachingNodeItem) []TeachingNodeItem {
	for i := range nodes {
		if i < len(nodes)-1 {
			nodes[i].NextNodeID = nodes[i+1].NodeID
		} else {
			nodes[i].NextNodeID = ""
		}
		if i > 0 {
			nodes[i].PrevNodeID = nodes[i-1].NodeID
		} else {
			nodes[i].PrevNodeID = ""
		}
	}
	return nodes
}

// ---- 局部内容生成的轮询参数 ----
//
// 用 var 而非 const：测试里要能把它们调小，否则一个用例要真等 90 秒。
var (
	contentPollInterval = 500 * time.Millisecond
	// 90s 是刻意留出的余量：前端的 MODIFY_LLM_TIMEOUT_MS 是 120s，
	// 前面还有一次 parse_modify 的往返与落快照的开销。宁可我们这边先超时、
	// 给出一句能看懂的错，也不要让 axios 直接 abort 成一句无头无尾的网络错误。
	contentPollBudget = 90 * time.Second
)

// waitContentResult 等待 /gen/content 的**异步任务**跑完并取回节点。
//
// 这是「局部修改从接入起就没真正生效过」的根因所在：/gen/content 起一个后台线程
// 就立刻返回（main.py 的 generate_content），首个响应里的 nodes **恒为空**。
// 调用方若直接把 resp.Nodes 交给 mergePartialResult，而后者开头就是
// `if len(partial) == 0 { return base }` —— 于是原样返回旧节点，可 modifiedIDs
// 照样被填成 target_ids，上层便报「已更新」，而返回给前端的内容一个字节都没变，
// 预览渲染出来自然一模一样。ContentStatus 这个轮询接口一直都在，
// 但此前只有 S3 讲稿进度页在用，修改路径从来没调用过。
//
// 失败一律返回 error 而不是静默退回旧节点：报「已更新」却什么都没改，
// 比直接报错更难排查。
func (s *CoursewareService) waitContentResult(
	ctx context.Context, first *GenContentStatusResponse,
) ([]TeachingNodeItem, error) {
	if first == nil {
		return nil, fmt.Errorf("局部重生成失败: 引擎未返回任务信息")
	}
	// 引擎若哪天改成同步返回，这里直接放行，不必再改一遍。
	if len(first.Nodes) > 0 {
		return first.Nodes, nil
	}
	if first.ContentID == "" {
		return nil, fmt.Errorf("局部重生成失败: 引擎未返回 content_id，无法取回结果")
	}

	deadline := time.Now().Add(contentPollBudget)
	ticker := time.NewTicker(contentPollInterval)
	defer ticker.Stop()

	// 最后一次查询的错误要留着 —— 全是网络错误时，那句错比「超时」有用得多。
	var lastErr error
	for {
		select {
		case <-ctx.Done():
			return nil, fmt.Errorf("局部重生成已取消: %w", ctx.Err())
		case <-ticker.C:
		}

		if time.Now().After(deadline) {
			if lastErr != nil {
				return nil, fmt.Errorf("局部重生成超时（状态查询持续失败）: %w", lastErr)
			}
			return nil, fmt.Errorf(
				"局部重生成超时（%s 内未完成），请稍后在版本管理中查看任务结果", contentPollBudget,
			)
		}

		status, err := s.aiClient.ContentStatus(ctx, first.ContentID)
		if err != nil {
			// 单次查询失败不当场放弃：任务在引擎侧照跑，抖动过去还能拿到结果。
			lastErr = err
			continue
		}
		lastErr = nil

		if len(status.Nodes) > 0 {
			return status.Nodes, nil
		}

		switch strings.ToLower(strings.TrimSpace(status.Status)) {
		case "done", "completed", "success":
			// 任务自称完成却没有节点 —— 引擎侧出了问题，别拿旧内容糊弄过去。
			if status.Error != "" {
				return nil, fmt.Errorf("局部重生成失败: %s", status.Error)
			}
			return nil, fmt.Errorf("局部重生成失败: 任务已完成但未返回任何节点")
		case "failed", "error":
			if status.Error != "" {
				return nil, fmt.Errorf("局部重生成失败: %s", status.Error)
			}
			return nil, fmt.Errorf("局部重生成失败: 引擎返回状态 %s", status.Status)
		}
		// pending / generating / 其它：继续等。
	}
}

// mergePartialResult —— B6 异步任务完成前可能只有部分节点；以局部结果覆盖目标节点。
func mergePartialResult(base []TeachingNodeItem, partial []TeachingNodeItem, targetIDs []string) []TeachingNodeItem {
	if len(partial) == 0 {
		return base
	}
	targetSet := make(map[string]bool, len(targetIDs))
	for _, id := range targetIDs {
		targetSet[id] = true
	}
	partialMap := make(map[string]TeachingNodeItem, len(partial))
	for _, n := range partial {
		partialMap[n.NodeID] = n
	}
	out := make([]TeachingNodeItem, 0, len(base))
	for _, n := range base {
		if targetSet[n.NodeID] {
			if pn, ok := partialMap[n.NodeID]; ok {
				out = append(out, pn)
				continue
			}
		}
		out = append(out, n)
	}
	return out
}

// ModifyHistory 修改记录列表。
func (s *CoursewareService) ModifyHistory(ctx context.Context, projectID string) ([]*CoursewareVersion, error) {
	return s.store.ListVersions(ctx, projectID)
}

// LookupProjectByGenID 按 generation_id 反查所属的 courseware 项目。
// 用于 genHandler.Modify 在调用 AI 后决定要不要落版本快照。
// 找不到时返回 (nil, ErrProjectNotFound)，调用方据此判断走透传还是落库。
func (s *CoursewareService) LookupProjectByGenID(ctx context.Context, genID string) (*CoursewareProject, error) {
	if s == nil || s.store == nil {
		return nil, ErrProjectNotFound
	}
	return s.store.GetProjectByGenID(ctx, genID)
}

// SetGenID 把 AI Engine 返回的 generation_id 绑到指定 project 上。
// genHandler.Modify 之后，AI Engine 后续的 GenerationStatus / GetPreview
// 都会按这个 gen_id 工作，本方法让 CoursewareProjectService 与 AI Engine
// 的会话边界对齐。
func (s *CoursewareService) SetGenID(ctx context.Context, projectID, genID string) error {
	if s == nil || s.store == nil {
		return ErrProjectNotFound
	}
	return s.store.UpdateProjectGenID(ctx, projectID, genID)
}

// RecordModifyResult —— 契约 v1.0 §1.1 接口 3 配套的落库动作。
//
// genHandler.Modify 收到 AI Engine 返回后调用本方法，把以下信息作为
// CoursewareVersion 快照持久化到 PostgreSQL：
//   - 请求侧：page_id / evidence_refs / user_instruction
//   - 响应侧：nodes（修改后） / version_number / citation_refs / evidence_used
//
// 同时，如果请求带 page_id + evidence_refs，会把它们回写到
// courseware_page_bindings（用户在前端提供的"这一页引用这些证据"的意图
// 即使 AI 没采纳也要落库，方便下次继续使用）。
//
// 设计为 fire-and-record：失败仅记录日志，不阻塞 AI 响应回前端；
// 因此方法本身返回 nil 吞掉错误，调用方继续走透传逻辑。
func (s *CoursewareService) RecordModifyResult(
	ctx context.Context,
	projectID string,
	req GenerationModifyRequest,
	resp GenerationModifyResponse,
) {
	if s == nil || s.store == nil {
		return
	}
	if projectID == "" {
		return
	}
	// 仅在 AI 明确说成功时落库；clarification / failed 不写历史。
	if resp.Status != "" && resp.Status != "ok" && resp.Status != "success" && resp.Status != "applied" {
		return
	}

	versionNo, err := s.store.NextVersionNo(ctx, projectID)
	if err != nil {
		return
	}
	nodesJSON, _ := json.Marshal(resp.Nodes)
	if len(nodesJSON) == 0 {
		nodesJSON = []byte("[]")
	}
	summary := strings.TrimSpace(req.UserInstruction)
	if summary == "" {
		summary = "AI 修改 v" + strconv.Itoa(resp.VersionNumber)
	}

	snap := &CoursewareVersion{
		VersionID:      "ver_" + uuid.NewString()[:12],
		ProjectID:      projectID,
		VersionNo:      versionNo,
		NodesJSON:      string(nodesJSON),
		ModifyInstr:    summary,
		VersionSummary: summary,
		CreatedAt:      time.Now(),
		GenerationID:   req.GenerationID,
		PageID:         strings.TrimSpace(req.PageID),
		EvidenceRefs:   append([]string{}, req.EvidenceRefs...),
		CitationRefs:   append([]string{}, resp.CitationRefs...),
		EvidenceUsed:   append([]string{}, resp.EvidenceUsed...),
	}
	_ = s.store.SaveVersion(ctx, snap)

	// 回写证据绑定：用户在前端"点了这一页绑这些证据"的意图要落库，
	// 即使 AI 这次没用上，下次 modify 仍能复用到这个项目+页。
	if strings.TrimSpace(req.PageID) != "" && len(req.EvidenceRefs) > 0 {
		_, _ = s.store.SetPageBindings(ctx, projectID, []PageEvidenceBinding{{
			PageID:       req.PageID,
			EvidenceRefs: append([]string{}, req.EvidenceRefs...),
			AutoBound:    false,
			BoundBy:      "user:modify_intent",
			BoundAt:      time.Now(),
		}})
	}
}

// LatestGenerationContext —— 给前端一个"权威读"端点的数据源。
// 返回：项目元数据 + 最新版本的节点 + 当前所有页绑定。
// 用于修复"切 PPT 不重置 AI 对话 / 左侧绑定打开就要可见"两类前端问题。
func (s *CoursewareService) LatestGenerationContext(ctx context.Context, projectID string) (*GenerationContext, error) {
	if s == nil || s.store == nil {
		return nil, ErrProjectNotFound
	}
	project, err := s.store.GetProject(ctx, projectID)
	if err != nil {
		return nil, err
	}
	versions, err := s.store.ListVersions(ctx, projectID)
	if err != nil {
		return nil, err
	}
	bindings, err := s.store.GetPageBindings(ctx, projectID)
	if err != nil {
		return nil, err
	}
	out := &GenerationContext{
		ProjectID: project.ProjectID,
		GenID:     project.GenID,
		Status:    project.Status,
		Step:      project.CurrentStep,
		UpdatedAt: project.UpdatedAt,
	}
	if len(versions) > 0 {
		latest := versions[len(versions)-1]
		out.LatestVersion = latest
		out.VersionNo = latest.VersionNo
		out.VersionID = latest.VersionID
		out.GenerationID = latest.GenerationID
		out.PageID = latest.PageID
		out.EvidenceRefs = latest.EvidenceRefs
		out.CitationRefs = latest.CitationRefs
		out.EvidenceUsed = latest.EvidenceUsed
	}
	if len(bindings) > 0 {
		out.PageBindings = make([]PageEvidenceBinding, 0, len(bindings))
		for _, b := range bindings {
			out.PageBindings = append(out.PageBindings, b)
		}
	}
	return out, nil
}

// GenerationContext —— 契约 v1.0 §3.2：latest generation 上下文响应。
// 给前端用于恢复预览、切项目重置 AI 对话、显示绑定关系。
type GenerationContext struct {
	ProjectID     string                `json:"project_id"`
	GenID         string                `json:"gen_id,omitempty"`
	Status        string                `json:"status,omitempty"`
	Step          string                `json:"current_step,omitempty"`
	UpdatedAt     time.Time             `json:"updated_at"`
	VersionID     string                `json:"version_id,omitempty"`
	VersionNo     int                   `json:"version_no,omitempty"`
	GenerationID  string                `json:"generation_id,omitempty"`
	PageID        string                `json:"page_id,omitempty"`
	EvidenceRefs  []string              `json:"evidence_refs,omitempty"`
	CitationRefs  []string              `json:"citation_refs,omitempty"`
	EvidenceUsed  []string              `json:"evidence_used,omitempty"`
	LatestVersion *CoursewareVersion    `json:"latest_version,omitempty"`
	PageBindings  []PageEvidenceBinding `json:"page_bindings,omitempty"`
}

// ---- A7: 回滚与审计 ----

// RollbackResult —— 回滚响应。
type RollbackResult struct {
	RestoredVersionNo int                `json:"restored_version_no"`
	NewVersionNo      int                `json:"new_version_no"`
	NewDraftVersionNo int                `json:"new_draft_version_no"`
	BaseVersionNo     int                `json:"base_version_no"`
	Nodes             []TeachingNodeItem `json:"nodes"`
	Presentation      map[string]string  `json:"presentation,omitempty"`
	PageBindings      interface{}        `json:"page_bindings,omitempty"`
}

// Rollback 克隆目标版本为新版本（不覆盖历史）。
func (s *CoursewareService) Rollback(ctx context.Context, projectID string, versionNo int) (*RollbackResult, error) {
	target, err := s.store.GetVersion(ctx, projectID, versionNo)
	if err != nil {
		return nil, err
	}
	return s.rollbackVersion(ctx, projectID, target)
}

// RollbackByID clones the selected historical version into a new editable
// version. The target version is never mutated.
func (s *CoursewareService) RollbackByID(ctx context.Context, projectID, versionID string) (*RollbackResult, error) {
	target, err := s.store.GetVersionByID(ctx, projectID, versionID)
	if err != nil {
		return nil, err
	}
	return s.rollbackVersion(ctx, projectID, target)
}

func (s *CoursewareService) rollbackVersion(ctx context.Context, projectID string, target *CoursewareVersion) (*RollbackResult, error) {
	// 克隆为新版本
	newNo, err := s.store.NextVersionNo(ctx, projectID)
	if err != nil {
		return nil, err
	}
	snap := &CoursewareVersion{
		VersionID:        "ver_" + uuid.NewString()[:12],
		ProjectID:        projectID,
		VersionNo:        newNo,
		ParentVersionID:  target.VersionID,
		NodesJSON:        target.NodesJSON, // 内容 = 目标版本
		PresentationJSON: target.PresentationJSON,
		SnapshotJSON:     target.SnapshotJSON,
		ModifyInstr:      fmt.Sprintf("回滚到 v%d", target.VersionNo),
		VersionSummary:   fmt.Sprintf("基于 v%d 分叉创建", target.VersionNo),
		CreatedAt:        time.Now(),
	}
	if err := s.store.SaveVersion(ctx, snap); err != nil {
		return nil, err
	}

	var nodes []TeachingNodeItem
	_ = json.Unmarshal([]byte(target.NodesJSON), &nodes)
	var restored CoursewareVersionSnapshot
	canonicalDraft := ""
	if target.SnapshotJSON != "" {
		_ = json.Unmarshal([]byte(target.SnapshotJSON), &restored)
		var canonical ContractVersionSnapshot
		if json.Unmarshal([]byte(target.SnapshotJSON), &canonical) == nil && canonical.Content != nil {
			contentRaw, _ := json.Marshal(canonical.Content)
			_ = json.Unmarshal(contentRaw, &restored.Nodes)
			restored.PageBindings = canonical.PageBindings
			if style, ok := canonical.Style.(map[string]interface{}); ok {
				restored.Presentation = make(map[string]string, len(style))
				for key, value := range style {
					if text, ok := value.(string); ok {
						restored.Presentation[key] = text
					}
				}
			}
			canonicalDraft = target.SnapshotJSON
		}
	}
	if len(restored.Nodes) == 0 {
		restored.Nodes = nodes
	}
	if len(restored.Presentation) == 0 && target.PresentationJSON != "" {
		_ = json.Unmarshal([]byte(target.PresentationJSON), &restored.Presentation)
	}

	// 更新草稿为完整回滚快照，避免页面证据绑定与样式在重新进入 S3 时丢失。
	restoredDraft := []byte(canonicalDraft)
	if len(restoredDraft) == 0 {
		restoredDraft, _ = json.Marshal(map[string]interface{}{
			"nodes":         restored.Nodes,
			"generation":    map[string]interface{}{"nodes": restored.Nodes},
			"presentation":  restored.Presentation,
			"page_bindings": restored.PageBindings,
		})
	}
	_ = s.store.SaveDraft(ctx, projectID, string(restoredDraft))

	return &RollbackResult{
		RestoredVersionNo: target.VersionNo,
		NewVersionNo:      newNo,
		NewDraftVersionNo: newNo,
		BaseVersionNo:     target.VersionNo,
		Nodes:             restored.Nodes,
		Presentation:      restored.Presentation,
		PageBindings:      restored.PageBindings,
	}, nil
}

// CreateVersionSnapshot 手动保存一个完整版本快照，用于 S3“保存新版本”。
func (s *CoursewareService) CreateVersionSnapshot(ctx context.Context, projectID, summary string, nodes []TeachingNodeItem, presentation map[string]string, pageBindings interface{}) (*CoursewareVersion, error) {
	if _, err := s.store.GetProject(ctx, projectID); err != nil {
		return nil, err
	}
	versionNo, err := s.store.NextVersionNo(ctx, projectID)
	if err != nil {
		return nil, err
	}
	if strings.TrimSpace(summary) == "" {
		summary = fmt.Sprintf("保存版本 v%d", versionNo)
	}
	nodesRaw, _ := json.Marshal(nodes)
	version := &CoursewareVersion{
		VersionID:        "ver_" + uuid.NewString()[:12],
		ProjectID:        projectID,
		VersionNo:        versionNo,
		NodesJSON:        string(nodesRaw),
		PresentationJSON: presentationJSON(presentation),
		SnapshotJSON:     snapshotJSON(nodes, presentation, pageBindings),
		ModifyInstr:      summary,
		VersionSummary:   summary,
		CreatedAt:        time.Now(),
	}
	if err := s.store.SaveVersion(ctx, version); err != nil {
		return nil, err
	}
	_ = s.store.SaveDraft(ctx, projectID, version.SnapshotJSON)
	return version, nil
}

// CreateVersionSnapshotJSON stores the canonical contract snapshot while
// keeping the legacy node/presentation columns populated for old readers.
func (s *CoursewareService) CreateVersionSnapshotJSON(ctx context.Context, projectID, changeNote string, snapshot ContractVersionSnapshot) (*CoursewareVersion, error) {
	if _, err := s.store.GetProject(ctx, projectID); err != nil {
		return nil, err
	}
	versionNo, err := s.store.NextVersionNo(ctx, projectID)
	if err != nil {
		return nil, err
	}
	raw, err := json.Marshal(snapshot)
	if err != nil {
		return nil, fmt.Errorf("版本快照序列化失败: %w", err)
	}
	var nodes []TeachingNodeItem
	contentRaw, _ := json.Marshal(snapshot.Content)
	_ = json.Unmarshal(contentRaw, &nodes)
	nodesRaw, _ := json.Marshal(nodes)
	var presentation map[string]string
	styleRaw, _ := json.Marshal(snapshot.Style)
	_ = json.Unmarshal(styleRaw, &presentation)
	version := &CoursewareVersion{
		VersionID:        "ver_" + uuid.NewString()[:12],
		ProjectID:        projectID,
		VersionNo:        versionNo,
		NodesJSON:        string(nodesRaw),
		PresentationJSON: presentationJSON(presentation),
		SnapshotJSON:     string(raw),
		ModifyInstr:      changeNote,
		VersionSummary:   changeNote,
		CreatedAt:        time.Now(),
	}
	if strings.TrimSpace(changeNote) == "" {
		version.ModifyInstr = fmt.Sprintf("保存版本 v%d", versionNo)
		version.VersionSummary = version.ModifyInstr
	}
	if err := s.store.SaveVersion(ctx, version); err != nil {
		return nil, err
	}
	if err := s.store.SaveDraft(ctx, projectID, string(raw)); err != nil {
		return nil, err
	}
	return version, nil
}

// Versions 版本列表（含修改指令摘要）。
func (s *CoursewareService) Versions(ctx context.Context, projectID string) ([]*CoursewareVersion, error) {
	return s.store.ListVersions(ctx, projectID)
}

// GetVersion 读取指定版本快照。
func (s *CoursewareService) GetVersion(ctx context.Context, projectID string, versionNo int) (*CoursewareVersion, error) {
	return s.store.GetVersion(ctx, projectID, versionNo)
}

// GetVersionByID 读取指定版本 ID，供 /versions/:version_id 使用。
func (s *CoursewareService) GetVersionByID(ctx context.Context, projectID, versionID string) (*CoursewareVersion, error) {
	return s.store.GetVersionByID(ctx, projectID, versionID)
}

// =============================================================================
// mem 实现（S1 standalone / 无 db 降级）
// =============================================================================

type memCoursewareStore struct {
	mu       sync.RWMutex
	projects map[string]*CoursewareProject
	drafts   map[string]string
	versions map[string][]*CoursewareVersion // project_id → 按 version_no 升序
	// pageBindings[project_id][page_id] → PageEvidenceBinding
	pageBindings map[string]map[string]PageEvidenceBinding
}

func newMemCoursewareStore() *memCoursewareStore {
	return &memCoursewareStore{
		projects:     make(map[string]*CoursewareProject),
		drafts:       make(map[string]string),
		versions:     make(map[string][]*CoursewareVersion),
		pageBindings: make(map[string]map[string]PageEvidenceBinding),
	}
}

func (m *memCoursewareStore) CreateProject(_ context.Context, p *CoursewareProject) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.projects[p.ProjectID]; ok {
		return fmt.Errorf("项目已存在: %s", p.ProjectID)
	}
	cp := *p
	m.projects[p.ProjectID] = &cp
	return nil
}

func (m *memCoursewareStore) GetProject(_ context.Context, projectID string) (*CoursewareProject, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	p, ok := m.projects[projectID]
	if !ok {
		return nil, ErrProjectNotFound
	}
	cp := *p
	return &cp, nil
}

func (m *memCoursewareStore) GetProjectByGenID(_ context.Context, genID string) (*CoursewareProject, error) {
	if genID == "" {
		return nil, ErrProjectNotFound
	}
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, p := range m.projects {
		if p.GenID == genID {
			cp := *p
			return &cp, nil
		}
	}
	return nil, ErrProjectNotFound
}

func (m *memCoursewareStore) ListProjects(_ context.Context, ownerID string) ([]*CoursewareProject, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := make([]*CoursewareProject, 0)
	for _, p := range m.projects {
		if p.OwnerID == ownerID {
			cp := *p
			out = append(out, &cp)
		}
	}
	// 按 updated_at 倒序
	for i := 0; i < len(out); i++ {
		for j := i + 1; j < len(out); j++ {
			if out[j].UpdatedAt.After(out[i].UpdatedAt) {
				out[i], out[j] = out[j], out[i]
			}
		}
	}
	return out, nil
}

func (m *memCoursewareStore) DeleteProject(_ context.Context, projectID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.projects[projectID]; !ok {
		return ErrProjectNotFound
	}
	delete(m.projects, projectID)
	delete(m.drafts, projectID)
	delete(m.versions, projectID)
	delete(m.pageBindings, projectID)
	return nil
}

func (m *memCoursewareStore) UpdateProjectStep(_ context.Context, projectID, step string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	p, ok := m.projects[projectID]
	if !ok {
		return ErrProjectNotFound
	}
	p.CurrentStep = step
	p.UpdatedAt = time.Now()
	return nil
}

func (m *memCoursewareStore) UpdateProjectGenID(_ context.Context, projectID, genID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	p, ok := m.projects[projectID]
	if !ok {
		return ErrProjectNotFound
	}
	p.GenID = genID
	p.UpdatedAt = time.Now()
	return nil
}

func (m *memCoursewareStore) UpdateProjectStatus(_ context.Context, projectID, status string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	p, ok := m.projects[projectID]
	if !ok {
		return ErrProjectNotFound
	}
	p.Status = status
	p.UpdatedAt = time.Now()
	return nil
}

func (m *memCoursewareStore) SaveDraft(_ context.Context, projectID, draftJSON string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.drafts[projectID] = draftJSON
	return nil
}

func (m *memCoursewareStore) GetDraft(_ context.Context, projectID string) (string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if _, ok := m.projects[projectID]; !ok {
		return "", ErrProjectNotFound
	}
	return m.drafts[projectID], nil
}

func (m *memCoursewareStore) NextVersionNo(_ context.Context, projectID string) (int, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	chain := m.versions[projectID]
	if len(chain) == 0 {
		return 1, nil
	}
	return chain[len(chain)-1].VersionNo + 1, nil
}

func (m *memCoursewareStore) SaveVersion(_ context.Context, v *CoursewareVersion) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.versions[v.ProjectID] = append(m.versions[v.ProjectID], v)
	return nil
}

func (m *memCoursewareStore) GetVersion(_ context.Context, projectID string, versionNo int) (*CoursewareVersion, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, v := range m.versions[projectID] {
		if v.VersionNo == versionNo {
			cp := *v
			return &cp, nil
		}
	}
	return nil, ErrVersionNotFound
}

func (m *memCoursewareStore) GetVersionByID(_ context.Context, projectID, versionID string) (*CoursewareVersion, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, v := range m.versions[projectID] {
		if v.VersionID == versionID {
			cp := *v
			return &cp, nil
		}
	}
	return nil, ErrVersionNotFound
}

func (m *memCoursewareStore) ListVersions(_ context.Context, projectID string) ([]*CoursewareVersion, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	chain := m.versions[projectID]
	out := make([]*CoursewareVersion, 0, len(chain))
	for _, v := range chain {
		cp := *v
		out = append(out, &cp)
	}
	return out, nil
}

func (m *memCoursewareStore) SetPageBindings(_ context.Context, projectID string, bindings []PageEvidenceBinding) ([]string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	bucket := m.pageBindings[projectID]
	if bucket == nil {
		bucket = make(map[string]PageEvidenceBinding, len(bindings))
		m.pageBindings[projectID] = bucket
	}
	for _, b := range bindings {
		cp := b
		if cp.EvidenceRefs == nil {
			cp.EvidenceRefs = []string{}
		}
		bucket[b.PageID] = cp
	}
	return []string{}, nil
}

func (m *memCoursewareStore) GetPageBindings(_ context.Context, projectID string) (map[string]PageEvidenceBinding, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := make(map[string]PageEvidenceBinding)
	for pageID, b := range m.pageBindings[projectID] {
		cp := b
		if cp.EvidenceRefs == nil {
			cp.EvidenceRefs = []string{}
		}
		out[pageID] = cp
	}
	return out, nil
}

// =============================================================================
// gorm 实现（完整模式）
// =============================================================================

type gormCoursewareStore struct {
	db *gorm.DB
}

func newGormCoursewareStore(db *gorm.DB) *gormCoursewareStore {
	return &gormCoursewareStore{db: db}
}

func (g *gormCoursewareStore) CreateProject(ctx context.Context, p *CoursewareProject) error {
	return g.db.WithContext(ctx).Create(&coursewareProjectRow{
		ID: p.ProjectID, OwnerID: p.OwnerID, Title: p.Title,
		CurrentStep: p.CurrentStep, GenID: p.GenID, Status: p.Status,
		CreatedAt: p.CreatedAt, UpdatedAt: p.UpdatedAt,
	}).Error
}

func (g *gormCoursewareStore) GetProject(ctx context.Context, projectID string) (*CoursewareProject, error) {
	var row coursewareProjectRow
	if err := g.db.WithContext(ctx).Where("id = ?", projectID).First(&row).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrProjectNotFound
		}
		return nil, err
	}
	return &CoursewareProject{
		ProjectID: row.ID, OwnerID: row.OwnerID, Title: row.Title,
		CurrentStep: row.CurrentStep, GenID: row.GenID, Status: row.Status,
		CreatedAt: row.CreatedAt, UpdatedAt: row.UpdatedAt,
	}, nil
}

func (g *gormCoursewareStore) GetProjectByGenID(ctx context.Context, genID string) (*CoursewareProject, error) {
	if genID == "" {
		return nil, ErrProjectNotFound
	}
	var row coursewareProjectRow
	if err := g.db.WithContext(ctx).Where("gen_id = ?", genID).First(&row).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrProjectNotFound
		}
		return nil, err
	}
	return &CoursewareProject{
		ProjectID: row.ID, OwnerID: row.OwnerID, Title: row.Title,
		CurrentStep: row.CurrentStep, GenID: row.GenID, Status: row.Status,
		CreatedAt: row.CreatedAt, UpdatedAt: row.UpdatedAt,
	}, nil
}

func (g *gormCoursewareStore) ListProjects(ctx context.Context, ownerID string) ([]*CoursewareProject, error) {
	var rows []coursewareProjectRow
	if err := g.db.WithContext(ctx).Where("owner_id = ?", ownerID).
		Order("updated_at DESC").Find(&rows).Error; err != nil {
		return nil, err
	}
	out := make([]*CoursewareProject, 0, len(rows))
	for _, r := range rows {
		out = append(out, &CoursewareProject{
			ProjectID: r.ID, OwnerID: r.OwnerID, Title: r.Title,
			CurrentStep: r.CurrentStep, GenID: r.GenID, Status: r.Status,
			CreatedAt: r.CreatedAt, UpdatedAt: r.UpdatedAt,
		})
	}
	return out, nil
}

func (g *gormCoursewareStore) DeleteProject(ctx context.Context, projectID string) error {
	return g.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("project_id = ?", projectID).Delete(&coursewareVersionRow{}).Error; err != nil {
			return err
		}
		if err := tx.Where("project_id = ?", projectID).Delete(&coursewareDraftRow{}).Error; err != nil {
			return err
		}
		if err := tx.Where("project_id = ?", projectID).Delete(&coursewarePageBindingRow{}).Error; err != nil {
			return err
		}
		res := tx.Where("id = ?", projectID).Delete(&coursewareProjectRow{})
		if res.Error != nil {
			return res.Error
		}
		if res.RowsAffected == 0 {
			return ErrProjectNotFound
		}
		return nil
	})
}

func (g *gormCoursewareStore) UpdateProjectStep(ctx context.Context, projectID, step string) error {
	res := g.db.WithContext(ctx).Model(&coursewareProjectRow{}).
		Where("id = ?", projectID).
		Updates(map[string]any{"current_step": step, "updated_at": time.Now()})
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrProjectNotFound
	}
	return nil
}

func (g *gormCoursewareStore) UpdateProjectGenID(ctx context.Context, projectID, genID string) error {
	res := g.db.WithContext(ctx).Model(&coursewareProjectRow{}).
		Where("id = ?", projectID).
		Updates(map[string]any{"gen_id": genID, "updated_at": time.Now()})
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrProjectNotFound
	}
	return nil
}

func (g *gormCoursewareStore) UpdateProjectStatus(ctx context.Context, projectID, status string) error {
	res := g.db.WithContext(ctx).Model(&coursewareProjectRow{}).
		Where("id = ?", projectID).
		Updates(map[string]any{"status": status, "updated_at": time.Now()})
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrProjectNotFound
	}
	return nil
}

func (g *gormCoursewareStore) SaveDraft(ctx context.Context, projectID, draftJSON string) error {
	return g.db.WithContext(ctx).Exec(`
		INSERT INTO courseware_drafts (project_id, draft_json, updated_at)
		VALUES (?, ?, ?)
		ON CONFLICT (project_id) DO UPDATE SET draft_json = EXCLUDED.draft_json, updated_at = EXCLUDED.updated_at
	`, projectID, draftJSON, time.Now()).Error
}

func (g *gormCoursewareStore) GetDraft(ctx context.Context, projectID string) (string, error) {
	var row coursewareDraftRow
	if err := g.db.WithContext(ctx).Where("project_id = ?", projectID).First(&row).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return "", nil // 无草稿返回空
		}
		return "", err
	}
	return row.DraftJSON, nil
}

func (g *gormCoursewareStore) NextVersionNo(ctx context.Context, projectID string) (int, error) {
	var maxNo int
	if err := g.db.WithContext(ctx).Model(&coursewareVersionRow{}).
		Where("project_id = ?", projectID).
		Select("COALESCE(MAX(version_no), 0)").Scan(&maxNo).Error; err != nil {
		return 0, err
	}
	return maxNo + 1, nil
}

func (g *gormCoursewareStore) SaveVersion(ctx context.Context, v *CoursewareVersion) error {
	row := versionToRow(v)
	var project coursewareProjectRow
	if err := g.db.WithContext(ctx).Select("owner_id").Where("id = ?", v.ProjectID).First(&project).Error; err != nil {
		return err
	}
	row.OwnerID = project.OwnerID
	return g.db.WithContext(ctx).Create(row).Error
}

func (g *gormCoursewareStore) GetVersion(ctx context.Context, projectID string, versionNo int) (*CoursewareVersion, error) {
	var row coursewareVersionRow
	if err := g.db.WithContext(ctx).
		Where("project_id = ? AND version_no = ?", projectID, versionNo).First(&row).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrVersionNotFound
		}
		return nil, err
	}
	return rowToVersion(row), nil
}

func (g *gormCoursewareStore) GetVersionByID(ctx context.Context, projectID, versionID string) (*CoursewareVersion, error) {
	var row coursewareVersionRow
	if err := g.db.WithContext(ctx).Where("project_id = ? AND version_id = ?", projectID, versionID).First(&row).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrVersionNotFound
		}
		return nil, err
	}
	return rowToVersion(row), nil
}

func (g *gormCoursewareStore) ListVersions(ctx context.Context, projectID string) ([]*CoursewareVersion, error) {
	var rows []coursewareVersionRow
	if err := g.db.WithContext(ctx).Where("project_id = ?", projectID).
		Order("version_no ASC").Find(&rows).Error; err != nil {
		return nil, err
	}
	out := make([]*CoursewareVersion, 0, len(rows))
	for _, r := range rows {
		out = append(out, rowToVersion(r))
	}
	return out, nil
}

func (g *gormCoursewareStore) SetPageBindings(ctx context.Context, projectID string, bindings []PageEvidenceBinding) ([]string, error) {
	now := time.Now().UTC()
	for _, b := range bindings {
		refs, err := json.Marshal(b.EvidenceRefs)
		if err != nil {
			return nil, err
		}
		if err := g.db.WithContext(ctx).Exec(`
			INSERT INTO courseware_page_bindings (project_id, page_id, evidence_refs, auto_bound, bound_by, bound_at, updated_at)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT (project_id, page_id) DO UPDATE SET
				evidence_refs = EXCLUDED.evidence_refs,
				auto_bound    = EXCLUDED.auto_bound,
				bound_by      = EXCLUDED.bound_by,
				bound_at      = EXCLUDED.bound_at,
				updated_at    = EXCLUDED.updated_at
		`, projectID, b.PageID, string(refs), b.AutoBound, b.BoundBy, b.BoundAt, now).Error; err != nil {
			return nil, err
		}
	}
	return []string{}, nil
}

func (g *gormCoursewareStore) GetPageBindings(ctx context.Context, projectID string) (map[string]PageEvidenceBinding, error) {
	var rows []coursewarePageBindingRow
	if err := g.db.WithContext(ctx).Where("project_id = ?", projectID).
		Order("page_id ASC").Find(&rows).Error; err != nil {
		return nil, err
	}
	out := make(map[string]PageEvidenceBinding, len(rows))
	for _, r := range rows {
		b := PageEvidenceBinding{
			PageID:       r.PageID,
			EvidenceRefs: []string{},
			AutoBound:    r.AutoBound,
			BoundBy:      r.BoundBy,
			BoundAt:      r.BoundAt,
		}
		if strings.TrimSpace(r.EvidenceRefs) != "" {
			if err := json.Unmarshal([]byte(r.EvidenceRefs), &b.EvidenceRefs); err != nil {
				return nil, fmt.Errorf("页面绑定 evidence_refs 反序列化失败: %s", err)
			}
			if b.EvidenceRefs == nil {
				b.EvidenceRefs = []string{}
			}
		}
		out[r.PageID] = b
	}
	return out, nil
}
