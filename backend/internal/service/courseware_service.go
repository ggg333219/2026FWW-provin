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
	// ProjectID is retained for the earlier A6/A7 schema; reads accept either so
	// projects created by the workspace can enter the AI modification flow.
	ID          string    `gorm:"column:id;size:36"`
	ProjectID   string    `gorm:"column:project_id;size:64;primaryKey"`
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
	VersionID        string    `json:"version_id"`
	ProjectID        string    `json:"project_id"`
	VersionNo        int       `json:"version_no"`
	ParentVersionID  string    `json:"parent_version_id,omitempty"`
	NodesJSON        string    `json:"-"` // 原始 JSON（内部）
	PresentationJSON string    `json:"-"` // 修改前的 PPT 呈现层快照
	SnapshotJSON     string    `json:"-"` // 完整快照：节点、样式、页面证据绑定
	ModifyInstr      string    `json:"modify_instruction"`
	VersionSummary   string    `json:"version_summary"`
	CreatedAt        time.Time `json:"created_at"`
}

type coursewareVersionRow struct {
	VersionID        string    `gorm:"column:version_id;size:64;primaryKey"`
	ProjectID        string    `gorm:"column:project_id;size:64;index"`
	VersionNo        int       `gorm:"column:version_no"`
	ParentVersionID  string    `gorm:"column:parent_version_id;size:64;index"`
	NodesJSON        string    `gorm:"column:nodes_snapshot;type:text"`
	PresentationJSON string    `gorm:"column:presentation_snapshot;type:text"`
	SnapshotJSON     string    `gorm:"column:snapshot_json;type:text"`
	ModifyInstr      string    `gorm:"column:modify_instruction;size:1000"`
	VersionSummary   string    `gorm:"column:version_summary;size:1000"`
	CreatedAt        time.Time `gorm:"column:created_at"`
}

func (coursewareVersionRow) TableName() string { return "courseware_versions" }

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
	Action                string            `json:"action"` // simplify|expand|delete|add|reorder|restyle|rewrite
	SecondaryActions      []string          `json:"secondary_actions"`
	Constraints           []string          `json:"constraints"`
	Confidence            float64           `json:"confidence"`
	ClarificationNeeded   bool              `json:"clarification_needed"`
	ClarificationQuestion string            `json:"clarification_question"`
	Presentation          map[string]string `json:"presentation"`
}

// ParseModifyRequest / Response —— Go→Python 调用 DTO。
type ParseModifyRequest struct {
	ProjectID   string             `json:"project_id"`
	Instruction string             `json:"instruction"`
	Nodes       []TeachingNodeItem `json:"nodes"`
}

type ParseModifyResponse struct {
	Intent ModifyIntent `json:"data"`
}

// =============================================================================
// CoursewareService —— 门面
// =============================================================================

// modifyClient —— CoursewareService 实际依赖的 AI 能力窄接口。
// 只调用意图解析与局部内容生成两个端点；窄接口便于测试注入桩。
type modifyClient interface {
	ParseModify(ctx context.Context, req ParseModifyRequest) (*ModifyIntent, error)
	GenerateContent(ctx context.Context, req GenContentRequest) (*GenContentStatusResponse, error)
}

type CoursewareService struct {
	aiClient modifyClient
	store    coursewareStore
}

// coursewareStore —— 持久化抽象（mem 降级 + gorm）。
type coursewareStore interface {
	CreateProject(ctx context.Context, p *CoursewareProject) error
	GetProject(ctx context.Context, projectID string) (*CoursewareProject, error)
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
	if err := db.AutoMigrate(&coursewareVersionRow{}, &coursewareDraftRow{}, &coursewarePageBindingRow{}); err != nil {
		return err
	}
	if err := db.AutoMigrate(&coursewareProjectRow{}); err != nil {
		if addErr := ensureCoursewareProjectColumns(db); addErr != nil {
			return addErr
		}
		return nil
	}
	return nil
}

// ensureCoursewareProjectColumns 给遗留的 courseware_projects 表补齐本模块需要的列。
// IF NOT EXISTS 保证可重复执行；已有的 id 主键与 owner_id/title 等列不被改动。
func ensureCoursewareProjectColumns(db *gorm.DB) error {
	columns := []struct{ name, ddl string }{
		{"project_id", "VARCHAR(64) NOT NULL DEFAULT ''"},
		{"owner_id", "VARCHAR(64) NOT NULL DEFAULT ''"},
		{"title", "VARCHAR(500) NOT NULL DEFAULT ''"},
		{"current_step", "VARCHAR(20) NOT NULL DEFAULT 's1_intent'"},
		{"gen_id", "VARCHAR(64) DEFAULT ''"},
		{"status", "VARCHAR(20) NOT NULL DEFAULT 'draft'"},
	}
	for _, col := range columns {
		ddl := fmt.Sprintf("ALTER TABLE courseware_projects ADD COLUMN IF NOT EXISTS %s %s", col.name, col.ddl)
		if err := db.Exec(ddl).Error; err != nil {
			return err
		}
	}
	return nil
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

// ---- A6: 修改编排 + 版本快照 ----

// ModifyResult —— modify 响应。
type ModifyResult struct {
	ModifiedNodes     []TeachingNodeItem `json:"modified_nodes"`
	AllNodes          []TeachingNodeItem `json:"all_nodes"`
	Intent            ModifyIntent       `json:"intent"`
	PreviousVersionID string             `json:"previous_version_id"`
	PreviousVersionNo int                `json:"previous_version_no"`
	NewVersionNo      int                `json:"new_version_no"`
	Clarification     string             `json:"clarification,omitempty"`
	Presentation      map[string]string  `json:"presentation,omitempty"`
}

// Modify 修改编排：解析意图 → （低置信度则追问）→ 局部生成 → 更新草稿 → 版本快照。
func (s *CoursewareService) Modify(ctx context.Context, projectID, instruction string, nodes []TeachingNodeItem) (*ModifyResult, error) {
	if _, err := s.store.GetProject(ctx, projectID); err != nil {
		return nil, err
	}
	if strings.TrimSpace(instruction) == "" {
		return nil, fmt.Errorf("instruction 不能为空")
	}

	// 1) B5: 解析意图
	intentPtr, err := s.aiClient.ParseModify(ctx, ParseModifyRequest{
		ProjectID:   projectID,
		Instruction: instruction,
		Nodes:       nodes,
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
		resp, err := s.aiClient.GenerateContent(ctx, GenContentRequest{
			Nodes:             updatedNodes,
			Mode:              "partial",
			TargetNodeIDs:     intent.TargetIDs,
			ModifyAction:      intent.Action,
			ModifyConstraints: intent.Constraints,
		})
		if err != nil {
			return nil, fmt.Errorf("局部重生成失败: %w", err)
		}
		updatedNodes = mergePartialResult(updatedNodes, resp.Nodes, intent.TargetIDs)
		modifiedIDs = intent.TargetIDs
	}
	// restyle：仅样式层，不改内容；样式字段由 AI 解析后透传给前端。

	// 5) 修改前快照（快照 = 修改前的完整状态）
	prevNo, err := s.store.NextVersionNo(ctx, projectID)
	if err != nil {
		return nil, err
	}
	nodesJSON, _ := json.Marshal(nodes) // 修改前
	snap := &CoursewareVersion{
		VersionID:        "ver_" + uuid.NewString()[:12],
		ProjectID:        projectID,
		VersionNo:        prevNo,
		NodesJSON:        string(nodesJSON),
		PresentationJSON: presentationJSON(presentationFromNodes(nodes)),
		SnapshotJSON:     snapshotJSON(nodes, presentationFromNodes(nodes), nil),
		ModifyInstr:      instruction,
		VersionSummary:   instruction,
		CreatedAt:        time.Now(),
	}
	if err := s.store.SaveVersion(ctx, snap); err != nil {
		return nil, err
	}

	// 6) 更新草稿
	draftJSON, _ := json.Marshal(updatedNodes)
	_ = s.store.SaveDraft(ctx, projectID, string(draftJSON))
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
		ModifiedNodes:     modifiedNodes,
		AllNodes:          updatedNodes,
		Intent:            intent,
		PreviousVersionID: snap.VersionID,
		PreviousVersionNo: snap.VersionNo,
		NewVersionNo:      snap.VersionNo, // 快照即新版本号
		Presentation:      intent.Presentation,
	}, nil
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
	nodes, _ := snapshot.Content.([]TeachingNodeItem)
	nodesRaw, _ := json.Marshal(nodes)
	presentation, _ := snapshot.Style.(map[string]string)
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
		ID: p.ProjectID, ProjectID: p.ProjectID, OwnerID: p.OwnerID, Title: p.Title,
		CurrentStep: p.CurrentStep, GenID: p.GenID, Status: p.Status,
		CreatedAt: p.CreatedAt, UpdatedAt: p.UpdatedAt,
	}).Error
}

func (g *gormCoursewareStore) GetProject(ctx context.Context, projectID string) (*CoursewareProject, error) {
	var row coursewareProjectRow
	if err := g.db.WithContext(ctx).Where("project_id = ? OR id = ?", projectID, projectID).First(&row).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrProjectNotFound
		}
		return nil, err
	}
	resolvedID := row.ProjectID
	if resolvedID == "" {
		resolvedID = row.ID
	}
	return &CoursewareProject{
		ProjectID: resolvedID, OwnerID: row.OwnerID, Title: row.Title,
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
		resolvedID := r.ProjectID
		if resolvedID == "" {
			resolvedID = r.ID
		}
		out = append(out, &CoursewareProject{
			ProjectID: resolvedID, OwnerID: r.OwnerID, Title: r.Title,
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
		res := tx.Where("project_id = ? OR id = ?", projectID, projectID).Delete(&coursewareProjectRow{})
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
		Where("project_id = ? OR id = ?", projectID, projectID).
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
		Where("project_id = ? OR id = ?", projectID, projectID).
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
		Where("project_id = ? OR id = ?", projectID, projectID).
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
	return g.db.WithContext(ctx).Create(&coursewareVersionRow{
		VersionID: v.VersionID, ProjectID: v.ProjectID, VersionNo: v.VersionNo,
		ParentVersionID: v.ParentVersionID, NodesJSON: v.NodesJSON, PresentationJSON: v.PresentationJSON,
		SnapshotJSON: v.SnapshotJSON, ModifyInstr: v.ModifyInstr, VersionSummary: v.VersionSummary, CreatedAt: v.CreatedAt,
	}).Error
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
	return &CoursewareVersion{
		VersionID: row.VersionID, ProjectID: row.ProjectID, VersionNo: row.VersionNo,
		ParentVersionID: row.ParentVersionID, NodesJSON: row.NodesJSON, PresentationJSON: row.PresentationJSON,
		SnapshotJSON: row.SnapshotJSON, ModifyInstr: row.ModifyInstr, VersionSummary: row.VersionSummary, CreatedAt: row.CreatedAt,
	}, nil
}

func (g *gormCoursewareStore) GetVersionByID(ctx context.Context, projectID, versionID string) (*CoursewareVersion, error) {
	var row coursewareVersionRow
	if err := g.db.WithContext(ctx).Where("project_id = ? AND version_id = ?", projectID, versionID).First(&row).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrVersionNotFound
		}
		return nil, err
	}
	return &CoursewareVersion{VersionID: row.VersionID, ProjectID: row.ProjectID, VersionNo: row.VersionNo,
		ParentVersionID: row.ParentVersionID, NodesJSON: row.NodesJSON, PresentationJSON: row.PresentationJSON,
		SnapshotJSON: row.SnapshotJSON, ModifyInstr: row.ModifyInstr, VersionSummary: row.VersionSummary, CreatedAt: row.CreatedAt}, nil
}

func (g *gormCoursewareStore) ListVersions(ctx context.Context, projectID string) ([]*CoursewareVersion, error) {
	var rows []coursewareVersionRow
	if err := g.db.WithContext(ctx).Where("project_id = ?", projectID).
		Order("version_no ASC").Find(&rows).Error; err != nil {
		return nil, err
	}
	out := make([]*CoursewareVersion, 0, len(rows))
	for _, r := range rows {
		out = append(out, &CoursewareVersion{
			VersionID: r.VersionID, ProjectID: r.ProjectID, VersionNo: r.VersionNo,
			ParentVersionID: r.ParentVersionID, NodesJSON: r.NodesJSON, PresentationJSON: r.PresentationJSON,
			SnapshotJSON: r.SnapshotJSON, ModifyInstr: r.ModifyInstr, VersionSummary: r.VersionSummary, CreatedAt: r.CreatedAt,
		})
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
