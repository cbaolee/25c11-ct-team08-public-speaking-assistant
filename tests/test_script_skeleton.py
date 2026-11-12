"""Unit tests for the Script Generation skeleton contracts and modules."""

from __future__ import annotations

from pathlib import Path

from src.text_processing import (
    ContentModerator,
    DocumentChunk,
    ScriptGenerationPipeline,
    ScriptGenerationRequest,
    TemplateDocument,
    TemplateEngine,
    TemplateStore,
    TopicMetadata,
    assemble_template,
    parse_slots,
    verify_paragraph_citation,
)


def test_parse_and_assemble_template_handles_boundary_period() -> None:
    body = (
        "First paragraph with {{ argument_intro_claim }}.\n\n"
        "Second paragraph {{ argument_body_point }}."
    )
    doc = TemplateDocument(
        metadata=TopicMetadata(
            template_id="wildlife/test_5m",
            category_slug="wildlife",
            category="Wildlife",
            topic="Test Topic",
            topic_slug="test_5m",
            duration_min=5,
        ),
        body=body,
        file_path="data/templates/wildlife/test_5m.md",
    )
    slots = parse_slots(doc)
    assert [s.name for s in slots] == [
        "argument_intro_claim",
        "argument_body_point",
    ]
    assert [s.slot_type for s in slots] == ["argument", "argument"]

    assembled = assemble_template(
        body,
        {
            "argument_intro_claim": "wildlife habitats are shrinking.",
            "argument_body_point": "requires urgent action",
        },
    )
    assert "shrinking.." not in assembled
    assert "wildlife habitats are shrinking." in assembled
    assert "Second paragraph requires urgent action." in assembled


def test_verify_paragraph_citation_deterministic() -> None:
    chunks = [
        DocumentChunk(chunk_id=0, heading="Intro", page=1, content="Chunk zero content"),
        DocumentChunk(chunk_id=1, heading="Methods", page=2, content="Chunk one content"),
    ]
    citation = verify_paragraph_citation(
        paragraph_index=1,
        reported_chunk_ids=[1, 99],
        retrieved_chunks=chunks,
    )
    assert citation.status == "cited"
    assert citation.chunk_id == 1
    assert citation.heading == "Methods"

    empty_citation = verify_paragraph_citation(
        paragraph_index=2,
        reported_chunk_ids=[42],
        retrieved_chunks=chunks,
    )
    assert empty_citation.status == "uncited"
    assert empty_citation.chunk_id is None


def test_template_store_loads_wildlife_templates() -> None:
    store = TemplateStore(templates_dir=Path("data/templates"))
    count = store.load()
    assert count > 0
    topics = store.list_topics(category_slug="wildlife")
    assert len(topics) > 0
    first = topics[0]
    tpl = store.get(first.template_id)
    assert tpl is not None
    assert tpl.metadata.duration_min in (5, 10, 15, 20)


def test_pipeline_skeleton_end_to_end() -> None:
    store = TemplateStore(templates_dir=Path("data/templates"))
    store.load()
    topics = store.list_topics(category_slug="wildlife")
    assert topics, "Expected Wildlife templates to be available"
    target = topics[0]

    pipeline = ScriptGenerationPipeline(
        template_store=store,
        moderator=ContentModerator(),
        template_engine=TemplateEngine(),
    )
    req = ScriptGenerationRequest(
        topic=target.template_id,
        category="Wildlife",
        duration_min=target.duration_min,
        raw_text=(
            "Protecting biodiversity and keystone species stabilizes "
            "ecosystems and prevents trophic cascades."
        ),
        user_id="test-user",
    )
    result = pipeline.run(req)
    assert result.source == "template"
    assert result.template_id == target.template_id
    assert result.word_count > 0
    assert "{{" not in result.script
