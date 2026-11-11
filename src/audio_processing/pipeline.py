import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Import cấu hình thực tế của bạn
from src.app.config import (
    settings,
    max_audio_seconds,
    max_upload_bytes,
    allowed_formats,
    decode_timeout_s,
    duration_cap_margin_s,
    MIN_PAUSE_S
)

from src.audio_processing.contracts import (
    BaselineProfile, InsufficientAudio, MasterAudio, SpeechSegment
)
from src.audio_processing.probe import probe
from src.audio_processing.decode import decode_to_master
from src.audio_processing.vad import (
    detect_speech, find_pauses, check_audio_quality, classify_pauses, after_ref_index
)
from src.audio_processing.stt import transcribe
from src.audio_processing.alignment import align
from src.audio_processing.text_norm import is_filler
from src.audio_processing.baseline import (
    compute_baseline_pause_profile, compute_baseline_f0, mean_loudness_db, extract_loudness_db
)
from src.audio_processing.result_schema import (
    AlignmentItem, EvaluationResultV2, FillerItem, PauseItem, SentenceItem
)
from src.audio_processing.scoring import (
    Encoder, accuracy_scores, build_sentence_pairs, combine_pronunciation, compute_fluency,
    compute_overall, compute_wpm, filler_pct, find_fillers, get_label, hesitations_per_min,
    score_filler, score_hesitation, score_pitch, score_semantic, score_sentences, score_wpm,
    speech_span,
)

# Ngưỡng ngập ngừng khi chưa có baseline (scoring_framework §5.2, chốt 06/11 = 0.7 s).
DEFAULT_HESITATION_THRESHOLD_S = 0.7

_COMPONENT_KEYS = ("accuracy", "fluency", "pronunciation", "semantic")
_SUBSCORE_KEYS = ("f_wpm", "f_pause", "f_filler", "p_clarity", "p_pitch")
_ACCURACY_KEYS = ("n_ref", "n_sub", "n_del", "n_ins", "n_near_miss", "n_homophone", "n_oov")
_FLUENCY_KEYS = ("wpm", "hesitations_per_min", "hesitation_count", "forgot_word_count",
                 "pause_threshold_s", "filler_pct", "filler_count")
_PITCH_KEYS = ("range_semitones", "f0_ref_hz", "f0_ref_source", "contour_st")


def _voiced_ratio(segments: list[SpeechSegment], duration_s: float) -> float:
    if duration_s <= 0:
        return 0.0
    return sum(seg.end_s - seg.start_s for seg in segments) / duration_s


def _merge_flags(*groups: list[str]) -> list[str]:
    """Gộp cờ giữ thứ tự xuất hiện, bỏ trùng."""
    return list(dict.fromkeys(f for group in groups for f in group))


def _baseline_block(baseline: BaselineProfile | None) -> dict | None:
    if baseline is None:
        return None
    return {"used": True, "median_pause_s": baseline.median_pause_s,
            "hesitation_threshold_s": baseline.hesitation_threshold_s}


def _insufficient(
    reason: str,
    *,
    master: MasterAudio,
    voiced_ratio: float,
    baseline: BaselineProfile | None,
    stt: dict | None,
    flags: list[str],
) -> EvaluationResultV2:
    """Kết quả không chấm (ADR-004 D1): mọi điểm null, danh sách rỗng, KHÔNG điền 0."""
    return EvaluationResultV2(
        schema_version="2.0", status="insufficient_audio", reason=reason,  # type: ignore[arg-type]
        overall=None, label=None,
        components=dict.fromkeys(_COMPONENT_KEYS),
        subscores=dict.fromkeys(_SUBSCORE_KEYS),
        accuracy_detail=dict.fromkeys(_ACCURACY_KEYS),
        fluency_detail=dict.fromkeys(_FLUENCY_KEYS),
        pitch_detail=dict.fromkeys(_PITCH_KEYS),
        audio={"duration_s": master.duration_s, "voiced_ratio": voiced_ratio},
        baseline=_baseline_block(baseline),
        alignment=[], pauses=[], fillers=[], sentences=[],
        stt=stt,
        flags=_merge_flags(flags, baseline.flags if baseline else ["no_baseline"]),
        warnings=[],
        display_only={"loudness_db": None,
                      "loudness_ref_db": baseline.mean_loudness_db if baseline else None},
    )


def evaluate_session(
    audio_path: Path,
    script: str,
    baseline: BaselineProfile | None,
    *,
    vad_params: Any,
    encode: Encoder | None = None,
) -> EvaluationResultV2:
    """Ráp toàn bộ luồng chấm điểm thành EvaluationResultV2 (ADR-004)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workdir = Path(temp_dir)

        probe(
            audio_path,
            max_seconds=max_audio_seconds,
            max_bytes=max_upload_bytes,
            allowed_formats=frozenset(allowed_formats)
        )
        master = decode_to_master(
            audio_path,
            workdir=workdir,
            max_seconds=max_audio_seconds,
            cap_margin_s=duration_cap_margin_s,
            timeout_s=decode_timeout_s
        )

        # (a) VAD + kiểm tra tỉ lệ tiếng nói. Loại trước STT: không tốn request.
        segments = detect_speech(master, params=vad_params)
        voiced_ratio = _voiced_ratio(segments, master.duration_s)
        try:
            check_audio_quality(segments, master.duration_s)
        except InsufficientAudio:
            return _insufficient("low_voiced_ratio", master=master, voiced_ratio=voiced_ratio,
                                 baseline=baseline, stt=None, flags=[])

        # (b) STT. transcribe ném InsufficientAudio khi bản chép rỗng (khi đó không biết
        # provider/model nên stt = None, TỰ CHỌN).
        try:
            stt = transcribe(master, settings=settings)
        except InsufficientAudio:
            return _insufficient("empty_transcript", master=master, voiced_ratio=voiced_ratio,
                                 baseline=baseline, stt=None, flags=[])
        stt_block = {"provider": stt.provider, "model": stt.model}
        if not any(not is_filler(x.word) for x in stt.words):
            return _insufficient("empty_transcript", master=master, voiced_ratio=voiced_ratio,
                                 baseline=baseline, stt=stt_block, flags=stt.flags)

        # (c) MỘT lần align, dùng chung cho A, P_clarity, pause, filler và S.
        result = align(script, stt.words)
        acc = accuracy_scores(result)
        ref_tokens = script.split()

        # (d) Pause: ngưỡng cá nhân từ baseline, không có thì 0.7 s.
        threshold = (baseline.hesitation_threshold_s if baseline is not None
                     else DEFAULT_HESITATION_THRESHOLD_S)
        pauses = find_pauses(segments, min_pause_s=MIN_PAUSE_S)
        classified = classify_pauses(pauses, result.items, script, hesitation_threshold_s=threshold)

        # (e) Fluency: WPM và H cùng mẫu số speech_span; R dùng chung cho hiển thị và chấm.
        n_words, span_s = speech_span(stt.words)
        wpm = compute_wpm(n_words, span_s)
        hes_count, forgot_count, h = hesitations_per_min(classified, span_s)
        fillers = find_fillers(stt.words, segments)
        r_pct = filler_pct(len(fillers), n_words)
        f_wpm, f_pause, f_filler = score_wpm(wpm), score_hesitation(h), score_filler(r_pct)
        fluency = compute_fluency(f_wpm, f_pause, f_filler)

        # (f) Pitch + Pronunciation
        pitch = score_pitch(master, baseline)
        pronunciation = combine_pronunciation(acc.clarity, pitch.score)

        # (g) Semantic
        sentences = score_sentences(build_sentence_pairs(script, result.items), encode=encode)
        semantic = score_semantic(sentences)

        # (h) Tổng
        overall = compute_overall(acc.accuracy, fluency, pronunciation, semantic)

        # (i) Cờ chất lượng dữ liệu
        flags = _merge_flags(stt.flags, result.flags, acc.flags, pitch.flags,
                             baseline.flags if baseline is not None else ["no_baseline"])

        return EvaluationResultV2(
            schema_version="2.0", status="ok", reason=None,
            overall=overall, label=get_label(overall),  # type: ignore[arg-type]
            components={"accuracy": acc.accuracy, "fluency": fluency,
                        "pronunciation": pronunciation, "semantic": semantic},
            subscores={"f_wpm": f_wpm, "f_pause": f_pause, "f_filler": f_filler,
                       "p_clarity": acc.clarity, "p_pitch": pitch.score},
            accuracy_detail=acc.accuracy_detail,
            fluency_detail={
                "wpm": wpm, "hesitations_per_min": h, "hesitation_count": hes_count,
                "forgot_word_count": forgot_count, "pause_threshold_s": threshold,
                "filler_pct": r_pct, "filler_count": len(fillers),
            },
            pitch_detail={"range_semitones": pitch.range_semitones, "f0_ref_hz": pitch.f0_ref_hz,
                          "f0_ref_source": pitch.f0_ref_source,
                          "contour_st": None},  # Series: Pha 3B (phase3 #30)
            audio={"duration_s": master.duration_s, "voiced_ratio": voiced_ratio},
            baseline=_baseline_block(baseline),
            alignment=[AlignmentItem(**asdict(it)) for it in result.items],
            pauses=[
                PauseItem(start_s=cp.pause.start_s, end_s=cp.pause.end_s, kind=cp.kind.value,
                          after_ref_index=cp.after_ref_index)
                for cp in classified
            ],
            fillers=[
                FillerItem(start_s=f.start_s, end_s=f.end_s, source=f.source, text=f.text,
                           after_ref_index=after_ref_index(result.items, f.start_s, ref_tokens))
                for f in fillers
            ],
            sentences=[SentenceItem(**asdict(sr)) for sr in sentences],
            stt=stt_block,
            flags=flags,
            warnings=[],  # Pha 3B (D7)
            display_only={"loudness_db": None,  # Series: Pha 3B
                          "loudness_ref_db": baseline.mean_loudness_db if baseline else None},
        )


def analyze_baseline(
    audio_path: Path,
    *,
    vad_params: Any
) -> dict:
    """
    Dành riêng cho việc phân tích file ghi âm giọng baseline mẫu.
    Trả một dạng JSON duy nhất (ADR-004 D12):
    {schema_version, status, reason, profile | None, flags}.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        workdir = Path(temp_dir)

        probe(
            audio_path,
            max_seconds=max_audio_seconds,
            max_bytes=max_upload_bytes,
            allowed_formats=frozenset(allowed_formats)
        )

        master = decode_to_master(
            audio_path,
            workdir=workdir,
            max_seconds=max_audio_seconds,
            cap_margin_s=duration_cap_margin_s,
            timeout_s=decode_timeout_s
        )

        segments = detect_speech(master, params=vad_params)
        try:
            check_audio_quality(segments, master.duration_s)
        except InsufficientAudio:
            return {
                "schema_version": "2.0", "status": "insufficient_audio",
                "reason": "low_voiced_ratio", "profile": None, "flags": [],
            }

        pauses = find_pauses(segments, min_pause_s=0.35)
        pause_profile = compute_baseline_pause_profile(pauses)

        f0_profile = compute_baseline_f0(master)

        combined_flags = pause_profile["flags"] + f0_profile["flags"]

        profile = BaselineProfile(
            median_pause_s=pause_profile["median_pause_s"],
            hesitation_threshold_s=pause_profile["hesitation_threshold_s"],
            median_f0_hz=f0_profile["median_f0_hz"],
            mean_loudness_db=mean_loudness_db(extract_loudness_db(master)),
            flags=combined_flags
        )
        return {
            "schema_version": "2.0", "status": "ok", "reason": None,
            "profile": asdict(profile), "flags": combined_flags,
        }
