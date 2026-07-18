package service

import (
	"strings"
	"time"

	"smart-teaching-backend/internal/model"
	"gorm.io/gorm"
)

// KnowledgeMapItem 学生在某个知识点上的掌握度条目。
type KnowledgeMapItem struct {
	KnowledgePointID string     `json:"knowledgePointId"`
	CourseID         string     `json:"courseId"`
	Name             string     `json:"name"`
	MasteryScore     float64    `json:"masteryScore"`
	CorrectCount     int        `json:"correctCount"`
	IncorrectCount   int        `json:"incorrectCount"`
	LastResponseMs   int        `json:"lastResponseMs"`
	LastPracticedAt  *time.Time `json:"lastPracticedAt,omitempty"`
}

// LearningProgressSummary 学习进展摘要。
type LearningProgressSummary struct {
	StudentID          string  `json:"studentId"`
	Days               int     `json:"days"`
	TotalKnowledgePts  int     `json:"totalKnowledgePoints"`
	PracticedPts       int     `json:"practicedKnowledgePoints"`
	AverageMastery     float64 `json:"averageMastery"`
	MasteryAbove80Rate float64 `json:"masteryAbove80Rate"`
}

// StudyRecommendation 学习建议。
type StudyRecommendation struct {
	KnowledgePointID string  `json:"knowledgePointId"`
	CourseID         string  `json:"courseId"`
	Name             string  `json:"name"`
	MasteryScore     float64 `json:"masteryScore"`
	Reason           string  `json:"reason"`
	Action           string  `json:"action"`
}

// KnowledgeMapService 负责学生知识点掌握度的计算与查询。
type KnowledgeMapService struct {
	db *gorm.DB
}

func NewKnowledgeMapService(db *gorm.DB) *KnowledgeMapService {
	return &KnowledgeMapService{db: db}
}

// UpdateMasteryScore 根据答题结果更新掌握度，范围固定在 [0, 1]。
func (s *KnowledgeMapService) UpdateMasteryScore(studentID, knowledgePointID string, isCorrect bool, responseTimeMs int) error {
	studentID = strings.TrimSpace(studentID)
	knowledgePointID = strings.TrimSpace(knowledgePointID)
	if studentID == "" || knowledgePointID == "" {
		return nil
	}

	now := time.Now().UTC()
	return s.db.Transaction(func(tx *gorm.DB) error {
		var mastery model.StudentKnowledgeMastery
		err := tx.Where("student_id = ? AND knowledge_point_id = ?", studentID, knowledgePointID).First(&mastery).Error
		if err != nil && err != gorm.ErrRecordNotFound {
			return err
		}
		if err == gorm.ErrRecordNotFound {
			mastery = model.StudentKnowledgeMastery{
				StudentID:        studentID,
				KnowledgePointID: knowledgePointID,
				MasteryScore:     0.5,
			}
		}

		delta := -0.06
		if isCorrect {
			delta = 0.08
		}
		// 响应更快时给轻微加成，保证单次波动可控。
		if responseTimeMs > 0 && responseTimeMs <= 5000 {
			delta += 0.02
		}
		mastery.MasteryScore = clampScore(mastery.MasteryScore + delta)
		if isCorrect {
			mastery.CorrectCount++
		} else {
			mastery.IncorrectCount++
		}
		if responseTimeMs > 0 {
			mastery.LastResponseMs = responseTimeMs
		}
		mastery.LastPracticedAt = &now

		if err == gorm.ErrRecordNotFound {
			return tx.Create(&mastery).Error
		}
		return tx.Model(&model.StudentKnowledgeMastery{}).
			Where("id = ?", mastery.ID).
			Updates(map[string]any{
				"mastery_score":     mastery.MasteryScore,
				"correct_count":     mastery.CorrectCount,
				"incorrect_count":   mastery.IncorrectCount,
				"last_response_ms":  mastery.LastResponseMs,
				"last_practiced_at": mastery.LastPracticedAt,
			}).Error
	})
}

func (s *KnowledgeMapService) GetKnowledgeMap(studentID string) ([]KnowledgeMapItem, error) {
	return s.queryKnowledgeMap(studentID, nil)
}

func (s *KnowledgeMapService) GetKnowledgePointMastery(studentID, knowledgePointID string) (*KnowledgeMapItem, error) {
	knowledgePointID = strings.TrimSpace(knowledgePointID)
	if knowledgePointID == "" {
		return nil, gorm.ErrRecordNotFound
	}
	items, err := s.queryKnowledgeMap(studentID, func(tx *gorm.DB) *gorm.DB {
		return tx.Where("m.knowledge_point_id = ?", knowledgePointID)
	})
	if err != nil {
		return nil, err
	}
	if len(items) == 0 {
		return nil, gorm.ErrRecordNotFound
	}
	return &items[0], nil
}

func (s *KnowledgeMapService) GetWeakKnowledgePoints(studentID string, threshold float32) ([]KnowledgeMapItem, error) {
	return s.queryKnowledgeMap(studentID, func(tx *gorm.DB) *gorm.DB {
		return tx.Where("m.mastery_score <= ?", threshold)
	})
}

func (s *KnowledgeMapService) GetStrongKnowledgePoints(studentID string, threshold float32) ([]KnowledgeMapItem, error) {
	return s.queryKnowledgeMap(studentID, func(tx *gorm.DB) *gorm.DB {
		return tx.Where("m.mastery_score >= ?", threshold)
	})
}

func (s *KnowledgeMapService) AnalyzeLearningProgress(studentID string, days int) (LearningProgressSummary, error) {
	studentID = strings.TrimSpace(studentID)
	if studentID == "" {
		return LearningProgressSummary{}, nil
	}
	if days <= 0 {
		days = 7
	}

	cutoff := time.Now().UTC().AddDate(0, 0, -days)
	var total int64
	if err := s.db.Model(&model.StudentKnowledgeMastery{}).Where("student_id = ?", studentID).Count(&total).Error; err != nil {
		return LearningProgressSummary{}, err
	}
	var practiced int64
	if err := s.db.Model(&model.StudentKnowledgeMastery{}).
		Where("student_id = ? AND last_practiced_at >= ?", studentID, cutoff).
		Count(&practiced).Error; err != nil {
		return LearningProgressSummary{}, err
	}

	var rows []model.StudentKnowledgeMastery
	if err := s.db.Where("student_id = ?", studentID).Find(&rows).Error; err != nil {
		return LearningProgressSummary{}, err
	}
	var sum float64
	var above80 int
	for _, row := range rows {
		sum += row.MasteryScore
		if row.MasteryScore >= 0.8 {
			above80++
		}
	}
	avg := 0.0
	aboveRate := 0.0
	if len(rows) > 0 {
		avg = sum / float64(len(rows))
		aboveRate = float64(above80) / float64(len(rows))
	}
	return LearningProgressSummary{
		StudentID:          studentID,
		Days:               days,
		TotalKnowledgePts:  int(total),
		PracticedPts:       int(practiced),
		AverageMastery:     avg,
		MasteryAbove80Rate: aboveRate,
	}, nil
}

func (s *KnowledgeMapService) RecommendNextStudy(studentID string) ([]StudyRecommendation, error) {
	items, err := s.GetWeakKnowledgePoints(studentID, 0.65)
	if err != nil {
		return nil, err
	}
	if len(items) == 0 {
		return []StudyRecommendation{}, nil
	}
	recommendations := make([]StudyRecommendation, 0, minInt(len(items), 5))
	for i, item := range items {
		if i >= 5 {
			break
		}
		recommendations = append(recommendations, StudyRecommendation{
			KnowledgePointID: item.KnowledgePointID,
			CourseID:         item.CourseID,
			Name:             item.Name,
			MasteryScore:     item.MasteryScore,
			Reason:           "该知识点掌握度偏低，建议优先复习。",
			Action:           "先看讲解视频，再完成 3-5 题巩固练习。",
		})
	}
	return recommendations, nil
}

func (s *KnowledgeMapService) queryKnowledgeMap(studentID string, extra func(*gorm.DB) *gorm.DB) ([]KnowledgeMapItem, error) {
	studentID = strings.TrimSpace(studentID)
	if studentID == "" {
		return []KnowledgeMapItem{}, nil
	}

	type row struct {
		KnowledgePointID string
		CourseID         string
		Name             string
		MasteryScore     float64
		CorrectCount     int
		IncorrectCount   int
		LastResponseMs   int
		LastPracticedAt  *time.Time
	}

	tx := s.db.Table("student_knowledge_masteries AS m").
		Select("m.knowledge_point_id, kp.course_id, kp.name, m.mastery_score, m.correct_count, m.incorrect_count, m.last_response_ms, m.last_practiced_at").
		Joins("LEFT JOIN knowledge_points AS kp ON kp.id = m.knowledge_point_id").
		Where("m.student_id = ?", studentID).
		Order("m.mastery_score ASC, m.updated_at DESC")
	if extra != nil {
		tx = extra(tx)
	}

	var rows []row
	if err := tx.Find(&rows).Error; err != nil {
		return nil, err
	}
	items := make([]KnowledgeMapItem, 0, len(rows))
	for _, r := range rows {
		items = append(items, KnowledgeMapItem{
			KnowledgePointID: r.KnowledgePointID,
			CourseID:         r.CourseID,
			Name:             r.Name,
			MasteryScore:     r.MasteryScore,
			CorrectCount:     r.CorrectCount,
			IncorrectCount:   r.IncorrectCount,
			LastResponseMs:   r.LastResponseMs,
			LastPracticedAt:  r.LastPracticedAt,
		})
	}
	return items, nil
}

func clampScore(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 1 {
		return 1
	}
	return v
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}
