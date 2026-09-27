"""灌入 TCP 教学资料并验证“TCP 三次握手”可被检索。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "docs" / "knowledge" / "TCP网络基础-知识库种子资料.md"


def post_json(base_url: str, path: str, payload: dict) -> dict:
    request = Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body.get("data", body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="AI Engine 地址；也可传 Go 后端地址")
    parser.add_argument("--knowledge-base-id", default="kb_tcp_teaching_v1")
    args = parser.parse_args()

    text = SEED.read_text(encoding="utf-8")
    uploaded = post_json(args.base_url, "/api/v1/knowledge/upload", {
        "knowledge_base_id": args.knowledge_base_id,
        "texts": [text],
    })
    if uploaded.get("chunk_count", 0) <= 0:
        raise SystemExit(f"灌入失败：{uploaded}")

    searched = post_json(args.base_url, "/api/v1/rag/search", {
        "query": "TCP 三次握手为什么需要三次",
        "knowledge_base_ids": [args.knowledge_base_id],
        "top_k": 5,
        "min_score": 0.0,
    })
    results = searched.get("results", [])
    matched = next((item for item in results if "三次握手" in item.get("content", "")), None)
    if not matched:
        raise SystemExit(f"检索验收失败：{searched}")
    print(json.dumps({
        "status": "passed",
        "knowledge_base_id": args.knowledge_base_id,
        "chunk_count": uploaded["chunk_count"],
        "matched_hit": matched.get("content", "")[:120],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
