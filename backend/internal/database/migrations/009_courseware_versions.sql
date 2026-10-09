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

-- 兼容早期脚本创建的 courseware_versions（可能只有 version_id/project_id/
-- version_no/nodes_snapshot 等旧字段）。CREATE TABLE IF NOT EXISTS 不会补列，
-- 因此必须显式补齐 009 后续模型需要的字段，避免迁移链在旧库上中断。
ALTER TABLE courseware_versions
    ADD COLUMN IF NOT EXISTS id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS owner_id VARCHAR(36) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS parsed_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS target_node_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS result_status VARCHAR(20) NOT NULL DEFAULT 'done';

CREATE INDEX IF NOT EXISTS idx_courseware_versions_project_version ON courseware_versions (project_id, version_no DESC);
CREATE INDEX IF NOT EXISTS idx_courseware_versions_owner ON courseware_versions (owner_id);
ALTER TABLE courseware_projects ADD COLUMN IF NOT EXISTS current_version INTEGER NOT NULL DEFAULT 1;
