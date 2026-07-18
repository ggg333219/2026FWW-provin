package handler

import (
	"fmt"
	"net/http"
	"strings"
	"time"

	"smart-teaching-backend/internal/model"

	"github.com/gin-gonic/gin"
)

// GetNodeInsightsV1 获取课程节点分析数据（仅新增的方法，防止与 compat_student.go 重复）
func (h *CompatibilityHandler) GetNodeInsightsV1(c *gin.Context) {
	courseID := c.Param("courseId")
	if strings.TrimSpace(courseID) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 courseId"})
		return
	}

	type pageStat struct {
		PageIndex int
		Count     int64
	}
	type nodePracticeStat struct {
		NodeID       string
		AttemptCount int64
		TotalCount   int64
		CorrectCount int64
	}
	type nodeReteachStat struct {
		NodeID       string
		ReteachCount int64
		TotalCount   int64
	}
	type trendRow struct {
		Day       string
		PageIndex int
		Count     int64
	}
	type nodeTrendRow struct {
		Day    string
		NodeID string
		Count  int64
	}

	var qStats []pageStat
	var nStats []pageStat
	h.db.Model(&model.QuestionLog{}).
		Select("page_index, count(*) as count").
		Where("course_id = ?", courseID).
		Group("page_index").
		Scan(&qStats)
	h.db.Model(&model.StudentNote{}).
		Select("page_num as page_index, count(*) as count").
		Where("course_id = ?", courseID).
		Group("page_num").
		Scan(&nStats)

	var pages []model.CoursePage
	_ = h.db.Where("course_id = ?", courseID).Order("page_index asc").Find(&pages).Error

	// page -> primary node
	nodeByPage := map[int]string{}
	titleByNode := map[string]string{}
	for _, page := range pages {
		nodeID := fmt.Sprintf("p%d_n1", page.PageIndex)
		nodeTitle := fmt.Sprintf("第%d页", page.PageIndex)
		nodes := loadTeachingNodesByPage(h.db, courseID, page.PageIndex)
		if len(nodes) > 0 && strings.TrimSpace(nodes[0].NodeID) != "" {
			nodeID = nodes[0].NodeID
			if strings.TrimSpace(nodes[0].Title) != "" {
				nodeTitle = nodes[0].Title
			}
		}
		nodeByPage[page.PageIndex] = nodeID
		titleByNode[nodeID] = nodeTitle
	}

	questionByNode := map[string]int64{}
	noteByNode := map[string]int64{}
	for _, item := range qStats {
		nodeID := nodeByPage[item.PageIndex]
		if nodeID == "" {
			nodeID = fmt.Sprintf("p%d_n1", item.PageIndex)
		}
		questionByNode[nodeID] += item.Count
	}
	for _, item := range nStats {
		nodeID := nodeByPage[item.PageIndex]
		if nodeID == "" {
			nodeID = fmt.Sprintf("p%d_n1", item.PageIndex)
		}
		noteByNode[nodeID] += item.Count
	}

	// 练习正确率
	var pStats []nodePracticeStat
	h.db.Model(&model.PracticeAttempt{}).
		Select("node_id, count(*) as attempt_count, sum(total_count) as total_count, sum(correct_count) as correct_count").
		Where("course_id = ?", courseID).
		Group("node_id").
		Scan(&pStats)
	practiceByNode := map[string]nodePracticeStat{}
	for _, stat := range pStats {
		practiceByNode[strings.TrimSpace(stat.NodeID)] = stat
	}

	// 重讲率（need_reteach）
	var rStats []nodeReteachStat
	h.db.Model(&model.DialogueTurn{}).
		Select("node_id, sum(case when need_reteach = true then 1 else 0 end) as reteach_count, count(*) as total_count").
		Where("course_id = ?", courseID).
		Group("node_id").
		Scan(&rStats)
	reteachByNode := map[string]nodeReteachStat{}
	for _, stat := range rStats {
		reteachByNode[strings.TrimSpace(stat.NodeID)] = stat
	}

	// 近7天趋势（问题数 + 练习尝试数）
	questionTrendRaw := make([]trendRow, 0)
	h.db.Model(&model.QuestionLog{}).
		Select("to_char(created_at, 'YYYY-MM-DD') as day, page_index, count(*) as count").
		Where("course_id = ? AND created_at >= ?", courseID, time.Now().AddDate(0, 0, -6)).
		Group("day, page_index").
		Scan(&questionTrendRaw)
	questionTrendByNode := map[string]map[string]int64{}
	for _, row := range questionTrendRaw {
		nodeID := nodeByPage[row.PageIndex]
		if nodeID == "" {
			nodeID = fmt.Sprintf("p%d_n1", row.PageIndex)
		}
		if _, ok := questionTrendByNode[nodeID]; !ok {
			questionTrendByNode[nodeID] = map[string]int64{}
		}
		questionTrendByNode[nodeID][row.Day] += row.Count
	}

	practiceTrendRaw := make([]nodeTrendRow, 0)
	h.db.Model(&model.PracticeAttempt{}).
		Select("to_char(created_at, 'YYYY-MM-DD') as day, node_id, count(*) as count").
		Where("course_id = ? AND created_at >= ?", courseID, time.Now().AddDate(0, 0, -6)).
		Group("day, node_id").
		Scan(&practiceTrendRaw)
	practiceTrendByNode := map[string]map[string]int64{}
	for _, row := range practiceTrendRaw {
		nodeID := strings.TrimSpace(row.NodeID)
		if nodeID == "" {
			continue
		}
		if _, ok := practiceTrendByNode[nodeID]; !ok {
			practiceTrendByNode[nodeID] = map[string]int64{}
		}
		practiceTrendByNode[nodeID][row.Day] += row.Count
	}

	// 汇总并按 insightScore 降序
	items := make([]gin.H, 0, len(nodeByPage))
	for _, page := range pages {
		nodeID := nodeByPage[page.PageIndex]
		if nodeID == "" {
			nodeID = fmt.Sprintf("p%d_n1", page.PageIndex)
		}
		nodeTitle := titleByNode[nodeID]
		questionCount := questionByNode[nodeID]
		noteCount := noteByNode[nodeID]

		pStat := practiceByNode[nodeID]
		practiceAccuracy := 0.0
		if pStat.TotalCount > 0 {
			practiceAccuracy = float64(pStat.CorrectCount) * 100 / float64(pStat.TotalCount)
		}
		rStat := reteachByNode[nodeID]
		reteachRate := 0.0
		if rStat.TotalCount > 0 {
			reteachRate = float64(rStat.ReteachCount) * 100 / float64(rStat.TotalCount)
		}

		insightScore := float64(questionCount) + float64(noteCount)*0.5 + practiceAccuracy*0.02 - reteachRate*0.03
		trend := make([]gin.H, 0)
		for d := 0; d < 7; d++ {
			day := time.Now().AddDate(0, 0, -6+d).Format("2006-01-02")
			qCount := questionTrendByNode[nodeID][day]
			pCount := practiceTrendByNode[nodeID][day]
			trend = append(trend, gin.H{
				"day":       day,
				"questions": qCount,
				"practices": pCount,
			})
		}

		items = append(items, gin.H{
			"nodeId":             nodeID,
			"pageNum":            page.PageIndex,
			"nodeTitle":          nodeTitle,
			"questionCount":      questionCount,
			"noteCount":          noteCount,
			"practiceAttempts":   pStat.AttemptCount,
			"practiceTotalCount": pStat.TotalCount,
			"practiceAccuracy":   fmt.Sprintf("%.1f%%", practiceAccuracy),
			"reteachCount":       rStat.ReteachCount,
			"reteachTotal":       rStat.TotalCount,
			"reteachRate":        fmt.Sprintf("%.1f%%", reteachRate),
			"insightScore":       fmt.Sprintf("%.1f", insightScore),
			"trend":              trend,
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "请求成功",
		"data": gin.H{
			"courseId": courseID,
			"insights": items,
		},
	})
}
