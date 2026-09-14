---
status: accepted
---

# 课件项目作为后端持久化主对象

成员 A 的 Go 后端以 `courseware_projects` 作为教师课件编辑闭环的持久化主对象，统一保存项目归属、当前步骤、整体草稿快照和最近一次成功的 `generation_id`。对外采用 `/api/v1/coursewares` 项目接口，所有权从 JWT 推导并以 `404` 隐藏他人项目；草稿采用最后写入生效的整体快照，生成成功后才回填关联结果。这样可以让刷新、重启和“继续编辑”恢复同一份课件上下文，同时保持异步 `task_id` 与业务对象 ID 的边界清晰。

## Consequences

- 新建、草稿、步骤和生成关联都围绕 `project_id` 组织。
- 新增正式 SQL migration，并保留旧接口兼容层。
- 导出统一走 `/api/v1/generations/{generation_id}/exports` 与 `/api/v1/exports/{export_job_id}`；旧导出路由转发到新逻辑。
- 归档项目禁止继续写入，但保留查询和历史版本导出能力。
