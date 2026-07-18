package apiresp

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// Error 统一错误 JSON：code + message，可选 detail（与现有前端约定一致）。
func Error(c *gin.Context, httpStatus int, code int, message string, detail string) {
	h := gin.H{"code": code, "message": message}
	if detail != "" {
		h["detail"] = detail
	}
	c.JSON(httpStatus, h)
}

// BadRequest 400。
func BadRequest(c *gin.Context, message string, detail string) {
	Error(c, http.StatusBadRequest, 400, message, detail)
}

// Unauthorized 401。
func Unauthorized(c *gin.Context, message string, detail string) {
	Error(c, http.StatusUnauthorized, 401, message, detail)
}

// Forbidden 403。
func Forbidden(c *gin.Context, message string, detail string) {
	Error(c, http.StatusForbidden, 403, message, detail)
}

// NotFound 404。
func NotFound(c *gin.Context, message string, detail string) {
	Error(c, http.StatusNotFound, 404, message, detail)
}

// Conflict 409。
func Conflict(c *gin.Context, message string, detail string) {
	Error(c, http.StatusConflict, 409, message, detail)
}

// Internal 500。
func Internal(c *gin.Context, message string, detail string) {
	Error(c, http.StatusInternalServerError, 500, message, detail)
}

// ServiceUnavailable 503。
func ServiceUnavailable(c *gin.Context, message string, detail string) {
	Error(c, http.StatusServiceUnavailable, 503, message, detail)
}

// OK 成功响应：code=200；必选 message；data 非 nil 时写入 data。
func OK(c *gin.Context, message string, data any) {
	h := gin.H{"code": 200, "message": message}
	if data != nil {
		h["data"] = data
	}
	c.JSON(http.StatusOK, h)
}

// OKData 仅返回 data，默认提示「请求成功」。
func OKData(c *gin.Context, data gin.H) {
	OK(c, "请求成功", data)
}

// OKDataWithMessage 成功且自定义 message。
func OKDataWithMessage(c *gin.Context, message string, data gin.H) {
	OK(c, message, data)
}

// OKMessage 成功且无业务 data 字段（如纯确认类）。
func OKMessage(c *gin.Context, message string) {
	OK(c, message, nil)
}

// OKDataExtra 成功响应：根级含 code、message、data，并将 extra 中的键与 data 同级合并（用于 schemaVersion 等与历史联调兼容）。
func OKDataExtra(c *gin.Context, message string, data any, extra gin.H) {
	h := gin.H{"code": 200, "message": message, "data": data}
	for k, v := range extra {
		h[k] = v
	}
	c.JSON(http.StatusOK, h)
}
