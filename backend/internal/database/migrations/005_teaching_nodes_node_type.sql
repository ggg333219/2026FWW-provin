-- teaching_nodes：持久化讲授节点类型（与接口 type / node_type 对齐）
ALTER TABLE teaching_nodes
    ADD COLUMN IF NOT EXISTS node_type VARCHAR(40);

CREATE INDEX IF NOT EXISTS idx_teaching_nodes_node_type ON teaching_nodes (node_type);
