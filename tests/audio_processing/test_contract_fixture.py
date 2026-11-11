"""Fixture hợp đồng EvaluationResultV2 (ADR-004, C4).

DỮ LIỆU TỔNG HỢP, KHÔNG PHẢI KẾT QUẢ ĐO. STT, VAD, F0 và độ to đều là giả (fixture
`run` của test_pipeline_evaluate.py); không có audio thật, không có số đo.

Test so sánh JSON thật do evaluate_session sinh ra với file trong tests/fixtures/.
Đặt UPDATE_FIXTURES=1 để ghi lại file. Các file này cũng là đầu vào của test JS
(mapResult) nên đổi hợp đồng thì phải sinh lại và xem diff.
"""

import json
import math
import os
from pathlib import Path

import pytest

# Tái dùng fixture `run` (không đổi hành vi test cũ). pytest nạp test_pipeline_evaluate
# ở chế độ prepend nên import theo tên module trần.
from test_pipeline_evaluate import (  # noqa: F401
    LOUDNESS,
    SpeechSegment,
    run,
    w,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"

# ---- ca ok_mixed (số tự đặt, không phải số đo) ----
MIXED_SCRIPT = "Good morning my friends are here today."
MIXED_WORDS = [
    w("Good", 0.0, 0.4), w("morning", 0.5, 0.9),
    w("um", 0.95, 1.1),                      # filler STT
    w("friend", 1.2, 2.0),                   # "my" del; friends -> friend: near_miss
    w("are", 2.8, 3.1),                      # sau khoảng lặng 0.8 s: hesitation
    w("cat", 3.2, 3.6),                      # "here" -> "cat": sub
    w("today", 5.4, 5.8),                    # sau khoảng lặng 1.7 s giữa câu: forgot_word
    w("really", 5.9, 6.3),                   # từ thừa cuối: ins
]
MIXED_SEGS = (SpeechSegment(0.0, 2.0), SpeechSegment(2.8, 3.7), SpeechSegment(5.4, 6.4))
MIXED_F0 = [(0.05, 100.0), (0.55, 110.0), (1.25, 130.0), (2.85, 90.0), (3.25, 200.0),
            (5.45, 120.0)]
MIXED_LOUDNESS = {"start_s": 0.0, "step_s": 0.1,
                  "values": [None if i % 5 == 4 else 55.0 + 0.25 * i for i in range(68)]}

CASES = {
    "evaluation_ok.json": {},
    "evaluation_ok_mixed.json": {
        "script": MIXED_SCRIPT, "words": MIXED_WORDS, "segments": MIXED_SEGS,
        "duration": 6.8, "f0": MIXED_F0, "loudness": MIXED_LOUDNESS,
    },
    "evaluation_insufficient.json": {
        "segments": (SpeechSegment(0.0, 1.0),), "duration": 10.0,
    },
}


def compare(actual, expected, path="$"):
    """So sánh đệ quy; trả danh sách mô tả chỗ lệch (rỗng = khớp)."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            return [f"{path}: khoá lệch"]
        diffs = []
        for k in expected:
            diffs += compare(actual[k], expected[k], f"{path}.{k}")
        return diffs
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [f"{path}: độ dài lệch"]
        diffs = []
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            diffs += compare(a, e, f"{path}[{i}]")
        return diffs
    if isinstance(expected, float) or isinstance(actual, float):
        ok = (isinstance(actual, (int, float)) and isinstance(expected, (int, float))
              and not isinstance(actual, bool) and not isinstance(expected, bool)
              and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12))
        return [] if ok else [f"{path}: {actual!r} != {expected!r}"]
    return [] if (actual == expected and type(actual) is type(expected)) \
        else [f"{path}: {actual!r} != {expected!r}"]


@pytest.mark.parametrize("name", list(CASES))
def test_contract_fixture(run, name):  # noqa: F811
    result = run(**CASES[name])
    actual = json.loads(json.dumps(result.model_dump(mode="json"), allow_nan=False))
    path = FIXTURE_DIR / name
    if os.environ.get("UPDATE_FIXTURES") == "1":
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(actual, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert compare(actual, expected) == []


def test_mixed_fixture_covers_required_cases(run):  # noqa: F811
    r = run(**CASES["evaluation_ok_mixed.json"])
    assert r.status == "ok"
    statuses = {it.status for it in r.alignment}
    assert {"equal", "sub", "del", "ins", "near_miss"} <= statuses
    assert len(r.fillers) >= 1
    kinds = {p.kind for p in r.pauses}
    assert {"hesitation", "forgot_word"} <= kinds
    for series in (r.pitch_detail["contour_st"], r.display_only["loudness_db"]):
        assert any(v is None for v in series["values"])
        assert any(v is not None for v in series["values"])


def test_comparator_detects_drift():
    base = {"a": [1.0, {"b": None}], "c": "x", "d": True}
    assert compare(json.loads(json.dumps(base)), base) == []
    for mutate in (
        lambda d: d["a"].__setitem__(0, 1.0001),      # float lệch
        lambda d: d["a"][1].__setitem__("b", 0.0),    # None -> số
        lambda d: d.__setitem__("c", "y"),            # chuỗi lệch
        lambda d: d.__setitem__("e", 1),              # thừa khoá
        lambda d: d["a"].append(2),                   # độ dài lệch
        lambda d: d.__setitem__("d", 1),              # bool vs int
    ):
        copy = json.loads(json.dumps(base))
        mutate(copy)
        assert compare(copy, base) != []
    assert compare(1.0 + 1e-12, 1.0) == []  # trong dung sai
