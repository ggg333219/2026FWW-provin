package handler

import (
	"context"
	"errors"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// GenerationHandler S3 课件生成 — HTTP 处理器
type GenerationHandler struct {
	aiClient       service.AIEngine
	outlineService *service.OutlineService
}

func NewGenerationHandler(aiClient service.AIEngine, outlineServices ...*service.OutlineService) *GenerationHandler {
	var outlineService *service.OutlineService
	if len(outlineServices) > 0 {
		outlineService = outlineServices[0]
	}
	return &GenerationHandler{aiClient: aiClient, outlineService: outlineService}
}

// Create  POST /api/v1/gen/create — 创建生成任务
func (h *GenerationHandler) Create(c *gin.Context) {
	var req service.GenerationCreateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if req.OutlineID != "" {
		if !req.OutlineConfirmed || req.OutlineVersion <= 0 || h.outlineService == nil {
			c.JSON(http.StatusConflict, gin.H{"code": 409, "message": "必须使用后端已确认的大纲版本生成课件"})
			return
		}
		outline, err := h.outlineService.GetConfirmed(req.OutlineID, req.OutlineVersion)
		if err != nil {
			status := http.StatusConflict
			if errors.Is(err, service.ErrOutlineNotFound) {
				status = http.StatusNotFound
			}
			c.JSON(status, gin.H{"code": status, "message": err.Error()})
			return
		}
		req.OutlineNodes = outline.Nodes
	} else if req.OutlineConfirmed {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "outline_confirmed 需要 outline_id"})
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
	if len(req.Nodes) == 0 && req.GenID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "nodes 或 gen_id 至少提供一个"})
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

// Modify  POST /api/v1/gen/modify — 应用编辑命令，生成新版本快照
func (h *GenerationHandler) Modify(c *gin.Context) {
	var req service.GenerationModifyRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.GenerationModify(c.Request.Context(), req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "修改命令执行失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Preview  GET /api/v1/gen/preview/:gen_id — 读取版本快照并渲染预览 HTML（前端刷新后恢复预览）。
func (h *GenerationHandler) Preview(c *gin.Context) {
	genID := c.Param("gen_id")
	if genID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 gen_id"})
		return
	}
	var version *int
	if v := c.Query("version"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			version = &n
		}
	}
	previewClient, ok := h.aiClient.(interface {
		GetPreview(context.Context, string, *int) (*service.GenerationPreviewResponse, error)
	})
	if !ok {
		c.JSON(http.StatusNotImplemented, gin.H{"code": 501, "message": "当前 AI 客户端不支持预览持久化"})
		return
	}
	resp, err := previewClient.GetPreview(c.Request.Context(), genID, version)
	if err != nil {
		if httpErr, isHTTP := err.(*service.AIEngineHTTPError); isHTTP && httpErr.StatusCode == http.StatusNotFound {
			c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "版本不存在，请先完成 S3 生成"})
			return
		}
		c.JSON(http.StatusBadGateway, gin.H{"code": 502, "message": "获取预览失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Finalize POST /api/v1/gen/finalize — 从确认的内容节点创建版本快照（PPT 生成步骤）
func (h *GenerationHandler) Finalize(c *gin.Context) {
	var req service.GenerationFinalizeRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if len(req.Nodes) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "nodes 不能为空"})
		return
	}
	resp, err := h.aiClient.GenerationFinalize(c.Request.Context(), req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "生成终稿失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}
