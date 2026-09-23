"""重建 default / academic / minimal 教学模板样例。

运行：python -m ai_engine.gen.templates.build_templates
生成物同时作为可直接打开的五版式模板样例，以及导出器 template_dir 的可选母版来源。
"""

from pathlib import Path

from ..export_ppt import PPTExporter


TEMPLATE_NODES = [
    {
        "node_id": "cover", "node_type": "cover",
        "title": "课程主题", "content": "授课对象 · 课时 · 教学目标",
    },
    {
        "node_id": "agenda", "node_type": "agenda", "title": "课程目录",
        "key_points": ["课程导入", "核心概念", "案例实践", "总结提升"],
    },
    {
        "node_id": "content", "node_type": "slide", "title": "核心内容",
        "content": "在这里填写本页的关键概念、方法或案例。",
        "core_points": ["教学要点一", "教学要点二"],
        "segments": [
            {"segment_type": "opening", "text": "用问题或场景引入本页。", "estimated_seconds": 30},
            {"segment_type": "explanation", "text": "讲清概念，并连接学生已有知识。", "estimated_seconds": 90},
            {"segment_type": "interaction", "text": "设置一个可现场回应的问题。", "estimated_seconds": 45},
        ],
    },
    {
        "node_id": "two-column", "node_type": "two_column", "title": "双栏讲授",
        "key_points": ["左栏聚焦核心结论", "要点保持可快速扫描"],
        "segments": [
            {"segment_type": "explanation", "text": "右栏呈现讲授分段与时长。", "estimated_seconds": 60},
            {"segment_type": "interaction", "text": "以问题检验学生理解。", "estimated_seconds": 45},
        ],
    },
    {
        "node_id": "summary", "node_type": "summary", "title": "本节小结",
        "key_points": ["回顾核心结论", "检查学习目标", "说明课后应用"],
    },
]


def build_templates() -> list[Path]:
    output_dir = Path(__file__).resolve().parent
    exporter = PPTExporter()
    outputs = []
    for template_id in ("default", "academic", "minimal"):
        target = output_dir / f"{template_id}.pptx"
        target.write_bytes(exporter.export_to_bytes(TEMPLATE_NODES, "教学课件模板", template_id).getvalue())
        outputs.append(target)
    return outputs


if __name__ == "__main__":
    for path in build_templates():
        print(path)
