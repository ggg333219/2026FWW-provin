package handler

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

type exportTestAI struct {
	status       *service.ExportStatusResponse
	createCalled bool
}

func (f *exportTestAI) ExportCreate(context.Context, string, service.ExportCreateRequest) (*service.ExportCreateResponse, error) {
	f.createCalled = true
	return &service.ExportCreateResponse{JobID: "exp_test"}, nil
}
func (f *exportTestAI) ExportStatus(context.Context, string) (*service.ExportStatusResponse, error) {
	return f.status, nil
}
func (f *exportTestAI) VersionLoad(context.Context, string, int) (*service.VersionSnapshot, error) {
	return &service.VersionSnapshot{VersionNumber: 1}, nil
}
func (f *exportTestAI) ExportDownloadURL(jobID, extension string) string {
	return "/download/" + jobID + "." + extension
}

type exportTestProjects struct{ err error }

func (f exportTestProjects) FindByGeneration(context.Context, string, string) (*model.CoursewareProject, error) {
	if f.err != nil {
		return nil, f.err
	}
	return &model.CoursewareProject{Title: "owned course"}, nil
}

func exportRequest(handler *ExportHandler, path string) *httptest.ResponseRecorder {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("userID", "teacher-1") })
	router.POST("/api/v1/export/:generation_id", handler.CreateV2)
	router.GET("/api/v1/export/status/:export_job_id", handler.StatusV2)
	router.GET("/api/v1/export/download/:job_id/:extension", handler.Download)
	recorder := httptest.NewRecorder()
	method, body := http.MethodGet, ""
	if strings.HasPrefix(path, "/api/v1/export/gen_") {
		method, body = http.MethodPost, `{"formats":["pptx"]}`
	}
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	if body != "" {
		request.Header.Set("Content-Type", "application/json")
	}
	router.ServeHTTP(recorder, request)
	return recorder
}

func TestExportStatusHidesAnotherOwnersQualityReport(t *testing.T) {
	ai := &exportTestAI{status: &service.ExportStatusResponse{
		JobID: "exp_other", GenerationID: "gen_other", QualityReport: &service.ExportQualityReport{Status: "failed"},
	}}
	handler := NewExportHandler(ai, exportTestProjects{err: errors.New("not owner")})
	response := exportRequest(handler, "/api/v1/export/status/exp_other")
	if response.Code != http.StatusNotFound || strings.Contains(response.Body.String(), "quality_report") {
		t.Fatalf("unexpected unauthorized status response: %d %s", response.Code, response.Body.String())
	}
}

func TestExportCreateRequiresOwnedGeneration(t *testing.T) {
	ai := &exportTestAI{}
	handler := NewExportHandler(ai, exportTestProjects{err: errors.New("not owner")})
	response := exportRequest(handler, "/api/v1/export/gen_other")
	if response.Code != http.StatusNotFound || ai.createCalled {
		t.Fatalf("unauthorized create reached AI Engine: status=%d called=%v", response.Code, ai.createCalled)
	}
}

func TestExportDownloadRequiresOwnedGeneration(t *testing.T) {
	ai := &exportTestAI{status: &service.ExportStatusResponse{JobID: "exp_other", GenerationID: "gen_other"}}
	handler := NewExportHandler(ai, exportTestProjects{err: errors.New("not owner")})
	response := exportRequest(handler, "/api/v1/export/download/exp_other/docx")
	if response.Code != http.StatusNotFound || response.Header().Get("Location") != "" {
		t.Fatalf("unauthorized download was not blocked: %d %s", response.Code, response.Header().Get("Location"))
	}
}

func TestOwnedExportStatusRewritesEachAvailableFileURL(t *testing.T) {
	ai := &exportTestAI{status: &service.ExportStatusResponse{
		JobID: "exp_owned", GenerationID: "gen_owned", Status: "failed",
		Files: map[string]string{"docx": "/download/exp_owned.docx"},
	}}
	handler := NewExportHandler(ai, exportTestProjects{})
	response := exportRequest(handler, "/api/v1/export/status/exp_owned")
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), "/api/v1/export/download/exp_owned/docx") {
		t.Fatalf("owned format URL was not proxied: %d %s", response.Code, response.Body.String())
	}
}
