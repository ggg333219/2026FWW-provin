import os
import time

os.environ.setdefault("AI_GEN_MODE", "mock")

from fastapi.testclient import TestClient

from ai_engine.gen.modify_intent import parse_modify_instruction
from ai_engine.main import app


NODES = [
    {"node_id": "node_1", "page_ref": 1, "title": "引言", "content": "原始引言"},
    {"node_id": "node_2", "page_ref": 2, "title": "概念", "content": "原始概念"},
    {"node_id": "node_3", "page_ref": 3, "title": "案例", "content": "原始案例"},
    {"node_id": "node_4", "page_ref": 4, "title": "总结", "content": "原始总结"},
]

client = TestClient(app)


def test_parse_compound_page_instruction():
    result = parse_modify_instruction("p1", "第三页太复杂，减少文字，增加一个生活案例", NODES)

    assert result["target_type"] == "node"
    assert result["target_ids"] == ["node_3"]
    assert result["actions"] == ["simplify", "expand"]
    assert "减少文字量" in result["constraints"]
    assert "增加生活案例" in result["constraints"]
    assert result["clarification_needed"] is False


def test_parse_reorder_instruction():
    result = parse_modify_instruction("p1", "把第二部分和第三部分换一下", NODES)

    assert result["action"] == "reorder"
    assert result["target_ids"] == ["node_2", "node_3"]


def test_parse_global_style_instruction():
    result = parse_modify_instruction("p1", "整体风格换成科技感", NODES)

    assert result["target_type"] == "style"
    assert result["action"] == "restyle"
    assert result["target_ids"] == []
    assert result["clarification_needed"] is False


def test_unknown_target_requests_clarification():
    result = parse_modify_instruction("p1", "帮我优化一下", NODES)

    assert result["clarification_needed"] is True
    assert result["confidence"] < 0.6


def test_partial_content_keeps_non_target_nodes_unchanged():
    response = client.post(
        "/api/v1/gen/content",
        json={
            "nodes": [
                *NODES[:2],
                {**NODES[2], "node_type": "interactive", "type": "interactive"},
                *NODES[3:],
            ],
            "mode": "partial",
            "target_node_ids": ["node_3"],
            "modify_instruction": "减少文字，增加生活案例",
            "actions": ["simplify", "expand"],
            "constraints": ["保留核心知识点", "增加生活案例"],
        },
    )
    assert response.status_code == 200
    content_id = response.json()["content_id"]
    for _ in range(400):
        result = client.get(f"/gen/content/status/{content_id}").json()
        if result["status"] in {"done", "failed"}:
            break
        time.sleep(0.01)
    assert result["status"] == "done"
    by_id = {node["node_id"]: node for node in result["nodes"]}
    assert by_id["node_1"]["content"] == "原始引言"
    assert by_id["node_2"]["content"] == "原始概念"
    assert by_id["node_4"]["content"] == "原始总结"
    assert by_id["node_3"]["content"] != "原始案例"
