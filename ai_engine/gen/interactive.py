"""
互动内容构建模块 — S3 课件生成

职责：
  根据节点内容生成课堂互动素材：测验题、投票、闪卡、讨论题

流程：
  节点内容 → interactive_builder → 互动素材列表（可嵌入 PPT/独立导出）
"""

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class InteractiveConfig:
    """互动内容配置"""
    model: str = ""
    temperature: float = 0.3


class InteractiveBuilder:
    """根据节点内容生成课堂互动素材"""

    def __init__(self, config: InteractiveConfig | None = None):
        self.config = config or InteractiveConfig()

    def build_quiz(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        """生成测验题"""
        title = node.get("title", "知识点")
        content = node.get("script") or node.get("content") or node.get("summary") or ""
        questions = node.get("interactive_questions") or []
        if questions:
            return [{"type": "quiz", "title": title, "questions": questions, "source": "node"}]
        # LLM 生成
        from openai import OpenAI
        api_key = os.getenv("AI_API_KEY")
        if not api_key:
            return self._fallback_quiz(title, content)
        model = self.config.model or os.getenv("AI_MODEL", "qwen-turbo")
        client = OpenAI(api_key=api_key)
        prompt = (
            f"根据以下内容生成2-3道课堂测验题。输出JSON: "
            f'{{"questions": [{{"question": "...", "options": ["A", "B", "C", "D"], "answer": "A", "explanation": "..."}}]}}\n\n'
            f"标题: {title}\n内容: {content[:1500]}"
        )
        try:
            resp = client.chat.completions.create(
                model=model, temperature=self.config.temperature,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            return [{"type": "quiz", "title": title, "questions": data.get("questions", []), "source": "llm"}]
        except Exception:
            return self._fallback_quiz(title, content)

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

    def build_all(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        """一键生成该节点所有互动物料"""
        items = []
        quiz = self.build_quiz(node)
        items.extend(quiz)
        cards = self.build_flashcards(node)
        items.extend(cards)
        vote = self.build_vote(node)
        if vote:
            items.append(vote)
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
