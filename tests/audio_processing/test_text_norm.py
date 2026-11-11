import time

import pytest

from src.audio_processing.text_norm import (
    FILLER_WORDS,
    PAUSE_PUNCT,
    SENTENCE_END,
    indexed_subtokens,
    is_filler,
    make_raw_key,
    normalize_script,
    normalize_token,
    split_sentences,
    trailing_punct,
)


def test_normalize_keeps_possessive_apostrophe():
    assert normalize_token("john's") == ("john's",)
    assert normalize_token("students'") == ("students'",)


def test_oclock_expands_to_three_subtokens_one_ref_index():
    tokens = normalize_script("at three o'clock")
    assert tokens[2].ref_index == 2
    assert tokens[2].subtokens == ("of", "the", "clock")
    assert indexed_subtokens(tokens)[-3:] == [(2, "of"), (2, "the"), (2, "clock")]


def test_normalize_returns_raw_and_normalized():
    tokens = normalize_script("Hello, world.")
    assert [t.raw for t in tokens] == ["Hello,", "world."]
    assert [t.subtokens for t in tokens] == [("hello",), ("world",)]


def test_dont_expands_to_do_not_same_ref_index():
    tokens = normalize_script("I don't know")
    assert tokens[1].ref_index == 1
    assert tokens[1].subtokens == ("do", "not")


def test_cant_becomes_cannot_single_token():
    assert normalize_token("can't") == ("cannot",)


def test_digit_to_words():
    assert normalize_token("3") == ("three",)


def test_split_sentences_three():
    assert split_sentences("Hello world. How are you? Fine!") == [
        (0, 2, "Hello world."),
        (2, 5, "How are you?"),
        (5, 6, "Fine!"),
    ]


def test_split_sentences_trailing_without_punct():
    assert split_sentences("First one. And then the rest") == [
        (0, 2, "First one."),
        (2, 6, "And then the rest"),
    ]


def test_curly_apostrophe_and_nfc():
    assert normalize_token("don’t") == normalize_token("don't") == ("do", "not")
    nfd = "café"
    nfc = "café"
    assert normalize_token(nfd) == normalize_token(nfc)
    assert make_raw_key(nfd) == make_raw_key(nfc)


def test_thousands_separator():
    assert normalize_token("1,000") == ("one", "thousand")


def test_hyphen_splits_same_ref_index():
    tokens = normalize_script("a well-known fact")
    assert tokens[1].subtokens == ("well", "known")
    assert [i for i, _ in indexed_subtokens(tokens)] == [0, 1, 1, 2]


def test_punct_only_token_kept_in_n_ref():
    tokens = normalize_script("wait — stop")
    assert len(tokens) == 3
    assert tokens[1].raw == "—"
    assert tokens[1].subtokens == ()
    assert normalize_token("—") == ()


def test_raw_key_strips_edges():
    assert make_raw_key("He's,") == make_raw_key("he's") == "he's"
    assert make_raw_key("students'") == "students'"
    assert make_raw_key("'tis") == "tis"


def test_ref_index_contiguous():
    script = "Well-known facts, don't you think? Yes — 3 of them."
    tokens = normalize_script(script)
    assert len(tokens) == len(script.split())
    assert [t.ref_index for t in tokens] == list(range(len(tokens)))


def test_split_sentences_closing_quote():
    assert split_sentences('He said "stop." Then left') == [
        (0, 3, 'He said "stop."'),
        (3, 5, "Then left"),
    ]


def test_split_sentences_empty():
    assert split_sentences("") == []


def test_is_filler():
    assert is_filler("um") is True
    assert is_filler("Uh,") is True
    assert is_filler("like") is False
    assert is_filler("you") is False


def test_capitalized_contraction_lowercased():
    assert normalize_token("I'm") == ("i", "am")


@pytest.mark.parametrize("filler_char", ["-", ".", "'", "$", "%"])
def test_normalize_token_long_run_is_fast(filler_char):
    token = "a" + filler_char * 20000 + "b"
    t0 = time.perf_counter()
    normalize_token(token)
    make_raw_key(token)
    assert time.perf_counter() - t0 < 0.5


def test_thousands_comma_only_when_valid():
    assert normalize_token("1,000") == ("one", "thousand")
    assert normalize_token("1,2,3") == ("one", "two", "three")
    assert normalize_token("1,2,3") != ("one", "hundred", "and", "twenty", "three")


def test_subtoken_edge_apostrophes_trimmed():
    assert normalize_token("word-'quote'") == ("word", "quote")
    assert normalize_token("a-'b") == ("a", "b")
    assert normalize_token("rock'n'roll") == ("rock'n'roll",)


def test_huge_number_does_not_raise():
    assert normalize_token("1" * 400) == ("1" * 400,)


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("'", ()),
        ("''", ()),
        ("'90s", ("90s",)),
        ("i.e.", ("i", "e")),
    ],
)
def test_edge_cases(token, expected):
    assert normalize_token(token) == expected


def test_normalize_script_multiple_whitespace():
    tokens = normalize_script("a  b\nc")
    assert len(tokens) == 3
    assert [t.ref_index for t in tokens] == [0, 1, 2]


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("$5", ("five", "dollars")),
        ("$1", ("one", "dollar")),
        ("50%", ("fifty", "percent")),
        ("(50%).", ("fifty", "percent")),
        ("$1,000", ("one", "thousand", "dollars")),
        ("$1.00", ("one", "dollar")),
        ("$01", ("one", "dollar")),
        ("$1.0", ("one", "dollar")),
        ("$1.5", ("one", "point", "five", "dollars")),
        ("$0", ("zero", "dollars")),
        ("$2", ("two", "dollars")),
        ("$50%", ("fifty",)),
        ("5$", ("five",)),
        ("%50", ("fifty",)),
        ("$", ()),
        ("%", ()),
        ("US$5", ("us", "five")),
        ("$5.50", ("five", "point", "five", "dollars")),
    ],
)
def test_money_and_percent(token, expected):
    assert normalize_token(token) == expected


@pytest.mark.parametrize(
    ("symbol_form", "spoken_form"),
    [("$5", "five dollars"), ("50%", "fifty percent")],
)
def test_money_percent_symmetric_with_spoken(symbol_form, spoken_form):
    spoken = tuple(s for w in spoken_form.split() for s in normalize_token(w))
    assert normalize_token(symbol_form) == spoken


def test_money_raw_key_unchanged():
    assert make_raw_key("$5") == "5"


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        ("Wait?! Go", [(0, 1, "Wait?!"), (1, 2, "Go")]),
        ("(Yes.) No", [(0, 1, "(Yes.)"), (1, 2, "No")]),
        ("'go.' now", [(0, 1, "'go.'"), (1, 2, "now")]),
        ("a.b c", [(0, 2, "a.b c")]),
        ("e.g., then", [(0, 2, "e.g., then")]),
        ("Really? ...", [(0, 2, "Really? ...")]),
        ("... Hello.", [(0, 2, "... Hello.")]),
        ("Hi. —", [(0, 2, "Hi. —")]),
        ("Done. ! Next.", [(0, 2, "Done. !"), (2, 3, "Next.")]),
        ("—", [(0, 1, "—")]),
    ],
)
def test_split_sentences_rules(script, expected):
    assert split_sentences(script) == expected


def test_split_sentences_cover_contiguously():
    script = "... Hi. ! Next? — Last"
    spans = split_sentences(script)
    assert spans[0][0] == 0 and spans[-1][1] == len(script.split())
    assert all(a[1] == b[0] for a, b in zip(spans, spans[1:], strict=False))
    assert all(a < b for a, b, _ in spans)


def test_trailing_punct():
    assert trailing_punct('end."') == "."
    assert trailing_punct("Wait?!") == "?!"
    assert trailing_punct("Hi,") == ","
    assert trailing_punct("(Yes.)") == "."
    assert trailing_punct("word") == ""
    # ADR: "ký tự cuối liên tiếp" cho ".," (không phải ","); điều quan trọng là không đóng câu
    assert trailing_punct("e.g.,")[-1] == ","


def test_trailing_punct_consecutive_chars():
    assert trailing_punct("e.g.,") == ".,"


def test_punct_constants():
    assert PAUSE_PUNCT == frozenset(".,;:?!")
    assert SENTENCE_END == frozenset(".!?")


def test_filler_words_exact():
    assert FILLER_WORDS == frozenset(
        "uh um er ah hmm uhm umm uhh erm ahh hm hmmm mm mmm".split()
    )
