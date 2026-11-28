"""Gibberish guard (contract E v2): shared vectors, rule edges, word counting, long input."""

import json
import time
from pathlib import Path

import pytest

from src.text_processing.input_guard import content_word_count, content_words, is_gibberish

VECTORS_PATH = Path(__file__).parent / "fixtures" / "gibberish_vectors.json"
VECTORS = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
LONG_TOKEN_CHARS = 18_000
LONG_TOKEN_BUDGET_S = 2.0


@pytest.mark.parametrize("case", VECTORS, ids=lambda case: ascii(case["input"]))
def test_shared_vector(case):
    refused = is_gibberish(case["input"], has_file=case.get("has_file", False))
    assert ("REJECT" if refused else "ALLOW") == case["expected"], case["rule"]


@pytest.mark.parametrize(
    ("text", "refused"),
    [
        ("aaaa ok", False),
        ("aaaa", False),  # T1 needs 5 in a row
        ("bcdfg", False),  # T3 needs 6 letters
        ("bcdfgh", True),
        ("BCDFGHK", False),  # all caps needs 8 letters
        ("BCDFGHKL", True),
        ("helasdfo", False),  # 4 neighbouring keys inside a longer word
        ("helasdfgo", True),
        ("heloiuytlo", True),  # reversed row
        ("bla bla bla", False),  # R4 needs 4 words
        ("a\tb\vc\fd\re", False),
    ],
)
def test_rule_edges(text, refused):
    assert is_gibberish(text) is refused


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("", 0),
        ("   ", 0),
        ("Climate change in the Mekong Delta", 6),
        ("5 100000 !!! \U0001f600", 0),
        ("COVID-19 (AI), 2024.", 2),
        ("TP.HCM", 1),
        ("one\ttwo\nthree\vfour\ffive\rsix", 6),
        ("one two three four　five", 5),
        ("one\u001ctwo\u001dthree\u001efour\u001ffive\u0085six﻿seven", 1),
        ("Viẹt Nam", 2),
    ],
)
def test_content_word_count(text, count):
    assert content_word_count(text) == count


def test_content_words_keep_case_and_drop_edges_and_numbers():
    assert content_words("COVID-19 (AI), 2024 !!! TP.HCM.") == ["COVID-19", "AI", "TP.HCM"]


@pytest.mark.parametrize(("tail", "refused"), [("speaking", False), ("asdfgabc", True)])
def test_very_long_token_is_judged_quickly(tail, refused):
    body = "speaking" * (LONG_TOKEN_CHARS // len("speaking") - 1)
    text = body + tail
    assert len(text) == LONG_TOKEN_CHARS

    started = time.perf_counter()
    result = is_gibberish(text)
    elapsed_s = time.perf_counter() - started

    assert result is refused
    assert elapsed_s < LONG_TOKEN_BUDGET_S
