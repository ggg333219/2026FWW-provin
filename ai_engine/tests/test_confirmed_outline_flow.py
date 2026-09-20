import time

from fastapi.testclient import TestClient

from ai_engine import main as main_module
from ai_engine.core.llm import LLMClient
from ai_engine.gen.outline import OutlineBuilder
from ai_engine.main import app


client = TestClient(app)


def _confirmed_outline_payload(**overrides):
    payload = {
        "session_id": "sess_outline_contract",
        "intent": {"topic": "冒泡排序"},
        "outline_id": "outline_contract_001",
        "outline_version": 2,
        "outline_confirmed": True,
        "outline_nodes": [
            {
                "node_id": "node_teacher_001",
                "order": 1,
                "title": "教师确认的冒泡排序原理",
                "summary": "保持本节点，不得重新生成大纲覆盖",
                # 前端大纲编辑器使用 content；AI 生成层必须在边界处归一化。
                "node_type": "content",
                "key_points": ["相邻元素比较", "元素交换"],
                "estimated_duration_minutes": 10,
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_unconfirmed_outline_cannot_start_generation():
    response = client.post(
        "/api/v1/gen/create",
        json=_confirmed_outline_payload(outline_confirmed=False),
    )

    assert response.status_code == 409


def test_confirmed_outline_is_used_without_being_rebuilt(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module._task_store, "_use_redis", False)

    def fake_chat_with_schema(self, system_prompt, user_prompt, schema, **kwargs):
        return {
            "scripts": [
                {
                    "node_id": "node_teacher_001",
                    "title": "教师确认的冒泡排序原理",
                    "script": "按照教师确认的大纲生成内容。",
                    "segments": [
                        {
                            "segment_id": "seg_001",
                            "node_id": "node_teacher_001",
                            "text": "按照教师确认的大纲生成内容。",
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(LLMClient, "chat_with_schema", fake_chat_with_schema)

    created = client.post("/api/v1/gen/create", json=_confirmed_outline_payload())
    assert created.status_code == 200
    task_id = created.json()["task_id"]

    status = None
    for _ in range(500):
        status = client.get(f"/api/v1/gen/status/{task_id}")
        assert status.status_code == 200
        if status.json()["status"] in {"done", "failed"}:
            break
        time.sleep(0.02)

    body = status.json()
    assert body["status"] == "done"
    assert body["nodes"][0]["node_id"] == "node_teacher_001"
    assert body["nodes"][0]["title"] == "教师确认的冒泡排序原理"


def test_outline_revision_preserves_existing_node_ids():
    class FakeLLM:
        def chat_with_schema(self, *_args, **_kwargs):
            return {
                "nodes": [
                    {
                        "node_id": "model_replaced_id",
                        "title": "增加案例后的标题",
                        "summary": "增加一个课堂案例",
                        "node_type": "slide",
                        "key_points": ["案例"],
                    }
                ]
            }

    result = OutlineBuilder(llm_client=FakeLLM()).revise(
        [
            {
                "node_id": "node_teacher_001",
                "title": "原标题",
                "summary": "原摘要",
                "node_type": "slide",
                "key_points": ["原要点"],
            }
        ],
        "增加一个案例",
    )

    assert result["nodes"][0]["node_id"] == "node_teacher_001"
    assert result["change_summary"]


def test_gen_finalize_creates_snapshot_from_confirmed_content():
    """测试 /api/v1/gen/finalize 从确认的内容节点创建版本快照（PPT 生成步骤）。"""
    resp = client.post("/api/v1/gen/finalize", json={
        "nodes": [
            {
                "node_id": "node_001",
                "title": "冒泡排序原理",
                "node_type": "slide",
                "content": "介绍冒泡排序的基本过程",
                "summary": "介绍冒泡排序的基本过程",
                "script": "这是讲稿内容。",
                "segments": [
                    {
                        "segment_id": "seg_001",
                        "node_id": "node_001",
                        "text": "这是讲稿内容。",
                        "segment_type": "explanation",
                        "estimated_seconds": 45,
                    }
                ],
                "key_points": ["相邻元素比较", "元素交换"],
            }
        ],
        "course_name": "冒泡排序",
        "summary": "教师确认终稿",
        "page_bindings": [
            {"page_id": "node_001", "evidence_refs": ["chunk_sort_1"]}
        ],
        "presentation": {"template_id": "deck-swiss-edu", "palette": "forest"},
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["generation_id"] is not None
    assert body["generation_id"].startswith("course_")
    assert body["version_number"] == 1
    assert body["status"] == "done"

    # 验证版本快照已保存
    from ai_engine.gen.version import get_version_manager
    vm = get_version_manager()
    snap = vm.load_version(body["generation_id"])
    assert snap is not None
    assert snap.version_number == 1
    assert len(snap.nodes_snapshot) == 1
    assert snap.nodes_snapshot[0].node_id == "node_001"
    assert snap.page_bindings[0]["evidence_refs"] == ["chunk_sort_1"]
    assert snap.presentation["template_id"] == "deck-swiss-edu"

    loaded = client.get(f'/api/v1/version/{body["generation_id"]}?v=1')
    assert loaded.status_code == 200
    assert loaded.json()["page_bindings"] == snap.page_bindings
    assert loaded.json()["presentation"] == snap.presentation


def test_gen_finalize_with_existing_generation_id():
    """测试 /api/v1/gen/finalize 复用已有的 generation_id。"""
    import uuid
    unique_gen_id = f"course_reuse_{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/v1/gen/finalize", json={
        "generation_id": unique_gen_id,
        "nodes": [
            {
                "node_id": "node_001",
                "title": "冒泡排序原理",
                "node_type": "slide",
                "content": "介绍冒泡排序",
                "summary": "介绍冒泡排序",
                "script": "这是讲稿内容。",
                "segments": [],
            }
        ],
        "course_name": "冒泡排序",
        "summary": "修订后终稿",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["generation_id"] == unique_gen_id
    assert body["version_number"] == 1


def test_exp_contract_returns_versioned_filename():
    """契约路径 /exp 返回 filename/courseware_title/version_no，旧字段仍保留。"""
    import uuid
    generation_id = f"course_export_{uuid.uuid4().hex[:8]}"
    finalized = client.post("/api/v1/gen/finalize", json={
        "generation_id": generation_id,
        "nodes": [{
            "node_id": "node_tcp",
            "title": "TCP 三次握手",
            "node_type": "slide",
            "content": "SYN、SYN-ACK、ACK",
            "summary": "TCP 建连过程",
        }],
    })
    assert finalized.status_code == 200

    exported = client.post(f"/api/v1/exp/{generation_id}", json={
        "format": "pptx",
        "version": 1,
        "courseware_title": "TCP三次握手课件",
    })

    assert exported.status_code == 200
    body = exported.json()
    assert body["filename"] == "TCP三次握手课件_v1.pptx"
    assert body["courseware_title"] == "TCP三次握手课件"
    assert body["version_no"] == 1
    assert body["version"] == 1


def test_gen_modify_supports_content_task_ids():
    """测试 /api/v1/gen/modify 支持以 content_ 开头的任务 ID（内容修改场景）。"""
    import ai_engine.main as main_module

    content_id = "content_modify_test_001"
    main_module._content_tasks[content_id] = {
        "content_id": content_id,
        "status": "done",
        "progress_pct": 100.0,
        "nodes": [
            {
                "node_id": "node_001",
                "title": "原标题",
                "node_type": "slide",
                "content": "原内容",
                "summary": "原摘要",
                "script": "原讲稿内容。",
                "segments": [],
            }
        ],
    }

    # 不传 nodes，让端点从 content task 加载
    resp = client.post("/api/v1/gen/modify", json={
        "generation_id": content_id,
        "commands": [
            {"type": "update_node", "node_id": "node_001", "content": "新讲稿内容。"}
        ],
        "regenerate": False,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["node_id"] == "node_001"

    # 验证内容任务中的节点已被写回
    assert "nodes" in main_module._content_tasks[content_id]
    assert len(main_module._content_tasks[content_id]["nodes"]) == 1
    assert main_module._content_tasks[content_id]["nodes"][0]["node_id"] == "node_001"


def test_gen_modify_content_task_returns_404_for_missing_id():
    """测试 /api/v1/gen/modify 对不存在的 content_* ID 返回 404。"""
    resp = client.post("/api/v1/gen/modify", json={
        "generation_id": "content_nonexistent_999",
        "commands": [{"type": "update_node", "node_id": "node_001", "content": "新内容"}],
        "regenerate": False,
    })
    assert resp.status_code == 404
