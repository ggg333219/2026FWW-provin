from ai_engine.gen.evidence_binding import (
    bind_evidence_to_draft_nodes,
    evidence_reference_ids,
)


def test_whole_draft_evidence_binding_is_persisted_on_every_node():
    packet = {
        "citations": [{"chunk_id": "chunk_a"}],
        "relevant_chunks": [{"chunk_id": "chunk_a"}, {"chunk_id": "chunk_b"}],
    }
    nodes = [
        {"node_id": "n1", "source_chunk_ids": ["manual_ref"]},
        {"node_id": "n2"},
    ]

    bound = bind_evidence_to_draft_nodes(nodes, packet)

    assert evidence_reference_ids(packet) == ["chunk_a", "chunk_b"]
    assert bound[0]["citation_refs"] == ["manual_ref", "chunk_a", "chunk_b"]
    assert bound[1]["source_chunk_ids"] == ["chunk_a", "chunk_b"]
    assert bound[1]["metadata"]["evidence_auto_bound"] is True
