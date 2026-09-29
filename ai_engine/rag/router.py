"""
KB 知识库 RAG FastAPI Router (router.py)

暴露 3 个 HTTP 端点供 Go 后端调用。

对应 Go 端已注册的路由：
  POST /api/v1/rag/search       → KnowledgeHandler.Search     → RAGSearch
  POST /api/v1/rag/evidence     → KnowledgeHandler.Evidence   → RAGEvidence
  POST /api/v1/knowledge/upload → KnowledgeHandler.Upload     → KnowledgeUpload

遵循开发规范（开发skill注意事项.md §3）：
  - 自包含 FastAPI router
  - 数据模型引用 ai_engine.core.schema
  - LLM 调用使用 ai_engine.core.LLMClient
  - 配置使用 ai_engine.core.settings
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from ai_engine.core import LLMClient
from ai_engine.core.schema import (
    Chunk,
    EvidenceRequest,
    EvidenceResponse,
    SearchRequest,
    SearchResponse,
    SourceType,
)

from .chunker import DocumentChunker
from .noise_filter import drop_noise_chunks, strip_noise_lines
from .embed import EmbeddingService
from .store import InMemoryVectorStore
from .store_pgvector import PGVectorStore
from .retrieve import HybridRetriever
from .rerank import ReRanker
from .evidence import EvidenceSynthesizer

# ---- Router 定义 ----
# 使用 /api/v1 前缀，与 Go 端 AIEngineClient.baseURL + path 拼接一致

router = APIRouter(prefix="/api/v1", tags=["KB-RAG"])

# ---- 模块级单例（进程内共享，避免重复初始化） ----

_chunker = DocumentChunker()
_embed_service = EmbeddingService()
def _build_store():
    """生产环境显式启用 pgvector；测试和无数据库场景保持零依赖内存实现。"""
    backend = (os.getenv("RAG_STORE_BACKEND") or "memory").strip().lower()
    if backend in {"pg", "pgvector", "postgres", "postgresql"}:
        return PGVectorStore()
    return InMemoryVectorStore()


_store = _build_store()
_retriever = HybridRetriever(store=_store, embed_service=_embed_service)
_reranker = ReRanker()
_synthesizer = EvidenceSynthesizer(llm_client=LLMClient(temperature=0.1))


# ---- 辅助函数 ----

def _get_store():
    """获取全局 store 实例。"""
    return _store


def _get_retriever() -> HybridRetriever:
    """获取全局 retriever 实例（每次搜索前重建 BM25 索引）。"""
    _retriever.rebuild_bm25()
    return _retriever


def _parse_source_type(raw: Any) -> Optional[SourceType]:
    """解析来源类型字符串。"""
    if not raw:
        return None
    try:
        return SourceType(str(raw).lower())
    except ValueError:
        return None


# =============================================================================
# 端点 1: 搜索
# =============================================================================

@router.post("/rag/search", response_model=SearchResponse)
async def rag_search(req: SearchRequest):
    """
    混合检索接口。

    接收查询文本，执行向量 + BM25 混合检索，返回 top-K 结果。

    Go 端调用: POST /api/v1/rag/search
    对应: KnowledgeHandler.Search → AIEngine.RAGSearch
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    scope = (req.scope or "course").strip().lower()
    if scope not in {"node", "page", "course"}:
        raise HTTPException(status_code=400, detail="scope 必须是 node、page 或 course")
    if scope == "node" and not (req.node_id or "").strip():
        raise HTTPException(status_code=400, detail="scope=node 时 node_id 不能为空")
    if scope == "page" and not (req.page_id or "").strip():
        raise HTTPException(status_code=400, detail="scope=page 时 page_id 不能为空")

    try:
        retriever = _get_retriever()
        results = retriever.search(
            query=req.query.strip(),
            top_k=req.top_k or 5,
            min_score=req.min_score or 0.2,
            knowledge_base_ids=req.knowledge_base_ids or None,
            scope=scope,
            node_id=req.node_id,
            page_id=req.page_id,
        )
        return SearchResponse(
            results=results,
            total_chunks=_store.count(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"检索失败: {str(e)}",
        )


# =============================================================================
# 端点 2: 证据融合
# =============================================================================

@router.post("/rag/evidence", response_model=EvidenceResponse)
async def rag_evidence(req: EvidenceRequest):
    """
    证据融合接口。

    执行 检索 → 重排序 → LLM合成 → EvidencePacket 全流程。

    兼容性说明：
      EvidencePacket 使用 relevant_chunks/synthesized_context/citations，
      S3 OutlineBuilder 已兼容此格式（同时支持 chunks 字段）。
    """
    query = (req.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")

    try:
        # 1. 混合检索（k=20 作为候选池）
        retriever = _get_retriever()
        candidates = retriever.search(
            query=query,
            top_k=20,
            min_score=0.3,  # 此阶段放宽阈值
            knowledge_base_ids=req.knowledge_base_ids or None,
        )

        # 2. 重排序（top-20 → top-5）
        reranked = _reranker.rerank(
            query=query,
            candidates=candidates,
            top_k=5,
        )

        # 3. LLM 合成 EvidencePacket
        context = dict(req.context) if req.context else {}
        response = _synthesizer.synthesize_to_response(
            search_results=reranked,
            query=query,
            context=context,
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"证据融合失败: {str(e)}",
        )


# =============================================================================
# 端点 3: 知识库上传 / 索引
# =============================================================================

# 扩展请求体以支持 Go 端 KnowledgeUploadRequest + 设计文档的 files 字段
from pydantic import BaseModel, Field


class KnowledgeUploadRequest(BaseModel):
    """知识库上传请求。

    兼容 Go 端 KnowledgeUploadRequest (session_id) +
    设计文档 KB-knowledge-base.md §3 (files + knowledge_base_id)。
    """
    session_id: str = ""
    knowledge_base_id: str = ""
    files: list[str] = Field(default_factory=list)
    """文件 URL 列表（minio:// 或本地路径），为空则从 session 查找已解析文件"""
    texts: list[str] = Field(default_factory=list)
    """直接上传的文本片段（用于测试/手动添加）"""


class KnowledgeUploadResponse(BaseModel):
    task_id: str = ""
    status: str = "pending"
    chunk_count: int = 0
    document_id: str = ""


@router.post("/knowledge/upload", response_model=KnowledgeUploadResponse)
async def knowledge_upload(req: KnowledgeUploadRequest):
    """
    知识库上传/索引接口。

    接收 session_id + 文件引用，执行：
      分块 → 嵌入向量化 → 写入向量存储 → 重建 BM25 索引

    Go 端调用: POST /api/v1/knowledge/upload
    对应: KnowledgeHandler.Upload → AIEngine.KnowledgeUpload
    """
    task_id = f"kb_upload_{uuid.uuid4().hex[:12]}"

    try:
        all_chunks: list[Chunk] = []

        # ---- 处理直接文本 ----
        for i, text in enumerate(req.texts):
            if not text.strip():
                continue
            chunks = _chunker.chunk_text(
                text=text.strip(),
                source_ref=f"manual_{i}",
                source_type=SourceType.TEXT,
            )
            all_chunks.extend(chunks)

        # ---- 处理文件列表 ----
        for file_url in req.files:
            if not file_url.strip():
                continue
            try:
                file_chunks = _process_file(file_url)
                all_chunks.extend(file_chunks)
            except Exception as e:
                # 单文件失败不阻塞整体流程
                print(f"[KB-Upload] 文件处理失败: {file_url} — {e}")

        # ---- 从 session 查找已解析文件（S2 产出） ----
        if req.session_id and not req.files and not req.texts:
            session_chunks = _find_session_chunks(req.session_id)
            all_chunks.extend(session_chunks)

        # ---- 无内容 ----
        if not all_chunks:
            return KnowledgeUploadResponse(
                task_id=task_id,
                status="done",
                chunk_count=0,
                document_id="",
            )

        # ---- 嵌入 → 存储 ----
        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        # 将资料归属写入 chunk 元数据；检索端据此执行 knowledge_base_ids 隔离。
        if req.knowledge_base_id:
            for chunk in all_chunks:
                chunk.metadata = {
                    **(chunk.metadata or {}),
                    "knowledge_base_id": req.knowledge_base_id,
                }
        embedded = _embed_service.embed_chunks(all_chunks)
        _store.insert_batch(embedded, doc_id=doc_id)

        # ---- 重建 BM25 ----
        _retriever.rebuild_bm25()

        return KnowledgeUploadResponse(
            task_id=task_id,
            status="done",
            chunk_count=len(embedded),
            document_id=doc_id,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"知识库索引失败: {str(e)}",
        )


# ---- 内部辅助 ----

# 进程内共享的 session→chunks 映射（S2 产出可供 KB 直接消费）
# 实际生产环境应通过 Redis/DB 共享
# 格式: {session_id: {"chunks": [...], "intent_id": "..."}}
_session_parsed_chunks: dict[str, dict] = {}


def register_session_chunks(session_id: str, chunks: list[Chunk], intent_id: Optional[str] = None) -> None:
    """
    供 S2 parse router 调用：注册解析完成的 chunks。

    S2 解析完成后调用此函数，KB 上传时可直接消费。
    """
    entry = _session_parsed_chunks.get(session_id, {"chunks": [], "intent_id": None})
    entry["chunks"].extend(chunks)
    if intent_id:
        entry["intent_id"] = intent_id
    _session_parsed_chunks[session_id] = entry


def _find_session_chunks(session_id: str) -> list[Chunk]:
    """查找某 session 的已解析 chunks。"""
    return _session_parsed_chunks.get(session_id, {}).get("chunks", [])


def _process_file(file_url: str) -> list[Chunk]:
    """
    处理单个文件 → Chunk 列表。

    支持：
      - 本地路径（.txt / .md / .pdf / .pptx / .docx）
      - minio:// 远程路径（通过 MinioClient 下载后解析）
    """
    from pathlib import Path

    # ---- minio:// 远程文件 ----
    if file_url.startswith("minio://"):
        try:
            from ai_engine.parse.minio_client import MinioClient
            minio = MinioClient()
            local_path = minio.download_file(file_url)
            if not local_path or not Path(local_path).exists():
                print(f"[KB-Upload] MinIO 下载失败或文件不存在: {file_url}")
                return []
            file_url = local_path  # 后续走本地文件逻辑
        except Exception as e:
            print(f"[KB-Upload] MinIO 客户端错误: {file_url} — {e}")
            return []

    # ---- 本地文件 ----
    path = Path(file_url)
    if not path.exists():
        print(f"[KB-Upload] 文件不存在: {file_url}")
        return []

    suffix = path.suffix.lower()
    text = _read_file_content_compatible(path, suffix)
    if not text:
        return []

    # 噪声行剥离放在切分之前：试卷页眉（班级__ 姓名__ 学号__）、答题横线、
    # 独立页码这类内容若留到切分后处理，会既自成垃圾切片，又挂在正常切片开头
    # 污染嵌入向量。剥离后再切，噪声不再占用窗口预算，切片反而更少更干净。
    text, stats = strip_noise_lines(text)
    if not text.strip():
        print(f"[KB-Upload] {path.name} — 剥离 {stats.lines_removed}/{stats.lines_total} "
              "行后无有效内容，跳过")
        return []

    source_type_map = {
        ".pdf": SourceType.PDF,
        ".pptx": SourceType.PPTX,
        ".docx": SourceType.DOCX,
        ".md": SourceType.TEXT,
        ".txt": SourceType.TEXT,
        ".csv": SourceType.TEXT,
    }
    source_type = source_type_map.get(suffix, SourceType.TEXT)

    chunks = _chunker.chunk_text(
        text=text,
        source_ref=path.name,
        source_type=source_type,
    )
    chunks, stats.chunks_dropped = drop_noise_chunks(chunks)
    print(f"[KB-Upload] {path.name} — 入库 {len(chunks)} 块；{stats}")
    return chunks


def _read_file_content(path, suffix: str) -> str:
    """读取文件文本内容（按类型调度解析器）。"""
    from pathlib import Path as _Path

    # 纯文本文件直接读
    if suffix in {".txt", ".md", ".csv"}:
        return _Path(path).read_text(encoding="utf-8", errors="ignore")

    # PDF: 尝试用 PyMuPDF 提取文本
    if suffix == ".pdf":
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(path))
            pages = [page.get_text() for page in doc]
            doc.close()
            return "\n\n".join(pages)
        except ImportError:
            return _Path(path).read_text(encoding="utf-8", errors="ignore")

    # PPTX: 尝试用 python-pptx 提取文本
    if suffix == ".pptx":
        try:
            from pptx import Presentation
            prs = Presentation(str(path))
            slides: list[str] = []
            for slide in prs.slides:
                parts: list[str] = []
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for p in shape.text_frame.paragraphs:
                            if p.text.strip():
                                parts.append(p.text.strip())
                slides.append("\n".join(parts))
            return "\n\n---\n\n".join(slides)
        except ImportError:
            return _Path(path).read_text(encoding="utf-8", errors="ignore")

    # DOCX: 尝试用 python-docx (如果装了的话) 否则纯文本
    if suffix == ".docx":
        try:
            from docx import Document
            doc = Document(str(path))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            return _Path(path).read_text(encoding="utf-8", errors="ignore")

    # 未知类型：尝试纯文本
    return _Path(path).read_text(encoding="utf-8", errors="ignore")
def _read_file_content_compatible(path, suffix: str) -> str:
    """更稳妥的文件内容读取器，按格式输出适合分块的纯文本。"""
    from pathlib import Path as _Path

    def _normalize(text: str) -> str:
        return re.sub(r"\r\n?", "\n", text or "").strip()

    def _read_text_fallback() -> str:
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
            try:
                return _Path(path).read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
            except Exception:
                break
        return _Path(path).read_text(encoding="utf-8", errors="ignore")

    def _strip_html(text: str) -> str:
        from html.parser import HTMLParser

        class _Parser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.parts: list[str] = []

            def handle_data(self, data: str) -> None:  # type: ignore[override]
                if data:
                    self.parts.append(data)

        parser = _Parser()
        parser.feed(text)
        return "\n".join(part.strip() for part in parser.parts if part.strip())

    if suffix in {".txt", ".md", ".log", ".yaml", ".yml", ".js", ".ts", ".py"}:
        return _normalize(_read_text_fallback())

    if suffix == ".json":
        raw = _normalize(_read_text_fallback())
        try:
            return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
        except Exception:
            return raw

    if suffix == ".csv":
        raw = _normalize(_read_text_fallback())
        try:
            rows = list(csv.reader(io.StringIO(raw)))
            rows = [row for row in rows if any(cell.strip() for cell in row)]
            if not rows:
                return ""
            widths = [max(len(row[i]) if i < len(row) else 0 for row in rows[:20]) for i in range(max(len(r) for r in rows))]
            lines: list[str] = []
            for row in rows[:100]:
                padded = []
                for i, cell in enumerate(row):
                    padded.append(cell + (" " * max(widths[i] - len(cell), 0)))
                lines.append(" | ".join(padded))
            return "\n".join(lines)
        except Exception:
            return raw

    if suffix in {".html", ".htm", ".xml"}:
        return _strip_html(_read_text_fallback())

    if suffix == ".pdf":
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(path))
            pages = [page.get_text() for page in doc]
            doc.close()
            return _normalize("\n\n".join(pages))
        except Exception:
            return _normalize(_read_text_fallback())

    if suffix == ".pptx":
        try:
            from pptx import Presentation
            prs = Presentation(str(path))
            slides: list[str] = []
            for slide in prs.slides:
                parts: list[str] = []
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for p in shape.text_frame.paragraphs:
                            if p.text.strip():
                                parts.append(p.text.strip())
                slides.append("\n".join(parts))
            return _normalize("\n\n---\n\n".join(slides))
        except Exception:
            return _normalize(_read_text_fallback())

    if suffix == ".docx":
        try:
            from docx import Document
            doc = Document(str(path))
            return _normalize("\n\n".join(p.text for p in doc.paragraphs if p.text.strip()))
        except Exception:
            return _normalize(_read_text_fallback())

    return _normalize(_read_text_fallback())
