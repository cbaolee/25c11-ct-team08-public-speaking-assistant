"""Test ráp evaluate_session -> EvaluationResultV2 (ADR-004, bước 10c Pha 3).

Không đọc audio thật, không gọi mạng, không tải model: probe / decode_to_master /
detect_speech / transcribe / scoring._extract_f0 bị monkeypatch, encoder là hàm giả.
Mọi số liệu là số tính tay (ghi ở từng test), không phải số đo.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import src.app.main as main
from src.audio_processing import pipeline, scoring
from src.audio_processing.contracts import (
    BaselineProfile,
    InsufficientAudio,
    MasterAudio,
    SpeechSegment,
    SttResult,
    VadParams,
    WordTimestamp,
)
from src.audio_processing.result_schema import EvaluationResultV2

SCRIPT = "Good morning my friends."
# F0 giả: cặp (time_s, Hz) trải trong duration 2.2 s. f0_ref = median Hz = 100
# -> ST = [0, 0, 0, 12]; P90 (numpy linear) = 8.4, P10 = 0 -> R_st = 8.4 >= 6 -> P_pitch = 100.
# Thời gian chọn giữa ô 0.1 s: ô 0, 5, 10, 15 (không nằm sát biên ô).
F0 = [(0.05, 100.0), (0.55, 100.0), (1.05, 100.0), (1.55, 200.0)]
# Series độ to giả cố định (22 ô = ceil(2.2 / 0.1)), có cả None.
LOUDNESS = {"start_s": 0.0, "step_s": 0.1,
            "values": [None] + [60.0 + i * 0.5 for i in range(20)] + [None]}


def fake_encode(texts):
    # Mọi câu cùng một vector -> cosine = 1.0 -> câu nào có hyp cũng passed.
    return np.array([[1.0, 0.0] for _ in texts])


def w(word, start, end):
    return WordTimestamp(word=word, start_s=start, end_s=end)


GOOD_WORDS = [w("Good", 0.0, 0.4), w("morning", 0.5, 0.9), w("my", 1.0, 1.4),
              w("friends.", 1.5, 2.0)]
FULL_SEGS = (SpeechSegment(0.0, 2.0),)
PAUSE_SEGS = (SpeechSegment(0.0, 0.95), SpeechSegment(1.75, 3.0))
PAUSE_WORDS = [w("Good", 0.0, 0.4), w("morning", 0.5, 0.9), w("my", 1.8, 2.2),
               w("friends.", 2.3, 2.9)]


@pytest.fixture
def run(monkeypatch, tmp_path: Path):
    """Dựng môi trường giả rồi gọi evaluate_session. Trả hàm run(...) -> EvaluationResultV2."""

    def _run(
        *,
        words=GOOD_WORDS,
        segments=FULL_SEGS,
        duration=2.2,
        f0=F0,
        baseline=None,
        script=SCRIPT,
        stt_flags=(),
        stt_exc=None,
        loudness=LOUDNESS,
    ):
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"x")
        master = MasterAudio(path=audio, duration_s=duration, warnings=[])
        monkeypatch.setattr(pipeline, "probe", lambda *a, **k: None)
        monkeypatch.setattr(pipeline, "decode_to_master", lambda *a, **k: master)
        monkeypatch.setattr(pipeline, "detect_speech", lambda *a, **k: list(segments))

        def fake_transcribe(m, *, settings):
            if stt_exc is not None:
                raise stt_exc
            return SttResult(
                transcript=" ".join(x.word for x in words),
                words=list(words),
                provider="deepgram",
                model="nova-2",
                flags=list(stt_flags),
            )

        monkeypatch.setattr(pipeline, "transcribe", fake_transcribe)
        monkeypatch.setattr(scoring, "_extract_f0", lambda m: list(f0))
        monkeypatch.setattr(pipeline, "loudness_series", lambda m, *a, **k: loudness)
        return pipeline.evaluate_session(
            audio, script, baseline, vad_params=VadParams(), encode=fake_encode
        )

    return _run


ALL_KEYS = set(EvaluationResultV2.model_fields)


def test_ok_full_hand_calculation(run):
    r = run()
    assert r.status == "ok" and r.reason is None
    # round-trip JSON
    assert EvaluationResultV2.model_validate_json(r.model_dump_json()) == r
    assert set(r.model_dump()) == ALL_KEYS
    assert r.schema_version == "2.1"
    # A = 100 (4/4 equal), P_clarity = 100 (không near-miss)
    assert r.components["accuracy"] == 100.0
    assert r.subscores["p_clarity"] == 100.0
    # span = 2.0 - 0.0 = 2 s, 4 từ -> WPM 120 -> f_wpm = 100 - 2.5 * 10 = 75
    assert r.fluency_detail["wpm"] == pytest.approx(120.0)
    assert r.subscores["f_wpm"] == pytest.approx(75.0)
    # không pause, không filler -> 100, 100; F = (75 + 100 + 100) / 3
    assert r.subscores["f_pause"] == 100.0 and r.subscores["f_filler"] == 100.0
    assert r.components["fluency"] == pytest.approx(275.0 / 3.0)
    # pitch: R_st = 8.4 -> 100; P = 0.5 * 100 + 0.5 * 100
    assert r.pitch_detail["range_semitones"] == pytest.approx(8.4)
    assert r.pitch_detail["f0_ref_hz"] == pytest.approx(100.0)
    assert r.pitch_detail["f0_ref_source"] == "session"
    # contour_st: 22 ô, khung ở ô 0, 5, 10 (ST 0) và ô 15 (ST 12 = 12*log2(200/100)); còn lại None
    cs = r.pitch_detail["contour_st"]
    assert cs["start_s"] == 0.0 and cs["step_s"] == 0.1 and len(cs["values"]) == 22
    assert [i for i, v in enumerate(cs["values"]) if v is not None] == [0, 5, 10, 15]
    assert cs["values"][0] == pytest.approx(0.0) and cs["values"][15] == pytest.approx(12.0)
    assert r.subscores["p_pitch"] == 100.0 and r.components["pronunciation"] == 100.0
    # S: một câu, cosine 1.0 -> 100
    assert r.components["semantic"] == 100.0
    assert len(r.sentences) == 1 and r.sentences[0].passed is True
    # Overall = 0.4*100 + 0.3*(275/3) + 0.2*100 + 0.1*100 = 97.5
    assert r.overall == pytest.approx(97.5)
    assert r.label == "Excellent"
    assert r.accuracy_detail == {"n_ref": 4, "n_sub": 0, "n_del": 0, "n_ins": 0,
                                 "n_near_miss": 0, "n_homophone": 0, "n_oov": 0}
    assert [it.status for it in r.alignment] == ["equal"] * 4
    assert r.pauses == [] and r.fillers == []
    assert r.audio == {"duration_s": 2.2, "voiced_ratio": pytest.approx(2.0 / 2.2)}
    assert r.stt == {"provider": "deepgram", "model": "nova-2"}
    assert r.flags == ["no_baseline"]
    assert r.baseline is None
    assert r.warnings == []
    assert r.display_only == {"loudness_db": LOUDNESS, "loudness_ref_db": None}


def test_baseline_merged_and_used(run):
    base = BaselineProfile(median_pause_s=0.4, hesitation_threshold_s=0.9, median_f0_hz=100.0,
                           mean_loudness_db=62.5, flags=["baseline_pause_unreliable"])
    # khoảng lặng 0.95 -> 1.75 (dài 0.8 s) sau "morning" (không dấu câu): PAUSE_SEGS/PAUSE_WORDS
    r = run(baseline=base, segments=PAUSE_SEGS, words=PAUSE_WORDS, duration=3.0)
    assert r.flags == ["baseline_pause_unreliable"]  # không có no_baseline
    assert r.pitch_detail["f0_ref_source"] == "baseline"
    assert r.display_only["loudness_ref_db"] == 62.5
    assert r.fluency_detail["pause_threshold_s"] == 0.9
    assert r.baseline == {"used": True, "median_pause_s": 0.4, "hesitation_threshold_s": 0.9}
    # 0.8 s < ngưỡng 0.9 -> natural, không phải hesitation
    assert [p.kind for p in r.pauses] == ["natural"]
    assert r.pauses[0].after_ref_index == 1
    assert r.fluency_detail["hesitation_count"] == 0


def test_default_threshold_without_baseline_makes_hesitation(run):
    r = run(segments=PAUSE_SEGS, words=PAUSE_WORDS, duration=3.0)
    assert r.fluency_detail["pause_threshold_s"] == 0.7
    assert [p.kind for p in r.pauses] == ["hesitation"]
    assert r.fluency_detail["hesitation_count"] == 1
    assert r.fluency_detail["forgot_word_count"] == 0
    # span = 2.9 s; H = 1 / (2.9 / 60) = 20.69 -> f_pause = clamp(100 - 20 * 19.69) = 0
    assert r.fluency_detail["hesitations_per_min"] == pytest.approx(60.0 / 2.9)
    assert r.subscores["f_pause"] == 0.0


def test_insufficient_low_voiced_ratio(run):
    # stt_exc=AssertionError: nếu pipeline lỡ gọi STT thì test đỏ (STT bị loại trước đó).
    r = run(segments=(SpeechSegment(0.0, 1.0),), duration=10.0,
            stt_exc=AssertionError("STT không được gọi khi voiced thấp"))  # 10% voiced
    assert r.status == "insufficient_audio" and r.reason == "low_voiced_ratio"
    assert r.stt is None
    assert r.overall is None and r.label is None
    assert all(v is None for v in r.components.values()) and len(r.components) == 4
    assert all(v is None for v in r.subscores.values()) and len(r.subscores) == 5
    assert set(r.accuracy_detail) == {"n_ref", "n_sub", "n_del", "n_ins", "n_near_miss",
                                      "n_homophone", "n_oov"}
    assert all(v is None for v in r.accuracy_detail.values())
    assert all(v is None for v in r.fluency_detail.values())
    assert r.alignment == [] and r.pauses == [] and r.fillers == [] and r.sentences == []
    assert r.audio == {"duration_s": 10.0, "voiced_ratio": pytest.approx(0.1)}
    assert "0.0" not in json.dumps(r.model_dump(mode="json")["components"])
    assert EvaluationResultV2.model_validate_json(r.model_dump_json()) == r


def test_insufficient_no_segments_voiced_ratio_zero(run):
    r = run(segments=(), duration=5.0)
    assert r.reason == "low_voiced_ratio" and r.audio["voiced_ratio"] == 0.0


@pytest.mark.parametrize("words", [[], [w("um", 0.0, 0.3), w("Uh", 0.5, 0.8)]])
def test_empty_transcript(run, words):
    r = run(words=words)
    assert r.status == "insufficient_audio" and r.reason == "empty_transcript"
    assert r.stt == {"provider": "deepgram", "model": "nova-2"}
    assert r.overall is None and r.label is None
    assert all(v is None for v in r.components.values())


def test_empty_transcript_from_stt_exception(run):
    r = run(stt_exc=InsufficientAudio("STT returned empty transcript"))
    assert r.status == "insufficient_audio" and r.reason == "empty_transcript"
    assert r.stt is None  # TỰ CHỌN: provider/model không có khi transcribe ném lỗi


def test_under_two_words_gives_null_fluency_and_overall(run):
    r = run(script="Hello world.", words=[w("hello", 0.0, 0.5)],
            segments=(SpeechSegment(0.0, 0.6),), duration=1.0)
    assert r.status == "ok"
    assert r.subscores["f_wpm"] is None and r.subscores["f_pause"] is None
    assert r.components["fluency"] is None
    assert r.overall is None and r.label is None
    assert r.fluency_detail["wpm"] is None and r.fluency_detail["hesitations_per_min"] is None
    # các thành phần khác vẫn chấm: "world" bị del -> A = 50
    assert r.components["accuracy"] == 50.0


def test_no_f0(run):
    r = run(f0=[])
    assert r.subscores["p_pitch"] is None and r.components["pronunciation"] is None
    assert "no_f0" in r.flags
    assert r.pitch_detail["f0_ref_hz"] is None and r.pitch_detail["range_semitones"] is None
    assert r.overall is None and r.label is None
    assert r.components["accuracy"] == 100.0  # thành phần khác không bị ảnh hưởng


def test_stt_filler_listed_but_not_in_alignment(run):
    words = [w("Good", 0.0, 0.4), w("um", 0.45, 0.55), w("morning", 0.6, 1.0),
             w("my", 1.1, 1.5), w("friends.", 1.6, 2.0)]
    r = run(words=words)
    assert len(r.fillers) == 1
    f = r.fillers[0]
    assert (f.source, f.text, f.start_s, f.end_s) == ("stt", "um", 0.45, 0.55)
    assert f.after_ref_index == 0  # từ nghe được ngay trước: "Good"
    assert all(it.hyp_word != "um" for it in r.alignment)
    assert r.accuracy_detail["n_ins"] == 0
    # 4 từ thật, 1 filler -> R = 25% -> F_filler = clamp(100 * (10 - 25) / 8) = 0
    assert r.fluency_detail["filler_count"] == 1
    assert r.fluency_detail["filler_pct"] == pytest.approx(25.0)
    assert r.subscores["f_filler"] == 0.0
    assert r.fluency_detail["wpm"] == pytest.approx(120.0)  # filler không tính vào WPM (D4)


def test_vad_only_filler(run):
    r = run(segments=(SpeechSegment(0.0, 2.0), SpeechSegment(2.6, 2.9)), duration=3.0)
    assert [(f.source, f.text, f.start_s, f.after_ref_index) for f in r.fillers] == [
        ("vad", None, 2.6, 3)
    ]
    # pause 2.0 -> 2.6 nằm sau "friends." (có dấu câu) -> punctuation
    assert [p.kind for p in r.pauses] == ["punctuation"]


def test_stt_flags_are_merged_in_order_without_duplicates(run):
    r = run(stt_flags=["filler_from_vad_only"])
    assert r.flags == ["filler_from_vad_only", "no_baseline"]


# ---- API ----

def _minimal_result() -> EvaluationResultV2:
    return EvaluationResultV2(
        schema_version="2.1", status="insufficient_audio", reason="low_voiced_ratio",
        overall=None, label=None, components={}, subscores={}, accuracy_detail={},
        fluency_detail={}, pitch_detail={}, audio={"duration_s": 1.0, "voiced_ratio": 0.0},
        baseline=None, alignment=[], pauses=[], fillers=[], sentences=[], stt=None,
        flags=["no_baseline"], warnings=[],
        display_only={"loudness_db": None, "loudness_ref_db": None},
    )


def _post_eval(monkeypatch, baseline_profile: str | None, captured: dict):
    def fake(audio_path, script, baseline, *, vad_params):
        captured["baseline"] = baseline
        return _minimal_result()

    monkeypatch.setattr(main, "evaluate_session", fake)
    data = {"script": "Hello."}
    if baseline_profile is not None:
        data["baseline_profile"] = baseline_profile
    return TestClient(main.app).post(
        "/api/evaluate", files={"audio": ("a.wav", b"x", "audio/wav")}, data=data
    )


def test_api_evaluate_returns_v2_json(monkeypatch):
    cap: dict = {}
    r = _post_eval(monkeypatch, None, cap)
    assert r.status_code == 200
    assert EvaluationResultV2.model_validate(r.json()).schema_version == "2.1"
    assert cap["baseline"] is None


def test_api_evaluate_baseline_without_loudness_ok(monkeypatch):
    cap: dict = {}
    body = {"median_pause_s": 0.5, "hesitation_threshold_s": 1.0, "median_f0_hz": 120.0,
            "flags": []}  # thiếu mean_loudness_db
    r = _post_eval(monkeypatch, json.dumps(body), cap)
    assert r.status_code == 200
    assert cap["baseline"].mean_loudness_db is None
    assert cap["baseline"].hesitation_threshold_s == 1.0


@pytest.mark.parametrize("bad", [
    '{"median_pause_s": 0.5, "bogus": 1}',   # thiếu trường + thừa trường
    '{"median_pause_s": 0.5, "hesitation_threshold_s": "abc", "median_f0_hz": 1.0, "flags": []}',
    '{"median_pause_s": 0.5, "hesitation_threshold_s": 1.0, "median_f0_hz": 1.0, "flags": "x"}',
    "[1, 2]",
    "not json",
])
def test_api_evaluate_bad_baseline_is_422(monkeypatch, bad):
    r = _post_eval(monkeypatch, bad, {})
    assert r.status_code == 422
    assert r.json()["error_code"] == "invalid_baseline"


# ---- Bổ sung (review bước 10): số dưới đây là số tự tính tay, không phải số đo ----

def test_align_called_once(run, monkeypatch):
    calls = []
    real_align = pipeline.align

    def counting(*a, **k):
        calls.append(1)
        return real_align(*a, **k)

    monkeypatch.setattr(pipeline, "align", counting)
    run()
    assert len(calls) == 1


def test_non_trivial_encoder_second_sentence_fails(run, monkeypatch):
    # Hai câu: "Good morning." / "See you." Nói đủ cả hai, 4 từ trong 2.0 s (WPM 120, f_wpm 75).
    words = [w("Good", 0.0, 0.4), w("morning.", 0.5, 0.9), w("See", 1.0, 1.4), w("you.", 1.5, 2.0)]
    calls = []

    def encode(texts):
        # Lần gọi 1 = các câu ref, lần 2 = các câu hyp (xem score_sentences).
        calls.append(list(texts))
        if len(calls) == 1:
            return np.array([[1.0, 0.0]] * len(texts))
        # hyp câu 1: cùng hướng ref (cosine 1.0). hyp câu 2: [0.6, 0.8] -> cosine 0.6 < 0.82.
        return np.array([[1.0, 0.0], [0.6, 0.8]])

    r = _run_with_encoder(run, monkeypatch, words=words, script="Good morning. See you.",
                          encode=encode)
    assert [s.passed for s in r.sentences] == [True, False]
    assert r.sentences[1].cosine == pytest.approx(0.6)
    # hyp_text lấy từ alignment: các hyp_word của câu (đã chuẩn hoá, lấy từ STT)
    assert r.sentences[0].hyp_text == calls[1][0]
    assert r.sentences[1].hyp_text == calls[1][1]
    assert r.sentences[1].hyp_text.lower().replace(".", "") == "see you"
    # S = 50. Overall = 0.4*100 + 0.3*(275/3) + 0.2*100 + 0.1*50 = 40 + 27.5 + 20 + 5 = 92.5
    assert r.components["semantic"] == 50.0
    assert r.overall == pytest.approx(92.5)


def _run_with_encoder(run, monkeypatch, *, words, script, encode):
    # fixture `run` cố định encode=fake_encode; bọc evaluate_session để thay encoder cho test này.
    orig = pipeline.evaluate_session

    def patched(audio, scr, baseline, *, vad_params, encode=None):  # noqa: ARG001
        return orig(audio, scr, baseline, vad_params=vad_params, encode=enc)

    enc = encode
    monkeypatch.setattr(pipeline, "evaluate_session", patched)
    return run(words=words, script=script)


def test_near_miss_at_pipeline_level(run):
    # "friends" vs "friend": CMU F R EH N D Z vs F R EH N D -> Lev = 1, max dài 6 -> sim = 5/6
    # = 0.833 thuộc [0.65, 0.90] -> near_miss. A không trừ near-miss -> 100.
    # P_clarity = clamp(100 * (1 - 5 * 1/4)) = clamp(-25) = 0. P = 0.5*0 + 0.5*100 = 50.
    words = [w("My", 0.0, 0.4), w("friend", 0.5, 0.9), w("are", 1.0, 1.4), w("here.", 1.5, 2.0)]
    r = run(words=words, script="My friends are here.")
    assert r.accuracy_detail["n_near_miss"] == 1
    assert r.accuracy_detail["n_ref"] == 4
    assert r.components["accuracy"] == 100.0
    assert r.subscores["p_clarity"] == 0.0
    assert r.components["pronunciation"] == pytest.approx(50.0)
    # Overall = 0.4*100 + 0.3*(275/3) + 0.2*50 + 0.1*100 = 40 + 27.5 + 10 + 10 = 87.5
    assert r.overall == pytest.approx(87.5)


# ---- Bước E1: contour_st, loudness_db, warnings (số tự tính tay, không phải số đo) ----

def test_loudness_series_passed_through(run):
    custom = {"start_s": 0.0, "step_s": 0.1, "values": [70.0] * 22}
    assert run(loudness=custom).display_only["loudness_db"] == custom


def test_loudness_series_none_is_kept_none(run):
    r = run(loudness=None)
    assert r.status == "ok" and r.display_only["loudness_db"] is None


def test_contour_none_and_no_f0_flag_when_no_f0(run):
    r = run(f0=[])
    assert r.pitch_detail["contour_st"] is None
    assert "no_f0" in r.flags


def test_warnings_empty_in_default_fixture(run):
    # WPM 120 (ngưỡng cảnh báo 110/175), filler 0 %, R_st 8.4 >= 4 -> không cảnh báo
    assert run().warnings == []


def test_warning_wpm_slow(run):
    # 4 từ, span 0.0 -> 2.2 = 2.2 s -> WPM = 4 / (2.2/60) = 109.09 < 110
    words = [w("Good", 0.0, 0.4), w("morning", 0.6, 1.0),
             w("my", 1.2, 1.6), w("friends.", 1.8, 2.2)]
    r = run(words=words)
    assert r.fluency_detail["wpm"] == pytest.approx(109.0909, abs=1e-3)
    assert r.warnings == ["wpm_slow"]


def test_warning_wpm_fast(run):
    # span 1.0 s -> WPM = 4 / (1/60) = 240 > 175 (voiced 1.0/2.2 = 45 % >= 30 %)
    words = [w("Good", 0.0, 0.2), w("morning", 0.25, 0.5),
             w("my", 0.55, 0.75), w("friends.", 0.8, 1.0)]
    r = run(words=words, segments=(SpeechSegment(0.0, 1.0),))
    assert r.fluency_detail["wpm"] == pytest.approx(240.0)
    assert r.warnings == ["wpm_fast"]


def test_warning_filler_high(run):
    # Cùng dữ liệu test_stt_filler_listed...: R = 1/4 = 25 % >= 4; WPM 120; R_st 8.4
    words = [w("Good", 0.0, 0.4), w("um", 0.45, 0.55), w("morning", 0.6, 1.0),
             w("my", 1.1, 1.5), w("friends.", 1.6, 2.0)]
    assert run(words=words).warnings == ["filler_high"]


def test_warning_monotone(run):
    # F0 phẳng: mọi ST = 0 -> R_st = 0 < 4 -> monotone. WPM 120, không filler.
    flat = [(0.05, 100.0), (0.55, 100.0), (1.05, 100.0), (1.55, 100.0)]
    r = run(f0=flat)
    assert r.pitch_detail["range_semitones"] == pytest.approx(0.0)
    assert r.warnings == ["monotone"]


def test_warnings_order_slow_filler_monotone(run):
    # span 2.2 s, 4 từ thật = 109.09 WPM (slow) + 1 filler (25 %) + F0 phẳng
    words = [w("Good", 0.0, 0.4), w("um", 0.45, 0.55), w("morning", 0.6, 1.0),
             w("my", 1.2, 1.6), w("friends.", 1.8, 2.2)]
    flat = [(0.05, 100.0), (0.55, 100.0), (1.05, 100.0), (1.55, 100.0)]
    r = run(words=words, f0=flat)
    assert r.warnings == ["wpm_slow", "filler_high", "monotone"]


def test_insufficient_has_no_warnings_loudness_or_contour(run):
    r = run(segments=(SpeechSegment(0.0, 1.0),), duration=10.0)
    assert r.status == "insufficient_audio"
    assert r.warnings == []
    assert r.display_only["loudness_db"] is None
    assert r.pitch_detail.get("contour_st") is None


def test_empty_transcript_has_no_warnings_or_loudness(run):
    r = run(words=[])
    assert r.status == "insufficient_audio"
    assert r.warnings == [] and r.display_only["loudness_db"] is None


@pytest.mark.parametrize("kwargs", [
    {},
    {"f0": []},
    {"loudness": None},
    {"segments": (SpeechSegment(0.0, 1.0),), "duration": 10.0},
])
def test_result_json_is_strict(run, kwargs):
    r = run(**kwargs)
    json.dumps(r.model_dump(mode="json"), allow_nan=False)


def test_empty_script_gives_null_scores(run):
    r = run(script="")
    assert r.components["accuracy"] is None
    assert r.subscores["p_clarity"] is None
    assert r.components["pronunciation"] is None
    assert r.components["semantic"] is None
    assert r.overall is None and r.label is None
    assert "empty_script" in r.flags
