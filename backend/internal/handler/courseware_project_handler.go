package handler

import (
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"smart-teaching-backend/internal/service"
)

type CoursewareProjectHandler struct {
	service *service.CoursewareProjectService
}

func NewCoursewareProjectHandler(s *service.CoursewareProjectService) *CoursewareProjectHandler {
	return &CoursewareProjectHandler{service: s}
}

func (h *CoursewareProjectHandler) owner(c *gin.Context) (string, bool) {
	id := strings.TrimSpace(c.GetString("userID"))
	if id == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"code": 401, "message": "缺少用户身份"})
		return "", false
	}
	return id, true
}
func projectError(c *gin.Context, err error) {
	status := http.StatusInternalServerError
	if errors.Is(err, service.ErrCoursewareProjectNotFound) {
		status = http.StatusNotFound
	}
	if errors.Is(err, service.ErrCoursewareProjectArchived) {
		status = http.StatusConflict
	}
	if status == 500 {
		c.JSON(status, gin.H{"code": status, "message": "课件项目操作失败"})
	} else {
		c.JSON(status, gin.H{"code": status, "message": err.Error()})
	}
}

func (h *CoursewareProjectHandler) Create(c *gin.Context) {
	owner, ok := h.owner(c)
	if !ok {
		return
	}
	var req service.CreateCoursewareProjectRequest
	if c.ShouldBindJSON(&req) != nil {
		c.JSON(400, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	p, err := h.service.Create(c.Request.Context(), owner, req.Title)
	if err != nil {
		c.JSON(400, gin.H{"code": 400, "message": err.Error()})
		return
	}
	c.JSON(200, gin.H{"code": 200, "data": p})
}
func (h *CoursewareProjectHandler) List(c *gin.Context) {
	owner, ok := h.owner(c)
	if !ok {
		return
	}
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	size, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
	if page < 1 || size < 1 || size > 100 {
		c.JSON(400, gin.H{"code": 400, "message": "分页参数错误"})
		return
	}
	items, total, err := h.service.List(c.Request.Context(), owner, page, size)
	if err != nil {
		projectError(c, err)
		return
	}
	c.JSON(200, gin.H{"code": 200, "data": gin.H{"items": items, "total": total, "page": page, "page_size": size}})
}
func (h *CoursewareProjectHandler) Context(c *gin.Context) {
	owner, ok := h.owner(c)
	if !ok {
		return
	}
	data, err := h.service.Context(c.Request.Context(), owner, c.Param("project_id"))
	if err != nil {
		projectError(c, err)
		return
	}
	c.JSON(200, gin.H{"code": 200, "data": data})
}
func (h *CoursewareProjectHandler) DraftGet(c *gin.Context) { h.Context(c) }
func (h *CoursewareProjectHandler) DraftPut(c *gin.Context) {
	owner, ok := h.owner(c)
	if !ok {
		return
	}
	var req service.SaveDraftRequest
	if c.ShouldBindJSON(&req) != nil {
		c.JSON(400, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	p, err := h.service.SaveDraft(c.Request.Context(), owner, c.Param("project_id"), req.DraftJSON)
	if err != nil {
		projectError(c, err)
		return
	}
	c.JSON(200, gin.H{"code": 200, "data": gin.H{"project": p, "draft": req.DraftJSON, "saved_at": p.UpdatedAt}})
}
func (h *CoursewareProjectHandler) StepPut(c *gin.Context) {
	owner, ok := h.owner(c)
	if !ok {
		return
	}
	var req service.SaveStepRequest
	if c.ShouldBindJSON(&req) != nil {
		c.JSON(400, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	p, err := h.service.SaveStep(c.Request.Context(), owner, c.Param("project_id"), req.CurrentStep)
	if err != nil {
		projectError(c, err)
		return
	}
	c.JSON(200, gin.H{"code": 200, "data": gin.H{"current_step": p.CurrentStep, "updated_at": p.UpdatedAt}})
}
