"""Minimal IntentEngine for S1 — rule-based fallback implementation.

This module provides a lightweight, dependency-free implementation
that extracts a best-effort `IntentSummary` from teacher messages,
generates follow-up questions for missing fields, and renders
a human-readable summary. It is intentionally simple so the skill
is runnable without external LLM dependencies during early integration.
"""
from typing import List, Dict, Any, Generator
import re

from ai_engine.core.schema import IntentSummary
from ai_engine.intent.rules import (
    detect_interactive,
    extract_duration,
    extract_knowledge_points,
    extract_output_formats,
    extract_style,
    extract_target_student,
    extract_topic,
)


class IntentEngine:
    @staticmethod
    def _join_teacher_messages(messages: List[Dict[str, Any]]) -> str:
        parts = []
        for m in messages:
            role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
            if role and role.lower() == "teacher":
                parts.append(content or "")
        return "。".join(parts)

    @staticmethod
    def _extract_duration(text: str):
        return extract_duration(text)

    @staticmethod
    def _extract_topic(text: str):
        return extract_topic(text)

    @staticmethod
    def extract_intent(messages: List[Dict[str, Any]]) -> IntentSummary:
        text = IntentEngine._join_teacher_messages(messages)
        intent = IntentSummary()
        intent.topic = IntentEngine._extract_topic(text) if text else None
        intent.duration_minutes = IntentEngine._extract_duration(text)

        intent.target_student = extract_target_student(text)
        intent.style = extract_style(text)
        intent.knowledge_points = extract_knowledge_points(text)
        intent.with_interactive = detect_interactive(text)
        intent.output_format = extract_output_formats(text)

        # key difficulties and expected outcomes
        kd = re.findall(r"难点[:：]?\s*([\u4e00-\u9fa5\w\s,，]+)", text)
        intent.key_difficulties = [s.strip() for s in (kd[0].split('，') if kd else [])] if kd else []
        eo = re.findall(r"目标[:：]?\s*([\u4e00-\u9fa5\w\s,，]+)", text)
        intent.expected_outcomes = [s.strip() for s in (eo[0].split('，') if eo else [])] if eo else []

        # missing fields
        missing = []
        if not intent.topic:
            missing.append("topic")
        if intent.duration_minutes is None:
            missing.append("duration_minutes")
        if not intent.style:
            missing.append("style")
        if not intent.target_student:
            missing.append("target_student")
        if not intent.knowledge_points:
            missing.append("knowledge_points")
        intent.missing_fields = missing

        return intent

    @staticmethod
    def generate_followup_questions(intent: IntentSummary) -> List[str]:
        qmap = {
            "topic": "请问本次课程的主题具体是什么？",
            "duration_minutes": "预计时长是多少分钟？",
            "style": "希望采用什么教学风格（讲练结合/案例驱动/项目制等）？",
            "target_student": "主要面向哪个年级或专业的学生？",
        }
        questions = []
        for f in intent.missing_fields:
            if f in qmap:
                questions.append(qmap[f])
        # limit to 2 follow-ups
        return questions[:2]

    @staticmethod
    def render_human_summary(intent: IntentSummary) -> str:
        parts = []
        if intent.topic:
            parts.append(f"主题: {intent.topic}")
        if intent.duration_minutes:
            parts.append(f"时长: {intent.duration_minutes} 分钟")
        if intent.style:
            parts.append(f"风格: {intent.style}")
        if intent.target_student:
            parts.append(f"面向: {intent.target_student}")
        if intent.knowledge_points:
            parts.append(f"知识点: {', '.join(intent.knowledge_points)}")
        if not parts:
            return "当前未提取到明确意图，请补充信息。"
        return "；".join(parts)


__all__ = ["IntentEngine"]


class LLMIntentEngine:
    """LLM-backed intent extractor using `ai_engine.core.LLMClient`.

    This class demonstrates how to call the shared `LLMClient` and
    parse JSON responses into `IntentSummary`. It is intentionally
    conservative: it returns a dict and does not raise on parse errors.
    """

    SYSTEM_PROMPT = (
        "你是教学设计助手，从教师的多轮对话中提取结构化教学意图。"
        "严格返回 JSON，字段包括 topic, duration_minutes, style, target_student,"
        "knowledge_points, output_format, with_interactive, key_difficulties, expected_outcomes, missing_fields。"
        "教师最后一次明确修订优先；讲课时间45或单独回答45表示45分钟；style 允许自由文本。"
        "只有明确出现知识点、包括、涉及或重点讲解时才填写 knowledge_points。"
    )

    JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "topic": {"type": ["string", "null"]},
            "duration_minutes": {"type": ["integer", "null"]},
            "style": {"type": ["string", "null"]},
            "target_student": {"type": ["string", "null"]},
            "knowledge_points": {"type": "array", "items": {"type": "string"}},
            "output_format": {"type": "array", "items": {"type": "string"}},
            "with_interactive": {"type": "boolean"},
            "key_difficulties": {"type": "array", "items": {"type": "string"}},
            "expected_outcomes": {"type": "array", "items": {"type": "string"}},
            "missing_fields": {"type": "array", "items": {"type": "string"}},
        },
    }

    def __init__(self, client=None):
        from ai_engine.core import LLMClient

        self.client = client or LLMClient(model="qwen-turbo", temperature=0.1)

    def extract_intent(self, messages: List[Dict[str, Any]]) -> dict:
        # build a simple user prompt containing recent teacher messages
        teacher_texts = []
        for m in messages:
            role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
            if role and role.lower() == "teacher":
                teacher_texts.append(content or "")
        user_prompt = "\n".join(teacher_texts) or "教师未提供内容。"

        try:
            result = self.client.chat_json(system=self.SYSTEM_PROMPT, user=user_prompt, schema=self.JSON_SCHEMA)
            if isinstance(result, dict):
                return result
            return {"error": "unexpected_response", "_raw": str(result)}
        except Exception as e:
            return {"error": "llm_call_failed", "reason": str(e)}

    def extract_intent_stream(
        self, messages: List[Dict[str, Any]]
    ) -> Generator[str, None, None]:
        """
        流式提取意图，逐 token yield LLM 的 JSON 输出。

        用于 SSE 流式推送场景——前端可以实时看到意图提取的进度。

        Args:
            messages: 对话消息列表。

        Yields:
            str: LLM 输出的增量文本 token。
        """
        teacher_texts = []
        for m in messages:
            role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
            if role and role.lower() == "teacher":
                teacher_texts.append(content or "")
        user_prompt = "\n".join(teacher_texts) or "教师未提供内容。"

        yield from self.client.chat_stream(
            system=self.SYSTEM_PROMPT,
            user=user_prompt,
        )

