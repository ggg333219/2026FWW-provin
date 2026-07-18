package learningevent

import (
	"fmt"
	"strings"
	"unicode/utf8"

	"github.com/google/uuid"
)

const (
	MaxNodeIDRunes = 100
	MaxPage        = 50000
	MaxTimeSec     = 86400 * 14
	MaxOpaqueIDLen = 80 // userId / sessionId：允许非 UUID 的业务标识（如演示账号 xuesheng）
)

// ValidateCourseID 课件 ID：非空 UUID（与 Course.BaseModel.ID 一致）。
func ValidateCourseID(courseID string) error {
	courseID = strings.TrimSpace(courseID)
	if courseID == "" {
		return fmt.Errorf("courseId required")
	}
	if len(courseID) > 36 {
		return fmt.Errorf("courseId too long")
	}
	if _, err := uuid.Parse(courseID); err != nil {
		return fmt.Errorf("courseId must be a valid UUID")
	}
	return nil
}

// ValidateUserID 非空时为可见字符、长度受限的 opaque id（兼容 UUID 与演示账号字符串）。
func ValidateUserID(userID string) error {
	return validateOpaqueID("userId", userID, MaxOpaqueIDLen)
}

// ValidateSessionID 同上；服务端下发的 session 多为 UUID，也允许其它客户端约定格式。
func ValidateSessionID(sessionID string) error {
	return validateOpaqueID("sessionId", sessionID, MaxOpaqueIDLen)
}

func validateOpaqueID(label, s string, maxLen int) error {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil
	}
	if len(s) > maxLen {
		return fmt.Errorf("%s too long", label)
	}
	for _, r := range s {
		if r < 32 && r != '\t' {
			return fmt.Errorf("%s contains invalid control characters", label)
		}
	}
	return nil
}

// ValidateNodeID 播放/讲授节点业务 ID：长度与控制字符约束（允许中文等任意可见字符）。
func ValidateNodeID(nodeID string) error {
	nodeID = strings.TrimSpace(nodeID)
	if nodeID == "" {
		return nil
	}
	if utf8.RuneCountInString(nodeID) > MaxNodeIDRunes {
		return fmt.Errorf("nodeId exceeds max length")
	}
	for _, r := range nodeID {
		if r < 32 && r != '\t' {
			return fmt.Errorf("nodeId contains invalid control characters")
		}
	}
	return nil
}

// ValidateProgressPage 当前页码范围。
func ValidateProgressPage(page int) error {
	if page < 1 || page > MaxPage {
		return fmt.Errorf("page out of valid range")
	}
	return nil
}

// ValidateTimeSec 播放时间戳（秒）范围，防异常大包。
func ValidateTimeSec(sec int) error {
	if sec < 0 || sec > MaxTimeSec {
		return fmt.Errorf("currentTimeSec out of valid range")
	}
	return nil
}
