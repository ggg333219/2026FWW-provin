package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// ExportHandler S4 导出任务 — HTTP 处理器
type ExportHandler struct {
	aiClient service.AIEngine
}

func NewExportHandler(aiClient service.AIEngine) *ExportHandler {
	return &ExportHandler{aiClient: aiClient}
}

// Create  POST /api/v1/export/:gen_id — 创建导出任务
func (h *ExportHandler) Create(c *gin.Context) {
	genID := c.Param("gen_id")
	if genID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 gen_id"})
		return
	}
	var req service.ExportCreateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.ExportCreate(c.Request.Context(), genID, req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建导出任务失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Status  GET /api/v1/export/status/:job_id — 查询导出状态
func (h *ExportHandler) Status(c *gin.Context) {
	jobID := c.Param("job_id")
	if jobID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 job_id"})
		return
	}
	resp, err := h.aiClient.ExportStatus(c.Request.Context(), jobID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "查询导出状态失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}
