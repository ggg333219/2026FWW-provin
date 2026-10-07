"""
应用统一配置 (core/config.py)

所有 Skill 模块从这里读取配置，而非直接从 os.getenv 读取。
现有代码 (qa.py, generator.py) 继续使用自己的 QAConfig/GenerationConfig，
新 Skill 代码使用 settings 单例。

使用方式：
    from ai_engine.core import settings
    settings.MODEL        # "qwen-turbo"
    settings.TEMPERATURE  # 0.2
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 加载 .env：优先从 workspace 根目录加载，回退为 CWD
_dotenv_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _dotenv_path.exists():
    load_dotenv(dotenv_path=str(_dotenv_path))
else:
    load_dotenv()

# ---- 环境变量键名常量 ----
_KEY_API_KEY = "AI_API_KEY"
_KEY_BASE_URL = "AI_BASE_URL"
_KEY_MODEL = "AI_MODEL"
_KEY_TEMPERATURE = "AI_TEMPERATURE"
_KEY_MODE = "AI_GEN_MODE"
_KEY_MAX_CONTENT_CHARS = "AI_MAX_CONTENT_CHARS"
_KEY_EMBEDDING_MODEL = "AI_EMBEDDING_MODEL"
_KEY_EMBEDDING_DIM = "AI_EMBEDDING_DIM"
_KEY_LLM_TIMEOUT = "LLM_TIMEOUT_SECONDS"
_KEY_LLM_GEN_CHUNK_SIZE = "LLM_GEN_CHUNK_SIZE"
_KEY_LLM_GEN_MAX_WORKERS = "LLM_GEN_MAX_WORKERS"

# ---- 默认值 ----
_DEFAULT_MODEL = "qwen-turbo"
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_MODE = "llm"
_DEFAULT_MAX_CONTENT_CHARS = 3500
# H1 三层超时统一：单次 LLM 调用 60s，重试 1 次（见 core/llm.py），
# 最坏 60s×2+退避 < Go 网关 90s / 前端 90s，保证重试周期不被上层切断。
_DEFAULT_LLM_TIMEOUT = 60
# Stage3 讲稿分块并行：每块节点数 / 最大并行 worker 数
# 提速改造（S3 一分钟量级）：默认每块 1 个节点（每节点独立 LLM 调用，粒度最细、
# 失败影响面最小），并行 worker 提到 4。均可通过环境变量覆盖。
_DEFAULT_LLM_GEN_CHUNK_SIZE = 1
_DEFAULT_LLM_GEN_MAX_WORKERS = 4
_DEFAULT_EMBEDDING_MODEL = "text-embedding-v3"
_DEFAULT_EMBEDDING_DIM = 1024


def _get_env_str(key: str, default: str) -> str:
    return (os.getenv(key) or "").strip() or default


def _get_env_float(key: str, default: float) -> float:
    try:
        val = float(os.getenv(key, ""))
        return val
    except (TypeError, ValueError):
        return default


def _get_env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, ""))
    except (TypeError, ValueError):
        return default


def resolve_llm_gen_chunk_size() -> int:
    """Stage3 讲稿生成：每块包含的节点数（env LLM_GEN_CHUNK_SIZE，非法值/小于1回退默认 1）。"""
    val = _get_env_int(_KEY_LLM_GEN_CHUNK_SIZE, _DEFAULT_LLM_GEN_CHUNK_SIZE)
    return val if val >= 1 else _DEFAULT_LLM_GEN_CHUNK_SIZE


def resolve_llm_gen_max_workers() -> int:
    """Stage3 讲稿生成：并行 LLM 调用的最大 worker 数（env LLM_GEN_MAX_WORKERS，非法值/小于1回退默认 4）。"""
    val = _get_env_int(_KEY_LLM_GEN_MAX_WORKERS, _DEFAULT_LLM_GEN_MAX_WORKERS)
    return val if val >= 1 else _DEFAULT_LLM_GEN_MAX_WORKERS


@dataclass(frozen=True)
class Settings:
    """
    全局配置单例，不可变。

    ⚠️ 新增配置项时，在此添加字段，并在 _build 中补充映射。
    """

    # ---- LLM ----
    API_KEY: str = ""
    BASE_URL: str = ""
    MODEL: str = _DEFAULT_MODEL
    TEMPERATURE: float = _DEFAULT_TEMPERATURE

    # ---- 生成模式 ----
    GEN_MODE: str = _DEFAULT_MODE
    MAX_CONTENT_CHARS: int = _DEFAULT_MAX_CONTENT_CHARS

    # ---- LLM 调用超时（秒）----
    LLM_TIMEOUT: int = _DEFAULT_LLM_TIMEOUT

    # ---- Stage3 讲稿分块并行 ----
    LLM_GEN_CHUNK_SIZE: int = _DEFAULT_LLM_GEN_CHUNK_SIZE
    LLM_GEN_MAX_WORKERS: int = _DEFAULT_LLM_GEN_MAX_WORKERS

    # ---- 嵌入 / RAG ----
    EMBEDDING_MODEL: str = _DEFAULT_EMBEDDING_MODEL
    EMBEDDING_DIM: int = _DEFAULT_EMBEDDING_DIM

    # ---- 路径 ----
    PROJECT_ROOT: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)
    UPLOAD_DIR: Path = field(default_factory=lambda: Path("uploads"))
    AUDIO_DIR: Path = field(default_factory=lambda: Path("uploads") / "generated_audio")

    # ---- API ----
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True

    @property
    def is_mock(self) -> bool:
        """是否使用 mock 模式（不调用真实 LLM）。"""
        return self.GEN_MODE.strip().lower() == "mock"


def _build_settings() -> Settings:
    return Settings(
        API_KEY=_get_env_str(_KEY_API_KEY, ""),
        BASE_URL=_get_env_str(_KEY_BASE_URL, ""),
        MODEL=_get_env_str(_KEY_MODEL, _DEFAULT_MODEL),
        TEMPERATURE=_get_env_float(_KEY_TEMPERATURE, _DEFAULT_TEMPERATURE),
        GEN_MODE=_get_env_str(_KEY_MODE, _DEFAULT_MODE),
        MAX_CONTENT_CHARS=_get_env_int(_KEY_MAX_CONTENT_CHARS, _DEFAULT_MAX_CONTENT_CHARS),
        LLM_TIMEOUT=_get_env_int(_KEY_LLM_TIMEOUT, _DEFAULT_LLM_TIMEOUT),
        LLM_GEN_CHUNK_SIZE=resolve_llm_gen_chunk_size(),
        LLM_GEN_MAX_WORKERS=resolve_llm_gen_max_workers(),
        EMBEDDING_MODEL=_get_env_str(_KEY_EMBEDDING_MODEL, _DEFAULT_EMBEDDING_MODEL),
        EMBEDDING_DIM=_get_env_int(_KEY_EMBEDDING_DIM, _DEFAULT_EMBEDDING_DIM),
        HOST=_get_env_str("HOST", "0.0.0.0"),
        PORT=_get_env_int("PORT", 8000),
        RELOAD=_get_env_str("RELOAD", "true").lower() in ("true", "1", "yes"),
    )


# ---- 全局单例 ----
settings = _build_settings()