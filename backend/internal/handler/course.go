package handler

import (
	"net/http"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
	"smart-teaching-backend/pkg/apiresp"
	"smart-teaching-backend/pkg/logger"
)

type CourseHandler struct {
	courseService service.CourseService
	db            *gorm.DB
}

func NewCourseHandler(courseService service.CourseService, db *gorm.DB) *CourseHandler {
	return &CourseHandler{courseService: courseService, db: db}
}

func (h *CourseHandler) GetPagePreview(c *gin.Context) {
	courseID := c.Param("courseId")
	pageNum, err := strconv.Atoi(c.Param("pageNum"))
	if err != nil || pageNum < 1 {
		apiresp.BadRequest(c, "页码必须是正整数", "")
		return
	}

	// 预生成切片（MinIO 等）可直接 302，浏览器 <img> 跟随跳转加载图片。
	// 跳过 picsum 占位 URL，转走本地栅格渲染。
	var coursePage model.CoursePage
	if err := h.db.Where("course_id = ? AND page_index = ?", courseID, pageNum).First(&coursePage).Error; err == nil {
		if url := strings.TrimSpace(coursePage.ImageURL); url != "" && !strings.Contains(url, "picsum.photos") {
			c.Header("Cache-Control", "public, max-age=300")
			c.Redirect(http.StatusFound, url)
			return
		}
	}

	// 无预生成图：渲染为 PNG（PDF 优先 pdftoppm；否则内置占位），避免对 <img> 返回 PDF 重定向。
	ctx := c.Request.Context()
	pngBytes, err := h.courseService.RasterPagePreview(ctx, courseID, pageNum)
	if err != nil {
		apiresp.NotFound(c, "课件不存在或页码无效", "")
		return
	}
	c.Header("Cache-Control", "public, max-age=120")
	c.Data(http.StatusOK, "image/png", pngBytes)
}

func (h *CourseHandler) UploadCourse(c *gin.Context) {
	file, err := c.FormFile("file")
	if err != nil {
		apiresp.BadRequest(c, "请选择要上传的文件", "")
		return
	}

	ext := strings.ToLower(filepath.Ext(file.Filename))
	validExts := map[string]bool{".pdf": true, ".pptx": true}
	if !validExts[ext] {
		apiresp.BadRequest(c, "只支持 PDF/PPTX 格式", "")
		return
	}

	title := strings.TrimSpace(c.PostForm("title"))
	if title == "" {
		title = strings.TrimSuffix(file.Filename, filepath.Ext(file.Filename))
	}

	course, err := h.courseService.UploadCourse(c.Request.Context(), file, title)
	if err != nil {
		logger.Errorf("上传课件失败: %v", err)
		apiresp.Internal(c, "上传失败", err.Error())
		return
	}

	apiresp.OK(c, "上传成功", course)
}

func (h *CourseHandler) GetCourse(c *gin.Context) {
	id := c.Param("id")
	if id == "" {
		id = c.Param("courseId")
	}

	course, err := h.courseService.GetCourse(id)
	if err != nil {
		logger.Errorf("获取课件失败: %v", err)
		apiresp.NotFound(c, "课件不存在", "")
		return
	}

	apiresp.OK(c, "请求成功", course)
}

func (h *CourseHandler) GetCoursePages(c *gin.Context) {
	courseID := c.Param("id")
	if courseID == "" {
		courseID = c.Param("courseId")
	}

	pages, err := h.courseService.GetCoursePages(courseID)
	if err != nil {
		logger.Errorf("获取课件页面失败: %v", err)
		apiresp.Internal(c, "获取失败", "")
		return
	}

	apiresp.OK(c, "请求成功", pages)
}

func (h *CourseHandler) DeleteCourse(c *gin.Context) {
	id := c.Param("id")
	if id == "" {
		id = c.Param("courseId")
	}

	if err := h.courseService.DeleteCourse(id); err != nil {
		logger.Errorf("删除课件失败: %v", err)
		apiresp.Internal(c, "删除失败", "")
		return
	}

	apiresp.OKMessage(c, "删除成功")
}
