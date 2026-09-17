package handler

import (
	"errors"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// OutlineHandler S3: 大纲草稿管理 — HTTP 处理器。
// 路由注册（backend/internal/router/teacher.go:159-166）：
//   POST   /api/v1/outlines                     — 生成大纲草稿（AI build，version=1）
//   GET    /api/v1/outlines/:outline_id         — 读取大纲（?version=N 可选，缺省最新）
//   PUT    /api/v1/outlines/:outline_id         — 保存大纲新版本（base_version 冲突 409）
//   POST   /api/v1/outlines/:outline_id/revise  — AI 修订（auto_apply=false 返回待确认候选）
//   POST   /api/v1/outlines/:outline_id/confirm — 确认大纲（校验后 status → confirmed）
//
// 契约对齐：
//   《文档/S3数据与接口规范.md》v1.0 §3.1-3.5（字段 snake_case、状态机 draft/confirmed/superseded）
//   前端 frontend/teacher/src/services/v1/outlineApi.js（5 端点一致）
//   Go 响应统一包 {code, data}（frontend request.js 要求 code === 200）
type OutlineHandler struct {
	outlineService *service.OutlineService
}

func NewOutlineHandler(outlineService *service.OutlineService) *OutlineHandler {
	return &OutlineHandler{outlineService: outlineService}
}

// Create POST /api/v1/outlines —— 生成大纲草稿。
// 请求字段：session_id(必填) / intent_id / intent / evidence_packet / markdown / course_name。
func (h *OutlineHandler) Create(c *gin.Context) {
	var req service.OutlineGenerateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	outline, err := h.outlineService.CreateOutline(c.Request.Context(), req)
	if err != nil {
		if httpErr, isHTTP := err.(*service.AIEngineHTTPError); isHTTP {
			c.JSON(httpErr.StatusCode, gin.H{"code": httpErr.StatusCode, "message": httpErr.Detail})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "生成大纲失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": outline})
}

// Get GET /api/v1/outlines/:outline_id —— 读取大纲。
// ?version=N 可选；缺省返回最新版本（与前端 outlineApi.get 对齐）。
func (h *OutlineHandler) Get(c *gin.Context) {
	outlineID := c.Param("outline_id")
	if outlineID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 outline_id"})
		return
	}
	version := 0
	if v := c.Query("version"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			version = n
		}
	}
	outline, err := h.outlineService.GetOutline(c.Request.Context(), outlineID, version)
	if err != nil {
		status := http.StatusInternalServerError
		if errors.Is(err, service.ErrOutlineNotFound) {
			status = http.StatusNotFound
		}
		c.JSON(status, gin.H{"code": status, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": outline})
}

// Save PUT /api/v1/outlines/:outline_id —— 保存大纲新版本。
// 请求字段：base_version(必填) / nodes(必填)。校验规则见 service.validateOutlineNodes。
func (h *OutlineHandler) Save(c *gin.Context) {
	outlineID := c.Param("outline_id")
	if outlineID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 outline_id"})
		return
	}
	var req struct {
		BaseVersion int                  `json:"base_version"`
		Nodes       []service.OutlineNode `json:"nodes"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	outline, err := h.outlineService.SaveOutlineVersion(c.Request.Context(), outlineID, req.BaseVersion, req.Nodes)
	if err != nil {
		status := http.StatusInternalServerError
		switch {
		case errors.Is(err, service.ErrOutlineVersionConflict):
			status = http.StatusConflict // 409：base_version 不匹配当前版本
		case errors.Is(err, service.ErrInvalidOutline):
			status = http.StatusUnprocessableEntity // 422：结构校验失败
		case errors.Is(err, service.ErrOutlineNotFound):
			status = http.StatusNotFound
		}
		c.JSON(status, gin.H{"code": status, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": outline})
}

// Revise POST /api/v1/outlines/:outline_id/revise —— AI 修改大纲。
// 请求字段：message(必填) / base_version(默认 1) / auto_apply(默认 false)。
// auto_apply=false：返回待确认候选（新版本号预置，不落库）；前端确认后 PUT base_version=候选号 提交。
func (h *OutlineHandler) Revise(c *gin.Context) {
	outlineID := c.Param("outline_id")
	if outlineID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 outline_id"})
		return
	}
	var req struct {
		Message     string `json:"message"`
		BaseVersion int    `json:"base_version"`
		AutoApply   bool   `json:"auto_apply"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if req.Message == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "message 不能为空"})
		return
	}
	if req.BaseVersion <= 0 {
		req.BaseVersion = 1
	}
	outline, err := h.outlineService.ReviseOutline(c.Request.Context(), outlineID, req.Message, req.BaseVersion, req.AutoApply)
	if err != nil {
		status := http.StatusInternalServerError
		if errors.Is(err, service.ErrOutlineVersionConflict) {
			status = http.StatusConflict
		} else if errors.Is(err, service.ErrOutlineNotFound) {
			status = http.StatusNotFound
		}
		c.JSON(status, gin.H{"code": status, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": outline})
}

// Confirm POST /api/v1/outlines/:outline_id/confirm —— 确认大纲。
// 请求字段：outline_version(必填)。校验通过后该版本 status → confirmed。
func (h *OutlineHandler) Confirm(c *gin.Context) {
	outlineID := c.Param("outline_id")
	if outlineID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 outline_id"})
		return
	}
	var req struct {
		OutlineVersion int `json:"outline_version"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if req.OutlineVersion <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "outline_version 必须大于 0"})
		return
	}
	outline, err := h.outlineService.ConfirmOutline(c.Request.Context(), outlineID, req.OutlineVersion)
	if err != nil {
		status := http.StatusInternalServerError
		switch {
		case errors.Is(err, service.ErrOutlineNotFound):
			status = http.StatusNotFound
		case errors.Is(err, service.ErrInvalidOutline):
			status = http.StatusUnprocessableEntity // 422：确认校验失败
		case errors.Is(err, service.ErrOutlineNotConfirmed):
			status = http.StatusConflict
		}
		c.JSON(status, gin.H{"code": status, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": outline})
}
