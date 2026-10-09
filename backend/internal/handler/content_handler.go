package handler

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// ModifyContentRequest —— S3 内容层的单节点 AI 修改请求。
//
// 这里刻意与 /api/v1/gen/content 的 GenContentRequest **不再共用一个结构体**。
// 旧实现把 Modify 绑成 GenContentRequest，而前端发的是
// {content_id, node_id, message}：三个字段一个都绑不上，req.Nodes 恒为空，
// 于是每次点「AI 修改」都被 `nodes 不能为空` 挡回来 —— 按钮在、功能不在，
// 正是 PRD「内容生成层无法编辑」那一条。
type ModifyContentRequest struct {
	ContentID string `json:"content_id"`
	NodeID    string `json:"node_id"`
	// Message 教师用自然语言写下的修改意图（如「精简文字并增加一个生活案例」）。
	Message string `json:"message"`
	// Action 引擎侧的动作枚举（simplify / expand / rewrite）。
	// 前端会先推断一次；留空时后端按 Message 兜底推断，不让旧调用方必须升级。
	Action          string                     `json:"action"`
	Nodes           []service.TeachingNodeItem `json:"nodes"`
	CourseName      string                     `json:"course_name"`
	ContextMarkdown string                     `json:"context_markdown"`
	OutlineID       string                     `json:"outline_id"`
	OutlineVersion  int                        `json:"outline_version"`
	Intent          *service.IntentSummary     `json:"intent,omitempty"`
	EvidenceRefs    []string                   `json:"evidence_refs,omitempty"`
}

// normalizeModifyAction 把教师的自然语言落到引擎认得的三档动作上。
//
// 引擎 partial_content.CONTENT_ACTIONS 只认 simplify / expand / rewrite：
// 动作决定提示词的骨架，教师的原话则原封不动进 modify_constraints，
// 两边拼起来才是「精简 + 教师自己那句补充要求」。认不出来就走 rewrite ——
// 它是最保守的一档，只换表述不改信息量。
func normalizeModifyAction(action string, message string) string {
	raw := strings.ToLower(strings.TrimSpace(action))
	switch raw {
	case "simplify", "expand", "rewrite":
		return raw
	}
	text := strings.ToLower(strings.TrimSpace(message))
	switch {
	case strings.Contains(text, "精简") || strings.Contains(text, "简化") ||
		strings.Contains(text, "缩短") || strings.Contains(text, "减少") ||
		strings.Contains(text, "压缩") || strings.Contains(text, "简洁") ||
		strings.Contains(text, "simplify"):
		return "simplify"
	case strings.Contains(text, "扩充") || strings.Contains(text, "增加") ||
		strings.Contains(text, "添加") || strings.Contains(text, "补充") ||
		strings.Contains(text, "展开") || strings.Contains(text, "详细") ||
		strings.Contains(text, "丰富") || strings.Contains(text, "案例") ||
		strings.Contains(text, "更多") || strings.Contains(text, "expand"):
		return "expand"
	}
	return "rewrite"
}

// ContentHandler P1: S3 大纲 → 内容生成（独立阶段）— HTTP 处理器。
// 路由注册（backend/internal/router/teacher.go:181-185）：
//   POST /api/v1/gen/content           — 创建内容生成任务（给定大纲节点）
//   GET  /api/v1/gen/content/status/:content_id — 查询内容生成状态
//   POST /api/v1/gen/content/modify    — 基于修改后的节点重新生成内容
type ContentHandler struct {
	aiClient service.AIEngine
}

func NewContentHandler(aiClient service.AIEngine) *ContentHandler {
	return &ContentHandler{aiClient: aiClient}
}

// Create  POST /api/v1/gen/content — 从大纲节点生成具体内容。
// 请求体与 Python /gen/content 的 GenContentRequest 对齐（nodes 必填）。
func (h *ContentHandler) Create(c *gin.Context) {
	var req service.GenContentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if len(req.Nodes) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "nodes 不能为空"})
		return
	}
	resp, err := h.aiClient.GenerateContent(c.Request.Context(), req)
	if err != nil {
		if httpErr, isHTTP := err.(*service.AIEngineHTTPError); isHTTP {
			c.JSON(httpErr.StatusCode, gin.H{"code": httpErr.StatusCode, "message": httpErr.Detail})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建内容生成任务失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Status  GET /api/v1/gen/content/status/:content_id — 轮询内容生成进度。
func (h *ContentHandler) Status(c *gin.Context) {
	contentID := c.Param("content_id")
	if contentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 content_id"})
		return
	}
	resp, err := h.aiClient.ContentStatus(c.Request.Context(), contentID)
	if err != nil {
		if httpErr, isHTTP := err.(*service.AIEngineHTTPError); isHTTP {
			c.JSON(httpErr.StatusCode, gin.H{"code": httpErr.StatusCode, "message": httpErr.Detail})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "查询内容生成状态失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}

// Modify  POST /api/v1/gen/content/modify — 对单个节点的已有内容做 AI 修改。
//
// 语义：带着「当前节点树 + 目标节点 + 教师那句修改要求」交给引擎的
// /gen/content（mode=partial），只重生成这一个节点，其余节点原样返回。
//
// 引擎侧是异步任务：首个响应里 nodes 恒为空，必须轮询 ContentStatus 才能拿到
// 结果（详见 service.WaitContentResult 的注释）。旧实现少了这一步，
// 上层拿到空节点仍报「已更新」，老师看到的就是改了没变化。
func (h *ContentHandler) Modify(c *gin.Context) {
	var req ModifyContentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	nodeID := strings.TrimSpace(req.NodeID)
	if nodeID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 node_id"})
		return
	}
	message := strings.TrimSpace(req.Message)
	if message == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少修改指令 message"})
		return
	}
	if len(req.Nodes) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    400,
			"message": "nodes 不能为空：AI 修改需要当前节点内容作为改写基础",
		})
		return
	}

	genReq := service.GenContentRequest{
		Nodes:             req.Nodes,
		ContextMarkdown:   req.ContextMarkdown,
		CourseName:        req.CourseName,
		Mode:              "partial",
		OutlineID:         req.OutlineID,
		OutlineVersion:    req.OutlineVersion,
		TargetNodeIDs:     []string{nodeID},
		ModifyAction:      normalizeModifyAction(req.Action, message),
		ModifyConstraints: []string{message},
		Intent:            req.Intent,
		EvidenceRefs:      req.EvidenceRefs,
	}
	if strings.TrimSpace(genReq.CourseName) == "" {
		genReq.CourseName = "课件"
	}

	first, err := h.aiClient.GenerateContent(c.Request.Context(), genReq)
	if err != nil {
		if httpErr, isHTTP := err.(*service.AIEngineHTTPError); isHTTP {
			c.JSON(httpErr.StatusCode, gin.H{"code": httpErr.StatusCode, "message": httpErr.Detail})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "修改内容生成失败: " + err.Error()})
		return
	}

	nodes, err := service.WaitContentResult(c.Request.Context(), h.aiClient, first)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	contentID := ""
	if first != nil {
		contentID = first.ContentID
	}
	c.JSON(http.StatusOK, gin.H{
		"code": 200,
		"data": gin.H{
			"content_id":  contentID,
			"status":      "done",
			"node_id":     nodeID,
			"action":      genReq.ModifyAction,
			"total_nodes": len(req.Nodes),
			"nodes":       nodes,
		},
	})
}

// ModifyScript POST /api/v1/gen/content/modify-script — 对单节点现有讲稿应用教师指令（讲稿 AI 编辑）。
// 不重跑大纲和整批节点；调用者负责把返回的讲稿保存到项目草稿/版本。
// 注意与 Modify（内容层整节点重生成）区分：本接口只改讲稿文本，同步返回。
func (h *ContentHandler) ModifyScript(c *gin.Context) {
	var req service.GenScriptModifyRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if strings.TrimSpace(req.NodeID) == "" || strings.TrimSpace(req.Script) == "" || strings.TrimSpace(req.Message) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "node_id、script 和 message 不能为空"})
		return
	}
	resp, err := h.aiClient.ModifyContentScript(c.Request.Context(), req)
	if err != nil {
		if httpErr, isHTTP := err.(*service.AIEngineHTTPError); isHTTP {
			c.JSON(httpErr.StatusCode, gin.H{"code": httpErr.StatusCode, "message": httpErr.Detail})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "修改讲稿失败: " + err.Error()})
		return
	}
	if resp.UsedFallback || strings.TrimSpace(resp.Script) == "" || resp.NodeID != req.NodeID {
		c.JSON(http.StatusBadGateway, gin.H{"code": 502, "message": "AI 未返回有效的当前节点讲稿，原稿未修改"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": resp})
}
