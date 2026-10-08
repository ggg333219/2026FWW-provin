package handler_test

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"smart-teaching-backend/internal/handler"
	appRouter "smart-teaching-backend/internal/router"
)

func TestKnowledgeRoutesRequireTeacherOrAdmin(t *testing.T) {
	gin.SetMode(gin.TestMode)
	engine := gin.New()
	appRouter.RegisterKnowledgeRoutes(engine.Group("/api/v1"), nil)

	for _, path := range []string{"/knowledge/upload", "/rag/search", "/rag/evidence"} {
		t.Run(path, func(t *testing.T) {
			for _, tc := range []struct {
				name       string
				role       string
				userID     string
				wantStatus int
			}{
				{name: "teacher", role: "teacher", userID: "user-1", wantStatus: http.StatusBadRequest},
				{name: "admin", role: "admin", userID: "user-1", wantStatus: http.StatusBadRequest},
				{name: "student", role: "student", wantStatus: http.StatusForbidden},
				{name: "empty user id", role: "teacher", wantStatus: http.StatusForbidden},
				{name: "missing token", wantStatus: http.StatusUnauthorized},
			} {
				t.Run(tc.name, func(t *testing.T) {
					recorder := httptest.NewRecorder()
					request := httptest.NewRequest(http.MethodPost, "/api/v1"+path, nil)
					if tc.role != "" {
						token, err := handler.GenerateToken(tc.userID, tc.role)
						if err != nil {
							t.Fatal(err)
						}
						request.Header.Set("Authorization", "Bearer "+token)
					}
					engine.ServeHTTP(recorder, request)
					if recorder.Code != tc.wantStatus {
						t.Fatalf("status = %d, want %d; body=%s", recorder.Code, tc.wantStatus, recorder.Body.String())
					}
				})
			}
		})
	}
}
