package handler

import (
	"net/http"

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
