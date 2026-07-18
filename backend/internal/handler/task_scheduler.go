package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

// TaskSchedulerHandler 任务调度处理器
type TaskSchedulerHandler struct {
	taskSchedulerService *service.TaskSchedulerService
}

// NewTaskSchedulerHandler 创建任务调度处理器
func NewTaskSchedulerHandler(taskSchedulerService *service.TaskSchedulerService) *TaskSchedulerHandler {
	return &TaskSchedulerHandler{
		taskSchedulerService: taskSchedulerService,
	}
}

// CreateScheduledTask 创建定时任务
func (tsh *TaskSchedulerHandler) CreateScheduledTask(c *gin.Context) {
	var req struct {
		UserID      interface{} `json:"userId"`
		StudentID   string      `json:"studentId"`
		TaskType    string      `json:"taskType" binding:"required"`
		TaskData    string      `json:"taskData" binding:"required"`
		CronExpr    string      `json:"cronExpr" binding:"required"`
		Description string      `json:"description"`
		MaxRetries  int         `json:"maxRetries"`
		Priority    int         `json:"priority"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	studentID := resolveTaskRequestID(req.StudentID, req.UserID)
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 userId 或 studentId"})
		return
	}

	task := &model.ScheduledTask{
		StudentID:   studentID,
		TaskType:    req.TaskType,
		TaskData:    req.TaskData,
		CronExpr:    req.CronExpr,
		Description: req.Description,
		Status:      "pending",
		MaxRetries:  req.MaxRetries,
		Priority:    req.Priority,
	}

	if err := tsh.taskSchedulerService.CreateScheduledTask(task); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建定时任务失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "创建成功", "data": normalizeScheduledTaskPayload(*task)})
}

// GetScheduledTasks 获取定时任务列表
func (tsh *TaskSchedulerHandler) GetScheduledTasks(c *gin.Context) {
	userIDStr := firstTaskNonEmpty(c.Query("studentId"), c.Query("userId"))
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

	tasks, total, err := tsh.taskSchedulerService.GetScheduledTasks(userIDStr, status, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取定时任务列表失败"})
		return
	}

	list := make([]gin.H, 0, len(tasks))
	for _, task := range tasks {
		list = append(list, normalizeScheduledTaskPayload(task))
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

// GetScheduledTask 获取单个定时任务详情
func (tsh *TaskSchedulerHandler) GetScheduledTask(c *gin.Context) {
	taskID := strings.TrimSpace(c.Param("id"))
	if taskID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "任务ID无效"})
		return
	}

	task, err := tsh.taskSchedulerService.GetScheduledTask(taskID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "定时任务不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": normalizeScheduledTaskPayload(*task)})
}

// UpdateScheduledTask 更新定时任务
func (tsh *TaskSchedulerHandler) UpdateScheduledTask(c *gin.Context) {
	taskID := strings.TrimSpace(c.Param("id"))
	if taskID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "任务ID无效"})
		return
	}

	var req struct {
		CronExpr    string `json:"cronExpr"`
		Description string `json:"description"`
		Status      string `json:"status"`
		MaxRetries  int    `json:"maxRetries"`
		Priority    int    `json:"priority"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	updates := make(map[string]interface{})
	if req.CronExpr != "" {
		updates["cron_expr"] = req.CronExpr
	}
	if req.Description != "" {
		updates["description"] = req.Description
	}
	if req.Status != "" {
		updates["status"] = req.Status
	}
	if req.MaxRetries > 0 {
		updates["max_retries"] = req.MaxRetries
	}
	if req.Priority > 0 {
		updates["priority"] = req.Priority
	}

	if err := tsh.taskSchedulerService.UpdateScheduledTask(taskID, updates); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "更新定时任务失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "更新成功"})
}

// DeleteScheduledTask 删除定时任务
func (tsh *TaskSchedulerHandler) DeleteScheduledTask(c *gin.Context) {
	taskID := strings.TrimSpace(c.Param("id"))
	if taskID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "任务ID无效"})
		return
	}

	if err := tsh.taskSchedulerService.DeleteScheduledTask(taskID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "删除定时任务失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "删除成功"})
}

// ExecuteTaskNow 立即执行任务
func (tsh *TaskSchedulerHandler) ExecuteTaskNow(c *gin.Context) {
	taskID := strings.TrimSpace(c.Param("id"))
	if taskID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "任务ID无效"})
		return
	}

	if err := tsh.taskSchedulerService.ExecuteTaskNow(taskID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "执行任务失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "任务已提交执行"})
}

// GetTaskStatuses 获取任务执行状态列表
func (tsh *TaskSchedulerHandler) GetTaskStatuses(c *gin.Context) {
	userIDStr := firstTaskNonEmpty(c.Query("studentId"), c.Query("userId"))
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

	statuses, total, err := tsh.taskSchedulerService.GetTaskStatuses(userIDStr, status, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取任务状态列表失败"})
		return
	}

	list := make([]gin.H, 0, len(statuses))
	for _, item := range statuses {
		list = append(list, normalizeTaskStatusPayload(item))
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

// GetTaskStatus 获取单个任务执行状态
func (tsh *TaskSchedulerHandler) GetTaskStatus(c *gin.Context) {
	statusID := strings.TrimSpace(c.Param("id"))
	if statusID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "状态ID无效"})
		return
	}

	status, err := tsh.taskSchedulerService.GetTaskStatus(statusID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "任务状态不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": normalizeTaskStatusPayload(*status)})
}

func resolveTaskRequestID(studentID string, raw interface{}) string {
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

func firstTaskNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func normalizeScheduledTaskPayload(task model.ScheduledTask) gin.H {
	return gin.H{
		"id":            task.ID,
		"taskType":      task.TaskType,
		"task_type":     task.TaskType,
		"taskData":      parseTaskPayload(task.TaskData),
		"task_data":     task.TaskData,
		"cronExpr":      task.CronExpr,
		"cron_expr":     task.CronExpr,
		"description":   task.Description,
		"scheduledAt":   task.ScheduledAt,
		"scheduled_at":  task.ScheduledAt,
		"status":        task.Status,
		"priority":      task.Priority,
		"maxRetries":    task.MaxRetries,
		"max_retries":   task.MaxRetries,
		"retryCount":    task.RetryCount,
		"retry_count":   task.RetryCount,
		"lastAttempt":   task.LastAttempt,
		"last_attempt":  task.LastAttempt,
		"nextAttempt":   task.NextAttempt,
		"next_attempt":  task.NextAttempt,
		"errorMessage":  task.ErrorMessage,
		"error_message": task.ErrorMessage,
		"studentId":     task.StudentID,
		"student_id":    task.StudentID,
		"createdAt":     task.CreatedAt,
		"created_at":    task.CreatedAt,
		"updatedAt":     task.UpdatedAt,
		"updated_at":    task.UpdatedAt,
	}
}

func normalizeTaskStatusPayload(status model.TaskStatus) gin.H {
	return gin.H{
		"id":           status.ID,
		"taskId":       status.TaskID,
		"task_id":      status.TaskID,
		"taskType":     status.TaskType,
		"task_type":    status.TaskType,
		"studentId":    status.StudentID,
		"student_id":   status.StudentID,
		"status":       status.Status,
		"progress":     status.Progress,
		"message":      status.Message,
		"startTime":    status.StartTime,
		"start_time":   status.StartTime,
		"endTime":      status.EndTime,
		"end_time":     status.EndTime,
		"metadata":     parseTaskPayload(status.Metadata),
		"metadataRaw":  status.Metadata,
		"metadata_raw": status.Metadata,
		"createdAt":    status.CreatedAt,
		"created_at":   status.CreatedAt,
		"updatedAt":    status.UpdatedAt,
		"updated_at":   status.UpdatedAt,
	}
}

func parseTaskPayload(raw string) any {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return map[string]any{}
	}

	var payload any
	if err := json.Unmarshal([]byte(raw), &payload); err == nil {
		return payload
	}
	return raw
}
