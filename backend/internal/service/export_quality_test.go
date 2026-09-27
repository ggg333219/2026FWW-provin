package service

import (
	"encoding/json"
	"testing"
)

func TestExportStatusResponseDecodesQualityReport(t *testing.T) {
	var response ExportStatusResponse
	err := json.Unmarshal([]byte(`{
		"job_id":"exp_test",
		"status":"done",
		"version":2,
		"quality_report":{
			"status":"passed_with_warnings",
			"slide_count":3,
			"findings":[{"code":"text_may_overflow","severity":"warning","message":"Text may overflow.","slide_number":2}]
		}
	}`), &response)
	if err != nil {
		t.Fatalf("decode export status: %v", err)
	}
	if response.Version != 2 || response.QualityReport == nil {
		t.Fatalf("export version or quality report missing: %+v", response)
	}
	if response.QualityReport.Status != "passed_with_warnings" || len(response.QualityReport.Findings) != 1 {
		t.Fatalf("unexpected quality report: %+v", response.QualityReport)
	}
	if response.QualityReport.Findings[0].SlideNumber == nil || *response.QualityReport.Findings[0].SlideNumber != 2 {
		t.Fatalf("finding slide number missing: %+v", response.QualityReport.Findings[0])
	}
}
