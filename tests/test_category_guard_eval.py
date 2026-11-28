"""Checks of the category guard evaluation set, and its calibration rule on the real model.

The `integration` tests need `all-MiniLM-L6-v2` in the local cache and skip without it.
"""

import json
from collections import Counter
from typing import Any

import pytest

from scripts import eval_category_guard as evaluator
from src.app import script_guards
from src.text_processing.category_guard import CategoryCheckResult
from src.text_processing.contracts import CATEGORY_SLUG_MAP
from src.text_processing.input_guard import content_word_count
from src.text_processing.parser import DocumentChunk
from src.text_processing.retrieval import SemanticRetriever

MIN_DISTANCE = 0.05
MIN_WORDS = 8
SHORT_CASE_IDS = {"inter-wild-short"}
SHORT_PROMPT = "AI drones protecting endangered elephants"

CASES = evaluator.load_cases()


def _of_kind(kind: str) -> list[dict[str, Any]]:
    return [case for case in CASES if case["kind"] == kind]


# ---------- structure of the case set (no model) ----------


def test_the_set_is_marked_as_ai_drafted_and_unreviewed() -> None:
    payload = json.loads(evaluator.EVAL_FILE.read_text(encoding="utf-8"))
    assert "AI-drafted by Claude Code, not yet reviewed by a human" in payload["description"]


def test_size_and_unique_ids() -> None:
    assert 60 <= len(CASES) <= 90
    assert len({case["id"] for case in CASES}) == len(CASES)
    assert len({case["prompt"] + "".join(case["chunks"]) for case in CASES}) == len(CASES)


def test_every_case_has_the_expected_fields() -> None:
    for case in CASES:
        expected = {"id", "selected", "kind", "prompt", "chunks"}
        if case["kind"] == "mismatch":
            expected.add("expected_category")
            assert case["expected_category"] in CATEGORY_SLUG_MAP, case["id"]
            assert case["expected_category"] != case["selected"], case["id"]
        assert set(case) == expected, case["id"]
        assert case["kind"] in evaluator.KINDS, case["id"]
        assert case["selected"] in CATEGORY_SLUG_MAP, case["id"]
        assert case["prompt"].strip(), case["id"]
        assert all(isinstance(text, str) and text.strip() for text in case["chunks"]), case["id"]


def test_each_category_has_on_topic_and_mismatch_cases() -> None:
    on_topic = Counter(case["selected"] for case in _of_kind("on_topic"))
    mismatch = Counter(case["selected"] for case in _of_kind("mismatch"))
    for slug in CATEGORY_SLUG_MAP:
        assert on_topic[slug] >= 5, slug
        assert mismatch[slug] >= 3, slug


def test_interdisciplinary_and_required_mismatch_pairs() -> None:
    assert len(_of_kind("interdisciplinary")) >= 8
    pairs = {(case["selected"], case["expected_category"]) for case in _of_kind("mismatch")}
    assert {
        ("wildlife", "learning_experiences"),
        ("sports", "information_technology"),
        ("cinematography", "gender_studies"),
    } <= pairs


def test_only_the_deliberate_case_is_too_short() -> None:
    for case in CASES:
        _, whole_text = evaluator.build_guard_inputs(case["prompt"], case["chunks"])
        is_short = content_word_count(whole_text) < MIN_WORDS
        assert is_short == (case["id"] in SHORT_CASE_IDS), case["id"]


def test_elephant_case_has_a_short_and_a_long_variant() -> None:
    by_id = {case["id"]: case for case in CASES}
    short, long = by_id["inter-wild-short"], by_id["inter-wild-long"]
    assert short["prompt"] == SHORT_PROMPT
    assert short["selected"] == long["selected"] == "wildlife"
    assert "AI drones" in long["prompt"] and "endangered elephants" in long["prompt"]
    assert content_word_count(long["prompt"]) >= MIN_WORDS


def test_some_cases_carry_file_chunks() -> None:
    assert {case["kind"] for case in CASES if case["chunks"]} == set(evaluator.KINDS)


# ---------- the script itself (no model) ----------


def test_guard_inputs_match_the_route_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def capture(**kwargs: Any) -> CategoryCheckResult:
        seen.update(kwargs)
        return CategoryCheckResult(True, "sports", None, None, None, None, "skipped", "x")

    monkeypatch.setattr(script_guards, "check_category_alignment", capture)
    prompt = "First sentence. Second one!\r\nThird line"
    texts = [f"Chunk {index}. With two sentences." for index in range(30)]
    chunks = [DocumentChunk(index, "Notes", 1, text) for index, text in enumerate(texts, 1)]
    pipeline = type("Pipeline", (), {"template_engine": None, "template_store": None})()

    script_guards._assert_category(pipeline, "sports", prompt, chunks)

    assert evaluator.build_guard_inputs(prompt, texts) == (seen["segments"], seen["whole_text"])


def test_distance_to_block_is_zero_only_when_both_thresholds_are_reached() -> None:
    low, high = evaluator.BLOCK_SELECTED_MAX, evaluator.BLOCK_OTHER_MIN
    assert evaluator.distance_to_block(low - 0.01, high + 0.01) == 0
    assert evaluator.distance_to_block(low + 0.10, high + 0.01) == pytest.approx(0.10)
    assert evaluator.distance_to_block(low - 0.01, high - 0.20) == pytest.approx(0.20)
    assert evaluator.distance_to_block(low + 0.10, high - 0.20) == pytest.approx(0.20)


def test_a_fail_open_result_has_no_zone() -> None:
    result = CategoryCheckResult(
        True, "sports", None, None, None, None, "fail_open", "embedding_error"
    )
    with pytest.raises(evaluator.ModelUnavailableError, match="model not available"):
        evaluator.zone_of(result)


def test_main_prints_no_numbers_without_a_model(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path
) -> None:
    monkeypatch.setattr(SemanticRetriever, "get_model", classmethod(lambda cls: None))
    target = tmp_path / "results.json"

    assert evaluator.main(["--json", str(target)]) != 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "model not available" in captured.err
    assert not target.exists()


# ---------- calibration rule on the real model ----------


@pytest.fixture(scope="module")
def real_report() -> evaluator.Report:
    try:
        return evaluator.run_evaluation(CASES)
    except evaluator.ModelUnavailableError as exc:
        pytest.skip(str(exc))


def _describe(results: list[evaluator.CaseResult]) -> list[str]:
    return [
        f"{r.id}: selected={r.selected_score:.4f} "
        f"other={r.best_other_category}:{r.best_other_score:.4f} d={r.distance:.4f}"
        for r in results
    ]


@pytest.mark.integration
def test_no_legitimate_case_is_blocked(real_report: evaluator.Report) -> None:
    blocked = [
        r
        for r in real_report.results
        if r.kind in evaluator.MUST_PASS_KINDS and r.zone == "block"
    ]
    assert not blocked, "\n".join(_describe(blocked))


@pytest.mark.integration
def test_legitimate_cases_keep_their_distance_from_blocking(
    real_report: evaluator.Report,
) -> None:
    scored = [
        r
        for r in real_report.results
        if r.kind in evaluator.MUST_PASS_KINDS and r.zone != "skipped"
    ]
    assert scored
    close = [r for r in scored if r.distance < MIN_DISTANCE]
    assert not close, "\n".join(_describe(close))
