package handler

import (
	"net/http"
	"path"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// ExportHandler S4 导出任务 — HTTP 处理器
type ExportHandler struct {
	aiClient       service.AIEngine
	projectService *service.CoursewareProjectService
}

func NewExportHandler(aiClient service.AIEngine, projectServices ...*service.CoursewareProjectService) *ExportHandler {
	var projectService *service.CoursewareProjectService
	if len(projectServices) > 0 {
		projectService = projectServices[0]
	}
	return &ExportHandler{aiClient: aiClient, projectService: projectService}
}

// CreateV2 provides the canonical generation-scoped export contract.
func (h *ExportHandler) CreateV2(c *gin.Context) {
	genID := c.Param("generation_id")
	if genID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 generation_id"})
		return
	}
	var req service.ExportCreateRequest
	if err := c.ShouldBindJSON(&req); err != nil || len(req.Formats) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "formats 不能为空"})
		return
	}
	if req.Version < 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "version 不能为负数"})
		return
	}
	if req.VersionID != "" {
		versionID := strings.TrimPrefix(strings.TrimPrefix(req.VersionID, "version_"), "v_")
		parsed, parseErr := strconv.Atoi(versionID)
		if parseErr != nil || parsed <= 0 {
			c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "version_id 格式错误"})
			return
		}
		req.Version = parsed
	}
	for _, requested := range req.Formats {
		if requested != "pptx" && requested != "docx" && requested != "html5" {
			c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "不支持的导出格式"})
			return
		}
	}
	if req.Version == 0 {
		latest, loadErr := h.aiClient.VersionLoad(c.Request.Context(), genID, 0)
		if loadErr != nil || latest.VersionNumber <= 0 {
			c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "未找到可导出的课件版本"})
			return
		}
		req.Version = latest.VersionNumber
	}
	requestedFormats := append([]string(nil), req.Formats...)
	format := requestedFormats[0]
	if len(requestedFormats) > 1 {
		format = "both"
	}
	if format == "html5" {
		format = "interactive"
	}
	req.Format, req.Formats = format, nil
	if h.projectService != nil && c.GetString("userID") != "" {
		if p, findErr := h.projectService.FindByGeneration(c.Request.Context(), c.GetString("userID"), genID); findErr == nil {
			req.CoursewareTitle = p.Title
		}
	}
	resp, err := h.aiClient.ExportCreate(c.Request.Context(), genID, req)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"code": 502, "message": "创建导出任务失败: " + err.Error()})
		return
	}
	resp.Formats = requestedFormats
	resp.Version = req.Version
	resp.CoursewareTitle = req.CoursewareTitle
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

func (h *ExportHandler) StatusV2(c *gin.Context) {
	jobID := c.Param("export_job_id")
	if jobID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 export_job_id"})
		return
	}
	resp, err := h.aiClient.ExportStatus(c.Request.Context(), jobID)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"code": 502, "message": "查询导出状态失败: " + err.Error()})
		return
	}
	h.rewriteExportDownloads(jobID, resp)
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Create  POST /api/v1/export/:gen_id — 创建导出任务
func (h *ExportHandler) Create(c *gin.Context) {
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

// Status  GET /api/v1/export/status/:job_id — 查询导出状态
func (h *ExportHandler) Status(c *gin.Context) {
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
	h.rewriteExportDownloads(jobID, resp)
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

func (h *ExportHandler) rewriteExportDownloads(jobID string, resp *service.ExportStatusResponse) {
	if resp == nil {
		return
	}
	if _, ok := h.aiClient.(interface {
		ExportDownloadURL(string, string) string
	}); ok {
		if resp.DownloadURL != "" {
			extension := strings.TrimPrefix(path.Ext(resp.DownloadURL), ".")
			if extension == "" {
				extension = "pptx"
			}
			resp.DownloadURL = "/api/v1/export/download/" + jobID + "/" + extension
		}
		for format := range resp.Files {
			extension := strings.ToLower(format)
			if extension == "html5" || extension == "interactive" {
				extension = "html"
			}
			resp.Files[format] = "/api/v1/export/download/" + jobID + "/" + extension
		}
	}
}

// Download  GET /api/v1/export/download/:job_id/:extension — 网关下载代理
func (h *ExportHandler) Download(c *gin.Context) {
	jobID := c.Param("job_id")
	extension := strings.ToLower(c.Param("extension"))
	// 网关白名单须与 AI 引擎 /download/{job_id}.{extension} 的产物集合一致：
	//   pptx=PPT 图文 / docx=Word 讲稿 / html=HTML5 互动导出（A12 4c），lesson_plan 复用 docx 下载。
	// 曾漏掉 html，导致 interactive 导出经网关下载恒 400。
	if jobID == "" || (extension != "pptx" && extension != "docx" && extension != "html") {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "导出文件参数错误"})
		return
	}
	provider, ok := h.aiClient.(interface {
		ExportDownloadURL(string, string) string
	})
	if !ok {
		c.JSON(http.StatusNotImplemented, gin.H{"code": 501, "message": "当前 AI 客户端不支持导出下载"})
		return
	}
	c.Redirect(http.StatusTemporaryRedirect, provider.ExportDownloadURL(jobID, extension))
}
