"""Generate the full-layout PPTX used for Office/WPS compatibility checks."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.gen.export_ppt import ExportPPTConfig, PPTExporter


COMPAT_NODES = [
    {
        "node_id": "cover", "node_type": "cover", "title": "AI 互动式教学兼容验证",
        "content": "Office / WPS · 可编辑 PPTX · 2026",
    },
    {
        "node_id": "agenda", "node_type": "agenda", "title": "验证目录",
        "key_points": ["中文字体与标点", "结构化要点", "讲授分段", "双栏版式", "互动与总结"],
    },
    {
        "node_id": "section", "node_type": "section", "title": "第一章｜课堂生成链路",
        "summary": "验证封面、章节、内容、互动、总结等页面在主流办公软件中的一致表现。",
    },
    {
        "node_id": "content", "node_type": "content", "title": "内容与讲授分段保持同源",
        "content": "系统根据教师意图生成结构化教学内容；预览与导出读取同一组节点字段。",
        "key_points": ["type / node_type 双字段兼容", "key_points / core_points 合并", "所有文本保持可编辑"],
        "segments": [
            {"segment_type": "opening", "text": "用“为什么同一份数据会导出不同页面？”导入。", "estimated_seconds": 30},
            {"segment_type": "explanation", "text": "讲解预览与导出统一识别规则，并展示中文顿号、引号。", "estimated_seconds": 90},
            {"segment_type": "interaction", "text": "请学生判断：A、字段缺失；B、类型冲突；C、模板失配。", "estimated_seconds": 45},
        ],
    },
    {
        "node_id": "two-column", "node_type": "two_column", "title": "双栏布局把要点与讲授过程并列呈现",
        "key_points": ["左栏只呈现核心结论", "要点间距稳定，不产生文字溢出", "栏间保留清晰视觉间隔"],
        "segments": [
            {"segment_type": "explanation", "text": "右栏展示讲授类型、文本与预估时长。", "estimated_seconds": 60},
            {"segment_type": "example", "text": "示例：算法复杂度从 O(n²) 优化到 O(n log n)。", "estimated_seconds": 50},
            {"segment_type": "summary", "text": "小结：左右栏内容职责明确，版式语义稳定。", "estimated_seconds": 35},
        ],
    },
    {
        "node_id": "quiz", "node_type": "quiz", "title": "课堂互动",
        "questions": ["预览与导出应优先读取哪个页面类型字段？", "当 segments 为空时，双栏右侧展示什么内容？"],
    },
    {
        "node_id": "summary", "node_type": "summary", "title": "验证结论",
        "key_points": ["文件结构符合 OOXML", "所有文本和形状可编辑", "中文标点显示完整", "双栏与分段信息均正常呈现"],
    },
]


def main() -> Path:
    output_dir = Path("data/exports")
    exporter = PPTExporter(ExportPPTConfig(output_dir=str(output_dir)))
    result = exporter.export(COMPAT_NODES, "wps_compat_test", template_id="default")
    path = Path(result["path"]).resolve()
    print(path)
    return path


if __name__ == "__main__":
    main()
