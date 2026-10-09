package service

import (
	"encoding/json"
	"strings"
	"testing"
)

// 契约 v1.0 模块1 接口3：POST /api/v1/gen/modify 新增 page_id / evidence_refs / user_instruction。
//
// 锁定两件事：
//  1. 字段只增不删 —— 未提供时 JSON 中完全不出现，未升级的 AI 引擎收到与改动前一致的请求体；
//  2. 响应侧能接住 citation_refs / evidence_used（"用了哪些证据"）。

func TestGenerationModifyRequestOmitsEvidenceWhenEmpty(t *testing.T) {
	raw, err := json.Marshal(GenerationModifyRequest{
		GenerationID: "content_001",
		Commands:     []ModifyCommandItem{{CommandType: "update_node", NodeID: "page_001", Regenerate: true}},
	})
	if err != nil {
		t.Fatalf("请求序列化失败: %v", err)
	}
	for _, field := range []string{"evidence_refs", "page_id", "user_instruction"} {
		if strings.Contains(string(raw), field) {
			t.Fatalf("未提供证据参数时不应下发 %s（会破坏对旧引擎的兼容）: %s", field, raw)
		}
	}
}

func TestGenerationModifyRequestEvidenceFields(t *testing.T) {
	raw, err := json.Marshal(GenerationModifyRequest{
		GenerationID:    "content_001",
		Commands:        []ModifyCommandItem{{CommandType: "update_node", NodeID: "page_001", Regenerate: true}},
		PageID:          "page_001",
		EvidenceRefs:    []string{"chunk_001", "chunk_002"},
		UserInstruction: "只讲 SYN 标志位",
	})
	if err != nil {
		t.Fatalf("请求序列化失败: %v", err)
	}
	var got map[string]any
	if err := json.Unmarshal(raw, &got); err != nil {
		t.Fatalf("请求反序列化失败: %v", err)
	}
	if got["page_id"] != "page_001" {
		t.Fatalf("page_id 未按契约下发: %s", raw)
	}
	refs, ok := got["evidence_refs"].([]any)
	if !ok || len(refs) != 2 || refs[0] != "chunk_001" || refs[1] != "chunk_002" {
		t.Fatalf("evidence_refs 未按契约下发: %s", raw)
	}
	if got["user_instruction"] != "只讲 SYN 标志位" {
		t.Fatalf("user_instruction 未按契约下发: %s", raw)
	}
}

func TestGenerationModifyResponseDecodesEvidenceRefs(t *testing.T) {
	raw := `{"status":"ok","version_number":3,"citation_refs":["chunk_001"],"evidence_used":["chunk_001"]}`
	var resp GenerationModifyResponse
	if err := json.Unmarshal([]byte(raw), &resp); err != nil {
		t.Fatalf("响应解析失败: %v", err)
	}
	if resp.Status != "ok" || resp.VersionNumber != 3 {
		t.Fatalf("既有字段解析异常: %+v", resp)
	}
	if len(resp.CitationRefs) != 1 || resp.CitationRefs[0] != "chunk_001" {
		t.Fatalf("citation_refs 未解析: %+v", resp)
	}
	if len(resp.EvidenceUsed) != 1 || resp.EvidenceUsed[0] != "chunk_001" {
		t.Fatalf("evidence_used 未解析: %+v", resp)
	}
}

func TestTeachingNodeItemAcceptsStructuredInteractiveQuestions(t *testing.T) {
	raw := `{"nodes":[{"node_id":"node_001","interactive_questions":[{"question":"快速排序的平均复杂度是什么？","options":["O(n)","O(n log n)"]}]}]}`
	var resp GenContentStatusResponse
	if err := json.Unmarshal([]byte(raw), &resp); err != nil {
		t.Fatalf("结构化 interactive_questions 不应阻断内容状态响应: %v", err)
	}
	if len(resp.Nodes) != 1 || len(resp.Nodes[0].InteractiveQuestions) != 1 {
		t.Fatalf("interactive_questions 未保留: %+v", resp.Nodes)
	}
}
