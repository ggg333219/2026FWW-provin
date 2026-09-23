package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// 契约 v1.0 模块1：页面级资料绑定（接口1 PUT / 接口2 GET /coursewares/:project_id/page-bindings）。
//
// 覆盖验收标准：
//	上传 PDF → 解析成 chunk → 勾选绑定到第3页 → 刷新页面后绑定关系还在（持久化往返）。

func newPageBindingsTestEngine() (*gin.Engine, *service.CoursewareService) {
	gin.SetMode(gin.TestMode)
	svc := service.NewCoursewareService(nil) // mem store 降级路径
	h := NewCoursewareHandler(svc)
	r := gin.New()
	projects := r.Group("/api/v1/coursewares")
	projects.PUT("/:project_id/page-bindings", h.PageBindingsPut)
	projects.GET("/:project_id/page-bindings", h.PageBindingsGet)
	return r, svc
}

func doPageBindings(t *testing.T, r *gin.Engine, method, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	var req *http.Request
	if body == "" {
		req = httptest.NewRequest(method, path, nil)
	} else {
		req = httptest.NewRequest(method, path, bytes.NewBufferString(body))
		req.Header.Set("Content-Type", "application/json")
	}
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	return w
}

func createProject(t *testing.T, svc *service.CoursewareService) string {
	t.Helper()
	p, err := svc.CreateProject(context.Background(), "teacher_demo", "契约模块1测试课件")
	if err != nil {
		t.Fatalf("创建课件项目失败: %v", err)
	}
	return p.ProjectID
}

func TestPageBindingsPutGetRoundTrip(t *testing.T) {
	r, svc := newPageBindingsTestEngine()
	projectID := createProject(t, svc)

	w := doPageBindings(t, r, http.MethodPut, "/api/v1/coursewares/"+projectID+"/page-bindings", `{
		"page_bindings": {
			"page_001": {"evidence_refs": ["chunk_001", "chunk_002"], "auto_bound": false, "bound_by": "user:teacher_demo"},
			"page_002": {"evidence_refs": ["chunk_003"], "auto_bound": true, "bound_by": "system:intent_keyword"}
		}
	}`)
	if w.Code != http.StatusOK {
		t.Fatalf("PUT 期望 200，实际 %d：%s", w.Code, w.Body.String())
	}
	var envelope struct {
		OK   bool           `json:"ok"`
		Data map[string]any `json:"data"`
		Err  string         `json:"error"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("PUT 响应解析失败: %v", err)
	}
	if !envelope.OK || envelope.Err != "" {
		t.Fatalf("PUT 响应未按契约返回 ok=true / error 为空: %+v", envelope)
	}
	rawUpdated, err := json.Marshal(envelope.Data["updated_pages"])
	if err != nil {
		t.Fatalf("updated_pages 编码失败: %v", err)
	}
	var updated []string
	if err := json.Unmarshal(rawUpdated, &updated); err != nil {
		t.Fatalf("updated_pages 不是字符串数组: %s", rawUpdated)
	}
	if len(updated) != 2 {
		t.Fatalf("updated_pages 应有 2 项，实际 %d: %v", len(updated), updated)
	}

	// 契约验收：刷新页面后绑定关系还在（重新 GET 一次）
	w = doPageBindings(t, r, http.MethodGet, "/api/v1/coursewares/"+projectID+"/page-bindings", "")
	if w.Code != http.StatusOK {
		t.Fatalf("GET 期望 200，实际 %d：%s", w.Code, w.Body.String())
	}
	var gotEnv struct {
		OK   bool `json:"ok"`
		Data struct {
			PageBindings map[string]service.PageEvidenceBinding `json:"page_bindings"`
		} `json:"data"`
		Err string `json:"error"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &gotEnv); err != nil {
		t.Fatalf("GET 响应解析失败: %v", err)
	}
	if !gotEnv.OK || gotEnv.Err != "" {
		t.Fatalf("GET 响应未按契约返回 ok=true / error 为空: %+v", gotEnv)
	}
	bindings := gotEnv.Data.PageBindings
	if len(bindings) != 2 {
		t.Fatalf("应返回 2 个页面的绑定，实际 %d: %+v", len(bindings), bindings)
	}
	b1 := bindings["page_001"]
	if b1.PageID != "page_001" || len(b1.EvidenceRefs) != 2 || b1.AutoBound || b1.BoundBy != "user:teacher_demo" {
		t.Fatalf("page_001 绑定字段不符: %+v", b1)
	}
	if b1.BoundAt.IsZero() {
		t.Fatalf("bound_at 应被服务端填充: %+v", b1)
	}
	b2 := bindings["page_002"]
	if len(b2.EvidenceRefs) != 1 || !b2.AutoBound || b2.BoundBy != "system:intent_keyword" {
		t.Fatalf("page_002 绑定字段不符: %+v", b2)
	}
}

func TestPageBindingsUpsertMergesAndClears(t *testing.T) {
	r, svc := newPageBindingsTestEngine()
	projectID := createProject(t, svc)
	base := "/api/v1/coursewares/" + projectID + "/page-bindings"

	if w := doPageBindings(t, r, http.MethodPut, base, `{
		"page_bindings": {
			"page_001": {"evidence_refs": ["chunk_001", "chunk_002"]},
			"page_002": {"evidence_refs": ["chunk_003"]}
		}}`); w.Code != http.StatusOK {
		t.Fatalf("首次 PUT 失败: %d %s", w.Code, w.Body.String())
	}
	// 只更新 page_001：清空其证据；page_002 不应被触及。
	if w := doPageBindings(t, r, http.MethodPut, base, `{
		"page_bindings": {"page_001": {"evidence_refs": []}}}`); w.Code != http.StatusOK {
		t.Fatalf("二次 PUT 失败: %d %s", w.Code, w.Body.String())
	}

	bindings, err := svc.GetPageBindings(context.Background(), projectID)
	if err != nil {
		t.Fatalf("读取绑定失败: %v", err)
	}
	if len(bindings) != 2 {
		t.Fatalf("upsert 后应有 2 个页面，实际 %d: %+v", len(bindings), bindings)
	}
	if refs := bindings["page_001"].EvidenceRefs; len(refs) != 0 {
		t.Fatalf("page_001 证据应被清空，实际 %v", refs)
	}
	if refs := bindings["page_002"].EvidenceRefs; len(refs) != 1 || refs[0] != "chunk_003" {
		t.Fatalf("page_002 不应被本次 PUT 影响，实际 %v", refs)
	}
}

func TestPageBindingsProjectNotFound(t *testing.T) {
	r, _ := newPageBindingsTestEngine()
	if w := doPageBindings(t, r, http.MethodGet, "/api/v1/coursewares/proj_missing/page-bindings", ""); w.Code != http.StatusNotFound {
		t.Fatalf("不存在的课件项目 GET 期望 404，实际 %d：%s", w.Code, w.Body.String())
	}
	if w := doPageBindings(t, r, http.MethodPut, "/api/v1/coursewares/proj_missing/page-bindings",
		`{"page_bindings": {"page_001": {"evidence_refs": ["chunk_001"]}}}`); w.Code != http.StatusNotFound {
		t.Fatalf("不存在的课件项目 PUT 期望 404，实际 %d：%s", w.Code, w.Body.String())
	}
}

func TestPageBindingsValidation(t *testing.T) {
	r, svc := newPageBindingsTestEngine()
	projectID := createProject(t, svc)
	base := "/api/v1/coursewares/" + projectID + "/page-bindings"

	for _, tc := range []struct{ name, body string }{
		{"缺少 page_bindings", "{}"},
		{"page_bindings 为 null", `{"page_bindings": null}`},
		{"非法 JSON", `{"page_bindings": {"page_001": {"evidence_refs": }`},
	} {
		t.Run(tc.name, func(t *testing.T) {
			w := doPageBindings(t, r, http.MethodPut, base, tc.body)
			if w.Code != http.StatusBadRequest {
				t.Fatalf("期望 400，实际 %d：%s", w.Code, w.Body.String())
			}
			var env struct {
				OK    bool   `json:"ok"`
				Error string `json:"error"`
			}
			if err := json.Unmarshal(w.Body.Bytes(), &env); err != nil {
				t.Fatalf("400 响应解析失败: %v", err)
			}
			if env.OK {
				t.Fatalf("400 响应不应带 ok=true: %s", w.Body.String())
			}
			if env.Error == "" {
				t.Fatalf("400 响应应给出错误描述: %s", w.Body.String())
			}
		})
	}
}

func TestPageBindingsContractJSONFields(t *testing.T) {
	// 契约 §4.1：字段名严格对齐，不得私自修改
	b := service.PageEvidenceBinding{
		PageID: "page_001", EvidenceRefs: []string{"chunk_001"},
		AutoBound: false, BoundBy: "user:teacher_demo",
	}
	raw, err := json.Marshal(b)
	if err != nil {
		t.Fatalf("序列化失败: %v", err)
	}
	var want map[string]any
	if err := json.Unmarshal(raw, &want); err != nil {
		t.Fatalf("反序列化失败: %v", err)
	}
	for _, field := range []string{"page_id", "evidence_refs", "auto_bound", "bound_by", "bound_at"} {
		if _, ok := want[field]; !ok {
			t.Fatalf("缺少契约字段 %s: %s", field, raw)
		}
	}
}

func TestPageBindingsDeleteProjectCascade(t *testing.T) {
	_, svc := newPageBindingsTestEngine()
	projectID := createProject(t, svc)
	if _, err := svc.SavePageBindings(context.Background(), projectID, []service.PageEvidenceBinding{
		{PageID: "page_001", EvidenceRefs: []string{"chunk_001"}},
	}); err != nil {
		t.Fatalf("保存绑定失败: %v", err)
	}
	if err := svc.DeleteProject(context.Background(), projectID); err != nil {
		t.Fatalf("删除项目失败: %v", err)
	}
	if _, err := svc.GetPageBindings(context.Background(), projectID); err == nil {
		t.Fatalf("项目删除后不应再能读取绑定")
	}
}
