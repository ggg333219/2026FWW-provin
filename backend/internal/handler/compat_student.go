package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

type practiceQuestionPayload struct {
	QuestionID        string   `json:"questionId"`
	Content           string   `json:"content"`
	Options           []string `json:"options,omitempty"`
	Answer            string   `json:"answer,omitempty"`
	Explanation       string   `json:"explanation,omitempty"`
	Type              string   `json:"type"`
	Difficulty        int      `json:"difficulty"`
	Score             int      `json:"score"`
	NodeID            string   `json:"nodeId,omitempty"`
	PageNum           int      `json:"pageNum,omitempty"`
	CourseID          string   `json:"courseId,omitempty"`
	KnowledgePointID  string   `json:"knowledgePointId,omitempty"`
	KnowledgePointIDs []string `json:"knowledgePointIds,omitempty"`
	ReferenceAnswer   string   `json:"referenceAnswer,omitempty"`
	SourceType        string   `json:"sourceType,omitempty"`
}

type practiceSubmitAnswer struct {
	QuestionID string `json:"questionId"`
	UserAnswer string `json:"userAnswer"`
}

type practiceAnswerDetail struct {
	QuestionID     string   `json:"questionId"`
	Content        string   `json:"content,omitempty"`
	UserAnswer     string   `json:"userAnswer"`
	CorrectAnswer  string   `json:"correctAnswer,omitempty"`
	IsCorrect      bool     `json:"correct"`
	Score          float64  `json:"score"`
	MaxScore       float64  `json:"maxScore"`
	Explanation    string   `json:"explanation,omitempty"`
	AIComment      string   `json:"aiComment,omitempty"`
	QuestionType   string   `json:"questionType"`
	KnowledgePoint []string `json:"knowledgePoints,omitempty"`
}

type aiScorePayload struct {
	Score             float64  `json:"score"`
	MaxScore          float64  `json:"maxScore"`
	IsCorrect         bool     `json:"isCorrect"`
	Comment           string   `json:"comment"`
	ReferenceAnswer   string   `json:"referenceAnswer"`
	KnowledgePoints   []string `json:"knowledgePoints"`
	MasteryDelta      int      `json:"masteryDelta"`
	ReviewStatus      string   `json:"reviewStatus"`
	Explanation       string   `json:"explanation"`
	NormalizedAnswer  string   `json:"normalizedAnswer"`
	NormalizedCorrect string   `json:"normalizedCorrect"`
}

func (h *CompatibilityHandler) GetStudentCoursewareList(c *gin.Context) {
	teachingCourseID := strings.TrimSpace(c.Query("teachingCourseId"))
	courseClassID := strings.TrimSpace(c.Query("courseClassId"))

	var courses []model.Course
	query := h.db.Order("created_at desc").Where("is_published = ?", true)
	if teachingCourseID != "" {
		query = query.Where("teaching_course_id = ?", teachingCourseID)
	}
	if courseClassID != "" {
		query = query.Where("course_class_id = ?", courseClassID)
	}
	if err := query.Find(&courses).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取课件列表失败"})
		return
	}
	if len(courses) == 0 {
		fallback := h.db.Order("created_at desc")
		if teachingCourseID != "" {
			fallback = fallback.Where("teaching_course_id = ?", teachingCourseID)
		}
		if courseClassID != "" {
			fallback = fallback.Where("course_class_id = ?", courseClassID)
		}
		_ = fallback.Find(&courses).Error
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": courses})
}

func (h *CompatibilityHandler) StartStudentSession(c *gin.Context) {
	var req struct {
		UserID   string `json:"userId" binding:"required"`
		CourseID string `json:"courseId" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	state := sessionState{
		SessionID:     uuid.NewString(),
		UserID:        req.UserID,
		CourseID:      req.CourseID,
		CurrentPage:   1,
		CurrentNodeID: "p1_n1",
		UpdatedAt:     time.Now(),
	}
	h.persistSession(state)
	syncDialogueSessionState(h.db, state.SessionID, req.UserID, req.CourseID, 1, state.CurrentNodeID, 0)
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"sessionId": state.SessionID, "courseId": req.CourseID}})
}

func (h *CompatibilityHandler) UpdateStudentProgress(c *gin.Context) {
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
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	page := req.Page
	if page <= 0 {
		page = req.CurrentPage
	}
	if page <= 0 {
		page = 1
	}
	nodeID := strings.TrimSpace(req.NodeID)
	if nodeID == "" {
		nodeID = strings.TrimSpace(req.CurrentNodeID)
	}
	if nodeID == "" {
		nodeID = fmt.Sprintf("p%d_n1", page)
	}
	state := sessionState{
		SessionID:     req.SessionID,
		UserID:        req.UserID,
		CourseID:      req.CourseID,
		CurrentPage:   page,
		CurrentNodeID: nodeID,
		UpdatedAt:     time.Now(),
	}
	if state.SessionID == "" {
		state.SessionID = uuid.NewString()
	}
	h.persistSession(state)
	syncDialogueSessionState(h.db, state.SessionID, req.UserID, req.CourseID, page, nodeID, req.CurrentTimeSec)

	if strings.TrimSpace(req.UserID) != "" {
		var progress model.UserProgress
		err := h.db.Where("user_id = ? AND course_id = ?", req.UserID, req.CourseID).First(&progress).Error
		if err == nil {
			_ = h.db.Model(&progress).Updates(map[string]any{"last_page": page}).Error
		} else {
			_ = h.db.Create(&model.UserProgress{UserID: req.UserID, CourseID: req.CourseID, LastPage: page}).Error
		}
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "ok", "data": gin.H{"sessionId": state.SessionID, "page": page, "nodeId": nodeID}})
}

func (h *CompatibilityHandler) GetStudentScript(c *gin.Context) {
	courseID := c.Param("courseId")
	pageStr := c.Param("page")
	page, err := strconv.Atoi(pageStr)
	if err != nil || page < 1 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "页码错误"})
		return
	}
	var coursePage model.CoursePage
	_ = h.db.Where("course_id = ? AND page_index = ?", courseID, page).First(&coursePage).Error
	displayText := pageDisplayText(coursePage)
	teachingNodes := loadTeachingNodesByPage(h.db, courseID, page)
	nodes := buildPlaybackNodesFromTeachingNodes(teachingNodes)
	if len(nodes) == 0 {
		nodes = buildScriptNodes(page, displayText)
	}
	audioMeta := buildPlaybackAudioMeta(courseID, page, teachingNodes)
	pageSummary := strings.TrimSpace(displayText)
	if len(teachingNodes) > 0 {
		pageSummary = buildTeachingNodePageSummary(teachingNodes)
	}
	if len(pageSummary) > 80 {
		pageSummary = pageSummary[:80]
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"courseId": courseID, "page": page, "nodes": nodes, "page_summary": pageSummary, "audio_meta": audioMeta, "playback_mode": audioMeta["playback_mode"]}})
}

func (h *CompatibilityHandler) GetStudentPlaybackAudio(c *gin.Context) {
	courseID := c.Param("courseId")
	page, err := strconv.Atoi(c.Param("pageNum"))
	if err != nil || page < 1 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "页码错误"})
		return
	}

	nodes := loadTeachingNodesByPage(h.db, courseID, page)
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": buildPlaybackAudioMeta(courseID, page, nodes)})
}
func (h *CompatibilityHandler) StreamStudentQA(c *gin.Context) {
	var req struct {
		SessionID string `json:"sessionId"`
		CourseID  string `json:"courseId" binding:"required"`
		Page      int    `json:"page" binding:"required"`
		NodeID    string `json:"nodeId"`
		Question  string `json:"question" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	session := h.loadSession(req.SessionID)
	userID := defaultStudentID(func() string {
		if session != nil {
			return session.UserID
		}
		return ""
	}())
	sessionID := strings.TrimSpace(req.SessionID)
	if sessionID == "" && session != nil {
		sessionID = session.SessionID
	}
	if sessionID == "" {
		sessionID = uuid.NewString()
	}
	nodeID := defaultStringValue(req.NodeID, fmt.Sprintf("p%d_n1", req.Page))
	historySummary, recentTurns := buildDialogueContext(h.db, sessionID, 4)
	var coursePage model.CoursePage
	contextText := ""
	if err := h.db.Where("course_id = ? AND page_index = ?", req.CourseID, req.Page).First(&coursePage).Error; err == nil {
		contextText = pageContextText(coursePage)
	}
	nodeScopedContext := buildNodeScopedContext(h.db, req.CourseID, req.Page, nodeID)
	if strings.TrimSpace(nodeScopedContext) != "" {
		contextText = nodeScopedContext
	}
	if strings.TrimSpace(contextText) == "" {
		contextText = buildPageContextFromTeachingNodes(loadTeachingNodesByPage(h.db, req.CourseID, req.Page))
	}
	aiResp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{Question: req.Question, CurrentPage: req.Page, Context: contextText, Mode: "llm", SessionID: sessionID, HistorySummary: historySummary, RecentTurns: recentTurns})
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 503, "message": "AI服务暂不可用"})
		return
	}
	resumePage := maxInt(aiResp.ResumePage, req.Page)
	resumeNodeID := aiResp.ResumeNodeID
	if resumeNodeID == "" {
		resumeNodeID = resolveResumeNodeIDByCourse(h.db, req.CourseID, nodeID, resumePage, aiResp.Intent.NeedReteach)
	}
	resumeSec := aiResp.ResumeSec
	if resumeSec == 0 {
		resumeSec = resolvePlaybackResumeSec(h.db, req.CourseID, resumePage, resumeNodeID)
	}
	appendDialogueTurn(h.db, sessionID, userID, req.CourseID, req.Page, nodeID, req.Question, aiResp.Answer, maxInt(aiResp.SourcePage, req.Page), aiResp.Intent.NeedReteach, aiResp.FollowUpSuggestion)
	if userID != "" {
		_ = h.db.Create(&model.QuestionLog{UserID: userID, CourseID: req.CourseID, PageIndex: req.Page, NodeID: nodeID, Question: req.Question, Answer: aiResp.Answer}).Error
	}
	state := sessionState{SessionID: sessionID, UserID: userID, CourseID: req.CourseID, CurrentPage: resumePage, CurrentNodeID: resumeNodeID, UpdatedAt: time.Now()}
	h.persistSession(state)
	syncDialogueSessionState(h.db, sessionID, userID, req.CourseID, resumePage, resumeNodeID, resumeSec)

	c.Writer.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
	c.Writer.Header().Set("Cache-Control", "no-cache")
	c.Writer.Header().Set("Connection", "keep-alive")
	c.Writer.Header().Set("X-Accel-Buffering", "no")
	flusher, ok := c.Writer.(http.Flusher)
	if !ok {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "当前连接不支持流式输出"})
		return
	}

	writeSSE := func(event string, payload any) {
		body, _ := json.Marshal(payload)
		_, _ = fmt.Fprintf(c.Writer, "event: %s\n", event)
		_, _ = fmt.Fprintf(c.Writer, "data: %s\n\n", string(body))
		flusher.Flush()
	}

	parts := strings.Fields(aiResp.Answer)
	if len(parts) == 0 {
		for _, r := range []rune(aiResp.Answer) {
			writeSSE("token", gin.H{"text": string(r)})
		}
	} else {
		for _, part := range parts {
			writeSSE("token", gin.H{"text": part + " "})
		}
	}
	writeSSE("sentence", gin.H{"text": aiResp.Answer})
	writeSSE("final", gin.H{
		"session_id":           sessionID,
		"need_reteach":         aiResp.Intent.NeedReteach,
		"understanding_level":  aiResp.Intent.UnderstandingLevel,
		"source_page":          maxInt(aiResp.SourcePage, req.Page),
		"source_node_id":       nodeID,
		"resume_page":          resumePage,
		"resume_node_id":       resumeNodeID,
		"resume_sec":           resumeSec,
		"follow_up_suggestion": aiResp.FollowUpSuggestion,
	})
}

func (h *CompatibilityHandler) GetStudentPlaybackAudioV1(c *gin.Context) {
	h.GetStudentPlaybackAudio(c)
}

func weakPointVirtualID(page int) string {
	return fmt.Sprintf("wp-page-%d", page)
}

func parseWeakPointVirtualID(id string) int {
	if strings.HasPrefix(id, "wp-page-") {
		page, _ := strconv.Atoi(strings.TrimPrefix(id, "wp-page-"))
		return page
	}
	return 0
}

func (h *CompatibilityHandler) listWeakPoints(studentID, courseID string) []gin.H {
	type pageStat struct {
		PageIndex int
		Count     int
	}
	var stats []pageStat
	h.db.Table("question_logs").Select("page_index, count(*) as count").Where("user_id = ? AND course_id = ?", studentID, courseID).Group("page_index").Order("count desc").Limit(5).Scan(&stats)
	result := make([]gin.H, 0, len(stats))
	for _, stat := range stats {
		mastery := 100 - stat.Count*12
		if mastery < 0 {
			mastery = 0
		}
		result = append(result, gin.H{"weakPointId": weakPointVirtualID(stat.PageIndex), "name": fmt.Sprintf("第%d页知识点", stat.PageIndex), "count": stat.Count, "mastery": mastery, "pageIndex": stat.PageIndex})
	}
	return result
}

func (h *CompatibilityHandler) GetWeakPointsV1(c *gin.Context) {
	courseID := c.Param("courseId")
	studentID := c.Query("studentId")
	if studentID == "" {
		studentID = c.GetHeader("X-Student-Id")
	}
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": h.listWeakPoints(studentID, courseID)})
}

func (h *CompatibilityHandler) ExplainWeakPointV1(c *gin.Context) {
	weakPointID := c.Param("weakPointId")
	page := parseWeakPointVirtualID(weakPointID)
	name := c.Query("name")
	if name == "" {
		if page > 0 {
			name = fmt.Sprintf("第%d页知识点", page)
		} else {
			name = weakPointID
		}
	}
	resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{Question: "请用教学口吻讲解知识点：" + name, CurrentPage: max(page, 1), Context: name, Mode: "llm"})
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 503, "message": "AI讲解暂不可用"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"weakPointId": weakPointID, "title": name, "content": resp.Answer}})
}

func (h *CompatibilityHandler) GenerateWeakPointTestV1(c *gin.Context) {
	weakPointID := c.Param("weakPointId")
	page := parseWeakPointVirtualID(weakPointID)
	var req struct {
		StudentID     string `json:"studentId"`
		QuestionType  string `json:"questionType"`
		WeakPointName string `json:"weakPointName"`
	}
	_ = c.ShouldBindJSON(&req)
	name := strings.TrimSpace(req.WeakPointName)
	if name == "" {
		if page > 0 {
			name = fmt.Sprintf("第%d页知识点", page)
		} else {
			name = weakPointID
		}
	}
	prompt := fmt.Sprintf("请为薄弱点“%s”生成一道单选题，返回严格JSON：{\"content\":\"题干\",\"options\":[\"A.xxx\",\"B.xxx\",\"C.xxx\",\"D.xxx\"],\"answer\":\"A\",\"explanation\":\"解析\"}", name)
	resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{Question: prompt, CurrentPage: max(page, 1), Context: name, Mode: "llm"})
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 503, "message": "AI习题生成失败"})
		return
	}
	testData, err := parseWeakPointTest(resp.Answer)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "AI习题返回格式异常"})
		return
	}
	optionsJSON, _ := json.Marshal(testData.Options)
	questionRecord := model.Question{
		WeakPointID:  weakPointID,
		CourseID:     "",
		PageNum:      page,
		QuestionType: defaultString(req.QuestionType, "single"),
		SourceType:   "ai",
		Content:      testData.Content,
		Options:      string(optionsJSON),
		Answer:       testData.Answer,
		Explanation:  testData.Explanation,
		Difficulty:   2,
		Score:        100,
	}
	if err := h.db.Create(&questionRecord).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "保存题目失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"questionId": questionRecord.ID, "content": testData.Content, "options": testData.Options, "type": questionRecord.QuestionType}})
}

func (h *CompatibilityHandler) CheckAnswerV1(c *gin.Context) {
	questionID := c.Param("questionId")
	var req struct {
		StudentID  string `json:"studentId" binding:"required"`
		UserAnswer string `json:"userAnswer" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	var question model.Question
	if err := h.db.First(&question, "id = ?", questionID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "题目不存在"})
		return
	}
	scoreResult := h.scoreQuestion(c, question, req.UserAnswer)
	answerRecord := model.AnswerRecord{
		StudentID:       req.StudentID,
		QuestionID:      questionID,
		UserAnswer:      req.UserAnswer,
		IsCorrect:       scoreResult.IsCorrect,
		Score:           scoreResult.Score,
		MaxScore:        scoreResult.MaxScore,
		AIComment:       scoreResult.Comment,
		ReviewStatus:    scoreResult.ReviewStatus,
		KnowledgePoints: mustJSON(scoreResult.KnowledgePoints),
		MasteryDelta:    scoreResult.MasteryDelta,
	}
	_ = h.db.Create(&answerRecord).Error
	h.updateKnowledgeMapFromQuestion(req.StudentID, question, scoreResult.IsCorrect)
	c.JSON(http.StatusOK, gin.H{
		"code": 200,
		"data": gin.H{
			"isCorrect":       scoreResult.IsCorrect,
			"correctAnswer":   blankIfSubjective(question),
			"explanation":     firstNonEmpty(scoreResult.Explanation, question.Explanation),
			"masteryDelta":    scoreResult.MasteryDelta,
			"score":           scoreResult.Score,
			"maxScore":        scoreResult.MaxScore,
			"aiComment":       scoreResult.Comment,
			"reviewStatus":    scoreResult.ReviewStatus,
			"referenceAnswer": scoreResult.ReferenceAnswer,
		},
	})
}

func (h *CompatibilityHandler) GetBreakpointV1(c *gin.Context) {
	courseID := c.Param("courseId")
	studentID := c.Query("studentId")
	if studentID == "" {
		studentID = c.GetHeader("X-Student-Id")
	}
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}
	var progress model.UserProgress
	lastPage := 1
	if err := h.db.Where("user_id = ? AND course_id = ?", studentID, courseID).First(&progress).Error; err == nil && progress.LastPage > 0 {
		lastPage = progress.LastPage
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"courseId": courseID, "pageNum": lastPage}})
}

func (h *CompatibilityHandler) UpdateBreakpointV1(c *gin.Context) {
	courseID := c.Param("courseId")
	var req struct {
		StudentID string `json:"studentId" binding:"required"`
		PageNum   int    `json:"pageNum"`
		LastPage  int    `json:"lastPage"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	page := req.PageNum
	if page <= 0 {
		page = req.LastPage
	}
	if page <= 0 {
		page = 1
	}
	var progress model.UserProgress
	if err := h.db.Where("user_id = ? AND course_id = ?", req.StudentID, courseID).First(&progress).Error; err == nil {
		_ = h.db.Model(&progress).Update("last_page", page).Error
	} else {
		_ = h.db.Create(&model.UserProgress{UserID: req.StudentID, CourseID: courseID, LastPage: page}).Error
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "ok", "data": gin.H{"pageNum": page}})
}

func (h *CompatibilityHandler) SaveNoteV1(c *gin.Context) {
	courseID := c.Param("courseId")
	var req struct {
		StudentID string `json:"studentId" binding:"required"`
		NodeID    string `json:"nodeId"`
		PageNum   int    `json:"pageNum" binding:"required"`
		Content   string `json:"content" binding:"required"`
		X         int    `json:"x"`
		Y         int    `json:"y"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	nodeID := strings.TrimSpace(req.NodeID)
	if nodeID == "" {
		nodeID = fmt.Sprintf("p%d_n1", req.PageNum)
	}
	note := model.StudentNote{UserID: req.StudentID, CourseID: courseID, NodeID: nodeID, PageNum: req.PageNum, Note: req.Content}
	if err := h.db.Create(&note).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "保存失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "保存成功", "data": gin.H{"noteId": note.ID, "nodeId": nodeID}})
}

func (h *CompatibilityHandler) GetStudentNotesV1(c *gin.Context) {
	studentID := strings.TrimSpace(c.Query("studentId"))
	courseID := strings.TrimSpace(c.Query("courseId"))
	pageNum, _ := strconv.Atoi(c.DefaultQuery("pageNum", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("pageSize", "20"))
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}
	if pageNum <= 0 {
		pageNum = 1
	}
	if pageSize <= 0 {
		pageSize = 20
	}
	query := h.db.Model(&model.StudentNote{}).Where("user_id = ?", studentID)
	if courseID != "" {
		query = query.Where("course_id = ?", courseID)
	}
	var total int64
	query.Count(&total)
	notes := []model.StudentNote{}
	query.Order("created_at desc").Offset((pageNum - 1) * pageSize).Limit(pageSize).Find(&notes)
	items := make([]gin.H, 0, len(notes))
	for _, note := range notes {
		items = append(items, normalizeStudentNotePayload(note))
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"items": items, "total": total, "page": pageNum, "pageSize": pageSize, "totalPages": (total + int64(pageSize) - 1) / int64(pageSize)}})
}

func (h *CompatibilityHandler) AddFavoriteV1(c *gin.Context) {
	var req struct {
		StudentID string   `json:"studentId" binding:"required"`
		CourseID  string   `json:"courseId"`
		NodeID    string   `json:"nodeId"`
		PageNum   int      `json:"pageNum"`
		Title     string   `json:"title"`
		Tags      []string `json:"tags"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	if req.StudentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}
	tagsJSON, _ := json.Marshal(req.Tags)
	favorite := model.StudentFavorite{UserID: req.StudentID, CourseID: req.CourseID, NodeID: req.NodeID, PageNum: req.PageNum, Title: req.Title, Tags: string(tagsJSON)}
	existing := model.StudentFavorite{}
	err := h.db.Where("user_id = ? AND course_id = ? AND node_id = ?", req.StudentID, req.CourseID, req.NodeID).First(&existing).Error
	if err == nil {
		if len(req.Tags) > 0 {
			existing.Tags = string(tagsJSON)
			h.db.Save(&existing)
		}
		c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"favoriteId": existing.ID, "message": "已收藏"}})
		return
	}
	if err := h.db.Create(&favorite).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "收藏失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"favoriteId": favorite.ID}})
}

func (h *CompatibilityHandler) GetFavoritesV1(c *gin.Context) {
	studentID := strings.TrimSpace(c.Query("studentId"))
	courseID := strings.TrimSpace(c.Query("courseId"))
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("pageSize", "20"))
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}
	if page <= 0 {
		page = 1
	}
	if pageSize <= 0 {
		pageSize = 20
	}
	query := h.db.Model(&model.StudentFavorite{}).Where("user_id = ?", studentID)
	if courseID != "" {
		query = query.Where("course_id = ?", courseID)
	}
	var total int64
	query.Count(&total)
	items := []model.StudentFavorite{}
	query.Order("created_at desc").Offset((page - 1) * pageSize).Limit(pageSize).Find(&items)
	payloadItems := make([]gin.H, 0, len(items))
	for _, item := range items {
		payloadItems = append(payloadItems, normalizeStudentFavoritePayload(item))
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"items": payloadItems, "total": total, "page": page, "pageSize": pageSize, "totalPages": (total + int64(pageSize) - 1) / int64(pageSize)}})
}

func (h *CompatibilityHandler) DeleteFavoriteV1(c *gin.Context) {
	favoriteID := c.Param("favoriteId")
	studentID := strings.TrimSpace(c.Query("studentId"))
	if favoriteID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少参数"})
		return
	}
	fav := model.StudentFavorite{}
	if err := h.db.First(&fav, "id = ?", favoriteID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "收藏不存在"})
		return
	}
	if studentID != "" && fav.UserID != studentID {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "收藏不存在"})
		return
	}
	if err := h.db.Delete(&fav).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "删除失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "删除成功"})
}

func (h *CompatibilityHandler) GeneratePracticeV1(c *gin.Context) {
	var req struct {
		StudentID  string `json:"studentId" binding:"required"`
		CourseID   string `json:"courseId" binding:"required"`
		NodeID     string `json:"nodeId"`
		PageNum    int    `json:"pageNum"`
		Difficulty int    `json:"difficulty"`
		Count      int    `json:"count"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	if req.Count <= 0 {
		req.Count = 3
	}
	if req.Count > 20 {
		req.Count = 20
	}
	if req.Difficulty <= 0 {
		req.Difficulty = 2
	}
	if req.PageNum <= 0 {
		req.PageNum = 1
	}

	questions := h.buildPracticeQuestions(c, req.StudentID, req.CourseID, req.NodeID, req.PageNum, req.Difficulty, req.Count)
	questionJSON, _ := json.Marshal(questions)
	task := model.PracticeTask{
		TaskID:     "task_" + uuid.NewString(),
		UserID:     req.StudentID,
		CourseID:   req.CourseID,
		NodeID:     req.NodeID,
		PageNum:    req.PageNum,
		Difficulty: req.Difficulty,
		Count:      len(questions),
		Questions:  string(questionJSON),
	}
	if err := h.db.Create(&task).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "生成练习失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"taskId": task.TaskID, "questions": sanitizePracticeQuestions(questions), "questionCount": len(questions)}})
}

func (h *CompatibilityHandler) SubmitPracticeV1(c *gin.Context) {
	var req struct {
		TaskID    string                 `json:"taskId" binding:"required"`
		StudentID string                 `json:"studentId" binding:"required"`
		Answers   []practiceSubmitAnswer `json:"answers" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	var task model.PracticeTask
	if err := h.db.Where("task_id = ? AND user_id = ?", req.TaskID, req.StudentID).First(&task).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "练习任务不存在"})
		return
	}
	existing := model.PracticeAttempt{}
	if err := h.db.Where("task_id = ? AND user_id = ?", req.TaskID, req.StudentID).First(&existing).Error; err == nil {
		c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"attemptId": existing.ID, "score": existing.Score, "correctCount": existing.Correct, "totalCount": existing.Total, "details": existing.Details}})
		return
	}

	questions := make([]practiceQuestionPayload, 0)
	if err := json.Unmarshal([]byte(task.Questions), &questions); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "练习数据损坏"})
		return
	}
	questionMap := make(map[string]practiceQuestionPayload, len(questions))
	for _, q := range questions {
		questionMap[q.QuestionID] = q
	}

	details := make([]practiceAnswerDetail, 0, len(req.Answers))
	correctCount := 0
	totalScore := 0.0
	maxScoreTotal := 0.0
	attemptID := uuid.NewString()

	for _, answer := range req.Answers {
		q, ok := questionMap[answer.QuestionID]
		if !ok {
			continue
		}

		questionModel, _ := h.ensureQuestionRecord(task, q)
		scoreResult := h.scoreQuestion(c, questionModel, answer.UserAnswer)
		maxScoreTotal += scoreResult.MaxScore
		totalScore += scoreResult.Score
		if scoreResult.IsCorrect {
			correctCount++
		}

		detail := practiceAnswerDetail{
			QuestionID:     answer.QuestionID,
			Content:        q.Content,
			UserAnswer:     answer.UserAnswer,
			CorrectAnswer:  blankIfSubjective(questionModel),
			IsCorrect:      scoreResult.IsCorrect,
			Score:          scoreResult.Score,
			MaxScore:       scoreResult.MaxScore,
			Explanation:    firstNonEmpty(scoreResult.Explanation, questionModel.Explanation),
			AIComment:      scoreResult.Comment,
			QuestionType:   questionModel.QuestionType,
			KnowledgePoint: scoreResult.KnowledgePoints,
		}
		details = append(details, detail)

		record := model.AnswerRecord{
			BaseModel:       model.BaseModel{ID: uuid.NewString()},
			StudentID:       req.StudentID,
			QuestionID:      questionModel.ID,
			TaskID:          req.TaskID,
			AttemptID:       attemptID,
			UserAnswer:      answer.UserAnswer,
			IsCorrect:       scoreResult.IsCorrect,
			Score:           scoreResult.Score,
			MaxScore:        scoreResult.MaxScore,
			AIComment:       scoreResult.Comment,
			ReviewStatus:    scoreResult.ReviewStatus,
			KnowledgePoints: mustJSON(scoreResult.KnowledgePoints),
			MasteryDelta:    scoreResult.MasteryDelta,
		}
		_ = h.db.Create(&record).Error
		h.updateKnowledgeMapFromQuestion(req.StudentID, questionModel, scoreResult.IsCorrect)
		h.upsertWeakPoint(req.StudentID, task.CourseID, task.NodeID, q.PageNum, detail, questionModel)
	}

	sort.Slice(details, func(i, j int) bool {
		return details[i].QuestionID < details[j].QuestionID
	})

	totalCount := len(details)
	score := 0
	if maxScoreTotal > 0 {
		score = int(totalScore / maxScoreTotal * 100)
	}
	detailsJSON, _ := json.Marshal(details)
	attempt := model.PracticeAttempt{
		TaskID:  req.TaskID,
		UserID:  req.StudentID,
		Score:   score,
		Correct: correctCount,
		Total:   totalCount,
		Details: string(detailsJSON),
	}
	if err := h.db.Create(&attempt).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "提交失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"attemptId": attempt.ID, "score": score, "correctCount": correctCount, "totalCount": totalCount, "details": details}})
}

func (h *CompatibilityHandler) GetPracticeTaskV1(c *gin.Context) {
	taskID := strings.TrimSpace(c.Param("taskId"))
	studentID := strings.TrimSpace(c.Query("studentId"))
	if taskID == "" || studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 taskId 或 studentId"})
		return
	}

	var task model.PracticeTask
	if err := h.db.Where("task_id = ? AND user_id = ?", taskID, studentID).First(&task).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "练习任务不存在"})
		return
	}

	questions := make([]practiceQuestionPayload, 0)
	if err := json.Unmarshal([]byte(task.Questions), &questions); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "练习数据损坏"})
		return
	}

	payload := gin.H{
		"taskId":        task.TaskID,
		"courseId":      task.CourseID,
		"nodeId":        task.NodeID,
		"pageNum":       task.PageNum,
		"difficulty":    task.Difficulty,
		"questionCount": task.Count,
		"createdAt":     task.CreatedAt,
		"questions":     sanitizePracticeQuestions(questions),
	}

	var attempt model.PracticeAttempt
	if err := h.db.Where("task_id = ? AND user_id = ?", task.TaskID, studentID).First(&attempt).Error; err == nil {
		payload["attempt"] = gin.H{
			"attemptId":    attempt.ID,
			"score":        attempt.Score,
			"correctCount": attempt.Correct,
			"totalCount":   attempt.Total,
			"details":      parsePracticeAttemptDetails(attempt.Details),
			"submittedAt":  attempt.CreatedAt,
		}
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": payload})
}

func (h *CompatibilityHandler) GetPracticeHistoryV1(c *gin.Context) {
	studentID := strings.TrimSpace(c.Query("studentId"))
	courseID := strings.TrimSpace(c.Query("courseId"))
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("pageSize", "20"))
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}
	if page <= 0 {
		page = 1
	}
	if pageSize <= 0 {
		pageSize = 20
	}
	query := h.db.Model(&model.PracticeTask{}).Where("user_id = ?", studentID)
	if courseID != "" {
		query = query.Where("course_id = ?", courseID)
	}
	var total int64
	query.Count(&total)

	var tasks []model.PracticeTask
	if err := query.Order("created_at desc").Offset((page - 1) * pageSize).Limit(pageSize).Find(&tasks).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "查询练习历史失败"})
		return
	}

	items := make([]gin.H, 0, len(tasks))
	for _, task := range tasks {
		var attempt model.PracticeAttempt
		_ = h.db.Where("task_id = ? AND user_id = ?", task.TaskID, studentID).First(&attempt).Error
		attemptPayload := gin.H{
			"attemptId":    attempt.ID,
			"score":        attempt.Score,
			"correctCount": attempt.Correct,
			"totalCount":   attempt.Total,
			"submittedAt":  attempt.CreatedAt,
			"hasAttempt":   attempt.ID != "",
			"details":      parsePracticeAttemptDetails(attempt.Details),
		}
		items = append(items, gin.H{
			"taskId":        task.TaskID,
			"courseId":      task.CourseID,
			"nodeId":        task.NodeID,
			"pageNum":       task.PageNum,
			"difficulty":    task.Difficulty,
			"questionCnt":   task.Count,
			"questionCount": task.Count,
			"status":        ternaryString(attempt.ID != "", "completed", "pending"),
			"createdAt":     task.CreatedAt,
			"attempt":       attemptPayload,
		})
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"items": items, "total": total, "page": page, "pageSize": pageSize}})
}

func (h *CompatibilityHandler) GetWrongQuestionsV1(c *gin.Context) {
	studentID := strings.TrimSpace(c.Query("studentId"))
	courseID := strings.TrimSpace(c.Query("courseId"))
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("pageSize", "20"))
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}
	if page <= 0 {
		page = 1
	}
	if pageSize <= 0 {
		pageSize = 20
	}

	query := h.db.Model(&model.AnswerRecord{}).Where("student_id = ? AND is_correct = ?", studentID, false)
	var total int64
	query.Count(&total)

	var records []model.AnswerRecord
	if err := query.Order("created_at desc").Offset((page - 1) * pageSize).Limit(pageSize).Find(&records).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "查询错题失败"})
		return
	}

	items := make([]gin.H, 0, len(records))
	for _, record := range records {
		var question model.Question
		if err := h.db.First(&question, "id = ?", record.QuestionID).Error; err != nil {
			continue
		}
		if courseID != "" && question.CourseID != courseID {
			continue
		}
		options := parseStringArray(question.Options)
		items = append(items, gin.H{
			"recordId":        record.ID,
			"questionId":      question.ID,
			"taskId":          record.TaskID,
			"courseId":        question.CourseID,
			"nodeId":          question.NodeID,
			"pageNum":         question.PageNum,
			"questionType":    question.QuestionType,
			"content":         question.Content,
			"options":         options,
			"userAnswer":      record.UserAnswer,
			"correctAnswer":   blankIfSubjective(question),
			"explanation":     question.Explanation,
			"score":           record.Score,
			"maxScore":        record.MaxScore,
			"aiComment":       record.AIComment,
			"reviewStatus":    record.ReviewStatus,
			"knowledgePoints": parseStringArray(record.KnowledgePoints),
			"createdAt":       record.CreatedAt,
			"referenceAnswer": question.AIReferenceAnswer,
		})
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"items": items, "total": total, "page": page, "pageSize": pageSize}})
}

func (h *CompatibilityHandler) RetryWrongQuestionV1(c *gin.Context) {
	questionID := c.Param("questionId")
	var req struct {
		StudentID string `json:"studentId" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	var question model.Question
	if err := h.db.First(&question, "id = ?", questionID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "题目不存在"})
		return
	}

	payload := practiceQuestionPayload{
		QuestionID:       question.ID,
		Content:          question.Content,
		Options:          parseStringArray(question.Options),
		Type:             question.QuestionType,
		Difficulty:       question.Difficulty,
		Score:            question.Score,
		NodeID:           question.NodeID,
		PageNum:          question.PageNum,
		CourseID:         question.CourseID,
		KnowledgePointID: question.KnowledgePointID,
		ReferenceAnswer:  question.AIReferenceAnswer,
		SourceType:       "retry",
	}
	taskQuestions := []practiceQuestionPayload{payload}
	taskQuestionsJSON, _ := json.Marshal(taskQuestions)
	task := model.PracticeTask{
		TaskID:     "task_" + uuid.NewString(),
		UserID:     req.StudentID,
		CourseID:   question.CourseID,
		NodeID:     question.NodeID,
		PageNum:    question.PageNum,
		Difficulty: question.Difficulty,
		Count:      1,
		Questions:  string(taskQuestionsJSON),
	}
	if err := h.db.Create(&task).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "生成重做任务失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"taskId": task.TaskID, "questions": sanitizePracticeQuestions(taskQuestions)}})
}

func (h *CompatibilityHandler) ExplainNodeV1(c *gin.Context) {
	nodeID := c.Param("nodeId")
	var req struct {
		CourseID string `json:"courseId" binding:"required"`
		PageNum  int    `json:"pageNum"`
		Question string `json:"question"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	question := req.Question
	if question == "" {
		question = fmt.Sprintf("请讲解节点 %s 的内容", nodeID)
	}
	resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{Question: question, CurrentPage: req.PageNum, Context: fmt.Sprintf("节点ID:%s 课程ID:%s", nodeID, req.CourseID), Mode: "llm"})
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 503, "message": "AI讲解暂不可用"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"nodeId": nodeID, "explanation": resp.Answer, "sourcePage": resp.SourcePage, "sourceExcerpt": resp.SourceExcerpt}})
}

func (h *CompatibilityHandler) GetStudyStatsV1(c *gin.Context) {
	courseID := c.Param("courseId")
	studentID := c.Query("studentId")
	if studentID == "" {
		studentID = c.GetHeader("X-Student-Id")
	}
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}
	var totalQuestions int64
	h.db.Model(&model.QuestionLog{}).Where("user_id = ? AND course_id = ?", studentID, courseID).Count(&totalQuestions)
	weakPoints := h.listWeakPoints(studentID, courseID)
	focusScore := 85
	if totalQuestions > 10 {
		focusScore = 70
	} else if totalQuestions > 5 {
		focusScore = 80
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"studentId": studentID, "courseId": courseID, "focusScore": focusScore, "totalQuestions": totalQuestions, "weakPoints": weakPoints, "noteCount": countStudentNotes(h.db, studentID, courseID)}})
}

func (h *CompatibilityHandler) GetStudentCoursewareListV1(c *gin.Context) {
	h.GetStudentCoursewareList(c)
}

func (h *CompatibilityHandler) StartStudentSessionV1(c *gin.Context) {
	h.StartStudentSession(c)
}

func (h *CompatibilityHandler) UpdateStudentProgressV1(c *gin.Context) {
	h.UpdateStudentProgress(c)
}

func (h *CompatibilityHandler) GetStudentScriptV1(c *gin.Context) {
	courseID := c.Param("courseId")
	pageStr := c.Param("pageNum")
	c.Params = append(filterParams(c.Params, "courseId"), gin.Param{Key: "courseId", Value: courseID})
	c.Params = append(filterParams(c.Params, "page"), gin.Param{Key: "page", Value: pageStr})
	h.GetStudentScript(c)
}

func (h *CompatibilityHandler) StreamStudentQAV1(c *gin.Context) {
	h.StreamStudentQA(c)
}

func (h *CompatibilityHandler) ParseKnowledgeV1(c *gin.Context) {
	NewWeakPointHandler(h.db, h.aiClient).ParseKnowledge(c)
}

func countStudentNotes(db *gorm.DB, studentID, courseID string) int64 {
	var total int64
	db.Model(&model.StudentNote{}).Where("user_id = ? AND course_id = ?", studentID, courseID).Count(&total)
	return total
}

// Review Plan Handlers

func (h *CompatibilityHandler) CreateReviewPlanV1(c *gin.Context) {
	var req struct {
		StudentID   string `json:"studentId" binding:"required"`
		Name        string `json:"name" binding:"required"`
		Description string `json:"description"`
		Frequency   string `json:"frequency" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	frequency, ok := normalizeReviewPlanFrequency(req.Frequency)
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "frequency 仅支持 daily / weekly / monthly"})
		return
	}
	nextReviewDate := calculateNextReviewDate(frequency, time.Now())
	plan := model.ReviewPlan{
		StudentID:      req.StudentID,
		Name:           req.Name,
		Description:    req.Description,
		Frequency:      frequency,
		NextReviewDate: &nextReviewDate,
		Status:         "active",
	}
	tx := h.db.Begin()
	if err := tx.Create(&plan).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建复习计划失败"})
		return
	}
	if err := h.syncReviewPlanReminderTask(tx, &plan); err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建复习计划失败"})
		return
	}
	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建复习计划失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": normalizeReviewPlanPayload(plan)})
}

func (h *CompatibilityHandler) GetReviewPlansV1(c *gin.Context) {
	studentID := c.Query("studentId")
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}
	var plans []model.ReviewPlan
	if err := h.db.Where("student_id = ?", studentID).Order("created_at desc").Find(&plans).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取复习计划失败"})
		return
	}
	payloadPlans := make([]gin.H, 0, len(plans))
	for _, plan := range plans {
		payloadPlans = append(payloadPlans, normalizeReviewPlanPayload(plan))
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": payloadPlans})
}

func (h *CompatibilityHandler) UpdateReviewPlanV1(c *gin.Context) {
	planID := c.Param("planId")
	var req struct {
		Name        string `json:"name"`
		Description string `json:"description"`
		Frequency   string `json:"frequency"`
		Status      string `json:"status"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	var plan model.ReviewPlan
	if err := h.db.First(&plan, "id = ?", planID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "复习计划不存在"})
		return
	}
	previousStatus := plan.Status
	frequencyChanged := false
	if req.Name != "" {
		plan.Name = req.Name
	}
	if req.Description != "" {
		plan.Description = req.Description
	}
	if req.Frequency != "" {
		frequency, ok := normalizeReviewPlanFrequency(req.Frequency)
		if !ok {
			c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "frequency 仅支持 daily / weekly / monthly"})
			return
		}
		frequencyChanged = plan.Frequency != frequency
		plan.Frequency = frequency
	}
	if req.Status != "" {
		plan.Status = req.Status
	}
	if strings.TrimSpace(plan.Status) == "" {
		plan.Status = "active"
	}
	statusBecameActive := !strings.EqualFold(previousStatus, "active") && strings.EqualFold(plan.Status, "active")
	if strings.EqualFold(plan.Status, "active") {
		needsReschedule := frequencyChanged || statusBecameActive || plan.NextReviewDate == nil
		if plan.NextReviewDate != nil && plan.NextReviewDate.Before(time.Now().UTC()) {
			needsReschedule = true
		}
		if needsReschedule {
			nextReviewDate := calculateNextReviewDate(plan.Frequency, time.Now())
			plan.NextReviewDate = &nextReviewDate
		}
	} else {
		plan.NextReviewDate = nil
	}
	tx := h.db.Begin()
	if err := tx.Save(&plan).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "更新复习计划失败"})
		return
	}
	if err := h.syncReviewPlanReminderTask(tx, &plan); err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "更新复习计划失败"})
		return
	}
	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "更新复习计划失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": normalizeReviewPlanPayload(plan)})
}

func (h *CompatibilityHandler) DeleteReviewPlanV1(c *gin.Context) {
	planID := c.Param("planId")
	tx := h.db.Begin()
	if err := h.deleteReviewPlanReminderTasks(tx, planID); err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "删除复习计划失败"})
		return
	}
	if err := tx.Delete(&model.ReviewPlan{}, "id = ?", planID).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "删除复习计划失败"})
		return
	}
	tx.Delete(&model.ReviewPlanItem{}, "review_plan_id = ?", planID)
	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "删除复习计划失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "删除成功"})
}

func (h *CompatibilityHandler) AddReviewPlanItemV1(c *gin.Context) {
	var req struct {
		ReviewPlanID string `json:"reviewPlanId" binding:"required"`
		ItemType     string `json:"itemType" binding:"required"`
		ItemID       string `json:"itemId" binding:"required"`
		Priority     int    `json:"priority"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	item := model.ReviewPlanItem{
		ReviewPlanID: req.ReviewPlanID,
		ItemType:     req.ItemType,
		ItemID:       req.ItemID,
		Priority:     req.Priority,
	}
	if err := h.db.Create(&item).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "添加复习项失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": item})
}

func (h *CompatibilityHandler) GetReviewPlanItemsV1(c *gin.Context) {
	planID := c.Param("planId")
	var items []model.ReviewPlanItem
	if err := h.db.Where("review_plan_id = ?", planID).Order("priority desc, created_at desc").Find(&items).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取复习项失败"})
		return
	}
	payloadItems := make([]gin.H, 0, len(items))
	for _, item := range items {
		payloadItems = append(payloadItems, normalizeReviewPlanItemPayload(item))
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": payloadItems})
}

func (h *CompatibilityHandler) UpdateReviewPlanItemV1(c *gin.Context) {
	itemID := c.Param("itemId")
	var req struct {
		Priority       int        `json:"priority"`
		LastReviewedAt *time.Time `json:"lastReviewedAt"`
		ReviewCount    int        `json:"reviewCount"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	var item model.ReviewPlanItem
	if err := h.db.First(&item, "id = ?", itemID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "复习项不存在"})
		return
	}
	if req.Priority > 0 {
		item.Priority = req.Priority
	}
	if req.LastReviewedAt != nil {
		item.LastReviewedAt = req.LastReviewedAt
		item.ReviewCount = req.ReviewCount
	}
	tx := h.db.Begin()
	if req.LastReviewedAt != nil {
		var plan model.ReviewPlan
		if err := tx.First(&plan, "id = ?", item.ReviewPlanID).Error; err == nil && strings.EqualFold(plan.Status, "active") {
			nextReviewDate := calculateNextReviewDate(plan.Frequency, *req.LastReviewedAt)
			plan.NextReviewDate = &nextReviewDate
			item.NextReviewDate = &nextReviewDate
			if err := tx.Save(&plan).Error; err != nil {
				tx.Rollback()
				c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "更新复习项失败"})
				return
			}
			if err := h.syncReviewPlanReminderTask(tx, &plan); err != nil {
				tx.Rollback()
				c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "更新复习项失败"})
				return
			}
		}
	}
	if err := tx.Save(&item).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "更新复习项失败"})
		return
	}
	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "更新复习项失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": normalizeReviewPlanItemPayload(item)})
}

func (h *CompatibilityHandler) DeleteReviewPlanItemV1(c *gin.Context) {
	itemID := c.Param("itemId")
	if err := h.db.Delete(&model.ReviewPlanItem{}, "id = ?", itemID).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "删除复习项失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "删除成功"})
}

// Delete Student Note
func (h *CompatibilityHandler) DeleteStudentNoteV1(c *gin.Context) {
	noteID := c.Param("noteId")
	studentID := c.Query("studentId")
	if noteID == "" || studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少参数"})
		return
	}
	note := model.StudentNote{}
	if err := h.db.First(&note, "id = ?", noteID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "笔记不存在"})
		return
	}
	if note.UserID != studentID {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "笔记不存在"})
		return
	}
	if err := h.db.Delete(&note).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "删除失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "删除成功"})
}

func normalizeStudentNotePayload(note model.StudentNote) gin.H {
	title := ""
	if note.PageNum > 0 {
		title = fmt.Sprintf("第%d页笔记", note.PageNum)
	}
	return gin.H{
		"id":         note.ID,
		"userId":     note.UserID,
		"user_id":    note.UserID,
		"courseId":   note.CourseID,
		"course_id":  note.CourseID,
		"pageNum":    note.PageNum,
		"page_num":   note.PageNum,
		"note":       note.Note,
		"title":      title,
		"createdAt":  note.CreatedAt,
		"created_at": note.CreatedAt,
		"updatedAt":  note.UpdatedAt,
		"updated_at": note.UpdatedAt,
	}
}

func normalizeStudentFavoritePayload(favorite model.StudentFavorite) gin.H {
	return gin.H{
		"id":         favorite.ID,
		"userId":     favorite.UserID,
		"user_id":    favorite.UserID,
		"courseId":   favorite.CourseID,
		"course_id":  favorite.CourseID,
		"nodeId":     favorite.NodeID,
		"node_id":    favorite.NodeID,
		"pageNum":    favorite.PageNum,
		"page_num":   favorite.PageNum,
		"title":      favorite.Title,
		"tags":       favorite.Tags,
		"createdAt":  favorite.CreatedAt,
		"created_at": favorite.CreatedAt,
		"updatedAt":  favorite.UpdatedAt,
		"updated_at": favorite.UpdatedAt,
	}
}

func normalizeReviewPlanPayload(plan model.ReviewPlan) gin.H {
	return gin.H{
		"id":               plan.ID,
		"studentId":        plan.StudentID,
		"student_id":       plan.StudentID,
		"name":             plan.Name,
		"description":      plan.Description,
		"frequency":        plan.Frequency,
		"status":           plan.Status,
		"nextReviewDate":   plan.NextReviewDate,
		"next_review_date": plan.NextReviewDate,
		"createdAt":        plan.CreatedAt,
		"created_at":       plan.CreatedAt,
		"updatedAt":        plan.UpdatedAt,
		"updated_at":       plan.UpdatedAt,
	}
}

func normalizeReviewPlanItemPayload(item model.ReviewPlanItem) gin.H {
	return gin.H{
		"id":               item.ID,
		"reviewPlanId":     item.ReviewPlanID,
		"review_plan_id":   item.ReviewPlanID,
		"itemType":         item.ItemType,
		"item_type":        item.ItemType,
		"itemId":           item.ItemID,
		"item_id":          item.ItemID,
		"priority":         item.Priority,
		"lastReviewedAt":   item.LastReviewedAt,
		"last_reviewed_at": item.LastReviewedAt,
		"reviewCount":      item.ReviewCount,
		"review_count":     item.ReviewCount,
		"nextReviewDate":   item.NextReviewDate,
		"next_review_date": item.NextReviewDate,
		"createdAt":        item.CreatedAt,
		"created_at":       item.CreatedAt,
		"updatedAt":        item.UpdatedAt,
		"updated_at":       item.UpdatedAt,
	}
}

func normalizeReviewPlanFrequency(frequency string) (string, bool) {
	switch strings.ToLower(strings.TrimSpace(frequency)) {
	case "daily":
		return "daily", true
	case "weekly":
		return "weekly", true
	case "monthly":
		return "monthly", true
	default:
		return "", false
	}
}

func calculateNextReviewDate(frequency string, base time.Time) time.Time {
	base = base.UTC()
	switch strings.ToLower(strings.TrimSpace(frequency)) {
	case "weekly":
		return base.AddDate(0, 0, 7)
	case "monthly":
		return base.AddDate(0, 1, 0)
	default:
		return base.AddDate(0, 0, 1)
	}
}

func reviewPlanTaskQuery(tx *gorm.DB, planID string) *gorm.DB {
	pattern := fmt.Sprintf("%%\"plan_id\":\"%s\"%%", planID)
	altPattern := fmt.Sprintf("%%\"planId\":\"%s\"%%", planID)
	return tx.Where("task_type = ? AND (task_data LIKE ? OR task_data LIKE ?)", "review_plan", pattern, altPattern)
}

func (h *CompatibilityHandler) deleteReviewPlanReminderTasks(tx *gorm.DB, planID string) error {
	return reviewPlanTaskQuery(tx, planID).
		Where("status IN ?", []string{"pending", "queued", "processing", "failed"}).
		Delete(&model.ScheduledTask{}).Error
}

func (h *CompatibilityHandler) syncReviewPlanReminderTask(tx *gorm.DB, plan *model.ReviewPlan) error {
	if plan == nil {
		return nil
	}
	if !strings.EqualFold(plan.Status, "active") || plan.NextReviewDate == nil {
		return h.deleteReviewPlanReminderTasks(tx, plan.ID)
	}

	scheduledAt := plan.NextReviewDate.Add(-time.Hour)
	now := time.Now().UTC()
	if scheduledAt.Before(now) {
		scheduledAt = *plan.NextReviewDate
	}
	if scheduledAt.Before(now) {
		scheduledAt = now.Add(time.Minute)
	}

	taskData := mustJSON(map[string]any{
		"plan_id":    plan.ID,
		"plan_name":  plan.Name,
		"student_id": plan.StudentID,
	})
	description := fmt.Sprintf("复习计划提醒：%s", plan.Name)

	var task model.ScheduledTask
	err := reviewPlanTaskQuery(tx, plan.ID).Order("created_at desc").First(&task).Error
	if err == nil {
		return tx.Model(&model.ScheduledTask{}).Where("id = ?", task.ID).Updates(map[string]any{
			"student_id":    plan.StudentID,
			"task_data":     taskData,
			"description":   description,
			"scheduled_at":  scheduledAt,
			"status":        "pending",
			"priority":      1,
			"max_retries":   3,
			"retry_count":   0,
			"last_attempt":  nil,
			"next_attempt":  nil,
			"error_message": "",
		}).Error
	}
	if err != nil && err != gorm.ErrRecordNotFound {
		return err
	}

	task = model.ScheduledTask{
		TaskType:    "review_plan",
		TaskData:    taskData,
		Description: description,
		ScheduledAt: scheduledAt,
		Status:      "pending",
		Priority:    1,
		MaxRetries:  3,
		StudentID:   plan.StudentID,
	}
	return tx.Create(&task).Error
}

func (h *CompatibilityHandler) updateKnowledgeMapFromQuestion(studentID string, question model.Question, isCorrect bool) {
	studentID = strings.TrimSpace(studentID)
	if studentID == "" {
		return
	}

	knowledgePointID := h.ensureKnowledgePointID(question)
	if knowledgePointID == "" {
		return
	}

	knowledgeMapService := service.NewKnowledgeMapService(h.db)
	_ = knowledgeMapService.UpdateMasteryScore(studentID, knowledgePointID, isCorrect, 10000)
}

func (h *CompatibilityHandler) ensureKnowledgePointID(question model.Question) string {
	explicitID := strings.TrimSpace(question.KnowledgePointID)
	name := h.resolveKnowledgePointName(question)
	content := firstNonEmpty(strings.TrimSpace(question.Explanation), strings.TrimSpace(question.Content))
	courseID := strings.TrimSpace(question.CourseID)

	if explicitID != "" {
		var point model.KnowledgePoint
		err := h.db.First(&point, "id = ?", explicitID).Error
		if err == nil {
			return point.ID
		}
		if err != nil && err != gorm.ErrRecordNotFound {
			return ""
		}

		point = model.KnowledgePoint{
			BaseModel: model.BaseModel{ID: explicitID},
			CourseID:  courseID,
			Name:      firstNonEmpty(name, explicitID),
			Level:     2,
			Content:   content,
		}
		if err := h.db.Create(&point).Error; err == nil {
			return point.ID
		}
	}

	if name == "" {
		return ""
	}

	var point model.KnowledgePoint
	query := h.db.Where("name = ?", name)
	if courseID != "" {
		query = query.Where("course_id = ?", courseID)
	} else {
		query = query.Where("course_id = ''")
	}
	if err := query.Order("created_at desc").First(&point).Error; err == nil {
		return point.ID
	}

	point = model.KnowledgePoint{
		CourseID: courseID,
		Name:     name,
		Level:    2,
		Content:  content,
	}
	if err := h.db.Create(&point).Error; err == nil {
		return point.ID
	}
	return ""
}

func (h *CompatibilityHandler) resolveKnowledgePointName(question model.Question) string {
	if question.WeakPointID != "" {
		var weakPoint model.WeakPoint
		if err := h.db.First(&weakPoint, "id = ?", question.WeakPointID).Error; err == nil && strings.TrimSpace(weakPoint.Name) != "" {
			return strings.TrimSpace(weakPoint.Name)
		}
	}

	if question.NodeID != "" {
		var node model.MindMapNode
		if err := h.db.Where("course_id = ? AND id = ?", question.CourseID, question.NodeID).First(&node).Error; err == nil && strings.TrimSpace(node.Title) != "" {
			return strings.TrimSpace(node.Title)
		}
		return fmt.Sprintf("节点 %s", question.NodeID)
	}

	if question.PageNum > 0 {
		return fmt.Sprintf("第%d页知识点", question.PageNum)
	}

	preview := []rune(strings.TrimSpace(question.Content))
	if len(preview) > 18 {
		preview = preview[:18]
	}
	if len(preview) > 0 {
		return fmt.Sprintf("题目：%s", string(preview))
	}

	return ""
}

func (h *CompatibilityHandler) buildPracticeQuestions(c *gin.Context, studentID, courseID, nodeID string, pageNum, difficulty, count int) []practiceQuestionPayload {
	existing := h.queryQuestionBank(courseID, nodeID, pageNum, difficulty, count)
	if len(existing) > 0 {
		return existing
	}

	questions := h.generatePracticeByAI(c, courseID, nodeID, pageNum, difficulty, count)
	if len(questions) > 0 {
		return questions
	}

	return h.generateFallbackPractice(courseID, nodeID, pageNum, difficulty, count)
}

func (h *CompatibilityHandler) queryQuestionBank(courseID, nodeID string, pageNum, difficulty, count int) []practiceQuestionPayload {
	query := h.db.Model(&model.Question{}).Where("course_id = ?", courseID)
	if nodeID != "" {
		query = query.Where("node_id = ?", nodeID)
	}
	if pageNum > 0 {
		query = query.Where("page_num = ?", pageNum)
	}
	if difficulty > 0 {
		query = query.Where("difficulty <= ?", difficulty+1)
	}
	var questions []model.Question
	if err := query.Order("updated_at desc").Limit(count).Find(&questions).Error; err != nil || len(questions) == 0 {
		return nil
	}
	result := make([]practiceQuestionPayload, 0, len(questions))
	for _, q := range questions {
		result = append(result, practiceQuestionPayload{
			QuestionID:       q.ID,
			Content:          q.Content,
			Options:          parseStringArray(q.Options),
			Answer:           q.Answer,
			Explanation:      q.Explanation,
			Type:             normalizeQuestionType(q.QuestionType),
			Difficulty:       defaultInt(q.Difficulty, difficulty),
			Score:            defaultInt(q.Score, 100),
			NodeID:           q.NodeID,
			PageNum:          q.PageNum,
			CourseID:         q.CourseID,
			KnowledgePointID: q.KnowledgePointID,
			ReferenceAnswer:  q.AIReferenceAnswer,
			SourceType:       firstNonEmpty(q.SourceType, "bank"),
		})
	}
	return result
}

func (h *CompatibilityHandler) generatePracticeByAI(c *gin.Context, courseID, nodeID string, pageNum, difficulty, count int) []practiceQuestionPayload {
	if h.aiClient == nil {
		return nil
	}
	contextText := h.buildPracticeContext(courseID, nodeID, pageNum)
	prompt := fmt.Sprintf("请围绕课程课件内容生成 %d 道练习题，返回严格JSON数组。每个元素结构：{\"content\":\"题干\",\"type\":\"single|multiple|judge|subjective\",\"options\":[\"A.xxx\"],\"answer\":\"标准答案\",\"explanation\":\"解析\",\"score\":100,\"referenceAnswer\":\"主观题参考答案\"}。如果是主观题，options 为空数组。难度为 %d。", count, difficulty)
	resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{
		Question:    prompt,
		CurrentPage: pageNum,
		Context:     contextText,
		Mode:        "llm",
	})
	if err != nil {
		return nil
	}
	parsed := parsePracticeQuestionsFromAI(resp.Answer)
	if len(parsed) == 0 {
		return nil
	}
	result := make([]practiceQuestionPayload, 0, len(parsed))
	for _, item := range parsed {
		record := model.Question{
			CourseID:          courseID,
			NodeID:            nodeID,
			PageNum:           pageNum,
			QuestionType:      normalizeQuestionType(item.Type),
			SourceType:        "ai",
			Content:           item.Content,
			Options:           mustJSON(item.Options),
			Answer:            item.Answer,
			Explanation:       item.Explanation,
			Difficulty:        difficulty,
			Score:             defaultInt(item.Score, 100),
			AIReferenceAnswer: firstNonEmpty(item.ReferenceAnswer, item.Answer),
		}
		if err := h.db.Create(&record).Error; err != nil {
			continue
		}
		result = append(result, practiceQuestionPayload{
			QuestionID:      record.ID,
			Content:         record.Content,
			Options:         item.Options,
			Answer:          record.Answer,
			Explanation:     record.Explanation,
			Type:            record.QuestionType,
			Difficulty:      record.Difficulty,
			Score:           defaultInt(record.Score, 100),
			NodeID:          record.NodeID,
			PageNum:         record.PageNum,
			CourseID:        record.CourseID,
			ReferenceAnswer: record.AIReferenceAnswer,
			SourceType:      record.SourceType,
		})
	}
	return result
}

func (h *CompatibilityHandler) generateFallbackPractice(courseID, nodeID string, pageNum, difficulty, count int) []practiceQuestionPayload {
	result := make([]practiceQuestionPayload, 0, count)
	for i := 1; i <= count; i++ {
		qType := "single"
		options := []string{"A. 核心概念", "B. 无关概念", "C. 错误用法", "D. 干扰项"}
		answer := "A"
		referenceAnswer := ""
		if i == count {
			qType = "subjective"
			options = nil
			answer = "请结合课件内容说明关键概念、使用方式与适用场景。"
			referenceAnswer = answer
		}
		record := model.Question{
			CourseID:          courseID,
			NodeID:            nodeID,
			PageNum:           pageNum,
			QuestionType:      qType,
			SourceType:        "practice",
			Content:           buildFallbackQuestionContent(pageNum, i, qType),
			Options:           mustJSON(options),
			Answer:            answer,
			Explanation:       "建议回看对应课件页内容后再作答。",
			Difficulty:        difficulty,
			Score:             100,
			AIReferenceAnswer: referenceAnswer,
		}
		_ = h.db.Create(&record).Error
		result = append(result, practiceQuestionPayload{
			QuestionID:      firstNonEmpty(record.ID, fmt.Sprintf("temp-%d-%d", time.Now().UnixNano(), i)),
			Content:         record.Content,
			Options:         options,
			Answer:          answer,
			Explanation:     record.Explanation,
			Type:            qType,
			Difficulty:      difficulty,
			Score:           100,
			NodeID:          nodeID,
			PageNum:         pageNum,
			CourseID:        courseID,
			ReferenceAnswer: referenceAnswer,
			SourceType:      "practice",
		})
	}
	return result
}

func (h *CompatibilityHandler) ensureQuestionRecord(task model.PracticeTask, payload practiceQuestionPayload) (model.Question, error) {
	var question model.Question
	if payload.QuestionID != "" {
		if err := h.db.First(&question, "id = ?", payload.QuestionID).Error; err == nil {
			return question, nil
		}
	}
	question = model.Question{
		BaseModel:         model.BaseModel{ID: uuid.NewString()},
		CourseID:          task.CourseID,
		NodeID:            firstNonEmpty(payload.NodeID, task.NodeID),
		PageNum:           defaultInt(payload.PageNum, task.PageNum),
		QuestionType:      normalizeQuestionType(payload.Type),
		SourceType:        firstNonEmpty(payload.SourceType, "practice"),
		Content:           payload.Content,
		Options:           mustJSON(payload.Options),
		Answer:            payload.Answer,
		Explanation:       payload.Explanation,
		Difficulty:        defaultInt(payload.Difficulty, task.Difficulty),
		Score:             defaultInt(payload.Score, 100),
		KnowledgePointID:  payload.KnowledgePointID,
		AIReferenceAnswer: payload.ReferenceAnswer,
	}
	err := h.db.Create(&question).Error
	return question, err
}

func (h *CompatibilityHandler) buildPracticeContext(courseID, nodeID string, pageNum int) string {
	parts := make([]string, 0, 3)
	var page model.CoursePage
	if pageNum > 0 {
		if err := h.db.Where("course_id = ? AND page_index = ?", courseID, pageNum).First(&page).Error; err == nil {
			parts = append(parts, page.ScriptText)
		}
	}
	if nodeID != "" {
		var node model.MindMapNode
		if err := h.db.Where("course_id = ? AND id = ?", courseID, nodeID).First(&node).Error; err == nil {
			parts = append(parts, node.Title+"："+node.Content)
		}
	}
	var points []model.KnowledgePoint
	query := h.db.Where("course_id = ?", courseID)
	if err := query.Order("level asc, created_at asc").Limit(10).Find(&points).Error; err == nil {
		for _, point := range points {
			parts = append(parts, point.Name+"："+point.Content)
		}
	}
	return strings.Join(parts, "\n")
}

func (h *CompatibilityHandler) scoreQuestion(c *gin.Context, question model.Question, userAnswer string) aiScorePayload {
	question.QuestionType = normalizeQuestionType(question.QuestionType)
	if isObjectiveQuestion(question.QuestionType) {
		return scoreObjectiveQuestion(question, userAnswer)
	}
	return h.scoreSubjectiveQuestion(c, question, userAnswer)
}

func scoreObjectiveQuestion(question model.Question, userAnswer string) aiScorePayload {
	correct := normalizeAnswer(question.Answer)
	user := normalizeAnswer(userAnswer)
	isCorrect := false
	switch question.QuestionType {
	case "multiple":
		isCorrect = normalizeMultiAnswer(user) == normalizeMultiAnswer(correct)
	case "judge":
		isCorrect = normalizeJudgeAnswer(user) == normalizeJudgeAnswer(correct)
	default:
		isCorrect = user == correct || strings.HasPrefix(user, correct)
	}
	score := 0.0
	if isCorrect {
		score = float64(defaultInt(question.Score, 100))
	}
	masteryDelta := -5
	comment := "答案不正确，建议回顾对应知识点。"
	if isCorrect {
		masteryDelta = 10
		comment = "回答正确，掌握较好。"
	}
	return aiScorePayload{
		Score:             score,
		MaxScore:          float64(defaultInt(question.Score, 100)),
		IsCorrect:         isCorrect,
		Comment:           comment,
		ReferenceAnswer:   question.Answer,
		KnowledgePoints:   compactStrings([]string{question.KnowledgePointID, question.NodeID}),
		MasteryDelta:      masteryDelta,
		ReviewStatus:      "auto",
		Explanation:       question.Explanation,
		NormalizedAnswer:  user,
		NormalizedCorrect: correct,
	}
}

func (h *CompatibilityHandler) scoreSubjectiveQuestion(c *gin.Context, question model.Question, userAnswer string) aiScorePayload {
	maxScore := float64(defaultInt(question.Score, 100))
	reference := firstNonEmpty(question.AIReferenceAnswer, question.Answer)
	base := fallbackSubjectiveScore(question, userAnswer)
	base.MaxScore = maxScore
	base.ReferenceAnswer = reference
	base.KnowledgePoints = compactStrings([]string{question.KnowledgePointID, question.NodeID})

	if h.aiClient == nil {
		return base
	}

	prompt := fmt.Sprintf("你是判题助手。请对以下主观题进行评分并只返回严格JSON对象：{\"score\":0-100,\"comment\":\"评语\",\"isCorrect\":true/false,\"masteryDelta\":-20到20,\"referenceAnswer\":\"参考答案\"}。题目：%s\n参考答案：%s\n学生答案：%s", question.Content, reference, userAnswer)
	resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{
		Question:    prompt,
		CurrentPage: max(question.PageNum, 1),
		Context:     firstNonEmpty(question.Explanation, question.Content),
		Mode:        "llm",
	})
	if err != nil {
		return base
	}

	type judgeResult struct {
		Score           float64 `json:"score"`
		Comment         string  `json:"comment"`
		IsCorrect       bool    `json:"isCorrect"`
		MasteryDelta    int     `json:"masteryDelta"`
		ReferenceAnswer string  `json:"referenceAnswer"`
	}
	payload := judgeResult{}
	if err := json.Unmarshal([]byte(cleanAIJSON(resp.Answer)), &payload); err != nil {
		return base
	}
	if payload.Score < 0 || payload.Score > maxScore {
		payload.Score = base.Score
	}
	if strings.TrimSpace(payload.Comment) == "" {
		payload.Comment = base.Comment
	}
	if strings.TrimSpace(payload.ReferenceAnswer) == "" {
		payload.ReferenceAnswer = reference
	}
	return aiScorePayload{
		Score:           payload.Score,
		MaxScore:        maxScore,
		IsCorrect:       payload.IsCorrect || payload.Score >= maxScore*0.6,
		Comment:         payload.Comment,
		ReferenceAnswer: payload.ReferenceAnswer,
		KnowledgePoints: base.KnowledgePoints,
		MasteryDelta:    clampInt(payload.MasteryDelta, -20, 20),
		ReviewStatus:    "auto",
		Explanation:     firstNonEmpty(question.Explanation, "主观题已完成智能评分。"),
	}
}

func fallbackSubjectiveScore(question model.Question, userAnswer string) aiScorePayload {
	maxScore := float64(defaultInt(question.Score, 100))
	ref := normalizeFreeText(firstNonEmpty(question.AIReferenceAnswer, question.Answer))
	ans := normalizeFreeText(userAnswer)
	refWords := strings.Fields(ref)
	matchCount := 0
	for _, word := range refWords {
		if word != "" && strings.Contains(ans, word) {
			matchCount++
		}
	}
	score := 0.0
	if len(refWords) > 0 {
		score = float64(matchCount) / float64(len(refWords)) * maxScore
	}
	if score > maxScore {
		score = maxScore
	}
	isCorrect := score >= maxScore*0.6
	masteryDelta := -4
	comment := "答案覆盖不完整，建议结合参考答案补充关键点。"
	if isCorrect {
		masteryDelta = 8
		comment = "答案基本覆盖关键点。"
	}
	return aiScorePayload{
		Score:        score,
		MaxScore:     maxScore,
		IsCorrect:    isCorrect,
		Comment:      comment,
		MasteryDelta: masteryDelta,
		ReviewStatus: "auto",
		Explanation:  firstNonEmpty(question.Explanation, "主观题已按关键点覆盖度进行评分。"),
	}
}

func (h *CompatibilityHandler) upsertWeakPoint(studentID, courseID, nodeID string, pageNum int, detail practiceAnswerDetail, question model.Question) {
	if detail.IsCorrect {
		return
	}
	name := firstNonEmpty(question.KnowledgePointID, nodeID)
	if name == "" {
		name = fmt.Sprintf("第%d页练习题", pageNum)
	}
	description := fmt.Sprintf("题目：%s；最近一次作答：%s", detail.Content, detail.UserAnswer)
	var weak model.WeakPoint
	err := h.db.Where("student_id = ? AND course_id = ? AND name = ?", studentID, courseID, name).First(&weak).Error
	if err == nil {
		newCount := weak.Count + 1
		newMastery := weak.MasteryLevel - 5
		if newMastery < 0 {
			newMastery = 0
		}
		_ = h.db.Model(&weak).Updates(map[string]any{
			"count":         newCount,
			"mastery_level": newMastery,
			"description":   description,
		}).Error
		return
	}
	weak = model.WeakPoint{
		StudentID:    studentID,
		CourseID:     courseID,
		Name:         name,
		Description:  description,
		Count:        1,
		MasteryLevel: 55,
	}
	_ = h.db.Create(&weak).Error
}

func sanitizePracticeQuestions(questions []practiceQuestionPayload) []gin.H {
	items := make([]gin.H, 0, len(questions))
	for _, q := range questions {
		items = append(items, gin.H{
			"questionId":       q.QuestionID,
			"content":          q.Content,
			"options":          q.Options,
			"type":             q.Type,
			"difficulty":       q.Difficulty,
			"score":            q.Score,
			"nodeId":           q.NodeID,
			"pageNum":          q.PageNum,
			"courseId":         q.CourseID,
			"knowledgePointId": q.KnowledgePointID,
			"referenceAnswer":  blankReferenceForObjective(q.Type, q.ReferenceAnswer),
			"sourceType":       q.SourceType,
		})
	}
	return items
}

func parseStringArray(raw string) []string {
	if strings.TrimSpace(raw) == "" {
		return nil
	}
	var arr []string
	if err := json.Unmarshal([]byte(raw), &arr); err == nil {
		return arr
	}
	return nil
}

func parsePracticeQuestionsFromAI(raw string) []practiceQuestionPayload {
	cleaned := cleanAIJSON(raw)
	var items []practiceQuestionPayload
	if err := json.Unmarshal([]byte(cleaned), &items); err == nil && len(items) > 0 {
		return items
	}
	var wrapper struct {
		Questions []practiceQuestionPayload `json:"questions"`
	}
	if err := json.Unmarshal([]byte(cleaned), &wrapper); err == nil && len(wrapper.Questions) > 0 {
		return wrapper.Questions
	}
	return nil
}

// parsePracticeAttemptDetails 解析练习尝试详情
func parsePracticeAttemptDetails(detailsJSON string) map[string]interface{} {
	var details map[string]interface{}
	if detailsJSON == "" {
		return map[string]interface{}{}
	}
	if err := json.Unmarshal([]byte(detailsJSON), &details); err != nil {
		return map[string]interface{}{}
	}
	return details
}

// ternaryString 条件返回字符串
func ternaryString(condition bool, trueVal, falseVal string) string {
	if condition {
		return trueVal
	}
	return falseVal
}

func cleanAIJSON(raw string) string {
	cleaned := strings.TrimSpace(raw)
	if strings.HasPrefix(cleaned, "```json") {
		cleaned = strings.TrimPrefix(cleaned, "```json")
	}
	if strings.HasPrefix(cleaned, "```") {
		cleaned = strings.TrimPrefix(cleaned, "```")
	}
	if strings.HasSuffix(cleaned, "```") {
		cleaned = strings.TrimSuffix(cleaned, "```")
	}
	return strings.TrimSpace(cleaned)
}

func normalizeQuestionType(t string) string {
	switch strings.ToLower(strings.TrimSpace(t)) {
	case "multiple", "multi":
		return "multiple"
	case "judge", "boolean", "tf":
		return "judge"
	case "fill", "blank":
		return "fill"
	case "subjective", "essay", "open":
		return "subjective"
	default:
		return "single"
	}
}

func isObjectiveQuestion(t string) bool {
	switch normalizeQuestionType(t) {
	case "single", "multiple", "judge", "fill":
		return true
	default:
		return false
	}
}

func normalizeAnswer(v string) string {
	return strings.ToUpper(strings.TrimSpace(strings.ReplaceAll(v, " ", "")))
}

func normalizeMultiAnswer(v string) string {
	parts := strings.Split(normalizeAnswer(v), "")
	filtered := make([]string, 0, len(parts))
	for _, part := range parts {
		if part != "" {
			filtered = append(filtered, part)
		}
	}
	sort.Strings(filtered)
	return strings.Join(filtered, "")
}

func normalizeJudgeAnswer(v string) string {
	s := strings.ToLower(strings.TrimSpace(v))
	switch s {
	case "true", "t", "对", "正确", "yes", "y", "1":
		return "true"
	case "false", "f", "错", "错误", "no", "n", "0":
		return "false"
	default:
		return s
	}
}

func normalizeFreeText(v string) string {
	replacer := strings.NewReplacer("，", " ", "。", " ", "；", " ", ";", " ", ",", " ", "\n", " ", "\t", " ")
	return strings.ToLower(strings.TrimSpace(replacer.Replace(v)))
}

func buildFallbackQuestionContent(pageNum, index int, qType string) string {
	if qType == "subjective" {
		return fmt.Sprintf("请概述第%d页第%d个核心知识点，并说明其典型应用场景。", pageNum, index)
	}
	return fmt.Sprintf("关于第%d页第%d个知识点，下列哪项表述最准确？", pageNum, index)
}

func blankIfSubjective(question model.Question) string {
	if isObjectiveQuestion(question.QuestionType) {
		return question.Answer
	}
	return ""
}

func blankReferenceForObjective(questionType, reference string) string {
	if isObjectiveQuestion(questionType) {
		return ""
	}
	return reference
}

func defaultInt(v, fallback int) int {
	if v > 0 {
		return v
	}
	return fallback
}

func clampInt(v, minValue, maxValue int) int {
	if v < minValue {
		return minValue
	}
	if v > maxValue {
		return maxValue
	}
	return v
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func mustJSON(v any) string {
	data, _ := json.Marshal(v)
	return string(data)
}

func compactStrings(values []string) []string {
	result := make([]string, 0, len(values))
	seen := map[string]struct{}{}
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}
