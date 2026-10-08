package service

import (
	"context"
	"fmt"
	"strings"
	"time"
)

// ---- 局部内容生成的轮询参数 ----
//
// 用 var 而非 const：测试里要能把它们调小，否则一个用例要真等 90 秒。
var (
	contentPollInterval = 500 * time.Millisecond
	// 90s 是刻意留出的余量：前端的 MODIFY_LLM_TIMEOUT_MS 是 120s，
	// 前面还有一次 parse_modify 的往返与落快照的开销。宁可我们这边先超时、
	// 给出一句能看懂的错，也不要让 axios 直接 abort 成一句无头无尾的网络错误。
	contentPollBudget = 90 * time.Second
)

// contentStatusClient 是 WaitContentResult 唯一依赖的能力。
//
// courseware 侧注入的是 modifyClient（AIEngine 的一个小子集），handler 侧注入的
// 是完整 AIEngine。用窄接口接住，免得为了一个方法把整份 AIEngine 的要求带进来。
type contentStatusClient interface {
	ContentStatus(ctx context.Context, contentID string) (*GenContentStatusResponse, error)
}

// WaitContentResult 等待 /gen/content 的**异步任务**跑完并取回节点。
//
// 这是「局部修改从接入起就没真正生效过」的根因所在：/gen/content 起一个后台线程
// 就立刻返回（main.py 的 generate_content），首个响应里的 nodes **恒为空**。
// 调用方若直接把 resp.Nodes 交给 mergePartialResult，而后者开头就是
// `if len(partial) == 0 { return base }` —— 于是原样返回旧节点，可 modifiedIDs
// 照样被填成 target_ids，上层便报「已更新」，而返回给前端的内容一个字节都没变，
// 预览渲染出来自然一模一样。ContentStatus 这个轮询接口一直都在，
// 但此前只有 S3 讲稿进度页在用，修改路径从来没调用过。
//
// 失败一律返回 error 而不是静默退回旧节点：报「已更新」却什么都没改，
// 比直接报错更难排查。
//
// 包级函数而非方法：courseware 的局部重生成与 S3 内容层的单节点 AI 修改用的是
// 同一套等待语义，两处各写一份必然会在某次改动后分叉。
func WaitContentResult(
	ctx context.Context, client contentStatusClient, first *GenContentStatusResponse,
) ([]TeachingNodeItem, error) {
	if first == nil {
		return nil, fmt.Errorf("局部重生成失败: 引擎未返回任务信息")
	}
	// 引擎若哪天改成同步返回，这里直接放行，不必再改一遍。
	if len(first.Nodes) > 0 {
		return first.Nodes, nil
	}
	if first.ContentID == "" {
		return nil, fmt.Errorf("局部重生成失败: 引擎未返回 content_id，无法取回结果")
	}
	if client == nil {
		return nil, fmt.Errorf("局部重生成失败: AI 引擎客户端未初始化")
	}

	deadline := time.Now().Add(contentPollBudget)
	ticker := time.NewTicker(contentPollInterval)
	defer ticker.Stop()

	// 最后一次查询的错误要留着 —— 全是网络错误时，那句错比「超时」有用得多。
	var lastErr error
	for {
		select {
		case <-ctx.Done():
			return nil, fmt.Errorf("局部重生成已取消: %w", ctx.Err())
		case <-ticker.C:
		}

		if time.Now().After(deadline) {
			if lastErr != nil {
				return nil, fmt.Errorf("局部重生成超时（状态查询持续失败）: %w", lastErr)
			}
			return nil, fmt.Errorf(
				"局部重生成超时（%s 内未完成），请稍后在版本管理中查看任务结果", contentPollBudget,
			)
		}

		status, err := client.ContentStatus(ctx, first.ContentID)
		if err != nil {
			// 单次查询失败不当场放弃：任务在引擎侧照跑，抖动过去还能拿到结果。
			lastErr = err
			continue
		}
		lastErr = nil
		if status == nil {
			lastErr = fmt.Errorf("AI 引擎未返回内容生成状态")
			continue
		}

		if len(status.Nodes) > 0 {
			return status.Nodes, nil
		}

		switch strings.ToLower(strings.TrimSpace(status.Status)) {
		case "done", "completed", "success":
			// 任务自称完成却没有节点 —— 引擎侧出了问题，别拿旧内容糊弄过去。
			if status.Error != "" {
				return nil, fmt.Errorf("局部重生成失败: %s", status.Error)
			}
			return nil, fmt.Errorf("局部重生成失败: 任务已完成但未返回任何节点")
		case "failed", "error":
			if status.Error != "" {
				return nil, fmt.Errorf("局部重生成失败: %s", status.Error)
			}
			return nil, fmt.Errorf("局部重生成失败: 引擎返回状态 %s", status.Status)
		}
		// pending / generating / 其它：继续等。
	}
}
