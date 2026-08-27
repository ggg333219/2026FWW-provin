# 教学 PPT 模板体系

稳定模板 ID：`default`（通用）、`academic`（学术）、`minimal`（简约）。历史 ID
`compact`、`widescreen` 分别兼容映射到 `minimal`、`default`。

页面版式由 `export_ppt.py` 自动选择：

| 标准/兼容页面类型 | 自动版式 |
|---|---|
| `cover`, `title` | 封面 |
| `agenda`, `toc`, `directory` | 目录 |
| `section`, `divider`, `chapter` | 章节分隔 |
| `slide`, `content` | 内容/讲授分段自适应 |
| `two_column` | 固定双栏：左侧核心要点，右侧讲授分段/内容展开 |
| `quiz`, `interactive`, `question` | 课堂互动 |
| `summary`, `conclusion`, `recap` | 总结 |

导出器优先读取 `node_type`，为空时回退 `type`。要点会合并
`key_points` 与 `core_points`；讲授分段读取 `segments` 中的类型、文本与预估时长。

运行 `python -m ai_engine.gen.templates.build_templates` 可重建三份五版式 PPTX 样例。
所有版式均由原生 PowerPoint 文本框和形状组成，不使用整页图片。
