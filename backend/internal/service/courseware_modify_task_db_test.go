package service

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

// Optional isolated-database contract test. Every test row is enclosed in an
// outer transaction and rolled back; only the additive task table persists.
func TestS4RealDBTaskMigrationAndAtomicSave(t *testing.T) {
	dsn := os.Getenv("A12_S4_TEST_DSN")
	if dsn == "" { t.Skip("A12_S4_TEST_DSN not configured") }
	db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{})
	if err != nil { t.Fatalf("database connection failed: %T", err) }
	if err := AutoMigrateCourseware(db); err != nil { t.Fatalf("courseware migration failed: %v", err) }
	if !db.Migrator().HasTable(&coursewareModifyTaskRow{}) { t.Fatal("courseware_modify_tasks missing") }

	tx := db.Begin()
	if tx.Error != nil { t.Fatal(tx.Error) }
	defer tx.Rollback()
	store := newGormCoursewareStore(tx)
	ctx := context.Background()
	projectID := "proj_s4_test_" + strings.ReplaceAll(uuid.NewString(), "-", "")[:12]
	project := &CoursewareProject{ProjectID: projectID, OwnerID: "s4_test", Title: "S4 transaction probe", Status: "draft", CreatedAt: time.Now(), UpdatedAt: time.Now()}
	if err := store.CreateProject(ctx, project); err != nil { t.Fatalf("create test project: %v", err) }
	before := []TeachingNodeItem{{NodeID: "node_1", Title: "First", Summary: "old"}, {NodeID: "node_2", Title: "Second", Summary: "stable"}}
	after := []TeachingNodeItem{{NodeID: "node_1", Title: "First", Summary: "new"}, {NodeID: "node_2", Title: "Second", Summary: "stable"}}
	beforeJSON, _ := json.Marshal(before)
	intentJSON, _ := json.Marshal(ModifyIntent{TargetIDs: []string{"node_1"}, Action: "rewrite"})
	task := &coursewareModifyTaskRow{TaskID: "mod_" + uuid.NewString(), ProjectID: projectID, ContentID: "content_s4_test", Instruction: "rewrite first body", BeforeJSON: string(beforeJSON), IntentJSON: string(intentJSON), Status: "processing", CreatedAt: time.Now()}
	if err := store.CreateModifyTask(ctx, task); err != nil { t.Fatalf("persist task: %v", err) }
	read, err := store.GetModifyTask(ctx, projectID, task.TaskID)
	if err != nil || read.Status != "processing" { t.Fatalf("read task: %+v %v", read, err) }
	result := &ModifyResult{TaskID: task.TaskID, Status: "done", AllNodes: after}
	if err := store.CompleteModifyTask(ctx, task, before, result); err != nil { t.Fatalf("complete task: %v", err) }
	if err := store.CompleteModifyTask(ctx, task, before, result); err != nil { t.Fatalf("idempotent completion: %v", err) }
	versions, err := store.ListVersions(ctx, projectID)
	if err != nil || len(versions) != 1 { t.Fatalf("expected exactly one version: %d %v", len(versions), err) }
	draft, err := store.GetDraft(ctx, projectID)
	if err != nil || !strings.Contains(draft, "new") { t.Fatalf("draft not updated: %v", err) }
	read, err = store.GetModifyTask(ctx, projectID, task.TaskID)
	if err != nil || read.Status != "done" || read.ResultJSON == "" { t.Fatalf("result not persisted: %+v %v", read, err) }

	if err := store.SaveDraft(ctx, projectID, "{invalid"); err != nil { t.Fatal(err) }
	failed := *task
	failed.TaskID = "mod_" + uuid.NewString()
	if err := store.CreateModifyTask(ctx, &failed); err != nil { t.Fatal(err) }
	if err := store.CompleteModifyTask(ctx, &failed, before, &ModifyResult{TaskID: failed.TaskID, Status: "done", AllNodes: after}); err == nil {
		t.Fatal("malformed draft should roll back version insert")
	}
	versions, err = store.ListVersions(ctx, projectID)
	if err != nil || len(versions) != 1 { t.Fatalf("failed save created a partial version: %d %v", len(versions), err) }
	read, err = store.GetModifyTask(ctx, projectID, failed.TaskID)
	if err != nil || read.Status != "processing" { t.Fatalf("failed transaction changed task status: %+v %v", read, err) }
}
