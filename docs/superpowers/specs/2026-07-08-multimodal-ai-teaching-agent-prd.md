# PRD — 多模态 AI 互动式教学智能体

## Problem Statement

当前教学工具存在"功能碎片化"和"意图理解浅层化"的问题：教师需要分别使用多个工具完成教学设计、PPT 制作、讲义撰写，流程割裂；工具只能执行单次简单指令，无法与教师进行多轮深入对话以精准把握其复杂的教学思路和个性化要求。

本项目旨在将现有的"泛雅 AI 智课系统"（原系统核心链路：课件解析→讲稿生成→学生问答→进度续接）重构为"多模态 AI 互动式教学智能体"（新链路：教师需求输入→多轮对话澄清→多模态参考融合→课件生成→预览修改→导出成品），让教师从"事务型工作者"转向"设计型导师"。

## Solution

构建一个以教师教学思路为驱动、具备深度互动与多模态解析生成能力的课件共创系统。系统通过自然语言（语音/文字）与教师进行多轮对话，主动询问确认细节直至清晰理解教学目标、核心知识点、讲授逻辑、重点难点和互动设计思路；允许教师上传 PDF/Word/PPT/图片/视频等多种参考资料并智能融合；生成结构完整、内容丰富的 PPT 课件初稿和 Word 教案，并支持按教师要求生成动画创意或互动小游戏；提供预览与修改反馈闭环，支持迭代优化并最终导出标准格式文件。

## User Stories

### 对话与需求澄清

1. 作为教师，我希望通过文字输入教学需求（主题、时长、风格、目标学生），系统能主动追问缺失的关键信息（教学目标、知识点清单、重点难点、产出格式），最终给我一个结构化的需求摘要供我确认。
2. 作为教师，我希望通过语音输入教学思路，系统能将语音转为文字并开始需求澄清流程。
3. 作为教师，我希望能上传已有的参考资料（PDF 教案、Word 文档、参考视频片段、图片），并告诉系统"参考这个 PDF 的哪个知识点的内容或格式"。
4. 作为教师，我确认需求摘要后，系统能锁定意图并进入生成阶段，不随意偏离我确认的内容范围。
5. 作为教师，我希望系统记录完整的对话历史，支持我随时回溯和补充修改。

### 多模态资料解析

6. 作为教师，我希望上传 PDF 文件，系统能提取其中的知识结构、案例内容和排版风格，并在生成时融合这些元素。
7. 作为教师，我希望上传 Word 文档，系统能解析其中的文本结构和教学设计要素。
8. 作为教师，我希望上传 PPT 文件，系统能理解其内容组织和视觉呈现方式。
9. 作为教师，我希望上传图片（截图、示意图），系统能通过 OCR 或视觉理解提取文字和结构信息。
10. 作为教师，我希望上传视频片段，系统能抽取关键帧、字幕或语音转写，并在生成时引用视频中的案例或讲解。
11. 作为教师，我上传资料后能看到解析状态（解析中/解析完成/解析失败），失败时能看到失败原因。

### 知识融合与 RAG

12. 作为教师，我希望系统能从本地专业知识库中检索与我的教学主题相关的资料，并在生成时融合这些知识。
13. 作为教师，我希望系统告诉我生成内容参考了知识库的哪部分内容，并展示引用来源。
14. 作为知识库管理员，我希望上传、更新和删除知识库文档，系统能自动完成清洗、切片、向量化并建立可检索索引。

### 课件生成

15. 作为教师，我确认需求后，系统能生成包含封面页、目录页、内容页（图文并茂、逻辑层次清晰）和总结页的 PPT 初稿。
16. 作为教师，系统生成的 PPT 内容应与我的教学目标、知识点和时长要求一致。
17. 作为教师，我希望能生成与 PPT 配套的 Word 教案，包含教学目标、教学过程、教学方法、课堂活动设计和课后作业。
18. 作为教师，我希望能根据知识点生成一个简单的互动小游戏创意或动画创意描述。

### 预览与修改再生成

19. 作为教师，我能在预览界面同时看到 PPT 页面缩略图和 Word 教案内容。
20. 作为教师，我看到预览后能提出修改意见（调整顺序、简化某页、增加案例、替换图片），系统能理解并执行修改。
21. 作为教师，系统修改后我能看到新旧版本的差异，确认满意后锁定版本。
22. 作为教师，我能看到生成历史的版本列表，支持切换查看和回滚到之前的版本。

### 导出与下载

23. 作为教师，我满意最终版本后，能以标准格式（.pptx、.docx）下载完整课件包。
24. 作为教师，如果生成了互动小游戏或动画，系统能以 HTML5/ GIF / MP4 等格式导出或嵌入 PPT 中。
25. 作为教师，导出任务完成后我能收到通知，并支持断点续传或重新下载。

### 系统与辅助功能

26. 作为教师，我希望所有长任务（解析、生成、导出）都支持异步执行并能查询实时进度。
27. 作为教师，我发起的每个会话有唯一 ID，支持跨设备恢复。
28. 作为知识库管理员，我能看到知识库的文档列表、切片数量和最后更新时间。
29. 作为系统，我能在教师上传非法格式或超大文件时给出明确提示，不产生二义性错误。

## Implementation Decisions

### 模块划分

**线 A — 底层能力扩展（AI Engine）**

- 新增 `parse_video` 工具 endpoint：接收视频文件 URL，调用 ffmpeg 抽取关键帧 + Whisper 语音转写 + VLM 摘要，返回结构化解析结果
- 新增 `generate_word` 工具 endpoint：接收教案结构化指令集，调用 LLM 生成 Word 格式教案文本，通过 python-docx 输出 .docx 文件流
- 新增 `ppt_export` 工具 endpoint：接收页面内容 JSON + 模板风格参数，通过 python-pptx 生成可下载 .pptx 文件流
- 新增 `rag_index` 工具 endpoint：接收文档文本，分片、向量化后写入向量库（Milvus/Chroma），返回 chunk 列表和入库状态
- 新增 `rag_retrieve` 工具 endpoint：接收查询向量，从向量库检索 top-k chunks，返回文本片段及来源引用
- 扩展 `AIEngine` Go 接口：向上述 5 个新 endpoint 各新增一个对应的 Go 方法

**线 B — 上层链路编排（Go Backend 新增模块）**

- 新增 `Conversation` 模块：管理教师与智能体的多轮对话上下文，维护对话状态机（收集需求中 / 已确认 / 生成中 / 修改中），输出结构化 `intentSummary`
- 新增 `Agent Orchestrator` 模块：根据 `intentSummary` 规划任务序列，决定调用哪个 Tool，按依赖顺序调度执行，处理失败重试
- 新增 `Version` 模块：每次生成后保存版本快照，记录修改差异（diff），支持回滚，提供"当前版本"锁定能力
- 新增 `Export Job` 模块：管理异步导出任务的生命周期（queued → running → success/failed），存储输出文件 URL

**线 C — 前端（Vue Teacher Workspace）**

- 新增对话 UI：消息气泡（教师/系统）、追问引导卡片、需求确认弹窗
- 新增资料上传 UI：拖拽上传区（支持 PDF/Word/PPT/图片/视频）、上传进度条、解析状态标签
- 新增预览 UI：PPT 页面缩略图网格 + Word 教案富文本展示
- 新增修改反馈 UI：修改意见输入框 + 差异高亮展示

### 数据模型新增

| 表 | 用途 |
|----|------|
| `conversation_summaries` | 教师需求结构化摘要（topic/duration/style/knowledge_points） |
| `material_assets` | 参考资料元信息（owner/file_url/file_type/parse_status） |
| `generation_versions` | 生成版本主表（course_id/version_no/parent_version_id/status） |
| `generation_contents` | 版本内容明细（version_id/content_type/content_json） |
| `rag_documents` | 知识库文档（source_type/source_ref/status） |
| `rag_chunks` | 切片内容（document_id/chunk_text/embedding_ref） |
| `export_jobs` | 导出任务（version_id/formats/status/output_url） |

### API 路由新增

```
POST /api/v1/teacher/conversations                    # 启动会话
POST /api/v1/teacher/conversations/{id}/messages     # 发送消息
POST /api/v1/teacher/conversations/{id}/confirm       # 确认需求摘要
POST /api/v1/teacher/materials/upload                # 上传参考资料
POST /api/v1/teacher/materials/{id}/parse            # 触发解析
POST /api/v1/teacher/generation/draft                # 生成初稿
GET  /api/v1/teacher/generation/{id}/preview         # 获取预览
POST /api/v1/teacher/generation/{id}/regenerate      # 提交修改并再生成
POST /api/v1/teacher/export                          # 创建导出任务
GET  /api/v1/teacher/export/{id}/download            # 下载导出文件
```

### Agent 与 Tool 接口协议

- Agent 不直接拼页面内容，统一通过 Tool 接口获取结构化结果
- Tool 返回必须携带 `toolName / toolVersion / requestId` 以便追踪
- 各 Tool 支持幂等重试，Agent 负责调度顺序和依赖管理

## Testing Decisions

### 测试策略

- **端到端优先**：从"教师输入需求"到"下载到 .pptx 文件"，覆盖完整用户旅程
- **接口契约测试**：AI Engine 各 Tool endpoint 有清晰的输入/输出 schema，Go Backend 与 AI Engine 之间通过 HTTP JSON 通信，可独立测试接口契约
- **版本差异测试**：Version 模块的 diff 展示需要验证修改内容的正确性，重点测"同一字段修改"和"新增/删除页面"两种场景
- **不测实现细节**：不测试 Agent 内部调度算法、不测试 LLM 输出内容的具体措辞（只测结构完整性）

### 优先测试点

1. AI Engine `parse_video`：相同视频文件连续解析 3 次，验证输出一致性
2. AI Engine `rag_retrieve`：检索 top-5 结果的来源可溯源、chunk 文本与原始文档一致
3. Go Backend Conversation：发送 5 轮对话后确认 `intentSummary` 包含所有关键字段
4. Go Backend Version：生成初稿 → 修改 → 再生成 → 验证版本链完整性和 diff 正确性
5. Export：触发导出后轮询状态，最终 .pptx 和 .docx 文件可正常用 Office 软件打开

## Out of Scope

- 互动小游戏或动画的实际开发（生成创意描述为最终产出，不做游戏引擎实现）
- 数字人/虚拟教师形象相关的展示效果
- 音频 TTS 合成（作为可选增强项，不在主链路）
- 学生端功能（原系统学生提问/续接播放模块保留但不作为本赛题重点）
- Dify API 接入层改造（已有双实现机制，不在本轮改动范围）
- 知识库资料的批量导入工具（管理员手动上传即可）
- 私有化部署和容器化

## Further Notes

本 PRD 基于以下现有文档和代码状态：

- 文档/ 文件夹下的 5 个设计文档（架构/模块/API/数据库/需求差异）
- AI Engine 能力清单（已有 PDF/PPTX 解析、讲稿生成、QA、知识点树解析；缺视频解析、Word 教案、PPT 成品导出、RAG）
- Go Backend 当前 AIEngine 接口定义（支持本地/Dify 双实现）
- Vue 前端 student/teacher 分离构建结构

本次重构的核心原则：从底层 AI Engine 能力层逐步往上扩展，上层改动依赖下层接口就绪后再推进，三条线（AI Engine 扩展 / Go Backend 编排 / Vue 前端）可基于 mock 接口并行开发，互不阻塞。
