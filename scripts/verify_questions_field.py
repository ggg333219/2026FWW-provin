# -*- coding: utf-8 -*-
"""
M1-4A · questions 字段全链路离线验证脚本

目的：
  此前修过 questions 类型不统一的 bug（questions 应为 list[str]，不能是 list[dict]）。
  本脚本构造含脏数据的样例节点，走"实际生效"的 normalize 写入点，验证输出 questions /
  interactive_questions 是否均为 list[str] 且过程不崩溃。

生效写入点（按 import 链路确认）：
  1. ai_engine/schema.py::normalize_stage2_nodes      （outline 阶段，gen/outline.py 与 generator.py 调用）
  2. ai_engine/schema.py::normalize_stage3_scripts    （普通讲稿归一，gen/node.py::NodeGenerator.generate_all 调用）
  3. ai_engine/gen/node.py::NodeGenerator._normalize_enhanced_scripts（增强讲稿归一，generate_enhanced 调用）

运行方式：
  python scripts/verify_questions_field.py
  （只做纯内存计算，不调用 LLM、不访问网络、不修改任何文件）
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_engine.schema import normalize_stage2_nodes, normalize_stage3_scripts  # noqa: E402
from ai_engine.gen.node import NodeGenerator  # noqa: E402

VALID_IDS = {"n1", "n2", "n3"}

# ── 样例节点（正常 / 缺字段 / 脏数据）────────────────────────────────────────
SAMPLE_NODES = [
    {
        "label": "S1_正常节点",
        "node": {
            "node_id": "n1",
            "title": "排序算法概述",
            "summary": "介绍常见排序算法分类",
            "node_type": "content",
            "questions": ["什么是稳定排序？", "快排最坏复杂度是多少？"],
            "interactive_questions": ["举例说明稳定排序的意义？"],
        },
        "expect": {"questions": ["什么是稳定排序？", "快排最坏复杂度是多少？"]},
    },
    {
        "label": "S2_缺questions字段",
        "node": {
            "node_id": "n2",
            "title": "冒泡排序",
            "summary": "冒泡排序的基本流程",
            "node_type": "content",
        },
        "expect": {"questions": []},
    },
    {
        "label": "S3_questions为list[dict]脏数据",
        "node": {
            "node_id": "n3",
            "title": "快速排序",
            "summary": "分治思想",
            "node_type": "content",
            "questions": [
                {"question": "快排的时间复杂度？", "answer": "O(nlogn)", "type": "quiz"},
                {"question": "快排是稳定排序吗？", "answer": "不是", "type": "quiz"},
            ],
        },
        "expect": {"questions": ["快排的时间复杂度？", "快排是稳定排序吗？"]},
    },
    {
        "label": "S4_interactive_questions为list[dict]且无questions",
        "node": {
            "node_id": "n1",
            "title": "归并排序",
            "summary": "分治+合并",
            "node_type": "quiz",
            "interactive_questions": [{"question": "归并的空间复杂度？", "answer": "O(n)"}],
        },
        "expect": {"questions": ["归并的空间复杂度？"]},
    },
    {
        "label": "S5_questions为str脏数据",
        "node": {
            "node_id": "n2",
            "title": "堆排序",
            "summary": "堆结构应用",
            "node_type": "content",
            "questions": "堆排序的时间复杂度是多少？",
        },
        "expect": {"questions": ["堆排序的时间复杂度是多少？"]},
    },
    {
        "label": "S6_questions为None",
        "node": {
            "node_id": "n3",
            "title": "桶排序",
            "summary": "桶思想",
            "node_type": "content",
            "questions": None,
            "interactive_questions": None,
        },
        "expect": {"questions": []},
    },
]

RESULTS: list[tuple[str, bool, str]] = []


def is_list_of_str(value) -> bool:
    return isinstance(value, list) and all(isinstance(q, str) for q in value)


def check_normalize(fn_name: str, fn, label: str, node: dict) -> tuple[bool, str]:
    """对单个样例节点跑一个 normalize 写入点，检查 questions 类型。返回 (ok, detail)。"""
    try:
        if fn_name == "normalize_stage2_nodes":
            out_list = fn([node])
            out = out_list[0] if out_list else {}
        elif fn_name == "normalize_stage3_scripts":
            out_list = fn([dict(node, script="讲解内容")], VALID_IDS)
            out = out_list[0] if out_list else {}
        else:  # _normalize_enhanced_scripts
            item = dict(node, script="讲解内容")
            out_list = NodeGenerator._normalize_enhanced_scripts([item], VALID_IDS)
            out = out_list[0] if out_list else {}
    except Exception as exc:  # 崩溃即 FAIL
        return False, f"异常崩溃: {type(exc).__name__}: {exc}"

    if not out:
        return False, "输出为空（节点被过滤）"

    problems = []
    for field in ("questions", "interactive_questions"):
        value = out.get(field)
        if not is_list_of_str(value):
            problems.append(f"{field}={value!r} (类型={type(value).__name__}, "
                            f"元素类型={{{', '.join(sorted({type(q).__name__ for q in value}))}}}"
                            if isinstance(value, list) and value else
                            f"{field}={value!r} (类型={type(value).__name__})")
    if problems:
        return False, "; ".join(problems)
    return True, "questions / interactive_questions 均为 list[str]"


def main() -> int:
    print("=" * 78)
    print("M1-4A questions 字段验证 — 生效 normalize 写入点 × 脏数据样例矩阵")
    print("=" * 78)

    write_points = [
        ("normalize_stage2_nodes", normalize_stage2_nodes),
        ("normalize_stage3_scripts", normalize_stage3_scripts),
        ("NodeGenerator._normalize_enhanced_scripts",
         lambda scripts, ids: NodeGenerator._normalize_enhanced_scripts(scripts, ids)),
    ]

    total = failed = 0
    for fn_name, fn in write_points:
        print(f"\n─── 写入点: {fn_name} ───")
        for sample in SAMPLE_NODES:
            total += 1
            ok, detail = check_normalize(fn_name, fn, sample["label"], sample["node"])
            tag = "PASS" if ok else "FAIL"
            if not ok:
                failed += 1
            print(f"  [{tag}] {sample['label']}  →  {detail}")

    print("\n" + "=" * 78)
    print(f"汇总: {total - failed}/{total} PASS, {failed} FAIL")
    print("=" * 78)
    print("整体结论:", "PASS" if failed == 0 else "FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
