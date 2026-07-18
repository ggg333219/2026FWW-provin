package handler

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

// KnowledgeMapHandler 知识图谱处理器
type KnowledgeMapHandler struct {
	knowledgeMapService *service.KnowledgeMapService
}

// NewKnowledgeMapHandler 创建知识图谱处理器
func NewKnowledgeMapHandler(knowledgeMapService *service.KnowledgeMapService) *KnowledgeMapHandler {
	return &KnowledgeMapHandler{
		knowledgeMapService: knowledgeMapService,
	}
}

// GetKnowledgeMap 获取知识图谱
func (kmh *KnowledgeMapHandler) GetKnowledgeMap(c *gin.Context) {
	studentID := c.Query("studentId")
	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}

	knowledgeMaps, err := kmh.knowledgeMapService.GetKnowledgeMap(studentID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取知识图谱失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": knowledgeMaps})
}

// GetKnowledgePointMastery 获取知识点掌握度
func (kmh *KnowledgeMapHandler) GetKnowledgePointMastery(c *gin.Context) {
	studentID := c.Query("studentId")
	knowledgePointID := c.Query("knowledgePointId")

	if studentID == "" || knowledgePointID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少必要参数"})
		return
	}

	knowledgeMap, err := kmh.knowledgeMapService.GetKnowledgePointMastery(studentID, knowledgePointID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "知识点掌握度记录不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": knowledgeMap})
}

// UpdateMasteryScore 更新掌握度
func (kmh *KnowledgeMapHandler) UpdateMasteryScore(c *gin.Context) {
	var req struct {
		StudentID        string `json:"studentId" binding:"required"`
		KnowledgePointID string `json:"knowledgePointId" binding:"required"`
		IsCorrect        bool   `json:"isCorrect"`
		ResponseTime     int    `json:"responseTime"` // 毫秒
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	err := kmh.knowledgeMapService.UpdateMasteryScore(req.StudentID, req.KnowledgePointID, req.IsCorrect, req.ResponseTime)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "更新掌握度失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "更新成功"})
}

// GetWeakKnowledgePoints 获取薄弱知识点
func (kmh *KnowledgeMapHandler) GetWeakKnowledgePoints(c *gin.Context) {
	studentID := c.Query("studentId")
	thresholdStr := c.DefaultQuery("threshold", "0.6")

	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}

	threshold, err := strconv.ParseFloat(thresholdStr, 32)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "threshold 参数无效"})
		return
	}

	knowledgeMaps, err := kmh.knowledgeMapService.GetWeakKnowledgePoints(studentID, float32(threshold))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取薄弱知识点失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": knowledgeMaps})
}

// GetStrongKnowledgePoints 获取强项知识点
func (kmh *KnowledgeMapHandler) GetStrongKnowledgePoints(c *gin.Context) {
	studentID := c.Query("studentId")
	thresholdStr := c.DefaultQuery("threshold", "0.8")

	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}

	threshold, err := strconv.ParseFloat(thresholdStr, 32)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "threshold 参数无效"})
		return
	}

	knowledgeMaps, err := kmh.knowledgeMapService.GetStrongKnowledgePoints(studentID, float32(threshold))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取强项知识点失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": knowledgeMaps})
}

// AnalyzeLearningProgress 分析学习进度
func (kmh *KnowledgeMapHandler) AnalyzeLearningProgress(c *gin.Context) {
	studentID := c.Query("studentId")
	daysStr := c.DefaultQuery("days", "7")

	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}

	days, err := strconv.Atoi(daysStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "days 参数无效"})
		return
	}

	progress, err := kmh.knowledgeMapService.AnalyzeLearningProgress(studentID, days)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "分析学习进度失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": progress})
}

// RecommendNextStudy 推荐下一步学习内容
func (kmh *KnowledgeMapHandler) RecommendNextStudy(c *gin.Context) {
	studentID := c.Query("studentId")

	if studentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 studentId"})
		return
	}

	recommendations, err := kmh.knowledgeMapService.RecommendNextStudy(studentID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "获取学习推荐失败"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "data": recommendations})
}
