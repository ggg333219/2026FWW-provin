"""六种图示的目视验收样本 —— 同时导出 .pptx 与预览 HTML。

自动化测试只能断言"文字进了形状"和"没有 PICTURE"，判断不了几何：环会不会撞到
标题条、表格会不会跑出页面底部、正文会不会溢出面板。那些只能用眼睛看，所以这个
脚本把六种 kind 各摆一页，另加两页**满配压力样本**（列数/条目数取上限，几何最紧）
和一页"不出图"对照页。

    D:\\anaconda\\python.exe scripts\\generate_figure_samples.py

产物（文件名取自 COURSE，下同）：
  docs/预览验证/图示渲染样本.pptx          用 PowerPoint / WPS 打开
  docs/预览验证/图示渲染样本_preview.html  用浏览器打开，对照预览侧
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_engine.gen.export_ppt import ExportPPTConfig, PPTExporter  # noqa: E402
from ai_engine.gen.preview import PreviewRenderer  # noqa: E402

OUT_DIR = _ROOT / "output" / "verification" / "figures"
COURSE = "图示渲染样本"


def _node(node_id: str, title: str, content: str, conclusion: str, figure: dict | None = None,
          details: list[dict] | None = None, points: list[str] | None = None) -> dict:
    node: dict = {
        "node_id": node_id, "type": "content", "node_type": "content",
        "title": title, "content": content, "key_conclusion": conclusion,
    }
    if figure:
        node["figure"] = figure
    if details:
        node["point_details"] = details
    if points:
        node["key_points"] = points
    return node


NODES: list[dict] = [
    # 注：预览的内容页是双栏版式 —— 左栏 3.6in 放**核心要点**（secondary 区），
    # 右栏放图示 + 正文。样本页必须给 key_points，否则左栏只剩底板和标题，
    # 看上去就是一个空方框（那不是版式的问题，是样本没喂够字段）。
    # 左栏宽 3.1in、字号 14，一行约 12 个汉字，要点请写短。
    #
    # ── 1. flow：3 步流程 ──
    _node(
        "fig_flow", "冒泡排序的执行流程",
        "每一轮把当前未排序部分的最大值送到末尾。",
        "n 个元素最多需要 n-1 轮",
        {"kind": "flow", "items": ["比较相邻两个元素", "逆序则交换", "本轮最大值归位"]},
        details=[{"point": "为什么是 n-1 轮", "detail": "每轮至少归位一个元素，最后一个不必再比。"}],
        points=["相邻两两比较", "逆序就交换", "每轮归位一个"],
    ),
    # ── 2. compare：左右对比，每侧 3 条 ──
    _node(
        "fig_compare", "冒泡排序与快速排序",
        "两者都是比较排序，差别在划分方式。",
        "快速排序用分治换取了更少的比较次数",
        {"kind": "compare",
         "left": {"title": "冒泡排序", "items": ["原地排序", "稳定", "平均 O(n²)"]},
         "right": {"title": "快速排序", "items": ["递归划分", "不稳定", "平均 O(n log n)"]}},
        points=["冒泡稳定但慢", "快速快但不稳定"],
    ),
    # ── 3. cycle：4 节点闭环 ──
    _node(
        "fig_cycle", "模型训练的反馈循环",
        "每一轮训练都由上一轮的评估结果驱动。",
        "训练不是一次性的，是评估驱动的闭环",
        {"kind": "cycle", "items": ["采集样本", "训练模型", "评估效果", "调整参数"]},
        points=["训练由评估驱动", "参数随反馈调整"],
    ),
    # ── 4. hierarchy：父 + 3 子 ──
    _node(
        "fig_hierarchy", "排序算法的分类",
        "按是否借助额外存储空间划分。",
        "先分清大类，再记具体算法",
        {"kind": "hierarchy", "items": ["排序算法", "冒泡排序", "快速排序", "归并排序"]},
        points=["先看是否原地", "再看是否稳定"],
    ),
    # ── 5. chart：4 个数据点，数值跨度适中（好判断条长与轨道） ──
    _node(
        "fig_chart", "快速排序递归深度随规模的增长",
        "规模扩大 100 倍，递归深度只多了 7 层。",
        "对数增长：规模翻倍，深度只多一层",
        {"kind": "chart", "series": [
            {"label": "100 个元素", "value": 7},
            {"label": "1000 个元素", "value": 10},
            {"label": "10000 个元素", "value": 14},
            {"label": "100000 个元素", "value": 17},
        ]},
        points=["对数增长很慢", "规模翻倍只多一层"],
    ),
    # ── 6. matrix：3 列 × 3 行 ──
    _node(
        "fig_matrix", "排序算法对比表",
        "同一组维度下横向比较才好读。",
        "没有最好的算法，只有最合适的场景",
        {"kind": "matrix",
         "columns": ["算法", "稳定性", "平均复杂度"],
         "rows": [["冒泡排序", "稳定", "O(n²)"],
                  ["快速排序", "不稳定", "O(n log n)"],
                  ["归并排序", "稳定", "O(n log n)"]]},
        points=["稳定看相等元素", "复杂度看平均与最坏"],
    ),
    # ── 7. 压力样本：matrix 取上限 5 列 × 6 行（几何最紧） ──
    _node(
        "fig_matrix_max", "压力样本：对比表取满 5 列 6 行",
        "列数与行数都取上限，检查表格是否跑出页面底部、正文是否还能放下。",
        "表格越宽越高，留给正文的空间就越小",
        {"kind": "matrix",
         "columns": ["算法", "稳定性", "平均", "最坏", "空间"],
         "rows": [["冒泡排序", "稳定", "O(n²)", "O(n²)", "O(1)"],
                  ["插入排序", "稳定", "O(n²)", "O(n²)", "O(1)"],
                  ["选择排序", "不稳定", "O(n²)", "O(n²)", "O(1)"],
                  ["快速排序", "不稳定", "O(n log n)", "O(n²)", "O(log n)"],
                  ["归并排序", "稳定", "O(n log n)", "O(n log n)", "O(n)"],
                  ["堆排序", "不稳定", "O(n log n)", "O(n log n)", "O(1)"]]},
        points=["稳定排序用于多关键字", "空间换时间要权衡"],
    ),
    # ── 8. 压力样本：compare 每侧取满 5 条 ──
    _node(
        "fig_compare_max", "压力样本：对比取满每侧 5 条",
        "两侧条目都取上限，检查面板高度是否还容得下正文。",
        "条目越多，正文就越容易被挤到面板外",
        {"kind": "compare",
         "left": {"title": "冒泡排序",
                  "items": ["原地排序", "稳定", "平均 O(n²)", "最坏 O(n²)", "空间 O(1)"]},
         "right": {"title": "快速排序",
                   "items": ["递归划分", "不稳定", "平均 O(n log n)", "最坏 O(n²)", "空间 O(log n)"]}},
        points=["平均与最坏分开看", "空间开销常被忽略"],
    ),
    # ── 9. 对照页：规划器判"不出图"时长什么样（反 AI 自嗨的那一侧） ──
    _node(
        "fig_none", "对照页：这页不出图",
        "定义是记忆性的，画出来只会是把要点重排一遍。",
        "复杂度的度量对象是增长趋势，不是秒数",
        details=[
            {"point": "为什么不用耗时秒数", "detail": "同一算法在不同机器上耗时不同，无法横向比较。"},
            {"point": "为什么看增长趋势", "detail": "它只与输入规模有关，与硬件无关。"},
        ],
        points=["大 O 描述上界", "常数项在大规模下可忽略"],
    ),
]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    exporter = PPTExporter(ExportPPTConfig(output_dir=str(OUT_DIR)))
    result = exporter.export(NODES, COURSE)
    print(f"PPTX  已导出：{result['path']}（{result['pages']} 页，{result['file_size']} 字节）")

    html_path = OUT_DIR / f"{COURSE}_preview.html"
    html_path.write_text(PreviewRenderer().render(NODES, COURSE), encoding="utf-8")
    print(f"预览  已写出：{html_path}")

    print("\n打开 .pptx 逐页核对：")
    for i, node in enumerate(NODES, start=1):
        kind = (node.get("figure") or {}).get("kind") or "（不出图）"
        print(f"  第 {i} 页  {kind:<10} {node['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
