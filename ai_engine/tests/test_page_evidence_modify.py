"""契约 v1.0 模块1 接口3：`POST /api/v1/gen/modify` 的 `evidence_refs` 证据约束。

验收标准（契约 §3 模块1）：
    将资料 chunk 绑定到第3页 → 对第3页做局部修改时，AI 只引用该页绑定的 chunk。

同时锁定向后兼容：不传 `evidence_refs` 时保持既有全库行为，重生成提示词不受影响。
"""

from importlib import import_module
from types import SimpleNamespace

from fastapi.testclient import TestClient

import ai_engine.main as main_module
from ai_engine.main import app


client = TestClient(app)


class _FakeChunkStore:
    """只实现 get_chunk 的最小知识库替身，用于隔离向量库依赖。"""

    def __init__(self, chunks: dict):
        self._chunks = chunks

    def get_chunk(self, chunk_id: str):
        return self._chunks.get(chunk_id)


def _install_fake_store(monkeypatch, chunks: dict):
    """把 ai_engine.rag.router 的全局存储替换为内存替身，测试后由 monkeypatch 还原。

    注意：该模块内部定义了 `router = APIRouter()` 会遮蔽包属性，
    必须用 import_module 取模块本身，不能用 `import ... as`。
    """
    rag_router = import_module("ai_engine.rag.router")
    monkeypatch.setattr(rag_router, "_store", _FakeChunkStore(chunks))


class _RecordingGenerator:
    """记录每次重生成的 extra_instruction，避免真实调用 LLM。"""

    calls: list[tuple[str, str]] = []

    def __init__(self, *args, **kwargs):
        pass

    def generate_single(self, node, course_name=None, max_attempts=None, extra_instruction=""):
        node = dict(node)
        _RecordingGenerator.calls.append((node.get("node_id", ""), extra_instruction))
        node["title"] = f"重生成:{node.get('node_id')}"
        return node


def _modify_payload(commands, **overrides):
    """构造内联节点的修改请求。

    不传 generation_id：端点在只有内联节点时走"原有行为"，不会落版本快照，
    从而隔离版本管理器与本用例无关的校验。
    """
    payload = {
        "nodes": [
            {"node_id": "page_001", "title": "第一页", "node_type": "slide", "content": "第一页正文"},
            {"node_id": "page_002", "title": "第二页", "node_type": "slide", "content": "第二页正文"},
        ],
        "commands": commands,
        "regenerate": True,
    }
    payload.update(overrides)
    return payload


def test_load_page_evidence_only_returns_bound_chunks(monkeypatch):
    """只取绑定 chunk 的原文；缺失/重复的 chunk_id 被静默跳过。"""
    _install_fake_store(monkeypatch, {
        "chunk_a": SimpleNamespace(chunk_id="chunk_a", content="冒泡排序的相邻比较规则"),
        "chunk_c": SimpleNamespace(chunk_id="chunk_c", content="选择排序的最优情况复杂度"),
    })

    context, used = main_module._load_page_evidence(["chunk_a", "chunk_missing", "chunk_a", None, ""])

    assert used == ["chunk_a"], used
    assert "冒泡排序的相邻比较规则" in context
    assert "选择排序" not in context
    assert "chunk_missing" not in context


def test_load_page_evidence_empty_input(monkeypatch):
    _install_fake_store(monkeypatch, {"chunk_a": SimpleNamespace(chunk_id="chunk_a", content="内容")})
    assert main_module._load_page_evidence([]) == ("", [])
    assert main_module._load_page_evidence(["chunk_missing"]) == ("", [])


def test_modify_evidence_refs_constrains_only_target_page(monkeypatch):
    """契约验收：绑定到第3页的证据只作用于第3页，其他页不拿到证据上下文。"""
    generator_calls = []
    monkeypatch.setattr(main_module, "NodeGenerator", _RecordingGenerator)
    _RecordingGenerator.calls = generator_calls
    _install_fake_store(monkeypatch, {
        "chunk_page3": SimpleNamespace(chunk_id="chunk_page3", content="TCP 三次握手 SYN 标志位含义"),
        "chunk_page7": SimpleNamespace(chunk_id="chunk_page7", content="TCP 四次挥手 TIME_WAIT 时长"),
    })

    resp = client.post(
        "/api/v1/gen/modify",
        json=_modify_payload(
            [
                {"type": "update_node", "node_id": "page_001", "regenerate": True},
                {"type": "update_node", "node_id": "page_002", "regenerate": True},
            ],
            page_id="page_001",
            evidence_refs=["chunk_page3", "chunk_missing"],
            user_instruction="讲清楚 SYN 标志位",
        ),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok", body

    # 响应回传本次实际引用的证据（契约 §4.1 引用来源字段）
    assert body["page_id"] == "page_001"
    assert body["citation_refs"] == ["chunk_page3"], body["citation_refs"]
    assert body["evidence_used"] == ["chunk_page3"]

    # 目标页拿到证据约束；其他页不注入
    instructions = dict(generator_calls)
    assert instructions["page_001"], "目标页应拿到证据上下文"
    assert "TCP 三次握手 SYN 标志位含义" in instructions["page_001"]
    assert "TIME_WAIT" not in instructions["page_001"], "非绑定资料不得进入上下文"
    assert "讲清楚 SYN 标志位" in instructions["page_001"]
    assert instructions["page_002"] == "", "未绑定该证据的页面不应收到证据上下文"


def test_modify_evidence_refs_without_page_id_applies_globally(monkeypatch):
    """未指定 page_id 时，证据上下文作用于所有重生成节点（局部修改批量场景）。"""
    generator_calls = []
    monkeypatch.setattr(main_module, "NodeGenerator", _RecordingGenerator)
    _RecordingGenerator.calls = generator_calls
    _install_fake_store(monkeypatch, {
        "chunk_a": SimpleNamespace(chunk_id="chunk_a", content="全局资料片段"),
    })

    resp = client.post(
        "/api/v1/gen/modify",
        json=_modify_payload(
            [
                {"type": "update_node", "node_id": "page_001", "regenerate": True},
                {"type": "update_node", "node_id": "page_002", "regenerate": True},
            ],
            evidence_refs=["chunk_a"],
        ),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_id"] is None
    assert body["citation_refs"] == ["chunk_a"]

    instructions = dict(generator_calls)
    assert all("全局资料片段" in text for text in instructions.values()), instructions


def test_modify_without_evidence_refs_keeps_legacy_behaviour(monkeypatch):
    """向后兼容：不传 evidence_refs 时重生成提示词不变，不注入证据块。"""
    generator_calls = []
    monkeypatch.setattr(main_module, "NodeGenerator", _RecordingGenerator)
    _RecordingGenerator.calls = generator_calls
    _install_fake_store(monkeypatch, {
        "chunk_a": SimpleNamespace(chunk_id="chunk_a", content="不应出现的资料"),
    })

    resp = client.post(
        "/api/v1/gen/modify",
        json=_modify_payload(
            [{"type": "update_node", "node_id": "page_001", "regenerate": True}],
            user_instruction="只调整语气",
        ),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok", body
    assert body["page_id"] is None
    assert body["citation_refs"] == []
    assert body["evidence_used"] == []

    instructions = dict(generator_calls)
    assert instructions["page_001"] == "只调整语气", instructions["page_001"]
    assert "不应出现的资料" not in instructions["page_001"]


def test_modify_rejects_unknown_node_even_with_evidence(monkeypatch):
    """证据参数不应绕过既有的节点存在性校验。"""
    monkeypatch.setattr(main_module, "NodeGenerator", _RecordingGenerator)
    _install_fake_store(monkeypatch, {
        "chunk_a": SimpleNamespace(chunk_id="chunk_a", content="资料"),
    })

    resp = client.post(
        "/api/v1/gen/modify",
        json=_modify_payload(
            [{"type": "update_node", "node_id": "page_missing", "regenerate": True}],
            page_id="page_missing",
            evidence_refs=["chunk_a"],
        ),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "validation_error", body
    assert body["errors"], body
