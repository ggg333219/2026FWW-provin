package handler

import (
	"fmt"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/pkg/apiresp"
	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
	"smart-teaching-backend/pkg/logger"
)

type AIHandler struct {
	db       *gorm.DB
	aiClient service.AIEngine
}

func NewAIHandler(db *gorm.DB, aiClient service.AIEngine) *AIHandler {
	return &AIHandler{db: db, aiClient: aiClient}
}

// 3.1 获取课件知识图谱
// GET /api/v1/ai/coursewares/:courseId/knowledge-graph
func (h *AIHandler) GetKnowledgeGraph(c *gin.Context) {
	courseId := c.Param("courseId")

	// TODO: 从数据库或 AI 服务获取知识图谱
	// 这里返回模拟数据
	data := gin.H{
		"courseId": courseId,
		"structure": []gin.H{
			{
				"chapter": "第一章：数据清洗基础",
				"knowledgePoints": []gin.H{
					{
						"name":      "缺失值处理",
						"subPoints": []string{"fillna()", "interpolate()", "dropna()"},
					},
					{
						"name":      "异常值识别",
						"subPoints": []string{"Z-Score", "IQR"},
					},
				},
			},
			{
				"chapter": "第二章：数据转换",
				"knowledgePoints": []gin.H{
					{
						"name":      "数据类型转换",
						"subPoints": []string{"astype()", "to_numeric()"},
					},
					{
						"name":      "数据标准化",
						"subPoints": []string{"MinMaxScaler", "StandardScaler"},
					},
				},
			},
		},
	}

	apiresp.OK(c, "请求成功", data)
}

// 3.2 智能多模态答疑
// POST /api/v1/ai/coursewares/:courseId/ask
func (h *AIHandler) AskQuestion(c *gin.Context) {
	courseId := c.Param("courseId")

	var req struct {
		PageNum    int    `json:"pageNum" binding:"required"`
		NodeID     string `json:"nodeId"`
		Type       string `json:"type"` // text/audio/image
		Question   string `json:"question" binding:"required"`
		TracePoint *struct {
			X float64 `json:"x"`
			Y float64 `json:"y"`
		} `json:"tracePoint,omitempty"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		logger.Errorf("参数错误: %v", err)
		apiresp.BadRequest(c, "参数错误", err.Error())
		return
	}

	// 获取当前页讲稿作为上下文
	var coursePage model.CoursePage
	context := ""
	if err := h.db.Where("course_id = ? AND page_index = ?", courseId, req.PageNum).First(&coursePage).Error; err == nil {
		context = pageContextText(coursePage)
	}
	if strings.TrimSpace(context) == "" {
		context = buildPageContextFromTeachingNodes(loadTeachingNodesByPage(h.db, courseId, req.PageNum))
	}
	nodeID := strings.TrimSpace(req.NodeID)
	if nodeID == "" {
		nodeID = fmt.Sprintf("p%d_n1", req.PageNum)
	}
	nodeScopedContext := buildNodeScopedContext(h.db, courseId, req.PageNum, nodeID)
	if strings.TrimSpace(nodeScopedContext) != "" {
		context = nodeScopedContext
	}

	// 使用 AI 客户端获取真实答案（已配置为 Dify 或本地引擎）
	answer := ""
	if h.aiClient != nil {
		resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{
			Question:    req.Question,
			CurrentPage: req.PageNum,
			Context:     context,
			Mode:        "llm",
		})
		if err == nil && strings.TrimSpace(resp.Answer) != "" {
			answer = resp.Answer
		}
	}

	// 如果 AI 调用失败，使用 fallback
	if answer == "" {
		answer = generateAIAnswer(req.Question, context)
	}

	if req.TracePoint != nil {
		answer = "针对坐标(" +
			strconv.FormatFloat(req.TracePoint.X, 'f', 2, 64) + "," +
			strconv.FormatFloat(req.TracePoint.Y, 'f', 2, 64) +
			")的解答：" + answer
	}

	// 记录提问日志
	log := model.QuestionLog{
		UserID:    c.GetString("userId"), // 需要从 JWT 获取
		CourseID:  courseId,
		PageIndex: req.PageNum,
		NodeID:    nodeID,
		Question:  req.Question,
		Answer:    answer,
	}
	h.db.Create(&log)

	apiresp.OK(c, "请求成功", gin.H{
			"answer":         answer,
			"sourcePage":     req.PageNum,
			"source_page":    req.PageNum,
			"sourceNodeId":   nodeID,
			"source_node_id": nodeID,
		})
}

// 生成 AI 回答（模拟）
func generateAIAnswer(question, context string) string {
	if context != "" {
		return "根据课件内容，" + question + "的答案是：" + context[:min(50, len(context))] + "..."
	}
	return "这是关于'" + question + "'的详细解答。"
}

// 辅助函数：取最小值
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
