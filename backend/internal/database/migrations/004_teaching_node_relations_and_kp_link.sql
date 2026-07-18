-- #53 知识节点关联：讲授节点之间的规范化边 + 知识点可选挂接讲授节点业务 ID
-- 与 GORM AutoMigrate 对齐；若仅用 AutoMigrate 可跳过手工执行。

CREATE TABLE IF NOT EXISTS teaching_node_relations (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    course_id VARCHAR(36) NOT NULL,
    from_node_id VARCHAR(100) NOT NULL,
    to_node_id VARCHAR(100) NOT NULL,
    relation_type VARCHAR(40) NOT NULL,
    weight REAL DEFAULT 1,
    metadata TEXT
);

-- 与 GORM uniqueIndex:idx_tnr_unique 一致（含软删列时以 ORM 迁移结果为准）
CREATE UNIQUE INDEX IF NOT EXISTS idx_tnr_unique
    ON teaching_node_relations (course_id, from_node_id, to_node_id, relation_type);

CREATE INDEX IF NOT EXISTS idx_tnr_course_from ON teaching_node_relations (course_id, from_node_id);

CREATE INDEX IF NOT EXISTS idx_teaching_node_relations_deleted_at ON teaching_node_relations (deleted_at);

ALTER TABLE knowledge_points
    ADD COLUMN IF NOT EXISTS source_teaching_node_id VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_knowledge_points_source_teaching_node
    ON knowledge_points (source_teaching_node_id);
