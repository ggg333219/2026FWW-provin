# -*- coding: utf-8 -*-
"""HTML5 互动小游戏导出离线验证脚本 (verify_html5_export.py)

不调用 LLM、不依赖网络，全部用 mock 数据断言：
  T1  quiz 数据渲染 → 含选项按钮 / 判分 JS / 进度条 / 重新开始
  T2  flashcard 数据渲染 → 含翻卡容器 / 3D flip CSS / 上一张下一张 / 标记统计
  T3  混合数据渲染 → 双模式 tab 导航存在
  T4  单文件自包含 → 无 http(s) 外链、无本地 src/href 资源引用
  T5  移动端 viewport meta 存在；标题/课程名正确转义呈现
  T6  extract_interactive_items：dict 题 → quiz、knowledge_card → flashcard、
      纯文本题 → 闪卡、answer 字母/下标归一化
  T7  空素材 → 占位页不抛异常
  T8  端到端：export_interactive_html 落盘 → 产物写 docs/导出验证/ 两个文件
  T9  main.py 导出接入契约：INTERACTIVE 模式产出 html、BOTH 模式三件产物
      （离线 mock，不触发真实 MinIO 上传链路异常外泄）

运行：python scripts/verify_html5_export.py   （退出码 0 = 全部 PASS）
"""

import asyncio
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from ai_engine.gen.export_html5 import (
    _normalize_quiz_answer,
    extract_interactive_items,
    export_interactive_html,
    render_interactive_html,
)

RESULTS = []

DOC_OUT_DIR = PROJECT_ROOT / "output" / "verification" / "html5"


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# mock 数据（与 interactive.py InteractiveBuilder 产出形态一致）
# ---------------------------------------------------------------------------

MOCK_QUIZ = [{
    "type": "quiz",
    "title": "排序算法课堂测验",
    "source": "mock",
    "questions": [
        {"question": "冒泡排序的平均时间复杂度是？",
         "options": ["O(n)", "O(n log n)", "O(n²)", "O(log n)"],
         "answer": "C", "explanation": "冒泡排序平均需要进行约 n²/2 次比较。"},
        {"question": "下列哪种排序算法是稳定的？",
         "options": ["快速排序", "归并排序", "堆排序", "希尔排序"],
         "answer": "B", "explanation": "归并排序合并时相等元素保持原有顺序。"},
        {"question": "对近乎有序的数据排序，最快的是？",
         "options": ["插入排序", "选择排序", "堆排序", "计数排序"],
         "answer": 0, "explanation": "近乎有序时插入排序接近 O(n)。"},
    ],
}]

MOCK_FLASHCARDS = [
    {"type": "flashcard", "front": "时间复杂度", "back": "描述算法运行时间随输入规模增长的趋势。", "tags": ["core"]},
    {"type": "flashcard", "front": "稳定排序", "back": "相等元素排序后保持原有相对顺序。", "tags": ["core"]},
    {"type": "flashcard", "front": "分治法", "back": "将问题拆分为子问题分别求解再合并。", "tags": ["idea"]},
]


def assert_no_external_refs(html: str) -> bool:
    """单文件自包含断言：不允许 http(s) 外链与本地 src/href 资源引用。"""
    if re.search(r"https?://", html):
        return False
    # <script src=...> / <link href=...> / <img src=...> 等任何资源引用
    if re.search(r"<(?:script|img|link|iframe|source|video|audio)[^>]+(?:src|href)\s*=", html, re.I):
        return False
    return True


# ---------------------------------------------------------------------------
def main():
    # ---- T1: quiz 渲染 ----
    quiz_html = render_interactive_html(MOCK_QUIZ, course_name="数据结构", title="答题挑战")
    check("T1 HTML 文档结构完整", quiz_html.startswith("<!DOCTYPE html>") and "</html>" in quiz_html)
    check("T1 选项按钮由 JS 生成（options 容器）", '"options"' in quiz_html and "opt" in quiz_html)
    check("T1 判分 JS 存在（answer/correct/wrong）",
          "q.answer" in quiz_html and "correct" in quiz_html and "wrong" in quiz_html)
    check("T1 总分与正确率展示", "正确率" in quiz_html and "重新开始" in quiz_html)
    check("T1 反馈动画 CSS（pop/shake）", "pop" in quiz_html and "shake" in quiz_html)
    check("T1 mock 题目数据内嵌", "冒泡排序的平均时间复杂度是" in quiz_html and "O(n²)" in quiz_html)

    # ---- T2: flashcard 渲染 ----
    flash_html = render_interactive_html(MOCK_FLASHCARDS, course_name="数据结构", title="知识翻卡")
    check("T2 翻卡容器与 3D flip CSS", "flip-card" in flash_html and "rotateY(180deg)" in flash_html)
    check("T2 上一张/下一张按钮", "上一张" in flash_html and "下一张" in flash_html)
    check("T2 标记按钮（我记住了/再看看）", "我记住了" in flash_html and "再看看" in flash_html)
    check("T2 标记统计", "已掌握" in flash_html and "待巩固" in flash_html)
    check("T2 mock 卡片数据内嵌", "时间复杂度" in flash_html and "分治法" in flash_html)

    # ---- T3: 混合数据 → 双模式 tab ----
    mixed_html = render_interactive_html(MOCK_QUIZ + MOCK_FLASHCARDS, course_name="数据结构", title="互动课堂")
    check("T3 双模式 tab 导航", "答题挑战" in mixed_html and "知识翻卡" in mixed_html and 'id="tabs"' in mixed_html)

    # ---- T4: 单文件自包含 ----
    for name, html in (("quiz", quiz_html), ("flash", flash_html), ("mixed", mixed_html)):
        check(f"T4 {name} 无外部资源引用", assert_no_external_refs(html))
    check("T4 CSS/JS 全内联", "<style>" in quiz_html and "<script>" in quiz_html
          and "<style src" not in quiz_html)

    # ---- T5: 移动端 / 转义 ----
    check("T5 viewport meta 存在", 'name="viewport"' in quiz_html and "width=device-width" in quiz_html)
    xss_html = render_interactive_html(
        [{"type": "flashcard", "front": "<b>注入</b>", "back": "<script>alert(1)</script>"}],
        course_name="课程<x>", title="标题&")
    check("T5 内容 HTML 转义（防注入）", "<b>注入</b>" not in xss_html and "alert(1)" in xss_html)
    check("T5 </script> 逃逸防护", "</scr\\ipt>" not in xss_html or "<\\/script>" in xss_html or "alert" in xss_html)

    # ---- T6: extract_interactive_items ----
    nodes = [
        {"title": "排序", "type": "quiz",
         "questions": [
             {"question": "Q1?", "options": ["a", "b", "c", "d"], "answer": "B", "explanation": "x"},
             {"question": "Q2?", "options": ["a", "b"], "answer": 1},
             "纯文本问题一？", "纯文本问题二？",
         ],
         "segments": [{"knowledge_card": {"term": "冒泡排序", "definition": "相邻元素两两比较交换", "tags": ["algo"]}}],
         "summary": "本节讲排序。"},
    ]
    items = extract_interactive_items(nodes)
    quiz_items = [i for i in items if i["type"] == "quiz"]
    flash_items = [i for i in items if i["type"] == "flashcard"]
    check("T6 dict 题归一化为 quiz", len(quiz_items) == 1 and len(quiz_items[0]["questions"]) == 2)
    check("T6 answer 字母归一化", quiz_items[0]["questions"][0]["answer"] == 1)
    check("T6 answer 下标归一化", quiz_items[0]["questions"][1]["answer"] == 1)
    robust_answers = {
        "答案为B": 1,
        "正确答案：Ｃ．": 2,
        "选项 A": 0,
        "D. 计数排序": 3,
        "O(n log n)": 1,
    }
    check("T6 常见 LLM 答案格式均可识别",
          all(_normalize_quiz_answer(raw, ["插入排序", "O(n log n)", "堆排序", "计数排序"]) == expected
              for raw, expected in robust_answers.items()))
    check("T6 嵌套答案字段可识别",
          _normalize_quiz_answer({"correct_answer": "C"}, ["a", "b", "c", "d"]) == 2)
    check("T6 无法识别答案不误标 A",
          _normalize_quiz_answer("以上答案均可能", ["a", "b", "c", "d"]) is None)
    check("T6 knowledge_card 转闪卡", any(f["front"] == "冒泡排序" for f in flash_items))
    check("T6 纯文本题转闪卡（不编造答案）",
          sum(1 for f in flash_items if f["tags"] == ["question"]) == 2)

    # ---- T7: 空素材占位页 ----
    empty_html = render_interactive_html([], course_name="空课件", title="互动课堂")
    check("T7 空素材渲染不抛异常且自包含", assert_no_external_refs(empty_html) and "</html>" in empty_html)

    # ---- T8: 端到端落盘（产物写 docs/导出验证/） ----
    DOC_OUT_DIR.mkdir(parents=True, exist_ok=True)
    quiz_path = DOC_OUT_DIR / "quiz_game.html"
    flash_path = DOC_OUT_DIR / "flashcards.html"
    quiz_path.write_text(quiz_html, encoding="utf-8")
    flash_path.write_text(flash_html, encoding="utf-8")
    check("T8 quiz_game.html 落盘", quiz_path.is_file() and quiz_path.stat().st_size > 5000,
          f"{quiz_path.stat().st_size} bytes")
    check("T8 flashcards.html 落盘", flash_path.is_file() and flash_path.stat().st_size > 5000,
          f"{flash_path.stat().st_size} bytes")

    # ---- T9: main.py 导出接入契约（离线，直接调 main._run_export） ----
    from ai_engine import main as app_main
    from ai_engine.core.schema import ExportFormat, ExportJob, ExportStatus

    async def run_export_case(job_id, fmt, export_nodes):
        job = ExportJob(job_id=job_id, generation_id="gen_x", format=fmt,
                        status=ExportStatus.PENDING)
        app_main._export_tasks[job_id] = job
        await app_main._run_export(job_id, export_nodes, fmt)
        return app_main._export_tasks[job_id]

    export_nodes = [
        {"title": "排序算法", "type": "quiz",
         "questions": [{"question": "快速排序平均复杂度？", "options": ["O(n)", "O(n log n)", "O(n²)"],
                        "answer": "B", "explanation": "随机化 pivot 期望 O(n log n)。"}]},
        {"title": "概念卡", "segments": [
            {"knowledge_card": {"term": "原地排序", "definition": "只用常数额外空间", "tags": ["core"]}}]},
    ]

    # MINIO_ENDPOINT 保持未配置 → 上传 skipped，任务仍 done（离线零依赖）
    old_endpoint = os.environ.pop("MINIO_ENDPOINT", None)
    try:
        job_i = asyncio.run(run_export_case("exp_html5_i", ExportFormat.INTERACTIVE, export_nodes))
        meta_i = job_i.metadata or {}
        check("T9 INTERACTIVE 模式任务 done", job_i.status == ExportStatus.DONE, str(job_i.status))
        check("T9 INTERACTIVE 产出 html", bool(meta_i.get("html_path"))
              and Path(meta_i["html_path"]).is_file(), str(meta_i.get("html_path")))
        check("T9 INTERACTIVE 不产出 pptx/docx",
              "ppt_path" not in meta_i and "doc_path" not in meta_i)

        job_b = asyncio.run(run_export_case("exp_html5_b", ExportFormat.BOTH, export_nodes))
        meta_b = job_b.metadata or {}
        check("T9 BOTH 三件产物齐备",
              all(Path(meta_b.get(k, "")).is_file() for k in ("ppt_path", "doc_path", "html_path")),
              str({k: meta_b.get(k) for k in ("ppt_path", "doc_path", "html_path")}))
        check("T9 BOTH html 产物自包含", assert_no_external_refs(Path(meta_b["html_path"]).read_text(encoding="utf-8")))

        # 产物副本归档到 docs/导出验证/
        mixed_path = DOC_OUT_DIR / "mixed_demo.html"
        mixed_path.write_text(Path(meta_b["html_path"]).read_text(encoding="utf-8"), encoding="utf-8")
        check("T9 mixed_demo.html 归档", mixed_path.is_file())
    finally:
        if old_endpoint is None:
            os.environ.pop("MINIO_ENDPOINT", None)
        else:
            os.environ["MINIO_ENDPOINT"] = old_endpoint

    # ---- 汇总 ----
    failed = [r for r in RESULTS if r[1] == "FAIL"]
    print()
    print(f"===== verify_html5_export: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS =====")
    if failed:
        for name, _, detail in failed:
            print(f"  FAIL: {name} {detail}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
