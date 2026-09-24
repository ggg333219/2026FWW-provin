# 归档索引

> 整理日期：2026-09-24
> 整理范围：仓库根目录 + `文档/` 下的历史文档
> 原则：**只归档、不销毁** —— 全部走 `git mv`，历史版本的完整内容仍可从 git log 取回

## 为什么要分这四类

本项目仓库同时承载**两场比赛**的材料（上一场：泛雅 AI 互动智课 · 国赛；
本场：锐捷 A12 多模态 AI 互动式教学智能体 · 省赛）。
两套材料混在同一目录会导致事实污染——把上一场的数字、架构、话术写进本场方案书。
本次整理的第一目标就是**划清这条边界**。

---

## 上一场比赛-泛雅国赛/

上一场（泛雅平台 AI 互动智课生成与智慧问答）的答辩与架构材料。
**保留原因**：本场方案书的写作范式（P-01 三位一体、P-02 亮点二段式等 12 条）
正是从上一场成稿《项目详细方案(5).docx》提炼的，这批材料是范式来源。
**不用于**本场方案书的任何事实引用。

| 文件 | 原位置 | 内容 |
|---|---|---|
| `答辩稿.txt` / `答辩稿_PPT顺序版.txt` | 根目录 | 上一场答辩讲稿 |
| `关于架构的理解.txt` / `企业级架构的设计.txt` | 根目录 | 上一场架构叙述 |
| `痛点划分梳理方式抉择依据.txt` / `问题描述.txt` / `评审内容.txt` | 根目录 | 上一场需求与评审材料 |
| `ppt内容.txt` | 根目录 | 上一场项目展示报告正文（泛雅AI互动智课系统） |
| `启示.md` | 根目录 | 与项目无关（赛事占卜内容），一并归档免误读 |

> 上一场更完整的一批材料（评委备查手册全 10 册、国赛答辩演讲稿多版本、
> `项目详细方案(5).md` 等）在 `docs-selected/`，该目录**已被 `.gitignore` 忽略**，
> 属于本机范式素材库，不在本次归档范围内。

## 已废任务包与历史方案/

已被后续契约替代、或方向已废弃的项目文档。**保留原因**：记录了当时的决策依据，
答辩若被问"为什么改方案"可回溯。

| 文件 | 原位置 | 作废依据 |
|---|---|---|
| `008/009/010-任务包-*-页面级资料绑定.md` | `文档/` | `文档/000-README.md` 已标注**已废**，字段/错误码/信封被 `011-S1S3新功能接口契约-v1.0.md` 全面覆盖 |
| `S1-S4-数据透传方案/`（全 10 篇） | `文档/` | 2026-08-17 的旧方案，S1→S4 透传设计已被契约 v1.0 与四层确认门替代 |
| `当前阶段问题与任务/`（全 9 篇） | `文档/` | 2026-08-26 的问题清单，绝大多数已闭环 |
| `教师端前端重构方案/`（全 9 篇） | `文档/` | 2026-08-09 的重构计划，已完成并被 `docs/design/skills/S2-S3-redesign-*.md` 取代 |
| `diagram.mmd` / `diagram.svg` | 根目录 | 描述**上一场泛雅架构**（"泛雅平台(宿主)"、`ai-vue-frontend`），与本场架构不符 |
| `README.AI.md` | 根目录 | 与 `AGENTS.md` **字节完全相同**（md5 `8a2be1ec…`），保留被工具引用的 `AGENTS.md` 即可 |

> `文档/005-接口契约手册.md` **未归档** —— 虽标注"旧版，参考"，
> 但被 `001`/`002`/`003` 多处引用，移动会断链。

## Dify-历史/

Dify 低代码编排时代的全部产物，已被自研 `ai_engine/` 取代。

| 文件 | 内容 |
|---|---|
| `dify/` | Dify 工作流定义（7 个 workflow）、plugin_daemon、qdrant 数据、`DIFY交接文档.md` |
| `CONFLICT_RESOLUTION_GUIDE.md` / `TASK_COMPLETION_CHECKLIST.md` | 2026-04-04 的 Dify 集成冲突解决记录 |
| `test-dify-integration.ps1` | Dify 联调脚本 |

> ⚠️ **安全项**：`归档/Dify-历史/dify/storage/privkeys/*/private.pem` 是一把**被 git 跟踪的私钥**。
> 本次只做了移动、未做清除——它仍留在 git 历史中。
> 若该目录属于废弃的 Dify 实例，建议后续用 `git filter-repo` 从历史中彻底移除并作废该密钥。

## 过程脚本与冒烟产物/

散落在根目录的一次性调试脚本与冒烟输出，零文档价值。

| 文件 | 说明 |
|---|---|
| `check_generate.py` / `ai_engine_test.py` / `backend_test.py` / `test_*.py`（6 个） | 根目录临时联调脚本，正式测试在 `backend/**/*_test.go`、`ai_engine/tests/`、`frontend/teacher/src/**/*.test.js` |
| `smoke_test_results.json` / `smoke_p0_engine_direct.txt` / `smoke_p0_gateway_results.txt` / `validate_audio_response.json` | 冒烟测试输出快照 |
| `计划参考.md` / `执行计划.md` / `探查现状.md` | **AI 会话记录被误存为文档**（含 `Copy code to clipboard`、`⏹ Interrupted`、`plan-mode-exit` 等会话标记，分别命中 85/85/7 处）。不是项目文档，其中 `执行计划.md` 还是 `计划参考.md` 的错乱重排副本 |
| `vite.config.js` | 根目录stray，真身在 `frontend/teacher/` |

## 根目录历史残留/

根目录的 stray 代码文件，真身均在子目录中，无任何项目代码引用（已逐个 grep 确认）。

| 文件 | 真身位置 |
|---|---|
| `go.mod` / `go.sum`（module `fw_workspace`） | `backend/go.mod`（module `smart-teaching-backend`） |
| `main.py`（旧 FastAPI 桩） | `ai_engine/main.py` |
| `index.html` | `frontend/teacher/index.html` |
| `package.json` / `package-lock.json` | `frontend/teacher/package.json` |
| `requirements.txt` | `ai_engine/requirements.txt` |
| `payload.json` | 临时请求体（`{"pageNum":1,"question":"请用教学口吻解释牛顿第一定律"}`） |

## 工具与设计参考/

| 文件 | 说明 |
|---|---|
| `huashu-design.skill.md` | 第三方技能定义（author: alchaincyf, v2.1.0），非本项目文档，且未注册到 `.claude/skills/` 或 `.agents/skills/` |
| `ppt设计哲学参考.md` | 豆包对话导出（含 `doubao.com/thread/...` 链接），属原始素材非成稿 |

---

## 本次直接删除（无归档）

| 文件 | 理由 |
|---|---|
| `版本：v2.0（精简主干版）` (0 B) | 空文件，疑似 shell 重定向误操作产生的文件名 |
| `目标：唯一——打通` (0 B) | 同上 |
| `日期：2026-08-27` (0 B) | 同上 |
| `2026-07-20-203817-httpsgithubcom…txt` (143 KB) | AI 会话全文导出，零文档价值，且**历史会话有夹带密钥的风险**（`.gitignore` 已为同类文件设防） |
| `2026-08-30-150440-this-session-is-being-continued-…txt` (144 KB) | 同上，且已被 `.gitignore` 忽略（未跟踪） |
| `mmdc_error.log` / `mmdc_exit_code.txt` | Mermaid CLI 渲染失败日志 |
| `exported_image.png` (520 KB) | 一次导出的残留图 |

## 未归档（当前有效，保留原位）

- `文档/000-README.md`、`001-分工方案`、`002/003/004-任务包`、`005-接口契约手册`、`006-进度与里程碑`、`007-任务分配`、`011-契约v1.0`、`A12赛题`、`S3数据与接口规范`
- `docs/` 全部验证报告（`P0-*`、`P1-*`、`M1-4*`、`M3-*`、`WPS*`、`联调验证/`、`导出验证/`、`预览验证/`）—— 这些是方案书**测试验证章的证据材料**
- `docs/adr/`、`docs/design/skills/`、`docs/knowledge/`
- `记录/` 全部（工作日志/汇报/看板/决策日志/归档）—— 方案书**附录会议纪要**的素材
- `AGENTS.md`、`CONTEXT.md`、`README.md`、`设计主旨.md`
- `docker-compose.yml` / `docker-compose.test.yml` / `Dockerfile` / `.env*.example`（基础设施配置，README 有引用）
- `会议讲稿.md`（已被 `.gitignore` 忽略）
