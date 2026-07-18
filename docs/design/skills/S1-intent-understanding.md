# Skill 1: 意图理解 (Intent Understanding) — 详细设计

> 基于 Phase 2 工作流分析结果编写
> 最后更新: 2026-07-15

## 1. 总体架构

本 Skill 跨越三层，与现有代码结构一致：

```
教师工作台 (Vue Frontend)
    |
    v
会话处理器 (Go Backend — conversation_handler.go)
    |
    v
会话管理器 (Go Backend — conversation_service.go)
    |
    v
意图引擎 (Python AI Engine — intent_engine.py)
```

**层边界：**
- Go 后端负责会话生命周期、轮次持久化、状态机转换和所有外部 API 契约
- Python AI Engine 负责所有 LLM 相关工作：从对话中提取意图、生成追问、生成可读摘要
- 前端提供聊天 UI、轮次显示和确认面板

## 2. 模块职责

### 2.1 会话管理器 (Go — `backend/internal/service/conversation_service.go`)

**职责：** 会话生命周期 CRUD、轮次持久化、状态机转换和锁定。

**复用现有代码：**
- `DialogueSession` 模型（`models.go` lines 110-120，需添加 `status` 字段）
- `DialogueTurn` 模型（`models.go` lines 208-222，需添加 `turn_type` 字段）
- `ensureDialogueSession()` 模式（`dialogue_support.go` lines 17-54）
- `appendDialogueTurn()` 模式（`dialogue_support.go` lines 63-83）
- `buildDialogueContext()` 模式（`dialogue_support.go` lines 86-118）

**新增数据库迁移：**
- `dialogue_sessions` 表添加 `status VARCHAR(30) DEFAULT 'collecting'`
- `dialogue_turns` 表添加 `turn_type VARCHAR(20) DEFAULT 'initial'`
- `dialogue_sessions` 表添加 `intent_summary JSONB`

**核心方法：`ProcessMessage(teacherInput, sessionId) -> (response, needFollowup, followupQuestions, intentSummary)`**

算法流程：
1. 加载或创建会话
2. 追加教师轮次
3. 若已锁定则拒绝
4. 调用意图引擎（Python）
5. 根据意图引擎响应更新会话状态
6. 追加智能体响应轮次
7. 返回响应

### 2.2 意图提取器 (Python — `ai_engine/intent_engine.py`)

**职责：** LLM 提示链，将完整对话历史转换为结构化 `IntentSummary`。

**复用现有代码：**
- `resolve_llm_base_url()` 从 `qa.py`
- OpenAI 客户端初始化模式
- JSON `response_format` 模式
- `_extract_json()` 回退

**LLM 提示结构：**

系统提示：定义为多模态 AI 教学智能体的意图理解模块，从对话历史中提取结构化教学意图，输出严格 JSON。

输出 JSON Schema：
```json
{
    "topic": string | null,
    "duration_minutes": integer | null,
    "style": string | null,
    "target_student": string | null,
    "knowledge_points": string[],
    "output_format": string[],
    "with_interactive": boolean,
    "key_difficulties": string[],
    "expected_outcomes": string[],
    "missing_fields": string[]
}
```

### 2.3 追问生成器 (Python — `intent_engine.py`)

**职责：** 根据当前 `IntentSummary` 和缺失字段列表，按优先级生成 1-2 个追问。

字段优先级：`topic > duration_minutes > style > target_student > others`

使用模板生成（90%+ 场景），LLM 回退重写仅当模板不足时。

### 2.4 摘要生成器 (Python — `intent_engine.py`)

**职责：** 生成人类可读的需求摘要供教师确认。纯模板渲染，无需 LLM 调用。

## 3. 会话状态机

```
collecting --> clarifying --> confirming --> confirmed --> locked

collecting → clarifying: 意图引擎检测到缺失字段时
clarifying → clarifying: 后续回答仍有缺口时
clarifying → confirming: 所有必填字段齐备时
confirming → confirmed: 教师调用 POST /confirm
confirmed → locked: 生成请求到达时自动锁定
```

- 进入 `locked` 后不再接受修改
- 教师发送修改意图可从任何状态回到 `collecting`
- 最多 8 轮澄清，超时 30 分钟自动终止

## 4. 接口契约

### POST /api/v1/teacher/conversations/{id}/messages

```json
// 请求
{ "message": "帮我做一份45分钟的排序算法课件", "session_id": "conv_xxx" }

// 响应（有缺失字段时）
{
  "code": 200,
  "data": {
    "response": "您希望这份课件主要面向哪个年级或专业的学生？",
    "need_followup": true,
    "followup_questions": ["面向哪个年级？", "什么风格？"],
    "intent_summary": { "topic": "排序算法", "duration_minutes": 45, ... },
    "session_status": "clarifying"
  }
}
```

### POST /api/v1/teacher/conversations/{id}/confirm

```json
// 请求
{ "session_id": "conv_xxx" }

// 响应
{
  "code": 200,
  "data": {
    "confirmed": true,
    "intent_summary": { /* 完整结构化意图 */ },
    "session_status": "confirmed"
  }
}
```

## 5. LLM 提示策略

| 调用点 | 模型 | 温度 | 格式 | 目的 |
|--------|------|------|------|------|
| 意图提取 | qwen-turbo | 0.1 | json_object | 从对话提取摘要 |
| 追问重写 | qwen-turbo | 0.3 | text | 模板不足时重写追问 |
| 摘要生成 | 无 | - | - | 纯模板 |

## 6. 错误处理

| 场景 | 处理方式 |
|------|---------|
| LLM 超时(>10s) | 返回部分意图，用通用追问 |
| JSON 解析失败 | 重试一次，使用 `_extract_json()` 回退 |
| 数据库不可用 | 日志 + 重试一次，返回 500 |
| 无效状态转换 | 返回 409 Conflict |
| 会话未找到 | 返回 404 |
| 速率限制(>30 msg/min) | 返回 429 |
| 意图引擎宕机 | 返回缓存静态追问 |

## 7. 现有代码复用映射

| 组件 | 文件 | 复用来源 |
|------|------|---------|
| 会话管理器 (Go) | `conversation_service.go` | `dialogue_support.go` lines 17-83 |
| 会话处理器 (Go) | `conversation_handler.go` | `compat_student.go` 请求/响应模式 |
| 意图引擎 (Python) | `intent_engine.py` | `qa.py` LLM 包装器 + JSON 模式 |
| Python API 路由 | `main.py` 新增路由 | 现有 FastAPI 路由模式 |
| 前端聊天 UI | 新组件 | 学生端 API 调用模式 |

## 8. 依赖关系

- 依赖：LLM 服务、Redis 会话缓存、Postgres
- 被调用：Agent Orchestrator（Go → Python HTTP）
- 输出消费：Agent Orchestrator 读取 `structured_intent` 分发到下游
