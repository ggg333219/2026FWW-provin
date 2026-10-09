from ai_engine.gen.lesson_plan import LessonPlanGenerator
from ai_engine.gen.lesson_plan_cache import (
    clear_lesson_plan_cache,
    generate_lesson_plan_cached,
)


def test_lesson_plan_cache_reuses_memory_and_disk_result(tmp_path, monkeypatch):
    monkeypatch.setenv("LESSON_PLAN_CACHE_DIR", str(tmp_path))
    clear_lesson_plan_cache()
    calls = {"count": 0}

    def fake_generate(self, nodes, intent, markdown, generation_instruction_set):
        calls["count"] += 1
        return {
            "course_name": intent["topic"],
            "data_source": "llm",
            "teaching_process": [],
        }

    monkeypatch.setattr(LessonPlanGenerator, "generate", fake_generate)
    inputs = ([{"title": "快速排序"}], {"topic": "排序算法"}, {})

    first = generate_lesson_plan_cached(*inputs)
    second = generate_lesson_plan_cached(*inputs)
    assert first == second
    assert calls["count"] == 1

    # 模拟 AI Engine 重启：清除进程内缓存，但保留磁盘缓存。
    clear_lesson_plan_cache()
    third = generate_lesson_plan_cached(*inputs)
    assert third == first
    assert calls["count"] == 1


def test_fallback_plan_is_not_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("LESSON_PLAN_CACHE_DIR", str(tmp_path))
    clear_lesson_plan_cache()
    calls = {"count": 0}

    def fake_generate(self, nodes, intent, markdown, generation_instruction_set):
        calls["count"] += 1
        return {
            "course_name": intent["topic"],
            "data_source": "fallback",
            "teaching_process": [],
        }

    monkeypatch.setattr(LessonPlanGenerator, "generate", fake_generate)
    inputs = ([{"title": "快速排序"}], {"topic": "排序算法"}, {})

    generate_lesson_plan_cached(*inputs)
    clear_lesson_plan_cache()
    generate_lesson_plan_cached(*inputs)
    assert calls["count"] == 2
