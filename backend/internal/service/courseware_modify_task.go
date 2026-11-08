package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

// Only S4 partial revisions use this durable task. The Python content task may
// outlive the HTTP request that started it.
type coursewareModifyTaskRow struct {
	TaskID      string    `gorm:"column:task_id;size:64;primaryKey"`
	ProjectID   string    `gorm:"column:project_id;size:64;index"`
	ContentID   string    `gorm:"column:content_id;size:64"`
	Instruction string    `gorm:"column:instruction;type:text"`
	BeforeJSON  string    `gorm:"column:before_json;type:text"`
	IntentJSON  string    `gorm:"column:intent_json;type:text"`
	Status      string    `gorm:"column:status;size:20;index"`
	Error       string    `gorm:"column:error;type:text"`
	ResultJSON  string    `gorm:"column:result_json;type:text"`
	CreatedAt   time.Time `gorm:"column:created_at"`
	UpdatedAt   time.Time `gorm:"column:updated_at"`
}

func (coursewareModifyTaskRow) TableName() string { return "courseware_modify_tasks" }

type modifyTaskStore interface {
	CreateModifyTask(context.Context, *coursewareModifyTaskRow) error
	GetModifyTask(context.Context, string, string) (*coursewareModifyTaskRow, error)
	PendingModifyTasks(context.Context, string) ([]coursewareModifyTaskRow, error)
	FailModifyTask(context.Context, string, string, string) error
	CompleteModifyTask(context.Context, *coursewareModifyTaskRow, []TeachingNodeItem, *ModifyResult) error
}

var modifyTaskPollInterval = 500 * time.Millisecond
var modifyTaskBudget = 20 * time.Minute
var modifyTaskWorkerMu sync.Mutex
var activeModifyWorkers = map[string]bool{}

func (s *CoursewareService) taskStore() modifyTaskStore { return s.store.(modifyTaskStore) }

func (s *CoursewareService) startModifyTask(ctx context.Context, projectID, instruction string, before []TeachingNodeItem, intent ModifyIntent, first *GenContentStatusResponse) (*ModifyResult, error) {
	if first.ContentID == "" {
		return nil, fmt.Errorf("局部重生成未返回 content_id")
	}
	beforeJSON, err := json.Marshal(before)
	if err != nil {
		return nil, err
	}
	intentJSON, err := json.Marshal(intent)
	if err != nil {
		return nil, err
	}
	now := time.Now()
	task := &coursewareModifyTaskRow{
		TaskID: "mod_" + uuid.NewString(), ProjectID: projectID, ContentID: first.ContentID,
		Instruction: instruction, BeforeJSON: string(beforeJSON), IntentJSON: string(intentJSON),
		Status: "processing", CreatedAt: now, UpdatedAt: now,
	}
	if err := s.taskStore().CreateModifyTask(ctx, task); err != nil {
		return nil, err
	}
	s.resumeModifyTask(*task)
	return &ModifyResult{TaskID: task.TaskID, Status: "processing", Intent: intent}, nil
}

// ResumeModifyTasks is called at server startup. A restarted Go process picks
// up Python tasks that were already accepted instead of losing their result.
func (s *CoursewareService) ResumeModifyTasks(ctx context.Context) error {
	tasks, err := s.taskStore().PendingModifyTasks(ctx, "")
	if err != nil {
		return err
	}
	for _, task := range tasks {
		s.resumeModifyTask(task)
	}
	return nil
}

func (s *CoursewareService) resumeModifyTask(task coursewareModifyTaskRow) {
	modifyTaskWorkerMu.Lock()
	if activeModifyWorkers[task.TaskID] {
		modifyTaskWorkerMu.Unlock()
		return
	}
	activeModifyWorkers[task.TaskID] = true
	modifyTaskWorkerMu.Unlock()
	go func() {
		defer func() {
			modifyTaskWorkerMu.Lock()
			delete(activeModifyWorkers, task.TaskID)
			modifyTaskWorkerMu.Unlock()
		}()
		s.runModifyTask(task)
	}()
}

func (s *CoursewareService) runModifyTask(task coursewareModifyTaskRow) {
	ctx := context.Background()
	deadline := task.CreatedAt.Add(modifyTaskBudget)
	markFailed := func(message string) {
		if err := s.taskStore().FailModifyTask(ctx, task.ProjectID, task.TaskID, message); err != nil {
			log.Printf("S4 task %s: failed to persist terminal status: %v", task.TaskID, err)
		}
	}
	for {
		status, err := s.aiClient.ContentStatus(ctx, task.ContentID)
		if err == nil && status != nil {
			state := strings.ToLower(strings.TrimSpace(status.Status))
			if state == "failed" || state == "error" || status.Error != "" {
				message := status.Error
				if message == "" {
					message = "AI 引擎生成失败"
				}
				markFailed(message)
				return
			}
			if state == "done" || state == "completed" || state == "success" {
				if err := s.finishModifyTask(ctx, &task, status.Nodes); err != nil {
					markFailed(err.Error())
				}
				return
			}
		}
		if time.Now().After(deadline) {
			markFailed("局部生成超过任务处理期限")
			return
		}
		time.Sleep(modifyTaskPollInterval)
	}
}

func (s *CoursewareService) finishModifyTask(ctx context.Context, task *coursewareModifyTaskRow, partial []TeachingNodeItem) error {
	var before []TeachingNodeItem
	var intent ModifyIntent
	if err := json.Unmarshal([]byte(task.BeforeJSON), &before); err != nil {
		return err
	}
	if err := json.Unmarshal([]byte(task.IntentJSON), &intent); err != nil {
		return err
	}
	if len(partial) == 0 {
		return fmt.Errorf("局部生成完成但没有返回节点")
	}
	seen := map[string]bool{}
	for _, node := range partial {
		seen[node.NodeID] = true
	}
	for _, id := range intent.TargetIDs {
		if !seen[id] {
			return fmt.Errorf("目标节点 %s 未返回", id)
		}
	}
	updated := mergePartialResult(before, partial, intent.TargetIDs)
	if strings.Contains(task.Instruction, "正文") && !hasBodyTargetChange(before, updated, intent.TargetIDs) {
		return fmt.Errorf("AI 未改写目标页面正文")
	}
	if !hasVisibleTargetChange(before, updated, intent.TargetIDs) {
		return fmt.Errorf("AI 未修改目标页面可见内容")
	}
	if wantsRemoveTeachingText(task.Instruction, intent.Constraints) {
		updated = clearTeachingText(updated, intent.TargetIDs)
	}
	updated = ensureElementMetadata(updated)
	updated = syncElementContent(updated)
	targetSet := map[string]bool{}
	for _, id := range intent.TargetIDs {
		targetSet[id] = true
	}
	for i := range updated {
		if !targetSet[updated[i].NodeID] {
			updated[i] = before[i]
		}
	}
	modified := make([]TeachingNodeItem, 0, len(intent.TargetIDs))
	for _, node := range updated {
		for _, id := range intent.TargetIDs {
			if node.NodeID == id {
				modified = append(modified, node)
				break
			}
		}
	}
	result := &ModifyResult{TaskID: task.TaskID, Status: "done", AllNodes: updated, ModifiedNodes: modified,
		Intent: intent, Presentation: intent.Presentation, ModifiedElementIDs: intent.TargetElementIDs}
	return s.taskStore().CompleteModifyTask(ctx, task, before, result)
}

func (s *CoursewareService) ModifyTaskStatus(ctx context.Context, projectID, taskID string) (*ModifyResult, error) {
	task, err := s.taskStore().GetModifyTask(ctx, projectID, taskID)
	if err != nil {
		return nil, err
	}
	if task.Status == "done" {
		var result ModifyResult
		if err := json.Unmarshal([]byte(task.ResultJSON), &result); err != nil {
			return nil, err
		}
		return &result, nil
	}
	return &ModifyResult{TaskID: task.TaskID, Status: task.Status, Error: task.Error}, nil
}

func (g *gormCoursewareStore) CreateModifyTask(ctx context.Context, task *coursewareModifyTaskRow) error {
	return g.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var project coursewareProjectRow
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Where("id = ?", task.ProjectID).First(&project).Error; err != nil {
			return err
		}
		var count int64
		if err := tx.Model(&coursewareModifyTaskRow{}).Where("project_id = ? AND status = ?", task.ProjectID, "processing").Count(&count).Error; err != nil {
			return err
		}
		if count > 0 {
			return fmt.Errorf("当前课件已有局部修改任务，请等待完成")
		}
		return tx.Create(task).Error
	})
}

func (g *gormCoursewareStore) GetModifyTask(ctx context.Context, projectID, taskID string) (*coursewareModifyTaskRow, error) {
	var task coursewareModifyTaskRow
	err := g.db.WithContext(ctx).Where("project_id = ? AND task_id = ?", projectID, taskID).First(&task).Error
	return &task, err
}

func (g *gormCoursewareStore) PendingModifyTasks(ctx context.Context, projectID string) ([]coursewareModifyTaskRow, error) {
	var tasks []coursewareModifyTaskRow
	query := g.db.WithContext(ctx).Where("status = ?", "processing")
	if projectID != "" {
		query = query.Where("project_id = ?", projectID)
	}
	err := query.Find(&tasks).Error
	return tasks, err
}

func (g *gormCoursewareStore) FailModifyTask(ctx context.Context, projectID, taskID, message string) error {
	return g.db.WithContext(ctx).Model(&coursewareModifyTaskRow{}).
		Where("project_id = ? AND task_id = ? AND status = ?", projectID, taskID, "processing").
		Updates(map[string]any{"status": "failed", "error": message, "updated_at": time.Now()}).Error
}

func draftWithModifiedNodes(raw string, nodes []TeachingNodeItem) (string, error) {
	draft := map[string]any{}
	if strings.TrimSpace(raw) != "" {
		if err := json.Unmarshal([]byte(raw), &draft); err != nil {
			return "", err
		}
	}
	generation, _ := draft["generation"].(map[string]any)
	if generation == nil {
		generation = map[string]any{}
	}
	generation["nodes"] = nodes
	draft["generation"] = generation
	encoded, err := json.Marshal(draft)
	return string(encoded), err
}

func (g *gormCoursewareStore) CompleteModifyTask(ctx context.Context, task *coursewareModifyTaskRow, before []TeachingNodeItem, result *ModifyResult) error {
	return g.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var current coursewareModifyTaskRow
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Where("task_id = ? AND project_id = ?", task.TaskID, task.ProjectID).First(&current).Error; err != nil {
			return err
		}
		if current.Status == "done" {
			return nil
		}
		if current.Status != "processing" {
			return fmt.Errorf("任务已结束: %s", current.Status)
		}
		var project coursewareProjectRow
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Where("id = ?", task.ProjectID).First(&project).Error; err != nil {
			return err
		}
		var maxNo int
		if err := tx.Model(&coursewareVersionRow{}).Where("project_id = ?", task.ProjectID).Select("COALESCE(MAX(version_no), 0)").Scan(&maxNo).Error; err != nil {
			return err
		}
		beforeJSON, err := json.Marshal(before)
		if err != nil {
			return err
		}
		afterJSON, err := json.Marshal(result.AllNodes)
		if err != nil {
			return err
		}
		versionID := "ver_" + strings.TrimPrefix(task.TaskID, "mod_")
		version := &CoursewareVersion{VersionID: versionID, ProjectID: task.ProjectID, VersionNo: maxNo + 1,
			NodesJSON: string(afterJSON), BeforeSnapshotJSON: string(beforeJSON),
			PresentationJSON: presentationJSON(presentationFromNodes(result.AllNodes)),
			SnapshotJSON:     snapshotJSON(result.AllNodes, presentationFromNodes(result.AllNodes), nil),
			ModifyInstr:      task.Instruction, VersionSummary: task.Instruction, CreatedAt: time.Now()}
		row := versionToRow(version)
		row.OwnerID = project.OwnerID
		if err := tx.Create(row).Error; err != nil {
			return err
		}
		var draft coursewareDraftRow
		err = tx.Where("project_id = ?", task.ProjectID).First(&draft).Error
		if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
			return err
		}
		draftJSON, err := draftWithModifiedNodes(draft.DraftJSON, result.AllNodes)
		if err != nil {
			return err
		}
		if err := tx.Save(&coursewareDraftRow{ProjectID: task.ProjectID, DraftJSON: draftJSON, UpdatedAt: time.Now()}).Error; err != nil {
			return err
		}
		if err := tx.Model(&coursewareProjectRow{}).Where("id = ?", task.ProjectID).Updates(map[string]any{"status": "done", "updated_at": time.Now()}).Error; err != nil {
			return err
		}
		result.PreviousVersionID = versionID
		result.PreviousVersionNo = version.VersionNo
		result.NewVersionNo = version.VersionNo
		resultJSON, err := json.Marshal(result)
		if err != nil {
			return err
		}
		return tx.Model(&coursewareModifyTaskRow{}).Where("task_id = ?", task.TaskID).
			Updates(map[string]any{"status": "done", "result_json": string(resultJSON), "updated_at": time.Now()}).Error
	})
}

func (m *memCoursewareStore) CreateModifyTask(_ context.Context, task *coursewareModifyTaskRow) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, existing := range m.modifyTasks {
		if existing.ProjectID == task.ProjectID && existing.Status == "processing" {
			return fmt.Errorf("当前课件已有局部修改任务")
		}
	}
	copy := *task
	m.modifyTasks[task.TaskID] = &copy
	return nil
}

func (m *memCoursewareStore) GetModifyTask(_ context.Context, projectID, taskID string) (*coursewareModifyTaskRow, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	task := m.modifyTasks[taskID]
	if task == nil || task.ProjectID != projectID {
		return nil, gorm.ErrRecordNotFound
	}
	copy := *task
	return &copy, nil
}

func (m *memCoursewareStore) PendingModifyTasks(_ context.Context, projectID string) ([]coursewareModifyTaskRow, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := []coursewareModifyTaskRow{}
	for _, task := range m.modifyTasks {
		if task.Status == "processing" && (projectID == "" || projectID == task.ProjectID) {
			out = append(out, *task)
		}
	}
	return out, nil
}

func (m *memCoursewareStore) FailModifyTask(_ context.Context, projectID, taskID, message string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	task := m.modifyTasks[taskID]
	if task == nil || task.ProjectID != projectID {
		return gorm.ErrRecordNotFound
	}
	if task.Status == "processing" {
		task.Status = "failed"
		task.Error = message
		task.UpdatedAt = time.Now()
	}
	return nil
}

func (m *memCoursewareStore) CompleteModifyTask(_ context.Context, task *coursewareModifyTaskRow, before []TeachingNodeItem, result *ModifyResult) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	current := m.modifyTasks[task.TaskID]
	if current == nil {
		return gorm.ErrRecordNotFound
	}
	if current.Status == "done" {
		return nil
	}
	if current.Status != "processing" {
		return fmt.Errorf("任务已结束: %s", current.Status)
	}
	beforeJSON, err := json.Marshal(before)
	if err != nil {
		return err
	}
	afterJSON, err := json.Marshal(result.AllNodes)
	if err != nil {
		return err
	}
	draftJSON, err := draftWithModifiedNodes(m.drafts[task.ProjectID], result.AllNodes)
	if err != nil {
		return err
	}
	versionNo := len(m.versions[task.ProjectID]) + 1
	versionID := "ver_" + strings.TrimPrefix(task.TaskID, "mod_")
	version := &CoursewareVersion{VersionID: versionID, ProjectID: task.ProjectID, VersionNo: versionNo,
		NodesJSON: string(afterJSON), BeforeSnapshotJSON: string(beforeJSON),
		PresentationJSON: presentationJSON(presentationFromNodes(result.AllNodes)),
		SnapshotJSON:     snapshotJSON(result.AllNodes, presentationFromNodes(result.AllNodes), nil),
		ModifyInstr:      task.Instruction, VersionSummary: task.Instruction, CreatedAt: time.Now()}
	result.PreviousVersionID = versionID
	result.PreviousVersionNo = versionNo
	result.NewVersionNo = versionNo
	resultJSON, err := json.Marshal(result)
	if err != nil {
		return err
	}
	m.versions[task.ProjectID] = append(m.versions[task.ProjectID], version)
	m.drafts[task.ProjectID] = draftJSON
	if project := m.projects[task.ProjectID]; project != nil {
		project.Status = "done"
	}
	current.Status = "done"
	current.ResultJSON = string(resultJSON)
	current.UpdatedAt = time.Now()
	return nil
}
