package handler

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// ContentHandler P1: S3 大纲 → 内容生成（独立阶段）— HTTP 处理器。
// 路由注册（backend/internal/router/teacher.go:181-185）：
//   POST /api/v1/gen/content           — 创建内容生成任务（给定大纲节点）
//   GET  /api/v1/gen/content/status/:content_id — 查询内容生成状态
//   POST /api/v1/gen/content/modify    — 按教师指令修改单节点讲稿
type ContentHandler struct {
	aiClient service.AIEngine
}

func NewContentHandler(aiClient service.AIEngine) *ContentHandler {
	return &ContentHandler{aiClient: aiClient}
}

// Create  POST /api/v1/gen/content — 从大纲节点生成具体内容。
// 请求体与 Python /gen/content 的 GenContentRequest 对齐（nodes 必填）。
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
		if httpErr, isHTTP := err.(*service.AIEngineHTTPError); isHTTP {
			c.JSON(httpErr.StatusCode, gin.H{"code": httpErr.StatusCode, "message": httpErr.Detail})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建内容生成任务失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Status  GET /api/v1/gen/content/status/:content_id — 轮询内容生成进度。
func (h *ContentHandler) Status(c *gin.Context) {
	contentID := c.Param("content_id")
	if contentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 content_id"})
		return
	}
	resp, err := h.aiClient.ContentStatus(c.Request.Context(), contentID)
	if err != nil {
		if httpErr, isHTTP := err.(*service.AIEngineHTTPError); isHTTP {
			c.JSON(httpErr.StatusCode, gin.H{"code": httpErr.StatusCode, "message": httpErr.Detail})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "查询内容生成状态失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Modify POST /api/v1/gen/content/modify — 对单个节点的现有讲稿应用教师指令。
// 不重跑大纲和整批节点；调用者负责把返回的讲稿保存到项目草稿/版本。
func (h *ContentHandler) Modify(c *gin.Context) {
	var req service.GenScriptModifyRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if strings.TrimSpace(req.NodeID) == "" || strings.TrimSpace(req.Script) == "" || strings.TrimSpace(req.Message) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "node_id、script 和 message 不能为空"})
		return
	}
	resp, err := h.aiClient.ModifyContentScript(c.Request.Context(), req)
	if err != nil {
		if httpErr, isHTTP := err.(*service.AIEngineHTTPError); isHTTP {
			c.JSON(httpErr.StatusCode, gin.H{"code": httpErr.StatusCode, "message": httpErr.Detail})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "修改讲稿失败: " + err.Error()})
		return
	}
	if resp.UsedFallback || strings.TrimSpace(resp.Script) == "" || resp.NodeID != req.NodeID {
		c.JSON(http.StatusBadGateway, gin.H{"code": 502, "message": "AI 未返回有效的当前节点讲稿，原稿未修改"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}
