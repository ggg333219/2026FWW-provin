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
	// Adjusted path since it's now in cmd/teacher/
	projectRoot := filepath.Dir(filepath.Dir(filepath.Dir(filepath.Dir(filename))))

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

	courseHandler := handler.NewCourseHandler(courseService, db)
	teacherHandler := handler.NewTeacherHandler(db, aiClient)
	weakPointHandler := handler.NewWeakPointHandler(db, aiClient)
	compatHandler := handler.NewCompatibilityHandler(db, aiClient, courseService)

	if cfg.Server.Mode == "release" {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.New()
	r.Use(gin.Recovery())

	// CORS & Global Middlewares
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

	api := r.Group("/api")
	router.RegisterTeacherRoutes(api, teacherHandler, courseHandler, compatHandler, weakPointHandler)

	applogger.Info("教师端服务运行中", zap.Int("port", 8082))
	if err := r.Run(":8082"); err != nil {
		applogger.Sugar.Fatalf("启动服务失败: %v", err)
	}
}
