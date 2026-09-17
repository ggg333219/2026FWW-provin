package service

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"smart-teaching-backend/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

var (
	ErrCoursewareProjectNotFound = errors.New("courseware project not found")
	ErrCoursewareProjectArchived = errors.New("courseware project is archived")
)

var validCoursewareSteps = map[string]bool{
	"s1_intent": true, "s2_material": true, "s3_studio": true, "s4_version": true,
}

type CoursewareProjectService struct{ db *gorm.DB }

func NewCoursewareProjectService(db *gorm.DB) *CoursewareProjectService {
	return &CoursewareProjectService{db: db}
}

type CreateCoursewareProjectRequest struct {
	Title string `json:"title"`
}
type SaveDraftRequest struct {
	DraftJSON json.RawMessage `json:"draft_json"`
}
type SaveStepRequest struct {
	CurrentStep string `json:"current_step"`
}

func (s *CoursewareProjectService) Create(_ context.Context, ownerID, title string) (*model.CoursewareProject, error) {
	title = strings.TrimSpace(title)
	if title == "" || len([]rune(title)) > 200 {
		return nil, fmt.Errorf("title must be 1-200 characters")
	}
	p := &model.CoursewareProject{BaseModel: model.BaseModel{ID: uuid.NewString()}, OwnerID: ownerID, Title: title, CurrentStep: "s1_intent", Status: "draft", DraftJSON: model.JSONB(`{}`)}
	if err := s.db.Create(p).Error; err != nil {
		return nil, err
	}
	return p, nil
}

func (s *CoursewareProjectService) Get(ctx context.Context, ownerID, id string) (*model.CoursewareProject, error) {
	var p model.CoursewareProject
	if err := s.db.WithContext(ctx).Where("id = ? AND owner_id = ?", id, ownerID).First(&p).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrCoursewareProjectNotFound
		}
		return nil, err
	}
	return &p, nil
}

func (s *CoursewareProjectService) List(ctx context.Context, ownerID string, page, pageSize int) ([]model.CoursewareProject, int64, error) {
	var total int64
	q := s.db.WithContext(ctx).Model(&model.CoursewareProject{}).Where("owner_id = ?", ownerID)
	if err := q.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	var items []model.CoursewareProject
	err := q.Order("updated_at DESC, id DESC").Offset((page - 1) * pageSize).Limit(pageSize).Find(&items).Error
	return items, total, err
}

// Delete removes a project from the owner's active list. CoursewareProject uses
// GORM soft deletion, so an accidental removal remains recoverable by operators.
func (s *CoursewareProjectService) Delete(ctx context.Context, ownerID, id string) error {
	p, err := s.Get(ctx, ownerID, id)
	if err != nil {
		return err
	}
	return s.db.WithContext(ctx).Delete(p).Error
}

func (s *CoursewareProjectService) SaveDraft(ctx context.Context, ownerID, id string, raw json.RawMessage) (*model.CoursewareProject, error) {
	p, err := s.Get(ctx, ownerID, id)
	if err != nil {
		return nil, err
	}
	if p.Status == "archived" {
		return nil, ErrCoursewareProjectArchived
	}
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 || !json.Valid(trimmed) || string(trimmed) == "null" || trimmed[0] != '{' {
		return nil, fmt.Errorf("draft_json must be a JSON object")
	}
	if len(trimmed) > 5*1024*1024 {
		return nil, fmt.Errorf("draft_json exceeds 5 MB")
	}
	p.DraftJSON = model.JSONB(append([]byte(nil), trimmed...))
	p.Status = "active"
	if err := s.db.WithContext(ctx).Save(p).Error; err != nil {
		return nil, err
	}
	return p, nil
}

func (s *CoursewareProjectService) SaveStep(ctx context.Context, ownerID, id, step string) (*model.CoursewareProject, error) {
	p, err := s.Get(ctx, ownerID, id)
	if err != nil {
		return nil, err
	}
	if p.Status == "archived" {
		return nil, ErrCoursewareProjectArchived
	}
	if !validCoursewareSteps[step] {
		return nil, fmt.Errorf("invalid current_step")
	}
	p.CurrentStep = step
	p.Status = "active"
	if err := s.db.WithContext(ctx).Save(p).Error; err != nil {
		return nil, err
	}
	return p, nil
}

func (s *CoursewareProjectService) Context(ctx context.Context, ownerID, id string) (map[string]any, error) {
	p, err := s.Get(ctx, ownerID, id)
	if err != nil {
		return nil, err
	}
	return map[string]any{"project": p, "draft": json.RawMessage(p.DraftJSON), "current_step": p.CurrentStep, "generation_id": nullableString(p.GenID)}, nil
}

func nullableString(v string) any {
	if v == "" {
		return nil
	}
	return v
}

func (s *CoursewareProjectService) AttachGeneration(ctx context.Context, ownerID, id, genID string) error {
	p, err := s.Get(ctx, ownerID, id)
	if err != nil {
		return err
	}
	if p.Status == "archived" {
		return ErrCoursewareProjectArchived
	}
	p.GenID = genID
	p.Status = "active"
	return s.db.WithContext(ctx).Save(p).Error
}

func (s *CoursewareProjectService) FindByGeneration(ctx context.Context, ownerID, genID string) (*model.CoursewareProject, error) {
	var p model.CoursewareProject
	if err := s.db.WithContext(ctx).Where("gen_id = ? AND owner_id = ?", genID, ownerID).First(&p).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrCoursewareProjectNotFound
		}
		return nil, err
	}
	return &p, nil
}
