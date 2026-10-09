package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	"smart-teaching-backend/internal/service"
)

func TestProjectVersionContractAndCloneRollback(t *testing.T) {
	gin.SetMode(gin.TestMode)
	svc := service.NewCoursewareService(nil)
	project, err := svc.CreateProject(context.Background(), "teacher_test", "TCP 课件")
	if err != nil {
		t.Fatal(err)
	}
	h := NewCoursewareHandler(svc)
	r := gin.New()
	r.POST("/api/v1/coursewares/:project_id/versions", h.CreateVersion)
	r.GET("/api/v1/coursewares/:project_id/versions/:version_id", h.VersionDetail)
	r.POST("/api/v1/coursewares/:project_id/rollback", h.Rollback)

	createBody := `{"version_no":1,"change_note":"首版","snapshot":{"outline":{"title":"TCP"},"content":[{"node_id":"node_tcp","title":"TCP 三次握手"}],"style":{"template_id":"forest"},"page_bindings":[{"page_id":"page_1"}],"generation_instruction_set":{"intent":{"topic":"TCP"},"confirmed_evidence":{"synthesized_context":"三次握手"}}}}`
	createReq := httptest.NewRequest(http.MethodPost, "/api/v1/coursewares/"+project.ProjectID+"/versions", strings.NewReader(createBody))
	createReq.Header.Set("Content-Type", "application/json")
	createRec := httptest.NewRecorder()
	r.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusOK {
		t.Fatalf("create expected 200, got %d: %s", createRec.Code, createRec.Body.String())
	}
	var created struct {
		Data map[string]any `json:"data"`
	}
	if err := json.Unmarshal(createRec.Body.Bytes(), &created); err != nil {
		t.Fatal(err)
	}
	versionID, _ := created.Data["version_id"].(string)
	if versionID == "" {
		t.Fatalf("version identity missing: %#v", created.Data)
	}
	detailReq := httptest.NewRequest(http.MethodGet, "/api/v1/coursewares/"+project.ProjectID+"/versions/"+versionID, nil)
	detailRec := httptest.NewRecorder()
	r.ServeHTTP(detailRec, detailReq)
	if detailRec.Code != http.StatusOK || !strings.Contains(detailRec.Body.String(), `"change_note":"首版"`) || !strings.Contains(detailRec.Body.String(), `"snapshot"`) || !strings.Contains(detailRec.Body.String(), `"generation_instruction_set"`) {
		t.Fatalf("detail contract missing canonical snapshot: %s", detailRec.Body.String())
	}

	rollbackBody := `{"target_version_id":"` + versionID + `"}`
	rollbackReq := httptest.NewRequest(http.MethodPost, "/api/v1/coursewares/"+project.ProjectID+"/rollback", strings.NewReader(rollbackBody))
	rollbackReq.Header.Set("Content-Type", "application/json")
	rollbackRec := httptest.NewRecorder()
	r.ServeHTTP(rollbackRec, rollbackReq)
	if rollbackRec.Code != http.StatusOK {
		t.Fatalf("rollback expected 200, got %d: %s", rollbackRec.Code, rollbackRec.Body.String())
	}
	var rolled struct {
		Data map[string]any `json:"data"`
	}
	if err := json.Unmarshal(rollbackRec.Body.Bytes(), &rolled); err != nil {
		t.Fatal(err)
	}
	if rolled.Data["base_version_no"] != float64(1) || rolled.Data["new_draft_version_no"] != float64(2) {
		t.Fatalf("clone rollback contract mismatch: %#v", rolled.Data)
	}
	versions, err := svc.Versions(context.Background(), project.ProjectID)
	if err != nil || len(versions) != 2 {
		t.Fatalf("rollback must retain history and append branch: count=%d err=%v", len(versions), err)
	}
}

func TestProjectVersionKeepsGeneratedFlashcardsForS4(t *testing.T) {
	gin.SetMode(gin.TestMode)
	svc := service.NewCoursewareService(nil)
	project, err := svc.CreateProject(context.Background(), "teacher_test", "Sorting")
	if err != nil {
		t.Fatal(err)
	}
	h := NewCoursewareHandler(svc)
	r := gin.New()
	r.POST("/api/v1/coursewares/:project_id/versions", h.CreateVersion)
	r.GET("/api/v1/coursewares/:project_id/versions/:version_id", h.VersionDetail)
	body := `{"change_note":"flashcards","snapshot":{"outline":{"nodes":[{"node_id":"card_1","interactive_plan":{"kind":"flashcard"}}]},"content":[{"node_id":"card_1","title":"Quick sort","type":"interactive","interactive_plan":{"kind":"flashcard"},"interactive_items":[{"type":"flashcard","front":"Quick sort","back":"Divide and conquer"}],"metadata":{"interactive_asset":{"status":"done","items":[{"type":"flashcard","front":"Quick sort","back":"Divide and conquer"}]}}}],"style":{},"page_bindings":[]}}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/coursewares/"+project.ProjectID+"/versions", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	created := httptest.NewRecorder()
	r.ServeHTTP(created, req)
	if created.Code != http.StatusOK {
		t.Fatalf("create failed: %s", created.Body.String())
	}
	var envelope struct { Data struct { VersionID string `json:"version_id"` } `json:"data"` }
	if err := json.Unmarshal(created.Body.Bytes(), &envelope); err != nil { t.Fatal(err) }
	detail := httptest.NewRecorder()
	r.ServeHTTP(detail, httptest.NewRequest(http.MethodGet, "/api/v1/coursewares/"+project.ProjectID+"/versions/"+envelope.Data.VersionID, nil))
	if detail.Code != http.StatusOK {
		t.Fatalf("load failed: %s", detail.Body.String())
	}
	for _, expected := range []string{`"type":"flashcard"`, `"front":"Quick sort"`, `"back":"Divide and conquer"`, `"interactive_asset"`} {
		if !strings.Contains(detail.Body.String(), expected) {
			t.Fatalf("saved card field %s missing: %s", expected, detail.Body.String())
		}
	}
}
