# 瑞士教育风预览与 PPTX 实现

Status: ready-for-agent
Triage: ready-for-agent

## Goal

在现有页面规格、预览渲染和 PPTX 导出共享链路上，使瑞士教育风成为真实版式主题，而不只是调色板变化。

## Acceptance Criteria

- 主题选择 ID 从教师端贯通到 AI Engine 的页面规格和 PPTX 导出请求。
- 主题设计参数包含直角、细线、字体声明、字号层级和配色；克莱因蓝使用已确认的主题值，避免 UI 与技能定义不一致。
- 实现被产品选定的核心教学布局，并确保不支持布局有明确回退而非空白。
- 预览和 PPTX 导出使用同一页面规格与主题参数；HTML 截图嵌入不作为并行实现路线。
- 导出的 PPTX 可打开、页面结构有效，并与 HTML/SVG 预览在代表性页面上一致。
- 不依赖不可用的 `pptygen` 空壳渲染路径；清理该路径的范围需以无调用引用证据为前提。

## Test Seam

对同一组代表性封面、概念、三卡、对比、时间轴、章节页和结语内容生成预览与 PPTX；检查主题参数贯通、页面可读和导出文件结构，并做视觉对照。

## Dependencies

- 依赖 issue 03 中页面密度与共享页面规格契约。
- 依赖既有 `.scratch/s3-pptx-export-quality/spec.md` 导出质量门禁。
