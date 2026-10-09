"""教师讲稿须随 S3 版本节点进入标准 Word 教案。"""

from docx import Document
import pytest

from ai_engine.core.config import Settings
from ai_engine.gen import lesson_plan
from ai_engine.gen.export_doc import LessonPlanDOCExporter


NODES = [
    {
        "node_id": "n1",
        "title": "冒泡排序",
        "content": "幻灯片正文",
        "script": "先观察相邻元素。\n再演示交换过程。",
    },
    {
        "node_id": "n2",
        "title": "快速排序",
        "lecture_script": "通过基准元素讲解分区。",
    },
    {"node_id": "n3", "title": "练习", "content": "仅有课件正文"},
]


class StubLLM:
    def __init__(self, fail=False):
        self.fail = fail

    def chat_with_schema(self, *_args, **_kwargs):
        if self.fail:
            raise ConnectionError("offline test")
        return {
            "teaching_objectives": [{"dimension": "知识目标", "content": "掌握排序思想"}],
            "teaching_process": [{
                "phase": "新授", "duration_minutes": 35,
                "teacher_activity": "讲解算法", "student_activity": "观察演示",
                "design_intent": "理解算法",
            }],
        }


@pytest.mark.parametrize("fail", [False, True])
def test_teacher_scripts_are_copied_into_docx_for_llm_and_fallback(monkeypatch, fail):
    monkeypatch.setattr(lesson_plan, "settings", Settings(GEN_MODE="llm"))
    plan = lesson_plan.LessonPlanGenerator(llm_client=StubLLM(fail)).generate(
        NODES, {"topic": "排序算法", "duration_minutes": 45},
    )

    assert plan.data_source == ("fallback" if fail else "llm")
    assert [item["node_id"] for item in plan.teacher_scripts] == ["n1", "n2"]
    assert plan.teacher_scripts[0]["script"] == NODES[0]["script"]
    assert plan.to_dict()["teacher_scripts"] == plan.teacher_scripts

    doc = Document(LessonPlanDOCExporter().export_to_bytes(plan))
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert text.index("四、教学过程") < text.index("教师讲稿（按课件节点）")
    assert text.index("教师讲稿（按课件节点）") < text.index("五、课堂活动设计")
    assert "先观察相邻元素。\n再演示交换过程。" in text
    assert "通过基准元素讲解分区。" in text
    assert "仅有课件正文" not in text


def test_lesson_plan_without_scripts_keeps_existing_sections(monkeypatch):
    monkeypatch.setattr(lesson_plan, "settings", Settings(GEN_MODE="llm"))
    plan = lesson_plan.LessonPlanGenerator(llm_client=StubLLM()).generate(
        [{"node_id": "n1", "title": "排序算法", "content": "课件正文"}],
        {"topic": "排序算法"},
    )
    doc = Document(LessonPlanDOCExporter().export_to_bytes(plan))
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "教师讲稿（按课件节点）" not in text
    assert "四、教学过程" in text
    assert "五、课堂活动设计" in text
