"""Minimal IntentEngine for S1 — rule-based fallback implementation.

This module provides a lightweight, dependency-free implementation
that extracts a best-effort `IntentSummary` from teacher messages,
generates follow-up questions for missing fields, and renders
a human-readable summary. It is intentionally simple so the skill
is runnable without external LLM dependencies during early integration.
"""
from typing import List, Dict, Any
import re

from ai_engine.core.schema import IntentSummary


class IntentEngine:
    @staticmethod
    def _join_teacher_messages(messages: List[Dict[str, Any]]) -> str:
        parts = []
        for m in messages:
            role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
            if role and role.lower() == "teacher":
                parts.append(content or "")
        return "\n".join(parts)

    @staticmethod
    def _extract_duration(text: str):
        # look for explicit minutes
        m = re.search(r"(\d{1,3})\s*分钟", text)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass

        # hours -> minutes
        m_h = re.search(r"(\d+(?:\.\d+)?)\s*小时", text)
        if m_h:
            try:
                return int(float(m_h.group(1)) * 60)
            except Exception:
                pass

        # common shorthand like '半小时'
        if re.search(r"半小时", text):
            return 30

        # english shorthand
        m2 = re.search(r"(\d{1,3})\s*min", text, re.I)
        if m2:
            try:
                return int(m2.group(1))
            except Exception:
                pass

        # fallback: look for numbers near '课' or '节' which might be minutes
        return None

    @staticmethod
    def _extract_topic(text: str):
        # Common patterns
        m = re.search(r"(?:帮我做|我想要|需要|请给我|来一份)(?:\d+\s*分钟)?([\u4e00-\u9fa5\w\s]{2,80}?)的?(?:课件|课程|讲稿|讲解|教学|练习)?", text)
        if m:
            candidate = m.group(1).strip()
            candidate = re.sub(r"(课件|课程|一节|一份|课|讲稿|讲解)$", "", candidate)
            candidate = re.sub(r"\d+\s*分钟", "", candidate)
            return candidate.strip()

        m2 = re.search(r"关于([\u4e00-\u9fa5\w\s]{2,80}?)(?:的|，|,|\.|$)", text)
        if m2:
            candidate = m2.group(1).strip()
            candidate = re.sub(r"(课件|课程|一节|一份|课)$", "", candidate)
            return candidate.strip()

        m3 = re.search(r"主题(?:是|:|：)\s*([\u4e00-\u9fa5\w\s]{2,80})", text)
        if m3:
            return m3.group(1).strip()

        # fallback: take nouns-like phrase from first 40 chars
        cleaned = re.sub(r"(请帮我|帮我|请|麻烦|做一份|做一节|我要)", "", text)
        cleaned = re.sub(r"(课件|课程|一节|一份|的课|讲稿)", "", cleaned)
        return cleaned.strip().splitlines()[0][:80].strip()

    @staticmethod
    def extract_intent(messages: List[Dict[str, Any]]) -> IntentSummary:
        text = IntentEngine._join_teacher_messages(messages)
        intent = IntentSummary()
        intent.topic = IntentEngine._extract_topic(text) if text else None
        intent.duration_minutes = IntentEngine._extract_duration(text)

        # try to extract target student and style with simple heuristics
        m = re.search(r"面向([\u4e00-\u9fa5\w\s]+?)(?:学生|专业|年级|，|,|的|$)", text)
        if m:
            intent.target_student = m.group(1).strip()
        m2 = re.search(r"(讲练结合|案例驱动|项目制|理论为主|讨论|课堂测验)", text)
        if m2:
            intent.style = m2.group(1)

        # knowledge points: look for keywords after '包括' or '涉及'
        kp = []
        m3 = re.search(r"(?:包括|包含|涉及|主要有)\s*([\u4e00-\u9fa5\w\s,，；;]+)", text)
        if m3:
            items = re.split(r"[，,；;]\s*", m3.group(1))
            kp = [i.strip() for i in items if i.strip()]
        else:
            # try to collect short noun phrases separated by '、' or commas
            m4 = re.findall(r"([\u4e00-\u9fa5]{2,10})(?:、|,|，)", text)
            if m4:
                kp = list(dict.fromkeys([i.strip() for i in m4 if i.strip()]))
        intent.knowledge_points = kp

        # detect if teacher mentioned interactive exercises
        intent.with_interactive = bool(re.search(r"互动|练习|测验|小测|讨论|问答", text))

        # detect output format hints (ppt, 讲稿, 习题)
        of = []
        if re.search(r"PPT|ppt|幻灯|课件", text):
            of.append("ppt")
        if re.search(r"讲稿|讲义|讲稿", text):
            of.append("script")
        if re.search(r"习题|练习题|题目", text):
            of.append("exercise")
        intent.output_format = of

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

