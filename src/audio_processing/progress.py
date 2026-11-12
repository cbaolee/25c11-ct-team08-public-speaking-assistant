from collections.abc import Iterable
from typing import TypedDict


class ProgressResult(TypedDict):
    delta: float | None
    n: int
    enough: bool


def compute_progress(overalls: Iterable[float | None]) -> ProgressResult:
    scores = [score for score in overalls if score is not None]
    n = len(scores)
    if n < 6:
        return {"delta": None, "n": n, "enough": False}

    previous = scores[-6:-3]
    latest = scores[-3:]
    return {
        "delta": sum(latest) / 3 - sum(previous) / 3,
        "n": n,
        "enough": True,
    }
