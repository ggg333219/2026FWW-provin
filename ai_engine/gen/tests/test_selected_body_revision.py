import copy

from pptx import Presentation

from ai_engine.gen.elements import build_element_snapshot, resolve_element_candidates
from ai_engine.gen.modify_intent import ModifyIntentParser
from ai_engine.gen.partial_content import run_partial_pipeline
from ai_engine.gen.node import NodeGenerator
from ai_engine.gen.page_spec import body_paragraphs
from ai_engine.gen.preview import PreviewRenderer
from ai_engine.gen.export_ppt import PPTExporter, ExportPPTConfig


INSTRUCTION = "请把这一页的正文改写得更通俗，并增加一个生活中的例子。"
BODY = "排序就是把东西按顺序排好。例如，整理书架时，把书按高度从低到高摆放。"


def nodes():
    return build_element_snapshot([
        {"node_id": f"node_{i}", "title": f"排序知识{i}", "node_type": "content",
         "content": f"原始正文{i}：根据关键字建立有序序列。", "summary": f"原始摘要{i}",
         "key_points": ["比较关键字"], "page_ref": i}
        for i in range(1, 4)
    ])


def test_selected_body_is_resolved_before_ambiguity_and_overrides_model_guess():
    class Model:
        def chat_with_schema(self, *args, **kwargs):
            return {"target_type": "node", "target_ids": ["node_1"],
                    "target_element_ids": ["el_node_1_title"], "action": "rewrite",
                    "confidence": 0.95, "clarification_needed": False}

    parser = ModifyIntentParser()
    parser._llm = Model()
    result = parser.parse(INSTRUCTION, nodes(), "node_2")
    assert not result["clarification_needed"]
    assert result["target_ids"] == ["node_2"]
    assert result["target_element_ids"] == ["el_node_2_body"]


def test_explicit_page_and_genuine_ambiguity_are_preserved():
    assert resolve_element_candidates("第三页正文改通俗", nodes(), "node_2")["target_element_ids"] == ["el_node_3_body"]
    assert resolve_element_candidates(INSTRUCTION, nodes())["status"] == "ambiguous"
    deck = nodes()
    extra = copy.deepcopy(deck[1]["metadata"]["elements"][-1])
    extra["element_id"] = "second_body"
    deck[1]["metadata"]["elements"].append(extra)
    assert resolve_element_candidates(INSTRUCTION, deck, "node_2")["status"] == "ambiguous"


def test_revised_body_reaches_preview_and_pptx_without_changing_other_pages(monkeypatch):
    monkeypatch.setattr("ai_engine.gen.partial_content.get_evidence_retriever", lambda: None)
    original = nodes()
    snapshot = copy.deepcopy(original)

    class Model:
        def chat_json(self, *args, **kwargs):
            return {"content": BODY}

    class Generator:
        def generate_single(self, node, **kwargs):
            assert node["node_id"] == "node_2"
            assert INSTRUCTION in kwargs["extra_instruction"]
            assert kwargs["revise_slide"]
            # A valid model may return visible body without summary or script.
            return NodeGenerator(llm_client=Model()).generate_single(node, **kwargs)

    revised = run_partial_pipeline(original, ["node_2"], "rewrite", [INSTRUCTION], "", "排序", Generator())
    assert original == snapshot
    assert revised[0] == original[0] and revised[2] == original[2]
    assert revised[1]["content"] == BODY
    assert body_paragraphs(revised[1]) == [BODY]
    assert BODY in PreviewRenderer().render_node(revised[1], 2)
    assert "原始正文2" not in PreviewRenderer().render_node(revised[1], 2)
    config = ExportPPTConfig(include_auto_cover=False, include_auto_toc=False,
                             include_auto_summary=False, include_closing_slide=False)
    prs = Presentation(PPTExporter(config).export_to_bytes(revised, "排序"))
    texts = ["\n".join(shape.text for shape in slide.shapes if shape.has_text_frame) for slide in prs.slides]
    assert len(texts) == 3
    assert "整理书架" in texts[1] and "原始正文2" not in texts[1]
    assert "整理书架" not in texts[0] and "整理书架" not in texts[2]
