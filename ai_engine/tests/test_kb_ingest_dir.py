"""本地目录批量灌入知识库的回归测试。

覆盖三条最容易悄悄坏掉的地方：
  1. 计划扫描能筛掉不支持的格式和 Office 临时文件（dry_run 不写库）
  2. 真实灌入后文件确实可被检索命中（防止"入库成功但向量是零向量"）
  3. 0 块文件（扫描件/空文件）要被显式列出来，而不是假装成功
"""

import importlib
import os

os.environ.setdefault("AI_GEN_MODE", "mock")
os.environ.setdefault("RAG_STORE_BACKEND", "memory")

from fastapi.testclient import TestClient  # noqa: E402

from ai_engine.main import app  # noqa: E402

rag_router = importlib.import_module("ai_engine.rag.router")

client = TestClient(app)

KB_ID = "kb_ingest_dir_test"


def _prepare_dir(tmp_path):
    (tmp_path / "课件正文.md").write_text(
        "# TCP 三次握手\n第一次客户端发送 SYN；第二次服务端返回 SYN+ACK；第三次客户端返回 ACK。\n",
        encoding="utf-8",
    )
    (tmp_path / "讲义.txt").write_text("TCP 的可靠传输依赖确认应答与重传机制。", encoding="utf-8")
    # 不支持的格式 + Office 临时文件：都应被跳过
    (tmp_path / "老课件.ppt").write_bytes(b"\xd0\xcf\x11\xe0binary-garbage")
    (tmp_path / "~$课件正文.md").write_text("临时锁定文件", encoding="utf-8")
    # 空文件：能读到 0 字符，应进 zero_chunk 而不是被算作成功
    (tmp_path / "空文档.md").write_text("", encoding="utf-8")
    return tmp_path


def test_scan_plan_skips_unsupported_and_temp_files(tmp_path, monkeypatch):
    _prepare_dir(tmp_path)
    monkeypatch.setenv("KB_INGEST_ALLOWED_ROOTS", str(tmp_path))
    rag_router._store.clear()

    resp = client.post("/api/v1/knowledge/ingest-dir", json={
        "directory": str(tmp_path),
        "knowledge_base_id": KB_ID,
        "dry_run": True,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    planned_names = {item["name"] for item in body["planned"]}
    assert planned_names == {"课件正文.md", "讲义.txt", "空文档.md"}
    skipped_names = {item["name"] for item in body["skipped"]}
    assert "老课件.ppt" in skipped_names
    assert "~$课件正文.md" not in planned_names  # Office 临时文件不应入库


def test_ingest_dir_then_searchable(tmp_path, monkeypatch):
    _prepare_dir(tmp_path)
    monkeypatch.setenv("KB_INGEST_ALLOWED_ROOTS", str(tmp_path))
    rag_router._store.clear()

    resp = client.post("/api/v1/knowledge/ingest-dir", json={
        "directory": str(tmp_path),
        "knowledge_base_id": KB_ID,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    print("[ingest-dir]", {
        "ingested": [(i["name"], i["chunks"]) for i in body["ingested"]],
        "zero_chunk": [i["name"] for i in body["zero_chunk"]],
        "total": body["total_chunks"],
        "probe": body["retrieval_probe"],
    })
    assert body["ok"] is True
    assert body["dry_run"] is False

    names = {item["name"]: item["chunks"] for item in body["ingested"]}
    assert names.get("课件正文.md", 0) > 0
    assert names.get("讲义.txt", 0) > 0
    # 0 块文件必须显式暴露，而不是静默丢弃
    assert "空文档.md" in {item["name"] for item in body["zero_chunk"]}
    assert body["total_chunks"] > 0
    # 灌完做一次真实检索自检
    assert body["retrieval_probe"].get("status") == "ok"

    searched = client.post("/api/v1/rag/search", json={
        "query": "TCP 三次握手",
        "knowledge_base_ids": [KB_ID],
        "top_k": 5,
        "min_score": 0.0,
    })
    assert searched.status_code == 200
    results = searched.json()["results"]
    assert results, "灌入后应能检索到内容"
    assert any("三次握手" in (item["content"] or "") for item in results)
    rag_router._store.clear()


def test_directory_outside_allowlist_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("KB_INGEST_ALLOWED_ROOTS", raising=False)
    resp = client.post("/api/v1/knowledge/ingest-dir", json={
        "directory": str(tmp_path),
        "dry_run": True,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert "允许范围" in (body.get("error") or "")
