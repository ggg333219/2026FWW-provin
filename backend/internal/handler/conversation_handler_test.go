package handler

import (
	"strings"
	"testing"

	"smart-teaching-backend/internal/service"
)

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
