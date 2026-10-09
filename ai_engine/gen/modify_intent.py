"""B5: 修改意图理解与节点定位。

把教师的自然语言修改指令解析为结构化修改操作：
  POST /api/v1/ai/parse_modify
    入参: project_id + instruction + nodes[]（当前大纲快照）
    出参: target_type / target_ids / action / constraints / confidence / clarification_needed

支持 7 种修改动作：
  simplify(精简) / expand(扩充) / delete(删除) / add(新增)
  / reorder(调整顺序) / restyle(换样式) / rewrite(重写)

低置信度（confidence < 0.6 或解析失败）时返回 clarification_needed=True
与追问建议，由上层向教师确认后再执行。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ai_engine.core.config import settings
from ai_engine.core.llm import LLMClient, resolve_llm_timeout
from ai_engine.gen.elements import resolve_element_candidates, build_element_snapshot

logger = logging.getLogger(__name__)

# 动作枚举（与 Go 侧 / 前端面板共用语义）
MODIFY_ACTIONS = ("simplify", "expand", "delete", "add", "reorder", "restyle", "rewrite")
TARGET_TYPES = ("node", "page", "global", "style")
CONFIDENCE_THRESHOLD = 0.6

#: 需要「指得动某一页」的两个动作集。
#: `_NODE_ACTIONS` 是「没有目标就必须追问」的那一组；`active_node_id` 只在这组里兜底
#: —— reorder / add 的目标语义不同（「当前页和下一页交换」要两个 id），强行套用只会改错。
_NODE_ACTIONS = ("simplify", "expand", "delete", "rewrite")

#: 指示代词。老师说「这页」时，所指由 UI 选中决定，不让模型猜。
_DEICTIC_TERMS = ("这页", "这一页", "本页", "当前页", "这张", "此页")


def build_modify_intent_schema() -> dict[str, Any]:
    """结构化输出的 JSON Schema（chat_with_schema ①级约束）。"""
    return {
        "name": "modify_intent",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "target_type": {"type": "string", "enum": list(TARGET_TYPES)},
                "target_ids": {"type": "array", "items": {"type": "string"}},
                "target_element_ids": {"type": "array", "items": {"type": "string"}},
                "action": {
                    "type": "string",
                    "enum": list(MODIFY_ACTIONS),
                },
                # 复合指令（"减少文字，增加案例"）会解析出一个主 action + 次要动作
                "secondary_actions": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(MODIFY_ACTIONS)},
                },
                "constraints": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
                "clarification_needed": {"type": "boolean"},
                "clarification_question": {"type": "string"},
                "risk_level": {"type": "string", "enum": ["low", "high"]},
                "confirmation_required": {"type": "boolean"},
                "presentation": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "template_id": {"type": "string"},
                        "palette": {"type": "string"},
                        "layout": {"type": "string"},
                        "font_family": {"type": "string"},
                        "density": {"type": "string"},
                    },
                    "required": ["template_id", "palette", "layout", "font_family", "density"],
                },
            },
            "required": [
                "target_type",
                "target_ids",
                "target_element_ids",
                "action",
                "secondary_actions",
                "constraints",
                "confidence",
                "clarification_needed",
                "clarification_question",
                "risk_level",
                "confirmation_required",
                "presentation",
            ],
        },
    }


_SYSTEM_PROMPT = """你是课件修改指令解析器。教师会用自然语言描述对课件的修改意图，你把它解析为结构化操作。

规则：
1. target_type：node=针对具体节点/页面；global=影响整个课件；style=纯样式调整；page 同 node（历史兼容）。
2. target_ids：从提供的大纲快照中选出目标 node_id（如 node_3）。全局/样式类指令填 []。
3. action（7 选 1，主动作）：
   - simplify: 精简内容（减少文字/简化表述/拆分复杂页面）
   - expand: 扩充内容（增加案例/补充细节/加深讲解）
   - delete: 删除节点
   - add: 新增节点
   - reorder: 调整顺序（换位置/移动到前后）
   - restyle: 换样式（配色/风格/字体/布局，不改变事实内容）
   - rewrite: 重写（大改表述但保持要点）
4. secondary_actions：复合指令的次要动作（如"减少文字，增加案例"主 simplify 次 expand）。
5. constraints：教师给出的约束（保留什么/必须包含什么/风格倾向）。
6. confidence：0~1，指令含糊（无明确目标/互相矛盾）时给低分。
7. clarification_needed：confidence 不足或存在歧义时为 true，并给 clarification_question（一句追问）。
8. presentation：只有 restyle 时填写样式层字段；不确定的字段返回空字符串，禁止修改正文内容。
9. 指令里出现「这页 / 本页 / 当前页 / 这张 / 此页」这类指示代词时，target_ids 必须是**教师当前选中的页面**（在下面的用户消息里给出）。选中页为空时才按上下文推断。

判断示例：
- "第三页太复杂，减少文字，增加一个生活案例" → target=node_3, action=simplify, secondary=[expand], constraints=["增加生活案例"]
- "把第二部分和第三部分换一下" → action=reorder, target_ids=[node_2, node_3]
- "整体风格换成科技感" → target_type=style, action=restyle, constraints=["科技感"]
- "删掉练习那页" → action=delete, 目标为含"练习"的节点
- "这页讲得不清楚，重新写" → action=rewrite, target_ids=[教师当前选中的页面]
"""


def _resolve_active_target(
    instruction: str,
    target_ids: list[str],
    action: str,
    target_type: str,
    active_node_id: str,
    valid_ids: set[str],
) -> list[str]:
    """让「这页」有所指：命中时用界面选中页覆盖模型的猜测。

    两种命中方式，都只在 `_NODE_ACTIONS` 那组动作上生效：

      1. 指令里出现指示代词（「这页」）→ 直接采纳选中页。模型看到的只有标题和摘要，
         让它去猜「这页」是哪页，本来就是件它无从知道的事。
      2. 模型没定位到任何页 → 用选中页兜底，不再回一句「请说明是哪一页」。
         选中页是教师刚刚用手指点的，比追问更接近他的意思。

    显式页号（「第三页」）不带指示代词，因此不受影响：模型选中了谁就是谁。
    """
    if action not in _NODE_ACTIONS or target_type not in ("node", "page"):
        return target_ids
    active = str(active_node_id or "").strip()
    if not active or active not in valid_ids:
        # 未选中或选中页已不在当前节点树里（换过版本/删过页）→ 退回模型结果
        return target_ids
    if any(term in (instruction or "") for term in _DEICTIC_TERMS):
        return [active]
    return target_ids or [active]


class ModifyIntentParser:
    """解析教师的自然语言修改指令。"""

    def __init__(self) -> None:
        self._llm: LLMClient | None = None

    def _get_llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient(
                model=getattr(settings, "MODEL", None),
                temperature=getattr(settings, "TEMPERATURE", 0.1),
                # 意图解析是修改链路的前置门槛。一次结构化请求失败后，
                # 由前端重试更可控，避免“单次 120 秒 + SDK/客户端重试”
                # 超过 Go 网关等待窗口。
                timeout=resolve_llm_timeout(),
                max_attempts=1,
                disable_sdk_retries=True,
            )
        return self._llm

    def parse(self, instruction: str, nodes: list[dict[str, Any]], active_node_id: str = "") -> dict[str, Any]:
        """解析修改指令。

        Args:
            instruction: 教师的自然语言修改指令。
            nodes: 当前大纲/内容快照。
            active_node_id: 教师界面上当前选中的页面。老师说「这页」时用它定位，
                不再依赖模型从标题里猜 —— 没有它，「这页加个例子」只会得到一句追问。

        Returns:
            {target_type, target_ids, action, secondary_actions,
             constraints, confidence, clarification_needed, clarification_question}
        """
        if not instruction or not instruction.strip():
            return self._clarify("请描述你想要的修改，例如“第三页减少文字”。")

        element_snapshot = build_element_snapshot(nodes or [])
        candidate_result = resolve_element_candidates(instruction, element_snapshot)
        if candidate_result["status"] == "ambiguous":
            return self._clarify_candidates(candidate_result["candidates"])

        nodes_brief = json.dumps(
            [
                {
                    "node_id": n.get("node_id", ""),
                    "title": n.get("title", ""),
                    "summary": n.get("summary", ""),
                    "node_type": n.get("node_type", "content"),
                    "order": n.get("order", i + 1),
                    "elements": [
                        {
                            "element_id": e.get("element_id"),
                            "element_type": e.get("element_type"),
                            "role": e.get("role"),
                            "position": (e.get("geometry") or {}).get("position", ""),
                            "content_preview": str(e.get("content", ""))[:120],
                        }
                        for e in (n.get("metadata") or {}).get("elements", [])
                    ],
                }
                for i, n in enumerate(nodes or [])
            ],
            ensure_ascii=False,
        )

        active = str(active_node_id or "").strip()
        user_prompt = (
            f"大纲快照（{len(nodes or [])} 个节点）：\n{nodes_brief}\n\n"
            f"教师当前选中的页面：{active or '（未选中）'}\n\n"
            f"教师修改指令：{instruction}"
        )

        try:
            result = self._get_llm().chat_with_schema(
                _SYSTEM_PROMPT,
                user_prompt,
                build_modify_intent_schema(),
                temperature=0.1,
            )
        except Exception as exc:  # LLM 整体不可用 → 走澄清而非崩溃
            logger.warning("[parse_modify] LLM 调用失败: %s", exc)
            return self._clarify("AI 服务暂不可用，请稍后重试或换一种说法。")

        return self._normalize(result, element_snapshot, candidate_result, active, instruction)

    # ------------------------------------------------------------------

    @staticmethod
    def _clarify(question: str) -> dict[str, Any]:
        return {
            "target_type": "global",
            "target_ids": [],
            "target_element_ids": [],
            "action": "rewrite",
            "secondary_actions": [],
            "constraints": [],
            "confidence": 0.0,
            "clarification_needed": True,
            "clarification_question": question,
            "risk_level": "low",
            "confirmation_required": False,
            "candidates": [],
            "presentation": {key: "" for key in ("template_id", "palette", "layout", "font_family", "density")},
        }

    @staticmethod
    def _normalize_presentation(value: Any, action: str) -> dict[str, str]:
        """只允许呈现层字段通过边界，避免把自然语言样式指令混入正文。"""
        keys = ("template_id", "palette", "layout", "font_family", "density")
        if action != "restyle" or not isinstance(value, dict):
            return {key: "" for key in keys}
        return {key: str(value.get(key) or "").strip() for key in keys}

    @staticmethod
    def _clarify_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
        labels = [
            f"第{item.get('page_number')}页{item.get('role')}（{item.get('content_preview') or '无文本'}）"
            for item in candidates[:5]
        ]
        return {
            **ModifyIntentParser._clarify("请明确要修改哪一个元素：" + "、".join(labels)),
            "candidates": candidates,
        }

    def _normalize(self, result: Any, nodes: list[dict[str, Any]],
                   candidate_result: dict[str, Any] | None = None,
                   active_node_id: str = "", instruction: str = "") -> dict[str, Any]:
        """LLM 返回容错归一：非 dict / 枚举外值 / 越界 node_id 收敛到安全值。"""
        if not isinstance(result, dict):
            return self._clarify("指令解析失败，请换一种说法（例如“第三页减少文字”）。")

        action = result.get("action")
        if action not in MODIFY_ACTIONS:
            action = "rewrite"

        target_type = result.get("target_type")
        if target_type not in TARGET_TYPES:
            target_type = "node" if action != "restyle" else "style"
        if action == "restyle" and target_type != "style":
            # restyle 语义上就是样式层
            target_type = "style"

        valid_ids = {str(n.get("node_id", "")) for n in nodes if n.get("node_id")}
        element_map = {
            str(e.get("element_id")): str(e.get("page_id"))
            for n in nodes
            for e in (n.get("metadata") or {}).get("elements", [])
            if e.get("element_id") and e.get("page_id")
        }
        target_ids = [
            str(t) for t in (result.get("target_ids") or []) if str(t) in valid_ids
        ]
        target_element_ids = [
            str(t) for t in (result.get("target_element_ids") or [])
            if str(t) in element_map
        ]
        if not target_element_ids and candidate_result and candidate_result.get("status") == "resolved":
            target_element_ids = list(candidate_result.get("target_element_ids") or [])
        if target_element_ids and not target_ids:
            target_ids = list(dict.fromkeys(element_map[item] for item in target_element_ids if item in element_map))
        target_ids = _resolve_active_target(
            instruction, target_ids, action, target_type, active_node_id, valid_ids
        )
        # 节点类动作但没定位到合法 id → 需要澄清
        if action in _NODE_ACTIONS and target_type in ("node", "page") and not target_ids:
            return self._clarify("没有定位到要修改的节点，请说明是哪一页（例如“第三页”）。")

        secondary = [a for a in (result.get("secondary_actions") or []) if a in MODIFY_ACTIONS and a != action]
        constraints = [str(c) for c in (result.get("constraints") or []) if str(c).strip()]

        try:
            confidence = float(result.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        clarification_needed = bool(result.get("clarification_needed")) or confidence < CONFIDENCE_THRESHOLD
        question = str(result.get("clarification_question") or "").strip()
        risk_level = str(result.get("risk_level") or "low")
        if risk_level not in {"low", "high"}:
            risk_level = "low"
        if action in {"delete", "add", "reorder", "restyle"} or target_element_ids and any(
            item.get("element_type") in {"image", "chart", "shape"}
            for item in (candidate_result or {}).get("candidates", [])
            if item.get("element_id") in target_element_ids
        ):
            risk_level = "high"
        confirmation_required = bool(result.get("confirmation_required")) or risk_level == "high"

        return {
            "target_type": target_type,
            "target_ids": target_ids,
            "target_element_ids": target_element_ids,
            "action": action,
            "secondary_actions": secondary,
            "constraints": constraints,
            "confidence": confidence,
            "clarification_needed": clarification_needed,
            "clarification_question": question,
            "risk_level": risk_level,
            "confirmation_required": confirmation_required,
            "candidates": (candidate_result or {}).get("candidates", []),
            "presentation": self._normalize_presentation(result.get("presentation"), action),
        }
