package handler

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
	"smart-teaching-backend/pkg/logger"
)

type TeacherHandler struct {
	db       *gorm.DB
	aiClient service.AIEngine
}

var errInvalidTeachingNodes = errors.New("invalid teaching nodes")

func NewTeacherHandler(db *gorm.DB, aiClient service.AIEngine) *TeacherHandler {
	return &TeacherHandler{db: db, aiClient: aiClient}
}

func (h *TeacherHandler) GetCoursewareList(c *gin.Context) {
	var courses []model.Course
	if err := h.db.Order("created_at desc").Find(&courses).Error; err != nil {
		logger.Errorf("获取课件列表失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取课件列表失败"})
		return
	}

	type courseNodeCountStat struct {
		CourseID string `gorm:"column:course_id"`
		Count    int64  `gorm:"column:count"`
	}

	knowledgePointCountByCourse := map[string]int64{}
	var countStats []courseNodeCountStat
	if err := h.db.Model(&model.TeachingNode{}).
		Select("course_id, count(*) as count").
		Group("course_id").
		Scan(&countStats).Error; err != nil {
		logger.Errorf("统计课件知识点数量失败: %v", err)
	} else {
		for _, stat := range countStats {
			knowledgePointCountByCourse[stat.CourseID] = stat.Count
		}
	}

	data := make([]gin.H, 0, len(courses))
	for _, course := range courses {
		knowledgePointCount := int(knowledgePointCountByCourse[course.ID])
		data = append(data, gin.H{
			"id":                    course.ID,
			"courseId":              course.ID,
			"title":                 course.Title,
			"file_url":              course.FileURL,
			"fileType":              course.FileType,
			"file_type":             course.FileType,
			"total_page":            course.TotalPage,
			"knowledge_point_count": knowledgePointCount,
			"knowledgePointCount":   knowledgePointCount,
			"teaching_course_id":    course.TeachingCourseID,
			"teaching_course_title": course.TeachingCourseTitle,
			"course_class_id":       course.CourseClassID,
			"course_class_name":     course.CourseClassName,
			"is_published":          course.IsPublished,
			"status":                publishStatus(course.IsPublished),
			"createdAt":             course.CreatedAt,
			"created_at":            course.CreatedAt,
		})
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "请求成功", "data": data})
}

func (h *TeacherHandler) GetScript(c *gin.Context) {
	courseID := c.Param("courseId")
	pageNum, err := parsePageParam(c.Param("pageNum"), c.Param("page"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "页码必须是数字"})
		return
	}

	var coursePage model.CoursePage
	if err := h.db.Where("course_id = ? AND page_index = ?", courseID, pageNum).First(&coursePage).Error; err != nil {
		nodes := loadTeachingNodesByPage(h.db, courseID, pageNum)
		c.JSON(http.StatusOK, gin.H{"code": 200, "message": "请求成功", "data": gin.H{"courseId": courseID, "pageNum": pageNum, "page": pageNum, "content": buildPageContextFromTeachingNodes(nodes), "nodes": buildTeacherNodePayload(nodes), "mappingCoverage": buildTeacherNodeCoverage(nodes)}})
		return
	}

	content := strings.TrimSpace(coursePage.ScriptText)
	nodes := loadTeachingNodesByPage(h.db, courseID, pageNum)
	if content == "" {
		content = buildPageContextFromTeachingNodes(nodes)
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "请求成功", "data": gin.H{"courseId": courseID, "pageNum": pageNum, "page": pageNum, "content": content, "nodes": buildTeacherNodePayload(nodes), "mappingCoverage": buildTeacherNodeCoverage(nodes)}})
}

func (h *TeacherHandler) UpdateScript(c *gin.Context) {
	courseID := c.Param("courseId")
	pageNum, err := parsePageParam(c.Param("pageNum"), c.Param("page"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "页码必须是数字"})
		return
	}

	var req struct {
		Content string `json:"content" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	if err := h.upsertScript(courseID, pageNum, req.Content); err != nil {
		logger.Errorf("保存讲稿失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "保存失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "保存成功"})
}

func (h *TeacherHandler) GetTeachingNodes(c *gin.Context) {
	courseID := c.Param("courseId")
	pageNum, err := parsePageParam(c.Param("pageNum"), c.Param("page"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "页码必须是数字"})
		return
	}

	nodes := loadTeachingNodesByPage(h.db, courseID, pageNum)
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "请求成功", "data": gin.H{"courseId": courseID, "pageNum": pageNum, "nodes": buildTeacherNodePayload(nodes), "mappingCoverage": buildTeacherNodeCoverage(nodes)}})
}

func (h *TeacherHandler) UpdateTeachingNodes(c *gin.Context) {
	courseID := c.Param("courseId")
	pageNum, err := parsePageParam(c.Param("pageNum"), c.Param("page"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "页码必须是数字"})
		return
	}

	var req struct {
		Nodes []teacherNodeUpsertRequest `json:"nodes" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	content, savedNodes, err := h.replaceTeachingNodes(courseID, pageNum, req.Nodes)
	if err != nil {
		if errors.Is(err, errInvalidTeachingNodes) {
			c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": err.Error()})
			return
		}
		logger.Errorf("保存节点讲稿失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "节点保存失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "保存成功", "data": gin.H{"courseId": courseID, "pageNum": pageNum, "content": content, "nodes": buildTeacherNodePayload(savedNodes), "mappingCoverage": buildTeacherNodeCoverage(savedNodes)}})
}

func (h *TeacherHandler) SaveScript(c *gin.Context) {
	var req struct {
		CourseID string `json:"courseId" binding:"required"`
		Page     int    `json:"page" binding:"required"`
		Content  string `json:"content" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	if err := h.upsertScript(req.CourseID, req.Page, req.Content); err != nil {
		logger.Errorf("保存讲稿失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "保存失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "保存成功"})
}

func (h *TeacherHandler) AIGenerateScript(c *gin.Context) {
	courseID := c.Param("courseId")
	if courseID == "" {
		courseID = strings.TrimSpace(c.PostForm("courseId"))
	}

	var req struct {
		PageNum    int    `json:"pageNum"`
		Page       int    `json:"page"`
		Mode       string `json:"mode"`
		CourseID   string `json:"courseId"`
		CourseName string `json:"courseName"`
	}
	_ = c.ShouldBindJSON(&req)
	if courseID == "" {
		courseID = req.CourseID
	}
	pageNum := req.PageNum
	if pageNum <= 0 {
		pageNum = req.Page
	}
	if pageNum <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	var course model.Course
	if err := h.db.First(&course, "id = ?", courseID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "课件不存在"})
		return
	}

	courseName := course.Title
	if strings.TrimSpace(req.CourseName) != "" {
		courseName = req.CourseName
	}

	var page model.CoursePage
	contextText := ""
	if err := h.db.Where("course_id = ? AND page_index = ?", courseID, pageNum).First(&page).Error; err == nil {
		contextText = pageContextText(page)
	}
	if strings.TrimSpace(contextText) == "" {
		contextText = fmt.Sprintf("课程：%s，第 %d 页", courseName, pageNum)
	}

	script := ""
	mindmapMarkdown := ""
	teachingNodes := loadTeachingNodesByPage(h.db, courseID, pageNum)
	if h.aiClient != nil {
		if generatedScript, generatedMindmap, usedNodes, err := generateAndStoreTeachingNodeScripts(c.Request.Context(), h.db, h.aiClient, courseName, defaultTeacherMode(req.Mode), teachingNodes); usedNodes && err == nil {
			script = generatedScript
			mindmapMarkdown = generatedMindmap
		} else {
			resp, genErr := h.aiClient.GenerateScript(c.Request.Context(), service.GenerateScriptRequest{Page: pageNum, Content: contextText, CourseName: courseName, Mode: defaultTeacherMode(req.Mode)})
			if genErr == nil && strings.TrimSpace(resp.Script) != "" {
				script = resp.Script
				mindmapMarkdown = resp.MindmapMarkdown
			}
		}
	}
	if strings.TrimSpace(script) == "" {
		script = generateMockScript(courseName, pageNum)
	}

	if err := h.upsertScript(courseID, pageNum, script); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "保存失败"})
		return
	}

	refreshedNodes := loadTeachingNodesByPage(h.db, courseID, pageNum)

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "请求成功", "data": gin.H{"courseId": courseID, "pageNum": pageNum, "page": pageNum, "content": script, "mindmapMarkdown": mindmapMarkdown, "nodes": buildTeacherNodePayload(refreshedNodes), "mappingCoverage": buildTeacherNodeCoverage(refreshedNodes)}})
}

func (h *TeacherHandler) GeneratePageAudio(c *gin.Context) {
	courseID := c.Param("courseId")
	pageNum, err := parsePageParam(c.Param("pageNum"), c.Param("page"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "页码必须是数字"})
		return
	}

	var req struct {
		VoiceType string `json:"voiceType"`
		Format    string `json:"audioFormat"`
		Provider  string `json:"provider"`
	}
	_ = c.ShouldBindJSON(&req)

	payload, err := ensurePlaybackAudioAssets(c.Request.Context(), h.db, h.aiClient, courseID, pageNum, req.VoiceType, req.Format, req.Provider)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "音频元数据已生成", "data": payload})
}

func (h *TeacherHandler) PublishCourseware(c *gin.Context) {
	courseID := c.Param("courseId")
	var req struct {
		CourseID            string `json:"courseId"`
		Scope               string `json:"scope"`
		TeachingCourseID    string `json:"teachingCourseId"`
		TeachingCourseTitle string `json:"teachingCourseTitle"`
		CourseClassID       string `json:"courseClassId"`
		CourseClassName     string `json:"courseClassName"`
	}
	_ = c.ShouldBindJSON(&req)
	if courseID == "" {
		courseID = req.CourseID
	}
	if courseID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 courseId"})
		return
	}

	var course model.Course
	if err := h.db.First(&course, "id = ?", courseID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "课件不存在"})
		return
	}

	scope := strings.TrimSpace(req.Scope)
	if scope == "" {
		scope = "all"
	}
	now := time.Now()
	if err := h.db.Model(&course).Updates(map[string]any{
		"is_published":          true,
		"publish_scope":         scope,
		"published_at":          now,
		"teaching_course_id":    strings.TrimSpace(req.TeachingCourseID),
		"teaching_course_title": strings.TrimSpace(req.TeachingCourseTitle),
		"course_class_id":       strings.TrimSpace(req.CourseClassID),
		"course_class_name":     strings.TrimSpace(req.CourseClassName),
	}).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "发布状态写入失败"})
		return
	}

	logger.Infof("课件发布成功: courseId=%s, scope=%s, title=%s", courseID, scope, course.Title)
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "发布成功", "data": gin.H{"courseId": courseID, "scope": scope, "teachingCourseId": strings.TrimSpace(req.TeachingCourseID), "courseClassId": strings.TrimSpace(req.CourseClassID), "publishedAt": now.Format(time.RFC3339)}})
}

func (h *TeacherHandler) GetStudentStats(c *gin.Context) {
	courseID := c.Param("courseId")
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": h.buildClassStats(courseID)})
}

func (h *TeacherHandler) GetClassStats(c *gin.Context) {
	courseID := c.Param("courseId")
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "请求成功", "data": h.buildClassStats(courseID)})
}

func (h *TeacherHandler) GetQuestionRecords(c *gin.Context) {
	courseID := c.Param("courseId")
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("pageSize", "20"))
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}

	offset := (page - 1) * pageSize
	type questionRecord struct {
		ID          string    `json:"id"`
		UserID      string    `json:"user_id"`
		PageIndex   int       `json:"page_index"`
		NodeID      string    `json:"node_id"`
		NodeTitle   string    `json:"node_title"`
		Question    string    `json:"question"`
		Answer      string    `json:"answer"`
		NeedReteach bool      `json:"need_reteach"`
		CreatedAt   time.Time `json:"created_at"`
	}

	var total int64
	h.db.Model(&model.DialogueTurn{}).Where("course_id = ?", courseID).Count(&total)

	list := make([]questionRecord, 0)
	if total > 0 {
		_ = h.db.Model(&model.DialogueTurn{}).
			Select("id, user_id, page_index, node_id, question, answer, need_reteach, created_at").
			Where("course_id = ?", courseID).
			Order("created_at desc").
			Offset(offset).
			Limit(pageSize).
			Scan(&list).Error
	} else {
		h.db.Model(&model.QuestionLog{}).Where("course_id = ?", courseID).Count(&total)
		_ = h.db.Model(&model.QuestionLog{}).
			Select("id, user_id, page_index, node_id, question, answer, created_at").
			Where("course_id = ?", courseID).
			Order("created_at desc").
			Offset(offset).
			Limit(pageSize).
			Scan(&list).Error
	}

	nodeIDs := make([]string, 0, len(list))
	nodeIDSet := make(map[string]struct{}, len(list))
	for _, item := range list {
		nodeID := strings.TrimSpace(item.NodeID)
		if nodeID == "" {
			continue
		}
		if _, ok := nodeIDSet[nodeID]; ok {
			continue
		}
		nodeIDSet[nodeID] = struct{}{}
		nodeIDs = append(nodeIDs, nodeID)
	}
	if len(nodeIDs) > 0 {
		type nodeBrief struct {
			NodeID string `gorm:"column:node_id"`
			Title  string `gorm:"column:title"`
		}
		briefs := make([]nodeBrief, 0, len(nodeIDs))
		_ = h.db.Model(&model.TeachingNode{}).
			Select("node_id, title").
			Where("course_id = ? AND node_id IN ?", courseID, nodeIDs).
			Scan(&briefs).Error
		titleMap := make(map[string]string, len(briefs))
		for _, item := range briefs {
			titleMap[strings.TrimSpace(item.NodeID)] = strings.TrimSpace(item.Title)
		}
		for i := range list {
			nodeID := strings.TrimSpace(list[i].NodeID)
			if nodeID == "" {
				continue
			}
			list[i].NodeTitle = titleMap[nodeID]
		}
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "请求成功", "data": gin.H{"list": list, "total": total, "page": page, "pageSize": pageSize}})
}

func (h *TeacherHandler) GetCardData(c *gin.Context) {
	courseID := c.Param("courseId")
	var course model.Course
	if err := h.db.First(&course, "id = ?", courseID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "课件不存在"})
		return
	}

	stats := h.buildTeacherPageStats(courseID, course.TotalPage)

	topCandidates := append([]teacherPageStat(nil), stats...)
	sort.Slice(topCandidates, func(i, j int) bool {
		return topCandidates[i].CardIndex > topCandidates[j].CardIndex
	})
	topPages := make([]gin.H, 0, minTeacherInt(5, len(topCandidates)))
	for i := 0; i < minTeacherInt(5, len(topCandidates)); i++ {
		stat := topCandidates[i]
		ratio := stat.CardIndex * 10
		if ratio > 100 {
			ratio = 100
		}
		topPages = append(topPages, gin.H{"page": stat.PageIndex, "value": stat.QuestionCount, "ratio": ratio, "needReteachCount": stat.NeedReteachCount, "sessionCount": stat.SessionCount})
	}

	classStats := h.buildClassStats(courseID)
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "请求成功", "data": gin.H{"pageStats": stats, "topPages": topPages, "totalQuestions": classStats["totalQuestions"], "reteachCount": classStats["reteachCount"], "activeSessions": classStats["activeSessions"]}})
}

func (h *TeacherHandler) upsertScript(courseID string, pageNum int, content string) error {
	return upsertTeacherScriptWithDB(h.db, courseID, pageNum, content)
}

func upsertTeacherScriptWithDB(db *gorm.DB, courseID string, pageNum int, content string) error {
	var coursePage model.CoursePage
	err := db.Where("course_id = ? AND page_index = ?", courseID, pageNum).First(&coursePage).Error
	if err != nil {
		return db.Create(&model.CoursePage{CourseID: courseID, PageIndex: pageNum, ScriptText: content}).Error
	}
	return db.Model(&coursePage).Update("script_text", content).Error
}

func (h *TeacherHandler) buildClassStats(courseID string) gin.H {
	var course model.Course
	_ = h.db.Select("id", "total_page").First(&course, "id = ?", courseID).Error
	stats := h.buildTeacherPageStats(courseID, course.TotalPage)

	type questionFreq struct {
		Page  int `json:"page"`
		Count int `json:"count"`
	}

	questionFreqs := make([]questionFreq, 0, len(stats))
	pageStats := make([]gin.H, 0, len(stats))
	pageStayTime := make([]gin.H, 0, len(stats))
	hotPages := make([]gin.H, 0)
	totalQuestions := 0
	totalReteach := 0
	activeSessions := 0
	for _, item := range stats {
		questionFreqs = append(questionFreqs, questionFreq{Page: item.PageIndex, Count: item.QuestionCount})
		pageStats = append(pageStats, gin.H{
			"page":              item.PageIndex,
			"count":             item.QuestionCount,
			"questionCount":     item.QuestionCount,
			"dialogueCount":     item.DialogueCount,
			"sessionCount":      item.SessionCount,
			"needReteachCount":  item.NeedReteachCount,
			"stayTime":          item.StayTime,
			"cardIndex":         item.CardIndex,
			"avgTurns":          item.AvgTurns,
			"estimatedDuration": item.BaseDuration,
		})
		pageStayTime = append(pageStayTime, gin.H{"page": item.PageIndex, "seconds": item.StayTime})
		totalQuestions += item.QuestionCount
		totalReteach += item.NeedReteachCount
		activeSessions += item.SessionCount
	}

	topCandidates := append([]teacherPageStat(nil), stats...)
	sort.Slice(topCandidates, func(i, j int) bool {
		if topCandidates[i].QuestionCount == topCandidates[j].QuestionCount {
			return topCandidates[i].CardIndex > topCandidates[j].CardIndex
		}
		return topCandidates[i].QuestionCount > topCandidates[j].QuestionCount
	})
	for i := 0; i < minTeacherInt(3, len(topCandidates)); i++ {
		if topCandidates[i].QuestionCount == 0 && topCandidates[i].SessionCount == 0 {
			continue
		}
		hotPages = append(hotPages, gin.H{"page": topCandidates[i].PageIndex, "count": topCandidates[i].QuestionCount, "cardIndex": topCandidates[i].CardIndex})
	}

	questions := h.collectTeacherQuestions(courseID)
	keywords := generateKeywordStats(questions)
	activeUsers := h.countDistinctUsers(courseID)
	nodeStats := h.buildTeacherNodeStats(courseID)
	mappingCoverage := h.buildCourseMappingCoverage(courseID)
	nodeHeatmap := h.buildNodeHeatmap(nodeStats)
	masteryRadar := h.buildMasteryRadar(nodeStats)
	classTrend := h.buildClassTrend(courseID)
	learningInsights := h.buildLearningInsights(courseID, nodeStats)
	avgTurnsPerSession := 0.0
	if activeSessions > 0 {
		avgTurnsPerSession = roundTeacherFloat(float64(totalQuestions) / float64(activeSessions))
	}

	return gin.H{
		"pageStayTime":       pageStayTime,
		"questionFreq":       questionFreqs,
		"wordCloud":          keywords,
		"pageStats":          pageStats,
		"keywords":           keywords,
		"hotPages":           hotPages,
		"totalQuestions":     totalQuestions,
		"totalDialogueTurns": totalQuestions,
		"reteachCount":       totalReteach,
		"activeSessions":     activeSessions,
		"activeUsers":        activeUsers,
		"avgTurnsPerSession": avgTurnsPerSession,
		"nodeStats":          nodeStats,
		"nodeHeatmap":        nodeHeatmap,
		"masteryRadar":       masteryRadar,
		"classTrend":         classTrend,
		"learningInsights":   learningInsights,
		"mappingCoverage":    mappingCoverage,
	}
}

type teacherNodeUpsertRequest struct {
	ID                 string           `json:"id"`
	NodeID             string           `json:"nodeId"`
	Title              string           `json:"title"`
	Summary            string           `json:"summary"`
	SchemaVersion      int              `json:"schemaVersion"`
	ScriptText         string           `json:"scriptText"`
	ReteachScript      string           `json:"reteachScript"`
	TransitionText     string           `json:"transitionText"`
	StructuredMarkdown string           `json:"structuredMarkdown"`
	KnowledgeNodesJSON string           `json:"knowledgeNodesJson"`
	ScriptSegmentsJSON string           `json:"scriptSegmentsJson"`
	KnowledgeNodes     []map[string]any `json:"knowledgeNodes"`
	ScriptSegments     []map[string]any `json:"scriptSegments"`
	EstimatedDuration  int              `json:"estimatedDuration"`
	SortOrder          int              `json:"sortOrder"`
}

type teacherPageStat struct {
	PageIndex        int     `json:"page"`
	QuestionCount    int     `json:"questionCount"`
	DialogueCount    int     `json:"dialogueCount"`
	NeedReteachCount int     `json:"needReteachCount"`
	SessionCount     int     `json:"sessionCount"`
	BaseDuration     int     `json:"estimatedDuration"`
	StayTime         float64 `json:"stayTime"`
	CardIndex        float64 `json:"cardIndex"`
	AvgTurns         float64 `json:"avgTurns"`
}

type teacherQuestionStat struct {
	PageIndex     int `gorm:"column:page_index"`
	QuestionCount int `gorm:"column:question_count"`
}

type teacherDialogueStat struct {
	PageIndex        int `gorm:"column:page_index"`
	DialogueCount    int `gorm:"column:dialogue_count"`
	NeedReteachCount int `gorm:"column:need_reteach_count"`
	SessionCount     int `gorm:"column:session_count"`
}

type teacherDurationStat struct {
	PageIndex    int `gorm:"column:page_index"`
	BaseDuration int `gorm:"column:base_duration"`
}

type teacherNodeAggStat struct {
	NodeID           string `gorm:"column:node_id"`
	DialogueCount    int    `gorm:"column:dialogue_count"`
	NeedReteachCount int    `gorm:"column:need_reteach_count"`
	SessionCount     int    `gorm:"column:session_count"`
}

type teacherNodeQuestionAggStat struct {
	NodeID        string `gorm:"column:node_id"`
	QuestionCount int    `gorm:"column:question_count"`
}

type teacherNodeDurationAggStat struct {
	NodeID       string `gorm:"column:node_id"`
	BaseDuration int    `gorm:"column:base_duration"`
}

type teacherTrendAggStat struct {
	Day          string `gorm:"column:day"`
	Count        int    `gorm:"column:count"`
	ReteachCount int    `gorm:"column:reteach_count"`
	UserCount    int    `gorm:"column:user_count"`
}

type teacherNodePriority struct {
	NodeID      string
	Title       string
	Page        int
	Score       float64
	ErrorRate   float64
	Dialogue    int
	NeedReteach int
}

func (h *TeacherHandler) buildTeacherNodeStats(courseID string) []gin.H {
	var nodes []model.TeachingNode
	_ = h.db.Select("node_id", "title", "page_index").Where("course_id = ?", courseID).Find(&nodes).Error

	titleByNodeID := make(map[string]string, len(nodes))
	pageByNodeID := make(map[string]int, len(nodes))
	for _, node := range nodes {
		nodeID := strings.TrimSpace(node.NodeID)
		if nodeID == "" {
			continue
		}
		titleByNodeID[nodeID] = strings.TrimSpace(node.Title)
		pageByNodeID[nodeID] = node.PageIndex
	}

	var agg []teacherNodeAggStat
	_ = h.db.Table("dialogue_turns").
		Select("node_id, count(*) as dialogue_count, sum(case when need_reteach then 1 else 0 end) as need_reteach_count, count(distinct session_id) as session_count").
		Where("course_id = ? AND node_id <> ''", courseID).
		Group("node_id").
		Order("dialogue_count desc").
		Limit(100).
		Scan(&agg).Error

	questionAgg := make([]teacherNodeQuestionAggStat, 0)
	_ = h.db.Table("question_logs").
		Select("node_id, count(*) as question_count").
		Where("course_id = ? AND node_id <> ''", courseID).
		Group("node_id").
		Scan(&questionAgg).Error

	questionByNode := make(map[string]int, len(questionAgg))
	for _, item := range questionAgg {
		nodeID := strings.TrimSpace(item.NodeID)
		if nodeID == "" {
			continue
		}
		questionByNode[nodeID] = item.QuestionCount
	}

	statByNode := make(map[string]teacherNodeAggStat, len(agg))
	for _, item := range agg {
		nodeID := strings.TrimSpace(item.NodeID)
		if nodeID == "" {
			continue
		}
		statByNode[nodeID] = item
	}
	for nodeID, questionCount := range questionByNode {
		if stat, ok := statByNode[nodeID]; ok {
			stat.DialogueCount = maxInt(stat.DialogueCount, questionCount)
			statByNode[nodeID] = stat
			continue
		}
		statByNode[nodeID] = teacherNodeAggStat{NodeID: nodeID, DialogueCount: questionCount, NeedReteachCount: 0, SessionCount: 0}
	}

	durationAgg := make([]teacherNodeDurationAggStat, 0)
	_ = h.db.Table("teaching_nodes").
		Select("node_id, coalesce(max(case when estimated_duration > 0 then estimated_duration else 0 end), 0) as base_duration").
		Where("course_id = ? AND node_id <> ''", courseID).
		Group("node_id").
		Scan(&durationAgg).Error
	durationByNode := make(map[string]int, len(durationAgg))
	for _, item := range durationAgg {
		nodeID := strings.TrimSpace(item.NodeID)
		if nodeID == "" {
			continue
		}
		durationByNode[nodeID] = item.BaseDuration
	}

	result := make([]gin.H, 0, len(statByNode))
	for _, item := range statByNode {
		nodeID := strings.TrimSpace(item.NodeID)
		if nodeID == "" {
			continue
		}
		title := titleByNodeID[nodeID]
		if title == "" {
			title = nodeID
		}
		baseDuration := durationByNode[nodeID]
		if baseDuration <= 0 {
			baseDuration = 30
		}
		dialogueCount := item.DialogueCount
		if dialogueCount <= 0 {
			dialogueCount = questionByNode[nodeID]
		}
		errorRate := 0.0
		if dialogueCount > 0 {
			errorRate = float64(item.NeedReteachCount) / float64(dialogueCount)
		}
		stayTime := float64(baseDuration) + float64(questionByNode[nodeID])*14 + float64(item.DialogueCount)*11 + float64(item.NeedReteachCount)*24
		confidencePenalty := float64(questionByNode[nodeID]) / float64(maxInt(1, questionByNode[nodeID]+item.DialogueCount))
		mastery := (1 - errorRate*0.75 - confidencePenalty*0.25) * 100
		if mastery < 0 {
			mastery = 0
		}
		if mastery > 100 {
			mastery = 100
		}
		result = append(result, gin.H{
			"nodeId":            nodeID,
			"title":             title,
			"page":              pageByNodeID[nodeID],
			"dialogueCount":     item.DialogueCount,
			"questionCount":     questionByNode[nodeID],
			"needReteachCount":  item.NeedReteachCount,
			"sessionCount":      item.SessionCount,
			"errorRate":         roundTeacherFloat(errorRate),
			"stayTime":          roundTeacherFloat(stayTime),
			"masteryScore":      roundTeacherFloat(mastery),
			"estimatedDuration": baseDuration,
		})
	}

	sort.Slice(result, func(i, j int) bool {
		left := maxInt(result[i]["dialogueCount"].(int), result[i]["questionCount"].(int))
		right := maxInt(result[j]["dialogueCount"].(int), result[j]["questionCount"].(int))
		if left == right {
			return result[i]["needReteachCount"].(int) > result[j]["needReteachCount"].(int)
		}
		return left > right
	})
	if len(result) > 50 {
		result = result[:50]
	}

	return result
}

func (h *TeacherHandler) buildCourseMappingCoverage(courseID string) gin.H {
	var nodes []model.TeachingNode
	_ = h.db.Select("node_id", "script_segments_json").Where("course_id = ?", courseID).Find(&nodes).Error
	return buildTeacherNodeCoverage(nodes)
}

func (h *TeacherHandler) replaceTeachingNodes(courseID string, pageNum int, rawNodes []teacherNodeUpsertRequest) (string, []model.TeachingNode, error) {
	trimmed := make([]teacherNodeUpsertRequest, 0, len(rawNodes))
	for index, node := range rawNodes {
		text := strings.TrimSpace(node.ScriptText)
		title := strings.TrimSpace(node.Title)
		summary := strings.TrimSpace(node.Summary)
		if text == "" && title == "" && summary == "" {
			continue
		}
		node.SortOrder = index + 1
		node.ScriptText = text
		node.Title = title
		node.Summary = summary
		node.StructuredMarkdown = strings.TrimSpace(node.StructuredMarkdown)
		node.KnowledgeNodesJSON = strings.TrimSpace(node.KnowledgeNodesJSON)
		node.ScriptSegmentsJSON = strings.TrimSpace(node.ScriptSegmentsJSON)
		if node.SchemaVersion <= 0 {
			node.SchemaVersion = 2
		}
		trimmed = append(trimmed, node)
	}

	if validationErr := validateTeacherNodeUpserts(trimmed, pageNum); validationErr != nil {
		return "", nil, fmt.Errorf("%w: %s", errInvalidTeachingNodes, validationErr.Error())
	}

	err := h.db.Transaction(func(tx *gorm.DB) error {
		var existing []model.TeachingNode
		if err := tx.Where("course_id = ? AND page_index = ?", courseID, pageNum).Find(&existing).Error; err != nil {
			return err
		}
		existingByID := make(map[string]model.TeachingNode, len(existing))
		existingByNodeID := make(map[string]model.TeachingNode, len(existing))
		keepIDs := make(map[string]struct{}, len(trimmed))
		for _, item := range existing {
			existingByID[item.ID] = item
			existingByNodeID[item.NodeID] = item
		}

		for index, item := range trimmed {
			persisted := model.TeachingNode{}
			if item.ID != "" {
				persisted = existingByID[item.ID]
			}
			if persisted.ID == "" && item.NodeID != "" {
				persisted = existingByNodeID[item.NodeID]
			}
			if persisted.ID == "" {
				persisted = model.TeachingNode{
					CourseID:      courseID,
					PageIndex:     pageNum,
					NodeID:        buildTeacherNodeID(pageNum, index+1, item.NodeID),
					Title:         defaultTeacherNodeTitle(pageNum, index+1, item.Title),
					ChapterTitle:  "第" + strconv.Itoa(pageNum) + "页",
					SchemaVersion: 2,
				}
			}
			persisted.CourseID = courseID
			persisted.PageIndex = pageNum
			persisted.NodeID = buildTeacherNodeID(pageNum, index+1, firstTeacherNonEmpty(item.NodeID, persisted.NodeID))
			persisted.Title = defaultTeacherNodeTitle(pageNum, index+1, firstTeacherNonEmpty(item.Title, persisted.Title))
			persisted.Summary = item.Summary
			persisted.ScriptText = item.ScriptText
			persisted.ReteachScript = strings.TrimSpace(item.ReteachScript)
			persisted.TransitionText = strings.TrimSpace(item.TransitionText)
			persisted.StructuredMarkdown = strings.TrimSpace(item.StructuredMarkdown)
			persisted.KnowledgeNodesJSON = normalizeTeacherKnowledgeNodesJSON(
				item.KnowledgeNodesJSON,
				item.KnowledgeNodes,
				persisted.NodeID,
				persisted.Title,
			)
			persisted.ScriptSegmentsJSON = normalizeTeacherScriptSegmentsJSON(
				item.ScriptSegmentsJSON,
				item.ScriptSegments,
				persisted.NodeID,
				firstTeacherNonEmpty(persisted.ScriptText, persisted.Summary),
			)
			persisted.SchemaVersion = maxInt(item.SchemaVersion, 2)
			persisted.EstimatedDuration = normalizeTeacherDuration(item.EstimatedDuration, persisted.ScriptText, persisted.Summary)
			persisted.SortOrder = index + 1

			if persisted.ID == "" {
				if err := tx.Create(&persisted).Error; err != nil {
					return err
				}
			} else {
				if err := tx.Model(&model.TeachingNode{}).Where("id = ?", persisted.ID).Updates(map[string]any{
					"course_id":            persisted.CourseID,
					"page_index":           persisted.PageIndex,
					"node_id":              persisted.NodeID,
					"title":                persisted.Title,
					"summary":              persisted.Summary,
					"script_text":          persisted.ScriptText,
					"reteach_script":       persisted.ReteachScript,
					"transition_text":      persisted.TransitionText,
					"structured_markdown":  persisted.StructuredMarkdown,
					"knowledge_nodes_json": persisted.KnowledgeNodesJSON,
					"script_segments_json": persisted.ScriptSegmentsJSON,
					"schema_version":       persisted.SchemaVersion,
					"estimated_duration":   persisted.EstimatedDuration,
					"sort_order":           persisted.SortOrder,
					"chapter_title":        persisted.ChapterTitle,
				}).Error; err != nil {
					return err
				}
			}
			keepIDs[persisted.ID] = struct{}{}
		}

		deleteIDs := make([]string, 0)
		for _, item := range existing {
			if _, ok := keepIDs[item.ID]; !ok {
				deleteIDs = append(deleteIDs, item.ID)
			}
		}
		if len(deleteIDs) > 0 {
			if err := tx.Where("id IN ?", deleteIDs).Delete(&model.TeachingNode{}).Error; err != nil {
				return err
			}
		}

		content := buildTeacherPageScriptFromNodes(trimmed)
		if err := upsertTeacherScriptWithDB(tx, courseID, pageNum, content); err != nil {
			return err
		}
		return nil
	})
	if err != nil {
		return "", nil, err
	}

	savedNodes := loadTeachingNodesByPage(h.db, courseID, pageNum)
	return buildPageContextFromTeachingNodes(savedNodes), savedNodes, nil
}

func validateTeacherNodeUpserts(nodes []teacherNodeUpsertRequest, pageNum int) error {
	if len(nodes) == 0 {
		return nil
	}

	nodeIDSet := make(map[string]struct{}, len(nodes))
	for idx, item := range nodes {
		nodeID := buildTeacherNodeID(pageNum, idx+1, strings.TrimSpace(item.NodeID))
		if nodeID == "" {
			return fmt.Errorf("第 %d 个节点缺少 nodeId", idx+1)
		}
		nodeIDSet[nodeID] = struct{}{}
	}

	for idx, item := range nodes {
		nodeID := buildTeacherNodeID(pageNum, idx+1, strings.TrimSpace(item.NodeID))
		nodeLabel := firstTeacherNonEmpty(strings.TrimSpace(item.Title), nodeID)

		segments := decodeTeacherJSONArray(normalizeTeacherScriptSegmentsJSON(item.ScriptSegmentsJSON, item.ScriptSegments, nodeID, firstTeacherNonEmpty(strings.TrimSpace(item.ScriptText), strings.TrimSpace(item.Summary))))
		if err := validateTeacherScriptSegments(nodeLabel, segments, nodeIDSet); err != nil {
			return err
		}
		segmentIDSet := buildTeacherSegmentIDSet(segments)

		knowledge := decodeTeacherJSONArray(normalizeTeacherKnowledgeNodesJSON(item.KnowledgeNodesJSON, item.KnowledgeNodes, nodeID, nodeLabel))
		if err := validateTeacherKnowledgeNodes(nodeLabel, knowledge, nodeIDSet, segmentIDSet); err != nil {
			return err
		}
	}

	return nil
}

func buildTeacherSegmentIDSet(segments []any) map[string]struct{} {
	result := make(map[string]struct{}, len(segments))
	for _, raw := range segments {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		segmentID := strings.TrimSpace(fmt.Sprintf("%v", item["segment_id"]))
		if segmentID == "" {
			continue
		}
		result[segmentID] = struct{}{}
	}
	return result
}

func validateTeacherScriptSegments(nodeLabel string, segments []any, nodeIDSet map[string]struct{}) error {
	seenSegmentIDs := make(map[string]struct{}, len(segments))
	for i, raw := range segments {
		item, ok := raw.(map[string]any)
		if !ok {
			return fmt.Errorf("节点 %s 的第 %d 条映射结构错误", nodeLabel, i+1)
		}
		segmentID := strings.TrimSpace(fmt.Sprintf("%v", item["segment_id"]))
		if segmentID == "" {
			return fmt.Errorf("节点 %s 的第 %d 条映射缺少 segment_id", nodeLabel, i+1)
		}
		if _, exists := seenSegmentIDs[segmentID]; exists {
			return fmt.Errorf("节点 %s 的 segment_id %s 重复", nodeLabel, segmentID)
		}
		seenSegmentIDs[segmentID] = struct{}{}

		nodeIDs, ok := item["node_ids"].([]any)
		if !ok || len(nodeIDs) == 0 {
			return fmt.Errorf("节点 %s 的 segment_id %s 缺少 node_ids", nodeLabel, segmentID)
		}
		for _, nodeRef := range nodeIDs {
			candidate := strings.TrimSpace(fmt.Sprintf("%v", nodeRef))
			if candidate == "" {
				return fmt.Errorf("节点 %s 的 segment_id %s 包含空 node_id", nodeLabel, segmentID)
			}
			if _, ok := nodeIDSet[candidate]; !ok {
				return fmt.Errorf("节点 %s 的 segment_id %s 引用了不存在的 node_id %s", nodeLabel, segmentID, candidate)
			}
		}
	}
	return nil
}

func validateTeacherKnowledgeNodes(nodeLabel string, knowledge []any, nodeIDSet map[string]struct{}, segmentIDSet map[string]struct{}) error {
	for i, raw := range knowledge {
		item, ok := raw.(map[string]any)
		if !ok {
			return fmt.Errorf("节点 %s 的第 %d 条知识结构错误", nodeLabel, i+1)
		}
		prereqRaw, ok := item["prerequisites"].([]any)
		if !ok {
			continue
		}
		for _, prereq := range prereqRaw {
			candidate := strings.TrimSpace(fmt.Sprintf("%v", prereq))
			if candidate == "" {
				continue
			}
			if _, exists := nodeIDSet[candidate]; !exists {
				return fmt.Errorf("节点 %s 的 prerequisites 引用了不存在的 node_id %s", nodeLabel, candidate)
			}
		}

		coverageRaw, ok := item["coverage_span"].([]any)
		if !ok {
			continue
		}
		for _, coverage := range coverageRaw {
			segmentID := strings.TrimSpace(fmt.Sprintf("%v", coverage))
			if segmentID == "" {
				continue
			}
			if _, exists := segmentIDSet[segmentID]; !exists {
				return fmt.Errorf("节点 %s 的 coverage_span 引用了不存在的 segment_id %s", nodeLabel, segmentID)
			}
		}
	}
	return nil
}

func buildTeacherNodePayload(nodes []model.TeachingNode) []gin.H {
	result := make([]gin.H, 0, len(nodes))
	for index, node := range nodes {
		knowledgeNodes := decodeTeacherJSONArray(node.KnowledgeNodesJSON)
		scriptSegments := decodeTeacherJSONArray(node.ScriptSegmentsJSON)
		result = append(result, gin.H{
			"id":                 node.ID,
			"nodeId":             node.NodeID,
			"page":               node.PageIndex,
			"type":               teacherNodeType(index, len(nodes)),
			"title":              node.Title,
			"summary":            node.Summary,
			"schemaVersion":      maxInt(node.SchemaVersion, 2),
			"scriptText":         node.ScriptText,
			"reteachScript":      node.ReteachScript,
			"transitionText":     node.TransitionText,
			"structuredMarkdown": node.StructuredMarkdown,
			"knowledgeNodesJson": node.KnowledgeNodesJSON,
			"scriptSegmentsJson": node.ScriptSegmentsJSON,
			"knowledgeNodes":     knowledgeNodes,
			"scriptSegments":     scriptSegments,
			"estimatedDuration":  playbackDurationSec(node),
			"sortOrder":          node.SortOrder,
		})
	}
	return result
}

func normalizeTeacherKnowledgeNodesJSON(raw string, structured []map[string]any, nodeID, title string) string {
	fallback := []map[string]any{
		{
			"node_id":       firstTeacherNonEmpty(nodeID, "node_unknown"),
			"parent_id":     "",
			"level":         1,
			"title":         firstTeacherNonEmpty(title, "未命名节点"),
			"tags":          []string{},
			"prerequisites": []string{},
			"difficulty":    "medium",
			"coverage_span": []string{"seg_1"},
		},
	}
	return normalizeTeacherJSONList(raw, structured, fallback)
}

func normalizeTeacherScriptSegmentsJSON(raw string, structured []map[string]any, nodeID, text string) string {
	fallbackText := strings.TrimSpace(text)
	if fallbackText == "" {
		fallbackText = "待补充讲稿内容"
	}
	fallback := []map[string]any{
		{
			"segment_id":      "seg_1",
			"text":            fallbackText,
			"node_ids":        []string{firstTeacherNonEmpty(nodeID, "node_unknown")},
			"confidence":      0.8,
			"manual_override": false,
		},
	}
	return normalizeTeacherJSONList(raw, structured, fallback)
}

func normalizeTeacherJSONList(raw string, structured []map[string]any, fallback []map[string]any) string {
	if len(structured) > 0 {
		payload, err := json.Marshal(structured)
		if err == nil {
			return string(payload)
		}
	}

	raw = strings.TrimSpace(raw)
	if raw != "" {
		var decoded any
		if err := json.Unmarshal([]byte(raw), &decoded); err == nil {
			normalized := normalizeTeacherDecodedJSONList(decoded)
			payload, marshalErr := json.Marshal(normalized)
			if marshalErr == nil {
				return string(payload)
			}
		}
	}

	payload, err := json.Marshal(fallback)
	if err != nil {
		return "[]"
	}
	return string(payload)
}

func normalizeTeacherDecodedJSONList(decoded any) []any {
	switch v := decoded.(type) {
	case []any:
		return v
	case []map[string]any:
		result := make([]any, 0, len(v))
		for _, item := range v {
			result = append(result, item)
		}
		return result
	case map[string]any:
		return []any{v}
	default:
		return []any{}
	}
}

func decodeTeacherJSONArray(raw string) []any {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return []any{}
	}
	var decoded any
	if err := json.Unmarshal([]byte(raw), &decoded); err != nil {
		return []any{}
	}
	return normalizeTeacherDecodedJSONList(decoded)
}

func buildTeacherNodeCoverage(nodes []model.TeachingNode) gin.H {
	totalNodes := len(nodes)
	if totalNodes == 0 {
		return gin.H{"totalNodes": 0, "coveredNodes": 0, "coverageRate": 1.0, "uncoveredNodeIds": []string{}}
	}

	covered := make(map[string]struct{}, totalNodes)
	for _, node := range nodes {
		nodeID := strings.TrimSpace(node.NodeID)
		if nodeID == "" {
			continue
		}
		segments := decodeTeacherJSONArray(node.ScriptSegmentsJSON)
		for _, segment := range segments {
			item, ok := segment.(map[string]any)
			if !ok {
				continue
			}
			nodeIDs, ok := item["node_ids"].([]any)
			if !ok {
				continue
			}
			for _, ref := range nodeIDs {
				candidate := strings.TrimSpace(fmt.Sprintf("%v", ref))
				if candidate != "" {
					covered[candidate] = struct{}{}
				}
			}
		}
	}

	uncovered := make([]string, 0)
	for _, node := range nodes {
		nodeID := strings.TrimSpace(node.NodeID)
		if nodeID == "" {
			continue
		}
		if _, ok := covered[nodeID]; !ok {
			uncovered = append(uncovered, nodeID)
		}
	}

	coveredCount := totalNodes - len(uncovered)
	rate := 0.0
	if totalNodes > 0 {
		rate = float64(coveredCount) / float64(totalNodes)
	}

	return gin.H{
		"totalNodes":       totalNodes,
		"coveredNodes":     coveredCount,
		"coverageRate":     roundTeacherFloat(rate),
		"uncoveredNodeIds": uncovered,
	}
}

func (h *TeacherHandler) buildTeacherPageStats(courseID string, totalPages int) []teacherPageStat {
	pageStats := make(map[int]*teacherPageStat)
	for page := 1; page <= maxCoursePage(totalPages); page++ {
		pageStats[page] = &teacherPageStat{PageIndex: page}
	}

	var questionStats []teacherQuestionStat
	_ = h.db.Table("question_logs").Select("page_index, count(*) as question_count").Where("course_id = ?", courseID).Group("page_index").Scan(&questionStats).Error
	for _, item := range questionStats {
		stat := ensureTeacherPageStat(pageStats, item.PageIndex)
		stat.QuestionCount = item.QuestionCount
	}

	var dialogueStats []teacherDialogueStat
	_ = h.db.Table("dialogue_turns").Select("page_index, count(*) as dialogue_count, sum(case when need_reteach then 1 else 0 end) as need_reteach_count, count(distinct session_id) as session_count").Where("course_id = ?", courseID).Group("page_index").Scan(&dialogueStats).Error
	for _, item := range dialogueStats {
		stat := ensureTeacherPageStat(pageStats, item.PageIndex)
		stat.DialogueCount = item.DialogueCount
		stat.NeedReteachCount = item.NeedReteachCount
		stat.SessionCount = item.SessionCount
		if stat.QuestionCount < item.DialogueCount {
			stat.QuestionCount = item.DialogueCount
		}
	}

	var durationStats []teacherDurationStat
	_ = h.db.Table("teaching_nodes").Select("page_index, coalesce(sum(case when estimated_duration > 0 then estimated_duration else 0 end), 0) as base_duration").Where("course_id = ?", courseID).Group("page_index").Scan(&durationStats).Error
	for _, item := range durationStats {
		stat := ensureTeacherPageStat(pageStats, item.PageIndex)
		stat.BaseDuration = item.BaseDuration
	}

	result := make([]teacherPageStat, 0, len(pageStats))
	for _, item := range pageStats {
		base := item.BaseDuration
		if base <= 0 {
			base = 30
		}
		sessionCount := item.SessionCount
		if sessionCount <= 0 {
			sessionCount = 1
		}
		engagementBoost := float64(item.DialogueCount*18+item.NeedReteachCount*35+item.QuestionCount*12) / float64(sessionCount)
		item.StayTime = roundTeacherFloat(float64(base) + engagementBoost)
		item.AvgTurns = roundTeacherFloat(float64(item.DialogueCount) / float64(sessionCount))
		item.CardIndex = roundTeacherCardIndex(item)
		result = append(result, *item)
	}
	sort.Slice(result, func(i, j int) bool {
		return result[i].PageIndex < result[j].PageIndex
	})
	return result
}

func ensureTeacherPageStat(pageStats map[int]*teacherPageStat, page int) *teacherPageStat {
	if page <= 0 {
		page = 1
	}
	if stat, ok := pageStats[page]; ok {
		return stat
	}
	stat := &teacherPageStat{PageIndex: page}
	pageStats[page] = stat
	return stat
}

func (h *TeacherHandler) collectTeacherQuestions(courseID string) []string {
	questions := make([]string, 0)
	logged := make([]string, 0)
	fromDialogue := make([]string, 0)
	_ = h.db.Table("question_logs").Where("course_id = ?", courseID).Pluck("question", &logged).Error
	_ = h.db.Table("dialogue_turns").Where("course_id = ?", courseID).Pluck("question", &fromDialogue).Error
	questions = append(questions, logged...)
	questions = append(questions, fromDialogue...)
	return questions
}

func (h *TeacherHandler) countDistinctUsers(courseID string) int64 {
	userSet := make(map[string]struct{})
	ids := make([]string, 0)
	_ = h.db.Table("question_logs").Where("course_id = ?", courseID).Distinct().Pluck("user_id", &ids).Error
	for _, item := range ids {
		if strings.TrimSpace(item) != "" {
			userSet[item] = struct{}{}
		}
	}
	ids = ids[:0]
	_ = h.db.Table("dialogue_turns").Where("course_id = ?", courseID).Distinct().Pluck("user_id", &ids).Error
	for _, item := range ids {
		if strings.TrimSpace(item) != "" {
			userSet[item] = struct{}{}
		}
	}
	return int64(len(userSet))
}

func (h *TeacherHandler) buildClassTrend(courseID string) []gin.H {
	dialogueAgg := make([]teacherTrendAggStat, 0)
	_ = h.db.Table("dialogue_turns").
		Select("to_char(date(created_at), 'YYYY-MM-DD') as day, count(*) as count, sum(case when need_reteach then 1 else 0 end) as reteach_count, count(distinct user_id) as user_count").
		Where("course_id = ?", courseID).
		Group("date(created_at)").
		Order("date(created_at)").
		Scan(&dialogueAgg).Error

	questionAgg := make([]teacherTrendAggStat, 0)
	_ = h.db.Table("question_logs").
		Select("to_char(date(created_at), 'YYYY-MM-DD') as day, count(*) as count").
		Where("course_id = ?", courseID).
		Group("date(created_at)").
		Order("date(created_at)").
		Scan(&questionAgg).Error

	type trendItem struct {
		Day           string
		QuestionCount int
		DialogueCount int
		ReteachCount  int
		UserCount     int
	}

	trendByDay := make(map[string]*trendItem)
	for _, item := range questionAgg {
		day := strings.TrimSpace(item.Day)
		if day == "" {
			continue
		}
		trendByDay[day] = &trendItem{Day: day, QuestionCount: item.Count}
	}
	for _, item := range dialogueAgg {
		day := strings.TrimSpace(item.Day)
		if day == "" {
			continue
		}
		current, ok := trendByDay[day]
		if !ok {
			current = &trendItem{Day: day}
			trendByDay[day] = current
		}
		current.DialogueCount = item.Count
		current.ReteachCount = item.ReteachCount
		current.UserCount = item.UserCount
		if current.QuestionCount < item.Count {
			current.QuestionCount = item.Count
		}
	}

	trend := make([]*trendItem, 0, len(trendByDay))
	for _, item := range trendByDay {
		trend = append(trend, item)
	}
	sort.Slice(trend, func(i, j int) bool {
		return trend[i].Day < trend[j].Day
	})

	result := make([]gin.H, 0, len(trend))
	for _, item := range trend {
		errorRate := 0.0
		if item.DialogueCount > 0 {
			errorRate = float64(item.ReteachCount) / float64(item.DialogueCount)
		}
		result = append(result, gin.H{
			"day":           item.Day,
			"questionCount": item.QuestionCount,
			"dialogueCount": item.DialogueCount,
			"reteachCount":  item.ReteachCount,
			"activeUsers":   item.UserCount,
			"errorRate":     roundTeacherFloat(errorRate),
		})
	}
	return result
}

func (h *TeacherHandler) buildLearningInsights(courseID string, nodeStats []gin.H) gin.H {
	priorities := make([]teacherNodePriority, 0, len(nodeStats))
	for _, item := range nodeStats {
		nodeID := strings.TrimSpace(fmt.Sprintf("%v", item["nodeId"]))
		if nodeID == "" {
			continue
		}
		errorRate := toTeacherFloat(item["errorRate"])
		dialogue := toTeacherInt(item["dialogueCount"])
		needReteach := toTeacherInt(item["needReteachCount"])
		score := errorRate*100 + float64(needReteach*3) + float64(dialogue)
		priorities = append(priorities, teacherNodePriority{
			NodeID:      nodeID,
			Title:       strings.TrimSpace(fmt.Sprintf("%v", item["title"])),
			Page:        toTeacherInt(item["page"]),
			Score:       score,
			ErrorRate:   errorRate,
			Dialogue:    dialogue,
			NeedReteach: needReteach,
		})
	}

	sort.Slice(priorities, func(i, j int) bool {
		return priorities[i].Score > priorities[j].Score
	})

	reteachRecommendations := make([]gin.H, 0, minTeacherInt(5, len(priorities)))
	for i := 0; i < minTeacherInt(5, len(priorities)); i++ {
		item := priorities[i]
		if item.Dialogue == 0 && item.NeedReteach == 0 {
			continue
		}
		reteachRecommendations = append(reteachRecommendations, gin.H{
			"nodeId":        item.NodeID,
			"title":         firstTeacherNonEmpty(item.Title, item.NodeID),
			"page":          item.Page,
			"priority":      roundTeacherFloat(item.Score),
			"errorRate":     roundTeacherFloat(item.ErrorRate),
			"dialogueCount": item.Dialogue,
			"reason":        fmt.Sprintf("重讲请求 %d 次，错误率 %.1f%%", item.NeedReteach, item.ErrorRate*100),
		})
	}

	prereqRecommendations := h.buildPrerequisiteRecommendations(courseID, priorities)

	return gin.H{
		"reteachNodes":     reteachRecommendations,
		"prerequisiteGaps": prereqRecommendations,
		"generatedAt":      time.Now().Format(time.RFC3339),
		"summary":          fmt.Sprintf("建议优先重讲 %d 个节点，补充前置知识 %d 个节点", len(reteachRecommendations), len(prereqRecommendations)),
	}
}

func (h *TeacherHandler) buildPrerequisiteRecommendations(courseID string, priorities []teacherNodePriority) []gin.H {
	top := minTeacherInt(8, len(priorities))
	if top == 0 {
		return []gin.H{}
	}

	nodeIDs := make([]string, 0, top)
	for i := 0; i < top; i++ {
		nodeIDs = append(nodeIDs, priorities[i].NodeID)
	}

	var nodes []model.TeachingNode
	_ = h.db.Select("node_id", "title", "page_index", "knowledge_nodes_json").
		Where("course_id = ? AND node_id IN ?", courseID, nodeIDs).
		Find(&nodes).Error

	byNode := make(map[string]model.TeachingNode, len(nodes))
	for _, node := range nodes {
		byNode[strings.TrimSpace(node.NodeID)] = node
	}

	recommendations := make([]gin.H, 0)
	for i := 0; i < top; i++ {
		item := priorities[i]
		node, ok := byNode[item.NodeID]
		if !ok {
			continue
		}
		knowledge := decodeTeacherJSONArray(node.KnowledgeNodesJSON)
		hasPrereq := false
		for _, raw := range knowledge {
			entry, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			nodeID := strings.TrimSpace(fmt.Sprintf("%v", entry["node_id"]))
			if nodeID != item.NodeID {
				continue
			}
			items, ok := entry["prerequisites"].([]any)
			if !ok {
				continue
			}
			for _, prereq := range items {
				candidate := strings.TrimSpace(fmt.Sprintf("%v", prereq))
				if candidate != "" {
					hasPrereq = true
					break
				}
			}
		}

		if hasPrereq {
			continue
		}

		recommendNodeID := ""
		recommendTitle := ""
		for _, candidate := range priorities {
			if candidate.Page >= item.Page {
				continue
			}
			recommendNodeID = candidate.NodeID
			recommendTitle = firstTeacherNonEmpty(candidate.Title, candidate.NodeID)
			break
		}
		if recommendNodeID == "" {
			recommendNodeID = fmt.Sprintf("p%d_n1", maxInt(1, item.Page-1))
			recommendTitle = "上一页导入节点"
		}

		recommendations = append(recommendations, gin.H{
			"nodeId":            item.NodeID,
			"title":             firstTeacherNonEmpty(node.Title, item.Title, item.NodeID),
			"page":              node.PageIndex,
			"suggestedPrereqId": recommendNodeID,
			"suggestedPrereq":   recommendTitle,
			"reason":            "该节点错误率较高且未配置 prerequisites，建议先补前置知识链路",
		})
	}

	return recommendations
}

func (h *TeacherHandler) buildNodeHeatmap(nodeStats []gin.H) []gin.H {
	result := make([]gin.H, 0, len(nodeStats))
	for _, item := range nodeStats {
		questionCount := toTeacherInt(item["questionCount"])
		dialogueCount := toTeacherInt(item["dialogueCount"])
		needReteach := toTeacherInt(item["needReteachCount"])
		heat := roundTeacherFloat(float64(questionCount) + float64(dialogueCount)*0.6 + float64(needReteach)*2.4)
		result = append(result, gin.H{
			"nodeId":        strings.TrimSpace(fmt.Sprintf("%v", item["nodeId"])),
			"title":         strings.TrimSpace(fmt.Sprintf("%v", item["title"])),
			"page":          toTeacherInt(item["page"]),
			"heat":          heat,
			"questionCount": questionCount,
			"errorRate":     toTeacherFloat(item["errorRate"]),
			"masteryScore":  toTeacherFloat(item["masteryScore"]),
		})
	}
	sort.Slice(result, func(i, j int) bool {
		return toTeacherFloat(result[i]["heat"]) > toTeacherFloat(result[j]["heat"])
	})
	if len(result) > 60 {
		result = result[:60]
	}
	return result
}

func (h *TeacherHandler) buildMasteryRadar(nodeStats []gin.H) gin.H {
	pageMastery := make(map[int][]float64)
	for _, item := range nodeStats {
		page := toTeacherInt(item["page"])
		if page <= 0 {
			page = 1
		}
		pageMastery[page] = append(pageMastery[page], toTeacherFloat(item["masteryScore"]))
	}

	pages := make([]int, 0, len(pageMastery))
	for page := range pageMastery {
		pages = append(pages, page)
	}
	sort.Ints(pages)

	indicators := make([]gin.H, 0, len(pages))
	values := make([]float64, 0, len(pages))
	total := 0.0
	for _, page := range pages {
		items := pageMastery[page]
		if len(items) == 0 {
			continue
		}
		sum := 0.0
		for _, score := range items {
			sum += score
		}
		avg := roundTeacherFloat(sum / float64(len(items)))
		total += avg
		indicators = append(indicators, gin.H{"name": fmt.Sprintf("P%d", page), "max": 100})
		values = append(values, avg)
	}

	avgMastery := 0.0
	if len(values) > 0 {
		avgMastery = roundTeacherFloat(total / float64(len(values)))
	}

	return gin.H{
		"indicators": indicators,
		"values":     values,
		"avgMastery": avgMastery,
	}
}

func buildTeacherPageScriptFromNodes(nodes []teacherNodeUpsertRequest) string {
	parts := make([]string, 0, len(nodes))
	for _, item := range nodes {
		text := strings.TrimSpace(item.ScriptText)
		if text == "" {
			text = strings.TrimSpace(item.Summary)
		}
		if text != "" {
			parts = append(parts, text)
		}
	}
	return strings.Join(parts, "\n\n")
}

func teacherNodeType(index, total int) string {
	if total <= 1 || index == 0 {
		return "opening"
	}
	if index == total-1 {
		return "transition"
	}
	return "explain"
}

func buildTeacherNodeID(pageNum, index int, raw string) string {
	raw = strings.TrimSpace(raw)
	if raw != "" {
		return raw
	}
	return fmt.Sprintf("p%d_n%d", pageNum, index)
}

func defaultTeacherNodeTitle(pageNum, index int, title string) string {
	title = strings.TrimSpace(title)
	if title != "" {
		return title
	}
	return fmt.Sprintf("第%d页节点%d", pageNum, index)
}

func normalizeTeacherDuration(duration int, content ...string) int {
	if duration > 0 {
		return duration
	}
	text := strings.Join(content, " ")
	base := len([]rune(strings.TrimSpace(text))) / 14
	if base < 20 {
		return 20
	}
	if base > 90 {
		return 90
	}
	return base
}

func firstTeacherNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func roundTeacherFloat(value float64) float64 {
	return mathRound(value*10) / 10
}

func roundTeacherCardIndex(stat *teacherPageStat) float64 {
	baseDuration := stat.BaseDuration
	if baseDuration <= 0 {
		baseDuration = 30
	}
	score := float64(stat.QuestionCount)*1.4 + float64(stat.NeedReteachCount)*2.3 + float64(stat.SessionCount)*0.8 + (stat.StayTime/float64(baseDuration))*1.5
	if score > 10 {
		score = 10
	}
	return roundTeacherFloat(score)
}

func mathRound(value float64) float64 {
	if value < 0 {
		return float64(int64(value - 0.5))
	}
	return float64(int64(value + 0.5))
}

func generateMockScript(courseName string, page int) string {
	templates := []string{
		"## %s 第%d页：课程导入\n\n### 教学目标\n- 了解本章节的核心概念\n- 建立知识框架\n- 明确学习重点\n\n### 讲解内容\n本页主要介绍本章节的背景、核心概念及学习路径。",
		"## %s 第%d页：深入讲解\n\n### 知识要点\n- 概念定义\n- 关键原理\n- 使用场景\n\n### 教学提示\n可以结合图示、案例和公式帮助学生理解。",
		"## %s 第%d页：案例分析\n\n### 案例拆解\n1. 场景说明\n2. 关键步骤\n3. 常见误区\n4. 课堂提问点\n\n### 小结\n帮助学生把抽象概念与真实场景建立联系。",
		"## %s 第%d页：总结回顾\n\n### 重点回顾\n1. 核心概念\n2. 方法步骤\n3. 易错点\n\n### 课堂互动\n建议通过一道练习题检验学生掌握情况。",
	}
	return fmt.Sprintf(templates[(page-1)%len(templates)], courseName, page)
}

func generateKeywordStats(questions []string) []gin.H {
	commonKeywords := []string{"依赖注入", "IoC", "AOP", "Spring", "微服务", "分布式", "事务", "缓存", "数据库", "接口", "fillna", "interpolate", "dropna", "缺失值", "异常值"}
	stats := make([]gin.H, 0)
	for _, keyword := range commonKeywords {
		count := 0
		for _, question := range questions {
			if strings.Contains(question, keyword) {
				count++
			}
		}
		if count > 0 {
			stats = append(stats, gin.H{"word": keyword, "count": count})
		}
	}
	sort.Slice(stats, func(i, j int) bool {
		return stats[i]["count"].(int) > stats[j]["count"].(int)
	})
	if len(stats) < 5 {
		for _, keyword := range []string{"概念", "原理", "实现", "应用", "区别"} {
			stats = append(stats, gin.H{"word": keyword, "count": 1})
			if len(stats) >= 5 {
				break
			}
		}
	}
	return stats
}

func toTeacherInt(value any) int {
	switch v := value.(type) {
	case int:
		return v
	case int32:
		return int(v)
	case int64:
		return int(v)
	case float32:
		return int(v)
	case float64:
		return int(v)
	case string:
		parsed, err := strconv.Atoi(strings.TrimSpace(v))
		if err == nil {
			return parsed
		}
	}
	return 0
}

func toTeacherFloat(value any) float64 {
	switch v := value.(type) {
	case int:
		return float64(v)
	case int32:
		return float64(v)
	case int64:
		return float64(v)
	case float32:
		return float64(v)
	case float64:
		return v
	case string:
		parsed, err := strconv.ParseFloat(strings.TrimSpace(v), 64)
		if err == nil {
			return parsed
		}
	}
	return 0
}

func parsePageParam(values ...string) (int, error) {
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			continue
		}
		return strconv.Atoi(value)
	}
	return 0, fmt.Errorf("missing page")
}

func publishStatus(published bool) string {
	if published {
		return "published"
	}
	return "draft"
}

func defaultTeacherMode(mode string) string {
	if strings.TrimSpace(mode) == "" {
		return "llm"
	}
	return mode
}

func maxCoursePage(page int) int {
	if page > 0 {
		return page
	}
	return 1
}

func minTeacherInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}
