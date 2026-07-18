-- 课件页内节点顺序查询（与 replaceTeachingNodes / loadTeachingNodesByPage 一致）
CREATE INDEX IF NOT EXISTS idx_teaching_nodes_course_page_sort
    ON teaching_nodes (course_id, page_index, sort_order);
