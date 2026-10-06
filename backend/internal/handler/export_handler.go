package handler

import (
	"context"
	"net/http"
	"path"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

// ExportHandler S4 导出任务 — HTTP 处理器
type ExportHandler struct {
	aiClient       exportAIClient
	projectService coursewareProjectLookup
}

type exportAIClient interface {
	ExportCreate(context.Context, string, service.ExportCreateRequest) (*service.ExportCreateResponse, error)
	ExportStatus(context.Context, string) (*service.ExportStatusResponse, error)
	VersionLoad(context.Context, string, int) (*service.VersionSnapshot, error)
}

type coursewareProjectLookup interface {
	Get(context.Context, string, string) (*model.CoursewareProject, error)
	FindByGeneration(context.Context, string, string) (*model.CoursewareProject, error)
}

func NewExportHandler(aiClient exportAIClient, projectServices ...coursewareProjectLookup) *ExportHandler {
	var projectService coursewareProjectLookup
	if len(projectServices) > 0 {
		projectService = projectServices[0]
	}
	return &ExportHandler{aiClient: aiClient, projectService: projectService}
}

func (h *ExportHandler) authorizeGeneration(c *gin.Context, genID string) bool {
	userID := c.GetString("userID")
	if userID == "" || h.projectService == nil || genID == "" {
		exportContractError(c, http.StatusNotFound, "课件不存在")
		return false
	}
	if _, err := h.projectService.FindByGeneration(c.Request.Context(), userID, genID); err != nil {
		project, projectErr := h.projectService.Get(c.Request.Context(), userID, genID)
		if projectErr != nil || project == nil || project.ID != genID || strings.TrimSpace(project.GenID) != "" {
			exportContractError(c, http.StatusNotFound, "课件不存在")
			return false
		}
	}
	return true
}

func exportContractError(c *gin.Context, status int, message string) {
	c.JSON(status, gin.H{"ok": false, "data": nil, "error": message, "code": status, "message": message})
}

func exportContractOK(c *gin.Context, data interface{}) {
	c.JSON(http.StatusOK, gin.H{"ok": true, "data": data, "error": "", "code": 200})
}

func normalizeExportCreateResponse(req service.ExportCreateRequest, resp *service.ExportCreateResponse) {
	if resp == nil {
		return
	}
	if resp.CoursewareTitle == "" {
		resp.CoursewareTitle = req.CoursewareTitle
	}
	if resp.CoursewareTitle == "" {
		resp.CoursewareTitle = "课件"
	}
	if resp.Version == 0 {
		resp.Version = req.Version
	}
	if resp.VersionNo == 0 {
		resp.VersionNo = resp.Version
	}
	if resp.Filename == "" {
		extension := "pptx"
		switch req.Format {
		case "docx", "lesson_plan":
			extension = "docx"
		case "interactive", "html5":
			extension = "html"
		}
		safeTitle := strings.NewReplacer("\\", "_", "/", "_", ":", "_", "*", "_", "?", "_", "\"", "_", "<", "_", ">", "_", "|", "_").Replace(resp.CoursewareTitle)
		resp.Filename = strings.Trim(safeTitle, " .") + "_v" + strconv.Itoa(resp.VersionNo) + "." + extension
	}
}

// CreateV2 provides the canonical generation-scoped export contract.
func (h *ExportHandler) CreateV2(c *gin.Context) {
	genID := c.Param("generation_id")
	if genID == "" {
		exportContractError(c, http.StatusBadRequest, "缺少 generation_id")
		return
	}
	if !h.authorizeGeneration(c, genID) {
		return
	}
	var req service.ExportCreateRequest
	if err := c.ShouldBindJSON(&req); err != nil || len(req.Formats) == 0 {
		exportContractError(c, http.StatusBadRequest, "formats 不能为空")
		return
	}
	if req.Version < 0 {
		exportContractError(c, http.StatusBadRequest, "version 不能为负数")
		return
	}
	if req.VersionID != "" {
		versionID := strings.TrimPrefix(strings.TrimPrefix(req.VersionID, "version_"), "v_")
		parsed, parseErr := strconv.Atoi(versionID)
		if parseErr != nil || parsed <= 0 {
			exportContractError(c, http.StatusBadRequest, "version_id 格式错误")
			return
		}
		req.Version = parsed
	}
	for _, requested := range req.Formats {
		if requested != "pptx" && requested != "docx" && requested != "html5" {
			exportContractError(c, http.StatusBadRequest, "不支持的导出格式")
			return
		}
	}
	if req.Version == 0 {
		latest, loadErr := h.aiClient.VersionLoad(c.Request.Context(), genID, 0)
		if loadErr != nil || latest.VersionNumber <= 0 {
			exportContractError(c, http.StatusNotFound, "未找到可导出的课件版本")
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
		exportContractError(c, http.StatusBadGateway, "创建导出任务失败: "+err.Error())
		return
	}
	resp.Formats = requestedFormats
	resp.Version = req.Version
	normalizeExportCreateResponse(req, resp)
	exportContractOK(c, resp)
}

func (h *ExportHandler) StatusV2(c *gin.Context) {
	jobID := c.Param("export_job_id")
	if jobID == "" {
		exportContractError(c, http.StatusBadRequest, "缺少 export_job_id")
		return
	}
	resp, err := h.aiClient.ExportStatus(c.Request.Context(), jobID)
	if err != nil {
		exportContractError(c, http.StatusBadGateway, "查询导出状态失败: "+err.Error())
		return
	}
	if !h.authorizeGeneration(c, resp.GenerationID) {
		return
	}
	h.rewriteExportDownloads(jobID, resp)
	exportContractOK(c, resp)
}

// Create  POST /api/v1/export/:gen_id — 创建导出任务
func (h *ExportHandler) Create(c *gin.Context) {
	genID := c.Param("gen_id")
	if genID == "" {
		exportContractError(c, http.StatusBadRequest, "缺少 gen_id")
		return
	}
	var payload struct {
		service.ExportCreateRequest
		ProjectID string `json:"project_id"`
	}
	if err := c.ShouldBindJSON(&payload); err != nil {
		exportContractError(c, http.StatusBadRequest, "参数错误: "+err.Error())
		return
	}
	if payload.ProjectID != "" {
		userID := c.GetString("userID")
		if userID == "" || h.projectService == nil {
			exportContractError(c, http.StatusNotFound, "课件不存在")
			return
		}
		project, err := h.projectService.Get(c.Request.Context(), userID, payload.ProjectID)
		if err != nil {
			exportContractError(c, http.StatusNotFound, "课件不存在")
			return
		}
		if strings.TrimSpace(project.GenID) != "" {
			genID = project.GenID
		} else {
			if len(payload.Nodes) == 0 {
				exportContractError(c, http.StatusBadRequest, "项目版本缺少可导出的节点")
				return
			}
			genID = payload.ProjectID
		}
	} else if !h.authorizeGeneration(c, genID) {
		return
	}
	req := payload.ExportCreateRequest
	resp, err := h.aiClient.ExportCreate(c.Request.Context(), genID, req)
	if err != nil {
		exportContractError(c, http.StatusBadGateway, "创建导出任务失败: "+err.Error())
		return
	}
	normalizeExportCreateResponse(req, resp)
	exportContractOK(c, resp)
}

// Status  GET /api/v1/export/status/:job_id — 查询导出状态
func (h *ExportHandler) Status(c *gin.Context) {
	jobID := c.Param("job_id")
	if jobID == "" {
		exportContractError(c, http.StatusBadRequest, "缺少 job_id")
		return
	}
	resp, err := h.aiClient.ExportStatus(c.Request.Context(), jobID)
	if err != nil {
		exportContractError(c, http.StatusBadGateway, "查询导出状态失败: "+err.Error())
		return
	}
	if !h.authorizeGeneration(c, resp.GenerationID) {
		return
	}
	h.rewriteExportDownloads(jobID, resp)
	exportContractOK(c, resp)
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
		exportContractError(c, http.StatusBadRequest, "导出文件参数错误")
		return
	}
	provider, ok := h.aiClient.(interface {
		ExportDownloadURL(string, string) string
	})
	if !ok {
		exportContractError(c, http.StatusNotImplemented, "当前 AI 客户端不支持导出下载")
		return
	}
	status, err := h.aiClient.ExportStatus(c.Request.Context(), jobID)
	if err != nil || !h.authorizeGeneration(c, status.GenerationID) {
		return
	}
	c.Redirect(http.StatusTemporaryRedirect, provider.ExportDownloadURL(jobID, extension))
}
