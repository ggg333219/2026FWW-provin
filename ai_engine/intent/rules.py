"""S1 共享规则提取器。

规则既服务 IntentEngine fallback，也服务 LLMClient mock，避免两条链路行为漂移。
所有提取都遵循“教师最后一次明确表达优先”，以支持确认前字段纠错。
"""

from __future__ import annotations

import re
from collections.abc import Iterable


_CLAUSE_END = r"(?=[；;。！？!?\n]|$)"


def _last_match(text: str, patterns: Iterable[str], flags: int = 0) -> str | None:
    matches: list[tuple[int, str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags):
            value = (match.group(1) or "").strip()
            if value:
                matches.append((match.start(), value))
    if not matches:
        return None
    return max(matches, key=lambda item: item[0])[1]


def _clean_phrase(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"^[：:\s]+|[，,。；;：:\s]+$", "", value)
    return cleaned or None


def extract_duration(text: str) -> int | None:
    candidates: list[tuple[int, int]] = []
    patterns = [
        r"(?:授课时长|讲课时间|课程时长|课堂时长|时长|课时)(?:是|为|约|大约|[:：])?\s*(\d{1,3})(?:\s*分钟)?",
        r"(\d{1,3})\s*分钟",
        r"(\d{1,3})\s*min(?:ute)?s?\b",
        r"(?:^|[。；;\n])\s*(\d{1,3})\s*(?=[。；;\n]|$)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            value = int(match.group(1))
            if 5 <= value <= 300:
                candidates.append((match.start(), value))

    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*小时", text):
        value = int(float(match.group(1)) * 60)
        if 5 <= value <= 300:
            candidates.append((match.start(), value))
    for match in re.finditer(r"半小时", text):
        candidates.append((match.start(), 30))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def extract_topic(text: str) -> str | None:
    explicit = _last_match(text, [
        rf"(?:课程主题|教学主题|主题)\s*(?:是|为|[:：])\s*([^；;。！？!?\n]+){_CLAUSE_END}",
    ])
    if explicit:
        return _clean_phrase(re.sub(r"(?:课件|课程|一节课|的课)$", "", explicit))

    about = _last_match(text, [
        r"关于\s*([\u4e00-\u9fa5A-Za-z0-9+\-]{2,40}?)(?:的)?(?:课件|课程|课|讲稿|讲解|教学)(?=[，,。；;！？!?]|$)",
    ])
    if about:
        return _clean_phrase(about)

    request = _last_match(text, [
        r"(?:帮我做|帮我准备|请设计|设计|准备|我想做|我想要|我需要|需要|请给我|来一份)"
        r"(?:一份|一节)?(?:\d+\s*分钟)?(?:的)?(?:关于)?"
        r"([\u4e00-\u9fa5A-Za-z0-9+\-]{2,40}?)"
        r"(?:的)?(?:课件|课程|课|讲稿|讲解|教学)(?=[，,。；;！？!?]|$)",
    ])
    if request:
        return _clean_phrase(re.sub(r"\d+\s*分钟", "", request))

    cleaned = re.sub(r"(?:请帮我|帮我|请|麻烦|做一份|做一节|我要|我需要)", "", text)
    cleaned = re.sub(r"(?:课件|课程|一节|一份|的课|讲稿)", "", cleaned)
    cleaned = re.split(r"[，,。；;]", cleaned.strip())[0]
    cleaned = re.sub(r"^\d+\s*分钟(?:的)?", "", cleaned)
    return _clean_phrase(cleaned[:80])


def extract_target_student(text: str) -> str | None:
    return _clean_phrase(_last_match(text, [
        rf"(?:授课对象|教学对象|面向对象)\s*(?:是|为|[:：])\s*([^；;。！？!?\n]+){_CLAUSE_END}",
        r"(?:面向|适合)\s*([^，,。；;！？!?\n]+?(?:学生|学员|教师|儿童|成人))(?=[，,。；;！？!?]|$)",
        r"(?:我想)?给\s*([^，,。；;！？!?\n]+?(?:学生|学员|教师|儿童|成人))\s*(?:做|上|讲|准备|设计)",
    ]))


def extract_style(text: str) -> str | None:
    explicit = _last_match(text, [
        rf"(?:教学风格|授课风格)\s*(?:是|为|[:：])\s*([^；;。！？!?\n]+){_CLAUSE_END}",
        r"风格\s*(?:是|为|[:：])?\s*([^，,。；;！？!?\n]+)",
        r"采用\s*([^，,。；;！？!?\n]+?)(?:的)?(?:方式|风格|教学法)(?=[，,。；;！？!?]|$)",
    ])
    if explicit:
        return _clean_phrase(re.sub(r"(?:一点|一些|的方式|的风格)$", "", explicit.strip()))
    known = list(re.finditer(
        r"讲练结合|案例分析|案例驱动|项目式|项目制|理论为主|探究式|讨论式|翻转课堂|课堂测验|沉浸式",
        text,
    ))
    return known[-1].group(0) if known else None


def extract_knowledge_points(text: str) -> list[str]:
    raw = _last_match(text, [
        rf"(?:核心知识点|知识点)\s*(?:是|为|包括|包含|[:：])\s*([^；;。！？!?\n]+){_CLAUSE_END}",
        rf"(?:重点包括|重点包含|重点讲解|包括|包含|涉及|涵盖)\s*([^；;。！？!?\n]+){_CLAUSE_END}",
    ])
    if not raw:
        return []
    raw = re.split(r"(?:，|,)?\s*(?:并|同时|另外|此外|最好)(?:加入|安排|设置|设计|增加|配合)", raw, maxsplit=1)[0]
    items = re.split(r"[、，,；;]|和|与", raw)
    result: list[str] = []
    for item in items:
        cleaned = _clean_phrase(item)
        if not cleaned:
            continue
        cleaned = re.sub(r"^(?:重点|主要|核心)", "", cleaned).strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result[:12]


def detect_interactive(text: str) -> bool:
    overrides = list(re.finditer(
        rf"互动设计\s*(?:是|为|[:：])\s*([^；;。！？!?\n]+){_CLAUSE_END}",
        text,
    ))
    if overrides:
        value = overrides[-1].group(1).strip()
        if re.search(r"不需要|不要|关闭|无需|否", value):
            return False
        if re.search(r"需要|开启|要|是", value):
            return True
    return bool(re.search(r"互动|练习|测验|小测|讨论|问答|翻卡|闪卡|动画演示|角色扮演", text))


def extract_output_formats(text: str) -> list[str]:
    result: list[str] = []
    if re.search(r"PPT|ppt|幻灯|课件", text):
        result.append("ppt")
    if re.search(r"Word|word|DOCX|docx|教案|讲义|讲稿", text):
        result.append("doc")
    return result or ["ppt"]
