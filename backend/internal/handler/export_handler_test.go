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
	createGenID  string
	createReq    service.ExportCreateRequest
}

func (f *exportTestAI) ExportCreate(_ context.Context, genID string, req service.ExportCreateRequest) (*service.ExportCreateResponse, error) {
	f.createCalled = true
	f.createGenID = genID
	f.createReq = req
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

type exportTestProjects struct {
	err     error
	project *model.CoursewareProject
}

func (f exportTestProjects) FindByGeneration(_ context.Context, _ string, genID string) (*model.CoursewareProject, error) {
	if f.err != nil {
		return nil, f.err
	}
	if f.project != nil {
		if f.project.GenID != genID {
			return nil, errors.New("generation not found")
		}
		return f.project, nil
	}
	return &model.CoursewareProject{Title: "owned course"}, nil
}
func (f exportTestProjects) Get(context.Context, string, string) (*model.CoursewareProject, error) {
	if f.err != nil {
		return nil, f.err
	}
	if f.project != nil {
		return f.project, nil
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

func TestExportCreateUsesOwnedProjectGenerationForSnapshot(t *testing.T) {
	ai := &exportTestAI{}
	projects := exportTestProjects{project: &model.CoursewareProject{
		Title: "高等数学", GenID: "course_current", BaseModel: model.BaseModel{ID: "project-1"},
	}}
	handler := NewExportHandler(ai, projects)
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("userID", "teacher-1") })
	router.POST("/api/v1/exp/:gen_id", handler.Create)
	body := `{"project_id":"project-1","format":"pptx","version":2,"nodes":[{"node_id":"node_001","title":"积分概念"}]}`
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodPost, "/api/v1/exp/course_stale", strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK || !ai.createCalled {
		t.Fatalf("project snapshot export was rejected: status=%d body=%s called=%v", recorder.Code, recorder.Body.String(), ai.createCalled)
	}
	if ai.createGenID != "course_current" || ai.createReq.Version != 2 || len(ai.createReq.Nodes) != 1 {
		t.Fatalf("export did not use the owned project snapshot: gen=%q version=%d nodes=%d", ai.createGenID, ai.createReq.Version, len(ai.createReq.Nodes))
	}
}

func TestExportProjectSnapshotWithoutGenerationCanBePolled(t *testing.T) {
	ai := &exportTestAI{status: &service.ExportStatusResponse{JobID: "exp_project", GenerationID: "project-1", Status: "done"}}
	projects := exportTestProjects{project: &model.CoursewareProject{
		Title: "高等数学", BaseModel: model.BaseModel{ID: "project-1"},
	}}
	handler := NewExportHandler(ai, projects)
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(func(c *gin.Context) { c.Set("userID", "teacher-1") })
	router.POST("/api/v1/exp/:gen_id", handler.Create)
	router.GET("/api/v1/exp/status/:job_id", handler.Status)
	body := `{"project_id":"project-1","format":"pptx","version":1,"nodes":[{"node_id":"node_001","title":"积分概念"}]}`
	request := httptest.NewRequest(http.MethodPost, "/api/v1/exp/project-1", strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	created := httptest.NewRecorder()
	router.ServeHTTP(created, request)
	if created.Code != http.StatusOK || ai.createGenID != "project-1" {
		t.Fatalf("project-only snapshot export failed: status=%d gen=%q body=%s", created.Code, ai.createGenID, created.Body.String())
	}
	status := httptest.NewRecorder()
	router.ServeHTTP(status, httptest.NewRequest(http.MethodGet, "/api/v1/exp/status/exp_project", nil))
	if status.Code != http.StatusOK {
		t.Fatalf("owned project-only export status failed: status=%d body=%s", status.Code, status.Body.String())
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
