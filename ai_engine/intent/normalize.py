"""S1 真实模型输出的字段级归一与校验。

背景：模型以 JSON 模式返回自由 JSON（未启用 provider 级 schema 强约束），单个字段
类型不符就足以让 pydantic 的整包校验失败 —— 此时 topic / duration / style /
knowledge_points 会**一起被丢弃**，整体回退规则引擎，且降级原因被记成"模型错误"，
掩盖了真正的问题（只是格式没对齐）。

本模块把"逐字段修复"与"整包丢弃"解耦：

- 能安全归一的字段就地归一（如 ``"45分钟"`` → ``45``、``"需要"`` → ``True``）；
- 无法归一的字段单独丢弃并留下说明，不牵连其它字段；
- 仅当关键字段（主题）仍不可用时，才由调用方判定整包失败并回退规则引擎。

归一说明会随接口响应返回（``normalization_notes``），用于区分"真实模型生成成功但
需要轻度归一"与"规则兜底"这两种情况。
"""

from __future__ import annotations

import re
from typing import Any

# 与 rules.extract_duration 保持一致的有效时长区间。
MIN_DURATION_MINUTES = 5
MAX_DURATION_MINUTES = 300

_TEXT_FIELDS = ("topic", "style", "target_student")
_LIST_FIELDS = ("knowledge_points", "key_difficulties", "expected_outcomes")

# 模型可能把课件说成 PPT / 幻灯片 / Word / 教案，统一收敛到 IntentSummary 约定的取值。
_OUTPUT_FORMAT_ALIASES = {
    "ppt": "ppt",
    "pptx": "ppt",
    "powerpoint": "ppt",
    "幻灯片": "ppt",
    "幻灯": "ppt",
    "doc": "doc",
    "docx": "doc",
    "word": "doc",
    "教案": "doc",
    "讲义": "doc",
    "讲稿": "doc",
    "both": "both",
    "all": "both",
    "ppt+doc": "both",
    "interactive": "interactive",
    "互动": "interactive",
    # 真实模型实测：GLM 等常把 output_format 直接写成"课件"这类通用词
    # （案例：裸句式请求返回字符串 "课件" 而非数组）。旧表只认精确别名时
    # 这些值会被整项丢弃，最终 output_format=[] —— 虽然不再整包降级，
    # 但模型给出的格式信息白白丢失。按规则侧 extract_output_formats 的口径
    # 收敛到 ppt，与规则引擎保持一致。
    "课件": "ppt",
    "演示文稿": "ppt",
    "ppt课件": "ppt",
    "幻灯片课件": "ppt",
    "课程课件": "ppt",
}

_TRUTHY_WORDS = {
    "true", "1", "yes", "y", "on", "是", "需要", "要", "有", "开", "开启",
    "要互动", "需要互动", "有互动", "带互动", "要测验", "需要测验",
}
_FALSY_WORDS = {
    "false", "0", "no", "n", "off", "否", "不", "不需要", "不要", "无需",
    "无", "关闭", "不要互动", "不需要互动", "无互动", "不带互动",
}

_LIST_SPLIT = re.compile(r"[、，,;；\n]+")
_DURATION_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _note(notes: list[str], field: str, detail: str) -> None:
    notes.append(f"{field}: {detail}")


def _coerce_text(value: Any) -> tuple[str | None, str | None]:
    """归一为去除首尾空白的字符串；无法归一时返回 (None, 说明)。"""
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text, None
        return None, "空字符串 → 丢弃"
    if isinstance(value, bool):
        return None, f"布尔值无法作为文本（{value!r}）→ 丢弃"
    if isinstance(value, (int, float)):
        return str(value), f"数值 {value!r} → 文本 '{value}'"
    return None, f"无法归一为文本（{type(value).__name__}）→ 丢弃"


def _coerce_duration(value: Any) -> tuple[int | None, str | None]:
    """归一授课时长（分钟）；越界与不可归一都视为该字段不可用。"""
    if isinstance(value, bool):
        return None, f"布尔值不是有效时长（{value!r}）→ 丢弃"
    if isinstance(value, (int, float)):
        minutes = int(value)
    elif isinstance(value, str):
        match = _DURATION_NUMBER.search(value)
        if not match:
            return None, f"未找到分钟数（{value!r}）→ 丢弃"
        minutes = int(float(match.group(0)))
    else:
        return None, f"无法归一为时长（{type(value).__name__}）→ 丢弃"

    if minutes < MIN_DURATION_MINUTES or minutes > MAX_DURATION_MINUTES:
        return None, (
            f"{minutes} 分钟超出有效区间 "
            f"[{MIN_DURATION_MINUTES}, {MAX_DURATION_MINUTES}] → 丢弃"
        )
    return minutes, None


def _coerce_bool(value: Any) -> tuple[bool | None, str | None]:
    """归一互动开关；模型常用中文回答，这里显式覆盖。"""
    if isinstance(value, bool):
        return value, None
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value), f"{value!r} → {bool(value)}"
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUTHY_WORDS:
            return True, f"{value!r} → True"
        if text in _FALSY_WORDS:
            return False, f"{value!r} → False"
        if any(word in text for word in ("不需要", "不要", "无需", "关闭", "不带")):
            return False, f"{value!r} → False"
        if any(word in text for word in ("需要", "开启", "要互动", "带互动", "有互动")):
            return True, f"{value!r} → True"
        return None, f"无法归一为布尔（{value!r}）→ 丢弃"
    return None, f"无法归一为布尔（{type(value).__name__}）→ 丢弃"


def _coerce_str_list(value: Any) -> tuple[list[str], str | None]:
    """归一字符串列表；模型可能把列表写成逗号分隔的单个字符串。"""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return [], "空字符串 → 视为空列表"
        items = [part.strip() for part in _LIST_SPLIT.split(text) if part.strip()]
        return items, f"字符串 → 列表（{len(items)} 项）"
    if isinstance(value, (list, tuple)):
        items: list[str] = []
        dropped = 0
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    items.append(text)
                else:
                    dropped += 1
            else:
                # 数字/布尔/对象都不是可用的知识点条目，直接丢弃。
                dropped += 1
        note = f"列表清洗（保留 {len(items)} 项，丢弃 {dropped} 项）" if dropped else None
        return items, note
    return [], f"无法归一为列表（{type(value).__name__}）→ 丢弃"


def _coerce_output_format(value: Any) -> tuple[list[str], str | None]:
    """归一输出格式到 ppt / doc / interactive。"""
    items, note = _coerce_str_list(value)
    normalized: list[str] = []
    dropped: list[str] = []
    for item in items:
        key = item.strip().lower()
        alias = _OUTPUT_FORMAT_ALIASES.get(key)
        if alias is None:
            # 自然语言写法兜底："PPT 演示文稿""Word 教案"等含关键词但不在精确表里。
            # 只做类型/取值收敛，不改语义（不会把"课件"臆断成 ppt+doc）。
            if any(word in key for word in ("课件", "幻灯", "演示文稿", "powerpoint", "ppt")):
                alias = "ppt"
                note = f"{note}；按关键词映射 '{item}' → ppt" if note else f"按关键词映射 '{item}' → ppt"
            elif any(word in key for word in ("教案", "讲义", "讲稿", "word", "docx", "doc")):
                alias = "doc"
                note = f"{note}；按关键词映射 '{item}' → doc" if note else f"按关键词映射 '{item}' → doc"
            else:
                dropped.append(item)
                continue
        if alias == "both":
            for fmt in ("ppt", "doc"):
                if fmt not in normalized:
                    normalized.append(fmt)
        elif alias not in normalized:
            normalized.append(alias)

    if dropped:
        detail = f"未知格式 {dropped} → 丢弃"
        note = f"{note}；{detail}" if note else detail
    return normalized, note


def normalize_intent_payload(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """把真实模型的原始输出归一成可安全构造 IntentSummary 的载荷。

    Args:
        raw: 模型返回的原始字典。

    Returns:
        ``(归一后的载荷, 归一说明列表)``。说明列表用于可观测：它记录哪些字段被
        修过、哪些被丢弃，便于区分"模型可用但需轻度归一"与"模型输出不可用"。
    """
    notes: list[str] = []
    payload: dict[str, Any] = {}

    for field in _TEXT_FIELDS:
        if field not in raw:
            continue
        value = raw.get(field)
        if value is None:
            payload[field] = None
            continue
        text, note = _coerce_text(value)
        payload[field] = text
        if note:
            _note(notes, field, note)

    if raw.get("duration_minutes") is not None:
        minutes, note = _coerce_duration(raw["duration_minutes"])
        payload["duration_minutes"] = minutes
        if note:
            _note(notes, "duration_minutes", note)
    elif "duration_minutes" in raw:
        payload["duration_minutes"] = None

    if raw.get("with_interactive") is not None:
        flag, note = _coerce_bool(raw["with_interactive"])
        payload["with_interactive"] = bool(flag)
        if note:
            _note(notes, "with_interactive", note)
    elif "with_interactive" in raw:
        payload["with_interactive"] = False

    for field in _LIST_FIELDS:
        if field not in raw:
            continue
        value = raw.get(field)
        if value is None:
            payload[field] = []
            continue
        items, note = _coerce_str_list(value)
        payload[field] = items
        if note:
            _note(notes, field, note)

    if "output_format" in raw:
        value = raw.get("output_format")
        if value is None:
            payload["output_format"] = []
        else:
            formats, note = _coerce_output_format(value)
            payload["output_format"] = formats
            if note:
                _note(notes, "output_format", note)

    # missing_fields 由服务层按最终摘要重算，模型自报的一律丢弃，避免口径不一致。
    known = set(_TEXT_FIELDS) | set(_LIST_FIELDS) | {
        "duration_minutes",
        "with_interactive",
        "output_format",
    }
    ignored = [key for key in raw if key not in known and key != "missing_fields"]
    if ignored:
        _note(notes, "未声明字段", f"{sorted(ignored)} → 忽略")

    return payload, notes


__all__ = [
    "normalize_intent_payload",
    "MIN_DURATION_MINUTES",
    "MAX_DURATION_MINUTES",
]
