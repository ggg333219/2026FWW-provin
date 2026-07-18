-- Teacher feedback behavior tracking table
CREATE TABLE IF NOT EXISTS teacher_feedback (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    teacher_id VARCHAR(64) NOT NULL,
    resource_id VARCHAR(128) NOT NULL,
    action VARCHAR(16) NOT NULL CHECK (action IN ('click', 'favorite', 'ignore', 'refresh')),
    ts TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_teacher_feedback_teacher_ts
    ON teacher_feedback (teacher_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_teacher_feedback_resource
    ON teacher_feedback (resource_id);
