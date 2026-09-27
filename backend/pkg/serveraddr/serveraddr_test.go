package serveraddr

import (
	"encoding/json"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"testing"
)

// freePort 先占住一个端口再释放，得到一个大概率仍可用的端口。
func freePort(t *testing.T) int {
	t.Helper()
	ln, err := net.Listen("tcp", ":0")
	if err != nil {
		t.Fatalf("获取空闲端口失败: %v", err)
	}
	port, err := portFromAddr(ln.Addr())
	if err != nil {
		t.Fatalf("解析端口失败: %v", err)
	}
	_ = ln.Close()
	return port
}

func TestResolveUsesPreferredPortWhenFree(t *testing.T) {
	port := freePort(t)
	ln, got, err := Resolve(port, DefaultMaxTries)
	if err != nil {
		t.Fatalf("Resolve 失败: %v", err)
	}
	defer ln.Close()
	if got != port {
		t.Fatalf("应使用首选端口 %d，实际 %d", port, got)
	}
}

func TestResolveRollsOverToNextPort(t *testing.T) {
	// 先占住首选端口——不 kill 这个"服务"，而是让 Resolve 绕开它。
	taken, err := net.Listen("tcp", ":0")
	if err != nil {
		t.Fatalf("占用端口失败: %v", err)
	}
	defer taken.Close()
	want, err := portFromAddr(taken.Addr())
	if err != nil {
		t.Fatalf("解析端口失败: %v", err)
	}

	ln, got, err := Resolve(want, DefaultMaxTries)
	if err != nil {
		t.Fatalf("Resolve 应顺延而非失败: %v", err)
	}
	defer ln.Close()
	if got <= want {
		t.Fatalf("不应返回已被占用的端口 %d（实际 %d）", want, got)
	}
	if got > want+DefaultMaxTries {
		t.Fatalf("顺延范围异常: 首选 %d, 实际 %d", want, got)
	}
}

func TestResolveExhaustionLeavesOccupantsAlone(t *testing.T) {
	// 占住连续两个端口。Resolve 应该报"没有可用端口"，
	// 而且绝不能反过来去关掉这些 listener——被占用的服务要留着。
	occupants := map[int]*net.TCPListener{}
	var first int
	for i := 0; i < 2; i++ {
		ln, err := net.Listen("tcp", ":0")
		if err != nil {
			t.Fatalf("占用端口失败: %v", err)
		}
		p, err := portFromAddr(ln.Addr())
		if err != nil {
			ln.Close()
			t.Fatalf("解析端口失败: %v", err)
		}
		if i == 0 {
			first = p
		}
		occupants[p] = ln.(*net.TCPListener)
	}
	// 再占住 first+1，把顺延路也堵住。
	if next, err := net.Listen("tcp", ":"+strconv.Itoa(first+1)); err == nil {
		defer next.Close()
	}
	defer func() {
		for _, ln := range occupants {
			_ = ln.Close()
		}
	}()

	ln, got, err := Resolve(first, 2)
	if err == nil {
		if ln != nil {
			_ = ln.Close()
		}
		t.Fatalf("两个端口都被占时应返回错误，实际返回 %d", got)
	}
	if got != 0 {
		t.Fatalf("失败时应返回 0，实际 %d", got)
	}
	// 关键断言：占用者还活着，没有被我们"顺手"关掉。
	for p, occ := range occupants {
		if _, err := occ.SyscallConn(); err != nil {
			t.Fatalf("占用端口 %d 的 listener 已被破坏: %v", p, err)
		}
	}
}

func TestResolveZeroMeansSystemAssigned(t *testing.T) {
	ln, got, err := Resolve(0, DefaultMaxTries)
	if err != nil {
		t.Fatalf("Resolve 失败: %v", err)
	}
	defer ln.Close()
	if got <= 0 {
		t.Fatalf("应由系统分配端口，实际 %d", got)
	}
	// 返回的 listener 必须是活的，供 gin.RunListener 直接复用。
	if ln.Addr() == nil {
		t.Fatal("返回的 listener 无地址")
	}
}

func TestPublishWritesMachineReadableRecord(t *testing.T) {
	dir := t.TempDir()
	path, err := Publish(dir, "teacher", 8082)
	if err != nil {
		t.Fatalf("Publish 失败: %v", err)
	}
	if filepath.Base(filepath.Dir(path)) != RuntimeDir {
		t.Fatalf("应写入 %s 目录，实际 %s", RuntimeDir, path)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("读取公告文件失败: %v", err)
	}
	var rec PublishRecord
	if err := json.Unmarshal(raw, &rec); err != nil {
		t.Fatalf("公告文件不是合法 JSON: %v", err)
	}
	if rec.Service != "teacher" || rec.Port != 8082 || rec.StartedAt == "" {
		t.Fatalf("公告内容不完整: %+v", rec)
	}
}

func TestPublishEmptyName(t *testing.T) {
	if _, err := Publish(t.TempDir(), "", 8082); err == nil {
		t.Fatal("空服务名应报错")
	}
}
