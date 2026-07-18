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

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

# 导入你之前写的 AI 核心逻辑
try:
    from .parser import DocumentParser
    from .generator import LessonGenerator, GenerationConfig
    from .qa import QAResponder, QAConfig, resolve_llm_base_url
    from .reconstructor import LessonReconstructor, ReconstructionConfig
    from .recommendation.service import router as recommendation_router
except ImportError:
    from parser import DocumentParser
    from generator import LessonGenerator, GenerationConfig
    from qa import QAResponder, QAConfig, resolve_llm_base_url
    from reconstructor import LessonReconstructor, ReconstructionConfig
    from recommendation.service import router as recommendation_router

app = FastAPI(title="泛雅 AI 智课系统后端", description="为前端提供解析、生成、问答、重讲等核心 AI 接口")
app.include_router(recommendation_router)

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


@app.get("/health")
def health_check():
    """健康检查接口，供前端联调测试"""
    return {"status": "running", "version": "v1.0.0", "llm": _llm_health_payload()}

if __name__ == "__main__":
    import uvicorn
    # 为了演示，直接运行 main.py 启动
    uvicorn.run(app, host="0.0.0.0", port=8000)
