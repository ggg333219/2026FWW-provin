package handler

import (
	"context"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"smart-teaching-backend/internal/service"
)

type interactiveAsset struct {
	InteractiveAssetID string           `json:"interactive_asset_id"`
	GenerationID       string           `json:"generation_id"`
	NodeID             string           `json:"node_id"`
	AssetType          string           `json:"asset_type"`
	Status             string           `json:"status"`
	Items              []map[string]any `json:"items"`
	FileURL            string           `json:"file_url"`
	EntryURL           string           `json:"entry_url"`
	Error              string           `json:"error,omitempty"`
	CreatedAt          time.Time        `json:"created_at"`
}

type InteractiveHandler struct {
	aiClient service.AIEngine
	mu       sync.RWMutex
	assets   map[string]interactiveAsset
}

func NewInteractiveHandler(aiClient service.AIEngine) *InteractiveHandler {
	return &InteractiveHandler{aiClient: aiClient, assets: make(map[string]interactiveAsset)}
}

type interactiveGenerateBody struct {
	InteractivePlan map[string]any `json:"interactive_plan"`
	Node            map[string]any `json:"node"`
}

// Generate handles POST /api/v1/generations/:generation_id/nodes/:node_id/interactive.
func (h *InteractiveHandler) Generate(c *gin.Context) {
	generationID := c.Param("generation_id")
	nodeID := c.Param("node_id")
	if generationID == "" || nodeID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 generation_id 或 node_id"})
		return
	}
	var body interactiveGenerateBody
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if body.Node == nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 node 快照"})
		return
	}
	body.Node["node_id"] = nodeID
	client, ok := h.aiClient.(interface {
		GenerateInteractive(context.Context, service.InteractiveGenerateRequest) (*service.InteractiveGenerateResponse, error)
	})
	if !ok {
		c.JSON(http.StatusNotImplemented, gin.H{"code": 501, "message": "当前 AI 客户端不支持互动生成"})
		return
	}
	resp, err := client.GenerateInteractive(c.Request.Context(), service.InteractiveGenerateRequest{
		Node:            body.Node,
		InteractivePlan: body.InteractivePlan,
	})
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"code": 502, "message": "生成互动内容失败: " + err.Error()})
		return
	}
	assetID := fmt.Sprintf("asset_%d", time.Now().UnixNano())
	asset := interactiveAsset{
		InteractiveAssetID: assetID,
		GenerationID:       generationID,
		NodeID:             nodeID,
		AssetType:          "html5",
		Status:             "done",
		Items:              resp.Items,
		CreatedAt:          time.Now(),
	}
	h.mu.Lock()
	h.assets[assetID] = asset
	h.mu.Unlock()
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": asset})
}

// Get is intentionally implemented separately from generation so the
// frontend can keep its existing polling contract.
func (h *InteractiveHandler) Get(c *gin.Context) {
	assetID := c.Param("interactive_asset_id")
	h.mu.RLock()
	asset, ok := h.assets[assetID]
	h.mu.RUnlock()
	if !ok {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "互动资源不存在"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": asset})
}

func (h *InteractiveHandler) LinkToPage(c *gin.Context) {
	assetID := c.Param("interactive_asset_id")
	h.mu.RLock()
	_, ok := h.assets[assetID]
	h.mu.RUnlock()
	if !ok {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "互动资源不存在"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{
		"interactive_asset_id": assetID,
		"linked":               true,
		"message":              fmt.Sprintf("互动资源 %s 已关联页面", assetID),
	}})
}
