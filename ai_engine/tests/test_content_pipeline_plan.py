"""P2：内容生成管道真的会做教学表达规划，并且不会把页面弄丢。

这里锁三件事：

  1. ``_plan_deck_safe`` / ``_attach_teaching_plan`` 的降级语义 —— 规划是加分项，
     拿不到 plan 时页面必须照常生成（老课件、规划服务挂掉都是这条路径）。
  2. ``req.intent`` 缺席是**合法输入**（Go 侧补不到 intent 时就是 None）。
  3. ``_run_content_pipeline`` 的增强分支：批量结果缺页要逐节点补，且**每个输入节点
     恰好产出一个输出节点**。改动前该分支既不赋值 merged 也不兜住缺页，首个节点
     UnboundLocalError、后续节点重复追加上一页 —— 页数翻倍是静默发生的。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_engine import main as main_module  # noqa: E402
from ai_engine.gen import teaching_plan as tp  # noqa: E402
from ai_engine.gen.node import NodeGenerator  # noqa: E402
from ai_engine.core.llm import LLMClient  # noqa: E402
from ai_engine.main import (  # noqa: E402
    GenContentRequest,
    _attach_teaching_plan,
    _plan_deck_safe,
    _run_content_pipeline,
)


@pytest.fixture(autouse=True)
def _deterministic_planner(monkeypatch):
    """强制规划器走确定性兜底：不碰网络，也不受 AI_GEN_MODE 影响。"""
    monkeypatch.setattr(tp, "_use_llm", lambda llm=None: None)
    # 证据加载会去找本地 RAG；这一组测试只关心 plan 与页数，给它一个空证据包。
    monkeypatch.setattr(main_module, "_load_page_evidence", lambda refs: ("", []))


# =============================================================================
# 1. 规划是加分项：任何异常都不能拖垮内容生成
# =============================================================================

def test_plan_deck_safe_returns_empty_when_planner_raises(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("规划服务不可用")

    monkeypatch.setattr(tp, "plan_deck", _boom)
    assert _plan_deck_safe({"topic": "排序"}, [{"node_id": "n1"}], "") == {}


def test_plan_deck_safe_plans_every_node():
    nodes = [
        {"node_id": "n1", "type": "content", "title": "冒泡排序",
         "summary": "每一轮把最大值送到末尾。", "key_points": ["相邻比较", "交换"]},
        {"node_id": "n2", "type": "cover", "title": "封面"},
    ]
    plans = _plan_deck_safe({}, nodes, "")

    assert set(plans) == {"n1", "n2"}


def test_plan_deck_works_without_intent():
    """intent 缺席是合法输入 —— Go 侧补不到时必须照常工作。"""
    nodes = [{"node_id": "n1", "type": "content", "title": "排序",
              "summary": "每一轮把最大值送到末尾。"}]
    for intent in ({}, None, "", [], {"topic": "排序"}):
        assert set(tp.plan_deck(intent, nodes, evidence="")) == {"n1"}


# =============================================================================
# 2. 落盘：plan / figure / key_conclusion 三件事
# =============================================================================

def test_attach_teaching_plan_writes_all_three():
    node = {"node_id": "n1", "type": "content", "title": "复杂度"}
    plan = {
        "node_id": "n1", "visual_type": "flow",
        "visual_structure": ["输入规模", "增长趋势", "复杂度"],
        "key_conclusion": "复杂度描述的是增长趋势",
        "teacher_note": "口头补充常数项",
    }
    merged = _attach_teaching_plan(node, plan)

    assert merged["teaching_plan"] is plan
    assert merged["key_conclusion"] == "复杂度描述的是增长趋势"
    assert merged["figure"]["kind"] == "flow"
    # 原节点不被就地改写（管道里 node 还可能被别处引用）
    assert "teaching_plan" not in node


def test_attach_teaching_plan_omits_figure_for_none():
    """visual_type=none 就是「这页不出图」—— 这是反 AI 自嗨的那道决策，必须真的不出。"""
    plan = {"node_id": "n1", "visual_type": "none", "key_conclusion": "定义是记忆性的"}
    merged = _attach_teaching_plan({"node_id": "n1", "type": "content"}, plan)

    assert "figure" not in merged
    assert merged["key_conclusion"] == "定义是记忆性的"


def test_attach_teaching_plan_is_noop_without_a_plan():
    node = {"node_id": "n1", "type": "content"}
    for plan in (None, {}, "flow", 42):
        assert _attach_teaching_plan(node, plan) == node


def test_gen_content_request_intent_defaults_to_empty():
    """不传 intent 时是 {}，规划器降级为只从节点推断 —— 不是 None，免得下游到处判空。"""
    assert GenContentRequest().intent == {}
    assert GenContentRequest(intent={"topic": "排序"}).intent == {"topic": "排序"}


# =============================================================================
# 3. 增强分支：不丢页、不重复页
# =============================================================================

def _nodes() -> list[dict]:
    return [
        {"node_id": "n1", "type": "content", "node_type": "content", "title": "第一页",
         "summary": "第一页的结论。", "key_points": ["甲", "乙"]},
        {"node_id": "n2", "type": "content", "node_type": "content", "title": "第二页",
         "summary": "第二页的结论。", "key_points": ["丙", "丁"]},
        {"node_id": "n3", "type": "content", "node_type": "content", "title": "第三页",
         "summary": "第三页的结论。", "key_points": ["戊", "己"]},
    ]


class _FakeGenerator:
    """generate_enhanced 故意漏掉 n2，逼出「缺页逐节点补生成」这条路径。"""

    def __init__(self):
        self.enhanced_calls = 0
        self.single_calls: list[str] = []

    def generate_enhanced(self, nodes, markdown="", course_name=None, **kwargs):
        self.enhanced_calls += 1
        return {"scripts": [
            {"node_id": "n1", "title": "第一页", "script": "批量-n1", "segments": []},
            {"node_id": "n3", "title": "第三页", "script": "批量-n3", "segments": []},
        ]}

    def generate_single(self, node, course_name=None, **kwargs):
        node_id = node["node_id"]
        self.single_calls.append(node_id)
        return {"node_id": node_id, "title": node.get("title", ""),
                "script": f"补生成-{node_id}", "segments": [],
                "point_details": [{"point": "要点", "detail": "展开"}]}


def _run(req: GenContentRequest, monkeypatch,
         generator_cls: type = _FakeGenerator) -> tuple[dict, _FakeGenerator]:
    fake = generator_cls()

    # 管道会调 NodeGenerator._generation_instruction_context(...)；桩必须保留这个
    # 类方法，否则每个节点都会以 AttributeError 失败（测试桩与实现脱节）。
    class _StubNodeGenerator:
        _generation_instruction_context = staticmethod(lambda instruction: {})

        def __new__(cls, *a, **k):
            return fake

    monkeypatch.setattr(main_module, "NodeGenerator", _StubNodeGenerator)
    content_id = "content_test"
    main_module._content_tasks[content_id] = {
        "content_id": content_id, "status": "generating", "progress_pct": 0.0,
        "current_node_id": "", "total_nodes": len(req.nodes), "completed_nodes": 0,
        "nodes": [], "error": None,
    }
    try:
        _run_content_pipeline(content_id, req)
        return main_module._content_tasks[content_id], fake
    finally:
        main_module._content_tasks.pop(content_id, None)


def test_enhanced_pipeline_emits_exactly_one_node_per_input(monkeypatch):
    """页数翻倍是静默的：教师只会看到课件里凭空多出重复页。"""
    req = GenContentRequest(nodes=_nodes(), enhanced=True)
    task, fake = _run(req, monkeypatch)

    assert [n["node_id"] for n in task["nodes"]] == ["n1", "n2", "n3"]
    assert task["error"] is None
    # 批量只调一次（改动前是每个节点都调一次整批）
    assert fake.enhanced_calls == 1
    # 缺页的只有 n2，它走逐节点补生成
    assert fake.single_calls == ["n2"]


def test_enhanced_pipeline_keeps_each_page_own_script(monkeypatch):
    """后续节点不能把上一页的 merged 再 append 一次。"""
    task, _ = _run(GenContentRequest(nodes=_nodes(), enhanced=True), monkeypatch)
    scripts = {n["node_id"]: n["script"] for n in task["nodes"]}

    assert scripts == {"n1": "批量-n1", "n2": "补生成-n2", "n3": "批量-n3"}


class _ExplodingEnhancedGenerator(_FakeGenerator):
    """批量接口整体失败（限流 / 502 / 超时）。"""

    def generate_enhanced(self, nodes, markdown="", course_name=None, **kwargs):
        self.enhanced_calls += 1
        raise RuntimeError("批量接口 502")


def test_enhanced_batch_failure_falls_back_per_node(monkeypatch):
    """批量接口挂掉 → 退回逐节点生成，任务照常 done。

    这条降级路径此前会 UnboundLocalError，而且**跑不出来**：异常发生在 except 块
    内部，不会被同一个 except 接住，一路冒到外层把整个任务标成 failed。触发点是
    该函数里那句降级日志 —— 当时 `_run_content_pipeline` 在函数体内写了
    `import logging`，使 logging 成为**该函数的局部名**，而那句日志执行在那两个
    局部导入之前，于是抛 UnboundLocalError 而非 NameError（顶层 import 救不了）。
    所以这条测试同时锁住两件事：降级可用，且 logging 保持模块级。
    """
    task, fake = _run(
        GenContentRequest(nodes=_nodes(), enhanced=True), monkeypatch,
        generator_cls=_ExplodingEnhancedGenerator,
    )

    assert task["status"] == "done"
    assert task["error"] is None
    assert [n["node_id"] for n in task["nodes"]] == ["n1", "n2", "n3"]
    # 三个节点全部走逐节点补生成
    assert fake.single_calls == ["n1", "n2", "n3"]


def test_pipeline_attaches_a_plan_to_every_node(monkeypatch):
    task, _ = _run(GenContentRequest(nodes=_nodes()), monkeypatch)

    assert len(task["nodes"]) == 3
    for node in task["nodes"]:
        assert isinstance(node.get("teaching_plan"), dict)
        assert node["teaching_plan"]["node_id"] == node["node_id"]
        assert node["teaching_plan"]["key_conclusion"]  # 摘要里有可用的短句
    # 原有字段没有被合并冲掉
    assert task["nodes"][0]["key_points"] == ["甲", "乙"]


def test_pipeline_still_works_when_the_planner_dies(monkeypatch):
    """规划失败 → 页面照常生成，只是没有 teaching_plan。"""
    monkeypatch.setattr(tp, "plan_deck", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("挂了")))
    task, _ = _run(GenContentRequest(nodes=_nodes()), monkeypatch)

    assert len(task["nodes"]) == 3
    assert task["status"] == "done"
    assert all("teaching_plan" not in n for n in task["nodes"])


# =============================================================================
# 4. 已确认资料必须真的进入讲稿 Prompt（/gen/content 首次全量生成）
# =============================================================================

def test_content_evidence_context_reads_confirmed_evidence_and_intent():
    """前端不传 context_markdown / intent，资料与意图都在 instruction_set 里。"""
    req = GenContentRequest(
        nodes=[{"node_id": "n1", "title": "队列"}],
        generation_instruction_set={
            "confirmed_evidence": {"synthesized_context": "队列是先进先出的线性结构"},
            "intent": {"topic": "图搜索", "target_student": "高一"},
        },
    )
    assert req.context_markdown == ""
    assert req.intent == {}

    ctx = main_module._content_evidence_context(req)
    assert "队列是先进先出的线性结构" in ctx
    assert "图搜索" in ctx
    assert "高一" in ctx


def test_content_evidence_context_stays_empty_without_evidence():
    """没有已确认资料时不能凭空造出「参考资料」，无资料模式仍是空上下文。"""
    req = GenContentRequest(
        nodes=[{"node_id": "n1"}],
        generation_instruction_set={"confirmed_evidence": None, "intent": {}},
    )
    assert main_module._content_evidence_context(req) == ""


@pytest.mark.parametrize(
    ("evidence", "intent", "has_source"),
    [
        ({"synthesized_context": "专属资料正文", "relevant_chunks": [
            {"chunk_id": "c1", "source_ref": "合成教材.docx", "content": "专属资料正文"},
        ]}, {"topic": "排序算法"}, True),
        (None, {}, False),
        (None, {"topic": "排序算法"}, False),
    ],
)
def test_first_script_prompt_labels_only_real_material_as_reference(
    monkeypatch, evidence, intent, has_source,
):
    """模型桩直接记录逐节点 Prompt，分别检查资料、空输入和仅意图。"""
    prompts = []

    def fake_chat_json(self, system, user, **kwargs):
        prompts.append(user)
        return {"script": "测试讲稿", "segments": [], "point_details": []}

    monkeypatch.setattr(LLMClient, "chat_json", fake_chat_json)
    req = GenContentRequest(
        nodes=[{"node_id": "n1", "title": "排序算法", "type": "content"}],
        generation_instruction_set={"confirmed_evidence": evidence, "intent": intent},
    )
    context = main_module._content_evidence_context(req)
    NodeGenerator().generate_single(req.nodes[0], context_markdown=context,
                                    context_is_preformatted=True)
    assert len(prompts) == 1
    prompt = prompts[0]
    assert ("【已确认的参考资料】" in prompt) is has_source
    assert ("专属资料正文" in prompt) is has_source
    assert ("合成教材.docx" in prompt) is has_source
    assert ("【教学意图】" in prompt) is bool(intent)
    if not has_source:
        assert "【参考材料】" not in prompt
        assert "从知识库检索到的相关资料" not in prompt


@pytest.mark.parametrize("has_source", [False, True])
def test_enhanced_prompt_keeps_sections_without_false_reference(monkeypatch, has_source):
    """增强批量写稿对有资料和仅意图两种输入使用准确标题。"""
    prompts = []

    def fake_chat_with_schema(self, system, user, schema, **kwargs):
        prompts.append(user)
        return {"scripts": [{"node_id": "n1", "title": "排序算法",
                             "script": "测试讲稿", "segments": [], "point_details": []}]}

    monkeypatch.setattr(LLMClient, "chat_with_schema", fake_chat_with_schema)
    req = GenContentRequest(
        nodes=[{"node_id": "n1", "title": "排序算法", "type": "content"}],
        generation_instruction_set={"confirmed_evidence": {
            "synthesized_context": "专属资料正文",
            "relevant_chunks": [{"chunk_id": "c1", "source_ref": "合成教材.docx"}],
        } if has_source else None,
                                    "intent": {"topic": "排序算法"}},
    )
    result = NodeGenerator().generate_enhanced(
        req.nodes, main_module._content_evidence_context(req),
        context_is_preformatted=True,
    )
    assert not result["used_fallback"]
    assert len(prompts) == 1
    assert "生成上下文" in prompts[0]
    assert "【教学意图】" in prompts[0]
    assert ("【已确认的参考资料】" in prompts[0]) is has_source
    assert ("专属资料正文" in prompts[0]) is has_source
    assert ("合成教材.docx" in prompts[0]) is has_source
    assert "【参考材料】" not in prompts[0]
    assert "从知识库检索到的相关资料" not in prompts[0]


def test_enhanced_batch_failure_keeps_first_script_context(monkeypatch):
    """批量失败后的逐节点补生成仍收到资料、来源与教学意图。"""
    prompts = []

    def failed_batch(self, *args, **kwargs):
        raise RuntimeError("synthetic batch failure")

    def fake_chat_json(self, system, user, **kwargs):
        prompts.append(user)
        return {"script": "测试讲稿", "segments": [], "point_details": []}

    monkeypatch.setattr(NodeGenerator, "_run_enhanced_batch", failed_batch)
    monkeypatch.setattr(LLMClient, "chat_json", fake_chat_json)
    req = GenContentRequest(
        nodes=[{"node_id": "n1", "title": "排序算法", "type": "content"}],
        generation_instruction_set={
            "confirmed_evidence": {"synthesized_context": "专属资料正文",
                                   "relevant_chunks": [{"chunk_id": "c1",
                                                        "source_ref": "合成教材.docx"}]},
            "intent": {"topic": "排序算法"},
        },
    )
    result = NodeGenerator().generate_enhanced(
        req.nodes, main_module._content_evidence_context(req),
        context_is_preformatted=True,
    )
    assert result["used_fallback"]
    assert len(prompts) == 1
    assert "【已确认的参考资料】" in prompts[0]
    assert "专属资料正文" in prompts[0]
    assert "合成教材.docx" in prompts[0]
    assert "【教学意图】" in prompts[0]


def test_full_pipeline_feeds_evidence_into_script_prompt(monkeypatch):
    """管道级：generate_single 拿到的 context_markdown 必须含资料正文。

    改动前这里恒为空串，讲稿凭空生成，页面却仍挂 citation_refs。
    """
    class _CapturingNodeGenerator:
        contexts: list = []
        _generation_instruction_context = staticmethod(lambda instruction: {})

        def generate_single(self, node, course_name=None, **kwargs):
            _CapturingNodeGenerator.contexts.append(kwargs.get("context_markdown", ""))
            return {"node_id": node["node_id"], "title": node.get("title", ""),
                    "script": "讲稿", "segments": []}

        def generate_enhanced(self, nodes, markdown="", course_name=None, **kwargs):
            _CapturingNodeGenerator.contexts.append(markdown)
            return {"scripts": []}

    monkeypatch.setattr(main_module, "NodeGenerator", _CapturingNodeGenerator)
    _CapturingNodeGenerator.contexts.clear()

    req = GenContentRequest(
        nodes=[{"node_id": "n1", "type": "content", "title": "队列", "summary": "先进先出"}],
        generation_instruction_set={
            "confirmed_evidence": {"synthesized_context": "队列是先进先出的线性结构"},
            "intent": {"topic": "图搜索"},
        },
    )
    content_id = "content_evidence_test"
    main_module._content_tasks[content_id] = {
        "content_id": content_id, "status": "generating", "progress_pct": 0.0,
        "current_node_id": "", "total_nodes": 1, "completed_nodes": 0,
        "nodes": [], "error": None,
    }
    try:
        _run_content_pipeline(content_id, req)
        assert _CapturingNodeGenerator.contexts
        assert all("队列是先进先出的线性结构" in ctx
                   for ctx in _CapturingNodeGenerator.contexts)
    finally:
        main_module._content_tasks.pop(content_id, None)
