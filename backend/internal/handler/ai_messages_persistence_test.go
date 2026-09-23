package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"smart-teaching-backend/internal/service"
)

// 契约 v1.0 §3.2：AI 对话气泡按 project_id 持久化——切 PPT / 刷新后能再拉回来。
//
// 本测试覆盖两条端到端路径：
//   POST /api/v1/coursewares/:project_id/ai-messages  幂等 upsert 一批气泡
//   GET  /api/v1/coursewares/:project_id/ai-messages  按时间升序读全部
//   DELETE /api/v1/coursewares/:project_id/ai-messages 清空（reset 时调用）
//
// 验证重点：
//  - 同 message_id 重发不会产生重复
//  - 时间升序正确
//  - role/intent/version_no 等字段保留
//  - 新项目返回空列表，不会拿到其它项目的对话
//
// 同时覆盖 mem store 与真 PostgreSQL（COURSEWARE_PG_DSN）。

func runAIMessagesScenario(t *testing.T, newService func(ai service.AIEngine) (*service.CoursewareService, func())) {
	t.Helper()
	ai := &modifyPersistFakeAI{}
	svc, cleanupSvc := newService(ai)
	t.Cleanup(cleanupSvc)
	cw := NewCoursewareHandler(svc)
	gin.SetMode(gin.TestMode)
	r := gin.New()
	v1 := r.Group("/api/v1")
	projects := v1.Group("/coursewares")
	projects.GET("/:project_id/ai-messages", cw.AIMessagesList)
	projects.POST("/:project_id/ai-messages", cw.AIMessagesUpsert)
	projects.DELETE("/:project_id/ai-messages", cw.AIMessagesClear)

	proj, err := svc.CreateProject(context.Background(), "teacher_aimsg", "AI 对话测试")
	if err != nil {
		t.Fatalf("CreateProject 失败: %v", err)
	}

	call := func(method, path, body string) *httptest.ResponseRecorder {
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

	now := time.Now().UTC().Truncate(time.Second)
	intent := &service.ModifyIntent{Action: "rewrite", TargetIDs: []string{"page_003"}}
	intentJSON, _ := json.Marshal(intent)

	// 1) 一次性 upsert 三条气泡（teacher + ai summary + ai 错误 → 验证三种类型都进库）
	upsertBody := `{
		"messages": [
			{ "message_id": "` + uuid.NewString() + `", "role": "teacher", "text": "把第三页换成生活案例", "created_at": "` + now.Format(time.RFC3339) + `" },
			{ "message_id": "` + uuid.NewString() + `", "role": "ai",     "text": "已更新：第三页", "is_summary": true, "version_no": 3, "intent": ` + string(intentJSON) + `, "created_at": "` + now.Add(1*time.Second).Format(time.RFC3339) + `" },
			{ "message_id": "` + uuid.NewString() + `", "role": "ai",     "text": "⚠️ AI 暂时不可用", "is_error": true, "created_at": "` + now.Add(2*time.Second).Format(time.RFC3339) + `" }
		]
	}`
	w := call(http.MethodPost, "/api/v1/coursewares/"+proj.ProjectID+"/ai-messages", upsertBody)
	if w.Code != http.StatusOK {
		t.Fatalf("POST ai-messages 期望 200 实际 %d：%s", w.Code, w.Body.String())
	}

	// 2) GET 验证列表按 created_at 升序，role/is_summary/version_no 都保留
	w = call(http.MethodGet, "/api/v1/coursewares/"+proj.ProjectID+"/ai-messages", "")
	if w.Code != http.StatusOK {
		t.Fatalf("GET ai-messages 期望 200 实际 %d：%s", w.Code, w.Body.String())
	}
	var env struct {
		Code int                       `json:"code"`
		Data struct {
			Messages []service.AIMessageItem `json:"messages"`
		} `json:"data"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &env); err != nil {
		t.Fatalf("ai-messages 响应解析失败: %v", err)
	}
	if env.Code != 200 || len(env.Data.Messages) != 3 {
		t.Fatalf("期望 3 条气泡，实际 %d：%s", len(env.Data.Messages), w.Body.String())
	}
	if env.Data.Messages[0].Role != "teacher" {
		t.Errorf("第 1 条应按时间升序排在最前，实际 role=%q", env.Data.Messages[0].Role)
	}
	if !env.Data.Messages[1].IsSummary || env.Data.Messages[1].VersionNo != 3 {
		t.Errorf("summary 那条丢失了 is_summary/version_no：%+v", env.Data.Messages[1])
	}
	if env.Data.Messages[1].Intent == nil || env.Data.Messages[1].Intent.Action != "rewrite" {
		t.Errorf("summary 那条的 intent 未保留：%+v", env.Data.Messages[1].Intent)
	}
	if !env.Data.Messages[2].IsError {
		t.Errorf("第 3 条 is_error 未保留：%+v", env.Data.Messages[2])
	}

	// 3) 幂等 upsert：把第 1 条的 text 改了再发一次，列表总数仍为 3，文本被覆盖
	first := env.Data.Messages[0]
	second := `{
		"messages": [
			{ "message_id": "` + first.MessageID + `", "role": "teacher", "text": "TEXT_OVERWRITTEN", "created_at": "` + now.Format(time.RFC3339) + `" }
		]
	}`
	w = call(http.MethodPost, "/api/v1/coursewares/"+proj.ProjectID+"/ai-messages", second)
	if w.Code != http.StatusOK {
		t.Fatalf("二次 POST 期望 200 实际 %d：%s", w.Code, w.Body.String())
	}
	w = call(http.MethodGet, "/api/v1/coursewares/"+proj.ProjectID+"/ai-messages", "")
	_ = json.Unmarshal(w.Body.Bytes(), &env)
	if len(env.Data.Messages) != 3 {
		t.Fatalf("幂等 upsert 后总数仍应为 3，实际 %d", len(env.Data.Messages))
	}
	if env.Data.Messages[0].Text != "TEXT_OVERWRITTEN" {
		t.Errorf("幂等覆盖失败，实际 text=%q", env.Data.Messages[0].Text)
	}

	// 4) 验证跨项目隔离：再建一个新项目，GET 应返回空
	proj2, err := svc.CreateProject(context.Background(), "teacher_aimsg2", "AI 对话测试 2")
	if err != nil {
		t.Fatalf("CreateProject 2 失败: %v", err)
	}
	w = call(http.MethodGet, "/api/v1/coursewares/"+proj2.ProjectID+"/ai-messages", "")
	_ = json.Unmarshal(w.Body.Bytes(), &env)
	if len(env.Data.Messages) != 0 {
		t.Fatalf("新项目应返回空，实际 %d 条", len(env.Data.Messages))
	}

	// 5) DELETE 清空，列表再读为空
	w = call(http.MethodDelete, "/api/v1/coursewares/"+proj.ProjectID+"/ai-messages", "")
	if w.Code != http.StatusOK {
		t.Fatalf("DELETE 期望 200 实际 %d：%s", w.Code, w.Body.String())
	}
	w = call(http.MethodGet, "/api/v1/coursewares/"+proj.ProjectID+"/ai-messages", "")
	_ = json.Unmarshal(w.Body.Bytes(), &env)
	if len(env.Data.Messages) != 0 {
		t.Fatalf("DELETE 后应为空，实际 %d 条", len(env.Data.Messages))
	}
}

// TestAIMessagesPersistedAndExposed —— 内存模式（无 DB 依赖）。
func TestAIMessagesPersistedAndExposed(t *testing.T) {
	runAIMessagesScenario(t, func(ai service.AIEngine) (*service.CoursewareService, func()) {
		svc := service.NewCoursewareService(ai)
		return svc, func() {}
	})
}

// TestAIMessagesPersistedAndExposedPG —— 真实 PostgreSQL 端到端。
// 用法：COURSEWARE_PG_DSN=... go test ./internal/handler -run TestAIMessagesPersistedAndExposedPG -count=1 -v
func TestAIMessagesPersistedAndExposedPG(t *testing.T) {
	dsn := os.Getenv("COURSEWARE_PG_DSN")
	if dsn == "" {
		t.Skip("未设置 COURSEWARE_PG_DSN，跳过真实库验证")
	}
	runAIMessagesScenario(t, func(ai service.AIEngine) (*service.CoursewareService, func()) {
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