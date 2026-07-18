import os
import time
import uuid
from typing import Any


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
                            "title": {"type": "string"},
                            "summary": {"type": "string"},
                            "source_span": {"type": "string"},
                            "prerequisites": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["node_id", "title", "summary", "source_span", "prerequisites"],
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


def normalize_stage2_nodes(nodes: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, item in enumerate(nodes or [], start=1):
        raw_id = str((item or {}).get("node_id") or f"node_{idx:03d}").strip()
        if not raw_id or raw_id in seen:
            continue
        seen.add(raw_id)
        result.append(
            {
                "node_id": raw_id,
                "title": str((item or {}).get("title") or f"知识节点{idx}").strip() or f"知识节点{idx}",
                "summary": str((item or {}).get("summary") or "").strip(),
                "source_span": str((item or {}).get("source_span") or "").strip(),
                "prerequisites": [
                    str(value).strip()
                    for value in ((item or {}).get("prerequisites") or [])
                    if str(value).strip()
                ],
            }
        )
    return result


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

        normalized.append(
            {
                "node_id": node_id,
                "title": str((item or {}).get("title") or node_id).strip() or node_id,
                "script": script_text,
                "segments": segments,
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
