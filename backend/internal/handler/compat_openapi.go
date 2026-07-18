package handler

import (
	"fmt"
	"mime/multipart"
	"net/http"
	"net/url"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

func (h *CompatibilityHandler) OpenLessonParse(c *gin.Context) {
	var req struct {
		SchoolID          string `json:"schoolId"`
		UserID            string `json:"userId"`
		CourseID          string `json:"courseId"`
		FileType          string `json:"fileType" binding:"required"`
		FileURL           string `json:"fileUrl" binding:"required"`
		IsExtractKeyPoint bool   `json:"isExtractKeyPoint"`
		Enc               string `json:"enc"`
		Time              string `json:"time"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	title := filepath.Base(req.FileURL)
	if decoded, err := url.QueryUnescape(title); err == nil {
		title = decoded
	}
	course := model.Course{BaseModel: model.BaseModel{ID: strings.TrimSpace(req.CourseID)}, Title: title, FileURL: req.FileURL, FileType: req.FileType}
	if course.ID == "" {
		course.ID = uuid.NewString()
	}
	var existing model.Course
	if err := h.db.First(&existing, "id = ?", course.ID).Error; err == nil {
		existing.Title = course.Title
		existing.FileURL = course.FileURL
		existing.FileType = course.FileType
		_ = h.db.Save(&existing).Error
		course = existing
	} else {
		_ = h.db.Create(&course).Error
	}
	openAPISuccess(c, "课件解析成功", gin.H{"parseId": course.ID, "fileInfo": gin.H{"fileName": title, "fileSize": 0, "pageCount": course.TotalPage}, "structurePreview": gin.H{"chapters": []gin.H{}}, "taskStatus": "processing"})
}

func (h *CompatibilityHandler) OpenGenerateScript(c *gin.Context) {
	var req struct {
		ParseID       string `json:"parseId" binding:"required"`
		TeachingStyle string `json:"teachingStyle"`
		SpeechSpeed   string `json:"speechSpeed"`
		CustomOpening string `json:"customOpening"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	var course model.Course
	if err := h.db.First(&course, "id = ?", req.ParseID).Error; err != nil {
		openAPIError(c, http.StatusNotFound, "解析任务不存在")
		return
	}
	content := req.CustomOpening
	if strings.TrimSpace(content) == "" {
		content = "课程标题：" + course.Title
	}
	script := ""
	teachingNodes := loadTeachingNodesByPage(h.db, req.ParseID, 1)
	if generatedScript, _, usedNodes, err := generateAndStoreTeachingNodeScripts(c.Request.Context(), h.db, h.aiClient, course.Title, "llm", teachingNodes); usedNodes && err == nil {
		script = generatedScript
	} else {
		resp, err := h.aiClient.GenerateScript(c.Request.Context(), service.GenerateScriptRequest{Page: 1, Content: content, CourseName: course.Title, Mode: "llm"})
		if err != nil {
			openAPIError(c, http.StatusInternalServerError, "脚本生成失败")
			return
		}
		script = resp.Script
	}
	sections := buildScriptNodes(1, script)
	openAPISuccess(c, "脚本生成成功", gin.H{"scriptId": "script_" + req.ParseID, "scriptStructure": sections, "editUrl": "/teacher/script/" + req.ParseID + "/1", "audioGenerateUrl": "/api/v1/lesson/generateAudio"})
}

func (h *CompatibilityHandler) OpenGenerateAudio(c *gin.Context) {
	var req struct {
		ScriptID    string   `json:"scriptId" binding:"required"`
		VoiceType   string   `json:"voiceType"`
		AudioFormat string   `json:"audioFormat"`
		Provider    string   `json:"provider"`
		SectionIDs  []string `json:"sectionIds"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	courseID := strings.TrimSpace(strings.TrimPrefix(req.ScriptID, "script_"))
	if courseID == "" {
		openAPIError(c, http.StatusBadRequest, "scriptId 无效")
		return
	}

	audioPackage, err := ensurePlaybackAudioAssets(c.Request.Context(), h.db, h.aiClient, courseID, 1, req.VoiceType, req.AudioFormat, req.Provider)
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	sections, _ := audioPackage["sections"].([]gin.H)
	if len(req.SectionIDs) > 0 {
		filtered := make([]gin.H, 0, len(req.SectionIDs))
		allowed := make(map[string]struct{}, len(req.SectionIDs))
		for _, sectionID := range req.SectionIDs {
			allowed[strings.TrimSpace(sectionID)] = struct{}{}
		}
		for _, section := range sections {
			nodeID, _ := section["node_id"].(string)
			if _, ok := allowed[nodeID]; ok {
				filtered = append(filtered, section)
			}
		}
		sections = filtered
	}

	openAPISuccess(c, "语音合成成功", gin.H{
		"audioId":  audioPackage["audio_id"],
		"audioUrl": audioPackage["audio_url"],
		"audioInfo": gin.H{
			"totalDuration": audioPackage["total_duration_sec"],
			"fileSize":      0,
			"format":        audioPackage["format"],
			"bitRate":       0,
			"provider":      audioPackage["provider"],
			"status":        audioPackage["status"],
			"playbackMode":  audioPackage["playback_mode"],
		},
		"sectionAudios": sections,
	})
}

func (h *CompatibilityHandler) OpenQAInteract(c *gin.Context) {
	var req struct {
		SchoolID         string `json:"schoolId"`
		UserID           string `json:"userId"`
		CourseID         string `json:"courseId" binding:"required"`
		LessonID         string `json:"lessonId"`
		SessionID        string `json:"sessionId"`
		QuestionType     string `json:"questionType"`
		QuestionContent  string `json:"questionContent"`
		Question         string `json:"question"`
		CurrentSectionID string `json:"currentSectionId"`
		HistoryQa        []struct {
			Question  string `json:"question"`
			Answer    string `json:"answer"`
			Timestamp string `json:"timestamp"`
		} `json:"historyQa"`
		Enc              string `json:"enc"`
		Time             string `json:"time"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	question := strings.TrimSpace(req.QuestionContent)
	if question == "" {
		question = strings.TrimSpace(req.Question)
	}
	if question == "" {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	page := parsePageFromNodeID(req.CurrentSectionID)
	if page <= 0 {
		page = 1
	}
	var coursePage model.CoursePage
	contextText := ""
	if err := h.db.Where("course_id = ? AND page_index = ?", req.CourseID, page).First(&coursePage).Error; err == nil {
		contextText = pageContextText(coursePage)
	}
	if strings.TrimSpace(contextText) == "" {
		contextText = buildPageContextFromTeachingNodes(loadTeachingNodesByPage(h.db, req.CourseID, page))
	}
	historyTurns := make([]service.ConversationTurn, 0, len(req.HistoryQa))
	for _, item := range req.HistoryQa {
		if strings.TrimSpace(item.Question) == "" && strings.TrimSpace(item.Answer) == "" {
			continue
		}
		historyTurns = append(historyTurns, service.ConversationTurn{Question: item.Question, Answer: item.Answer})
	}
	resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{Question: question, CurrentPage: page, Context: contextText, Mode: "llm", SessionID: req.SessionID, RecentTurns: historyTurns})
	if err != nil {
		openAPIError(c, http.StatusServiceUnavailable, "问答交互失败")
		return
	}
	relatedSectionID := defaultString(req.CurrentSectionID, fmt.Sprintf("p%d_n1", page))
	openAPISuccess(c, "问答交互成功", gin.H{
		"answerId":          "ans_" + uuid.NewString(),
		"answerContent":     resp.Answer,
		"answerType":        defaultString(req.QuestionType, "text"),
		"relatedKnowledge":  gin.H{"knowledgeId": "know_" + relatedSectionID, "knowledgeName": relatedSectionID, "relatedSectionId": relatedSectionID},
		"suggestions":       []string{resp.FollowUpSuggestion},
		"understandingLevel": UnderstandingLevelOrFallback(resp.Intent.UnderstandingLevel, resp.Intent.NeedReteach),
	})
}

func (h *CompatibilityHandler) OpenVoiceToText(c *gin.Context) {
	var req struct {
		VoiceURL     string `json:"voiceUrl"`
		AudioURL     string `json:"audioUrl"`
		Text         string `json:"text"`
		VoiceDuration int   `json:"voiceDuration"`
		Language     string `json:"language"`
		Enc          string `json:"enc"`
		Time         string `json:"time"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	text := strings.TrimSpace(req.Text)
	if text == "" {
		text = guessTextFromVoiceURL(defaultString(req.VoiceURL, req.AudioURL))
	}
	openAPISuccess(c, "语音识别成功", gin.H{"text": text, "confidence": 0.66, "timestamp": time.Now().Format("2006-01-02 15:04:05"), "language": defaultString(req.Language, "zh-CN")})
}

func (h *CompatibilityHandler) OpenTrackProgress(c *gin.Context) {
	var req struct {
		SchoolID         string  `json:"schoolId"`
		UserID           string  `json:"userId" binding:"required"`
		CourseID         string  `json:"courseId" binding:"required"`
		LessonID         string  `json:"lessonId"`
		CurrentPage      int     `json:"currentPage"`
		CurrentSectionID string  `json:"currentSectionId"`
		ProgressPercent  float64 `json:"progressPercent"`
		LastOperateTime  string  `json:"lastOperateTime"`
		QARecordID       string  `json:"qaRecordId"`
		SessionID        string  `json:"sessionId"`
		Enc              string  `json:"enc"`
		Time             string  `json:"time"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	page := req.CurrentPage
	if page <= 0 {
		page = parsePageFromNodeID(req.CurrentSectionID)
	}
	if page <= 0 {
		page = 1
	}
	state := sessionState{SessionID: defaultString(req.SessionID, uuid.NewString()), UserID: req.UserID, CourseID: req.CourseID, CurrentPage: page, CurrentNodeID: defaultString(req.CurrentSectionID, fmt.Sprintf("p%d_n1", page)), ProgressPercent: req.ProgressPercent, LastOperateTime: defaultString(req.LastOperateTime, time.Now().Format("2006-01-02 15:04:05")), UpdatedAt: time.Now()}
	h.persistSession(state)
	var progress model.UserProgress
	if err := h.db.Where("user_id = ? AND course_id = ?", req.UserID, req.CourseID).First(&progress).Error; err == nil {
		_ = h.db.Model(&progress).Update("last_page", page).Error
	} else {
		_ = h.db.Create(&model.UserProgress{UserID: req.UserID, CourseID: req.CourseID, LastPage: page}).Error
	}
	openAPISuccess(c, "进度记录成功", gin.H{"trackId": state.SessionID, "sessionId": state.SessionID, "currentPage": page, "currentSectionId": state.CurrentNodeID, "totalProgress": req.ProgressPercent, "nextSectionSuggest": nextNodeID(state.CurrentNodeID, page)})
}

func (h *CompatibilityHandler) OpenAdjustProgress(c *gin.Context) {
	var req struct {
		SchoolID           string `json:"schoolId"`
		UserID             string `json:"userId" binding:"required"`
		CourseID           string `json:"courseId"`
		LessonID           string `json:"lessonId" binding:"required"`
		CurrentSectionID   string `json:"currentSectionId"`
		UnderstandingLevel string `json:"understandingLevel"`
		QARecordID         string `json:"qaRecordId"`
		Enc                string `json:"enc"`
		Time               string `json:"time"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	adjustType := "normal"
	supplementContent := gin.H{}
	if strings.EqualFold(req.UnderstandingLevel, "partial") || strings.EqualFold(req.UnderstandingLevel, "low") {
		adjustType = "supplement"
		supplementContent = gin.H{"content": "建议补充讲解当前节点的基础概念与示例。", "duration": 30, "relatedExample": "可结合当前节点的典型例题进行补充说明。"}
	}
	currentSectionID := strings.TrimSpace(req.CurrentSectionID)
	if currentSectionID == "" {
		currentSectionID = "p1_n1"
	}
	nextSectionID := nextNodeID(currentSectionID, parsePageFromNodeID(currentSectionID))
	openAPISuccess(c, "节奏调整成功", gin.H{"adjustPlan": gin.H{"continueSectionId": currentSectionID, "adjustType": adjustType, "supplementContent": supplementContent, "nextSections": []gin.H{{"sectionId": currentSectionID, "adjustedDuration": 75, "isKeyPointStrengthen": adjustType == "supplement"}, {"sectionId": nextSectionID, "adjustedDuration": 40, "isKeyPointStrengthen": false}}}})
}

func guessTextFromVoiceURL(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	if parsed, err := url.Parse(raw); err == nil && parsed.Path != "" {
		raw = parsed.Path
	}
	base := filepath.Base(raw)
	base = strings.TrimSuffix(base, filepath.Ext(base))
	base = strings.TrimSpace(base)
	if base == "" {
		return raw
	}
	return base
}

func (h *CompatibilityHandler) OpenSyncCourse(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	data, err := syncCourseFromPlatform(h.db, req)
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	openAPISuccess(c, "课程同步成功", data)
}

func (h *CompatibilityHandler) OpenSyncUser(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	data, err := syncUserFromPlatform(h.db, req)
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	openAPISuccess(c, "用户同步成功", data)
}

func (h *CompatibilityHandler) OpenPlatformOverview(c *gin.Context) {
	data, err := platformOverview(h.db)
	if err != nil {
		openAPIError(c, http.StatusInternalServerError, "平台总览获取失败")
		return
	}
	openAPISuccess(c, "平台总览获取成功", data)
}

func (h *CompatibilityHandler) OpenPlatformUsers(c *gin.Context) {
	data, err := listPlatformUsers(h.db, platformListOptions{
		Page:       intValue(c.Query("page")),
		PageSize:   intValue(c.Query("pageSize")),
		PlatformID: c.Query("platformId"),
		Role:       c.Query("role"),
		OrgCode:    c.Query("orgCode"),
		Keyword:    c.Query("keyword"),
	})
	if err != nil {
		openAPIError(c, http.StatusInternalServerError, "平台用户列表获取失败")
		return
	}
	openAPISuccess(c, "平台用户列表获取成功", data)
}

func (h *CompatibilityHandler) OpenPlatformCourses(c *gin.Context) {
	data, err := listPlatformCourses(h.db, platformListOptions{
		Page:       intValue(c.Query("page")),
		PageSize:   intValue(c.Query("pageSize")),
		PlatformID: c.Query("platformId"),
		Status:     c.Query("status"),
		OrgCode:    c.Query("orgCode"),
		UserID:     c.Query("teacherId"),
		Keyword:    c.Query("keyword"),
	})
	if err != nil {
		openAPIError(c, http.StatusInternalServerError, "平台课程列表获取失败")
		return
	}
	openAPISuccess(c, "平台课程列表获取成功", data)
}

func (h *CompatibilityHandler) OpenPlatformClasses(c *gin.Context) {
	data, err := listPlatformClasses(h.db, platformListOptions{
		Page:       intValue(c.Query("page")),
		PageSize:   intValue(c.Query("pageSize")),
		PlatformID: c.Query("platformId"),
		Status:     c.Query("status"),
		CourseID:   c.Query("courseId"),
		UserID:     c.Query("teacherId"),
		Keyword:    c.Query("keyword"),
	})
	if err != nil {
		openAPIError(c, http.StatusInternalServerError, "平台班级列表获取失败")
		return
	}
	openAPISuccess(c, "平台班级列表获取成功", data)
}

func (h *CompatibilityHandler) OpenPlatformEnrollments(c *gin.Context) {
	data, err := listPlatformEnrollments(h.db, platformListOptions{
		Page:       intValue(c.Query("page")),
		PageSize:   intValue(c.Query("pageSize")),
		PlatformID: c.Query("platformId"),
		Role:       c.Query("role"),
		Status:     c.Query("status"),
		CourseID:   c.Query("courseId"),
		ClassID:    c.Query("classId"),
		UserID:     c.Query("userId"),
		Keyword:    c.Query("keyword"),
	})
	if err != nil {
		openAPIError(c, http.StatusInternalServerError, "平台选课列表获取失败")
		return
	}
	openAPISuccess(c, "平台选课列表获取成功", data)
}

func (h *CompatibilityHandler) OpenPlatformUserDetail(c *gin.Context) {
	data, err := platformUserDetail(h.db, c.Param("userId"))
	if err != nil {
		openAPIError(c, http.StatusNotFound, "平台用户详情获取失败")
		return
	}
	openAPISuccess(c, "平台用户详情获取成功", data)
}

func (h *CompatibilityHandler) OpenPlatformCourseDetail(c *gin.Context) {
	data, err := platformCourseDetail(h.db, c.Param("courseId"))
	if err != nil {
		openAPIError(c, http.StatusNotFound, "平台课程详情获取失败")
		return
	}
	openAPISuccess(c, "平台课程详情获取成功", data)
}

func (h *CompatibilityHandler) OpenPlatformClassDetail(c *gin.Context) {
	data, err := platformClassDetail(h.db, c.Param("classId"))
	if err != nil {
		openAPIError(c, http.StatusNotFound, "平台班级详情获取失败")
		return
	}
	openAPISuccess(c, "平台班级详情获取成功", data)
}

func (h *CompatibilityHandler) OpenPlatformEnrollmentDetail(c *gin.Context) {
	data, err := platformEnrollmentDetail(h.db, c.Param("enrollmentId"))
	if err != nil {
		openAPIError(c, http.StatusNotFound, "平台选课详情获取失败")
		return
	}
	openAPISuccess(c, "平台选课详情获取成功", data)
}

func (h *CompatibilityHandler) OpenCreatePlatformCourse(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	data, err := createPlatformCourse(h.db, req)
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	openAPISuccess(c, "平台课程创建成功", data)
}

func (h *CompatibilityHandler) OpenUpdatePlatformCourse(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	data, err := updatePlatformCourse(h.db, c.Param("courseId"), req)
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	openAPISuccess(c, "平台课程更新成功", data)
}

func (h *CompatibilityHandler) OpenDeletePlatformCourse(c *gin.Context) {
	data, err := deletePlatformCourse(h.db, c.Param("courseId"))
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	openAPISuccess(c, "平台课程删除成功", data)
}

func (h *CompatibilityHandler) OpenCreatePlatformClass(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	data, err := createPlatformClass(h.db, req)
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	openAPISuccess(c, "平台班级创建成功", data)
}

func (h *CompatibilityHandler) OpenUpdatePlatformClass(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	data, err := updatePlatformClass(h.db, c.Param("classId"), req)
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	openAPISuccess(c, "平台班级更新成功", data)
}

func (h *CompatibilityHandler) OpenDeletePlatformClass(c *gin.Context) {
	data, err := deletePlatformClass(h.db, c.Param("classId"))
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	openAPISuccess(c, "平台班级删除成功", data)
}

func (h *CompatibilityHandler) OpenCreatePlatformEnrollment(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	data, err := createPlatformEnrollment(h.db, req)
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	openAPISuccess(c, "平台选课创建成功", data)
}

func (h *CompatibilityHandler) OpenUpdatePlatformEnrollment(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		openAPIError(c, http.StatusBadRequest, "参数错误")
		return
	}
	data, err := updatePlatformEnrollment(h.db, c.Param("enrollmentId"), req)
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	openAPISuccess(c, "平台选课更新成功", data)
}

func (h *CompatibilityHandler) OpenDeletePlatformEnrollment(c *gin.Context) {
	data, err := deletePlatformEnrollment(h.db, c.Param("enrollmentId"))
	if err != nil {
		openAPIError(c, http.StatusBadRequest, err.Error())
		return
	}
	openAPISuccess(c, "平台选课删除成功", data)
}

func fileHeaderFromMultipart(file *multipart.FileHeader) *multipart.FileHeader {
	return file
}
