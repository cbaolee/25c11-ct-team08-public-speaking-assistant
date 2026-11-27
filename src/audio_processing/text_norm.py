"""Text normalization shared by scoring and vad (ADR-005 P12, ADR-004 D2/D19/D20)."""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import contractions
from num2words import num2words

FILLER_WORDS: frozenset[str] = frozenset(
    {
        "uh",
        "um",
        "er",
        "ah",
        "hmm",
        "uhm",
        "umm",
        "uhh",
        "erm",
        "ahh",
        "hm",
        "hmmm",
        "mm",
        "mmm",
    }
)

_CURLY_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})
_NUMBER_RE = re.compile(r"\d+(\.\d+)?")
_THOUSANDS_RE = re.compile(r"\d{1,3}(,\d{3})+(\.\d+)?")  # valid thousands commas
_SPLIT_RE = re.compile(r"[^\w']|_")  # any character that is not a letter, digit or '
_NUM2WORDS_ERRORS = (OverflowError, ValueError, KeyError, InvalidOperation)
PAUSE_PUNCT: frozenset[str] = frozenset(".,;:?!")
SENTENCE_END: frozenset[str] = frozenset(".!?")
_CLOSERS = "\"'”’)]}"


@dataclass(frozen=True)
class RefToken:
    """One original script token (from script.split()) with its normalized sub-tokens."""

    ref_index: int  # position in script.split()
    raw: str  # original token, punctuation kept
    raw_key: str  # original form used for matching before expansion (ADR-005 P12 point 2)
    subtokens: tuple[str, ...]  # normalized sub-tokens; () for a punctuation-only token


def _trim_edges(text: str) -> tuple[str, str, str]:
    """Trim both ends in linear O(n): return (trimmed head, core, trimmed tail).

    "Not a letter/digit" = not str.isalnum() (same set as the old regex: non-word or underscore).
    """
    start, end = 0, len(text)
    while start < end and not text[start].isalnum():
        start += 1
    while end > start and not text[end - 1].isalnum():
        end -= 1
    return text[:start], text[start:end], text[end:]


def _clean(text: str) -> str:
    """Trim both ends; keep inner '; a final ' is kept only right after 's'."""
    _, core, tail = _trim_edges(text)
    if core.endswith("s") and tail.startswith("'"):
        core += "'"
    return core


def _prepare(token: str) -> str:
    return unicodedata.normalize("NFC", token).translate(_CURLY_APOSTROPHES).lower()


def make_raw_key(token: str) -> str:
    """NFC, curly quotes to ', lowercase, drop non-letter/digit characters at both ends.

    Keep inner '; a final ' is kept only when the character before it is 's'.
    """
    return _clean(_prepare(token))


def _number_pieces(digits: str) -> list[str]:
    """Number (thousands commas removed) to words; if num2words fails, keep the digits."""
    try:
        return [num2words(digits)]
    except _NUM2WORDS_ERRORS:
        return [digits]


def _convert_part(part: str) -> list[str]:
    """One part (after contractions) -> pieces; valid numbers go through num2words."""
    if _THOUSANDS_RE.fullmatch(part):
        return _number_pieces(part.replace(",", ""))
    if _NUMBER_RE.fullmatch(part):
        return _number_pieces(part)
    # Not one whole number: split first ("1,2,3" -> "1","2","3"), then convert each number piece
    out: list[str] = []
    for piece in _SPLIT_RE.split(part):
        out.extend(_number_pieces(piece) if _NUMBER_RE.fullmatch(piece) else [piece])
    return out


def _finish(parts: list[str]) -> tuple[str, ...]:
    """Split pieces at non letter/digit/' characters, trim ' at both ends, drop empties."""
    subs = (_clean(p) for part in parts for p in _SPLIT_RE.split(part))
    return tuple(p for p in subs if p)


def _money_or_percent(text: str) -> tuple[str, ...] | None:
    """Rule A: '$<number>' and '<number>%' (leading $ / trailing % kept). None if no match."""
    head, core, tail = _trim_edges(text)
    is_money = head.endswith("$")
    is_percent = tail.startswith("%")
    if is_money == is_percent:  # neither, or both ($50%): handle as a normal token
        return None
    if not (_THOUSANDS_RE.fullmatch(core) or _NUMBER_RE.fullmatch(core)):
        return None
    digits = core.replace(",", "")
    words = _convert_part(digits)
    if is_percent:
        unit = "percent"
    else:
        unit = "dollar" if Decimal(digits) == 1 else "dollars"
    return _finish([*words, unit])


def normalize_token(token: str) -> tuple[str, ...]:
    """raw_key -> contractions.fix -> lowercase -> numbers to words -> split into sub-tokens."""
    money = _money_or_percent(_prepare(token))
    if money is not None:
        return money
    key = make_raw_key(token)
    if not key:
        return ()
    parts: list[str] = []
    for part in contractions.fix(key).lower().split():
        parts.extend(_convert_part(part))
    return _finish(parts)


def normalize_script(script: str) -> list[RefToken]:
    """Each script.split() token becomes one RefToken; N_ref = len(result) (D2)."""
    return [
        RefToken(i, raw, make_raw_key(raw), normalize_token(raw))
        for i, raw in enumerate(script.split())
    ]


def indexed_subtokens(tokens: list[RefToken]) -> list[tuple[int, str]]:
    """Flatten to [(ref_index, subtoken), ...] in order."""
    return [(t.ref_index, sub) for t in tokens for sub in t.subtokens]


def trailing_punct(raw: str) -> str:
    """Drop closing characters (" ' ” ’ ) ] }) at the end, return the trailing PAUSE_PUNCT run."""
    end = len(raw)
    while end > 0 and raw[end - 1] in _CLOSERS:
        end -= 1
    start = end
    while start > 0 and raw[start - 1] in PAUSE_PUNCT:
        start -= 1
    return raw[start:end]


def split_sentences(script: str) -> list[tuple[int, int, str]]:
    """Split sentences by D19 + rule B. Returns [(ref_start, ref_end, text)], half-open ranges.

    A sentence closes only when one of its tokens has sub-tokens; punctuation-only tokens join
    the previous sentence.
    """
    words = script.split()
    spans: list[tuple[int, int]] = []
    start = 0
    has_word = False
    for i, word in enumerate(words):
        has_word = has_word or bool(normalize_token(word))
        punct = trailing_punct(word)
        if not punct or punct[-1] not in SENTENCE_END:
            continue
        if has_word:
            spans.append((start, i + 1))
        elif spans:
            spans[-1] = (spans[-1][0], i + 1)
        else:
            continue  # no previous sentence yet: keep adding to the open one
        start = i + 1
        has_word = False
    if start < len(words):
        if has_word or not spans:
            spans.append((start, len(words)))
        else:
            spans[-1] = (spans[-1][0], len(words))
    return [(a, b, " ".join(words[a:b])) for a, b in spans]


def is_filler(token: str) -> bool:
    """True if make_raw_key(token) is in FILLER_WORDS (hyp side only)."""
    return make_raw_key(token) in FILLER_WORDS
