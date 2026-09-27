package main

import (
	"bytes"
	"fmt"
	"io"
	"path/filepath"
	"runtime"
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
	"smart-teaching-backend/pkg/serveraddr"
)

// 共享的 config.yaml 里写的是教师端端口，api 单体用 18080。
// 学生端没有独立配置文件时回退到拆分前的 8081，保持既有行为。
const (
	monolithDefaultPort = 18080 // 与 pkg/config setDefaults 的 server.port 一致
	defaultStudentPort  = 8081
)

func main() {
	_, filename, _, _ := runtime.Caller(0)
	// 本文件位于 backend/cmd/student/main.go，向上 3 级即为 backend 根目录。
	// 之前这里多了一级 Dir，会解析到仓库根目录；那里的 config/ 不存在，
	// resolveConfigFiles 对缺目录返回空列表而非报错，于是静默退回 viper 默认值
	// （database.host=localhost，而不是 docker-compose 里的 teaching-postgres）。
	projectRoot := filepath.Dir(filepath.Dir(filepath.Dir(filename)))

	cfg, err := config.LoadConfig(filepath.Join(projectRoot, "config"))
	if err != nil {
		fmt.Printf("加载配置失败: %v\n", err)
		return
	}

	err = applogger.InitLogger(
		cfg.Log.Level,
		filepath.Join(projectRoot, "logs/student.log"),
		cfg.Log.MaxSize,
		cfg.Log.MaxBackups,
		cfg.Log.MaxAge,
	)
	if err != nil {
		fmt.Printf("初始化日志失败: %v\n", err)
		return
	}

	// 端口从配置读，不再写死 8081；实际被占用时会顺延（见 serveraddr.Serve）。
	preferredPort := cfg.Server.Port
	if preferredPort == monolithDefaultPort {
		preferredPort = defaultStudentPort
	}
	applogger.Info("学生端系统启动中...",
		zap.Int("port", preferredPort),
		zap.String("mode", cfg.Server.Mode),
	)

	db, err := gorm.Open(postgres.Open(cfg.Database.DSN()), &gorm.Config{
		Logger: gormlogger.Default.LogMode(gormlogger.Info),
	})
	if err != nil {
		applogger.Sugar.Fatalf("连接数据库失败: %v", err)
	}

	minioClient, err := oss.NewMinioClient(&cfg.OSS)
	if err != nil {
		applogger.Sugar.Fatalf("初始化MinIO失败: %v", err)
	}

	aiClient := service.NewAIEngineClient(cfg.AI.BaseURL, cfg.AI.Timeout)
	courseService := service.NewCourseService(db, minioClient, aiClient)
	knowledgeMapService := service.NewKnowledgeMapService(db)
	knowledgeMapHandler := handler.NewKnowledgeMapHandler(knowledgeMapService)

	courseHandler := handler.NewCourseHandler(courseService, db)
	studentHandler := handler.NewStudentHandler(db, aiClient)
	weakPointHandler := handler.NewWeakPointHandler(db, aiClient, knowledgeMapService)
	compatHandler := handler.NewCompatibilityHandler(db, aiClient, courseService)

	if cfg.Server.Mode == "release" {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.New()
	r.Use(gin.Recovery())

	// CORS & Global Middlewares
	r.Use(func(c *gin.Context) {
		c.Writer.Header().Set("Content-Type", "application/json; charset=utf-8")
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

	api := r.Group("/api")
	router.RegisterStudentRoutes(api, studentHandler, compatHandler, weakPointHandler, courseHandler, knowledgeMapHandler)

	applogger.Info("学生端服务运行中", zap.Int("port", preferredPort))
	if err := serveraddr.Serve(r, preferredPort, "student", projectRoot, applogger.Sugar.Warnf); err != nil {
		applogger.Sugar.Fatalf("启动服务失败: %v", err)
	}
}
