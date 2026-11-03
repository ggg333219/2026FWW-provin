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
from ai_engine.intent.normalize import normalize_intent_payload
from ai_engine.intent.rules import (
    extract_explicit_knowledge_points,
    extract_topic_strict,
    filter_knowledge_point_fragments,
    is_grounded_knowledge_point,
)

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

    def extract_intent(
        self, session_id: str, messages: list[DialogueTurn], request_id: str = ""
    ) -> dict[str, Any]:
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

        summary, engine_name, used_fallback, fallback_reason, notes = self._extract_summary(
            messages, raw_messages
        )
        if used_fallback:
            safe_request_id = request_id if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", request_id or "") else "unavailable"
            logging.getLogger(__name__).warning(
                "S1 intent extraction degraded request_id=%s reason=%s",
                safe_request_id,
                fallback_reason or "unknown",
            )
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
            "fallback_reason": fallback_reason,
            # F01 可观测性：真实模型输出的归一/丢弃说明。
            # 非空表示模型输出可用但存在格式偏差；空表示模型输出本身规整。
            "normalization_notes": notes,
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
    ) -> tuple[IntentSummary, str, bool, str | None, list[str]]:
        """提取结构化意图。

        Returns:
            ``(摘要, 引擎名, 是否降级, 降级原因, 归一说明)``。
        """
        result: Any = None
        notes: list[str] = []
        if self.engine is not None:
            try:
                result = self.engine.extract_intent(raw_messages)
                if isinstance(result, IntentSummary):
                    if result.topic:
                        return result, self.engine.__class__.__name__, False, None, notes
                    reason = "invalid_model_response"
                elif isinstance(result, dict) and not result.get("error"):
                    summary, notes = self._build_summary_from_payload(result)
                    if summary.topic:
                        return summary, self.engine.__class__.__name__, False, None, notes
                    self._log_degraded(
                        reason=f"自定义引擎输出缺少有效主题（topic={summary.topic!r}）",
                        raw_output=self._dump_raw_output(result),
                        path="engine",
                    )
                    reason = "invalid_model_response"
                elif isinstance(result, dict):
                    self._log_degraded(
                        reason=f"自定义引擎返回错误（error={result.get('error')!r}）",
                        raw_output=self._dump_raw_output(result),
                        path="engine",
                    )
                    reason = self._classify_engine_failure(result)
                else:
                    self._log_degraded(
                        reason=f"自定义引擎返回了不支持的类型（{type(result).__name__}）",
                        raw_output=self._dump_raw_output(result),
                        path="engine",
                    )
                    reason = "invalid_model_response"
            except Exception as exc:
                self._log_degraded(
                    reason=f"自定义引擎输出校验失败：{type(exc).__name__}: {exc}",
                    raw_output=self._dump_raw_output(result),
                    path="engine",
                    exc=exc,
                )
                reason = self._classify_engine_failure({"reason": f"{type(exc).__name__} {exc}"})
            # 降级到规则引擎时，模型输出并未被采用，因此不携带归一说明 ——
            # 保持"normalization_notes 非空 ⇔ 模型输出被采用"的契约清晰。
            return IntentEngine.extract_intent(raw_messages), "IntentEngine", True, reason, []

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
            summary, notes = self._build_summary_from_payload(result or {})
            if not summary.topic:
                raise ValueError("LLM 未返回有效主题")
            return summary, "LLM", False, None, notes
        except Exception as exc:
            self._log_degraded(
                reason=f"LLM 意图提取失败：{type(exc).__name__}: {exc}",
                raw_output=self._dump_raw_output(result),
                path="chat_json",
                exc=exc,
            )
            reason = "invalid_model_response" if isinstance(exc, (ValueError, TypeError)) else self._classify_engine_failure(
                {"reason": f"{type(exc).__name__} {exc}"}
            )
            # 同上：降级时模型输出未被采用，不携带归一说明。
            return IntentEngine.extract_intent(raw_messages), "IntentEngine", True, reason, []

    @staticmethod
    def _build_summary_from_payload(payload: dict[str, Any]) -> tuple[IntentSummary, list[str]]:
        """把模型原始输出归一后再构造摘要。

        先归一再校验：单个字段的类型偏差（模型把 with_interactive 说成"需要"、
        把 duration 说成"45分钟"等）不再连带丢弃其它已正确解析的字段。
        """
        normalized, notes = normalize_intent_payload(payload)
        return IntentSummary(**normalized), notes

    @staticmethod
    def _classify_engine_failure(result: dict[str, Any]) -> str:
        """Map provider exceptions to safe categories without exposing their details."""
        detail = str(result.get("reason") or result.get("error") or "").lower()
        if "timeout" in detail or "timed out" in detail or "deadline exceeded" in detail:
            return "timeout"
        if any(marker in detail for marker in ("connection", "connecterror", "dns")):
            return "engine_unavailable"
        return "model_error"

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
        """用可确定的教师原话校正模型结果，模型仍负责规则无法覆盖的开放字段。

        校正原则：规则结论只在**高置信度**时才允许覆盖模型结果。
        规则的兜底猜测（剥词取首句）容易产出"做45分钟快速排序"这类脏值，
        若允许它覆盖，会把模型已经解析正确的字段弄坏。
        """
        rule_summary = IntentEngine.extract_intent(raw_messages)
        teacher_text = "。".join(item["content"] for item in raw_messages if item["role"].lower() == "teacher")

        for field in ("duration_minutes", "style", "target_student"):
            value = getattr(rule_summary, field, None)
            if value not in (None, ""):
                setattr(summary, field, value)

        # 主题：只有规则高置信度命中时才覆盖模型结果，否则保留模型给出的主题。
        rule_topic = extract_topic_strict(teacher_text)
        if rule_topic:
            summary.topic = rule_topic

        # 知识点：教师**明确标注**（"知识点：…"）时以规则为准，清单最可信；
        # 未标注时保留模型结果，但要求能在教师原话中找到依据 ——
        # 既避免"教师已经说过的知识点被规则清空"，也避免模型自行脑补，
        # 也避免"互动选择题"这类**要求**被当成知识点。
        # 注意：规则未命中时不从主题反推知识点 —— 主题是课程名，
        # 推导出来的知识点属于凭空推断，会让系统不再追问真正缺失的信息。
        explicit_points = extract_explicit_knowledge_points(teacher_text)
        if explicit_points:
            summary.knowledge_points = explicit_points
        else:
            candidates = [
                point
                for point in summary.knowledge_points
                if is_grounded_knowledge_point(point, teacher_text)
            ]
            summary.knowledge_points = filter_knowledge_point_fragments(
                candidates,
                style=summary.style,
                target_student=summary.target_student,
            )

        if "互动设计" in teacher_text:
            summary.with_interactive = rule_summary.with_interactive
        elif rule_summary.with_interactive:
            summary.with_interactive = True
        # 输出格式：只有教师**明确点名**格式（PPT / 幻灯片 / Word / 教案…）才用规则结论覆盖模型。
        # 通用词"课件"不算 —— 它几乎出现在每一句教学需求里（"做一节XX课件"），
        # 若据此覆盖，会把模型已归一好的 ["ppt","doc"] 压成 ["ppt"]，
        # 等于让 F01 的归一成果在合并阶段被丢弃。
        if re.search(r"PPT|ppt|幻灯|Word|word|DOCX|docx|教案|讲义|讲稿", teacher_text):
            summary.output_format = rule_summary.output_format
        elif not summary.output_format:
            # 模型没给格式、教师也没点名时，用规则的默认（PPT），不留空。
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
