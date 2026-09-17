package service

import (
	"context"
	"errors"
	"testing"
)

// ---- fake AIEngine：仅实现大纲两个方法，其余留空（测试只走 OutlineService）----

type fakeOutlineAI struct {
	generateResp *OutlineGenerateResponse
	reviseResp   *OutlineReviseAIResponse
	generateErr  error
	reviseErr    error
}

func (f *fakeOutlineAI) GenerateOutline(_ context.Context, _ OutlineGenerateRequest) (*OutlineGenerateResponse, error) {
	if f.generateErr != nil {
		return nil, f.generateErr
	}
	return f.generateResp, nil
}

func (f *fakeOutlineAI) ReviseOutline(_ context.Context, _ OutlineReviseAIRequest) (*OutlineReviseAIResponse, error) {
	if f.reviseErr != nil {
		return nil, f.reviseErr
	}
	return f.reviseResp, nil
}

func sampleNodes() []OutlineNode {
	return []OutlineNode{
		{NodeID: "node_001", Order: 1, Title: "引言", Summary: "课程导入", NodeType: OutlineNodeTypeContent, KeyPoints: []string{"背景"}, EstimatedDurationMin: 5},
		{NodeID: "node_002", Order: 2, Title: "主算法", Summary: "核心讲解", NodeType: OutlineNodeTypeSection, KeyPoints: []string{"原理"}, EstimatedDurationMin: 20},
	}
}

func newTestService() *OutlineService {
	return &OutlineService{
		aiClient: &fakeOutlineAI{
			generateResp: &OutlineGenerateResponse{Nodes: sampleNodes()},
			reviseResp:   &OutlineReviseAIResponse{Nodes: sampleNodes(), ChangeSummary: []string{"调整顺序"}},
		},
		store: newMemOutlineStore(),
	}
}

func mustCreateOutline(t *testing.T, svc *OutlineService, sessionID string) *Outline {
	t.Helper()
	outline, err := svc.CreateOutline(context.Background(), OutlineGenerateRequest{
		SessionID: sessionID,
		Intent:    &IntentSummary{},
	})
	if err != nil {
		t.Fatalf("CreateOutline 失败: %v", err)
	}
	if outline.OutlineID == "" {
		t.Fatal("CreateOutline 未生成 outline_id")
	}
	if outline.OutlineVersion != 1 {
		t.Fatalf("首版应为 version=1, 实际 %d", outline.OutlineVersion)
	}
	if outline.Status != OutlineStatusDraft {
		t.Fatalf("首版应为 draft, 实际 %s", outline.Status)
	}
	return outline
}

// TestCreateOutlineVersion1Draft —— 创建大纲 → version=1 + status=draft。
func TestCreateOutlineVersion1Draft(t *testing.T) {
	svc := newTestService()
	outline := mustCreateOutline(t, svc, "session_1")
	if len(outline.Nodes) != 2 {
		t.Fatalf("节点数应为 2, 实际 %d", len(outline.Nodes))
	}
	if outline.Nodes[0].Order != 1 || outline.Nodes[1].Order != 2 {
		t.Fatalf("order 应重排为连续 1..n: %v", []int{outline.Nodes[0].Order, outline.Nodes[1].Order})
	}
}

// TestConfirmFlow —— draft → confirmed：Confirm 后状态翻转、confirmed_at 非空。
func TestConfirmFlow(t *testing.T) {
	svc := newTestService()
	outline := mustCreateOutline(t, svc, "session_1")

	confirmed, err := svc.ConfirmOutline(context.Background(), outline.OutlineID, 1)
	if err != nil {
		t.Fatalf("ConfirmOutline 失败: %v", err)
	}
	if confirmed.Status != OutlineStatusConfirmed {
		t.Fatalf("确认后应为 confirmed, 实际 %s", confirmed.Status)
	}
	if confirmed.ConfirmedAt == nil {
		t.Fatal("确认后 confirmed_at 不应为空")
	}

	// 已确认大纲可被 GetConfirmed 读取（供 GenerationHandler 注入节点）
	got, err := svc.GetConfirmed(context.Background(), outline.OutlineID, 1)
	if err != nil {
		t.Fatalf("GetConfirmed 应通过: %v", err)
	}
	if len(got.Nodes) != 2 {
		t.Fatalf("GetConfirmed 应返回节点, 实际 %d", len(got.Nodes))
	}
}

// TestGetConfirmedRejectsDraft —— 未确认大纲 GetConfirmed 必须拒绝（409 语义）。
func TestGetConfirmedRejectsDraft(t *testing.T) {
	svc := newTestService()
	outline := mustCreateOutline(t, svc, "session_1")

	_, err := svc.GetConfirmed(context.Background(), outline.OutlineID, 1)
	if !errors.Is(err, ErrOutlineNotConfirmed) {
		t.Fatalf("未确认大纲应返回 ErrOutlineNotConfirmed, 实际 %v", err)
	}
}

// TestConfirmEmptyNodesRejected —— 空节点大纲确认必须失败（规范 §3.5 节点数>0）。
func TestConfirmEmptyNodesRejected(t *testing.T) {
	svc := newTestService()
	svc.aiClient = &fakeOutlineAI{generateResp: &OutlineGenerateResponse{Nodes: []OutlineNode{}}}
	outline := mustCreateOutline(t, svc, "session_1")

	_, err := svc.ConfirmOutline(context.Background(), outline.OutlineID, 1)
	if !errors.Is(err, ErrInvalidOutline) {
		t.Fatalf("空节点确认应返回 ErrInvalidOutline, 实际 %v", err)
	}
}

// TestSaveVersionConflict —— base_version 不匹配当前版本 → ErrOutlineVersionConflict（409）。
func TestSaveVersionConflict(t *testing.T) {
	svc := newTestService()
	outline := mustCreateOutline(t, svc, "session_1")

	// 以错误 base_version=2 保存（当前为 1）→ 冲突
	_, err := svc.SaveOutlineVersion(context.Background(), outline.OutlineID, 2, sampleNodes())
	if !errors.Is(err, ErrOutlineVersionConflict) {
		t.Fatalf("base_version 不匹配应返回 ErrOutlineVersionConflict, 实际 %v", err)
	}
}

// TestSaveVersionSupersedesConfirmed —— 确认后修改：旧版本 → superseded，新版本 → draft。
func TestSaveVersionSupersedesConfirmed(t *testing.T) {
	svc := newTestService()
	outline := mustCreateOutline(t, svc, "session_1")

	if _, err := svc.ConfirmOutline(context.Background(), outline.OutlineID, 1); err != nil {
		t.Fatalf("ConfirmOutline 失败: %v", err)
	}

	// 对 confirmed v1 保存修改 → 生成 v2(draft)，v1 变 superseded
	nodes := sampleNodes()
	nodes[0].Title = "引言（修订）"
	saved, err := svc.SaveOutlineVersion(context.Background(), outline.OutlineID, 1, nodes)
	if err != nil {
		t.Fatalf("SaveOutlineVersion 失败: %v", err)
	}
	if saved.OutlineVersion != 2 {
		t.Fatalf("修改后应生成 version=2, 实际 %d", saved.OutlineVersion)
	}
	if saved.Status != OutlineStatusDraft {
		t.Fatalf("新版本应为 draft（可重新确认）, 实际 %s", saved.Status)
	}

	old, err := svc.GetOutline(context.Background(), outline.OutlineID, 1)
	if err != nil {
		t.Fatalf("读取 v1 失败: %v", err)
	}
	if old.Status != OutlineStatusSuperseded {
		t.Fatalf("被修改的 confirmed v1 应置 superseded, 实际 %s", old.Status)
	}
}

// TestSaveVersionDuplicateNodeIDRejected —— node_id 重复 → ErrInvalidOutline（规范 §3.4）。
func TestSaveVersionDuplicateNodeIDRejected(t *testing.T) {
	svc := newTestService()
	outline := mustCreateOutline(t, svc, "session_1")

	dup := []OutlineNode{
		{NodeID: "node_x", Order: 1, Title: "A", Summary: "s", NodeType: OutlineNodeTypeContent, EstimatedDurationMin: 5},
		{NodeID: "node_x", Order: 2, Title: "B", Summary: "s", NodeType: OutlineNodeTypeContent, EstimatedDurationMin: 5},
	}
	_, err := svc.SaveOutlineVersion(context.Background(), outline.OutlineID, 1, dup)
	if !errors.Is(err, ErrInvalidOutline) {
		t.Fatalf("node_id 重复应返回 ErrInvalidOutline, 实际 %v", err)
	}
}

// TestSaveVersionOrderGapRejected —— order 不连续 → ErrInvalidOutline（规范 §3.4）。
func TestSaveVersionOrderGapRejected(t *testing.T) {
	svc := newTestService()
	outline := mustCreateOutline(t, svc, "session_1")

	gap := []OutlineNode{
		{NodeID: "node_a", Order: 1, Title: "A", Summary: "s", NodeType: OutlineNodeTypeContent, EstimatedDurationMin: 5},
		{NodeID: "node_b", Order: 3, Title: "B", Summary: "s", NodeType: OutlineNodeTypeContent, EstimatedDurationMin: 5}, // order 跳号
	}
	_, err := svc.SaveOutlineVersion(context.Background(), outline.OutlineID, 1, gap)
	if !errors.Is(err, ErrInvalidOutline) {
		t.Fatalf("order 不连续应返回 ErrInvalidOutline, 实际 %v", err)
	}
}

// TestReviseAutoApplyFalseNoPersist —— auto_apply=false：返回候选版本（version+1），不落库。
func TestReviseAutoApplyFalseNoPersist(t *testing.T) {
	svc := newTestService()
	outline := mustCreateOutline(t, svc, "session_1")

	candidate, err := svc.ReviseOutline(context.Background(), outline.OutlineID, "加个例子", 1, false)
	if err != nil {
		t.Fatalf("ReviseOutline 失败: %v", err)
	}
	if candidate.OutlineVersion != 2 {
		t.Fatalf("修订候选应预置 version=2, 实际 %d", candidate.OutlineVersion)
	}
	if candidate.Status != OutlineStatusDraft {
		t.Fatalf("修订候选应为 draft, 实际 %s", candidate.Status)
	}

	// 未落库：版本链仍只有 v1
	latest, err := svc.GetOutline(context.Background(), outline.OutlineID, 0)
	if err != nil {
		t.Fatal(err)
	}
	if latest.OutlineVersion != 1 {
		t.Fatalf("auto_apply=false 不应落库, 最新应仍为 v1, 实际 %d", latest.OutlineVersion)
	}
}

// TestReviseAutoApplyTruePersists —— auto_apply=true：修订结果作为新版本保存。
func TestReviseAutoApplyTruePersists(t *testing.T) {
	svc := newTestService()
	outline := mustCreateOutline(t, svc, "session_1")

	saved, err := svc.ReviseOutline(context.Background(), outline.OutlineID, "加个例子", 1, true)
	if err != nil {
		t.Fatalf("ReviseOutline(auto) 失败: %v", err)
	}
	if saved.OutlineVersion != 2 {
		t.Fatalf("auto_apply=true 应保存为 v2, 实际 %d", saved.OutlineVersion)
	}

	latest, err := svc.GetOutline(context.Background(), outline.OutlineID, 0)
	if err != nil {
		t.Fatal(err)
	}
	if latest.OutlineVersion != 2 {
		t.Fatalf("落库后最新应 v2, 实际 %d", latest.OutlineVersion)
	}
}

// TestCreateOutlineSessionRequired —— 无 session_id 拒绝。
func TestCreateOutlineSessionRequired(t *testing.T) {
	svc := newTestService()
	_, err := svc.CreateOutline(context.Background(), OutlineGenerateRequest{})
	if err == nil {
		t.Fatal("session_id 为空应报错")
	}
}

// TestGetOutlineVersionNotFound —— 读不存在的大纲 → ErrOutlineNotFound。
func TestGetOutlineVersionNotFound(t *testing.T) {
	svc := newTestService()
	_, err := svc.GetOutline(context.Background(), "outline_nope", 0)
	if !errors.Is(err, ErrOutlineNotFound) {
		t.Fatalf("不存在大纲应返回 ErrOutlineNotFound, 实际 %v", err)
	}
}
