# -*- coding: utf-8 -*-
"""角色 A · P0 smoke test：生成 → 预览 → 修改 → 导出（真实 API 链路，mock 生成模式）

验证对象（与 docs/A0-schema统一-唯一真值-20260902.md 对应）：
  - 任务状态 status/stage/progress_pct 枚举一致
  - node 各 canonical 字段齐全、questions 严格 list[str]
  - version_number 递增（v1 初稿 → v2 编辑）
  - 导出 pptx/interactive/lesson_plan 三格式 job done + download 非空

用法：
  python scripts/smoke_p0_contract.py                      # 引擎直连（默认 mock）
  GO_GATEWAY=http://127.0.0.1:8082 python scripts/smoke_p0_contract.py   # 走教师 Go 网关
  AI_ENGINE_ROOT_URL=... python scripts/smoke_p0_contract.py             # 自定义引擎地址

前置：AI 引擎已在 8000 运行且 AI_GEN_MODE=mock（或可访问 LLM）。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GATEWAY = os.getenv("GO_GATEWAY", "").rstrip("/")
ENGINE_ROOT = os.getenv("AI_ENGINE_ROOT_URL", "http://127.0.0.1:8000").rstrip("/")
# 统一 API 前缀：直连=引擎 /api/v1；网关=Go 网关 /api/v1（网关仅透传，不改字段）
API_ROOT = (GATEWAY if GATEWAY else ENGINE_ROOT) + "/api/v1"

FAIL = []


def _req(method, url, payload=None, timeout=180, follow=True):
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        return e.code, {"_http_error": raw}


def _raw_get(url, timeout=180):
    """下载产物按原始字节读取（html/pptx/docx 均非 JSON）。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _unwrap(data):
    """引擎返回裸对象；Go 网关返回 {code,data}。此处只取 data。"""
    if isinstance(data, dict) and "code" in data and "data" in data:
        return data["data"]
    return data


def _ensure(cond, label, extra=""):
    if not cond:
        FAIL.append(label)
        print(f"  ❌ {label} {extra}")
    else:
        print(f"  ✅ {label}")


def _url(*parts):
    return "/".join(str(p).strip("/") for p in parts if str(p).strip("/"))


def _poll(url, want=("done", "failed"), key="status", timeout=180):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        code, data = _req("GET", url)
        data = _unwrap(data)
        st = str(data.get(key, "")).lower()
        last = data
        if st in want:
            return data
        time.sleep(1)
    raise TimeoutError(f"轮询超时 {url}: {last}")


def main():
    root = API_ROOT
    print(f"🚀 P0 smoke（生成→预览→修改→导出） target={root}  mode={'Go网关' if GATEWAY else '引擎直连'}")

    # ---------------------------------------------------------- 1. 生成
    intent = {
        "topic": "排序算法",
        "duration_minutes": 45,
        "style": "讲练结合",
        "target_student": "大一计算机专业",
        "knowledge_points": ["冒泡排序", "快速排序", "时间复杂度"],
        "output_format": ["ppt"],
        "with_interactive": True,
        "key_difficulties": ["递归理解"],
        "expected_outcomes": ["理解原理", "能分析复杂度"],
    }
    code, data = _req("POST", _url(root, "gen/create"),
                      {"session_id": "smoke_a_p0", "intent": intent, "template_id": "default"})
    data = _unwrap(data)
    _ensure(code == 200 and data.get("task_id") and data.get("generation_id"), "gen/create 返回 task_id+generation_id", str(data)[:200])
    task_id, gen_id = data.get("task_id"), data.get("generation_id")

    status = _poll(_url(root, "gen/status", task_id))
    st = str(status.get("status", ""))
    _ensure(st == "done", "gen 最终 status=done", f"actual={st} error={status.get('error')}")
    _ensure(isinstance(status.get("progress_pct", 0), (int, float)) and status.get("progress_pct", 0) == 100, "progress_pct=100")
    nodes = status.get("nodes") or []
    _ensure(isinstance(nodes, list) and len(nodes) >= 2, "生成节点数 ≥2", f"n={len(nodes)}")

    if str(status.get("status", "")).lower() != "done" or not nodes:
        print("\n❌ 生成未完成，停止后续预览/版本/导出断言，原始错误已在上方输出。")
        sys.exit(1)

    # ---------------------------------------------------------- 2. 节点 schema
    required = ["node_id", "title", "node_type", "content", "summary", "script",
                "core_points", "key_points", "questions", "interactive_questions",
                "segments", "estimated_duration_minutes"]
    bad = [k for k in required if k not in nodes[0]]
    _ensure(not bad, "节点 canonical 字段齐全", f"缺 {bad}")
    _ensure(nodes[0]["node_type"] in {"slide", "section", "quiz", "interactive", "cover", "divider"},
            "node_type ∈ 白名单", nodes[0].get("node_type"))
    qs_types = {type(q).__name__ for n in nodes for q in (n.get("questions") or [])}
    _ensure(qs_types <= {"str"}, "questions 严格 list[str]", f"含非str {qs_types}")
    n0, n1 = nodes[0]["node_id"], nodes[1]["node_id"]

    # ---------------------------------------------------------- 3. 预览
    code, data = _req("POST", _url(root, "gen/preview"),
                      {"gen_id": gen_id, "course_name": "排序算法"})
    pv = _unwrap(data)
    _ensure(code == 200 and pv.get("html") and len(pv.get("html", "")) > 500, "预览 HTML 渲染(版本快照恢复)", f"len={len(pv.get('html',''))}")

    # ---------------------------------------------------------- 4. 版本 v1
    # history 是轻量元数据列表，按 API 契约不携带 generation_id / nodes_snapshot；
    # 完整快照由 GET /version/{gen_id}?v=N 返回，不能在这里复用完整对象断言。
    code, data = _req("GET", _url(root, "version", gen_id, "history"))
    hist = _unwrap(data).get("versions") or []
    _ensure(code == 200 and len(hist) >= 1, "version/history 含初稿 v1", f"versions={[v.get('version_number') for v in hist]}")
    history_keys = ["id", "version_number", "summary", "locked", "created_at"]
    missing = [k for k in history_keys if k not in hist[0]]
    _ensure(not missing, "版本历史元数据字段齐全", f"缺 {missing}")

    code, data = _req("GET", _url(root, "version", gen_id) + "?v=1")
    snapshot = _unwrap(data)
    snapshot_keys = ["id", "version_number", "nodes_snapshot", "summary", "locked", "created_at"]
    missing = [k for k in snapshot_keys if k not in snapshot]
    _ensure(code == 200 and not missing, "版本 v1 完整快照字段齐全", f"缺 {missing}")
    _ensure(isinstance(snapshot.get("nodes_snapshot"), list) and snapshot.get("nodes_snapshot"),
            "版本 v1 nodes_snapshot 为非空列表",
            f"type={type(snapshot.get('nodes_snapshot')).__name__}")

    # ---------------------------------------------------------- 5. 修改 → v2
    code, data = _req("POST", _url(root, "gen/modify"),
                      {"generation_id": gen_id, "commands": [{"type": "swap_nodes", "target_node_ids": [n0, n1]}]})
    md = _unwrap(data)
    _ensure(code == 200 and str(md.get("status")) in {"ok", "partial_error"}, "gen/modify 执行", str(md)[:200])
    _ensure(md.get("version_number") == 2, "修改后 version_number=2", f"v={md.get('version_number')}")

    # ---------------------------------------------------------- 6. 版本 v2
    code, data = _req("GET", _url(root, "version", gen_id, "history"))
    hist2 = _unwrap(data).get("versions") or []
    _ensure(len(hist2) == 2, "history 递增为 2 个版本", f"versions={[v.get('version_number') for v in hist2]}")

    code, data = _req("GET", _url(root, "version", gen_id) + "?v=2")
    snapshot2 = _unwrap(data)
    _ensure(code == 200 and isinstance(snapshot2.get("nodes_snapshot"), list),
            "版本 v2 完整快照可加载", f"keys={list(snapshot2) if isinstance(snapshot2, dict) else type(snapshot2).__name__}")

    # ---------------------------------------------------------- 7. 导出三格式
    for fmt, ext in (("pptx", "pptx"), ("interactive", "html"), ("lesson_plan", "docx")):
        code, data = _req("POST", _url(root, "export", gen_id), {"format": fmt, "version": 2})
        job = _unwrap(data)
        job_id = job.get("job_id")
        _ensure(code == 200 and job_id, f"export {fmt} 创建 job", str(job)[:160])
        if not job_id:
            continue
        sts = _poll(_url(root, "export/status", job_id))
        _ensure(str(sts.get("status")) == "done", f"export {fmt} status=done", str(sts.get("error"))[:160])
        dl = sts.get("download_url") or ""
        _ensure(bool(dl), f"export {fmt} 返回 download_url", f"st={sts}")
        # 下载：引擎直连返回 /download/{job}.{ext}（拼 ENGINE_ROOT）；
        # 网关 Status 重写为 /api/v1/export/download/{job}/{ext》（拼 GATEWAY，网关 307 到引擎 /download，urllib 自动跟随）。
        dl_host = GATEWAY if GATEWAY else ENGINE_ROOT
        dl_url = (dl_host + dl) if dl.startswith("/") else dl
        dcode, dbytes = _raw_get(dl_url)
        _ensure(dcode == 200 and len(dbytes) > 0, f"export {fmt} 下载成功({len(dbytes)}B)", f"http={dcode}")

    # ---------------------------------------------------------- 8. 汇总
    print("\n" + ("🎉 P0 smoke 全通过" if not FAIL else f"❌ P0 smoke 失败 {len(FAIL)} 项：\n- " + "\n- ".join(FAIL)))
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    main()
