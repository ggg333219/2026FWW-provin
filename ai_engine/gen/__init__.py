"""gen — AI Engine 生成模块（S3 课件生成 + S4 个性化满足）

替代原有单块 generator.py，按业务域拆分：

S3 课件生成:
  outline.py       — 大纲构建
  node.py          — 逐节点生成
  export_ppt.py    — PPTX 导出
  export_doc.py    — DOCX 导出
  interactive.py   — 互动内容

S4 个性化满足:
  preview.py       — 预览渲染
  commands.py      — 命令解析
  patch.py         — 节点修补
"""
