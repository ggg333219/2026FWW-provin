package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
	"smart-teaching-backend/pkg/apiresp"
	"smart-teaching-backend/pkg/learningevent"
	"smart-teaching-backend/pkg/logger"
)

type StudentHandler struct {
	db       *gorm.DB
	aiClient service.AIEngine
}

func NewStudentHandler(db *gorm.DB, aiClient service.AIEngine) *StudentHandler {
	return &StudentHandler{db: db, aiClient: aiClient}
}

type GetCoursewarePageRequest struct {
	CourseID    string `json:"courseId" binding:"required"`
	CurrentPage int    `json:"currentPage" binding:"required"`
}

type AIQuestionRequest struct {
	StudentID string `json:"studentId"`
	CourseID  string `json:"courseId" binding:"required"`
	PageNum   int    `json:"pageNum" binding:"required"`
	NodeID    string `json:"nodeId"`
	Question  string `json:"question" binding:"required"`
	Type      string `json:"type"`
}

type TraceQuestionRequest struct {
	StudentID string  `json:"studentId"`
	CourseID  string  `json:"courseId" binding:"required"`
	PageNum   int     `json:"pageNum" binding:"required"`
	NodeID    string  `json:"nodeId"`
	X         float64 `json:"x" binding:"required"`
	Y         float64 `json:"y" binding:"required"`
	Question  string  `json:"question" binding:"required"`
}

type UpdateBreakpointRequest struct {
	StudentID string `json:"studentId"`
	UserID    string `json:"userId"`
	CourseID  string `json:"courseId"`
	LastPage  int    `json:"lastPage"`
	PageNum   int    `json:"pageNum"`
}

type SaveNoteRequest struct {
	StudentID string `json:"studentId"`
	UserID    string `json:"userId"`
	CourseID  string `json:"courseId"`
	PageNum   int    `json:"pageNum" binding:"required"`
	Note      string `json:"note"`
	Content   string `json:"content"`
}

func (h *StudentHandler) StartSession(c *gin.Context) {
	var req struct {
		UserID   string `json:"userId" binding:"required"`
		CourseID string `json:"courseId" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", err.Error())
		return
	}
	if err := learningevent.ValidateCourseID(req.CourseID); err != nil {
		apiresp.BadRequest(c, "课件参数不合法", err.Error())
		return
	}
	if strings.TrimSpace(req.UserID) == "" {
		apiresp.BadRequest(c, "参数错误", "userId required")
		return
	}
	if err := learningevent.ValidateUserID(req.UserID); err != nil {
		apiresp.BadRequest(c, "用户参数不合法", err.Error())
		return
	}

	sessionID := uuid.NewString()
	syncDialogueSessionState(h.db, sessionID, req.UserID, req.CourseID, 1, "p1_n1", 0)
	apiresp.OK(c, "请求成功", gin.H{"sessionId": sessionID, "courseId": req.CourseID})
}

func (h *StudentHandler) UpdateProgress(c *gin.Context) {
	var req struct {
		SessionID      string `json:"sessionId"`
		UserID         string `json:"userId"`
		CourseID       string `json:"courseId" binding:"required"`
		Page           int    `json:"page"`
		CurrentPage    int    `json:"currentPage"`
		NodeID         string `json:"nodeId"`
		CurrentNodeID  string `json:"currentNodeId"`
		CurrentTimeSec int    `json:"currentTimeSec"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", err.Error())
		return
	}
	if err := learningevent.ValidateCourseID(req.CourseID); err != nil {
		apiresp.BadRequest(c, "课件参数不合法", err.Error())
		return
	}
	if err := learningevent.ValidateUserID(req.UserID); err != nil {
		apiresp.BadRequest(c, "用户参数不合法", err.Error())
		return
	}
	if err := learningevent.ValidateSessionID(req.SessionID); err != nil {
		apiresp.BadRequest(c, "会话参数不合法", err.Error())
		return
	}
	if err := learningevent.ValidateTimeSec(req.CurrentTimeSec); err != nil {
		apiresp.BadRequest(c, "播放时间参数不合法", err.Error())
		return
	}

	page := req.Page
	if page <= 0 {
		page = req.CurrentPage
	}
	if page <= 0 {
		page = 1
	}
	if err := learningevent.ValidateProgressPage(page); err != nil {
		apiresp.BadRequest(c, "页码不合法", err.Error())
		return
	}
	if strings.TrimSpace(req.UserID) != "" {
		h.saveProgress(req.UserID, req.CourseID, page)
	}

	nodeID := strings.TrimSpace(req.NodeID)
	if nodeID == "" {
		nodeID = strings.TrimSpace(req.CurrentNodeID)
	}
	if nodeID == "" {
		nodeID = fmt.Sprintf("p%d_n1", page)
	}
	if err := learningevent.ValidateNodeID(nodeID); err != nil {
		apiresp.BadRequest(c, "节点参数不合法", err.Error())
		return
	}
	syncDialogueSessionState(h.db, req.SessionID, req.UserID, req.CourseID, page, nodeID, req.CurrentTimeSec)

	apiresp.OK(c, "ok", gin.H{"sessionId": req.SessionID, "page": page, "nodeId": nodeID})
}

func (h *StudentHandler) GetBreakpoint(c *gin.Context) {
	courseID := c.Param("courseId")
	userID := strings.TrimSpace(c.Query("userId"))
	if userID == "" {
		apiresp.BadRequest(c, "缺少参数: userId", "")
		return
	}

	lastPage := h.getLastPage(userID, courseID)
	apiresp.OK(c, "请求成功", gin.H{"lastPageNum": lastPage, "pageNum": lastPage})
}

func (h *StudentHandler) GetStudentBreakpoint(c *gin.Context) {
	courseID := strings.TrimSpace(c.Query("courseId"))
	studentID := strings.TrimSpace(c.Query("studentId"))
	if studentID == "" || courseID == "" {
		apiresp.BadRequest(c, "缺少必填参数: studentId 或 courseId", "")
		return
	}

	lastPage := h.getLastPage(studentID, courseID)
	apiresp.OK(c, "请求成功", gin.H{"lastPageNum": lastPage})
}

func (h *StudentHandler) UpdateBreakpoint(c *gin.Context) {
	h.updateBreakpointCore(c, c.Param("courseId"))
}

func (h *StudentHandler) UpdateStudentBreakpoint(c *gin.Context) {
	var req UpdateBreakpointRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "缺少必填参数: studentId, courseId 或 lastPage", "")
		return
	}

	studentID := defaultStudentID(req.StudentID, req.UserID)
	page := req.LastPage
	if page <= 0 {
		page = req.PageNum
	}
	if page <= 0 {
		page = 1
	}
	if studentID == "" || strings.TrimSpace(req.CourseID) == "" {
		apiresp.BadRequest(c, "缺少必填参数: studentId, courseId 或 lastPage", "")
		return
	}

	h.saveProgress(studentID, req.CourseID, page)
	apiresp.OK(c, "断点更新成功", gin.H{"lastPageNum": page})
}

func (h *StudentHandler) SaveNote(c *gin.Context) {
	h.saveNoteCore(c, c.Param("courseId"))
}

func (h *StudentHandler) SaveStudentNote(c *gin.Context) {
	var req SaveNoteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "缺少必填参数", "")
		return
	}

	studentID := defaultStudentID(req.StudentID, req.UserID)
	content := strings.TrimSpace(req.Content)
	if content == "" {
		content = strings.TrimSpace(req.Note)
	}
	if studentID == "" || strings.TrimSpace(req.CourseID) == "" || content == "" {
		apiresp.BadRequest(c, "缺少必填参数", "")
		return
	}

	note := model.StudentNote{UserID: studentID, CourseID: req.CourseID, PageNum: req.PageNum, Note: content}
	if err := h.db.Create(&note).Error; err != nil {
		logger.Errorf("保存笔记失败: %v", err)
		apiresp.Internal(c, "保存失败", "")
		return
	}

	apiresp.OK(c, "保存成功", gin.H{"status": "saved", "noteId": note.ID})
}

func (h *StudentHandler) GetCoursewarePage(c *gin.Context) {
	if courseID := c.Param("courseId"); courseID != "" {
		h.getCoursewarePageV1(c, courseID)
		return
	}

	var req GetCoursewarePageRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}

	content, title := h.loadPageScript(req.CourseID, req.CurrentPage)
	apiresp.OK(c, "成功", gin.H{"courseId": req.CourseID, "currentPage": req.CurrentPage, "content": content, "title": title})
}

func (h *StudentHandler) GetPlaybackAudio(c *gin.Context) {
	courseID := c.Param("courseId")
	pageNum, err := strconv.Atoi(c.Param("pageNum"))
	if err != nil || pageNum < 1 {
		apiresp.BadRequest(c, "页码必须是数字", "")
		return
	}

	nodes := loadTeachingNodesByPage(h.db, courseID, pageNum)
	audioMeta := buildPlaybackAudioMeta(courseID, pageNum, nodes)
	apiresp.OK(c, "请求成功", audioMeta)
}

func (h *StudentHandler) AskAIQuestion(c *gin.Context) {
	var req AIQuestionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		logger.Errorf("参数错误: %v", err)
		apiresp.BadRequest(c, "缺少必填参数: courseId, pageNum 或 question", "")
		return
	}

	nodeID := resolveStudentNodeID(req.NodeID, req.PageNum)
	resp := h.askQuestionWithFallback(c, req.CourseID, req.PageNum, nodeID, req.Question)
	h.recordQuestion(defaultStudentID(req.StudentID, c.GetString("userId")), req.CourseID, req.PageNum, nodeID, req.Question, resp.Answer)
	apiresp.OK(c, "成功", gin.H{"answer": resp.Answer, "sourcePage": resp.SourcePage, "source_page": resp.SourcePage, "sourceNodeId": nodeID, "source_node_id": nodeID, "sourceExcerpt": resp.SourceExcerpt, "needReteach": resp.Intent.NeedReteach, "followUpSuggestion": resp.FollowUpSuggestion, "aiUnavailable": resp.Fallback})
}

func (h *StudentHandler) TraceAIQuestion(c *gin.Context) {
	var req TraceQuestionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}

	question := fmt.Sprintf("%s（圈选坐标: %.2f, %.2f）", req.Question, req.X, req.Y)
	nodeID := resolveStudentNodeID(req.NodeID, req.PageNum)
	resp := h.askQuestionWithFallback(c, req.CourseID, req.PageNum, nodeID, question)
	h.recordQuestion(defaultStudentID(req.StudentID, c.GetString("userId")), req.CourseID, req.PageNum, nodeID, req.Question, resp.Answer)
	apiresp.OK(c, "成功", gin.H{"answer": resp.Answer, "sourcePage": resp.SourcePage, "source_page": resp.SourcePage, "sourceNodeId": nodeID, "source_node_id": nodeID, "sourceExcerpt": resp.SourceExcerpt})
}

func (h *StudentHandler) QAStream(c *gin.Context) {
	var req struct {
		SessionID string `json:"sessionId"`
		CourseID  string `json:"courseId" binding:"required"`
		Page      int    `json:"page" binding:"required"`
		NodeID    string `json:"nodeId"`
		Question  string `json:"question" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}
	sessionID := strings.TrimSpace(req.SessionID)
	if sessionID == "" {
		sessionID = uuid.NewString()
	}
	userID := strings.TrimSpace(c.GetString("userId"))
	nodeID := defaultStringValue(req.NodeID, fmt.Sprintf("p%d_n1", req.Page))
	historySummary, recentTurns := buildDialogueContext(h.db, sessionID, 4)
	content, _ := h.loadPageScript(req.CourseID, req.Page)
	nodeScopedContext := buildNodeScopedContext(h.db, req.CourseID, req.Page, nodeID)
	if strings.TrimSpace(nodeScopedContext) != "" {
		content = nodeScopedContext
	}
	result := questionReply{SourcePage: req.Page, ResumePage: req.Page}
	if h.aiClient != nil {
		resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{Question: req.Question, CurrentPage: req.Page, Context: content, Mode: "llm", SessionID: sessionID, HistorySummary: historySummary, RecentTurns: recentTurns})
		if err == nil && strings.TrimSpace(resp.Answer) != "" {
			result.Answer = resp.Answer
			result.SourcePage = maxInt(resp.SourcePage, req.Page)
			result.SourceExcerpt = resp.SourceExcerpt
			result.ResumePage = maxInt(resp.ResumePage, req.Page)
			result.ResumeNodeID = resp.ResumeNodeID
			result.ResumeSec = resp.ResumeSec
			result.FollowUpSuggestion = resp.FollowUpSuggestion
			result.Intent.NeedReteach = resp.Intent.NeedReteach
			result.Intent.UnderstandingLevel = resp.Intent.UnderstandingLevel
		} else {
			result = h.askQuestionWithFallback(c, req.CourseID, req.Page, nodeID, req.Question)
		}
	} else {
		result = h.askQuestionWithFallback(c, req.CourseID, req.Page, nodeID, req.Question)
	}
	resumeNodeID := result.ResumeNodeID
	if resumeNodeID == "" {
		resumeNodeID = resolveResumeNodeIDByCourse(h.db, req.CourseID, nodeID, result.ResumePage, result.Intent.NeedReteach)
	}
	resumeSec := result.ResumeSec
	if resumeSec == 0 {
		resumeSec = resolvePlaybackResumeSec(h.db, req.CourseID, result.ResumePage, resumeNodeID)
	}
	appendDialogueTurn(h.db, sessionID, userID, req.CourseID, req.Page, nodeID, req.Question, result.Answer, result.SourcePage, result.Intent.NeedReteach, result.FollowUpSuggestion)
	syncDialogueSessionState(h.db, sessionID, userID, req.CourseID, result.ResumePage, resumeNodeID, resumeSec)
	c.Writer.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
	c.Writer.Header().Set("Cache-Control", "no-cache")
	c.Writer.Header().Set("Connection", "keep-alive")
	c.Writer.Header().Set("Access-Control-Allow-Origin", "*")

	flusher, ok := c.Writer.(http.Flusher)
	if !ok {
		apiresp.Internal(c, "当前连接不支持流式输出", "")
		return
	}

	writeEvent := func(event string, payload any) {
		body, _ := json.Marshal(payload)
		_, _ = fmt.Fprintf(c.Writer, "event: %s\n", event)
		_, _ = fmt.Fprintf(c.Writer, "data: %s\n\n", string(body))
		flusher.Flush()
	}

	parts := strings.Fields(result.Answer)
	if len(parts) == 0 {
		for _, r := range []rune(result.Answer) {
			writeEvent("token", gin.H{"text": string(r)})
		}
	} else {
		for _, part := range parts {
			writeEvent("token", gin.H{"text": part + " "})
		}
	}
	writeEvent("sentence", gin.H{"text": result.Answer})
	writeEvent("final", gin.H{"session_id": sessionID, "need_reteach": result.Intent.NeedReteach, "understanding_level": result.Intent.UnderstandingLevel, "source_page": result.SourcePage, "source_node_id": nodeID, "resume_page": result.ResumePage, "resume_node_id": resumeNodeID, "resume_sec": resumeSec, "follow_up_suggestion": result.FollowUpSuggestion})
	h.recordQuestion(userID, req.CourseID, req.Page, nodeID, req.Question, result.Answer)
}

func (h *StudentHandler) GetStudentStudyData(c *gin.Context) {
	studentID := strings.TrimSpace(c.Query("studentId"))
	courseID := strings.TrimSpace(c.Query("courseId"))
	if studentID == "" || courseID == "" {
		apiresp.BadRequest(c, "缺少必填参数: studentId 或 courseId", "")
		return
	}
	apiresp.OK(c, "请求成功", h.buildStudyStats(studentID, courseID))
}

func (h *StudentHandler) GetPersonalStats(c *gin.Context) {
	courseID := c.Param("courseId")
	studentID := strings.TrimSpace(c.Query("userId"))
	if studentID == "" {
		studentID = strings.TrimSpace(c.Query("studentId"))
	}
	if studentID == "" {
		apiresp.BadRequest(c, "缺少参数: userId", "")
		return
	}
	apiresp.OK(c, "请求成功", h.buildStudyStats(studentID, courseID))
}

func (h *StudentHandler) getCoursewarePageV1(c *gin.Context, courseID string) {
	pageNum, err := strconv.Atoi(c.Param("pageNum"))
	if err != nil || pageNum < 1 {
		apiresp.BadRequest(c, "页码必须是数字", "")
		return
	}

	content, _ := h.loadPageScript(courseID, pageNum)
	teachingNodes := loadTeachingNodesByPage(h.db, courseID, pageNum)
	nodes := buildPlaybackNodesFromTeachingNodes(teachingNodes)
	if len(nodes) == 0 {
		nodes = buildPlaybackNodes(pageNum, content)
	}
	audioMeta := buildPlaybackAudioMeta(courseID, pageNum, teachingNodes)
	pageSummary := content
	if len(teachingNodes) > 0 {
		pageSummary = buildTeachingNodePageSummary(teachingNodes)
	}
	apiresp.OK(c, "请求成功", gin.H{"courseId": courseID, "page": pageNum, "nodes": nodes, "page_summary": pageSummary, "audio_meta": audioMeta, "playback_mode": audioMeta["playback_mode"]})
}

func (h *StudentHandler) updateBreakpointCore(c *gin.Context, courseID string) {
	var req UpdateBreakpointRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}

	studentID := defaultStudentID(req.StudentID, req.UserID)
	page := req.PageNum
	if page <= 0 {
		page = req.LastPage
	}
	if page <= 0 {
		page = 1
	}
	if studentID == "" || courseID == "" {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}

	h.saveProgress(studentID, courseID, page)
	apiresp.OK(c, "ok", gin.H{"lastPageNum": page, "pageNum": page})
}

func (h *StudentHandler) saveNoteCore(c *gin.Context, courseID string) {
	var req SaveNoteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}

	studentID := defaultStudentID(req.StudentID, req.UserID)
	content := strings.TrimSpace(req.Content)
	if content == "" {
		content = strings.TrimSpace(req.Note)
	}
	if studentID == "" || courseID == "" || content == "" {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}

	note := model.StudentNote{UserID: studentID, CourseID: courseID, PageNum: req.PageNum, Note: content}
	if err := h.db.Create(&note).Error; err != nil {
		apiresp.Internal(c, "保存失败", "")
		return
	}
	apiresp.OK(c, "保存成功", gin.H{"noteId": note.ID, "status": "saved"})
}

type questionReply struct {
	Answer             string
	SourcePage         int
	SourceExcerpt      string
	ResumePage         int
	ResumeNodeID       string
	ResumeSec          int
	FollowUpSuggestion string
	Fallback           bool
	Intent             struct {
		NeedReteach        bool
		UnderstandingLevel string
	}
}

func (h *StudentHandler) askQuestionWithFallback(c *gin.Context, courseID string, pageNum int, nodeID string, question string) questionReply {
	content, _ := h.loadPageScript(courseID, pageNum)
	nodeScopedContext := buildNodeScopedContext(h.db, courseID, pageNum, nodeID)
	if strings.TrimSpace(nodeScopedContext) != "" {
		content = nodeScopedContext
	}
	result := questionReply{SourcePage: pageNum, ResumePage: pageNum}
	if h.aiClient != nil {
		resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{Question: question, CurrentPage: pageNum, Context: content, Mode: "llm"})
		if err == nil && strings.TrimSpace(resp.Answer) != "" {
			result.Answer = resp.Answer
			result.SourcePage = maxInt(resp.SourcePage, pageNum)
			result.SourceExcerpt = resp.SourceExcerpt
			result.ResumePage = maxInt(resp.ResumePage, pageNum)
			result.FollowUpSuggestion = resp.FollowUpSuggestion
			result.Fallback = resp.UsedFallback
			result.Intent.NeedReteach = resp.Intent.NeedReteach
			return result
		}
	}

	preview := content
	if len([]rune(preview)) > 80 {
		runes := []rune(preview)
		preview = string(runes[:80]) + "..."
	}
	if strings.TrimSpace(preview) == "" {
		preview = "当前页暂无讲稿内容，可先让教师补充讲稿后再进行精确答疑。"
	}
	result.Answer = fmt.Sprintf("根据当前课件内容，关于“%s”的说明如下：%s", question, preview)
	result.SourceExcerpt = preview
	result.FollowUpSuggestion = "可以继续追问关键概念、公式来源或应用场景。"
	result.Fallback = true
	return result
}

func (h *StudentHandler) loadPageScript(courseID string, pageNum int) (string, string) {
	var course model.Course
	_ = h.db.First(&course, "id = ?", courseID).Error
	var coursePage model.CoursePage
	if err := h.db.Where("course_id = ? AND page_index = ?", courseID, pageNum).First(&coursePage).Error; err == nil {
		if text := pageContextText(coursePage); strings.TrimSpace(text) != "" {
			return text, course.Title
		}
	}
	if text := buildPageContextFromTeachingNodes(loadTeachingNodesByPage(h.db, courseID, pageNum)); strings.TrimSpace(text) != "" {
		return text, course.Title
	}
	return "", course.Title
}

func (h *StudentHandler) recordQuestion(studentID, courseID string, pageNum int, nodeID, question, answer string) {
	studentID = strings.TrimSpace(studentID)
	if studentID == "" || strings.TrimSpace(courseID) == "" || strings.TrimSpace(question) == "" {
		return
	}
	_ = h.db.Create(&model.QuestionLog{UserID: studentID, CourseID: courseID, PageIndex: pageNum, NodeID: strings.TrimSpace(nodeID), Question: question, Answer: answer}).Error
}

func resolveStudentNodeID(rawNodeID string, pageNum int) string {
	nodeID := strings.TrimSpace(rawNodeID)
	if nodeID != "" {
		return nodeID
	}
	return fmt.Sprintf("p%d_n1", pageNum)
}

func (h *StudentHandler) saveProgress(studentID, courseID string, page int) {
	var progress model.UserProgress
	err := h.db.Where("user_id = ? AND course_id = ?", studentID, courseID).First(&progress).Error
	if err == nil {
		_ = h.db.Model(&progress).Update("last_page", page).Error
		return
	}
	_ = h.db.Create(&model.UserProgress{UserID: studentID, CourseID: courseID, LastPage: page}).Error
}

func (h *StudentHandler) getLastPage(studentID, courseID string) int {
	var progress model.UserProgress
	if err := h.db.Where("user_id = ? AND course_id = ?", studentID, courseID).First(&progress).Error; err == nil && progress.LastPage > 0 {
		return progress.LastPage
	}
	return 1
}

func (h *StudentHandler) buildStudyStats(studentID, courseID string) gin.H {
	var totalQuestions int64
	h.db.Model(&model.QuestionLog{}).Where("user_id = ? AND course_id = ?", studentID, courseID).Count(&totalQuestions)
	var noteCount int64
	h.db.Model(&model.StudentNote{}).Where("user_id = ? AND course_id = ?", studentID, courseID).Count(&noteCount)
	weakPoints := buildStudentWeakPoints(h.db, studentID, courseID)
	focusScore := 90
	if totalQuestions > 10 {
		focusScore = 72
	} else if totalQuestions > 5 {
		focusScore = 82
	}

	mastery := gin.H{}
	for _, item := range weakPoints {
		name, _ := item["name"].(string)
		masteryLevel, _ := item["mastery"].(int)
		mastery[name] = masteryLevel
	}

	return gin.H{"studentId": studentID, "courseId": courseID, "focusScore": focusScore, "totalQuestions": totalQuestions, "weakPoints": weakPoints, "noteCount": noteCount, "studyHours": float64(maxInt(int(noteCount), 1)) * 0.5, "mastery": mastery}
}

func buildStudentWeakPoints(db *gorm.DB, studentID, courseID string) []gin.H {
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
		result = append(result, gin.H{"weakPointId": fmt.Sprintf("wp-page-%d", stat.PageIndex), "name": fmt.Sprintf("第%d页知识点", stat.PageIndex), "count": stat.Count, "mastery": mastery, "pageIndex": stat.PageIndex})
	}
	return result
}

func buildPlaybackNodes(page int, content string) []gin.H {
	content = strings.TrimSpace(content)
	if content == "" {
		return []gin.H{}
	}
	parts := strings.FieldsFunc(content, func(r rune) bool {
		return r == '\n' || r == '。' || r == '！' || r == '？'
	})
	nodes := make([]gin.H, 0, len(parts))
	for index, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		nodeType := "explain"
		if index == 0 {
			nodeType = "opening"
		} else if index == len(parts)-1 {
			nodeType = "transition"
		}
		nodes = append(nodes, gin.H{"node_id": fmt.Sprintf("p%d_n%d", page, index+1), "type": nodeType, "text": part})
	}
	return nodes
}

func defaultStudentID(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func defaultStringValue(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}
