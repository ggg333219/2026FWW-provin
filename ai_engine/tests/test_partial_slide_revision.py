"""局部修改必须改到**幻灯片上看得见的内容**。

背景：老师报的 bug 是「对话里报『已更新：典型案例』，HTML 预览没有任何变化」。
根因有两层，本文件把两层都钉住：

1. 回写侧：``run_partial_pipeline`` 只写 script / segments / point_details，
   而其中只有 point_details 属于 ROLE_PRIMARY；正文（summary）根本不回写。
   更糟的是整次回写被 ``new_script.get("script")`` 这道闸门卡着 —— 模型把力气
   花在页面上、没给讲稿时，整次修改被静默丢弃。
2. 提示词侧：``generate_single`` 的框架是「生成分段讲授脚本」，模型据此把
   point_details 照抄一遍，页面自然纹丝不动。

对应的契约是 ``revise_slide=True`` + ``apply_page_revision``。
"""

from __future__ import annotations

import pytest

from ai_engine.gen import partial_content
from ai_engine.gen.node import NodeGenerator, _current_slide_context
from ai_engine.gen.partial_content import (
    _revision_has_content,
    _supports_slide_revision,
    apply_page_revision,
    run_partial_pipeline,
)


# =============================================================================
# 1. apply_page_revision —— 写回策略（哪些字段算「上屏」）
# =============================================================================

_NODE = {
    "node_id": "node_2",
    "title": "冒泡排序",
    "node_type": "content",
    "summary": "相邻两两比较，大的往后挪。",
    "point_details": [{"point": "相邻比较", "detail": "每轮把最大的送到末尾。"}],
    "script": "原始讲稿",
    "segments": [{"segment_id": "seg_001", "text": "原始分段", "node_id": "node_2"}],
    "source_chunk_ids": ["chunk_old"],
}


def test_writes_back_the_on_slide_fields() -> None:
    """summary 与 point_details 是幻灯片正文，必须写回 —— 这是这个 bug 的本体。"""
    updated = apply_page_revision(_NODE, {
        "summary": "相邻两两比较，大的往右挪；一轮定一个。",
        "point_details": [{"point": "相邻比较", "detail": "每轮确定一个最大值的位置。"}],
    })

    assert updated["summary"] == "相邻两两比较，大的往右挪；一轮定一个。"
    assert updated["point_details"] == [
        {"point": "相邻比较", "detail": "每轮确定一个最大值的位置。"}
    ]
    # 讲稿侧跟着走
    assert updated["script"] == "原始讲稿", "这次没给讲稿，旧讲稿保留"


def test_keeps_page_identity() -> None:
    """title / node_type 是页面身份，模型是照抄输入的，一律不回写。"""
    updated = apply_page_revision(_NODE, {
        "title": "node_2",          # 模型漏字段时的典型产物
        "node_type": "quiz",
        "summary": "新正文",
    })

    assert updated["title"] == "冒泡排序"
    assert updated["node_type"] == "content"


def test_empty_summary_does_not_wipe_the_body() -> None:
    """模型不配合时给的是空串 —— 「键在就覆盖」会把整页正文抹掉。"""
    updated = apply_page_revision(_NODE, {"summary": "", "script": "新讲稿"})
    assert updated["summary"] == "相邻两两比较，大的往后挪。"
    assert updated["script"] == "新讲稿"


def test_body_follows_content_when_the_node_has_one() -> None:
    """page_spec.body_paragraphs 的读取顺序是 content → summary。

    老节点上两者并存时只写 summary 等于没改 —— 但也不该给本来没有 content 的
    节点凭空造一个。
    """
    legacy = {**_NODE, "content": "旧正文"}
    updated = apply_page_revision(legacy, {"summary": "新正文"})
    assert updated["content"] == "新正文"
    assert updated["summary"] == "新正文"

    fresh = apply_page_revision(_NODE, {"summary": "新正文"})
    assert "content" not in fresh


def test_appends_evidence_without_losing_existing_refs() -> None:
    updated = apply_page_revision(_NODE, {"summary": "新正文"}, evidence_ids=["chunk_new"])
    assert updated["source_chunk_ids"] == ["chunk_old", "chunk_new"]


def test_non_dict_revision_is_a_noop() -> None:
    assert apply_page_revision(_NODE, None) == _NODE
    assert apply_page_revision(_NODE, "讲稿") == _NODE


# =============================================================================
# 2. 闸门 —— 不能再因为「没给讲稿」丢掉整次修改
# =============================================================================

@pytest.mark.parametrize("revision", [
    {"script": "有讲稿"},
    {"summary": "只有正文"},
    {"point_details": [{"point": "p", "detail": "d"}]},
    {"segments": [{"segment_id": "seg_001", "text": "t"}]},
])
def test_revision_counts_as_content(revision) -> None:
    assert _revision_has_content(revision) is True


@pytest.mark.parametrize("revision", [
    None, "讲稿", {}, {"script": "", "summary": "  ", "segments": [], "point_details": []},
])
def test_empty_revision_is_not_content(revision) -> None:
    assert _revision_has_content(revision) is False


# =============================================================================
# 3. run_partial_pipeline —— revise_slide 透传与向后兼容
# =============================================================================

class _SlideAwareGenerator:
    """实现了 revise_slide 的生成器：模拟「模型只改页面、不给讲稿」。"""

    def __init__(self, revision: dict) -> None:
        self.revision = revision
        self.calls: list[dict] = []

    def generate_single(self, node, course_name=None, max_attempts=None,
                        extra_instruction="", context_markdown="", revise_slide=False):
        self.calls.append({"node_id": node.get("node_id"), "revise_slide": revise_slide})
        return dict(self.revision)


class _LegacyGenerator:
    """只实现基础签名的生成器（测试与外部注入的常见形态）。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_single(self, node, course_name=None, max_attempts=None,
                        extra_instruction="", context_markdown=""):
        self.calls.append({"node_id": node.get("node_id")})
        return {**node, "script": f"重生成:{node.get('node_id')}"}


def _run(gen, target="node_2"):
    return run_partial_pipeline(
        nodes=[dict(n) for n in (_NODE, {**_NODE, "node_id": "node_3", "title": "快速排序"})],
        target_node_ids=[target],
        modify_action="simplify",
        modify_constraints=["减少文字"],
        context_markdown="",
        course_name="排序算法",
        generator=gen,
    )


def test_revise_slide_is_requested_when_supported() -> None:
    gen = _SlideAwareGenerator({"summary": "精简后的正文", "script": "精简后的讲稿"})
    _run(gen)
    assert gen.calls == [{"node_id": "node_2", "revise_slide": True}]


def test_legacy_generator_still_works() -> None:
    """不支持 revise_slide 的生成器退回老行为，不能因为一个 kwarg 整次失败。"""
    gen = _LegacyGenerator()
    assert _supports_slide_revision(gen) is False
    updated = _run(gen)
    assert updated[0]["script"] == "重生成:node_2"


def test_slide_only_revision_reaches_the_slide() -> None:
    """模型只改页面、没给讲稿 —— 旧实现会在这里把整次修改丢掉。"""
    gen = _SlideAwareGenerator({
        "summary": "只讲相邻比较，一轮定一个。",
        "point_details": [{"point": "相邻比较", "detail": "一轮确定一个最大值。"}],
        "script": "",  # 讲稿为空，正是旧闸门 ``if new_script.get("script")`` 卡掉的情形
    })
    updated = _run(gen)

    assert updated[0]["summary"] == "只讲相邻比较，一轮定一个。"
    assert updated[0]["point_details"] == [
        {"point": "相邻比较", "detail": "一轮确定一个最大值。"}
    ]
    assert updated[0]["script"] == "原始讲稿", "没给新讲稿就保留旧的"
    # 非目标页一字未动
    assert updated[1]["summary"] == _NODE["summary"]
    assert updated[1]["script"] == _NODE["script"]


def test_empty_revision_keeps_the_page_intact() -> None:
    gen = _SlideAwareGenerator({})
    updated = _run(gen)
    assert updated[0] == _NODE


def test_generator_with_var_keyword_is_treated_as_slide_aware() -> None:
    class _AnyKwargs:
        def generate_single(self, node, **kwargs):
            return {}

    assert _supports_slide_revision(_AnyKwargs()) is True


# =============================================================================
# 4. 提示词 —— 不点破「改的是幻灯片」，模型就只会重写讲稿
# =============================================================================

class _CapturingLLM:
    def __init__(self, payload=None) -> None:
        self.system_prompts: list[str] = []
        self.user_prompts: list[str] = []
        self.payload = payload if payload is not None else {"script": "讲稿"}

    def chat_json(self, system_prompt, user_prompt, temperature=None):
        self.system_prompts.append(system_prompt)
        self.user_prompts.append(user_prompt)
        return self.payload


def test_revise_slide_prompt_states_the_page_contract() -> None:
    llm = _CapturingLLM({"script": "讲稿", "summary": "新正文",
                         "point_details": [{"point": "p", "detail": "d"}]})
    out = NodeGenerator(llm_client=llm).generate_single(
        _NODE, "排序算法", extra_instruction="减少文字", revise_slide=True,
    )

    system_prompt = llm.system_prompts[-1]
    assert "局部修改" in system_prompt
    assert "summary" in system_prompt and "point_details" in system_prompt
    # 当前页面内容要摊给模型看，否则它只能照着大纲字段重新生成一份相似稿
    user_prompt = llm.user_prompts[-1]
    assert "【当前页面内容（将被改写）】" in user_prompt
    assert _NODE["summary"] in user_prompt
    assert "相邻比较" in user_prompt          # point_details 的 point
    assert out["summary"] == "新正文"


def test_without_revise_slide_prompt_is_unchanged() -> None:
    """默认 False：prompt 与返回形状都与加这个参数之前逐字相同（防回归）。"""
    llm = _CapturingLLM()
    gen = NodeGenerator(llm_client=llm)
    out = gen.generate_single(_NODE, "排序算法", extra_instruction="精简")

    assert "局部修改" not in llm.system_prompts[-1]
    assert "【当前页面内容（将被改写）】" not in llm.user_prompts[-1]
    assert "summary" not in out, "新建/批量路径的返回形状必须保持不变"


def test_without_revise_slide_the_model_summary_is_ignored() -> None:
    llm = _CapturingLLM({"script": "讲稿", "summary": "模型自作主张的正文"})
    out = NodeGenerator(llm_client=llm).generate_single(_NODE, "排序算法")
    assert "summary" not in out


def test_current_slide_context_is_empty_for_a_bare_node() -> None:
    assert _current_slide_context({"node_id": "n1", "title": "T"}) == ""
