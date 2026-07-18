package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

// NotificationHandler 通知处理器
type NotificationHandler struct {
	notificationService  *service.NotificationService
	taskSchedulerService *service.TaskSchedulerService
}

// NewNotificationHandler 创建通知处理器
func NewNotificationHandler(notificationService *service.NotificationService, taskSchedulerService *service.TaskSchedulerService) *NotificationHandler {
	return &NotificationHandler{
		notificationService:  notificationService,
		taskSchedulerService: taskSchedulerService,
	}
}

// CreateNotification 创建通知
func (nh *NotificationHandler) CreateNotification(c *gin.Context) {
	var req struct {
		UserID      interface{} `json:"userId"`
		StudentID   string      `json:"studentId"`
		Title       string      `json:"title" binding:"required"`
		Content     string      `json:"content" binding:"required"`
		Type        string      `json:"type" binding:"required"`
		Priority    string      `json:"priority"`
		Channels    []string    `json:"channels"`
		ScheduledAt *int64      `json:"scheduledAt"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	studentID := resolveFlexibleID(req.StudentID, req.UserID)
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 userId 或 studentId"})
		return
	}

	notification := &model.Notification{
		StudentID: studentID,
		Title:     req.Title,
		Content:   req.Content,
		Type:      req.Type,
		Priority:  req.Priority,
		Channels:  marshalChannelJSON(req.Channels),
	}
	if req.ScheduledAt != nil {
		scheduledTime := time.Unix(*req.ScheduledAt, 0)
		notification.ScheduledAt = &scheduledTime
	}

	if err := nh.notificationService.CreateNotification(notification); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建通知失败"})
		return
	}

	if nh.taskSchedulerService != nil {
		if err := nh.taskSchedulerService.SyncNotificationTask(notification); err != nil {
			_ = nh.notificationService.DeleteNotification(notification.ID)
			c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建通知失败"})
			return
		}
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "创建成功", "data": normalizeNotificationPayload(*notification)})
}

// GetNotifications 获取用户通知列表
func (nh *NotificationHandler) GetNotifications(c *gin.Context) {
	userIDStr := firstNotificationNonEmpty(c.Query("studentId"), c.Query("userId"))
	pageStr := c.DefaultQuery("page", "1")
	pageSizeStr := c.DefaultQuery("pageSize", "20")
	status := c.Query("status")

	if userIDStr == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 userId 或 studentId"})
		return
	}

	page, err := strconv.Atoi(pageStr)
	if err != nil || page <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "page 参数无效"})
		return
	}

	pageSize, err := strconv.Atoi(pageSizeStr)
	if err != nil || pageSize <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "pageSize 参数无效"})
		return
	}

	notifications, total, err := nh.notificationService.GetNotifications(userIDStr, status, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取通知列表失败"})
		return
	}

	list := make([]gin.H, 0, len(notifications))
	for _, notification := range notifications {
		list = append(list, normalizeNotificationPayload(notification))
	}

	c.JSON(http.StatusOK, gin.H{
		"code": 200,
		"data": gin.H{
			"list":       list,
			"total":      total,
			"page":       page,
			"pageSize":   pageSize,
			"totalPages": (total + int64(pageSize) - 1) / int64(pageSize),
		},
	})
}

// GetNotification 获取单个通知详情
func (nh *NotificationHandler) GetNotification(c *gin.Context) {
	notificationID := strings.TrimSpace(c.Param("id"))
	if notificationID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "通知ID无效"})
		return
	}

	notification, err := nh.notificationService.GetNotification(notificationID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "通知不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": normalizeNotificationPayload(*notification)})
}

// MarkAsRead 标记通知为已读
func (nh *NotificationHandler) MarkAsRead(c *gin.Context) {
	notificationID := strings.TrimSpace(c.Param("id"))
	if notificationID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "通知ID无效"})
		return
	}

	if err := nh.notificationService.MarkAsRead(notificationID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "标记已读失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "标记成功"})
}

// MarkAllAsRead 标记所有通知为已读
func (nh *NotificationHandler) MarkAllAsRead(c *gin.Context) {
	userIDStr := firstNotificationNonEmpty(c.Query("studentId"), c.Query("userId"))
	if userIDStr == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 userId 或 studentId"})
		return
	}

	if err := nh.notificationService.MarkAllAsRead(userIDStr); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "标记已读失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "标记成功"})
}

// DeleteNotification 删除通知
func (nh *NotificationHandler) DeleteNotification(c *gin.Context) {
	notificationID := strings.TrimSpace(c.Param("id"))
	if notificationID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "通知ID无效"})
		return
	}

	if nh.taskSchedulerService != nil {
		if err := nh.taskSchedulerService.DeleteNotificationTasks(notificationID); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "删除通知失败"})
			return
		}
	}

	if err := nh.notificationService.DeleteNotification(notificationID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "删除通知失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "删除成功"})
}

// GetUnreadCount 获取未读通知数量
func (nh *NotificationHandler) GetUnreadCount(c *gin.Context) {
	userIDStr := firstNotificationNonEmpty(c.Query("studentId"), c.Query("userId"))
	if userIDStr == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 userId 或 studentId"})
		return
	}

	count, err := nh.notificationService.GetUnreadCount(userIDStr)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取未读数量失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"unreadCount": count}})
}

// SendImmediateNotification 立即发送通知
func (nh *NotificationHandler) SendImmediateNotification(c *gin.Context) {
	var req struct {
		UserID    interface{} `json:"userId"`
		StudentID string      `json:"studentId"`
		Title     string      `json:"title" binding:"required"`
		Content   string      `json:"content" binding:"required"`
		Type      string      `json:"type" binding:"required"`
		Channels  []string    `json:"channels"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	studentID := resolveFlexibleID(req.StudentID, req.UserID)
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 userId 或 studentId"})
		return
	}

	notification, err := nh.notificationService.SendImmediateNotification(studentID, req.Title, req.Content, req.Type, req.Channels)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "发送通知失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "发送成功", "data": normalizeNotificationPayload(*notification)})
}

func resolveFlexibleID(studentID string, raw interface{}) string {
	if trimmed := strings.TrimSpace(studentID); trimmed != "" {
		return trimmed
	}

	switch v := raw.(type) {
	case nil:
		return ""
	case string:
		return strings.TrimSpace(v)
	case float64:
		if v == float64(int64(v)) {
			return strconv.FormatInt(int64(v), 10)
		}
		return strconv.FormatFloat(v, 'f', -1, 64)
	case float32:
		if v == float32(int64(v)) {
			return strconv.FormatInt(int64(v), 10)
		}
		return strconv.FormatFloat(float64(v), 'f', -1, 32)
	case int:
		return strconv.Itoa(v)
	case int64:
		return strconv.FormatInt(v, 10)
	case uint:
		return strconv.FormatUint(uint64(v), 10)
	case uint64:
		return strconv.FormatUint(v, 10)
	default:
		return strings.TrimSpace(fmt.Sprint(v))
	}
}

func marshalChannelJSON(channels []string) string {
	if len(channels) == 0 {
		channels = []string{"app"}
	}
	data, _ := json.Marshal(channels)
	return string(data)
}

func firstNotificationNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func normalizeNotificationPayload(notification model.Notification) gin.H {
	channels := parseNotificationChannels(notification.Channels)
	return gin.H{
		"id":           notification.ID,
		"studentId":    notification.StudentID,
		"student_id":   notification.StudentID,
		"title":        notification.Title,
		"content":      notification.Content,
		"type":         notification.Type,
		"priority":     notification.Priority,
		"status":       notification.Status,
		"relatedId":    notification.RelatedID,
		"related_id":   notification.RelatedID,
		"relatedType":  notification.RelatedType,
		"related_type": notification.RelatedType,
		"scheduledAt":  notification.ScheduledAt,
		"scheduled_at": notification.ScheduledAt,
		"sentAt":       notification.SentAt,
		"sent_at":      notification.SentAt,
		"channels":     channels,
		"channelsRaw":  notification.Channels,
		"channels_raw": notification.Channels,
		"createdAt":    notification.CreatedAt,
		"created_at":   notification.CreatedAt,
		"updatedAt":    notification.UpdatedAt,
		"updated_at":   notification.UpdatedAt,
	}
}

func parseNotificationChannels(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return []string{"app"}
	}

	var channels []string
	if err := json.Unmarshal([]byte(raw), &channels); err == nil && len(channels) > 0 {
		return channels
	}

	return []string{raw}
}
