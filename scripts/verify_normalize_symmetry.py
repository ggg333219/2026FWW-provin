# -*- coding: utf-8 -*-
"""
M1-4B · normalize 函数完整性（字段对称性）深度审计 — 离线注入测试脚本

对象（按 import 链路确认的生效函数）：
  A. ai_engine/schema.py::normalize_stage2_nodes
     （大纲阶段节点归一，被 gen/outline.py 与 generator.py 调用）
  B. ai_engine/gen/node.py::NodeGenerator._normalize_enhanced_scripts
     （增强讲稿归一，被 NodeGenerator.generate_enhanced 调用；
      generator.py 内另有一份 LessonGenerator 版旧副本，字段集更窄，不在本表对比范围）

方法：
  对每个关键字段注入 None / 空值 / 错误类型（list 传成 str、dict、非数字字符串等），
  断言两函数 (1) 不抛异常 (2) 输出字段类型可接受；并输出两函数逐字段结果对比，
  暴露"一边有兜底另一边没有 / 字段名不一致 / 类型不一致"的不对称点。

运行方式：
  python scripts/verify_normalize_symmetry.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_engine.schema import normalize_stage2_nodes  # noqa: E402
from ai_engine.gen.node import NodeGenerator  # noqa: E402

VALID_IDS = {"n1", "n2"}

BASE_NODE = {
    "node_id": "n1",
    "title": "快速排序",
    "summary": "分治思想的典型应用",
    "source_span": "p3-p5",
    "node_type": "content",
    "type": "content",
    "prerequisites": ["n2"],
    "key_points": ["选取基准", "分区操作"],
    "core_points": ["递归实现"],
    "questions": ["快排最坏复杂度？"],
    "interactive_questions": ["举例说明分区过程？"],
    "segments": [{"segment_id": "seg_1", "text": "讲解内容", "node_id": "n1",
                  "segment_type": "explanation", "estimated_seconds": 45}],
    "layout_hint": "content",
    "font_size_hint": "medium",
    "text_alignment": "left",
    "slide_background": "white",
    "script": "这是讲稿内容。",
}

# 注入用例: (用例名, 字段, 注入值, 期望类型描述, 输出校验器)
# 校验器返回 None 表示通过，否则返回问题描述
NONE_OK = lambda v: None if (v is None or isinstance(v, str)) else f"期望 str 或 None，得到 {type(v).__name__}"
LIST_STR = lambda v: None if (isinstance(v, list) and all(isinstance(x, str) for x in v)) else \
    f"期望 list[str]，得到 {type(v).__name__}: {v!r}"
DICT_OK = lambda v: None if (v is None or isinstance(v, (str, dict))) else f"期望 str/dict/None，得到 {type(v).__name__}"
SEGMENTS_OK = lambda v: None if isinstance(v, list) else f"期望 list，得到 {type(v).__name__}"
STR_OK = lambda v: None if isinstance(v, str) else f"期望 str，得到 {type(v).__name__}"

CASES = [
    # 字段            注入值                        期望                       校验器
    ("title",              None,                          "str",              STR_OK),
    ("title",              123,                           "str",              STR_OK),
    ("title",              ["列表标题"],                   "str",              STR_OK),
    ("summary",            None,                          "str",              STR_OK),
    ("summary",            123,                           "str",              STR_OK),
    ("summary",            ["列表摘要"],                   "str",              STR_OK),
    ("source_span",        None,                          "str/None",         NONE_OK),
    ("source_span",        123,                           "str",              STR_OK),
    ("node_type",          None,                          "str",              STR_OK),
    ("node_type",          123,                           "str",              STR_OK),
    ("node_type",          "content",                     "str(content→slide?)", STR_OK),
    ("type",               None,                          "str",              STR_OK),
    ("prerequisites",      None,                          "list[str]",        LIST_STR),
    ("prerequisites",      "n2",                          "list[str]",        LIST_STR),
    ("prerequisites",      [123, None],                   "list[str]",        LIST_STR),
    ("prerequisites",      {"0": "n2"},                   "list[str]",        LIST_STR),
    ("key_points",         None,                          "list[str]",        LIST_STR),
    ("key_points",         "选取基准",                     "list[str]",        LIST_STR),
    ("key_points",         [{"pt": 1}],                   "list[str]",        LIST_STR),
    ("key_points",         [123],                         "list[str]",        LIST_STR),
    ("core_points",        None,                          "list[str]",        LIST_STR),
    ("core_points",        "递归实现",                     "list[str]",        LIST_STR),
    ("core_points",        [{"pt": 1}],                   "list[str]",        LIST_STR),
    ("questions",          None,                          "list[str]",        LIST_STR),
    ("questions",          "单个问题",                     "list[str]",        LIST_STR),
    ("questions",          [{"question": "q", "answer": "a"}], "list[str]",   LIST_STR),
    ("questions",          [123, None],                   "list[str]",        LIST_STR),
    ("questions",          {"q1": "文本"},                 "list[str]",        LIST_STR),
    ("interactive_questions", None,                       "list[str]",        LIST_STR),
    ("interactive_questions", "单个问题",                  "list[str]",        LIST_STR),
    ("interactive_questions", [{"question": "q"}],        "list[str]",        LIST_STR),
    ("segments",           None,                          "list",             SEGMENTS_OK),
    ("segments",           "seg_1",                       "list",             SEGMENTS_OK),
    ("segments",           [{"segment_id": "s1", "text": "t", "node_id": "n1",
                             "segment_type": "opening", "estimated_seconds": "abc"}], "list", SEGMENTS_OK),
    ("segments",           [{"segment_id": "s1", "text": "t", "node_id": "n1",
                             "segment_type": "opening", "estimated_seconds": None}], "list", SEGMENTS_OK),
    ("segments",           [{"segment_id": "s1", "text": "t", "node_id": "n1",
                             "segment_type": 123, "knowledge_card": ["非dict"]}], "list", SEGMENTS_OK),
    ("layout_hint",        None,                          "str/None",         DICT_OK),
    ("layout_hint",        123,                           "str/None",         DICT_OK),
    ("layout_hint",        ["two_column"],                "str/None",         DICT_OK),
    ("font_size_hint",     None,                          "str/None",         DICT_OK),
    ("font_size_hint",     {"size": "large"},             "str/None",         DICT_OK),
    ("text_alignment",     None,                          "str/None",         DICT_OK),
    ("text_alignment",     123,                           "str/None",         DICT_OK),
    ("slide_background",   None,                          "str/None",         DICT_OK),
    ("slide_background",   123,                           "str/None",         DICT_OK),
    ("script",             None,                          "str",              STR_OK),
    ("script",             123,                           "str",              STR_OK),
    ("script",             ["段落1", "段落2"],              "str",              STR_OK),
]


def run_a(node: dict):
    out = normalize_stage2_nodes([node])
    return out[0] if out else {}


def run_b(node: dict):
    out = NodeGenerator._normalize_enhanced_scripts([node], VALID_IDS)
    return out[0] if out else {}


def main() -> int:
    print("=" * 86)
    print("M1-4B normalize 对称性注入测试 — normalize_stage2_nodes(A) vs _normalize_enhanced_scripts(B)")
    print("=" * 86)

    results = []  # (field, value, ok_a, detail_a, ok_b, detail_b)
    for field, inject, expect, checker in CASES:
        node = {**BASE_NODE, field: inject}

        ok_a, detail_a = True, "-"
        try:
            out_a = run_a(node)
            problem = checker(out_a.get(field, "<缺失>"))
            if problem:
                ok_a, detail_a = False, problem
            elif field not in out_a and field not in ("script", "segments", "summary", "source_span",
                                                       "prerequisites", "node_type", "type", "estimated_seconds"):
                ok_a, detail_a = False, "输出缺失该字段"
            else:
                detail_a = repr(out_a.get(field))[:60]
        except Exception as exc:
            ok_a, detail_a = False, f"崩溃: {type(exc).__name__}: {exc}"

        ok_b, detail_b = True, "-"
        try:
            out_b = run_b(node)
            problem = checker(out_b.get(field, "<缺失>"))
            if problem:
                ok_b, detail_b = False, problem
            elif field not in out_b and field not in ("script", "segments", "summary", "source_span",
                                                       "prerequisites", "node_type", "type", "estimated_seconds"):
                ok_b, detail_b = False, "输出缺失该字段"
            else:
                detail_b = repr(out_b.get(field))[:60]
        except Exception as exc:
            ok_b, detail_b = False, f"崩溃: {type(exc).__name__}: {exc}"

        results.append((field, inject, expect, ok_a, detail_a, ok_b, detail_b))

    # 打印矩阵
    asym = 0
    print(f"\n{'字段':<22}{'注入值':<26}{'期望':<20}{'A:stage2':<8}{'B:enhanced':<10}对称")
    print("-" * 110)
    for field, inject, expect, ok_a, detail_a, ok_b, detail_b in results:
        inj = repr(inject)[:24]
        sym = "" if ok_a == ok_b else "  ← 不对称"
        if ok_a != ok_b:
            asym += 1
        a_s = "PASS" if ok_a else "FAIL"
        b_s = "PASS" if ok_b else "FAIL"
        print(f"{field:<22}{inj:<26}{expect:<20}{a_s:<8}{b_s:<10}{sym}")
        if not ok_a:
            print(f"{'':<22}A详情: {detail_a}")
        if not ok_b:
            print(f"{'':<22}B详情: {detail_b}")

    total = len(results)
    fail_a = sum(1 for r in results if not r[3])
    fail_b = sum(1 for r in results if not r[5])
    print("-" * 110)
    print(f"用例总数: {total}；A 失败 {fail_a}；B 失败 {fail_b}；A/B 结果不一致（不对称）用例: {asym}")
    print("整体结论:", "PASS" if fail_a == 0 and fail_b == 0 else
          f"FAIL（A 失败 {fail_a}，B 失败 {fail_b}）")
    return 0 if fail_a == 0 and fail_b == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
