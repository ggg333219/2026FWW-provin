package serveraddr

import (
	"fmt"
	"net/http"
)

// LogFunc 与 zap.SugaredLogger.Warnf / fmt.Printf 的签名一致，
// 调用方可以直接传 applogger.Sugar.Warnf，无需在 serveraddr 里引入 gin 或 zap。
type LogFunc func(format string, args ...any)

// Serve 把 handler 绑到一个可用端口上阻塞服务。
//
// preferred 被占用时顺延，不终止占用方；实际端口通过 log 通知，
// 并写入 <dir>/.runtime/<service>.json 作为机器可读的端口公告。
// log 为空时安静处理（测试用）。
func Serve(handler http.Handler, preferred int, service, dir string, log LogFunc) error {
	ln, port, err := Resolve(preferred, DefaultMaxTries)
	if err != nil {
		return fmt.Errorf("服务 %q 没有可用端口: %w", service, err)
	}
	if preferred > 0 && port != preferred {
		say(log, "%s: 配置端口 %d 已被其他程序占用，本次改用 %d（不会终止占用方）", service, preferred, port)
	}
	if path, pubErr := Publish(dir, service, port); pubErr != nil {
		say(log, "%s: 端口公告写入失败: %v", service, pubErr)
	} else {
		say(log, "%s: 端口公告 %s", service, path)
	}
	say(log, "%s: 监听 http://0.0.0.0:%d", service, port)
	say(log, "%s: 本机访问 http://localhost:%d  健康检查 http://localhost:%d/health", service, port, port)
	return http.Serve(ln, handler)
}

func say(log LogFunc, format string, args ...any) {
	if log != nil {
		log(format, args...)
	}
}
