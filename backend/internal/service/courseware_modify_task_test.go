package service

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"
)

func TestModifyTaskResumesAfterGoRestart(t *testing.T) {
	shrinkContentPolling(t, time.Millisecond, time.Second)
	ai := &fakeModifyAI{statusResp: &GenContentStatusResponse{Status: "done", Nodes: []TeachingNodeItem{{NodeID: "node_2", Summary: "恢复后生成的正文"}}}}
	first := newCoursewareTestSvc(ai)
	project := mustCreateProject(t, first)
	beforeJSON, _ := json.Marshal(sampleTeachingNodes())
	intentJSON, _ := json.Marshal(asyncIntent("rewrite"))
	task := &coursewareModifyTaskRow{TaskID: "mod_restarted", ProjectID: project.ProjectID, ContentID: "python_content", Instruction: "重写第二页正文", BeforeJSON: string(beforeJSON), IntentJSON: string(intentJSON), Status: "processing", CreatedAt: time.Now()}
	if err := first.taskStore().CreateModifyTask(context.Background(), task); err != nil {
		t.Fatal(err)
	}
	restarted := &CoursewareService{aiClient: ai, store: first.store}
	if err := restarted.ResumeModifyTasks(context.Background()); err != nil {
		t.Fatal(err)
	}
	result := awaitModifyTask(t, restarted, project.ProjectID, task.TaskID)
	if result.Status != "done" || result.NewVersionNo != 1 {
		t.Fatalf("重启恢复失败: %+v", result)
	}
}

func TestModifyTaskCompletesAfterOldWaitBudgetAndIsIdempotent(t *testing.T) {
	shrinkContentPolling(t, 2*time.Millisecond, 20*time.Millisecond)
	modifyTaskBudget = time.Second
	ai := &fakeModifyAI{
		intent:  asyncIntent("rewrite"),
		genResp: &GenContentStatusResponse{ContentID: "late_content", Status: "generating"},
		statusResp: &GenContentStatusResponse{ContentID: "late_content", Status: "done", Nodes: []TeachingNodeItem{
			{NodeID: "node_2", Title: "冒泡排序", Summary: "新的页面正文", Script: "新讲稿"},
		}},
	}
	for i := 0; i < 35; i++ {
		ai.statusQueue = append(ai.statusQueue, &GenContentStatusResponse{Status: "generating"})
	}
	svc := newCoursewareTestSvc(ai)
	project := mustCreateProject(t, svc)
	before := sampleTeachingNodes()
	started, err := svc.Modify(context.Background(), project.ProjectID, "重写第二页正文", before)
	if err != nil || started.Status != "processing" {
		t.Fatalf("任务应立即受理: %+v %v", started, err)
	}
	time.Sleep(30 * time.Millisecond) // 等价于超过缩短后的旧 90 秒请求窗口
	if versions, _ := svc.ModifyHistory(context.Background(), project.ProjectID); len(versions) != 0 {
		t.Fatalf("生成未完成时不应保存版本: %d", len(versions))
	}
	result := awaitModifyTask(t, svc, project.ProjectID, started.TaskID)
	if result.Status != "done" || result.NewVersionNo != 1 {
		t.Fatalf("后台完成后应保存: %+v", result)
	}
	if result.AllNodes[0].Title != before[0].Title || result.AllNodes[0].Summary != before[0].Summary || result.AllNodes[0].Script != before[0].Script ||
		result.AllNodes[2].Title != before[2].Title || result.AllNodes[2].Summary != before[2].Summary || result.AllNodes[2].Script != before[2].Script {
		t.Fatal("非目标页发生变化")
	}
	for i := 0; i < 3; i++ {
		again, err := svc.ModifyTaskStatus(context.Background(), project.ProjectID, started.TaskID)
		if err != nil || again.NewVersionNo != 1 {
			t.Fatalf("重复查询应返回同一结果: %+v %v", again, err)
		}
	}
	task, _ := svc.taskStore().GetModifyTask(context.Background(), project.ProjectID, started.TaskID)
	if err := svc.finishModifyTask(context.Background(), task, ai.statusResp.Nodes); err != nil {
		t.Fatal(err)
	}
	versions, _ := svc.ModifyHistory(context.Background(), project.ProjectID)
	if len(versions) != 1 {
		t.Fatalf("重复完成不能再写版本: %d", len(versions))
	}
}

func TestModifyTaskRejectsUnchangedBody(t *testing.T) {
	shrinkContentPolling(t, time.Millisecond, time.Second)
	ai := &fakeModifyAI{intent: asyncIntent("rewrite"), genResp: &GenContentStatusResponse{ContentID: "unchanged", Status: "generating"},
		statusResp: &GenContentStatusResponse{Status: "done", Nodes: []TeachingNodeItem{{NodeID: "node_2", Summary: "原理", Script: "新讲稿"}}}}
	svc := newCoursewareTestSvc(ai)
	project := mustCreateProject(t, svc)
	started, err := svc.Modify(context.Background(), project.ProjectID, "重写第二页正文", sampleTeachingNodes())
	if err != nil {
		t.Fatal(err)
	}
	result := awaitModifyTask(t, svc, project.ProjectID, started.TaskID)
	if result.Status != "failed" || !strings.Contains(result.Error, "正文") {
		t.Fatalf("原正文不能宣称成功: %+v", result)
	}
	versions, _ := svc.ModifyHistory(context.Background(), project.ProjectID)
	if len(versions) != 0 {
		t.Fatal("失败不应保存版本")
	}
}

type failingCompleteStore struct{ *memCoursewareStore }

func (f *failingCompleteStore) CompleteModifyTask(context.Context, *coursewareModifyTaskRow, []TeachingNodeItem, *ModifyResult) error {
	return errors.New("version database unavailable")
}

func TestModifyTaskSaveFailureKeepsPreviousVersion(t *testing.T) {
	shrinkContentPolling(t, time.Millisecond, time.Second)
	ai := &fakeModifyAI{intent: asyncIntent("rewrite"), genResp: &GenContentStatusResponse{ContentID: "save_fail", Status: "generating"},
		statusResp: &GenContentStatusResponse{Status: "done", Nodes: []TeachingNodeItem{{NodeID: "node_2", Summary: "新正文"}}}}
	svc := newCoursewareTestSvc(ai)
	svc.store = &failingCompleteStore{svc.store.(*memCoursewareStore)}
	project := mustCreateProject(t, svc)
	started, err := svc.Modify(context.Background(), project.ProjectID, "重写第二页正文", sampleTeachingNodes())
	if err != nil {
		t.Fatal(err)
	}
	result := awaitModifyTask(t, svc, project.ProjectID, started.TaskID)
	if result.Status != "failed" || !strings.Contains(result.Error, "version database unavailable") {
		t.Fatalf("保存失败应可见: %+v", result)
	}
	versions, _ := svc.ModifyHistory(context.Background(), project.ProjectID)
	if len(versions) != 0 {
		t.Fatal("保存失败不能产生部分版本")
	}
}
