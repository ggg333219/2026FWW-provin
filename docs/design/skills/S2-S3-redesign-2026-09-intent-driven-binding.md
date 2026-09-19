# Skill 2 / Skill 3 重设计方案：意图驱动的自动绑定 + 页面级资料

> 状态：**草稿 v0.2（用户回复了 §8 的 4 个问题后修订）** · 最后更新：2026-09-18
> 适用读者：成员 A（Go 后端）/ B（AI 引擎）/ C（前端）/ D（协调）
> 与既有文档关系：**覆写** `docs/design/skills/S2-multimodal-interaction.md` 第 3 节主流程
> 与既有文档关系：**扩展** `docs/design/skills/S3-courseware-generation.md` §2 三阶段管道（页面管理、互动资源保留为现有内容）

---

## 0 · 一句话总结

**S2 路由入口删除（代码保留复用）**——资料上传与证据绑定整体下沉到 S3 工作台，按**页面**（page，最小节点单位）粒度上传、勾选、绑定；意图关键词驱动的"自动绑定"在 S3 进入时触发，由系统后台完成，不再让教师重复劳动。S3 工作台在现有四阶段（大纲 / 内容 / 页面管理 / 样式）基础上加入左栏资料侧边栏，让**局部修改有靶点**、**全课件迭代有节奏**。

---

## 1 · 问题陈述（为什么必须改）

### 1.1 现状的冗余链路

当前主流程：

```
S1（意图）→ S2（资料上传 + 手工搜索 + 证据绑定）→ S3（生成）→ S4（修改/版本）
```

锚点证据：
- `frontend/teacher/src/pages/S2MaterialPage.vue:33-40` — 跳出确认对话框："当前还没有绑定可用证据…可以返回上方上传并检索资料"
- `frontend/teacher/src/pages/S3StudioPage.vue:175-178` — "无参考资料提示：内容将基于 S1 意图自动生成"，已具备"无 S2 直接生成"路径，但前提仍要"先返回 S2 补充资料"才能更好生成
- `ai_engine/rag/retrieve.py:206` — `knowledge_base_ids: 限定知识库范围（目前未实现过滤）`
- `frontend/teacher/src/stores/materialStore.js:4` — `EVIDENCE_HANDOFF_KEY = 'fuww_s2_evidence_packet'`（整课件单包）
- `frontend/teacher/src/stores/materialStore.js:35-41` — evidence_packet 结构：`{ query, relevant_chunks: ChunkSchema[], citations: [{ chunk_id, text_snippet, source_ref }] }`——绑定粒度是"整课件"，不是"页面"

关键冗余：

1. **关键词二次输入** — 教师在 S1 已经填了主题、对象、目标、时长等关键词（`IntentSummary.topic / audience / objectives`），到 S2 又要再手敲一遍检索关键词
2. **绑定粒度错配** — 现有 S2 把证据绑定到"整个课件"，S3 生成 PPT 时所有节点共享同一份 evidence_packet，局部修改无法针对性选取证据
3. **S2 强制流程化** — 即使教师临时只想改一两页 PPT，也被迫走完整 S2 上传-检索-绑定流程（参见 `S2MaterialPage.vue:33` 的"未绑定证据拦截"逻辑）

### 1.2 设计目标

| 维度 | 现状 | 目标 |
|---|---|---|
| 主流程必经步 | S1→S2→S3→S4 | S1→S3→S4（S2 路由删除，代码复用进 S3） |
| S2 路由 | 独立页面 `S2MaterialPage.vue` | 删除路由入口；组件代码并入 S3 左栏 |
| 资料上传入口 | 仅 S2 页面 | 仅 S3 左栏"按页面上传"（取消"按整课件上传"路径） |
| 证据绑定粒度 | 整份课件（evidence_packet） | 单个 page（per-page binding） |
| 自动 vs 手动 | 全部手动 | 意图关键词 → S3 进入时自动绑定；局部补充 → 手动 |
| 阶段切换 | 一锅烩七阶段 | 4 phase-tabs（大纲/内容/页面管理/样式），3 个确认门（大纲/内容/样式）硬阻塞 |

---

## 2 · 新设计总览

### 2.1 主流程（新）

```
S1（意图锁定）
   ↓ intent_id + IntentSummary
S3（课件生成工作台）
   ├─ [进入时] 平台用 IntentSummary 关键词对 KB 自动检索
   │           → 为每个 page 预填默认 evidence_refs（标记 auto_bound=true）
   ├─ [左栏 NEW] 教师按"当前选中页面"上传 / 勾选 / 解绑资料
   │             （覆盖默认绑定；per-page 粒度）
   ├─ [中栏] 四阶段视图：大纲 → 内容 → 页面管理 → 样式
   │         （大纲/内容/样式 三道硬阻塞门；页面管理是内容层内的子工作台）
   └─ [右栏] AI 修改入口（基于"当前页面" + 绑定的 evidence_refs 局部重生成）
   ↓ generation_id
S4（版本/回滚/迭代）
   ├─ 选择历史版本 → 回滚并克隆出新版本
   ├─ 新版本携带原 nodeBindings 作为版本快照的一部分
   └─ 在新版本上重新进入 S3 大纲层编辑（编辑即开新版本）
```

### 2.2 S3 工作台信息架构（改造后）

```
┌──────────────────── S3 工作台 ────────────────────┐
│ 头部：阶段指示 [大纲]→[内容]→[页面管理]→[样式]            │  沿用 S3StudioPage.vue:60-78
├──────────────┬─────────────────────────┬──────────┤
│              │                         │          │
│  资料侧边栏  │    四阶段主区            │  AI 对话 │
│  (左栏 改造) │    (中栏 扩展)           │ (右栏)  │
│              │                         │          │
│  当前页面:   │  ┌─ 大纲 ─────────┐       │  "把第3页│
│  P3 - 二分   │  │ OutlineEditor │       │   案例改 │
│              │  │ (含页级证据徽章)│       │   成..." │
│  ● 上传       │  │ ✓ 已确认门       │       │          │
│  ● 勾选chunks│  └─────────────────┘       │   (按页面│
│  ● 解绑       │                         │   绑定证 │
│              │  ┌─ 内容生成 ──────┐       │   据)    │
│  [自动绑定]   │  │ 进度条/逐页生成│       │          │
│  标签        │  │ ✓ 已确认门       │       │          │
│              │  └─────────────────┘       │          │
│              │  ┌─ 页面管理 ──────┐       │          │
│              │  │ pages[] 列表    │       │          │
│              │  │ + 互动资源(HTML5)│       │          │
│              │  │ (内容层子工作台)│       │          │
│              │  └─────────────────┘       │          │
│              │                         │          │
│              │  ┌─ 样式 ─────────┐       │          │
│              │  │ StylePicker    │       │          │
│              │  │ ✓ 已确认门       │       │          │
│              │  └─────────────────┘       │          │
└──────────────┴─────────────────────────┴──────────┘
```

### 2.3 数据模型新增

#### 2.3.1 页面级证据绑定（per-page binding）

> **节点最小单位 = 页面**。锚点：`frontend/teacher/src/pages/S3StudioPage.vue:241` `<span class="page-node">` 即 S3 中"页面"的内部标识。outline_node 与 page 一一对应（一页即一个教学节点），不存在"页面再拆子节点"。

```yaml
PageEvidenceBinding:                # 锚定 page（最小节点单位）
  page_id: str                       # = outline_node.node_id（与 S3 大纲节点 1:1）
  evidence_refs: list[str]           # chunk_id 列表（沿用 ai_engine/rag/chunker.py:364 的确定性 ID）
  auto_bound: bool                   # true = 平台基于意图关键词自动绑定；false = 教师手动
  bound_at: datetime
  bound_by: str                      # "system:intent_keyword" | "user:<teacher_id>"

PageUploadSlot:                     # S3 阶段教师上传的"针对该页"的补充材料
  page_id: str
  upload_session_id: str             # 与旧 S2 共享 parse task 上下文（解析复用 ai_engine/parse/router.py:39）
  chunks: list[Chunk]                # 与 KB 同一 Chunk 形态
  selected: bool                     # 是否勾选 → 绑定到该页
```

**关键约束**：

- `evidence_refs` 元素必须是已有 `chunk_id`（沿用 `ai_engine/rag/chunker.py:364` 的 `_make_deterministic_chunk_id`），禁止重新发明 UUID
- `auto_bound=true` 的 binding 在教师手动覆盖前是只读"建议"；教师可解绑或追加，教师优先原则记录在 `bound_by`
- **页面级绑定与旧 `evidence_packet` 并行存在**：旧字段保留兼容旧课件，新生成只填 `PageEvidenceBinding`

#### 2.3.2 阶段确认门（硬阻塞）

S3 现有 4 个 phase-tabs（`S3StudioPage.vue:60-78`），其中 3 个设为**硬阻塞确认门**：

```
phase-tabs:
  [大纲]  → OutlineEditor（含页级证据徽章）        ─┐
                                                     │
  [内容生成]  → 生成进度 + 页面内容                   │  硬阻塞：
                                                     │  上一门未确认
  [页面管理]  → 页面列表 + 互动资源 (HTML5)        │  → 下一门禁用
                                                     │  （沿用 S3StudioPage.vue:71-78
  [样式]  → 模板/配色/版式/字体/密度                │    :disabled 机制）
                                                  ─┘
```

> **页面管理**不单设确认门，作为内容层内的子工作台（页面状态修改、互动资源生成属于"内容"层面工作，不触发样式层失效）

每道门独立 `version_no`（如 `outline_v3 / content_v2 / style_v1`），跨门回退需走 S4 版本回滚。

---

## 3 · S3 必须确认的 3 项（用户原话级需求）

> 用户原话："S3要确认的是1.支持局部修改（项目本身要求）2.上传资料可以支持勾选 3.上传资料可以支持绑定到对应页面"

### 3.1 支持局部修改（项目本身要求）

**机理**：右侧 AI 对话（`ModifyPanel.vue`）接受教师指令后，只对"当前选中页面"重生成，其他页保持不变。`PageEvidenceBinding.evidence_refs` 提供该页可用的 chunks 作为局部上下文。

锚点：
- `frontend/teacher/src/components/teacher/ModifyPanel.vue:56,121,143-147` — 现有逻辑已按 `node_id` 操作（即 page_id），重生成范围控制已具备，需补 evidence_refs 透传
- `ai_engine/rag/retrieve.py:193-206` — `HybridRetriever.search` 已支持 `node_id` / `scope` / `page_id` 过滤

### 3.2 上传资料可以支持勾选

**机理**：左栏上传完成后，平台解析为 chunk 列表（沿用 `ai_engine/rag/chunker.py`）。教师逐 chunk 勾选（多选），勾选态记入 `PageUploadSlot.selected` 或直接写入 `PageEvidenceBinding.evidence_refs`。

锚点：
- 现有 `EvidenceSidebar.vue:25,48,61` 已支持 scope/nodeId 选择，但当前只有"应用证据"按钮，无 chunk-level 勾选 UI
- 新增：`ChunkPicker.vue` —— 列出当前页面已上传/已检索到的 chunk，每行带 checkbox

### 3.3 上传资料可以支持绑定到对应页面

**机理**：左栏的"当前页面上下文"由大纲节点选择驱动。选中某 page → 上传的资料自动归属该 page → 解析完成后落入该 page 的 `PageUploadSlot`。教师把勾选的 chunks 写入 `PageEvidenceBinding.evidence_refs`，绑定完成。

锚点：
- `S3StudioPage.vue:241` — 现有 pages 列表已支持单页选中（点击 `page-item` 高亮 + 联动其他面板），需扩展为联动左栏"当前页面"上下文
- `materialStore.js:35-41` — 旧 `evidence_packet` 字段保留兼容，新数据走 `nodeBindings: Record<page_id, PageEvidenceBinding>`

---

## 4 · 三大创新点（答辩优势）

### 4.1 页面级资料上传 + 筛选绑定（局部修改有靶点）

**机理**：左栏围绕"当前页面"组织上下文——上传的资料、检索的资料、绑定的证据，全部按页面过滤。

**价值**：
- **局部修改有靶点**：教师说"把第 3 页案例改一下"，AI 知道第 3 页绑定了哪些 chunks，只在那几个 chunks 里检索/重生成，不污染其他页面
- **效率最高**：同一份资料可在多个相关页面重复绑定（避免重复上传）；同一页的多次修改复用同一证据集
- **最大化满足用户期望**：教师的修改意图被精确路由到对应页面的资料池，AI 输出与意图强相关

锚点：
- 现有 `EvidenceSidebar.vue:25` 已支持 `(scope === 'node' || scope === 'page')` 过滤，本设计把 scope=page 设为默认
- `ModifyPanel.vue` 现有逻辑基于 `node_id`（= page_id）→ 局部重生成能力已具备

### 4.2 三道硬阻塞确认门（逐步确认降低 AI 返工）

**机理**：把"一次性生成整份 PPT"拆为大纲 / 内容 / 样式 三道硬阻塞确认门，每道门独立锁定进入下一道。

**价值**：
- **降低 AI 返工**：教师在内容层发现大纲有误，可只回退到大纲门（保留已生成的样式选择），不必整份推翻
- **降低教师焦虑**：每门都是"看得见的中间产物"，不会出现"等 90 秒发现整份不对"的挫败感
- **节省 token**：前一道门失败时，后续门未启动，LLM 调用次数按门数封顶

锚点：
- 现有 `S3StudioPage.vue:71-78` 的 `:disabled="!outlineStore.isConfirmed"` 等机制可复用，作为硬阻塞基础

### 4.3 意图关键词自动绑定（S3 进入时触发）

**机理**：S3 工作台挂载（onMounted）时，系统后台立即用 `IntentSummary.topic + audience + objectives + duration_minutes` 组合生成检索 query，调 `ai_engine/rag/router.py:113` 的 `POST /api/v1/rag/search`，对每个 page 返回 top-K chunks，预填进 `PageEvidenceBinding.evidence_refs`，标记 `auto_bound=true`。

**价值**：
- **彻底消除关键词二次输入**：教师在 S1 填的内容直接驱动后台检索，不暴露搜索界面
- **教师仍可覆盖**：左栏提供"重置自动绑定 / 手动追加 / 解绑"操作
- **教学意图与证据强相关**：算法生成的 query 携带意图上下文，比手敲关键词命中率更高

锚点：
- `ai_engine/rag/router.py:113` — `min_score=req.min_score or 0.2` 已兜底（commit 1577a82）
- `ai_engine/core/schema.py:589` — `SearchRequest.min_score = 0.2`
- `ai_engine/rag/evidence.py:7-8` — `query → hybrid_retrieve(k=20) → rerank(k=5) → synthesize(retrieved, query, intent_context) → evidence_packet` 已具备意图上下文融合能力

---

## 5 · S2 路由删除（用户已确认）

> 用户原话："S2可以删掉路由入口但是原本的代码可以复用"

### 5.1 删除清单

- `frontend/teacher/src/router/*.js` 中 `S2Material` 路由注册
- `frontend/teacher/src/pages/S2MaterialPage.vue` 中的"独立路由入口"部分（`S2MaterialPage.vue:23-50`）
- `frontend/teacher/src/pages/MiddlePage.vue:6` 的"资料与证据中心"按钮（已删 S2 路由后失效）
- `S1IntentPage.vue` 中指向 `S2Material` 的 router-link

### 5.2 保留复用清单

- `frontend/teacher/src/stores/materialStore.js` — 改名为 `pageMaterialStore` 或保留，但**核心逻辑（chunks 上传、解析、勾选）整体迁入 S3 左栏**
- `frontend/teacher/src/components/teacher/S2MaterialHub.vue` / `S2MaterialWorkspace.vue` — 拆为左栏的子组件（如 `MaterialSidebar.vue` 的内部分区）
- `frontend/teacher/src/components/teacher/TeacherUploadModal.vue` — 复用进 S3 左栏
- 后端 `ai_engine/parse/router.py:39` 的 `/api/v1/parse/process` 端点 + 异步任务链路 — 保留，前端左栏直接调用
- `ai_engine/rag/router.py:295` 的 `register_session_chunks` — 保留并扩展支持 `page_id`

### 5.3 不动清单

- `ai_engine/parse/router.py` 解析端点
- `ai_engine/rag/*` 全部 RAG 检索逻辑（只增 `page_id` 过滤参数）
- 后端 `POST /api/v1/knowledge/upload` 鉴权裸奔问题（超出本设计范围，留给 A 类）

---

## 6 · 详细实施改动清单

> 按角色分组。每条带具体文件 + 验证手段。

### 6.1 AI 引擎侧（B 类）

| # | 改动 | 涉及文件 | 验证手段 |
|---|---|---|---|
| B-1 | 新增 `POST /api/v1/intent/:intent_id/auto-bind-pages` 端点：基于 IntentSummary 对每个 page 自动 RAG 检索 | `ai_engine/main.py`、`ai_engine/rag/router.py` | 单测：固定 IntentSummary → 固定检索结果（mock store） |
| B-2 | `HybridRetriever.search` 支持 `page_id` 过滤（`scope="page"`） | `ai_engine/rag/retrieve.py:193-206` | 单测：传 page_id → 只返回该页 chunks |
| B-3 | 新增 per-page evidence 持久化（在 `_session_parsed_chunks` 旁路加 `page_bindings`） | `ai_engine/rag/router.py:282`（参见 HANDOFF Phase 2 P5） | 单测：auto_bind 后查询特定 page_id 返回绑定列表 |
| B-4 | `POST /api/v1/generation/content/:page_id/regenerate` 接受新参数 `evidence_refs`，仅在指定 refs 上重生成 | `ai_engine/main.py` | 单测：传 evidence_refs → 检索 context 被限定 |
| B-5 | `register_session_chunks` 扩展支持 `page_id` 参数 | `ai_engine/rag/router.py:295`、`ai_engine/parse/task_manager.py:387,476`（已有调用点） | 单测：传 page_id → chunks 与 page 关联 |

### 6.2 Go 后端侧（A 类）

| # | 改动 | 涉及文件 | 验证手段 |
|---|---|---|---|
| A-1 | DTO 新增 `PageEvidenceBinding` / `PageUploadSlot`（与 §2.3 同步） | `backend/internal/service/models.go`、`backend/internal/service/ai_engine_client.go:429+`（已有 RAGSearchRequest，加 PageBindings 字段） | `go build ./...` 通过 + 单元类型校验 |
| A-2 | `OutlineHandler` 新增 `POST /outlines/:id/auto-bind-evidence`（代理 B-1） | `backend/internal/handler/outline_handler.go` | `go test ./internal/handler/...` |
| A-3 | `GenerationHandler` 接受 `evidence_refs` 透传给 AI 引擎 | `backend/internal/handler/generation_handler.go` | 单测：参数字段透传校验 |
| A-4 | `VersionHandler` 快照包含 `pageBindings` 字段 | `backend/internal/handler/version_handler.go` | 单测：rollback 后 pageBindings 一并恢复 |

### 6.3 前端侧（C 类）

| # | 改动 | 涉及文件 | 验证手段 |
|---|---|---|---|
| C-1 | **新增** `MaterialSidebar.vue`：按当前选中 page 过滤+上传+勾选+解绑 | `frontend/teacher/src/components/teacher/MaterialSidebar.vue`（新增） | browser_debug 截图：上传→勾选→绑定流程可视 |
| C-2 | `materialStore.js` 改造：`evidence_packet` 保留兼容 + 新增 `pageBindings: Record<page_id, PageEvidenceBinding>` | `frontend/teacher/src/stores/materialStore.js:35-41` | `materialStore.test.js` 现有用例保持通过 + 新增 pageBindings 用例 |
| C-3 | `S3StudioPage.vue` 接入 MaterialSidebar 作为左栏；选中 page 时联动 MaterialSidebar 上下文 | `frontend/teacher/src/pages/S3StudioPage.vue:60-78`（保留 phase-tabs），在 phase-panel 外加 `<MaterialSidebar :page-id="selectedPageId" />` | browser_debug：点不同 page → 左栏 chunks 列表更新 |
| C-4 | phase-tabs 硬阻塞：把现有 `:disabled="!outlineStore.isConfirmed"` 等机制扩展为完整 3 门（大纲/内容/样式） | `frontend/teacher/src/pages/S3StudioPage.vue:71-78` | browser_debug：未确认大纲 → 内容 tab 禁用；未确认内容 → 样式 tab 禁用 |
| C-5 | `ModifyPanel.vue` 调用 `regenerate` 时带当前选中 `page_id` + `evidence_refs` | `frontend/teacher/src/components/teacher/ModifyPanel.vue:121,143-147`（已有 node_id 透传） | 单测：调用携带参数字段断言 |
| C-6 | 路由层：删除 `S2Material` 路由 + `S2MaterialPage.vue` 独立入口组件（保留组件代码作 C-1 子组件复用） | `frontend/teacher/src/router/*.js`、`frontend/teacher/src/pages/S2MaterialPage.vue:23-50` | `npm run build` 通过 + 路由表 grep 无 S2 残留 |
| C-7 | `S4VersionPage.vue:200` 的"返回 S3 调整证据"扩展为 `?from_rollback_version=N` + 自动跳到 S3 大纲层 | `frontend/teacher/src/pages/S4VersionPage.vue:200` | browser_debug：rollback → 跳 S3 大纲 → 编辑即开新版本 |
| C-8 | `ModifyPanel.vue` 接收 page_id 自动绑定（教师点右栏对话时隐含选中的 page） | `frontend/teacher/src/components/teacher/ModifyPanel.vue:111`（已用 node_id = page_id） | 单测：emit regenerate 时携带 page_id |

### 6.4 中间页（低优先级）

`MiddlePage.vue:6` 的"资料与证据中心"按钮随 S2 路由一起删除（用户已确认）。中间页后续可以挂"按课件统计节点绑定覆盖率"摘要作为后续 polish，非本期范围。

---

## 7 · S4 对接位点（不重写 S4）

S4 设计文档 `docs/design/skills/S4-personalization.md` 不动。在本设计下需要确认 2 个对接点：

1. **版本回滚 → 新版本迭代**：教师在 S4 选某历史版本回滚后，应自动跳转到 S3 大纲层（不是预览），让教师继续编辑 → 编辑即开新版本（在 `versionStore.createNewVersion` 钩子触发）
2. **per-page 绑定进版本快照（用户已确认）**：`VersionManager` 快照必须包含 `pageBindings`，否则回滚后绑定关系丢失

锚点：
- `frontend/teacher/src/pages/S4VersionPage.vue:200` 已有 `<router-link :to="{ name: 'S3Studio' ... }">返回 S3 调整证据</router-link>`，需要把目标参数从 `generation_id` 扩展为 `?from_rollback_version=N`
- `ai_engine/gen/version.py`（500 行）需要支持 `pageBindings` 字段透传（具体实施待 S3 落地后回填）

---

## 8 · 用户已确认决策（原 §8 待确认问题已关闭）

| # | 原问题 | 决策 | 影响 |
|---|---|---|---|
| 1 | S2 路由是否拆掉？ | **删除路由入口，代码复用** | C-6 删除路由 + C-1 复用组件代码 |
| 2 | 三阶段确认是硬阻塞还是软提醒？ | **硬阻塞** | C-4 完整 3 门 disable 机制 |
| 3 | 自动绑定触发时机？ | **S3 进入时触发** | onMounted 钩子触发 B-1，调 `/api/v1/intent/:intent_id/auto-bind-pages` |
| 4 | per-page 绑定是否进入版本快照？ | **进入版本快照** | A-4 VersionHandler 快照字段 + C-7 rollback 路径 |

---

## 9 · 风险与备选

| 风险 | 触发条件 | 缓解 |
|---|---|---|
| 自动绑定命中率低 | 意图关键词过于宽泛（如"计算机基础"） | 保留教师手工覆盖权；自动绑定失败时降级为"空绑定 + 提示教师上传" |
| 旧 S2 路由删除影响未升级客户端 | 教师浏览器缓存 | 路由表层做兼容层：旧 `/S2Material` 路径重定向到 `S3Studio` |
| per-page 绑定 schema 改动影响旧数据 | 旧课件没有 `pageBindings` 字段 | 旧课件整课件级 `evidence_packet` 保留作为兜底；首次进入新设计时一次性迁移 |
| 三门硬阻塞破坏旧工作流 | 教师习惯"一锅烩"自动生成 | 阶段条提供"实验性开关：跳过阶段确认"（默认关闭，二期上线） |
| 页面级绑定与互动资源冲突 | 互动节点类型（HTML5）的页面 | 互动资源（`interactiveStore`）与页面级绑定解耦——互动资源另存独立 asset_id 池 |

---

## 10 · 验收清单

- [ ] 答辩可讲清"为什么三道硬阻塞门 + 为什么页面级绑定"两个创新点（详见 §4）
- [ ] 评审方理解"S2 路由删除、代码复用"为何不破坏旧教师使用习惯（详见 §5 + §9）
- [ ] 落地后跑通：意图锁定 → S3 进入自动绑定 → 教师上传/勾选覆盖 → 大纲确认 → 内容生成（页面级局部重生成）→ 样式确认 → S4 回滚到旧版本（pageBindings 一并恢复）→ 自动跳回 S3 大纲层编辑 → 编辑即开新版本
- [ ] 测试覆盖：B-1 / B-2 / B-4 / B-5 / A-1 / A-3 / A-4 / C-2 / C-5 / C-8 各至少 1 个单测

---

**附：与既有文档的差异一览**

| 维度 | 旧 S2 设计 | 新设计 |
|---|---|---|
| 在主流程中 | 必经步 | **路由删除**，代码复用进 S3 左栏 |
| 资料上传 | 仅 S2 页面 | 仅 S3 左栏（按页面） |
| 证据绑定粒度 | 整份课件 | 单个 page（页面即最小节点单位） |
| 自动绑定 | 无 | 意图关键词驱动，S3 进入时后台触发 |
| 旧 S3 设计 | 一锅烩七阶段管道 | 4 phase-tabs + 3 道硬阻塞确认门 |
| AI 对话修改 | 全课件重生成 | 页面级 + 限定 evidence_refs 重生成 |
| 互动资源 | 独立子流程 | 保留，作为"页面管理"phase 的子工作台 |
| 中间页 | 含"资料与证据中心"按钮 | 删除该按钮（路由已删） |
| 版本快照 | 仅 generation 内容 | + pageBindings（用户已确认） |