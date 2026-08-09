from datetime import datetime
import sys
from fastapi import FastAPI, UploadFile, File, HTTPException
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
from ai_engine.reconstructor import LessonReconstructor, ReconstructionConfig
from ai_engine.recommendation.service import router as recommendation_router
from ai_engine.gen.outline import OutlineBuilder, OutlineConfig
from ai_engine.gen.node import NodeGenerator, NodeGenConfig
from ai_engine.gen.export_ppt import PPTExporter, ExportPPTConfig
from ai_engine.gen.export_doc import DOCExporter, ExportDocConfig
from ai_engine.gen.preview import PreviewRenderer
from ai_engine.gen.commands import CommandParser, EditCommand, CommandType
from ai_engine.gen.patch import NodePatcher
from ai_engine.gen.interactive import InteractiveBuilder
from ai_engine.intent.router import router as intent_router
from ai_engine.core.schema import (
    GenerationCreateRequest, GenerationCreateResponse,
    GenerationStatusResponse, GenerationStatus, GenerationStage,
    GenerationTask, ExportRequest, ExportFormat,
    ExportStatusResponse, ExportStatus, ExportJob,
    RollbackRequest,
)

app = FastAPI(title="泛雅 AI 智课系统后端", description="为前端提供解析、生成、问答、重讲等核心 AI 接口")
app.include_router(recommendation_router)
app.include_router(intent_router)

# ---- Phase 4: Skill 模块注册（新增，互不冲突） ----
from ai_engine.parse.router import router as parse_router
app.include_router(parse_router)

from ai_engine.rag.router import router as rag_router
app.include_router(rag_router)

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

# --- 核心接口实现 ---

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    1. 上传接口：接收 PDF/PPTX，并自动触发解析
    对应：智课生成模块 - 文档解析
    """
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
    """直接返回结构化解析结果，供 Go 后端上传后落库。"""
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
    """将解析后的页文本重构为章节与讲授节点。"""
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
    """
    2. 智课生成接口：获取生成的讲稿和思维导图
    对应：创新点1 (导图) & 智课生成模块 (脚本)
    """
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
    """
    3. 实时问答与案例重讲接口
    对应：创新点2 (溯源) & 创新点3 (重讲案例)
    """
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
    result = responder.answer(req.question, req.page)
    
    return result


@app.post("/generate-script")
async def generate_script(req: GenerateScriptRequest):
    """基于页内容直接生成讲稿与导图（供 Go 后端调用）。"""
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
        result = generator.generate(parsed_document)
        lesson = (result.get("lessons") or [{}])[0]
        return {
            "page": req.page,
            "script": lesson.get("script", ""),
            "mindmap_markdown": lesson.get("mindmap_markdown", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讲稿生成失败: {str(e)}")


@app.post("/generate-node-script")
async def generate_node_script(req: GenerateNodeScriptRequest):
    """基于讲授节点生成可交互讲稿。"""
    try:
        generator = LessonGenerator(GenerationConfig(mode=req.mode))
        return generator.generate_node_script(req.teaching_node, req.course_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"节点讲稿生成失败: {str(e)}")


@app.post("/generate-enhanced")
async def generate_enhanced(req: GenerateFromMarkdownRequest):
    """增强版三阶段生成：输出带 segment_type/estimated_seconds/interaction_hint/knowledge_card 的结构化脚本。"""
    try:
        generator = LessonGenerator(GenerationConfig(mode=req.mode))
        return generator.generate_from_markdown_enhanced(req.markdown, req.course_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"增强生成失败: {str(e)}")


@app.post("/generate-from-markdown")
async def generate_from_markdown(req: GenerateFromMarkdownRequest):
    """三阶段最小链路：Markdown -> 节点树(node_id) -> 节点讲稿(node_id)。"""
    try:
        generator = LessonGenerator(GenerationConfig(mode=req.mode))
        return generator.generate_from_markdown(req.markdown, req.course_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Markdown 三阶段生成失败: {str(e)}")


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
    client = OpenAI(api_key=api_key, base_url=base_url)

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
        return responder.answer(req.question, req.current_page, history_summary=req.history_summary, recent_turns=req.recent_turns)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"问答失败: {str(e)}")


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
    client = OpenAI(api_key=api_key, base_url=base_url)

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
        raise HTTPException(status_code=500, detail=f"知识点解析失败: {e}")


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
    """预览渲染请求"""
    nodes: list[dict[str, Any]]
    course_name: str = "课件预览"


class ModifyRequest(BaseModel):
    """修改命令请求"""
    nodes: list[dict[str, Any]]
    commands: list[dict[str, Any]]  # 结构化命令列表
    regenerate: bool = False
    course_name: str | None = None


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
            result = builder.build_from_markdown(req.markdown, req.course_name)
        else:
            result = builder.build(req.intent, req.evidence_packet)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"大纲构建失败: {str(e)}")


@app.post("/gen/nodes")
async def generate_nodes(req: GenNodesRequest):
    """[S3] 逐节点生成讲稿"""
    generator = NodeGenerator()
    try:
        if req.enhanced:
            result = generator.generate_enhanced(req.nodes, req.context_markdown, req.course_name)
        else:
            result = generator.generate_all(req.nodes, req.context_markdown, req.course_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"节点生成失败: {str(e)}")


@app.post("/gen/node/single")
async def generate_single_node(req: dict[str, Any]):
    """[S3] 单个节点重生成（供 S4 修补调用）"""
    node = req.get("node", {})
    course_name = req.get("course_name")
    generator = NodeGenerator()
    try:
        return generator.generate_single(node, course_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"单节点生成失败: {str(e)}")


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
        return {"items": builder.build_all(req.node)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"互动内容生成失败: {str(e)}")


# — S4 个性化满足接口 —

@app.post("/api/v1/gen/preview")
async def render_preview(req: PreviewRequest):
    """[S4] 预览渲染：节点树 → HTML"""
    renderer = PreviewRenderer()
    try:
        html_content = renderer.render(req.nodes, req.course_name)
        return {"html": html_content, "node_count": len(req.nodes)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览渲染失败: {str(e)}")


@app.post("/api/v1/gen/modify")
async def modify_nodes(req: ModifyRequest):
    """[S4] 修改命令：应用编辑命令到节点树"""
    parser = CommandParser()
    patcher = NodePatcher()

    # 解析命令
    parse_result = parser.parse(req.commands)
    if parse_result.errors:
        return {"status": "parse_error", "errors": parse_result.errors}

    # 验证命令
    valid_ids = {n["node_id"] for n in req.nodes}
    all_errors = []
    for cmd in parse_result.commands:
        errs = parser.validate(cmd, valid_ids)
        all_errors.extend(errs)
    if all_errors:
        return {"status": "validation_error", "errors": all_errors}

    # 执行修补
    generator = NodeGenerator(NodeGenConfig()) if req.regenerate else None
    regenerate_fn = (lambda nid, node: generator.generate_single(node, req.course_name)) if generator else None
    result = patcher.apply(req.nodes, parse_result.commands, regenerate_fn)

    return {
        "status": "ok" if not result.errors else "partial_error",
        "nodes": result.nodes,
        "changes": result.changes,
        "errors": result.errors,
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
        outline = builder.build_from_markdown(markdown, course_name)

        # 2. 节点讲稿
        generator = NodeGenerator()
        scripts = generator.generate_all(outline["nodes"], markdown, course_name)

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
        raise HTTPException(status_code=500, detail=f"全流程失败: {str(e)}")


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
        return {"current_version": new_ver.version_number, "status": "done"}
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

# 进程内生成任务存储（生产环境用 Redis/DB）
_gen_tasks: dict[str, GenerationTask] = {}
_gen_tasks_lock = asyncio.Lock()


@app.post("/api/v1/gen/create", response_model=GenerationCreateResponse)
async def gen_create(req: GenerationCreateRequest):
    """
    POST /api/v1/gen/create — 创建生成任务，执行 outline → nodes 全流程。

    对应 Go 端：GenerationHandler.Create → AIEngine.GenerationCreate
    """
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
        status=GenerationStatus.PENDING,
        stage=GenerationStage.INTENT_LOCKED,
        progress_pct=0.0,
        intent=intent,
        evidence=req.evidence_packet,
        template_id=req.template_id,
        nodes=[],
        created_at=datetime.now(),
    )

    async with _gen_tasks_lock:
        _gen_tasks[task_id] = task

    # 后台执行生成管道
    asyncio.create_task(_run_generation_pipeline(task_id, req))

    return GenerationCreateResponse(
        task_id=task_id,
        generation_id=gen_id,
        status=GenerationStatus.PENDING,
        generation_type="ppt" if not req.intent.output_format else (req.intent.output_format[0] if req.intent.output_format else "ppt"),
    )


async def _run_generation_pipeline(task_id: str, req: GenerationCreateRequest):
    """后台生成管道：outline → nodes → 保存版本快照"""
    async with _gen_tasks_lock:
        task = _gen_tasks.get(task_id)
        if not task:
            return

    try:
        # Stage 1: 意图锁定
        task.status = GenerationStatus.GENERATING
        task.stage = GenerationStage.INTENT_LOCKED
        task.progress_pct = 10.0

        # Stage 2: 收集证据（如有）
        task.stage = GenerationStage.EVIDENCE_GATHERING
        task.progress_pct = 20.0

        # Stage 3: 构建大纲
        task.stage = GenerationStage.STRUCTURING
        task.progress_pct = 30.0
        builder = OutlineBuilder()
        if req.evidence_packet:
            intent_dict = req.intent.model_dump() if hasattr(req.intent, "model_dump") else req.intent
            evidence_dict = req.evidence_packet.model_dump() if hasattr(req.evidence_packet, "model_dump") else req.evidence_packet
            outline = builder.build(intent_dict, evidence_dict)
        else:
            intent_dict = req.intent.model_dump() if hasattr(req.intent, "model_dump") else req.intent
            outline = builder.build(intent_dict, None)
        nodes = outline.get("nodes", [])
        task.nodes = nodes
        task.progress_pct = 50.0

        # Stage 4: 逐节点生成
        task.stage = GenerationStage.GENERATING
        generator = NodeGenerator()
        course_name = req.intent.topic or "课件"
        scripts = generator.generate_all(nodes, "", course_name)
        task.progress_pct = 80.0

        # 合并节点
        merged_nodes = []
        for node in nodes:
            script_data = next(
                (s for s in scripts.get("scripts", []) if s.get("node_id") == node.get("node_id")),
                {"script": "", "segments": []},
            )
            merged = {**node}
            if isinstance(script_data, dict):
                merged["script"] = script_data.get("script", "")
                merged["segments"] = script_data.get("segments", [])
            merged_nodes.append(merged)
        task.nodes = merged_nodes

        # Stage 5: 保存版本快照
        task.stage = GenerationStage.PREVIEW
        task.progress_pct = 90.0
        vm = get_version_manager()
        vm.save_snapshot(
            generation_id=task.generation_id,
            nodes=merged_nodes,
            summary="初稿",
        )

        # 完成
        task.status = GenerationStatus.DONE
        task.stage = GenerationStage.DONE
        task.progress_pct = 100.0

        async with _gen_tasks_lock:
            _gen_tasks[task_id] = task

    except Exception as e:
        task.status = GenerationStatus.FAILED
        task.error = str(e)
        async with _gen_tasks_lock:
            _gen_tasks[task_id] = task


@app.get("/api/v1/gen/status/{task_id}", response_model=GenerationStatusResponse)
async def gen_status(task_id: str):
    """
    GET /api/v1/gen/status/{task_id} — 查询生成任务状态。

    对应 Go 端：GenerationHandler.Status → AIEngine.GenerationStatus
    """
    async with _gen_tasks_lock:
        task = _gen_tasks.get(task_id)

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


# =============================================================================
# S4 异步导出端点（对齐 Go ExportHandler → AIEngine）
# =============================================================================

from ai_engine.gen.export_ppt import PPTExporter, ExportPPTConfig
from ai_engine.gen.export_doc import DOCExporter, ExportDocConfig

# 进程内导出任务存储
_export_tasks: dict[str, ExportJob] = {}
_export_lock = asyncio.Lock()


@app.post("/api/v1/export/{gen_id}", response_model=ExportStatusResponse)
async def export_create(gen_id: str, req: ExportRequest):
    """
    POST /api/v1/export/{gen_id} — 创建异步导出任务。

    对应 Go 端：ExportHandler.Create → AIEngine.ExportCreate
    """
    job_id = f"exp_{uuid.uuid4().hex[:12]}"

    # 获取最新版本节点
    vm = get_version_manager()
    latest = vm.load_version(gen_id)
    if not latest:
        raise HTTPException(status_code=404, detail="版本不存在")
    nodes = latest.nodes_snapshot

    # 创建导出任务
    job = ExportJob(
        job_id=job_id,
        generation_id=gen_id,
        format=req.format,
        version=req.version or latest.version_number,
        status=ExportStatus.PENDING,
        created_at=datetime.now(),
    )

    async with _export_lock:
        _export_tasks[job_id] = job

    # 后台执行导出
    asyncio.create_task(_run_export(job_id, nodes, req.format))

    return ExportStatusResponse(
        job_id=job_id,
        status=ExportStatus.PENDING,
        download_url=None,
        error=None,
    )


async def _run_export(job_id: str, nodes: list[dict], fmt: ExportFormat):
    """后台导出任务"""
    async with _export_lock:
        job = _export_tasks.get(job_id)
        if not job:
            return

    try:
        job.status = ExportStatus.EXPORTING

        course_name = "课件"
        export_dir = Path("data/exports")
        export_dir.mkdir(parents=True, exist_ok=True)

        if fmt in (ExportFormat.BOTH, ExportFormat.PPTX):
            exporter = PPTExporter()
            buf = exporter.export_to_bytes(nodes, course_name)
            ppt_path = export_dir / f"{job_id}.pptx"
            ppt_path.write_bytes(buf.getvalue())
            job.metadata = job.metadata or {}
            job.metadata["ppt_path"] = str(ppt_path)

        if fmt in (ExportFormat.BOTH, ExportFormat.DOCX):
            exporter = DOCExporter()
            buf = exporter.export_to_bytes(nodes, course_name)
            doc_path = export_dir / f"{job_id}.docx"
            doc_path.write_bytes(buf.getvalue())
            job.metadata = job.metadata or {}
            job.metadata["doc_path"] = str(doc_path)

        job.status = ExportStatus.DONE
        job.minio_path = str(export_dir / job_id)

        async with _export_lock:
            _export_tasks[job_id] = job

    except Exception as e:
        job.status = ExportStatus.FAILED
        job.error = str(e)
        async with _export_lock:
            _export_tasks[job_id] = job


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
    if job.status == ExportStatus.DONE:
        meta = job.metadata or {}
        if "ppt_path" in meta:
            download_url = f"/download/{job_id}.pptx"
        elif "doc_path" in meta:
            download_url = f"/download/{job_id}.docx"

    return ExportStatusResponse(
        job_id=job.job_id,
        status=job.status,
        download_url=download_url,
        error=job.error,
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
