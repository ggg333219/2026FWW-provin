package handler

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

func ensureDialogueSession(db *gorm.DB, sessionID, userID, courseID string, page int, nodeID string, currentTimeSec int) string {
	sessionID = strings.TrimSpace(sessionID)
	if sessionID == "" {
		sessionID = uuid.NewString()
	}

	now := time.Now()
	var session model.DialogueSession
	err := db.First(&session, "id = ?", sessionID).Error
	if err == nil {
		updates := map[string]any{
			"user_id":          strings.TrimSpace(userID),
			"course_id":        strings.TrimSpace(courseID),
			"current_page":     page,
			"current_node_id":  strings.TrimSpace(nodeID),
			"current_time_sec": maxInt(currentTimeSec, 0),
			"last_asked_at":    now,
		}
		_ = db.Model(&session).Updates(updates).Error
		return sessionID
	}

	if !errors.Is(err, gorm.ErrRecordNotFound) {
		return sessionID
	}

	created := model.DialogueSession{
		BaseModel:      model.BaseModel{ID: sessionID},
		UserID:         strings.TrimSpace(userID),
		CourseID:       strings.TrimSpace(courseID),
		CurrentPage:    page,
		CurrentNodeID:  strings.TrimSpace(nodeID),
		CurrentTimeSec: maxInt(currentTimeSec, 0),
		LastAskedAt:    &now,
	}
	_ = db.Create(&created).Error
	return sessionID
}

func syncDialogueSessionState(db *gorm.DB, sessionID, userID, courseID string, page int, nodeID string, currentTimeSec int) {
	if strings.TrimSpace(sessionID) == "" || strings.TrimSpace(courseID) == "" {
		return
	}
	ensureDialogueSession(db, sessionID, userID, courseID, page, nodeID, currentTimeSec)
}

func appendDialogueTurn(db *gorm.DB, sessionID, userID, courseID string, page int, nodeID, question, answer string, sourcePage int, needReteach bool, followUpSuggestion string) {
	if strings.TrimSpace(sessionID) == "" || strings.TrimSpace(courseID) == "" || strings.TrimSpace(question) == "" {
		return
	}

	var turnCount int64
	_ = db.Model(&model.DialogueTurn{}).Where("session_id = ?", sessionID).Count(&turnCount).Error
	turn := model.DialogueTurn{
		SessionID:          sessionID,
		CourseID:           strings.TrimSpace(courseID),
		UserID:             strings.TrimSpace(userID),
		TurnIndex:          int(turnCount) + 1,
		PageIndex:          page,
		NodeID:             strings.TrimSpace(nodeID),
		Question:           strings.TrimSpace(question),
		Answer:             strings.TrimSpace(answer),
		SourcePage:         sourcePage,
		NeedReteach:        needReteach,
		FollowUpSuggestion: strings.TrimSpace(followUpSuggestion),
	}
	_ = db.Create(&turn).Error
}

func buildDialogueContext(db *gorm.DB, sessionID string, limit int) (string, []service.ConversationTurn) {
	sessionID = strings.TrimSpace(sessionID)
	if sessionID == "" {
		return "", nil
	}
	if limit <= 0 {
		limit = 4
	}

	var turns []model.DialogueTurn
	_ = db.Where("session_id = ?", sessionID).Order("turn_index desc").Limit(limit).Find(&turns).Error
	if len(turns) == 0 {
		return "", nil
	}

	for left, right := 0, len(turns)-1; left < right; left, right = left+1, right-1 {
		turns[left], turns[right] = turns[right], turns[left]
	}

	history := make([]service.ConversationTurn, 0, len(turns))
	parts := make([]string, 0, len(turns))
	for _, turn := range turns {
		history = append(history, service.ConversationTurn{
			Question: turn.Question,
			Answer:   turn.Answer,
			Page:     turn.PageIndex,
			NodeID:   turn.NodeID,
		})
		parts = append(parts, fmt.Sprintf("第%d轮 学生：%s AI：%s", turn.TurnIndex, trimForDialogueSummary(turn.Question, 60), trimForDialogueSummary(turn.Answer, 100)))
	}

	return strings.Join(parts, "\n"), history
}

func trimForDialogueSummary(value string, limit int) string {
	value = strings.TrimSpace(value)
	if value == "" || limit <= 0 {
		return value
	}
	runes := []rune(value)
	if len(runes) <= limit {
		return value
	}
	return string(runes[:limit]) + "..."
}

func resolveResumeNodeID(currentNodeID string, page int, needReteach bool) string {
	if needReteach {
		return defaultStringValue(currentNodeID, fmt.Sprintf("p%d_n1", page))
	}
	return nextNodeID(currentNodeID, page)
}

func resolveResumeNodeIDByCourse(db *gorm.DB, courseID, currentNodeID string, page int, needReteach bool) string {
	currentNodeID = strings.TrimSpace(currentNodeID)
	if strings.TrimSpace(courseID) == "" {
		return resolveResumeNodeID(currentNodeID, page, needReteach)
	}

	nodes := loadTeachingNodesByPage(db, courseID, page)
	if len(nodes) == 0 {
		return resolveResumeNodeID(currentNodeID, page, needReteach)
	}

	if needReteach {
		if currentNodeID != "" {
			return currentNodeID
		}
		return defaultStringValue(strings.TrimSpace(nodes[0].NodeID), fmt.Sprintf("p%d_n1", page))
	}

	if currentNodeID == "" {
		return defaultStringValue(strings.TrimSpace(nodes[0].NodeID), fmt.Sprintf("p%d_n1", page))
	}

	for i := 0; i < len(nodes); i++ {
		if strings.TrimSpace(nodes[i].NodeID) != currentNodeID {
			continue
		}
		if i+1 < len(nodes) {
			return defaultStringValue(strings.TrimSpace(nodes[i+1].NodeID), nextNodeID(currentNodeID, page))
		}
		return nextNodeID(currentNodeID, page)
	}

	return nextNodeID(currentNodeID, page)
}

func buildNodeScopedContext(db *gorm.DB, courseID string, page int, nodeID string) string {
	nodeID = strings.TrimSpace(nodeID)
	nodes := loadTeachingNodesByPage(db, courseID, page)
	if len(nodes) == 0 {
		return ""
	}

	nodeByID := make(map[string]model.TeachingNode, len(nodes))
	for _, node := range nodes {
		id := strings.TrimSpace(node.NodeID)
		if id != "" {
			nodeByID[id] = node
		}
	}

	targetNodeIDs := map[string]struct{}{}
	if nodeID != "" {
		targetNodeIDs[nodeID] = struct{}{}
		for _, prereq := range extractPrerequisiteNodeIDs(nodeByID, nodeID) {
			targetNodeIDs[prereq] = struct{}{}
		}
	}

	segments := make([]string, 0)
	if len(targetNodeIDs) > 0 {
		for _, node := range nodes {
			matched := extractSegmentTextsByNodeSet(node.ScriptSegmentsJSON, targetNodeIDs)
			if len(matched) > 0 {
				segments = append(segments, matched...)
			}
		}
	}

	if len(segments) > 0 {
		return strings.Join(filterEmptyStrings(segments), "\n\n")
	}

	if len(targetNodeIDs) > 0 {
		parts := make([]string, 0)
		for target := range targetNodeIDs {
			node, ok := nodeByID[target]
			if !ok {
				continue
			}
			text := strings.TrimSpace(teachingNodeContextText(node))
			if text != "" {
				parts = append(parts, text)
			}
		}
		if len(parts) > 0 {
			return strings.Join(filterEmptyStrings(parts), "\n\n")
		}
	}

	return buildPageContextFromTeachingNodes(nodes)
}

func extractSegmentTextsByNodeSet(rawJSON string, nodeIDSet map[string]struct{}) []string {
	rawJSON = strings.TrimSpace(rawJSON)
	if rawJSON == "" || len(nodeIDSet) == 0 {
		return nil
	}

	var segments []map[string]any
	if err := json.Unmarshal([]byte(rawJSON), &segments); err != nil {
		return nil
	}

	result := make([]string, 0)
	for _, segment := range segments {
		nodeIDs, ok := segment["node_ids"].([]any)
		if !ok {
			continue
		}
		contains := false
		for _, item := range nodeIDs {
			candidate := strings.TrimSpace(fmt.Sprintf("%v", item))
			if _, ok := nodeIDSet[candidate]; ok {
				contains = true
				break
			}
		}
		if !contains {
			continue
		}
		text := strings.TrimSpace(fmt.Sprintf("%v", segment["text"]))
		if text != "" {
			result = append(result, text)
		}
	}

	return result
}

func extractPrerequisiteNodeIDs(nodeByID map[string]model.TeachingNode, nodeID string) []string {
	node, ok := nodeByID[nodeID]
	if !ok {
		return nil
	}
	raw := strings.TrimSpace(node.KnowledgeNodesJSON)
	if raw == "" {
		return nil
	}

	var entries []map[string]any
	if err := json.Unmarshal([]byte(raw), &entries); err != nil {
		return nil
	}

	result := make([]string, 0)
	seen := make(map[string]struct{})
	for _, entry := range entries {
		entryNodeID := strings.TrimSpace(fmt.Sprintf("%v", entry["node_id"]))
		if entryNodeID != nodeID {
			continue
		}
		prereqRaw, ok := entry["prerequisites"].([]any)
		if !ok {
			continue
		}
		for _, item := range prereqRaw {
			candidate := strings.TrimSpace(fmt.Sprintf("%v", item))
			if candidate == "" {
				continue
			}
			if _, exists := nodeByID[candidate]; !exists {
				continue
			}
			if _, exists := seen[candidate]; exists {
				continue
			}
			seen[candidate] = struct{}{}
			result = append(result, candidate)
		}
	}

	return result
}
