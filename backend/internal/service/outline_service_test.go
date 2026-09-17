package service

import (
	"context"
	"errors"
	"testing"
)

type fakeOutlineAI struct{}

func (fakeOutlineAI) GenerateOutline(context.Context, OutlineGenerateRequest) (*OutlineGenerateResponse, error) {
	return &OutlineGenerateResponse{Nodes: []OutlineNode{{
		NodeID: "node_001", Title: "冒泡排序原理", Summary: "比较与交换", NodeType: "content",
	}}}, nil
}

func (fakeOutlineAI) ReviseOutline(_ context.Context, req OutlineReviseAIRequest) (*OutlineReviseAIResponse, error) {
	return &OutlineReviseAIResponse{Nodes: req.Nodes, ChangeSummary: []string{"已按要求调整"}}, nil
}

type outlineAIWithEmptySummary struct{}

func (outlineAIWithEmptySummary) GenerateOutline(context.Context, OutlineGenerateRequest) (*OutlineGenerateResponse, error) {
	return &OutlineGenerateResponse{Nodes: []OutlineNode{{
		NodeID: "node_001", Title: "核心概念", Summary: "", NodeType: "content",
	}}}, nil
}

func (outlineAIWithEmptySummary) ReviseOutline(_ context.Context, req OutlineReviseAIRequest) (*OutlineReviseAIResponse, error) {
	return &OutlineReviseAIResponse{Nodes: req.Nodes}, nil
}

func TestOutlineCreateNormalizesEmptySummary(t *testing.T) {
	svc := NewOutlineService(outlineAIWithEmptySummary{})
	created, err := svc.Create(context.Background(), OutlineCreateRequest{
		SessionID: "sess_empty_summary", IntentID: "intent_empty_summary", Intent: map[string]any{"topic": "核心概念"},
	})
	if err != nil {
		t.Fatalf("create outline with empty summary: %v", err)
	}
	if created.Nodes[0].Summary != "核心概念" {
		t.Fatalf("want title fallback summary, got %q", created.Nodes[0].Summary)
	}
}

func TestOutlineConfirmedVersionCannotBeOverwritten(t *testing.T) {
	svc := NewOutlineService(fakeOutlineAI{})
	created, err := svc.Create(context.Background(), OutlineCreateRequest{
		SessionID: "sess_001", IntentID: "intent_001", Intent: map[string]any{"topic": "排序算法"},
	})
	if err != nil {
		t.Fatalf("create outline: %v", err)
	}
	if created.Status != OutlineStatusDraft || created.OutlineVersion != 1 {
		t.Fatalf("unexpected initial outline: %#v", created)
	}

	nodes := append([]OutlineNode(nil), created.Nodes...)
	nodes[0].Title = "教师调整后的冒泡排序原理"
	saved, err := svc.Save(created.OutlineID, OutlineSaveRequest{BaseVersion: 1, Nodes: nodes})
	if err != nil {
		t.Fatalf("save outline: %v", err)
	}
	if saved.OutlineVersion != 2 {
		t.Fatalf("want version 2, got %d", saved.OutlineVersion)
	}

	confirmed, err := svc.Confirm(created.OutlineID, 2)
	if err != nil {
		t.Fatalf("confirm outline: %v", err)
	}
	if confirmed.Status != OutlineStatusConfirmed {
		t.Fatalf("want confirmed, got %s", confirmed.Status)
	}

	_, err = svc.Save(created.OutlineID, OutlineSaveRequest{BaseVersion: 2, Nodes: nodes})
	if !errors.Is(err, ErrOutlineConfirmed) {
		t.Fatalf("want ErrOutlineConfirmed, got %v", err)
	}

	used, err := svc.GetConfirmed(created.OutlineID, 2)
	if err != nil {
		t.Fatalf("get confirmed outline: %v", err)
	}
	if used.Nodes[0].Title != "教师调整后的冒泡排序原理" {
		t.Fatalf("confirmed nodes changed: %#v", used.Nodes)
	}
}
