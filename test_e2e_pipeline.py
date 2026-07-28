import os
import json
import time
from pathlib import Path
from urllib import error, request


BASE_URL = os.getenv("AI_ENGINE_BASE_URL", "http://127.0.0.1:8000/api/v1")
ROOT_URL = os.getenv("AI_ENGINE_ROOT_URL", "http://127.0.0.1:8000")
SESSION_ID = os.getenv("E2E_SESSION_ID", f"e2e_{int(time.time())}")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _sample_file() -> Path:
    candidates = [
        _repo_root() / "文档" / "服务外包省赛A12赛题.docx",
        _repo_root() / "README.md",
        _repo_root() / "ai_engine" / "README.md",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("找不到可用于解析的样例文件")


def _request_json(method: str, url: str, payload: dict | None = None, timeout: int = 120):
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200, f"请求失败 {url}: {response.status} {body}"
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise AssertionError(f"请求失败 {url}: {exc.code} {body}") from exc


def _post_json(url: str, payload: dict, timeout: int = 120):
    return _request_json("POST", url, payload, timeout=timeout)


def _get_json(url: str, timeout: int = 120):
    return _request_json("GET", url, None, timeout=timeout)


def _ensure(condition: bool, message: str):
    assert condition, message


def _require_dict(value, message: str) -> dict:
    _ensure(isinstance(value, dict), message)
    return value


def _require_list(value, message: str) -> list:
    _ensure(isinstance(value, list), message)
    return value


def _short_text(value, limit: int = 80) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _poll_parse_status(task_id: str, timeout_seconds: int = 180):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        data = _get_json(f"{BASE_URL}/parse/status/{task_id}")
        status = str(data.get("status", "")).lower()
        if status in {"done", "failed"}:
            return data
        time.sleep(1)
    raise TimeoutError(f"解析任务超时: {task_id}")


def _poll_generation_status(task_id: str, timeout_seconds: int = 180):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        data = _get_json(f"{BASE_URL}/gen/status/{task_id}")
        status = str(data.get("status", "")).lower()
        if status in {"done", "failed"}:
            return data
        time.sleep(1)
    raise TimeoutError(f"生成任务超时: {task_id}")


def run_e2e_test():
    print("🚀 开始 AI Engine 4-Skill 全链路联调测试...\n")

    sample_path = _sample_file()
    print(f"使用样例文件: {sample_path}")

    # -------------------------------------------------------------
    # Skill 1: 意图理解
    # -------------------------------------------------------------
    print("---- [1/4] 测试 Skill 1: 意图理解 ----")
    intent_payload = {
        "session_id": SESSION_ID,
        "messages": [
            {
                "role": "teacher",
                "content": "帮我做一份45分钟的排序算法课件，面向大一计算机专业，讲练结合，重点覆盖冒泡排序、快速排序和课堂互动。",
            }
        ],
    }
    intent_data = _post_json(f"{ROOT_URL}/intent/extract?mode=rule", intent_payload)
    intent_summary = _require_dict(intent_data.get("intent_summary") or {}, "Skill 1 失败: 未返回 intent_summary")
    session_status = str(intent_data.get("session_status") or "").strip().lower()
    allowed_session_status = {"collecting", "clarifying", "confirming", "confirmed", "locked"}
    _ensure(session_status in allowed_session_status, f"Skill 1 失败: 非法 session_status: {session_status!r}")
    _ensure(
        isinstance(intent_summary.get("missing_fields", []), list),
        "Skill 1 失败: missing_fields 必须是列表",
    )
    if intent_summary.get("topic") is not None:
        _ensure(isinstance(intent_summary.get("topic"), str), "Skill 1 失败: topic 必须为字符串或 null")
    if intent_summary.get("title") is not None:
        _ensure(isinstance(intent_summary.get("title"), str), "Skill 1 失败: title 必须为字符串或 null")
    print(
        f"✅ Skill 1 成功! topic: {intent_summary.get('topic') or intent_summary.get('title')}, "
        f"status: {session_status}"
    )

    confirm_data = _post_json(f"{ROOT_URL}/intent/confirm", {"session_id": SESSION_ID})
    print(f"  └─ 确认结果: {confirm_data.get('confirmed')}, session_status: {confirm_data.get('session_status')}")

    # -------------------------------------------------------------
    # Skill 2: 多模态解析
    # -------------------------------------------------------------
    print("\n---- [2/4] 测试 Skill 2: 多模态解析 ----")
    parse_payload = {
        "session_id": SESSION_ID,
        "file_paths": [str(sample_path)],
    }
    parse_data = _post_json(f"{BASE_URL}/parse/process", parse_payload)
    task_id = parse_data.get("task_id")
    assert task_id, "Skill 2 失败: 未返回 task_id"
    print(f"✅ Skill 2 已创建解析任务: {task_id}")

    parse_status = _poll_parse_status(task_id)
    assert str(parse_status.get("status", "")).lower() == "done", f"Skill 2 失败: {parse_status}"
    chunks = _require_list(parse_status.get("chunks", []), "Skill 2 失败: chunks 必须是列表")
    _ensure(chunks, "Skill 2 失败: 未解析出 chunks")
    first_chunk = _require_dict(chunks[0], "Skill 2 失败: 第一个 chunk 不是对象")
    for key in ["chunk_id", "source_type", "source_ref", "content", "seq_index", "metadata"]:
        _ensure(key in first_chunk, f"Skill 2 失败: chunk 缺少字段 {key}")
    _ensure(isinstance(first_chunk["chunk_id"], str) and first_chunk["chunk_id"], "Skill 2 失败: chunk_id 非法")
    _ensure(isinstance(first_chunk["source_type"], str) and first_chunk["source_type"], "Skill 2 失败: source_type 非法")
    _ensure(isinstance(first_chunk["content"], str) and first_chunk["content"].strip(), "Skill 2 失败: content 不能为空")
    _ensure(isinstance(first_chunk["seq_index"], int), "Skill 2 失败: seq_index 必须为整数")
    _ensure(isinstance(first_chunk["metadata"], dict), "Skill 2 失败: metadata 必须为对象")
    print(f"✅ Skill 2 成功! 解析出 {len(chunks)} 个 chunks")
    print(f"  └─ Chunk 示例: {first_chunk['chunk_id']} | {first_chunk['source_type']} | {_short_text(first_chunk['content'], 120)}")

    # -------------------------------------------------------------
    # Skill 3: 知识库入库 / RAG 证据融合
    # -------------------------------------------------------------
    print("\n---- [3/4] 测试 Skill 3: 知识库入库与证据融合 ----")
    kb_upload_data = _post_json(
        f"{BASE_URL}/knowledge/upload",
        {
            "session_id": SESSION_ID,
            "knowledge_base_id": "",
            "files": [],
            "texts": [],
        },
    )
    assert kb_upload_data.get("status") == "done", f"Skill 3 失败: {kb_upload_data}"
    print(f"✅ 知识库入库成功! chunk_count: {kb_upload_data.get('chunk_count')}, document_id: {kb_upload_data.get('document_id')}")

    evidence_query = str(intent_summary.get("topic") or intent_summary.get("title") or "排序算法")
    evidence_data = _post_json(
        f"{BASE_URL}/rag/evidence",
        {
            "query": evidence_query,
            "context": {"session_id": SESSION_ID},
            "knowledge_base_ids": [],
        },
    )
    evidence_packet = _require_dict(evidence_data.get("evidence_packet") or {}, "Skill 3 失败: 未返回 evidence_packet")
    relevant_chunks = _require_list(evidence_packet.get("relevant_chunks") or evidence_packet.get("chunks") or [], "Skill 3 失败: 证据块必须是列表")
    _ensure(relevant_chunks, "Skill 3 失败: 未命中证据块")
    first_evidence = _require_dict(relevant_chunks[0], "Skill 3 失败: 第一个证据块不是对象")
    _ensure("content" in first_evidence, "Skill 3 失败: 证据块缺少 content")
    _ensure("score" in first_evidence or "metadata" in first_evidence, "Skill 3 失败: 证据块缺少 score 或 metadata")
    if "score" in first_evidence:
        _ensure(isinstance(first_evidence["score"], (int, float)), "Skill 3 失败: score 必须为数值")
    if "source" in first_evidence:
        _ensure(isinstance(first_evidence["source"], dict), "Skill 3 失败: source 必须为对象")
    print(f"✅ Skill 3 成功! 命中 {len(relevant_chunks)} 个证据块")
    print(f"  └─ 证据块示例: score={first_evidence.get('score')}, content={_short_text(first_evidence.get('content'), 120)}")

    # -------------------------------------------------------------
    # Skill 4: 课件生成 + 预览修改
    # -------------------------------------------------------------
    print("\n---- [4/4] 测试 Skill 4: 课件生成与个性化修改 ----")
    generation_payload = {
        "session_id": SESSION_ID,
        "intent": intent_summary,
        "evidence_packet": evidence_packet,
        "template_id": "default",
    }
    gen_create_data = _post_json(f"{BASE_URL}/gen/create", generation_payload)
    gen_task_id = gen_create_data.get("task_id")
    assert gen_task_id, "Skill 4 失败: 未返回生成 task_id"
    print(f"✅ 生成任务已创建: {gen_task_id}")

    gen_status = _poll_generation_status(gen_task_id)
    assert str(gen_status.get("status", "")).lower() == "done", f"Skill 4 失败: {gen_status}"
    nodes = _require_list(gen_status.get("nodes", []), "Skill 4 失败: nodes 必须是列表")
    _ensure(nodes, "Skill 4 失败: 未生成 nodes")
    for index, node in enumerate(nodes):
        node_obj = _require_dict(node, f"Skill 4 失败: 第 {index + 1} 个节点不是对象")
        for key in ["node_id", "title", "content"]:
            _ensure(key in node_obj, f"Skill 4 失败: 节点缺少字段 {key}")
        _ensure(isinstance(node_obj["node_id"], str) and node_obj["node_id"], f"Skill 4 失败: 第 {index + 1} 个节点 node_id 非法")
        _ensure(isinstance(node_obj["title"], str) and node_obj["title"].strip(), f"Skill 4 失败: 第 {index + 1} 个节点 title 非法")
        _ensure(isinstance(node_obj["content"], str), f"Skill 4 失败: 第 {index + 1} 个节点 content 非法")
        if "node_type" in node_obj:
            _ensure(isinstance(node_obj["node_type"], str), f"Skill 4 失败: 第 {index + 1} 个节点 node_type 非法")
    print(f"✅ 课件生成成功! 节点数: {len(nodes)}")
    for index, node in enumerate(nodes, start=1):
        print(f"  └─ Node {index}: {node.get('title')} | {node.get('node_type')} | {_short_text(node.get('content'), 80)}")

    preview_data = _post_json(
        f"{ROOT_URL}/gen/preview",
        {
            "nodes": nodes,
            "course_name": str(intent_summary.get("topic") or "课件"),
        },
    )
    assert preview_data.get("html"), "Skill 4 失败: 预览 HTML 为空"

    modify_payload = {
        "nodes": nodes,
        "commands": [
            {
                "type": "swap_nodes",
                "params": {
                    "node_ids": [nodes[0]["node_id"], nodes[1]["node_id"]] if len(nodes) >= 2 else [nodes[0]["node_id"]],
                },
            },
        ],
        "regenerate": False,
        "course_name": str(intent_summary.get("topic") or "课件"),
    }
    modify_data = _post_json(f"{ROOT_URL}/gen/modify", modify_payload)
    assert modify_data.get("status") in {"ok", "partial_error"}, f"Skill 4 失败: {modify_data}"
    modified_nodes = modify_data.get("nodes", [])
    assert modified_nodes, "Skill 4 失败: 修改后未返回 nodes"
    print(f"✅ Skill 4 成功! 修改后节点数: {len(modified_nodes)}")

    print("\n🎉🎉🎉 恭喜！4 个 Skill 全链路联调测试完全通过！")


if __name__ == "__main__":
    run_e2e_test()