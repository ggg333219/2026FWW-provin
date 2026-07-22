package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// KnowledgeHandler KB 知识库 — HTTP 处理器
type KnowledgeHandler struct {
	aiClient service.AIEngine
}

func NewKnowledgeHandler(aiClient service.AIEngine) *KnowledgeHandler {
	return &KnowledgeHandler{aiClient: aiClient}
}

// Search  POST /api/v1/rag/search — 知识库检索
func (h *KnowledgeHandler) Search(c *gin.Context) {
	var req service.RAGSearchRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.RAGSearch(c.Request.Context(), req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "检索失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Evidence  POST /api/v1/rag/evidence — 证据融合
func (h *KnowledgeHandler) Evidence(c *gin.Context) {
	var req service.RAGEvidenceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.RAGEvidence(c.Request.Context(), req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "证据融合失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Upload  POST /api/v1/knowledge/upload — 上传文档到知识库
func (h *KnowledgeHandler) Upload(c *gin.Context) {
	var req service.KnowledgeUploadRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.KnowledgeUpload(c.Request.Context(), &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "上传失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}
