package service

import (
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"

	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/pkg/logger"
)

const (
	TeachingRelationPrerequisite = "prerequisite"
	TeachingRelationSuccessor    = "successor"
	TeachingRelationRelated      = "related"
)

// ErrTeachingNodePrerequisiteCycle 表示 knowledge_nodes 中 prerequisite 边形成有向环。
var ErrTeachingNodePrerequisiteCycle = errors.New("teaching node prerequisite cycle")

// KnowledgeGraphService 课件级知识节点图：讲授节点 + 规范化边 + 与 KnowledgePoint 树并存。
type KnowledgeGraphService struct {
	db *gorm.DB
}

func NewKnowledgeGraphService(db *gorm.DB) *KnowledgeGraphService {
	return &KnowledgeGraphService{db: db}
}

// RebuildTeachingNodeRelations 根据 teaching_nodes 全量重算边：先删后插，幂等。
func (s *KnowledgeGraphService) RebuildTeachingNodeRelations(courseID string) error {
	return s.RebuildTeachingNodeRelationsTx(s.db, courseID)
}

// RebuildTeachingNodeRelationsTx 在指定 DB/事务会话内重建边，供与节点保存同一事务提交。
func (s *KnowledgeGraphService) RebuildTeachingNodeRelationsTx(db *gorm.DB, courseID string) error {
	courseID = strings.TrimSpace(courseID)
	if courseID == "" {
		return fmt.Errorf("courseID required")
	}

	var nodes []model.TeachingNode
	if err := db.Where("course_id = ?", courseID).
		Order("page_index ASC, sort_order ASC, created_at ASC, id ASC").
		Find(&nodes).Error; err != nil {
		return err
	}

	nodeSet := make(map[string]struct{}, len(nodes))
	for _, n := range nodes {
		id := strings.TrimSpace(n.NodeID)
		if id != "" {
			nodeSet[id] = struct{}{}
		}
	}

	edges := make(map[string]model.TeachingNodeRelation)

	addWeightedEdge := func(from, to, relType string, weight float32) {
		from, to = strings.TrimSpace(from), strings.TrimSpace(to)
		if from == "" || to == "" || from == to {
			return
		}
		if _, ok := nodeSet[from]; !ok {
			return
		}
		if _, ok := nodeSet[to]; !ok {
			return
		}
		if weight <= 0 {
			weight = 1
		}
		key := courseID + "\x00" + from + "\x00" + to + "\x00" + relType
		if existing, dup := edges[key]; dup {
			if weight > existing.Weight {
				existing.Weight = weight
				edges[key] = existing
			}
			return
		}
		edges[key] = model.TeachingNodeRelation{
			CourseID:     courseID,
			FromNodeID:   from,
			ToNodeID:     to,
			RelationType: relType,
			Weight:       weight,
		}
	}

	for _, n := range nodes {
		parsePrerequisiteEdgesWeighted(n.KnowledgeNodesJSON, nodeSet, addWeightedEdge)
	}

	for i := 0; i < len(nodes)-1; i++ {
		a := strings.TrimSpace(nodes[i].NodeID)
		b := strings.TrimSpace(nodes[i+1].NodeID)
		addWeightedEdge(a, b, TeachingRelationSuccessor, 1)
	}

	if PrerequisiteGraphHasCycle(edges) {
		return fmt.Errorf("%w: 请检查 knowledge_nodes 中的 prerequisites", ErrTeachingNodePrerequisiteCycle)
	}

	return db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Unscoped().Where("course_id = ?", courseID).Delete(&model.TeachingNodeRelation{}).Error; err != nil {
			return err
		}
		if len(edges) == 0 {
			return nil
		}
		batch := make([]model.TeachingNodeRelation, 0, len(edges))
		for _, e := range edges {
			batch = append(batch, e)
		}
		sort.Slice(batch, func(i, j int) bool {
			if batch[i].FromNodeID != batch[j].FromNodeID {
				return batch[i].FromNodeID < batch[j].FromNodeID
			}
			if batch[i].ToNodeID != batch[j].ToNodeID {
				return batch[i].ToNodeID < batch[j].ToNodeID
			}
			return batch[i].RelationType < batch[j].RelationType
		})
		return tx.Create(&batch).Error
	})
}

// PrerequisiteGraphHasCycle 仅针对 prerequisite 边检测有向环。
func PrerequisiteGraphHasCycle(edges map[string]model.TeachingNodeRelation) bool {
	adj := make(map[string][]string)
	nodeMark := make(map[string]struct{})
	for _, e := range edges {
		if e.RelationType != TeachingRelationPrerequisite {
			continue
		}
		f, t := strings.TrimSpace(e.FromNodeID), strings.TrimSpace(e.ToNodeID)
		if f == "" || t == "" {
			continue
		}
		adj[f] = append(adj[f], t)
		nodeMark[f] = struct{}{}
		nodeMark[t] = struct{}{}
	}
	state := make(map[string]int8) // 0=未访问 1=栈中 2=完成
	var dfs func(string) bool
	dfs = func(u string) bool {
		if state[u] == 1 {
			return true
		}
		if state[u] == 2 {
			return false
		}
		state[u] = 1
		for _, v := range adj[u] {
			if dfs(v) {
				return true
			}
		}
		state[u] = 2
		return false
	}
	for n := range nodeMark {
		if state[n] == 0 && dfs(n) {
			return true
		}
	}
	return false
}

// BackfillTeachingNodeRelationsForAllCourses 启动迁移后为每个有讲授节点的课件重建关联边。
func BackfillTeachingNodeRelationsForAllCourses(db *gorm.DB) error {
	var courseIDs []string
	if err := db.Model(&model.TeachingNode{}).Distinct("course_id").Pluck("course_id", &courseIDs).Error; err != nil {
		return err
	}
	kg := NewKnowledgeGraphService(db)
	for _, cid := range courseIDs {
		if strings.TrimSpace(cid) == "" {
			continue
		}
		if err := kg.RebuildTeachingNodeRelations(cid); err != nil {
			// 历史脏数据可能含环，不阻塞整库启动
			logger.Warnf("teaching_node_relations 回填跳过 course=%s: %v", cid, err)
		}
	}
	return nil
}

func parsePrerequisiteEdgesWeighted(raw string, nodeSet map[string]struct{}, addEdge func(from, to, relType string, weight float32)) {
	raw = strings.TrimSpace(raw)
	if raw == "" || raw == "[]" {
		return
	}
	var entries []map[string]any
	if err := json.Unmarshal([]byte(raw), &entries); err != nil {
		return
	}
	for _, entry := range entries {
		target := strings.TrimSpace(fmt.Sprintf("%v", entry["node_id"]))
		if target == "" {
			continue
		}
		if _, ok := nodeSet[target]; !ok {
			continue
		}
		prereqRaw, ok := entry["prerequisites"].([]any)
		if ok {
			weightsMap := parsePrerequisiteWeightsMap(entry["prerequisite_weights"])
			for _, item := range prereqRaw {
				from, w := parsePrerequisiteItem(item, weightsMap)
				if from == "" || from == target {
					continue
				}
				addEdge(from, target, TeachingRelationPrerequisite, w)
			}
		}
		relatedRaw, ok := entry["related_node_ids"].([]any)
		if ok {
			for _, item := range relatedRaw {
				other := strings.TrimSpace(fmt.Sprintf("%v", item))
				if other == "" || other == target {
					continue
				}
				addEdge(target, other, TeachingRelationRelated, 1)
			}
		}
	}
}

func parsePrerequisiteWeightsMap(v any) map[string]float32 {
	out := make(map[string]float32)
	m, ok := v.(map[string]any)
	if !ok {
		return out
	}
	for k, val := range m {
		k = strings.TrimSpace(k)
		if k == "" {
			continue
		}
		switch t := val.(type) {
		case float64:
			out[k] = float32(t)
		case float32:
			out[k] = t
		case int:
			out[k] = float32(t)
		case int64:
			out[k] = float32(t)
		case string:
			var f float64
			if _, err := fmt.Sscanf(strings.TrimSpace(t), "%f", &f); err == nil {
				out[k] = float32(f)
			}
		}
	}
	return out
}

func parsePrerequisiteItem(item any, weightsByFrom map[string]float32) (id string, weight float32) {
	weight = 1
	switch t := item.(type) {
	case map[string]any:
		id = strings.TrimSpace(fmt.Sprintf("%v", firstNonEmptyKey(t, "node_id", "id", "from")))
		if id != "" {
			if w, ok := weightsByFrom[id]; ok && w > 0 {
				weight = w
			}
			if x := toFloat32Any(t["weight"]); x > 0 {
				weight = x
			}
		}
		return id, weight
	default:
		id = strings.TrimSpace(fmt.Sprintf("%v", item))
		if id != "" {
			if w, ok := weightsByFrom[id]; ok && w > 0 {
				weight = w
			}
		}
		return id, weight
	}
}

func firstNonEmptyKey(m map[string]any, keys ...string) string {
	for _, k := range keys {
		if v := strings.TrimSpace(fmt.Sprintf("%v", m[k])); v != "" && v != "<nil>" {
			return v
		}
	}
	return ""
}

func toFloat32Any(v any) float32 {
	switch t := v.(type) {
	case float64:
		return float32(t)
	case float32:
		return t
	case int:
		return float32(t)
	case int64:
		return float32(t)
	default:
		return 0
	}
}

// ListTeachingNodeRelations 返回某课件下已持久化的边。
func (s *KnowledgeGraphService) ListTeachingNodeRelations(courseID string) ([]model.TeachingNodeRelation, error) {
	var rows []model.TeachingNodeRelation
	err := s.db.Where("course_id = ?", strings.TrimSpace(courseID)).
		Order("relation_type ASC, from_node_id ASC, to_node_id ASC").
		Find(&rows).Error
	return rows, err
}

// ListTeachingNodesForGraph 讲授节点摘要列表（全课件）。
func (s *KnowledgeGraphService) ListTeachingNodesForGraph(courseID string) ([]model.TeachingNode, error) {
	var nodes []model.TeachingNode
	err := s.db.Where("course_id = ?", strings.TrimSpace(courseID)).
		Order("page_index ASC, sort_order ASC, created_at ASC, id ASC").
		Find(&nodes).Error
	return nodes, err
}

// TeachingNodeOrphanBucket 某张表/字段上引用到的、但不在 teaching_nodes 中的业务 node_id。
type TeachingNodeOrphanBucket struct {
	Source  string   `json:"source"`
	NodeIDs []string `json:"nodeIds"`
}

// TeachingNodeOrphanReport 课件级讲授节点引用健康扫描结果。
type TeachingNodeOrphanReport struct {
	CourseID       string                     `json:"courseId"`
	ValidNodeCount int                        `json:"validNodeCount"`
	Buckets        []TeachingNodeOrphanBucket `json:"buckets"`
	UnionOrphanIDs []string                   `json:"unionOrphanNodeIds"`
	HasOrphans     bool                       `json:"hasOrphans"`
}

type orphanNodeColumnSpec struct {
	source string
	model  any
	col    string
}

// ScanOrphanTeachingNodeReferences 扫描各业务表中 course_id 下的 node 引用，找出 teaching_nodes 中不存在的业务 node_id。
// 用于节点重命名/删除后的脏引用治理与联调排查（PostgreSQL：列名使用 snake_case）。
func (s *KnowledgeGraphService) ScanOrphanTeachingNodeReferences(courseID string) (*TeachingNodeOrphanReport, error) {
	courseID = strings.TrimSpace(courseID)
	if courseID == "" {
		return nil, fmt.Errorf("courseID required")
	}

	valid := make(map[string]struct{})
	var tnIDs []string
	if err := s.db.Model(&model.TeachingNode{}).Where("course_id = ?", courseID).Pluck("node_id", &tnIDs).Error; err != nil {
		return nil, err
	}
	for _, id := range tnIDs {
		id = strings.TrimSpace(id)
		if id != "" {
			valid[id] = struct{}{}
		}
	}

	specs := []orphanNodeColumnSpec{
		{"questions", &model.Question{}, "node_id"},
		{"question_logs", &model.QuestionLog{}, "node_id"},
		{"dialogue_turns", &model.DialogueTurn{}, "node_id"},
		{"dialogue_sessions", &model.DialogueSession{}, "current_node_id"},
		{"audio_assets", &model.AudioAsset{}, "node_id"},
		{"student_notes", &model.StudentNote{}, "node_id"},
		{"student_favorites", &model.StudentFavorite{}, "node_id"},
		{"practice_tasks", &model.PracticeTask{}, "node_id"},
		{"knowledge_points", &model.KnowledgePoint{}, "source_teaching_node_id"},
		{"node_favorites", &model.NodeFavorite{}, "node_id"},
		{"teaching_node_relations.from", &model.TeachingNodeRelation{}, "from_node_id"},
		{"teaching_node_relations.to", &model.TeachingNodeRelation{}, "to_node_id"},
	}

	union := make(map[string]struct{})
	var buckets []TeachingNodeOrphanBucket
	for _, sp := range specs {
		ids, err := distinctOrphanNodeIDsForCourse(s.db, courseID, valid, sp.model, sp.col)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", sp.source, err)
		}
		if len(ids) == 0 {
			continue
		}
		for _, id := range ids {
			union[id] = struct{}{}
		}
		buckets = append(buckets, TeachingNodeOrphanBucket{Source: sp.source, NodeIDs: ids})
	}

	unionSlice := make([]string, 0, len(union))
	for id := range union {
		unionSlice = append(unionSlice, id)
	}
	sort.Strings(unionSlice)

	return &TeachingNodeOrphanReport{
		CourseID:       courseID,
		ValidNodeCount: len(valid),
		Buckets:        buckets,
		UnionOrphanIDs: unionSlice,
		HasOrphans:     len(unionSlice) > 0,
	}, nil
}

func distinctOrphanNodeIDsForCourse(db *gorm.DB, courseID string, valid map[string]struct{}, m any, col string) ([]string, error) {
	q := db.Model(m).Where("course_id = ?", courseID).
		Where(col+" IS NOT NULL").
		Where("BTRIM("+col+") <> ?", "")

	if len(valid) > 0 {
		list := make([]string, 0, len(valid))
		for id := range valid {
			list = append(list, id)
		}
		sort.Strings(list)
		q = q.Where(col+" NOT IN ?", list)
	}

	var raw []string
	if err := q.Distinct(col).Pluck(col, &raw).Error; err != nil {
		return nil, err
	}
	outSet := make(map[string]struct{})
	for _, s := range raw {
		s = strings.TrimSpace(s)
		if s != "" {
			outSet[s] = struct{}{}
		}
	}
	out := make([]string, 0, len(outSet))
	for id := range outSet {
		out = append(out, id)
	}
	sort.Strings(out)
	return out, nil
}

// TeachingNodeRepairCount 单表修复影响行数。
type TeachingNodeRepairCount struct {
	Source       string `json:"source"`
	RowsAffected int64  `json:"rowsAffected"`
}

// TeachingNodeRepairReport 脏引用修复结果（清除非法 node 引用 + 重建关联边）。
type TeachingNodeRepairReport struct {
	CourseID          string                    `json:"courseId"`
	TargetOrphanIDs   []string                  `json:"targetOrphanNodeIds"`
	Counts            []TeachingNodeRepairCount `json:"counts"`
	GraphRebuilt      bool                      `json:"graphRebuilt"`
	GraphRebuildError string                    `json:"graphRebuildError,omitempty"`
}

// RepairOrphanTeachingNodeReferences 清除各表中对「不存在讲授节点」的引用，并尝试重建 teaching_node_relations。
// onlyThese 非空时仅处理与扫描结果交集内的 node_id；收藏类记录对孤儿节点做软删除，避免 UNIQUE(node_id) 清空冲突。
func (s *KnowledgeGraphService) RepairOrphanTeachingNodeReferences(courseID string, onlyThese []string) (*TeachingNodeRepairReport, error) {
	courseID = strings.TrimSpace(courseID)
	if courseID == "" {
		return nil, fmt.Errorf("courseID required")
	}

	scan, err := s.ScanOrphanTeachingNodeReferences(courseID)
	if err != nil {
		return nil, err
	}
	orphans := scan.UnionOrphanIDs
	if len(onlyThese) > 0 {
		want := make(map[string]struct{}, len(onlyThese))
		for _, x := range onlyThese {
			x = strings.TrimSpace(x)
			if x != "" {
				want[x] = struct{}{}
			}
		}
		filtered := make([]string, 0, len(orphans))
		for _, id := range orphans {
			if _, ok := want[id]; ok {
				filtered = append(filtered, id)
			}
		}
		orphans = filtered
	}
	if len(orphans) == 0 {
		return &TeachingNodeRepairReport{
			CourseID:        courseID,
			TargetOrphanIDs: nil,
			Counts:          nil,
			GraphRebuilt:    false,
		}, nil
	}

	var counts []TeachingNodeRepairCount
	err = s.db.Transaction(func(tx *gorm.DB) error {
		r := tx.Unscoped().Where("course_id = ? AND (from_node_id IN ? OR to_node_id IN ?)", courseID, orphans, orphans).
			Delete(&model.TeachingNodeRelation{})
		if r.Error != nil {
			return r.Error
		}
		counts = append(counts, TeachingNodeRepairCount{Source: "teaching_node_relations", RowsAffected: r.RowsAffected})

		steps := []struct {
			source string
			run    func() *gorm.DB
		}{
			{"questions", func() *gorm.DB {
				return tx.Model(&model.Question{}).Where("course_id = ? AND node_id IN ?", courseID, orphans).Update("node_id", "")
			}},
			{"question_logs", func() *gorm.DB {
				return tx.Model(&model.QuestionLog{}).Where("course_id = ? AND node_id IN ?", courseID, orphans).Update("node_id", "")
			}},
			{"dialogue_turns", func() *gorm.DB {
				return tx.Model(&model.DialogueTurn{}).Where("course_id = ? AND node_id IN ?", courseID, orphans).Update("node_id", "")
			}},
			{"dialogue_sessions", func() *gorm.DB {
				return tx.Model(&model.DialogueSession{}).Where("course_id = ? AND current_node_id IN ?", courseID, orphans).Update("current_node_id", "")
			}},
			{"audio_assets", func() *gorm.DB {
				return tx.Model(&model.AudioAsset{}).Where("course_id = ? AND node_id IN ?", courseID, orphans).Update("node_id", "")
			}},
			{"practice_tasks", func() *gorm.DB {
				return tx.Model(&model.PracticeTask{}).Where("course_id = ? AND node_id IN ?", courseID, orphans).Update("node_id", "")
			}},
			{"student_notes", func() *gorm.DB {
				return tx.Model(&model.StudentNote{}).Where("course_id = ? AND node_id IN ?", courseID, orphans).Update("node_id", "")
			}},
			{"knowledge_points", func() *gorm.DB {
				return tx.Model(&model.KnowledgePoint{}).Where("course_id = ? AND source_teaching_node_id IN ?", courseID, orphans).Update("source_teaching_node_id", "")
			}},
		}
		for _, step := range steps {
			res := step.run()
			if res.Error != nil {
				return fmt.Errorf("%s: %w", step.source, res.Error)
			}
			counts = append(counts, TeachingNodeRepairCount{Source: step.source, RowsAffected: res.RowsAffected})
		}

		df := tx.Where("course_id = ? AND node_id IN ?", courseID, orphans).Delete(&model.StudentFavorite{})
		if df.Error != nil {
			return fmt.Errorf("student_favorites: %w", df.Error)
		}
		counts = append(counts, TeachingNodeRepairCount{Source: "student_favorites", RowsAffected: df.RowsAffected})

		nf := tx.Where("course_id = ? AND node_id IN ?", courseID, orphans).Delete(&model.NodeFavorite{})
		if nf.Error != nil {
			return fmt.Errorf("node_favorites: %w", nf.Error)
		}
		counts = append(counts, TeachingNodeRepairCount{Source: "node_favorites", RowsAffected: nf.RowsAffected})

		return nil
	})
	if err != nil {
		return nil, err
	}

	out := &TeachingNodeRepairReport{
		CourseID:        courseID,
		TargetOrphanIDs: orphans,
		Counts:          counts,
	}
	if rebuildErr := s.RebuildTeachingNodeRelations(courseID); rebuildErr != nil {
		out.GraphRebuildError = rebuildErr.Error()
	} else {
		out.GraphRebuilt = true
	}
	return out, nil
}
