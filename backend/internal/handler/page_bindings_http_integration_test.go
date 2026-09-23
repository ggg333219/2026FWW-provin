package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"sort"
	"testing"

	"github.com/gin-gonic/gin"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"smart-teaching-backend/internal/service"
)

// 契约 v1.0 模块1 接口1/接口2 的端到端验证：HTTP → handler → gorm → 真实 PostgreSQL。
//
// 单测里的 page_bindings_contract_test.go 走的是 mem store（进程内 map），
// 只能证明业务逻辑；这里额外验证路由信封、真实建表与 ON CONFLICT upsert，
// 并覆盖契约验收标准——绑定后"刷新页面"（重开连接）绑定关系仍在。
//
// 路由注册方式与 router.RegisterNewSkillRoutes 中的 coursewares 组一致。
//
// 用法：
//
//	COURSEWARE_PG_DSN="postgres://postgres:123456@127.0.0.1:25432/teaching_test?sslmode=disable" \
//	    go test ./internal/handler/ -run TestPageBindingsHTTPOverPostgres -count=1 -v
func TestPageBindingsHTTPOverPostgres(t *testing.T) {
	dsn := os.Getenv("COURSEWARE_PG_DSN")
	if dsn == "" {
		t.Skip("未设置 COURSEWARE_PG_DSN，跳过真实库验证")
	}
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

	gin.SetMode(gin.TestMode)
	r := gin.New()
	svc := service.NewCoursewareServiceWithDB(nil, db)
	group := r.Group("/api/v1/coursewares")
	group.PUT("/:project_id/page-bindings", NewCoursewareHandler(svc).PageBindingsPut)
	group.GET("/:project_id/page-bindings", NewCoursewareHandler(svc).PageBindingsGet)

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

	proj, err := svc.CreateProject(context.Background(), "teacher_test", "契约模块1端到端")
	if err != nil {
		t.Fatalf("创建项目失败: %v", err)
	}
	t.Cleanup(func() { _ = svc.DeleteProject(context.Background(), proj.ProjectID) })
	base := "/api/v1/coursewares/" + proj.ProjectID + "/page-bindings"

	// 接口1：保存绑定
	w, code := call(http.MethodPut, base, `{
		"page_bindings": {
			"page_003": {"evidence_refs": ["chunk_001", "chunk_002"], "auto_bound": false, "bound_by": "user:teacher_test"},
			"page_001": {"evidence_refs": ["chunk_003"], "auto_bound": true, "bound_by": "system:intent_keyword"}
		}}`)
	if code != http.StatusOK {
		t.Fatalf("PUT 期望 200，实际 %d：%s", code, w.Body.String())
	}
	var putEnv struct {
		OK   bool `json:"ok"`
		Data struct {
			UpdatedPages []string `json:"updated_pages"`
		} `json:"data"`
		Err  string `json:"error"`
		Code int    `json:"code"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &putEnv); err != nil {
		t.Fatalf("PUT 响应解析失败: %v", err)
	}
	if !putEnv.OK || putEnv.Err != "" || putEnv.Code != 200 || len(putEnv.Data.UpdatedPages) != 2 {
		t.Fatalf("PUT 响应不符合契约信封: %s", w.Body.String())
	}
	if got := putEnv.Data.UpdatedPages; !sort.StringsAreSorted(got) {
		t.Fatalf("updated_pages 未按序返回: %v", got)
	}

	// 契约验收：重新建一个连接（等价于刷新页面/服务重启）后绑定关系仍在
	db2, err := gorm.Open(postgres.Open(dsn), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
	if err != nil {
		t.Fatalf("重连 PostgreSQL 失败: %v", err)
	}
	if sqlDB, err := db2.DB(); err == nil {
		t.Cleanup(func() { _ = sqlDB.Close() })
	}
	svc2 := service.NewCoursewareServiceWithDB(nil, db2)
	r2 := gin.New()
	group2 := r2.Group("/api/v1/coursewares")
	group2.GET("/:project_id/page-bindings", NewCoursewareHandler(svc2).PageBindingsGet)
	w2 := httptest.NewRecorder()
	r2.ServeHTTP(w2, httptest.NewRequest(http.MethodGet, base, nil))
	if w2.Code != http.StatusOK {
		t.Fatalf("重连后 GET 期望 200，实际 %d：%s", w2.Code, w2.Body.String())
	}
	var gotEnv struct {
		OK   bool `json:"ok"`
		Data struct {
			PageBindings map[string]service.PageEvidenceBinding `json:"page_bindings"`
		} `json:"data"`
		Err string `json:"error"`
	}
	if err := json.Unmarshal(w2.Body.Bytes(), &gotEnv); err != nil {
		t.Fatalf("GET 响应解析失败: %v", err)
	}
	if !gotEnv.OK || gotEnv.Err != "" {
		t.Fatalf("GET 响应不符合契约信封: %s", w2.Body.String())
	}
	bindings := gotEnv.Data.PageBindings
	if len(bindings) != 2 {
		t.Fatalf("重连后应有 2 个页面的绑定，实际 %d: %+v", len(bindings), bindings)
	}
	b3 := bindings["page_003"]
	if b3.PageID != "page_003" || len(b3.EvidenceRefs) != 2 || b3.AutoBound || b3.BoundBy != "user:teacher_test" || b3.BoundAt.IsZero() {
		t.Fatalf("page_003 绑定未跨连接持久化: %+v", b3)
	}
	b1 := bindings["page_001"]
	if len(b1.EvidenceRefs) != 1 || !b1.AutoBound || b1.BoundBy != "system:intent_keyword" {
		t.Fatalf("page_001 绑定未跨连接持久化: %+v", b1)
	}

	// 接口2：契约错误码 404（资源不存在）
	if _, code := call(http.MethodGet, "/api/v1/coursewares/proj_missing/page-bindings", ""); code != http.StatusNotFound {
		t.Fatalf("不存在的项目 GET 期望 404，实际 %d", code)
	}
	// 契约错误码 400（参数错误）
	if _, code := call(http.MethodPut, base, `{"page_bindings": null}`); code != http.StatusBadRequest {
		t.Fatalf("空 page_bindings 期望 400，实际 %d", code)
	}
}
