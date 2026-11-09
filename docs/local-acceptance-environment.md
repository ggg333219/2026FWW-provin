# 本地验收环境

## 工作区与服务

- 工作区：`C:\Users\27968\2026FWW-provin\tmp\acceptance-pr3-pr4-1107`
- 分支：`codex/s4-partial-reliability`
- Vue：15173
- Go：18081
- Python：18001
- Redis：`127.0.0.1:16379`
- PostgreSQL：`127.0.0.1:15432/teaching_s4_acceptance`
- MinIO：沿用当前本机验收环境

启动入口是 `scripts/start-all.ps1`。它按 `.env` 后 `.env.local` 的顺序加载配置；后者优先覆盖继承环境变量。Python 以工作区为当前目录启动，Go 使用该工作区构建的 `teacher-s4.exe`。

## LLM 本地配置

在工作区根目录创建或编辑被 Git 忽略的 `.env.local`，填写：

```text
AI_BASE_URL=https://api.siliconflow.cn/v1
AI_MODEL=deepseek-ai/DeepSeek-V4-Flash
AI_GEN_MODE=llm
AI_API_KEY=<本机自行填写>
```

不要把 Key 写入脚本、命令行参数、日志或 Git。切换服务或分支前确认使用的是同一工作区的 `.env.local`，并先检查 `/health` 的 provider、model、mode 和 `configured`。

## 数据安全

验收数据库为历史数据库的专用副本，不是原始 `teaching` 库。不要执行 `DROP`、`TRUNCATE` 或重置操作。Redis 中的旧任务也不要仅凭状态字段清理。

本次验收备份：

`C:\Users\27968\2026FWW-provin\backups\teaching-s4-acceptance-20261108-130906\teaching_s4_acceptance.dump`

SHA-256：

`6ADF95F7CD689F0834D458C608062BD2346B9EA2F6E8B7184EF7B1242898BA11`

文件大小约 2.0 MB，已使用容器内 `pg_restore --list` 读取，归档包含 297 个条目。另一个早期主机重定向文件未通过归档校验，不应使用。

## 换 Agent 注意事项

1. 先确认工作区、分支、HEAD 和端口对应进程，禁止检查 Desktop 下的同名副本。
2. 先确认 PostgreSQL 数据库名和数据量，再启动 Go。
3. 不要输出或读取 API Key 内容；只报告是否存在及 `/health` 的脱敏状态。
4. 不操作 Chrome、不调用真实模型，除非用户明确进行验收并授权。
5. 不提交 `.env.local`、`logs/` 或数据库备份。

## A12 首次讲稿与 S2 验收归档（2026-11-09）

### 集成基线

- 主线：`submission-package-1009`
- 验收/集成前代码 SHA：`187af8ac2e62e84f96df35620f2ece7f8cab4e77`
- PR #14、PR #15 已通过主线合并提交包含；未重复 cherry-pick。
- 本次新增前端修复及部署配置修复在独立集成分支上验证。

### 本轮代码修复

- `frontend/teacher/src/components/teacher/S2MaterialWorkspace.vue`
  - 返回 S2 时使用 `preserveSessionMaterials`，保留同 session 的本地解析素材和真实 Chunk；切换 session 时仍清空旧素材。
- `frontend/teacher/src/stores/materialStore.js`
  - `knowledge/upload` 返回 `chunk_count <= 0` 时报告索引失败，不伪装成成功。
- `frontend/teacher/src/utils/s2E2E.test.js`
  - 覆盖页面切换后的 Chunk 保留、session 隔离和空索引结果。
- `deploy/docker-compose.server.yml`
  - Go 与 Python 共享专用 named volume `s2-parse-data`，挂载到 `/tmp/fuww_s2_parse`，并统一设置 `S2_PARSE_DIR`。
- 隔离验收专用 `docker-compose.browser-acceptance.yml` 未纳入提交。

### 证据等级

| 验收项 | 结果 | 证据等级 |
|---|---|---|
| S2 真实 TXT 上传、解析 | 通过 | 人工浏览器 |
| 解析 Chunk 展示 | 通过 | 人工浏览器 |
| S2 → S3 → S2 状态恢复 | 通过 | 人工浏览器 |
| 知识库索引非空 | 通过 | 人工浏览器 |
| RAG 证据包非空 | 通过 | 人工浏览器 |
| 原始 Chunk 来源追踪 | 通过 | 人工浏览器 |
| S3 大纲请求携带 EvidencePacket | 通过 | 人工浏览器 |
| `/gen/content` 请求携带真实资料 | 通过 | 人工浏览器 |
| `/gen/content` 返回 `content_id` | 通过 | 人工浏览器 |
| PR #14 节点讲稿 Prompt 资料注入 | 通过 | 独立 Python 模型桩 |
| PR #15 意图与参考资料分离 | 通过 | 独立 Python 模型桩 |
| 整合环境真实 LLM 讲稿生成 | 未验证 | 本轮未执行 |
| 完整课件生成和导出 | 未验证 | 本轮未执行 |
| 浏览器刷新、容器重启后的恢复 | 未验证 | 本轮未执行 |
| B1/B2/B3 | 未修复 | 不在本轮范围 |

### 定向验证命令

在隔离教师端工作区执行：

```powershell
npm run test:unit -- --run src/utils/s2E2E.test.js
npm run build
```

结果：`23 passed, 0 failed`；前端生产构建成功。

独立 Prompt 模型桩验证使用隔离 AI Engine 容器内 Python 进程执行，覆盖有资料/无资料两组：

```powershell
docker exec browser-acceptance-1109-ai-engine-1 python -c "独立模型桩 Prompt 断言脚本"
```

结果：节点讲稿 Prompt 和教学规划 Prompt 的两组对照断言全部通过；该结果不等同于真实浏览器端到端 Prompt 验收。

### 未覆盖风险

- 真实 LLM 生成质量、完整课件生成与导出未验证。
- 浏览器刷新或 Go/Python/Redis 重启后的跨进程恢复未验证。
- 正式部署 Compose 的共享解析 volume 已补齐，但未在生产数据卷上执行启动或迁移。
