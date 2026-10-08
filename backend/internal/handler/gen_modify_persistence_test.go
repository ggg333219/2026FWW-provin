package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"smart-teaching-backend/internal/service"
)

// 契约 v1.0 §1.1 接口 3 + §3.2 的端到端验证：
//
//	POST /api/v1/gen/modify 带 page_id + evidence_refs + user_instruction
//	  → AI Engine（fake，返回可控的 citation_refs / evidence_used / nodes）
//	  → coursewareService.RecordModifyResult 把请求+响应落 CoursewareVersion + page_bindings
//	  → GET /api/v1/coursewares/:id/latest-generation-context 读出
//
// 这条链是修复以下两个前端问题的前提：
//   1. AI 对话切换 PPT 不重置：前端必须能按 gen_id / project_id 拉"权威读"，
//      否则只能从本地内存捞对话，自然会残留；
//   2. 左侧资料绑定打开 PPT 时不显示：绑定已落库（page_bindings 表），
//      前端走 LatestGenerationContext 即可一次性拿到所有页的当前绑定。
//
// 本测试同时覆盖 mem store（无 DB 依赖）和真 PostgreSQL（COURSEWARE_PG_DSN）。

// modifyPersistFakeAI —— 只实现 GenerationModify 的可控 AI Engine。
// 其它方法全部返回 nil，避免无关方法被本链路意外触发。
type modifyPersistFakeAI struct {
	modifyCalls   int
	modifyRequest service.GenerationModifyRequest
	modifyResp    *service.GenerationModifyResponse
}

func (m *modifyPersistFakeAI) GenerationModify(_ context.Context, req service.GenerationModifyRequest) (*service.GenerationModifyResponse, error) {
	m.modifyCalls++
	m.modifyRequest = req
	if m.modifyResp == nil {
		return nil, nil
	}
	return m.modifyResp, nil
}

// 实现 service.AIEngine 接口的其它方法（全部返回 nil；测试不会调到）
func (m *modifyPersistFakeAI) ParseDocument(context.Context, *multipart.FileHeader) (*service.ParseDocumentResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) ReconstructDocument(context.Context, service.ReconstructDocumentRequest) (*service.ReconstructDocumentResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) GenerateNodeScript(context.Context, service.GenerateNodeScriptRequest) (*service.GenerateNodeScriptResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) GenerateFromMarkdown(context.Context, service.GenerateFromMarkdownRequest) (*service.GenerateFromMarkdownResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) GenerateScript(context.Context, service.GenerateScriptRequest) (*service.GenerateScriptResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) GenerateAudio(context.Context, service.GenerateAudioRequest) (*service.GenerateAudioResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) AskWithContext(context.Context, service.AskWithContextRequest) (*service.AskWithContextResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) ParseKnowledge(context.Context, service.ParseKnowledgeRequest) (*service.ParseKnowledgeResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) IntentExtract(context.Context, service.IntentExtractRequest) (*service.IntentExtractResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) IntentConfirm(context.Context, service.IntentConfirmRequest) (*service.IntentConfirmResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) ParseProcess(context.Context, *service.ParseProcessRequest) (*service.ParseProcessResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) ParseStatus(context.Context, string) (*service.ParseStatusResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) ParseVideo(context.Context, *service.ParseVideoRequest) (*service.ParseProcessResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) RAGSearch(context.Context, service.RAGSearchRequest) (*service.RAGSearchResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) RAGEvidence(context.Context, service.RAGEvidenceRequest) (*service.RAGEvidenceResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) KnowledgeUpload(context.Context, *service.KnowledgeUploadRequest) (*service.KnowledgeUploadResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) GenerationCreate(context.Context, service.GenerationCreateRequest) (*service.GenerationCreateResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) GenerationStatus(context.Context, string) (*service.GenerationStatusResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) GenerateOutline(context.Context, service.OutlineGenerateRequest) (*service.OutlineGenerateResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) StreamOutline(context.Context, service.OutlineGenerateRequest, func(string, []byte) error) error {
	return nil
}
func (m *modifyPersistFakeAI) ReviseOutline(context.Context, service.OutlineReviseAIRequest) (*service.OutlineReviseAIResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) ParseModify(context.Context, service.ParseModifyRequest) (*service.ModifyIntent, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) GenerateContent(context.Context, service.GenContentRequest) (*service.GenContentStatusResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) ContentStatus(context.Context, string) (*service.GenContentStatusResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) VersionHistory(context.Context, string) (*service.VersionHistoryResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) VersionLoad(context.Context, string, int) (*service.VersionSnapshot, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) VersionRollback(context.Context, string, service.VersionRollbackRequest) (*service.VersionRollbackResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) VersionLock(context.Context, string) (*service.VersionLockResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) ExportCreate(context.Context, string, service.ExportCreateRequest) (*service.ExportCreateResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) ExportStatus(context.Context, string) (*service.ExportStatusResponse, error) {
	return nil, nil
}
func (m *modifyPersistFakeAI) GenerationFinalize(context.Context, service.GenerationFinalizeRequest) (*service.GenerationFinalizeResponse, error) {
	return nil, nil
}

// runModifyPersistScenario —— mem 模式下的核心场景，DB 模式复用同一组断言。
func runModifyPersistScenario(t *testing.T, newService func(ai service.AIEngine) (*service.CoursewareService, func())) {
	t.Helper()
	ai := &modifyPersistFakeAI{
		modifyResp: &service.GenerationModifyResponse{
			Status:          "ok",
			VersionNumber:   7,
			CommandsApplied: []string{"rewrite"},
			CitationRefs:    []string{"chunk_001", "chunk_005"},
			EvidenceUsed:    []string{"chunk_005"},
			Nodes: []interface{}{
				map[string]interface{}{
					"node_id":    "page_003",
					"title":      "修改后的页面",
					"summary":    "用 chunk_005 改写后的案例",
					"updated_by": "ai_engine",
				},
			},
		},
	}
	svc, cleanupSvc := newService(ai)
	t.Cleanup(cleanupSvc)
	cw := NewCoursewareHandler(svc)

	gin.SetMode(gin.TestMode)
	r := gin.New()
	v1 := r.Group("/api/v1")
	gen := v1.Group("/gen")
	gen.POST("/modify", NewGenerationHandler(ai, nil, svc).Modify)
	projects := v1.Group("/coursewares")
	projects.GET("/:project_id/latest-generation-context", cw.LatestGenerationContext)
	projects.GET("/:project_id/page-bindings", cw.PageBindingsGet)

	// 准备一个 project，并把它跟 generation_id 绑上（这样 genHandler.Modify
	// 才能按 gen_id 反查到 project 走落库分支）。
	proj, err := svc.CreateProject(context.Background(), "teacher_modify_test", "落 modify 测试")
	if err != nil {
		t.Fatalf("CreateProject 失败: %v", err)
	}
	genID := "gen_" + uuid.NewString()[:8]
	if err := svc.SetGenID(context.Background(), proj.ProjectID, genID); err != nil {
		t.Fatalf("SetGenID 失败: %v", err)
	}

	call := func(method, path, body string) (*httptest.ResponseRecorder, int) {
		var req *http.Request
		if body == "" {
			req = httptest.NewRequest(method, path, nil)
		} else {
			req = httptest.NewRequest(method, path, bytes.NewBufferString(body))
			req.Header.Set("Content-Type", "application/json")
		}
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		return w, w.Code
	}

	// 1) POST /api/v1/gen/modify —— 带 page_id + evidence_refs + user_instruction
	modifyBody := `{
		"generation_id": "` + genID + `",
		"page_id": "page_003",
		"evidence_refs": ["chunk_001", "chunk_005"],
		"user_instruction": "把第三页案例改成生活中的例子"
	}`
	w, code := call(http.MethodPost, "/api/v1/gen/modify", modifyBody)
	if code != http.StatusOK {
		t.Fatalf("POST /gen/modify 期望 200，实际 %d：%s", code, w.Body.String())
	}
	var modifyEnv struct {
		Code int                               `json:"code"`
		Data *service.GenerationModifyResponse `json:"data"`
		Err  string                            `json:"error"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &modifyEnv); err != nil {
		t.Fatalf("modify 响应解析失败: %v", err)
	}
	if modifyEnv.Code != 200 || modifyEnv.Data == nil {
		t.Fatalf("modify 信封不符合契约: %s", w.Body.String())
	}
	if ai.modifyCalls != 1 {
		t.Fatalf("AI GenerationModify 应被调用 1 次，实际 %d", ai.modifyCalls)
	}
	if got := ai.modifyRequest.PageID; got != "page_003" {
		t.Fatalf("AI 收到的 page_id = %q，期望 page_003", got)
	}
	if got := ai.modifyRequest.EvidenceRefs; len(got) != 2 || got[0] != "chunk_001" || got[1] != "chunk_005" {
		t.Fatalf("AI 收到的 evidence_refs = %v，期望 [chunk_001 chunk_005]", got)
	}

	// 2) GET /latest-generation-context —— 验证版本落库 + 绑定回写
	ctxPath := "/api/v1/coursewares/" + proj.ProjectID + "/latest-generation-context"
	w2, code2 := call(http.MethodGet, ctxPath, "")
	if code2 != http.StatusOK {
		t.Fatalf("GET latest-generation-context 期望 200，实际 %d：%s", code2, w2.Body.String())
	}
	var ctxEnv struct {
		Code int                        `json:"code"`
		Data *service.GenerationContext `json:"data"`
		Err  string                     `json:"error"`
	}
	if err := json.Unmarshal(w2.Body.Bytes(), &ctxEnv); err != nil {
		t.Fatalf("ctx 响应解析失败: %v", err)
	}
	if ctxEnv.Code != 200 || ctxEnv.Data == nil {
		t.Fatalf("ctx 信封不符合契约: %s", w2.Body.String())
	}
	got := ctxEnv.Data
	if got.ProjectID != proj.ProjectID {
		t.Fatalf("ctx.project_id = %q，期望 %q", got.ProjectID, proj.ProjectID)
	}
	if got.GenerationID != genID {
		t.Fatalf("ctx.generation_id = %q，期望 %q", got.GenerationID, genID)
	}
	if got.VersionNo != 1 {
		t.Fatalf("ctx.version_no = %d，期望 1", got.VersionNo)
	}
	if got.PageID != "page_003" {
		t.Fatalf("ctx.page_id = %q，期望 page_003", got.PageID)
	}
	if len(got.EvidenceRefs) != 2 || got.EvidenceRefs[0] != "chunk_001" || got.EvidenceRefs[1] != "chunk_005" {
		t.Fatalf("ctx.evidence_refs = %v，期望 [chunk_001 chunk_005]", got.EvidenceRefs)
	}
	if len(got.CitationRefs) != 2 || got.CitationRefs[0] != "chunk_001" || got.CitationRefs[1] != "chunk_005" {
		t.Fatalf("ctx.citation_refs = %v，期望 [chunk_001 chunk_005]", got.CitationRefs)
	}
	if len(got.EvidenceUsed) != 1 || got.EvidenceUsed[0] != "chunk_005" {
		t.Fatalf("ctx.evidence_used = %v，期望 [chunk_005]", got.EvidenceUsed)
	}
	if len(got.PageBindings) != 1 || got.PageBindings[0].PageID != "page_003" {
		t.Fatalf("ctx.page_bindings = %+v，期望含 page_003 一条", got.PageBindings)
	}
	if got.LatestVersion == nil {
		t.Fatalf("ctx.latest_version 不应为空")
	}
	if got.LatestVersion.ModifyInstr != "把第三页案例改成生活中的例子" {
		t.Fatalf("ctx.latest_version.modify_instruction = %q，期望用户指令原文",
			got.LatestVersion.ModifyInstr)
	}
}

// TestGenModifyPersistsAndExposesViaLatestContext —— 内存模式（无 DB 依赖）。
func TestGenModifyPersistsAndExposesViaLatestContext(t *testing.T) {
	runModifyPersistScenario(t, func(ai service.AIEngine) (*service.CoursewareService, func()) {
		svc := service.NewCoursewareService(ai)
		return svc, func() {}
	})
}

// TestGenModifyPersistsAndExposesViaLatestContextPG —— 真实 PostgreSQL 端到端。
// 用法：COURSEWARE_PG_DSN=... go test ./internal/handler -run TestGenModifyPersistsAndExposesViaLatestContextPG -count=1 -v
func TestGenModifyPersistsAndExposesViaLatestContextPG(t *testing.T) {
	dsn := os.Getenv("COURSEWARE_PG_DSN")
	if dsn == "" {
		t.Skip("未设置 COURSEWARE_PG_DSN，跳过真实库验证")
	}
	runModifyPersistScenario(t, func(ai service.AIEngine) (*service.CoursewareService, func()) {
		db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
		if err != nil {
			t.Fatalf("连接 PostgreSQL 失败: %v", err)
		}
		if sqlDB, err := db.DB(); err == nil {
			t.Cleanup(func() { _ = sqlDB.Close() })
		}
		if err := service.AutoMigrateCourseware(db); err != nil {
			t.Fatalf("AutoMigrateCourseware 失败: %v", err)
		}
		svc := service.NewCoursewareServiceWithDB(ai, db)
		return svc, func() {}
	})
}
