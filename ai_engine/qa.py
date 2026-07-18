import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_COMPAT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 三态理解程度枚举
UNDERSTANDING_NONE = "none"
UNDERSTANDING_PARTIAL = "partial"
UNDERSTANDING_FULL = "full"

RETEACH_KEYWORDS = ["听不懂", "不懂", "太难", "没明白", "再讲", "换个说法", "举例", "不太会"]


def resolve_llm_base_url(model: str) -> tuple[str, str]:
    raw_base_url = (os.getenv("AI_BASE_URL") or "").strip()
    if raw_base_url:
        parsed = urlparse(raw_base_url)
        host = (parsed.netloc or parsed.path).lower()
        if "example.com" not in host:
            return raw_base_url, ""
        reason = "placeholder_base_url"
    else:
        reason = ""

    if (model or "").strip().lower().startswith("gpt-"):
        return DEFAULT_OPENAI_BASE_URL, reason
    return DEFAULT_COMPAT_BASE_URL, reason


@dataclass
class QAConfig:
    mode: str = "llm"  # 默认使用真实模型
    model: str = os.getenv("AI_MODEL", "qwen-turbo")
    temperature: float = 0.2


class QAResponder:
    """问答溯源 + 案例重讲响应器。"""

    def __init__(self, parsed_document: dict[str, Any], config: QAConfig | None = None):
        self.parsed_document = parsed_document
        self.config = config or QAConfig(
            mode=os.getenv("AI_GEN_MODE", "llm"),
            model=os.getenv("AI_MODEL", "qwen-turbo"),
            temperature=float(os.getenv("AI_TEMPERATURE", "0.2")),
        )
        self.page_map = {
            item["page"]: item.get("content", "")
            for item in self.parsed_document.get("parsed_pages", [])
            if "page" in item
        }

    def answer(self, question: str, current_page: int, history_summary: str = "", recent_turns: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        source_page = self._resolve_source_page(current_page)
        source_content = self.page_map.get(source_page, "")
        recent_turns = recent_turns or []

        understanding = self._predict_understanding(question, source_content, history_summary)
        need_reteach = understanding in (UNDERSTANDING_NONE, UNDERSTANDING_PARTIAL)
        answer_text, used_fallback, fallback_reason = self._llm_answer(question, source_page, source_content, need_reteach, history_summary, recent_turns)

        resume_page, resume_node_id, resume_sec = self._resolve_resume_strategy(source_page, understanding, current_page)

        return {
            "question": question,
            "source_page": source_page,
            "source_excerpt": source_content[:160].strip(),
            "intent": {
                "need_reteach": need_reteach,
                "understanding_level": understanding,
                "reason": "llm_prediction",
            },
            "answer": answer_text,
            "used_fallback": used_fallback,
            "fallback_reason": fallback_reason,
            "resume_page": resume_page,
            "resume_node_id": resume_node_id,
            "resume_sec": resume_sec,
            "follow_up_suggestion": self._make_followup_suggestion(question, need_reteach, source_page),
        }

    def _predict_understanding(self, question: str, source_content: str, history_summary: str) -> str:
        api_key = os.getenv("AI_API_KEY")
        if not api_key:
            return UNDERSTANDING_PARTIAL if (any(kw in question.lower() for kw in RETEACH_KEYWORDS)) else UNDERSTANDING_FULL
        try:
            from openai import OpenAI
            base_url, _ = resolve_llm_base_url(self.config.model)
            client = OpenAI(api_key=api_key, base_url=base_url)
            resp = client.chat.completions.create(
                model=self.config.model, temperature=0.1,
                messages=[
                    {"role": "system", "content": "你是教学助手的意图分析模块。只返回JSON: {\"understanding_level\": \"none|partial|full\"}\n- none: 听不懂/要求重讲\n- partial: 有具体疑点需补充\n- full: 理解正确可推进"},
                    {"role": "user", "content": f"问题: {question}\n内容: {source_content[:400]}\n历史: {history_summary[:200] or '无'}\n输出JSON。"}
                ],
                response_format={"type": "json_object"}
            )
            raw = resp.choices[0].message.content
            data = json.loads(raw)
            level = str(data.get("understanding_level", UNDERSTANDING_PARTIAL)).strip().lower()
            if level in (UNDERSTANDING_NONE, UNDERSTANDING_PARTIAL, UNDERSTANDING_FULL):
                return level
        except Exception:
            pass
        return UNDERSTANDING_PARTIAL if (any(kw in question.lower() for kw in RETEACH_KEYWORDS)) else UNDERSTANDING_FULL

    def _resolve_resume_strategy(self, source_page: int, understanding: str, current_page: int) -> tuple:
        if understanding == UNDERSTANDING_FULL:
            return source_page + 1, f"p{source_page+1}_n1", 0
        if understanding == UNDERSTANDING_PARTIAL:
            return source_page, f"p{source_page}_n1", max((current_page - 1) * 15, 5)
        return source_page, f"p{source_page}_n1", 0

    def _resolve_source_page(self, current_page: int) -> int:
        if current_page in self.page_map:
            return current_page
        if not self.page_map:
            return 1
        nearest = min(self.page_map.keys(), key=lambda page: abs(page - current_page))
        return nearest

    @staticmethod
    def _need_reteach(question: str) -> bool:
        q = question.strip().lower()
        return any(keyword in q for keyword in RETEACH_KEYWORDS)

    def _llm_answer(self, question: str, source_page: int, source_content: str, need_reteach: bool, history_summary: str, recent_turns: list[dict[str, Any]]) -> tuple[str, bool, str]:
        try:
            from openai import OpenAI
        except ImportError as error:
            reason = f"missing_openai:{error}"
            return self._fallback_answer(question, source_content, need_reteach, reason), True, reason

        api_key = os.getenv("AI_API_KEY")
        if not api_key:
            reason = "missing_api_key"
            return self._fallback_answer(question, source_content, need_reteach, reason), True, reason

        base_url, _ = resolve_llm_base_url(self.config.model)
        client = OpenAI(api_key=api_key, base_url=base_url)

        role_desc = "高校专业课老师" if not need_reteach else "善于举例的耐心导师"
        system_prompt = (
            f"你是{role_desc}，必须使用苏格拉底式启发教学。"
            "严禁直接给最终答案，先澄清学生卡点，再逐步引导。"
            "每次输出必须遵守："
            "1) 先用一句话确认学生问题；"
            "2) 提一个引导问题；"
            "3) 给不超过两句的提示或类比；"
            "4) 以问题结尾，推动学生继续思考。"
            "禁止出现“标准答案是”这类直接给结论的话术。"
        )
        
        user_prompt = (
            f"学生问题: {question}\n"
            f"当前文档第 {source_page} 页参考内容: {source_content}\n"
            f"是否需要重讲(Reteach): {need_reteach}\n"
            f"历史对话摘要: {history_summary or '无'}\n"
            f"最近几轮问答: {self._format_recent_turns(recent_turns)}\n"
            "请按苏格拉底法给出启发式回应。"
            "如果学生的问题明显承接上一轮，请主动沿用历史上下文，不要把它当作全新问题。"
        )

        try:
            response = client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.config.temperature
            )
            return response.choices[0].message.content, False, ""
        except Exception as e:
            reason = str(e)
            return self._fallback_answer(question, source_content, need_reteach, reason), True, reason

    def _fallback_answer(self, question: str, source_content: str, need_reteach: bool, reason: str) -> str:
        lines = [line.strip() for line in re.split(r"[\n。；;]", source_content or "") if line.strip()]
        preview = "；".join(lines[:3]) if lines else "当前页缺少足够上下文，建议教师补充讲稿或原文。"
        if need_reteach:
            return (
                f"我理解你现在卡在“{question}”，我们先不急着看答案。"
                f"先想一想：在这页内容“{preview}”里，你觉得最难的是概念、步骤，还是公式代入？"
                "提示你一个思路：先说出你已确定的一步，再补上下一步会容易很多。你想先从哪一步开始？"
            )
        return (
            f"你这个问题很好，我们先聚焦“{question}”对应的关键线索：{preview}。"
            "先回答我一个小问题：你现在更不确定“为什么这样做”，还是“不知道下一步做什么”？"
            f"提示：把问题拆成“已知-目标-第一步”三段会更清晰。你愿意先说说你的第一步吗？（兜底模式：{reason}）"
        )

    def _make_followup_suggestion(self, question: str, need_reteach: bool, source_page: int) -> str:
        """生成更贴近实际的后续操作建议（用于前端展示给学生选择）。"""
        if need_reteach:
            return (
                "我可以：1) 用更生活化的例子重新解释；"
                "2) 按步骤分解并配上简短练习；"
                "3) 给出一个可操作的小实验/图示帮助理解。你想先听哪个？"
            )

        # 对于正常提问，给出更具体的后续选项
        return (
            "我可以：1) 展开详细原理与推导；"
            "2) 给出一个相关的真实例子或应用场景；"
            "3) 把相关页的要点串成一份简短笔记。请选择你想要的方式。"
        )

    @staticmethod
    def _format_recent_turns(recent_turns: list[dict[str, Any]]) -> str:
        if not recent_turns:
            return "无"

        parts = []
        for index, turn in enumerate(recent_turns[-4:], start=1):
            question = str(turn.get("question", "")).strip()
            answer = str(turn.get("answer", "")).strip()
            page = turn.get("page")
            prefix = f"第{index}轮"
            if page:
                prefix += f"(第{page}页)"
            parts.append(f"{prefix} 学生：{question} AI：{answer}")
        return "\n".join(parts)
        

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json\n", "", 1).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("模型返回内容中未找到有效 JSON")
        return json.loads(cleaned[start : end + 1])
