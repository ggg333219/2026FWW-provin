package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

func loadTeachingNodesByPage(db *gorm.DB, courseID string, page int) []model.TeachingNode {
	var nodes []model.TeachingNode
	_ = db.Where("course_id = ? AND page_index = ?", courseID, page).Order("sort_order asc, created_at asc").Find(&nodes).Error
	return nodes
}

func buildPlaybackNodesFromTeachingNodes(nodes []model.TeachingNode) []gin.H {
	result := make([]gin.H, 0, len(nodes))
	currentStartSec := 0
	for index, node := range nodes {
		text := teachingNodeDisplayText(node)
		if strings.TrimSpace(text) == "" {
			continue
		}
		nodeType := "explain"
		if index == 0 {
			nodeType = "opening"
		} else if index == len(nodes)-1 {
			nodeType = "transition"
		}
		startSec, durationSec, endSec := playbackTiming(node, currentStartSec)
		readyAudio := strings.TrimSpace(node.AudioURL) != "" && strings.TrimSpace(node.TTSStatus) == "ready"
		result = append(result, gin.H{
			"node_id":            node.NodeID,
			"type":               nodeType,
			"title":              node.Title,
			"text":               text,
			"duration_sec":       durationSec,
			"start_sec":          startSec,
			"end_sec":            endSec,
			"resume_sec":         startSec,
			"audio_url":          node.AudioURL,
			"audio_duration_sec": maxInt(node.AudioDurationSec, durationSec),
			"audio_start_sec":    startSec,
			"audio_end_sec":      endSec,
			"tts_status":         defaultAudioStatus(node.TTSStatus),
			"has_audio":          readyAudio,
		})
		currentStartSec = endSec
	}
	return result
}

func buildTeachingNodePageSummary(nodes []model.TeachingNode) string {
	parts := make([]string, 0, len(nodes))
	for _, node := range nodes {
		text := strings.TrimSpace(node.Title)
		if text == "" {
			text = strings.TrimSpace(node.Summary)
		}
		if text != "" {
			parts = append(parts, text)
		}
	}
	return strings.Join(parts, "；")
}

func buildPageContextFromTeachingNodes(nodes []model.TeachingNode) string {
	parts := make([]string, 0, len(nodes))
	for _, node := range nodes {
		if text := strings.TrimSpace(teachingNodeContextText(node)); text != "" {
			parts = append(parts, text)
		}
	}
	return strings.Join(parts, "\n\n")
}

func teachingNodeContextText(node model.TeachingNode) string {
	if text := strings.TrimSpace(node.ScriptText); text != "" {
		return text
	}
	parts := []string{strings.TrimSpace(node.Title), strings.TrimSpace(node.Summary)}
	for _, item := range decodeJSONStringArray(node.CorePoints) {
		if strings.TrimSpace(item) != "" {
			parts = append(parts, item)
		}
	}
	return strings.Join(filterEmptyStrings(parts), "。")
}

func teachingNodeDisplayText(node model.TeachingNode) string {
	if text := strings.TrimSpace(node.ScriptText); text != "" {
		return text
	}
	return teachingNodeContextText(node)
}

func playbackDurationSec(node model.TeachingNode) int {
	if node.EstimatedDuration > 0 {
		return node.EstimatedDuration
	}
	text := teachingNodeDisplayText(node)
	baseDuration := len([]rune(strings.TrimSpace(text))) / 14
	if baseDuration < 20 {
		baseDuration = 20
	}
	if baseDuration > 90 {
		baseDuration = 90
	}
	return baseDuration
}

func playbackTiming(node model.TeachingNode, fallbackStartSec int) (int, int, int) {
	startSec := fallbackStartSec
	if node.AudioStartSec > 0 {
		startSec = node.AudioStartSec
	}
	durationSec := playbackDurationSec(node)
	if node.AudioDurationSec > 0 {
		durationSec = node.AudioDurationSec
	}
	endSec := startSec + durationSec
	if node.AudioEndSec > startSec {
		endSec = node.AudioEndSec
		durationSec = endSec - startSec
	}
	return startSec, durationSec, endSec
}

func generateAndStoreTeachingNodeScripts(
	ctx context.Context,
	db *gorm.DB,
	aiClient service.AIEngine,
	courseName string,
	mode string,
	nodes []model.TeachingNode,
) (string, string, bool, error) {
	if aiClient == nil || len(nodes) == 0 {
		return "", "", false, nil
	}

	scripts := make([]string, 0, len(nodes))
	mindmaps := make([]string, 0, len(nodes))
	used := false

	for _, node := range nodes {
		resp, err := aiClient.GenerateNodeScript(ctx, service.GenerateNodeScriptRequest{
			TeachingNode: map[string]any{
				"node_id":           node.NodeID,
				"title":             node.Title,
				"summary":           node.Summary,
				"core_points":       decodeJSONStringArray(node.CorePoints),
				"examples":          decodeJSONStringArray(node.Examples),
				"common_confusions": decodeJSONStringArray(node.CommonConfusions),
			},
			CourseName: courseName,
			Mode:       mode,
		})
		if err != nil {
			return "", "", true, err
		}
		used = true
		updates := map[string]any{
			"script_text":           strings.TrimSpace(resp.Script),
			"reteach_script":        strings.TrimSpace(resp.ReteachScript),
			"transition_text":       strings.TrimSpace(resp.Transition),
			"mindmap_markdown":      strings.TrimSpace(resp.MindmapMarkdown),
			"interactive_questions": encodeJSONStringArray(resp.InteractiveQuestions),
			"structured_markdown":   strings.TrimSpace(resp.StructuredMarkdown),
			"knowledge_nodes_json":  encodeJSON(resp.KnowledgeNodes),
			"script_segments_json":  encodeJSON(resp.ScriptSegments),
			"schema_version":        2,
		}
		_ = db.Model(&model.TeachingNode{}).Where("id = ?", node.ID).Updates(updates).Error
		if strings.TrimSpace(resp.Script) != "" {
			scripts = append(scripts, strings.TrimSpace(resp.Script))
		}
		if strings.TrimSpace(resp.MindmapMarkdown) != "" {
			mindmaps = append(mindmaps, strings.TrimSpace(resp.MindmapMarkdown))
		}
	}

	return strings.Join(scripts, "\n\n"), strings.Join(mindmaps, "\n\n"), used, nil
}

func decodeJSONStringArray(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	var values []string
	if err := json.Unmarshal([]byte(raw), &values); err == nil {
		return values
	}
	return nil
}

func encodeJSONStringArray(values []string) string {
	if len(values) == 0 {
		return "[]"
	}
	payload, err := json.Marshal(values)
	if err != nil {
		return "[]"
	}
	return string(payload)
}

func encodeJSON(value any) string {
	payload, err := json.Marshal(value)
	if err != nil {
		return "[]"
	}
	if len(payload) == 0 {
		return "[]"
	}
	return string(payload)
}

func defaultScriptSegments(script string, nodeID string) []map[string]any {
	text := strings.TrimSpace(script)
	if text == "" {
		return []map[string]any{}
	}
	rough := []string{text}
	if strings.Contains(text, "。") {
		rough = strings.Split(text, "。")
	}
	segments := make([]map[string]any, 0, len(rough))
	for idx, seg := range rough {
		seg = strings.TrimSpace(seg)
		if seg == "" {
			continue
		}
		segments = append(segments, map[string]any{
			"segment_id":      fmt.Sprintf("seg_%d", idx+1),
			"text":            seg,
			"node_ids":        []string{nodeID},
			"confidence":      0.8,
			"manual_override": false,
		})
	}
	if len(segments) == 0 {
		segments = append(segments, map[string]any{
			"segment_id": "seg_1",
			"text":       text,
			"node_ids":   []string{nodeID},
			"confidence": 0.8,
		})
	}
	return segments
}

func defaultKnowledgeNodes(nodeID string, title string) []map[string]any {
	return []map[string]any{
		{
			"node_id":       nodeID,
			"parent_id":     "",
			"level":         1,
			"title":         title,
			"tags":          []string{"core"},
			"prerequisites": []string{},
			"difficulty":    "medium",
			"coverage_span": []string{"seg_1"},
		},
	}
}

func filterEmptyStrings(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			result = append(result, strings.TrimSpace(value))
		}
	}
	return result
}
