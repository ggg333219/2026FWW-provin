"""
统一 LLM 客户端 (core/llm.py)

封装 OpenAI 兼容客户端初始化和调用，供所有 Skill 模块使用。

使用方式：
    from ai_engine.core import LLMClient

    client = LLMClient(model="deepseek-v4-flash-0731", temperature=0.1)
    response = client.chat("你是助教", "帮我写大纲")
    # -> "好的，以下是大纲..."

    # JSON 模式（强制结构化输出）
    result = client.chat_json(
        system="你是一个意图提取器，输出 JSON",
        user="用户说了...",
        schema={...}  # OpenAI response_format 的 schema
    )
    # -> {"topic": "排序算法", ...}

    # 流式输出（用于 SSE 推送）
    for token in client.chat_stream("你是助教", "帮我写大纲"):
        print(token, end="")
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Generator, Optional
from urllib.parse import urlparse

from .config import settings

logger = logging.getLogger(__name__)

# ---- 常量 ----

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_COMPAT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 超时/连接类异常的自动重试参数（默认值；可用环境变量覆盖，见下方 resolve_* 函数）：
#   LLM_RETRY_MAX_ATTEMPTS     总尝试次数上限，默认 2（首次 + 1 次重试）
#   LLM_RETRY_BACKOFF_SECONDS  重试退避秒数，逗号分隔，默认 "2,4"（2s→4s）
# 单次调用最坏耗时 ≈ max_attempts × timeout + sum(backoff)；批量降级路径
# （node.py 逐节点 generate_single）应传 max_attempts=1 收紧，避免 N×(timeout+退避) 放大。
LLM_RETRY_MAX_ATTEMPTS = 2
LLM_RETRY_BACKOFF_SECONDS = (2.0, 4.0)


def resolve_llm_retry_max_attempts() -> int:
    """解析重试总尝试次数上限：环境变量 LLM_RETRY_MAX_ATTEMPTS 优先，非法值回退默认 2。"""
    raw = (os.getenv("LLM_RETRY_MAX_ATTEMPTS") or "").strip()
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return LLM_RETRY_MAX_ATTEMPTS


def resolve_llm_retry_backoff_seconds() -> tuple[float, ...]:
    """解析重试退避秒数序列：环境变量 LLM_RETRY_BACKOFF_SECONDS（逗号分隔）优先，非法值回退默认 (2.0, 4.0)。"""
    raw = (os.getenv("LLM_RETRY_BACKOFF_SECONDS") or "").strip()
    if raw:
        try:
            parts = tuple(float(p.strip()) for p in raw.split(",") if p.strip())
            if parts:
                return parts
        except ValueError:
            pass
    return LLM_RETRY_BACKOFF_SECONDS


def resolve_llm_timeout() -> int:
    """
    解析 LLM 调用超时秒数。

    优先读环境变量 LLM_TIMEOUT_SECONDS（运行时可改，便于测试/压测），
    未设置或非法时回退 settings.LLM_TIMEOUT（同样来自该变量，默认 60）。

    供 core.LLMClient 及 legacy 直连 OpenAI() 的模块（qa.py/parser.py/
    generator.py/main.py）统一使用，保证超时保护口径一致。
    """
    raw = (os.getenv("LLM_TIMEOUT_SECONDS") or "").strip()
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return settings.LLM_TIMEOUT


def _is_retryable_error(e: BaseException) -> bool:
    """
    判断是否为超时/连接类异常（可安全重试）。

    覆盖：
      - 内置 TimeoutError / socket.timeout（3.10+ 归一为 TimeoutError）
      - openai.APITimeoutError / openai.APIConnectionError（按类名匹配）
      - httpx.TimeoutException 等类名含 timeout/connection 的异常
    业务类错误（如 RateLimitError 429、AuthenticationError 401）不在重试范围。
    """
    if isinstance(e, TimeoutError):
        return True
    name = type(e).__name__.lower()
    if "timeout" in name or "connection" in name:
        return True
    msg = str(e).lower()
    return any(
        marker in msg
        for marker in ("timed out", "timeout", "connection error", "connection refused", "connection reset")
    )


# ---- 公共工具函数（从 qa.py 提取，保持签名兼容） ----

def resolve_llm_base_url(model: str) -> tuple[str, str]:
    """
    确定 LLM API base URL。

    返回 (base_url, reason):
      - base_url: 实际的 API 端点
      - reason: 为空表示正常，非空表示 fallback 原因（用于日志/调试）

    与旧版 qa.resolve_llm_base_url 签名和返回值完全兼容。
    """
    raw_base_url = (os.getenv("AI_BASE_URL") or "").strip()
    if raw_base_url:
        parsed = urlparse(raw_base_url)
        host = (parsed.netloc or parsed.path).lower()
        if "example.com" not in host:
            return raw_base_url, ""
        reason = "placeholder_base_url"
    else:
        reason = ""

    if (model or "").strip().lower().startswith("gpt-"):
        return DEFAULT_OPENAI_BASE_URL, reason
    return DEFAULT_COMPAT_BASE_URL, reason


def extract_json(text: str) -> Any:
    """
    从 LLM 返回文本中提取并解析 JSON。

    处理 ```json ... ``` 包裹、前后空白、多段文本含多个 JSON 等情况。
    与旧版 QAResponder._extract_json 兼容，增强为独立函数。

    同时容忍根节点为数组：chat_with_schema 降级链的②③级（json_object /
    纯 prompt 约束）不强制根为 object，模型可能直接返回裸数组
    （如 nodes / scripts 列表）。旧实现只找 {} 区间，裸数组会直接抛
    ValueError，导致三级降级链全部失败——即使每级其实都拿到了可用内容。
    根形状按最先出现的括号判定，解析失败再退回另一种，保持原有
    “优先取 {}” 的行为不变。
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).replace("json", "", 1).strip()

    first_obj, first_arr = cleaned.find("{"), cleaned.find("[")
    if first_arr != -1 and (first_obj == -1 or first_arr < first_obj):
        candidates = (("[", "]"), ("{", "}"))
    else:
        candidates = (("{", "}"), ("[", "]"))

    for open_ch, close_ch in candidates:
        start, end = cleaned.find(open_ch), cleaned.rfind(close_ch)
        if start == -1 or end <= start:
            continue
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            continue

    raise ValueError(f"模型返回内容中未找到有效 JSON: {text[:200]}")


# ---- LLM 客户端 ----

@dataclass
class LLMResponse:
    """LLM 调用的统一返回结构。"""
    content: str
    model: str
    usage: Optional[dict[str, int]] = None
    used_fallback: bool = False
    fallback_reason: str = ""


class LLMClient:
    """
    统一的 LLM 调用客户端。

    封装 OpenAI 兼容客户端，提供 chat / chat_json 两种调用方式，
    自动处理 API key 获取、base URL 解析、超时、JSON 提取与回退。
    """

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_attempts: Optional[int] = None,
        disable_sdk_retries: bool = False,
        stop_schema_fallback_on_error: bool = False,
    ):
        self.model = model or settings.MODEL
        self.temperature = temperature if temperature is not None else settings.TEMPERATURE
        # 超时保护：显式传入优先（如 video_processor 的 300s），
        # 否则取 LLM_TIMEOUT_SECONDS / 默认 60
        self.timeout = int(timeout) if timeout else resolve_llm_timeout()
        # 重试收紧：显式传入 max_attempts（如批量降级路径传 1 = 不重试）优先，
        # None 时每次调用按 LLM_RETRY_MAX_ATTEMPTS 环境变量 / 默认 2 解析
        self.max_attempts = int(max_attempts) if max_attempts and int(max_attempts) > 0 else None
        self.disable_sdk_retries = disable_sdk_retries
        self.stop_schema_fallback_on_error = stop_schema_fallback_on_error
        self._api_key = api_key
        self._base_url = base_url

    # ---- 属性（懒解析） ----

    @property
    def api_key(self) -> str:
        key = self._api_key or settings.API_KEY or (os.getenv("AI_API_KEY") or "")
        return key.strip()

    @property
    def base_url(self) -> str:
        if self._base_url:
            return self._base_url
        url, _ = resolve_llm_base_url(self.model)
        return url

    # ---- 核心调用 ----

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        """
        普通文本聊天调用。

        Args:
            system: 系统提示词
            user: 用户消息
            temperature: 覆盖默认温度
            model: 覆盖默认模型

        Returns:
            LLMResponse 包含 content
        """
        return self._call(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            model=model,
        )

    def chat_stream(
        self,
        system: str,
        user: str,
        *,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """
        流式文本聊天调用，逐 token yield。

        用于 SSE 流式推送场景（如意图提取进度展示）。

        Args:
            system: 系统提示词
            user: 用户消息
            temperature: 覆盖默认温度
            model: 覆盖默认模型

        Yields:
            str: 每个增量文本 token
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        # Mock 模式或缺少 API key → 回退为非流式 mock 输出（按字符拆分）
        if settings.is_mock or not self.api_key:
            fallback = self._mock_response(messages)
            # 按合理块模拟流式输出
            chunk_size = max(1, len(fallback) // 20)
            for i in range(0, len(fallback), chunk_size):
                yield fallback[i:i + chunk_size]
            return

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )

            actual_model = model or self.model
            actual_temperature = temperature if temperature is not None else self.temperature

            stream = client.chat.completions.create(
                model=actual_model,
                messages=messages,
                temperature=actual_temperature,
                stream=True,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content

        except Exception:
            # 流式失败 → 回退为非流式
            fallback = self._fallback_text(messages)
            yield fallback

    def chat_json(
        self,
        system: str,
        user: str,
        schema: Optional[dict[str, Any]] = None,
        *,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        JSON 模式调用，返回解析后的字典。

        Args:
            system: 系统提示词
            user: 用户消息
            schema: OpenAI response_format 的 schema（strict=True 时需提供）
            temperature: 覆盖默认温度
            model: 覆盖默认模型

        Returns:
            解析后的 JSON 字典
        """
        kwargs: dict[str, Any] = {}
        if schema:
            kwargs["response_format"] = {"type": "json_object"}
            # 如果 schema 中包含 "name" 和 "strict"，构造 structured output 格式
            if "name" in schema or "strict" in schema:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": schema,
                }

        response = self._call(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature or 0.1,
            model=model,
            **kwargs,
        )

        if response.used_fallback:
            # 回退模式下尝试从文本提取 JSON
            try:
                return extract_json(response.content)
            except (ValueError, json.JSONDecodeError):
                return {"error": response.fallback_reason, "_raw": response.content[:500]}

        try:
            return json.loads(response.content)
        except (json.JSONDecodeError, TypeError):
            try:
                return extract_json(response.content)
            except (ValueError, json.JSONDecodeError):
                return {"error": "json_parse_failed", "_raw": response.content[:500]}

    def chat_with_schema(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> Any:
        """
        带 JSON Schema 的结构化输出调用（显式版本，带三级降级链）。

        背景：严格 response_format=json_schema 在部分 OpenAI 兼容网关上不稳定
        （400 / 空 content / 偶发失败），一旦失败整段调用就退回兜底内容，造成质量塌方。

        降级链（每级失败自动进入下一级，全部失败才抛 RuntimeError，由调用方走 fallback）：
          ① json_schema 严格模式（response_format=json_schema，原 system prompt）
          ② response_format=json_object + 把 schema 融合进 system prompt
          ③ 纯 prompt 约束（无 response_format，schema 融合进 system prompt）

        与 _call 重试的关系：降级链位于 _call 之上，每级仅发起一次 _call；
        _call 内部对超时/连接类异常的重试沿用既有策略（max_attempts + 退避），
        降级链本身不追加任何重试。降级只发生在「该级最终失败（重试耗尽 /
        不可重试错误如 400）或返回内容解析失败」之后，切换的是不同请求形态，
        因此不存在同一请求形态的重复重试套娃。

        Mock 模式 / 缺少 API key：保持旧行为（解析 mock 内容返回 dict，不抛异常），
        保证离线演示与既有测试不受影响。

        Args:
            system: 系统提示词
            user: 用户消息
            schema: OpenAI json_schema 格式的定义（需含 name 字段才触发 structured output）
            temperature: 覆盖默认温度
            model: 覆盖默认模型

        Returns:
            解析后的 JSON 字典

        Raises:
            RuntimeError: 三级降级链全部失败时抛出（调用方应捕获并走 fallback）。
        """
        # Mock 模式 / 缺少 key：与旧 chat_json 行为一致，不进入降级链
        if settings.is_mock or not self.api_key:
            return self.chat_json(
                system=system,
                user=user,
                schema=schema,
                temperature=temperature,
                model=model,
            )

        schema_text = json.dumps(schema, ensure_ascii=False)
        fused_system = (
            f"{system}\n\n"
            "【输出格式强制要求】请输出一个且仅一个 JSON 对象，严格符合以下 JSON Schema"
            "（不得输出 schema 之外的字段，不要输出解释性文字或 Markdown 代码块标记）：\n"
            f"{schema_text}"
        )

        # (级别名, 额外 kwargs, 该级使用的 system prompt)
        levels: list[tuple[str, dict[str, Any], str]] = [
            ("json_schema_strict", {"response_format": {"type": "json_schema", "json_schema": schema}}, system),
            ("json_object_plus_schema_prompt", {"response_format": {"type": "json_object"}}, fused_system),
            ("pure_prompt_constraint", {}, fused_system),
        ]

        failures: list[str] = []
        for level_name, extra_kwargs, level_system in levels:
            try:
                response = self._call(
                    messages=[
                        {"role": "system", "content": level_system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature or 0.1,
                    model=model,
                    **extra_kwargs,
                )
            except Exception as exc:  # _call 理论上不抛异常，此处为防御性兜底
                failures.append(f"{level_name}: {exc}")
                logger.warning(
                    "[chat_with_schema] 级别 %s 调用异常，降级到下一级: %s", level_name, exc,
                )
                if self.stop_schema_fallback_on_error:
                    break
                continue

            if response.used_fallback:
                # _call 重试耗尽或遇到不可重试错误（如 400）→ 该级失败，降级
                failures.append(f"{level_name}: {response.fallback_reason or 'used_fallback'}")
                logger.warning(
                    "[chat_with_schema] 级别 %s 请求失败（重试耗尽或不可重试错误），降级到下一级: %s",
                    level_name, response.fallback_reason,
                )
                # A different JSON encoding cannot repair a slow or unavailable
                # provider. Stop the format fallback chain and let the caller use
                # its deterministic fallback instead of repeating long requests.
                if self.stop_schema_fallback_on_error:
                    break
                continue

            try:
                try:
                    return json.loads(response.content)
                except (json.JSONDecodeError, TypeError):
                    return extract_json(response.content)
            except (ValueError, json.JSONDecodeError) as exc:
                failures.append(f"{level_name}: json_parse_failed({exc})")
                logger.warning(
                    "[chat_with_schema] 级别 %s 返回内容无法解析为 JSON，降级到下一级", level_name,
                )
                if self.stop_schema_fallback_on_error:
                    break

        raise RuntimeError(
            "chat_with_schema 三级降级链全部失败: " + " | ".join(failures)
        )

    def chat_messages(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        """
        自定义消息列表调用（多轮对话等复杂场景）。

        Args:
            messages: 完整消息列表 [{"role": "...", "content": "..."}, ...]
            temperature: 覆盖默认温度
            model: 覆盖默认模型
        """
        return self._call(messages=messages, temperature=temperature, model=model)

    def embed(
        self,
        texts: list[str],
        *,
        model: Optional[str] = None,
        dim: Optional[int] = None,
    ) -> list[list[float]]:
        """
        Embedding 向量化调用。

        用于 KB 知识库 RAG 的文本向量化。
        调用 OpenAI 兼容的 Embedding API。

        Args:
            texts: 待向量化的文本列表。
            model: 嵌入模型名（默认从 AI_EMBEDDING_MODEL 环境变量读取）。
            dim: 向量维度。

        Returns:
            等长的 list[list[float]]。
        """
        import os
        import logging
        logger = logging.getLogger(__name__)
        embedding_model = model or (os.getenv("AI_EMBEDDING_MODEL") or "local-bge-small-zh").strip()
        default_dim = 512
        try:
            default_dim = int(os.getenv("AI_EMBEDDING_DIM", "512"))
        except (TypeError, ValueError):
            pass
        embedding_dim = dim or default_dim

        if not texts:
            return []

        if settings.is_mock:
            return [[0.0] * embedding_dim for _ in range(len(texts))]

        global _local_embedder
        try:
            if '_local_embedder' not in globals():
                from sentence_transformers import SentenceTransformer
                logger.info("加载本地嵌入模型 BGE-small-zh...")
                _local_embedder = SentenceTransformer("BAAI/bge-small-zh-v1.5", device="cpu")
                logger.info("本地嵌入模型加载完成")
            vecs = _local_embedder.encode(texts, normalize_embeddings=True)
            return [list(v) for v in vecs]
        except Exception as e:
            logger.error(f"本地嵌入失败: {e}")
            return [[0.0] * embedding_dim for _ in range(len(texts))]

    # ---- 内部实现 ----

    def _post_chat_completions(
        self,
        messages: list[dict[str, str]],
        actual_model: str,
        actual_temperature: float,
        **kwargs: Any,
    ) -> Any:
        """发起一次 OpenAI 兼容 chat.completions 调用（带超时保护）。

        独立成方法便于测试时 monkeypatch（离线验证超时重试逻辑）。
        """
        from openai import OpenAI

        client_options = {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "timeout": self.timeout,
        }
        if self.disable_sdk_retries:
            client_options["max_retries"] = 0
        client = OpenAI(**client_options)
        return client.chat.completions.create(
            model=actual_model,
            messages=messages,
            temperature=actual_temperature,
            **kwargs,
        )

    def _call(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """底层 LLM 调用，处理统一异常、超时重试、回退和日志。"""
        # Mock 模式
        if settings.is_mock:
            return LLMResponse(
                content=self._mock_response(messages),
                model=model or self.model,
                used_fallback=True,
                fallback_reason="mock_mode",
            )

        # Missing API key should gracefully fall back to mock mode for local demo
        api_key = self.api_key
        if not api_key:
            return LLMResponse(
                content=self._mock_response(messages),
                model=model or self.model,
                used_fallback=True,
                fallback_reason="missing_api_key_mock",
            )

        actual_model = model or self.model
        actual_temperature = temperature if temperature is not None else self.temperature

        last_error: Optional[Exception] = None
        max_attempts = self.max_attempts or resolve_llm_retry_max_attempts()
        backoff = resolve_llm_retry_backoff_seconds()
        for attempt in range(1, max_attempts + 1):
            try:
                response = self._post_chat_completions(
                    messages, actual_model, actual_temperature, **kwargs
                )

                content = response.choices[0].message.content or ""
                usage = None
                if hasattr(response, "usage") and response.usage:
                    usage = {
                        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                        "total_tokens": getattr(response.usage, "total_tokens", 0),
                    }

                return LLMResponse(
                    content=content,
                    model=actual_model,
                    usage=usage,
                    used_fallback=False,
                    fallback_reason="",
                )
            except Exception as e:
                last_error = e
                if attempt < max_attempts and _is_retryable_error(e):
                    delay = backoff[min(attempt - 1, len(backoff) - 1)]
                    logger.warning(
                        "[LLMClient] 超时/连接类异常（第 %d 次尝试），%.1fs 后重试: %s",
                        attempt, delay, e,
                    )
                    time.sleep(delay)
                    continue
                break

        logger.error(
            "[LLMClient] LLM 调用最终失败，回退兜底内容: model=%s, error=%s",
            actual_model, last_error,
        )
        return LLMResponse(
            content=self._fallback_text(messages),
            model=model or self.model,
            used_fallback=True,
            fallback_reason=str(last_error),
        )

    # ---- 回退 ----

    def _fallback_text(self, messages: list[dict[str, str]]) -> str:
        """LLM 不可用时的回退响应。"""
        return (
            f"[{self.__class__.__name__}] AI 服务暂时不可用。"
            f" 请检查 API_KEY 和网络连接。"
        )

    def _mock_response(self, messages: list[dict[str, str]]) -> str:
        """Mock 模式下的结构化意图响应。"""
        from ai_engine.intent.rules import (
            detect_interactive,
            extract_duration,
            extract_knowledge_points,
            extract_output_formats,
            extract_style,
            extract_target_student,
            extract_topic,
        )

        text = "\n".join(m["content"] for m in messages if m["role"] == "teacher")
        duration = extract_duration(text)
        topic = extract_topic(text)
        target_student = extract_target_student(text)
        style = extract_style(text)
        knowledge_points = extract_knowledge_points(text)
        output_format = extract_output_formats(text)
        with_interactive = detect_interactive(text)
        key_difficulties = self._mock_extract_list(r"难点[:：]?\s*([\u4e00-\u9fa5\w\s,，]+)", text)
        expected_outcomes = self._mock_extract_list(r"目标[:：]?\s*([\u4e00-\u9fa5\w\s,，]+)", text)
        missing_fields = [
            f for f, value in [
                ("topic", topic),
                ("duration_minutes", duration),
                ("style", style),
                ("target_student", target_student),
                ("knowledge_points", knowledge_points),
            ]
            if not value
        ]
        return json.dumps({
            "topic": topic,
            "duration_minutes": duration,
            "style": style,
            "target_student": target_student,
            "knowledge_points": knowledge_points,
            "output_format": output_format,
            "with_interactive": with_interactive,
            "key_difficulties": key_difficulties,
            "expected_outcomes": expected_outcomes,
            "missing_fields": missing_fields,
        }, ensure_ascii=False, indent=2)

    def _mock_extract_duration(self, text: str) -> int | None:
        m = re.search(r"(\d{1,3})\s*分钟", text)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d+(?:\.\d+)?)\s*小时", text)
        if m:
            return int(float(m.group(1)) * 60)
        if re.search(r"半小时", text):
            return 30
        return None

    def _mock_extract_topic(self, text: str) -> str | None:
        m = re.search(r"关于([\u4e00-\u9fa5\w\s]{2,80}?)(?:的|，|,|\.|$)", text)
        if m:
            return m.group(1).strip()
        m = re.search(r"我要一份(\d{1,3}分钟的)?([\u4e00-\u9fa5\w\s]{2,80}?)(?:课件|讲稿|练习|讲解|测验|活动)?", text)
        if m:
            return (m.group(2) or "").strip()
        return None

    def _mock_extract_target_student(self, text: str) -> str | None:
        m = re.search(r"面向([\u4e00-\u9fa5\w\s]+?)(?:学生|专业|年级|，|,|的|$)", text)
        if m:
            return m.group(1).strip()
        return None

    def _mock_extract_style(self, text: str) -> str | None:
        m = re.search(r"(讲练结合|案例分析|案例驱动|讨论环节|互动|项目制|理论为主|课堂活动)", text)
        if m:
            return m.group(1).strip()
        return None

    def _mock_extract_knowledge_points(self, text: str) -> list[str]:
        m = re.search(r"(包括|包含|涉及|重点讲解|重点|涵盖)\s*([\u4e00-\u9fa5\w\s,，；;]+)", text)
        if m:
            items = re.split(r"[，,；;]\s*", m.group(2))
            return [i.strip() for i in items if i.strip()]
        items = re.findall(r"([\u4e00-\u9fa5]{2,10})(?:、|,|，)", text)
        return list(dict.fromkeys([i.strip() for i in items if i.strip()]))

    def _mock_extract_output_format(self, text: str) -> list[str]:
        result = []
        if re.search(r"PPT|ppt|幻灯|课件", text):
            result.append("ppt")
        if re.search(r"讲稿|讲义", text):
            result.append("script")
        if re.search(r"习题|练习题|题目|练习", text):
            result.append("exercise")
        return result

    def _mock_extract_list(self, pattern: str, text: str) -> list[str]:
        m = re.search(pattern, text)
        if not m:
            return []
        return [item.strip() for item in re.split(r"[，,；;]\s*", m.group(1)) if item.strip()]


# ---- 便捷单例工厂 ----

def create_llm_client(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> LLMClient:
    """创建一个新的 LLMClient 实例。"""
    return LLMClient(model=model, temperature=temperature)
