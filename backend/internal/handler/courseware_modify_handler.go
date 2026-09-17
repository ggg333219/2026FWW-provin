package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

type modifyAI interface {
	ParseModify(ctx context.Context, req service.ModifyIntentRequest) (*service.ModifyIntentResponse, error)
}

type CoursewareModifyHandler struct {
	projects *service.CoursewareProjectService
	versions *service.CoursewareVersionService
	ai       service.AIEngine
}

func NewCoursewareModifyHandler(projects *service.CoursewareProjectService, versions *service.CoursewareVersionService, ai service.AIEngine) *CoursewareModifyHandler {
	return &CoursewareModifyHandler{projects: projects, versions: versions, ai: ai}
}

type modifyRequest struct {
	Instruction     string `json:"instruction"`
	ModifySessionID string `json:"modify_session_id,omitempty"`
}

func (h *CoursewareModifyHandler) Modify(c *gin.Context) {
	owner := strings.TrimSpace(c.GetString("userID"))
	if owner == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"code": 401, "message": "缺少用户身份"})
		return
	}
	var req modifyRequest
	if err := c.ShouldBindJSON(&req); err != nil || strings.TrimSpace(req.Instruction) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "instruction 不能为空"})
		return
	}
	projectID := c.Param("project_id")
	project, err := h.projects.Get(c.Request.Context(), owner, projectID)
	if err != nil {
		projectError(c, err)
		return
	}
	if project.Status == "archived" {
		c.JSON(http.StatusConflict, gin.H{"code": 409, "message": "课件项目已归档"})
		return
	}
	nodes, draft, err := draftNodes(project.DraftJSON)
	if err != nil || len(nodes) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "课件草稿中没有可修改节点"})
		return
	}
	parser, ok := h.ai.(modifyAI)
	if !ok {
		c.JSON(http.StatusNotImplemented, gin.H{"code": 501, "message": "当前 AI 客户端不支持修改意图解析"})
		return
	}
	parsed, err := parser.ParseModify(c.Request.Context(), service.ModifyIntentRequest{ProjectID: projectID, Instruction: req.Instruction, Nodes: nodes, ModifySessionID: req.ModifySessionID})
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"code": 502, "message": "解析修改意图失败: " + err.Error()})
		return
	}
	if parsed.ClarificationNeeded || len(parsed.TargetIDs) == 0 && parsed.TargetType != "style" {
		c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"clarification_needed": true, "clarification": parsed.Clarification, "parsed": parsed}})
		return
	}
	newNodes := nodes
	if !isStyleOnly(parsed.Actions) {
		genReq := service.GenContentRequest{Nodes: nodes, CourseName: project.Title, Mode: "partial", TargetNodeIDs: parsed.TargetIDs, ModifyInstruction: req.Instruction, Actions: parsed.Actions, Constraints: parsed.Constraints}
		content, err := h.ai.GenerateContent(c.Request.Context(), genReq)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"code": 502, "message": "创建局部生成任务失败: " + err.Error()})
			return
		}
		content, err = waitContent(c, h.ai, content.ContentID)
		if err != nil || content.Status == "failed" {
			c.JSON(http.StatusBadGateway, gin.H{"code": 502, "message": "局部生成失败"})
			return
		}
		newNodes = mergeModifiedNodes(nodes, content.Nodes, parsed.TargetIDs)
	}
	draft["nodes"] = newNodes
	newDraft, _ := json.Marshal(draft)
	oldNodes, _ := json.Marshal(nodes)
	version, err := h.versions.ApplyModification(c.Request.Context(), owner, projectID, oldNodes, newDraft, req.Instruction, service.ModifyAudit{Actions: parsed.Actions, TargetNodeIDs: parsed.TargetIDs, Confidence: parsed.Confidence})
	if err != nil {
		projectError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"modified_nodes": newNodes, "previous_version_id": version.ID, "version_no": version.VersionNo + 1, "parsed": parsed}})
}

func (h *CoursewareModifyHandler) History(c *gin.Context) {
	owner := strings.TrimSpace(c.GetString("userID"))
	if owner == "" {
		c.JSON(401, gin.H{"code": 401, "message": "缺少用户身份"})
		return
	}
	items, err := h.versions.List(c.Request.Context(), owner, c.Param("project_id"))
	if err != nil {
		projectError(c, err)
		return
	}
	c.JSON(200, gin.H{"code": 200, "data": gin.H{"versions": items}})
}

func (h *CoursewareModifyHandler) Rollback(c *gin.Context) {
	owner := strings.TrimSpace(c.GetString("userID"))
	if owner == "" {
		c.JSON(401, gin.H{"code": 401, "message": "缺少用户身份"})
		return
	}
	var req struct {
		VersionID string `json:"version_id"`
	}
	if c.ShouldBindJSON(&req) != nil || req.VersionID == "" {
		c.JSON(400, gin.H{"code": 400, "message": "version_id 不能为空"})
		return
	}
	project, err := h.projects.Get(c.Request.Context(), owner, c.Param("project_id"))
	if err != nil {
		projectError(c, err)
		return
	}
	nodes, draft, err := draftNodes(project.DraftJSON)
	if err != nil {
		c.JSON(400, gin.H{"code": 400, "message": "草稿格式错误"})
		return
	}
	var target service.CoursewareVersion
	items, err := h.versions.List(c.Request.Context(), owner, c.Param("project_id"))
	if err != nil {
		projectError(c, err)
		return
	}
	for _, item := range items {
		if item.ID == req.VersionID {
			target = item
			break
		}
	}
	if target.ID == "" {
		c.JSON(404, gin.H{"code": 404, "message": "版本不存在"})
		return
	}
	var targetNodes []any
	if json.Unmarshal(target.NodesSnapshot, &targetNodes) != nil {
		c.JSON(500, gin.H{"code": 500, "message": "版本快照损坏"})
		return
	}
	draft["nodes"] = targetNodes
	newDraft, _ := json.Marshal(draft)
	oldNodes, _ := json.Marshal(nodes)
	created, err := h.versions.Rollback(c.Request.Context(), owner, c.Param("project_id"), req.VersionID, oldNodes, newDraft)
	if err != nil {
		projectError(c, err)
		return
	}
	c.JSON(200, gin.H{"code": 200, "data": gin.H{"version_id": created.ID, "version_no": created.VersionNo, "nodes": targetNodes}})
}

func draftNodes(raw model.JSONB) ([]service.TeachingNodeItem, map[string]any, error) {
	var draft map[string]any
	if len(raw) == 0 {
		draft = map[string]any{}
	} else if err := json.Unmarshal(raw, &draft); err != nil {
		return nil, nil, err
	}
	rawNodes, ok := draft["nodes"]
	if !ok {
		return nil, draft, nil
	}
	buf, err := json.Marshal(rawNodes)
	if err != nil {
		return nil, nil, err
	}
	var nodes []service.TeachingNodeItem
	if err := json.Unmarshal(buf, &nodes); err != nil {
		return nil, nil, err
	}
	return nodes, draft, nil
}
func mergeModifiedNodes(original, modified []service.TeachingNodeItem, targets []string) []service.TeachingNodeItem {
	byID := map[string]service.TeachingNodeItem{}
	for _, n := range modified {
		byID[n.NodeID] = n
	}
	out := make([]service.TeachingNodeItem, 0, len(original))
	for _, n := range original {
		if contains(targets, n.NodeID) {
			if replacement, ok := byID[n.NodeID]; ok {
				out = append(out, replacement)
				continue
			}
		}
		out = append(out, n)
	}
	return out
}
func contains(items []string, value string) bool {
	for _, item := range items {
		if item == value {
			return true
		}
	}
	return false
}

func isStyleOnly(actions []string) bool {
	return len(actions) == 1 && actions[0] == "restyle"
}
func waitContent(c *gin.Context, ai service.AIEngine, id string) (*service.GenContentStatusResponse, error) {
	if id == "" {
		return nil, errors.New("empty content id")
	}
	deadline := time.Now().Add(2 * time.Minute)
	for time.Now().Before(deadline) {
		result, err := ai.ContentStatus(c.Request.Context(), id)
		if err != nil {
			return nil, err
		}
		if result.Status == "done" || result.Status == "failed" {
			return result, nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return nil, errors.New("content generation timeout")
}
