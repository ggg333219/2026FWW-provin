package handler

import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/base64"
    "encoding/json"
    "os"
    "strings"
    "time"

    "github.com/gin-gonic/gin"
    "smart-teaching-backend/pkg/apiresp"
)

type simpleClaims struct {
    UserID string `json:"userId"`
    Role   string `json:"role"`
    Exp    int64  `json:"exp"`
    Iat    int64  `json:"iat"`
}

// GenerateToken 使用 HMAC-SHA256 对 payload 签名，token 格式：base64(payloadJSON).base64(sig)
func GenerateToken(userID, role string) (string, error) {
    secret := os.Getenv("OPEN_API_JWT_SECRET")
    if secret == "" {
        secret = "dev-secret"
    }
    now := time.Now()
    claims := simpleClaims{UserID: userID, Role: role, Exp: now.Add(24 * time.Hour).Unix(), Iat: now.Unix()}
    payload, err := json.Marshal(claims)
    if err != nil {
        return "", err
    }
    payloadB64 := base64.RawURLEncoding.EncodeToString(payload)
    mac := hmac.New(sha256.New, []byte(secret))
    mac.Write([]byte(payloadB64))
    sig := mac.Sum(nil)
    sigB64 := base64.RawURLEncoding.EncodeToString(sig)
    return payloadB64 + "." + sigB64, nil
}

func parseToken(tokenStr string) (*simpleClaims, bool) {
    parts := strings.Split(tokenStr, ".")
    if len(parts) != 2 {
        return nil, false
    }
    payloadB64, sigB64 := parts[0], parts[1]
    secret := os.Getenv("OPEN_API_JWT_SECRET")
    if secret == "" {
        secret = "dev-secret"
    }
    mac := hmac.New(sha256.New, []byte(secret))
    mac.Write([]byte(payloadB64))
    expectedSig := mac.Sum(nil)
    sig, err := base64.RawURLEncoding.DecodeString(sigB64)
    if err != nil {
        return nil, false
    }
    if !hmac.Equal(sig, expectedSig) {
        return nil, false
    }
    payload, err := base64.RawURLEncoding.DecodeString(payloadB64)
    if err != nil {
        return nil, false
    }
    var claims simpleClaims
    if err := json.Unmarshal(payload, &claims); err != nil {
        return nil, false
    }
    if time.Now().Unix() > claims.Exp {
        return nil, false
    }
    return &claims, true
}

func JWTAuthMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        path := c.Request.URL.Path
        // Allow unauthenticated paths: auth and open signature-based endpoints
        if strings.HasPrefix(path, "/api/v1/auth") || strings.HasPrefix(path, "/api/v1/lesson") || strings.HasPrefix(path, "/api/v1/qa") || strings.HasPrefix(path, "/api/v1/progress") || strings.HasPrefix(path, "/api/v1/platform") {
            c.Next()
            return
        }

        authHeader := c.GetHeader("Authorization")
        if authHeader == "" {
            apiresp.Unauthorized(c, "缺少授权头", "")
            c.Abort()
            return
        }
        parts := strings.Fields(authHeader)
        if len(parts) != 2 || strings.ToLower(parts[0]) != "bearer" {
            apiresp.Unauthorized(c, "授权头格式错误", "")
            c.Abort()
            return
        }
        tokenStr := parts[1]
        claims, ok := parseToken(tokenStr)
        if !ok {
            apiresp.Unauthorized(c, "无效或过期的令牌", "")
            c.Abort()
            return
        }
        c.Set("userID", claims.UserID)
        c.Set("role", claims.Role)
        c.Next()
    }
}
