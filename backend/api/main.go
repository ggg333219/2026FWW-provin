package main

import (
	"bytes"
	"fmt"
	"io"
	"path/filepath"
	"runtime"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	gormlogger "gorm.io/gorm/logger"

	"smart-teaching-backend/internal/database/sqlmigrate"
	"smart-teaching-backend/internal/handler"
	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/repository"
	"smart-teaching-backend/internal/service"
	"smart-teaching-backend/pkg/apiresp"
	"smart-teaching-backend/pkg/config"
	applogger "smart-teaching-backend/pkg/logger"
	"smart-teaching-backend/pkg/oss"
	
)

func main() {
	_, filename, _, _ := runtime.Caller(0)
	projectRoot := filepath.Dir(filepath.Dir(filename))

	cfg, err := config.LoadConfig(filepath.Join(projectRoot, "config"))
	if err != nil {
		fmt.Printf("加载配置失败: %v\n", err)
		return
	}

	err = applogger.InitLogger(
		cfg.Log.Level,
		filepath.Join(projectRoot, cfg.Log.Filename),
		cfg.Log.MaxSize,
		cfg.Log.MaxBackups,
		cfg.Log.MaxAge,
	)
	if err != nil {
		fmt.Printf("初始化日志失败: %v\n", err)
		return
	}

	applogger.Info("系统启动中...",
		zap.String("port", fmt.Sprintf("%d", cfg.Server.Port)),
		zap.String("mode", cfg.Server.Mode),
	)

	db, err := gorm.Open(postgres.Open(cfg.Database.DSN()), &gorm.Config{
		Logger: gormlogger.Default.LogMode(gormlogger.Info),
	})
	if err != nil {
		applogger.Sugar.Fatalf("连接数据库失败: %v", err)
	}

	err = db.AutoMigrate(
		&model.Course{},
		&model.CoursePage{},
		&model.TeachingNode{},
		&model.TeachingNodeRelation{},
		&model.UserProgress{},
		&model.DialogueSession{},
		&model.DialogueTurn{},
		&model.AudioAsset{},
		&model.PlatformUser{},
		&model.TeachingCourse{},
		&model.CourseClass{},
		&model.CourseEnrollment{},
		&model.QuestionLog{},
		&model.TeacherEdit{},
		&model.MindMapNode{},
		&model.StudentNote{},
		&model.StudentFavorite{},
		&model.PracticeTask{},
		&model.PracticeAttempt{},
		&model.ReviewPlan{},
		&model.ReviewPlanItem{},
		&model.ScheduledTask{},
		&model.WeakPoint{},
		&model.KnowledgePoint{},
		&model.StudentKnowledgeMastery{},
		&model.Question{},
		&model.AnswerRecord{},
		&model.NodeFavorite{},
		&model.User{},
		&model.StudentKnowledgeMap{},
		&model.Notification{},
		&model.TaskStatus{},
	)
	if err != nil {
		applogger.Sugar.Fatalf("数据库迁移失败: %v", err)
	}

	migrationsDir := filepath.Join(projectRoot, "internal", "database", "migrations")
	if err := sqlmigrate.Run(db, migrationsDir); err != nil {
		applogger.Sugar.Fatalf("SQL 版本迁移失败: %v", err)
	}

	if err = model.RunPostMigrateBackfill(db); err != nil {
		applogger.Sugar.Fatalf("数据库回填失败: %v", err)
	}

	if err = service.BackfillTeachingNodeRelationsForAllCourses(db); err != nil {
		applogger.Sugar.Fatalf("知识节点关联回填失败: %v", err)
	}

	applogger.Info("数据库连接成功", zap.String("database", cfg.Database.DBName))

	if _, err := repository.InitRedis(&cfg.Redis); err != nil {
		applogger.Sugar.Fatalf("连接Redis失败: %v", err)
	}
	applogger.Info("Redis连接成功")

	minioClient, err := oss.NewMinioClient(&cfg.OSS)
	if err != nil {
		applogger.Sugar.Fatalf("初始化MinIO失败: 初始化MinIO失败: %v", err)
	}
	applogger.Info("MinIO连接成功")

	// 根据配置选择 AI 客户端（Dify 或本地 AI 引擎）
	var aiClient service.AIEngine
	if cfg.AI.UseDify {
		if cfg.AI.DifyBaseURL == "" {
			cfg.AI.DifyBaseURL = "http://127.0.0.1:18001"
		}
		aiClient = service.NewDifyClient(cfg.AI.DifyBaseURL, cfg.AI.DifyAPIKey)
		applogger.Sugar.Infof("使用 Dify AI 客户端: %s", cfg.AI.DifyBaseURL)
	} else {
		aiClient = service.NewAIEngineClient(cfg.AI.BaseURL, cfg.AI.Timeout)
		applogger.Sugar.Infof("使用本地 AI 引擎客户端: %s", cfg.AI.BaseURL)
	}

	courseService := service.NewCourseService(db, minioClient, aiClient)

	// 初始化新的服务
	knowledgeMapService := service.NewKnowledgeMapService(db)
	notificationService := service.NewNotificationService(db)
	taskSchedulerService := service.NewTaskSchedulerService(db)
	if err := taskSchedulerService.Start(); err != nil {
		applogger.Sugar.Fatalf("启动任务调度器失败: %v", err)
	}
	applogger.Info("任务调度器启动成功")

	courseHandler := handler.NewCourseHandler(courseService, db)
	teacherHandler := handler.NewTeacherHandler(db, aiClient)
	studentHandler := handler.NewStudentHandler(db, aiClient)
	weakPointHandler := handler.NewWeakPointHandler(db, aiClient)
	compatHandler := handler.NewCompatibilityHandler(db, aiClient, courseService)
	authHandler := handler.NewAuthHandler(db)

	// 初始化新的处理器
	knowledgeMapHandler := handler.NewKnowledgeMapHandler(knowledgeMapService)
	notificationHandler := handler.NewNotificationHandler(notificationService, taskSchedulerService)
	taskSchedulerHandler := handler.NewTaskSchedulerHandler(taskSchedulerService)

	if cfg.Server.Mode == "release" {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.New()
	r.Use(gin.Recovery())

	// JWT 身份验证中间件（对 /api/v1 下非公开接口生效）
	r.Use(handler.JWTAuthMiddleware())

	r.Use(func(c *gin.Context) {
		// 课件单页预览可能返回 302 图片地址或 PNG 二进制，不能强行声明为 JSON。
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

	r.Use(func(c *gin.Context) {
		start := time.Now()
		c.Next()
		latency := time.Since(start)

		applogger.Info("HTTP请求",
			zap.String("method", c.Request.Method),
			zap.String("path", c.Request.URL.Path),
			zap.Int("status", c.Writer.Status()),
			zap.Duration("latency", latency),
			zap.String("client_ip", c.ClientIP()),
		)
	})

	r.GET("/health", func(c *gin.Context) {
		apiresp.OK(c, "ok", gin.H{"status": "ok", "time": time.Now().Format("2006-01-02 15:04:05")})
	})

	api := r.Group("/api")
	{
		api.GET("/courseware/:courseId/page/:pageNum", courseHandler.GetPagePreview)
		api.GET("/courseware/:courseId/pages", courseHandler.GetCoursePages)

		legacyTeacher := api.Group("/teacher")
		{
			legacyTeacher.GET("/courseware-list", teacherHandler.GetCoursewareList)
			legacyTeacher.POST("/upload-courseware", courseHandler.UploadCourse)
			legacyTeacher.DELETE("/courseware/:courseId", courseHandler.DeleteCourse)
			legacyTeacher.POST("/publish-courseware", teacherHandler.PublishCourseware)
			legacyTeacher.GET("/script/:courseId/:page", teacherHandler.GetScript)
			legacyTeacher.POST("/script/save", teacherHandler.SaveScript)
			legacyTeacher.POST("/ai-generate-script", teacherHandler.AIGenerateScript)
			legacyTeacher.GET("/student-stats/:courseId", teacherHandler.GetStudentStats)
			legacyTeacher.GET("/question-records/:courseId", teacherHandler.GetQuestionRecords)
			legacyTeacher.GET("/card-data/:courseId", teacherHandler.GetCardData)
		}

		legacyStudent := api.Group("/student")
		{
			legacyStudent.GET("/courseware-list", compatHandler.GetStudentCoursewareList)
			legacyStudent.POST("/session/start", compatHandler.StartStudentSession)
			legacyStudent.POST("/progress/update", compatHandler.UpdateStudentProgress)
			legacyStudent.GET("/script/:courseId/:page", compatHandler.GetStudentScript)
			legacyStudent.POST("/qa/stream", compatHandler.StreamStudentQA)

			legacyStudent.POST("/courseware/page", studentHandler.GetCoursewarePage)
			legacyStudent.POST("/ai/question", studentHandler.AskAIQuestion)
			legacyStudent.POST("/ai/traceQuestion", studentHandler.TraceAIQuestion)
			legacyStudent.GET("/studyData", studentHandler.GetStudentStudyData)
			legacyStudent.GET("/breakpoint", studentHandler.GetStudentBreakpoint)
			legacyStudent.PUT("/breakpoint", studentHandler.UpdateStudentBreakpoint)
			legacyStudent.POST("/saveNote", studentHandler.SaveStudentNote)
		}

		legacyWeakPoint := api.Group("/weakPoint")
		{
			legacyWeakPoint.GET("/getList", weakPointHandler.GetWeakPointList)
			legacyWeakPoint.POST("/getExplain", weakPointHandler.GetWeakPointExplain)
			legacyWeakPoint.POST("/getTest", weakPointHandler.GenerateTest)
			legacyWeakPoint.POST("/checkAnswer", weakPointHandler.CheckAnswer)
		}

		api.POST("/ai/parseKnowledge", weakPointHandler.ParseKnowledge)

		v1 := api.Group("/v1")
		{
			auth := v1.Group("/auth")
			{
				auth.POST("/register", authHandler.Register)
				auth.POST("/login", authHandler.Login)
			}

			v1.GET("/courseware/:courseId/page/:pageNum", courseHandler.GetPagePreview)
			v1.GET("/courseware/:courseId/pages", courseHandler.GetCoursePages)
			teacherV1 := v1.Group("/teacher/coursewares")
			{
				teacherV1.GET("", teacherHandler.GetCoursewareList)
				teacherV1.GET("/", teacherHandler.GetCoursewareList)
				teacherV1.POST("/upload", compatHandler.UploadCoursewareV1)
				teacherV1.DELETE("/:courseId", compatHandler.DeleteCoursewareV1)
				teacherV1.GET("/:courseId/scripts/:pageNum", compatHandler.GetTeacherScriptV1)
				teacherV1.PUT("/:courseId/scripts/:pageNum", compatHandler.UpdateTeacherScriptV1)
				teacherV1.POST("/:courseId/scripts/ai-generate", compatHandler.AIGenerateTeacherScriptV1)
				teacherV1.POST("/:courseId/publish", compatHandler.PublishCoursewareV1)
				teacherV1.GET("/:courseId/stats", teacherHandler.GetClassStats)
				teacherV1.GET("/:courseId/questions", teacherHandler.GetQuestionRecords)
				teacherV1.GET("/:courseId/card-data", compatHandler.GetCardDataV1)
				teacherV1.GET("/:courseId/node-insights", compatHandler.GetNodeInsightsV1)
				teacherV1.POST("/:courseId/knowledge-graph/sync", compatHandler.SyncCourseKnowledgeGraphV1)
				teacherV1.GET("/:courseId/knowledge-graph/reference-health", compatHandler.GetTeachingNodeReferenceHealthV1)
				teacherV1.POST("/:courseId/knowledge-graph/reference-health/repair", compatHandler.PostTeachingNodeReferenceRepairV1)
			}

			aiV1 := v1.Group("/ai")
			{
				aiV1.POST("/parse-knowledge", compatHandler.ParseKnowledgeV1)
				coursewareAI := aiV1.Group("/coursewares")
				{
					coursewareAI.GET("/:courseId/knowledge-graph", compatHandler.GetKnowledgeGraphV1)
					coursewareAI.POST("/:courseId/ask", compatHandler.AskCoursewareV1)
				}
			}

			studentV1 := v1.Group("/student")
			{
				studentV1.GET("/coursewares", compatHandler.GetStudentCoursewareListV1)
				studentV1.POST("/sessions", compatHandler.StartStudentSessionV1)
				studentV1.POST("/sessions/progress", compatHandler.UpdateStudentProgressV1)
				studentV1.POST("/qa/stream", compatHandler.StreamStudentQAV1)
				studentV1.GET("/coursewares/:courseId/weak-points", compatHandler.GetWeakPointsV1)
				studentV1.GET("/coursewares/:courseId/scripts/:pageNum", compatHandler.GetStudentScriptV1)
				studentV1.GET("/weak-points/:weakPointId/explain", compatHandler.ExplainWeakPointV1)
				studentV1.POST("/weak-points/:weakPointId/generate-test", compatHandler.GenerateWeakPointTestV1)
				studentV1.POST("/tests/:questionId/check", compatHandler.CheckAnswerV1)
				studentV1.GET("/coursewares/:courseId/breakpoint", compatHandler.GetBreakpointV1)
				studentV1.PUT("/coursewares/:courseId/breakpoint", compatHandler.UpdateBreakpointV1)
				studentV1.POST("/coursewares/:courseId/notes", compatHandler.SaveNoteV1)
				studentV1.GET("/coursewares/:courseId/stats", compatHandler.GetStudyStatsV1)
				studentV1.GET("/notes", compatHandler.GetStudentNotesV1)
				studentV1.POST("/favorites", compatHandler.AddFavoriteV1)
				studentV1.GET("/favorites", compatHandler.GetFavoritesV1)
				studentV1.DELETE("/favorites/:favoriteId", compatHandler.DeleteFavoriteV1)
				studentV1.POST("/practice/generate", compatHandler.GeneratePracticeV1)
				studentV1.POST("/practice/submit", compatHandler.SubmitPracticeV1)
				studentV1.GET("/practice/history", compatHandler.GetPracticeHistoryV1)
				studentV1.GET("/practice/wrong-questions", compatHandler.GetWrongQuestionsV1)
				studentV1.POST("/practice/wrong-questions/:questionId/retry", compatHandler.RetryWrongQuestionV1)
				studentV1.POST("/review-plans", compatHandler.CreateReviewPlanV1)
				studentV1.GET("/review-plans", compatHandler.GetReviewPlansV1)
				studentV1.PUT("/review-plans/:planId", compatHandler.UpdateReviewPlanV1)
				studentV1.DELETE("/review-plans/:planId", compatHandler.DeleteReviewPlanV1)
				studentV1.POST("/review-plans/:planId/items", compatHandler.AddReviewPlanItemV1)
				studentV1.GET("/review-plans/:planId/items", compatHandler.GetReviewPlanItemsV1)
				studentV1.PUT("/review-plan-items/:itemId", compatHandler.UpdateReviewPlanItemV1)
				studentV1.DELETE("/review-plan-items/:itemId", compatHandler.DeleteReviewPlanItemV1)
				studentV1.DELETE("/notes/:noteId", compatHandler.DeleteStudentNoteV1)
				studentV1.POST("/nodes/:nodeId/explain", compatHandler.ExplainNodeV1)

				// 知识图谱相关路由
				knowledgeMap := studentV1.Group("/knowledge-map")
				{
					knowledgeMap.GET("", knowledgeMapHandler.GetKnowledgeMap)
					knowledgeMap.GET("/point", knowledgeMapHandler.GetKnowledgePointMastery)
					knowledgeMap.POST("/update", knowledgeMapHandler.UpdateMasteryScore)
					knowledgeMap.GET("/weak-points", knowledgeMapHandler.GetWeakKnowledgePoints)
					knowledgeMap.GET("/strong-points", knowledgeMapHandler.GetStrongKnowledgePoints)
					knowledgeMap.GET("/progress", knowledgeMapHandler.AnalyzeLearningProgress)
					knowledgeMap.GET("/recommendations", knowledgeMapHandler.RecommendNextStudy)
				}

				// 通知相关路由
				notifications := v1.Group("/notifications")
				{
					notifications.POST("", notificationHandler.CreateNotification)
					notifications.GET("", notificationHandler.GetNotifications)
					notifications.GET("/:id", notificationHandler.GetNotification)
					notifications.PUT("/:id/read", notificationHandler.MarkAsRead)
					notifications.PUT("/read-all", notificationHandler.MarkAllAsRead)
					notifications.DELETE("/:id", notificationHandler.DeleteNotification)
					notifications.GET("/unread-count", notificationHandler.GetUnreadCount)
					notifications.POST("/send-immediate", notificationHandler.SendImmediateNotification)
				}

				// 任务调度相关路由
				tasks := v1.Group("/tasks")
				{
					tasks.POST("/scheduled", taskSchedulerHandler.CreateScheduledTask)
					tasks.GET("/scheduled", taskSchedulerHandler.GetScheduledTasks)
					tasks.GET("/scheduled/:id", taskSchedulerHandler.GetScheduledTask)
					tasks.PUT("/scheduled/:id", taskSchedulerHandler.UpdateScheduledTask)
					tasks.DELETE("/scheduled/:id", taskSchedulerHandler.DeleteScheduledTask)
					tasks.POST("/scheduled/:id/execute", taskSchedulerHandler.ExecuteTaskNow)
					tasks.GET("/statuses", taskSchedulerHandler.GetTaskStatuses)
					tasks.GET("/statuses/:id", taskSchedulerHandler.GetTaskStatus)
				}
			}

			openLesson := v1.Group("/lesson")
			openLesson.Use(handler.OpenAPISignatureMiddleware())
			{
				openLesson.POST("/parse", compatHandler.OpenLessonParse)
				openLesson.POST("/generateScript", compatHandler.OpenGenerateScript)
				openLesson.POST("/generateAudio", compatHandler.OpenGenerateAudio)
			}

			openQA := v1.Group("/qa")
			openQA.Use(handler.OpenAPISignatureMiddleware())
			{
				openQA.POST("/interact", compatHandler.OpenQAInteract)
				openQA.POST("/voiceToText", compatHandler.OpenVoiceToText)
			}

			openProgress := v1.Group("/progress")
			openProgress.Use(handler.OpenAPISignatureMiddleware())
			{
				openProgress.POST("/track", compatHandler.OpenTrackProgress)
				openProgress.POST("/adjust", compatHandler.OpenAdjustProgress)
			}

			openPlatform := v1.Group("/platform")
			openPlatform.Use(handler.OpenAPISignatureMiddleware())
			{
				openPlatform.GET("/users", compatHandler.OpenPlatformUsers)
				openPlatform.GET("/users/:userId", compatHandler.OpenPlatformUserDetail)
				openPlatform.GET("/courses", compatHandler.OpenPlatformCourses)
				openPlatform.POST("/courses", compatHandler.OpenCreatePlatformCourse)
				openPlatform.GET("/courses/:courseId", compatHandler.OpenPlatformCourseDetail)
				openPlatform.PUT("/courses/:courseId", compatHandler.OpenUpdatePlatformCourse)
				openPlatform.DELETE("/courses/:courseId", compatHandler.OpenDeletePlatformCourse)
				openPlatform.GET("/classes", compatHandler.OpenPlatformClasses)
				openPlatform.POST("/classes", compatHandler.OpenCreatePlatformClass)
				openPlatform.GET("/classes/:classId", compatHandler.OpenPlatformClassDetail)
				openPlatform.PUT("/classes/:classId", compatHandler.OpenUpdatePlatformClass)
				openPlatform.DELETE("/classes/:classId", compatHandler.OpenDeletePlatformClass)
				openPlatform.GET("/enrollments", compatHandler.OpenPlatformEnrollments)
				openPlatform.POST("/enrollments", compatHandler.OpenCreatePlatformEnrollment)
				openPlatform.GET("/enrollments/:enrollmentId", compatHandler.OpenPlatformEnrollmentDetail)
				openPlatform.PUT("/enrollments/:enrollmentId", compatHandler.OpenUpdatePlatformEnrollment)
				openPlatform.DELETE("/enrollments/:enrollmentId", compatHandler.OpenDeletePlatformEnrollment)
				openPlatform.GET("/overview", compatHandler.OpenPlatformOverview)
				openPlatform.POST("/syncCourse", compatHandler.OpenSyncCourse)
				openPlatform.POST("/syncUser", compatHandler.OpenSyncUser)
			}
		}
	}

	addr := fmt.Sprintf(":%d", cfg.Server.Port)
	for _, route := range r.Routes() {
		applogger.Infof("Route: %s %s", route.Method, route.Path)
	}
	applogger.Sugar.Infof("服务器启动成功，访问地址: http://localhost%s", addr)
	applogger.Sugar.Infof("健康检查: http://localhost%s/health", addr)

	if err := r.Run(addr); err != nil {
		applogger.Sugar.Fatalf("服务器启动失败: %v", err)
	}
}
