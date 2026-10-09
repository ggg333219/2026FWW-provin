"""
互动内容构建模块 — S3 课件生成

职责：
  根据节点内容生成课堂互动素材：测验题、投票、闪卡、讨论题

流程：
  节点内容 → interactive_builder → 互动素材列表（可嵌入 PPT/独立导出）

LLM 调用：
  统一通过 core.llm.LLMClient，构造函数可注入 llm_client 供测试用。
"""

import json
from dataclasses import dataclass
from typing import Any, Optional

from ..core.llm import LLMClient


@dataclass
class InteractiveConfig:
    """互动内容配置"""
    model: str = ""
    temperature: float = 0.3


class InteractiveBuilder:
    """根据节点内容生成课堂互动素材"""

    def __init__(self, config: InteractiveConfig | None = None, llm_client: Optional[LLMClient] = None):
        self.config = config or InteractiveConfig()
        self._llm = llm_client  # 可注入，供测试用

    def build_quiz(self, node: dict[str, Any], *, mode: str = "llm") -> list[dict[str, Any]]:
        """生成测验题"""
        title = node.get("title", "知识点")
        content = node.get("script") or node.get("content") or node.get("summary") or ""
        questions = node.get("interactive_questions") or []
        if questions:
            return [{"type": "quiz", "title": title, "questions": questions, "source": "node"}]
        if str(mode or "llm").strip().lower() == "mock":
            return self._fallback_quiz(title, content)
        # LLM 生成
        try:
            result = self._get_llm().chat_json(
                system="你是一个课堂测验生成助手。",
                user=(
                    f"根据以下内容生成2-3道课堂测验题。输出JSON格式:\n"
                    f'{{"questions": [{{"question": "...", "options": ["A", "B", "C", "D"], "answer": "A", "explanation": "..."}}]}}\n\n'
                    f"标题: {title}\n内容: {content[:1500]}"
                ),
                temperature=self.config.temperature,
            )
            return [{"type": "quiz", "title": title,
                     "questions": result.get("questions", []), "source": "llm"}]
        except Exception:
            return self._fallback_quiz(title, content)

    def _get_llm(self) -> LLMClient:
        if self._llm is not None:
            return self._llm
        return LLMClient(temperature=self.config.temperature, model=self.config.model or None)

    def build_flashcards(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        """生成知识闪卡"""
        segments = node.get("segments") or []
        if segments:
            cards = []
            for seg in segments:
                kc = seg.get("knowledge_card") or {}
                if kc.get("term"):
                    cards.append({"type": "flashcard", "front": kc["term"],
                                  "back": kc.get("definition", ""), "tags": kc.get("tags", [])})
            if cards:
                return cards
        return self._fallback_flashcards(node.get("title", "知识点"),
                                         node.get("script") or node.get("summary") or "")

    def build_vote(self, node: dict[str, Any]) -> dict[str, Any] | None:
        """生成课堂投票题（适用于有争议/需要判断的节点）"""
        title = node.get("title", "")
        if any(kw in title for kw in ["投票", "选择", "判断", "你对"]):
            return {
                "type": "vote",
                "title": f"投票: {title}",
                "question": f"你对「{title}」的理解是?",
                "options": ["完全掌握", "基本理解", "有些模糊", "需要重讲"],
            }
        return None

    def build_all(self, node: dict[str, Any], *, mode: str = "llm") -> list[dict[str, Any]]:
        """一键生成该节点所有互动物料"""
        items = []
        plan = node.get("interactive_plan") or {}
        kind = str(plan.get("kind") or "").strip().lower()
        if kind == "flashcard":
            items.extend(self.build_flashcards(node))
        else:
            items.extend(self.build_quiz(node, mode=mode))
            if kind == "":
                items.extend(self.build_flashcards(node))
        return items

    def _fallback_quiz(self, title: str, content: str) -> list[dict[str, Any]]:
        return [{
            "type": "quiz", "title": title, "source": "fallback",
            "questions": [
                {"question": f"关于「{title}」的核心概念是什么？",
                 "options": ["理解正确", "理解偏差", "完全无关", "以上都不是"],
                 "answer": "A", "explanation": f"「{title}」是本节的核心知识点。"},
            ],
        }]

    def _fallback_flashcards(self, title: str, content: str) -> list[dict[str, Any]]:
        return [{"type": "flashcard", "front": title,
                 "back": content[:200] if content else f"关于{title}的核心知识", "tags": ["core"]}]
