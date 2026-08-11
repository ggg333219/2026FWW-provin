package handler

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// VersionHandler S4 版本管理 — HTTP 处理器
type VersionHandler struct {
	aiClient service.AIEngine
}

func NewVersionHandler(aiClient service.AIEngine) *VersionHandler {
	return &VersionHandler{aiClient: aiClient}
}

// Load  GET /api/v1/version/:gen_id — 加载指定版本详情（默认最新，可选 ?v=versionNumber）
func (h *VersionHandler) Load(c *gin.Context) {
	genID := c.Param("gen_id")
	if genID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 gen_id"})
		return
	}
	versionNumber := 0
	if v := c.Query("v"); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil {
			versionNumber = parsed
		}
	}
	resp, err := h.aiClient.VersionLoad(c.Request.Context(), genID, versionNumber)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "加载版本失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// History  GET /api/v1/version/:gen_id/history — 版本历史
func (h *VersionHandler) History(c *gin.Context) {
	genID := c.Param("gen_id")
	if genID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 gen_id"})
		return
	}
	resp, err := h.aiClient.VersionHistory(c.Request.Context(), genID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取版本历史失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Rollback  POST /api/v1/version/:gen_id/rollback — 回滚到指定版本
func (h *VersionHandler) Rollback(c *gin.Context) {
	genID := c.Param("gen_id")
	if genID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 gen_id"})
		return
	}
	var req service.VersionRollbackRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.VersionRollback(c.Request.Context(), genID, req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "回滚失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Lock  POST /api/v1/version/:gen_id/lock — 锁定版本
func (h *VersionHandler) Lock(c *gin.Context) {
	genID := c.Param("gen_id")
	if genID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 gen_id"})
		return
	}
	resp, err := h.aiClient.VersionLock(c.Request.Context(), genID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "锁定失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// ExportCreate  POST /api/v1/export/:gen_id — 创建导出任务
func (h *VersionHandler) ExportCreate(c *gin.Context) {
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

// ExportStatus  GET /api/v1/export/status/:job_id — 查询导出任务状态
func (h *VersionHandler) ExportStatus(c *gin.Context) {
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
