from fastapi.testclient import TestClient
from ai_engine.main import app


client = TestClient(app)


def test_intent_extract_rule_mode_and_confirm():
    payload = {
        "session_id": "test_sess_1",
        "messages": [
            {"role": "teacher", "content": "帮我做一份45分钟的排序算法课件，面向大一计算机专业，讲练结合。包括冒泡排序, 快速排序"}
        ],
    }
    r = client.post("/intent/extract?mode=rule", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data.get("intent_summary")
    assert "need_followup" in data

    # confirm
    r2 = client.post("/intent/confirm", json={"session_id": "test_sess_1"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("confirmed") is True or d2.get("session_status") == "confirmed"


def test_intent_extract_default_mode():
    payload = {
        "session_id": "test_sess_2",
        "messages": [{"role": "teacher", "content": "请帮我做一份课件"}],
    }
    r = client.post("/intent/extract", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data.get("intent_summary")
