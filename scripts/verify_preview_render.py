"""M2-3B 预览渲染离线验证脚本。

构造含 slide / quiz / interactive 三种类型、带 key_points / script / segments
的样例节点列表，直接调用 PreviewRenderer 生成 HTML：
  1. 输出保存到 docs/预览验证/sample_preview.html
  2. 断言 HTML 中包含：quiz 题目与选项、key_points 高亮 class、"讲授文本"标签、
     segment 中文语义标签
  3. 向后兼容断言：旧节点（无 segments / 无 key_points / 无 script）渲染不崩溃，
     且不产生空区块

运行方式（仓库根目录）：
  python scripts/verify_preview_render.py
不依赖网络，不调用 LLM API。
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.gen.preview import PreviewRenderer  # noqa: E402

OUT_PATH = PROJECT_ROOT / "output" / "verification" / "preview" / "sample_preview.html"

SAMPLE_NODES = [
    # 1. 封面
    {
        "node_id": "node_001",
        "title": "排序算法入门",
        "node_type": "cover",
        "subtitle": "面向大一计算机专业",
    },
    # 2. 普通内容页：key_points + script + segments 全字段
    {
        "node_id": "node_002",
        "title": "冒泡排序的基本思想",
        "node_type": "slide",
        "content": "冒泡排序通过相邻元素两两比较，把较大元素逐步交换到序列尾部。",
        "key_points": ["相邻元素两两比较", "每轮把最大值冒泡到末尾", "时间复杂度 O(n²)"],
        "script": "同学们好，这一页我们先来看冒泡排序的核心思想。请大家注意每一轮比较结束后，最大的元素会像气泡一样浮到序列末尾。",
        "segments": [
            {"segment_id": "seg_001", "text": "我们先从一个生活中的例子说起。",
             "segment_type": "opening", "estimated_seconds": 30, "difficulty": "easy"},
            {"segment_id": "seg_002", "text": "冒泡排序每一轮都会把当前未排序部分的最大值放到最后。",
             "segment_type": "explanation", "estimated_seconds": 60, "difficulty": "medium"},
            {"segment_id": "seg_003", "text": "比如数组 [5, 3, 8]，第一轮比较后 8 会被放到最后。",
             "segment_type": "example", "estimated_seconds": 45, "difficulty": "easy"},
            {"segment_id": "seg_004", "text": "这一段就是本页的小结。",
             "segment_type": "summary", "estimated_seconds": 20, "difficulty": "easy"},
        ],
    },
    # 3. quiz 页：dict 题目（题干 + 选项 + 答案 + 解析）+ 字符串题目
    {
        "node_id": "node_003",
        "title": "随堂小测",
        "node_type": "quiz",
        "questions": [
            {
                "question": "冒泡排序的时间复杂度是多少？",
                "options": ["O(n)", "O(n log n)", "O(n²)", "O(1)"],
                "answer": "C",
                "explanation": "冒泡排序最坏情况下需要进行 n(n-1)/2 次比较，属于平方级。",
            },
            "请用自己的话复述冒泡排序的一轮比较过程。",
        ],
        "script": "给大家两分钟时间完成这道选择题，之后我会随机请一位同学复述冒泡排序的过程。",
    },
    # 4. interactive 页：互动投票题目
    {
        "node_id": "node_004",
        "title": "课堂互动：你掌握了吗？",
        "node_type": "interactive",
        "questions": [
            {
                "question": "你对冒泡排序的掌握程度是？",
                "options": ["完全掌握", "基本理解", "有些模糊", "需要重讲"],
                "answer": "",
            },
        ],
    },
    # 5. segment_type 缺失 + 未知类型的页（兜底标签验证）
    {
        "node_id": "node_005",
        "title": "课后练习",
        "node_type": "slide",
        "content": "完成教材第 3 章习题 1-5。",
        "segments": [
            {"segment_id": "seg_101", "text": "这是一个没有 segment_type 的旧分段。"},
            {"segment_id": "seg_102", "text": "这是一个 segment_type 未知（demo）的分段。",
             "segment_type": "demo_type"},
        ],
    },
]

LEGACY_NODE = {
    "node_id": "legacy_001",
    "title": "极简旧节点",
    "type": "content",
    "content": "只有一句正文的旧版本节点，用于验证向后兼容。",
}


def check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    return cond


def main() -> int:
    renderer = PreviewRenderer()

    # ── 1. 样例节点渲染并保存 ──
    html_out = renderer.render(SAMPLE_NODES, course_name="排序算法入门")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html_out, encoding="utf-8")
    print(f"样例预览已生成: {OUT_PATH}")

    all_ok = True
    print("\n== M2-3B 渲染能力断言 ==")

    # a. quiz / interactive 专属渲染分支（题目列表 + 选项展示）
    all_ok &= check("quiz 题干渲染", "冒泡排序的时间复杂度是多少？" in html_out)
    all_ok &= check("quiz 选项渲染（q-option 节点）",
                    html_out.count('<li class="q-option') >= 5)  # quiz 4 项 + interactive 4 项
    all_ok &= check("quiz 答案选项高亮", '<li class="q-option q-option-answer">' in html_out)
    all_ok &= check("quiz 解析渲染", "解析：冒泡排序最坏情况下需要进行 n(n-1)/2 次比较" in html_out)
    # 断言的是「这页有没有专属 slide class」，不是「div 上只能有 class 一个属性」——
    # 外壳自 P2 起还带 data-node-id（局部刷新的锚），所以只匹到 class 为止。
    all_ok &= check("quiz 页专属布局（quiz-slide div）",
                    'class="slide quiz-slide"' in html_out)
    all_ok &= check("interactive 页专属布局（quiz-slide interactive-slide div）",
                    'class="slide quiz-slide interactive-slide"' in html_out)

    # a2. 局部刷新的锚：每页都带 data-node-id，且互不重复
    page_ids = re.findall(r'<div class="slide [^"]*" data-node-id="([^"]*)"', html_out)
    expected_ids = [n["node_id"] for n in SAMPLE_NODES] + ["__auto_summary__"]
    all_ok &= check("每页都有 data-node-id（局部刷新的锚）",
                    len(page_ids) == html_out.count('<div class="slide ') and all(page_ids))
    all_ok &= check("data-node-id 与节点一一对应且不重复",
                    page_ids == expected_ids and len(page_ids) == len(set(page_ids)))

    # b. key_points 视觉高亮（断言渲染产物而非 CSS 定义）
    all_ok &= check("key_points 高亮文本 class（kp-highlight）",
                    '<span class="kp-highlight">相邻元素两两比较</span>' in html_out)
    all_ok &= check("key_points 列表项 class（kp-item）",
                    '<li class="kp-item">' in html_out)

    # c. script "讲授文本"标签区块
    all_ok &= check("讲授文本标签区块（section.script-block）",
                    '<section class="script-block"><h4>讲授文本</h4>' in html_out)
    all_ok &= check("script 内容渲染", "最大的元素会像气泡一样浮到序列末尾" in html_out)

    # d. segments 语义化中文标签 + 兜底标签
    all_ok &= check("segment 导入标签", '>导入</span>' in html_out)
    all_ok &= check("segment 讲解标签", '>讲解</span>' in html_out)
    all_ok &= check("segment 示例标签", '>示例</span>' in html_out)
    all_ok &= check("segment 小结标签", '>小结</span>' in html_out)
    all_ok &= check("segment 缺失类型兜底（段落）", '>段落</span>' in html_out)
    all_ok &= check("segment 未知类型兜底（其他）", '>其他</span>' in html_out)

    print("\n== 向后兼容断言 ==")
    legacy_html = renderer.render([LEGACY_NODE], course_name="旧节点兼容")
    all_ok &= check("旧节点渲染不崩溃且内容正常", bool(legacy_html) and "极简旧节点" in legacy_html)
    all_ok &= check("旧节点不产生空讲授文本区块", '<section class="script-block">' not in legacy_html)
    all_ok &= check("旧节点不产生空分段区块", '<section class="segments-block">' not in legacy_html)
    all_ok &= check("空节点列表返回空态不崩溃", "empty-state" in renderer.render([], course_name="空"))

    print("\n" + ("ALL PASS" if all_ok else "SOME CHECKS FAILED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
