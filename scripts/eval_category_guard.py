"""Evaluate layer 1 of the category guard offline, with the real embedding model.

Runs ``check_category_alignment`` with ``allow_llm=False`` and no client on the labelled cases of
``tests/fixtures/category_guard_eval_set.json`` and prints the measured scores. The cases are
AI-drafted and not yet reviewed by a human. Thresholds are only read, never changed.

Usage:
    HF_HUB_OFFLINE=1 uv run python scripts/eval_category_guard.py [--json PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.app.constants import CONSTANTS  # noqa: E402
from src.text_processing import category_guard  # noqa: E402
from src.text_processing.category_guard import (  # noqa: E402
    CategoryCheckResult,
    check_category_alignment,
    split_segments,
)
from src.text_processing.contracts import CATEGORY_SLUG_MAP  # noqa: E402
from src.text_processing.parser import DocumentChunk  # noqa: E402
from src.text_processing.retrieval import SemanticRetriever  # noqa: E402
from src.text_processing.template_store import TemplateStore  # noqa: E402

EVAL_FILE = REPO_ROOT / "tests" / "fixtures" / "category_guard_eval_set.json"

_CONFIG = CONSTANTS["script_guard"]
MAX_SEGMENTS = int(_CONFIG["category_guard_max_segments"])
BLOCK_SELECTED_MAX = float(_CONFIG["category_guard_block_selected_max"])
BLOCK_OTHER_MIN = float(_CONFIG["category_guard_block_other_min"])

ZONES = ("block", "gray", "safe", "skipped")
KINDS = ("on_topic", "interdisciplinary", "mismatch")
MUST_PASS_KINDS = ("on_topic", "interdisciplinary")
_ZONE_BY_REASON = {"safe": "safe", "mismatch": "block", "gray_allowed": "gray"}
_CLOSEST_SHOWN = 5


class ModelUnavailableError(RuntimeError):
    """Layer 1 could not score with the real model, so there are no numbers to report."""


@dataclass(frozen=True)
class CaseResult:
    """Measured outcome of one case; scores are None when the guard skipped it."""

    id: str
    kind: str
    selected: str
    expected_category: str | None
    selected_score: float | None
    best_other_category: str | None
    best_other_score: float | None
    margin: float | None
    zone: str
    suggested_category: str | None
    distance: float | None


@dataclass(frozen=True)
class Report:
    """All case results plus the prototype sizes and the first prototype encode time."""

    results: list[CaseResult]
    prototype_titles: dict[str, int]
    prototype_texts: dict[str, int]
    prototype_encode_s: float


def load_cases(path: Path = EVAL_FILE) -> list[dict[str, Any]]:
    """The labelled cases of the evaluation set."""
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def build_guard_inputs(prompt: str, chunk_texts: Sequence[str]) -> tuple[list[str], str]:
    """`segments` and `whole_text`, joined as `src/app/script_guards.py::_assert_category` does."""
    chunks = [DocumentChunk(index, "Notes", 1, text) for index, text in enumerate(chunk_texts, 1)]
    segments = split_segments(prompt, chunks, max_segments=MAX_SEGMENTS)
    whole_text = "\n".join(text for text in (prompt, *(c.content for c in chunks)) if text)
    return segments, whole_text


def distance_to_block(selected_score: float, best_other_score: float) -> float:
    """How far the scores are from the block zone; 0 on or inside both block thresholds."""
    return max(
        max(0.0, selected_score - BLOCK_SELECTED_MAX),
        max(0.0, BLOCK_OTHER_MIN - best_other_score),
    )


def zone_of(result: CategoryCheckResult) -> str:
    """The zone of a layer 1 result; a fail-open result has no zone and raises."""
    if result.layer == "skipped":
        return "skipped"
    if result.layer == "embedding" and result.reason in _ZONE_BY_REASON:
        return _ZONE_BY_REASON[result.reason]
    raise ModelUnavailableError(
        f"model not available: layer={result.layer} reason={result.reason}"
    )


def evaluate_case(
    case: dict[str, Any], retriever: SemanticRetriever, store: TemplateStore
) -> CaseResult:
    """Run the guard on one case without any LLM."""
    segments, whole_text = build_guard_inputs(case["prompt"], case["chunks"])
    result = check_category_alignment(
        selected_category=case["selected"],
        segments=segments,
        whole_text=whole_text,
        retriever=retriever,
        template_store=store,
        client=None,
        allow_llm=False,
    )
    selected, other = result.selected_score, result.best_other_score
    scored = selected is not None and other is not None
    return CaseResult(
        id=case["id"],
        kind=case["kind"],
        selected=case["selected"],
        expected_category=case.get("expected_category"),
        selected_score=selected,
        best_other_category=result.best_other_category,
        best_other_score=other,
        margin=other - selected if scored else None,
        zone=zone_of(result),
        suggested_category=result.suggested_category,
        distance=distance_to_block(selected, other) if scored else None,
    )


def run_evaluation(cases: list[dict[str, Any]]) -> Report:
    """Load the real model and templates, time the prototype encoding, then score every case."""
    retriever = SemanticRetriever()
    model = category_guard._usable_model(retriever)
    if model is None:
        raise ModelUnavailableError("model not available")
    store = TemplateStore()
    store.load()
    texts = {slug: category_guard._prototype_texts(slug, store) for slug in CATEGORY_SLUG_MAP}
    titles = {
        slug: len(items) - len(category_guard._HANDWRITTEN[slug]) for slug, items in texts.items()
    }
    try:
        started = time.perf_counter()
        category_guard._prototype_matrices(retriever, model, store)
        encode_s = time.perf_counter() - started
    except Exception as exc:
        raise ModelUnavailableError(f"model not available: {type(exc).__name__}") from exc
    return Report(
        results=[evaluate_case(case, retriever, store) for case in cases],
        prototype_titles=titles,
        prototype_texts={slug: len(items) for slug, items in texts.items()},
        prototype_encode_s=encode_s,
    )


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def _table(results: list[CaseResult]) -> list[str]:
    header = (
        f"{'id':<18} {'kind':<17} {'selected':<22} {'sel_score':>9} "
        f"{'best_other':<22} {'oth_score':>9} {'margin':>8} {'zone':<7} {'d':>7}"
    )
    lines = [header, "-" * len(header)]
    for r in results:
        lines.append(
            f"{r.id:<18} {r.kind:<17} {r.selected:<22} {_number(r.selected_score):>9} "
            f"{r.best_other_category or '-':<22} {_number(r.best_other_score):>9} "
            f"{_number(r.margin):>8} {r.zone:<7} {_number(r.distance):>7}"
        )
    return lines


def _zone_counts(results: list[CaseResult]) -> str:
    counts = Counter(r.zone for r in results)
    return " | ".join(f"{zone}={counts[zone]}" for zone in ZONES)


def _summary(results: list[CaseResult]) -> list[str]:
    mismatches = [r for r in results if r.kind == "mismatch"]
    blocked = [r for r in mismatches if r.zone == "block"]
    right = sum(1 for r in blocked if r.suggested_category == r.expected_category)
    lines = [
        f"mismatch (N={len(mismatches)}): {_zone_counts(mismatches)}",
        f"  blocked with suggested == expected_category: {right}/{len(blocked)}",
    ]
    for kind in MUST_PASS_KINDS:
        group = [r for r in results if r.kind == kind]
        lines.append(f"{kind} (N={len(group)}): {_zone_counts(group)}")
    closest = sorted(
        (r for r in results if r.kind in MUST_PASS_KINDS and r.distance is not None),
        key=lambda r: (r.distance, r.id),
    )
    if closest:
        lines.append(
            f"smallest d among on_topic + interdisciplinary: {closest[0].distance:.4f} "
            f"({closest[0].id})"
        )
        lines.append(f"{_CLOSEST_SHOWN} on_topic/interdisciplinary cases closest to blocking:")
        lines.extend(
            f"  {r.id:<18} d={r.distance:.4f} selected_score={r.selected_score:.4f} "
            f"best_other={r.best_other_category}:{r.best_other_score:.4f} zone={r.zone}"
            for r in closest[:_CLOSEST_SHOWN]
        )
    return lines


def format_report(report: Report) -> str:
    """Per-case table, zone summary, prototype sizes and the measured encode time."""
    lines = [
        f"Category guard layer 1, N={len(report.results)} cases, allow_llm=False",
        "Cases: AI-drafted, not yet reviewed by a human.",
        f"Block thresholds: selected_score < {BLOCK_SELECTED_MAX} and "
        f"best_other_score >= {BLOCK_OTHER_MIN}",
        "",
        *_table(report.results),
        "",
        *_summary(report.results),
        "",
        "Prototypes per category (template titles / all prototype texts):",
        *(
            f"  {slug:<22} {report.prototype_titles[slug]:>3} / {report.prototype_texts[slug]}"
            for slug in report.prototype_titles
        ),
        f"First prototype encode time: {report.prototype_encode_s:.3f} s",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the report; return 2 without any number when the model cannot score."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="also write the results to this file")
    args = parser.parse_args(argv)
    try:
        report = run_evaluation(load_cases())
    except ModelUnavailableError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(format_report(report))
    if args.json:
        args.json.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
