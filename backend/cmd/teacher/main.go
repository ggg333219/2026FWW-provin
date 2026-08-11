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

	"smart-teaching-backend/internal/handler"
	"smart-teaching-backend/internal/router"
	"smart-teaching-backend/internal/service"
	"smart-teaching-backend/pkg/config"
	applogger "smart-teaching-backend/pkg/logger"
	"smart-teaching-backend/pkg/oss"
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

	applogger.Info("教师端系统启动中...",
		zap.Int("port", 8082), // Default teacher port
	)
	aiClient := service.NewAIEngineClient(cfg.AI.BaseURL, cfg.AI.Timeout)

	db, err := gorm.Open(postgres.Open(cfg.Database.DSN()), &gorm.Config{
		Logger: gormlogger.Default.LogMode(gormlogger.Info),
	})
	if err != nil {
		applogger.Sugar.Warnf("数据库不可用，自动进入 S1 轻量模式: %v", err)
		runS1Standalone(cfg.Server.Mode, aiClient)
		return
	}

	minioClient, err := oss.NewMinioClient(&cfg.OSS)
	if err != nil {
		applogger.Sugar.Warnf("MinIO 不可用，自动进入 S1 轻量模式: %v", err)
		runS1Standalone(cfg.Server.Mode, aiClient)
		return
	}

	courseService := service.NewCourseService(db, minioClient, aiClient)

	courseHandler := handler.NewCourseHandler(courseService, db)
	teacherHandler := handler.NewTeacherHandler(db, aiClient)
	weakPointHandler := handler.NewWeakPointHandler(db, aiClient)
	compatHandler := handler.NewCompatibilityHandler(db, aiClient, courseService)

	// ---- 4 Skill + KB 新处理器 ----
	convHandler := handler.NewConversationHandler(aiClient)
	parseHandler := handler.NewParseHandler(aiClient)
	knowledgeHandler := handler.NewKnowledgeHandler(aiClient)
	genHandler := handler.NewGenerationHandler(aiClient)
	versionHandler := handler.NewVersionHandler(aiClient)
	exportHandler := handler.NewExportHandler(aiClient)

	r := newBaseEngine(cfg.Server.Mode)

	api := r.Group("/api")
	router.RegisterTeacherRoutes(api, teacherHandler, courseHandler, compatHandler, weakPointHandler)

	// 4 Skill + KB 新路由（v1 子路由）
	skillV1 := api.Group("/v1")
	router.RegisterNewSkillRoutes(skillV1,
		convHandler, parseHandler, knowledgeHandler,
		genHandler, versionHandler, exportHandler,
	)

	applogger.Info("教师端服务运行中", zap.Int("port", 8082))
	if err := r.Run(":8082"); err != nil {
		applogger.Sugar.Fatalf("启动服务失败: %v", err)
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
func runS1Standalone(mode string, aiClient service.AIEngine) {
	r := newBaseEngine(mode)
	convHandler := handler.NewConversationHandler(aiClient)
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "UP", "mode": "s1-standalone"})
	})
	intent := r.Group("/api/v1/intent")
	intent.POST("/extract", convHandler.ExtractIntent)
	intent.POST("/confirm", convHandler.ConfirmIntent)

	applogger.Info("S1 轻量服务运行中（无需 PostgreSQL/MinIO）", zap.Int("port", 8082))
	if err := r.Run(":8082"); err != nil {
		applogger.Sugar.Fatalf("启动 S1 轻量服务失败: %v", err)
	}
}
