"""Generate the six-node snapshot used for preview/export and WPS checks."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.gen.export_ppt import ExportPPTConfig, PPTExporter


SIX_NODE_SNAPSHOT = [
    {
        "node_id": "n1", "type": "cover", "node_type": "cover",
        "title": "排序算法课堂", "content": "六节点预览与导出同源验收",
    },
    {
        "node_id": "n2", "type": "section", "node_type": "section",
        "title": "学习目录", "content": "从复杂度概念走向算法选择",
        "key_points": ["理解复杂度", "比较典型算法"],
    },
    {
        "node_id": "n3", "type": "content", "node_type": "content",
        "title": "复杂度基础", "content": "复杂度描述算法耗时随数据规模增长的趋势。",
        "key_points": ["时间复杂度", "空间复杂度"],
        "core_points": ["时间复杂度", "空间复杂度"],
        "segments": [
            {"segment_type": "opening", "text": "从查找成绩的耗时问题导入。", "estimated_seconds": 45},
            {"segment_type": "explanation", "text": "讲解大 O 表示法。", "estimated_seconds": 90},
        ],
    },
    {
        "node_id": "n4", "type": "two_column", "node_type": "two_column",
        "title": "算法对比", "content": "比较不同排序算法的适用场景。",
        "key_points": ["冒泡排序稳定", "快速排序平均更快"],
        "core_points": ["冒泡排序稳定", "快速排序平均更快"],
        "segments": [
            {"segment_type": "example", "text": "对比 O(n²) 与 O(n log n)。", "estimated_seconds": 60},
        ],
    },
    {
        "node_id": "n5", "type": "quiz", "node_type": "quiz",
        "title": "课堂检测", "questions": ["哪种算法平均复杂度为 O(n log n)？"],
    },
    {
        "node_id": "n6", "type": "summary", "node_type": "summary",
        "title": "课程小结", "key_points": ["选择算法要结合数据规模", "关注时间与空间权衡"],
        "core_points": ["选择算法要结合数据规模", "关注时间与空间权衡"],
    },
]


def main() -> Path:
    output_dir = Path("data/exports")
    exporter = PPTExporter(ExportPPTConfig(output_dir=str(output_dir)))
    result = exporter.export(
        SIX_NODE_SNAPSHOT,
        "member3_six_node_consistency",
        template_id="default",
    )
    path = Path(result["path"]).resolve()
    print(path)
    return path


if __name__ == "__main__":
    main()
