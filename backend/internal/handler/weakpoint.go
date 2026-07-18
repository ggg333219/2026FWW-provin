package handler

import (
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/pkg/apiresp"
	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

type WeakPointHandler struct {
	db       *gorm.DB
	aiClient service.AIEngine
}

func NewWeakPointHandler(db *gorm.DB, aiClient service.AIEngine) *WeakPointHandler {
	return &WeakPointHandler{db: db, aiClient: aiClient}
}

func (h *WeakPointHandler) ParseKnowledge(c *gin.Context) {
	var req struct {
		FileContent string `json:"fileContent" binding:"required"`
		FileType    string `json:"fileType" binding:"required"`
		StudentID   string `json:"studentId" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}

	text := strings.TrimSpace(req.FileContent)
	if text == "" {
		text = fmt.Sprintf("请根据 %s 文件内容拆解知识点", req.FileType)
	}

	if h.aiClient != nil {
		resp, err := h.aiClient.ParseKnowledge(c.Request.Context(), service.ParseKnowledgeRequest{Text: text, Mode: "llm"})
		if err == nil && len(resp.Structure) > 0 {
			apiresp.OK(c, "请求成功", gin.H{"structure": resp.Structure})
			return
		}
	}

	apiresp.OK(c, "请求成功", gin.H{"structure": fallbackKnowledgeStructure(text)})
}

func (h *WeakPointHandler) GetWeakPointList(c *gin.Context) {
	courseID := c.Param("courseId")
	if courseID == "" {
		courseID = strings.TrimSpace(c.Query("courseId"))
	}
	studentID := strings.TrimSpace(c.Query("studentId"))
	if studentID == "" {
		apiresp.BadRequest(c, "缺少参数: studentId", "")
		return
	}

	weakPoints := buildWeakPointList(h.db, studentID, courseID)
	if len(weakPoints) == 0 {
		weakPoints = []gin.H{}
	}

	apiresp.OK(c, "请求成功", weakPoints)
}

func (h *WeakPointHandler) GetWeakPointExplain(c *gin.Context) {
	weakPointID, weakPointName := h.resolveWeakPointExplainInput(c)
	if weakPointID == "" && weakPointName == "" {
		apiresp.BadRequest(c, "缺少薄弱点参数", "")
		return
	}
	if weakPointName == "" {
		weakPointName = fallbackWeakPointName(weakPointID)
	}

	content := fallbackWeakPointExplain(weakPointID, weakPointName)
	if h.aiClient != nil {
		resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{Question: "请用教学口吻讲解知识点：" + weakPointName, CurrentPage: maxWeakPointPage(weakPointID), Context: weakPointName, Mode: "llm"})
		if err == nil && strings.TrimSpace(resp.Answer) != "" {
			content = resp.Answer
		}
	}

	apiresp.OK(c, "请求成功", gin.H{"id": weakPointID, "weakPointId": weakPointID, "name": weakPointName, "title": weakPointName + " · 知识点讲解", "content": content, "examples": []string{"结合当前页讲稿复述一遍", "尝试举一个自己的例子"}})
}

func (h *WeakPointHandler) GenerateTest(c *gin.Context) {
	weakPointID := c.Param("weakPointId")
	var req struct {
		QuestionType  string `json:"questionType"`
		WeakPointID   string `json:"weakPointId"`
		WeakPointName string `json:"weakPointName"`
	}
	_ = c.ShouldBindJSON(&req)
	if weakPointID == "" {
		weakPointID = req.WeakPointID
	}
	questionType := strings.TrimSpace(req.QuestionType)
	if questionType == "" {
		questionType = "single"
	}
	weakPointName := strings.TrimSpace(req.WeakPointName)
	if weakPointName == "" {
		weakPointName = fallbackWeakPointName(weakPointID)
	}

	var payload *weakPointTestPayload
	if h.aiClient != nil {
		prompt := fmt.Sprintf("请为薄弱点“%s”生成一道%s题，返回严格JSON：{\"content\":\"题干\",\"options\":[\"A.xxx\",\"B.xxx\",\"C.xxx\",\"D.xxx\"],\"answer\":\"A\",\"explanation\":\"解析\"}", weakPointName, mapQuestionType(questionType))
		resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{Question: prompt, CurrentPage: maxWeakPointPage(weakPointID), Context: weakPointName, Mode: "llm"})
		if err == nil {
			payload, _ = parseWeakPointTest(resp.Answer)
		}
	}
	if payload == nil {
		payload = fallbackWeakPointTest(weakPointID, questionType)
	}

	optionsJSON, _ := json.Marshal(payload.Options)
	questionRecord := model.Question{WeakPointID: weakPointID, QuestionType: questionType, Content: payload.Content, Options: string(optionsJSON), Answer: payload.Answer, Explanation: payload.Explanation, Difficulty: 2}
	if err := h.db.Create(&questionRecord).Error; err != nil {
		apiresp.Internal(c, "保存题目失败", "")
		return
	}

	apiresp.OK(c, "请求成功", gin.H{"questionId": questionRecord.ID, "type": questionType, "content": payload.Content, "options": payload.Options})
}

func (h *WeakPointHandler) CheckAnswer(c *gin.Context) {
	questionID := c.Param("questionId")
	var req struct {
		StudentID  string `json:"studentId"`
		QuestionID string `json:"questionId"`
		UserAnswer string `json:"userAnswer" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "缺少参数: userAnswer", "")
		return
	}
	if questionID == "" {
		questionID = req.QuestionID
	}

	var question model.Question
	if err := h.db.First(&question, "id = ?", questionID).Error; err != nil {
		apiresp.OK(c, "请求成功", fallbackCheckAnswer(questionID, req.UserAnswer))
		return
	}

	correctAnswer := strings.TrimSpace(question.Answer)
	userAnswer := strings.TrimSpace(req.UserAnswer)
	isCorrect := strings.EqualFold(userAnswer, correctAnswer)
	if !isCorrect && len(correctAnswer) == 1 {
		isCorrect = strings.HasPrefix(strings.ToUpper(userAnswer), strings.ToUpper(correctAnswer))
	}
	masteryDelta := -5
	if isCorrect {
		masteryDelta = 10
	}
	if strings.TrimSpace(req.StudentID) != "" {
		_ = h.db.Create(&model.AnswerRecord{StudentID: req.StudentID, QuestionID: questionID, UserAnswer: req.UserAnswer, IsCorrect: isCorrect, MasteryDelta: masteryDelta}).Error
	}

	apiresp.OK(c, "请求成功", gin.H{"isCorrect": isCorrect, "correctAnswer": correctAnswer, "explanation": question.Explanation, "masteryDelta": masteryDelta, "newMastery": 65 + masteryDelta})
}

type weakPointTestPayload struct {
	Content     string   `json:"content"`
	Options     []string `json:"options"`
	Answer      string   `json:"answer"`
	Explanation string   `json:"explanation"`
}

func parseWeakPointTest(raw string) (*weakPointTestPayload, error) {
	cleaned := strings.TrimSpace(raw)
	if strings.HasPrefix(cleaned, "```") {
		cleaned = strings.TrimPrefix(cleaned, "```json")
		cleaned = strings.TrimPrefix(cleaned, "```")
		cleaned = strings.TrimSuffix(cleaned, "```")
		cleaned = strings.TrimSpace(cleaned)
	}

	var payload weakPointTestPayload
	if err := json.Unmarshal([]byte(cleaned), &payload); err != nil {
		return nil, err
	}
	if strings.TrimSpace(payload.Content) == "" || len(payload.Options) < 2 || strings.TrimSpace(payload.Answer) == "" {
		return nil, errInvalidAIResponse
	}
	if strings.TrimSpace(payload.Explanation) == "" {
		payload.Explanation = "请回顾本题涉及的知识点后再尝试一次。"
	}
	return &payload, nil
}

var errInvalidAIResponse = errors.New("invalid AI response payload")

func fallbackKnowledgeStructure(text string) []gin.H {
	parts := strings.FieldsFunc(text, func(r rune) bool {
		return r == '\n' || r == '。' || r == '；' || r == ';'
	})
	result := make([]gin.H, 0)
	for index, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		result = append(result, gin.H{"name": fmt.Sprintf("知识点%d", index+1), "children": []gin.H{{"name": part}}})
		if len(result) >= 6 {
			break
		}
	}
	if len(result) == 0 {
		result = []gin.H{{"name": "课程概览", "children": []gin.H{{"name": "核心概念"}, {"name": "关键方法"}, {"name": "应用场景"}}}}
	}
	return result
}

func buildWeakPointList(db *gorm.DB, studentID, courseID string) []gin.H {
	type pageStat struct {
		PageIndex int
		Count     int
	}
	var stats []pageStat
	db.Table("question_logs").Select("page_index, count(*) as count").Where("user_id = ? AND course_id = ?", studentID, courseID).Group("page_index").Order("count desc").Limit(5).Scan(&stats)
	result := make([]gin.H, 0, len(stats))
	for _, stat := range stats {
		mastery := 100 - stat.Count*12
		if mastery < 0 {
			mastery = 0
		}
		result = append(result, gin.H{"weakPointId": fmt.Sprintf("wp-page-%d", stat.PageIndex), "id": fmt.Sprintf("wp-page-%d", stat.PageIndex), "name": fmt.Sprintf("第%d页知识点", stat.PageIndex), "description": "根据提问记录自动识别的薄弱点", "count": stat.Count, "mastery": mastery, "pageIndex": stat.PageIndex})
	}
	return result
}

func (h *WeakPointHandler) resolveWeakPointExplainInput(c *gin.Context) (string, string) {
	weakPointID := c.Param("weakPointId")
	weakPointName := strings.TrimSpace(c.Query("name"))
	if weakPointID != "" || weakPointName != "" {
		return weakPointID, weakPointName
	}
	var req struct {
		WeakPointID   string `json:"weakPointId"`
		WeakPointName string `json:"weakPointName"`
	}
	_ = c.ShouldBindJSON(&req)
	return req.WeakPointID, req.WeakPointName
}

func fallbackWeakPointExplain(weakPointID, weakPointName string) string {
	switch weakPointID {
	case "wp_001":
		return "缺失值是数据中为空的部分。常用处理方法包括 fillna()、interpolate() 和 dropna()，需要根据数据类型和业务场景选择合适策略。"
	case "wp_002":
		return "异常值是明显偏离总体分布的数据点。常见识别方法包括 Z-Score、IQR 和箱线图，处理时要先判断是否真实异常。"
	default:
		if page := maxWeakPointPage(weakPointID); page > 0 {
			return fmt.Sprintf("第 %d 页知识点需要重点回顾。建议先重新阅读该页讲稿，再结合一个真实案例理解核心概念。", page)
		}
		return fmt.Sprintf("%s 是当前阶段需要重点巩固的知识点。建议从定义、例子、练习三个层面逐步掌握。", weakPointName)
	}
}

func fallbackWeakPointName(weakPointID string) string {
	if weakPointID == "" {
		return "薄弱点练习"
	}
	if page := maxWeakPointPage(weakPointID); page > 0 {
		return fmt.Sprintf("第%d页知识点", page)
	}
	return weakPointID
}

func fallbackWeakPointTest(weakPointID, questionType string) *weakPointTestPayload {
	if questionType == "multiple" {
		return &weakPointTestPayload{Content: "以下哪些方法可用于处理缺失值？", Options: []string{"A.fillna()", "B.interpolate()", "C.dropna()", "D.duplicated()"}, Answer: "ABC", Explanation: "fillna()、interpolate()、dropna() 都属于常见缺失值处理方法。"}
	}
	switch weakPointID {
	case "wp_002":
		return &weakPointTestPayload{Content: "在 IQR 法中，异常值通常指什么？", Options: []string{"A.超出 Q1-1.5IQR 或 Q3+1.5IQR 的值", "B.所有均值以上的值", "C.所有中位数以下的值", "D.随机出现的值"}, Answer: "A", Explanation: "IQR 法以四分位距为基准识别异常值。"}
	default:
		return &weakPointTestPayload{Content: "处理缺失值时，哪种方法更适合时间序列数据？", Options: []string{"A.fillna(0)", "B.interpolate()", "C.dropna()", "D.sort_values()"}, Answer: "B", Explanation: "时间序列数据通常更适合使用插值法保持变化趋势。"}
	}
}

func fallbackCheckAnswer(questionID, userAnswer string) gin.H {
	correctAnswer := "B"
	explanation := "interpolate() 线性插值更适合时序数据，可以根据前后数据推断缺失值。"
	if strings.Contains(questionID, "002") {
		correctAnswer = "A"
		explanation = "IQR 法中，超出 Q1-1.5IQR 或 Q3+1.5IQR 的值会被视为异常值。"
	}
	isCorrect := strings.EqualFold(strings.TrimSpace(userAnswer), correctAnswer)
	masteryDelta := -5
	if isCorrect {
		masteryDelta = 10
	}
	return gin.H{"isCorrect": isCorrect, "correctAnswer": correctAnswer, "explanation": explanation, "masteryDelta": masteryDelta, "newMastery": 65 + masteryDelta}
}

func maxWeakPointPage(weakPointID string) int {
	if strings.HasPrefix(weakPointID, "wp-page-") {
		page, _ := strconv.Atoi(strings.TrimPrefix(weakPointID, "wp-page-"))
		return page
	}
	return 1
}

func mapQuestionType(questionType string) string {
	if strings.EqualFold(questionType, "multiple") {
		return "多选"
	}
	return "单选"
}
