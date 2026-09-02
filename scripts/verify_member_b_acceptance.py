# -*- coding: utf-8 -*-
"""成员 B 最终验收：真实 LLM 教案质量 + 互动答案识别健壮性。

运行：python -X utf8 scripts/verify_member_b_acceptance.py

该脚本会真实调用项目配置的 LLM 一次，并在 docs/导出验证 下生成可人工打开的
DOCX 与 HTML 产物。任一质量门不满足时以非零状态退出。
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.core.config import settings
from ai_engine.gen.export_doc import LessonPlanDOCExporter
from ai_engine.gen.export_html5 import extract_interactive_items, render_interactive_html
from ai_engine.gen.lesson_plan import LessonPlanGenerator

OUT_DIR = PROJECT_ROOT / "docs" / "导出验证"

NODES = [
    {
        "node_id": "limit-1",
        "title": "函数极限的概念",
        "type": "content",
        "content": "通过邻域语言理解函数极限，并与数列极限建立联系。",
        "core_points": ["ε-N 定义", "数列极限与函数极限"],
        "segments": [{
            "knowledge_card": {
                "term": "ε-N 定义",
                "definition": "用任意 ε 与相应 N 的量词关系严格描述趋近过程。",
                "tags": ["重点"],
            }
        }],
    },
    {
        "node_id": "limit-2",
        "title": "极限的性质",
        "type": "content",
        "content": "结合例题辨析唯一性、有界性和保号性。",
        "core_points": ["唯一性", "有界性", "保号性"],
        "segments": [{
            "knowledge_card": {
                "term": "极限的保号性",
                "definition": "极限严格为正时，函数在充分靠近目标点处保持为正。",
                "tags": ["难点"],
            }
        }],
    },
    {
        "node_id": "limit-3",
        "title": "课堂练习",
        "type": "quiz",
        "content": "完成 ε-N 定义的分层练习。",
        "metadata": {
            "interactive": [{
                "type": "quiz",
                "title": "极限概念辨析",
                "questions": [
                    {"question": "ε-N 定义中首先任意给定的是？",
                     "options": ["ε", "N", "函数值", "自变量"], "answer": "答案为A"},
                    {"question": "极限若存在，其个数是？",
                     "options": ["0个", "唯一", "两个", "无穷多个"], "answer": "正确答案：Ｂ．"},
                    {"question": "保号性对应哪项？",
                     "options": ["A. 唯一", "B. 有界", "C. 保持符号", "D. 周期"],
                     "answer": {"correct_answer": "C. 保持符号"}},
                    {"question": "无法由材料唯一判定的题目",
                     "options": ["甲", "乙", "丙", "丁"], "answer": "需结合上下文判断"},
                ],
            }]
        },
    },
    {
        "node_id": "limit-4",
        "title": "课堂小结",
        "type": "summary",
        "content": "回顾极限思想、量词关系与严谨表达。",
        "core_points": ["极限思想", "严谨表达"],
    },
]

INTENT = {
    "topic": "函数极限",
    "duration_minutes": 45,
    "target_student": "大学一年级理工科学生",
    "style": "启发式互动教学",
    "knowledge_points": ["ε-N 定义", "极限的性质"],
    "key_difficulties": ["ε-N 定义中的量词关系"],
    "with_interactive": True,
}


def fail(message: str) -> None:
    raise AssertionError(message)


def validate_lesson_plan(plan) -> None:
    if plan.data_source != "llm":
        fail(f"真实模型未生效，data_source={plan.data_source}")
    if plan.course_name != INTENT["topic"]:
        fail(f"课程名未服从教师意图：{plan.course_name}")
    if plan.duration_minutes != INTENT["duration_minutes"]:
        fail(f"总课时错误：{plan.duration_minutes}")
    dimensions = {item.get("dimension") for item in plan.teaching_objectives}
    required_dimensions = {"知识目标", "能力目标", "素养目标"}
    if not required_dimensions.issubset(dimensions):
        fail(f"三维目标不完整：{dimensions}")
    if not plan.key_difficulties.get("key_points") or not plan.key_difficulties.get("difficult_points"):
        fail("重点或难点为空")
    if not plan.teaching_methods:
        fail("教学方法为空")
    phases = {phase.phase: phase for phase in plan.teaching_process}
    for phase_name in ("导入", "新授", "练习", "小结"):
        phase = phases.get(phase_name)
        if not phase:
            fail(f"缺少教学阶段：{phase_name}")
        if not all((phase.teacher_activity, phase.student_activity, phase.design_intent)):
            fail(f"教学阶段存在空字段：{phase_name}")
    if sum(phase.duration_minutes for phase in plan.teaching_process) != plan.duration_minutes:
        fail("教学阶段时长之和不等于总课时")
    if not plan.classroom_activities or not plan.homework or not plan.board_design:
        fail("课堂活动、作业或板书设计存在空章节")
    serialized = json.dumps(plan.to_dict(), ensure_ascii=False)
    placeholders = ("待补充", "待完善", "TODO", "TBD", "Lorem ipsum")
    if any(token.lower() in serialized.lower() for token in placeholders):
        fail("教案包含占位文本")


def validate_interactive() -> str:
    items = extract_interactive_items(NODES)
    quizzes = [item for item in items if item.get("type") == "quiz"]
    cards = [item for item in items if item.get("type") == "flashcard"]
    if len(quizzes) != 1 or len(quizzes[0]["questions"]) != 4:
        fail("互动题目抽取数量错误")
    answers = [question["answer"] for question in quizzes[0]["questions"]]
    if answers != [0, 1, 2, None]:
        fail(f"答案归一化错误：{answers}")
    if len(cards) < 2 or any(not card.get("front") or not card.get("back") for card in cards):
        fail("知识翻卡缺少正面或背面内容")
    html = render_interactive_html(items, course_name=INTENT["topic"], title="互动课堂")
    if "null" not in html or "q.answer" not in html or "知识翻卡" not in html:
        fail("HTML5 产物未保留安全的不判分路径或翻卡功能")
    return html


def main() -> int:
    if settings.is_mock or not settings.API_KEY:
        print("[FAIL] 未配置真实 LLM，无法完成成员 B 验收")
        return 2

    print(f"[INFO] real LLM: model={settings.MODEL}, timeout={settings.LLM_TIMEOUT}s")
    plan = LessonPlanGenerator().generate(NODES, INTENT)
    validate_lesson_plan(plan)
    print("[PASS] B-1 真实 LLM 教案：章节完整、无占位、时长一致")

    html = validate_interactive()
    print("[PASS] B-2 互动答案识别：常见格式、嵌套格式与不误判路径通过")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    docx_path = OUT_DIR / "member_b_lesson_plan.docx"
    html_path = OUT_DIR / "member_b_interactive.html"
    json_path = OUT_DIR / "member_b_lesson_plan.json"
    docx_path.write_bytes(LessonPlanDOCExporter().export_to_bytes(plan).getvalue())
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[PASS] 验收产物：{docx_path.relative_to(PROJECT_ROOT)}")
    print(f"[PASS] 验收产物：{html_path.relative_to(PROJECT_ROOT)}")
    print(f"[PASS] 结构证据：{json_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(1)
