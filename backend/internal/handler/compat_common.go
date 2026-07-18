package handler

import (
	"bytes"
	"context"
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"

	"smart-teaching-backend/internal/repository"
	"smart-teaching-backend/internal/service"
	"smart-teaching-backend/pkg/logger"
)

type CompatibilityHandler struct {
	db            *gorm.DB
	aiClient      service.AIEngine
	courseService service.CourseService
}

type sessionState struct {
	SessionID     string    `json:"sessionId"`
	UserID        string    `json:"userId"`
	CourseID      string    `json:"courseId"`
	CurrentPage   int       `json:"currentPage"`
	CurrentNodeID string    `json:"currentNodeId"`
	ProgressPercent float64 `json:"progressPercent,omitempty"`
	LastOperateTime string  `json:"lastOperateTime,omitempty"`
	UpdatedAt     time.Time `json:"updatedAt"`
}

var sessionStore sync.Map

func NewCompatibilityHandler(db *gorm.DB, aiClient service.AIEngine, courseService service.CourseService) *CompatibilityHandler {
	return &CompatibilityHandler{db: db, aiClient: aiClient, courseService: courseService}
}

func OpenAPISignatureMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		staticKey := strings.TrimSpace(os.Getenv("OPEN_API_STATIC_KEY"))
		if staticKey == "" {
			c.Next()
			return
		}

		params := map[string]any{}
		enc := c.Query("enc")
		timeValue := c.Query("time")

		if len(c.Request.URL.Query()) > 0 {
			for key, values := range c.Request.URL.Query() {
				if len(values) > 0 {
					params[key] = values[0]
				}
			}
		}

		if c.Request.Body != nil {
			bodyBytes, _ := io.ReadAll(c.Request.Body)
			c.Request.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
			if len(bytes.TrimSpace(bodyBytes)) > 0 {
				var bodyMap map[string]any
				if err := json.Unmarshal(bodyBytes, &bodyMap); err == nil {
					for k, v := range bodyMap {
						params[k] = v
					}
				}
			}
		}

		if enc == "" {
			enc = stringifyAny(params["enc"])
		}
		if timeValue == "" {
			timeValue = stringifyAny(params["time"])
		}

		if enc == "" || timeValue == "" {
			openAPIError(c, http.StatusForbidden, "缺少 enc 或 time")
			c.Abort()
			return
		}

		delete(params, "enc")
		delete(params, "time")

		// 只对指定的平铺字段做签名，避免复杂 JSON 导致的序列化不一致
		signFieldsEnv := strings.TrimSpace(os.Getenv("OPEN_API_SIGN_FIELDS"))
		var signFields []string
		if signFieldsEnv == "" {
			signFields = []string{"platformId", "userId"}
		} else {
			for _, f := range strings.Split(signFieldsEnv, ",") {
				if s := strings.TrimSpace(f); s != "" {
					signFields = append(signFields, s)
				}
			}
		}

		filtered := map[string]any{}
		for _, k := range signFields {
			if v, ok := params[k]; ok {
				if stringifyAny(v) != "" {
					filtered[k] = v
				}
			}
		}

		expected, builderStr := buildOpenAPISignature(filtered, staticKey, timeValue)
		if !strings.EqualFold(expected, enc) {
			// 记录期望签名与用于计算的原始串，便于诊断客户端计算差异
			logger.Infof("openapi signature mismatch expected=%s provided=%s builder=%s", expected, enc, builderStr)
			openAPIError(c, http.StatusForbidden, "签名校验失败")
			c.Abort()
			return
		}

		c.Next()
	}
}

func buildOpenAPISignature(params map[string]any, staticKey, timeValue string) (string, string) {
	keys := make([]string, 0, len(params))
	for k, v := range params {
		if stringifyAny(v) == "" {
			continue
		}
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var builder strings.Builder
	for _, key := range keys {
		builder.WriteString(key)
		builder.WriteString(stringifyForSign(params[key]))
	}
	builder.WriteString(staticKey)
	builder.WriteString(timeValue)
	b := builder.String()
	hash := md5.Sum([]byte(b))
	expected := strings.ToUpper(hex.EncodeToString(hash[:]))
	// 返回 expected 和用于计算的原始串，便于诊断
	return expected, b
}

func stringifyForSign(v any) string {
	switch val := v.(type) {
	case nil:
		return ""
	case string:
		return val
	case bool, float64, float32, int, int64, int32:
		return fmt.Sprint(val)
	case map[string]any:
		// deterministic serialization: sort keys
		keys := make([]string, 0, len(val))
		for k := range val {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		var sb strings.Builder
		sb.WriteString("{")
		for i, k := range keys {
			if i > 0 {
				sb.WriteString(",")
			}
			sb.WriteString("\"")
			sb.WriteString(k)
			sb.WriteString("\":")
			sb.WriteString(stringifyForSign(val[k]))
		}
		sb.WriteString("}")
		return sb.String()
	case []any:
		var sb strings.Builder
		sb.WriteString("[")
		for i, e := range val {
			if i > 0 {
				sb.WriteString(",")
			}
			sb.WriteString(stringifyForSign(e))
		}
		sb.WriteString("]")
		return sb.String()
	default:
		return fmt.Sprint(val)
	}
}

func stringifyAny(v any) string {
	switch value := v.(type) {
	case nil:
		return ""
	case string:
		return value
	case fmt.Stringer:
		return value.String()
	default:
		return fmt.Sprint(value)
	}
}

func openAPISuccess(c *gin.Context, msg string, data any) {
	c.JSON(http.StatusOK, gin.H{
		"code":      200,
		"msg":       msg,
		"data":      data,
		"requestId": "req_" + uuid.NewString(),
	})
}

func openAPIError(c *gin.Context, status int, msg string) {
	c.JSON(status, gin.H{
		"code":      status,
		"msg":       msg,
		"data":      gin.H{},
		"requestId": "req_" + uuid.NewString(),
	})
}

func buildScriptNodes(page int, content string) []gin.H {
	content = strings.TrimSpace(content)
	if content == "" {
		return []gin.H{}
	}
	segments := strings.FieldsFunc(content, func(r rune) bool {
		return r == '\n' || r == '。' || r == '！' || r == '？'
	})
	nodes := make([]gin.H, 0, len(segments))
	for idx, seg := range segments {
		seg = strings.TrimSpace(seg)
		if seg == "" {
			continue
		}
		nodeType := "explain"
		if idx == 0 {
			nodeType = "opening"
		} else if idx == len(segments)-1 {
			nodeType = "transition"
		}
		nodes = append(nodes, gin.H{
			"node_id": fmt.Sprintf("p%d_n%d", page, idx+1),
			"type":    nodeType,
			"text":    seg,
		})
	}
	return nodes
}

func nextNodeID(nodeID string, page int) string {
	if nodeID == "" {
		return fmt.Sprintf("p%d_n1", page)
	}
	parts := strings.Split(nodeID, "_n")
	if len(parts) != 2 {
		return fmt.Sprintf("p%d_n1", page)
	}
	index, err := strconv.Atoi(parts[1])
	if err != nil {
		return fmt.Sprintf("p%d_n1", page)
	}
	return fmt.Sprintf("%s_n%d", parts[0], index+1)
}

func (h *CompatibilityHandler) persistSession(state sessionState) {
	sessionStore.Store(state.SessionID, state)
	if redisClient := repository.GetRedis(); redisClient != nil {
		if payload, err := json.Marshal(state); err == nil {
			_ = redisClient.Set(context.Background(), "study:session:"+state.SessionID, payload, 24*time.Hour).Err()
		}
	}
}

func (h *CompatibilityHandler) loadSession(sessionID string) *sessionState {
	if sessionID == "" {
		return nil
	}
	if value, ok := sessionStore.Load(sessionID); ok {
		state := value.(sessionState)
		return &state
	}
	if redisClient := repository.GetRedis(); redisClient != nil {
		payload, err := redisClient.Get(context.Background(), "study:session:"+sessionID).Result()
		if err == nil {
			var state sessionState
			if json.Unmarshal([]byte(payload), &state) == nil {
				sessionStore.Store(sessionID, state)
				return &state
			}
		}
	}
	return nil
}

func defaultString(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func filterParams(params gin.Params, key string) gin.Params {
	result := make(gin.Params, 0, len(params))
	for _, p := range params {
		if p.Key != key {
			result = append(result, p)
		}
	}
	return result
}

func parsePageFromNodeID(nodeID string) int {
	if strings.HasPrefix(nodeID, "p") {
		parts := strings.Split(strings.TrimPrefix(nodeID, "p"), "_n")
		page, _ := strconv.Atoi(parts[0])
		return page
	}
	return 0
}

func UnderstandingLevelOrFallback(llm string, needReteach bool) string {
	if llm != "" && llm != "unknown" {
		return llm
	}
	if needReteach {
		return "partial"
	}
	return "full"
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
