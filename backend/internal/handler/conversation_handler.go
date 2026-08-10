package handler

import (
	"errors"
	"net/http"
	"strings"

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
	if message := validateIntentExtractRequest(&req); message != "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": message})
		return
	}
	resp, err := h.aiClient.IntentExtract(c.Request.Context(), req)
	if err != nil {
		writeAIEngineError(c, "意图提取失败", err)
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
	req.SessionID = strings.TrimSpace(req.SessionID)
	if req.SessionID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "session_id 不能为空"})
		return
	}
	resp, err := h.aiClient.IntentConfirm(c.Request.Context(), req)
	if err != nil {
		writeAIEngineError(c, "意图确认失败", err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

func validateIntentExtractRequest(req *service.IntentExtractRequest) string {
	req.SessionID = strings.TrimSpace(req.SessionID)
	if req.SessionID == "" {
		return "session_id 不能为空"
	}
	if len(req.Messages) == 0 {
		return "messages 不能为空"
	}
	if len(req.Messages) > 32 {
		return "对话消息过多，请重新开始会话"
	}
	teacherMessages := 0
	for index := range req.Messages {
		turn := &req.Messages[index]
		turn.Role = strings.ToLower(strings.TrimSpace(turn.Role))
		turn.Content = strings.TrimSpace(turn.Content)
		if turn.Role != "teacher" && turn.Role != "assistant" && turn.Role != "system" {
			return "messages.role 仅支持 teacher、assistant 或 system"
		}
		if turn.Content == "" {
			return "消息内容不能为空"
		}
		if len([]rune(turn.Content)) > 4000 {
			return "单条消息不能超过 4000 个字符"
		}
		if turn.Role == "teacher" {
			teacherMessages++
		}
	}
	if teacherMessages == 0 {
		return "至少需要一条教师消息"
	}
	return ""
}

func writeAIEngineError(c *gin.Context, prefix string, err error) {
	status := http.StatusBadGateway
	message := prefix + ": " + err.Error()
	var upstreamErr *service.AIEngineHTTPError
	if errors.As(err, &upstreamErr) {
		if upstreamErr.StatusCode >= 400 && upstreamErr.StatusCode < 500 {
			status = upstreamErr.StatusCode
		}
		if strings.TrimSpace(upstreamErr.Detail) != "" {
			message = upstreamErr.Detail
		}
	}
	c.JSON(status, gin.H{"code": status, "message": message})
}
