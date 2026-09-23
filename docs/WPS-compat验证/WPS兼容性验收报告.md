# PPT 导出兼容性验收报告

验收日期：2026-08-28  
验收对象：`wps_compat_test.pptx`  
导出链路：`PPTExporter`（python-pptx）→ OOXML `.pptx`

## 1. 验收结论

本轮生成的 7 页全版式测试稿已在 WPS Office 12.1.0.28043 中真实打开并逐页抽查，未出现文件损坏提示、字体缺失、中文标点丢失、文本越界或形状错位。封面、内容/讲授分段、真双栏、总结四类关键页面均保留原生文本框和形状，可继续编辑。

Microsoft PowerPoint Office16 已被启动，但当前桌面控制环境未暴露可交互的主文档窗口（进程 `Responding=True`、`MainWindowHandle=0`），因此本报告不将其记为已完成的 Office 实机验收。该项保留为后续人工交叉复核，不影响已经完成的 WPS 与 OOXML 结构验收。

## 2. 测试覆盖

测试稿包含 cover、agenda、section、content、two_column、quiz、summary 共 7 类页面。其中 content 验证正文与 `segments` 同源展示，two_column 验证左栏核心要点、右栏讲授分段的独立语义布局。

测试文本包含中文顿号、引号、分号、复杂度表达式和分钟/秒时长，以覆盖常见中文教学内容。

## 3. 自动化与结构检查

- `TestPPTExporter`：20 passed，3 subtests passed；
- python-pptx 二次读取：7 slides；
- 图片形状：0，确认不是整页截图伪导出；
- 原生文本形状：73；
- 三套模板 `default / academic / minimal` 已使用同一构建脚本重新生成；
- 7 页渲染图全部生成，人工逐页检查未发现溢出或遮挡。

Windows 下的 `render_slides.py` / `slides_test.py` 在成功产出全部页面 PNG 后仍返回非零状态，属于辅助器状态判断异常；本轮以实际生成的 7 张 PNG、逐页视觉复核和 WPS 实机打开结果交叉确认，不把该辅助器异常计为 PPTX 导出失败。

## 4. WPS 实机抽查结果

| 页面 | 检查点 | 结果 | 证据 |
|---|---|---|---|
| 封面 | 文件可打开、标题完整、中文字体正常 | 通过 | `wps_cover.png` |
| 内容/segments | 分段类型、文本、时长完整，左右区域无挤压 | 通过 | `wps_content_segments.png` |
| two_column | 左右栏职责独立，右栏展示分段，未退化为 content 别名 | 通过 | `wps_two_column.png` |
| 总结 | 列表完整、中文标点正常、留白稳定 | 通过 | `wps_summary.png` |

完整渲染总览见 `render_montage.png`，可复现实机测试的文件见 `wps_compat_test.pptx`。

## 5. 后续建议

1. 在另一台已正常激活并能打开主文档窗口的 Microsoft PowerPoint 2016+ 环境补做一次人工交叉打开；
2. 将全版式测试稿生成脚本纳入发布前回归，避免后续模板改动破坏 `segments` 或 `two_column`；
3. 保留 WPS 截图与 OOXML 结构统计作为每轮导出改动的验收证据。
