from collections.abc import Iterable


def compute_progress(overalls: Iterable[float | None]) -> float | None:
    scores = [score for score in overalls if score is not None]
    if len(scores) < 6:
        return None

    previous = scores[-6:-3]
    latest = scores[-3:]
    return sum(latest) / 3 - sum(previous) / 3
