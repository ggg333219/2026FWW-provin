package handler

import (
	"net/http"
	"path"
	"strings"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// ExportHandler S4 导出任务 — HTTP 处理器
type ExportHandler struct {
	aiClient service.AIEngine
}

func NewExportHandler(aiClient service.AIEngine) *ExportHandler {
	return &ExportHandler{aiClient: aiClient}
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
	if resp.DownloadURL != "" {
		extension := strings.TrimPrefix(path.Ext(resp.DownloadURL), ".")
		if extension == "" {
			extension = "pptx"
		}
		if _, ok := h.aiClient.(interface {
			ExportDownloadURL(string, string) string
		}); ok {
			resp.DownloadURL = "/api/v1/export/download/" + jobID + "/" + extension
		}
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
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
