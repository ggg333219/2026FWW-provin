#!/usr/bin/env python3
"""
联调：讲授节点引用健康扫描 / 修复 + 学情进度校验（需本机已启动 Go 后端与 Postgres）。

用法（PowerShell）:
  cd 项目根目录
  pip install requests   # 若未安装
  python scripts/test_knowledge_graph_maintenance.py

可选环境变量:
  API_BASE=http://localhost:18080   # 默认
  COURSE_ID=<uuid>                # 指定课件；不填则取教师课件列表第一个
  RUN_REPAIR=1                    # 为 1 时在扫描有孤儿时执行修复（会改库，慎用）
"""

from __future__ import annotations

import json
import os
import sys
import uuid

try:
    import requests
except ImportError:
    print("请先安装: pip install requests", file=sys.stderr)
    sys.exit(1)

API_BASE = os.environ.get("API_BASE", "http://localhost:18080").rstrip("/")
V1 = f"{API_BASE}/api/v1"


def pretty(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def main() -> int:
    print(f"API_BASE = {API_BASE}\n")

    # 1) 健康检查
    r = requests.get(f"{API_BASE}/health", timeout=5)
    print(f"GET /health -> {r.status_code}")
    print(r.text[:500] or "(empty)")
    if r.status_code != 200:
        print("\n后端未就绪，请先: cd backend && go run ./api/main.go", file=sys.stderr)
        return 1

    # 2) 取课件 ID
    course_id = os.environ.get("COURSE_ID", "").strip()
    if not course_id:
        r = requests.get(f"{V1}/teacher/coursewares", timeout=60)
        print(f"\nGET /api/v1/teacher/coursewares -> {r.status_code}")
        if r.status_code != 200:
            print(r.text, file=sys.stderr)
            return 1
        body = r.json()
        rows = body.get("data") or []
        if not rows:
            print("数据库中暂无课件，无法测 reference-health。请先上传一个课件。")
            return 0
        course_id = rows[0].get("id") or rows[0].get("courseId")
        print(f"使用列表第一个课件 courseId = {course_id}")

    # 3) 引用健康扫描
    url_health = f"{V1}/teacher/coursewares/{course_id}/knowledge-graph/reference-health"
    r = requests.get(url_health, timeout=120)
    print(f"\nGET .../knowledge-graph/reference-health -> {r.status_code}")
    try:
        health_json = r.json()
        print(pretty(health_json))
    except Exception:
        print(r.text)
        return 1

    # 4) 修复：未 confirm 应 400
    url_repair = f"{V1}/teacher/coursewares/{course_id}/knowledge-graph/reference-health/repair"
    r = requests.post(url_repair, json={}, timeout=10)
    print(f"\nPOST .../reference-health/repair (无 confirm) -> {r.status_code} (期望 400)")
    print(pretty(r.json()) if r.headers.get("content-type", "").startswith("application/json") else r.text)

    # 5) 可选：真实修复
    if os.environ.get("RUN_REPAIR") == "1":
        data = health_json.get("data") or {}
        if not data.get("hasOrphans"):
            print("\nRUN_REPAIR=1 但当前无孤儿引用，跳过修复。")
        else:
            print("\nRUN_REPAIR=1：即将执行修复（5 秒后执行，Ctrl+C 取消）...")
            import time

            time.sleep(5)
            r = requests.post(url_repair, json={"confirm": True}, timeout=120)
            print(f"POST repair confirm=true -> {r.status_code}")
            print(pretty(r.json()) if r.headers.get("content-type", "").startswith("application/json") else r.text)
    else:
        print("\n（未设置 RUN_REPAIR=1，跳过破坏性修复。需要时: $env:RUN_REPAIR='1'）")

    # 6) 学情进度：合法 payload
    prog_url = f"{V1}/student/sessions/progress"
    ok_body = {
        "sessionId": str(uuid.uuid4()),
        "userId": "xuesheng",
        "courseId": course_id,
        "currentPage": 1,
        "currentNodeId": "p1_n1",
        "currentTimeSec": 0,
    }
    r = requests.post(prog_url, json=ok_body, timeout=10)
    print(f"\nPOST /api/v1/student/sessions/progress (合法) -> {r.status_code} (期望 200)")
    print(pretty(r.json()) if r.headers.get("content-type", "").startswith("application/json") else r.text)

    # 7) 非法 courseId（非 UUID）
    bad = dict(ok_body)
    bad["courseId"] = "not-a-uuid"
    r = requests.post(prog_url, json=bad, timeout=10)
    print(f"\nPOST .../sessions/progress (非法 courseId) -> {r.status_code} (期望 400)")
    print(pretty(r.json()) if r.headers.get("content-type", "").startswith("application/json") else r.text)

    print("\n完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
