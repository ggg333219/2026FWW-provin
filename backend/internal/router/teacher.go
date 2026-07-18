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
	weakPointHandler *handler.WeakPointHandler) {

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
