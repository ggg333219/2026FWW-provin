"""教学表达规划器（gen/teaching_plan.py）的单元测试。

这一层回答的是「这个知识点应该怎么教」——链路里此前缺失的那一步。测试要锁住的
不是"模型输出好不好"，而是三件确定性的事：

1. **唯一决策点**：表达形式只在规划器里决定一次，``plan_to_figure`` 是机械映射，
   同一份 plan 恒等输出；下游不得再决策一次。
2. **反 AI 自嗨是硬约束**：``none`` 是合法的、常见的答案；prompt 之外还有代码级
   配额兜底，出图页数超比例就按结构性强弱截断为 ``none``。
3. **脏数据不抛异常**：规划失败退化成"这页没有规划"，绝不拖垮整份课件的渲染。
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_engine.gen import teaching_plan as tp  # noqa: E402
from ai_engine.gen.page_spec import (  # noqa: E402
    ROLE_PRIMARY,
    build_page_spec,
    normalize_conclusion,
    normalize_figure,
)


# =============================================================================
# 工具
# =============================================================================

class _StubLLM:
    """替身：记录调用并按预设返回，绝不联网。"""

    def __init__(self, payload):
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    def chat_json(self, system, user, **kwargs):
        self.calls.append((system, user))
        return self.payload


@pytest.fixture
def no_llm(monkeypatch):
    """强制走确定性兜底路径（等价于 AI_GEN_MODE=mock）。"""
    monkeypatch.setattr(tp, "_use_llm", lambda llm: None)


def _nodes(n: int = 3) -> list[dict]:
    return [
        {"node_id": f"n{i}", "type": "content", "title": f"知识点{i}",
         "summary": f"第{i}个知识点的说明。", "key_points": [f"要点{i}"]}
        for i in range(1, n + 1)
    ]


def _flow_plan(node_id: str = "n1", items: int = 3) -> dict:
    return {
        "node_id": node_id,
        "knowledge_point": "Agent Loop",
        "teaching_goal": "理解 Agent 为什么需要循环执行",
        "key_conclusion": "复杂任务需要多次 Tool Call",
        "visual_type": "flow",
        "visual_structure": [f"步骤{i}" for i in range(1, items + 1)],
        "teacher_note": "强调一次 Tool Call 通常只能完成一个局部动作。",
    }


# =============================================================================
# 1. plan_to_figure：机械映射，无第二次决策
# =============================================================================

def test_plan_to_figure_is_deterministic():
    plan = tp.normalize_plan(_flow_plan())
    first, second = tp.plan_to_figure(plan), tp.plan_to_figure(plan)

    assert first == second
    assert first == {"kind": "flow", "title": "复杂任务需要多次 Tool Call",
                     "items": ["步骤1", "步骤2", "步骤3"]}


@pytest.mark.parametrize("plan,expected", [
    (None, None),
    ("flow", None),
    ([], None),
    ({}, None),
    ({"visual_type": "none", "visual_structure": None}, None),
    ({"visual_type": "", "visual_structure": ["甲", "乙"]}, None),
    ({"visual_type": "treemap", "visual_structure": ["甲"]}, None),
])
def test_plan_to_figure_refuses_to_draw(plan, expected):
    """none / 未登记 / 非 dict 一律不画 —— 机械映射不做任何补救性猜测。"""
    assert tp.plan_to_figure(plan) is expected


def test_plan_to_figure_falls_back_to_knowledge_point_for_title():
    plan = tp.normalize_plan({**_flow_plan(), "key_conclusion": ""})
    assert tp.plan_to_figure(plan)["title"] == "Agent Loop"


def test_plan_to_figure_is_independent_of_normalization():
    """契约：plan_to_figure 只搬运、不校验 —— 同一份意图走不走 normalize 翻出来的图一样。"""
    raw = _flow_plan()
    assert tp.plan_to_figure(tp.normalize_plan(raw)) == tp.plan_to_figure(raw)


# =============================================================================
# 2. 规划输出必须活过 page_spec 的校验（唯一裁判）
# =============================================================================

@pytest.mark.parametrize("raw,expected_kind", [
    (_flow_plan(), "flow"),
    ({"node_id": "n1", "teaching_goal": "G", "visual_type": "cycle",
      "visual_structure": ["计划", "执行", "检查"]}, "cycle"),
    ({"node_id": "n1", "teaching_goal": "G", "visual_type": "hierarchy",
      "visual_structure": ["排序算法", "比较类", "非比较类"]}, "hierarchy"),
    ({"node_id": "n1", "teaching_goal": "G", "visual_type": "compare",
      "visual_structure": {"left": {"title": "冒泡", "items": ["稳定"]},
                           "right": {"title": "快排", "items": ["不稳定"]}}}, "compare"),
    ({"node_id": "n1", "teaching_goal": "G", "visual_type": "chart",
      "visual_structure": [{"label": "冒泡", "value": 45},
                           {"label": "快排", "value": 12}]}, "chart"),
    ({"node_id": "n1", "teaching_goal": "G", "visual_type": "matrix",
      "visual_structure": {"columns": ["算法", "稳定性"],
                           "rows": [["冒泡排序", "稳定"]]}}, "matrix"),
])
def test_plan_figure_survives_page_spec_validation(raw, expected_kind):
    """规划器认的形态必须正是 page_spec 认的形态 —— 否则链路中间会静默丢图。"""
    plan = tp.normalize_plan(raw)
    assert plan and plan["visual_type"] == expected_kind

    figure = tp.plan_to_figure(plan)
    assert figure is not None, "规划说出图，却翻不出 figure"
    assert normalize_figure({"figure": figure}) is not None, "page_spec 不认这个 figure"


@pytest.mark.parametrize("raw", [
    {"node_id": "n1", "teaching_goal": "G", "visual_type": "flow",
     "visual_structure": [{"label": "单条"}]},                       # 一条构不成关系
    {"node_id": "n1", "teaching_goal": "G", "visual_type": "chart",
     "visual_structure": [{"label": "只有一项", "value": 90}]},       # 一根柱子
    {"node_id": "n1", "teaching_goal": "G", "visual_type": "chart",
     "visual_structure": [{"label": "甲", "value": "不是数"},
                          {"label": "乙", "value": 5}]},             # 一项非数 → 只剩一项
    {"node_id": "n1", "teaching_goal": "G", "visual_type": "matrix",
     "visual_structure": {"columns": [], "rows": []}},               # 没有列
    {"node_id": "n1", "teaching_goal": "G", "visual_type": "compare",
     "visual_structure": {"left": {"items": []}, "right": {"items": []}}},
])
def test_unusable_structure_is_demoted_to_none(raw):
    """画不出来的结构如实记成 none —— 不留下"plan 说出图、下游画不出"的裂缝。"""
    plan = tp.normalize_plan(raw)
    assert plan is not None
    assert plan["visual_type"] == "none" and plan["visual_structure"] is None


def test_plan_structure_records_what_will_actually_be_drawn():
    """plan 里存的是规范化**之后**的形态，所以人工审阅 plan 表看到的就是实际结果。"""
    plan = tp.normalize_plan({
        "node_id": "n1", "teaching_goal": "G", "visual_type": "matrix",
        "visual_structure": {"columns": ["算法", "稳定性"], "rows": [["冒泡排序"], ["快排", "不稳定", "多出来的一格"]]},
    })

    assert plan["visual_structure"]["rows"] == [["冒泡排序", ""], ["快排", "不稳定"]]
    assert tp.plan_to_figure(plan)["rows"] == plan["visual_structure"]["rows"]


# =============================================================================
# 3. 脏输入一律不抛异常
# =============================================================================

@pytest.mark.parametrize("raw", [
    None, "flow", [], 42, (),
    {},                                                  # 什么都没有
    {"teaching_goal": "", "key_conclusion": "", "teacher_note": "", "visual_type": "none"},
    {"visual_type": "treemap", "visual_structure": ["甲"]},
    {"visual_type": "flow", "visual_structure": "甲"},    # 字符串不是列表
    {"visual_type": "matrix", "visual_structure": ["甲"]},  # 形态不对
    {"visual_type": None, "visual_structure": None},
    {"visual_type": "flow", "visual_structure": [None, "", {}]},   # 全是空标签
])
def test_normalize_plan_never_raises(raw):
    result = tp.normalize_plan(raw)
    assert result is None or isinstance(result, dict)


def test_normalize_plan_fills_the_full_shape():
    """拿到手的 plan 一定是完整形态 —— 调用方不必再 .get(k, default)。"""
    plan = tp.normalize_plan({"node_id": "n7", "teaching_goal": "G"})

    assert set(plan) == {"node_id", "knowledge_point", "teaching_goal", "key_conclusion",
                         "visual_type", "visual_structure", "teacher_note", "density"}
    assert plan["node_id"] == "n7"
    assert plan["visual_type"] == "none" and plan["density"] == "standard"


def test_normalize_plan_rejects_unregistered_visual_type():
    plan = tp.normalize_plan({"teaching_goal": "G", "visual_type": "venn",
                              "visual_structure": ["甲", "乙"]})
    assert plan["visual_type"] == "none"


def test_normalize_plan_uses_fallback_node_id():
    plan = tp.normalize_plan({"teaching_goal": "G"}, "n9")
    assert plan["node_id"] == "n9"


# =============================================================================
# 4. 配额：不依赖模型自觉的那道闸
# =============================================================================

def test_apply_figure_quota_truncates_to_ratio():
    """10 页全判出图 → 只留 60%，其余改判 none。"""
    plans = {
        f"n{i}": {"visual_type": "flow", "visual_structure": ["甲", "乙", "丙"]}
        for i in range(10)
    }
    out = tp.apply_figure_quota(plans)

    drawing = [k for k, p in out.items() if p["visual_type"] != "none"]
    assert len(drawing) == 6, "配额 0.6 × 10 = 6"
    for key in out:
        if out[key]["visual_type"] == "none":
            assert out[key]["visual_structure"] is None, "改判 none 时结构要一起清掉"


def test_apply_figure_quota_keeps_the_structurally_strongest():
    """截断按结构性强弱：流程图比层级图更值得占版面。"""
    plans = {f"f{i}": {"visual_type": "flow", "visual_structure": ["甲", "乙"]} for i in range(6)}
    plans.update({f"h{i}": {"visual_type": "hierarchy", "visual_structure": ["甲", "乙"]} for i in range(4)})

    out = tp.apply_figure_quota(plans)

    assert all(out[f"f{i}"]["visual_type"] == "flow" for i in range(6))
    assert all(out[f"h{i}"]["visual_type"] == "none" for i in range(4))


def test_apply_figure_quota_does_not_mutate_input():
    plans = {f"n{i}": {"visual_type": "flow", "visual_structure": ["甲", "乙"]} for i in range(10)}
    snapshot = copy.deepcopy(plans)

    tp.apply_figure_quota(plans)

    assert plans == snapshot


def test_apply_figure_quota_leaves_small_decks_alone():
    plans = {"n1": {"visual_type": "flow", "visual_structure": ["甲", "乙"]},
             "n2": {"visual_type": "none", "visual_structure": None}}
    assert tp.apply_figure_quota(plans) == plans


def test_apply_figure_quota_always_allows_at_least_one_figure():
    """两页里两页都想出图时不能全砍光 —— 至少留一张，否则课件只剩文字。"""
    plans = {"n1": {"visual_type": "flow", "visual_structure": ["甲", "乙"]},
             "n2": {"visual_type": "flow", "visual_structure": ["甲", "乙"]}}
    out = tp.apply_figure_quota(plans)
    assert any(p["visual_type"] == "flow" for p in out.values())


def test_apply_figure_quota_counts_only_content_pages():
    """结构性页不进分母 —— 否则配额被凭空放宽到形同虚设。"""
    plans = {f"c{i}": {"visual_type": "flow", "visual_structure": ["甲", "乙"]} for i in range(6)}
    plans.update({f"s{i}": {"visual_type": "none", "visual_structure": None} for i in range(4)})

    out = tp.apply_figure_quota(plans, content_ids={f"c{i}" for i in range(6)})

    drawing = [k for k, p in out.items() if p["visual_type"] != "none"]
    assert len(drawing) == 3, "6 个内容页 × 0.6 = 3，而不是 10 页 × 0.6 = 6"


def test_plan_deck_applies_quota(no_llm):
    """10 页都是"想画图"的内容页 → 配额必须真的咬住。"""
    nodes = [{"node_id": f"n{i}", "type": "content", "title": f"流程{i}",
              "summary": "首先甲，然后乙，最后丙。"} for i in range(10)]

    plans = tp.plan_deck({}, nodes)

    drawing = [p for p in plans.values() if p["visual_type"] != "none"]
    assert 0 < len(drawing) <= 6, "既不能全放过，也不能全砍光"


def test_plan_deck_quota_ignores_structural_pages(no_llm):
    """封面/目录/测验/小结混进来时，配额仍只按 6 个内容页算。"""
    nodes = [{"node_id": f"c{i}", "type": "content", "title": f"流程{i}",
              "summary": "首先甲，然后乙，最后丙。"} for i in range(6)]
    nodes += [{"node_id": "p_cover", "type": "cover", "title": "封面"},
              {"node_id": "p_sec", "type": "section", "title": "目录"},
              {"node_id": "p_quiz", "type": "quiz", "title": "测验"},
              {"node_id": "p_sum", "type": "summary", "title": "小结"}]

    plans = tp.plan_deck({}, nodes)

    assert all(plans[k]["visual_type"] == "none" for k in ("p_cover", "p_sec", "p_quiz", "p_sum"))
    drawing = [p for p in plans.values() if p["visual_type"] != "none"]
    assert len(drawing) == 3


# =============================================================================
# 5. plan_deck / plan_node
# =============================================================================

def test_plan_deck_covers_every_node(no_llm):
    plans = tp.plan_deck({}, _nodes(4))
    assert set(plans) == {"n1", "n2", "n3", "n4"}


def test_plan_deck_returns_empty_for_no_nodes(no_llm):
    assert tp.plan_deck({}, []) == {}
    assert tp.plan_deck({}, [None, "不是节点"]) == {}


def test_plan_deck_works_without_intent(no_llm):
    """intent 缺席是合法输入 —— Go 侧补不到 intent 时链路必须照常走完。"""
    assert set(tp.plan_deck(None, _nodes(2))) == {"n1", "n2"}
    assert set(tp.plan_deck({}, _nodes(2))) == {"n1", "n2"}


def test_plan_deck_falls_back_per_node_when_llm_is_silent():
    """模型漏了某几页 → 只有那几页退兜底，不能整批报废。"""
    stub = _StubLLM({"plans": [_flow_plan("n1")]})
    plans = tp.plan_deck({"topic": "排序算法"}, _nodes(3), llm=stub)

    assert set(plans) == {"n1", "n2", "n3"}
    assert plans["n1"]["key_conclusion"] == "复杂任务需要多次 Tool Call"
    assert plans["n2"]["node_id"] == "n2"


def test_plan_deck_drops_fabricated_node_ids():
    stub = _StubLLM({"plans": [_flow_plan("n1"), _flow_plan("n99")]})
    plans = tp.plan_deck({}, _nodes(2), llm=stub)

    assert "n99" not in plans
    assert set(plans) == {"n1", "n2"}


def test_plan_deck_survives_a_broken_llm(monkeypatch):
    """规划调用抛异常 → 整批退兜底，绝不冒泡到调用方。"""
    class _Broken:
        def chat_json(self, *a, **kw):
            raise RuntimeError("模型挂了")

    plans = tp.plan_deck({}, _nodes(3), llm=_Broken())
    assert set(plans) == {"n1", "n2", "n3"}


def test_plan_node_does_not_apply_quota():
    """单页重规划不套配额 —— 教师明确要求的那一页不该被全局配额砍掉。"""
    node = {"node_id": "n1", "type": "content", "title": "循环",
            "summary": "首先判断，然后调用工具，最后回到判断。"}
    plan = tp.plan_node({}, node, llm=_StubLLM({"plans": [_flow_plan("n1")]}))
    assert plan["visual_type"] == "flow"


def test_plan_node_falls_back_on_unusable_reply():
    node = {"node_id": "n1", "type": "content", "title": "知识点", "key_points": ["甲"]}
    plan = tp.plan_node({}, node, llm=_StubLLM({"plans": []}))
    assert plan["node_id"] == "n1" and plan["visual_type"] in tp.VISUAL_TYPES


# =============================================================================
# 6. 教学意图进了提示词
# =============================================================================

def test_intent_brief_carries_the_fields_that_change_expression():
    brief = tp._intent_brief({
        "topic": "排序算法", "target_student": "大二学生", "style": "案例驱动",
        "key_difficulties": ["复杂度分析"], "expected_outcomes": "能选对算法",
    })

    for token in ("排序算法", "大二学生", "案例驱动", "复杂度分析", "能选对算法"):
        assert token in brief


@pytest.mark.parametrize("intent", [None, {}, {"topic": ""}, "不是字典", 42])
def test_intent_brief_is_empty_for_absent_intent(intent):
    assert tp._intent_brief(intent) == ""


def test_plan_deck_passes_intent_and_nodes_to_the_model():
    stub = _StubLLM({"plans": []})
    tp.plan_deck({"topic": "排序算法", "style": "案例驱动"}, _nodes(2), llm=stub)

    system, user = stub.calls[0]
    assert "什么时候不该出图" in system, "反自嗨判据必须进系统提示词"
    assert "排序算法" in user and "案例驱动" in user
    assert "知识点1" in user and "知识点2" in user


def test_plan_deck_passes_evidence_and_forbids_fabrication():
    stub = _StubLLM({"plans": []})
    tp.plan_deck({}, _nodes(1), evidence="大O表示法描述增长趋势。", llm=stub)

    user = stub.calls[0][1]
    assert "大O表示法描述增长趋势。" in user
    assert "不得编造" in user


# =============================================================================
# 7. 兜底启发式（原导出侧的决策逻辑，降级为"没有 LLM 时"的确定性路径）
# =============================================================================

def test_heuristic_plan_detects_a_process_from_sequence_words():
    node = {"node_id": "n1", "type": "content", "title": "Agent Loop",
            "summary": "首先 LLM 判断，然后调用工具，接着拿到结果，最后再次判断。"}
    plan = tp.heuristic_plan(node)

    assert plan["visual_type"] == "flow"
    assert len(plan["visual_structure"]) >= 2
    assert all("首先" not in step for step in plan["visual_structure"]), "顺序词应被剥掉"


def test_heuristic_plan_detects_numbers_as_a_chart():
    node = {"node_id": "n1", "type": "content", "title": "占比",
            "content": "冒泡排序耗时占比 45%，快速排序 12%，归并排序 10%。"}
    plan = tp.heuristic_plan(node)

    assert plan["visual_type"] == "chart"
    assert [s["value"] for s in plan["visual_structure"]] == [45.0, 12.0, 10.0]


def test_heuristic_plan_refuses_to_draw_for_a_single_point():
    """单一要点构不成关系 —— 这正是「不该出图」的默认行为，不是兜底失败。"""
    node = {"node_id": "n1", "type": "content", "title": "定义", "key_points": ["算法是求解步骤的集合"]}
    assert tp.heuristic_plan(node)["visual_type"] == "none"


@pytest.mark.parametrize("node_type", ["cover", "section", "quiz", "interactive", "summary"])
def test_heuristic_plan_never_draws_on_structural_pages(node_type):
    """封面 / 目录 / 测验 / 小结的表达形式已由页型定死，再配图是重复排版。"""
    node = {"node_id": "n1", "type": node_type, "title": "标题",
            "summary": "首先甲，然后乙，接着丙。", "key_points": ["甲", "乙"]}
    assert tp.heuristic_plan(node)["visual_type"] == "none"


def test_heuristic_plan_is_deterministic():
    node = {"node_id": "n1", "type": "content", "title": "流程",
            "summary": "首先甲，然后乙，最后丙。"}
    assert tp.heuristic_plan(node) == tp.heuristic_plan(node)


def test_heuristic_conclusion_obeys_the_display_rule():
    """兜底规划器不能承诺一句最终渲染不出来的结论。"""
    usable = {"node_id": "n1", "type": "content", "title": "排序",
              "summary": "每一轮把最大值送到末尾。"}
    # 按句切分时句末标点一并去掉：大字结论是幻灯片上的一句断言，末尾挂句号是排版噪音
    assert tp.heuristic_plan(usable)["key_conclusion"] == "每一轮把最大值送到末尾"

    too_long = {"node_id": "n2", "type": "content", "title": "长文", "summary": "长" * 80 + "。"}
    assert tp.heuristic_plan(too_long)["key_conclusion"] == ""


def test_heuristic_keeps_a_conclusion_the_node_already_has():
    """节点自带 key_conclusion 时不得被 summary 的首句覆盖。

    小结页往往只有 key_conclusion、没有 summary —— 旧实现只看 summary，这类页在
    plan 表和幻灯片上都会变成空白。
    """
    node = {"node_id": "p_sum", "type": "summary", "title": "小结",
            "key_conclusion": "选择算法要结合数据规模"}
    assert tp.heuristic_plan(node)["key_conclusion"] == "选择算法要结合数据规模"

    # 超长 / 非字符串仍然按「不可用」处理，不会被原样带进 plan
    over = dict(node, key_conclusion="长" * 80, summary="短句。")
    assert tp.heuristic_plan(over)["key_conclusion"] == "短句"
    dirty = dict(node, key_conclusion=123)
    assert tp.heuristic_plan(dirty)["key_conclusion"] == ""


def test_heuristic_plan_on_a_bare_node_still_returns_a_plan():
    plan = tp.heuristic_plan({})
    assert plan["visual_type"] == "none" and set(plan) == {
        "node_id", "knowledge_point", "teaching_goal", "key_conclusion",
        "visual_type", "visual_structure", "teacher_note", "density"}


# =============================================================================
# 8. 接入 page_spec：大字结论 + 图示真的上幻灯片
# =============================================================================

def _planned_node() -> dict:
    node = {
        "node_id": "n1", "type": "content", "title": "冒泡排序",
        "summary": "相邻比较，逆序交换。",
        "key_points": ["每轮确定一个最大值"],
        "point_details": [{"point": "每轮确定一个最大值",
                           "detail": "第 i 轮结束后，末尾 i 个元素已就位。"}],
    }
    plan = tp.normalize_plan({
        "node_id": "n1", "knowledge_point": "冒泡排序",
        "teaching_goal": "理解一轮比较做了什么",
        "key_conclusion": "每一轮把当前最大值送到末尾",
        "visual_type": "flow",
        "visual_structure": ["比较相邻两项", "逆序则交换", "指针后移"],
        "teacher_note": "口头补充：交换次数等于逆序对数量。",
    })
    node["teaching_plan"] = plan
    node["key_conclusion"] = plan["key_conclusion"]
    node["figure"] = tp.plan_to_figure(plan)
    return node


def test_content_page_order_is_total_then_detail():
    """figure → text → conclusion → details：先"总"后"分"，细节给结论作注脚。"""
    spec = build_page_spec(_planned_node(), 1)
    assert [b.kind for b in spec.blocks if b.role == ROLE_PRIMARY] == \
        ["figure", "text", "conclusion", "details"]


def test_teaching_plan_round_trips_into_the_preview():
    from ai_engine.gen.preview import PreviewRenderer

    html = PreviewRenderer().render([_planned_node()], course_name="测试")

    assert '<section class="conclusion-block">' in html
    assert "每一轮把当前最大值送到末尾" in html
    for label in ("比较相邻两项", "逆序则交换", "指针后移"):
        assert label in html, f"图示标签 {label} 没进预览"
    # 教师口语补充只留在 plan 里，不该出现在幻灯片上
    assert "口头补充：交换次数等于逆序对数量。" not in html


def test_conclusion_comes_from_teaching_plan_when_node_lacks_it():
    node = _planned_node()
    node.pop("key_conclusion")
    assert normalize_conclusion(node) == "每一轮把当前最大值送到末尾"


@pytest.mark.parametrize("node,expected", [
    ({}, ""),
    ({"key_conclusion": "   "}, ""),
    ({"key_conclusion": "一句话结论"}, "一句话结论"),
    ({"key_conclusion": "结" * 61}, ""),            # 超长：模型把整段正文塞进来了
    ({"key_conclusion": "结" * 60}, "结" * 60),
    ({"key_conclusion": 123}, ""),                  # 非字符串
])
def test_normalize_conclusion_guards(node, expected):
    assert normalize_conclusion(node) == expected


def test_legacy_node_gets_no_conclusion_block():
    spec = build_page_spec({"type": "content", "title": "旧课件", "key_points": ["甲"]}, 1)
    assert "conclusion" not in [b.kind for b in spec.blocks]


def test_plan_without_figure_still_yields_a_conclusion():
    """规划器判 none 的页面靠大字结论承担教学目的 —— 这是「不出图」不等于「没内容」。"""
    plan = tp.normalize_plan({
        "node_id": "n1", "teaching_goal": "记住定义",
        "key_conclusion": "算法是求解步骤的有穷集合",
        "visual_type": "none", "visual_structure": None,
        "teacher_note": "举例：从家到学校也是一串步骤。",
    })
    node = {"node_id": "n1", "type": "content", "title": "定义",
            "key_conclusion": plan["key_conclusion"], "teaching_plan": plan,
            "figure": tp.plan_to_figure(plan)}

    spec = build_page_spec(node, 1)
    assert "figure" not in [b.kind for b in spec.blocks]
    assert "conclusion" in [b.kind for b in spec.blocks]


# =============================================================================
# 9. 人工审阅用的 plan 表
# =============================================================================

def test_format_plan_table_shows_every_page_and_the_ratio(no_llm):
    """表是给人看的：每页一行，且必须能一眼看出出图比例是否超标。"""
    nodes = [{"node_id": f"c{i}", "type": "content", "title": f"流程{i}",
              "summary": "首先甲，然后乙，最后丙。"} for i in range(4)]
    nodes.append({"node_id": "p_sum", "type": "summary", "title": "小结",
                  "key_conclusion": "选择算法要结合数据规模"})

    table = tp.format_plan_table(tp.plan_deck({}, nodes))
    rows = [ln for ln in table.splitlines() if ln.strip()]

    assert "node_id" in table
    assert all(f"c{i}" in table for i in range(4))
    assert "p_sum" in table and "选择算法要结合数据规模" in table
    # 4 个内容页都想出图，配额 0.6 → 只留 2 页；表上要能直接读出这个数
    assert "共 5 页" in table and "出图 2 页" in table
    assert f"{int(tp.MAX_FIGURE_PAGE_RATIO * 100)}%" in table
    assert len(rows) == len(nodes) + 4, "表头 + 分隔线 ×2 + 5 行 + 汇总行"


def test_format_plan_table_renders_each_structure_shape():
    """四种结构形态都要能压成一行 —— 压不出来会让审阅者跳过整列。"""
    briefs = {
        "flow": tp._structure_brief(["甲", "乙"]),
        "chart": tp._structure_brief([{"label": "冒泡", "value": 45}]),
        "matrix": tp._structure_brief({"columns": ["算法", "稳定性"], "rows": [["冒泡", "稳定"]]}),
        "compare": tp._structure_brief({"left": {"title": "左", "items": ["甲"]},
                                        "right": {"title": "右", "items": ["乙"]}}),
    }
    assert briefs["flow"] == "甲 → 乙"
    assert briefs["chart"] == "冒泡=45"
    assert briefs["matrix"] == "[算法、稳定性] × 1行"
    assert "左(甲)" in briefs["compare"] and "右(乙)" in briefs["compare"]
    assert tp._structure_brief(None) == "—"


def test_clip_counts_cjk_as_two_columns():
    """中文按两列算，否则表格会参差不齐。"""
    assert tp._clip("中文中文中文", 6) == "中文…"
    assert tp._clip("abcdef", 6) == "abcdef"
    assert tp._display_width("中文") == 4
    assert tp._display_width("ab") == 2
