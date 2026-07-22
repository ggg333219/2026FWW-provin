# 开发 Skill 注意事项

> 团队 4 人并行开发 4 个 Skill + KB 的协作规范
> 最后更新: 2026-07-21

---

## 0. 你当前要做的（S1 意图理解）

当前这个项目是“在已有代码基础上继续扩展”，不是从零重写。你现在负责的是 S1 意图理解板块，重点是把“多轮对话 → 结构化教学意图”这条链路接通，并且保证后续 S3 能直接消费。

### 当前优先级
1. 先做“最小可用闭环”：从教师对话中提取主题、时长、风格、目标学生等字段。
2. 再补“追问机制”：当信息不完整时，生成 1~2 个针对性的追问。
3. 最后补“确认流程”：教师确认后，产出可传给下游的结构化意图摘要。

### 你现在需要落地的内容
- 在 `ai_engine/intent/` 下新增意图提取、追问生成、确认逻辑相关模块。
- 通过 `ai_engine/core/schema.py` 里的 `IntentSummary`、`IntentExtractRequest`、`IntentConfirmRequest` 作为统一契约。
- 在 `ai_engine/main.py` 注册 S1 的 FastAPI router，确保 Python 侧可被调用。
- 让 Go 侧现有的 `backend/internal/handler/conversation_handler.go` 通过已有接口调用到 Python 的 `/intent/extract` 和 `/intent/confirm`。
- 先保证“能跑通”而不是追求过度复杂：优先验证对话输入 → 结构化意图 → 追问 → 确认这条链路。

### 当前不要动的内容
- 不要改动旧的 `ai_engine/qa.py`、`ai_engine/generator.py`、`ai_engine/parser.py`、`ai_engine/schema.py`。
- 不要把 S1 设计做成全量重构，先保证与现有项目兼容。

### 你当前最关键的目标
- 能从一段教师对话里产出 `IntentSummary`。
- 能在信息不完整时生成合理追问。
- 能把确认后的意图交给后续模块使用。

---

## 1. 项目现状

### 已完成的准备工作

- ✅ 目录骨架已建（`ai_engine/{core,intent,parse,gen,rag}`、`backend/internal/repository`、`frontend/teacher/src/{router,views,components/...}`）
- ✅ `ai_engine/core/` 共享基础设施已就绪（`config.py` + `llm.py` + `sse.py` + `schema.py`）
- ✅ Go 后端接口已扩展（`AIEngine` 接口新增 16 个方法、6 个新 handler 文件、17 条新路由、编译通过）
- ⬜ **Phase 4：Skill 实现开发（当前阶段）**
- ⬜ Phase 5：记录跟踪与收尾

### 每人分工

| 人 | 负责 | Python 模块 | Go Handler | 前置依赖 |
|----|------|------------|-----------|---------|
| P1 | **S1 意图理解** | `ai_engine/intent/` | `conversation_handler.go` | 无（独立） |
| P2 | **S2 多模态解析** | `ai_engine/parse/` | `parse_handler.go` | 无（独立） |
| P3 | **KB 知识库 RAG** | `ai_engine/rag/` | `knowledge_handler.go` | 需要 Chunk schema（已定） |
| P4 | **S3 课件生成 + S4 个性化满足** | `ai_engine/gen/` | `generation_handler.go` + `version_handler.go` + `export_handler.go` | 需要 IntentSummary + EvidencePacket（先用 mock） |

---

## 2. 核心开发原则

### 原则 1：新代码用新路径，旧代码不动

现有文件（`qa.py`、`generator.py`、`main.py`、`parser.py` 等）一个不改。新 Skill 代码全部写在对应的新目录里：

```
ai_engine/
├── intent/       ← P1 写这里
├── parse/        ← P2 写这里
├── rag/          ← P3 写这里
└── gen/          ← P4 写这里
```

**不修改 `qa.py`、`generator.py`、`parser.py`、`schema.py`（旧的那个）。**

### 原则 2：LLM 调用统一走 `core/`

```python
# ✅ 正确
from ai_engine.core import LLMClient

client = LLMClient(model="qwen-turbo", temperature=0.1)
response = client.chat("system prompt", "user input")
result = client.chat_json("system", "user", schema={...})

# ❌ 禁止：新代码自己 new OpenAI()、自己 os.getenv
from openai import OpenAI                   # 不要
client = OpenAI(api_key=..., base_url=...)  # 不要
```

`LLMClient` 自动处理：API key 获取、base URL 路由、Mock 模式、JSON 提取、异常回退。

### 原则 3：数据模型统一引用 `core/schema.py`

```python
# ✅ 正确
from ai_engine.core.schema import IntentSummary, EvidencePacket, TeachingNode, Chunk

intent = IntentSummary(topic="排序算法", duration_minutes=45)

# ❌ 禁止：新代码自己重新定义已经存在的结构
class IntentSummary:    # 不要，用 core/schema.py 的
    ...
```

两个 schema 文件共存：

- `ai_engine/schema.py` — 旧的，现有代码在用，**不改**
- `ai_engine/core/schema.py` — 新的，**所有新 Skill 代码引用这个**

### 原则 4：配置统一读 `settings`

```python
from ai_engine.core import settings

settings.MODEL        # → "qwen-turbo"
settings.TEMPERATURE  # → 0.2
settings.is_mock      # → False（开发时可在 .env 设为 mock 模式）
```

**不要在 Skill 代码里出现 `os.getenv("AI_MODEL")`。**

---

## 3. Skill 开发边界

### 3.1 每个 Skill 自包含一个 FastAPI router

```python
# ai_engine/intent/router.py
from fastapi import APIRouter
from ai_engine.core.schema import IntentExtractRequest

router = APIRouter(prefix="/intent", tags=["S1-Intent"])

@router.post("/extract")
async def extract(req: IntentExtractRequest):
    ...
```

P4 注意：S3 和 S4 可以共用一个 router 文件，也可以拆成 `gen/router.py` + `version/router.py`，按需决定。

### 3.2 在 `ai_engine/main.py` 注册 router

每个人在 main.py 追加一行即可，互不冲突：

```python
# main.py 新增（按需取消注释）
# from ai_engine.intent.router import router as intent_router
# from ai_engine.parse.router import router as parse_router
# from ai_engine.rag.router import router as rag_router
# from ai_engine.gen.router import router as gen_router

# app.include_router(intent_router)
# app.include_router(parse_router)
# app.include_router(rag_router)
# app.include_router(gen_router)
```

### 3.3 Python 路由与 Go 路由的对应关系

Go 端路由已经注册好，指向已存在的 handler。Go handler 会调用 `AIEngine` 接口方法 → HTTP → Python router。

| Python 路由 | Go 路由 | Go Handler | AIEngine 接口方法 |
|------------|---------|-----------|------------------|
| `/intent/extract` | `POST /api/v1/intent/extract` | `ConversationHandler.ExtractIntent` | `IntentExtract` |
| `/intent/confirm` | `POST /api/v1/intent/confirm` | `ConversationHandler.ConfirmIntent` | `IntentConfirm` |
| `/parse/process` | `POST /api/v1/parse/process` | `ParseHandler.ProcessFile` | `ParseProcess` |
| `/parse/status/{task_id}` | `GET /api/v1/parse/status/:task_id` | `ParseHandler.ParseStatus` | `ParseStatus` |
| `/parse/video` | `POST /api/v1/parse/video` | `ParseHandler.ProcessVideo` | `ParseVideo` |
| `/rag/search` | `POST /api/v1/rag/search` | `KnowledgeHandler.Search` | `RAGSearch` |
| `/rag/evidence` | `POST /api/v1/rag/evidence` | `KnowledgeHandler.Evidence` | `RAGEvidence` |
| `/knowledge/upload` | `POST /api/v1/knowledge/upload` | `KnowledgeHandler.Upload` | `KnowledgeUpload` |
| `/gen/create` | `POST /api/v1/gen/create` | `GenerationHandler.Create` | `GenerationCreate` |
| `/gen/status/{task_id}` | `GET /api/v1/gen/status/:task_id` | `GenerationHandler.Status` | `GenerationStatus` |
| `/gen/modify/{gen_id}` | `POST /api/v1/gen/modify/:gen_id` | `GenerationHandler.Create`（暂用） | `GenerationModify` |
| `/version/{gen_id}/history` | `GET /api/v1/version/:gen_id/history` | `VersionHandler.History` | `VersionHistory` |
| `/version/{gen_id}/rollback` | `POST /api/v1/version/:gen_id/rollback` | `VersionHandler.Rollback` | `VersionRollback` |
| `/version/{gen_id}/lock` | `POST /api/v1/version/:gen_id/lock` | `VersionHandler.Lock` | `VersionLock` |
| `/export/{gen_id}` | `POST /api/v1/export/:gen_id` | `ExportHandler.Create` | `ExportCreate` |
| `/export/status/{job_id}` | `GET /api/v1/export/status/:job_id` | `ExportHandler.Status` | `ExportStatus` |

---

## 4. 跨 Skill 契约规则

### 4.1 上游没写完时，用 mock 数据开发

```python
# P4 开发 S3 时 mock S1 的输出
MOCK_INTENT = IntentSummary(
    topic="排序算法",
    duration_minutes=45,
    style="讲练结合",
    target_student="大一计算机专业",
    knowledge_points=["冒泡排序", "快速排序"],
)

# P4 开发 S3 时 mock KB 的输出
MOCK_EVIDENCE = EvidencePacket(
    relevant_chunks=[Chunk(chunk_id="c1", content="...", source_type="pdf")],
    synthesized_context="这是关于排序算法的参考内容",
    citations=[Citation(chunk_id="c1", text_snippet="...", source_ref="doc_xxx")],
)
```

### 4.2 接口字段只增不删不改名

- 如果 `core/schema.py` 里缺某个字段 → 直接在 `core/schema.py` 加（新增 Optional 字段不影响已有代码）
- 如果字段名不合理 → **通知全团队讨论**，不能自己悄悄改
- 联调时发现字段对不上 → 问题出在没有通知团队

### 4.3 跨 Skill 数据流

```
S1 → IntentSummary ──┐
                     ├──→ S3 (mock 直到 S1 完成)
S2 → Chunks → KB → EvidencePacket ──┘
                         ↓
                    S3 → TeachingNode[] → S4 (version + export)
```

### 4.4 联调顺序建议

1. **先通一路**：P1 + P4 联调 S1→S3（mock KB）
2. **再通另一路**：P2 + P3 + P4 联调 S2→KB→S3（mock S1）
3. **最后全流程**：S1 → S2 → KB → S3 → S4 端到端

---

## 5. 质量标准

### 5.1 文件规范

- 每个新 `.py` 文件**必须有文件级 docstring**，说明该文件做什么
- 函数/方法必须有类型注解
- 类必须有 class docstring

### 5.2 测试

- 每个 Skill 模块的核心逻辑要有单元测试
- 测试文件放 `ai_engine/tests/` 下
- 运行方式：`python -m pytest ai_engine/tests/`

### 5.3 提交前检查清单

| 检查项 | 命令 |
|--------|------|
| Python 导入正常 | `python -c "from ai_engine.intent.router import ..."` |
| Go 编译通过 | `cd backend && go build ./cmd/teacher/...` |
| Schema 一致 | 确认用到的字段名和 `core/schema.py` 完全一致 |
| 没有新 import openai | `grep -r "from openai import" ai_engine/intent/ ai_engine/parse/ ai_engine/rag/ ai_engine/gen/` 应无结果（统一走 core/llm.py） |

### 5.4 Mock 模式

开发时可以在 `.env` 中设 `AI_GEN_MODE=mock`，这样所有 `LLMClient` 调用返回模拟响应，无需真实 API key：

```env
AI_GEN_MODE=mock
```

---

## 6. 常见问题

### Q: 我想用的字段在 `core/schema.py` 里没有怎么办？

直接在 `core/schema.py` 里新增，注意：

- 可选字段用 `Optional` 包裹
- 列表字段用 `Field(default_factory=list)`
- 加上字段注释说明用途

### Q: 需要修改现有文件怎么办？

只允许两个地方可以改：

1. `ai_engine/main.py` — 追加 router 注册
2. `ai_engine/core/schema.py` — 追加新字段/新结构

其他现有文件（`qa.py`、`generator.py`、`parser.py` 等）一律不动。

### Q: Go 那边的路由需要改吗？

不需要。Go 端的 handler、路由、`AIEngine` 接口都已注册好。P4 如果发现 `gen/modify` 的 handler 需要拆分，可以新建 `generation_modify_handler.go`，然后在 `main.go` 注入并在 `RegisterNewSkillRoutes` 里替换。

### Q: 我需要新加一个 Python 依赖包怎么办？

1. 加到 `ai_engine/requirements.txt`
2. 通知全团队 `pip install -r ai_engine/requirements.txt`

### Q: 前端谁做？

当前 Phase 4 优先完成后端 + AI Engine 的 Skill 逻辑。前端开发在 Skill 逻辑跑通后再开始，或者按需与后端同步进行（前端不阻塞后端）。
