package service

import (
	"encoding/json"
	"testing"
)

func TestExportCreateRequestPreservesFlashcardData(t *testing.T) {
	const payload = `{"format":"interactive","nodes":[{"node_id":"node_1","title":"排序算法","interactive_plan":{"kind":"flashcard"},"interactive_items":[{"type":"flashcard","front":"快速排序","back":"分治"}],"metadata":{"interactive_asset":{"items":[{"type":"flashcard","front":"冒泡排序","back":"相邻交换"}]}}}]}`
	var req ExportCreateRequest
	if err := json.Unmarshal([]byte(payload), &req); err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(req)
	if err != nil {
		t.Fatal(err)
	}
	var forwarded map[string]any
	if err := json.Unmarshal(encoded, &forwarded); err != nil {
		t.Fatal(err)
	}
	nodes := forwarded["nodes"].([]any)
	node := nodes[0].(map[string]any)
	if node["interactive_plan"].(map[string]any)["kind"] != "flashcard" {
		t.Fatal("翻卡计划在 Go 网关转发时丢失")
	}
	if node["interactive_items"].([]any)[0].(map[string]any)["front"] != "快速排序" {
		t.Fatal("内嵌翻卡在 Go 网关转发时丢失")
	}
	asset := node["metadata"].(map[string]any)["interactive_asset"].(map[string]any)
	if asset["items"].([]any)[0].(map[string]any)["back"] != "相邻交换" {
		t.Fatal("互动资源在 Go 网关转发时丢失")
	}
}
