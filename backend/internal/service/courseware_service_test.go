package service

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"
)

// ---- fake：只实现 modifyClient 窄接口 ----

type fakeModifyAI struct {
	intent       *ModifyIntent
	intentErr    error
	genResp      *GenContentStatusResponse
	genErr       error
	lastGenReq   *GenContentRequest
	statusResp   *GenContentStatusResponse
	statusErr    error
	statusCalls  int
	statusQueue  []*GenContentStatusResponse
	statusErrFor int
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

func (f *fakeModifyAI) ContentStatus(_ context.Context, _ string) (*GenContentStatusResponse, error) {
	f.statusCalls++
	if f.statusErrFor > 0 && f.statusCalls <= f.statusErrFor {
		return nil, f.statusErr
	}
	if len(f.statusQueue) > 0 {
		response := f.statusQueue[0]
		f.statusQueue = f.statusQueue[1:]
		return response, nil
	}
	if f.statusErrFor > 0 {
		return f.statusResp, nil
	}
	if f.statusResp == nil && f.statusErr == nil {
		return &GenContentStatusResponse{Status: "generating"}, nil
	}
	return f.statusResp, f.statusErr
}

func TestModifyWaitsForGeneratedNodes(t *testing.T) {
	ai := &fakeModifyAI{
		intent:     &ModifyIntent{TargetType: "node", TargetIDs: []string{"node_2"}, Action: "expand", Confidence: 0.9},
		genResp:    &GenContentStatusResponse{ContentID: "content_1", Status: "generating"},
		statusResp: &GenContentStatusResponse{ContentID: "content_1", Status: "done", Nodes: []TeachingNodeItem{{NodeID: "node_2", Title: "冒泡排序", Summary: "新增生活案例", Script: "新的讲稿"}}},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)
	result, err := svc.Modify(context.Background(), p.ProjectID, "第二页增加生活案例", sampleTeachingNodes())
	if err != nil {
		t.Fatalf("Modify: %v", err)
	}
	if ai.statusCalls != 1 || result.AllNodes[1].Summary != "新增生活案例" {
		t.Fatalf("应等待完成并应用结果: calls=%d node=%+v", ai.statusCalls, result.AllNodes[1])
	}
}

func TestModifyDoesNotSaveEmptyOrFailedGeneration(t *testing.T) {
	for _, status := range []string{"done", "failed"} {
		t.Run(status, func(t *testing.T) {
			ai := &fakeModifyAI{
				intent:     &ModifyIntent{TargetType: "node", TargetIDs: []string{"node_2"}, Action: "expand", Confidence: 0.9},
				genResp:    &GenContentStatusResponse{ContentID: "content_1", Status: "generating"},
				statusResp: &GenContentStatusResponse{ContentID: "content_1", Status: status, Error: "upstream failed"},
			}
			svc := newCoursewareTestSvc(ai)
			p := mustCreateProject(t, svc)
			if _, err := svc.Modify(context.Background(), p.ProjectID, "第二页增加案例", sampleTeachingNodes()); err == nil {
				t.Fatal("空结果或失败应返回错误")
			}
			versions, _ := svc.ModifyHistory(context.Background(), p.ProjectID)
			if len(versions) != 0 {
				t.Fatalf("失败不应保存版本: %d", len(versions))
			}
		})
	}
}

func TestModifyExpandRejectsScriptOnlyChange(t *testing.T) {
	ai := &fakeModifyAI{
		intent:  &ModifyIntent{TargetType: "node", TargetIDs: []string{"node_2"}, Action: "expand", Confidence: 0.9},
		genResp: &GenContentStatusResponse{Status: "done", Nodes: []TeachingNodeItem{{NodeID: "node_2", Title: "冒泡排序", Summary: "原理", Script: "只改了讲稿"}}},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)
	if _, err := svc.Modify(context.Background(), p.ProjectID, "第二页增加案例", sampleTeachingNodes()); err == nil {
		t.Fatal("仅修改讲稿不应被标记为 PPT 扩写成功")
	}
	versions, _ := svc.ModifyHistory(context.Background(), p.ProjectID)
	if len(versions) != 0 {
		t.Fatalf("可见内容未变不应保存版本: %d", len(versions))
	}
}

func sampleTeachingNodes() []TeachingNodeItem {
	return []TeachingNodeItem{
		{NodeID: "node_1", Title: "引言", Summary: "导入", Script: "原始讲稿1"},
		{NodeID: "node_2", Title: "冒泡排序", Summary: "原理", Script: "原始讲稿2"},
		{NodeID: "node_3", Title: "快速排序", Summary: "分治", Script: "原始讲稿3"},
	}
}

func TestApplyDirectSpecialPageTitle(t *testing.T) {
	nodes := []TeachingNodeItem{
		{NodeID: "__auto_cover__", Title: "旧标题", NodeType: "cover"},
		{NodeID: "node_1", Title: "正文", NodeType: "content"},
	}
	updated, modified, ok := applyDirectSpecialPageTitle(
		"这页title换成排序算法",
		ModifyIntent{TargetIDs: []string{"__auto_cover__"}},
		nodes,
	)

	if !ok || len(modified) != 1 || updated[0].Title != "排序算法" {
		t.Fatalf("special title edit not applied: ok=%v modified=%v nodes=%+v", ok, modified, updated)
	}
	if updated[1].Title != "正文" {
		t.Fatalf("normal node changed unexpectedly: %+v", updated[1])
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
	r1, err := svc.Modify(context.Background(), p.ProjectID, "第二页精简", sampleTeachingNodes(), "")
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
		if _, err := svc.Modify(context.Background(), p.ProjectID, "再改一次", r1.AllNodes, ""); err != nil {
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
	draftJSON, err := svc.GetDraft(context.Background(), p.ProjectID)
	if err != nil {
		t.Fatalf("读取修改后的草稿失败: %v", err)
	}
	var draft struct {
		Generation struct {
			Nodes []TeachingNodeItem `json:"nodes"`
		} `json:"generation"`
	}
	if err := json.Unmarshal([]byte(draftJSON), &draft); err != nil {
		t.Fatalf("修改后的草稿应保持对象结构: %v; raw=%s", err, draftJSON)
	}
	if len(draft.Generation.Nodes) != len(r1.AllNodes) {
		t.Fatalf("修改后的草稿应保存完整生成节点, 实际 %d", len(draft.Generation.Nodes))
	}
	// 正式版本保存修改后状态，BeforeSnapshotJSON 保存修改前状态。
	var snapNodes []TeachingNodeItem
	_ = json.Unmarshal([]byte(versions[0].BeforeSnapshotJSON), &snapNodes)
	if len(snapNodes) != 3 || snapNodes[1].Script != "原始讲稿2" {
		t.Fatalf("首个快照应为修改前状态, 实际 %+v", snapNodes)
	}
}

// TestModifyPartialCarriesCourseNameAndBoundEvidence —— 局部重生成必须带上
// course_name 与目标页绑定的证据 chunk_id。
//
// 回归的是「局部修改凭空重写」：此前 Go 侧构造 GenContentRequest 时只填了
// nodes/target/action/constraints，course_name 与证据都没传，Python 侧拿不到
// 任何材料，只能靠模型自由发挥 —— 与 S3 大纲/内容生成走 RAG 的行为不一致。
func TestModifyPartialCarriesCourseNameAndBoundEvidence(t *testing.T) {
	ai := &fakeModifyAI{
		intent: &ModifyIntent{
			TargetType: "node", TargetIDs: []string{"node_2"},
			Action: "expand", Confidence: 0.9,
		},
		genResp: &GenContentStatusResponse{Status: "done", Nodes: []TeachingNodeItem{{NodeID: "node_2", Title: "冒泡排序", Summary: "增加证据", Script: "证据讲稿"}}},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc) // 项目标题为 "排序算法"

	// node_2 绑定两个 chunk（含一个重复项，应去重），node_3 的不该被带上
	if _, err := svc.SavePageBindings(context.Background(), p.ProjectID, []PageEvidenceBinding{
		{PageID: "node_2", EvidenceRefs: []string{"chunk_a", "chunk_b", "chunk_a"}},
		{PageID: "node_3", EvidenceRefs: []string{"chunk_z"}},
	}); err != nil {
		t.Fatalf("SavePageBindings: %v", err)
	}

	if _, err := svc.Modify(context.Background(), p.ProjectID, "第二页展开讲讲", sampleTeachingNodes(), ""); err != nil {
		t.Fatalf("Modify: %v", err)
	}
	if ai.lastGenReq == nil {
		t.Fatal("应调用局部生成")
	}
	if ai.lastGenReq.CourseName != "排序算法" {
		t.Fatalf("course_name 应为项目标题, 实际 %q", ai.lastGenReq.CourseName)
	}
	got := ai.lastGenReq.EvidenceRefs
	if len(got) != 2 || got[0] != "chunk_a" || got[1] != "chunk_b" {
		t.Fatalf("应只带目标页绑定并去重, 实际 %v", got)
	}
}

// TestModifyPartialWithoutBindingsSendsNoEvidence —— 未绑定时不伪造证据。
func TestModifyPartialWithoutBindingsSendsNoEvidence(t *testing.T) {
	ai := &fakeModifyAI{
		intent: &ModifyIntent{
			TargetType: "node", TargetIDs: []string{"node_2"},
			Action: "simplify", Confidence: 0.9,
		},
		genResp: &GenContentStatusResponse{Status: "done", Nodes: []TeachingNodeItem{{NodeID: "node_2", Title: "冒泡排序", Summary: "精简结果", Script: "精简讲稿"}}},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	if _, err := svc.Modify(context.Background(), p.ProjectID, "第二页精简", sampleTeachingNodes(), ""); err != nil {
		t.Fatalf("Modify: %v", err)
	}
	if len(ai.lastGenReq.EvidenceRefs) != 0 {
		t.Fatalf("无绑定时不应带证据, 实际 %v", ai.lastGenReq.EvidenceRefs)
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

	result, err := svc.Modify(context.Background(), p.ProjectID, "改一下", sampleTeachingNodes(), "")
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

func TestModifyRequiresConfirmationForHighRiskElementAction(t *testing.T) {
	ai := &fakeModifyAI{intent: &ModifyIntent{
		TargetType: "node", TargetIDs: []string{"node_2"},
		TargetElementIDs: []string{"el_node_2_chart"}, Action: "restyle",
		RiskLevel: "high", ConfirmationRequired: true, Confidence: 0.95,
	}}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	result, err := svc.ModifyWithOptions(context.Background(), p.ProjectID, "把第二页图表改成柱状图", sampleTeachingNodes(), false)
	if err != nil {
		t.Fatalf("ModifyWithOptions: %v", err)
	}
	if !result.RequiresConfirmation || result.RiskLevel != "high" {
		t.Fatalf("高风险元素修改应先确认: %+v", result)
	}
	versions, _ := svc.ModifyHistory(context.Background(), p.ProjectID)
	if len(versions) != 0 {
		t.Fatalf("确认前不应产生版本, 实际 %d", len(versions))
	}
}

func TestEnsureElementMetadataKeepsStableIDs(t *testing.T) {
	nodes := ensureElementMetadata(sampleTeachingNodes())
	first := nodes[1].Metadata["elements"].([]map[string]any)
	if first[0]["element_id"] != "el_node_2_title" {
		t.Fatalf("标题元素 ID 不稳定: %#v", first[0])
	}
	nodes = ensureElementMetadata(nodes)
	second := nodes[1].Metadata["elements"].([]map[string]any)
	if second[0]["element_id"] != first[0]["element_id"] {
		t.Fatalf("重复归一化改变元素 ID")
	}
}

func TestModifyCanRemoveTeachingText(t *testing.T) {
	ai := &fakeModifyAI{
		intent: &ModifyIntent{
			TargetType: "node", TargetIDs: []string{"node_3"},
			Action: "simplify", Constraints: []string{"去掉讲授文本"},
			Confidence: 0.95,
		},
		genResp: &GenContentStatusResponse{
			Status: "done",
			Nodes: []TeachingNodeItem{{
				NodeID: "node_3", Script: "重新生成的讲授文本", Segments: []map[string]interface{}{{"text": "分段"}},
			}},
		},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	result, err := svc.Modify(context.Background(), p.ProjectID, "去掉第三页讲授文本", sampleTeachingNodes(), "")
	if err != nil {
		t.Fatalf("Modify: %v", err)
	}
	if result.AllNodes[2].Script != "" || len(result.AllNodes[2].Segments) != 0 {
		t.Fatalf("应清空目标节点讲授文本和分段, 实际 script=%q segments=%v", result.AllNodes[2].Script, result.AllNodes[2].Segments)
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

	result, err := svc.Modify(context.Background(), p.ProjectID, "删掉冒泡排序", sampleTeachingNodes(), "")
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

	result, err := svc.Modify(context.Background(), p.ProjectID, "首尾换一下", sampleTeachingNodes(), "")
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
		if _, err := svc.Modify(context.Background(), p.ProjectID, "改", nodes, ""); err != nil {
			t.Fatalf("Modify#%d: %v", i+1, err)
		}
	}

	// 回滚到 v1 → 生成 v4，内容 = v1 的正式版本状态
	rb, err := svc.Rollback(context.Background(), p.ProjectID, 1)
	if err != nil {
		t.Fatalf("Rollback: %v", err)
	}
	if rb.NewVersionNo != 4 {
		t.Fatalf("回滚应生成 v4, 实际 %d", rb.NewVersionNo)
	}
	if len(rb.Nodes) != 3 || rb.Nodes[1].Script != "v2 内容" {
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
	v4, err := svc.GetVersion(context.Background(), p.ProjectID, 4)
	if err != nil || v4.ParentVersionID != versions[0].VersionID {
		t.Fatalf("v4 应记录 v1 为父版本: err=%v parent=%q", err, v4.ParentVersionID)
	}
}

func TestCreateVersionSnapshotIncludesPageBindings(t *testing.T) {
	svc := newCoursewareTestSvc(&fakeModifyAI{})
	p := mustCreateProject(t, svc)
	bindings := []map[string]interface{}{{"page_id": "page_1", "node_id": "node_1", "citation_refs": []string{"chunk_tcp_1"}}}
	created, err := svc.CreateVersionSnapshot(context.Background(), p.ProjectID, "首版课件", sampleTeachingNodes(), map[string]string{"template_id": "deck-swiss-edu"}, bindings)
	if err != nil {
		t.Fatalf("CreateVersionSnapshot: %v", err)
	}
	if created.VersionNo != 1 || created.VersionSummary != "首版课件" {
		t.Fatalf("版本元数据错误: %+v", created)
	}
	detail, err := svc.GetVersionByID(context.Background(), p.ProjectID, created.VersionID)
	if err != nil {
		t.Fatalf("GetVersionByID: %v", err)
	}
	var snapshot CoursewareVersionSnapshot
	if err := json.Unmarshal([]byte(detail.SnapshotJSON), &snapshot); err != nil {
		t.Fatalf("解析完整快照失败: %v", err)
	}
	if len(snapshot.Nodes) != 3 || snapshot.Presentation["template_id"] != "deck-swiss-edu" || snapshot.PageBindings == nil {
		t.Fatalf("完整快照缺少节点、呈现或页面绑定: %+v", snapshot)
	}
	rb, err := svc.Rollback(context.Background(), p.ProjectID, created.VersionNo)
	if err != nil {
		t.Fatalf("Rollback: %v", err)
	}
	if rb.Presentation["template_id"] != "deck-swiss-edu" || rb.PageBindings == nil {
		t.Fatalf("回滚响应未恢复呈现或页面绑定: %+v", rb)
	}
	draftJSON, err := svc.GetDraft(context.Background(), p.ProjectID)
	if err != nil {
		t.Fatalf("GetDraft: %v", err)
	}
	var restored CoursewareVersionSnapshot
	if err := json.Unmarshal([]byte(draftJSON), &restored); err != nil {
		t.Fatalf("解析回滚草稿失败: %v", err)
	}
	if restored.PageBindings == nil || restored.Presentation["template_id"] != "deck-swiss-edu" {
		t.Fatalf("回滚草稿丢失页面绑定或呈现: %+v", restored)
	}
}

func TestVersionToRowIncludesLegacyPrimaryKey(t *testing.T) {
	version := &CoursewareVersion{VersionID: "ver_test_001", ProjectID: "proj_test_001"}
	row := versionToRow(version)
	if row.ID == "" || row.ID != version.VersionID {
		t.Fatalf("版本行必须填充物理主键 id，实际=%q version_id=%q", row.ID, row.VersionID)
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

func TestContractVersionSnapshotAndRollbackByID(t *testing.T) {
	svc := newCoursewareTestSvc(&fakeModifyAI{})
	p := mustCreateProject(t, svc)
	snapshot := ContractVersionSnapshot{
		Outline: map[string]interface{}{"title": "排序算法"},
		Content: sampleTeachingNodes(),
		PageBindings: map[string]interface{}{
			"page_003": map[string]interface{}{"evidence_refs": []string{"chunk_005"}},
		},
		Style: map[string]interface{}{"template_id": "tech"},
	}
	created, err := svc.CreateVersionSnapshotJSON(context.Background(), p.ProjectID, "保存第三页修改", snapshot)
	if err != nil {
		t.Fatalf("CreateVersionSnapshotJSON: %v", err)
	}
	if created.VersionNo != 1 {
		t.Fatalf("expected v1, got %d", created.VersionNo)
	}

	rolled, err := svc.RollbackByID(context.Background(), p.ProjectID, created.VersionID)
	if err != nil {
		t.Fatalf("RollbackByID: %v", err)
	}
	if rolled.NewDraftVersionNo != 2 || rolled.BaseVersionNo != 1 {
		t.Fatalf("unexpected fork result: %+v", rolled)
	}
	draft, err := svc.GetDraft(context.Background(), p.ProjectID)
	if err != nil {
		t.Fatalf("GetDraft: %v", err)
	}
	var restored ContractVersionSnapshot
	if err := json.Unmarshal([]byte(draft), &restored); err != nil {
		t.Fatalf("parse restored snapshot: %v", err)
	}
	if restored.PageBindings == nil || restored.Style == nil {
		t.Fatalf("rollback lost page bindings or style: %+v", restored)
	}
	versions, err := svc.Versions(context.Background(), p.ProjectID)
	if err != nil || len(versions) != 2 {
		t.Fatalf("history should preserve source and fork: err=%v count=%d", err, len(versions))
	}
}

// =============================================================================
// 局部修改的异步取数 —— 「报已更新但 HTML 没变」的根因回归
// =============================================================================

// shrinkContentPolling 把轮询参数调到测试量级。
// 不下调的话，一个超时用例要真等 90 秒。
func shrinkContentPolling(t *testing.T, interval, budget time.Duration) {
	t.Helper()
	prevInterval, prevBudget := contentPollInterval, contentPollBudget
	contentPollInterval, contentPollBudget = interval, budget
	t.Cleanup(func() { contentPollInterval, contentPollBudget = prevInterval, prevBudget })
}

func asyncIntent(action string) *ModifyIntent {
	return &ModifyIntent{
		TargetType: "node", TargetIDs: []string{"node_2"},
		Action: action, Confidence: 0.9,
	}
}

// TestModifyWaitsForAsyncContentTask —— 老师报的那个 bug 的正面回归。
//
// /gen/content 起一个后台线程后立刻返回，首个响应里的 nodes **恒为空**。旧实现
// 把这份空结果交给 mergePartialResult，而后者首行就是
// `if len(partial) == 0 { return base }` —— 原样退回旧节点；可 modifiedIDs 照样
// 被填成 target_ids，于是对话报「已更新」，而返回给前端的节点一个字节都没变，
// 预览渲染出来自然一模一样。这个用例钉住：结果必须取自轮询，而不是首个响应。
func TestModifyWaitsForAsyncContentTask(t *testing.T) {
	shrinkContentPolling(t, time.Millisecond, time.Second)

	ai := &fakeModifyAI{
		intent: asyncIntent("simplify"),
		// 真实引擎的 POST 响应形状：有 content_id，没有 nodes
		genResp: &GenContentStatusResponse{ContentID: "content_async", Status: "generating"},
		statusQueue: []*GenContentStatusResponse{
			{ContentID: "content_async", Status: "generating"},
			{ContentID: "content_async", Status: "generating"},
			{ContentID: "content_async", Status: "done", Nodes: []TeachingNodeItem{
				{NodeID: "node_2", Title: "冒泡排序", Summary: "精简后的正文", Script: "精简后的讲稿"},
			}},
		},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	result, err := svc.Modify(context.Background(), p.ProjectID, "第二页精简", sampleTeachingNodes(), "")
	if err != nil {
		t.Fatalf("Modify: %v", err)
	}
	if got := result.AllNodes[1].Script; got != "精简后的讲稿" {
		t.Fatalf("异步结果没被取回，讲稿仍是旧的: %q", got)
	}
	if got := result.AllNodes[1].Summary; got != "精简后的正文" {
		t.Fatalf("正文（上屏内容）没被取回: %q", got)
	}
	if ai.statusCalls < 3 {
		t.Fatalf("应轮询到任务结束，实际只查了 %d 次", ai.statusCalls)
	}
	if result.AllNodes[0].Script != "原始讲稿1" || result.AllNodes[2].Script != "原始讲稿3" {
		t.Fatal("非目标页不应变化")
	}
	if result.NewVersionNo != 1 {
		t.Fatalf("应为 v1, 实际 %d", result.NewVersionNo)
	}
}

// TestModifyErrorsWhenTaskFinishesWithoutNodes —— 任务自称完成却没有节点，
// 必须报错，而不是拿旧内容冒充「已更新」。
func TestModifyErrorsWhenTaskFinishesWithoutNodes(t *testing.T) {
	shrinkContentPolling(t, time.Millisecond, time.Second)

	ai := &fakeModifyAI{
		intent:  asyncIntent("rewrite"),
		genResp: &GenContentStatusResponse{ContentID: "content_empty", Status: "generating"},
		statusResp: &GenContentStatusResponse{
			ContentID: "content_empty", Status: "done", Error: "3 个节点生成失败",
		},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	_, err := svc.Modify(context.Background(), p.ProjectID, "重写第二页", sampleTeachingNodes(), "")
	if err == nil {
		t.Fatal("任务完成但无节点时必须报错")
	}
	if !strings.Contains(err.Error(), "3 个节点生成失败") {
		t.Fatalf("错误应带上引擎给的原因, 实际 %v", err)
	}
	versions, _ := svc.ModifyHistory(context.Background(), p.ProjectID)
	if len(versions) != 0 {
		t.Fatalf("失败不应产生快照, 实际 %d", len(versions))
	}
}

// TestModifyPropagatesEngineFailure —— 引擎报 failed，错误要透上来。
func TestModifyPropagatesEngineFailure(t *testing.T) {
	shrinkContentPolling(t, time.Millisecond, time.Second)

	ai := &fakeModifyAI{
		intent:     asyncIntent("expand"),
		genResp:    &GenContentStatusResponse{ContentID: "content_bad", Status: "generating"},
		statusResp: &GenContentStatusResponse{ContentID: "content_bad", Status: "failed", Error: "模型调用超时"},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	_, err := svc.Modify(context.Background(), p.ProjectID, "第二页展开", sampleTeachingNodes(), "")
	if err == nil || !strings.Contains(err.Error(), "模型调用超时") {
		t.Fatalf("应透传引擎失败原因, 实际 %v", err)
	}
}

// TestModifyErrorsWithoutContentID —— 引擎既没给节点也没给 content_id：
// 立刻报错，不要空转一整个轮询预算。
func TestModifyErrorsWithoutContentID(t *testing.T) {
	shrinkContentPolling(t, time.Millisecond, 50*time.Millisecond)

	ai := &fakeModifyAI{
		intent:  asyncIntent("simplify"),
		genResp: &GenContentStatusResponse{Status: "generating"},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	_, err := svc.Modify(context.Background(), p.ProjectID, "第二页精简", sampleTeachingNodes(), "")
	if err == nil || !strings.Contains(err.Error(), "content_id") {
		t.Fatalf("无 content_id 应立刻报错, 实际 %v", err)
	}
	if ai.statusCalls != 0 {
		t.Fatalf("无 content_id 就不该发起状态查询, 实际 %d 次", ai.statusCalls)
	}
}

// TestModifyToleratesTransientStatusErrors —— 单次状态查询失败不放弃：
// 任务在引擎侧照跑，网络抖一下还是该把结果取回来。
func TestModifyToleratesTransientStatusErrors(t *testing.T) {
	shrinkContentPolling(t, time.Millisecond, time.Second)

	ai := &fakeModifyAI{
		intent:       asyncIntent("expand"),
		genResp:      &GenContentStatusResponse{ContentID: "content_flaky", Status: "generating"},
		statusErr:    errors.New("connection reset by peer"),
		statusErrFor: 2,
		statusResp: &GenContentStatusResponse{
			ContentID: "content_flaky", Status: "done",
			Nodes: []TeachingNodeItem{{NodeID: "node_2", Summary: "增加生活案例", Script: "抖完之后的讲稿"}},
		},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	result, err := svc.Modify(context.Background(), p.ProjectID, "第二页展开", sampleTeachingNodes(), "")
	if err != nil {
		t.Fatalf("抖动不应导致整体失败: %v", err)
	}
	if result.AllNodes[1].Script != "抖完之后的讲稿" {
		t.Fatalf("抖动恢复后应取回结果, 实际 %q", result.AllNodes[1].Script)
	}
}

// TestModifyTimesOutWhenTaskNeverFinishes —— 任务一直不结束：报超时，
// 而不是无限等下去（前端 MODIFY_LLM_TIMEOUT_MS 是 120s）。
func TestModifyTimesOutWhenTaskNeverFinishes(t *testing.T) {
	shrinkContentPolling(t, time.Millisecond, 30*time.Millisecond)

	ai := &fakeModifyAI{
		intent:  asyncIntent("simplify"),
		genResp: &GenContentStatusResponse{ContentID: "content_stuck", Status: "generating"},
		// statusResp 留空 → 永远 generating
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	_, err := svc.Modify(context.Background(), p.ProjectID, "第二页精简", sampleTeachingNodes(), "")
	if err == nil || !strings.Contains(err.Error(), "超时") {
		t.Fatalf("应报超时, 实际 %v", err)
	}
}

// TestModifyAbortsWhenContextIsCancelled —— 前端断开连接时不该继续空转。
func TestModifyAbortsWhenContextIsCancelled(t *testing.T) {
	shrinkContentPolling(t, time.Millisecond, time.Second)

	ai := &fakeModifyAI{
		intent:  asyncIntent("simplify"),
		genResp: &GenContentStatusResponse{ContentID: "content_cancel", Status: "generating"},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := svc.Modify(ctx, p.ProjectID, "第二页精简", sampleTeachingNodes(), "")
	if err == nil || !strings.Contains(err.Error(), "已取消") {
		t.Fatalf("取消后应中止等待, 实际 %v", err)
	}
}
