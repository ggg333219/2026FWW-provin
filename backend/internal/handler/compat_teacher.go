package handler

import (
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

func (h *CompatibilityHandler) DeleteCoursewareV1(c *gin.Context) {
	courseID := c.Param("courseId")
	if err := h.courseService.DeleteCourse(courseID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "删除失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "删除成功"})
}

func (h *CompatibilityHandler) GetTeacherScriptV1(c *gin.Context) {
	courseID := c.Param("courseId")
	pageStr := c.Param("pageNum")
	c.Params = append(filterParams(c.Params, "page"), gin.Param{Key: "page", Value: pageStr}, gin.Param{Key: "courseId", Value: courseID})
	NewTeacherHandler(h.db, h.aiClient).GetScript(c)
}

func (h *CompatibilityHandler) UpdateTeacherScriptV1(c *gin.Context) {
	courseID := c.Param("courseId")
	pageStr := c.Param("pageNum")
	page, err := strconv.Atoi(pageStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "页码错误"})
		return
	}
	var req struct {
		Content string `json:"content" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	var coursePage model.CoursePage
	err = h.db.Where("course_id = ? AND page_index = ?", courseID, page).First(&coursePage).Error
	if err != nil {
		coursePage = model.CoursePage{CourseID: courseID, PageIndex: page, ScriptText: req.Content}
		err = h.db.Create(&coursePage).Error
	} else {
		err = h.db.Model(&coursePage).Update("script_text", req.Content).Error
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "保存失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "保存成功"})
}

func (h *CompatibilityHandler) GetTeacherNodesV1(c *gin.Context) {
	courseID := c.Param("courseId")
	pageStr := c.Param("pageNum")
	params := filterParams(filterParams(c.Params, "page"), "courseId")
	c.Params = append(params, gin.Param{Key: "page", Value: pageStr}, gin.Param{Key: "courseId", Value: courseID})
	NewTeacherHandler(h.db, h.aiClient).GetTeachingNodes(c)
}

func (h *CompatibilityHandler) UpdateTeacherNodesV1(c *gin.Context) {
	courseID := c.Param("courseId")
	pageStr := c.Param("pageNum")
	params := filterParams(filterParams(c.Params, "page"), "courseId")
	c.Params = append(params, gin.Param{Key: "page", Value: pageStr}, gin.Param{Key: "courseId", Value: courseID})
	NewTeacherHandler(h.db, h.aiClient).UpdateTeachingNodes(c)
}

func (h *CompatibilityHandler) GenerateTeacherAudioV1(c *gin.Context) {
	courseID := c.Param("courseId")
	pageStr := c.Param("pageNum")
	params := filterParams(filterParams(c.Params, "page"), "courseId")
	c.Params = append(params, gin.Param{Key: "page", Value: pageStr}, gin.Param{Key: "courseId", Value: courseID})
	NewTeacherHandler(h.db, h.aiClient).GeneratePageAudio(c)
}

func (h *CompatibilityHandler) AIGenerateTeacherScriptV1(c *gin.Context) {
	courseID := c.Param("courseId")
	var req struct {
		PageNum int    `json:"pageNum" binding:"required"`
		Mode    string `json:"mode"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	var course model.Course
	if err := h.db.First(&course, "id = ?", courseID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "课件不存在"})
		return
	}
	var page model.CoursePage
	contextText := ""
	if err := h.db.Where("course_id = ? AND page_index = ?", courseID, req.PageNum).First(&page).Error; err == nil {
		contextText = pageContextText(page)
	}
	script := ""
	mindmapMarkdown := ""
	teachingNodes := loadTeachingNodesByPage(h.db, courseID, req.PageNum)
	if generatedScript, generatedMindmap, usedNodes, err := generateAndStoreTeachingNodeScripts(c.Request.Context(), h.db, h.aiClient, course.Title, defaultString(req.Mode, "llm"), teachingNodes); usedNodes && err == nil {
		script = generatedScript
		mindmapMarkdown = generatedMindmap
	} else {
		resp, err := h.aiClient.GenerateScript(c.Request.Context(), service.GenerateScriptRequest{Page: req.PageNum, Content: contextText, CourseName: course.Title, Mode: defaultString(req.Mode, "llm")})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "AI生成失败"})
			return
		}
		script = resp.Script
		mindmapMarkdown = resp.MindmapMarkdown
		// 页面级生成成功但节点级失败时，用页面脚本回填 node 字段
		for _, node := range teachingNodes {
			segments := defaultScriptSegments(script, node.NodeID)
			_ = h.db.Model(&model.TeachingNode{}).Where("id = ?", node.ID).Updates(map[string]any{
				"script_text":          script,
				"mindmap_markdown":     mindmapMarkdown,
				"knowledge_nodes_json": encodeJSON(defaultKnowledgeNodes(node.NodeID, node.Title)),
				"script_segments_json": encodeJSON(segments),
				"schema_version":       2,
			}).Error
		}
	}
	if err := h.db.Where("course_id = ? AND page_index = ?", courseID, req.PageNum).First(&page).Error; err == nil {
		_ = h.db.Model(&page).Update("script_text", script).Error
	} else {
		_ = h.db.Create(&model.CoursePage{CourseID: courseID, PageIndex: req.PageNum, ScriptText: script}).Error
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"courseId": courseID, "pageNum": req.PageNum, "content": script, "mindmapMarkdown": mindmapMarkdown}})
}

func (h *CompatibilityHandler) PublishCoursewareV1(c *gin.Context) {
	courseID := c.Param("courseId")
	var req struct {
		Scope               string `json:"scope"`
		TeachingCourseID    string `json:"teachingCourseId"`
		TeachingCourseTitle string `json:"teachingCourseTitle"`
		CourseClassID       string `json:"courseClassId"`
		CourseClassName     string `json:"courseClassName"`
	}
	_ = c.ShouldBindJSON(&req)
	if strings.TrimSpace(req.Scope) == "" {
		req.Scope = "all"
	}
	now := time.Now()
	updates := map[string]any{
		"is_published":          true,
		"publish_scope":         req.Scope,
		"published_at":          now,
		"teaching_course_id":    strings.TrimSpace(req.TeachingCourseID),
		"teaching_course_title": strings.TrimSpace(req.TeachingCourseTitle),
		"course_class_id":       strings.TrimSpace(req.CourseClassID),
		"course_class_name":     strings.TrimSpace(req.CourseClassName),
	}
	if err := h.db.Model(&model.Course{}).Where("id = ?", courseID).Updates(updates).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "发布失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "发布成功", "data": gin.H{"courseId": courseID, "scope": req.Scope, "teachingCourseId": strings.TrimSpace(req.TeachingCourseID), "courseClassId": strings.TrimSpace(req.CourseClassID), "publishedAt": now.Format("2006-01-02 15:04:05")}})
}

func (h *CompatibilityHandler) GetCardDataV1(c *gin.Context) {
	courseID := c.Param("courseId")
	c.Params = append(filterParams(c.Params, "courseId"), gin.Param{Key: "courseId", Value: courseID})
	NewTeacherHandler(h.db, h.aiClient).GetCardData(c)
}

func (h *CompatibilityHandler) GetKnowledgeGraphV1(c *gin.Context) {
	courseID := c.Param("courseId")
	var nodes []model.KnowledgePoint
	if err := h.db.Where("course_id = ?", courseID).Order("level asc, created_at asc").Find(&nodes).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "查询知识图谱失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"courseId": courseID, "knowledgeGraph": buildKnowledgeTree(nodes)}})
}

func buildKnowledgeTree(nodes []model.KnowledgePoint) []gin.H {
	childrenMap := map[string][]model.KnowledgePoint{}
	roots := make([]model.KnowledgePoint, 0)
	for _, node := range nodes {
		if strings.TrimSpace(node.ParentID) == "" {
			roots = append(roots, node)
			continue
		}
		childrenMap[node.ParentID] = append(childrenMap[node.ParentID], node)
	}
	for parentID := range childrenMap {
		sort.Slice(childrenMap[parentID], func(i, j int) bool {
			if childrenMap[parentID][i].Level == childrenMap[parentID][j].Level {
				return childrenMap[parentID][i].CreatedAt.Before(childrenMap[parentID][j].CreatedAt)
			}
			return childrenMap[parentID][i].Level < childrenMap[parentID][j].Level
		})
	}
	var convert func(model.KnowledgePoint) gin.H
	convert = func(node model.KnowledgePoint) gin.H {
		children := childrenMap[node.ID]
		result := gin.H{"id": node.ID, "name": node.Name, "level": node.Level, "content": node.Content}
		if len(children) > 0 {
			next := make([]gin.H, 0, len(children))
			for _, child := range children {
				next = append(next, convert(child))
			}
			result["children"] = next
		}
		return result
	}
	result := make([]gin.H, 0, len(roots))
	for _, root := range roots {
		result = append(result, convert(root))
	}
	return result
}

func (h *CompatibilityHandler) AskCoursewareV1(c *gin.Context) {
	courseID := c.Param("courseId")
	var req struct {
		PageNum    int    `json:"pageNum" binding:"required"`
		Type       string `json:"type"`
		Question   string `json:"question" binding:"required"`
		StudentID  string `json:"studentId"`
		TracePoint *struct {
			X float64 `json:"x"`
			Y float64 `json:"y"`
		} `json:"tracePoint"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}
	var coursePage model.CoursePage
	contextText := ""
	if err := h.db.Where("course_id = ? AND page_index = ?", courseID, req.PageNum).First(&coursePage).Error; err == nil {
		contextText = pageContextText(coursePage)
	}
	if strings.TrimSpace(contextText) == "" {
		contextText = buildPageContextFromTeachingNodes(loadTeachingNodesByPage(h.db, courseID, req.PageNum))
	}
	question := req.Question
	if req.TracePoint != nil {
		question = fmt.Sprintf("%s（定位坐标: %.2f, %.2f）", req.Question, req.TracePoint.X, req.TracePoint.Y)
	}
	resp, err := h.aiClient.AskWithContext(c.Request.Context(), service.AskWithContextRequest{Question: question, CurrentPage: req.PageNum, Context: contextText, Mode: "llm"})
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 503, "message": "AI服务暂不可用"})
		return
	}
	if strings.TrimSpace(req.StudentID) != "" {
		_ = h.db.Create(&model.QuestionLog{UserID: req.StudentID, CourseID: courseID, PageIndex: req.PageNum, NodeID: fmt.Sprintf("p%d_n1", req.PageNum), Question: req.Question, Answer: resp.Answer}).Error
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{"answer": resp.Answer, "sourcePage": resp.SourcePage, "sourceExcerpt": resp.SourceExcerpt, "followUpSuggestion": resp.FollowUpSuggestion, "needReteach": resp.Intent.NeedReteach}})
}

func (h *CompatibilityHandler) UploadCoursewareV1(c *gin.Context) {
	title := c.PostForm("title")
	if title == "" {
		title = "未命名课件"
	}
	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "请选择文件"})
		return
	}
	course, err := h.courseService.UploadCourse(c.Request.Context(), file, title)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "上传失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "上传成功", "data": course})
}

func (h *CompatibilityHandler) SyncCourseKnowledgeGraphV1(c *gin.Context) {
	courseID := strings.TrimSpace(c.Param("courseId"))
	if courseID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 courseId"})
		return
	}
	kg := service.NewKnowledgeGraphService(h.db)
	if err := kg.RebuildTeachingNodeRelations(courseID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "知识图谱同步失败", "error": err.Error()})
		return
	}
	relations, err := kg.ListTeachingNodeRelations(courseID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "知识图谱查询失败", "error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "同步成功", "data": gin.H{"courseId": courseID, "edgeCount": len(relations), "relations": relations}})
}

func (h *CompatibilityHandler) GetTeachingNodeReferenceHealthV1(c *gin.Context) {
	courseID := strings.TrimSpace(c.Param("courseId"))
	if courseID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 courseId"})
		return
	}
	kg := service.NewKnowledgeGraphService(h.db)
	report, err := kg.ScanOrphanTeachingNodeReferences(courseID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "引用健康检查失败", "error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "请求成功", "data": report})
}

func (h *CompatibilityHandler) PostTeachingNodeReferenceRepairV1(c *gin.Context) {
	courseID := strings.TrimSpace(c.Param("courseId"))
	if courseID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 courseId"})
		return
	}
	var req struct {
		Confirm bool     `json:"confirm"`
		NodeIDs []string `json:"nodeIds"`
	}
	_ = c.ShouldBindJSON(&req)
	if !req.Confirm {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "请先确认修复操作(confirm=true)"})
		return
	}
	kg := service.NewKnowledgeGraphService(h.db)
	report, err := kg.RepairOrphanTeachingNodeReferences(courseID, req.NodeIDs)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "引用修复失败", "error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "修复完成", "data": report})
}
