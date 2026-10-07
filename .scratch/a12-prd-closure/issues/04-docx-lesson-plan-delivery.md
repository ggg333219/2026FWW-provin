# Word 教案内容与导出完成状态

Status: ready-for-human
Triage: ready-for-human

## Goal

确保 Word 教案包含完整教学板块、突出显示新增板块，并让异步 DOCX 导出有可靠终态和可下载产物。

## Acceptance Criteria

- DOCX 包含教学目标、教学过程、教学方法、课堂活动设计、课后作业。
- 教学方法、课堂活动设计、课后作业均有实际生成内容，标题加粗并以醒目大字号呈现（目标字号 14 pt）。
- 导出任务对模型、转换、存储和状态更新失败均能进入可见的失败终态；成功时返回正确版本的下载链接。
- 前端轮询成功、失败、超时和重试时保留错误诊断并避免无限显示“导出中”。
- 导出中的 DOCX 与用户选定的课件版本一致；其他格式已有文件不因 DOCX 失败而丢失。

## Test Seam

提交版本化 DOCX 导出请求，轮询到终态并下载文件；解析 DOCX 包检查板块文本、标题样式和版本关联；注入生成/存储失败验证失败终态。

## Existing Specs

- `.scratch/s3-pptx-export-quality/spec.md` 只适用于 PPTX 质量检查；本 issue 负责 DOCX 内容和状态，不扩大其范围。

## Comments

- 2026-10-07: 实施提交 `e439fd8` 补齐标准教案生成、生成指令集/已确认资料消费、版本化导出及 14pt 加粗新增板块标题。`ai_engine/tests/test_lesson_plan_export.py` 下载实际 DOCX 并验证五个板块、目标对象、选定版本和标题样式；对应 Go/前端回归测试也通过。
- 人工验收仍待完成：用 Word/LibreOffice 对导出 DOCX 做页面视觉检查；对模型/转换/存储失败注入并确认导出任务失败终态与重试体验。
