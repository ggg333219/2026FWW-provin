package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// ConversationHandler S1 意图理解 — HTTP 处理器
type ConversationHandler struct {
	aiClient service.AIEngine
}

func NewConversationHandler(aiClient service.AIEngine) *ConversationHandler {
	return &ConversationHandler{aiClient: aiClient}
}

// ExtractIntent  POST /api/v1/intent/extract — 提取意图
func (h *ConversationHandler) ExtractIntent(c *gin.Context) {
	var req service.IntentExtractRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.IntentExtract(c.Request.Context(), req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "意图提取失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// ConfirmIntent  POST /api/v1/intent/confirm — 确认意图
func (h *ConversationHandler) ConfirmIntent(c *gin.Context) {
	var req service.IntentConfirmRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.IntentConfirm(c.Request.Context(), req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "意图确认失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}
