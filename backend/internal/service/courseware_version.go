package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"smart-teaching-backend/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

type CoursewareVersion struct {
	ID                string      `gorm:"primaryKey;size:36" json:"version_id"`
	ProjectID         string      `gorm:"size:36;not null;index" json:"project_id"`
	OwnerID           string      `gorm:"size:36;not null;index" json:"owner_id"`
	VersionNo         int         `gorm:"not null" json:"version_no"`
	NodesSnapshot     model.JSONB `gorm:"type:jsonb;not null;default:'[]'" json:"nodes_snapshot"`
	ModifyInstruction string      `gorm:"type:text;not null" json:"modify_instruction"`
	ParsedActions     model.JSONB `gorm:"type:jsonb;not null;default:'[]'" json:"parsed_actions"`
	TargetNodeIDs     model.JSONB `gorm:"type:jsonb;not null;default:'[]'" json:"target_node_ids"`
	Confidence        float64     `gorm:"not null;default:0" json:"confidence"`
	ResultStatus      string      `gorm:"size:20;not null;default:'done'" json:"result_status"`
	CreatedAt         time.Time   `json:"created_at"`
}

type CoursewareVersionService struct{ db *gorm.DB }

func NewCoursewareVersionService(db *gorm.DB) *CoursewareVersionService {
	return &CoursewareVersionService{db: db}
}

type ModifyAudit struct {
	Actions       []string
	TargetNodeIDs []string
	Confidence    float64
}

func (s *CoursewareVersionService) ApplyModification(ctx context.Context, ownerID, projectID string, oldNodes, newDraft []byte, instruction string, audit ModifyAudit) (*CoursewareVersion, error) {
	var version CoursewareVersion
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var project model.CoursewareProject
		if err := tx.Where("id = ? AND owner_id = ?", projectID, ownerID).First(&project).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return ErrCoursewareProjectNotFound
			}
			return err
		}
		if project.Status == "archived" {
			return ErrCoursewareProjectArchived
		}
		if len(oldNodes) == 0 || !json.Valid(oldNodes) || len(newDraft) == 0 || !json.Valid(newDraft) {
			return fmt.Errorf("invalid modification snapshot")
		}
		actions, _ := json.Marshal(audit.Actions)
		targets, _ := json.Marshal(audit.TargetNodeIDs)
		version = CoursewareVersion{ID: uuid.NewString(), ProjectID: projectID, OwnerID: ownerID, VersionNo: project.CurrentVersion, NodesSnapshot: model.JSONB(append([]byte(nil), oldNodes...)), ModifyInstruction: instruction, ParsedActions: model.JSONB(actions), TargetNodeIDs: model.JSONB(targets), Confidence: audit.Confidence, ResultStatus: "done", CreatedAt: time.Now()}
		if err := tx.Create(&version).Error; err != nil {
			return err
		}
		project.DraftJSON = model.JSONB(append([]byte(nil), newDraft...))
		project.CurrentVersion++
		project.Status = "active"
		return tx.Save(&project).Error
	})
	if err != nil {
		return nil, err
	}
	return &version, nil
}

func (s *CoursewareVersionService) List(ctx context.Context, ownerID, projectID string) ([]CoursewareVersion, error) {
	var versions []CoursewareVersion
	if err := s.db.WithContext(ctx).Where("owner_id = ? AND project_id = ?", ownerID, projectID).Order("version_no ASC").Find(&versions).Error; err != nil {
		return nil, err
	}
	return versions, nil
}

func (s *CoursewareVersionService) Rollback(ctx context.Context, ownerID, projectID, versionID string, oldNodes, newDraft []byte) (*CoursewareVersion, error) {
	var created CoursewareVersion
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var target CoursewareVersion
		if err := tx.Where("id = ? AND owner_id = ? AND project_id = ?", versionID, ownerID, projectID).First(&target).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return ErrCoursewareProjectNotFound
			}
			return err
		}
		var project model.CoursewareProject
		if err := tx.Where("id = ? AND owner_id = ?", projectID, ownerID).First(&project).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return ErrCoursewareProjectNotFound
			}
			return err
		}
		if project.Status == "archived" {
			return ErrCoursewareProjectArchived
		}
		if len(oldNodes) == 0 || !json.Valid(oldNodes) || len(newDraft) == 0 || !json.Valid(newDraft) {
			return fmt.Errorf("invalid rollback snapshot")
		}
		created = CoursewareVersion{ID: uuid.NewString(), ProjectID: projectID, OwnerID: ownerID, VersionNo: project.CurrentVersion, NodesSnapshot: model.JSONB(append([]byte(nil), oldNodes...)), ModifyInstruction: fmt.Sprintf("rollback to version %d", target.VersionNo), ParsedActions: model.JSONB(`[]`), TargetNodeIDs: model.JSONB(`[]`), ResultStatus: "done", CreatedAt: time.Now()}
		if err := tx.Create(&created).Error; err != nil {
			return err
		}
		project.DraftJSON = model.JSONB(append([]byte(nil), newDraft...))
		project.CurrentVersion++
		project.Status = "active"
		return tx.Save(&project).Error
	})
	if err != nil {
		return nil, err
	}
	return &created, nil
}
