package handler

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
	"sort"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// CoursewareHandler 课件项目 + 修改对话 + 版本快照（A1 最小基础 / A6 / A7）。
//
// 路由（backend/internal/router/teacher.go）：
//
//	POST /api/v1/coursewares                          — 新建项目（A1）
//	GET  /api/v1/coursewares                          — 我的课件列表（A1）
//	PUT  /api/v1/coursewares/:project_id/step         — 持久化步骤（A3）
//	PUT  /api/v1/coursewares/:project_id/draft        — 保存草稿（A2）
//	GET  /api/v1/coursewares/:project_id/draft        — 读取草稿（A2）
//	POST /api/v1/coursewares/:project_id/modify       — 修改编排（A6）
//	GET  /api/v1/coursewares/:project_id/modify-history — 修改记录（A6）
//	GET  /api/v1/coursewares/:project_id/versions     — 版本列表（A7）
//	POST /api/v1/coursewares/:project_id/rollback     — 回滚（A7）
//	PUT  /api/v1/coursewares/:project_id/page-bindings — 保存页面级证据绑定（契约 v1.0 模块1）
//	GET  /api/v1/coursewares/:project_id/page-bindings — 读取页面级证据绑定（契约 v1.0 模块1）
type CoursewareHandler struct {
	svc *service.CoursewareService
}

func NewCoursewareHandler(svc *service.CoursewareService) *CoursewareHandler {
	return &CoursewareHandler{svc: svc}
}

// Create POST /api/v1/coursewares —— 新建课件项目。
func (h *CoursewareHandler) Create(c *gin.Context) {
	var req struct {
		OwnerID string `json:"owner_id"`
		Title   string `json:"title"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if req.OwnerID == "" {
		// 教师端当前为本地登录态，未强制 JWT；缺省归入 demo 教师避免 400 阻断联调
		req.OwnerID = "teacher_demo"
	}
	p, err := h.svc.CreateProject(c.Request.Context(), req.OwnerID, req.Title)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": p})
}

// List GET /api/v1/coursewares —— 我的课件列表。
func (h *CoursewareHandler) List(c *gin.Context) {
	ownerID := c.Query("owner_id")
	if ownerID == "" {
		ownerID = "teacher_demo"
	}
	items, err := h.svc.ListProjects(c.Request.Context(), ownerID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true, "data": gin.H{"items": items}, "error": "", "code": 200})
}

// UpdateStep PUT /:project_id/step —— 持久化当前步骤。
func (h *CoursewareHandler) UpdateStep(c *gin.Context) {
	projectID := c.Param("project_id")
	var req struct {
		Step        string `json:"step"`
		CurrentStep string `json:"current_step"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	step := req.CurrentStep
	if step == "" {
		step = req.Step
	}
	if step == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "step 必填"})
		return
	}
	if err := h.svc.UpdateStep(c.Request.Context(), projectID, step); err != nil {
		h.mapError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"project_id": projectID, "step": step, "current_step": step}})
}

// SaveDraft PUT /:project_id/draft —— 保存草稿。
func (h *CoursewareHandler) SaveDraft(c *gin.Context) {
	projectID := c.Param("project_id")
	var req struct {
		DraftJSON json.RawMessage `json:"draft_json"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	raw := bytes.TrimSpace(req.DraftJSON)
	if len(raw) == 0 {
		raw = []byte("{}")
	}
	draftJSON := string(raw)
	if raw[0] == '"' {
		if err := json.Unmarshal(raw, &draftJSON); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "draft_json 不是有效 JSON"})
			return
		}
	}
	if !json.Valid([]byte(draftJSON)) {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "draft_json 不是有效 JSON"})
		return
	}
	if err := h.svc.SaveDraft(c.Request.Context(), projectID, draftJSON); err != nil {
		h.mapError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"saved": true}})
}

// Context GET /:project_id/context —— 一次返回恢复编辑所需的项目与草稿。
func (h *CoursewareHandler) Context(c *gin.Context) {
	projectID := c.Param("project_id")
	project, err := h.svc.GetProject(c.Request.Context(), projectID)
	if err != nil {
		h.mapError(c, err)
		return
	}
	draftJSON, err := h.svc.GetDraft(c.Request.Context(), projectID)
	if err != nil {
		h.mapError(c, err)
		return
	}
	var draft any = map[string]any{}
	if draftJSON != "" {
		if err := json.Unmarshal([]byte(draftJSON), &draft); err != nil {
			draft = map[string]any{}
		}
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{
		"project": project, "draft": draft, "current_step": project.CurrentStep,
		"generation_id": project.GenID,
	}})
}

// Delete DELETE /:project_id —— 删除项目及关联草稿、版本。
func (h *CoursewareHandler) Delete(c *gin.Context) {
	if err := h.svc.DeleteProject(c.Request.Context(), c.Param("project_id")); err != nil {
		h.mapError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"deleted": true}})
}

// GetDraft GET /:project_id/draft —— 读取草稿（draft_json 为原始 JSON 字符串）。
func (h *CoursewareHandler) GetDraft(c *gin.Context) {
	projectID := c.Param("project_id")
	draft, err := h.svc.GetDraft(c.Request.Context(), projectID)
	if err != nil {
		h.mapError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"draft_json": draft}})
}

// Modify POST /:project_id/modify —— A6 修改编排（意图解析 → 局部生成 → 快照）。
func (h *CoursewareHandler) Modify(c *gin.Context) {
	projectID := c.Param("project_id")
	var req struct {
		Instruction string                     `json:"instruction"`
		Nodes       []service.TeachingNodeItem `json:"nodes"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if req.Instruction == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "instruction 不能为空"})
		return
	}
	result, err := h.svc.Modify(c.Request.Context(), projectID, req.Instruction, req.Nodes)
	if err != nil {
		h.mapError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": result})
}

// ModifyHistory GET /:project_id/modify-history —— 修改记录列表。
func (h *CoursewareHandler) ModifyHistory(c *gin.Context) {
	projectID := c.Param("project_id")
	versions, err := h.svc.ModifyHistory(c.Request.Context(), projectID)
	if err != nil {
		h.mapError(c, err)
		return
	}
	type versionItem struct {
		VersionID         string                     `json:"version_id"`
		VersionNo         int                        `json:"version_no"`
		ParentVersionID   string                     `json:"parent_version_id,omitempty"`
		VersionSummary    string                     `json:"version_summary"`
		ModifyInstruction string                     `json:"modify_instruction"`
		CreatedAt         string                     `json:"created_at"`
		Nodes             []service.TeachingNodeItem `json:"nodes"`
		Presentation      map[string]string          `json:"presentation,omitempty"`
	}
	items := make([]versionItem, 0, len(versions))
	for _, v := range versions {
		var nodes []service.TeachingNodeItem
		_ = json.Unmarshal([]byte(v.NodesJSON), &nodes)
		var presentation map[string]string
		if v.PresentationJSON != "" {
			_ = json.Unmarshal([]byte(v.PresentationJSON), &presentation)
		}
		items = append(items, versionItem{
			VersionID: v.VersionID, VersionNo: v.VersionNo, ParentVersionID: v.ParentVersionID,
			VersionSummary:    v.VersionSummary,
			ModifyInstruction: v.ModifyInstr, CreatedAt: v.CreatedAt.Format("2006-01-02 15:04:05"),
			Nodes:        nodes,
			Presentation: presentation,
		})
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"items": items}})
}

// Versions GET /:project_id/versions —— 版本列表（含修改指令摘要）。
func (h *CoursewareHandler) Versions(c *gin.Context) {
	h.ModifyHistory(c) // 同一数据源，字段一致
}

// CreateVersion POST /:project_id/versions —— 手动保存完整版本快照。
func (h *CoursewareHandler) CreateVersion(c *gin.Context) {
	projectID := c.Param("project_id")
	var req struct {
		VersionNo      int                              `json:"version_no"`
		Snapshot       *service.ContractVersionSnapshot `json:"snapshot"`
		ChangeNote     string                           `json:"change_note"`
		Nodes          []service.TeachingNodeItem       `json:"nodes"`
		Presentation   map[string]string                `json:"presentation"`
		PageBindings   interface{}                      `json:"page_bindings"`
		VersionSummary string                           `json:"version_summary"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"ok": false, "data": nil, "error": "版本快照参数错误: " + err.Error(), "code": 400})
		return
	}
	var version *service.CoursewareVersion
	var err error
	if req.Snapshot != nil {
		version, err = h.svc.CreateVersionSnapshotJSON(c.Request.Context(), projectID, req.ChangeNote, *req.Snapshot)
	} else {
		// Legacy fields remain accepted for one compatibility cycle.
		summary := req.ChangeNote
		if summary == "" {
			summary = req.VersionSummary
		}
		version, err = h.svc.CreateVersionSnapshot(c.Request.Context(), projectID, summary, req.Nodes, req.Presentation, req.PageBindings)
	}
	if err != nil {
		h.mapError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true, "data": gin.H{"version_id": version.VersionID, "version_no": version.VersionNo}, "error": "", "code": 200})
}

// VersionDetail GET /:project_id/versions/:version_id —— 获取单版本详情。
func (h *CoursewareHandler) VersionDetail(c *gin.Context) {
	version, err := h.svc.GetVersionByID(c.Request.Context(), c.Param("project_id"), c.Param("version_id"))
	if err != nil {
		h.mapError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true, "data": h.versionDetail(version), "error": "", "code": 200})
}

func (h *CoursewareHandler) versionDetail(v *service.CoursewareVersion) gin.H {
	var snapshot service.CoursewareVersionSnapshot
	if v.SnapshotJSON != "" {
		_ = json.Unmarshal([]byte(v.SnapshotJSON), &snapshot)
	}
	if len(snapshot.Nodes) == 0 && v.NodesJSON != "" {
		_ = json.Unmarshal([]byte(v.NodesJSON), &snapshot.Nodes)
	}
	if len(snapshot.Presentation) == 0 && v.PresentationJSON != "" {
		_ = json.Unmarshal([]byte(v.PresentationJSON), &snapshot.Presentation)
	}
	publicSnapshot := service.ContractVersionSnapshot{
		Outline:      map[string]interface{}{},
		Content:      snapshot.Nodes,
		PageBindings: snapshot.PageBindings,
		Style:        snapshot.Presentation,
	}
	if v.SnapshotJSON != "" {
		var canonical service.ContractVersionSnapshot
		if json.Unmarshal([]byte(v.SnapshotJSON), &canonical) == nil && (canonical.Content != nil || canonical.Outline != nil || canonical.Style != nil) {
			publicSnapshot = canonical
		}
	}
	return gin.H{
		"version_id": v.VersionID, "project_id": v.ProjectID, "version_no": v.VersionNo,
		"parent_version_id": v.ParentVersionID, "change_note": v.ModifyInstr,
		"version_summary": v.VersionSummary, "modify_instruction": v.ModifyInstr, "created_at": v.CreatedAt,
		"snapshot": publicSnapshot,
		// Legacy response fields remain temporarily for existing S3 consumers.
		"nodes": snapshot.Nodes, "presentation": snapshot.Presentation, "page_bindings": snapshot.PageBindings,
	}
}

// Rollback POST /:project_id/rollback —— A7 回滚（克隆式，不覆盖历史）。
func (h *CoursewareHandler) Rollback(c *gin.Context) {
	projectID := c.Param("project_id")
	var req struct {
		TargetVersionID string `json:"target_version_id"`
		VersionNo       int    `json:"version_no"` // legacy compatibility
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"ok": false, "data": nil, "error": "target_version_id 必填", "code": 400})
		return
	}
	var result *service.RollbackResult
	var err error
	if req.TargetVersionID != "" {
		result, err = h.svc.RollbackByID(c.Request.Context(), projectID, req.TargetVersionID)
	} else if req.VersionNo > 0 {
		// Legacy clients may still send a number while migrating.
		result, err = h.svc.Rollback(c.Request.Context(), projectID, req.VersionNo)
	} else {
		c.JSON(http.StatusBadRequest, gin.H{"ok": false, "data": nil, "error": "target_version_id 必填", "code": 400})
		return
	}
	if err != nil {
		h.mapError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true, "data": result, "error": "", "code": 200})
}

func (h *CoursewareHandler) mapError(c *gin.Context, err error) {
	status := http.StatusInternalServerError
	switch {
	case errors.Is(err, service.ErrProjectNotFound), errors.Is(err, service.ErrVersionNotFound):
		status = http.StatusNotFound
	}
	c.JSON(status, gin.H{"ok": false, "data": nil, "error": err.Error(), "code": status})
}

// PageBindingsPut PUT /:project_id/page-bindings —— 保存页面级证据绑定。
//
// 契约 v1.0 模块1 接口1：请求体为 { "page_bindings": { "<page_id>": { evidence_refs, auto_bound, bound_by } } }。
// upsert 语义——只写入传入的页面，其余页面绑定保持不变；
// 传空 evidence_refs 表示清空该页的证据引用（教师手动解绑全部资料）。
func (h *CoursewareHandler) PageBindingsPut(c *gin.Context) {
	projectID := c.Param("project_id")
	var req struct {
		PageBindings map[string]service.PageEvidenceBinding `json:"page_bindings"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"ok": false, "data": nil, "error": "page_bindings 参数错误: " + err.Error(), "code": 400})
		return
	}
	if req.PageBindings == nil {
		c.JSON(http.StatusBadRequest, gin.H{"ok": false, "data": nil, "error": "page_bindings 不能为空", "code": 400})
		return
	}
	bindings := make([]service.PageEvidenceBinding, 0, len(req.PageBindings))
	for pageID, binding := range req.PageBindings {
		binding.PageID = pageID // 以 map key 为准，请求体内的 page_id 可省略
		bindings = append(bindings, binding)
	}
	updated, err := h.svc.SavePageBindings(c.Request.Context(), projectID, bindings)
	if err != nil {
		h.mapError(c, err)
		return
	}
	sort.Strings(updated)
	c.JSON(http.StatusOK, gin.H{"ok": true, "data": gin.H{"updated_pages": updated}, "error": "", "code": 200})
}

// PageBindingsGet GET /:project_id/page-bindings —— 读取当前项目的页面级证据绑定。
//
// 契约 v1.0 模块1 接口2：响应 data.page_bindings 以 page_id 为键，
// 每页含 page_id / evidence_refs / auto_bound / bound_by / bound_at。
func (h *CoursewareHandler) PageBindingsGet(c *gin.Context) {
	bindings, err := h.svc.GetPageBindings(c.Request.Context(), c.Param("project_id"))
	if err != nil {
		h.mapError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true, "data": gin.H{"page_bindings": bindings}, "error": "", "code": 200})
}
