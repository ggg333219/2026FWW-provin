package service

import (
	"context"
	"strings"
	"testing"
)

func TestSelectedBodyRevisionPreservesFullInstructionAndOtherPages(t *testing.T) {
	instruction := "请把这一页的正文改写得更通俗，并增加一个生活中的例子。"
	nodes := sampleTeachingNodes()
	ai := &fakeModifyAI{
		intent: &ModifyIntent{TargetType: "node", TargetIDs: []string{"node_2"}, Action: "rewrite", Confidence: 0.95},
		genResp: &GenContentStatusResponse{Status: "done", Nodes: []TeachingNodeItem{
			{NodeID: "node_1", Title: "不应采用的其他页修改", Content: "不应采用"},
			{NodeID: "node_2", Title: nodes[1].Title, Content: "排序就像整理书架。", Summary: "排序就像整理书架。"},
		}},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)
	result, err := svc.Modify(context.Background(), p.ProjectID, instruction, nodes, "node_2")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(strings.Join(ai.lastGenReq.ModifyConstraints, "\n"), instruction) {
		t.Fatal("原始的通俗改写及生活例子要求必须传到生成端")
	}
	if result.AllNodes[0].Title != nodes[0].Title || result.AllNodes[0].Content != nodes[0].Content {
		t.Fatal("非目标页被改变")
	}
	if result.AllNodes[1].Content != "排序就像整理书架。" {
		t.Fatal("正文未更新")
	}
}

func TestSelectedBodyRewriteRejectsUnchangedModelResult(t *testing.T) {
	nodes := sampleTeachingNodes()
	ai := &fakeModifyAI{
		intent:  &ModifyIntent{TargetType: "node", TargetIDs: []string{"node_2"}, Action: "rewrite", Confidence: 0.95},
		genResp: &GenContentStatusResponse{Status: "done", Nodes: nodes},
	}
	svc := newCoursewareTestSvc(ai)
	p := mustCreateProject(t, svc)
	if _, err := svc.Modify(context.Background(), p.ProjectID, "改写这一页的正文", nodes, "node_2"); err == nil {
		t.Fatal("正文未改变时不能报告成功")
	}
}
