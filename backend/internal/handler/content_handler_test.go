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

type scriptModifyAI struct {
	service.AIEngine
	request service.GenScriptModifyRequest
}

func (f *scriptModifyAI) ModifyContentScript(_ context.Context, req service.GenScriptModifyRequest) (*service.GenScriptModifyResponse, error) {
	f.request = req
	return &service.GenScriptModifyResponse{NodeID: req.NodeID, Script: "修改后的讲稿"}, nil
}

func TestContentModifyScript(t *testing.T) {
	gin.SetMode(gin.TestMode)
	ai := &scriptModifyAI{}
	router := gin.New()
	router.POST("/api/v1/gen/content/modify", NewContentHandler(ai).Modify)
	body, _ := json.Marshal(service.GenScriptModifyRequest{
		NodeID: "node-1", Title: "冒泡排序", Script: "原讲稿", Message: "精简", CourseName: "排序算法",
	})
	request := httptest.NewRequest(http.MethodPost, "/api/v1/gen/content/modify", bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if ai.request.NodeID != "node-1" || ai.request.Script != "原讲稿" || ai.request.Message != "精简" {
		t.Fatalf("AI request mismatch: %+v", ai.request)
	}
}

func TestContentModifyScriptRejectsMissingSource(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.POST("/api/v1/gen/content/modify", NewContentHandler(&scriptModifyAI{}).Modify)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/gen/content/modify", bytes.NewBufferString(`{"node_id":"node-1","message":"精简"}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
}
