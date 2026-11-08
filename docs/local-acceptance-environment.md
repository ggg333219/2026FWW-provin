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
