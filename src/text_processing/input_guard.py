"""Guard against junk chat input such as "aaaaa", "asdfgh" or "?????" (contract E v2).

The web client implements the same rules; `tests/fixtures/gibberish_vectors.json` keeps both
sides in step. The numbers below are part of the rules, not settings to tune.
"""

import unicodedata

GIBBERISH_MESSAGE = (
    "Your message looks like random or repeated characters. "
    "Please enter a clear topic, details, or instructions."
)

KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
RUN_MIN = 5
RUN_WHOLE_MIN = 4
REPEAT_CHAR_MIN = 5
LOW_VARIETY_MIN_LETTERS = 6
LOW_VARIETY_MAX_DISTINCT = 2
NO_VOWEL_MIN = 6
NO_VOWEL_MIN_ALL_CAPS = 8
REPEAT_TOKEN_MIN = 4

ASCII_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyz")
VOWELS = frozenset("aeiouy")
EXEMPT = frozenset({"generate", "done", "tạo", "xong", "yes", "no", "ok", "okay", "sure"})
EXEMPT_END_PUNCTUATION = ".!?"
CONTROL_SPACES = frozenset("\t\n\v\f\r")
SPACE_CATEGORIES = frozenset({"Zs", "Zl", "Zp"})


def _keyboard_runs(min_len: int, max_len: int) -> frozenset[str]:
    """Neighbouring keys of one row, in both directions, `min_len` to `max_len` long."""
    return frozenset(
        line[start : start + length]
        for row in KEYBOARD_ROWS
        for line in (row, row[::-1])
        for length in range(min_len, min(max_len, len(line)) + 1)
        for start in range(len(line) - length + 1)
    )


_WHOLE_TOKEN_RUNS = _keyboard_runs(RUN_WHOLE_MIN, max(map(len, KEYBOARD_ROWS)))
_INNER_RUNS = _keyboard_runs(RUN_MIN, RUN_MIN)


def _is_space(char: str) -> bool:
    return char in CONTROL_SPACES or unicodedata.category(char) in SPACE_CATEGORIES


def _is_letter(char: str) -> bool:
    return unicodedata.category(char).startswith("L")


def _is_content(char: str) -> bool:
    return unicodedata.category(char).startswith(("L", "N"))


def _split_words(text: str) -> list[str]:
    """NFC words split on the contract's whitespace, which is not that of `str.split()`."""
    spaced = "".join(
        " " if _is_space(char) else char for char in unicodedata.normalize("NFC", text)
    )
    return [word for word in spaced.split(" ") if word]


def _core(word: str) -> str:
    """The word without the leading and trailing characters that are no letter or digit."""
    start, end = 0, len(word)
    while start < end and not _is_content(word[start]):
        start += 1
    while end > start and not _is_content(word[end - 1]):
        end -= 1
    return word[start:end]


def _cores(words: list[str]) -> list[str]:
    return [core for core in map(_core, words) if core]


def _has_letter(core: str) -> bool:
    return any(map(_is_letter, core))


def _has_repeated_letter(lowered: str) -> bool:
    """T1: one letter repeated in a row."""
    run, previous = 0, ""
    for char in lowered:
        if not _is_letter(char):
            run = 0
        elif char == previous:
            run += 1
        else:
            run = 1
        if run >= REPEAT_CHAR_MIN:
            return True
        previous = char
    return False


def _has_low_variety(letters: str) -> bool:
    """T2: a long word made of very few different letters."""
    return len(letters) >= LOW_VARIETY_MIN_LETTERS and len(set(letters)) <= LOW_VARIETY_MAX_DISTINCT


def _lacks_vowels(core: str, letters: str) -> bool:
    """T3: a long Latin word without a vowel; short all-caps ones pass as acronyms."""
    folded = "".join(
        char
        for char in unicodedata.normalize("NFD", letters)
        if unicodedata.category(char) != "Mn"
    )
    if not set(folded) <= ASCII_LETTERS or set(folded) & VOWELS:
        return False
    is_all_caps = not any(char.islower() for char in core if _is_letter(char))
    return len(folded) >= (NO_VOWEL_MIN_ALL_CAPS if is_all_caps else NO_VOWEL_MIN)


def _is_keyboard_run(lowered: str, letters: str) -> bool:
    """T4: the whole word, or a part of its letters, follows the keys of one row."""
    if letters == lowered and lowered in _WHOLE_TOKEN_RUNS:
        return True
    # Every longer run contains one of length RUN_MIN, so one window size keeps this linear.
    return any(
        letters[start : start + RUN_MIN] in _INNER_RUNS
        for start in range(len(letters) - RUN_MIN + 1)
    )


def _is_junk(core: str) -> bool:
    lowered = core.lower()
    letters = "".join(filter(_is_letter, lowered))
    return (
        _has_repeated_letter(lowered)
        or _has_low_variety(letters)
        or _lacks_vowels(core, letters)
        or _is_keyboard_run(lowered, letters)
    )


def content_words(text: str) -> list[str]:
    """The word cores of `text` that contain at least one letter, case kept."""
    return list(filter(_has_letter, _cores(_split_words(text))))


def content_word_count(text: str) -> int:
    """How many words of `text` contain at least one letter."""
    return len(content_words(text))


def is_gibberish(text: str, *, has_file: bool = False) -> bool:
    """Whether the whole message is junk; an attached file or empty text always passes."""
    if has_file:
        return False
    words = _split_words(text)
    normalized = " ".join(words)
    if not words or normalized.lower().rstrip(EXEMPT_END_PUNCTUATION) in EXEMPT:
        return False
    if not any(map(_is_content, normalized)):
        return True
    cores = _cores(words)
    if len(cores) >= REPEAT_TOKEN_MIN and len({core.lower() for core in cores}) == 1:
        return True
    lettered = [core for core in cores if _has_letter(core)]
    return bool(lettered) and all(map(_is_junk, lettered))
