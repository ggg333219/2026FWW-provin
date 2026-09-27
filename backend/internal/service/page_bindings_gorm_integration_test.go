package service

import (
	"context"
	"os"
	"testing"
	"time"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

// 真实 PostgreSQL 集成验证（模块1 的持久化验收：刷新页面后绑定关系仍在）。
//
// 默认跳过——单测走 mem store，只有连真实库时才能验证 AutoMigrate 建的表、
// gorm 的 ON CONFLICT upsert SQL，以及版本/草稿/页面绑定三张子表是否真的被创建。
//
// 用法：
//
//	docker compose --env-file .env.test -f docker-compose.test.yml up -d postgres
//	COURSEWARE_PG_DSN="postgres://postgres:123456@127.0.0.1:25432/teaching_test?sslmode=disable" \
//	    go test ./internal/service/ -run 'TestPageBindings' -count=1 -v
func TestPageBindingsPersistAcrossReconnect(t *testing.T) {
	dsn := os.Getenv("COURSEWARE_PG_DSN")
	if dsn == "" {
		t.Skip("未设置 COURSEWARE_PG_DSN，跳过真实库验证")
	}
	open := func() *gorm.DB {
		db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
		if err != nil {
			t.Fatalf("连接 PostgreSQL 失败: %v", err)
		}
		return db
	}
	closeDB := func(db *gorm.DB) {
		if sqlDB, err := db.DB(); err == nil {
			_ = sqlDB.Close()
		}
	}

	db := open()
	defer closeDB(db)

	if err := AutoMigrateCourseware(db); err != nil {
		t.Fatalf("AutoMigrateCourseware 失败（模块1 表建不出来，契约验收无法成立）: %v", err)
	}
	for _, row := range []interface{ TableName() string }{
		&coursewareProjectRow{}, &coursewareVersionRow{}, &coursewareDraftRow{}, &coursewarePageBindingRow{},
	} {
		if !db.Migrator().HasTable(row) {
			t.Fatalf("缺少表 %s：AutoMigrateCourseware 报告成功但表未创建", row.TableName())
		}
	}

	ctx := context.Background()
	svc := NewCoursewareServiceWithDB(nil, db)
	proj, err := svc.CreateProject(ctx, "teacher_test", "契约模块1集成测试")
	if err != nil {
		t.Fatalf("创建课件项目失败: %v", err)
	}
	t.Cleanup(func() { _ = svc.DeleteProject(context.Background(), proj.ProjectID) })

	if _, err := svc.SavePageBindings(ctx, proj.ProjectID, []PageEvidenceBinding{
		{PageID: "page_001", EvidenceRefs: []string{"chunk_001", "chunk_002"}, AutoBound: false, BoundBy: "user:teacher_test"},
		{PageID: "page_002", EvidenceRefs: []string{"chunk_003"}, AutoBound: true, BoundBy: "system:intent_keyword"},
	}); err != nil {
		t.Fatalf("保存页面绑定失败: %v", err)
	}

	// 重新建一个连接与 store，等价于"刷新页面 / 服务重启"后再读取。
	db2 := open()
	defer closeDB(db2)
	svc2 := NewCoursewareServiceWithDB(nil, db2)

	bindings, err := svc2.GetPageBindings(ctx, proj.ProjectID)
	if err != nil {
		t.Fatalf("重新连接后读取绑定失败: %v", err)
	}
	if len(bindings) != 2 {
		t.Fatalf("应有 2 个页面的绑定，实际 %d: %+v", len(bindings), bindings)
	}
	b1 := bindings["page_001"]
	if b1.PageID != "page_001" || len(b1.EvidenceRefs) != 2 || b1.AutoBound || b1.BoundBy != "user:teacher_test" {
		t.Fatalf("page_001 绑定未在库里持久化: %+v", b1)
	}
	if b1.EvidenceRefs[0] != "chunk_001" || b1.EvidenceRefs[1] != "chunk_002" {
		t.Fatalf("evidence_refs 未原样持久化: %v", b1.EvidenceRefs)
	}
	if time.Since(b1.BoundAt) > time.Hour || time.Since(b1.BoundAt) < 0 {
		t.Fatalf("bound_at 未在服务端填充: %v", b1.BoundAt)
	}
	b2 := bindings["page_002"]
	if len(b2.EvidenceRefs) != 1 || !b2.AutoBound || b2.BoundBy != "system:intent_keyword" {
		t.Fatalf("page_002 绑定未在库里持久化: %+v", b2)
	}

	// upsert：只更新 page_001（清空其证据），page_002 不应被触及。
	if _, err := svc2.SavePageBindings(ctx, proj.ProjectID, []PageEvidenceBinding{
		{PageID: "page_001", EvidenceRefs: []string{}},
	}); err != nil {
		t.Fatalf("二次保存绑定失败: %v", err)
	}
	again, err := svc2.GetPageBindings(ctx, proj.ProjectID)
	if err != nil {
		t.Fatalf("upsert 后读取绑定失败: %v", err)
	}
	if refs := again["page_001"].EvidenceRefs; len(refs) != 0 {
		t.Fatalf("page_001 证据应被清空，实际 %v", refs)
	}
	if refs := again["page_002"].EvidenceRefs; len(refs) != 1 || refs[0] != "chunk_003" {
		t.Fatalf("page_002 不应被本次保存影响，实际 %v", refs)
	}

	// 级联删除：项目删掉后页面绑定也应消失。
	if err := svc2.DeleteProject(ctx, proj.ProjectID); err != nil {
		t.Fatalf("删除项目失败: %v", err)
	}
	if _, err := svc2.GetPageBindings(ctx, proj.ProjectID); err == nil {
		t.Fatalf("项目删除后不应再能读取页面绑定")
	}
}
