"""本地资料目录 → 知识库 的一站式灌入能力。

统一入口，避免"脚本一套、服务一套"的二次分裂。三种触发方式共用同一实现：

  1. HTTP  ：POST /api/v1/knowledge/ingest-dir（dry_run 可先输出计划）
  2. 启动  ：环境变量 KB_AUTO_INGEST_DIR（多个用 os.pathsep 分隔）
             或 KB_AUTO_BOOTSTRAP=1（默认灌 docs/knowledge）
  3. CLI   ：scripts/ingest_knowledge_dir.py（走 HTTP，面向正在运行的服务）

设计要点（踩过的坑，别改回去）：
  - 只认能真正提取出文本的扩展名。把 .ppt/.doc/.xls(x)/图片/压缩包也丢进来的话，
    解析器会把二进制当纯文本读，乱码会被灌进知识库且极难清理。
  - 跳过 Office 临时文件（~$ 开头）与隐藏文件，避免读到打开中的半成品。
  - 逐文件统计 chunk_count，并把「0 块」的文件单独列进 zero_chunk：
    扫描版 PDF 提不出文字层会静默产出 0 块，必须暴露出来而不是假装成功。
  - 结果不可验证时不算完成：报告里带 count 与 retrieval_probe，
    区分「向量通道正常 / 零向量 / 嵌入完全没工作」三态。

用法：
    from ai_engine.rag.ingest import ingest_directory
    report = ingest_directory("docs/knowledge", knowledge_base_id="kb_tcp_teaching_v1")
    report = ingest_directory("E:/复习资料", dry_run=True)   # 只看计划，不写库
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

# 允许入库的扩展名（即解析器真正能从里面读到文本的类型）
SUPPORTED_EXTS = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm",
    ".pdf", ".pptx", ".docx",
}

# 明确跳过的扩展名：二进制/老旧格式，会被当纯文本读成乱码
UNSUPPORTED_EXTS = {
    ".ppt", ".doc", ".xls", ".xlsx", ".bmp", ".png", ".jpg", ".jpeg", ".gif",
    ".zip", ".rar", ".7z", ".mp3", ".mp4", ".avi", ".mov", ".exe", ".dll",
}

DEFAULT_MAX_FILE_BYTES = 80 * 1024 * 1024  # 80MB，超过基本不是教学资料正文

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def allowed_roots() -> list[Path]:
    """允许被灌入的根目录。

    默认只允许项目目录；需要导入项目外的资料时，用
    KB_INGEST_ALLOWED_ROOTS（多个用 os.pathsep 分隔）显式放行，
    避免 HTTP 接口被当成任意目录遍历的读文件口子。
    """
    roots = [PROJECT_ROOT]
    for raw in (os.getenv("KB_INGEST_ALLOWED_ROOTS") or "").split(os.pathsep):
        raw = raw.strip()
        if raw:
            roots.append(Path(raw).expanduser().resolve())
    return roots


def resolve_directory(directory: str) -> tuple[Optional[Path], Optional[str]]:
    """解析目录路径：相对路径按项目根解析，绝对路径必须落在允许的根下。"""
    raw = directory.strip()
    if not raw:
        return None, "directory 不能为空"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    if not path.exists():
        return None, f"目录不存在: {path}"
    if not path.is_dir():
        return None, f"不是目录: {path}"
    for root in allowed_roots():
        try:
            path.relative_to(root)
            return path, None
        except ValueError:
            continue
    hint = "、".join(str(r) for r in allowed_roots())
    return None, f"目录不在允许范围内（需位于 {hint} 之内，或用 KB_INGEST_ALLOWED_ROOTS 放行）: {path}"


def _iter_files(root: Path, recursive: bool = True):
    """产出目录下所有文件；是否可入库由 scan_plan 判定并给出跳过原因。"""
    walker = root.rglob("*") if recursive else root.glob("*")
    for path in sorted(walker):
        if path.is_file():
            yield path


def _rag_router():
    """取 rag 路由模块。

    注意不能写 `from ai_engine.rag import router`：包 __init__ 导出的
    `router` 是 APIRouter 实例，会遮蔽同名子模块，拿到对象再取函数会报
    "'APIRouter' object has no attribute '_process_file'"。
    """
    import importlib

    return importlib.import_module("ai_engine.rag.router")


def scan_plan(
    directory: str,
    recursive: bool = True,
    limit: int = 0,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    """生成灌入计划（不写库）。用于 dry_run 与实际灌入前的同一份判定。"""
    path, err = resolve_directory(directory)
    if err:
        return {"ok": False, "error": err}

    limit = max(0, int(limit or 0))
    max_file_bytes = max(0, int(max_file_bytes or DEFAULT_MAX_FILE_BYTES))

    planned: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for file_path in _iter_files(path, recursive=recursive):
        name = file_path.name
        suffix = file_path.suffix.lower()
        if name.startswith("~$"):
            skipped.append({"file": str(file_path), "name": name, "reason": "Office 临时文件（~$ 开头）"})
            continue
        if name.startswith("."):
            skipped.append({"file": str(file_path), "name": name, "reason": "隐藏文件"})
            continue
        try:
            size = file_path.stat().st_size
        except OSError as exc:
            skipped.append({"file": str(file_path), "name": name, "reason": f"无法读取: {exc}"})
            continue
        if suffix not in SUPPORTED_EXTS:
            skipped.append({"file": str(file_path), "name": name, "reason": f"不支持的格式: {suffix or '(无扩展名)'}"})
            continue
        if max_file_bytes and size > max_file_bytes:
            skipped.append({"file": str(file_path), "name": name, "reason": f"文件过大: {size} 字节"})
            continue
        planned.append({"file": str(file_path), "name": file_path.name, "size": size, "ext": suffix})

    truncated = False
    if limit and len(planned) > limit:
        planned = planned[:limit]
        truncated = True
    return {"ok": True, "root": str(path), "planned": planned, "skipped": skipped, "truncated": truncated}


def _embed_and_store(chunks: list[Any], knowledge_base_id: str) -> tuple[int, str]:
    """把一个文件的 chunks 写库，返回 (实际入库块数, doc_id)。"""
    rag_router = _rag_router()

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    if knowledge_base_id:
        for chunk in chunks:
            chunk.metadata = {**(chunk.metadata or {}), "knowledge_base_id": knowledge_base_id}
    embedded = rag_router._embed_service.embed_chunks(chunks)
    rag_router._store.insert_batch(embedded, doc_id=doc_id)
    return len(embedded), doc_id


def ingest_directory(
    directory: str,
    knowledge_base_id: str = "",
    recursive: bool = True,
    limit: int = 0,
    dry_run: bool = False,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    """扫描目录并灌入知识库。

    dry_run=True 时只返回计划，不写库。返回报告包含每个文件的 chunk 数、
    0 块文件清单、跳过清单，以及一次检索自检（retrieval_probe）。
    """
    started = time.monotonic()
    plan = scan_plan(directory, recursive=recursive, limit=limit, max_file_bytes=max_file_bytes)
    if not plan.get("ok"):
        return {"ok": False, "error": plan.get("error"), "dry_run": dry_run,
                "duration_ms": int((time.monotonic() - started) * 1000)}

    report: dict[str, Any] = {
        "ok": True,
        "directory": plan["root"],
        "knowledge_base_id": knowledge_base_id,
        "dry_run": bool(dry_run),
        "scanned": len(plan["planned"]) + len(plan["skipped"]),
        "planned_count": len(plan["planned"]),
        "truncated": plan["truncated"],
        "planned": plan["planned"],
        "skipped": plan["skipped"],
        "ingested": [],
        "zero_chunk": [],
        "failed": [],
        "total_chunks": 0,
    }
    if dry_run:
        report["duration_ms"] = int((time.monotonic() - started) * 1000)
        return report

    rag_router = _rag_router()
    first_snippet = ""

    for item in plan["planned"]:
        file_path = item["file"]
        try:
            chunks = rag_router._process_file(file_path)
        except Exception as exc:
            report["failed"].append({"file": file_path, "name": item["name"], "reason": str(exc)})
            print(f"[kb-ingest] 解析失败 {file_path} — {exc}", flush=True)
            continue
        if not chunks:
            # 没有切出任何块：扫描版 PDF / 空白文档。暴露而不是静默跳过。
            report["zero_chunk"].append({"file": file_path, "name": item["name"], "reason": "未提取到有效文本（扫描件/空文件？）"})
            print(f"[kb-ingest] 0 块，跳过入库 {file_path}", flush=True)
            continue
        try:
            count, doc_id = _embed_and_store(chunks, knowledge_base_id)
        except Exception as exc:
            report["failed"].append({"file": file_path, "name": item["name"], "reason": str(exc)})
            print(f"[kb-ingest] 入库失败 {file_path} — {exc}", flush=True)
            continue
        report["ingested"].append({"file": file_path, "name": item["name"], "chunks": count, "doc_id": doc_id})
        report["total_chunks"] += count
        # 取真实内容片段做后续检索自检：用通用词探测会受阈值影响误判为失效
        if not first_snippet and chunks:
            first_snippet = str(getattr(chunks[0], "content", "") or "").strip()[:40]
        # 取真实内容片段做后续检索自检：用通用词探测会受阈值影响误判为失效
        if not first_snippet and chunks:
            first_snippet = str(getattr(chunks[0], "content", "") or "").strip()[:40]
        print(f"[kb-ingest] {item['name']} — 入库 {count} 块", flush=True)

    if report["total_chunks"]:
        try:
            rag_router._retriever.rebuild_bm25()
        except Exception as exc:
            report["bm25_rebuild_error"] = str(exc)
            print(f"[kb-ingest] BM25 重建失败: {exc}", flush=True)
        report["retrieval_probe"] = _retrieval_probe(knowledge_base_id, query=first_snippet or "核心概念")

    report["duration_ms"] = int((time.monotonic() - started) * 1000)
    print(f"[kb-ingest] 完成 {plan['root']}: {len(report['ingested'])} 文件 / "
          f"{report['total_chunks']} 块 / {report['duration_ms']}ms", flush=True)
    return report


def _retrieval_probe(knowledge_base_id: str, query: str = "核心概念") -> dict[str, Any]:
    """灌完做一次真实检索，确认不是零向量/嵌入失效。"""
    rag_router = _rag_router()

    query = (query or "核心概念").strip() or "核心概念"
    try:
        results = rag_router._retriever.search(
            query=query,
            top_k=3,
            min_score=0.0,
            knowledge_base_ids=[knowledge_base_id] if knowledge_base_id else None,
        )
    except Exception as exc:
        return {"query": query, "status": "error", "detail": str(exc)}
    if not results:
        return {"query": query, "status": "empty", "hits": 0}
    top = results[0]
    return {
        "query": query,
        "status": "ok",
        "hits": len(results),
        "top_score": round(float(getattr(top, "score", 0.0) or 0.0), 6),
        "top_source": getattr(top, "source_ref", "") or "",
    }


def bootstrap_from_env() -> list[dict[str, Any]]:
    """启动时按环境变量自动灌入；返回每个目录的报告（无配置则返回空列表）。"""
    raw_dirs = [d for d in (os.getenv("KB_AUTO_INGEST_DIR") or "").split(os.pathsep) if d.strip()]
    if not raw_dirs and os.getenv("KB_AUTO_BOOTSTRAP") == "1":
        raw_dirs = ["docs/knowledge"]
    kb_id = os.getenv("KB_DEFAULT_KNOWLEDGE_BASE_ID", "kb_auto")
    reports: list[dict[str, Any]] = []
    for directory in raw_dirs:
        try:
            reports.append(ingest_directory(directory, knowledge_base_id=kb_id))
        except Exception as exc:  # 启动阶段的灌入失败不能拖垮引擎
            print(f"[kb-bootstrap] 失败 {directory} — {exc}", flush=True)
            reports.append({"ok": False, "directory": directory, "error": str(exc)})
    return reports
