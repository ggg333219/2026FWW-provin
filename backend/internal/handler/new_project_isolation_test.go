package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// TestNewProjectLatestContextIsClean ——
// 新建项目（无 version / 无 binding）调 latest-generation-context，
// 必须返回干净的空状态，作为前端"刷新 + 隔离"的权威读源。
func TestNewProjectLatestContextIsClean(t *testing.T) {
	svc := service.NewCoursewareService(&modifyPersistFakeAI{})
	cw := NewCoursewareHandler(svc)
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.GET("/api/v1/coursewares/:project_id/latest-generation-context", cw.LatestGenerationContext)

	proj, err := svc.CreateProject(context.Background(), "teacher_fresh", "新课件")
	if err != nil {
		t.Fatalf("CreateProject: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet,
		"/api/v1/coursewares/"+proj.ProjectID+"/latest-generation-context", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("期望 200 实际 %d: %s", w.Code, w.Body.String())
	}
	var env struct {
		Code int                        `json:"code"`
		Data *service.GenerationContext `json:"data"`
		Err  string                     `json:"error"`
	}
	_ = json.Unmarshal(w.Body.Bytes(), &env)
	if env.Code != 200 || env.Data == nil {
		t.Fatalf("信封不符: %s", w.Body.String())
	}
	got := env.Data
	if got.VersionNo != 0 {
		t.Errorf("新项目 version_no 应为 0，实际 %d", got.VersionNo)
	}
	if got.VersionID != "" {
		t.Errorf("新项目 version_id 应为空，实际 %q", got.VersionID)
	}
	if got.PageID != "" {
		t.Errorf("新项目 page_id 应为空，实际 %q", got.PageID)
	}
	if len(got.EvidenceRefs) != 0 {
		t.Errorf("新项目 evidence_refs 应为空，实际 %v", got.EvidenceRefs)
	}
	if len(got.CitationRefs) != 0 {
		t.Errorf("新项目 citation_refs 应为空，实际 %v", got.CitationRefs)
	}
	if len(got.PageBindings) != 0 {
		t.Errorf("新项目 page_bindings 应为空，实际 %v", got.PageBindings)
	}
	if got.LatestVersion != nil {
		t.Errorf("新项目 latest_version 应为 nil，实际 %+v", got.LatestVersion)
	}
	fmt.Printf("✅ 新项目 latest-generation-context 返回干净空状态：version_no=%d, bindings=%d\n",
		got.VersionNo, len(got.PageBindings))
}

// TestNewProjectAfterOldProjectHasNoLeak ——
// 顺序：A 项目走完 modify（有 version+binding）→ 创建 B 项目 → 查 B 的上下文
// 必须返回 B 自己的空状态，绝不能带 A 的残留。这是"切 PPT 不重置 / 新建课件
// 显示之前缓存"问题的后端权威验证。
func TestNewProjectAfterOldProjectHasNoLeak(t *testing.T) {
	svc := service.NewCoursewareService(&modifyPersistFakeAI{})
	cw := NewCoursewareHandler(svc)
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.GET("/api/v1/coursewares/:project_id/latest-generation-context", cw.LatestGenerationContext)
	r.GET("/api/v1/coursewares/:project_id/page-bindings", cw.PageBindingsGet)

	// --- A 项目：手动塞一份 version + binding（不依赖 AI Engine，避免与 modify
	// 测试耦合；这里直接调底层 Service API 模拟"已落库"的状态）。
	projA, err := svc.CreateProject(context.Background(), "teacher_A", "A 课件")
	if err != nil {
		t.Fatalf("CreateProject A: %v", err)
	}
	if err := svc.SetGenID(context.Background(), projA.ProjectID, "gen_A"); err != nil {
		t.Fatalf("A.SetGenID: %v", err)
	}
	if _, err := svc.SavePageBindings(context.Background(), projA.ProjectID, []service.PageEvidenceBinding{
		{PageID: "page_007", EvidenceRefs: []string{"chunk_LEAK"}},
	}); err != nil {
		t.Fatalf("A.SavePageBindings: %v", err)
	}

	// --- B 项目：新建一个全新的。
	projB, err := svc.CreateProject(context.Background(), "teacher_B", "B 课件")
	if err != nil {
		t.Fatalf("CreateProject B: %v", err)
	}

	// --- 验证 B 的 latest-generation-context 绝不带 A 的痕迹
	req := httptest.NewRequest(http.MethodGet,
		"/api/v1/coursewares/"+projB.ProjectID+"/latest-generation-context", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("B 期望 200 实际 %d: %s", w.Code, w.Body.String())
	}
	var env struct {
		Data *service.GenerationContext `json:"data"`
	}
	_ = json.Unmarshal(w.Body.Bytes(), &env)
	if env.Data == nil {
		t.Fatalf("B 响应无 data: %s", w.Body.String())
	}
	if env.Data.VersionNo != 0 {
		t.Errorf("B.version_no 应为 0，实际 %d（从 A 漏过来的！）", env.Data.VersionNo)
	}
	if len(env.Data.PageBindings) != 0 {
		t.Errorf("B.page_bindings 应为空，实际 %+v（从 A 漏过来的！）", env.Data.PageBindings)
	}
	for _, b := range env.Data.PageBindings {
		if b.PageID == "page_007" || contains(b.EvidenceRefs, "chunk_LEAK") {
			t.Errorf("B 居然含有 A 的绑定 %+v", b)
		}
	}

	// --- 再核一遍 A 自己读出来的还是干净的（防止测试间串扰）
	reqA := httptest.NewRequest(http.MethodGet,
		"/api/v1/coursewares/"+projA.ProjectID+"/latest-generation-context", nil)
	wA := httptest.NewRecorder()
	r.ServeHTTP(wA, reqA)
	var envA struct {
		Data *service.GenerationContext `json:"data"`
	}
	_ = json.Unmarshal(wA.Body.Bytes(), &envA)
	if envA.Data == nil || len(envA.Data.PageBindings) != 1 || envA.Data.PageBindings[0].PageID != "page_007" {
		t.Errorf("A 自身绑定异常，应有 page_007/chunk_LEAK，实际 %+v", envA.Data.PageBindings)
	}

	fmt.Printf("✅ A→B 切换：A 有 1 条绑定；B 干净（version_no=%d, bindings=%d），无泄漏\n",
		env.Data.VersionNo, len(env.Data.PageBindings))
}

func contains(s []string, v string) bool {
	for _, x := range s {
		if x == v {
			return true
		}
	}
	return false
}