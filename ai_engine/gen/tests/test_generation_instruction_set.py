"""Shared generation instruction contract stays visible across S3 planning stages."""

from ai_engine.gen.node import NodeGenerator
from ai_engine.gen.outline import OutlineBuilder
from ai_engine.gen.teaching_plan import plan_deck
from ai_engine.core.schema import GenerationCreateRequest


INSTRUCTIONS = {
    "schema_version": 1,
    "outline_nodes": [{"node_id": "n1", "title": "排序", "summary": "排序方法"}],
    "output_requirements": {"formats": ["ppt", "docx"], "with_interactive": True},
    "presentation": {"template_id": "swiss-edu", "density": "standard"},
    "generation_mode": "full_pipeline",
}


def test_outline_prompt_receives_shared_instruction_set(monkeypatch):
    builder = OutlineBuilder()
    captured = {}

    def capture(markdown, _key_points, _duration):
        captured["markdown"] = markdown
        return []

    monkeypatch.setattr(builder, "_run_node_tree_generation", capture)
    builder.build({"topic": "排序"}, generation_instruction_set=INSTRUCTIONS)

    assert '"template_id": "swiss-edu"' in captured["markdown"]
    assert '"formats": ["ppt", "docx"]' in captured["markdown"]


def test_teaching_plan_prompt_receives_shared_instruction_set():
    class CaptureLLM:
        prompt = ""

        def chat_json(self, _system, prompt, **_kwargs):
            self.prompt = prompt
            return {"plans": []}

    llm = CaptureLLM()
    plan_deck({"topic": "排序"}, [{"node_id": "n1", "title": "排序"}],
              generation_instruction_set=INSTRUCTIONS, llm=llm)

    assert '"density": "standard"' in llm.prompt
    assert '"with_interactive": true' in llm.prompt


def test_node_content_prompt_receives_shared_instruction_set():
    class CaptureLLM:
        prompt = ""

        def chat_with_schema(self, _system, prompt, _schema, **_kwargs):
            self.prompt = prompt
            return {"scripts": []}

    llm = CaptureLLM()
    generator = NodeGenerator(llm_client=llm)
    generator.generate_all(
        [{"node_id": "n1", "title": "排序"}],
        generation_instruction_set=INSTRUCTIONS,
    )

    assert '"template_id": "swiss-edu"' in llm.prompt
    assert '"generation_mode": "full_pipeline"' in llm.prompt


def test_generation_request_keeps_scope_separate_from_page_strategy():
    request = GenerationCreateRequest(
        generation_scope="full_pipeline",
        generate_mode="page_parallel",
        generation_instruction_set={
            "generation_mode": "full_pipeline",
            "page_generation_mode": "page_parallel",
        },
    )

    assert request.generation_scope == "full_pipeline"
    assert request.generate_mode == "page_parallel"
    assert request.generation_instruction_set.page_generation_mode == "page_parallel"
    assert request.generation_instruction_set.outline_nodes == []


def test_generation_request_preserves_edited_outline_nodes_in_instruction_set():
    request = GenerationCreateRequest(
        outline_id="outline_1",
        outline_version=2,
        outline_confirmed=True,
        outline_nodes=INSTRUCTIONS["outline_nodes"],
        generation_instruction_set=INSTRUCTIONS,
    )

    assert request.generation_instruction_set.outline_nodes == INSTRUCTIONS["outline_nodes"]
