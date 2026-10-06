CREATE TABLE IF NOT EXISTS courseware_versions (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    owner_id VARCHAR(36) NOT NULL,
    version_no INTEGER NOT NULL,
    nodes_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    modify_instruction TEXT NOT NULL DEFAULT '',
    parsed_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    target_node_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    result_status VARCHAR(20) NOT NULL DEFAULT 'done',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_courseware_versions_project_version ON courseware_versions (project_id, version_no DESC);
CREATE INDEX IF NOT EXISTS idx_courseware_versions_owner ON courseware_versions (owner_id);
ALTER TABLE courseware_projects ADD COLUMN IF NOT EXISTS current_version INTEGER NOT NULL DEFAULT 1;
