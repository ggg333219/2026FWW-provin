package handler

import (
	"strings"

	"smart-teaching-backend/internal/model"
)

func pageContextText(page model.CoursePage) string {
	if text := strings.TrimSpace(page.SourceText); text != "" {
		return text
	}
	return strings.TrimSpace(page.ScriptText)
}

func pageDisplayText(page model.CoursePage) string {
	if text := strings.TrimSpace(page.ScriptText); text != "" {
		return text
	}
	return strings.TrimSpace(page.SourceText)
}
