"""S1 意图理解服务：多轮澄清、结构化摘要与确认状态机。"""

from __future__ import annotations

from datetime import datetime
import json
import logging
import re
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from ai_engine.core import LLMClient, IntentSummary, DialogueTurn, SessionStatus, ConversationSession, settings
from ai_engine.intent.intent_engine import IntentEngine

logger = logging.getLogger(__name__)

# 降级日志中原始 LLM 输出的最大长度，避免超长输出刷爆日志。
_DEGRADED_RAW_OUTPUT_MAX_CHARS = 800


# 单进程会话仓库。生产环境可在不改变服务接口的情况下替换为 Redis。
SESSIONS: dict[str, ConversationSession] = {}


class IntentSessionError(RuntimeError):
    """S1 会话不可继续。"""


class IntentSessionNotFound(IntentSessionError):
    pass


class IntentSessionExpired(IntentSessionError):
    pass


class IntentSessionLocked(IntentSessionError):
    pass


class IntentNotReady(IntentSessionError):
    def __init__(self, missing_fields: list[str]) -> None:
        self.missing_fields = missing_fields
        super().__init__("核心教学意图尚未补充完整")


class IntentUnderstandingService:
    """S1 应用服务，确保一次请求只执行一次提取并推进会话状态。"""

    CORE_REQUIRED_FIELDS = ("topic", "duration_minutes")
    QUALITY_FIELDS = ("style", "target_student", "knowledge_points")
    FIELD_LABELS = {
        "topic": "课程主题",
        "duration_minutes": "授课时长",
        "style": "教学风格",
        "target_student": "授课对象",
        "knowledge_points": "核心知识点",
    }

    def __init__(self, client: LLMClient | None = None, engine: object | None = None) -> None:
        self.client = client or LLMClient(model=settings.MODEL, temperature=0.1)
        self.engine = engine

    def extract_intent(self, session_id: str, messages: list[DialogueTurn]) -> dict[str, Any]:
        """从完整对话历史提取意图，并推进 collecting/clarifying/confirming。"""
        session_id = (session_id or "").strip()
        if not session_id:
            raise ValueError("session_id 不能为空")
        if not messages:
            raise ValueError("messages 不能为空")

        previous = SESSIONS.get(session_id)
        if previous:
            if previous.is_timed_out:
                SESSIONS.pop(session_id, None)
                raise IntentSessionExpired("会话已超过 30 分钟，请重新开始")
            if previous.is_locked:
                raise IntentSessionLocked("意图已锁定，无法继续修改")

        raw_messages = [
            {"role": item.role, "content": item.content.strip()}
            for item in messages
            if item.content and item.content.strip()
        ]
        if not any(item["role"].lower() == "teacher" for item in raw_messages):
            raise ValueError("至少需要一条教师消息")

        summary, engine_name, used_fallback = self._extract_summary(messages, raw_messages)
        summary = self._merge_rule_evidence(summary, raw_messages)
        summary.missing_fields = self._infer_missing_fields(summary)

        teacher_turns = sum(1 for item in raw_messages if item["role"].lower() == "teacher")
        max_turns = previous.max_turns if previous else 8
        core_missing = [field for field in self.CORE_REQUIRED_FIELDS if field in summary.missing_fields]
        can_confirm = not core_missing

        if can_confirm:
            status = SessionStatus.CONFIRMING
        elif teacher_turns >= max_turns:
            status = SessionStatus.CONFIRMING
        elif teacher_turns <= 1:
            status = SessionStatus.COLLECTING
        else:
            status = SessionStatus.CLARIFYING

        followups = self.build_followup_questions(summary, core_only=teacher_turns >= max_turns)
        response = self._build_assistant_response(summary, followups, can_confirm, teacher_turns, max_turns)

        session = previous or ConversationSession(session_id=session_id)
        session.intent = summary
        session.status = status
        session.turn_count = teacher_turns
        session.updated_at = datetime.now()
        SESSIONS[session_id] = session

        return {
            "session_id": session_id,
            "intent_summary": summary.model_dump(),
            "session_status": status.value,
            "response": response,
            "need_followup": bool(followups),
            "followup_questions": followups,
            "human_summary": IntentEngine.render_human_summary(summary),
            "completion_pct": self._completion_pct(summary),
            "turn_count": teacher_turns,
            "max_turns": max_turns,
            "can_confirm": can_confirm,
            "engine": engine_name,
            "used_fallback": used_fallback,
            # H0 可观测性：degraded 是 used_fallback 的显式别名，
            # 供监控/前端统一识别“LLM 失败→规则引擎兜底”的降级链路。
            "degraded": used_fallback,
        }

    def build_followup_questions(self, summary: IntentSummary, core_only: bool = False) -> list[str]:
        """一次只突出一个关键追问，附一个可选质量追问，保持对话自然。"""
        qmap = {
            "topic": "这节课最想讲清楚的主题是什么？",
            "duration_minutes": "这节课计划安排多少分钟？",
            "style": "你更偏好案例驱动、讲练结合，还是项目式教学？",
            "target_student": "这节课主要面向哪个年级、专业或基础层次的学生？",
            "knowledge_points": "希望重点覆盖哪些知识点？列出 2–5 个即可。",
        }
        ordered = list(self.CORE_REQUIRED_FIELDS)
        if not core_only:
            ordered.extend(self.QUALITY_FIELDS)
        questions = [qmap[field] for field in ordered if field in summary.missing_fields]
        return questions[:2]

    def confirm_intent(self, session_id: str) -> dict[str, Any]:
        """确认核心字段完整的意图，生成稳定 intent_id 供 S2/S3 关联。"""
        session = SESSIONS.get((session_id or "").strip())
        if not session:
            raise IntentSessionNotFound("未找到对应的意图会话")
        if session.is_timed_out:
            SESSIONS.pop(session.session_id, None)
            raise IntentSessionExpired("会话已超过 30 分钟，请重新开始")
        if session.is_locked:
            raise IntentSessionLocked("意图已经锁定")

        session.intent.missing_fields = self._infer_missing_fields(session.intent)
        core_missing = [field for field in self.CORE_REQUIRED_FIELDS if field in session.intent.missing_fields]
        if core_missing:
            raise IntentNotReady(core_missing)

        session.status = SessionStatus.CONFIRMED
        session.updated_at = datetime.now()
        SESSIONS[session.session_id] = session
        intent_id = f"intent_{uuid5(NAMESPACE_URL, session.session_id).hex[:16]}"
        return {
            "session_id": session.session_id,
            "intent_id": intent_id,
            "confirmed": True,
            "intent_summary": session.intent.model_dump(),
            "session_status": SessionStatus.CONFIRMED.value,
            "completion_pct": self._completion_pct(session.intent),
            "next_step": "material_upload",
        }

    def _extract_summary(
        self,
        messages: list[DialogueTurn],
        raw_messages: list[dict[str, str]],
    ) -> tuple[IntentSummary, str, bool]:
        result: Any = None
        if self.engine is not None:
            try:
                result = self.engine.extract_intent(raw_messages)
                if isinstance(result, IntentSummary):
                    return result, self.engine.__class__.__name__, False
                if isinstance(result, dict) and not result.get("error"):
                    summary = IntentSummary(**result)
                    if summary.topic:
                        return summary, self.engine.__class__.__name__, False
                    self._log_degraded(
                        reason=f"自定义引擎输出缺少有效主题（topic={summary.topic!r}）",
                        raw_output=self._dump_raw_output(result),
                        path="engine",
                    )
                elif isinstance(result, dict):
                    self._log_degraded(
                        reason=f"自定义引擎返回错误（error={result.get('error')!r}）",
                        raw_output=self._dump_raw_output(result),
                        path="engine",
                    )
                else:
                    self._log_degraded(
                        reason=f"自定义引擎返回了不支持的类型（{type(result).__name__}）",
                        raw_output=self._dump_raw_output(result),
                        path="engine",
                    )
            except Exception as exc:
                self._log_degraded(
                    reason=f"自定义引擎输出校验失败：{type(exc).__name__}: {exc}",
                    raw_output=self._dump_raw_output(result),
                    path="engine",
                    exc=exc,
                )
            return IntentEngine.extract_intent(raw_messages), "IntentEngine", True

        prompt = self._build_extract_prompt(messages)
        try:
            result = self.client.chat_json(
                system=(
                    "你是教学设计智能体。根据教师与助手的完整多轮对话合并信息，严格返回 JSON。"
                    "字段为 topic、duration_minutes、style、target_student、knowledge_points、"
                    "output_format、with_interactive、key_difficulties、expected_outcomes、missing_fields。"
                    "不要把助手的追问误当成教师需求；教师最后一次明确修订优先。"
                    "讲课时间45、时长45或单独回答45均表示45分钟；style 接受任意自然语言描述。"
                    "只有教师明确说到知识点、包括、涉及或重点讲解时才提取 knowledge_points，"
                    "不要把教学风格、授课对象或互动要求误当知识点；output_format 仅使用 ppt、doc。"
                ),
                user=prompt,
            )
            summary = IntentSummary(**(result or {}))
            if not summary.topic:
                raise ValueError("LLM 未返回有效主题")
            return summary, "LLM", False
        except Exception as exc:
            self._log_degraded(
                reason=f"LLM 意图提取失败：{type(exc).__name__}: {exc}",
                raw_output=self._dump_raw_output(result),
                path="chat_json",
                exc=exc,
            )
            return IntentEngine.extract_intent(raw_messages), "IntentEngine", True

    @staticmethod
    def _dump_raw_output(result: Any) -> str:
        """把原始 LLM/引擎输出序列化为可读日志文本，超长截断。"""
        if result is None:
            return "<无输出>"
        if isinstance(result, str):
            text = result
        else:
            try:
                text = json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                text = repr(result)
        if len(text) > _DEGRADED_RAW_OUTPUT_MAX_CHARS:
            text = text[:_DEGRADED_RAW_OUTPUT_MAX_CHARS] + f"…（已截断，全长 {len(text)} 字符）"
        return text

    @staticmethod
    def _log_degraded(reason: str, raw_output: str, path: str, exc: Exception | None = None) -> None:
        """H0 可观测性：LLM 结果验证失败回退规则引擎时，输出结构化降级日志。"""
        logger.warning(
            "S1 意图提取降级：LLM 结果未通过校验，回退本地规则引擎 | "
            "path=%s | reason=%s | raw_output=%s",
            path,
            reason,
            raw_output,
            exc_info=exc if exc is not None else None,
        )

    @staticmethod
    def _build_extract_prompt(messages: list[DialogueTurn]) -> str:
        return "\n".join(f"{item.role}: {item.content}" for item in messages) or "用户尚未提供明确内容。"

    @staticmethod
    def _merge_rule_evidence(summary: IntentSummary, raw_messages: list[dict[str, str]]) -> IntentSummary:
        """用可确定的教师原话校正模型结果，模型仍负责规则无法覆盖的开放字段。"""
        rule_summary = IntentEngine.extract_intent(raw_messages)
        for field in ("topic", "duration_minutes", "style", "target_student"):
            value = getattr(rule_summary, field, None)
            if value not in (None, ""):
                setattr(summary, field, value)
        # Knowledge points are accepted only when the teacher explicitly labels
        # them. This prevents ordinary request fragments (for example a style
        # preference) from being promoted to course content by the model.
        summary.knowledge_points = rule_summary.knowledge_points

        teacher_text = "。".join(item["content"] for item in raw_messages if item["role"].lower() == "teacher")
        if "互动设计" in teacher_text:
            summary.with_interactive = rule_summary.with_interactive
        elif rule_summary.with_interactive:
            summary.with_interactive = True
        if re.search(r"PPT|ppt|幻灯|课件|Word|word|DOCX|docx|教案|讲义|讲稿", teacher_text):
            summary.output_format = rule_summary.output_format
        return summary

    def _infer_missing_fields(self, summary: IntentSummary) -> list[str]:
        return [
            field
            for field in (*self.CORE_REQUIRED_FIELDS, *self.QUALITY_FIELDS)
            if getattr(summary, field, None) in (None, "", [])
        ]

    @staticmethod
    def _completion_pct(summary: IntentSummary) -> int:
        weights = {
            "topic": 25,
            "duration_minutes": 25,
            "style": 15,
            "target_student": 15,
            "knowledge_points": 20,
        }
        return sum(weight for field, weight in weights.items() if getattr(summary, field, None) not in (None, "", []))

    def _build_assistant_response(
        self,
        summary: IntentSummary,
        followups: list[str],
        can_confirm: bool,
        turn_count: int,
        max_turns: int,
    ) -> str:
        if can_confirm:
            quality_missing = [self.FIELD_LABELS[f] for f in self.QUALITY_FIELDS if f in summary.missing_fields]
            if quality_missing and turn_count < max_turns:
                return f"核心需求已经清楚了。为了让成品更贴合课堂，我还可以补充确认：{'、'.join(quality_missing)}。你也可以直接确认当前方案。"
            return "教学意图已经完整，我已整理成右侧方案卡。确认后即可进入资料融合。"
        if followups:
            return followups[0]
        return "我已达到本轮澄清上限，请在右侧检查核心信息后确认或重新开始。"


__all__ = [
    "IntentUnderstandingService",
    "SESSIONS",
    "IntentSessionError",
    "IntentSessionNotFound",
    "IntentSessionExpired",
    "IntentSessionLocked",
    "IntentNotReady",
]
