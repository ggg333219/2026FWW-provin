package service

import (
	"encoding/json"
	"errors"
	"time"

	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
)

// NotificationService 通知服务
type NotificationService struct {
	db *gorm.DB
}

// NewNotificationService 创建通知服务
func NewNotificationService(db *gorm.DB) *NotificationService {
	return &NotificationService{db: db}
}

// CreateNotification 创建通知
func (ns *NotificationService) CreateNotification(notification *model.Notification) error {
	if notification == nil {
		return errors.New("notification is nil")
	}
	if notification.StudentID == "" {
		return errors.New("student_id is required")
	}

	if notification.Priority == "" {
		notification.Priority = "normal"
	}
	if notification.Channels == "" {
		notification.Channels = marshalNotificationChannels(nil)
	}

	now := time.Now()
	if notification.ScheduledAt != nil && notification.ScheduledAt.After(now) {
		if notification.Status == "" {
			notification.Status = "scheduled"
		}
	} else {
		if notification.Status == "" || notification.Status == "pending" {
			notification.Status = "unread"
		}
		if notification.SentAt == nil {
			notification.SentAt = &now
		}
	}

	return ns.db.Create(notification).Error
}

// GetNotifications 获取用户通知
func (ns *NotificationService) GetNotifications(studentID string, status string, page, pageSize int) ([]model.Notification, int64, error) {
	var notifications []model.Notification
	query := ns.db.Model(&model.Notification{}).Where("student_id = ?", studentID)
	if status != "" {
		query = query.Where("status = ?", status)
	}

	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	offset := (page - 1) * pageSize
	err := query.Order("created_at DESC").
		Limit(pageSize).
		Offset(offset).
		Find(&notifications).Error
	return notifications, total, err
}

// GetNotification 获取单个通知
func (ns *NotificationService) GetNotification(notificationID string) (*model.Notification, error) {
	var notification model.Notification
	if err := ns.db.First(&notification, "id = ?", notificationID).Error; err != nil {
		return nil, err
	}
	return &notification, nil
}

// MarkAsRead 标记通知为已读
func (ns *NotificationService) MarkAsRead(notificationID string) error {
	return ns.db.Model(&model.Notification{}).
		Where("id = ?", notificationID).
		Update("status", "read").Error
}

// MarkAllAsRead 标记所有通知为已读
func (ns *NotificationService) MarkAllAsRead(studentID string) error {
	return ns.db.Model(&model.Notification{}).
		Where("student_id = ? AND status = ?", studentID, "unread").
		Update("status", "read").Error
}

// GetUnreadCount 获取未读通知数量
func (ns *NotificationService) GetUnreadCount(studentID string) (int64, error) {
	var count int64
	err := ns.db.Model(&model.Notification{}).
		Where("student_id = ? AND status = ?", studentID, "unread").
		Count(&count).Error
	return count, err
}

// DeleteNotification 删除通知
func (ns *NotificationService) DeleteNotification(notificationID string) error {
	return ns.db.Delete(&model.Notification{}, "id = ?", notificationID).Error
}

// ScheduleNotification 调度定时通知
func (ns *NotificationService) ScheduleNotification(studentID, title, content, notificationType, priority string, scheduledAt time.Time, relatedID, relatedType string) error {
	notification := &model.Notification{
		StudentID:   studentID,
		Title:       title,
		Content:     content,
		Type:        notificationType,
		Priority:    priority,
		RelatedID:   relatedID,
		RelatedType: relatedType,
		ScheduledAt: &scheduledAt,
		Channels:    marshalNotificationChannels(nil),
	}
	return ns.CreateNotification(notification)
}

// ProcessScheduledNotifications 处理定时通知
func (ns *NotificationService) ProcessScheduledNotifications() error {
	var notifications []model.Notification
	now := time.Now()
	err := ns.db.Where("status = ? AND scheduled_at <= ?", "scheduled", now).
		Find(&notifications).Error
	if err != nil {
		return err
	}

	for _, notification := range notifications {
		sentAt := time.Now()
		updates := map[string]interface{}{
			"status":  "unread",
			"sent_at": sentAt,
		}
		if err := ns.db.Model(&notification).Updates(updates).Error; err != nil {
			return err
		}
	}
	return nil
}

// ArchiveOldNotifications 归档旧通知
func (ns *NotificationService) ArchiveOldNotifications(days int) error {
	cutoffDate := time.Now().AddDate(0, 0, -days)
	return ns.db.Model(&model.Notification{}).
		Where("status = ? AND created_at < ?", "read", cutoffDate).
		Update("status", "archived").Error
}

// GetNotificationStats 获取通知统计
func (ns *NotificationService) GetNotificationStats(studentID string) (map[string]interface{}, error) {
	var stats struct {
		Total    int64
		Unread   int64
		Read     int64
		Archived int64
	}

	ns.db.Model(&model.Notification{}).Where("student_id = ?", studentID).Count(&stats.Total)
	ns.db.Model(&model.Notification{}).Where("student_id = ? AND status = ?", studentID, "unread").Count(&stats.Unread)
	ns.db.Model(&model.Notification{}).Where("student_id = ? AND status = ?", studentID, "read").Count(&stats.Read)
	ns.db.Model(&model.Notification{}).Where("student_id = ? AND status = ?", studentID, "archived").Count(&stats.Archived)

	var typeStats []struct {
		Type  string
		Count int64
	}
	ns.db.Model(&model.Notification{}).
		Select("type, count(*) as count").
		Where("student_id = ?", studentID).
		Group("type").
		Find(&typeStats)

	typeCountMap := make(map[string]int64, len(typeStats))
	for _, ts := range typeStats {
		typeCountMap[ts.Type] = ts.Count
	}

	return map[string]interface{}{
		"total":    stats.Total,
		"unread":   stats.Unread,
		"read":     stats.Read,
		"archived": stats.Archived,
		"by_type":  typeCountMap,
	}, nil
}

// SendPushNotification 发送推送通知（模拟实现）
func (ns *NotificationService) SendPushNotification(notification *model.Notification) error {
	now := time.Now()
	notification.SentAt = &now
	if notification.Status == "scheduled" || notification.Status == "" {
		notification.Status = "unread"
	}
	return ns.db.Save(notification).Error
}

// SendImmediateNotification 立即发送通知
func (ns *NotificationService) SendImmediateNotification(studentID, title, content, notificationType string, channels []string) (*model.Notification, error) {
	now := time.Now()
	notification := &model.Notification{
		StudentID: studentID,
		Title:     title,
		Content:   content,
		Type:      notificationType,
		Priority:  "normal",
		Status:    "unread",
		Channels:  marshalNotificationChannels(channels),
		SentAt:    &now,
	}
	if err := ns.CreateNotification(notification); err != nil {
		return nil, err
	}
	return notification, nil
}

// BatchSendNotifications 批量发送通知
func (ns *NotificationService) BatchSendNotifications() error {
	var notifications []model.Notification
	err := ns.db.Where("status = ? AND sent_at IS NULL", "unread").
		Find(&notifications).Error
	if err != nil {
		return err
	}

	for _, notification := range notifications {
		if err := ns.SendPushNotification(&notification); err != nil {
			continue
		}
	}
	return nil
}

func marshalNotificationChannels(channels []string) string {
	if len(channels) == 0 {
		channels = []string{"app"}
	}
	data, _ := json.Marshal(channels)
	return string(data)
}
