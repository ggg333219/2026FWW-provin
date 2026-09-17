package handler

import (
	"errors"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// OutlineHandler 只负责 HTTP 适配；版本和确认态由 OutlineService 管理。
type OutlineHandler struct {
	service *service.OutlineService
}

func NewOutlineHandler(outlineService *service.OutlineService) *OutlineHandler {
	return &OutlineHandler{service: outlineService}
}

func (h *OutlineHandler) Create(c *gin.Context) {
	var req service.OutlineCreateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	result, err := h.service.Create(c.Request.Context(), req)
	h.respond(c, result, err)
}

func (h *OutlineHandler) Get(c *gin.Context) {
	version := 0
	if raw := c.Query("version"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed <= 0 {
			c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "version 必须为正整数"})
			return
		}
		version = parsed
	}
	result, err := h.service.Get(c.Param("outline_id"), version)
	h.respond(c, result, err)
}

func (h *OutlineHandler) Save(c *gin.Context) {
	var req service.OutlineSaveRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	result, err := h.service.Save(c.Param("outline_id"), req)
	h.respond(c, result, err)
}

func (h *OutlineHandler) Revise(c *gin.Context) {
	var req service.OutlineReviseRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	result, err := h.service.Revise(c.Request.Context(), c.Param("outline_id"), req)
	h.respond(c, result, err)
}

func (h *OutlineHandler) Confirm(c *gin.Context) {
	var req struct {
		OutlineVersion int `json:"outline_version"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	result, err := h.service.Confirm(c.Param("outline_id"), req.OutlineVersion)
	h.respond(c, result, err)
}

func (h *OutlineHandler) respond(c *gin.Context, result any, err error) {
	if err == nil {
		c.JSON(http.StatusOK, gin.H{"code": 200, "data": result})
		return
	}
	status := http.StatusBadGateway
	switch {
	case errors.Is(err, service.ErrOutlineNotFound):
		status = http.StatusNotFound
	case errors.Is(err, service.ErrOutlineVersionConflict), errors.Is(err, service.ErrOutlineConfirmed), errors.Is(err, service.ErrOutlineNotConfirmed):
		status = http.StatusConflict
	case errors.Is(err, service.ErrOutlineInvalid):
		status = http.StatusBadRequest
	}
	c.JSON(status, gin.H{"code": status, "message": err.Error()})
}
