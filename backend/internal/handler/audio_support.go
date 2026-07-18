package handler

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/internal/service"
)

func ensurePlaybackAudioAssets(ctx context.Context, db *gorm.DB, aiClient service.AIEngine, courseID string, page int, voiceType, format, provider string) (gin.H, error) {
	nodes := loadTeachingNodesByPage(db, courseID, page)
	if len(nodes) == 0 {
		return gin.H{}, fmt.Errorf("当前页暂无可生成音频的教学节点")
	}

	voiceType = defaultAudioVoiceType(voiceType)
	format = defaultAudioFormat(format)
	provider = strings.TrimSpace(provider)
	if provider == "" {
		provider = "mock-tts"
	}

	if aiClient != nil {
		requestNodes := make([]service.GenerateAudioNode, 0, len(nodes))
		currentStartSec := 0
		for _, node := range nodes {
			text := strings.TrimSpace(teachingNodeDisplayText(node))
			if text == "" {
				continue
			}
			startSec, durationSec, endSec := playbackTiming(node, currentStartSec)
			requestNodes = append(requestNodes, service.GenerateAudioNode{
				NodeID:      node.NodeID,
				Title:       node.Title,
				Text:        text,
				DurationSec: durationSec,
				StartSec:    startSec,
				EndSec:      endSec,
			})
			currentStartSec = endSec
		}
		if len(requestNodes) > 0 {
			resp, err := aiClient.GenerateAudio(ctx, service.GenerateAudioRequest{
				CourseID:   courseID,
				Page:       page,
				VoiceType:  voiceType,
				Format:     format,
				Provider:   provider,
				Nodes:      requestNodes,
				PlaybackID: fmt.Sprintf("audio_%s_%d", courseID, page),
			})
			if err == nil && len(resp.Sections) > 0 {
				return persistGeneratedAudioAssets(db, courseID, page, voiceType, resp), nil
			}
		}
	}

	return ensurePlaceholderAudioAssets(db, courseID, page, voiceType, format, provider)
}

func ensurePlaceholderAudioAssets(db *gorm.DB, courseID string, page int, voiceType, format, provider string) (gin.H, error) {
	nodes := loadTeachingNodesByPage(db, courseID, page)
	if len(nodes) == 0 {
		return gin.H{}, fmt.Errorf("当前页暂无可生成音频的教学节点")
	}

	voiceType = defaultAudioVoiceType(voiceType)
	format = defaultAudioFormat(format)
	provider = defaultAudioProvider(provider)

	sections := make([]gin.H, 0, len(nodes))
	currentStartSec := 0
	hasAudio := false
	for _, node := range nodes {
		text := strings.TrimSpace(teachingNodeDisplayText(node))
		if text == "" {
			continue
		}
		durationSec := playbackDurationSec(node)
		startSec := currentStartSec
		endSec := currentStartSec + durationSec
		currentStartSec = endSec

		status := strings.TrimSpace(node.TTSStatus)
		if status == "" || status == "not_generated" {
			status = "placeholder"
		}
		if strings.TrimSpace(node.AudioURL) != "" && status == "ready" {
			hasAudio = true
		}

		scriptHash := hashAudioSource(text, voiceType, format, provider)
		asset := model.AudioAsset{}
		err := db.Where("course_id = ? AND page_index = ? AND node_id = ?", courseID, page, node.NodeID).First(&asset).Error
		if err == nil {
			_ = db.Model(&asset).Updates(map[string]any{
				"provider":           provider,
				"voice_type":         voiceType,
				"format":             format,
				"status":             status,
				"audio_url":          node.AudioURL,
				"duration_sec":       durationSec,
				"start_sec":          startSec,
				"end_sec":            endSec,
				"source_script_hash": scriptHash,
			}).Error
		} else {
			_ = db.Create(&model.AudioAsset{
				CourseID:         courseID,
				PageIndex:        page,
				NodeID:           node.NodeID,
				Provider:         provider,
				VoiceType:        voiceType,
				Format:           format,
				Status:           status,
				AudioURL:         node.AudioURL,
				DurationSec:      durationSec,
				StartSec:         startSec,
				EndSec:           endSec,
				SourceScriptHash: scriptHash,
			}).Error
		}

		_ = db.Model(&model.TeachingNode{}).Where("id = ?", node.ID).Updates(map[string]any{
			"audio_duration_sec": durationSec,
			"audio_start_sec":    startSec,
			"audio_end_sec":      endSec,
			"tts_status":         status,
			"voice_profile":      voiceType,
		}).Error

		sections = append(sections, gin.H{
			"node_id":            node.NodeID,
			"title":              node.Title,
			"text":               text,
			"audio_url":          node.AudioURL,
			"duration_sec":       durationSec,
			"start_sec":          startSec,
			"end_sec":            endSec,
			"audio_duration_sec": durationSec,
			"audio_start_sec":    startSec,
			"audio_end_sec":      endSec,
			"tts_status":         status,
			"has_audio":          strings.TrimSpace(node.AudioURL) != "" && status == "ready",
		})
	}

	pageStatus := "placeholder"
	if hasAudio {
		pageStatus = "ready"
	}
	_ = db.Model(&model.CoursePage{}).Where("course_id = ? AND page_index = ?", courseID, page).Updates(map[string]any{
		"audio_status":       pageStatus,
		"audio_provider":     provider,
		"audio_duration_sec": currentStartSec,
	}).Error

	return gin.H{
		"audio_id":           fmt.Sprintf("audio_%s_%d", courseID, page),
		"course_id":          courseID,
		"page":               page,
		"audio_url":          "",
		"voice_type":         voiceType,
		"format":             format,
		"provider":           provider,
		"status":             pageStatus,
		"has_audio":          hasAudio,
		"playback_mode":      playbackModeByAvailability(hasAudio),
		"total_duration_sec": currentStartSec,
		"generated_at":       time.Now().Format(time.RFC3339),
		"sections":           sections,
	}, nil
}

func buildPlaybackAudioMeta(courseID string, page int, nodes []model.TeachingNode) gin.H {
	sections := make([]gin.H, 0, len(nodes))
	totalDuration := 0
	hasAudio := false
	for _, node := range nodes {
		text := strings.TrimSpace(teachingNodeDisplayText(node))
		if text == "" {
			continue
		}
		startSec, durationSec, endSec := playbackTiming(node, totalDuration)
		if endSec > totalDuration {
			totalDuration = endSec
		}
		ready := strings.TrimSpace(node.AudioURL) != "" && strings.TrimSpace(node.TTSStatus) == "ready"
		if ready {
			hasAudio = true
		}
		sections = append(sections, gin.H{
			"node_id":      node.NodeID,
			"title":        node.Title,
			"audio_url":    node.AudioURL,
			"duration_sec": durationSec,
			"start_sec":    startSec,
			"end_sec":      endSec,
			"tts_status":   defaultAudioStatus(node.TTSStatus),
			"has_audio":    ready,
		})
	}

	return gin.H{
		"audio_id":           fmt.Sprintf("audio_%s_%d", courseID, page),
		"course_id":          courseID,
		"page":               page,
		"audio_url":          "",
		"has_audio":          hasAudio,
		"playback_mode":      playbackModeByAvailability(hasAudio),
		"total_duration_sec": totalDuration,
		"sections":           sections,
	}
}

func hashAudioSource(parts ...string) string {
	hasher := sha256.New()
	for _, part := range parts {
		_, _ = hasher.Write([]byte(strings.TrimSpace(part)))
	}
	return hex.EncodeToString(hasher.Sum(nil))
}

func defaultAudioVoiceType(voiceType string) string {
	voiceType = strings.TrimSpace(voiceType)
	if voiceType == "" {
		return "standard_female"
	}
	return voiceType
}

func defaultAudioFormat(format string) string {
	format = strings.TrimSpace(format)
	if format == "" {
		return "mp3"
	}
	return format
}

func defaultAudioProvider(provider string) string {
	provider = strings.TrimSpace(provider)
	if provider == "" {
		return "placeholder-tts"
	}
	return provider
}

func defaultAudioStatus(status string) string {
	status = strings.TrimSpace(status)
	if status == "" {
		return "not_generated"
	}
	return status
}

func playbackModeByAvailability(hasAudio bool) string {
	if hasAudio {
		return "audio_timeline"
	}
	return "duration_timeline"
}

func resolvePlaybackResumeSec(db *gorm.DB, courseID string, page int, nodeID string) int {
	nodes := loadTeachingNodesByPage(db, courseID, page)
	currentStartSec := 0
	for _, node := range nodes {
		text := strings.TrimSpace(teachingNodeDisplayText(node))
		if text == "" {
			continue
		}
		startSec, _, endSec := playbackTiming(node, currentStartSec)
		if node.NodeID == nodeID {
			return startSec
		}
		currentStartSec = endSec
	}
	return 0
}

func persistGeneratedAudioAssets(db *gorm.DB, courseID string, page int, voiceType string, resp *service.GenerateAudioResponse) gin.H {
	if resp == nil {
		return gin.H{}
	}
	status := strings.TrimSpace(resp.Status)
	if status == "" {
		status = "ready"
	}
	provider := defaultAudioProvider(resp.Provider)
	sections := make([]gin.H, 0, len(resp.Sections))
	for _, section := range resp.Sections {
		scriptHash := hashAudioSource(section.Text, voiceType, resp.Format, provider)
		asset := model.AudioAsset{}
		err := db.Where("course_id = ? AND page_index = ? AND node_id = ?", courseID, page, section.NodeID).First(&asset).Error
		payload := map[string]any{
			"provider":           provider,
			"voice_type":         defaultAudioVoiceType(resp.VoiceType),
			"format":             defaultAudioFormat(resp.Format),
			"status":             status,
			"audio_url":          strings.TrimSpace(section.AudioURL),
			"duration_sec":       maxInt(section.DurationSec, 0),
			"start_sec":          maxInt(section.StartSec, 0),
			"end_sec":            maxInt(section.EndSec, maxInt(section.StartSec, 0)+maxInt(section.DurationSec, 0)),
			"source_script_hash": scriptHash,
		}
		if err == nil {
			_ = db.Model(&asset).Updates(payload).Error
		} else {
			_ = db.Create(&model.AudioAsset{
				CourseID:         courseID,
				PageIndex:        page,
				NodeID:           section.NodeID,
				Provider:         provider,
				VoiceType:        defaultAudioVoiceType(resp.VoiceType),
				Format:           defaultAudioFormat(resp.Format),
				Status:           status,
				AudioURL:         strings.TrimSpace(section.AudioURL),
				DurationSec:      maxInt(section.DurationSec, 0),
				StartSec:         maxInt(section.StartSec, 0),
				EndSec:           maxInt(section.EndSec, maxInt(section.StartSec, 0)+maxInt(section.DurationSec, 0)),
				SourceScriptHash: scriptHash,
			}).Error
		}

		_ = db.Model(&model.TeachingNode{}).Where("course_id = ? AND page_index = ? AND node_id = ?", courseID, page, section.NodeID).Updates(map[string]any{
			"audio_url":          strings.TrimSpace(section.AudioURL),
			"audio_duration_sec": maxInt(section.DurationSec, 0),
			"audio_start_sec":    maxInt(section.StartSec, 0),
			"audio_end_sec":      maxInt(section.EndSec, maxInt(section.StartSec, 0)+maxInt(section.DurationSec, 0)),
			"tts_status":         status,
			"voice_profile":      defaultAudioVoiceType(resp.VoiceType),
		}).Error

		sections = append(sections, gin.H{
			"node_id":            section.NodeID,
			"title":              section.Title,
			"text":               section.Text,
			"audio_url":          section.AudioURL,
			"duration_sec":       section.DurationSec,
			"start_sec":          section.StartSec,
			"end_sec":            section.EndSec,
			"audio_duration_sec": section.DurationSec,
			"audio_start_sec":    section.StartSec,
			"audio_end_sec":      section.EndSec,
			"tts_status":         status,
			"has_audio":          strings.TrimSpace(section.AudioURL) != "",
		})
	}

	_ = db.Model(&model.CoursePage{}).Where("course_id = ? AND page_index = ?", courseID, page).Updates(map[string]any{
		"audio_status":       status,
		"audio_provider":     provider,
		"audio_duration_sec": maxInt(resp.TotalDuration, 0),
	}).Error

	return gin.H{
		"audio_id":           resp.AudioID,
		"course_id":          courseID,
		"page":               page,
		"audio_url":          strings.TrimSpace(resp.AudioURL),
		"voice_type":         defaultAudioVoiceType(resp.VoiceType),
		"format":             defaultAudioFormat(resp.Format),
		"provider":           provider,
		"status":             status,
		"has_audio":          true,
		"playback_mode":      playbackModeByAvailability(true),
		"total_duration_sec": maxInt(resp.TotalDuration, 0),
		"generated_at":       resp.GeneratedAt,
		"sections":           sections,
	}
}
