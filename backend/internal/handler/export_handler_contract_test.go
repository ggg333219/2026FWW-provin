package handler

import (
	"testing"

	"smart-teaching-backend/internal/service"
)

func TestNormalizeExportCreateResponseContract(t *testing.T) {
	req := service.ExportCreateRequest{
		Format:          "pptx",
		Version:         3,
		CoursewareTitle: "TCP三次握手课件",
	}
	resp := &service.ExportCreateResponse{JobID: "job_123", Status: "pending"}

	normalizeExportCreateResponse(req, resp)

	if resp.Filename != "TCP三次握手课件_v3.pptx" {
		t.Fatalf("filename 未按契约生成: %q", resp.Filename)
	}
	if resp.CoursewareTitle != req.CoursewareTitle || resp.VersionNo != 3 || resp.Version != 3 {
		t.Fatalf("导出契约字段不完整: %+v", resp)
	}
}

func TestNormalizeExportCreateResponseHTML5Extension(t *testing.T) {
	req := service.ExportCreateRequest{Format: "interactive", Version: 2, CoursewareTitle: "课堂互动"}
	resp := &service.ExportCreateResponse{}

	normalizeExportCreateResponse(req, resp)

	if resp.Filename != "课堂互动_v2.html" {
		t.Fatalf("HTML5 filename 未按契约生成: %q", resp.Filename)
	}
}
