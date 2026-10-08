"""
Word 标准教案生成模块 — A12 赛题 4b

职责：
  结构化节点数组 + 意图摘要 → 标准教案（LessonPlan）

标准教案章节（对齐 A12 赛题硬性要求 4b）：
  教学目标（知识/能力/素养三维）、教学重点与难点、教学方法、
  教学过程（阶段/教师活动/学生活动/设计意图/时长）、
  课堂活动设计、课后作业、板书设计（可选）。

生成策略：
  1. LLM 路径：chat_with_schema 按节点+意图生成教案 JSON（失败自动降级链见 core/llm.py）
  2. Fallback 路径：LLM 失败 / AI_GEN_MODE=mock 时，从节点的
     title / key_points / questions 机械拼装标准教案结构，保证导出永不空。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from ai_engine.core.config import settings

logger = logging.getLogger(__name__)

# ---- 三维目标维度常量 ----

DIMENSION_KNOWLEDGE = "知识目标"
DIMENSION_ABILITY = "能力目标"
DIMENSION_LITERACY = "素养目标"

# 教学过程四个标准阶段
PHASE_INTRO = "导入"
PHASE_NEW = "新授"
PHASE_PRACTICE = "练习"
PHASE_SUMMARY = "小结"


# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class ProcessPhase:
    """教学过程的一个阶段。"""
    phase: str = PHASE_NEW
    duration_minutes: int = 5
    teacher_activity: str = ""
    student_activity: str = ""
    design_intent: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "duration_minutes": self.duration_minutes,
            "teacher_activity": self.teacher_activity,
            "student_activity": self.student_activity,
            "design_intent": self.design_intent,
        }


@dataclass
class LessonPlan:
    """标准教案数据结构（A12 赛题 4b）。"""
    course_name: str = ""
    """课程名称（取自意图 topic 或首节点标题）"""
    subject: str = ""
    """学科（如"计算机科学"）"""
    grade_level: str = ""
    """授课对象 / 年级（如"大一计算机专业"）"""
    duration_minutes: int = 45
    """总课时（分钟）"""

    teaching_objectives: list[dict[str, str]] = field(default_factory=list)
    """三维目标：[{"dimension": "知识目标|能力目标|素养目标", "content": "..."}]"""

    key_difficulties: dict[str, list[str]] = field(default_factory=dict)
    """重点难点：{"key_points": ["重点..."], "difficult_points": ["难点..."]}"""

    teaching_methods: list[str] = field(default_factory=list)
    """教学方法：讲授法 / 演示法 / 小组讨论法 等"""

    teaching_process: list[ProcessPhase] = field(default_factory=list)
    """教学过程阶段列表"""

    classroom_activities: list[dict[str, str]] = field(default_factory=list)
    """课堂活动：[{"name": "活动名", "description": "活动说明"}]"""

    homework: list[str] = field(default_factory=list)
    """课后作业列表"""

    board_design: str = ""
    """板书设计（可选）"""

    data_source: str = "fallback"
    """生成来源："llm" | "fallback" | "mock"，用于诊断"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "course_name": self.course_name,
            "subject": self.subject,
            "grade_level": self.grade_level,
            "duration_minutes": self.duration_minutes,
            "teaching_objectives": list(self.teaching_objectives),
            "key_difficulties": {
                "key_points": list(self.key_difficulties.get("key_points", [])),
                "difficult_points": list(self.key_difficulties.get("difficult_points", [])),
            },
            "teaching_methods": list(self.teaching_methods),
            "teaching_process": [p.to_dict() for p in self.teaching_process],
            "classroom_activities": list(self.classroom_activities),
            "homework": list(self.homework),
            "board_design": self.board_design,
            "data_source": self.data_source,
        }


# =============================================================================
# 工具函数
# =============================================================================

def _as_mapping(obj: Any) -> dict[str, Any]:
    """dict / Pydantic / dataclass 输入统一为 dict。"""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return dict(vars(obj))


def _node_text(node: dict[str, Any]) -> str:
    """取节点可读正文（content / script / summary）。"""
    text = node.get("content") or node.get("script") or node.get("summary") or ""
    return str(text).strip()


def _node_key_points(node: dict[str, Any]) -> list[str]:
    points = node.get("core_points") or node.get("key_points") or []
    if isinstance(points, str):
        points = [points]
    return [str(p).strip() for p in points if str(p).strip()]


def _node_questions(node: dict[str, Any]) -> list[str]:
    questions = node.get("questions") or node.get("interactive_questions") or []
    if isinstance(questions, str):
        questions = [questions]
    return [str(q).strip() for q in questions if str(q).strip()]


def _clean_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _clean_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


# =============================================================================
# 生成器
# =============================================================================

LESSON_PLAN_SCHEMA = {
    "name": "lesson_plan",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "course_name": {"type": "string"},
            "subject": {"type": "string"},
            "grade_level": {"type": "string"},
            "duration_minutes": {"type": "integer"},
            "teaching_objectives": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dimension": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["dimension", "content"],
                },
            },
            "key_difficulties": {
                "type": "object",
                "properties": {
                    "key_points": {"type": "array", "items": {"type": "string"}},
                    "difficult_points": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key_points", "difficult_points"],
            },
            "teaching_methods": {"type": "array", "items": {"type": "string"}},
            "teaching_process": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "phase": {"type": "string"},
                        "duration_minutes": {"type": "integer"},
                        "teacher_activity": {"type": "string"},
                        "student_activity": {"type": "string"},
                        "design_intent": {"type": "string"},
                    },
                    "required": ["phase", "duration_minutes", "teacher_activity",
                                 "student_activity", "design_intent"],
                },
            },
            "classroom_activities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["name", "description"],
                },
            },
            "homework": {"type": "array", "items": {"type": "string"}},
            "board_design": {"type": "string"},
        },
        "required": [
            "course_name", "subject", "grade_level", "duration_minutes",
            "teaching_objectives", "key_difficulties", "teaching_methods",
            "teaching_process", "classroom_activities", "homework", "board_design",
        ],
    },
}


class LessonPlanGenerator:
    """节点 + 意图 → 标准教案（LLM 优先，确定性 fallback 兜底）。"""

    def __init__(self, llm_client: Any = None):
        self._llm_client = llm_client

    def _get_llm_client(self) -> Any:
        if self._llm_client is None:
            from ai_engine.core.llm import LLMClient
            self._llm_client = LLMClient(max_attempts=1)
        return self._llm_client

    def generate(
        self,
        nodes: list[dict[str, Any]],
        intent: Any = None,
        markdown: Optional[str] = None,
        generation_instruction_set: Any = None,
    ) -> LessonPlan:
        """生成标准教案。

        Args:
            nodes: 结构化节点数组（dict 或 Pydantic TeachingNode）
            intent: 意图摘要（IntentSummary 或 dict，可为 None）
            markdown: 可选的课件 markdown 源文（用于补充上下文）

        Returns:
            LessonPlan（data_source 标明生成来源，导出永不空）
        """
        intent_dict = _as_mapping(intent)
        instruction_set = _as_mapping(generation_instruction_set)
        if not intent_dict and isinstance(instruction_set.get("intent"), dict):
            intent_dict = instruction_set["intent"]
        norm_nodes = [_as_mapping(n) for n in (nodes or [])]

        # mock 模式不调 LLM，直接构造样例教案
        if settings.is_mock:
            plan = self._build_fallback_plan(norm_nodes, intent_dict, markdown=markdown)
            plan.data_source = "mock"
            return plan

        try:
            client = self._get_llm_client()
            data = client.chat_with_schema(
                system=(
                    "你是一位资深教研员。根据给定的课件节点和教学意图，"
                    "生成一份标准教案 JSON。要求："
                    "1. teaching_objectives 必须包含知识目标、能力目标、素养目标三个维度；"
                    "2. teaching_process 按 导入/新授/练习/小结 划分阶段，"
                    "各阶段时长之和等于 duration_minutes；"
                    "3. 内容基于给定节点，不得虚构与课件无关的知识点。"
                ),
                user=self._build_user_prompt(norm_nodes, intent_dict, markdown, instruction_set),
                schema=LESSON_PLAN_SCHEMA,
            )
            plan = self._plan_from_llm(data, norm_nodes, intent_dict)
            plan.data_source = "llm"
            return plan
        except Exception as exc:
            logger.warning("[LessonPlanGenerator] LLM 生成教案失败，走确定性 fallback: %s", exc)
            return self._build_fallback_plan(norm_nodes, intent_dict, markdown=markdown)

    # ---- LLM 路径 ----

    def _build_user_prompt(
        self, nodes: list[dict[str, Any]], intent: dict[str, Any], markdown: Optional[str],
        generation_instruction_set: Optional[dict[str, Any]] = None,
    ) -> str:
        lines: list[str] = []
        topic = _clean_str(intent.get("topic"))
        if topic:
            lines.append(f"教学主题：{topic}")
        if intent.get("duration_minutes"):
            lines.append(f"课时：{intent['duration_minutes']} 分钟")
        if intent.get("target_student"):
            lines.append(f"授课对象：{intent['target_student']}")
        if intent.get("style"):
            lines.append(f"教学风格：{intent['style']}")
        if intent.get("knowledge_points"):
            lines.append(f"知识点：{'、'.join(_clean_list(intent['knowledge_points']))}")
        if intent.get("key_difficulties"):
            lines.append(f"预设难点：{'、'.join(_clean_list(intent['key_difficulties']))}")

        instruction_set = generation_instruction_set or {}
        output_requirements = instruction_set.get("output_requirements") or {}
        if output_requirements:
            lines.append(f"本次输出要求：{output_requirements}")
        evidence = instruction_set.get("confirmed_evidence") or {}
        evidence_context = _clean_str(evidence.get("synthesized_context")) if isinstance(evidence, dict) else ""
        if evidence_context:
            lines.append(f"教师已确认的参考资料：\n{evidence_context[:4000]}")
        references = instruction_set.get("reference_materials") or []
        if references:
            lines.append(f"参考资料来源清单：{references[:30]}")

        lines.append("课件节点：")
        for idx, node in enumerate(nodes, start=1):
            title = _clean_str(node.get("title")) or f"第{idx}节"
            node_type = _clean_str(node.get("type") or node.get("node_type")) or "content"
            lines.append(f"  {idx}. [{node_type}] {title}")
            points = _node_key_points(node)
            if points:
                lines.append(f"     要点：{'；'.join(points[:4])}")
            questions = _node_questions(node)
            if questions:
                lines.append("     互动问题：" + "；".join(questions[:2]))

        if markdown:
            excerpt = markdown[:2000]
            lines.append(f"课件源文摘录：\n{excerpt}")
        return "\n".join(lines)

    def _plan_from_llm(
        self, data: Any, nodes: list[dict[str, Any]], intent: dict[str, Any],
    ) -> LessonPlan:
        """把 LLM 返回的 JSON 规范化为 LessonPlan。

        LLM 经常只返回 schema 中的核心字段。这里保留模型生成的有效内容，同时用
        节点驱动的确定性教案补齐缺失章节，避免导出的“真实 LLM 教案”出现空白栏。
        """
        if not isinstance(data, dict):
            raise ValueError("LLM 返回内容不是 JSON 对象")
        if data.get("error"):
            raise ValueError(f"LLM 返回错误标记: {data.get('error')}")

        objectives_raw = data.get("teaching_objectives") or []
        objectives: list[dict[str, str]] = []
        if isinstance(objectives_raw, list):
            for item in objectives_raw:
                if isinstance(item, dict):
                    dim = _clean_str(item.get("dimension"))
                    content = _clean_str(item.get("content"))
                    if dim and content:
                        objectives.append({"dimension": dim, "content": content})
                elif isinstance(item, str) and item.strip():
                    # 宽容处理：纯字符串目标归入知识目标维度之外的原样保留
                    objectives.append({"dimension": "", "content": item.strip()})
        if not objectives:
            raise ValueError("LLM 教案缺少 teaching_objectives")

        fallback = self._build_fallback_plan(nodes, intent)
        canonical_dimensions = (
            DIMENSION_KNOWLEDGE, DIMENSION_ABILITY, DIMENSION_LITERACY,
        )
        objective_dimensions = {item["dimension"] for item in objectives}
        for fallback_objective in fallback.teaching_objectives:
            dimension = fallback_objective["dimension"]
            if dimension in canonical_dimensions and dimension not in objective_dimensions:
                objectives.append(dict(fallback_objective))
                objective_dimensions.add(dimension)

        process_raw = data.get("teaching_process") or []
        phases: list[ProcessPhase] = []
        if isinstance(process_raw, list):
            for item in process_raw:
                if not isinstance(item, dict):
                    continue
                try:
                    minutes = int(item.get("duration_minutes") or 0)
                except (TypeError, ValueError):
                    minutes = 0
                phases.append(ProcessPhase(
                    phase=_clean_str(item.get("phase"), PHASE_NEW),
                    duration_minutes=minutes,
                    teacher_activity=_clean_str(item.get("teacher_activity")),
                    student_activity=_clean_str(item.get("student_activity")),
                    design_intent=_clean_str(item.get("design_intent")),
                ))
        if not phases:
            raise ValueError("LLM 教案缺少 teaching_process")

        # 标准四阶段必须齐全；模型阶段内容缺字段时逐项补齐，而不是整份降级。
        fallback_phases = {phase.phase: phase for phase in fallback.teaching_process}
        normalized_phases: list[ProcessPhase] = []
        consumed: set[int] = set()
        for phase_name in (PHASE_INTRO, PHASE_NEW, PHASE_PRACTICE, PHASE_SUMMARY):
            matched_index = next(
                (idx for idx, phase in enumerate(phases)
                 if idx not in consumed and phase.phase == phase_name),
                None,
            )
            base = fallback_phases[phase_name]
            if matched_index is None:
                normalized_phases.append(base)
                continue
            consumed.add(matched_index)
            current = phases[matched_index]
            normalized_phases.append(ProcessPhase(
                phase=phase_name,
                duration_minutes=current.duration_minutes if current.duration_minutes > 0
                else base.duration_minutes,
                teacher_activity=current.teacher_activity or base.teacher_activity,
                student_activity=current.student_activity or base.student_activity,
                design_intent=current.design_intent or base.design_intent,
            ))
        phases = normalized_phases

        kd_raw = data.get("key_difficulties") or {}
        key_difficulties = {}
        if isinstance(kd_raw, dict):
            key_difficulties = {
                "key_points": _clean_list(kd_raw.get("key_points")),
                "difficult_points": _clean_list(kd_raw.get("difficult_points")),
            }
        elif isinstance(kd_raw, list):
            key_difficulties = {"key_points": _clean_list(kd_raw), "difficult_points": []}

        activities_raw = data.get("classroom_activities") or []
        activities: list[dict[str, str]] = []
        if isinstance(activities_raw, list):
            for item in activities_raw:
                if isinstance(item, dict):
                    name = _clean_str(item.get("name"))
                    desc = _clean_str(item.get("description"))
                    if name:
                        activities.append({"name": name, "description": desc})
                elif isinstance(item, str) and item.strip():
                    activities.append({"name": item.strip(), "description": ""})

        # 教师明确给出的课时属于意图约束，优先级高于模型自行估算。
        try:
            duration = int(intent.get("duration_minutes") or data.get("duration_minutes") or 0)
        except (TypeError, ValueError):
            duration = 0
        if duration <= 0:
            duration = self._resolve_total_minutes(nodes, intent)

        # 课时总和是教案表格的硬约束。优先调整“新授”阶段；若模型时长严重异常，
        # 直接采用确定性分配，保证每阶段至少 1 分钟且总和准确。
        delta = duration - sum(phase.duration_minutes for phase in phases)
        new_phase = next(phase for phase in phases if phase.phase == PHASE_NEW)
        if delta and new_phase.duration_minutes + delta > 0:
            new_phase.duration_minutes += delta
        elif delta:
            durations = self._split_durations(duration)
            for phase in phases:
                phase.duration_minutes = durations[phase.phase]

        fallback_kd = fallback.key_difficulties
        key_difficulties = {
            "key_points": key_difficulties.get("key_points") or fallback_kd["key_points"],
            "difficult_points": key_difficulties.get("difficult_points")
            or fallback_kd["difficult_points"],
        }

        teaching_methods = _clean_list(data.get("teaching_methods"))
        classroom_activities = activities or [dict(item) for item in fallback.classroom_activities]
        homework = _clean_list(data.get("homework")) or list(fallback.homework)
        board_design = _clean_str(data.get("board_design")) or fallback.board_design

        return LessonPlan(
            course_name=_clean_str(intent.get("topic"))
                        or _clean_str(data.get("course_name")) or "课程",
            subject=_clean_str(data.get("subject"), "综合"),
            grade_level=_clean_str(data.get("grade_level")
                                   or intent.get("target_student"), "全体学生"),
            duration_minutes=duration,
            teaching_objectives=objectives,
            key_difficulties=key_difficulties,
            teaching_methods=teaching_methods or list(fallback.teaching_methods),
            teaching_process=phases,
            classroom_activities=classroom_activities,
            homework=homework,
            board_design=board_design,
        )

    # ---- Fallback 路径（确定性，永不失败） ----

    def _resolve_total_minutes(
        self, nodes: list[dict[str, Any]], intent: dict[str, Any],
    ) -> int:
        """课时来源：意图 > 节点 estimated_duration 之和 > 默认 45。"""
        raw = intent.get("duration_minutes")
        try:
            if raw and int(raw) > 0:
                return int(raw)
        except (TypeError, ValueError):
            pass
        total = 0.0
        for node in nodes:
            for key in ("estimated_duration_minutes", "estimated_duration"):
                try:
                    val = float(node.get(key) or 0)
                    if val > 0:
                        total += val
                        break
                except (TypeError, ValueError):
                    continue
        return int(total) if total > 0 else 45

    def _classify_node(self, node: dict[str, Any]) -> str:
        """节点类型 → 标准教学阶段。"""
        node_type = _clean_str(node.get("type") or node.get("node_type")).lower()
        if node_type == "title":
            return PHASE_INTRO
        if node_type in ("quiz", "interactive", "exercise"):
            return PHASE_PRACTICE
        if node_type == "summary":
            return PHASE_SUMMARY
        return PHASE_NEW  # content / slide / section / 未知

    def _split_durations(self, total: int) -> dict[str, int]:
        """按 导入10% / 新授60% / 练习20% / 小结10% 分配课时，余数归新授。"""
        intro = max(1, int(total * 0.10))
        practice = max(1, int(total * 0.20))
        summary = max(1, int(total * 0.10))
        new = total - intro - practice - summary
        if new < 1:
            # 课时太短时保底：导入1 + 新授(total-3) + 练习1 + 小结1
            new = max(1, total - 3)
        return {PHASE_INTRO: intro, PHASE_NEW: new,
                PHASE_PRACTICE: practice, PHASE_SUMMARY: summary}

    def _build_fallback_plan(
        self,
        nodes: list[dict[str, Any]],
        intent: dict[str, Any],
        markdown: Optional[str] = None,
    ) -> LessonPlan:
        """从节点 title / key_points / questions 机械拼装标准教案，保证永不空。"""
        topic = _clean_str(intent.get("topic"))
        if not topic:
            first_title = next(
                (_clean_str(n.get("title")) for n in nodes if _clean_str(n.get("title"))), ""
            )
            topic = first_title or "课程"

        total_minutes = self._resolve_total_minutes(nodes, intent)
        durations = self._split_durations(total_minutes)

        # ---- 按阶段归组节点 ----
        grouped: dict[str, list[dict[str, Any]]] = {
            PHASE_INTRO: [], PHASE_NEW: [], PHASE_PRACTICE: [], PHASE_SUMMARY: [],
        }
        for node in nodes:
            grouped[self._classify_node(node)].append(node)

        # 各阶段保底：导入/练习/小结缺失时补模板阶段，保证标准结构完整
        if not grouped[PHASE_INTRO]:
            grouped[PHASE_INTRO] = [{"title": "课程导入", "content": ""}]
        if not grouped[PHASE_PRACTICE]:
            grouped[PHASE_PRACTICE] = [{"title": "随堂练习", "content": ""}]
        if not grouped[PHASE_SUMMARY]:
            grouped[PHASE_SUMMARY] = [{"title": "课堂小结", "content": ""}]

        phase_design_intents = {
            PHASE_INTRO: "通过情境导入激发学习兴趣，建立新旧知识联系，明确本节课学习目标。",
            PHASE_NEW: "围绕核心知识点展开讲授与演示，结合要点拆解帮助学生建立知识结构。",
            PHASE_PRACTICE: "通过随堂练习与互动问答检验学习效果，及时发现并纠正理解偏差。",
            PHASE_SUMMARY: "梳理本节知识脉络，强化重点记忆，布置课后任务巩固延伸。",
        }
        phase_student_templates = {
            PHASE_INTRO: "观察引入情境，思考并回答导入问题，明确本节学习任务。",
            PHASE_NEW: "听讲并记录要点，参与课堂问答，跟随演示理解知识点的应用方式。",
            PHASE_PRACTICE: "独立完成练习题，参与互动问答，订正并总结易错点。",
            PHASE_SUMMARY: "跟随教师回顾知识脉络，记录课后作业要求。",
        }

        phases: list[ProcessPhase] = []
        for phase_name in (PHASE_INTRO, PHASE_NEW, PHASE_PRACTICE, PHASE_SUMMARY):
            group = grouped[phase_name]
            titles = [_clean_str(n.get("title")) for n in group if _clean_str(n.get("title"))]
            points: list[str] = []
            questions: list[str] = []
            for n in group:
                points.extend(_node_key_points(n)[:3])
                questions.extend(_node_questions(n)[:2])

            if phase_name == PHASE_INTRO:
                teacher = f"以“{titles[0] if titles else topic}”为情境导入，" \
                          f"提出引导性问题，引出本节主题“{topic}”。"
            elif phase_name == PHASE_NEW:
                teacher = "依次讲解：" + ("；".join(titles) if titles else topic) + "。"
                if points:
                    teacher += "重点展开：" + "；".join(points[:4]) + "。"
            elif phase_name == PHASE_PRACTICE:
                teacher = "布置随堂练习并巡回指导"
                if questions:
                    teacher += "，组织互动问答：" + "；".join(questions[:2]) + "。"
                else:
                    teacher += "，针对易错点进行点评讲解。"
            else:
                teacher = f"带领学生回顾“{topic}”的知识脉络，总结重点，布置课后作业。"

            phases.append(ProcessPhase(
                phase=phase_name,
                duration_minutes=durations[phase_name],
                teacher_activity=teacher,
                student_activity=phase_student_templates[phase_name],
                design_intent=phase_design_intents[phase_name],
            ))

        # ---- 三维目标 ----
        knowledge_points = _clean_list(intent.get("knowledge_points"))
        all_points = list(dict.fromkeys(
            [p for n in nodes for p in _node_key_points(n)]
        ))
        objectives: list[dict[str, str]] = []
        if knowledge_points or all_points:
            kps = knowledge_points[:3] or all_points[:3]
            objectives.append({
                "dimension": DIMENSION_KNOWLEDGE,
                "content": "理解并掌握" + "、".join(kps) + "的基本概念与核心要点。",
            })
        else:
            objectives.append({
                "dimension": DIMENSION_KNOWLEDGE,
                "content": f"理解并掌握“{topic}”的基本概念、核心要点及其知识结构。",
            })
        objectives.append({
            "dimension": DIMENSION_ABILITY,
            "content": f"能够运用“{topic}”的相关知识分析并解决实际问题，"
                       "提升课堂练习与互动问答中的表达能力。",
        })
        objectives.append({
            "dimension": DIMENSION_LITERACY,
            "content": "通过课堂讲授与小组互动，培养主动思考、合作探究的学习素养。",
        })

        # ---- 重点难点 ----
        key_points = all_points[:4] or [f"“{topic}”的核心概念与知识结构"]
        difficult_points = _clean_list(intent.get("key_difficulties"))[:3] or \
            [f"“{topic}”中知识点的综合应用与易混淆概念辨析"]

        # ---- 教学方法 ----
        methods = ["讲授法", "演示法"]
        style = _clean_str(intent.get("style"))
        if style and style not in methods:
            methods.insert(1, style)
        if intent.get("with_interactive") or any(_node_questions(n) for n in nodes):
            methods.append("小组讨论法")
        methods = list(dict.fromkeys(methods))

        # ---- 课堂活动 ----
        activities: list[dict[str, str]] = []
        quiz_questions = [q for n in nodes for q in _node_questions(n)]
        if quiz_questions:
            activities.append({
                "name": "随堂互动问答",
                "description": "围绕" + "；".join(quiz_questions[:3]) + " 展开课堂问答与讨论。",
            })
        if intent.get("with_interactive") or not activities:
            activities.append({
                "name": "小组讨论",
                "description": f"分组讨论“{topic}”的典型应用场景，各组代表汇报讨论结论。",
            })

        # ---- 课后作业 ----
        homework = quiz_questions[:3]
        if not homework:
            homework = [
                f"复习本节“{topic}”核心知识点，整理课堂笔记。",
                "完成教材配套练习题，巩固课堂所学。",
            ]

        # ---- 板书设计（可选） ----
        board = ""
        content_titles = [
            _clean_str(n.get("title")) for n in nodes if _clean_str(n.get("title"))
        ]
        if content_titles:
            board = f"课题：{topic}\n知识主线：{' → '.join(content_titles[:6])}"
            if all_points:
                board += "\n核心要点：" + "、".join(all_points[:4])

        return LessonPlan(
            course_name=topic,
            subject=_clean_str(intent.get("subject"), "综合"),
            grade_level=_clean_str(intent.get("target_student"), "全体学生"),
            duration_minutes=total_minutes,
            teaching_objectives=objectives,
            key_difficulties={"key_points": key_points, "difficult_points": difficult_points},
            teaching_methods=methods,
            teaching_process=phases,
            classroom_activities=activities,
            homework=homework,
            board_design=board,
            data_source="fallback",
        )
