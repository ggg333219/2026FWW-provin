package service

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

const testAPIKey = "app-test-key"

func TestDetectReteachIntent(t *testing.T) {
	tests := []struct {
		question string
		want     bool
	}{
		{"这段我听不懂，能再讲一遍吗？", true},
		{"请解释一下这个概念", true},
		{"什么是机器学习？", false},
		{"", false},
	}

	for _, tt := range tests {
		if got := detectReteachIntent(tt.question); got != tt.want {
			t.Fatalf("detectReteachIntent(%q) = %v, want %v", tt.question, got, tt.want)
		}
	}
}

func TestParseSSEAnswer(t *testing.T) {
	body := []byte("data: {\"answer\":\"第一段\"}\n\ndata: {\"answer\":\"最终答案\"}\n\n")
	if got := parseSSEAnswer(body); got != "最终答案" {
		t.Fatalf("parseSSEAnswer() = %q, want %q", got, "最终答案")
	}
}

func TestDecodeWorkflowOutput(t *testing.T) {
	t.Run("result string json", func(t *testing.T) {
		var out GenerateScriptResponse
		err := decodeWorkflowOutput(map[string]interface{}{
			"result": `{"page":2,"script":"hello","mindmap_markdown":"# map"}`,
		}, &out)
		if err != nil {
			t.Fatalf("decodeWorkflowOutput returned error: %v", err)
		}
		if out.Page != 2 || out.Script != "hello" {
			t.Fatalf("unexpected decode result: %+v", out)
		}
	})

	t.Run("nested object", func(t *testing.T) {
		var out ParseKnowledgeResponse
		err := decodeWorkflowOutput(map[string]interface{}{
			"data": map[string]interface{}{
				"structure": []map[string]interface{}{
					{"name": "第一章"},
				},
			},
		}, &out)
		if err != nil {
			t.Fatalf("decodeWorkflowOutput returned error: %v", err)
		}
		if len(out.Structure) != 1 || out.Structure[0].Name != "第一章" {
			t.Fatalf("unexpected decode result: %+v", out)
		}
	})

	t.Run("empty outputs", func(t *testing.T) {
		var out GenerateScriptResponse
		err := decodeWorkflowOutput(nil, &out)
		if err == nil {
			t.Fatal("expected error for nil outputs")
		}
	})
}

func TestAskWithContext_BlockingResponse(t *testing.T) {
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/chat-messages": func(w http.ResponseWriter, r *http.Request) {
			assertBearerToken(t, r, testAPIKey)
			var payload map[string]interface{}
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				t.Fatalf("decode chat payload: %v", err)
			}
			if payload["query"] != "什么是梯度下降？" {
				t.Fatalf("unexpected query: %v", payload["query"])
			}
			inputs, _ := payload["inputs"].(map[string]interface{})
			if inputs["scene"] != difySceneAskWithContext {
				t.Fatalf("unexpected scene: %v", inputs["scene"])
			}
			if inputs["current_page"].(float64) != 3 {
				t.Fatalf("unexpected current_page: %v", inputs["current_page"])
			}

			_ = json.NewEncoder(w).Encode(map[string]string{
				"answer": "梯度下降是一种优化算法。",
			})
		},
	})
	defer server.Close()

	client := NewDifyClient(server.URL, testAPIKey)
	resp, err := client.AskWithContext(context.Background(), AskWithContextRequest{
		Question:    "什么是梯度下降？",
		CurrentPage: 3,
		Context:     "机器学习基础",
		Mode:        "llm",
	})
	if err != nil {
		t.Fatalf("AskWithContext returned error: %v", err)
	}
	if resp.Answer != "梯度下降是一种优化算法。" {
		t.Fatalf("unexpected answer: %q", resp.Answer)
	}
	if resp.Intent.NeedReteach {
		t.Fatal("expected no reteach intent")
	}
}

func TestAskWithContext_StructuredJSONAnswer(t *testing.T) {
	structured := AskWithContextResponse{
		Question:   "请总结",
		Answer:     "结构化答案",
		SourcePage: 5,
		ResumePage: 5,
	}
	structured.Intent.NeedReteach = true
	structured.Intent.Reason = "用户要求重讲"

	payload, _ := json.Marshal(structured)
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/chat-messages": func(w http.ResponseWriter, r *http.Request) {
			_ = json.NewEncoder(w).Encode(map[string]string{"answer": string(payload)})
		},
	})
	defer server.Close()

	client := NewDifyClient(server.URL, testAPIKey)
	resp, err := client.AskWithContext(context.Background(), AskWithContextRequest{
		Question: "请总结",
		Mode:     "llm",
	})
	if err != nil {
		t.Fatalf("AskWithContext returned error: %v", err)
	}
	if resp.Answer != "结构化答案" || !resp.Intent.NeedReteach {
		t.Fatalf("unexpected structured response: %+v", resp)
	}
}

func TestGenerateScript_WorkflowSuccess(t *testing.T) {
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/workflows/run": func(w http.ResponseWriter, r *http.Request) {
			var payload struct {
				Inputs map[string]interface{} `json:"inputs"`
			}
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				t.Fatalf("decode workflow payload: %v", err)
			}
			if payload.Inputs["scene"] != difySceneGenerateScript {
				t.Fatalf("unexpected scene: %v", payload.Inputs["scene"])
			}
			if payload.Inputs["page"].(float64) != 1 {
				t.Fatalf("unexpected page: %v", payload.Inputs["page"])
			}

			writeWorkflowResult(w, GenerateScriptResponse{
				Page:            1,
				Script:          "这是第一页讲稿",
				MindmapMarkdown: "# 第一页",
			})
		},
	})
	defer server.Close()

	client := NewDifyClient(server.URL, testAPIKey)
	resp, err := client.GenerateScript(context.Background(), GenerateScriptRequest{
		Page:       1,
		Content:    "PPT 内容",
		CourseName: "人工智能导论",
		Mode:       "llm",
	})
	if err != nil {
		t.Fatalf("GenerateScript returned error: %v", err)
	}
	if resp.Script != "这是第一页讲稿" {
		t.Fatalf("unexpected script: %q", resp.Script)
	}
}

func TestParseKnowledge_WorkflowSuccess(t *testing.T) {
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/workflows/run": func(w http.ResponseWriter, r *http.Request) {
			writeWorkflowResult(w, ParseKnowledgeResponse{
				Structure: []KnowledgeNode{
					{Name: "线性代数", Children: []KnowledgeNode{{Name: "矩阵"}}},
				},
			})
		},
	})
	defer server.Close()

	client := NewDifyClient(server.URL, testAPIKey)
	resp, err := client.ParseKnowledge(context.Background(), ParseKnowledgeRequest{
		Text: "线性代数与矩阵",
		Mode: "llm",
	})
	if err != nil {
		t.Fatalf("ParseKnowledge returned error: %v", err)
	}
	if len(resp.Structure) != 1 || resp.Structure[0].Name != "线性代数" {
		t.Fatalf("unexpected structure: %+v", resp.Structure)
	}
}

func TestParseDocument_UploadAndWorkflow(t *testing.T) {
	var uploadedFilename string
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/files/upload": func(w http.ResponseWriter, r *http.Request) {
			if err := r.ParseMultipartForm(1 << 20); err != nil {
				t.Fatalf("parse multipart: %v", err)
			}
			file, header, err := r.FormFile("file")
			if err != nil {
				t.Fatalf("read uploaded file: %v", err)
			}
			defer file.Close()
			content, _ := io.ReadAll(file)
			if string(content) != "sample ppt content" {
				t.Fatalf("unexpected file content: %q", string(content))
			}
			uploadedFilename = header.Filename
			_ = json.NewEncoder(w).Encode(map[string]string{"id": "file-123"})
		},
		"/v1/workflows/run": func(w http.ResponseWriter, r *http.Request) {
			var payload struct {
				Inputs map[string]interface{} `json:"inputs"`
			}
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				t.Fatalf("decode workflow payload: %v", err)
			}
			if payload.Inputs["scene"] != difySceneParseDocument {
				t.Fatalf("unexpected scene: %v", payload.Inputs["scene"])
			}
			fileInput, _ := payload.Inputs["file"].(map[string]interface{})
			if fileInput["upload_file_id"] != "file-123" {
				t.Fatalf("unexpected upload_file_id: %v", fileInput["upload_file_id"])
			}

			writeWorkflowResult(w, ParseDocumentResponse{
				DocID:      "doc-1",
				DocName:    "demo.pptx",
				DocType:    "pptx",
				TotalPages: 2,
				ParsedPages: []ParsedPage{
					{Page: 1, Content: "page 1", ContentLength: 6},
				},
			})
		},
	})
	defer server.Close()

	client := NewDifyClient(server.URL, testAPIKey)
	resp, err := client.ParseDocument(context.Background(), newTestFileHeader(t, "demo.pptx", "sample ppt content"))
	if err != nil {
		t.Fatalf("ParseDocument returned error: %v", err)
	}
	if uploadedFilename != "demo.pptx" {
		t.Fatalf("unexpected uploaded filename: %q", uploadedFilename)
	}
	if resp.DocID != "doc-1" || resp.TotalPages != 2 {
		t.Fatalf("unexpected parse response: %+v", resp)
	}
}

func TestReconstructDocument_WorkflowSuccess(t *testing.T) {
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/workflows/run": func(w http.ResponseWriter, r *http.Request) {
			writeWorkflowResult(w, ReconstructDocumentResponse{
				DocID:   "doc-1",
				DocName: "demo.pptx",
				Chapters: []ReconstructedChapter{
					{ChapterID: "ch1", Title: "绪论", NodeIDs: []string{"p1_n1"}},
				},
			})
		},
	})
	defer server.Close()

	client := NewDifyClient(server.URL, testAPIKey)
	resp, err := client.ReconstructDocument(context.Background(), ReconstructDocumentRequest{
		ParsedDocument: map[string]any{"doc_id": "doc-1"},
		Mode:           "llm",
	})
	if err != nil {
		t.Fatalf("ReconstructDocument returned error: %v", err)
	}
	if len(resp.Chapters) != 1 || resp.Chapters[0].Title != "绪论" {
		t.Fatalf("unexpected reconstruct response: %+v", resp)
	}
}

func TestGenerateNodeScript_WorkflowSuccess(t *testing.T) {
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/workflows/run": func(w http.ResponseWriter, r *http.Request) {
			writeWorkflowResult(w, GenerateNodeScriptResponse{
				NodeID:  "p1_n1",
				Title:   "绪论",
				Script:  "同学们好",
				ReteachScript: "我们换个角度再讲",
			})
		},
	})
	defer server.Close()

	client := NewDifyClient(server.URL, testAPIKey)
	resp, err := client.GenerateNodeScript(context.Background(), GenerateNodeScriptRequest{
		TeachingNode: map[string]any{"node_id": "p1_n1", "title": "绪论"},
		CourseName:   "AI 导论",
		Mode:         "llm",
	})
	if err != nil {
		t.Fatalf("GenerateNodeScript returned error: %v", err)
	}
	if resp.NodeID != "p1_n1" || resp.Script != "同学们好" {
		t.Fatalf("unexpected node script: %+v", resp)
	}
}

func TestGenerateFromMarkdown_WorkflowSuccess(t *testing.T) {
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/workflows/run": func(w http.ResponseWriter, r *http.Request) {
			writeWorkflowResult(w, GenerateFromMarkdownResponse{
				CourseName: "AI 导论",
				KeyPoints:  []string{"监督学习", "无监督学习"},
				NodeTree: PipelineNodeTree{
					Nodes: []PipelineNode{{NodeID: "n1", Title: "机器学习"}},
				},
			})
		},
	})
	defer server.Close()

	client := NewDifyClient(server.URL, testAPIKey)
	resp, err := client.GenerateFromMarkdown(context.Background(), GenerateFromMarkdownRequest{
		Markdown:   "# 机器学习",
		CourseName: "AI 导论",
		Mode:       "llm",
	})
	if err != nil {
		t.Fatalf("GenerateFromMarkdown returned error: %v", err)
	}
	if len(resp.KeyPoints) != 2 || resp.NodeTree.Nodes[0].Title != "机器学习" {
		t.Fatalf("unexpected markdown response: %+v", resp)
	}
}

func TestGenerateAudio_WorkflowSuccess(t *testing.T) {
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/workflows/run": func(w http.ResponseWriter, r *http.Request) {
			writeWorkflowResult(w, GenerateAudioResponse{
				AudioID:       "audio-1",
				AudioURL:      "http://example.com/audio.mp3",
				Status:        "ready",
				TotalDuration: 120,
			})
		},
	})
	defer server.Close()

	client := NewDifyClient(server.URL, testAPIKey)
	resp, err := client.GenerateAudio(context.Background(), GenerateAudioRequest{
		CourseID:  "course-1",
		Page:      1,
		VoiceType: "female",
		Format:    "mp3",
		Provider:  "dashscope",
		Nodes: []GenerateAudioNode{
			{NodeID: "p1_n1", Title: "绪论", Text: "同学们好"},
		},
	})
	if err != nil {
		t.Fatalf("GenerateAudio returned error: %v", err)
	}
	if resp.AudioID != "audio-1" || resp.Status != "ready" {
		t.Fatalf("unexpected audio response: %+v", resp)
	}
}

func TestDifyClient_FallbackOnWorkflowFailure(t *testing.T) {
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/workflows/run": func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
			_, _ = w.Write([]byte(`{"message":"workflow unavailable"}`))
		},
	})
	defer server.Close()

	fallback := &mockAIEngine{
		generateScriptResp: &GenerateScriptResponse{
			Page:   2,
			Script: "fallback script",
		},
	}
	client := NewDifyClientWithFallback(server.URL, testAPIKey, testAPIKey, fallback)

	resp, err := client.GenerateScript(context.Background(), GenerateScriptRequest{
		Page:    2,
		Content: "content",
		Mode:    "llm",
	})
	if err != nil {
		t.Fatalf("GenerateScript returned error: %v", err)
	}
	if resp.Script != "fallback script" {
		t.Fatalf("expected fallback script, got %q", resp.Script)
	}
	if fallback.generateScriptCalls != 1 {
		t.Fatalf("expected fallback to be called once, got %d", fallback.generateScriptCalls)
	}
}

func TestDifyClient_FallbackOnChatFailure(t *testing.T) {
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/chat-messages": func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusBadGateway)
			_, _ = w.Write([]byte(`{"message":"chat unavailable"}`))
		},
	})
	defer server.Close()

	fallback := &mockAIEngine{
		askResp: &AskWithContextResponse{Answer: "fallback answer"},
	}
	client := NewDifyClientWithFallback(server.URL, testAPIKey, testAPIKey, fallback)

	resp, err := client.AskWithContext(context.Background(), AskWithContextRequest{
		Question: "test",
		Mode:     "llm",
	})
	if err != nil {
		t.Fatalf("AskWithContext returned error: %v", err)
	}
	if resp.Answer != "fallback answer" {
		t.Fatalf("expected fallback answer, got %q", resp.Answer)
	}
	if fallback.askCalls != 1 {
		t.Fatalf("expected fallback ask once, got %d", fallback.askCalls)
	}
}

func TestGenerateScript_NoFallbackReturnsError(t *testing.T) {
	server := newDifyTestServer(t, map[string]http.HandlerFunc{
		"/v1/workflows/run": func(w http.ResponseWriter, r *http.Request) {
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"data": map[string]interface{}{
					"status": "failed",
					"error":  "invalid scene",
				},
			})
		},
	})
	defer server.Close()

	client := NewDifyClient(server.URL, testAPIKey)
	_, err := client.GenerateScript(context.Background(), GenerateScriptRequest{Page: 1, Mode: "llm"})
	if err == nil {
		t.Fatal("expected error when workflow failed and no fallback configured")
	}
	if !strings.Contains(err.Error(), "workflow 执行失败") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestParseDocument_NilFile(t *testing.T) {
	client := NewDifyClient("http://127.0.0.1:1", testAPIKey)
	_, err := client.ParseDocument(context.Background(), nil)
	if err == nil {
		t.Fatal("expected error for nil file")
	}
	if !strings.Contains(err.Error(), "文件不能为空") {
		t.Fatalf("unexpected error: %v", err)
	}
}

type mockAIEngine struct {
	askCalls              int
	generateScriptCalls   int
	parseDocumentCalls    int
	askResp               *AskWithContextResponse
	generateScriptResp    *GenerateScriptResponse
	parseDocumentResp     *ParseDocumentResponse
}

func (m *mockAIEngine) ParseDocument(context.Context, *multipart.FileHeader) (*ParseDocumentResponse, error) {
	m.parseDocumentCalls++
	return m.parseDocumentResp, nil
}
func (m *mockAIEngine) ReconstructDocument(context.Context, ReconstructDocumentRequest) (*ReconstructDocumentResponse, error) {
	return nil, nil
}
func (m *mockAIEngine) GenerateNodeScript(context.Context, GenerateNodeScriptRequest) (*GenerateNodeScriptResponse, error) {
	return nil, nil
}
func (m *mockAIEngine) GenerateFromMarkdown(context.Context, GenerateFromMarkdownRequest) (*GenerateFromMarkdownResponse, error) {
	return nil, nil
}
func (m *mockAIEngine) GenerateScript(context.Context, GenerateScriptRequest) (*GenerateScriptResponse, error) {
	m.generateScriptCalls++
	return m.generateScriptResp, nil
}
func (m *mockAIEngine) GenerateAudio(context.Context, GenerateAudioRequest) (*GenerateAudioResponse, error) {
	return nil, nil
}
func (m *mockAIEngine) AskWithContext(context.Context, AskWithContextRequest) (*AskWithContextResponse, error) {
	m.askCalls++
	return m.askResp, nil
}
func (m *mockAIEngine) ParseKnowledge(context.Context, ParseKnowledgeRequest) (*ParseKnowledgeResponse, error) {
	return nil, nil
}

func newDifyTestServer(t *testing.T, handlers map[string]http.HandlerFunc) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handler, ok := handlers[r.URL.Path]
		if !ok {
			t.Fatalf("unexpected request path: %s", r.URL.Path)
		}
		handler(w, r)
	}))
}

func writeWorkflowResult(w http.ResponseWriter, result interface{}) {
	payload, err := json.Marshal(result)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"data": map[string]interface{}{
			"status": "succeeded",
			"outputs": map[string]interface{}{
				"result": string(payload),
			},
		},
	})
}

func assertBearerToken(t *testing.T, r *http.Request, want string) {
	t.Helper()
	auth := r.Header.Get("Authorization")
	if auth != "Bearer "+want {
		t.Fatalf("unexpected authorization header: %q", auth)
	}
}

func newTestFileHeader(t *testing.T, filename, content string) *multipart.FileHeader {
	t.Helper()

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	part, err := writer.CreateFormFile("file", filename)
	if err != nil {
		t.Fatalf("create form file: %v", err)
	}
	if _, err := io.WriteString(part, content); err != nil {
		t.Fatalf("write form file content: %v", err)
	}
	if err := writer.Close(); err != nil {
		t.Fatalf("close multipart writer: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/upload", body)
	req.Header.Set("Content-Type", writer.FormDataContentType())
	if err := req.ParseMultipartForm(1 << 20); err != nil {
		t.Fatalf("parse multipart form: %v", err)
	}
	files := req.MultipartForm.File["file"]
	if len(files) == 0 {
		t.Fatal("multipart file not found")
	}
	return files[0]
}
