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

from core.config import get_settings
from core.llm import LLMClient

logger = logging.getLogger(__name__)

# 动作枚举（与 Go 侧 / 前端面板共用语义）
MODIFY_ACTIONS = ("simplify", "expand", "delete", "add", "reorder", "restyle", "rewrite")
TARGET_TYPES = ("node", "page", "global", "style")
CONFIDENCE_THRESHOLD = 0.6


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
            },
            "required": [
                "target_type",
                "target_ids",
                "action",
                "secondary_actions",
                "constraints",
                "confidence",
                "clarification_needed",
                "clarification_question",
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

判断示例：
- "第三页太复杂，减少文字，增加一个生活案例" → target=node_3, action=simplify, secondary=[expand], constraints=["增加生活案例"]
- "把第二部分和第三部分换一下" → action=reorder, target_ids=[node_2, node_3]
- "整体风格换成科技感" → target_type=style, action=restyle, constraints=["科技感"]
- "删掉练习那页" → action=delete, 目标为含"练习"的节点
- "这页讲得不清楚，重新写" → action=rewrite
"""


class ModifyIntentParser:
    """解析教师的自然语言修改指令。"""

    def __init__(self) -> None:
        self._llm: LLMClient | None = None

    def _get_llm(self) -> LLMClient:
        if self._llm is None:
            settings = get_settings()
            self._llm = LLMClient(settings.llm)
        return self._llm

    def parse(self, instruction: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        """解析修改指令。

        Returns:
            {target_type, target_ids, action, secondary_actions,
             constraints, confidence, clarification_needed, clarification_question}
        """
        if not instruction or not instruction.strip():
            return self._clarify("请描述你想要的修改，例如“第三页减少文字”。")

        nodes_brief = json.dumps(
            [
                {
                    "node_id": n.get("node_id", ""),
                    "title": n.get("title", ""),
                    "summary": n.get("summary", ""),
                    "node_type": n.get("node_type", "content"),
                    "order": n.get("order", i + 1),
                }
                for i, n in enumerate(nodes or [])
            ],
            ensure_ascii=False,
        )

        user_prompt = (
            f"大纲快照（{len(nodes or [])} 个节点）：\n{nodes_brief}\n\n"
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

        return self._normalize(result, nodes or [])

    # ------------------------------------------------------------------

    @staticmethod
    def _clarify(question: str) -> dict[str, Any]:
        return {
            "target_type": "global",
            "target_ids": [],
            "action": "rewrite",
            "secondary_actions": [],
            "constraints": [],
            "confidence": 0.0,
            "clarification_needed": True,
            "clarification_question": question,
        }

    def _normalize(self, result: Any, nodes: list[dict[str, Any]]) -> dict[str, Any]:
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
        target_ids = [
            str(t) for t in (result.get("target_ids") or []) if str(t) in valid_ids
        ]
        # 节点类动作但没定位到合法 id → 需要澄清
        if action in ("simplify", "expand", "delete", "rewrite") and target_type in ("node", "page") and not target_ids:
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

        return {
            "target_type": target_type,
            "target_ids": target_ids,
            "action": action,
            "secondary_actions": secondary,
            "constraints": constraints,
            "confidence": confidence,
            "clarification_needed": clarification_needed,
            "clarification_question": question,
        }
