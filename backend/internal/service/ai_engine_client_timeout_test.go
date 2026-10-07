package service

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestIntentExtractUsesExtendedTimeout(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/intent/extract" {
			http.NotFound(w, r)
			return
		}
		time.Sleep(80 * time.Millisecond)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"session_id":"s1","intent_summary":{},"session_status":"collecting"}`))
	}))
	defer server.Close()

	client := NewAIEngineClient(server.URL, 20*time.Millisecond).(*aiEngineClient)
	if client.baseURL != server.URL {
		t.Fatalf("AI base URL = %q, want test server %q", client.baseURL, server.URL)
	}
	if _, err := client.IntentExtract(context.Background(), IntentExtractRequest{}); err != nil {
		t.Fatalf("意图提取未使用专用等待时间: %v", err)
	}
	var response map[string]any
	if err := client.postJSON(context.Background(), "/other", map[string]any{}, &response); err == nil {
		t.Fatal("普通 AI 请求不应继承意图提取专用等待时间")
	}
}
