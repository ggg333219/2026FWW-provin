---
# ── 基础信息 ──
phase: 2
task: P1-P2
title: 项目现状分析与架构设计方案产出
author: 协调人 (claude-code)
date: 2026-07-18

# ── 状态 ──
status: completed
summary: >
  完成 Phase 1 项目扫描 + Phase 2 架构设计，输出 6 份方案文档 +
  README.AI.md 启动说明书 + 仓库迁移与清理。项目已具备交予 3 位队友
  并行开发的条件。

# ── 改动清单 ──
files_created:
  - 文档/000-README.md — 项目总览入口
  - 文档/001-分工方案-总览.md — 3 人分工 + 协作规则
  - 文档/002-任务包-Go后端-A.md — 同学 A 任务包（8 项）
  - 文档/003-任务包-PythonAI引擎-B.md — 同学 B 任务包（14 项）
  - 文档/004-任务包-Vue前端-C.md — 同学 C 任务包（8 项）
  - 文档/005-接口契约手册.md — 跨层 API 定义 + 数据模型
  - 文档/006-进度与里程碑.md — 当前进度 + 里程碑
  - 文档/ (deleted) — 删除了 7 份过期的 Phase 1 旧文档，内容合并到保留文档
  - README.AI.md — AI 启动说明书（835 行，7 章 + 3 附录）
  - docs/design/skills/ — 7 份架构设计文档（架构总览 + 4 Skill + KB + 目录重构）
  - 记录/汇报/README.md — 汇报模板
  - 记录/README.md — 记录目录索引（更新）
  - 记录/进度跟踪/README.md — 进度看板（更新）

files_modified:
  - 文档/000-README.md — 合并了新旧对比表和 7 层架构图
  - 文档/001-分工方案-总览.md — 合并了模块职责映射表
  - 文档/002-任务包-Go后端-A.md — 合并了 19 张数据表清单 + 迁移策略
  - 文档/003-任务包-PythonAI引擎-B.md — 合并了能力评估表和已知 bug
  - 文档/005-接口契约手册.md — 合并了资料上传接口和 Agent↔Tool 协议

files_deleted:
  - 文档/00_项目文件要求.txt
  - 文档/01_需求差异分析.md
  - 文档/02_系统架构.md
  - 文档/03_模块设计.md
  - 文档/04_API接口.md
  - 文档/05_数据库设计.md
  - 文档/AI Engine能力清单.md
  - 文档/各部分审核.md

# ── 验证结果 ──
build: SKIP
tests_pass: 0
tests_fail: 0
tests_skip: 0
coverage: null

# ── 依赖关系 ──
blocks:
  - A1: 死代码清理
  - B1: AI Engine 目录重组
  - C1: 清理孤儿目录 + 路由框架
next: "进入 Phase 3，3 位队友并行推进各自任务包"
next_ref: "文档/001-分工方案-总览.md"

# ── 同步信息 ──
affects_B: true
affects_C: true
breaking_change: false
review_needed: false
review_note: ""

# ── 后续指引 ──
handoff: >
  A/B/C 三位队友参考 文档/001-分工方案-总览.md 直接开始 Phase 3 即可。
  建议每人先看 文档/005-接口契约手册.md 了解跨层接口再动手。
  README.AI.md（835 行启动说明书）已放到项目根目录，拖进 AI 可以快速上手。
---

## 一、我们做了什么

### Phase 1：项目现状分析

| 工作项 | 说明 |
|--------|------|
| 项目结构扫描 | Go 64 文件 / 18,470 行；Python 17 文件 / 3,966 行；Vue 49 文件 / 33,391 行 |
| 需求差异分析 | 旧系统（讲授型）→ 新系统（智能体共创型）6 大差距 |
| 代码健康报告 | 识别 3 个 God Object（compat_student.go 2260 行 / teacher.go 1798 行 / platform_sync_support.go 2033 行）|
| 死代码识别 | 3 个空桩目录（handlers / services / models）+ 9 个测试工作流文件 |

### Phase 2：4 Skill + 知识库架构设计

| 工作项 | 产出路径 |
|--------|---------|
| 架构总览 | docs/design/skills/architecture-overview.md |
| S1 意图理解 | docs/design/skills/S1-intent-understanding.md |
| S2 多模态交互 | docs/design/skills/S2-multimodal-interaction.md |
| S3 课件生成 | docs/design/skills/S3-courseware-generation.md |
| S4 个性化满足 | docs/design/skills/S4-personalization.md |
| KB 知识库 RAG | docs/design/skills/KB-knowledge-base.md |
| 目录重构计划 | docs/design/skills/directory-restructure-plan.md |

### 方案文档输出

| 文件 | 核心内容 |
|------|---------|
| 文档/000-README.md | 项目定位、技术栈、一句话理解 7 层架构 |
| 文档/001-分工方案-总览.md | 3 层分工、10 模块职责映射、3 周冲刺节奏 |
| 文档/002-任务包-Go后端-A.md | 8 项任务 + 19 张表 + 迁移策略 |
| 文档/003-任务包-PythonAI引擎-B.md | 14 项任务 + 能力评估表 + 已知 bug |
| 文档/004-任务包-Vue前端-C.md | 8 项任务 + mock 优先策略 |
| 文档/005-接口契约手册.md | S1-S4 + KB 全部接口 + 6 数据模型 + 4 状态机 |
| 文档/006-进度与里程碑.md | 当前进度 + 里程碑 + 验收标准 + 风险矩阵 |
| README.AI.md | 30KB / 835 行，拖进 AI 工具即可启动 |

### 仓库整理

- 清理死代码：删除 3 个空桩目录、9 个测试工作流、临时文件
- 清理大文件：删除 PPTX/DOCX/ZIP/EXE/WAV，仓库从 341MB → 26MB（源文件部分）
- 文档整理：删除 7 份过期 Phase 1 文档，内容合并到保留文档
- 完整迁移到 D:\Desktop\2026FWW-provin（637 文件，仅含源代码 + md 文档）

## 二、关键决策

### D-001：4 Skill + KB 架构划分

将系统按业务能力划分为 5 个模块，取代原来的平铺式结构：
- **S1 意图理解**：对话式需求采集 → 结构化意图
- **S2 多模态交互**：资料上传 → 多格式解析 → 统一分块
- **KB 知识库**：分块 → 向量化 → 混合检索 → 证据融合
- **S3 课件生成**：大纲 → 节点 → PPT/DOCX 导出
- **S4 个性化满足**：预览 → 修改 → 版本管理 → 锁定 / 导出

### D-002：pgvector 而非专用向量数据库

不改 PostgreSQL 体系，直接用 pgvector 扩展。省掉 Milvus/Qdrant 部署成本。

### D-003：接口即契约

A ↔ B 之间通过 HTTP REST 对接，接口格式统一写在 005-接口契约手册.md 中，改接口必须先改文档。

## 三、队友启动指引

| 队友 | 先看什么 | 然后做什么 |
|------|---------|-----------|
| 同学 A | 文档/002-任务包-Go后端-A.md | A1 死代码清理 → A2 compat_student.go 拆分 |
| 同学 B | 文档/003-任务包-PythonAI引擎-B.md | B1 目录重组 → B2 LLM 统一封装 |
| 同学 C | 文档/004-任务包-Vue前端-C.md | C1 清理 → C2 路由 → C3 对话视图 |

A 和 B 开始联调前必须一起看 `文档/005-接口契约手册.md`。

## 四、后续建议

1. **A/B/C 按分工启动**：每人按分工方案先做自己任务包里的前置任务（A1/B1/C1），做完后再看是否需要和其他人联调
2. **接口契约前置阅读**：A 和 B 开始联调前必须一起看 `文档/005-接口契约手册.md`，确认请求/响应格式
3. **README.AI.md 各人验证**：项目根目录的 README.AI.md（835 行）为 AI 工具准备，建议每人拖进自己的 AI 试一下，看能否正确理解整个项目
4. **测试基线**：代码整理后还没跑全量测试，建议队友开始自己任务前先跑一次确认基线
