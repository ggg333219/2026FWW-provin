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


# 意图字段标签：形如「互动设计：需要」「授课对象：…」的子句描述的是**别的字段**，
# 不是知识点。规则抽取知识点时若不剔除，会把这类子句混进知识点列表。
_FIELD_CLAUSE_LABELS = (
    "互动设计", "教学风格", "授课风格", "讲课风格", "授课对象", "教学对象",
    "核心知识点", "知识点", "重点难点", "学习目标", "预期成果", "预期学习成果",
    "输出格式", "授课时长", "课程时长", "课程主题", "教学主题", "难点", "目标", "主题",
)

_FIELD_CLAUSE_PATTERN = re.compile(
    r"^(?:" + "|".join(re.escape(label) for label in _FIELD_CLAUSE_LABELS) + r")\s*[:：]"
)


def is_field_clause(text: str) -> bool:
    """判断文本是否是「其它字段名：值」形式的子句。

    只匹配带冒号的标签形式，避免误伤「代码风格」「面向对象编程」这类正当知识点。
    """
    return bool(_FIELD_CLAUSE_PATTERN.match((text or "").strip()))


# 互动要求类片段：属于「要不要互动」的需求，不是课程内容。
_INTERACTION_FRAGMENT_MARKERS = (
    "互动", "小游戏", "课堂游戏", "小测", "测验", "翻卡", "闪卡",
    "动画演示", "角色扮演", "课堂练习", "抢答",
)


def _normalize_for_match(text: str) -> str:
    """去掉空白与标点，只保留可比对的实义字符。"""
    return re.sub(r"[\s，,。；;：:、！!？?（）()《》〈〉\"'’“”\-—_·]+", "", text or "")


def is_grounded_knowledge_point(point: str, teacher_text: str) -> bool:
    """判断模型给出的知识点是否能在教师原话中找到依据。

    没有依据的知识点多半是模型自行脑补的，必须丢弃；能找到依据的才予以保留。
    """
    normalized_point = _normalize_for_match(point)
    normalized_text = _normalize_for_match(teacher_text)
    if len(normalized_point) < 2:
        return False
    # 教师原话本身包含该知识点 —— 直接判定为有依据。
    if normalized_point in normalized_text:
        return True
    # 反向包含（教师说"分治"，模型给出"分治思想"）只在教师原话足够具体时成立，
    # 否则一句短话（如"45"）会把毫不相关的知识点全部"接地"，等于没校验。
    return len(normalized_text) >= 4 and normalized_text in normalized_point


def filter_knowledge_point_fragments(
    points: Iterable[str],
    style: str | None = None,
    target_student: str | None = None,
) -> list[str]:
    """剔除被模型误当成知识点的碎片。

    三类碎片：

    1. 「其它字段名：值」子句，例如把「互动设计：需要」当成知识点；
    2. 已经作为 style / target_student 抽走的原话被重复塞进知识点，
       例如把「风格活泼一点」当成知识点；
    3. 互动要求类片段，例如把「课堂小游戏」当成知识点。
    """
    style_value = (style or "").strip()
    student_value = (target_student or "").strip()
    result: list[str] = []
    for item in points or []:
        text = str(item).strip()
        if not text:
            continue
        if is_field_clause(text):
            continue
        if len(style_value) >= 2 and (style_value in text or text in style_value):
            continue
        if len(student_value) >= 2 and (student_value in text or text in student_value):
            continue
        if any(marker in text for marker in _INTERACTION_FRAGMENT_MARKERS):
            continue
        result.append(text)
    return result


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


def extract_topic_strict(text: str) -> str | None:
    """只做高置信度的主题抽取（显式标注 / 关于X / 帮我做X课件）。

    与 :func:`extract_topic` 的区别是**不含兜底猜测**：兜底分支靠剥词取首句，
    在"请做45分钟快速排序课件"这类句子上会产出"做45分钟快速排序"这种脏值。

    合并阶段用本函数判断规则结论是否可信：可信才允许覆盖模型结果，
    不可信时保留模型给出的主题。
    """
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
        r"(?:帮我做|帮我准备|请做|请设计|设计|准备|我想做|我想要|我需要|需要|请给我|来一份)"
        r"(?:一份|一节)?(?:\d+\s*分钟)?(?:的)?(?:关于)?"
        r"([\u4e00-\u9fa5A-Za-z0-9+\-]{2,40}?)"
        r"(?:的)?(?:课件|课程|课|讲稿|讲解|教学)(?=[，,。；;！？!?]|$)",
    ])
    if request:
        return _clean_phrase(re.sub(r"\d+\s*分钟", "", request))

    return None


def extract_topic(text: str) -> str | None:
    """抽取课程主题；高置信度抽取失败时退回保守的兜底猜测。"""
    strict = extract_topic_strict(text)
    if strict:
        return strict

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
        # 「互动设计：需要」这类子句描述的是别的字段，不是知识点。
        if is_field_clause(cleaned):
            continue
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
