# 将 GIF 与视频媒体嵌入 PPTX

Status: ready-for-agent
Triage: ready-for-agent

## Goal

把课件生成的 GIF 或视频作为实际媒体嵌入 PPT 页面，保证下载的 PPTX 自包含且媒体可播放；HTML5 互动课件仍作为独立交付物。

## Acceptance Criteria

- 教师要求动画/视频时，生成结果可关联到目标页面与媒体资产；页面未要求媒体时不插入空占位。
- PPTX 中含媒体文件 part 和对应幻灯片关系/对象，下载的 PPTX 不依赖本机临时路径或网络外链。
- 媒体字节、格式或嵌入失败时导出不得报告完整成功，错误和部分可交付文件状态清楚。
- PPTX 导出质量闸门仍执行；媒体嵌入不会破坏普通页面、DOCX 或 HTML5 导出。
- HTML5 互动保持完整交互并可独立打开/导出；不声称其已作为可交互网页嵌入 PPT。

## Test Seam

使用已知 GIF 和小型视频 fixture 创建 PPTX，检查 ZIP 中媒体内容与 slide relationships；下载并使用支持的解析/播放冒烟检查内容。检查没有外链占位并覆盖媒体损坏失败路径。

## Existing Specs

- `.scratch/member-b-ai-engine/spec.md`：复用真实 HTML5 互动生成与独立导出。
- `.scratch/s3-pptx-export-quality/spec.md`：在既有 export API / status / artifact seam 中扩展媒体验收。
