package service

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strconv"
	"strings"
	"sync"
	"time"

	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
)

// TaskSchedulerService 定时任务调度服务
type TaskSchedulerService struct {
	db        *gorm.DB
	taskQueue chan *model.ScheduledTask
	stopCh    chan struct{}
	started   bool
	mu        sync.Mutex
}

// NewTaskSchedulerService 创建定时任务调度服务
func NewTaskSchedulerService(db *gorm.DB) *TaskSchedulerService {
	return &TaskSchedulerService{
		db:        db,
		taskQueue: make(chan *model.ScheduledTask, 1000),
		stopCh:    make(chan struct{}),
	}
}

// Start 启动调度器
func (ts *TaskSchedulerService) Start() error {
	ts.mu.Lock()
	defer ts.mu.Unlock()
	if ts.started {
		return nil
	}

	ts.started = true
	for i := 0; i < 10; i++ {
		go ts.worker()
	}
	go ts.dispatchLoop()
	ts.checkPendingTasks()

	log.Println("TaskSchedulerService started")
	return nil
}

// Stop 停止调度器
func (ts *TaskSchedulerService) Stop() {
	ts.mu.Lock()
	defer ts.mu.Unlock()
	if !ts.started {
		return
	}
	close(ts.stopCh)
	ts.started = false
}

// ScheduleTask 调度一个任务
func (ts *TaskSchedulerService) ScheduleTask(taskType string, taskData interface{}, scheduledAt time.Time, studentID string) error {
	data, err := json.Marshal(taskData)
	if err != nil {
		return err
	}

	task := &model.ScheduledTask{
		TaskType:    taskType,
		TaskData:    string(data),
		ScheduledAt: scheduledAt,
		StudentID:   studentID,
		Priority:    1,
		MaxRetries:  3,
		Status:      "pending",
	}
	return ts.CreateScheduledTask(task)
}

// CreateScheduledTask 创建定时任务
func (ts *TaskSchedulerService) CreateScheduledTask(task *model.ScheduledTask) error {
	if task == nil {
		return errors.New("task is nil")
	}
	if strings.TrimSpace(task.TaskType) == "" {
		return errors.New("task_type is required")
	}
	if strings.TrimSpace(task.TaskData) == "" {
		task.TaskData = "{}"
	}
	if task.Priority <= 0 {
		task.Priority = 1
	}
	if task.MaxRetries <= 0 {
		task.MaxRetries = 3
	}
	task.Status = "pending"

	if cronExpr := strings.TrimSpace(task.CronExpr); cronExpr != "" {
		nextRun, err := nextRunFromCron(cronExpr, time.Now())
		if err != nil {
			return err
		}
		task.ScheduledAt = nextRun
	} else if task.ScheduledAt.IsZero() {
		task.ScheduledAt = time.Now()
	}

	if err := ts.db.Create(task).Error; err != nil {
		return err
	}
	if task.ScheduledAt.Before(time.Now().Add(time.Minute)) {
		return ts.enqueuePendingTask(task)
	}
	return nil
}

// GetScheduledTasks 获取任务列表
func (ts *TaskSchedulerService) GetScheduledTasks(studentID, status string, page, pageSize int) ([]model.ScheduledTask, int64, error) {
	var tasks []model.ScheduledTask
	query := ts.db.Model(&model.ScheduledTask{}).Where("student_id = ?", studentID)
	if status != "" {
		query = query.Where("status = ?", status)
	}

	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	offset := (page - 1) * pageSize
	err := query.Order("created_at DESC").Limit(pageSize).Offset(offset).Find(&tasks).Error
	return tasks, total, err
}

// GetScheduledTask 获取单个任务
func (ts *TaskSchedulerService) GetScheduledTask(taskID string) (*model.ScheduledTask, error) {
	var task model.ScheduledTask
	if err := ts.db.First(&task, "id = ?", taskID).Error; err != nil {
		return nil, err
	}
	return &task, nil
}

// UpdateScheduledTask 更新任务
func (ts *TaskSchedulerService) UpdateScheduledTask(taskID string, updates map[string]interface{}) error {
	if cronExpr, ok := updates["cron_expr"].(string); ok && strings.TrimSpace(cronExpr) != "" {
		nextRun, err := nextRunFromCron(cronExpr, time.Now())
		if err != nil {
			return err
		}
		updates["scheduled_at"] = nextRun
	}

	if status, ok := updates["status"].(string); ok && strings.TrimSpace(status) == "pending" {
		if _, hasScheduledAt := updates["scheduled_at"]; !hasScheduledAt {
			updates["scheduled_at"] = time.Now()
		}
	}

	return ts.db.Model(&model.ScheduledTask{}).Where("id = ?", taskID).Updates(updates).Error
}

// DeleteScheduledTask 删除任务
func (ts *TaskSchedulerService) DeleteScheduledTask(taskID string) error {
	return ts.db.Delete(&model.ScheduledTask{}, "id = ?", taskID).Error
}

// SyncNotificationTask 为定时通知创建或更新对应的调度任务
func (ts *TaskSchedulerService) SyncNotificationTask(notification *model.Notification) error {
	if notification == nil || strings.TrimSpace(notification.ID) == "" {
		return nil
	}

	now := time.Now()
	if notification.ScheduledAt == nil || !notification.ScheduledAt.After(now) || !strings.EqualFold(notification.Status, "scheduled") {
		return ts.DeleteNotificationTasks(notification.ID)
	}

	taskDataBytes, err := json.Marshal(map[string]any{
		"notification_id": notification.ID,
		"student_id":      notification.StudentID,
		"title":           notification.Title,
		"type":            notification.Type,
	})
	if err != nil {
		return err
	}

	description := firstString(strings.TrimSpace(notification.Title), "定时通知")
	taskData := string(taskDataBytes)

	var task model.ScheduledTask
	err = ts.notificationTaskQuery(notification.ID).Order("created_at desc").First(&task).Error
	if err == nil {
		return ts.db.Model(&model.ScheduledTask{}).Where("id = ?", task.ID).Updates(map[string]any{
			"student_id":    notification.StudentID,
			"task_data":     taskData,
			"description":   description,
			"scheduled_at":  *notification.ScheduledAt,
			"status":        "pending",
			"priority":      1,
			"max_retries":   3,
			"retry_count":   0,
			"last_attempt":  nil,
			"next_attempt":  nil,
			"error_message": "",
		}).Error
	}
	if err != nil && err != gorm.ErrRecordNotFound {
		return err
	}

	task = model.ScheduledTask{
		TaskType:    "notification",
		TaskData:    taskData,
		Description: description,
		ScheduledAt: *notification.ScheduledAt,
		Status:      "pending",
		Priority:    1,
		MaxRetries:  3,
		StudentID:   notification.StudentID,
	}
	return ts.db.Create(&task).Error
}

// DeleteNotificationTasks 删除通知关联的待执行调度任务
func (ts *TaskSchedulerService) DeleteNotificationTasks(notificationID string) error {
	if strings.TrimSpace(notificationID) == "" {
		return nil
	}
	return ts.notificationTaskQuery(notificationID).
		Where("status IN ?", []string{"pending", "queued", "processing", "failed"}).
		Delete(&model.ScheduledTask{}).Error
}

// ExecuteTaskNow 立即执行任务
func (ts *TaskSchedulerService) ExecuteTaskNow(taskID string) error {
	task, err := ts.GetScheduledTask(taskID)
	if err != nil {
		return err
	}

	now := time.Now()
	if err := ts.db.Model(&model.ScheduledTask{}).
		Where("id = ?", taskID).
		Updates(map[string]interface{}{
			"status":        "pending",
			"scheduled_at":  now,
			"next_attempt":  nil,
			"error_message": "",
		}).Error; err != nil {
		return err
	}

	task.Status = "pending"
	task.ScheduledAt = now
	task.NextAttempt = nil
	task.ErrorMessage = ""
	return ts.enqueuePendingTask(task)
}

// GetTaskStatuses 获取任务状态列表
func (ts *TaskSchedulerService) GetTaskStatuses(studentID, status string, page, pageSize int) ([]model.TaskStatus, int64, error) {
	var statuses []model.TaskStatus
	query := ts.db.Model(&model.TaskStatus{}).Where("student_id = ?", studentID)
	if status != "" {
		query = query.Where("status = ?", status)
	}

	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	offset := (page - 1) * pageSize
	err := query.Order("created_at DESC").Limit(pageSize).Offset(offset).Find(&statuses).Error
	return statuses, total, err
}

// GetTaskStatus 获取单个任务状态
func (ts *TaskSchedulerService) GetTaskStatus(statusID string) (*model.TaskStatus, error) {
	var status model.TaskStatus
	if err := ts.db.First(&status, "id = ?", statusID).Error; err != nil {
		return nil, err
	}
	return &status, nil
}

// ScheduleReviewReminders 调度复习提醒
func (ts *TaskSchedulerService) ScheduleReviewReminders() {
	var plans []model.ReviewPlan
	if err := ts.db.Where("status = ? AND next_review_date IS NOT NULL", "active").Find(&plans).Error; err != nil {
		return
	}

	for _, plan := range plans {
		if plan.NextReviewDate != nil && plan.NextReviewDate.After(time.Now()) {
			remindAt := plan.NextReviewDate.Add(-time.Hour)
			taskData := map[string]interface{}{
				"plan_id":    plan.ID,
				"plan_name":  plan.Name,
				"student_id": plan.StudentID,
			}
			_ = ts.ScheduleTask("review_plan", taskData, remindAt, plan.StudentID)
		}
	}
}

// SchedulePracticeGeneration 调度练习题生成
func (ts *TaskSchedulerService) SchedulePracticeGeneration() {
	var weakPoints []model.WeakPoint
	if err := ts.db.Where("mastery_level < ?", 70).Find(&weakPoints).Error; err != nil {
		return
	}

	for _, wp := range weakPoints {
		taskData := map[string]interface{}{
			"weak_point_id": wp.ID,
			"student_id":    wp.StudentID,
			"course_id":     wp.CourseID,
			"difficulty":    3,
			"count":         5,
		}

		now := time.Now()
		scheduledAt := time.Date(now.Year(), now.Month(), now.Day(), 9, 0, 0, 0, now.Location())
		if scheduledAt.Before(now) {
			scheduledAt = scheduledAt.Add(24 * time.Hour)
		}
		_ = ts.ScheduleTask("practice_generation", taskData, scheduledAt, wp.StudentID)
	}
}

func (ts *TaskSchedulerService) worker() {
	for {
		select {
		case task := <-ts.taskQueue:
			if task != nil {
				ts.processTask(task)
			}
		case <-ts.stopCh:
			return
		}
	}
}

func (ts *TaskSchedulerService) processTask(task *model.ScheduledTask) {
	startedAt := time.Now()
	task.Status = "processing"
	task.LastAttempt = &startedAt
	task.ErrorMessage = ""
	if err := ts.db.Model(&model.ScheduledTask{}).
		Where("id = ?", task.ID).
		Updates(map[string]interface{}{
			"status":        "processing",
			"last_attempt":  startedAt,
			"error_message": "",
		}).Error; err != nil {
		log.Printf("update task to processing failed: %v", err)
		return
	}

	taskStatus := &model.TaskStatus{
		TaskID:    task.ID,
		TaskType:  task.TaskType,
		StudentID: task.StudentID,
		Status:    "running",
		StartTime: &startedAt,
	}
	if err := ts.db.Create(taskStatus).Error; err != nil {
		log.Printf("create task status failed: %v", err)
		return
	}

	err := ts.executeTask(task)
	finishedAt := time.Now()
	taskStatus.EndTime = &finishedAt

	if err != nil {
		taskStatus.Status = "failed"
		taskStatus.Progress = 0
		taskStatus.Message = err.Error()
		task.ErrorMessage = err.Error()
		task.RetryCount++
		if task.RetryCount < task.MaxRetries {
			nextAttempt := finishedAt.Add(time.Duration(1<<task.RetryCount) * time.Minute)
			task.NextAttempt = &nextAttempt
			task.ScheduledAt = nextAttempt
			task.Status = "pending"
		} else {
			task.Status = "failed"
		}
	} else {
		taskStatus.Status = "completed"
		taskStatus.Progress = 100
		taskStatus.Message = "执行成功"
		task.NextAttempt = nil
		task.ErrorMessage = ""
		if strings.TrimSpace(task.CronExpr) != "" {
			nextRun, nextErr := nextRunFromCron(task.CronExpr, finishedAt)
			if nextErr != nil {
				task.Status = "failed"
				task.ErrorMessage = nextErr.Error()
				taskStatus.Status = "failed"
				taskStatus.Progress = 0
				taskStatus.Message = nextErr.Error()
			} else {
				task.Status = "pending"
				task.ScheduledAt = nextRun
			}
		} else {
			task.Status = "completed"
		}
	}

	if saveErr := ts.db.Save(task).Error; saveErr != nil {
		log.Printf("save task failed: %v", saveErr)
	}
	if saveErr := ts.db.Save(taskStatus).Error; saveErr != nil {
		log.Printf("save task status failed: %v", saveErr)
	}
}

func (ts *TaskSchedulerService) executeTask(task *model.ScheduledTask) error {
	switch task.TaskType {
	case "review_plan", "review_reminder":
		return ts.processReviewReminder(task)
	case "practice_generation":
		return ts.processPracticeGeneration(task)
	case "notification":
		return ts.processNotification(task)
	default:
		return fmt.Errorf("unknown task type: %s", task.TaskType)
	}
}

func (ts *TaskSchedulerService) checkPendingTasks() {
	var tasks []model.ScheduledTask
	now := time.Now()

	if err := ts.db.Where("status = ? AND scheduled_at <= ?", "pending", now).
		Order("priority ASC, scheduled_at ASC").
		Limit(200).
		Find(&tasks).Error; err != nil {
		log.Printf("check pending tasks failed: %v", err)
		return
	}

	for _, task := range tasks {
		taskCopy := task
		if err := ts.enqueuePendingTask(&taskCopy); err != nil {
			log.Printf("enqueue task %s failed: %v", task.ID, err)
		}
	}
}

func (ts *TaskSchedulerService) dispatchLoop() {
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			ts.checkPendingTasks()
		case <-ts.stopCh:
			return
		}
	}
}

func (ts *TaskSchedulerService) enqueuePendingTask(task *model.ScheduledTask) error {
	result := ts.db.Model(&model.ScheduledTask{}).
		Where("id = ? AND status = ?", task.ID, "pending").
		Update("status", "queued")
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return nil
	}

	task.Status = "queued"
	select {
	case ts.taskQueue <- task:
		return nil
	default:
		_ = ts.db.Model(&model.ScheduledTask{}).
			Where("id = ? AND status = ?", task.ID, "queued").
			Update("status", "pending").Error
		return errors.New("task queue is full")
	}
}

func (ts *TaskSchedulerService) processReviewReminder(task *model.ScheduledTask) error {
	taskData, err := decodeTaskData(task.TaskData)
	if err != nil {
		return err
	}

	planID := stringValue(taskData, "plan_id", "planId")
	planName := stringValue(taskData, "plan_name", "planName")
	if planName == "" {
		planName = task.Description
	}
	if planName == "" {
		planName = "复习计划"
	}

	notification := &model.Notification{
		StudentID:   task.StudentID,
		Title:       "复习提醒",
		Content:     fmt.Sprintf("您的复习计划「%s」该复习了。", planName),
		Type:        "review_reminder",
		Priority:    "normal",
		RelatedID:   planID,
		RelatedType: "review_plan",
		Channels:    `["app"]`,
	}
	return ts.db.Create(notification).Error
}

func (ts *TaskSchedulerService) processPracticeGeneration(task *model.ScheduledTask) error {
	taskData, err := decodeTaskData(task.TaskData)
	if err != nil {
		return err
	}

	weakPointID := stringValue(taskData, "weak_point_id", "weakPointId")
	studentID := firstString(task.StudentID, stringValue(taskData, "student_id", "studentId", "userId"))
	courseID := stringValue(taskData, "course_id", "courseId")
	difficulty := intValue(taskData, 3, "difficulty")
	count := intValue(taskData, 5, "count")

	practiceTask := &model.PracticeTask{
		TaskID:     fmt.Sprintf("task_%d", time.Now().UnixNano()),
		UserID:     studentID,
		CourseID:   courseID,
		NodeID:     weakPointID,
		Difficulty: difficulty,
		Count:      count,
		Questions:  "[]",
	}
	if err := ts.db.Create(practiceTask).Error; err != nil {
		return err
	}

	notification := &model.Notification{
		StudentID:   studentID,
		Title:       "新练习题",
		Content:     fmt.Sprintf("系统已为您生成 %d 道练习题，请及时完成。", count),
		Type:        "practice_due",
		Priority:    "normal",
		RelatedID:   practiceTask.ID,
		RelatedType: "practice_task",
		Channels:    `["app"]`,
	}
	return ts.db.Create(notification).Error
}

func (ts *TaskSchedulerService) processNotification(task *model.ScheduledTask) error {
	taskData, err := decodeTaskData(task.TaskData)
	if err != nil {
		return err
	}

	notificationID := stringValue(taskData, "notification_id", "notificationId")
	if notificationID != "" {
		var notification model.Notification
		if err := ts.db.First(&notification, "id = ?", notificationID).Error; err != nil {
			return err
		}

		now := time.Now()
		notification.SentAt = &now
		if notification.Status == "scheduled" || notification.Status == "" {
			notification.Status = "unread"
		}
		return ts.db.Save(&notification).Error
	}

	studentID := firstString(task.StudentID, stringValue(taskData, "student_id", "studentId", "userId"))
	notification := &model.Notification{
		StudentID:   studentID,
		Title:       firstString(stringValue(taskData, "title"), "系统通知"),
		Content:     firstString(stringValue(taskData, "content"), task.Description),
		Type:        firstString(stringValue(taskData, "type"), "system"),
		Priority:    firstString(stringValue(taskData, "priority"), "normal"),
		Channels:    `["app"]`,
		RelatedID:   stringValue(taskData, "related_id", "relatedId"),
		RelatedType: stringValue(taskData, "related_type", "relatedType"),
	}
	if notification.Content == "" {
		notification.Content = "您有一条新的系统通知。"
	}
	return ts.db.Create(notification).Error
}

func decodeTaskData(raw string) (map[string]interface{}, error) {
	var taskData map[string]interface{}
	if strings.TrimSpace(raw) == "" {
		return map[string]interface{}{}, nil
	}
	if err := json.Unmarshal([]byte(raw), &taskData); err != nil {
		return nil, err
	}
	return taskData, nil
}

func stringValue(data map[string]interface{}, keys ...string) string {
	for _, key := range keys {
		if value, ok := data[key]; ok {
			switch typed := value.(type) {
			case string:
				if trimmed := strings.TrimSpace(typed); trimmed != "" {
					return trimmed
				}
			case float64:
				if typed == float64(int64(typed)) {
					return strconv.FormatInt(int64(typed), 10)
				}
				return strconv.FormatFloat(typed, 'f', -1, 64)
			case float32:
				if typed == float32(int64(typed)) {
					return strconv.FormatInt(int64(typed), 10)
				}
				return strconv.FormatFloat(float64(typed), 'f', -1, 32)
			case int:
				return strconv.Itoa(typed)
			case int64:
				return strconv.FormatInt(typed, 10)
			case uint:
				return strconv.FormatUint(uint64(typed), 10)
			case uint64:
				return strconv.FormatUint(typed, 10)
			}
		}
	}
	return ""
}

func intValue(data map[string]interface{}, defaultValue int, keys ...string) int {
	for _, key := range keys {
		if value, ok := data[key]; ok {
			switch typed := value.(type) {
			case int:
				return typed
			case int64:
				return int(typed)
			case float64:
				return int(typed)
			case float32:
				return int(typed)
			case string:
				if parsed, err := strconv.Atoi(strings.TrimSpace(typed)); err == nil {
					return parsed
				}
			}
		}
	}
	return defaultValue
}

func firstString(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func nextRunFromCron(expr string, from time.Time) (time.Time, error) {
	fields := strings.Fields(strings.TrimSpace(expr))
	if len(fields) != 5 {
		return time.Time{}, fmt.Errorf("invalid cron expr: %s", expr)
	}

	minuteSet, err := parseCronField(fields[0], 0, 59, false)
	if err != nil {
		return time.Time{}, err
	}
	hourSet, err := parseCronField(fields[1], 0, 23, false)
	if err != nil {
		return time.Time{}, err
	}
	daySet, err := parseCronField(fields[2], 1, 31, false)
	if err != nil {
		return time.Time{}, err
	}
	monthSet, err := parseCronField(fields[3], 1, 12, false)
	if err != nil {
		return time.Time{}, err
	}
	weekdaySet, err := parseCronField(fields[4], 0, 6, true)
	if err != nil {
		return time.Time{}, err
	}

	candidate := from.Truncate(time.Minute).Add(time.Minute)
	deadline := from.AddDate(1, 0, 0)
	for !candidate.After(deadline) {
		if minuteSet[candidate.Minute()] &&
			hourSet[candidate.Hour()] &&
			daySet[candidate.Day()] &&
			monthSet[int(candidate.Month())] &&
			weekdaySet[int(candidate.Weekday())] {
			return candidate, nil
		}
		candidate = candidate.Add(time.Minute)
	}

	return time.Time{}, fmt.Errorf("cron expr has no next run within 1 year: %s", expr)
}

func parseCronField(field string, minValue, maxValue int, weekday bool) (map[int]bool, error) {
	result := make(map[int]bool, maxValue-minValue+1)
	tokens := strings.Split(field, ",")
	for _, token := range tokens {
		token = strings.TrimSpace(token)
		if token == "" {
			return nil, errors.New("empty cron token")
		}

		step := 1
		base := token
		if strings.Contains(token, "/") {
			parts := strings.Split(token, "/")
			if len(parts) != 2 {
				return nil, fmt.Errorf("invalid cron token: %s", token)
			}
			base = parts[0]
			parsedStep, err := strconv.Atoi(parts[1])
			if err != nil || parsedStep <= 0 {
				return nil, fmt.Errorf("invalid cron step: %s", token)
			}
			step = parsedStep
		}

		start := minValue
		end := maxValue
		switch {
		case base == "*":
		case strings.Contains(base, "-"):
			rangeParts := strings.Split(base, "-")
			if len(rangeParts) != 2 {
				return nil, fmt.Errorf("invalid cron range: %s", token)
			}
			parsedStart, err := parseCronValue(rangeParts[0], weekday)
			if err != nil {
				return nil, err
			}
			parsedEnd, err := parseCronValue(rangeParts[1], weekday)
			if err != nil {
				return nil, err
			}
			start = parsedStart
			end = parsedEnd
		default:
			value, err := parseCronValue(base, weekday)
			if err != nil {
				return nil, err
			}
			start = value
			end = value
		}

		if start < minValue || end > maxValue || start > end {
			return nil, fmt.Errorf("cron value out of range: %s", token)
		}
		for value := start; value <= end; value += step {
			result[value] = true
		}
	}
	return result, nil
}

func parseCronValue(raw string, weekday bool) (int, error) {
	value, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil {
		return 0, err
	}
	if weekday && value == 7 {
		return 0, nil
	}
	return value, nil
}

func (ts *TaskSchedulerService) notificationTaskQuery(notificationID string) *gorm.DB {
	pattern := fmt.Sprintf("%%\"notification_id\":\"%s\"%%", notificationID)
	altPattern := fmt.Sprintf("%%\"notificationId\":\"%s\"%%", notificationID)
	return ts.db.Where("task_type = ? AND (task_data LIKE ? OR task_data LIKE ?)", "notification", pattern, altPattern)
}
