package service

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
)

// ---- fake AIEngine：只实现 ParseModify + GenerateContent（CoursewareService 所需）----

type fakeModifyAI struct {
	intent    *ModifyIntent
	intentErr error
	genResp   *GenContentStatusResponse
	genErr    error
	lastGenReq *GenContentRequest
}

func (f *fakeModifyAI) ParseModify(_ context.Context, _ ParseModifyRequest) (*ModifyIntent, error) {
	if f.intentErr != nil {
		return nil, f.intentErr
	}
	return f.intent, nil
}

func (f *fakeModifyAI) GenerateContent(_ context.Context, req GenContentRequest) (*GenContentStatusResponse, error) {
	f.lastGenReq = &req
	if f.genErr != nil {
		return nil, f.genErr
	}
	return f.genResp, nil
}

// 以下方法为接口完整性占位（CoursewareService 不调用）
func (f *fakeModifyAI) Chat(ctx context.Context, req ChatRequest) (*ChatResponse, error) { return nil, nil }
func (f *fakeModifyAI) GenerateOutline(ctx context.Context, req OutlineGenerateRequest) (*OutlineGenerateResponse, error) {
	return nil, nil
}
func (f *fakeModifyAI) ReviseOutline(ctx context.Context, req OutlineReviseAIRequest) (*OutlineReviseAIResponse, error) {
	return nil, nil
}

func sampleTeachingNodes() []TeachingNodeItem {
	return []TeachingNodeItem{
		{NodeID: "node_1", Title: "引言", Summary: "导入", Script: "原始讲稿1"},
		{NodeID: "node_2", Title: "冒泡排序", Summary: "原理", Script: "原始讲稿2"},
		{NodeID: "node_3", Title: "快速排序", Summary: "分治", Script: "原始讲稿3"},
	}
}

func newCoursewareTestSvc(ai *fakeModifyAI) *CoursewareService {
	return &CoursewareService{aiClient: ai, store: newMemCoursewareStore()}
}

func mustCreateProject(t *testing.T, svc *CoursewareService) *CoursewareProject {
	t.Helper()
	p, err := svc.CreateProject(context.Background(), "teacher_test", "排序算法")
	if err != nil {
		t.Fatalf("CreateProject: %v", err)
	}
	return p
}

// TestCoursewareCreateAndList —— A1 最小基础：建项目 → 列表可见。
func TestCoursewareCreateAndList(t *testing.T) {
	svc := newCoursewareTestSvc(&fakeModifyAI{})
	p := mustCreateProject(t, svc)
	if p.ProjectID == "" || p.CurrentStep != "s1_intent" || p.Status != "draft" {
		t.Fatalf("项目元数据异常: %+v", p)
	}
	items, err := svc.ListProjects(context.Background(), "teacher_test")
	if err != nil || len(items) != 1 {
		t.Fatalf("列表应含 1 个项目, err=%v len=%d", err, len(items))
	}
	// 他人不可见
	other, _ := svc.ListProjects(context.Background(), "teacher_other")
	if len(other) != 0 {
		t.Fatalf("归属过滤失败: %d", len(other))
	}
}

// TestModifySnapshotPerCall —— A6: 每次修改前自动快照，版本号自增。
func TestModifySnapshotPerCall(t *testing.T) {
	ai := &fakeModifyAI{
		intent: &ModifyIntent{
			TargetType: "node", TargetIDs: []string{"node_2"},
			Action: "simplify", Constraints: []string{"减少文字"},
			Confidence: 0.9,
		},
		genResp: &GenContentStatusResponse{
			Status: "done",
			Nodes: []TeachingNodeItem{
				{NodeID: "node_2", Title: "冒泡排序", Summary: "原理", Script: "精简后的讲稿2"},
			},
		},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	// 第一次修改
	r1, err := svc.Modify(context.Background(), p.ProjectID, "第二页精简", sampleTeachingNodes())
	if err != nil {
		t.Fatalf("Modify#1: %v", err)
	}
	if r1.Clarification != "" {
		t.Fatalf("高置信度不应追问: %s", r1.Clarification)
	}
	// 局部生成被调用且 mode=partial
	if ai.lastGenReq == nil || ai.lastGenReq.Mode != "partial" || len(ai.lastGenReq.TargetNodeIDs) != 1 {
		t.Fatalf("partial 参数异常: %+v", ai.lastGenReq)
	}
	// 目标节点内容被替换，其他节点不变
	if r1.AllNodes[1].Script != "精简后的讲稿2" {
		t.Fatalf("目标节点应被更新, 实际 %q", r1.AllNodes[1].Script)
	}
	if r1.AllNodes[0].Script != "原始讲稿1" || r1.AllNodes[2].Script != "原始讲稿3" {
		t.Fatalf("非目标节点不应变化")
	}
	if r1.NewVersionNo != 1 {
		t.Fatalf("首次修改版本号应为 1, 实际 %d", r1.NewVersionNo)
	}

	// 第二、三次修改 → 版本 2、3
	for i := 0; i < 2; i++ {
		if _, err := svc.Modify(context.Background(), p.ProjectID, "再改一次", r1.AllNodes); err != nil {
			t.Fatalf("Modify#%d: %v", i+2, err)
		}
	}
	versions, _ := svc.ModifyHistory(context.Background(), p.ProjectID)
	if len(versions) != 3 {
		t.Fatalf("3 次修改应有 3 个快照, 实际 %d", len(versions))
	}
	if versions[2].VersionNo != 3 {
		t.Fatalf("版本号应自增到 3, 实际 %d", versions[2].VersionNo)
	}
	// 首个快照保存的是"修改前"状态
	var snapNodes []TeachingNodeItem
	_ = json.Unmarshal([]byte(versions[0].NodesJSON), &snapNodes)
	if len(snapNodes) != 3 || snapNodes[1].Script != "原始讲稿2" {
		t.Fatalf("首个快照应为修改前状态, 实际 %+v", snapNodes)
	}
}

// TestModifyClarification —— A6: 低置信度返回追问，不执行修改。
func TestModifyClarification(t *testing.T) {
	ai := &fakeModifyAI{
		intent: &ModifyIntent{
			TargetType: "global", Action: "rewrite",
			Confidence: 0.3, ClarificationNeeded: true,
			ClarificationQuestion: "你是指减少文字量还是拆分页面？",
		},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	result, err := svc.Modify(context.Background(), p.ProjectID, "改一下", sampleTeachingNodes())
	if err != nil {
		t.Fatalf("Modify: %v", err)
	}
	if result.Clarification == "" {
		t.Fatal("低置信度应返回追问")
	}
	// 不应有版本快照产生
	versions, _ := svc.ModifyHistory(context.Background(), p.ProjectID)
	if len(versions) != 0 {
		t.Fatalf("追问时不应产生快照, 实际 %d", len(versions))
	}
}

// TestModifyDeleteAction —— 结构类动作（delete）Go 本地执行，不调 Python。
func TestModifyDeleteAction(t *testing.T) {
	ai := &fakeModifyAI{
		intent: &ModifyIntent{
			TargetType: "node", TargetIDs: []string{"node_2"},
			Action: "delete", Confidence: 0.95,
		},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	result, err := svc.Modify(context.Background(), p.ProjectID, "删掉冒泡排序", sampleTeachingNodes())
	if err != nil {
		t.Fatalf("Modify(delete): %v", err)
	}
	if len(result.AllNodes) != 2 {
		t.Fatalf("删除后应剩 2 节点, 实际 %d", len(result.AllNodes))
	}
	if ai.lastGenReq != nil {
		t.Fatal("delete 不应触发内容生成")
	}
}

// TestModifyReorderAction —— 结构类动作（reorder）交换位置并重建链。
func TestModifyReorderAction(t *testing.T) {
	ai := &fakeModifyAI{
		intent: &ModifyIntent{
			TargetType: "node", TargetIDs: []string{"node_1", "node_3"},
			Action: "reorder", Confidence: 0.95,
		},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	result, err := svc.Modify(context.Background(), p.ProjectID, "首尾换一下", sampleTeachingNodes())
	if err != nil {
		t.Fatalf("Modify(reorder): %v", err)
	}
	if result.AllNodes[0].NodeID != "node_3" || result.AllNodes[2].NodeID != "node_1" {
		t.Fatalf("交换失败: %s, %s", result.AllNodes[0].NodeID, result.AllNodes[2].NodeID)
	}
	if result.AllNodes[0].NextNodeID != "node_2" {
		t.Fatalf("链表重建失败: next=%s", result.AllNodes[0].NextNodeID)
	}
}

// TestRollbackClonesVersion —— A7: 回滚 = 克隆为新版本，历史保留。
func TestRollbackClonesVersion(t *testing.T) {
	ai := &fakeModifyAI{
		intent: &ModifyIntent{
			TargetType: "node", TargetIDs: []string{"node_2"},
			Action: "simplify", Confidence: 0.9,
		},
		genResp: &GenContentStatusResponse{
			Status: "done",
			Nodes:  []TeachingNodeItem{{NodeID: "node_2", Script: "v2 内容"}},
		},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	// 3 次修改 → v1/v2/v3
	nodes := sampleTeachingNodes()
	for i := 0; i < 3; i++ {
		if _, err := svc.Modify(context.Background(), p.ProjectID, "改", nodes); err != nil {
			t.Fatalf("Modify#%d: %v", i+1, err)
		}
	}

	// 回滚到 v1 → 生成 v4，内容 = v1 的修改前状态（原始 nodes）
	rb, err := svc.Rollback(context.Background(), p.ProjectID, 1)
	if err != nil {
		t.Fatalf("Rollback: %v", err)
	}
	if rb.NewVersionNo != 4 {
		t.Fatalf("回滚应生成 v4, 实际 %d", rb.NewVersionNo)
	}
	if len(rb.Nodes) != 3 || rb.Nodes[1].Script != "原始讲稿2" {
		t.Fatalf("回滚内容应为 v1 状态, 实际 %+v", rb.Nodes)
	}
	// v1/v2/v3 仍可查
	versions, _ := svc.Versions(context.Background(), p.ProjectID)
	if len(versions) != 4 {
		t.Fatalf("版本链应含 4 条(v1-v4), 实际 %d", len(versions))
	}
	if _, err := svc.GetVersion(context.Background(), p.ProjectID, 2); err != nil {
		t.Fatalf("v2 应仍可查: %v", err)
	}
}

// TestRollbackNotFound —— 回滚不存在的版本 → 404。
func TestRollbackNotFound(t *testing.T) {
	svc := newCoursewareTestSvc(&fakeModifyAI{})
	p := mustCreateProject(t, svc)
	_, err := svc.Rollback(context.Background(), p.ProjectID, 99)
	if !errors.Is(err, ErrVersionNotFound) {
		t.Fatalf("应返回 ErrVersionNotFound, 实际 %v", err)
	}
}
