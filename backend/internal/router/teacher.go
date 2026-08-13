package router

import (
	"smart-teaching-backend/internal/handler"
	"smart-teaching-backend/pkg/apiresp"

	"github.com/gin-gonic/gin"
)

func RegisterTeacherRoutes(api *gin.RouterGroup,
	teacherHandler *handler.TeacherHandler,
	courseHandler *handler.CourseHandler,
	compatHandler *handler.CompatibilityHandler,
	weakPointHandler *handler.WeakPointHandler,
	authHandler *handler.AuthHandler) {

	// Health Check
	api.GET("/health", func(c *gin.Context) {
		apiresp.OK(c, "ok", gin.H{"status": "UP"})
	})

	// Courseware preview (Shared but often used in teacher tools)
	api.GET("/courseware/:courseId/page/:pageNum", courseHandler.GetPagePreview)

	// Legacy Teacher Routes
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

	// Teacher V1 Routes
	v1 := api.Group("/v1")
	{
		// 注册/登录（前端 HomeLogin 调用）
		if authHandler != nil {
			authV1 := v1.Group("/auth")
			{
				authV1.POST("/register", authHandler.Register)
				authV1.POST("/login", authHandler.Login)
			}
		}

		v1.GET("/courseware/:courseId/page/:pageNum", courseHandler.GetPagePreview)

		teacherV1 := v1.Group("/teacher/coursewares")
		{
			teacherV1.GET("", teacherHandler.GetCoursewareList)
			teacherV1.GET("/", teacherHandler.GetCoursewareList)
			teacherV1.POST("/upload", compatHandler.UploadCoursewareV1)
			teacherV1.DELETE("/:courseId", compatHandler.DeleteCoursewareV1)
			teacherV1.GET("/:courseId/scripts/:pageNum", compatHandler.GetTeacherScriptV1)
			teacherV1.PUT("/:courseId/scripts/:pageNum", compatHandler.UpdateTeacherScriptV1)
			teacherV1.GET("/:courseId/pages/:pageNum/nodes", compatHandler.GetTeacherNodesV1)
			teacherV1.PUT("/:courseId/pages/:pageNum/nodes", compatHandler.UpdateTeacherNodesV1)
			teacherV1.POST("/:courseId/pages/:pageNum/audio", compatHandler.GenerateTeacherAudioV1)
			teacherV1.POST("/:courseId/scripts/ai-generate", compatHandler.AIGenerateTeacherScriptV1)
			teacherV1.POST("/:courseId/publish", compatHandler.PublishCoursewareV1)
			teacherV1.GET("/:courseId/stats", teacherHandler.GetClassStats)
			teacherV1.GET("/:courseId/questions", teacherHandler.GetQuestionRecords)
			teacherV1.GET("/:courseId/card-data", compatHandler.GetCardDataV1)
			teacherV1.POST("/:courseId/knowledge-graph/sync", compatHandler.SyncCourseKnowledgeGraphV1)
			teacherV1.GET("/:courseId/knowledge-graph/reference-health", compatHandler.GetTeachingNodeReferenceHealthV1)
			teacherV1.POST("/:courseId/knowledge-graph/reference-health/repair", compatHandler.PostTeachingNodeReferenceRepairV1)
		}

		// Specialized AI V1 for teachers
		aiV1 := v1.Group("/ai")
		{
			aiV1.POST("/parse-knowledge", compatHandler.ParseKnowledgeV1)
		}

		// ---- S2: 素材库（真实路由，替换前端 Mock 回退）----
		// materialApi.js 调用:
		//   GET    /api/v1/teacher/materials/search → 列表（keyword 过滤）
		//   GET    /api/v1/teacher/materials        → 列表
		//   GET    /api/v1/teacher/materials/:id    → 详情
		//   GET    /api/v1/teacher/materials/:id/chunks → 切片
		//   DELETE /api/v1/teacher/materials/:id    → 删除
		// 兼容前端 session 级"素材列表"：coursewares 同时返回 courseId + id，前端可直接消费。
		materials := v1.Group("/teacher/materials")
		{
			materials.GET("/search", teacherHandler.ListMaterials)
			materials.GET("", teacherHandler.ListMaterials)
			materials.GET("/", teacherHandler.ListMaterials)
			materials.GET("/:materialId", teacherHandler.GetMaterialDetail)
			materials.GET("/:materialId/chunks", teacherHandler.GetMaterialChunks)
			materials.DELETE("/:materialId", teacherHandler.DeleteMaterial)
		}

		api.POST("/ai/parseKnowledge", weakPointHandler.ParseKnowledge)

		// Open API Lessons (Typically a teacher/admin feature)
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
			// Add OpenAPI QA methods here if any
		}
	}
}

// RegisterNewSkillRoutes 注册 4 Skill + KB 的新路由
// 与旧路由共存，向后兼容
func RegisterNewSkillRoutes(
	v1 *gin.RouterGroup,
	convHandler *handler.ConversationHandler,
	parseHandler *handler.ParseHandler,
	knowledgeHandler *handler.KnowledgeHandler,
	genHandler *handler.GenerationHandler,
	versionHandler *handler.VersionHandler,
	exportHandler *handler.ExportHandler,
) {
	// ---- S1: 意图理解 ----
	intent := v1.Group("/intent")
	{
		intent.POST("/extract", convHandler.ExtractIntent)
		intent.POST("/confirm", convHandler.ConfirmIntent)
	}

	// ---- S2: 多模态解析 ----
	parse := v1.Group("/parse")
	{
		parse.POST("/upload", parseHandler.Upload)
		parse.POST("/process", parseHandler.ProcessFile)
		parse.GET("/status/:task_id", parseHandler.ParseStatus)
		parse.POST("/video", parseHandler.ProcessVideo)
	}

	// ---- KB: 知识库 RAG ----
	rag := v1.Group("/rag")
	{
		rag.POST("/search", knowledgeHandler.Search)
		rag.POST("/evidence", knowledgeHandler.Evidence)
	}
	knowledge := v1.Group("/knowledge")
	{
		knowledge.POST("/upload", knowledgeHandler.Upload)
	}

	// ---- S3: 课件生成 ----
	gen := v1.Group("/gen")
	{
		gen.POST("/create", genHandler.Create)
		gen.GET("/status/:task_id", genHandler.Status)
		gen.GET("/preview/:gen_id", genHandler.Preview)
		gen.POST("/modify/:gen_id", genHandler.Create) // 简化：后续拆为单独 modify handler
	}

	// ---- S4: 版本管理 ----
	ver := v1.Group("/version")
	{
		ver.GET("/:gen_id", versionHandler.Load)
		ver.GET("/:gen_id/history", versionHandler.History)
		ver.POST("/:gen_id/rollback", versionHandler.Rollback)
		ver.POST("/:gen_id/lock", versionHandler.Lock)
	}

	// ---- S4: 导出 ----
	exp := v1.Group("/export")
	{
		exp.POST("/:gen_id", exportHandler.Create)
		exp.GET("/status/:job_id", exportHandler.Status)
	}
}