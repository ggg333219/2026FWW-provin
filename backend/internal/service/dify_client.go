package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"strings"
	"time"
)

// DifyClient 实现 AIEngine 接口，与 Dify API 交互
type DifyClient struct {
	baseURL  string
	apiKey   string
	client   *http.Client
	debug    bool
	fallback any
}

// NewDifyClient 创建新的 Dify 客户端
func NewDifyClient(baseURL, apiKey string) *DifyClient {
	if baseURL == "" {
		baseURL = "http://127.0.0.1:18001"
	}
	// 移除末尾的斜杠
	baseURL = strings.TrimSuffix(baseURL, "/")

	return &DifyClient{
		baseURL: baseURL,
		apiKey:  apiKey,
		client: &http.Client{
			Timeout: 60 * time.Second,
		},
		debug: false,
	}
}

// NewDifyClientWithFallback creates a Dify client with an optional local AI fallback.
// fallbackAPIKey is retained for compatibility with the original constructor contract.
func NewDifyClientWithFallback(baseURL, apiKey, fallbackAPIKey string, fallback any) *DifyClient {
	_ = fallbackAPIKey
	client := NewDifyClient(baseURL, apiKey)
	client.fallback = fallback
	return client
}

// SetDebug 设置是否输出调试信息
func (c *DifyClient) SetDebug(debug bool) {
	c.debug = debug
}

// AskWithContext 调用 Dify 对话接口
func (c *DifyClient) AskWithContext(ctx context.Context, req AskWithContextRequest) (*AskWithContextResponse, error) {
	url := fmt.Sprintf("%s/v1/chat-messages", c.baseURL)

	// 构建请求体
	payload := map[string]interface{}{
		"query": req.Question,
		"user":  "smart-teaching-backend",
	}

	// 如果有上下文信息，添加到 inputs
	if strings.TrimSpace(req.Context) != "" {
		payload["inputs"] = map[string]interface{}{
			"context": req.Context,
		}
	}
	inputs, _ := payload["inputs"].(map[string]interface{})
	if inputs == nil {
		inputs = map[string]interface{}{}
	}
	inputs["scene"] = difySceneAskWithContext
	inputs["current_page"] = req.CurrentPage
	payload["inputs"] = inputs

	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	if c.debug {
		fmt.Printf("[DifyClient] Request URL: %s\n", url)
		fmt.Printf("[DifyClient] Request Body: %s\n", string(body))
	}

	// 创建请求
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewBuffer(body))
	if err != nil {
		return nil, err
	}

	// 设置请求头
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.apiKey))

	// 发送请求
	httpResp, err := c.client.Do(httpReq)
	if err != nil {
		return c.askFallback(ctx, req, fmt.Errorf("Dify 服务调用失败: %w", err))
	}
	defer httpResp.Body.Close()

	respBody, err := io.ReadAll(httpResp.Body)
	if err != nil {
		return c.askFallback(ctx, req, err)
	}

	if c.debug {
		fmt.Printf("[DifyClient] Response Status: %d\n", httpResp.StatusCode)
		fmt.Printf("[DifyClient] Response Body: %s\n", string(respBody))
	}

	if httpResp.StatusCode >= 300 {
		return c.askFallback(ctx, req, fmt.Errorf("Dify 服务返回异常状态: %d", httpResp.StatusCode))
	}

	// 处理 Dify 流式响应或 blocking JSON 响应
	// Dify 返回 SSE (Server-Sent Events) 格式，每行格式为 "data: {...}"
	lines := strings.Split(string(respBody), "\n")
	var answer string
	var lastEvent map[string]interface{}

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || !strings.HasPrefix(line, "data:") {
			continue
		}

		// 移除 "data: " 前缀
		dataStr := strings.TrimPrefix(line, "data:")
		dataStr = strings.TrimSpace(dataStr)

		var event map[string]interface{}
		if err := json.Unmarshal([]byte(dataStr), &event); err != nil {
			continue
		}

		lastEvent = event

		// 从 "answer" 字段中提取答案
		if msg, ok := event["answer"].(string); ok {
			answer = msg
		}
	}
	if answer == "" {
		var blocking struct {
			Answer string `json:"answer"`
		}
		if json.Unmarshal(respBody, &blocking) == nil {
			answer = blocking.Answer
		}
	}

	// 如果是流式响应结束，从最后一条消息中提取最终答案
	if answer == "" && lastEvent != nil {
		if msg, ok := lastEvent["answer"].(string); ok {
			answer = msg
		}
	}

	result := &AskWithContextResponse{
		Question:           req.Question,
		SourcePage:         0,
		SourceExcerpt:      "",
		Answer:             answer,
		UsedFallback:       false,
		FallbackReason:     "",
		ResumePage:         0,
		FollowUpSuggestion: "",
	}
	result.Intent.NeedReteach = false
	result.Intent.Reason = ""

	if strings.TrimSpace(answer) == "" {
		return c.askFallback(ctx, req, fmt.Errorf("Dify 响应未包含 answer"))
	}
	// 允许 Dify 返回结构化的答疑 JSON，同时保留普通文本答案。
	var structured AskWithContextResponse
	if json.Unmarshal([]byte(answer), &structured) == nil && structured.Answer != "" {
		structured.Question = req.Question
		return &structured, nil
	}
	return result, nil
}

func (c *DifyClient) askFallback(ctx context.Context, req AskWithContextRequest, cause error) (*AskWithContextResponse, error) {
	if c.fallback == nil {
		return nil, cause
	}
	fallback, ok := c.fallback.(interface {
		AskWithContext(context.Context, AskWithContextRequest) (*AskWithContextResponse, error)
	})
	if !ok {
		return nil, cause
	}
	resp, err := fallback.AskWithContext(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("Dify 调用失败，回退也失败: %w", err)
	}
	resp.UsedFallback = true
	resp.FallbackReason = cause.Error()
	return resp, nil
}

// ParseDocument 解析文档
func (c *DifyClient) ParseDocument(ctx context.Context, file *multipart.FileHeader) (*ParseDocumentResponse, error) {
	if file == nil {
		return nil, fmt.Errorf("文件不能为空")
	}

	src, err := file.Open()
	if err != nil {
		return nil, fmt.Errorf("打开上传文件失败: %w", err)
	}
	defer src.Close()

	content, err := io.ReadAll(src)
	if err != nil {
		return nil, fmt.Errorf("读取上传文件失败: %w", err)
	}
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("file", file.Filename)
	if err != nil {
		return nil, fmt.Errorf("构造 multipart 请求失败: %w", err)
	}
	if _, err := part.Write(content); err != nil {
		return nil, fmt.Errorf("写入 multipart 文件失败: %w", err)
	}
	if err := writer.Close(); err != nil {
		return nil, fmt.Errorf("关闭 multipart writer 失败: %w", err)
	}

	uploadReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/v1/files/upload", &body)
	if err != nil {
		return nil, fmt.Errorf("构造 Dify 上传请求失败: %w", err)
	}
	uploadReq.Header.Set("Content-Type", writer.FormDataContentType())
	uploadReq.Header.Set("Authorization", "Bearer "+c.apiKey)
	uploadResp, err := c.client.Do(uploadReq)
	if err != nil {
		return c.parseDocumentFallback(ctx, file, fmt.Errorf("Dify 文件上传失败: %w", err))
	}
	defer uploadResp.Body.Close()
	if uploadResp.StatusCode >= 300 {
		return c.parseDocumentFallback(ctx, file, fmt.Errorf("Dify 文件上传返回异常状态: %d", uploadResp.StatusCode))
	}
	var uploaded struct {
		ID string `json:"id"`
	}
	if err := json.NewDecoder(uploadResp.Body).Decode(&uploaded); err != nil || uploaded.ID == "" {
		return c.parseDocumentFallback(ctx, file, fmt.Errorf("Dify 文件上传响应缺少 id"))
	}

	var result ParseDocumentResponse
	err = c.runWorkflow(ctx, difySceneParseDocument, map[string]any{
		"file": map[string]any{
			"upload_file_id":  uploaded.ID,
			"transfer_method": "local_file",
		},
	}, &result)
	if err != nil {
		return c.parseDocumentFallback(ctx, file, err)
	}
	return &result, nil
}

func (c *DifyClient) parseDocumentFallback(ctx context.Context, file *multipart.FileHeader, cause error) (*ParseDocumentResponse, error) {
	if c.fallback != nil {
		fallback, ok := c.fallback.(interface {
			ParseDocument(context.Context, *multipart.FileHeader) (*ParseDocumentResponse, error)
		})
		if !ok {
			return nil, cause
		}
		resp, err := fallback.ParseDocument(ctx, file)
		if err == nil {
			return resp, nil
		}
	}
	return nil, cause
}

// ReconstructDocument 重建文档
func (c *DifyClient) ReconstructDocument(ctx context.Context, req ReconstructDocumentRequest) (*ReconstructDocumentResponse, error) {
	var out ReconstructDocumentResponse
	if err := c.postJSON(ctx, "/reconstruct-document", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// GenerateNodeScript 生成节点脚本
func (c *DifyClient) GenerateNodeScript(ctx context.Context, req GenerateNodeScriptRequest) (*GenerateNodeScriptResponse, error) {
	var out GenerateNodeScriptResponse
	if err := c.postJSON(ctx, "/generate-node-script", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// GenerateFromMarkdown 从 Markdown 生成
func (c *DifyClient) GenerateFromMarkdown(ctx context.Context, req GenerateFromMarkdownRequest) (*GenerateFromMarkdownResponse, error) {
	var out GenerateFromMarkdownResponse
	if err := c.postJSON(ctx, "/generate-from-markdown", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// GenerateScript 生成脚本
func (c *DifyClient) GenerateScript(ctx context.Context, req GenerateScriptRequest) (*GenerateScriptResponse, error) {
	var out GenerateScriptResponse
	if err := c.postJSON(ctx, "/generate-script", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// GenerateAudio 生成音频
func (c *DifyClient) GenerateAudio(ctx context.Context, req GenerateAudioRequest) (*GenerateAudioResponse, error) {
	var out GenerateAudioResponse
	if err := c.postJSON(ctx, "/generate-audio", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ParseKnowledge 解析知识
func (c *DifyClient) ParseKnowledge(ctx context.Context, req ParseKnowledgeRequest) (*ParseKnowledgeResponse, error) {
	var out ParseKnowledgeResponse
	if err := c.postJSON(ctx, "/parse-knowledge", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// postJSON 尝试先调用 Dify, 若失败则回退到本地 AI 引擎
func (c *DifyClient) postJSON(ctx context.Context, path string, reqBody any, out any) error {
	inputs, err := structToMap(reqBody)
	if err != nil {
		return err
	}
	scene := map[string]string{
		"/reconstruct-document":   difySceneReconstruct,
		"/generate-node-script":   difySceneGenerateNode,
		"/generate-from-markdown": difySceneGenerateMarkdown,
		"/generate-script":        difySceneGenerateScript,
		"/generate-audio":         difySceneGenerateAudio,
		"/parse-knowledge":        difySceneParseKnowledge,
	}[path]
	if scene == "" {
		return fmt.Errorf("未知 Dify workflow 路径: %s", path)
	}
	if err := c.runWorkflow(ctx, scene, inputs, out); err == nil {
		return nil
	} else if c.fallback != nil {
		return c.callFallback(ctx, path, reqBody, out, err)
	} else {
		return err
	}
}

func (c *DifyClient) runWorkflow(ctx context.Context, scene string, inputs map[string]any, out any) error {
	if inputs == nil {
		inputs = map[string]any{}
	}
	inputs["scene"] = scene
	payload := map[string]any{
		"inputs":        inputs,
		"response_mode": "blocking",
		"user":          "smart-teaching-backend",
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("序列化 workflow 请求失败: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/v1/workflows/run", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("构造 workflow 请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	resp, err := c.client.Do(req)
	if err != nil {
		return fmt.Errorf("Dify workflow 调用失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("workflow 返回异常状态: %d", resp.StatusCode)
	}
	var envelope struct {
		Data struct {
			Status  string         `json:"status"`
			Error   string         `json:"error"`
			Outputs map[string]any `json:"outputs"`
		} `json:"data"`
		Outputs map[string]any `json:"outputs"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&envelope); err != nil {
		return fmt.Errorf("解析 workflow 响应失败: %w", err)
	}
	if envelope.Data.Status == "failed" {
		return fmt.Errorf("workflow 执行失败: %s", envelope.Data.Error)
	}
	outputs := envelope.Data.Outputs
	if len(outputs) == 0 {
		outputs = envelope.Outputs
	}
	return decodeWorkflowOutput(outputs, out)
}

func structToMap(value any) (map[string]any, error) {
	body, err := json.Marshal(value)
	if err != nil {
		return nil, fmt.Errorf("序列化 workflow 输入失败: %w", err)
	}
	var result map[string]any
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("解析 workflow 输入失败: %w", err)
	}
	return result, nil
}

func (c *DifyClient) callFallback(ctx context.Context, path string, reqBody any, out any, cause error) error {
	switch path {
	case "/generate-script":
		fallback, ok := c.fallback.(interface {
			GenerateScript(context.Context, GenerateScriptRequest) (*GenerateScriptResponse, error)
		})
		if !ok {
			return fmt.Errorf("Dify 调用失败，回退客户端不支持 generate-script: %w", cause)
		}
		resp, err := fallback.GenerateScript(ctx, reqBody.(GenerateScriptRequest))
		if err == nil {
			*out.(*GenerateScriptResponse) = *resp
			return nil
		}
	case "/parse-knowledge":
		fallback, ok := c.fallback.(interface {
			ParseKnowledge(context.Context, ParseKnowledgeRequest) (*ParseKnowledgeResponse, error)
		})
		if !ok {
			return fmt.Errorf("Dify 调用失败，回退客户端不支持 parse-knowledge: %w", cause)
		}
		resp, err := fallback.ParseKnowledge(ctx, reqBody.(ParseKnowledgeRequest))
		if err == nil {
			*out.(*ParseKnowledgeResponse) = *resp
			return nil
		}
	}
	return fmt.Errorf("Dify 调用失败，回退也失败: %w", cause)
}
