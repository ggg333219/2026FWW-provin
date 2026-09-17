package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

const (
	difySceneAskWithContext    = "ask_with_context"
	difySceneGenerateScript    = "generate_script"
	difySceneParseDocument     = "parse_document"
	difySceneReconstruct       = "reconstruct_document"
	difySceneGenerateNode      = "generate_node_script"
	difySceneGenerateMarkdown  = "generate_from_markdown"
	difySceneGenerateAudio     = "generate_audio"
	difySceneParseKnowledge    = "parse_knowledge"
	difySceneIntentExtract     = "intent_extract"
	difySceneIntentConfirm     = "intent_confirm"
	difySceneParseProcess      = "parse_process"
	difySceneParseStatus       = "parse_status"
	difySceneParseVideo        = "parse_video"
	difySceneRAGSearch         = "rag_search"
	difySceneRAGEvidence       = "rag_evidence"
	difySceneKnowledgeUpload   = "knowledge_upload"
	difySceneGenerationCreate  = "generation_create"
	difySceneGenerationStatus  = "generation_status"
	difySceneGenerateOutline   = "generate_outline"
	difySceneReviseOutline     = "revise_outline"
	difySceneGenerationPreview = "generation_preview"
	difySceneGenerationModify  = "generation_modify"
	difySceneGenerationFinalize = "generation_finalize"
	difySceneVersionHistory    = "version_history"
	difySceneVersionLoad       = "version_load"
	difySceneVersionRollback   = "version_rollback"
	difySceneVersionLock       = "version_lock"
	difySceneExportCreate      = "export_create"
	difySceneExportStatus      = "export_status"
)

func detectReteachIntent(question string) bool {
	question = strings.TrimSpace(question)
	if question == "" {
		return false
	}
	for _, marker := range []string{"听不懂", "没听懂", "不明白", "再讲一遍", "重讲", "再解释", "解释一下", "不会", "不理解"} {
		if strings.Contains(question, marker) {
			return true
		}
	}
	return false
}

func parseSSEAnswer(body []byte) string {
	answer := ""
	for _, line := range strings.Split(string(body), "\n") {
		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		var event map[string]any
		if json.Unmarshal([]byte(strings.TrimSpace(strings.TrimPrefix(line, "data:"))), &event) == nil {
			if value, ok := event["answer"].(string); ok {
				answer = value
			}
		}
	}
	return answer
}

func decodeWorkflowOutput(outputs map[string]any, out any) error {
	if len(outputs) == 0 {
		return fmt.Errorf("workflow 输出为空")
	}
	value, ok := outputs["result"]
	if !ok {
		value = outputs
		if nested, nestedOK := outputs["data"]; nestedOK {
			value = nested
		}
	}
	var payload []byte
	switch typed := value.(type) {
	case string:
		payload = []byte(typed)
	default:
		var err error
		payload, err = json.Marshal(typed)
		if err != nil {
			return fmt.Errorf("序列化 workflow 输出失败: %w", err)
		}
	}
	if err := json.Unmarshal(payload, out); err != nil {
		return fmt.Errorf("解析 workflow 输出失败: %w", err)
	}
	return nil
}

// runDifyScene is the adapter for the newer S1-S4 contract. Dify exposes
// workflows rather than the local AI Engine REST surface, so each operation
// carries an explicit scene name and a JSON-compatible input object.
func (c *DifyClient) runDifyScene(ctx context.Context, scene string, inputs any, out any, fallback func() error) error {
	inputMap, err := structToMap(inputs)
	if err != nil {
		return err
	}
	if err := c.runWorkflow(ctx, scene, inputMap, out); err == nil {
		return nil
	} else if fallback != nil {
		if fallbackErr := fallback(); fallbackErr == nil {
			return nil
		} else {
			return fmt.Errorf("Dify 场景 %s 调用失败，回退也失败: %w", scene, fallbackErr)
		}
	} else {
		return fmt.Errorf("Dify 场景 %s 调用失败: %w", scene, err)
	}
}

func (c *DifyClient) fallbackEngine() (AIEngine, bool) {
	engine, ok := c.fallback.(AIEngine)
	return engine, ok
}

// IntentExtract implements S1 through the configured Dify workflow.
func (c *DifyClient) IntentExtract(ctx context.Context, req IntentExtractRequest) (*IntentExtractResponse, error) {
	var out IntentExtractResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.IntentExtract(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneIntentExtract, req, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) IntentConfirm(ctx context.Context, req IntentConfirmRequest) (*IntentConfirmResponse, error) {
	var out IntentConfirmResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.IntentConfirm(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneIntentConfirm, req, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) ParseProcess(ctx context.Context, req *ParseProcessRequest) (*ParseProcessResponse, error) {
	var out ParseProcessResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.ParseProcess(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneParseProcess, req, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) ParseStatus(ctx context.Context, taskID string) (*ParseStatusResponse, error) {
	var out ParseStatusResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.ParseStatus(ctx, taskID)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneParseStatus, map[string]string{"task_id": taskID}, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) ParseVideo(ctx context.Context, req *ParseVideoRequest) (*ParseProcessResponse, error) {
	var out ParseProcessResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.ParseVideo(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneParseVideo, req, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) RAGSearch(ctx context.Context, req RAGSearchRequest) (*RAGSearchResponse, error) {
	var out RAGSearchResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.RAGSearch(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneRAGSearch, req, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) RAGEvidence(ctx context.Context, req RAGEvidenceRequest) (*RAGEvidenceResponse, error) {
	var out RAGEvidenceResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.RAGEvidence(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneRAGEvidence, req, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) KnowledgeUpload(ctx context.Context, req *KnowledgeUploadRequest) (*KnowledgeUploadResponse, error) {
	var out KnowledgeUploadResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.KnowledgeUpload(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneKnowledgeUpload, req, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) GenerationCreate(ctx context.Context, req GenerationCreateRequest) (*GenerationCreateResponse, error) {
	var out GenerationCreateResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.GenerationCreate(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneGenerationCreate, req, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) GenerationStatus(ctx context.Context, taskID string) (*GenerationStatusResponse, error) {
	var out GenerationStatusResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.GenerationStatus(ctx, taskID)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneGenerationStatus, map[string]string{"task_id": taskID}, &out, fallback); err != nil {
		return nil, err
	}
	// P3: 防御性验证 nodes 数组，防止畸形 LLM 输出进入版本化/导出流程
	if out.Nodes != nil {
		validNodes := make([]TeachingNodeItem, 0, len(out.Nodes))
		for _, n := range out.Nodes {
			if n.NodeID != "" {
				validNodes = append(validNodes, n)
			}
		}
		out.Nodes = validNodes
	}
	return &out, nil
}

// GenerateOutline 走 Dify 场景；Dify 未配置时降级到本地 AI Engine。
func (c *DifyClient) GenerateOutline(ctx context.Context, req OutlineGenerateRequest) (*OutlineGenerateResponse, error) {
	var out OutlineGenerateResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.GenerateOutline(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneGenerateOutline, req, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

// ReviseOutline 走 Dify 场景；Dify 未配置时降级到本地 AI Engine。
func (c *DifyClient) ReviseOutline(ctx context.Context, req OutlineReviseAIRequest) (*OutlineReviseAIResponse, error) {
	var out OutlineReviseAIResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.ReviseOutline(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneReviseOutline, req, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

// GenerationPreview is kept on DifyClient for the preview handler's optional
// capability check, although it is intentionally outside the legacy AIEngine interface.func (c *DifyClient) GenerationPreview(ctx context.Context, req GenerationPreviewRequest) (*GenerationPreviewResponse, error) {
	var out GenerationPreviewResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			preview, ok := c.fallback.(interface {
				GenerationPreview(context.Context, GenerationPreviewRequest) (*GenerationPreviewResponse, error)
			})
			if !ok {
				return fmt.Errorf("回退客户端不支持 generation preview")
			}
			result, err := preview.GenerationPreview(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	} else {
		_ = engine
	}
	if err := c.runDifyScene(ctx, difySceneGenerationPreview, req, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) GenerationModify(ctx context.Context, req GenerationModifyRequest) (*GenerationModifyResponse, error) {
	var out GenerationModifyResponse
	inputs := map[string]any{"generation_id": req.GenerationID, "request": req}
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.GenerationModify(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneGenerationModify, inputs, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) GenerationFinalize(ctx context.Context, req GenerationFinalizeRequest) (*GenerationFinalizeResponse, error) {
	var out GenerationFinalizeResponse
	inputs := map[string]any{"generation_id": req.GenerationID, "request": req}
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.GenerationFinalize(ctx, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneGenerationFinalize, inputs, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) VersionHistory(ctx context.Context, genID string) (*VersionHistoryResponse, error) {
	var out VersionHistoryResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.VersionHistory(ctx, genID)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneVersionHistory, map[string]string{"generation_id": genID}, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) VersionLoad(ctx context.Context, genID string, versionNumber int) (*VersionSnapshot, error) {
	var out VersionSnapshot
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.VersionLoad(ctx, genID, versionNumber)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneVersionLoad, map[string]any{"generation_id": genID, "version": versionNumber}, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) VersionRollback(ctx context.Context, genID string, req VersionRollbackRequest) (*VersionRollbackResponse, error) {
	var out VersionRollbackResponse
	inputs := map[string]any{"generation_id": genID, "request": req}
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.VersionRollback(ctx, genID, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneVersionRollback, inputs, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) VersionLock(ctx context.Context, genID string) (*VersionLockResponse, error) {
	var out VersionLockResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.VersionLock(ctx, genID)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneVersionLock, map[string]string{"generation_id": genID}, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) ExportCreate(ctx context.Context, genID string, req ExportCreateRequest) (*ExportCreateResponse, error) {
	var out ExportCreateResponse
	inputs := map[string]any{"generation_id": genID, "request": req}
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.ExportCreate(ctx, genID, req)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneExportCreate, inputs, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *DifyClient) ExportStatus(ctx context.Context, jobID string) (*ExportStatusResponse, error) {
	var out ExportStatusResponse
	engine, hasFallback := c.fallbackEngine()
	var fallback func() error
	if hasFallback {
		fallback = func() error {
			result, err := engine.ExportStatus(ctx, jobID)
			if err == nil {
				out = *result
			}
			return err
		}
	}
	if err := c.runDifyScene(ctx, difySceneExportStatus, map[string]string{"job_id": jobID}, &out, fallback); err != nil {
		return nil, err
	}
	return &out, nil
}

// P1: 内容生成阶段 — 委托给 fallback engine（aiEngineClient）
func (c *DifyClient) GenerateContent(ctx context.Context, req GenContentRequest) (*GenContentStatusResponse, error) {
	engine, hasFallback := c.fallbackEngine()
	if !hasFallback {
		return nil, errors.New("DifyClient 不支持内容生成，需要 AI Engine fallback")
	}
	return engine.GenerateContent(ctx, req)
}

func (c *DifyClient) ContentStatus(ctx context.Context, contentID string) (*GenContentStatusResponse, error) {
	engine, hasFallback := c.fallbackEngine()
	if !hasFallback {
		return nil, errors.New("DifyClient 不支持内容状态查询，需要 AI Engine fallback")
	}
	return engine.ContentStatus(ctx, contentID)
}

var _ AIEngine = (*DifyClient)(nil)
