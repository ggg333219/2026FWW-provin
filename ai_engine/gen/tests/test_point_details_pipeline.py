"""P2：point_details 穿过两级白名单，以及 patch 的合并语义。

链路里最容易**静默**丢字段的两处都在这里锁住：

  1. ``schema.normalize_stage3_scripts`` — 固定 key 白名单重建 dict
  2. ``NodeGenerator._normalize_enhanced_scripts`` — 另一份**不同**的白名单

漏掉任意一处，模型给的要点展开都会在到达 page_spec 之前消失，而其它测试全绿 ——
幻灯片上「要点展开」整块不见了，却没有任何报错。这正是 P1 只在预览侧生效、导出侧
拿不到内容那类 bug 的同一形状，所以必须两边都断言。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_engine.gen.commands import CommandType, EditCommand  # noqa: E402
from ai_engine.gen.node import NodeGenerator, _plan_constraint  # noqa: E402
from ai_engine.gen.patch import NodePatcher  # noqa: E402
from ai_engine.schema import normalize_point_details, normalize_stage3_scripts  # noqa: E402


# =============================================================================
# 1. 归一：口径与 page_spec 一致，脏数据一律退化
# =============================================================================

def test_point_details_keep_point_and_detail():
    assert normalize_point_details([{"point": "相邻比较", "detail": "每次只比一对。"}]) == [
        {"point": "相邻比较", "detail": "每次只比一对。"}
    ]


def test_point_details_accept_aliases():
    """模型爱用 title/text 代替 point/detail —— 认别名比丢整条划算。"""
    assert normalize_point_details([{"title": "甲", "text": "乙"}]) == [
        {"point": "甲", "detail": "乙"}
    ]


def test_point_details_fall_back_to_detail_when_point_missing():
    """只有展开没有标题时，用展开兜底 —— 不留只有标题没有内容的空壳。"""
    assert normalize_point_details([{"detail": "只有展开"}]) == [
        {"point": "只有展开", "detail": "只有展开"}
    ]


def test_point_details_drop_empty_entries():
    assert normalize_point_details([{"point": "", "detail": ""}, None, {"point": "甲"}]) == [
        {"point": "甲", "detail": ""}
    ]


def test_point_details_reject_dirty_input():
    for raw in (None, "不是列表", 42, {"point": "甲"}):
        assert normalize_point_details(raw) == []


# =============================================================================
# 2. 两级白名单都必须带上它
# =============================================================================

def _raw_script() -> dict:
    return {
        "node_id": "n1", "title": "冒泡排序", "script": "讲稿",
        "segments": [{"segment_id": "seg_001", "text": "开场", "node_id": "n1"}],
        "point_details": [{"point": "相邻比较", "detail": "每次只比一对。"}],
    }


def test_stage3_whitelist_carries_point_details():
    out = normalize_stage3_scripts([_raw_script()], {"n1"})

    assert out[0]["point_details"] == [{"point": "相邻比较", "detail": "每次只比一对。"}]


def test_enhanced_whitelist_carries_point_details():
    out = NodeGenerator._normalize_enhanced_scripts([_raw_script()], {"n1"})

    assert out[0]["point_details"] == [{"point": "相邻比较", "detail": "每次只比一对。"}]


# =============================================================================
# 3. 单节点生成：真的产出 point_details，并按规划约束写
# =============================================================================

class _StubLLM:
    def __init__(self, payload=None):
        self.payload = payload or {}
        self.calls: list[tuple[str, str]] = []

    def chat_json(self, system, user, **kwargs):
        self.calls.append((system, user))
        return self.payload


def test_generate_single_returns_point_details():
    llm = _StubLLM({
        "node_id": "n1", "title": "冒泡排序", "script": "讲稿",
        "segments": [{"segment_id": "seg_001", "text": "开场", "node_id": "n1"}],
        "point_details": [{"point": "相邻比较", "detail": "每次只比一对。"}],
    })
    out = NodeGenerator(llm_client=llm).generate_single({"node_id": "n1", "title": "冒泡排序"})

    assert out["point_details"] == [{"point": "相邻比较", "detail": "每次只比一对。"}]


def test_generate_single_without_point_details_yields_empty_list():
    """模型没给就落到空列表，而不是让 page_spec 去猜。"""
    llm = _StubLLM({"node_id": "n1", "title": "T", "script": "S", "segments": []})
    out = NodeGenerator(llm_client=llm).generate_single({"node_id": "n1", "title": "T"})

    assert out["point_details"] == []


def test_plan_is_injected_as_a_constraint():
    """写稿提示词必须带上本页已定的结论 —— 否则图示讲 A、讲稿讲 B。"""
    llm = _StubLLM({"node_id": "n1", "title": "T", "script": "S", "segments": []})
    plan = {"teaching_goal": "理解增长趋势", "key_conclusion": "复杂度描述增长趋势",
            "teacher_note": "口头补充常数项"}
    NodeGenerator(llm_client=llm).generate_single(
        {"node_id": "n1", "title": "T"}, teaching_plan=plan
    )

    _, user_prompt = llm.calls[0]
    assert "复杂度描述增长趋势" in user_prompt
    assert "理解增长趋势" in user_prompt
    assert "口头补充常数项" in user_prompt


def test_prompt_is_unchanged_without_a_plan():
    """不传 plan 时 prompt 与改动前逐字相同（向后兼容）。"""
    llm = _StubLLM({"node_id": "n1", "title": "T", "script": "S", "segments": []})
    NodeGenerator(llm_client=llm).generate_single({"node_id": "n1", "title": "T"})

    _, user_prompt = llm.calls[0]
    assert "本页教学规划" not in user_prompt


def test_plan_constraint_is_empty_for_missing_or_empty_plan():
    for plan in (None, "flow", {}, {"teaching_goal": "", "key_conclusion": "", "teacher_note": ""}):
        assert _plan_constraint(plan) == ""


# =============================================================================
# 4. 局部重生成：合并而非整体替换
# =============================================================================

def _rich_node() -> dict:
    return {
        "node_id": "n1", "type": "content", "node_type": "content",
        "title": "冒泡排序", "summary": "相邻两两比较。",
        "key_points": ["相邻比较", "O(n²)"],
        "script": "旧讲稿", "segments": [],
        "teaching_plan": {"visual_type": "flow", "key_conclusion": "每轮把最大值送到末尾"},
        "figure": {"kind": "flow", "items": ["比较", "交换"]},
        "point_details": [{"point": "旧要点", "detail": "旧展开"}],
    }


def _regenerate_only_script(node_id, node):
    """模仿 generate_single 的返回形状：只有少数几个 key。"""
    return {
        "node_id": node_id, "title": "冒泡排序", "script": "新讲稿",
        "segments": [{"segment_id": "seg_001", "text": "新开场", "node_id": node_id}],
        "point_details": [{"point": "新要点", "detail": "新展开"}],
    }


def test_patch_merges_instead_of_replacing_the_node():
    """整体替换会冲掉 type / summary / key_points / figure / teaching_plan。

    这些字段一丢，页面当场退化成"没有要点、没有图示"，而 error 列表是空的 ——
    教师只会看到内容莫名其妙变少了。
    """
    result = NodePatcher().apply(
        [_rich_node()],
        [EditCommand(type=CommandType.UPDATE_NODE,
                     params={"node_id": "n1", "regenerate": True})],
        regenerate_fn=_regenerate_only_script,
    )

    assert result.errors == []
    node = result.nodes[0]
    assert node["script"] == "新讲稿"
    assert node["point_details"] == [{"point": "新要点", "detail": "新展开"}]
    # 下面这些都必须还在
    assert node["type"] == "content"
    assert node["summary"] == "相邻两两比较。"
    assert node["key_points"] == ["相邻比较", "O(n²)"]
    assert node["teaching_plan"]["key_conclusion"] == "每轮把最大值送到末尾"
    assert node["figure"] == {"kind": "flow", "items": ["比较", "交换"]}
