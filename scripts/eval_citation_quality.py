"""Evaluate citation quality BEFORE vs. AFTER Hybrid Source Classifier + Cross-Encoder NLI.

Runs on ``tests/fixtures/citation_eval_set.json`` (60 labelled scenarios across 6 categories)
and prints exact measured metrics (Precision, Recall, F1, Casual/Instruction False-Citation
Rate, Paraphrase Recall, Contradiction Leakage Rate, and Multi-Source Attribution Rate).

Usage:
    .venv\\Scripts\\python.exe scripts/eval_citation_quality.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.text_processing.contracts import DocumentChunk, ParagraphCitation  # noqa: E402
from src.text_processing.parser import parse_input_to_chunks  # noqa: E402
from src.text_processing.pipeline import _build_chat_note_chunks  # noqa: E402
from src.text_processing.retrieval import (  # noqa: E402
    _STOPWORDS,
    NLIVerifier,
    SemanticRetriever,
    align_script_citations,
)
from src.text_processing.sanitizer import sanitize_chunks, sanitize_text  # noqa: E402

EVAL_FILE = REPO_ROOT / "tests" / "fixtures" / "citation_eval_set.json"


# ---------------------------------------------------------------------------
# Faithful implementation of the LEGACY ("Before") pipeline for comparison
# ---------------------------------------------------------------------------


def _legacy_extract_tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return {t for t in raw if (len(t) >= 3 or t.isdigit()) and t not in _STOPWORDS}


def _legacy_is_verbatim_inline(query_or_para: str, chunk_text: str) -> bool:
    q_tokens = _legacy_extract_tokens(query_or_para)
    c_tokens = _legacy_extract_tokens(chunk_text)
    return bool(q_tokens and len(q_tokens) <= 4 and q_tokens <= c_tokens)


def _legacy_lexical_overlap(query_or_para: str, chunk_text: str) -> float:
    q_tokens = _legacy_extract_tokens(query_or_para)
    c_tokens = _legacy_extract_tokens(chunk_text)
    if not q_tokens or not c_tokens:
        return 0.0
    shared = q_tokens & c_tokens
    if not shared:
        return 0.0
    if _legacy_is_verbatim_inline(query_or_para, chunk_text):
        return 1.0
    if len(shared) < 2:
        return 0.0
    return len(shared) / min(len(q_tokens), 10)


def _legacy_build_chunks(case: dict[str, Any]) -> list[DocumentChunk]:
    """Legacy chunk builder: NO sub-chunking and ANY chat note >=8 words becomes a chunk."""
    chunks: list[DocumentChunk] = []
    if case.get("chunks"):
        for item in case["chunks"]:
            chunks.append(
                DocumentChunk(
                    chunk_id=int(item["chunk_id"]),
                    heading=str(item["heading"]),
                    page=int(item["page"]),
                    content=str(item["content"]),
                )
            )
    elif case.get("raw_doc"):
        # Legacy parser had max_chunk_words=0 (no sub-chunking)
        raw_chunks = parse_input_to_chunks(raw_text=case["raw_doc"], max_chunk_words=0)
        chunks.extend(sanitize_chunks(raw_chunks))

    note_num = 0
    for raw_note in case.get("user_notes", []):
        cleaned = sanitize_text(raw_note).strip()
        if len(cleaned.split()) < 8:
            continue
        note_num += 1
        chunks.append(
            DocumentChunk(
                chunk_id=len(chunks) + 1,
                heading=f"Chat note #{note_num}",
                page=0,
                content=cleaned,
            )
        )
    return chunks


def _legacy_align_single_paragraph(
    para_text: str,
    chunks: list[DocumentChunk],
    retriever: SemanticRetriever,
    min_support_score: float = 0.52,
) -> ParagraphCitation:
    """Legacy align_script_citations + verify_paragraph_citation (Bi-Encoder + lexical >= 0.25)."""
    if not chunks or not para_text.strip():
        return ParagraphCitation(paragraph=1, heading=None, page=None, status="uncited")

    chunk_embeddings = retriever.encode_chunks(chunks)
    emb_by_id = (
        {c.chunk_id: chunk_embeddings[i] for i, c in enumerate(chunks)}
        if (chunk_embeddings is not None and len(chunk_embeddings) == len(chunks))
        else None
    )
    top_candidates = retriever.retrieve_top_k(
        para_text,
        chunks,
        k=2,
        chunk_embeddings=chunk_embeddings,
        min_score=min_support_score,
    )
    if not top_candidates:
        return ParagraphCitation(paragraph=1, heading=None, page=None, status="uncited")

    model = retriever.get_model()
    para_vec = retriever._encode(model, [para_text])[0] if model is not None else None
    best_chunk: DocumentChunk | None = None
    best_score = -1.0

    for ch in top_candidates:
        c_full = f"{ch.heading}: {ch.content}"
        if _legacy_is_verbatim_inline(para_text, c_full):
            score = 1.0
        else:
            lex = _legacy_lexical_overlap(para_text, c_full)
            if para_vec is not None and emb_by_id is not None:
                sem = float(np.dot(emb_by_id[ch.chunk_id], para_vec))
                score = sem if lex >= 0.25 else -1.0
            else:
                score = lex
        if score > best_score:
            best_score = score
            best_chunk = ch

    if best_chunk is not None and best_score >= min_support_score:
        norm_page = best_chunk.page if best_chunk.page > 0 else None
        return ParagraphCitation(
            paragraph=1,
            heading=best_chunk.heading,
            page=norm_page,
            status="cited",
            chunk_id=best_chunk.chunk_id,
            sources=[
                {
                    "chunk_id": best_chunk.chunk_id,
                    "heading": best_chunk.heading,
                    "page": norm_page,
                }
            ],
        )
    return ParagraphCitation(paragraph=1, heading=None, page=None, status="uncited")


# ---------------------------------------------------------------------------
# New ("After") pipeline runner
# ---------------------------------------------------------------------------


def _new_build_chunks(case: dict[str, Any], retriever: SemanticRetriever) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    if case.get("chunks"):
        for item in case["chunks"]:
            chunks.append(
                DocumentChunk(
                    chunk_id=int(item["chunk_id"]),
                    heading=str(item["heading"]),
                    page=int(item["page"]),
                    content=str(item["content"]),
                )
            )
    elif case.get("raw_doc"):
        raw_chunks = parse_input_to_chunks(raw_text=case["raw_doc"])
        chunks.extend(sanitize_chunks(raw_chunks))

    if case.get("user_notes"):
        note_chunks = _build_chat_note_chunks(
            case["user_notes"],
            start_chunk_id=len(chunks) + 1,
            retriever=retriever,
        )
        chunks.extend(note_chunks)
    return chunks


def _compute_metrics(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    tp = sum(1 for r in records if r["expected"] and r[key])
    fp = sum(1 for r in records if (not r["expected"]) and r[key])
    fn = sum(1 for r in records if r["expected"] and (not r[key]))
    tn = sum(1 for r in records if (not r["expected"]) and (not r[key]))

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    acc = (tp + tn) / len(records) if records else 0.0

    def _rate(cat_list: list[str], pred_true: bool) -> tuple[int, int, float]:
        sub = [r for r in records if r["category"] in cat_list]
        hits = sum(1 for r in sub if r[key] == pred_true)
        return hits, len(sub), (hits / len(sub) if sub else 0.0)

    cas_fp, cas_n, cas_rate = _rate(["casual_leakage"], True)
    ins_fp, ins_n, ins_rate = _rate(["instruction_leakage"], True)
    con_fp, con_n, con_rate = _rate(["contradiction_and_altered_numbers"], True)
    src_tp, src_n, src_rate = _rate(["direct_and_mixed_source"], True)
    par_tp, par_n, par_rate = _rate(["paraphrased_grounding"], True)
    mul_tp, mul_n, mul_rate = _rate(["multihop_and_multisource"], True)

    multi_sub = [r for r in records if r.get("expected_min_sources", 0) >= 2]
    multi_full = sum(
        1 for r in multi_sub if r[f"{key}_num_sources"] >= r["expected_min_sources"]
    )

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": acc,
        "casual_fp": (cas_fp, cas_n, cas_rate),
        "instruction_fp": (ins_fp, ins_n, ins_rate),
        "contradiction_fp": (con_fp, con_n, con_rate),
        "direct_recall": (src_tp, src_n, src_rate),
        "paraphrase_recall": (par_tp, par_n, par_rate),
        "multihop_recall": (mul_tp, mul_n, mul_rate),
        "multisource_full": (
            multi_full,
            len(multi_sub),
            multi_full / len(multi_sub) if multi_sub else 0.0,
        ),
    }


def main() -> None:
    payload = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = payload["cases"]

    retriever = SemanticRetriever()
    nli = NLIVerifier()

    emb_model = retriever.get_model()
    nli_model = nli.get_model()
    emb_name = type(emb_model).__name__ if emb_model else "None (fallback)"
    nli_name = type(nli_model).__name__ if nli_model else "None (fallback)"
    print(f"Bi-Encoder loaded: {emb_name}")
    print(f"NLI Model ({nli.model_name}) loaded: {nli_name}")

    records: list[dict[str, Any]] = []
    t0_before = time.perf_counter()
    for case in cases:
        b_chunks = _legacy_build_chunks(case)
        b_cite = _legacy_align_single_paragraph(case["script_paragraph"], b_chunks, retriever)
        records.append(
            {
                "id": case["id"],
                "category": case["category"],
                "expected": bool(case["expected_cited"]),
                "expected_min_sources": int(case.get("expected_min_sources", 0)),
                "before": b_cite.status == "cited",
                "before_num_sources": len(b_cite.sources) if b_cite.status == "cited" else 0,
            }
        )
    dt_before = time.perf_counter() - t0_before

    t0_after = time.perf_counter()
    for idx, case in enumerate(cases):
        a_chunks = _new_build_chunks(case, retriever)
        if a_chunks:
            aligned = align_script_citations(
                case["script_paragraph"],
                a_chunks,
                retriever=retriever,
                nli_verifier=nli,
            )
            a_cite = aligned[0]
        else:
            a_cite = ParagraphCitation(paragraph=1, heading=None, page=None, status="uncited")
        records[idx]["after"] = a_cite.status == "cited"
        records[idx]["after_num_sources"] = len(a_cite.sources) if a_cite.status == "cited" else 0
    dt_after = time.perf_counter() - t0_after

    m_before = _compute_metrics(records, "before")
    m_after = _compute_metrics(records, "after")

    print(f"\n=== CITATION QUALITY BENCHMARK (N = {len(records)} labelled cases) ===")
    print(f"Total runtime — Before: {dt_before:.2f}s | After: {dt_after:.2f}s\n")
    header = f"{'Metric':<42} | {'Before':<18} | {'After':<18}"
    print(header)
    print("-" * len(header))
    for title, key_m in [
        ("Overall Precision", "precision"),
        ("Overall Recall", "recall"),
        ("Overall F1 Score", "f1"),
        ("Overall Accuracy", "accuracy"),
    ]:
        bv = m_before[key_m] * 100
        av = m_after[key_m] * 100
        print(f"{title:<42} | {bv:6.2f}%            | {av:6.2f}%")
    b_quad = f"{m_before['tp']}/{m_before['fp']}/{m_before['fn']}/{m_before['tn']}"
    a_quad = f"{m_after['tp']}/{m_after['fp']}/{m_after['fn']}/{m_after['tn']}"
    print(f"{'TP / FP / FN / TN':<42} | {b_quad:<18} | {a_quad}")

    for label, field_name in [
        ("Casual Chat False-Cite Rate (lower=better)", "casual_fp"),
        ("Instruction False-Cite Rate (lower=better)", "instruction_fp"),
        ("Contradiction Leakage Rate (lower=better)", "contradiction_fp"),
        ("Direct/Mixed/Long-Doc Recall (higher=better)", "direct_recall"),
        ("Paraphrase Grounding Recall (higher=better)", "paraphrase_recall"),
        ("Multi-Hop Synthesis Recall (higher=better)", "multihop_recall"),
        ("Multi-Source (>=2 sources) Recall", "multisource_full"),
    ]:
        b_cnt, b_tot, b_rt = m_before[field_name]
        a_cnt, a_tot, a_rt = m_after[field_name]
        b_col = f"{b_cnt:>2}/{b_tot:<2} ({b_rt * 100:5.1f}%)"
        a_col = f"{a_cnt:>2}/{a_tot:<2} ({a_rt * 100:5.1f}%)"
        print(f"{label:<42} | {b_col:<18} | {a_col}")

    misses_after = [r for r in records if r["after"] != r["expected"]]
    if misses_after:
        print("\nRemaining After mismatches:")
        for m in misses_after:
            print(f"  - {m['id']} ({m['category']}): expected={m['expected']}, got={m['after']}")
    else:
        print("\nZero classification/verification errors in After!")


if __name__ == "__main__":
    main()
