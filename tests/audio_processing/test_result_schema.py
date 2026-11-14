"""Test hợp đồng EvaluationResultV2 (ADR-004). Không gọi mạng."""

import pytest

# Import trong thân test: nếu module chưa có, test đỏ (không đỏ lúc collect).


def _alignment_kwargs(**over):
    base = dict(
        status="equal",
        ref_index=0,
        hyp_index=0,
        ref_word="Hello",
        hyp_word="hello",
        start_s=0.0,
        end_s=0.4,
        sentence_index=0,
    )
    base.update(over)
    return base


def _result_kwargs(**over):
    base = dict(
        schema_version="2.1",
        status="ok",
        reason=None,
        overall=88.0,
        label="Good",
        components={"accuracy": 90.0, "fluency": 85.0, "pronunciation": 80.0, "semantic": 100.0},
        subscores={},
        accuracy_detail={},
        fluency_detail={},
        pitch_detail={},
        audio={"duration_s": 10.0, "voiced_ratio": 0.8},
        baseline=None,
        alignment=[],
        pauses=[],
        fillers=[],
        sentences=[],
        stt={"provider": "deepgram", "model": "nova-2"},
        flags=[],
        warnings=[],
        display_only={},
    )
    base.update(over)
    return base


def test_alignment_invalid_status():
    from pydantic import ValidationError

    from src.audio_processing.result_schema import AlignmentItem

    with pytest.raises(ValidationError):
        AlignmentItem(**_alignment_kwargs(status="wrong"))


def test_alignment_ins_none_ref():
    from src.audio_processing.result_schema import AlignmentItem

    item = AlignmentItem(
        **_alignment_kwargs(status="ins", ref_index=None, ref_word=None, hyp_index=3)
    )
    assert item.ref_index is None and item.ref_word is None
    assert item.homophone is False  # default theo ADR-004


def test_alignment_del_none_times():
    from src.audio_processing.result_schema import AlignmentItem

    item = AlignmentItem(
        **_alignment_kwargs(
            status="del", hyp_index=None, hyp_word=None, start_s=None, end_s=None
        )
    )
    assert item.start_s is None and item.end_s is None


def test_pause_kind_rejects_rhetorical():
    from pydantic import ValidationError

    from src.audio_processing.result_schema import PauseItem

    with pytest.raises(ValidationError):
        PauseItem(start_s=1.0, end_s=2.0, kind="rhetorical", after_ref_index=2)
    ok = PauseItem(start_s=1.0, end_s=2.0, kind="punctuation", after_ref_index=None)
    assert ok.kind == "punctuation"


def test_filler_source_literal():
    from pydantic import ValidationError

    from src.audio_processing.result_schema import FillerItem

    with pytest.raises(ValidationError):
        FillerItem(start_s=0.0, end_s=0.2, source="whisper", text="um", after_ref_index=0)
    ok = FillerItem(start_s=0.0, end_s=0.2, source="vad", text=None, after_ref_index=None)
    assert ok.text is None


def test_series_accepts_none():
    from src.audio_processing.result_schema import Series

    s = Series(start_s=0.0, step_s=0.1, values=[1.0, None, 2.5])
    assert s.values == [1.0, None, 2.5]


def test_result_invalid_status():
    from pydantic import ValidationError

    from src.audio_processing.result_schema import EvaluationResultV2

    with pytest.raises(ValidationError):
        EvaluationResultV2(**_result_kwargs(status="done"))


def test_result_schema_version_literal():
    from pydantic import ValidationError

    from src.audio_processing.result_schema import EvaluationResultV2

    with pytest.raises(ValidationError):
        EvaluationResultV2(**_result_kwargs(schema_version="1.0"))


def test_result_label_literal():
    from pydantic import ValidationError

    from src.audio_processing.result_schema import EvaluationResultV2

    with pytest.raises(ValidationError):
        EvaluationResultV2(**_result_kwargs(label="Tốt"))  # nhãn tiếng Việt bị loại
    assert EvaluationResultV2(**_result_kwargs(label=None, overall=None)).label is None


def test_result_insufficient_audio_nulls():
    from src.audio_processing.result_schema import EvaluationResultV2

    r = EvaluationResultV2(
        **_result_kwargs(
            status="insufficient_audio",
            reason="low_voiced_ratio",
            overall=None,
            label=None,
            stt=None,
            baseline=None,
        )
    )
    assert r.overall is None and r.label is None and r.stt is None
    assert r.reason == "low_voiced_ratio"


def test_result_missing_reason_rejected():
    from pydantic import ValidationError

    from src.audio_processing.result_schema import EvaluationResultV2

    kwargs = _result_kwargs()
    del kwargs["reason"]  # X | None không default => bắt buộc truyền
    with pytest.raises(ValidationError):
        EvaluationResultV2(**kwargs)


def test_roundtrip_json():
    from src.audio_processing.result_schema import (
        AlignmentItem,
        EvaluationResultV2,
        FillerItem,
        PauseItem,
        SentenceItem,
        Series,
    )

    contour = Series(start_s=0.0, step_s=0.1, values=[0.5, None, -1.25]).model_dump()
    original = EvaluationResultV2(
        **_result_kwargs(
            pitch_detail={"range_semitones": 5.0, "f0_ref_hz": 120.0, "contour_st": contour},
            alignment=[AlignmentItem(**_alignment_kwargs())],
            pauses=[PauseItem(start_s=1.0, end_s=1.8, kind="hesitation", after_ref_index=0)],
            fillers=[
                FillerItem(start_s=2.0, end_s=2.2, source="stt", text="um", after_ref_index=0)
            ],
            sentences=[
                SentenceItem(
                    index=0,
                    ref_text="Hello.",
                    ref_start=0,
                    ref_end=1,
                    hyp_text="hello",
                    cosine=0.99,
                    passed=True,
                )
            ],
        )
    )
    restored = EvaluationResultV2.model_validate_json(original.model_dump_json())
    assert restored == original


def test_baseline_response_ok_has_profile():
    from src.audio_processing.result_schema import BaselineResponse

    r = BaselineResponse(
        schema_version="2.0",
        status="ok",
        reason=None,
        profile={"median_pause_s": 0.5, "median_f0_hz": 120.0, "mean_loudness_db": 60.0},
        flags=[],
    )
    assert r.profile["median_f0_hz"] == 120.0


def test_baseline_response_insufficient_audio_profile_none():
    from pydantic import ValidationError

    from src.audio_processing.result_schema import BaselineResponse

    r = BaselineResponse(
        schema_version="2.0",
        status="insufficient_audio",
        reason="empty_transcript",
        profile=None,
        flags=[],
    )
    assert r.profile is None
    with pytest.raises(ValidationError):
        BaselineResponse(
            schema_version="2.0",
            status="insufficient_audio",
            reason="other",
            profile=None,
            flags=[],
        )
