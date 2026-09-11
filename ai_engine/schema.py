import math
import os
import time
import uuid
from typing import Any

# 大纲节点时长兜底：intent 未提供课时、或 LLM 未给出合法时长时使用。
DEFAULT_NODE_DURATION_MINUTES = 5
# build_from_markdown 没有 intent 课时时的默认总课时（分钟）。
DEFAULT_TOTAL_DURATION_MINUTES = 45


def build_stage1_markdown_schema() -> dict[str, Any]:
    return {
        "name": "stage1_markdown_understanding",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "normalized_markdown": {"type": "string"},
                "key_points": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["normalized_markdown", "key_points"],
        },
    }


def build_stage2_node_tree_schema() -> dict[str, Any]:
    return {
        "name": "stage2_node_tree",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "node_id": {"type": "string"},
                            "title": {"type": "string", "maxLength": 60},
                            "summary": {"type": "string", "maxLength": 60},
                            "node_type": {
                                "type": "string",
                                "enum": ["slide", "section", "quiz", "interactive", "cover", "divider"],
                            },
                            # 核心要点（渲染器统一读 key_points）
                            "key_points": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 4,
                            },
                            # 节点时长（分钟）。Go 大纲确认接口 validateOutlineNodes
                            # 要求每个节点 > 0，此处只做类型约束不做 minimum——
                            # 部分 Provider 对 minimum 支持不稳定，正数保证由
                            # normalize_stage2_nodes / assign_node_durations 完成。
                            # 保持可选以兼容旧 LLM 响应。
                            "estimated_duration_minutes": {"type": "number"},
                        },
                        "required": ["node_id", "title", "node_type"],
                    },
                }
            },
            "required": ["nodes"],
        },
    }


def build_stage3_script_schema() -> dict[str, Any]:
    return {
        "name": "stage3_node_scripts",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "scripts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "node_id": {"type": "string"},
                            "title": {"type": "string"},
                            "script": {"type": "string"},
                            "segments": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "segment_id": {"type": "string"},
                                        "text": {"type": "string"},
                                        "node_id": {"type": "string"},
                                    },
                                    "required": ["segment_id", "text", "node_id"],
                                },
                            },
                        },
                        "required": ["node_id", "title", "script", "segments"],
                    },
                }
            },
            "required": ["scripts"],
        },
    }


def build_enhanced_script_schema() -> dict[str, Any]:
    return {
        "name": "enhanced_node_scripts",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "scripts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "node_id": {"type": "string"},
                            "title": {"type": "string"},
                            "script": {"type": "string"},
                            "segments": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "segment_id": {"type": "string"},
                                        "text": {"type": "string"},
                                        "node_id": {"type": "string"},
                                        "node_ids": {"type": "array", "items": {"type": "string"}},
                                        "segment_type": {"type": "string", "enum": ["opening", "explanation", "example", "interaction", "transition", "summary"]},
                                        "estimated_seconds": {"type": "integer"},
                                        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                                        "interaction_hint": {"type": "string"},
                                        "knowledge_card": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "term": {"type": "string"},
                                                "definition": {"type": "string"},
                                                "formula": {"type": "string"},
                                                "tags": {"type": "array", "items": {"type": "string"}},
                                            },
                                            "required": ["term", "definition"],
                                        },
                                    },
                                    "required": ["segment_id", "text", "node_id", "segment_type", "estimated_seconds"],
                                },
                            },
                        },
                        "required": ["node_id", "title", "script", "segments"],
                    },
                }
            },
            "required": ["scripts"],
        },
    }


def normalize_duration_minutes(value: Any) -> float | None:
    """把任意输入收敛为「有限的正数分钟」，非法值返回 None。

    Go 大纲确认接口 validateOutlineNodes 要求 estimated_duration_minutes > 0，
    所以 0、负数、NaN、inf、空串、非数字字符串一律视为无效，由调用方补默认值。
    """
    if isinstance(value, bool):  # bool 是 int 子类，必须先排除，避免 True→1
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    if math.isnan(number) or math.isinf(number) or number <= 0:
        return None
    return number


def _existing_duration(node: dict[str, Any]) -> float | None:
    """读取节点已有合法时长，兼容历史字段名（duration_minutes / estimated_duration）。"""
    for key in ("estimated_duration_minutes", "duration_minutes", "estimated_duration"):
        value = normalize_duration_minutes((node or {}).get(key))
        if value is not None:
            return value
    return None


def assign_node_durations(
    nodes: list[dict[str, Any]],
    total_duration_minutes: int | float | None = None,
) -> list[dict[str, Any]]:
    """为每个节点补齐正数 estimated_duration_minutes（就地修改并返回同一列表）。

    两种模式：
      - 提供合法总课时：按节点数做正整数均分，余数分给前几个节点；课时少于节点数时
        退化为每节点 1 分钟。保证总和等于课时且不产生 0 分钟节点。
      - 未提供总课时：优先保留节点已有合法时长，无效（缺失/0/负数/NaN/字符串）的
        补 DEFAULT_NODE_DURATION_MINUTES。该模式对已分配结果幂等，供修订路径保留
        教师手工调过的单节点时长。
    """
    if not nodes:
        return nodes

    total = normalize_duration_minutes(total_duration_minutes)
    if total is not None:
        count = len(nodes)
        existing = [_existing_duration(node) for node in nodes]
        if all(value is not None for value in existing):
            # 全部节点都带合法时长：信任 LLM / 上游的分配（提示词已要求贴合总课时），
            # 只做取整与正数保证，避免把测验、互动等短节点抹平成平均分。
            for node, value in zip(nodes, existing):
                node["estimated_duration_minutes"] = max(1, round(value))
            return nodes
        total_minutes = int(total)
        if total_minutes < count:
            # 课时少于节点数：每节点 1 分钟，宁可总时长超出也不产生 0 分钟节点
            for node in nodes:
                node["estimated_duration_minutes"] = 1
            return nodes
        base, remainder = divmod(total_minutes, count)
        for index, node in enumerate(nodes):
            node["estimated_duration_minutes"] = base + (1 if index < remainder else 0)
        return nodes

    for node in nodes:
        value = _existing_duration(node)
        node["estimated_duration_minutes"] = (
            max(1, round(value)) if value is not None else DEFAULT_NODE_DURATION_MINUTES
        )
    return nodes


def extract_list_payload(result: Any, *keys: str) -> list[dict[str, Any]]:
    """从 LLM 结构化返回中取出对象数组，容忍多种根形状。

    chat_with_schema 的降级链在②③级（response_format=json_object / 纯 prompt 约束）
    不强制根节点为 object，模型可能直接返回裸数组；strict 级也可能因网关兼容性差异
    返回数组。调用方若直接写 result.get(...)，在 list 上会抛 AttributeError
    并被上层 except 吞成 fallback，造成质量塌方。

    Args:
        result: chat_with_schema 的返回值，可能是 dict 或 list。
        keys: 候选键名，按顺序取第一个命中且为 list 的值。默认取 "nodes"。

    Returns:
        仅含 dict 元素的数组；形状无法识别时返回 []。
    """
    if isinstance(result, list):
        candidates: Any = result
    elif isinstance(result, dict):
        candidates = None
        for key in keys or ("nodes",):
            value = result.get(key)
            if isinstance(value, list):
                candidates = value
                break
    else:
        return []
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, dict)]


def extract_nodes_payload(result: Any) -> list[dict[str, Any]]:
    """节点数组专用入口，等价于 extract_list_payload(result, "nodes")。"""
    return extract_list_payload(result, "nodes")


def normalize_stage2_nodes(
    nodes: list[dict[str, Any]] | None,
    total_duration_minutes: int | float | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, item in enumerate(nodes or [], start=1):
        # 类型守卫：LLM 偶发输出非 dict 元素（如嵌套 list / 字符串），跳过而非崩溃。
        # 修复前 `(item or {}).get(...)` 对 list 元素抛 'list' object has no attribute 'get'。
        if not isinstance(item, dict):
            continue
        raw_id = str((item or {}).get("node_id") or f"node_{idx:03d}").strip()
        if not raw_id or raw_id in seen:
            continue
        seen.add(raw_id)

        raw_type = str((item or {}).get("type") or (item or {}).get("node_type") or "content").strip()
        core_pts = (item or {}).get("core_points") or []
        key_pts = (item or {}).get("key_points") or []
        questions_raw = (item or {}).get("questions")
        interactive_raw = (item or {}).get("interactive_questions")

        result.append(
            {
                "node_id": raw_id,
                "title": str((item or {}).get("title") or f"知识节点{idx}").strip() or f"知识节点{idx}",
                "summary": str((item or {}).get("summary") or "").strip(),
                "source_span": str((item or {}).get("source_span") or "").strip(),
                "node_type": sanitize_node_type(raw_type),
                "type": sanitize_node_type(raw_type),
                "prerequisites": [
                    str(value).strip()
                    for value in ((item or {}).get("prerequisites") or [])
                    if str(value).strip()
                ],
                # 兼容字段：key_points 优先，否则 fallback 到 core_points
                # 类型归一：str/list[dict]/dict 等脏数据统一转为 list[str]（M1-4 P5）
                "key_points": normalize_text_list(key_pts) or normalize_text_list(core_pts),
                "core_points": normalize_text_list(core_pts),
                # 兼容字段：questions 优先，否则 fallback 到 interactive_questions
                # 类型归一：str/list[dict]/dict 等脏数据统一转为 list[str]（M1-4A P5）
                "questions": normalize_text_list(questions_raw) or normalize_text_list(interactive_raw),
                "interactive_questions": normalize_text_list(interactive_raw) or normalize_text_list(questions_raw),
                # 空数组显式声明，避免 None；非列表段落丢弃，保持 canonical list[dict]
                "segments": ((item or {}).get("segments") if isinstance((item or {}).get("segments"), list) else []),
                # schema.py 定义为 Optional[str]，脏类型统一转文本，None 保持 None
                "layout_hint": _normalize_optional_text((item or {}).get("layout_hint")),
                "font_size_hint": _normalize_optional_text((item or {}).get("font_size_hint")),
                "text_alignment": _normalize_optional_text((item or {}).get("text_alignment")),
                "slide_background": _normalize_optional_text((item or {}).get("slide_background")),
                # 节点时长（分钟）：契约字段名固定为 estimated_duration_minutes，
                # 不再依赖 Go 侧 JSON 映射的隐式默认（缺失会落成 0 而被确认校验拒绝）。
                # 此处先取节点自带合法值，最终正数保证由下方 assign_node_durations 完成。
                "estimated_duration_minutes": normalize_duration_minutes(
                    (item or {}).get("estimated_duration_minutes")
                ),
            }
        )
    return assign_node_durations(result, total_duration_minutes)


def normalize_stage3_scripts(scripts: list[dict[str, Any]] | None, valid_node_ids: set[str]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in scripts or []:
        node_id = str((item or {}).get("node_id") or "").strip()
        if not node_id or node_id not in valid_node_ids:
            continue
        segments: list[dict[str, Any]] = []
        for seg in (item or {}).get("segments") or []:
            segment_id = str((seg or {}).get("segment_id") or "").strip()
            text = str((seg or {}).get("text") or "").strip()
            seg_node_id = str((seg or {}).get("node_id") or node_id).strip()
            if not segment_id or not text:
                continue
            if seg_node_id not in valid_node_ids:
                seg_node_id = node_id
            segments.append({"segment_id": segment_id, "text": text, "node_id": seg_node_id})

        script_text = str((item or {}).get("script") or "").strip()
        if not script_text and segments:
            script_text = "".join([seg["text"] for seg in segments])

        # 提取兼容字段（允许 LLM 输出 title/script 作为备选）
        raw_type = str((item or {}).get("type") or (item or {}).get("node_type") or "content").strip()
        core_pts = (item or {}).get("core_points") or []
        key_pts = (item or {}).get("key_points") or []
        questions_raw = (item or {}).get("questions")
        interactive_raw = (item or {}).get("interactive_questions")

        normalized.append(
            {
                "node_id": node_id,
                "title": str((item or {}).get("title") or node_id).strip() or node_id,
                "script": script_text,
                "node_type": sanitize_node_type(raw_type),
                "type": sanitize_node_type(raw_type),
                # 兼容字段
                # 类型归一：str/list[dict]/dict 等脏数据统一转为 list[str]（M1-4 P5）
                "key_points": normalize_text_list(key_pts) or normalize_text_list(core_pts),
                "core_points": normalize_text_list(core_pts),
                "questions": normalize_text_list(questions_raw) or normalize_text_list(interactive_raw),
                "interactive_questions": normalize_text_list(interactive_raw) or normalize_text_list(questions_raw),
                "segments": segments,
                "layout_hint": _normalize_optional_text((item or {}).get("layout_hint")),
                "font_size_hint": _normalize_optional_text((item or {}).get("font_size_hint")),
                "text_alignment": _normalize_optional_text((item or {}).get("text_alignment")),
                "slide_background": _normalize_optional_text((item or {}).get("slide_background")),
            }
        )
    return normalized


def build_document_schema(
    file_path: str,
    document_type: str,
    total_pages: int,
    parsed_pages: list[dict[str, Any]],
    started_at: float,
) -> dict[str, Any]:
    elapsed_ms = int((time.time() - started_at) * 1000)
    non_empty_pages = len(parsed_pages)
    empty_pages = max(total_pages - non_empty_pages, 0)

    return {
        "doc_id": f"doc_{uuid.uuid4().hex[:12]}",
        "doc_name": os.path.basename(file_path),
        "doc_path": file_path,
        "doc_type": document_type,
        "total_pages": total_pages,
        "parsed_pages": parsed_pages,
        "stats": {
            "non_empty_pages": non_empty_pages,
            "empty_pages": empty_pages,
            "elapsed_ms": elapsed_ms,
        },
    }


def build_reconstruction_schema(
    parsed_document: dict[str, Any],
    chapters: list[dict[str, Any]],
    teaching_nodes: list[dict[str, Any]],
    started_at: float,
) -> dict[str, Any]:
    elapsed_ms = int((time.time() - started_at) * 1000)

    return {
        "doc_id": parsed_document.get("doc_id"),
        "doc_name": parsed_document.get("doc_name"),
        "doc_type": parsed_document.get("doc_type"),
        "chapters": chapters,
        "teaching_nodes": teaching_nodes,
        "stats": {
            "chapter_count": len(chapters),
            "node_count": len(teaching_nodes),
            "elapsed_ms": elapsed_ms,
        },
    }


def build_node_script_schema(
    node_id: str,
    title: str,
    script: str,
    mindmap_markdown: str,
    interactive_questions: list[str],
    reteach_script: str,
    transition: str,
    structured_markdown: str = "",
    knowledge_nodes: list[dict[str, Any]] | None = None,
    script_segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_nodes = normalize_knowledge_nodes(knowledge_nodes or [], default_node_id=node_id, default_title=title)
    normalized_segments = normalize_script_segments(script_segments or [], node_id=node_id, fallback_script=script)
    normalized_nodes, normalized_segments = align_node_segment_mapping(
        normalized_nodes,
        normalized_segments,
        default_node_id=node_id,
    )

    return {
        "node_id": node_id,
        "title": title,
        "script": script,
        "mindmap_markdown": mindmap_markdown,
        "interactive_questions": interactive_questions,
        "reteach_script": reteach_script,
        "transition": transition,
        "structured_markdown": (structured_markdown or "").strip(),
        "knowledge_nodes": normalized_nodes,
        "script_segments": normalized_segments,
    }


def normalize_knowledge_nodes(
    knowledge_nodes: list[dict[str, Any]],
    default_node_id: str,
    default_title: str,
) -> list[dict[str, Any]]:
    if not knowledge_nodes:
        return [
            {
                "node_id": default_node_id,
                "parent_id": "",
                "level": 1,
                "title": default_title,
                "tags": [],
                "prerequisites": [],
                "difficulty": "medium",
                "coverage_span": ["seg_1"],
            }
        ]

    result: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    for index, item in enumerate(knowledge_nodes, start=1):
        node_item = item or {}
        node_item_id = str(node_item.get("node_id") or f"{default_node_id}_{index}").strip()
        if not node_item_id or node_item_id in seen_node_ids:
            continue
        seen_node_ids.add(node_item_id)
        result.append(
            {
                "node_id": node_item_id,
                "parent_id": str(node_item.get("parent_id") or "").strip(),
                "level": _to_int(node_item.get("level"), 1),
                "title": str(node_item.get("title") or default_title).strip(),
                "tags": _to_string_list(node_item.get("tags")),
                "prerequisites": _to_string_list(node_item.get("prerequisites")),
                "difficulty": _normalize_difficulty(node_item.get("difficulty")),
                "coverage_span": _to_string_list(node_item.get("coverage_span")),
            }
        )

    return result or [
        {
            "node_id": default_node_id,
            "parent_id": "",
            "level": 1,
            "title": default_title,
            "tags": [],
            "prerequisites": [],
            "difficulty": "medium",
            "coverage_span": ["seg_1"],
        }
    ]


def normalize_script_segments(
    script_segments: list[dict[str, Any]],
    node_id: str,
    fallback_script: str,
) -> list[dict[str, Any]]:
    if not script_segments:
        text = (fallback_script or "").strip()
        return [
            {
                "segment_id": "seg_1",
                "text": text,
                "node_ids": [node_id],
                "confidence": 0.8,
                "manual_override": False,
            }
        ]

    result: list[dict[str, Any]] = []
    seen_segment_ids: set[str] = set()
    for index, item in enumerate(script_segments, start=1):
        seg = item or {}
        segment_id = str(seg.get("segment_id") or f"seg_{index}").strip()
        if not segment_id or segment_id in seen_segment_ids:
            continue
        seen_segment_ids.add(segment_id)

        text = str(seg.get("text") or "").strip()
        if not text:
            continue

        mapped_nodes = _to_string_list(seg.get("node_ids")) or [node_id]

        result.append(
            {
                "segment_id": segment_id,
                "text": text,
                "node_ids": mapped_nodes,
                "confidence": _to_float(seg.get("confidence"), 0.8),
                "manual_override": bool(seg.get("manual_override", False)),
            }
        )

    if result:
        return result
    return [
        {
            "segment_id": "seg_1",
            "text": (fallback_script or "").strip(),
            "node_ids": [node_id],
            "confidence": 0.8,
            "manual_override": False,
        }
    ]


def align_node_segment_mapping(
    knowledge_nodes: list[dict[str, Any]],
    script_segments: list[dict[str, Any]],
    default_node_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not knowledge_nodes:
        return knowledge_nodes, script_segments

    segment_ids = {str(seg.get("segment_id") or "").strip() for seg in script_segments}
    segment_ids.discard("")

    node_id_list = [str(node.get("node_id") or "").strip() for node in knowledge_nodes]
    node_id_set = {item for item in node_id_list if item}
    if not node_id_set:
        node_id_set = {default_node_id}

    # 1) 过滤节点 coverage_span 到真实 segment_id，并确保每个节点最少覆盖一个段落
    fallback_segment_id = next(iter(segment_ids), "seg_1")
    for node in knowledge_nodes:
        node_id = str(node.get("node_id") or default_node_id).strip() or default_node_id
        coverage = _to_string_list(node.get("coverage_span"))
        filtered = [item for item in coverage if item in segment_ids]
        if not filtered:
            # 回退：优先使用显式引用本节点的段落
            node_segments = [
                str(seg.get("segment_id") or "").strip()
                for seg in script_segments
                if node_id in _to_string_list(seg.get("node_ids"))
            ]
            node_segments = [item for item in node_segments if item]
            filtered = node_segments or [fallback_segment_id]
        node["coverage_span"] = filtered

    # 2) 校准每个段落 node_ids，剔除不存在节点，并至少挂到默认节点
    first_node = node_id_list[0] if node_id_list and node_id_list[0] else default_node_id
    for seg in script_segments:
        mapped = _to_string_list(seg.get("node_ids"))
        mapped = [item for item in mapped if item in node_id_set]
        if not mapped:
            seg_id = str(seg.get("segment_id") or "").strip()
            owners = []
            if seg_id:
                for node in knowledge_nodes:
                    coverage = _to_string_list(node.get("coverage_span"))
                    if seg_id in coverage:
                        owner_id = str(node.get("node_id") or "").strip()
                        if owner_id:
                            owners.append(owner_id)
            mapped = owners or [first_node]
        seg["node_ids"] = mapped

    return knowledge_nodes, script_segments


VALID_NODE_TYPES = frozenset({"slide", "section", "quiz", "interactive", "cover", "divider"})


def sanitize_node_type(raw: Any) -> str:
    """把 LLM 输出的 node_type 收敛到合法枚举白名单。

    背景：GenerationVersion.nodes_snapshot 的 node_type 是枚举校验，LLM 偶发输出
    白名单外的值（实测出现过 'summary'、'content'），会让快照保存整批 ValidationError、
    连带 status 接口 500。白名单外的值一律收敛为 'slide'（最通用的内容页类型）。
    """
    value = str(raw or "").strip().lower()
    return value if value in VALID_NODE_TYPES else "slide"


# 引擎节点类型 → Go 大纲契约（backend/internal/service/outline_service.go）
# OutlineNodeType* 允许的枚举：content | section | quiz | interactive | summary。
# 引擎侧 slide/cover/divider 在 Go 确认校验中都算非法，统一收敛为最通用的 content。
OUTLINE_NODE_TYPE_MAP = {
    "content": "content",
    "slide": "content",
    "cover": "content",
    "divider": "content",
    "section": "section",
    "quiz": "quiz",
    "interactive": "interactive",
    "summary": "summary",
}


def to_outline_contract_node_type(raw: Any) -> str:
    """把引擎 node_type 映射为 Go 大纲确认接口允许的取值。

    注意与 sanitize_node_type 的分工：sanitize_node_type 的白名单对应引擎内部
    GenerationVersion.nodes_snapshot 枚举（slide/section/quiz/interactive/cover/divider），
    而 Go 大纲契约用的是 content/section/quiz/interactive/summary，两者只在
    section/quiz/interactive 上重叠。因此不能在 sanitize_node_type 里直接改白名单，
    否则会破坏引擎快照契约——边界映射由本函数专门承担。
    """
    value = str(raw or "").strip().lower()
    return OUTLINE_NODE_TYPE_MAP.get(value, "content")


def to_outline_contract_nodes(nodes: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """大纲输出边界：把引擎节点收敛到 Go OutlineNode 契约。

    Go validateOutlineNodes 要求 node_id 唯一、order 从 1 连续、title/summary 非空、
    estimated_duration_minutes > 0、node_type 合法。这里只负责 AI Engine 侧能保证的部分：
      - node_type 映射为 content|section|quiz|interactive|summary
      - summary 为空时用 title 兜底（Go 侧不会补 summary）
      - estimated_duration_minutes 保证正数
    order 由 Go normalizeOutlineNodes 重排，此处不输出。
    """
    contracted: list[dict[str, Any]] = []
    for index, node in enumerate(nodes or [], start=1):
        item = dict(node or {})
        node_type = to_outline_contract_node_type(item.get("node_type") or item.get("type"))
        item["node_type"] = node_type
        item["type"] = node_type
        item["title"] = str(item.get("title") or "").strip() or f"知识节点{index}"
        if not str(item.get("summary") or "").strip():
            item["summary"] = f"围绕「{item['title']}」进行讲授。"
        contracted.append(item)
    return assign_node_durations(contracted)


def _normalize_optional_text(value: Any) -> str | None:
    """将可选文本字段收敛为 str 或 None，避免进入 TeachingNode 时类型漂移。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("value", "name", "text"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
    return None


def normalize_text_list(value: Any) -> list[str]:
    """把 questions / interactive_questions / key_points 等字段归一为 list[str]。

    规则（与 migrate_snapshot._normalize_questions 对齐，供多个 normalize 写入点共享，
    避免各处实现漂移）：
      - str → 单元素包装（非空才保留）
      - list：str 保留；dict 提取 question / content / text 键文本；其他非 None 元素 str 化
      - 其他类型（dict / None / 数字等）→ []
    """
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            if item.strip():
                result.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("question") or item.get("content") or item.get("text")
            if isinstance(text, str) and text.strip():
                result.append(text.strip())
        elif item is not None:
            result.append(str(item).strip())
    return result


def _to_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float) -> float:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return default
    if val < 0:
        return 0.0
    if val > 1:
        return 1.0
    return val


def _normalize_difficulty(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"easy", "medium", "hard"}:
        return text
    return "medium"
