"""Chuẩn hoá văn bản dùng chung cho scoring và vad (ADR-005 P12, ADR-004 D2/D19/D20)."""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import contractions
from num2words import num2words

FILLER_WORDS: frozenset[str] = frozenset(
    {
        "uh", "um", "er", "ah", "hmm", "uhm", "umm", "uhh",
        "erm", "ahh", "hm", "hmmm", "mm", "mmm",
    }
)

_CURLY_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})
_NUMBER_RE = re.compile(r"\d+(\.\d+)?")
_THOUSANDS_RE = re.compile(r"\d{1,3}(,\d{3})+(\.\d+)?")  # phẩy nghìn hợp lệ
_SPLIT_RE = re.compile(r"[^\w']|_")  # mọi ký tự không phải chữ, số hoặc '
_NUM2WORDS_ERRORS = (OverflowError, ValueError, KeyError, InvalidOperation)
PAUSE_PUNCT: frozenset[str] = frozenset(".,;:?!")
SENTENCE_END: frozenset[str] = frozenset(".!?")
_CLOSERS = "\"'”’)]}"


@dataclass(frozen=True)
class RefToken:
    """Một token gốc của kịch bản (theo script.split()) cùng các token con đã chuẩn hoá."""

    ref_index: int  # vị trí trong script.split()
    raw: str  # token gốc, giữ nguyên dấu câu
    raw_key: str  # dạng gốc để so khớp trước khi bung (ADR-005 P12 ý 2)
    subtokens: tuple[str, ...]  # token con đã chuẩn hoá; () nếu token chỉ có dấu câu


def _trim_edges(text: str) -> tuple[str, str, str]:
    """Cắt hai đầu tuyến tính O(n): trả (đầu bị cắt, lõi, đuôi bị cắt).

    Ký tự "không phải chữ/số" = not str.isalnum() (cùng tập với regex cũ: non-word hoặc gạch dưới).
    """
    start, end = 0, len(text)
    while start < end and not text[start].isalnum():
        start += 1
    while end > start and not text[end - 1].isalnum():
        end -= 1
    return text[:start], text[start:end], text[end:]


def _clean(text: str) -> str:
    """Cắt hai đầu; giữ ' bên trong; ' cuối chỉ giữ khi ngay trước là 's'."""
    _, core, tail = _trim_edges(text)
    if core.endswith("s") and tail.startswith("'"):
        core += "'"
    return core


def _prepare(token: str) -> str:
    return unicodedata.normalize("NFC", token).translate(_CURLY_APOSTROPHES).lower()


def make_raw_key(token: str) -> str:
    """NFC, đổi nháy cong thành ', lowercase, bỏ ký tự không phải chữ/số ở hai đầu.

    Giữ ' bên trong; ' ở cuối chỉ giữ khi ngay trước nó là 's'.
    """
    return _clean(_prepare(token))


def _number_pieces(digits: str) -> list[str]:
    """Số (đã bỏ phẩy nghìn) thành chữ; lỗi num2words thì giữ chữ số."""
    try:
        return [num2words(digits)]
    except _NUM2WORDS_ERRORS:
        return [digits]


def _convert_part(part: str) -> list[str]:
    """Một phần (sau contractions) -> các mảnh; số hợp lệ qua num2words."""
    if _THOUSANDS_RE.fullmatch(part):
        return _number_pieces(part.replace(",", ""))
    if _NUMBER_RE.fullmatch(part):
        return _number_pieces(part)
    # Không phải số nguyên khối: tách trước ("1,2,3" -> "1","2","3"), rồi đổi từng mảnh số
    out: list[str] = []
    for piece in _SPLIT_RE.split(part):
        out.extend(_number_pieces(piece) if _NUMBER_RE.fullmatch(piece) else [piece])
    return out


def _finish(parts: list[str]) -> tuple[str, ...]:
    """Tách mọi mảnh tại ký tự không phải chữ/số/', cắt ' ở hai đầu từng token con, bỏ rỗng."""
    subs = (_clean(p) for part in parts for p in _SPLIT_RE.split(part))
    return tuple(p for p in subs if p)


def _money_or_percent(text: str) -> tuple[str, ...] | None:
    """Luật A: '$<số>' và '<số>%' (giữ $ đầu, % cuối khi cắt dấu câu). None nếu không khớp."""
    head, core, tail = _trim_edges(text)
    is_money = head.endswith("$")
    is_percent = tail.startswith("%")
    if is_money == is_percent:  # không có, hoặc cả hai ($50%): xử lý như token thường
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
    """raw_key -> contractions.fix -> lowercase lại -> số thành chữ -> tách token con."""
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
    """Mỗi token của script.split() thành một RefToken; N_ref = len(kết quả) (D2)."""
    return [
        RefToken(i, raw, make_raw_key(raw), normalize_token(raw))
        for i, raw in enumerate(script.split())
    ]


def indexed_subtokens(tokens: list[RefToken]) -> list[tuple[int, str]]:
    """Phẳng hoá thành [(ref_index, subtoken), ...] theo thứ tự."""
    return [(t.ref_index, sub) for t in tokens for sub in t.subtokens]


def trailing_punct(raw: str) -> str:
    """Bỏ ký tự đóng (" ' ” ’ ) ] }) ở cuối, rồi trả các ký tự cuối liên tiếp thuộc PAUSE_PUNCT."""
    end = len(raw)
    while end > 0 and raw[end - 1] in _CLOSERS:
        end -= 1
    start = end
    while start > 0 and raw[start - 1] in PAUSE_PUNCT:
        start -= 1
    return raw[start:end]


def split_sentences(script: str) -> list[tuple[int, int, str]]:
    """Tách câu theo D19 + luật B. Trả [(ref_start, ref_end, text)], khoảng nửa mở.

    Câu chỉ đóng khi có ít nhất một token có subtoken; token chỉ dấu câu gộp vào câu trước.
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
            continue  # chưa có câu trước: tiếp tục gom vào câu đang mở
        start = i + 1
        has_word = False
    if start < len(words):
        if has_word or not spans:
            spans.append((start, len(words)))
        else:
            spans[-1] = (spans[-1][0], len(words))
    return [(a, b, " ".join(words[a:b])) for a, b in spans]


def is_filler(token: str) -> bool:
    """True nếu make_raw_key(token) thuộc FILLER_WORDS (chỉ áp phía hyp)."""
    return make_raw_key(token) in FILLER_WORDS
