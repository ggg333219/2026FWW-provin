package handler

import (
	"errors"
	"net/http"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// ContentHandler P1 大纲→内容生成阶段 — HTTP 处理器
type ContentHandler struct {
	aiClient service.AIEngine
}

func NewContentHandler(aiClient service.AIEngine) *ContentHandler {
	return &ContentHandler{aiClient: aiClient}
}

// Create POST /api/v1/gen/content — 为已确认大纲的节点生成讲稿内容
func (h *ContentHandler) Create(c *gin.Context) {
	var req service.GenContentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if len(req.Nodes) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "nodes 不能为空"})
		return
	}

	resp, err := h.aiClient.GenerateContent(c.Request.Context(), req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建内容生成任务失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Status GET /api/v1/gen/content/status/:content_id — 查询内容生成状态
func (h *ContentHandler) Status(c *gin.Context) {
	contentID := c.Param("content_id")
	if contentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 content_id"})
		return
	}

	resp, err := h.aiClient.ContentStatus(c.Request.Context(), contentID)
	if err != nil {
		var httpErr *service.AIEngineHTTPError
		if errors.As(err, &httpErr) && httpErr.StatusCode == http.StatusNotFound {
			c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "内容生成任务不存在"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "查询内容生成状态失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Modify POST /api/v1/gen/content/modify — AI 修改节点内容（自然语言指令）
func (h *ContentHandler) Modify(c *gin.Context) {
	var req struct {
		ContentID string `json:"content_id"`
		NodeID    string `json:"node_id"`
		Message   string `json:"message"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if req.ContentID == "" || req.NodeID == "" || req.Message == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "content_id / node_id / message 不能为空"})
		return
	}

	// 通过 gen/modify 委托给 AI Engine 执行修改命令（复用既有修改链路）
	modifyReq := service.GenerationModifyRequest{
		GenerationID: req.ContentID,
		Commands: []service.ModifyCommandItem{
			{
				CommandType: "update_node",
				NodeID:      req.NodeID,
				Content:     req.Message,
				Regenerate:  true,
			},
		},
		Regenerate: true,
	}
	resp, err := h.aiClient.GenerationModify(c.Request.Context(), modifyReq)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "内容修改失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}
