package model

import (
	"fmt"

	"gorm.io/gorm"

	"smart-teaching-backend/pkg/logger"
)

// RunPostMigrateBackfill executes idempotent data backfills after schema migration.
// It keeps legacy data compatible with strict node/mapping validations.
func RunPostMigrateBackfill(db *gorm.DB) error {
	if db == nil {
		return nil
	}

	steps := []struct {
		name string
		run  func(*gorm.DB) error
	}{
		{name: "teaching_nodes schema_version", run: backfillTeachingNodeSchemaVersion},
		{name: "teaching_nodes json defaults", run: backfillTeachingNodeJSONDefaults},
		{name: "teaching_nodes missing node_id", run: backfillTeachingNodeNodeID},
		{name: "question_logs missing node_id", run: backfillQuestionLogNodeID},
		{name: "dialogue_turns missing node_id", run: backfillDialogueTurnNodeID},
		{name: "dialogue_sessions current_node_id", run: backfillDialogueSessionCurrentNodeID},
	}

	for _, step := range steps {
		if err := step.run(db); err != nil {
			return fmt.Errorf("post-migrate backfill failed on %s: %w", step.name, err)
		}
	}

	logger.Infof("post-migrate backfill finished")
	return nil
}

func backfillTeachingNodeSchemaVersion(db *gorm.DB) error {
	return db.Model(&TeachingNode{}).
		Where("schema_version IS NULL OR schema_version <= ?", 0).
		Update("schema_version", 2).Error
}

func backfillTeachingNodeJSONDefaults(db *gorm.DB) error {
	if err := db.Model(&TeachingNode{}).
		Where("knowledge_nodes_json IS NULL OR btrim(knowledge_nodes_json) = ''").
		Update("knowledge_nodes_json", "[]").Error; err != nil {
		return err
	}
	if err := db.Model(&TeachingNode{}).
		Where("script_segments_json IS NULL OR btrim(script_segments_json) = ''").
		Update("script_segments_json", "[]").Error; err != nil {
		return err
	}
	if err := db.Model(&TeachingNode{}).
		Where("structured_markdown IS NULL").
		Update("structured_markdown", "").Error; err != nil {
		return err
	}
	if err := db.Model(&TeachingNode{}).
		Where("script_text IS NULL").
		Update("script_text", "").Error; err != nil {
		return err
	}
	return nil
}

func backfillTeachingNodeNodeID(db *gorm.DB) error {
	return db.Exec(`
WITH missing_nodes AS (
	SELECT
		id,
		CONCAT('legacy_', REPLACE(id::text, '-', '')) AS generated_node_id
	FROM teaching_nodes
	WHERE COALESCE(btrim(node_id), '') = ''
)
UPDATE teaching_nodes t
SET node_id = m.generated_node_id
FROM missing_nodes m
WHERE t.id = m.id
`).Error
}

func backfillQuestionLogNodeID(db *gorm.DB) error {
	return db.Exec(`
WITH preferred_node AS (
	SELECT
		course_id,
		page_index,
		node_id,
		ROW_NUMBER() OVER (
			PARTITION BY course_id, page_index
			ORDER BY sort_order ASC, created_at ASC, id ASC
		) AS rn
	FROM teaching_nodes
	WHERE COALESCE(btrim(node_id), '') <> ''
), picked AS (
	SELECT course_id, page_index, node_id
	FROM preferred_node
	WHERE rn = 1
)
UPDATE question_logs q
SET node_id = p.node_id
FROM picked p
WHERE q.course_id = p.course_id
	AND q.page_index = p.page_index
	AND COALESCE(btrim(q.node_id), '') = ''
`).Error
}

func backfillDialogueTurnNodeID(db *gorm.DB) error {
	return db.Exec(`
WITH preferred_node AS (
	SELECT
		course_id,
		page_index,
		node_id,
		ROW_NUMBER() OVER (
			PARTITION BY course_id, page_index
			ORDER BY sort_order ASC, created_at ASC, id ASC
		) AS rn
	FROM teaching_nodes
	WHERE COALESCE(btrim(node_id), '') <> ''
), picked AS (
	SELECT course_id, page_index, node_id
	FROM preferred_node
	WHERE rn = 1
)
UPDATE dialogue_turns d
SET node_id = p.node_id
FROM picked p
WHERE d.course_id = p.course_id
	AND d.page_index = p.page_index
	AND COALESCE(btrim(d.node_id), '') = ''
`).Error
}

func backfillDialogueSessionCurrentNodeID(db *gorm.DB) error {
	return db.Exec(`
UPDATE dialogue_sessions s
SET current_node_id = latest.node_id
FROM (
	SELECT DISTINCT ON (session_id)
		session_id,
		node_id
	FROM dialogue_turns
	WHERE COALESCE(btrim(node_id), '') <> ''
	ORDER BY session_id, turn_index DESC, created_at DESC
) latest
WHERE s.id = latest.session_id
	AND COALESCE(btrim(s.current_node_id), '') = ''
`).Error
}
