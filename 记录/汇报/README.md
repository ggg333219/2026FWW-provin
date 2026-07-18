# 汇报 / 模板

> 每个独立任务做完了填。填完存 `记录/汇报/P{阶段}-{任务编号}-{简短标题}.md`。
> 核心目的：**说清楚谁干了什么、干成什么样、改了哪些东西、跟谁有关、下一步谁接**。

---

## 模板

```yaml
---
# ── 基础 ──
task_id:                # 如 P3-A1、B2
title:                  # 中文标题，如"死代码清理"
author:                 # 填表人
date:                   # 完成日期
status:                 # completed | partial | blocked | failed

# ── 内容 ──
summary: >              # 一句话说清楚——给下一个人看的
  做了什么、结果怎样
changes:                # 改了哪些文件（列表，路径即可 / 路径 — 说明）
  # created: ...
  # modified: ...
  # deleted: ...

# ── 衔接 ──
affects:                # 影响谁？A | B | C | AB | BC | ABC | 无
next: >                 # 下一步谁接？从哪里开始？注意什么？
  接替指引、重点关注事项
---
```

### 如果需要补充（选填）

模板的 `---` 下面可以自由写正文，不限格式。常见情况：

- **completed**：详细过程、关键决策、踩坑记录
- **blocked / failed**：卡在哪、需要什么支持

---

## 例子一：正常完成

```yaml
---
task_id: P3-A1
title: 死代码清理
author: 同学 A
date: 2026-07-18
status: completed
summary: >
  删除 backend 中 3 个已确认为死代码的目录（共 8 个 stub 文件）
  和 9 个测试工作流文件，清理后 go build ./... 全部通过
changes:
  deleted:
    - backend/internal/handlers/ — 2 个空桩 handler
    - backend/internal/services/ — 2 个空桩 service
    - backend/internal/models/ — 3 个无引用 struct
    - backend/test_workflow_*.go — 9 个测试工作流文件
affects: A
next: >
  接 A2：拆分 compat_student.go（2260 行）。
  建议先跑一次 go test ./... 确认基线再动手。
---

删之前逐个确认了无引用，没有踩坑。每个 commit 都能 git revert。
```

## 例子二：被阻塞

```yaml
---
task_id: P3-A5
title: 会话管理模块
author: 同学 A
date: 2026-07-20
status: blocked
summary: >
  会话管理模块写了一半，卡在 AI Engine 接口还没发布，无法联调
changes:
  created:
    - backend/internal/handler/conversation_handler.go
    - backend/internal/service/conversation_service.go
  modified:
    - backend/internal/service/models.go — 加了 status、turn_type 字段
build: PASS
affects: AB
next: >
  等 B2（LLM 统一封装）完成后继续 A5。
  联调前需要和 B 同学对齐接口字段名，接口定义在 005-接口契约手册.md。
---
```

## 例子三：大跨度综合汇报（跨阶段总结，多人看）

适合给"我这一大轮做了什么"的整体复盘，发给所有人：

```yaml
---
task_id: P1-P2
title: 项目现状分析与架构设计方案产出
author: 协调人
date: 2026-07-18
status: completed
summary: >
  完成全项目扫描、4 Skill + KB 架构设计、3 人分工方案、
  接口契约手册、README.AI 启动说明书、仓库迁移。
  项目已具备三队友并行开发条件
changes:
  created:
    - 文档/000-README.md ~ 006（6 份方案文档）
    - README.AI.md（835 行启动说明书）
    - docs/design/skills/（7 份架构设计文档）
    - 记录/（汇报模板、进度看板、决策日志、周报模板）
  deleted:
    - 文档/00_项目文件要求.txt ~ AI Engine能力清单.md（7 份过期文档）
affects: ABC
next: >
  三位队友分别从 A1/B1/C1 开始，每个人做之前先读 文档/001-分工方案-总览.md。
  A 和 B 联调前必须一起过一遍 005-接口契约手册.md。
---

## 我们做了什么

### Phase 1：项目现状分析
- 扫描全项目结构：Go 64 文件 / 18,470 行；Python 17 文件 / 3,966 行；Vue 49 文件 / 33,391 行
- 定位 3 个 God Object（compat_student.go 2260 行、teacher.go 1798 行等）
- 识别 3 个空桩目录 + 9 个测试工作流文件（已清理）

### Phase 2：架构设计
- 将系统划分为 4 Skill + KB 架构（S1 意图理解 → S2 多模态交互 → KB 知识库 → S3 课件生成 → S4 个性化满足）
- 输出 6 份任务方案文档 + 接口契约手册 + README.AI.md

### 关键决策
- **D-001**：4 Skill + KB 架构划分，取代平铺式结构
- **D-002**：pgvector 而非专用向量数据库（省部署成本）
- **D-003**：接口即契约，改接口先改文档
```
