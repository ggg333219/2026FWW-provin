# 信息索取单 A–G 组回填（截至 2026-09-24）

> 对应文档：`项目方案撰写规划与信息索取单.md` 第五节
> 回填规则遵循索取单要求：按编号逐条；只给原子事实；数据带**数值+口径+样本/环境+时间**；拿不准写「待补」；区分「已实现（有证据）」与「规划中」。
> 事实底座详见 `A12项目报告.md`。

---

## A 组｜报送约束

| 编号 | 回填 |
|---|---|
| **A-05 评分标准原文 + 权重** | **待补**。赛题原文第 9 节「评分要点」全文仅一句：「赛题评分要点见附件：**A 类初决赛阶段评分表**」。**该附件不在本仓库内**，本机无法取得。需向赛题方索取后方可确定章节配比。<br>来源：`文档/服务外包省赛A12赛题.docx` 第 9 节 |
| **A-02 有无官方模板** | **待补**。赛题原文仅列提交材料 6 项（项目概要介绍 / 项目简介 PPT / **项目详细方案** / 项目演示视频 / 本地知识库资料 / 自愿补充材料），**未提模板**。 |
| **A-03 字数或页数上限** | **待补**。赛题原文**未规定**字数或页数上限。 |
| **A-04 提交格式与截止时间** | **待补**。赛题原文**未载明**截止时间。提交格式方面，第（3）项为「项目详细方案」（未指定 docx/pdf），第（4）项为「项目演示视频」（未指定格式与时长）。 |
| **A-06 评审形式（书面/答辩）** | **部分**。赛题原文提到「**A 类初决赛阶段**评分表」，说明分**初赛与决赛两个阶段**，但未说明各阶段是书面评阅还是答辩。<br>**其余待补**。 |

> 📌 **可用的替代依据**：在拿到评分表前，只能按赛题原文第 6 节**「任务要求」5 项 + 「技术要求与指标」4 项**倒推章节配比。这 9 项已在 `A12项目报告.md` §1.2/§1.3 逐条列明。

---

## B 组｜架构与实现

| 编号 | 回填 |
|---|---|
| **B-01 分层架构与服务清单** | ✅ **已实现**。三层服务：前端 Vue3（`frontend/teacher/`，9 页面）→ 后端 Go（`backend/`，Gin+GORM+JWT）→ AI 引擎 Python（`ai_engine/`，FastAPI）。<br>后端六层：`router` / `handler`(33 文件) / `service`(14) / `model` / `repository`(仅 `redis.go`) / `database`。<br>AI 引擎六模块：`core` / `intent` / `parse` / `rag` / `gen` / `recommendation`。<br>跨层原则 5 条（层隔离/默认异步/工具复用/证据协议/版本边界）见 `文档/000-README.md`。 |
| **B-02 部署拓扑** | ✅ 详见 `A12项目报告.md` §2.7。PostgreSQL+pgvector :15432、Redis :16379、MinIO :19000/19001、Go 后端 :18080、AI 引擎 :8000、前端 Vite :5173（均可自动顺延，见 `backend/pkg/serveraddr.Serve`）。<br>第三方依赖：**千问（DashScope 兼容）LLM**，模型默认 `qwen-turbo`。 |
| **B-03 技术选型决策表（≥6 项）** | **待补**。仓库内**未见**记录「放弃的备选方案与理由」的决策文档。现有决策日志仅 2 篇（`记录/决策日志/D-001-项目重构策略与Skill划分.md`、`D-002-gen模块拆分.md`），**不构成选型决策表**。<br>**需团队补充**。 |
| **B-04 接口数量 + 代表性契约** | ✅ 数量：**161 个路由**（GET 74 / POST 69 / PUT 11 / DELETE 7 / PATCH 0），口径为 `backend/internal/router/` 注册路由，统计时间 2026-09-24。<br>代表性契约（权威来源 `文档/011-S2S3新功能接口契约-v1.0.md`）：<br>① `PUT/GET /api/v1/coursewares/:project_id/page-bindings` —— 页面级资料绑定<br>② `POST /api/v1/gen/modify` —— 修改再生，字段含 `evidence_refs` / `page_id` / `user_instruction` / `citation_refs` / `evidence_used`<br>③ AI 对话消息按 `project_id` 持久化，**幂等 upsert 键为 `(project_id, message_id)`**（契约 §3.2）<br>另有权威读端点 `/latest-generation-context`。 |
| **B-05 代码规模/版本/规范** | ✅ 规模：Go **82 文件/27,638 行**、Python **93 文件/28,332 行**、Vue **42 文件/21,512 行** + JS **67 文件/10,016 行**，合计 284 文件 / **87,498 物理行**（口径：`find`+`wc -l`，含测试与注释，2026-09-24 实测）。测试文件 52 个。<br>版本见 §2.6。协作规范：`.github/CODEOWNERS`；**无 CI**。 |

---

## C 组｜算法细节

| 编号 | 回填 |
|---|---|
| **C-01 意图状态机** | ✅ **已实现**。状态集合 `collecting → clarifying → confirming → confirmed → locked`（`ai_engine/core/schema.py:45-51`）。<br>**锁定判定**：`_REQUIRED_FIELDS = [topic, duration_minutes]` 为必需字段（`schema.py:178`）。<br>**信息缺失时如何选下一个问题**：按 `_FIELD_PRIORITY = [topic, duration_minutes, style, target_student]` 顺序，依据 `intent.missing_fields` 生成追问，**单轮最多 2 个**（`intent/intent_engine.py:91` `questions[:2]`）。<br>**纠错机制**：所有字段抽取取文本中**最靠后的匹配**（`rules.py:25` `max(matches, key=item[0])`），实现「教师最后一次明确表达优先」。<br>**会话约束**：`max_turns=8`、`timeout_minutes=30`（`schema.py:259-262`）。<br>**双链路**：规则兜底 `IntentEngine` + LLM `LLMIntentEngine`（`qwen-turbo`, `temperature=0.1`, JSON Schema 约束），规则同时服务两条链路**避免行为漂移**（`rules.py` 头注释）。 |
| **C-02 多模态解析各路链路** | ✅ **已实现**。PDF：`doc_parser.py:150`（marker 优先，plain text 兜底）。PPTX：`:412` python-pptx 形状文本 + `_extract_ppt_images` + `_describe_image` 走 VLM。DOCX：`:571` unstructured 优先。<br>图片：`ocr_engine.py` **PaddleOCR**（`lang="ch"`, `use_angle_cls=True`）+ `_analyze_layout` 版面分析。视频：`video_processor.py` 元数据 → **FFmpeg 抽 5 关键帧** → 每帧 VLM 描述 → **Faster-Whisper ASR**（`base`）→ LLM 纠错。<br>**产出字段**统一标准化为 `Chunk`（`chunk_id`/`source_type`/`source_ref`/`content`/`page_ref`/`seq_index`/`metadata`）。<br>**意图—资料对应关系**由 `parse/material_mapper.py` 承担（对应赛题 2c）。 |
| **C-03 混合检索** | ✅ **已实现（重排除外）**。<br>**切分**：按类型分策略 —— PDF `paragraph` 512/64；PPTX `slide` 不限制；DOCX `section` 每章独立；IMAGE `sentence` 256/0；VIDEO/AUDIO `window` 256/32（`rag/chunker.py:49-67`）。<br>**向量**：`text-embedding-v3`，**1024 维**，批 20，env 可覆盖（`rag/embed.py:34-47`）。<br>**融合权重**：`0.7 × 向量 + 0.3 × BM25`；BM25 为纯 Python Okapi 实现，`k1=1.5`、`b=0.75`，中文单字+2gram；候选池 `top_k×4` 封顶 200（`rag/retrieve.py`）。<br>**降级**：无 embedding key 时自动退化为**纯 BM25**（`retrieve.py:212-234`）。<br>⚠️ **重排：规划中**。`rag/rerank.py` 当前为**占位透传**（`model_name=None` → `candidates[:top_k]`），Cross-encoder 接入仅在 TODO 中（计划 `BAAI/bge-reranker-v2-m3`），`sentence-transformers` 未默认安装。设计目标为 top-20 → 精排 → top-5。 |
| **C-04 EvidencePacket 结构与绑定规则** | ✅ **已实现**。结构：`relevant_chunks: list[Chunk]` / `synthesized_context: str`（LLM 合成，**200–500 字**）/ `citations: list[Citation]` / `query: str`（`core/schema.py:340-351`）。<br>`Citation` = `chunk_id` / `text_snippet`（**≤100 字**）/ `source_ref`（`schema.py:333-337`）。<br>**合成链路**：`query → hybrid_retrieve(k=20) → rerank(k=5) → synthesize(...) → evidence_packet`（`rag/evidence.py:10-16`）。<br>**双重回退**：LLM 异常 → 捕获；LLM 空返回 → `_fallback_synthesize()` 简单拼接（每 chunk 前 500 字、引用前 100 字）。<br>**绑定规则**：`EvidencePacket` 经 `TeachingNode.citation_refs` 与页面级 `page_bindings` 绑定到教学节点/页面，契约见 `文档/011-S2S3新功能接口契约-v1.0.md` 模块 1。 |
| **C-05 分层生成** | ✅ **已实现**。大纲层 `gen/outline.py`（输入 `intent + evidence_packet`，输出节点树，另支持 `revise()`）；内容层 `gen/node.py`（`generate_all`/`generate_enhanced`/`generate_single`）；样式层 `gen/export_ppt.py` + `gen/templates/` + `gen/skills/deck_swiss_edu/`。<br>**层间边界**：大纲层只产出 6 字段（`node_id`/`title`/`node_type`/`summary`/`key_points`≤4/`estimated_duration_minutes`），**明确不产出** `source_span`/`prerequisites`/`segments`/讲稿正文，交由后续管线（`outline.py:166`）。<br>**层间约束**：提示词硬约束「全节点时长之和应接近课程总时长 N 分钟」，产出后过 `normalize_duration_minutes` 并 `max(1, round(...))` 兜底（`outline.py:154-166`）。<br>**三层兜底**：`_fallback_scripts`/`_enhanced_fallback`/`_single_fallback`。 |
| **C-06 质量保障** | ✅ **已实现**。<br>**Schema 约束**：`core/schema.py`（732 行）Pydantic 模型 + `LLMIntentEngine.JSON_SCHEMA` 约束 LLM 输出；边界归一化 `normalize_generation_node_type()` 把兼容转换限制在边界而不放宽内部枚举。<br>**字段检查**：`gen/validator.py` `ContentValidator.validate()` → `ValidationResult`；`scale_ratio` 计算缩放比；`compute_scaled_font()` 缩字号；`paginate()` 超长分页，三种策略 `_paginate_by_segments`/`_paginate_by_paragraphs`/`_paginate_by_chars`。<br>**规则兜底**：见 C-07 的「逐项补齐」。 |
| **C-07 教学规范算法化** | ✅ **已实现**。<br>**课时分配**：大纲层提示词强制每节点 `estimated_duration_minutes`，且**全节点之和须接近总时长**；产出后归一化并 `max(1, round())`。<br>**节点类型识别**：`NodeType` 六类 `slide`/`section`/`quiz`/`interactive`/`cover`/`divider`。<br>**教学目标组织**：**三维目标** —— 知识目标 / 能力目标 / 素养目标（`gen/lesson_plan.py:26-32` 常量）。<br>**四阶段教学流程**：`lesson_plan.py:32` 定义标准四阶段，每阶段含「阶段 / 教师活动 / 学生活动 / 设计意图 / 时长」。<br>**核心策略（最有说服力的一点）**：`lesson_plan.py:396` 注释原文 —— 「标准四阶段必须齐全；模型阶段内容缺字段时**逐项补齐**，而不是整份降级」，即结构完整性由代码保证，模型只填内容。 |
| **C-08 版本分叉与断点续编** | ✅ **已实现**。`gen/version.py` `VersionManager`：`save_snapshot(parent_version)` / `list_versions` / `load_version` / `diff(v1,v2)`（按 `node_id` 比对）/ `revert_to()` / `lock_version`。<br>**数据模型关键设计**：`revert_to` 用 `deepcopy(target.nodes_snapshot)` 造**新版本**并记 `parent_version=目标版本` —— **回滚是克隆而非覆写，历史版本永不丢失，可形成版本分叉树**（`version.py:378-404`）。<br>**并发控制**：Redis 分布式锁，TTL **30 秒**、重试 **3 次**，无 Redis 时回退 `threading.Lock`（`version.py:60, 91-181`）。<br>**快照存储**：文件形式，位于 `_versions_dir(gen_id)`，元信息 `_versions_meta_path`。<br>**断点续编**：前端 `/courseware/create` → `CoursewareResumePage.vue`；切片级续编见 `gen/partial_content.py`。<br>**修改命令 7 类**（`schema.py:122-130`）：`update_node`/`swap_nodes`/`add_node`/`delete_node`/`change_template`/`merge_nodes`/`split_node`。 |
| **C-09 难点清单 3-5 个** | **部分（可归因，但需团队确认表述）**。以下 5 个难点均**从代码与实测报告中可证**，建议团队据此定稿：<br>**① 无 LLM 时链路仍须可跑** → 约束：早期集成无 API key、演示环境可能断网 → 解法：规则引擎与 LLM 双链路共用同一套规则（`rules.py` 头注释「避免两条链路行为漂移」）+ 检索自动退化纯 BM25 + 合成 `_fallback_synthesize` → 实测：P0-1 视频链路 **18/18 PASS**（全程零真实 LLM 调用）。<br>**② 模型输出不可控导致教案残缺** → 约束：一次模型失误不能毁掉整份教案 → 解法：**逐项补齐而非整份降级**（`lesson_plan.py:396`）→ 实测：`verify_lesson_plan 16/16 PASS`。<br>**③ 跨机器 ffmpeg/ffprobe 不可用导致抽帧静默为空** → 约束：imageio-ffmpeg 只带 ffmpeg 不带 ffprobe → 解法：新增 `_resolve_tool()` + 时长三级回退（ffprobe → `ffmpeg -i` stderr → 纯 Python 解析 MP4 moov/mvhd）→ 实测：**5 帧 @0/5/10/15/20s**，时长 25.0s（来源 `docs/P0-1-视频解析实测报告-20260831.md`）。<br>**④ WPS 渲染差异** → 约束：不能引入图片/SmartArt/真实透明度 → 解法：仅用文本框+自选图形+纯色填充，用**颜色混合 `_blend` 模拟半透明**规避 WPS 差异 → 实测：`verify_export_pptx 16/16`，`graphicFrame=0`，`a:ea ea=90`。<br>**⑤ 版本回滚会覆盖历史** → 约束：教师要能安全试错 → 解法：回滚=深拷贝造新版本（克隆而非覆写）+ Redis 分布式锁防并发写。<br>⚠️ **每条的「实测效果」目前只有断言通过率，无耗时/质量量化**，需补 D 组数据后定稿。 |

---

## D 组｜数据与验证

| 编号 | 回填 |
|---|---|
| **D-01 端到端跑通记录** | **部分**。有日期的端到端实测：`docs/P0-1-视频解析实测报告-20260831.md`（含 HTTP 端到端 `POST /api/v1/parse/video` → `status=done`）。其余链路最近一次完整跑通的时间与记录位置**待补**。 |
| **D-02 性能指标实测值** | **待补（最大缺口）**。现有报告**全部没有耗时数据**（唯一时间数字是测试脚本自身的执行时长，如 `pytest ... in 239.13s`、vitest `14.86s`，**不是业务指标**）。<br>需补：意图澄清轮数、各类型解析耗时、检索召回与响应、大纲/内容/样式分层生成耗时、首 Token 延迟、端到端总耗时。<br>**测试素材可直接复用**：`scripts/tmp_testvideo/test_video.mp4`（25 秒、1280×720、225,557 字节）。 |
| **D-03 质量指标** | **待补**。仓库内**无**生成准确率/完整性/可用性的评估方法、评估人、样本量与结果。<br>⚠️ 注意：`docs/联调验证/成员3-六节点一致性/验收报告.md` 明确声明其导出文件是**「标准六节点快照」且「不能冒充真实 LLM 产物」**，**不可**用作生成质量证据。 |
| **D-04 并发与稳定性** | **部分**。**降级策略有据**（见 C-03 检索退化、C-06 兜底、P0-1 显式降级路径验证 PASS）；**并发数、失败率、压测数据待补**。 |
| **D-05 测试用例数与缺陷** | **部分**。可核数据：<br>· Python：`pytest ai_engine/gen/tests/ -q` → **122 passed, 8 subtests passed**（P0-3/P1-4 两份报告一致，2026-08-31）<br>· Go 全量：**117 passed, 8 failed, 8 subtests passed**；排除 8 个 Windows 路径失败项后 **109 passed, 16 deselected**（`docs/联调验证/成员3-六节点一致性/验收报告.md`）<br>· 前端：**7 文件 / 52 用例全通过，14.86s**（P1-5，2026-08-31）<br>· 专项断言：`verify_export_pptx 16/16`、`verify_lesson_plan 16/16`、`verify_export_upload 21/21`、`verify_html5_export 33/33`、视频链路 **18/18**、WPS `TestPPTExporter 20 passed`<br>测试文件存量：Go 18 + Python 23 + 前端 11 = **52 个**。<br>**缺陷台账（发现/修复/遗留）待补**；已知遗留 8 个（Windows 硬编码 `/tmp`）。 |
| **D-06 优化前后对比** | **待补**。P1-4 报告显示 `verify_export_pptx` 从 **8 项基线 → 16 项断言**，属**断言覆盖扩展**，非性能优化对比。 |
| **D-07 全部数据的测试环境与口径** | **部分**。可核环境：<br>· WPS Office **12.1.0.28043**（实机）；PowerPoint Office16 `MainWindowHandle=0` **未验证**<br>· faster-whisper **1.2.1**、imageio-ffmpeg **0.6.0**、whisper base 离线模型（`model.bin` 145,217,532 字节）<br>· 前端构建 vite **7.3.1**，689 模块<br>· 操作系统 Windows（8 个失败项源于 Unix `/tmp` 硬编码）<br>· 统计时间：报告日期 2026-08-30 ~ 2026-08-31<br>其余项的样本量与统计时间**待补**。 |

---

## E 组｜页面与素材

| 编号 | 回填 |
|---|---|
| **E-01 关键页面截图** | **待补**。需实机截图。<br>页面清单已具备（`frontend/teacher/src/router/index.js`，9 个）：`LoginPage`、`MiddlePage`、`WorkspacePage`、`CoursewareResumePage`（断点续编）、`S1IntentPage`、`S2MaterialPage`、`S3StudioPage`、`S4VersionPage`、`AnalyticsPage`。<br>**已有可用的导出产物截图（非界面截图）**：`docs/联调验证/成员3-六节点一致性/slide-1.png` ~ `slide-6.png`、`docs/WPS-compat验证/wps_*.png`（cover/content/summary/two_column/render_montage）、`docs/WPS验证/*.png`。 |
| **E-02 每页分区构成** | **待补**。需逐页读 `.vue` 模板后按 P-04 写成分区文字，本次未做，**不臆测布局**。 |
| **E-03 现有架构图/流程图清单** | **部分**。仓库内**无 `.mmd`/`.drawio` 源文件**（根目录原 `diagram.mmd`/`diagram.svg` 描述的是**上一届泛雅架构**，已归档，**不可复用**）。<br>现有图文件均为**导出产物截图**（PNG）：见 E-01。<br>图形资产草稿在 `docs-selected/图系资产/`（**上一届，仅可作范式参考，不可引用内容**）。<br>**结论：本届的架构图/流程图需新画**，索取单第四节「必配图清单 G-01~G-09」目前**全部待产出**。 |

---

## F 组｜团队与过程

| 编号 | 回填 |
|---|---|
| **F-01 成员与模块** | **部分**。`记录/README.md` 显示分工为 **A - Go 后端 / B - Python AI 引擎 / C - Vue 前端** 三角色，另有**协调人**；每人有独立工作日志与看板。<br>**实际姓名、人数、到文件级的对应关系待补**（需团队确认）。 |
| **F-02 周期与里程碑** | **部分**。周期口径为 **git 提交历史**：首次提交 **2026-07-18**（`init`）→ 最新 **2026-09-23**（`ed75f3f`），共 **224 次提交**，覆盖 2026-07/08/09 **三个月**。<br>迭代轮次与里程碑节点**待补**（`文档/000-README.md` 提到 5 阶段，Phase 1-3 已完成、Phase 4 进行中，但该文档最后更新于 2026-09-23，需以团队口径为准）。 |
| **F-03 协作方式** | **部分**。有 `记录/` 三文件类型过程记录体系（工作日志 / 汇报 / 决策日志 / 看板），约定 `[任务ID]`、`@某人`、`⚠️`、`❓` 标记法；有 `.github/CODEOWNERS`。<br>**是否 Issue 驱动、例会机制、任务管理工具待补**。 |
| **F-04 真实会议记录** | **待补**。`记录/` 下**不存在独立会议纪要文件**，`记录/周报/` 仅有 `模板.md`。<br>现有最接近的实物：**2 份汇报**（`2026-08-27-PR整合与下一步行动.md`、`2026-08-28-成员3-PPT导出第二轮整改复盘.md`）+ **2 份决策日志**（D-001、D-002）。<br>**不会凭空生成会议纪要**；若附录需要，须团队提供真实记录。 |
| **F-05 真实教师试用/校企集成** | **待补**。仓库内**未见**任何教师试用、校企集成或试点的佐证材料。<br>赛题原文第 7 节提到「如果有具体的客户案例或经过客户实际场景测试…可以提供使用或试用说明文档」，**目前无**。 |

---

## G 组｜合规

| 编号 | 回填 |
|---|---|
| **G-01 第三方模型合规 + 资料版权** | **部分**。<br>· LLM：**千问（DashScope 兼容接口）**，默认模型 `qwen-turbo`（`ai_engine/core/config.py:41`），密钥经环境变量 `AI_API_KEY` 注入（`.env.example:18`）。多 provider 抽象详见 `ai_engine/core/llm.py`（801 行，**待细核**）。<br>· 密钥管理规范：`.env.example:11` 注明「真实 `AI_API_KEY` / `ANTHROPIC_AUTH_TOKEN` 等请只写入 `.env.local`（已被 `.gitignore` 忽略）」——**已有正确的密钥隔离约定**。<br>· ⚠️ **教学资料版权/授权确认逻辑：未检得**（搜 `授权`/`版权`/`copyright`/`consent` 无命中）。属**待补/待实现**。 |
| **G-02 权限隔离与未成年人数据** | **部分**。<br>· 认证实现：`backend/internal/handler/jwt_auth.go`；资源所有权通过 JWT 的 `owner_id` 过滤，使用方见 `backend/internal/handler/courseware_handler.go` 与 `ai.go`。<br>· 所有权语义（来源 `CONTEXT.md`）：非本人资源返回 **404**（而非 403），避免暴露资源存在性——**这是有意的安全设计**。<br>· 存储：MinIO 对象存储 + PostgreSQL。<br>· **未成年人/学生数据**：本项目 A12 面向**教师备课**，**不涉及学生数据**。仓库内命中的 `student`/`学生` 字样多来自**上一届泛雅项目残留**（面向学生），**不属本届功能**。<br>· MinIO 访问控制细节（bucket policy / 预签名 URL）**待核**。 |
| **G-03 开源组件与协议清单** | **部分**。⚠️ **关键风险：`PyMuPDF==1.27.1` 采用 AGPL-3.0（传染性协议）**，商业闭源分发需取得 Artifex 商业授权。PDF 解析就依赖它，**必须处理**。<br>其余直接依赖的常见协议（**待用 `node_modules/*/LICENSE` 与 `go.sum` 逐个复核后定稿**）：<br>· Apache-2.0：`echarts`、`minio`(py)、`openai`(py)、`paddleocr`、`sentence-transformers`<br>· MIT：`gin`、`vue`、`pinia`、`vue-router`、`mermaid`、`katex`、`markdown-it`、`@tiptap/*`、`fastapi`、`python-pptx`、`python-docx`、`faster-whisper`<br>· BSD：`go-redis/v8`(BSD-2)、`google/uuid`(BSD-3)、`uvicorn`(BSD-3)、`imageio-ffmpeg`(BSD-2)<br>· LGPL：`psycopg2-binary`（LGPL-3.0，含链接例外）<br>· `pgvector`(py) **待核对**<br>仓库自带 LICENSE 文件：**待核**。 |

---

## 回填状态汇总

| 组 | ✅ 已回填 | 🟡 部分回填 | ⛔ 待补 |
|---|---|---|---|
| A | — | A-06 | **A-02、A-03、A-04、A-05** |
| B | B-01、B-02、B-04、B-05 | — | **B-03** |
| C | C-01 ~ C-08 | C-09 | — |
| D | — | D-01、D-04、D-05、D-07 | **D-02、D-03、D-06** |
| E | — | E-03 | **E-01、E-02** |
| F | — | F-01、F-02、F-03 | **F-04、F-05** |
| G | — | G-01、G-02、G-03 | 各项细节 |

**必须由项目侧（而非本报告）提供的**：A-05 评分表、B-03 选型决策表、D-02/D-03 性能与质量数据、E-01/E-02 截图与页面分区、F-01/F-04/F-05 人员与真实记录、G 组细核结论。
