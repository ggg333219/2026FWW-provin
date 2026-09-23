package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"smart-teaching-backend/internal/service"
)

type interactiveAsset struct {
	InteractiveAssetID string           `json:"interactive_asset_id"`
	GenerationID       string           `json:"generation_id"`
	NodeID             string           `json:"node_id"`
	AssetType          string           `json:"asset_type"`
	Status             string           `json:"status"`
	Items              []map[string]any `json:"items"`
	FileURL            string           `json:"file_url"`
	EntryURL           string           `json:"entry_url"`
	Error              string           `json:"error,omitempty"`
	CreatedAt          time.Time        `json:"created_at"`
}

type InteractiveHandler struct {
	aiClient service.AIEngine
	mu       sync.RWMutex
	assets   map[string]interactiveAsset
}

func NewInteractiveHandler(aiClient service.AIEngine) *InteractiveHandler {
	return &InteractiveHandler{aiClient: aiClient, assets: make(map[string]interactiveAsset)}
}

type interactiveGenerateBody struct {
	InteractivePlan map[string]any `json:"interactive_plan"`
	Node            map[string]any `json:"node"`
}

// Generate handles POST /api/v1/generations/:generation_id/nodes/:node_id/interactive.
func (h *InteractiveHandler) Generate(c *gin.Context) {
	generationID := c.Param("generation_id")
	nodeID := c.Param("node_id")
	if generationID == "" || nodeID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 generation_id 或 node_id"})
		return
	}
	var body interactiveGenerateBody
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}
	if body.Node == nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 node 快照"})
		return
	}
	body.Node["node_id"] = nodeID
	client, ok := h.aiClient.(interface {
		GenerateInteractive(context.Context, service.InteractiveGenerateRequest) (*service.InteractiveGenerateResponse, error)
	})
	if !ok {
		c.JSON(http.StatusNotImplemented, gin.H{"code": 501, "message": "当前 AI 客户端不支持互动生成"})
		return
	}
	resp, err := client.GenerateInteractive(c.Request.Context(), service.InteractiveGenerateRequest{
		Node:            body.Node,
		InteractivePlan: body.InteractivePlan,
	})
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"code": 502, "message": "生成互动内容失败: " + err.Error()})
		return
	}
	assetID := fmt.Sprintf("asset_%d", time.Now().UnixNano())
	asset := interactiveAsset{
		InteractiveAssetID: assetID,
		GenerationID:       generationID,
		NodeID:             nodeID,
		AssetType:          "html5",
		Status:             "done",
		Items:              resp.Items,
		EntryURL:           fmt.Sprintf("/api/v1/interactive/assets/%s/preview", assetID),
		CreatedAt:          time.Now(),
	}
	h.mu.Lock()
	h.assets[assetID] = asset
	h.mu.Unlock()
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": asset})
}

// Get is intentionally implemented separately from generation so the
// frontend can keep its existing polling contract.
func (h *InteractiveHandler) Get(c *gin.Context) {
	assetID := c.Param("interactive_asset_id")
	h.mu.RLock()
	asset, ok := h.assets[assetID]
	h.mu.RUnlock()
	if !ok {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "互动资源不存在"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": asset})
}

func (h *InteractiveHandler) LinkToPage(c *gin.Context) {
	generationID := c.Param("generation_id")
	pageID := c.Param("page_id")
	var body struct {
		InteractiveAssetID string `json:"interactive_asset_id"`
		Label              string `json:"label"`
	}
	if err := c.ShouldBindJSON(&body); err != nil || body.InteractiveAssetID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "interactive_asset_id 必填"})
		return
	}
	assetID := body.InteractiveAssetID
	h.mu.RLock()
	asset, ok := h.assets[assetID]
	h.mu.RUnlock()
	if !ok {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "互动资源不存在"})
		return
	}
	if asset.GenerationID != generationID {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "互动资源不属于当前课件"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "data": gin.H{
		"interactive_asset_id": assetID,
		"generation_id":        generationID,
		"page_id":              pageID,
		"label":                body.Label,
		"entry_url":            asset.EntryURL,
		"linked":               true,
		"message":              fmt.Sprintf("互动资源 %s 已关联页面 %s", assetID, pageID),
	}})
}

// Preview renders a self-contained, playable HTML5 quiz for the generated asset.
func (h *InteractiveHandler) Preview(c *gin.Context) {
	assetID := c.Param("interactive_asset_id")
	h.mu.RLock()
	asset, ok := h.assets[assetID]
	h.mu.RUnlock()
	if !ok {
		c.String(http.StatusNotFound, "互动资源不存在")
		return
	}
	itemsJSON, err := json.Marshal(asset.Items)
	if err != nil {
		c.String(http.StatusInternalServerError, "互动资源序列化失败")
		return
	}
	page := `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>课堂互动</title><style>body{margin:0;font-family:system-ui,"Microsoft YaHei",sans-serif;background:linear-gradient(145deg,#eef8f4,#fff);color:#173f36}.app{max-width:760px;margin:0 auto;padding:32px 20px}h1{margin:0 0 8px}.sub{color:#678078;margin-bottom:22px}.card{background:#fff;border:1px solid #d7e8e1;border-radius:16px;padding:20px;margin:14px 0;box-shadow:0 8px 24px #1f5b4712}.option{display:block;width:100%;margin:8px 0;padding:11px 13px;text-align:left;border:1px solid #c9ddd5;border-radius:10px;background:#f9fcfb;cursor:pointer}.option:hover{border-color:#2f8069}.option.correct{background:#e8f8f1;border-color:#2a9b70}.option.wrong{background:#fff0f0;border-color:#cf6666}.answer{min-height:22px;color:#526b63;font-size:14px}.flash{cursor:pointer}.flash .back{display:none;margin-top:10px;color:#316657}.flash.open .back{display:block}</style></head><body><main class="app"><h1>课堂互动练习</h1><p class="sub">选择答案即可即时反馈，点击闪卡可查看解释。</p><div id="root"></div></main><script>const items=__ITEMS__;const root=document.getElementById('root');let qn=0;for(const item of items){if(item.type==='quiz'){for(const q of (item.questions||[])){qn++;const card=document.createElement('section');card.className='card';card.innerHTML='<h3>'+qn+'. '+esc(q.question||'课堂练习')+'</h3>';const answer=document.createElement('p');answer.className='answer';(q.options||[]).forEach((opt,i)=>{const b=document.createElement('button');b.className='option';b.textContent=opt;b.onclick=()=>{card.querySelectorAll('.option').forEach(x=>x.disabled=true);const expected=String(q.answer||'A').trim();const ok=expected===String.fromCharCode(65+i)||expected===opt;b.classList.add(ok?'correct':'wrong');answer.textContent=(ok?'回答正确。':'再想一想。')+(q.explanation?' '+q.explanation:'')};card.appendChild(b)});card.appendChild(answer);root.appendChild(card)}}else if(item.type==='flashcard'){const card=document.createElement('section');card.className='card flash';card.innerHTML='<h3>'+esc(item.front||item.title||'知识闪卡')+'</h3><p>点击查看答案</p><div class="back">'+esc(item.back||'')+'</div>';card.onclick=()=>card.classList.toggle('open');root.appendChild(card)}}if(!root.children.length)root.innerHTML='<section class="card"><p>互动内容正在准备中，请稍后重试。</p></section>';function esc(v){const d=document.createElement('div');d.textContent=String(v||'');return d.innerHTML}</script></body></html>`
	safeItemsJSON := strings.ReplaceAll(string(itemsJSON), "</", "<\\/")
	page = strings.Replace(page, "__ITEMS__", safeItemsJSON, 1)
	c.Header("Content-Type", "text/html; charset=utf-8")
	c.String(http.StatusOK, page)
}
