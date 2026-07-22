"""S1 意图理解服务：从多轮对话中提取结构化教学意图。"""

from __future__ import annotations

from typing import Any

from ai_engine.core import LLMClient, IntentSummary, DialogueTurn, SessionStatus, ConversationSession
from ai_engine.intent.intent_engine import IntentEngine, LLMIntentEngine

# In-memory session store for S1
SESSIONS: dict[str, ConversationSession] = {}


class IntentUnderstandingService:
    """实现意图提取、追问生成与确认逻辑。"""

    def __init__(self, client: LLMClient | None = None, engine: object | None = None) -> None:
        """If `engine` is provided it should implement `extract_intent(messages)`.

        When `engine` is None, the service will try `LLMClient.chat_json` and
        fall back to the local rule-based `IntentEngine` on error.
        """
        self.client = client or LLMClient(model="qwen-turbo", temperature=0.1)
        self.engine = engine

    def extract_intent(self, session_id: str, messages: list[DialogueTurn]) -> dict[str, Any]:
        """从对话历史提取结构化教学意图。"""
        # normalize messages to simple dicts
        raw_msgs = []
        for item in messages:
            raw_msgs.append({"role": getattr(item, "role", ""), "content": getattr(item, "content", "")})

        # 1) If a concrete engine is provided, use it (could be rule-based or LLM wrapper)
        if self.engine:
            try:
                res = self.engine.extract_intent(raw_msgs)
                if isinstance(res, IntentSummary):
                    summary = res
                elif isinstance(res, dict):
                    summary = IntentSummary(**res)
                else:
                    summary = IntentEngine().extract_intent(raw_msgs)
            except Exception:
                summary = IntentEngine().extract_intent(raw_msgs)
        else:
            # 2) Default: try shared LLM client, then fallback to rule-based
            prompt = self._build_extract_prompt(messages)
            try:
                result = self.client.chat_json(
                    system=(
                        "你是一个教学设计助手，负责从教师与助手的多轮对话中提取结构化教学意图。"
                        "请严格输出 JSON，字段包含 topic、duration_minutes、style、target_student、"
                        "knowledge_points、output_format、with_interactive、key_difficulties、expected_outcomes、missing_fields。"
                    ),
                    user=prompt,
                )
                if not result or not result.get("topic"):
                    raise ValueError("LLM returned incomplete result, falling back")
                summary = IntentSummary(**result)
            except Exception:
                summary = IntentEngine().extract_intent(raw_msgs)

        summary.missing_fields = self._infer_missing_fields(summary)

        # persist minimal session state
        session = ConversationSession(session_id=session_id or "", intent=summary, status=SessionStatus.CLARIFYING)
        SESSIONS[session.session_id] = session

        return {
            "session_id": session_id,
            "intent_summary": summary.model_dump(),
            "session_status": SessionStatus.CLARIFYING.value,
        }

    def build_followup_questions(self, summary: IntentSummary) -> list[str]:
        """根据当前意图摘要生成追问。"""
        questions: list[str] = []
        if not summary.topic:
            questions.append("您想讲的主题是什么？")
        if summary.duration_minutes is None:
            questions.append("这节课预计多长时间？")
        if not summary.style:
            questions.append("您希望采用什么教学风格？")
        if not summary.target_student:
            questions.append("课程面向哪些学生？")
        return questions[:2]

    def confirm_intent(self, session_id: str, summary: IntentSummary) -> dict[str, Any]:
        """确认意图并返回可供下游使用的摘要。"""
        summary.missing_fields = self._infer_missing_fields(summary)
        # update persisted session if exists
        if session_id in SESSIONS:
            sess = SESSIONS[session_id]
            sess.intent = summary
            sess.status = SessionStatus.CONFIRMED
            SESSIONS[session_id] = sess

        return {
            "session_id": session_id,
            "confirmed": True,
            "intent_summary": summary.model_dump(),
            "session_status": SessionStatus.CONFIRMED.value,
        }

    def _build_extract_prompt(self, messages: list[DialogueTurn]) -> str:
        lines: list[str] = []
        for item in messages:
            lines.append(f"{item.role}: {item.content}")
        return "\n".join(lines) or "用户尚未提供明确内容。"

    def _infer_missing_fields(self, summary: IntentSummary) -> list[str]:
        missing: list[str] = []
        if not summary.topic:
            missing.append("topic")
        if summary.duration_minutes is None:
            missing.append("duration_minutes")
        if not summary.style:
            missing.append("style")
        if not summary.target_student:
            missing.append("target_student")
        return missing
