# 垂直切片方案 — 多模态 AI 互动式教学智能体

> 基于 PRD（`2026-07-08-multimodal-ai-teaching-agent-prd.md`）切分，共 10 条垂直切片。
> 每条切片为穿透所有层级的 tracer bullet，可独立开发、独立验证。

---

## 切片清单总览

| # | 切片名称 | 类型 | 依赖 |
|---|----------|------|------|
| 1 | 视频资料解析 | AFK | 无 |
| 2 | 本地知识库 RAG 入库 | AFK | 无 |
| 3 | 知识库检索融合 | AFK | Slice 2 |
| 4 | 多轮对话需求澄清 | AFK | 无 |
| 5 | Word 教案生成与导出 | AFK | Slice 4 |
| 6 | PPT 成品生成与导出 | AFK | Slice 4 |
| 7 | 版本管理与差异对比 | AFK | Slice 5 + Slice 6 |
| 8 | 参考资料上传与解析 | AFK | 无 |
| 9 | 预览与修改反馈 UI | HITL | Slice 5 + Slice 6 + Slice 7 |
| 10 | 互动小游戏创意生成 | AFK | Slice 4 |

---

## Slice 1 — 视频资料解析

### What to build

教师上传视频文件（MP4/AVI/MOV）→ Go 后端接收并转发给 AI Engine → AI Engine 调用 ffmpeg 抽关键帧 + Whisper 语音转写 + VLM 摘要 → 返回结构化解析结果（关键帧列表 + 字幕文本 + 摘要）→ 前端展示解析状态和结果摘要。

### Acceptance criteria

- [ ] 视频文件上传接口可接收 mp4/avi/mov，文件大小限制合理（建议 500MB 以内）
- [ ] AI Engine `/parse-video` 端点返回结构化 JSON：keyFrames（帧URL列表）、transcript（字幕文本）、summary（AI摘要）
- [ ] 解析为异步任务，前端可轮询任务状态（queued / running / success / failed）
- [ ] 解析失败时返回明确错误信息，不产生二义性报错
- [ ] 关键帧抽取策略合理（建议 ffmpeg 按时间均匀抽 5-10 帧，或按场景变化检测）

### Blocked by

None — 可立即开始

---

## Slice 2 — 本地知识库 RAG 入库

### What to build

管理员上传知识库文档（txt/md/pdf）→ AI Engine `rag_index` 做文档清洗 → 分片（chunk_size 建议 500-1000 字）→ 向量化（Embedding API）→ 写入向量库（Milvus / Chroma）→ Go 后端记录 `rag_documents` 和 `rag_chunks` 元数据 → 返回入库状态和 chunk 数量。

### Acceptance criteria

- [ ] 知识库文档上传接口支持 txt / md / pdf，上传后返回 documentId
- [ ] `POST /rag-index` 端点执行完整入库流程：清洗 → 分片 → 向量化 → 写入向量库
- [ ] `rag_documents` 表记录文档元信息（source_type / source_ref / status）
- [ ] `rag_chunks` 表记录切片内容（document_id / chunk_text / embedding_ref / chunk_index）
- [ ] 入库完成后返回 chunk 总数，可查询指定文档的切片列表
- [ ] 支持幂等：同一文档重复入库时更新而非重复创建

### Blocked by

None — 可立即开始

---

## Slice 3 — 知识库检索融合

### What to build

教师发起教学查询（或生成指令中附带查询）→ AI Engine `rag_retrieve` 接收查询向量 → 向量库检索 top-k（建议 k=5）chunks → 返回文本片段 + 来源引用（documentName + chunkIndex）→ 结果以结构化格式输出，可供后续生成模块直接引用。

### Acceptance criteria

- [ ] `POST /rag-retrieve` 端点接收查询文本，返回 top-k 相关切片
- [ ] 每个返回结果携带来源信息（原文片段、来源文档名、chunk 位置）
- [ ] 检索延迟合理（建议单次 < 500ms）
- [ ] 检索结果可作为生成模块的输入，格式与生成指令集兼容
- [ ] 空检索结果时返回空列表而非报错

### Blocked by

Slice 2（知识库需先有数据才能检索）

---

## Slice 4 — 多轮对话需求澄清

### What to build

教师发送消息（文字或语音转文字）→ Go Conversation 模块记录轮次 → AI Engine 判断是否需要追问（教学目标 / 知识点清单 / 时长 / 风格 / 产出格式）→ 若需追问返回追问内容 + `needFollowup=true` → 教师继续补充 → 多轮后教师确认需求 → 输出结构化 `intentSummary`（topic / duration / style / knowledge_points / output_format）→ 锁定会话状态为 confirmed。

### Acceptance criteria

- [ ] `POST /conversations/{id}/messages` 支持文字输入，返回 AI 追问内容
- [ ] `needFollowup=true` 时前端展示追问引导卡片，引导教师补充信息
- [ ] 多轮对话上下文完整保留（至少支持 10 轮以上）
- [ ] `intentSummary` 包含字段：topic / duration / style / target_student / knowledge_points[] / output_format[] / with_interactive
- [ ] 教师可调用 `POST /conversations/{id}/confirm` 确认意图摘要，确认后状态锁定
- [ ] 确认前教师可修改已输入内容，确认后进入生成阶段

### Blocked by

None — 可立即开始，后端逻辑可独立于前端 UI 开发

---

## Slice 5 — Word 教案生成与导出

### What to build

教师确认 `intentSummary` 后 → Go 后端调用 AI Engine `generate-word` → AI Engine 接收教案结构指令（教学目标 / 教学过程 / 教学方法 / 课堂活动 / 课后作业）→ LLM 生成 Word 格式内容 → 通过 python-docx 生成 .docx 文件 → 存入 MinIO → 前端可下载。

### Acceptance criteria

- [ ] `POST /generation/draft` 支持指定输出格式 docx（单独或与 pptx 并行）
- [ ] 生成的 Word 教案包含：教学目标、教学过程（含时间分配）、教学方法、课堂活动设计、课后作业
- [ ] .docx 文件可正常用 Microsoft Word / WPS 打开，格式不乱
- [ ] 生成过程为异步，前端可轮询任务状态
- [ ] 生成完成后前端显示下载链接，支持多次下载

### Blocked by

Slice 4（依赖 intentSummary 作为生成输入）

---

## Slice 6 — PPT 成品生成与导出

### What to build

教师确认 `intentSummary` 后 → Go 后端调用 AI Engine `ppt-export` → AI Engine 接收页面内容 JSON + 模板风格参数 → 通过 python-pptx 生成 .pptx（含封面页 / 目录页 / 内容页 / 总结页）→ 存入 MinIO → 前端可下载。

### Acceptance criteria

- [ ] `POST /generation/draft` 支持指定输出格式 pptx
- [ ] 生成的 PPT 包含：封面（标题 + 副标题）、目录页、内容页（图文并茂、逻辑层次清晰）、总结页
- [ ] 每页内容与 intentSummary 中的知识点对应，无遗漏
- [ ] .pptx 文件可正常用 Microsoft PowerPoint / WPS 打开，格式不乱
- [ ] 生成过程为异步，前端可轮询任务状态
- [ ] 生成完成后前端显示下载链接，支持多次下载

### Blocked by

Slice 4（依赖 intentSummary 作为生成输入）

---

## Slice 7 — 版本管理与差异对比

### What to build

教师提交修改意见 → Go Agent 调度再生成 → Version 模块保存新版本快照 → 记录版本链（parent_version_id）→ 支持查看历史版本列表 → 支持 diff 展示（新增 / 修改 / 删除页面标记）→ 支持回滚到指定历史版本。

### Acceptance criteria

- [ ] 每次再生成自动创建新版本，记录 version_no 和 parent_version_id
- [ ] `GET /generation/{id}/versions` 返回版本列表（version_no / created_at / summary）
- [ ] `GET /generation/{id}/versions/{version_no}` 返回指定版本的完整内容
- [ ] diff 展示支持：页面级差异（新增页面 / 删除页面 / 修改页面内容）
- [ ] `POST /generation/{id}/rollback` 支持回滚到指定版本，回滚后生成新版本（不断链）
- [ ] 教师可锁定"最终版本"，锁定后不可直接修改（需通过再生成流程）

### Blocked by

Slice 5 + Slice 6（依赖生成结果才有版本可管理）

---

## Slice 8 — 参考资料上传与解析

### What to build

教师上传参考资料（PDF / Word / PPT / 图片）→ Go 后端接收并记录 `material_assets` → 根据文件类型分发到对应解析器 → 解析完成后更新 `parse_status` → 前端展示解析状态（解析中 / 解析完成 / 解析失败）和关键内容摘要。

### Acceptance criteria

- [ ] 上传接口支持 PDF / Word(.docx) / PPT(.pptx) / 图片(.jpg/.png)，返回 materialId
- [ ] PDF / PPT 复用现有 AI Engine DocumentParser，返回页级结构化文本
- [ ] Word 文档新增解析器，提取文本结构和段落语义
- [ ] 图片上传后调用 OCR 提取文字，标注图片内文字区域
- [ ] 解析状态实时更新，前端展示进度
- [ ] 解析结果与 intentSummary 关联（通过 material_mappings 表）

### Blocked by

None — 可立即开始，与 Slice 1 并行开发

---

## Slice 9 — 预览与修改反馈 UI

### What to build

前端预览界面同时展示 PPT 页面缩略图网格 + Word 教案富文本 → 教师在界面内输入修改意见 → 提交反馈触发再生成 → 展示差异高亮（新内容绿色 / 删除内容红色 / 修改内容黄色）→ 教师确认满意后点击"锁定版本"。

### Acceptance criteria

- [ ] 预览界面同时渲染 PPT 和 Word 内容，无需切换页面
- [ ] 教师可对单页或整体提出修改意见（如"第3页简化"、"增加一个生活案例"）
- [ ] 修改提交后展示新旧版本 diff 高亮，教师可逐条确认接受或拒绝
- [ ] 确认"满意"后版本锁定，进入导出流程
- [ ] 预览过程无需刷新页面，局部更新差异区域

### Blocked by

Slice 5 + Slice 6 + Slice 7（依赖生成能力和版本管理就绪）

### Type

HITL — 需人工测试交互体验，无法完全自动化验证

---

## Slice 10 — 互动小游戏创意生成

### What to build

教师在需求中声明"需要互动内容" → AI Engine 根据知识点生成小游戏创意描述（游戏规则 / 流程 / UI 示意图）→ 以结构化 JSON 或 Markdown 返回 → 前端展示创意卡片（标题 / 规则说明 / 适用知识点 / 建议时长）。

### Acceptance criteria

- [ ] `intentSummary` 中 `with_interactive=true` 时触发互动内容生成
- [ ] 生成结果包含：游戏名称、游戏规则描述、适合年龄段、建议时长、所需道具/素材
- [ ] 创意描述具体可执行（非泛泛而言），教师可基于描述自行实现或交由开发实现
- [ ] 若知识点不适合互动游戏（如纯记忆性内容），生成器应给出说明而非强制生成
- [ ] 导出时说明互动内容的导出形式（HTML5 / GIF / MP4 / 嵌入PPT）

### Blocked by

Slice 4（依赖 intentSummary 中的 with_interactive 标记）

### Type

AFK — 生成逻辑可自动化，创意质量由人工预览把关

---

## 依赖关系图

```
Slice 4 ──┬── Slice 5 ──┬── Slice 7 ──┬── Slice 9 (HITL)
          │             │
          │             └── Slice 6 ──┘
          │                              (Slice 7 同时依赖 5+6)
          │
          └── Slice 10

Slice 1 ────────────────────────────── Slice 9 (HITL)
Slice 2 ── Slice 3
Slice 8 ──（独立，可与上述任意切片并行）
```

---

## 开发顺序建议

**第一梯队（可立即开始，无依赖）**

- Slice 4（对话澄清）— 后端逻辑先跑通
- Slice 2（RAG 入库）— 知识库基础
- Slice 8（资料上传解析）— 独立可并行

**第二梯队（依赖第一梯队）**

- Slice 3（RAG 检索）— 依赖 Slice 2
- Slice 5 / Slice 6（生成）— 依赖 Slice 4
- Slice 1（视频解析）— 与 Slice 8 类似，可并行

**第三梯队（依赖第二梯队）**

- Slice 7（版本管理）— 依赖 Slice 5 + 6
- Slice 10（互动创意）— 依赖 Slice 4

**第四梯队（HITL，需人工）**

- Slice 9（预览 UI）— 依赖 Slice 5 + 6 + 7 就绪后开始
