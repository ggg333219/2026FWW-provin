"""把本地目录批量灌入知识库（方案 A：内存向量库）。

针对「考前复习资料」这类混合格式目录设计：
  - 只上传上传端点真正支持的格式，跳过 .ppt/.doc/.xls(x)/.bmp/.rar 等
    （否则会被当成纯文本读，把二进制乱码灌进库）
  - 跳过 ~$ 开头的 Office 锁定临时文件
  - 逐文件上传并记录 chunk_count，把「0 chunk」的文件单独列出来
    （扫描版 PDF 提不到文字层，会静默产出 0 chunk，必须暴露出来）
  - 最后做两项验收：① 抽查检索质量；② 用一个语料里绝对不存在的词查询，
    区分「向量通道正常 / 存的是零向量 / 嵌入完全没工作」三态。

    ⚠️ 不能看分数高低：ai_engine/rag/retrieve.py:400-408 按通道最大值归一化，
    每个通道第一名恒为 1.0；且向量不可用时会走 _bm25_only_search，
    那条路径的第一名同样是 1.0。所以「最高分 1.0」证明不了任何事。

用法：
    # 1) 先看会传哪些文件，不实际上传
    /d/anaconda/python scripts/ingest_knowledge_dir.py --root "E:/资料目录" --dry-run

    # 2) 试点：只传前 5 个可上传文件，验证链路
    /d/anaconda/python scripts/ingest_knowledge_dir.py --root "E:/资料目录" --limit 5

    # 3) 全量
    /d/anaconda/python scripts/ingest_knowledge_dir.py --root "E:/资料目录" --kb-id kb_review_2024
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# 中文输出防乱码（Windows 控制台默认 GBK）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# ---- 上传端点真正支持的扩展名（见 ai_engine/rag/router.py:463-529）----
SUPPORTED = {
    ".pdf", ".docx", ".pptx",
    ".md", ".txt", ".csv", ".json",
    ".html", ".htm", ".xml",
    ".py", ".log", ".yaml", ".yml", ".ts", ".js",
}

# ---- 明确不支持、且会被误当纯文本读的扩展名：必须排除 ----
BINARY_TRAPS = {
    ".ppt", ".doc", ".xls", ".xlsx",
    ".bmp", ".jpg", ".jpeg", ".png", ".gif", ".tiff", ".webp",
    ".rar", ".zip", ".7z", ".gz",
    ".mp3", ".wav", ".m4a", ".mp4", ".avi", ".mov", ".mkv",
}

# 向量权重 0.7 / BM25 权重 0.3（ai_engine/rag/retrieve.py:31-32）。
# 三态探针中「两侧都活」时，向量第一名（BM25 命中为 0）得分 = 0.7×1.0 + 0.3×0 = 0.7
VECTOR_ALIVE_SCORE = 0.6

# 探针查询：这三个英文词元在中文信息技术语料里不可能出现，
# 因此 BM25 侧必然全 0 —— 命中与否只由向量通道决定。
PROBE_QUERY = "quantum entanglement chlorophyll"


def post_json(base_url: str, path: str, payload: dict, timeout: int = 300) -> dict:
    request = Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body.get("data", body)


def collect(root: Path) -> tuple[list[Path], list[Path]]:
    """返回 (可上传文件, 被排除文件)。"""
    uploadable: list[Path] = []
    skipped: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("~$"):
            skipped.append(path)
            continue
        suffix = path.suffix.lower()
        if suffix in SUPPORTED:
            uploadable.append(path)
        else:
            skipped.append(path)
    return uploadable, skipped


def upload_one(base_url: str, kb_id: str, path: Path) -> tuple[int, str]:
    """上传单个文件，返回 (chunk_count, 错误信息)。"""
    try:
        result = post_json(base_url, "/api/v1/knowledge/upload", {
            "knowledge_base_id": kb_id,
            "files": [str(path)],
        })
        return int(result.get("chunk_count", 0) or 0), ""
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:160]
        return 0, f"HTTP {exc.code}: {detail}"
    except (URLError, TimeoutError) as exc:
        return 0, f"连接失败: {exc}"
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True, help="要灌入的目录")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="AI 引擎地址")
    parser.add_argument("--kb-id", default="kb_review_2024", help="知识库 ID（检索隔离用）")
    parser.add_argument("--limit", type=int, default=0, help="只传前 N 个文件（试点用）")
    parser.add_argument("--dry-run", action="store_true", help="只列出会传的文件，不上传")
    parser.add_argument("--query", default="", help="检索验收用的查询词")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"[FAIL] 目录不存在: {root}")
        return 1

    uploadable, skipped = collect(root)
    if args.limit > 0:
        uploadable = uploadable[: args.limit]

    print(f"目录: {root}")
    print(f"可上传: {len(uploadable)} 个   被排除: {len(skipped)} 个")
    if skipped:
        from collections import Counter
        counter = Counter(p.suffix.lower() or "(无扩展名)" for p in skipped)
        print("  排除原因分布: " + ", ".join(f"{ext}×{n}" for ext, n in counter.most_common()))
        traps = [p for p in skipped if p.suffix.lower() in BINARY_TRAPS]
        if traps:
            print(f"  其中 {len(traps)} 个是二进制格式 —— 已主动排除，")
            print("  否则会被当纯文本读成乱码灌进库（rag/router.py:373 的 TEXT 兜底）")

    if args.dry_run:
        print("\n--dry-run，以下文件将会被上传：")
        for path in uploadable:
            print(f"  {path.relative_to(root)}")
        return 0

    if not uploadable:
        print("[FAIL] 没有可上传的文件")
        return 1

    # ---- 逐文件上传 ----
    print(f"\n开始上传（{len(uploadable)} 个文件）...")
    total_chunks = 0
    empty_files: list[Path] = []
    failed: list[tuple[Path, str]] = []

    for index, path in enumerate(uploadable, start=1):
        count, error = upload_one(args.base_url, args.kb_id, path)
        total_chunks += count
        rel = path.relative_to(root)
        if error:
            failed.append((path, error))
            print(f"  [{index}/{len(uploadable)}] FAIL {rel} — {error}")
        elif count == 0:
            empty_files.append(path)
            print(f"  [{index}/{len(uploadable)}]   0 chunk  {rel}")
        else:
            print(f"  [{index}/{len(uploadable)}] {count:>4} chunk  {rel}")

    # ---- 结果汇总 ----
    print("\n" + "=" * 60)
    print(f"总计 {total_chunks} 个 chunk，来自 {len(uploadable) - len(empty_files) - len(failed)} 个文件")

    if empty_files:
        print(f"\n产出 0 chunk 的文件 {len(empty_files)} 个"
              "（扫描版 PDF 提不到文字层，属正常现象，需 OCR 才能入库）：")
        for path in empty_files[:20]:
            print(f"  - {path.relative_to(root)}")
        if len(empty_files) > 20:
            print(f"  ... 另有 {len(empty_files) - 20} 个")

    if failed:
        print(f"\n上传失败 {len(failed)} 个：")
        for path, error in failed[:10]:
            print(f"  - {path.relative_to(root)} — {error}")

    if total_chunks == 0:
        print("\n[FAIL] 一个 chunk 都没灌进去，中止验收。")
        return 1

    # ---- 验收 1：抽查检索质量（只看内容是否相关，不用分数判好坏）----
    query = args.query or "排序算法"
    print("\n" + "=" * 60)
    print(f"检索抽查: query={query!r}  kb={args.kb_id}")
    try:
        searched = post_json(args.base_url, "/api/v1/rag/search", {
            "query": query,
            "knowledge_base_ids": [args.kb_id],
            "top_k": 5,
            "min_score": 0.2,
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 检索请求失败: {exc}")
        return 1

    results = searched.get("results", []) or []
    if not results:
        print("[FAIL] 检索无任何命中")
        return 1

    print(f"命中 {len(results)} 条（score 仅供排序参考，不是相似度）：")
    for item in results:
        score = float(item.get("score", 0) or 0)
        head = (item.get("content", "") or "").replace("\n", " ")[:60]
        print(f"  score={score:.4f}  {head}")
    print("  ↑ 请人工确认这些内容与查询词是否语义相关 —— 这才是质量判据。")

    # ---- 验收 2：向量通道三态探针 ----
    # min_score 必须传负数：router 里是 `req.min_score or 0.2`，
    # 传 0.0 会被 falsy 判成 0.2，把零分结果滤光，前两态就分不出来了。
    print("\n" + "=" * 60)
    print(f"向量通道探针: query={PROBE_QUERY!r}（词元在中文语料中必然不存在）")
    try:
        probed = post_json(args.base_url, "/api/v1/rag/search", {
            "query": PROBE_QUERY,
            "knowledge_base_ids": [args.kb_id],
            "top_k": 5,
            "min_score": -1,
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 探针请求失败: {exc}")
        return 1

    probe_hits = probed.get("results", []) or []
    probe_best = max(
        (float(item.get("score", 0) or 0) for item in probe_hits), default=0.0
    )

    print()
    if probe_hits and probe_best >= VECTOR_ALIVE_SCORE:
        print(f"[PASS] 探针命中 {len(probe_hits)} 条，最高分 {probe_best:.4f} ≈ 0.7"
              "（0.7×向量第一名 + 0.3×BM25 零命中）")
        print("       —— 向量通道正常工作，语义检索可用。")
        return 0

    if probe_hits:
        print(f"[FAIL] 探针命中 {len(probe_hits)} 条，但最高分只有 {probe_best:.4f}。")
        print("       BM25 侧必然为 0，所以分数只可能来自向量侧 —— 接近 0 说明")
        print("       查询能嵌入、但**库里存的是零向量**（灌库时嵌入是坏的）。")
        print("       修好嵌入后重跑本脚本即可覆盖重算（chunk_id 是确定性的）。")
        return 1

    print("[FAIL] 探针一条都没命中 —— 查询向量为零，嵌入接口完全没工作，")
    print("       检索退化成了纯 BM25。请先跑：")
    print("         /d/anaconda/python scripts/verify_embedding.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
