# 项目草稿隔离与教师端清理

Status: ready-for-agent
Triage: ready-for-agent

## Goal

确保草稿恢复按课件项目隔离，并完成 PRD 指定的登录文案和早期 HTML5 mock 清理。

## Acceptance Criteria

- 新建项目、继续编辑和切换项目时只读写当前 `project_id` 草稿；缺少项目身份时不得回退读取其他项目的全局草稿。
- 刷新页面和重新登录后的恢复结果与服务端项目草稿一致，旧全局 key 不会覆盖新项目状态。
- 登录界面不再出现泛雅旧产品身份文案。
- 删除早期蓝色 mock HTML5 预览；真实 HTML5 互动资产仍可预览和独立导出。
- 不清理学生端或其他未列入本 issue 的旧代码。

## Test Seam

教师端项目切换 Store/组件测试覆盖保存、恢复和旧 key 隔离；浏览器测试在两个项目间往返并刷新，检查草稿没有串用；真实互动资产预览回归通过。

## Existing Specs

- `.scratch/s3-gap-completion/spec.md`：复用项目草稿持久化合同。
- `.scratch/member-b-ai-engine/spec.md`：复用真实 HTML5 预览，不把 mock 清理扩大成互动生成重做。
