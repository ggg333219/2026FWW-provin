package handler

import (
	"context"
	"net/http"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// GenerationHandler S3 课件生成 — HTTP 处理器
type GenerationHandler struct {
	aiClient service.AIEngine
}

func NewGenerationHandler(aiClient service.AIEngine) *GenerationHandler {
	return &GenerationHandler{aiClient: aiClient}
}

// Create  POST /api/v1/gen/create — 创建生成任务
func (h *GenerationHandler) Create(c *gin.Context) {
	var req service.GenerationCreateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.GenerationCreate(c.Request.Context(), req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建生成任务失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Status  GET /api/v1/gen/status/:task_id — 查询生成状态
func (h *GenerationHandler) Status(c *gin.Context) {
	taskID := c.Param("task_id")
	if taskID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 task_id"})
		return
	}
	resp, err := h.aiClient.GenerationStatus(c.Request.Context(), taskID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "查询生成状态失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// PreviewHTML POST /api/v1/gen/preview — 将生成节点渲染为可嵌入的 HTML 预览。
func (h *GenerationHandler) PreviewHTML(c *gin.Context) {
	var req service.GenerationPreviewRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if len(req.Nodes) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "nodes 不能为空"})
		return
	}
	previewClient, ok := h.aiClient.(interface {
		GenerationPreview(context.Context, service.GenerationPreviewRequest) (*service.GenerationPreviewResponse, error)
	})
	if !ok {
		c.JSON(http.StatusNotImplemented, gin.H{"code": 501, "message": "当前 AI 客户端不支持 S3 HTML 预览"})
		return
	}
	resp, err := previewClient.GenerationPreview(c.Request.Context(), req)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"code": 502, "message": "生成预览失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Preview  GET /api/v1/gen/preview/:gen_id — 预览（当前简化：走 status 返回）
func (h *GenerationHandler) Preview(c *gin.Context) {
	genID := c.Param("gen_id")
	if genID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 gen_id"})
		return
	}
	// 预览本质上是一个已完成生成的 status 查询
	resp, err := h.aiClient.GenerationStatus(c.Request.Context(), genID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取预览失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}
