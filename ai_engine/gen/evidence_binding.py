"""Bind one EvidencePacket to every node in a generated PPT draft."""

from typing import Any


def evidence_reference_ids(packet: dict[str, Any] | None) -> list[str]:
    """Return stable, de-duplicated chunk ids from both evidence collections."""
    if not isinstance(packet, dict):
        return []
    nested = packet.get("evidence_packet")
    if isinstance(nested, dict):
        packet = nested
    refs: list[str] = []
    for key in ("citations", "relevant_chunks", "chunks"):
        values = packet.get(key) or []
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("chunk_id") or item.get("id") or "").strip()
            if ref and ref not in refs:
                refs.append(ref)
    return refs


def bind_evidence_to_draft_nodes(
    nodes: list[dict[str, Any]], packet: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Attach whole-draft evidence refs without discarding existing node refs."""
    refs = evidence_reference_ids(packet)
    if not refs:
        return nodes
    bound: list[dict[str, Any]] = []
    for raw in nodes:
        node = dict(raw or {})
        combined = []
        for ref in [*(node.get("source_chunk_ids") or []), *refs]:
            value = str(ref or "").strip()
            if value and value not in combined:
                combined.append(value)
        node["source_chunk_ids"] = combined
        node["citation_refs"] = list(combined)
        node["metadata"] = {
            **(node.get("metadata") or {}),
            "evidence_scope": "draft",
            "evidence_auto_bound": True,
            "evidence_bound_by": "s1_intent_auto_search",
        }
        bound.append(node)
    return bound
