-- C6: 持久化课件项目右侧 AI 修改对话。
-- 按 (project_id, message_id) 幂等，支持刷新页面和重复提交不产生重复气泡。
CREATE TABLE IF NOT EXISTS courseware_ai_messages (
    id BIGSERIAL PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    message_id VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    intent_json TEXT NOT NULL DEFAULT '',
    is_clarification BOOLEAN NOT NULL DEFAULT FALSE,
    is_summary BOOLEAN NOT NULL DEFAULT FALSE,
    is_error BOOLEAN NOT NULL DEFAULT FALSE,
    version_no INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uniq_courseware_ai_messages_project_message
        UNIQUE (project_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_courseware_ai_messages_project_created
    ON courseware_ai_messages (project_id, created_at ASC);
