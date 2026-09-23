package main

import (
	"bytes"
	"fmt"
	"io"
	"path/filepath"
	"runtime"
	"strings"
	"unicode/utf8"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	gormlogger "gorm.io/gorm/logger"

	"smart-teaching-backend/internal/database/sqlmigrate"
	"smart-teaching-backend/internal/handler"
	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/router"
	"smart-teaching-backend/internal/service"
	"smart-teaching-backend/pkg/config"
	applogger "smart-teaching-backend/pkg/logger"
	"smart-teaching-backend/pkg/oss"
	"smart-teaching-backend/pkg/serveraddr"
)

func main() {
	_, filename, _, _ := runtime.Caller(0)
	// 本文件位于 backend/cmd/teacher/main.go，向上 3 级即为 backend 根目录。
	projectRoot := filepath.Dir(filepath.Dir(filepath.Dir(filename)))

	cfg, err := config.LoadConfig(filepath.Join(projectRoot, "config"))
	if err != nil {
		fmt.Printf("加载配置失败: %v\n", err)
		return
	}

	err = applogger.InitLogger(
		cfg.Log.Level,
		filepath.Join(projectRoot, "logs/teacher.log"),
		cfg.Log.MaxSize,
		cfg.Log.MaxBackups,
		cfg.Log.MaxAge,
	)
	if err != nil {
		fmt.Printf("初始化日志失败: %v\n", err)
		return
	}

	// 端口从配置读，不再写死 8082；实际被占用时会顺延（见 serveraddr.Serve）。
	applogger.Info("教师端系统启动中...",
		zap.Int("port", cfg.Server.Port),
		zap.String("mode", cfg.Server.Mode),
	)
	aiClient := service.NewAIEngineClient(cfg.AI.BaseURL, cfg.AI.Timeout)

	db, err := gorm.Open(postgres.Open(cfg.Database.DSN()), &gorm.Config{
		Logger: gormlogger.Default.LogMode(gormlogger.Info),
	})
	if err != nil {
		applogger.Sugar.Warnf("数据库不可用，自动进入 S1 轻量模式: %v", err)
		runS1Standalone(cfg.Server.Mode, cfg.Server.Port, projectRoot, aiClient)
		return
	}

	minioClient, err := oss.NewMinioClient(&cfg.OSS)
	if err != nil {
		applogger.Sugar.Warnf("MinIO 不可用，自动进入 S1 轻量模式: %v", err)
		runS1Standalone(cfg.Server.Mode, cfg.Server.Port, projectRoot, aiClient)
		return
	}

	courseService := service.NewCourseService(db, minioClient, aiClient)

	// ---- 数据库迁移 ----
	migrationsDir := filepath.Join(projectRoot, "internal", "database", "migrations")
	if err := sqlmigrate.Run(db, migrationsDir); err != nil {
		applogger.Warn("SQL 迁移失败，尝试 AutoMigrate", zap.Error(err))
	}
	if err := db.AutoMigrate(
		&model.User{},
		&model.Course{},
		&model.CoursewareProject{},
		&model.CoursePage{},
		&model.TeachingNode{},
		&model.TeachingNodeRelation{},
		&model.UserProgress{},
		&model.DialogueSession{},
		&model.AudioAsset{},
		&model.PlatformUser{},
		&model.TeachingCourse{},
		&model.CourseClass{},
		&model.CourseEnrollment{},
		&model.DialogueTurn{},
		&model.QuestionLog{},
		&model.TeacherEdit{},
		&model.MindMapNode{},
		&model.StudentNote{},
		&model.StudentFavorite{},
		&model.PracticeTask{},
		&model.PracticeAttempt{},
		&model.WeakPoint{},
		&model.KnowledgePoint{},
		&model.Question{},
		&model.AnswerRecord{},
		&model.ReviewPlan{},
		&model.ReviewPlanItem{},
		&model.StudentKnowledgeMap{},
		&model.StudentKnowledgeMastery{},
		&model.ScheduledTask{},
		&model.Notification{},
		&model.TaskStatus{},
		&model.NodeFavorite{},
	); err != nil {
		applogger.Warn("AutoMigrate 失败", zap.Error(err))
	}
	if err := model.RunPostMigrateBackfill(db); err != nil {
		applogger.Warn("数据库回填失败", zap.Error(err))
	}

	courseHandler := handler.NewCourseHandler(courseService, db)
	teacherHandler := handler.NewTeacherHandler(db, aiClient)
	knowledgeMapService := service.NewKnowledgeMapService(db)
	weakPointHandler := handler.NewWeakPointHandler(db, aiClient, knowledgeMapService)
	compatHandler := handler.NewCompatibilityHandler(db, aiClient, courseService)
	authHandler := handler.NewAuthHandler(db)

	// ---- 4 Skill + KB 新处理器 ----
	convHandler := handler.NewConversationHandler(aiClient)
	parseHandler := handler.NewParseHandler(aiClient)
	knowledgeHandler := handler.NewKnowledgeHandler(aiClient)
	// S3 大纲：db 就绪的完整模式走 Postgres 持久化（OutlineService 属跨重启状态管理）。
	if err := service.AutoMigrateOutline(db); err != nil {
		applogger.Warn("outline_versions 表迁移失败", zap.Error(err))
	}
	outlineService := service.NewOutlineServiceWithDB(aiClient, db)
	outlineHandler := handler.NewOutlineHandler(outlineService)
	genHandler := handler.NewGenerationHandler(aiClient, outlineService, service.NewCoursewareProjectService(db))
	interactiveHandler := handler.NewInteractiveHandler(aiClient)
	versionHandler := handler.NewVersionHandler(aiClient)
	exportHandler := handler.NewExportHandler(aiClient, service.NewCoursewareProjectService(db))
	contentHandler := handler.NewContentHandler(aiClient)
	// A1: 课件项目持久化（远程队友实现）
	coursewareProjectHandler := handler.NewCoursewareProjectHandler(service.NewCoursewareProjectService(db))
	// A6/A7: 修改对话 + 版本快照 + 回滚
	if err := service.AutoMigrateCourseware(db); err != nil {
		applogger.Warn("courseware 表迁移失败", zap.Error(err))
	}
	coursewareService := service.NewCoursewareServiceWithDB(aiClient, db)
	coursewareHandler := handler.NewCoursewareHandler(coursewareService)

	r := newBaseEngine(cfg.Server.Mode)

	// 前端 health 探测走根路径 /health（见 teacherApi.js / services/v1/index.js），
	// 而完整路由只注册了 /api/health。这里补一个根路径别名，避免被误判为后端离线。
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "UP"})
	})

	api := r.Group("/api")
	router.RegisterTeacherRoutes(api, teacherHandler, courseHandler, compatHandler, weakPointHandler, authHandler)

	// 4 Skill + KB 新路由（v1 子路由）
	skillV1 := api.Group("/v1")
	router.RegisterNewSkillRoutes(skillV1,
		convHandler, parseHandler, knowledgeHandler, outlineHandler,
		genHandler, interactiveHandler, versionHandler, exportHandler, contentHandler, coursewareProjectHandler, coursewareHandler,
	)

	applogger.Info("教师端服务运行中", zap.Int("port", cfg.Server.Port))
	if err := serveraddr.Serve(r, cfg.Server.Port, "teacher", projectRoot, applogger.Sugar.Warnf); err != nil {
		applogger.Sugar.Fatalf("启动教师端服务失败: %v", err)
	}
}

func newBaseEngine(mode string) *gin.Engine {
	if mode == "release" {
		gin.SetMode(gin.ReleaseMode)
	}
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(func(c *gin.Context) {
		p := c.Request.URL.Path
		if !(strings.Contains(p, "/courseware/") && strings.Contains(p, "/page/")) {
			c.Writer.Header().Set("Content-Type", "application/json; charset=utf-8")
		}
		c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	})
	r.Use(func(c *gin.Context) {
		bodyBytes, readErr := io.ReadAll(c.Request.Body)
		if readErr == nil && len(bodyBytes) > 0 {
			if !utf8.Valid(bodyBytes) {
				applogger.Warn("请求体包含非 UTF-8 字符")
			}
			c.Request.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
		}
		c.Next()
	})
	return r
}

// runS1Standalone 在 PostgreSQL/MinIO 未启动时只暴露 S1 所需路由。
// 这样前端仍然经过 Go Backend 调用 AI Engine，不会退化为直连 Python。
// preferredPort / runtimeDir 用于端口自动顺延与 .runtime 公告。
func runS1Standalone(mode string, preferredPort int, runtimeDir string, aiClient service.AIEngine) {
	r := newBaseEngine(mode)
	convHandler := handler.NewConversationHandler(aiClient)
	outlineService := service.NewOutlineService(aiClient)
	outlineHandler := handler.NewOutlineHandler(outlineService)
	genHandler := handler.NewGenerationHandler(aiClient, outlineService)
	versionHandler := handler.NewVersionHandler(aiClient)
	exportHandler := handler.NewExportHandler(aiClient)
	contentHandler := handler.NewContentHandler(aiClient)
	coursewareService := service.NewCoursewareService(aiClient)
	coursewareHandler := handler.NewCoursewareHandler(coursewareService)

	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "UP", "mode": "s1-standalone"})
	})

	// A6/A7: 课件项目 + 修改对话 + 版本快照（内存存储降级）
	coursewares := r.Group("/api/v1/coursewares")
	{
		coursewares.POST("", coursewareHandler.Create)
		coursewares.GET("", coursewareHandler.List)
		coursewares.DELETE("/:project_id", coursewareHandler.Delete)
		coursewares.GET("/:project_id/context", coursewareHandler.Context)
		coursewares.PUT("/:project_id/step", coursewareHandler.UpdateStep)
		coursewares.PUT("/:project_id/draft", coursewareHandler.SaveDraft)
		coursewares.GET("/:project_id/draft", coursewareHandler.GetDraft)
		coursewares.POST("/:project_id/modify", coursewareHandler.Modify)
		coursewares.GET("/:project_id/modify-history", coursewareHandler.ModifyHistory)
		coursewares.GET("/:project_id/versions", coursewareHandler.Versions)
		coursewares.POST("/:project_id/versions", coursewareHandler.CreateVersion)
		coursewares.GET("/:project_id/versions/:version_id", coursewareHandler.VersionDetail)
		coursewares.POST("/:project_id/rollback", coursewareHandler.Rollback)
		// 契约 v1.0 模块1：页面级资料绑定（降级模式落内存，进程重启即失）
		coursewares.PUT("/:project_id/page-bindings", coursewareHandler.PageBindingsPut)
		coursewares.GET("/:project_id/page-bindings", coursewareHandler.PageBindingsGet)
	}

	// S1: 意图理解
	intent := r.Group("/api/v1/intent")
	{
		intent.POST("/extract", convHandler.ExtractIntent)
		intent.POST("/confirm", convHandler.ConfirmIntent)
	}

	outlines := r.Group("/api/v1/outlines")
	{
		outlines.POST("", outlineHandler.Create)
		outlines.GET("/:outline_id", outlineHandler.Get)
		outlines.PUT("/:outline_id", outlineHandler.Save)
		outlines.POST("/:outline_id/revise", outlineHandler.Revise)
		outlines.POST("/:outline_id/confirm", outlineHandler.Confirm)
	}

	// S3: 课件生成
	gen := r.Group("/api/v1/gen")
	{
		gen.POST("/create", genHandler.Create)
		gen.GET("/status/:task_id", genHandler.Status)
		gen.POST("/preview", genHandler.PreviewHTML)
		gen.GET("/preview/:gen_id", genHandler.Preview)
		gen.POST("/modify", genHandler.Modify)
		gen.POST("/finalize", genHandler.Finalize)
	}

	// P1: S3 大纲 → 内容生成
	genContent := r.Group("/api/v1/gen")
	{
		genContent.POST("/content", contentHandler.Create)
		genContent.GET("/content/status/:content_id", contentHandler.Status)
		genContent.POST("/content/modify", contentHandler.Modify)
	}

	// S4: 版本管理
	ver := r.Group("/api/v1/version")
	{
		ver.GET("/:gen_id", versionHandler.Load)
		ver.GET("/:gen_id/history", versionHandler.History)
		ver.POST("/:gen_id/rollback", versionHandler.Rollback)
		ver.POST("/:gen_id/lock", versionHandler.Lock)
	}

	// S4: 导出
	exp := r.Group("/api/v1/export")
	{
		exp.POST("/:gen_id", exportHandler.Create)
		exp.GET("/status/:job_id", exportHandler.Status)
		exp.GET("/download/:job_id/:extension", exportHandler.Download)
	}

	applogger.Info("S1 轻量服务运行中（无需 PostgreSQL/MinIO）", zap.Int("port", preferredPort))
	if err := serveraddr.Serve(r, preferredPort, "teacher", runtimeDir, applogger.Sugar.Warnf); err != nil {
		applogger.Sugar.Fatalf("启动 S1 轻量服务失败: %v", err)
	}
}
