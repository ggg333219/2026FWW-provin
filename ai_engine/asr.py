"""服务端语音识别（ASR）模块 — 语音输入链路的服务端。

设计动机：Web Speech API 绑定 Chrome/Edge 且依赖 Google 识别服务（国内不可用），
改为前端 MediaRecorder 录音 → 上传本端点 → 服务端转写 → 返回文本。

Provider 链（按序尝试，首个可用者生效）：
  1. dashscope   — 配置了 DASHSCOPE_API_KEY / AI_API_KEY 时走阿里云 Paraformer
                   （短音频同步识别，与 LLM 共用同一把 key）
  2. local_whisper — 环境开启 ASR_ALLOW_LOCAL_WHISPER=1 且安装了 faster-whisper 时，
                   用本地模型转写（默认 tiny int8，CPU 可跑；模型经 HF_ENDPOINT 镜像下载）
  3. 未配置      — 返回 501 / ASR_NOT_CONFIGURED，前端展示明确提示

对外契约（供前端/网关消费）：
  transcribe_bytes(data, content_type, language) -> {text, provider, duration_ms}
"""

from __future__ import annotations

import io
import os
import threading
import time
from typing import Any, Optional

# 上传上限：60s 16kHz 单声道 opus 约 1-2MB，放宽到 20MB 兼容 wav/mp3
MAX_AUDIO_BYTES = 20 * 1024 * 1024

SUPPORTED_LANGUAGES = {"zh", "en", "zh-CN", "en-US"}


class ASRError(Exception):
    """带 error_code 的 ASR 业务异常，main.py 据此映射 HTTP 状态码。"""

    def __init__(self, error_code: str, message: str, status_code: int = 500):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _dashscope_api_key() -> str:
    return _env("DASHSCOPE_API_KEY") or _env("AI_API_KEY")


def local_whisper_enabled() -> bool:
    return _env("ASR_ALLOW_LOCAL_WHISPER") == "1"


def asr_provider_name() -> str:
    """当前生效（或优先）的 provider，用于 /health 展示。"""
    if _dashscope_api_key():
        return "dashscope"
    if local_whisper_enabled():
        return "local_whisper"
    return "none"


# ---------------------------------------------------------------------------
# Provider 1: DashScope Paraformer（短音频同步识别）
# ---------------------------------------------------------------------------

_DASHSCOPE_WEBM_NOTE = "dashscope 不支持 webm 容器时返回原错误，由调用方决定降级"


def _transcribe_dashscope(data: bytes, content_type: str, language: str) -> dict[str, Any]:
    api_key = _dashscope_api_key()
    if not api_key:
        raise ASRError("ASR_NOT_CONFIGURED", "未配置 DASHSCOPE_API_KEY", 501)
    try:
        import dashscope
        from dashscope.audio.asr import Recognition
    except Exception as exc:  # pragma: no cover - 可选依赖
        raise ASRError("ASR_PROVIDER_UNAVAILABLE", f"dashscope SDK 未安装: {exc}", 501) from exc

    dashscope.api_key = api_key
    # Recognition.call 仅接受文件路径/URL：写临时文件（保持常见扩展名便于 SDK 识别容器格式）
    ext = "wav"
    if "webm" in content_type:
        ext = "webm"
    elif "mp4" in content_type or "m4a" in content_type:
        ext = "m4a"
    elif "mpeg" in content_type or "mp3" in content_type:
        ext = "mp3"
    import tempfile

    started = time.monotonic()
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="asr_", suffix=f".{ext}", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        lang_code = "zh" if language.startswith("zh") else "en"
        response = Recognition.call(
            model="paraformer-realtime-v2",
            file_url=None,
            file=tmp_path,
            format=ext if ext != "m4a" else "mp4",
            sample_rate=16000,
            language_hints=[lang_code],
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if response is None or getattr(response, "status_code", 200) != 200:
        message = getattr(response, "message", "dashscope 识别失败") if response else "dashscope 无响应"
        raise ASRError("ASR_PROVIDER_FAILED", f"dashscope 识别失败: {message}", 502)

    sentences = getattr(response, "get_response", lambda: None)()
    text_parts: list[str] = []
    output = getattr(response, "output", None)
    if output:
        # Recognition 同步调用直接返回 sentence 列表
        for item in getattr(output, "sentence", None) or []:
            text = str(getattr(item, "text", "") or "").strip()
            if text:
                text_parts.append(text)
    text = "".join(text_parts).strip()
    if not text and sentences:
        text = str(sentences).strip()
    duration_ms = int((time.monotonic() - started) * 1000)
    return {"text": text, "provider": "dashscope", "duration_ms": duration_ms}


# ---------------------------------------------------------------------------
# Provider 2: 本地 faster-whisper（可选，懒加载单例）
# ---------------------------------------------------------------------------

_whisper_model: Optional[Any] = None
_whisper_lock = threading.Lock()
_whisper_model_name: str = ""


def _get_whisper_model() -> Any:
    global _whisper_model, _whisper_model_name
    if _whisper_model is not None:
        return _whisper_model
    with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise ASRError(
                "ASR_PROVIDER_UNAVAILABLE",
                f"faster-whisper 未安装（pip install faster-whisper）: {exc}",
                501,
            ) from exc
        model_name = _env("ASR_WHISPER_MODEL", "tiny")
        started = time.monotonic()
        # int8 + cpu：2GB 内存服务器可承受的最小组合；下载走 HF_ENDPOINT 镜像
        _whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
        _whisper_model_name = model_name
        print(f"[asr] faster-whisper 模型加载完成 model={model_name} "
              f"cost={time.monotonic() - started:.1f}s", flush=True)
        return _whisper_model


def _transcribe_local_whisper(data: bytes, content_type: str, language: str) -> dict[str, Any]:
    model = _get_whisper_model()
    ext = "webm"
    if content_type:
        if "wav" in content_type or "wave" in content_type:
            ext = "wav"
        elif "mpeg" in content_type or "mp3" in content_type:
            ext = "mp3"
        elif "ogg" in content_type:
            ext = "ogg"
        elif "mp4" in content_type or "m4a" in content_type:
            ext = "m4a"
    import tempfile

    started = time.monotonic()
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="asr_", suffix=f".{ext}", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        # initial_prompt 引导输出简体中文短句（tiny 模型中文易出繁体/英文漂移）
        initial_prompt = "以下是普通话的句子，请输出简体中文。" if language.startswith("zh") else None
        segments, info = model.transcribe(
            tmp_path,
            language="zh" if language.startswith("zh") else ("en" if language.startswith("en") else None),
            initial_prompt=initial_prompt,
            beam_size=1,
            vad_filter=True,
        )
        text = "".join(segment.text for segment in segments).strip()
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    duration_ms = int((time.monotonic() - started) * 1000)
    return {"text": text, "provider": f"local_whisper:{_whisper_model_name}", "duration_ms": duration_ms}


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------

def transcribe_bytes(data: bytes, content_type: str, language: str = "zh") -> dict[str, Any]:
    """音频字节 → 识别文本。供 main.py 的 HTTP 端点调用。"""
    if not data:
        raise ASRError("ASR_EMPTY_AUDIO", "音频内容为空", 400)
    if len(data) > MAX_AUDIO_BYTES:
        raise ASRError("ASR_AUDIO_TOO_LARGE", "音频超过 20MB 上限", 413)
    language = (language or "zh").strip() or "zh"
    if language not in SUPPORTED_LANGUAGES:
        language = "zh"

    errors: list[str] = []
    if _dashscope_api_key():
        try:
            return _transcribe_dashscope(data, content_type, language)
        except ASRError as exc:
            errors.append(f"dashscope: {exc.message}")
            # 云端失败不自动落到本地：云端可用说明本地未必要开；但若本地也开了则继续尝试
            if not local_whisper_enabled():
                raise
    if local_whisper_enabled():
        try:
            return _transcribe_local_whisper(data, content_type, language)
        except ASRError:
            raise
    raise ASRError(
        "ASR_NOT_CONFIGURED",
        "语音识别服务未配置：设置 DASHSCOPE_API_KEY（云端）或 ASR_ALLOW_LOCAL_WHISPER=1（本地模型）",
        501,
    )
