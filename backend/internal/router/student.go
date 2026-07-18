package router

import (
	"smart-teaching-backend/internal/handler"
	"smart-teaching-backend/pkg/apiresp"

	"github.com/gin-gonic/gin"
)

func RegisterStudentRoutes(api *gin.RouterGroup,
	studentHandler *handler.StudentHandler,
	compatHandler *handler.CompatibilityHandler,
	weakPointHandler *handler.WeakPointHandler,
	courseHandler *handler.CourseHandler) {

	// Health Check
	api.GET("/health", func(c *gin.Context) {
		apiresp.OK(c, "ok", gin.H{"status": "UP"})
	})

	// Legacy Student Routes
	legacyStudent := api.Group("/student")
	{
		legacyStudent.GET("/courseware-list", compatHandler.GetStudentCoursewareList)
		legacyStudent.POST("/session/start", compatHandler.StartStudentSession)
		legacyStudent.POST("/progress/update", compatHandler.UpdateStudentProgress)
		legacyStudent.GET("/script/:courseId/:page", compatHandler.GetStudentScript)
		legacyStudent.GET("/script/:courseId/:page/audio", compatHandler.GetStudentPlaybackAudio)
		legacyStudent.POST("/qa/stream", compatHandler.StreamStudentQA)

		legacyStudent.POST("/courseware/page", studentHandler.GetCoursewarePage)
		legacyStudent.POST("/ai/question", studentHandler.AskAIQuestion)
		legacyStudent.POST("/ai/traceQuestion", studentHandler.TraceAIQuestion)
		legacyStudent.GET("/studyData", studentHandler.GetStudentStudyData)
		legacyStudent.GET("/breakpoint", studentHandler.GetStudentBreakpoint)
		legacyStudent.PUT("/breakpoint", studentHandler.UpdateStudentBreakpoint)
		legacyStudent.POST("/saveNote", studentHandler.SaveStudentNote)
	}

	// Legacy WeakPoint Routes
	legacyWeakPoint := api.Group("/weakPoint")
	{
		legacyWeakPoint.GET("/getList", weakPointHandler.GetWeakPointList)
		legacyWeakPoint.POST("/getExplain", weakPointHandler.GetWeakPointExplain)
		legacyWeakPoint.POST("/getTest", weakPointHandler.GenerateTest)
		legacyWeakPoint.POST("/checkAnswer", weakPointHandler.CheckAnswer)
	}

	// V1 Student Routes
	v1 := api.Group("/v1")
	{
		studentV1 := v1.Group("/student")
		{
			studentV1.GET("/coursewares", compatHandler.GetStudentCoursewareListV1)
			studentV1.POST("/sessions", compatHandler.StartStudentSessionV1)
			studentV1.POST("/sessions/progress", compatHandler.UpdateStudentProgressV1)
			studentV1.POST("/qa/stream", compatHandler.StreamStudentQAV1)
			studentV1.GET("/coursewares/:courseId/weak-points", compatHandler.GetWeakPointsV1)
			studentV1.GET("/coursewares/:courseId/scripts/:pageNum", compatHandler.GetStudentScriptV1)
			studentV1.GET("/coursewares/:courseId/scripts/:pageNum/audio", compatHandler.GetStudentPlaybackAudioV1)
			studentV1.GET("/weak-points/:weakPointId/explain", compatHandler.ExplainWeakPointV1)
			studentV1.POST("/weak-points/:weakPointId/generate-test", compatHandler.GenerateWeakPointTestV1)
			studentV1.POST("/tests/:questionId/check", compatHandler.CheckAnswerV1)
			studentV1.GET("/coursewares/:courseId/breakpoint", compatHandler.GetBreakpointV1)
			studentV1.PUT("/coursewares/:courseId/breakpoint", compatHandler.UpdateBreakpointV1)
			studentV1.POST("/coursewares/:courseId/notes", compatHandler.SaveNoteV1)
			studentV1.GET("/coursewares/:courseId/stats", compatHandler.GetStudyStatsV1)
		}

		// Shared AI V1 for students
		aiV1 := v1.Group("/ai")
		{
			coursewareAI := aiV1.Group("/coursewares")
			{
				coursewareAI.GET("/:courseId/knowledge-graph", compatHandler.GetKnowledgeGraphV1)
				coursewareAI.POST("/:courseId/ask", compatHandler.AskCoursewareV1)
			}
		}
	}
}
