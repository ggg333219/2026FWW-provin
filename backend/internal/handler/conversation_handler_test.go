package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

type intentExtractTestAI struct {
	service.AIEngine
	req service.IntentExtractRequest
	err error
}

func (f *intentExtractTestAI) IntentExtract(_ context.Context, req service.IntentExtractRequest) (*service.IntentExtractResponse, error) {
	f.req = req
	if f.err != nil {
		return nil, f.err
	}
	return &service.IntentExtractResponse{SessionID: req.SessionID, SessionStatus: service.SessionStatusCollecting}, nil
}

func TestValidateIntentExtractRequest(t *testing.T) {
	tests := []struct {
		name    string
		req     service.IntentExtractRequest
		wantErr string
	}{
		{
			name: "valid request is normalized",
			req: service.IntentExtractRequest{
				SessionID: " session_01 ",
				Messages:  []service.DialogueTurn{{Role: " Teacher ", Content: " 排序算法课件 "}},
			},
		},
		{
			name:    "missing session",
			req:     service.IntentExtractRequest{Messages: []service.DialogueTurn{{Role: "teacher", Content: "内容"}}},
			wantErr: "session_id",
		},
		{
			name:    "invalid role",
			req:     service.IntentExtractRequest{SessionID: "s", Messages: []service.DialogueTurn{{Role: "user", Content: "内容"}}},
			wantErr: "role",
		},
		{
			name:    "teacher message required",
			req:     service.IntentExtractRequest{SessionID: "s", Messages: []service.DialogueTurn{{Role: "assistant", Content: "问题"}}},
			wantErr: "教师消息",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := validateIntentExtractRequest(&tt.req)
			if tt.wantErr == "" && got != "" {
				t.Fatalf("unexpected validation error: %s", got)
			}
			if tt.wantErr != "" && !strings.Contains(got, tt.wantErr) {
				t.Fatalf("expected error containing %q, got %q", tt.wantErr, got)
			}
		})
	}
}

func TestExtractIntentForwardsRequestIDAndSanitizesUpstreamError(t *testing.T) {
	gin.SetMode(gin.TestMode)
	ai := &intentExtractTestAI{err: &service.AIEngineHTTPError{
		StatusCode: http.StatusInternalServerError,
		Detail:     "provider key=secret and internal traceback",
	}}
	router := gin.New()
	router.POST("/intent/extract", NewConversationHandler(ai).ExtractIntent)
	request := httptest.NewRequest(http.MethodPost, "/intent/extract", strings.NewReader(
		`{"session_id":"session-1","messages":[{"role":"teacher","content":"排序算法"}]}`,
	))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Request-ID", "req-safe-123")
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)

	if response.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, body=%s", response.Code, response.Body.String())
	}
	if ai.req.RequestID != "req-safe-123" || response.Header().Get("X-Request-ID") != "req-safe-123" {
		t.Fatalf("request ID was not correlated: request=%q response=%q", ai.req.RequestID, response.Header().Get("X-Request-ID"))
	}
	var payload map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if strings.Contains(response.Body.String(), "secret") || strings.Contains(response.Body.String(), "traceback") {
		t.Fatalf("upstream diagnostic leaked to teacher: %s", response.Body.String())
	}
	if !strings.Contains(payload["message"].(string), "保留本轮输入") || payload["request_id"] != "req-safe-123" {
		t.Fatalf("unexpected safe error payload: %#v", payload)
	}
}

func TestIntentExtractErrorClassifiesTimeout(t *testing.T) {
	status, category, message := intentExtractError(context.DeadlineExceeded)
	if status != http.StatusGatewayTimeout || category != "timeout" || !strings.Contains(message, "重试") {
		t.Fatalf("unexpected timeout mapping: status=%d category=%q message=%q", status, category, message)
	}
}

func TestSafeRequestIDRejectsLogSeparators(t *testing.T) {
	if safeRequestID("req-safe_123.test") == false {
		t.Fatal("safe request id was rejected")
	}
	if safeRequestID("req-123\nlevel=ERROR") {
		t.Fatal("request id with log separators was accepted")
	}
}
