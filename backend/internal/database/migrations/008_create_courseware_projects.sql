CREATE TABLE IF NOT EXISTS courseware_projects (
    id VARCHAR(36) PRIMARY KEY,
    owner_id VARCHAR(36) NOT NULL,
    title VARCHAR(200) NOT NULL,
    current_step VARCHAR(30) NOT NULL DEFAULT 's1_intent',
    gen_id VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    draft_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_courseware_projects_owner_updated ON courseware_projects (owner_id, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_courseware_projects_gen_id ON courseware_projects (gen_id);
