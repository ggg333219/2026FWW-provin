"""P5：教学表达规划器真的接在老师端走的那条链路上（/api/v1/gen/create）。

上一轮把规划器接在了 ``/gen/content`` —— 前端从不调用的一条路由。于是
``teaching_plan`` / ``figure`` / ``key_conclusion`` 在真实课件里从未出现过，只在测试与
示例脚本里成立。这个文件锁住「现在真的接上了」，以及接上之后最容易再断掉的四处：

  1. **意图的形态**：``/gen/create`` 传的是 pydantic ``IntentSummary``，``/gen/content``
     传的是 dict。``_intent_brief`` 只认 dict 的话，教学意图会在规划器门口被静默丢掉，
     一路辛苦透传过来却等于没传。
  2. **字段的存活**：``TeachingNode`` 未声明的键会被 pydantic 静默丢弃，而且丢弃点不止
     一处（task.nodes 响应、GenerationVersion 快照落盘）。``script`` 字段的注释就是
     这个 bug 上一次发作留下的疤。
  3. **合并的尺度**：讲稿结果并回节点时，``normalize_stage3_scripts`` 会给缺失字段填
     默认值（``title`` 缺失填 ``node_id``、``key_points`` 缺失填 ``[]``），整体合并会把
     老师确认过的标题和页型一起冲掉。
  4. **端到端**：``/gen/status`` 返回的节点里真的带 ``point_details``。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_engine import main as main_module  # noqa: E402
from ai_engine.core.llm import LLMClient  # noqa: E402
from ai_engine.core.schema import IntentSummary, TeachingNode  # noqa: E402
from ai_engine.gen import teaching_plan as tp  # noqa: E402
from ai_engine.gen.node import NodeGenerator  # noqa: E402
from ai_engine.gen.version import VersionManager  # noqa: E402
from ai_engine.main import (  # noqa: E402
    _attach_teaching_plan,
    _evidence_brief,
    _merge_script_into_node,
    app,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _deterministic_planner(monkeypatch):
    """强制规划器走确定性兜底：不碰网络，也不受 AI_GEN_MODE 影响。"""
    monkeypatch.setattr(tp, "_use_llm", lambda llm=None: None)


# =============================================================================
# 1. 意图：pydantic 模型也要认得出
# =============================================================================

def test_intent_brief_accepts_pydantic_intent():
    """老师端走的是 /gen/create，intent 是 IntentSummary 而不是 dict。"""
    intent = IntentSummary(
        topic="排序算法",
        style="案例驱动",
        target_student="大一计算机专业",
        key_difficulties=["复杂度分析"],
        expected_outcomes=["能比较典型排序算法"],
    )
    brief = tp._intent_brief(intent)

    assert "教学主题：排序算法" in brief
    assert "教学风格：案例驱动" in brief
    assert "授课对象：大一计算机专业" in brief
    assert "复杂度分析" in brief


def test_intent_brief_still_accepts_dict_and_survives_junk():
    assert "教学主题：排序" in tp._intent_brief({"topic": "排序"})
    for junk in (None, "", [], 42, object()):
        assert tp._intent_brief(junk) == ""


def test_plan_deck_puts_intent_into_the_prompt():
    """意图要真的进到规划提示词里 —— 认得出模型但不往里写，等于白认。"""
    seen: list[str] = []

    class _FakeLLM:
        def chat_json(self, system_prompt, user_prompt, **kwargs):
            seen.append(user_prompt)
            return {"plans": []}

    tp.plan_deck(
        IntentSummary(topic="排序算法", style="案例驱动"),
        [{"node_id": "n1", "type": "content", "title": "冒泡排序", "summary": "每一轮把最大值送到末尾。"}],
        evidence="",
        llm=_FakeLLM(),
    )

    assert seen, "规划器没有调用 LLM"
    assert "教学主题：排序算法" in seen[0]
    assert "案例驱动" in seen[0]


# =============================================================================
# 2. 证据：/gen/create 拿到的是 EvidencePacket 而不是 chunk 引用
# =============================================================================

def test_evidence_brief_prefers_synthesized_context():
    brief = _evidence_brief({
        "synthesized_context": "排序算法的复杂度对比。",
        "relevant_chunks": [{"content": "不应出现"}],
    })
    assert "排序算法的复杂度对比。" in brief
    assert "不应出现" not in brief


def test_evidence_brief_falls_back_to_chunks_and_is_bounded():
    brief = _evidence_brief({"relevant_chunks": [{"content": "甲"}, {"content": "乙"}]})
    assert "甲" in brief and "乙" in brief

    huge = _evidence_brief({"relevant_chunks": [{"content": "长" * 5000}]})
    assert len(huge) <= main_module._PLAN_EVIDENCE_LIMIT

    for junk in (None, "", [], {"synthesized_context": None}):
        assert _evidence_brief(junk) == ""


# =============================================================================
# 3. 合并：只增不减，不碰大纲定下的字段
# =============================================================================

def test_merge_script_carries_point_details():
    """这是曾经被丢掉的那个字段 —— 生成得出来、白名单也过得了，栽在合并那一步。"""
    node = {"node_id": "n1", "title": "复杂度", "node_type": "content"}
    script = {
        "node_id": "n1", "script": "讲稿", "segments": [{"segment_id": "s1"}],
        "point_details": [{"point": "时间复杂度", "detail": "描述增长趋势"}],
    }
    merged = _merge_script_into_node(node, script)

    assert merged["point_details"] == [{"point": "时间复杂度", "detail": "描述增长趋势"}]
    assert merged["script"] == "讲稿"
    assert merged["segments"] == [{"segment_id": "s1"}]


def test_merge_script_does_not_clobber_outline_authoritative_fields():
    """讲稿模型漏标题 → normalize_stage3_scripts 填 node_id；整体合并会让页面上出现 "n3"。

    页型同理：讲稿模型把封面报成 content，封面就退回普通内容页 —— 都是老师确认过的信息。
    """
    node = {
        "node_id": "n3", "title": "教师确认的封面", "node_type": "cover", "type": "cover",
        "content": "课程名", "summary": "教师写的摘要", "key_points": ["甲", "乙"],
        "source_chunk_ids": ["chunk_1"],
    }
    script = {
        "node_id": "n3", "title": "n3", "node_type": "content", "type": "content",
        "script": "讲稿", "segments": [], "key_points": [], "core_points": [],
    }
    merged = _merge_script_into_node(node, script)

    assert merged["title"] == "教师确认的封面"
    assert merged["node_type"] == "cover"
    assert merged["type"] == "cover"
    assert merged["summary"] == "教师写的摘要"
    assert merged["key_points"] == ["甲", "乙"]
    assert merged["source_chunk_ids"] == ["chunk_1"]
    assert merged["script"] == "讲稿"


def test_merge_script_ignores_empty_and_non_dict():
    node = {"node_id": "n1", "title": "标题", "script": "原讲稿"}
    merged = _merge_script_into_node(node, {"script": "", "segments": [], "point_details": None})
    assert merged["script"] == "原讲稿"
    assert "point_details" not in merged

    assert _merge_script_into_node(node, None) == node
    assert _merge_script_into_node(node, "丢弃") == node


# =============================================================================
# 4. 字段存活：穿过 pydantic 与磁盘快照
# =============================================================================

def _planned_node() -> dict:
    node = {"node_id": "n1", "title": "复杂度基础", "node_type": "content",
            "summary": "复杂度描述算法规模增长趋势。", "key_points": ["时间复杂度"]}
    plan = {
        "node_id": "n1", "teaching_goal": "理解增长趋势",
        "visual_type": "flow", "visual_structure": ["输入规模", "增长趋势", "复杂度"],
        "key_conclusion": "复杂度描述的是增长趋势，不是绝对耗时",
    }
    merged = _merge_script_into_node(
        node, {"script": "讲稿", "segments": [],
               "point_details": [{"point": "时间复杂度", "detail": "描述增长趋势"}]},
    )
    return _attach_teaching_plan(merged, plan)


def test_teaching_node_roundtrip_keeps_new_fields():
    """未声明的字段会被 pydantic 静默丢弃 —— 丢在这里就再也到不了前端与导出。"""
    original = _planned_node()
    roundtripped = TeachingNode.model_validate(original).model_dump()

    assert roundtripped["point_details"] == [{"point": "时间复杂度", "detail": "描述增长趋势"}]
    assert roundtripped["key_conclusion"] == "复杂度描述的是增长趋势，不是绝对耗时"
    assert roundtripped["figure"]["kind"] == "flow"
    assert roundtripped["figure"]["items"] == ["输入规模", "增长趋势", "复杂度"]
    assert roundtripped["teaching_plan"]["node_id"] == "n1"


def test_version_snapshot_keeps_new_fields(monkeypatch, tmp_path):
    """GenerationVersion 落盘是第二个丢弃点：快照里没有，预览与导出就都读不到。"""
    monkeypatch.chdir(tmp_path)
    vm = VersionManager()
    vm.save_snapshot("gen_plan_fields", [_planned_node()], "初稿")

    on_disk = json.loads(
        (tmp_path / "data" / "versions" / "gen_plan_fields" / "v_1.json").read_text(encoding="utf-8")
    )
    snapshot = on_disk["nodes_snapshot"][0]

    assert snapshot["point_details"] == [{"point": "时间复杂度", "detail": "描述增长趋势"}]
    assert snapshot["key_conclusion"] == "复杂度描述的是增长趋势，不是绝对耗时"
    assert snapshot["figure"]["kind"] == "flow"
    assert snapshot["teaching_plan"]["node_id"] == "n1"


# =============================================================================
# 5. 写稿 prompt：规划作为约束注入
# =============================================================================

def _capture_batch_prompt(monkeypatch, plans) -> str:
    seen: list[str] = []

    def fake_chat_with_schema(self, system_prompt, user_prompt, schema, **kwargs):
        seen.append(user_prompt)
        return {"scripts": []}

    monkeypatch.setattr(LLMClient, "chat_with_schema", fake_chat_with_schema)
    NodeGenerator().generate_all(
        [{"node_id": "n1", "title": "复杂度基础", "type": "content",
          "summary": "复杂度描述算法规模增长趋势。"}],
        "", "排序算法", plans=plans,
    )
    assert len(seen) == 1
    return seen[0]


def test_generate_all_injects_plan_constraints(monkeypatch):
    prompt = _capture_batch_prompt(monkeypatch, {
        "n1": {"node_id": "n1", "teaching_goal": "理解增长趋势",
               "key_conclusion": "复杂度描述的是增长趋势", "teacher_note": "口头补充常数项"},
    })

    assert "【各页教学表达约束】" in prompt
    # 批量写稿是一次调用生成全部节点，约束必须带 node_id 才谈得上归属
    assert "n1" in prompt
    assert "复杂度描述的是增长趋势" in prompt
    assert "口头补充常数项" in prompt


def test_generate_all_prompt_is_unchanged_without_plans(monkeypatch):
    """老课件 / 规划失败时，prompt 必须与不传 plans 时逐字相同。"""
    baseline = _capture_batch_prompt(monkeypatch, None)
    for empty in ({}, {"n2": {"node_id": "n2"}}, "不是 dict"):
        assert _capture_batch_prompt(monkeypatch, empty) == baseline


# =============================================================================
# 6. 端到端：/api/v1/gen/create → /gen/status
# =============================================================================

def _create_payload() -> dict:
    return {
        "session_id": "sess_plan_wiring",
        "intent": {"topic": "排序算法", "style": "案例驱动"},
        "outline_id": "outline_plan_001",
        "outline_version": 1,
        "outline_confirmed": True,
        "outline_nodes": [
            {
                "node_id": "node_plan_001",
                "order": 1,
                "title": "复杂度基础",
                "summary": "复杂度描述算法规模增长趋势。",
                "node_type": "content",
                "key_points": ["时间复杂度", "空间复杂度"],
                "estimated_duration_minutes": 10,
            }
        ],
    }


def _run_create(monkeypatch, tmp_path, payload: dict) -> dict:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module._task_store, "_use_redis", False)

    def fake_chat_with_schema(self, system_prompt, user_prompt, schema, **kwargs):
        return {"scripts": [{
            "node_id": "node_plan_001",
            "title": "复杂度基础",
            "script": "讲稿正文。",
            "segments": [{"segment_id": "seg_001", "node_id": "node_plan_001",
                          "text": "讲稿正文。"}],
            "point_details": [{"point": "时间复杂度", "detail": "描述增长趋势"}],
        }]}

    monkeypatch.setattr(LLMClient, "chat_with_schema", fake_chat_with_schema)

    created = client.post("/api/v1/gen/create", json=payload)
    assert created.status_code == 200
    task_id = created.json()["task_id"]

    status = None
    for _ in range(500):
        status = client.get(f"/api/v1/gen/status/{task_id}")
        assert status.status_code == 200
        if status.json()["status"] in {"done", "failed"}:
            break
        time.sleep(0.02)
    return status.json()


def test_create_pipeline_delivers_planned_fields_to_the_api(monkeypatch, tmp_path):
    """这是本轮的全部意义：真实链路的响应里真的有这些字段。

    改动前 point_details 停在合并那一步、teaching_plan/figure/key_conclusion 压根没有；
    前端拿到的节点与改动前逐字相同，等于新特性不存在。
    """
    body = _run_create(monkeypatch, tmp_path, _create_payload())

    assert body["status"] == "done"
    node = body["nodes"][0]

    assert node["node_id"] == "node_plan_001"
    assert node["title"] == "复杂度基础"
    # 曾经被合并丢掉的字段
    assert node["point_details"] == [{"point": "时间复杂度", "detail": "描述增长趋势"}]
    # 规划器挂上去的三个
    assert node["teaching_plan"]["node_id"] == "node_plan_001"
    assert node["key_conclusion"]
    assert isinstance(node["figure"], dict)
    # 大纲定下的字段没被讲稿结果冲掉
    assert node["key_points"] == ["时间复杂度", "空间复杂度"]


def test_create_pipeline_still_succeeds_when_the_planner_dies(monkeypatch, tmp_path):
    """规划是加分项：规划服务挂掉，课件必须照常生成，只是没有 teaching_plan。

    断言用「空值」而不是「键不存在」：TeachingNode 给这三个字段都声明了默认值，
    序列化后键一定在，缺席只体现为空 dict / 空串。用 `not ...` 两种形态都覆盖得到。
    """
    monkeypatch.setattr(
        tp, "plan_deck",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("规划服务不可用")),
    )
    body = _run_create(monkeypatch, tmp_path, _create_payload())

    assert body["status"] == "done"
    node = body["nodes"][0]
    assert not node.get("teaching_plan")
    assert not node.get("figure")
    assert not node.get("key_conclusion")
    # 讲稿链路不受影响
    assert node["point_details"] == [{"point": "时间复杂度", "detail": "描述增长趋势"}]
