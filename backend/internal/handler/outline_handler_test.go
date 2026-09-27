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

// ---- 与 service 测试同构的 fake（满足 service 的窄 outlineClient 接口）----

type fakeAIOutline struct {
	nodes []service.OutlineNode
}

func (f *fakeAIOutline) GenerateOutline(_ context.Context, _ service.OutlineGenerateRequest) (*service.OutlineGenerateResponse, error) {
	if f.nodes == nil {
		f.nodes = []service.OutlineNode{
			{NodeID: "node_001", Order: 1, Title: "引言", Summary: "导入", NodeType: "content", EstimatedDurationMin: 5},
			{NodeID: "node_002", Order: 2, Title: "主算法", Summary: "核心", NodeType: "section", EstimatedDurationMin: 20},
		}
	}
	return &service.OutlineGenerateResponse{Nodes: f.nodes}, nil
}

func (f *fakeAIOutline) ReviseOutline(_ context.Context, _ service.OutlineReviseAIRequest) (*service.OutlineReviseAIResponse, error) {
	return &service.OutlineReviseAIResponse{Nodes: f.nodes, ChangeSummary: []string{"AI 修订"}}, nil
}

func setupOutlineRouter(t *testing.T) *gin.Engine {
	t.Helper()
	gin.SetMode(gin.TestMode)
	svc := service.NewOutlineService(&fakeAIOutline{})
	h := NewOutlineHandler(svc)
	r := gin.New()
	// 复刻 router/teacher.go 的 outlines 路由组
	g := r.Group("/api/v1/outlines")
	{
		g.POST("", h.Create)
		g.GET("/:outline_id", h.Get)
		g.PUT("/:outline_id", h.Save)
		g.POST("/:outline_id/revise", h.Revise)
		g.POST("/:outline_id/confirm", h.Confirm)
	}
	return r
}

func doJSON(t *testing.T, r *gin.Engine, method, path, body string) *httptest.ResponseRecorder {
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

func mustCreate(t *testing.T, r *gin.Engine) string {
	t.Helper()
	w := doJSON(t, r, "POST", "/api/v1/outlines", `{
		"session_id": "session_1",
		"intent": {"topic": "排序算法", "duration_minutes": 45},
		"evidence_packet": {},
		"markdown": ""
	}`)
	if w.Code != http.StatusOK {
		t.Fatalf("创建大纲 HTTP %d: %s", w.Code, w.Body.String())
	}
	var resp struct {
		Code int `json:"code"`
		Data struct {
			OutlineID string `json:"outline_id"`
		} `json:"data"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("解析响应失败: %v", err)
	}
	if resp.Code != 200 || resp.Data.OutlineID == "" {
		t.Fatalf("响应异常: %+v", resp)
	}
	return resp.Data.OutlineID
}

// TestOutlineCreate_Code200 —— POST /api/v1/outlines 成功返回 {code:200, data:{outline_id...}}。
func TestOutlineCreate_Code200(t *testing.T) {
	r := setupOutlineRouter(t)
	w := doJSON(t, r, "POST", "/api/v1/outlines", `{
		"session_id": "session_1",
		"intent": {"topic": "排序算法"},
		"evidence_packet": {},
		"markdown": ""
	}`)
	if w.Code != http.StatusOK {
		t.Fatalf("期望 200, 实际 %d: %s", w.Code, w.Body.String())
	}
	var resp struct {
		Code int `json:"code"`
		Data struct {
			OutlineID    string `json:"outline_id"`
			OutlineVersion int  `json:"outline_version"`
			Status       string `json:"status"`
			Nodes        []any  `json:"nodes"`
		} `json:"data"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if resp.Code != 200 {
		t.Fatalf("业务 code 应为 200, 实际 %d", resp.Code)
	}
	if resp.Data.OutlineID == "" || resp.Data.OutlineVersion != 1 || resp.Data.Status != "draft" {
		t.Fatalf("大纲元数据不符: %+v", resp.Data)
	}
	if len(resp.Data.Nodes) == 0 {
		t.Fatal("大纲应包含节点")
	}
}

// TestOutlineCreate_MissingSession —— 缺 session_id → 400。
func TestOutlineCreate_MissingSession(t *testing.T) {
	r := setupOutlineRouter(t)
	w := doJSON(t, r, "POST", "/api/v1/outlines", `{"intent":{}}`)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("缺 session_id 应 400, 实际 %d", w.Code)
	}
}

// TestOutlineGet_ByID —— 创建后 GET 可读回。
func TestOutlineGet_ByID(t *testing.T) {
	r := setupOutlineRouter(t)
	id := mustCreate(t, r)
	w := doJSON(t, r, "GET", "/api/v1/outlines/"+id, "")
	if w.Code != http.StatusOK {
		t.Fatalf("GET 大纲 HTTP %d: %s", w.Code, w.Body.String())
	}
}

// TestOutlineGet_NotFound —— 不存在的 outline_id → 404。
func TestOutlineGet_NotFound(t *testing.T) {
	r := setupOutlineRouter(t)
	w := doJSON(t, r, "GET", "/api/v1/outlines/outline_nope", "")
	if w.Code != http.StatusNotFound {
		t.Fatalf("不存在大纲应 404, 实际 %d", w.Code)
	}
}

// TestOutlineConfirmFlow_HTTP —— 创建 → 确认 → code 200 + status=confirmed。
func TestOutlineConfirmFlow_HTTP(t *testing.T) {
	r := setupOutlineRouter(t)
	id := mustCreate(t, r)

	w := doJSON(t, r, "POST", "/api/v1/outlines/"+id+"/confirm", `{"outline_version":1}`)
	if w.Code != http.StatusOK {
		t.Fatalf("确认大纲 HTTP %d: %s", w.Code, w.Body.String())
	}
	var resp struct {
		Code int `json:"code"`
		Data struct {
			Status string `json:"status"`
		} `json:"data"`
	}
	_ = json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Data.Status != "confirmed" {
		t.Fatalf("确认后 status 应为 confirmed, 实际 %s", resp.Data.Status)
	}
}

// TestOutlineSave_VersionConflict_409 —— base_version 错误 → 409。
func TestOutlineSave_VersionConflict_409(t *testing.T) {
	r := setupOutlineRouter(t)
	id := mustCreate(t, r)

	body := `{
		"base_version": 99,
		"nodes": [{"node_id":"node_001","order":1,"title":"引言","summary":"导入","node_type":"content","key_points":[],"estimated_duration_minutes":5}]
	}`
	w := doJSON(t, r, "PUT", "/api/v1/outlines/"+id, body)
	if w.Code != http.StatusConflict {
		t.Fatalf("base_version 冲突应 409, 实际 %d: %s", w.Code, w.Body.String())
	}
}

// TestOutlineSave_InvalidNode_422 —— node_id 重复 → 422。
func TestOutlineSave_InvalidNode_422(t *testing.T) {
	r := setupOutlineRouter(t)
	id := mustCreate(t, r)

	body := `{
		"base_version": 1,
		"nodes": [
			{"node_id":"node_x","order":1,"title":"A","summary":"s","node_type":"content","estimated_duration_minutes":5},
			{"node_id":"node_x","order":2,"title":"B","summary":"s","node_type":"content","estimated_duration_minutes":5}
		]
	}`
	w := doJSON(t, r, "PUT", "/api/v1/outlines/"+id, body)
	if w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("node_id 重复应 422, 实际 %d: %s", w.Code, w.Body.String())
	}
}

// TestOutlineRevise_HTTP —— revise 返回候选版本（version+1, draft, 不落库）。
func TestOutlineRevise_HTTP(t *testing.T) {
	r := setupOutlineRouter(t)
	id := mustCreate(t, r)

	w := doJSON(t, r, "POST", "/api/v1/outlines/"+id+"/revise", `{
		"message": "加个生活案例",
		"base_version": 1,
		"auto_apply": false
	}`)
	if w.Code != http.StatusOK {
		t.Fatalf("revise HTTP %d: %s", w.Code, w.Body.String())
	}
	var resp struct {
		Code int `json:"code"`
		Data struct {
			OutlineVersion int    `json:"outline_version"`
			Status         string `json:"status"`
			Nodes          []any  `json:"nodes"`
		} `json:"data"`
	}
	_ = json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Data.OutlineVersion != 2 || resp.Data.Status != "draft" {
		t.Fatalf("修订候选应 v2/draft, 实际 v%d/%s", resp.Data.OutlineVersion, resp.Data.Status)
	}
}
