package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

type handlerOutlineAI struct{}

func (handlerOutlineAI) GenerateOutline(context.Context, service.OutlineGenerateRequest) (*service.OutlineGenerateResponse, error) {
	return &service.OutlineGenerateResponse{Nodes: []service.OutlineNode{{
		NodeID: "node_teacher_001", Title: "教师确认标题", Summary: "教师确认摘要", NodeType: "content",
	}}}, nil
}

func (handlerOutlineAI) ReviseOutline(_ context.Context, req service.OutlineReviseAIRequest) (*service.OutlineReviseAIResponse, error) {
	return &service.OutlineReviseAIResponse{Nodes: req.Nodes}, nil
}

func TestGenerationCreateInjectsBackendConfirmedOutline(t *testing.T) {
	var forwarded service.GenerationCreateRequest
	aiServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/gen/create" {
			t.Fatalf("unexpected AI path: %s", r.URL.Path)
		}
		if err := json.NewDecoder(r.Body).Decode(&forwarded); err != nil {
			t.Fatalf("decode forwarded request: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"task_id":"task_001","generation_id":"gen_001","status":"pending"}`))
	}))
	defer aiServer.Close()

	outlineService := service.NewOutlineService(handlerOutlineAI{})
	outline, err := outlineService.Create(context.Background(), service.OutlineCreateRequest{Intent: map[string]any{"topic": "测试课程"}})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = outlineService.Confirm(outline.OutlineID, outline.OutlineVersion); err != nil {
		t.Fatal(err)
	}

	h := NewGenerationHandler(service.NewAIEngineClient(aiServer.URL, time.Second), outlineService)
	body, _ := json.Marshal(service.GenerationCreateRequest{
		SessionID: "sess_001", OutlineID: outline.OutlineID, OutlineVersion: outline.OutlineVersion,
		OutlineConfirmed: true,
		OutlineNodes:     []service.OutlineNode{{NodeID: "untrusted", Title: "前端伪造", Summary: "不得透传"}},
	})
	recorder := httptest.NewRecorder()
	ctx, _ := gin.CreateTestContext(recorder)
	ctx.Request = httptest.NewRequest(http.MethodPost, "/api/v1/gen/create", bytes.NewReader(body))
	ctx.Request.Header.Set("Content-Type", "application/json")
	h.Create(ctx)

	if recorder.Code != http.StatusOK {
		t.Fatalf("unexpected status %d: %s", recorder.Code, recorder.Body.String())
	}
	if len(forwarded.OutlineNodes) != 1 || forwarded.OutlineNodes[0].NodeID != "node_teacher_001" {
		t.Fatalf("generation did not use backend confirmed outline: %#v", forwarded.OutlineNodes)
	}
}
