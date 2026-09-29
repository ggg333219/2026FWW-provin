"""P4：局部修改之后，这一页的表达决策要跟着正文一起变。

``/api/v1/gen/modify`` 是老师改单页真正走的那条路（CommandParser → NodePatcher.apply）。
改动前它只回写 ``script`` / ``segments`` / ``point_details``：老师把第 2 页的正文重写了，
幻灯片上的图示和大字结论还停在旧内容上 —— 看起来就是「改了等于没改」。这个文件锁住四件事：

  1. **合并尺度**：``generate_single`` 恒返回全键且值可能为空，``{**node, **script_data}``
     会把该页已有分段清空；而同一个 dict 还带着前端在消费的 ``reteach_script`` /
     ``transition``，换成字段白名单又会把这些悄悄丢掉。两个方向都要挡住。
  2. **替换语义**：重规划说这页不该出图 / 不该有结论时，旧的必须真的删掉。
  3. **意图透传**：教学意图由 create 落进快照 metadata，modify 读回来交给规划器，
     并且跨版本存活（改第二次不能丢）。
  4. **范围**：只有目标页被重规划，其他页一字未动。
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_engine.core.llm import LLMClient  # noqa: E402
from ai_engine.gen import teaching_plan as tp  # noqa: E402
from ai_engine.gen.node import merge_script_into_node  # noqa: E402
from ai_engine.gen.version import VersionManager  # noqa: E402
from ai_engine.main import _attach_teaching_plan, app  # noqa: E402

client = TestClient(app)


# =============================================================================
# 1. 合并尺度：两个方向都要挡住
# =============================================================================

def test_merge_keeps_the_keys_the_frontend_reads():
    """modify 路径的 dict 是模型原样返回，带 mindmap_markdown / reteach_script / transition。

    前端在读这三个（docs §3 A6 的 reteachScript / transitionText），字段白名单式合并
    会把它们无声丢掉 —— 这正是共用函数用「保护键黑名单」而不是白名单的原因。
    """
    node = {"node_id": "n1", "title": "复杂度"}
    merged = merge_script_into_node(node, {
        "node_id": "n1", "title": "n1", "script": "讲稿",
        "reteach_script": "换个说法再讲一遍", "transition": "下一节看空间复杂度",
        "mindmap_markdown": "- 复杂度",
    })

    assert merged["reteach_script"] == "换个说法再讲一遍"
    assert merged["transition"] == "下一节看空间复杂度"
    assert merged["mindmap_markdown"] == "- 复杂度"
    assert merged["script"] == "讲稿"
    assert merged["title"] == "复杂度"  # 保护键：不被脚本里的 "n1" 覆盖


def test_empty_script_fields_do_not_wipe_what_is_already_there():
    """模型这次没给分段 → generate_single 返回 segments: [] → 不能把已有分段清空。

    这是「改完之后预览里的分段区块整个消失」的根因：真值短路把空列表当成了有效值。
    """
    node = {
        "node_id": "n1", "title": "复杂度",
        "segments": [{"segment_id": "seg_001", "text": "旧分段"}],
        "point_details": [{"point": "旧要点", "detail": "旧展开"}],
    }
    merged = merge_script_into_node(
        node, {"script": "新讲稿", "segments": [], "point_details": []}
    )

    assert merged["segments"] == [{"segment_id": "seg_001", "text": "旧分段"}]
    assert merged["point_details"] == [{"point": "旧要点", "detail": "旧展开"}]
    assert merged["script"] == "新讲稿"


# =============================================================================
# 2. 替换语义：规划说没有，旧的就该真的没有
# =============================================================================

def test_replace_drops_the_stale_figure_and_conclusion():
    """第 2 页原来出流程图，改完规划说不该出图 —— 旧的必须删掉。

    只挂不删的话，幻灯片上会留着一张与新正文对不上的图，比没有图更糟。
    """
    node = {
        "node_id": "n1",
        "figure": {"kind": "flow", "items": ["旧 A"]},
        "key_conclusion": "旧结论",
        "teaching_plan": {"node_id": "n1", "visual_type": "flow"},
    }
    merged = _attach_teaching_plan(
        node, {"node_id": "n1", "teaching_goal": "改后目标", "visual_type": "none", "key_conclusion": ""},
        replace=True,
    )

    assert "figure" not in merged
    assert "key_conclusion" not in merged
    assert merged["teaching_plan"]["visual_type"] == "none"


def test_without_replace_never_deletes():
    """新建路径的语义不能变：节点本来是干净的，只挂不删。"""
    node = {"node_id": "n1", "figure": {"kind": "flow"}}
    merged = _attach_teaching_plan(node, {"node_id": "n1", "visual_type": "none"})
    assert merged["figure"] == {"kind": "flow"}


def test_replace_keeps_the_old_plan_when_the_new_one_is_empty():
    """拿不到新决策不等于旧决策错了 —— 不该因为一次规划失败把整页的图和结论抹掉。"""
    node = {
        "node_id": "n1", "figure": {"kind": "flow"}, "key_conclusion": "旧结论",
        "teaching_plan": {"node_id": "n1", "visual_type": "flow"},
    }
    assert _attach_teaching_plan(node, {}, replace=True) == node


# =============================================================================
# 3. 端到端：/api/v1/gen/modify
# =============================================================================

_META = {
    "outline_id": "outline_modify_001",
    "intent": {"topic": "排序算法", "style": "案例驱动", "target_student": "大一计算机专业"},
}


def _nodes() -> list[dict]:
    return [
        {"node_id": "n1", "title": "课程封面", "node_type": "cover", "type": "cover",
         "summary": "排序算法。"},
        {"node_id": "n2", "title": "复杂度基础", "node_type": "slide", "type": "slide",
         "summary": "复杂度描述算法规模增长趋势。", "key_points": ["时间复杂度"],
         "segments": [{"segment_id": "seg_001", "text": "旧分段", "node_id": "n2"}],
         "point_details": [{"point": "旧要点", "detail": "旧展开"}],
         "figure": {"kind": "flow", "title": "旧图", "items": ["旧 A", "旧 B"]},
         "key_conclusion": "旧结论",
         "teaching_plan": {"node_id": "n2", "visual_type": "flow"}},
        {"node_id": "n3", "title": "空间复杂度", "node_type": "slide", "type": "slide",
         "summary": "额外空间随输入规模增长。",
         "figure": {"kind": "cycle", "title": "n3 的图", "items": ["甲", "乙"]},
         "key_conclusion": "n3 的结论"},
    ]


def _replanned_at_target(node: dict) -> dict:
    """一个「改完之后应该长这样」的规划。"""
    return {
        "node_id": node.get("node_id"), "teaching_goal": "改后目标",
        "visual_type": "flow", "visual_structure": ["输入规模", "增长趋势"],
        "key_conclusion": "改后的结论",
    }


def _fake_script(self, system_prompt, user_prompt, **kwargs):
    """generate_single 的返回。segments 刻意留空 —— 模型这次没给分段。"""
    return {
        "node_id": "n2", "title": "复杂度基础",
        "script": "改后讲稿",
        "segments": [],
        "point_details": [{"point": "新要点", "detail": "新展开"}],
        # 前端在读、且不在旧字段白名单里的键
        "reteach_script": "换个说法再讲一遍",
        "transition": "下一节看空间复杂度",
    }


def _run_modify(monkeypatch, tmp_path, planner):
    """跑一次 /api/v1/gen/modify（改 n2），返回 (响应体, 规划器实际收到的 (intent, node_id))。"""
    monkeypatch.chdir(tmp_path)
    VersionManager().save_snapshot("gen_modify_001", _nodes(), "初稿", metadata=_META)

    seen: list[tuple] = []

    def spy_plan_node(intent, node, *, evidence="", llm=None):
        seen.append((intent, node.get("node_id")))
        # 过一遍 normalize_plan，与真实 plan_node 的返回形态一致：它交出去的是
        # **规范化之后**的规划（visual_structure 记的是真会画出来的东西）。
        return tp.normalize_plan(planner(node), str(node.get("node_id") or "")) or {}

    monkeypatch.setattr(tp, "plan_node", spy_plan_node)
    monkeypatch.setattr(LLMClient, "chat_json", _fake_script)

    resp = client.post("/api/v1/gen/modify", json={
        "generation_id": "gen_modify_001",
        "commands": [{"type": "update_node", "node_id": "n2", "regenerate": True}],
        "regenerate": True,
        "user_instruction": "强调增长趋势",
    })
    assert resp.status_code == 200
    return resp.json(), seen


def test_modify_replans_the_target_page(monkeypatch, tmp_path):
    """本轮的全部意义：改完第 2 页，结论、图示、展开同时变。"""
    body, _ = _run_modify(monkeypatch, tmp_path, _replanned_at_target)
    assert body["errors"] == []
    by_id = {n["node_id"]: n for n in body["nodes"]}
    target = by_id["n2"]

    # 重规划的三个产物都换了
    assert target["key_conclusion"] == "改后的结论"
    assert target["figure"]["items"] == ["输入规模", "增长趋势"]
    assert target["teaching_plan"]["teaching_goal"] == "改后目标"
    # 正文侧：point_details 换了，segments 没被空列表冲掉
    assert target["point_details"] == [{"point": "新要点", "detail": "新展开"}]
    assert target["segments"] == [{"segment_id": "seg_001", "text": "旧分段", "node_id": "n2"}]
    # 前端在读的键没被合并规则丢掉
    assert target["reteach_script"] == "换个说法再讲一遍"
    # 大纲定下的字段没被讲稿模型改写
    assert target["title"] == "复杂度基础"
    assert target["key_points"] == ["时间复杂度"]


def test_only_the_target_page_is_replanned(monkeypatch, tmp_path):
    """「其他页一字未动」是这条路径的契约，也是老师最容易一眼看出来的回归。

    比的是 v1 与 v2 两份快照本身，而不是手写的 fixture：节点从快照读出来时会被
    ``TeachingNode`` 补全一整套默认值，拿手写的最小 dict 去比对必然不相等 ——
    那测的是"我记不记得住有哪些字段"，不是"这页动没动"。
    """
    body, seen = _run_modify(monkeypatch, tmp_path, _replanned_at_target)
    before = {
        node.node_id: node.model_dump()
        for node in VersionManager().load_version("gen_modify_001", 1).nodes_snapshot
    }
    after = {n["node_id"]: n for n in body["nodes"]}

    assert [node_id for _, node_id in seen] == ["n2"]
    assert after["n1"] == before["n1"]
    assert after["n3"] == before["n3"]
    assert after["n2"] != before["n2"]
    # 顺带把「其他页一字未动」具体化：n3 的图与结论原封不动
    assert after["n3"]["key_conclusion"] == "n3 的结论"
    assert after["n3"]["figure"] == {"kind": "cycle", "title": "n3 的图", "items": ["甲", "乙"]}


def test_the_stored_intent_reaches_the_planner(monkeypatch, tmp_path):
    """create 把 intent 写进快照 metadata，modify 必须读回来交给规划器。

    否则「改一页」时规划看不见教学主题 / 风格 / 对象，与整份课件的意图脱节 ——
    这正是 P4 选 b 方案（意图落盘）而不是让规划器空手跑的原因。
    """
    _, seen = _run_modify(monkeypatch, tmp_path, _replanned_at_target)

    intent, _node_id = seen[0]
    assert intent["topic"] == "排序算法"
    assert intent["style"] == "案例驱动"


def test_the_new_version_keeps_the_intent(monkeypatch, tmp_path):
    """改第二次不能丢意图：save_snapshot 不带 metadata 就会把它抹成 {}。"""
    _run_modify(monkeypatch, tmp_path, _replanned_at_target)

    latest = VersionManager().load_version("gen_modify_001")
    assert latest.version_number == 2
    assert latest.metadata["intent"]["topic"] == "排序算法"


def test_replanning_failure_keeps_the_page_intact(monkeypatch, tmp_path):
    """规划是加分项：规划服务挂掉时页面保留原来的图示与结论，而不是变得光秃秃。"""

    def _explode(node):
        raise RuntimeError("规划服务不可用")

    body, _ = _run_modify(monkeypatch, tmp_path, _explode)
    assert body["errors"] == []
    by_id = {n["node_id"]: n for n in body["nodes"]}

    assert by_id["n2"]["key_conclusion"] == "旧结论"
    assert by_id["n2"]["figure"]["items"] == ["旧 A", "旧 B"]
    # 正文照样改成功 —— 规划失败不该拖垮这次修改
    assert by_id["n2"]["point_details"] == [{"point": "新要点", "detail": "新展开"}]
