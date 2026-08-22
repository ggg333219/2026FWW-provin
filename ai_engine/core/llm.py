"""
统一 LLM 客户端 (core/llm.py)

封装 OpenAI 兼容客户端初始化和调用，供所有 Skill 模块使用。

使用方式：
    from ai_engine.core import LLMClient

    client = LLMClient(model="qwen-turbo", temperature=0.1)
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
import os
import re
from dataclasses import dataclass, field
from typing import Any, Generator, Optional
from urllib.parse import urlparse

from .config import settings

# ---- 常量 ----

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_COMPAT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


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


def extract_json(text: str) -> dict[str, Any]:
    """
    从 LLM 返回文本中提取并解析 JSON。

    处理 ```json ... ``` 包裹、前后空白、多段文本含多个 JSON 等情况。
    与旧版 QAResponder._extract_json 兼容，增强为独立函数。
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).replace("json", "", 1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"模型返回内容中未找到有效 JSON: {text[:200]}")
    return json.loads(cleaned[start : end + 1])


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
        timeout: int = 60,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model = model or settings.MODEL
        self.temperature = temperature if temperature is not None else settings.TEMPERATURE
        self.timeout = timeout
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
    ) -> dict[str, Any]:
        """
        带 JSON Schema 的结构化输出调用（显式版本）。

        与 chat_json(schema=...) 等价，但语义更明确：
        明确告诉调用方这个调用一定会携带 schema。

        Args:
            system: 系统提示词
            user: 用户消息
            schema: OpenAI json_schema 格式的定义（需含 name 字段才触发 structured output）
            temperature: 覆盖默认温度
            model: 覆盖默认模型

        Returns:
            解析后的 JSON 字典
        """
        return self.chat_json(
            system=system,
            user=user,
            schema=schema,
            temperature=temperature,
            model=model,
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

        embedding_model = model or (os.getenv("AI_EMBEDDING_MODEL") or "text-embedding-v3").strip()
        default_dim = 1024
        try:
            default_dim = int(os.getenv("AI_EMBEDDING_DIM", "1024"))
        except (TypeError, ValueError):
            pass
        embedding_dim = dim or default_dim

        if not texts:
            return []

        # Mock 模式 / 无 API key → 零向量回退
        if settings.is_mock or not self.api_key:
            return [[0.0] * embedding_dim for _ in range(len(texts))]

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )

            response = client.embeddings.create(
                model=embedding_model,
                input=texts,
            )

            sorted_data = sorted(response.data, key=lambda d: d.index)
            return [list(d.embedding) for d in sorted_data]

        except Exception:
            return [[0.0] * embedding_dim for _ in range(len(texts))]

    # ---- 内部实现 ----

    def _call(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """底层 LLM 调用，处理统一异常、回退和日志。"""
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

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )

            actual_model = model or self.model
            actual_temperature = temperature if temperature is not None else self.temperature

            response = client.chat.completions.create(
                model=actual_model,
                messages=messages,
                temperature=actual_temperature,
                **kwargs,
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
            return LLMResponse(
                content=self._fallback_text(messages),
                model=model or self.model,
                used_fallback=True,
                fallback_reason=str(e),
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
