package handler

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// ParseHandler S2 多模态解析 — HTTP 处理器
type ParseHandler struct {
	aiClient service.AIEngine
}

func NewParseHandler(aiClient service.AIEngine) *ParseHandler {
	return &ParseHandler{aiClient: aiClient}
}

// parseUploadDir 返回 S2 上传文件的落盘目录（Go 与 ai_engine 同机时引擎可直接读取）。
// 可通过环境变量 S2_PARSE_DIR 覆盖，默认使用系统临时目录下的 fuww_s2_parse。
func parseUploadDir() string {
	dir := strings.TrimSpace(os.Getenv("S2_PARSE_DIR"))
	if dir == "" {
		dir = filepath.Join(os.TempDir(), "fuww_s2_parse")
	}
	return dir
}

// sourceTypeFromName 根据扩展名推断 S2 素材类型（与前端 fileTypeFromName / 引擎 _infer_source_type 保持一致）。
func sourceTypeFromName(name string) string {
	ext := strings.ToLower(strings.TrimPrefix(filepath.Ext(name), "."))
	switch ext {
	case "mp4", "avi", "mov", "mkv", "wmv", "flv":
		return "video"
	case "mp3", "wav", "m4a", "ogg", "flac":
		return "audio"
	case "png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff":
		return "image"
	case "pdf":
		return "pdf"
	case "pptx", "ppt":
		return "pptx"
	case "docx", "doc":
		return "docx"
	default:
		return "text"
	}
}

// Upload POST /api/v1/parse/upload — 接收 multipart 文件，落盘到引擎可读目录，
// 返回本地路径供 parse/process 使用（真实后端解析磁盘文件）。
func (h *ParseHandler) Upload(c *gin.Context) {
	sessionID := strings.TrimSpace(c.PostForm("session_id"))
	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "请选择文件: " + err.Error()})
		return
	}

	// 会话子目录 + 时间戳前缀，避免同名文件互相覆盖
	base := filepath.Join(parseUploadDir(), sanitizePathSegment(sessionID))
	if err := os.MkdirAll(base, 0o755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建上传目录失败: " + err.Error()})
		return
	}
	// 保留原始文件名便于引擎按扩展名推断类型，同时避免路径穿越
	cleanName := sanitizePathSegment(filepath.Base(file.Filename))
	if cleanName == "" || cleanName == "." {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "文件名非法"})
		return
	}
	dest := filepath.Join(base, fmt.Sprintf("%d_%s", time.Now().UnixNano(), cleanName))

	// 统一路径分隔符为前斜杠，确保 JSON 序列化时不会产生无效的 \U 转义序列
	dest = strings.ReplaceAll(dest, "\\", "/")

	if err := c.SaveUploadedFile(file, dest); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "保存上传文件失败: " + err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{
		"file_path":   dest,
		"file_name":   file.Filename,
		"file_size":   file.Size,
		"source_type": sourceTypeFromName(file.Filename),
	}})
}

func sanitizePathSegment(name string) string {
	// 去掉路径分隔符与危险字符，保留中文/字母/数字/点/下划线/连字符
	name = filepath.Base(name)
	cleaned := make([]rune, 0, len(name))
	for _, r := range name {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') ||
			r == '.' || r == '_' || r == '-' || r > 127 {
			cleaned = append(cleaned, r)
		}
	}
	return strings.TrimSpace(string(cleaned))
}

// ProcessFile  POST /api/v1/parse/process — 上传并解析文件
func (h *ParseHandler) ProcessFile(c *gin.Context) {
	var req service.ParseProcessRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.ParseProcess(c.Request.Context(), &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "解析任务创建失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// ParseStatus  GET /api/v1/parse/status/:task_id — 查询解析状态
func (h *ParseHandler) ParseStatus(c *gin.Context) {
	taskID := c.Param("task_id")
	if taskID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 task_id"})
		return
	}
	resp, err := h.aiClient.ParseStatus(c.Request.Context(), taskID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "查询解析状态失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// ProcessVideo  POST /api/v1/parse/video — 视频专用解析
func (h *ParseHandler) ProcessVideo(c *gin.Context) {
	var req service.ParseVideoRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	resp, err := h.aiClient.ParseVideo(c.Request.Context(), &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "视频解析失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}
