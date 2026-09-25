from datetime import datetime
import sys
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import shutil
import os
import uuid
import json
import wave
from pathlib import Path
from typing import List, Optional, Any

CURRENT_DIR = Path(__file__).resolve().parent  # ai_engine/
PROJECT_ROOT = CURRENT_DIR.parent  # 项目根目录
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 导入 AI 核心逻辑（使用绝对导入，依赖 PROJECT_ROOT 已在 sys.path 中）
from ai_engine.parser import DocumentParser
from ai_engine.generator import LessonGenerator, GenerationConfig
from ai_engine.qa import QAResponder, QAConfig, resolve_llm_base_url
from ai_engine.core.llm import resolve_llm_timeout, _is_retryable_error
from ai_engine.reconstructor import LessonReconstructor, ReconstructionConfig
from ai_engine.recommendation.service import router as recommendation_router
from ai_engine.gen.outline import OutlineBuilder, OutlineConfig
from ai_engine.gen.modify_intent import ModifyIntentParser
from ai_engine.gen.evidence_binding import bind_evidence_to_draft_nodes
from ai_engine.gen.node import NodeGenerator, NodeGenConfig
from ai_engine.gen.export_ppt import PPTExporter, ExportPPTConfig
from ai_engine.gen.export_doc import DOCExporter, ExportDocConfig
from ai_engine.gen.preview import PreviewRenderer
from ai_engine.gen.validator import ContentValidator
from ai_engine.gen.commands import CommandParser, EditCommand, CommandType
from ai_engine.gen.patch import NodePatcher
from ai_engine.gen.interactive import InteractiveBuilder
from ai_engine.intent.router import router as intent_router
# RAG 内联调用支持（S2→KB 证据自动注入 S3 管线）
from ai_engine.rag.router import _get_retriever, _reranker, _synthesizer
from ai_engine.core.schema import (
    GenerationCreateRequest, GenerationCreateResponse,
    GenerationStatusResponse, GenerationStatus, GenerationStage,
    GenerationTask, TeachingNode, IntentSummary,
    ExportRequest, ExportFormat,
    ExportStatusResponse, ExportStatus, ExportJob,
    RollbackRequest,
    normalize_generation_nodes,
)

app = FastAPI(title="泛雅 AI 智课系统后端", description="为前端提供解析、生成、问答、重讲等核心 AI 接口")
app.include_router(recommendation_router)
# 保留旧的 /intent/* 供历史调试工具使用，同时提供 Go Backend 约定的 /api/v1/intent/*。
app.include_router(intent_router)
app.include_router(intent_router, prefix="/api/v1")

# ---- Phase 4: Skill 模块注册（新增，互不冲突） ----
from ai_engine.parse.router import router as parse_router
app.include_router(parse_router)

from ai_engine.rag.router import router as rag_router
app.include_router(rag_router)

# ---- Phase 4: S3 Skill 路由（新增）----
from ai_engine.gen.skill_router import router as skill_router
app.include_router(skill_router)

# 启用跨域支持，让前端 Vue/React 能访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 临时文件存放目录
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
AUDIO_DIR = UPLOAD_DIR / "generated_audio"
AUDIO_DIR.mkdir(exist_ok=True)
app.mount("/generated-audio", StaticFiles(directory=str(AUDIO_DIR)), name="generated-audio")

# deck-skill HTML 预览目录
PREVIEW_DIR = UPLOAD_DIR / "previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/previews", StaticFiles(directory=str(PREVIEW_DIR)), name="previews")

# 内存中的简单“状态机”：真实环境下这里会接数据库
# 存储 key: doc_id, value: { "parsed": ..., "generated": ... }
STORAGE = {}

# --- 数据模型定义 ---

class ChatRequest(BaseModel):
    doc_id: str
    question: str
    page: int
    mode: str = "llm"  # 默认改为 llm


class GenerateScriptRequest(BaseModel):
    page: int
    content: str
    course_name: Optional[str] = None
    mode: str = "llm"
    evidence: Optional[dict[str, Any]] = None


class AskWithContextRequest(BaseModel):
    question: str
    current_page: int
    context: str = ""
    mode: str = "llm"
    session_id: Optional[str] = None
    history_summary: str = ""
    recent_turns: List[dict[str, Any]] = Field(default_factory=list)


class ParseKnowledgeRequest(BaseModel):
    text: str
    mode: str = "llm"


class ReconstructDocumentRequest(BaseModel):
    parsed_document: dict[str, Any]
    mode: str = "hybrid"


class GenerateNodeScriptRequest(BaseModel):
    teaching_node: dict[str, Any]
    course_name: Optional[str] = None
    mode: str = "llm"
    evidence: Optional[dict[str, Any]] = None


class GenerateFromMarkdownRequest(BaseModel):
    markdown: str
    course_name: Optional[str] = None
    mode: str = "llm"


class GenerateAudioNode(BaseModel):
    node_id: str
    title: str = ""
    text: str = ""
    duration_sec: int = 0
    start_sec: int = 0
    end_sec: int = 0
    audio_url: str = ""


class GenerateAudioRequest(BaseModel):
    course_id: str
    page: int
    voice_type: str = ""
    format: str = "wav"
    provider: str = ""
    nodes: List[GenerateAudioNode] = Field(default_factory=list)
    playback_id: str = ""

def _llm_endpoint_error(e: Exception, fallback_prefix: str) -> HTTPException:
    """LLM 端点层统一异常兜底：把意外异常转成友好 HTTP 错误，不裸抛 500。

    - 超时类异常 → 504 "生成超时，请稍后重试"
    - 连接类异常 → 503 "AI 服务网络异常，请检查 API 配置"
    - 其余异常   → 500，保持原有 "{前缀}: {详情}" 格式

    说明：LLMClient._call 内部已有兜底回退（不外抛，返回 used_fallback 标记），
    本函数只处理端点层漏出的意外异常（如 OpenAI 客户端直连、TTS、JSON 解析等）。
    复用 ai_engine.core.llm._is_retryable_error 的超时/连接判定，保持判定口径一致。
    """
    if _is_retryable_error(e):
        name = type(e).__name__.lower()
        msg = str(e).lower()
        if "timeout" in name or "timed out" in msg or "timeout" in msg:
            return HTTPException(status_code=504, detail="生成超时，请稍后重试")
        return HTTPException(status_code=503, detail="AI 服务网络异常，请检查 API 配置")
    return HTTPException(status_code=500, detail=f"{fallback_prefix}: {str(e)}")


# =============================================================================
# 旧版 generator.py 路由（已废弃，仅保留供兼容）
# 前端已全部改用 /api/v1/gen/* 系列路由
# =============================================================================

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """[DEPRECATED] 旧版上传接口，请使用 /api/v1/teacher/coursewares/upload"""
    # 旧版实现：接收 PDF/PPTX，并自动触发解析
    file_id = f"doc_{uuid.uuid4().hex[:8]}"
    file_ext = Path(file.filename).suffix
    file_path = UPLOAD_DIR / f"{file_id}{file_ext}"

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # 实时解析文档
        parser = DocumentParser(str(file_path))
        parsed_data = parser.parse()
        
        # 记录到内存（实际开发中这里会存入数据库）
        STORAGE[file_id] = {
            "parsed": parsed_data,
            "reconstructed": LessonReconstructor().reconstruct(parsed_data),
            "file_path": str(file_path)
        }
        
        return {
            "doc_id": file_id,
            "doc_name": file.filename,
            "total_pages": parsed_data["total_pages"],
            "message": "文件解析成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@app.post("/parse-document")
async def parse_document(file: UploadFile = File(...)):
    """[DEPRECATED] 旧版解析接口，请使用 /api/v1/parse/process"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".pptx"}:
        raise HTTPException(status_code=400, detail="仅支持 PDF/PPTX 文件")

    file_id = f"parse_{uuid.uuid4().hex[:8]}"
    file_path = UPLOAD_DIR / f"{file_id}{suffix}"

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        parser = DocumentParser(str(file_path))
        return parser.parse()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@app.post("/reconstruct-document")
async def reconstruct_document(req: ReconstructDocumentRequest):
    """[DEPRECATED] 旧版重构接口，已由 S3 节点生成替代"""
    parsed_document = req.parsed_document or {}
    if not parsed_document.get("parsed_pages"):
        raise HTTPException(status_code=400, detail="parsed_document.parsed_pages 不能为空")
    try:
        reconstructor = LessonReconstructor(ReconstructionConfig(mode=req.mode))
        return reconstructor.reconstruct(parsed_document)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内容重构失败: {str(e)}")


@app.get("/lessons/{doc_id}")
async def get_lessons(doc_id: str, mode: str = "llm"):
    """[DEPRECATED] 旧版课程获取接口，由 S3 生成流程替代"""
    if doc_id not in STORAGE:
        raise HTTPException(status_code=404, detail="文档未找到")
    
    # 如果还没生成过，则现在生成
    if "generated" not in STORAGE[doc_id]:
        generator = LessonGenerator(GenerationConfig(mode=mode))
        generated_data = generator.generate(STORAGE[doc_id]["parsed"])
        STORAGE[doc_id]["generated"] = generated_data

    return STORAGE[doc_id]["generated"]


@app.post("/chat")
async def chat_with_ai(req: ChatRequest):
    """[DEPRECATED] 旧版问答接口，已由 S1 意图理解 + RAG 替代"""
    if req.doc_id not in STORAGE:
        # 如果 doc_id 不存在且 STORAGE 非空，尝试匹配最近的一个文档（方便调试）
        if STORAGE:
            last_id = list(STORAGE.keys())[-1]
            doc_data = STORAGE[last_id]
        else:
            raise HTTPException(status_code=404, detail="未找到任何已解析文档，请先上传。")
    else:
        doc_data = STORAGE[req.doc_id]
    
    parsed_doc = doc_data["parsed"]
    
    # 强制尝试获取环境变量中的模式，如果请求是 mock 也会被改为环境变量设定的模式
    # 这样用户在 Postman 里如果不改参数，也能生效
    env_mode = os.getenv("AI_GEN_MODE", "llm")
    final_mode = env_mode if env_mode == "llm" else req.mode

    # 调用你写的 QA 响应器
    responder = QAResponder(parsed_doc, config=QAConfig(mode=final_mode))
    try:
        result = await asyncio.to_thread(responder.answer, req.question, req.page)
    except Exception as e:
        raise _llm_endpoint_error(e, "问答失败")

    return result


@app.post("/generate-script")
async def generate_script(req: GenerateScriptRequest):
    """[DEPRECATED] 旧版讲稿生成，请使用 /api/v1/gen/create"""
    try:
        parsed_document = {
            "doc_id": f"inline_{uuid.uuid4().hex[:8]}",
            "doc_name": req.course_name or "inline_course",
            "parsed_pages": [
                {
                    "page": req.page,
                    "content": req.content.strip() or f"第{req.page}页内容",
                    "content_length": len(req.content.strip()),
                }
            ],
        }
        generator = LessonGenerator(GenerationConfig(mode=req.mode))
        result = generator.generate(parsed_document, evidence=req.evidence)
        lesson = (result.get("lessons") or [{}])[0]
        return {
            "page": req.page,
            "script": lesson.get("script", ""),
            "mindmap_markdown": lesson.get("mindmap_markdown", ""),
        }
    except Exception as e:
        raise _llm_endpoint_error(e, "讲稿生成失败")


@app.post("/generate-node-script")
async def generate_node_script(req: GenerateNodeScriptRequest):
    """[DEPRECATED] 旧版节点讲稿生成，请使用 /api/v1/gen/create"""
    try:
        generator = LessonGenerator(GenerationConfig(mode=req.mode))
        return generator.generate_node_script(req.teaching_node, req.course_name, evidence=req.evidence)
    except Exception as e:
        raise _llm_endpoint_error(e, "节点讲稿生成失败")


@app.post("/generate-enhanced")
async def generate_enhanced(req: GenerateFromMarkdownRequest):
    """[DEPRECATED] 旧版增强生成，请使用 /api/v1/gen/create"""
    try:
        generator = LessonGenerator(GenerationConfig(mode=req.mode))
        return generator.generate_from_markdown_enhanced(req.markdown, req.course_name)
    except Exception as e:
        raise _llm_endpoint_error(e, "增强生成失败")


@app.post("/generate-from-markdown")
async def generate_from_markdown(req: GenerateFromMarkdownRequest):
    """[DEPRECATED] 旧版 markdown 生成，请使用 /api/v1/gen/create"""
    try:
        generator = LessonGenerator(GenerationConfig(mode=req.mode))
        return generator.generate_from_markdown(req.markdown, req.course_name)
    except Exception as e:
        raise _llm_endpoint_error(e, "Markdown 三阶段生成失败")


def _audio_base_url() -> str:
    return os.getenv("AI_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _normalize_audio_provider(provider: str) -> str:
    value = (provider or os.getenv("TTS_PROVIDER") or "mock-tts").strip().lower()
    return value or "mock-tts"


def _normalize_audio_voice(value: str) -> str:
    return (value or os.getenv("TTS_VOICE") or "alloy").strip() or "alloy"


def _normalize_audio_format(value: str) -> str:
    normalized = (value or "wav").strip().lower()
    if normalized not in {"wav", "mp3"}:
        return "wav"
    return normalized


def _estimate_duration_sec(node: GenerateAudioNode) -> int:
    if node.duration_sec > 0:
        return node.duration_sec
    text = (node.text or "").strip()
    return max(2, min(90, len(text) // 12 if text else 2))


def _write_silent_wav(output_path: Path, duration_sec: int) -> None:
    sample_rate = 16000
    chunk_frames = sample_rate
    total_frames = max(sample_rate, duration_sec * sample_rate)
    silence_chunk = b"\x00\x00" * chunk_frames
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        remaining = total_frames
        while remaining > 0:
            current = min(chunk_frames, remaining)
            wav_file.writeframes(silence_chunk[: current * 2])
            remaining -= current


def _generate_mock_tts(req: GenerateAudioRequest, provider: str, voice_type: str) -> dict[str, Any]:
    sections: List[dict[str, Any]] = []
    total_duration = 0
    for index, node in enumerate(req.nodes, start=1):
        duration_sec = _estimate_duration_sec(node)
        start_sec = node.start_sec if node.start_sec >= total_duration else total_duration
        end_sec = start_sec + duration_sec
        total_duration = end_sec

        file_name = f"{req.course_id}_p{req.page}_{index:02d}_{uuid.uuid4().hex[:8]}.wav"
        output_path = AUDIO_DIR / file_name
        _write_silent_wav(output_path, duration_sec)
        sections.append({
            "node_id": node.node_id,
            "title": node.title,
            "text": node.text,
            "duration_sec": duration_sec,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "audio_url": f"{_audio_base_url()}/generated-audio/{file_name}",
        })

    return {
        "audio_id": req.playback_id or f"audio_{req.course_id}_{req.page}",
        "audio_url": "",
        "provider": provider,
        "voice_type": voice_type,
        "format": "wav",
        "status": "ready",
        "total_duration_sec": total_duration,
        "playback_mode": "audio_timeline",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "sections": sections,
    }


def _generate_openai_tts(req: GenerateAudioRequest, provider: str, voice_type: str) -> dict[str, Any]:
    from openai import OpenAI

    api_key = os.getenv("AI_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 AI_API_KEY，无法调用 OpenAI TTS")

    model = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
    base_url, _ = resolve_llm_base_url(model)
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=resolve_llm_timeout())

    sections: List[dict[str, Any]] = []
    total_duration = 0
    for index, node in enumerate(req.nodes, start=1):
        duration_sec = _estimate_duration_sec(node)
        text = (node.text or "").strip() or node.title or node.node_id
        start_sec = node.start_sec if node.start_sec >= total_duration else total_duration
        end_sec = start_sec + duration_sec
        total_duration = end_sec

        file_name = f"{req.course_id}_p{req.page}_{index:02d}_{uuid.uuid4().hex[:8]}.mp3"
        output_path = AUDIO_DIR / file_name
        speech = client.audio.speech.create(model=model, voice=voice_type, input=text)
        speech.stream_to_file(output_path)
        sections.append({
            "node_id": node.node_id,
            "title": node.title,
            "text": node.text,
            "duration_sec": duration_sec,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "audio_url": f"{_audio_base_url()}/generated-audio/{file_name}",
        })

    return {
        "audio_id": req.playback_id or f"audio_{req.course_id}_{req.page}",
        "audio_url": "",
        "provider": provider,
        "voice_type": voice_type,
        "format": "mp3",
        "status": "ready",
        "total_duration_sec": total_duration,
        "playback_mode": "audio_timeline",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "sections": sections,
    }


@app.post("/generate-audio")
async def generate_audio(req: GenerateAudioRequest):
    if not req.course_id.strip():
        raise HTTPException(status_code=400, detail="course_id 不能为空")
    if req.page < 1:
        raise HTTPException(status_code=400, detail="page 必须大于 0")
    if not req.nodes:
        raise HTTPException(status_code=400, detail="nodes 不能为空")

    provider = _normalize_audio_provider(req.provider)
    voice_type = _normalize_audio_voice(req.voice_type)
    _ = _normalize_audio_format(req.format)
    try:
        if provider == "openai-tts":
            return _generate_openai_tts(req, provider, voice_type)
        return _generate_mock_tts(req, provider, voice_type)
    except Exception as exc:
        if provider != "mock-tts":
            fallback = _generate_mock_tts(req, "mock-tts", voice_type)
            fallback["status"] = "fallback_ready"
            fallback["fallback_reason"] = str(exc)
            return fallback
        raise HTTPException(status_code=500, detail=f"音频生成失败: {str(exc)}")


@app.post("/ask-with-context")
async def ask_with_context(req: AskWithContextRequest):
    """基于上下文直接问答（供 Go 后端调用）。"""
    try:
        parsed_document = {
            "doc_id": f"inline_{uuid.uuid4().hex[:8]}",
            "doc_name": "inline_context",
            "parsed_pages": [
                {
                    "page": req.current_page,
                    "content": req.context.strip() or "当前页面暂无文本上下文",
                    "content_length": len(req.context.strip()),
                }
            ],
        }
        responder = QAResponder(parsed_document, config=QAConfig(mode=req.mode))
        return await asyncio.to_thread(
            responder.answer, req.question, req.current_page,
            history_summary=req.history_summary, recent_turns=req.recent_turns,
        )
    except Exception as e:
        raise _llm_endpoint_error(e, "问答失败")


def _llm_parse_knowledge(text: str, mode: str) -> dict[str, Any]:
    if mode != "llm":
        raise RuntimeError("parse-knowledge 仅支持 llm 模式")

    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("缺少 openai 依赖，请安装 requirements.txt")

    api_key = os.getenv("AI_API_KEY")
    if not api_key:
        raise RuntimeError("缺少环境变量 AI_API_KEY，无法调用大模型")

    model = os.getenv("AI_MODEL", "qwen-turbo")
    base_url, _ = resolve_llm_base_url(model)
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=resolve_llm_timeout())

    prompt = (
        "请把输入内容拆解为知识点树，输出严格 JSON，格式为: "
        "{\"structure\":[{\"name\":\"章节\",\"children\":[{\"name\":\"知识点\",\"children\":[]}]}]}。"
        "不要输出额外解释。"
    )

    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": "你是课程知识点结构化助手。"},
            {"role": "user", "content": prompt + "\n\n输入内容:\n" + text[:5000]},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    data = json.loads(content)
    if "structure" not in data or not isinstance(data.get("structure"), list):
        raise RuntimeError("模型未返回合法 structure 字段")
    return {"structure": data["structure"]}


@app.post("/parse-knowledge")
async def parse_knowledge(req: ParseKnowledgeRequest):
    """将文本拆解为知识点树（供 Go 后端调用）。"""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")
    try:
        return _llm_parse_knowledge(text, req.mode)
    except Exception as e:
        raise _llm_endpoint_error(e, "知识点解析失败")


def _llm_health_payload() -> dict[str, Any]:
    api_key = (os.getenv("AI_API_KEY") or "").strip()
    model = (os.getenv("AI_MODEL") or "qwen-turbo").strip()
    base_url, normalize_reason = resolve_llm_base_url(model)
    return {
        "configured": bool(api_key),
        "mode": (os.getenv("AI_GEN_MODE") or "llm").strip() or "llm",
        "provider_base_url": base_url,
        "model": model,
        "degraded": not bool(api_key),
        "reason": "missing_api_key" if not api_key else normalize_reason,
    }


# ═══════════════════════════════════════════════════════════════
# P4 — S3 课件生成 + S4 个性化满足 新接口
# ═══════════════════════════════════════════════════════════════

# — 数据模型 —

class GenOutlineRequest(BaseModel):
    """构建大纲请求"""
    intent: dict[str, Any] = Field(default_factory=dict)
    evidence_packet: dict[str, Any] | None = None
    markdown: str | None = None
    course_name: str | None = None


class GenOutlineReviseRequest(BaseModel):
    """根据教师指令生成大纲修订候选，不负责保存或确认。"""
    nodes: list[dict[str, Any]]
    message: str


class ParseModifyRequest(BaseModel):
    """[B5] /api/v1/ai/parse_modify 请求体。"""
    project_id: str = ""
    instruction: str
    nodes: list[dict[str, Any]] = Field(default_factory=list)


_modify_intent_parser: ModifyIntentParser | None = None


def get_modify_intent_parser() -> ModifyIntentParser:
    """[B5] 单例：LLM 客户端复用。"""
    global _modify_intent_parser
    if _modify_intent_parser is None:
        _modify_intent_parser = ModifyIntentParser()
    return _modify_intent_parser


class GenNodesRequest(BaseModel):
    """生成节点讲稿请求"""
    nodes: list[dict[str, Any]]
    context_markdown: str = ""
    course_name: str | None = None
    enhanced: bool = False


class ExportPPTRequest(BaseModel):
    """导出 PPTX 请求"""
    nodes: list[dict[str, Any]]
    course_name: str = "课件"
    template_id: str = "default"


class PreviewRequest(BaseModel):
    """预览渲染请求

    支持两种调用方式：
      1. inline nodes：直接传结构化节点数组渲染
      2. 版本快照：传 gen_id（可选 version）从版本快照体系恢复节点并渲染
    """
    nodes: list[dict[str, Any]] = []
    course_name: str = "课件预览"
    gen_id: str = ""            # 版本快照预览：提供 gen_id 时按版本恢复节点
    version: int | None = None  # 指定版本号，缺省加载最新版


class ModifyRequest(BaseModel):
    """修改命令请求"""
    generation_id: str | None = None
    nodes: list[dict[str, Any]] = []
    commands: list[dict[str, Any]]  # 结构化命令列表
    regenerate: bool = False
    course_name: str | None = None
    page_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    user_instruction: str = ""


class InteractiveRequest(BaseModel):
    """互动内容生成请求"""
    node: dict[str, Any]


# — S3 课件生成接口 —

@app.post("/gen/outline")
async def generate_outline(req: GenOutlineRequest):
    """[S3] 构建大纲：从 intent / markdown 生成节点树"""
    builder = OutlineBuilder()
    try:
        if req.markdown:
            result = await asyncio.to_thread(builder.build_from_markdown, req.markdown, req.course_name)
        else:
            result = await asyncio.to_thread(builder.build, req.intent, req.evidence_packet)
        return result
    except Exception as e:
        raise _llm_endpoint_error(e, "大纲构建失败")


@app.post("/gen/outline/revise")
async def revise_outline(req: GenOutlineReviseRequest):
    """[S3] 仅计算大纲修订候选；版本和确认态仍由 Go 后端管理。"""
    try:
        return await asyncio.to_thread(OutlineBuilder().revise, req.nodes, req.message)
    except Exception as e:
        raise _llm_endpoint_error(e, "大纲修订失败")


@app.post("/gen/nodes")
async def generate_nodes(req: GenNodesRequest):
    """[S3] 逐节点生成讲稿"""
    generator = NodeGenerator()
    try:
        if req.enhanced:
            result = await asyncio.to_thread(generator.generate_enhanced, req.nodes, req.context_markdown, req.course_name)
        else:
            result = await asyncio.to_thread(generator.generate_all, req.nodes, req.context_markdown, req.course_name)
        return result
    except Exception as e:
        raise _llm_endpoint_error(e, "节点生成失败")


class GenContentRequest(BaseModel):
    """生成节点内容请求（P1：大纲确认后的内容生成阶段）"""
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    """大纲节点列表（已确认的大纲节点）"""
    context_markdown: str = ""
    course_name: str = "课件"
    mode: str = "llm"
    enhanced: bool = False
    outline_id: str = ""
    outline_version: int = 0
    # B6: 局部重生成
    target_node_ids: list[str] = Field(default_factory=list, description="[B6] 局部重生成目标节点ID；非空时进入 partial 模式")
    modify_action: str = ""
    """[B6] 修改动作：simplify/expand/rewrite/restyle 等"""
    modify_constraints: list[str] = Field(default_factory=list)
    """[B6] 教师修改约束"""


class GenContentStatusResponse(BaseModel):
    """内容生成状态响应"""
    content_id: str = ""
    status: str = "pending"  # pending / generating / done / failed
    progress_pct: float = 0.0
    current_node_id: str = ""
    total_nodes: int = 0
    completed_nodes: int = 0
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


# — P1: S3 大纲 → 内容生成（独立阶段，区别于全流程 gen/create）—

import asyncio
import threading
import uuid

# 进程内内容生成任务存储（内存层）
_content_tasks: dict[str, dict[str, Any]] = {}
_content_tasks_lock = threading.Lock()


def _persist_content_task_sync(content_id: str, data: dict) -> None:
    """在同步 daemon 线程中持久化内容生成任务快照。"""
    try:
        if getattr(_task_store, "is_redis_available", False):
            import asyncio as _asyncio
            try:
                _asyncio.run(_task_store.save_task(f"content:{content_id}", data))
            except Exception:
                pass
        _task_store._mem.save_task(f"content:{content_id}", data)
    except Exception:
        pass


@app.post("/gen/content", response_model=GenContentStatusResponse)
async def generate_content(req: GenContentRequest):
    """[S3 P1] 大纲确认后的内容生成：逐节点生成讲稿内容。

    对应 Go 端：ContentHandler.Create → AIEngine.GenerateContent
    与 /api/v1/gen/create 的区别：
      - /gen/create 是全流程（outline → nodes → PPT）
      - /gen/content 仅生成节点讲稿内容（大纲 → 内容），供教师确认后再生成 PPT
    """
    if not req.nodes:
        raise HTTPException(status_code=400, detail="nodes 不能为空")

    content_id = f"content_{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow().isoformat() + "Z"

    task_data = {
        "content_id": content_id,
        "status": "generating",
        "progress_pct": 0.0,
        "current_node_id": "",
        "total_nodes": len(req.nodes),
        "completed_nodes": 0,
        "nodes": [],
        "error": None,
        "outline_id": req.outline_id,
        "outline_version": req.outline_version,
        "mode": req.mode,
        "enhanced": req.enhanced,
        "course_name": req.course_name,
        "created_at": now,
    }

    with _content_tasks_lock:
        _content_tasks[content_id] = task_data
    _persist_content_task_sync(content_id, task_data)

    # 后台逐节点生成内容
    thread_args = (content_id, req)
    threading.Thread(target=_run_content_pipeline, args=thread_args, daemon=True).start()

    return GenContentStatusResponse(
        content_id=content_id,
        status="generating",
        progress_pct=0.0,
        total_nodes=len(req.nodes),
        completed_nodes=0,
    )


def _run_content_pipeline(content_id: str, req: GenContentRequest):
    """后台内容生成管道：逐节点生成讲稿（同步，daemon 线程）

    [B6] mode=partial 或 target_node_ids 非空时走局部重生成：
    只重新生成目标节点，其余节点内容与引用关系不变。
    """
    with _content_tasks_lock:
        task = _content_tasks.get(content_id)
        if not task:
            return

    try:
        # ---- B6: 局部重生成分支 ----
        if req.target_node_ids and req.mode == "partial":
            from ai_engine.gen.partial_content import run_partial_pipeline
            generator = NodeGenerator()
            updated_nodes = run_partial_pipeline(
                nodes=req.nodes,
                target_node_ids=req.target_node_ids,
                modify_action=req.modify_action or "rewrite",
                modify_constraints=req.modify_constraints,
                context_markdown=req.context_markdown,
                course_name=req.course_name,
                generator=generator,
            )
            with _content_tasks_lock:
                task = _content_tasks.get(content_id)
                if task:
                    task["nodes"] = updated_nodes
                    task["status"] = "done"
                    task["progress_pct"] = 100.0
                    task["completed_nodes"] = len(req.target_node_ids)
                    task["total_nodes"] = len(req.nodes)
                    _content_tasks[content_id] = task
                _persist_content_task_sync(content_id, task)
            return

        generator = NodeGenerator()
        nodes = req.nodes
        total = len(nodes)
        completed = []
        errors = []

        for idx, node in enumerate(nodes):
            try:
                task["current_node_id"] = node.get("node_id", "")
                pct = ((idx) / total) * 100.0 if total > 0 else 0.0
                task["progress_pct"] = pct
                with _content_tasks_lock:
                    _content_tasks[content_id] = task
                _persist_content_task_sync(content_id, task)

                node_type = str(node.get("node_type") or node.get("type") or "").strip().lower()
                if node_type == "interactive":
                    interactive_items = InteractiveBuilder().build_all(node)
                    from ai_engine.gen.export_html5 import render_interactive_html
                    merged = {
                        **node,
                        "interactive_items": interactive_items,
                        "content": render_interactive_html(
                            interactive_items,
                            course_name=req.course_name,
                            title=str(node.get("title") or "互动课堂"),
                        ),
                    }
                elif req.enhanced:
                    result = generator.generate_enhanced(nodes, req.context_markdown, req.course_name)
                    script_data = next(
                        (s for s in result.get("scripts", []) if s.get("node_id") == node.get("node_id")),
                        {"script": "", "segments": []},
                    )
                else:
                    script_data = generator.generate_single(node, req.course_name)

                    merged = {**node, **script_data}
                completed.append(merged)
                task["completed_nodes"] = idx + 1
                task["nodes"] = list(completed)
                with _content_tasks_lock:
                    _content_tasks[content_id] = task
                _persist_content_task_sync(content_id, task)

            except Exception as node_err:
                import logging
                logging.getLogger(__name__).warning(
                    "[Content Pipeline] node %s error: %s", node.get("node_id"), str(node_err)
                )
                errors.append({"node_id": node.get("node_id"), "error": str(node_err)})
                completed.append({**node, "script": "", "segments": [], "error": str(node_err)})
                task["completed_nodes"] = idx + 1
                task["nodes"] = list(completed)
                with _content_tasks_lock:
                    _content_tasks[content_id] = task
                _persist_content_task_sync(content_id, task)

        # 完成
        task["status"] = "done"
        task["progress_pct"] = 100.0
        task["current_node_id"] = ""
        if errors:
            task["error"] = f"{len(errors)} 个节点生成失败"
        with _content_tasks_lock:
            _content_tasks[content_id] = task
        _persist_content_task_sync(content_id, task)

    except Exception as e:
        import logging, traceback
        logging.getLogger(__name__).error(
            "[Content Pipeline ERROR] content_id=%s error=%s\n%s",
            content_id, str(e), traceback.format_exc()
        )
        task["status"] = "failed"
        task["error"] = str(e)
        with _content_tasks_lock:
            _content_tasks[content_id] = task
        _persist_content_task_sync(content_id, task)


@app.get("/gen/content/status/{content_id}", response_model=GenContentStatusResponse)
async def content_status(content_id: str):
    """[S3 P1] 查询内容生成任务状态。

    对应 Go 端：ContentHandler.Status → AIEngine.ContentStatus
    """
    with _content_tasks_lock:
        task = _content_tasks.get(content_id)

    # Redis 回退
    if not task:
        redis_data = await _task_store.load_task(f"content:{content_id}")
        if redis_data:
            task = redis_data
            with _content_tasks_lock:
                _content_tasks[content_id] = task

    if not task:
        raise HTTPException(status_code=404, detail="内容生成任务不存在")

    return GenContentStatusResponse(
        content_id=task.get("content_id", content_id),
        status=task.get("status", "pending"),
        progress_pct=task.get("progress_pct", 0.0),
        current_node_id=task.get("current_node_id", ""),
        total_nodes=task.get("total_nodes", 0),
        completed_nodes=task.get("completed_nodes", 0),
        nodes=task.get("nodes", []),
        error=task.get("error"),
    )


@app.post("/gen/node/single")
async def generate_single_node(req: dict[str, Any]):
    """[S3] 单个节点重生成（供 S4 修补调用）"""
    node = req.get("node", {})
    course_name = req.get("course_name")
    generator = NodeGenerator()
    try:
        return await asyncio.to_thread(generator.generate_single, node, course_name)
    except Exception as e:
        raise _llm_endpoint_error(e, "单节点生成失败")


@app.post("/gen/export/ppt")
async def export_ppt(req: ExportPPTRequest):
    """[S3] 导出 PPTX"""
    exporter = PPTExporter()
    try:
        return exporter.export(req.nodes, req.course_name, req.template_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PPTX 导出失败: {str(e)}")


@app.post("/gen/export/ppt-bytes")
async def export_ppt_bytes(req: ExportPPTRequest):
    """[S3] 导出 PPTX 字节流（直接上传 MinIO）"""
    exporter = PPTExporter()
    try:
        buf = exporter.export_to_bytes(req.nodes, req.course_name, req.template_id)
        from fastapi.responses import StreamingResponse
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                 headers={"Content-Disposition": f"attachment; filename={req.course_name}.pptx"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PPTX 导出失败: {str(e)}")


@app.post("/gen/export/doc")
async def export_doc(req: ExportPPTRequest):
    """[S3] 导出 DOCX"""
    exporter = DOCExporter()
    try:
        return exporter.export(req.nodes, req.course_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DOCX 导出失败: {str(e)}")


@app.post("/gen/export/doc-bytes")
async def export_doc_bytes(req: ExportPPTRequest):
    """[S3] 导出 DOCX 字节流（直接上传 MinIO）"""
    exporter = DOCExporter()
    try:
        buf = exporter.export_to_bytes(req.nodes, req.course_name)
        from fastapi.responses import StreamingResponse
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                 headers={"Content-Disposition": f"attachment; filename={req.course_name}.docx"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DOCX 导出失败: {str(e)}")


@app.post("/gen/interactive")
async def generate_interactive(req: InteractiveRequest):
    """[S3] 生成互动内容（测验/闪卡/投票）"""
    builder = InteractiveBuilder()
    try:
        return {"items": await asyncio.to_thread(builder.build_all, req.node)}
    except Exception as e:
        raise _llm_endpoint_error(e, "互动内容生成失败")


# — S3 生成终稿（从确认内容 → 版本快照 / PPT）—

class GenFinalizeRequest(BaseModel):
    """生成终稿请求：从教师确认的内容节点创建版本快照。"""
    generation_id: str | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    course_name: str = "课件"
    summary: str = "教师确认终稿"
    outline_id: str = ""
    outline_version: int = 0
    page_bindings: list[dict[str, Any]] = Field(default_factory=list)
    presentation: dict[str, Any] = Field(default_factory=dict)


class GenFinalizeResponse(BaseModel):
    """生成终稿响应"""
    generation_id: str
    version_number: int
    status: str


@app.post("/api/v1/gen/finalize", response_model=GenFinalizeResponse)
async def gen_finalize(req: GenFinalizeRequest):
    """[S3] 生成终稿：从确认的内容节点创建版本快照。

    对应 Go 端：GenerationHandler.Finalize → AIEngine.GenerationFinalize

    流程：
      1. 接收确认后的内容节点
      2. 创建 generation 任务（状态 done）
      3. 保存版本快照（PPT 步骤）
      4. 返回 generation_id 和 version_number

    与 /api/v1/gen/create 的区别：
      - /gen/create 是全流程（outline → nodes → PPT），含 LLM 生成
      - /gen/finalize 仅做版本快照，节点内容由前端/后端确认后直接传入
    """
    if not req.nodes:
        raise HTTPException(status_code=400, detail="nodes 不能为空")

    gen_id = req.generation_id or f"course_{uuid.uuid4().hex[:12]}"

    # 创建已完成 generation 任务
    task = GenerationTask(
        task_id=f"gen_{uuid.uuid4().hex[:12]}",
        session_id=gen_id,
        generation_id=gen_id,
        outline_id=req.outline_id,
        outline_version=req.outline_version,
        status=GenerationStatus.DONE,
        stage=GenerationStage.DONE,
        progress_pct=100.0,
        intent=IntentSummary(topic=req.course_name),
        nodes=[TeachingNode.model_validate(node) for node in req.nodes],
        created_at=datetime.now(),
    )

    with _gen_tasks_lock:
        _gen_tasks[task.task_id] = task
    await _persist_generation_task(task)

    # 保存版本快照
    vm = get_version_manager()
    snapshot = vm.save_snapshot(
        generation_id=gen_id,
        nodes=req.nodes,
        summary=req.summary,
        metadata={
            "outline_id": req.outline_id,
            "outline_version": req.outline_version,
        },
        page_bindings=req.page_bindings,
        presentation=req.presentation,
    )

    return GenFinalizeResponse(
        generation_id=gen_id,
        version_number=snapshot.version_number,
        status="done",
    )


# — S4 个性化满足接口 —

@app.post("/api/v1/gen/preview")
async def render_preview(req: PreviewRequest):
    """[S4] 预览渲染：节点树 / 版本快照 → HTML

    inline nodes 直接渲染；提供 gen_id 时从版本快照恢复节点再渲染，
    返回 version_number 与恢复的节点，供前端持久化与数据同步。
    """
    renderer = PreviewRenderer()
    nodes = req.nodes or []
    generation_id = (req.gen_id or "").strip()
    version_number: int | None = None
    course_name = req.course_name or "课件预览"

    try:
        if generation_id and not nodes:
            snapshot = get_version_manager().load_version(generation_id, req.version)
            if not snapshot:
                raise HTTPException(status_code=404, detail="版本不存在，请先完成 S3 生成")
            nodes = [
                node.model_dump() if hasattr(node, "model_dump") else node
                for node in snapshot.nodes_snapshot
            ]
            version_number = snapshot.version_number
            # 快照 summary 为空时保留默认课程名，否则以快照摘要为准
            if snapshot.summary and snapshot.summary not in ("", "课件预览", "初始版本", f"版本 {version_number}"):
                course_name = snapshot.summary

        # 预览必须走 PreviewRenderer：它是唯一读取 metadata.presentation
        # （配色/字体/密度）的渲染器，且内部已自行润色（见 preview.py render()）。
        html_content = renderer.render(nodes, course_name)
        return {
            "html": html_content,
            "node_count": len(nodes),
            "generation_id": generation_id or None,
            "version_number": version_number,
            "nodes": nodes,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览渲染失败: {str(e)}")


def _load_page_evidence(evidence_refs: list[str] | None) -> tuple[str, list[str]]:
    """Load only explicitly bound chunks for page-scoped regeneration."""
    if not evidence_refs:
        return "", []
    from importlib import import_module

    store = import_module("ai_engine.rag.router")._store
    blocks: list[str] = []
    used: list[str] = []
    for raw_ref in evidence_refs:
        ref = str(raw_ref or "").strip()
        if not ref or ref in used:
            continue
        chunk = store.get_chunk(ref)
        content = str(getattr(chunk, "content", "") or "").strip() if chunk else ""
        if not content:
            continue
        used.append(ref)
        blocks.append(f"[{ref}] {content}")
    if not blocks:
        return "", []
    return "仅依据以下已绑定证据修改，不得引用其他资料：\n" + "\n\n".join(blocks), used


@app.post("/api/v1/gen/modify")
async def modify_nodes(req: ModifyRequest):
    """[S4] 修改命令：应用编辑命令到节点树

    支持两种数据源：
      1. generation_id 以 "gen_" 开头 → 从版本快照加载（原有行为）
      2. generation_id 以 "content_" 开头 → 从内容任务加载（新增：支持内容修改）
      3. 直接传 nodes → 内联节点（原有行为）
    """
    parser = CommandParser()
    patcher = NodePatcher()

    # 版本管理页面只持有 generation_id；Studio 可以直接提交当前节点树。
    # 新增：内容修改场景下 generation_id 以 "content_" 开头，从 _content_tasks 加载。
    nodes = req.nodes
    is_content_task = False
    if not nodes and req.generation_id:
        if req.generation_id.startswith("content_"):
            # 从内容任务加载节点（支持内容修改）
            with _content_tasks_lock:
                content_task = _content_tasks.get(req.generation_id)
            if not content_task:
                raise HTTPException(status_code=404, detail="内容任务不存在")
            nodes = content_task.get("nodes", [])
            is_content_task = True
            if not nodes:
                raise HTTPException(status_code=400, detail="内容任务无节点数据")
        else:
            # 从版本快照加载（原有行为）
            snapshot = get_version_manager().load_version(req.generation_id)
            if not snapshot:
                raise HTTPException(status_code=404, detail="版本不存在")
            nodes = [node.model_dump() if hasattr(node, "model_dump") else node for node in snapshot.nodes_snapshot]
    if not nodes:
        raise HTTPException(status_code=400, detail="nodes 或 generation_id 至少提供一个")

    # 解析命令
    parse_result = parser.parse(req.commands)
    if parse_result.errors:
        return {"status": "parse_error", "errors": parse_result.errors}

    # 验证命令
    valid_ids = {n["node_id"] for n in nodes}
    all_errors = []
    for cmd in parse_result.commands:
        errs = parser.validate(cmd, valid_ids)
        all_errors.extend(errs)
    if all_errors:
        return {"status": "validation_error", "errors": all_errors}

    # 执行修补
    generator = NodeGenerator(NodeGenConfig()) if req.regenerate else None
    evidence_context, evidence_used = _load_page_evidence(req.evidence_refs)

    def regenerate_node(nid, node):
        if not generator:
            return node
        applies_to_page = not req.page_id or str(nid) == str(req.page_id)
        parts = []
        if applies_to_page and req.user_instruction.strip():
            parts.append(req.user_instruction.strip())
        if applies_to_page and evidence_context:
            parts.append(evidence_context)
        return generator.generate_single(
            node,
            req.course_name,
            extra_instruction="\n\n".join(parts),
        )

    regenerate_fn = regenerate_node if generator else None
    try:
        result = await asyncio.to_thread(patcher.apply, nodes, parse_result.commands, regenerate_fn)
    except Exception as e:
        raise _llm_endpoint_error(e, "修改命令执行失败")

    # 把本次实际使用的绑定证据写回目标页；不让请求中的缺失 chunk 伪装成引用。
    if evidence_used and not result.errors:
        target_ids = {str(req.page_id)} if req.page_id else {
            str(command.params.get("node_id"))
            for command in parse_result.commands
            if command.params.get("node_id")
        }
        for node in result.nodes:
            if target_ids and str(node.get("node_id")) not in target_ids:
                continue
            refs = list(dict.fromkeys([*(node.get("source_chunk_ids") or []), *evidence_used]))
            node["source_chunk_ids"] = refs
            node["citation_refs"] = list(refs)

    # 保存修改结果
    version_number = None
    if is_content_task and req.generation_id and not result.errors:
        # 内容任务：将修改后的节点写回 _content_tasks
        with _content_tasks_lock:
            if req.generation_id in _content_tasks:
                _content_tasks[req.generation_id]["nodes"] = result.nodes
                _persist_content_task_sync(req.generation_id, _content_tasks[req.generation_id])
    elif req.generation_id and not result.errors and not is_content_task:
        # 版本快照：保存新版本（原有行为）
        version = get_version_manager().save_snapshot(
            generation_id=req.generation_id,
            nodes=result.nodes,
            summary="编辑修改",
        )
        version_number = version.version_number

        # 内存数据同步
        if req.generation_id:
            vm = get_version_manager()
            latest = vm.load_version(req.generation_id)
            if latest and latest.nodes_snapshot:
                refreshed_nodes = [
                    n.model_dump() if hasattr(n, "model_dump") else n
                    for n in latest.nodes_snapshot
                ]
                for tid, task in _gen_tasks.items():
                    if task.generation_id == req.generation_id:
                        task.nodes = refreshed_nodes
                        task.status = GenerationStatus.DONE
                        task.stage = GenerationStage.DONE
                        task.progress_pct = 100.0

    return {
        "status": "ok" if not result.errors else "partial_error",
        "nodes": result.nodes,
        "changes": result.changes,
        "errors": result.errors,
        "version_number": version_number,
        "page_id": req.page_id,
        "citation_refs": evidence_used,
        "evidence_used": evidence_used,
    }


@app.post("/gen/parse-command")
async def parse_command(raw_input: dict[str, Any]):
    """[S4] 解析修改命令（自然语言 → 结构化命令）"""
    parser = CommandParser()
    result = parser.parse(raw_input.get("text", ""))
    return {
        "is_structured": result.is_structured,
        "commands": [
            {"type": c.type.value, "params": c.params, "confidence": c.confidence}
            for c in result.commands
        ],
        "errors": result.errors,
    }


@app.get("/gen/full-pipeline")
async def full_pipeline_preview(markdown: str = "", course_name: str = "课件"):
    """[S3+S4] 一键全流程：Markdown → 大纲 → 节点 → 预览 HTML"""
    if not markdown.strip():
        raise HTTPException(status_code=400, detail="markdown 参数不能为空")
    try:
        # 1. 大纲
        builder = OutlineBuilder()
        outline = await asyncio.to_thread(builder.build_from_markdown, markdown, course_name)

        # 2. 节点讲稿
        generator = NodeGenerator()
        scripts = await asyncio.to_thread(generator.generate_all, outline["nodes"], markdown, course_name)

        # 3. 合并节点数据
        merged_nodes = []
        for node in outline["nodes"]:
            script = next(
                (s for s in scripts["scripts"] if s["node_id"] == node["node_id"]),
                {"script": "", "segments": []},
            )
            merged = {**node, "script": script.get("script", ""), "segments": script.get("segments", [])}
            merged_nodes.append(merged)

        # 4. 预览
        renderer = PreviewRenderer()
        html = renderer.render(merged_nodes, course_name)

        return {
            "course_name": course_name,
            "node_count": len(merged_nodes),
            "used_fallback": outline.get("used_fallback", False) or scripts.get("used_fallback", False),
            "outline": outline,
            "scripts": scripts,
            "preview_html": html,
        }
    except Exception as e:
        raise _llm_endpoint_error(e, "全流程失败")


# =============================================================================
# S4 版本管理端点（对齐 Go VersionHandler → AIEngine）
# =============================================================================

from ai_engine.gen.version import get_version_manager


@app.get("/api/v1/version/{gen_id}/history")
async def version_history(gen_id: str):
    """GET /api/v1/version/{gen_id}/history — 版本历史列表"""
    vm = get_version_manager()
    versions = vm.list_versions(gen_id)
    return {
        "versions": [
            {
                "version_number": v.version_number,
                "id": v.id,
                "summary": v.summary,
                "locked": v.locked,
                "created_at": v.created_at.isoformat() if v.created_at else "",
            }
            for v in versions
        ]
    }


@app.post("/api/v1/version/{gen_id}/rollback")
async def version_rollback(gen_id: str, req: RollbackRequest):
    """POST /api/v1/version/{gen_id}/rollback — 回滚到指定版本"""
    vm = get_version_manager()
    try:
        new_ver = vm.revert_to(gen_id, req.target_version)
        return {
            "current_version": new_ver.version_number,
            "status": "done",
            "nodes": [n.model_dump() if hasattr(n, "model_dump") else n for n in new_ver.nodes_snapshot],
            "page_bindings": new_ver.page_bindings,
            "presentation": new_ver.presentation,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/version/{gen_id}/lock")
async def version_lock(gen_id: str):
    """POST /api/v1/version/{gen_id}/lock — 锁定最新版"""
    vm = get_version_manager()
    try:
        locked = vm.lock_version(gen_id)
        return {"version": locked.version_number, "locked": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/version/{gen_id}")
async def version_load(gen_id: str, v: int | None = None):
    """GET /api/v1/version/{gen_id}?v=N — 加载指定版本，为空则加载最新版"""
    vm = get_version_manager()
    snap = vm.load_version(gen_id, v)
    if not snap:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {
        "version_number": snap.version_number,
        "id": snap.id,
        "nodes_snapshot": [n.model_dump() if hasattr(n, "model_dump") else n for n in snap.nodes_snapshot],
        "page_bindings": snap.page_bindings,
        "presentation": snap.presentation,
        "summary": snap.summary,
        "locked": snap.locked,
        "created_at": snap.created_at.isoformat() if snap.created_at else "",
    }


@app.get("/api/v1/version/{gen_id}/diff")
async def version_diff(gen_id: str, v1: int, v2: int):
    """GET /api/v1/version/{gen_id}/diff?v1=1&v2=2 — 对比两个版本差异"""
    vm = get_version_manager()
    return vm.diff(gen_id, v1, v2)


# =============================================================================
# S3 生成任务管理端点（对齐 Go GenerationHandler → AIEngine）
# =============================================================================

import asyncio
import threading
import uuid
from ai_engine.core.schema import (
    GenerationCreateRequest,
    GenerationCreateResponse,
    GenerationStatusResponse,
    GenerationStatus,
    GenerationStage,
    ExportRequest,
    ExportFormat,
    ExportStatusResponse,
    ExportStatus,
    ExportJob,
)
from ai_engine.gen.version import get_version_manager
from ai_engine.core.redis_client import get_redis_task_store

# 进程内生成任务存储（内存层）+ Redis 持久化层
_gen_tasks: dict[str, GenerationTask] = {}
# 注意：_gen_tasks 会被两个线程访问 —— 事件循环线程（async 端点）与
# daemon 生成线程（_run_generation_pipeline）。因此必须用 threading.Lock，
# 不能用 asyncio.Lock（既非线程安全，也不能在同步线程里 with 使用）。
_gen_tasks_lock = threading.Lock()
_task_store = get_redis_task_store()  # Redis 持久化（不可用时自动降级内存）


async def _persist_generation_task(task: GenerationTask) -> None:
    """Persist the latest task snapshot for cross-worker status queries."""
    task_dict = task.model_dump(mode="json")
    task_dict["status"] = task.status.value
    task_dict["stage"] = task.stage.value
    await _task_store.save_task(task.task_id, task_dict)


def _restore_task_from_dict(data: dict) -> GenerationTask | None:
    """从 Redis 加载的 dict 重建 GenerationTask Pydantic 对象。"""
    try:
        from ai_engine.core.schema import GenerationStatus, GenerationStage
        # 恢复枚举值
        status_str = data.get("status", "")
        stage_str = data.get("stage", "")
        data["status"] = GenerationStatus(status_str) if status_str else GenerationStatus.PENDING
        data["stage"] = GenerationStage(stage_str) if stage_str else GenerationStage.INTENT_LOCKED
        # nodes 从 JSON 字符串还原
        if isinstance(data.get("nodes"), str):
            import json
            data["nodes"] = json.loads(data["nodes"])
        return GenerationTask(**data)
    except Exception:
        return None


@app.post("/api/v1/gen/create", response_model=GenerationCreateResponse)
async def gen_create(req: GenerationCreateRequest):
    """
    POST /api/v1/gen/create — 创建生成任务，执行 outline → nodes 全流程。

    对应 Go 端：GenerationHandler.Create → AIEngine.GenerationCreate
    """
    if req.outline_id:
        if not req.outline_confirmed:
            raise HTTPException(status_code=409, detail="大纲尚未确认")
        if req.outline_version <= 0:
            raise HTTPException(status_code=409, detail="大纲版本无效")
        if not req.outline_nodes:
            raise HTTPException(status_code=409, detail="已确认大纲缺少节点")

    task_id = f"gen_{uuid.uuid4().hex[:12]}"
    gen_id = f"course_{uuid.uuid4().hex[:12]}"

    # 构建任务对象
    # 如果有 course_id/title/markdown，构建 intent
    intent = req.intent
    if req.course_id and not req.session_id:
        # 前端调用时只传了 course_id，构建默认 intent
        if not intent.topic and req.title:
            intent.topic = req.title

    task = GenerationTask(
        task_id=task_id,
        session_id=req.session_id or req.course_id,
        generation_id=gen_id,
        outline_id=req.outline_id,
        outline_version=req.outline_version,
        status=GenerationStatus.PENDING,
        stage=GenerationStage.INTENT_LOCKED,
        progress_pct=0.0,
        intent=intent,
        evidence=req.evidence_packet,
        template_id=req.template_id,
        nodes=[],
        created_at=datetime.now(),
    )

    with _gen_tasks_lock:
        _gen_tasks[task_id] = task
    # 持久化到 Redis（跨 worker 可见；Redis 不可用时自动降级）
    await _persist_generation_task(task)

    # 后台执行生成管道（同步管道放 daemon 线程，避免阻塞事件循环）

    threading.Thread(target=_run_generation_pipeline, args=(task_id, req), daemon=True).start()
    return GenerationCreateResponse(
        task_id=task_id,
        generation_id=gen_id,
        status=GenerationStatus.PENDING,
        generation_type="ppt" if not req.intent.output_format else (req.intent.output_format[0] if req.intent.output_format else "ppt"),
        outline_id=req.outline_id,
        outline_version=req.outline_version,
    )


def _persist_task_sync(task: GenerationTask) -> None:
    """在同步上下文（daemon 生成线程）中持久化任务快照。

    RedisTaskStore 的 save_task 是 async 方法；在 daemon 线程里没有事件循环，
    不能直接 await。这里优先复用 RedisTaskStore 的同步内存回退存储
    （_InMemoryTaskStore，线程安全），Redis 可用时再在线程内以事件循环方式写。
    """
    task_dict = task.model_dump(mode="json")
    task_dict["status"] = task.status.value
    task_dict["stage"] = task.stage.value
    # Redis 可用时，用临时事件循环在 daemon 线程内写 Redis（跨 worker 可见）
    if getattr(_task_store, "is_redis_available", False):
        try:
            _task_store._serialize(task_dict)  # 预校验可序列化
            asyncio.run(_task_store.save_task(task.task_id, task_dict))
            return
        except Exception:
            pass  # 降级到内存回退存储
    # 内存回退存储（_InMemoryTaskStore.save_task 是同步、线程安全）
    _task_store._mem.save_task(task.task_id, task_dict)


def _run_generation_pipeline(task_id: str, req: GenerationCreateRequest):
    """后台生成管道：outline → nodes → 保存版本快照（同步，运行于 daemon 线程）"""
    with _gen_tasks_lock:
        task = _gen_tasks.get(task_id)
        if not task:
            return

    try:
        # Stage 1: 意图锁定
        task.status = GenerationStatus.GENERATING
        task.stage = GenerationStage.INTENT_LOCKED
        task.progress_pct = 10.0
        _persist_task_sync(task)

        # Stage 2: 收集证据（如有）
        # ★ P1修复：如果前端未传 evidence_packet，但有 session_id，
        #   自动从 RAG 知识库获取证据，实现 S2→KB→S3 自动链路。
        task.stage = GenerationStage.EVIDENCE_GATHERING
        task.progress_pct = 20.0
        _persist_task_sync(task)
        evidence_dict = None
        if req.evidence_packet:
            evidence_dict = req.evidence_packet.model_dump() if hasattr(req.evidence_packet, "model_dump") else req.evidence_packet
        elif req.session_id:
            # 自动从 RAG 获取证据：检索 session 对应的已解析 chunks
            try:
                retriever = _get_retriever()
                candidates = retriever.search(
                    query=req.intent.topic or "",
                    top_k=20,
                    min_score=0.3,
                    knowledge_base_ids=None,
                )
                if candidates:
                    reranked = _reranker.rerank(
                        query=req.intent.topic or "",
                        candidates=candidates,
                        top_k=5,
                    )
                    synthesized = _synthesizer.synthesize_to_response(
                        search_results=reranked,
                        query=req.intent.topic or "",
                        context={},
                    )
                    evidence_dict = synthesized.model_dump() if hasattr(synthesized, "model_dump") else dict(synthesized)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "[S3 Evidence] 自动证据获取失败，改为无证据生成: session_id=%s, error=%s",
                    req.session_id, str(e)
                )

        # Stage 3: 构建大纲
        task.stage = GenerationStage.STRUCTURING
        task.progress_pct = 30.0
        _persist_task_sync(task)
        if req.outline_id:
            # 新流程：只使用 Go 已确认并注入的指定版本大纲，禁止重新生成覆盖。
            nodes = []
            for raw_node in req.outline_nodes:
                node = dict(raw_node)
                node_type = str(node.get("node_type") or node.get("type") or "slide")
                # 前端大纲词汇只在 AI 输入边界映射；Go 保存的教师大纲保持原值。
                if node_type in {"content", "summary"}:
                    node_type = "slide"
                node["node_type"] = node_type
                node["type"] = node_type
                nodes.append(node)
        else:
            # 兼容旧调用：未携带 outline_id 时仍执行原有一键生成流程。
            builder = OutlineBuilder()
            if req.markdown:
                outline = builder.build_from_markdown(req.markdown, req.intent.topic or "课件")
            else:
                intent_dict = req.intent.model_dump() if hasattr(req.intent, "model_dump") else req.intent
                outline = builder.build(intent_dict, evidence_dict)
            nodes = outline.get("nodes", [])
        # Outline responses may use the legacy Go-facing `content` type. The
        # generation pipeline must validate only the internal TeachingNode
        # enum, so normalize both confirmed and legacy paths at one boundary.
        nodes = normalize_generation_nodes(nodes)
        # S1→S3 自动检索绑定的是整份 PPT 草稿。必须在 AI 任务与版本快照
        # 层写入引用，不能只依赖前端渲染后补字段，否则刷新/回滚会丢绑定。
        nodes = bind_evidence_to_draft_nodes(nodes, evidence_dict)
        task.nodes = [TeachingNode.model_validate(node) for node in nodes]
        task.progress_pct = 50.0

        # Stage 4: 讲稿生成（增强版）
        # 有 markdown 时用 LessonGenerator（已验证 LLM 路径正确），无 markdown 时降级为 NodeGenerator
        task.stage = GenerationStage.GENERATING
        _persist_task_sync(task)
        course_name = req.intent.topic or "课件"
        if req.markdown:
            lesson_gen = LessonGenerator(GenerationConfig(mode="llm"))

            def _stage_progress_cb(pct: float, message: str = "") -> None:
                # Stage3 分块并行的 worker 线程会并发回调本函数：
                # 1) 只增不减，避免乱序回调把进度拉回去
                # 2) 持久化走 _persist_task_sync（daemon 线程内临时事件循环写 Redis /
                #    线程安全的内存回退），回调异常必须吞掉，不能打断生成管道
                try:
                    task.progress_pct = max(task.progress_pct, float(pct))
                    with _gen_tasks_lock:
                        _gen_tasks[task_id] = task
                    _persist_task_sync(task)
                except Exception:
                    pass

            result = lesson_gen.generate_from_markdown_enhanced(
                req.markdown, course_name, progress_cb=_stage_progress_cb,
                preset_nodes=nodes,
            )
            scripts_list = result.get("scripts", [])
            node_ids = {n["node_id"] for n in nodes}
            scripts_dict = {"scripts": scripts_list}
        else:
            generator = NodeGenerator()
            scripts_dict = generator.generate_all(nodes, "", course_name)
            scripts_list = scripts_dict.get("scripts", [])
            node_ids = {n["node_id"] for n in nodes}
        task.progress_pct = 80.0

        # 合并节点
        merged_nodes = []
        for node in nodes:
            script_data = next(
                (s for s in scripts_list if s.get("node_id") == node.get("node_id")),
                {"script": "", "segments": []},
            )
            merged = {**node}
            if isinstance(script_data, dict):
                merged["script"] = script_data.get("script", "")
                merged["segments"] = script_data.get("segments", [])
            merged_nodes.append(merged)
        task.nodes = merged_nodes

        # Stage 5: 内容自适应校验（标注超长节点字号/分页提示）
        validator = ContentValidator()
        validated_nodes = []
        for n in merged_nodes:
            vr = validator.validate(n)
            n = validator.compute_scaled_font(n, vr)
            validated_nodes.append(n)
        task.nodes = [TeachingNode.model_validate(node) for node in validated_nodes]
        merged_nodes = validated_nodes

        # Stage 6: 保存版本快照
        task.stage = GenerationStage.PREVIEW
        task.progress_pct = 90.0
        _persist_task_sync(task)
        vm = get_version_manager()
        vm.save_snapshot(
            generation_id=task.generation_id,
            nodes=merged_nodes,
            summary="初稿",
            metadata={
                "outline_id": req.outline_id,
                "outline_version": req.outline_version,
            },
        )

        # 完成
        task.status = GenerationStatus.DONE
        task.stage = GenerationStage.DONE
        task.progress_pct = 100.0

        with _gen_tasks_lock:
            _gen_tasks[task_id] = task
        _persist_task_sync(task)

    except Exception as e:
        import logging, traceback
        logging.getLogger(__name__).error(
            "[Pipeline ERROR] gen_id=%s task_id=%s error=%s\n%s",
            getattr(task, 'generation_id', '?'), task_id, str(e), traceback.format_exc()
        )
        task.status = GenerationStatus.FAILED
        task.error = str(e)
        with _gen_tasks_lock:
            _gen_tasks[task_id] = task
        _persist_task_sync(task)


@app.get("/api/v1/gen/status/{task_id}", response_model=GenerationStatusResponse)
async def gen_status(task_id: str):
    """
    GET /api/v1/gen/status/{task_id} — 查询生成任务状态。

    对应 Go 端：GenerationHandler.Status → AIEngine.GenerationStatus
    读取顺序：内存 dict（快）→ Redis（进程重启后可恢复）→ 404
    """
    with _gen_tasks_lock:
        task = _gen_tasks.get(task_id)

    # Redis 回退：进程重启后从 Redis 恢复任务状态
    if not task:
        redis_data = await _task_store.load_task(task_id)
        if redis_data:
            task = _restore_task_from_dict(redis_data)
            if task:
                with _gen_tasks_lock:
                    _gen_tasks[task_id] = task

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    stage_map = {
        "intent_locked": "正在解析意图…",
        "evidence_gathering": "正在收集素材…",
        "structuring": "正在构建大纲…",
        "generating": "正在生成讲稿…",
        "preview": "正在生成预览…",
        "modifying": "正在应用修改…",
        "done": "生成完成",
    }

    return GenerationStatusResponse(
        task_id=task.task_id,
        generation_id=task.generation_id,
        outline_id=task.outline_id,
        outline_version=task.outline_version,
        status=task.status,
        stage=task.stage,
        progress_pct=task.progress_pct,
        progress=task.progress_pct / 100.0 if task.progress_pct else 0.0,
        stage_text=stage_map.get(task.stage.value if hasattr(task.stage, 'value') else str(task.stage or ""), ""),
        current_node=task.current_node or "",
        nodes=task.nodes,
        preview_url=None,
        error=task.error,
    )


@app.get("/api/v1/gen/preview/{gen_id}")
async def get_preview(gen_id: str, version: Optional[int] = None):
    """
    GET /api/v1/gen/preview/{gen_id} — 读取版本快照并渲染预览 HTML。

    对应 Go 端：GenerationHandler.Preview → AIEngine.GetPreview
    version: 留空加载最新版；指定版本号加载对应快照。
    前端刷新页面时调用此接口恢复预览内容（磁盘快照，跨重启有效）。
    """
    # 生成管道在完成前必写磁盘快照，因此统一从版本快照读取，
    # 与 POST /api/v1/gen/preview 的 gen_id 路径保持一致（version_number / course_name 一致）。
    snapshot = get_version_manager().load_version(gen_id, version)
    if not snapshot:
        raise HTTPException(status_code=404, detail="版本不存在，请先完成 S3 生成")
    nodes = [
        node.model_dump() if hasattr(node, "model_dump") else node
        for node in snapshot.nodes_snapshot
    ]
    if not nodes:
        raise HTTPException(status_code=404, detail="该版本无节点数据")

    renderer = PreviewRenderer()
    version_number = snapshot.version_number
    course_name = snapshot.summary or gen_id
    html = renderer.render(nodes, course_name)
    return {
        "html": html,
        "node_count": len(nodes),
        "generation_id": gen_id,
        "version_number": version_number,
        "nodes": nodes,
    }


# =============================================================================
# S4 异步导出端点（对齐 Go ExportHandler → AIEngine）
# =============================================================================

from ai_engine.gen.export_ppt import PPTExporter, ExportPPTConfig
from ai_engine.gen.export_doc import DOCExporter, ExportDocConfig, LessonPlanDOCExporter
from ai_engine.gen.export_html5 import export_interactive_html
from ai_engine.gen.lesson_plan import LessonPlanGenerator

# 进程内导出任务存储
_export_tasks: dict[str, ExportJob] = {}
_export_lock = asyncio.Lock()


def _export_contract_filename(courseware_title: str, version: int, fmt: ExportFormat) -> str:
    safe_title = "".join("_" if ch in '\\/:*?\"<>|' else ch for ch in courseware_title).strip(" .") or "课件"
    extension = {
        ExportFormat.DOCX: "docx",
        ExportFormat.LESSON_PLAN: "docx",
        ExportFormat.INTERACTIVE: "html",
    }.get(fmt, "pptx")
    return f"{safe_title}_v{version}.{extension}"


@app.post("/api/v1/exp/{gen_id}", response_model=ExportStatusResponse)
@app.post("/api/v1/export/{gen_id}", response_model=ExportStatusResponse)
async def export_create(gen_id: str, req: ExportRequest):
    """
    POST /api/v1/export/{gen_id} — 创建异步导出任务。

    对应 Go 端：ExportHandler.Create → AIEngine.ExportCreate
    """
    job_id = f"exp_{uuid.uuid4().hex[:12]}"

    requested_version = int(req.version or 0)
    # S4 项目版本以 Go/PostgreSQL 的快照为权威来源。传入 nodes 时直接
    # 导出该快照，避免 AI Engine 重启或跨存储后找不到同名 generation 版本。
    if req.nodes:
        nodes = req.nodes
        selected_version = requested_version if requested_version > 0 else 1
    else:
        # 兼容旧调用：按 generation_id 从 AI Engine 版本存储加载。
        vm = get_version_manager()
        selected = vm.load_version(gen_id, requested_version) if requested_version > 0 else vm.load_version(gen_id)
        if not selected:
            raise HTTPException(status_code=404, detail="版本不存在")
        nodes = selected.nodes_snapshot
        selected_version = selected.version_number
    courseware_title = (req.courseware_title or "课件").strip() or "课件"

    # 创建导出任务
    job = ExportJob(
        job_id=job_id,
        generation_id=gen_id,
        format=req.format,
        version=selected_version,
        status=ExportStatus.PENDING,
        metadata={
            "courseware_title": courseware_title,
            "version": selected_version,
            "filename": _export_contract_filename(courseware_title, selected_version, req.format),
        },
        created_at=datetime.now(),
    )

    async with _export_lock:
        _export_tasks[job_id] = job

    # 教案导出（lesson_plan）需要意图摘要补充课时/授课对象等，从内存生成任务查找（找不到则 fallback 全靠节点）
    intent_dict = None
    with _gen_tasks_lock:
        for _task in _gen_tasks.values():
            if _task.generation_id == gen_id:
                intent_dict = (
                    _task.intent.model_dump()
                    if hasattr(_task.intent, "model_dump") else dict(_task.intent)
                )
                break

    # 后台执行导出
    asyncio.create_task(
        _run_export(
            job_id, nodes, req.format, intent=intent_dict,
            courseware_title=courseware_title, version=selected_version,
        )
    )

    return ExportStatusResponse(
        job_id=job_id,
        filename=job.metadata["filename"],
        status=ExportStatus.PENDING,
        download_url=None,
        error=None,
        courseware_title=courseware_title,
        version=selected_version,
        version_no=selected_version,
    )


async def _run_export(
    job_id: str, nodes: list[dict], fmt: ExportFormat, intent: dict | None = None,
    courseware_title: str = "课件", version: int = 1,
):
    """后台导出任务"""
    async with _export_lock:
        job = _export_tasks.get(job_id)
        if not job:
            return

    try:
        job.status = ExportStatus.EXPORTING

        course_name = courseware_title
        export_dir = Path("data/exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        job.metadata = job.metadata or {}
        job.metadata["courseware_title"] = course_name
        job.metadata["version"] = version

        # Word 标准教案（A12 赛题 4b）：LLM 生成 + 确定性 fallback，导出永不空。
        # 产物存 doc_path（.docx），复用既有上传/下载链路，无需改动 upload 循环。
        if fmt == ExportFormat.LESSON_PLAN:
            generator = LessonPlanGenerator()
            plan = await asyncio.to_thread(generator.generate, nodes, intent or {}, None)
            exporter = LessonPlanDOCExporter()
            buf = exporter.export_to_bytes(plan)
            doc_path = export_dir / f"{job_id}.docx"
            doc_path.write_bytes(buf.getvalue())
            job.metadata = job.metadata or {}
            job.metadata["doc_path"] = str(doc_path)
            job.metadata["lesson_plan_source"] = getattr(plan, "data_source", "unknown")
            job.file_size = doc_path.stat().st_size

        if fmt in (ExportFormat.BOTH, ExportFormat.PPTX):
            exporter = PPTExporter()
            buf = exporter.export_to_bytes(nodes, course_name)
            ppt_path = export_dir / f"{job_id}.pptx"
            ppt_path.write_bytes(buf.getvalue())
            job.metadata = job.metadata or {}
            job.metadata["ppt_path"] = str(ppt_path)
            job.file_size = ppt_path.stat().st_size

        if fmt in (ExportFormat.BOTH, ExportFormat.DOCX):
            exporter = DOCExporter()
            buf = exporter.export_to_bytes(nodes, course_name)
            doc_path = export_dir / f"{job_id}.docx"
            doc_path.write_bytes(buf.getvalue())
            job.metadata = job.metadata or {}
            job.metadata["doc_path"] = str(doc_path)
            job.file_size = doc_path.stat().st_size

        # HTML5 互动小游戏（A12 赛题 4c/5c）：both/interactive 模式下随 pptx/docx 一起产出
        if fmt in (ExportFormat.BOTH, ExportFormat.INTERACTIVE):
            html5 = export_interactive_html(
                nodes, course_name,
                output_dir=str(export_dir), file_name=f"{job_id}.html",
            )
            job.metadata = job.metadata or {}
            job.metadata["html_path"] = html5["path"]
            job.file_size = html5["file_size"]

        job.status = ExportStatus.DONE

        # 真实上传 MinIO（导出成功后尽力上传；失败降级为本地路径，任务仍为 done）。
        # 上传段独立捕获异常：任何上传问题都不能把已 DONE 的导出翻转为 FAILED。
        from ai_engine.gen.export_upload import upload_export_file

        try:
            meta = job.metadata or {}
            upload_results: list[dict] = []
            for key, ext in (("ppt_path", "pptx"), ("doc_path", "docx"), ("html_path", "html")):
                local_path = meta.get(key)
                if not local_path:
                    continue
                result = upload_export_file(
                    local_path, f"exports/{job_id}.{ext}",
                    bucket=None,  # bucket 默认值统一由 export_upload 解析（MINIO_BUCKET，默认 teaching）
                )
                upload_results.append(result.to_meta())
                if result.upload_status == "uploaded":
                    job.minio_path = result.minio_path
                else:
                    # 降级：保留本地路径，任务仍为 done，但记录失败原因
                    job.minio_path = local_path
                    job.error = (f"{job.error}; " if job.error else "") + result.reason

            if upload_results:
                meta["uploads"] = upload_results
                # 汇总状态：全部 uploaded 才是 uploaded，否则 failed/skipped
                statuses = {r["upload_status"] for r in upload_results}
                if statuses == {"uploaded"}:
                    meta["upload_status"] = "uploaded"
                    meta["upload_error"] = None
                else:
                    meta["upload_status"] = "failed" if "failed" in statuses else "skipped"
                    meta["upload_error"] = "; ".join(
                        r.get("upload_error") or "" for r in upload_results
                    ).strip(" ;") or None
                job.metadata = meta
        except Exception as upload_exc:
            # 上传辅助逻辑本身的意外错误也降级，不影响导出主流程
            job.metadata = job.metadata or {}
            job.metadata["upload_status"] = "failed"
            job.metadata["upload_error"] = f"上传模块异常: {upload_exc}"

        async with _export_lock:
            _export_tasks[job_id] = job

    except Exception as e:
        job.status = ExportStatus.FAILED
        job.error = str(e)
        async with _export_lock:
            _export_tasks[job_id] = job


@app.get("/api/v1/exp/status/{job_id}", response_model=ExportStatusResponse)
@app.get("/api/v1/export/status/{job_id}", response_model=ExportStatusResponse)
async def export_status(job_id: str):
    """
    GET /api/v1/export/status/{job_id} — 查询导出任务状态。

    对应 Go 端：ExportHandler.Status → AIEngine.ExportStatus
    """
    async with _export_lock:
        job = _export_tasks.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="导出任务不存在")

    download_url = None
    files: dict[str, str] = {}
    if job.status == ExportStatus.DONE:
        meta = job.metadata or {}
        if "ppt_path" in meta:
            files["pptx"] = f"/download/{job_id}.pptx"
        if "doc_path" in meta:
            files["docx"] = f"/download/{job_id}.docx"
        if "html_path" in meta:
            files["html"] = f"/download/{job_id}.html"
        download_url = next(iter(files.values()), None)

    meta = job.metadata or {}
    return ExportStatusResponse(
        job_id=job.job_id,
        filename=meta.get("filename") or _export_contract_filename(
            meta.get("courseware_title") or "课件", int(meta.get("version") or job.version or 1), job.format,
        ),
        status=job.status,
        download_url=download_url,
        error=job.error,
        upload_status=meta.get("upload_status"),
        minio_path=job.minio_path,
        file_size=job.file_size,
        courseware_title=meta.get("courseware_title") or "课件",
        version=int(meta.get("version") or job.version or 1),
        version_no=int(meta.get("version") or job.version or 1),
        files=files,
    )


@app.get("/download/{job_id}.{extension}")
async def export_download(job_id: str, extension: str):
    """下载已完成的 PPTX/DOCX/HTML5 导出文件。"""
    async with _export_lock:
        job = _export_tasks.get(job_id)

    if not job or job.status != ExportStatus.DONE:
        raise HTTPException(status_code=404, detail="导出文件不存在或任务尚未完成")

    key = {"pptx": "ppt_path", "docx": "doc_path", "html": "html_path"}.get(extension.lower())
    path = Path(job.metadata.get(key, "")) if key else None
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="请求的导出格式不存在")

    media_types = {
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "html": "text/html; charset=utf-8",
    }
    meta = job.metadata or {}
    title = str(meta.get("courseware_title") or "课件")
    safe_title = "".join("_" if ch in '\\/:*?\"<>|' else ch for ch in title).strip(" .") or "课件"
    version = int(meta.get("version") or job.version or 1)
    return FileResponse(
        path,
        media_type=media_types[extension.lower()],
        filename=f"{safe_title}_v{version}.{extension.lower()}",
    )


# =============================================================================
# 健康检查
# =============================================================================

@app.get("/health")
def health_check():
    """健康检查接口，供前端联调测试"""
    return {"status": "running", "version": "v1.0.0", "llm": _llm_health_payload()}


# =============================================================================
# Auth 端点（注册/登录，无 Go 后端时本地兜底）
# =============================================================================

import json as _json
import hashlib as _hashlib
_AUTH_FILE = CURRENT_DIR / "data" / "auth_users.json"

def _load_auth_users():
    if _AUTH_FILE.exists():
        try:
            return _json.loads(_AUTH_FILE.read_text())
        except Exception:
            return {}
    return {}

def _save_auth_users(users):
    _AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    _AUTH_FILE.write_text(_json.dumps(users, ensure_ascii=False, indent=2))

def _hash_pw(password: str) -> str:
    return _hashlib.sha256(password.encode()).hexdigest()

class AuthRegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "teacher"

class AuthLoginRequest(BaseModel):
    username: str
    password: str

class AuthResponse(BaseModel):
    code: int = 200
    message: str = "ok"
    data: Optional[dict] = None

@app.post("/api/v1/ai/parse_modify")
async def ai_parse_modify(req: ParseModifyRequest):
    """[B5] 修改意图理解与节点定位：自然语言 → 结构化修改操作。

    对应 Go 端：A6 modify 编排的第一步；低置信度返回 clarification_needed=true。
    """
    try:
        parser = get_modify_intent_parser()
        result = await asyncio.to_thread(parser.parse, req.instruction, req.nodes)
        return result
    except Exception as e:
        raise _llm_endpoint_error(e, "修改指令解析失败")


@app.post("/api/v1/auth/register")
def auth_register(req: AuthRegisterRequest):
    users = _load_auth_users()
    name = req.username.strip().lower()
    if name in users:
        return AuthResponse(code=400, message="账号已存在")
    users[name] = {
        "username": name,
        "password": _hash_pw(req.password),
        "role": req.role if req.role in ("teacher", "student") else "teacher"
    }
    _save_auth_users(users)
    return AuthResponse(code=200, message="注册成功", data={"username": name, "role": users[name]["role"]})

@app.post("/api/v1/auth/login")
def auth_login(req: AuthLoginRequest):
    users = _load_auth_users()
    name = req.username.strip().lower()
    user = users.get(name)
    if not user or user["password"] != _hash_pw(req.password):
        return AuthResponse(code=400, message="账号或密码错误")
    return AuthResponse(code=200, message="登录成功", data={"username": name, "role": user["role"]})


if __name__ == "__main__":
    import uvicorn
    # 为了演示，直接运行 main.py 启动
    uvicorn.run(app, host="0.0.0.0", port=8000)
