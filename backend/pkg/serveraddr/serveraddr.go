// Package serveraddr 解析 HTTP 服务的监听地址。
//
// 本地同时跑教师端/学生端/AI 引擎时，配置端口被占用是最常见的启动失败原因
// （listen tcp :8082: bind: Only one usage of each socket address ...）。
// 这里不终止占用端口的进程，而是顺延到下一个可用端口。
package serveraddr

import (
	"encoding/json"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"time"
)

// DefaultMaxTries 是配置端口被占用时最多尝试的连续端口数。
const DefaultMaxTries = 100

// Resolve 依次尝试 :preferred, :preferred+1, ... 直到拿到一个能真正绑定的端口。
//
// preferred <= 0 表示"任意可用端口"，直接交给系统分配。
// 返回的 listener 已经打开，调用方应直接用 gin.RunListener(ln) 复用——
// 不要拿返回的端口再 bind 一次，两步之间会有竞态。
// port 是实际绑定到的端口号。
func Resolve(preferred int, maxTries int) (ln net.Listener, port int, err error) {
	if maxTries <= 0 {
		maxTries = DefaultMaxTries
	}
	if preferred <= 0 {
		listener, listenErr := net.Listen("tcp", ":0")
		if listenErr != nil {
			return nil, 0, fmt.Errorf("没有可用端口: %w", listenErr)
		}
		got, parseErr := portFromAddr(listener.Addr())
		if parseErr != nil {
			_ = listener.Close()
			return nil, 0, fmt.Errorf("解析监听端口失败: %w", parseErr)
		}
		return listener, got, nil
	}

	var lastErr error
	for i := 0; i < maxTries; i++ {
		port := preferred + i
		if port > 65535 {
			break
		}
		listener, listenErr := net.Listen("tcp", fmt.Sprintf(":%d", port))
		if listenErr == nil {
			return listener, port, nil
		}
		lastErr = listenErr
	}
	return nil, 0, fmt.Errorf("端口 %d 起的 %d 个连续端口均不可用: %w", preferred, maxTries, lastErr)
}

// RuntimeDir 是端口公告文件的相对目录名。
// 写在这里而不是配置文件目录，是为了避免和 config/ 的 gitignore 规则混淆。
const RuntimeDir = ".runtime"

// PublishRecord 是写给脚本/CI/前端 dev server 的机器可读端口公告。
// 端口自动顺延后，光看日志不够——前端拿不到新端口就等于没解决。
type PublishRecord struct {
	Service   string `json:"service"`
	Port      int    `json:"port"`
	StartedAt string `json:"started_at"`
}

// Publish 把实际监听端口写到 <dir>/<RuntimeDir>/<name>.json。
// dir 为空则写到当前工作目录；写失败不影响服务启动，只返回错误供调用方打日志。
func Publish(dir, name string, port int) (string, error) {
	if name == "" {
		return "", fmt.Errorf("service 名称不能为空")
	}
	path := filepath.Join(dir, RuntimeDir, name+".json")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return "", fmt.Errorf("创建目录失败: %w", err)
	}
	rec, err := json.Marshal(PublishRecord{
		Service:   name,
		Port:      port,
		StartedAt: time.Now().UTC().Format(time.RFC3339),
	})
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(path, append(rec, '\n'), 0o644); err != nil {
		return "", fmt.Errorf("写入端口公告失败: %w", err)
	}
	return path, nil
}

func portFromAddr(addr net.Addr) (int, error) {
	_, portStr, err := net.SplitHostPort(addr.String())
	if err != nil {
		return 0, err
	}
	return strconv.Atoi(portStr)
}
