package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
)

func seededInteractiveHandler() *InteractiveHandler {
	h := NewInteractiveHandler(nil)
	h.assets["asset_test"] = interactiveAsset{
		InteractiveAssetID: "asset_test",
		GenerationID:       "gen_test",
		NodeID:             "node_1",
		Status:             "done",
		EntryURL:           "/api/v1/interactive/assets/asset_test/preview",
		Items: []map[string]any{{
			"type": "quiz",
			"questions": []map[string]any{{
				"question": "TCP 建立连接需要几次握手？",
				"options":  []string{"一次", "两次", "三次", "四次"},
				"answer":   "C",
			}},
		}},
	}
	return h
}

func TestInteractiveLinkUsesJSONAssetID(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := seededInteractiveHandler()
	r := gin.New()
	r.POST("/api/v1/generations/:generation_id/pages/:page_id/interactive-link", h.LinkToPage)
	body := `{"interactive_asset_id":"asset_test","label":"握手小测"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/generations/gen_test/pages/page_1/interactive-link", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
	var envelope struct {
		Data map[string]any `json:"data"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &envelope); err != nil {
		t.Fatal(err)
	}
	if envelope.Data["page_id"] != "page_1" || envelope.Data["interactive_asset_id"] != "asset_test" {
		t.Fatalf("unexpected link response: %#v", envelope.Data)
	}
}

func TestInteractivePreviewIsPlayableHTML(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := seededInteractiveHandler()
	r := gin.New()
	r.GET("/api/v1/interactive/assets/:interactive_asset_id/preview", h.Preview)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/api/v1/interactive/assets/asset_test/preview", nil))
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	content := w.Body.String()
	for _, expected := range []string{"课堂互动练习", "TCP 建立连接需要几次握手", "onclick"} {
		if !strings.Contains(content, expected) {
			t.Fatalf("preview missing %q", expected)
		}
	}
}
