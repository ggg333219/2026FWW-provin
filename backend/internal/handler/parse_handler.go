package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// ParseHandler S2 多模态解析 — HTTP 处理器
type ParseHandler struct {
	aiClient service.AIEngine
}

func NewParseHandler(aiClient service.AIEngine) *ParseHandler {
	return &ParseHandler{aiClient: aiClient}
}

// ProcessFile  POST /api/v1/parse/process — 上传并解析文件
func (h *ParseHandler) ProcessFile(c *gin.Context) {
	var req service.ParseProcessRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.ParseProcess(c.Request.Context(), &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "解析任务创建失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// ParseStatus  GET /api/v1/parse/status/:task_id — 查询解析状态
func (h *ParseHandler) ParseStatus(c *gin.Context) {
	taskID := c.Param("task_id")
	if taskID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 task_id"})
		return
	}
	resp, err := h.aiClient.ParseStatus(c.Request.Context(), taskID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "查询解析状态失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// ProcessVideo  POST /api/v1/parse/video — 视频专用解析
func (h *ParseHandler) ProcessVideo(c *gin.Context) {
	var req service.ParseVideoRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.ParseVideo(c.Request.Context(), &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "视频解析失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}
