"""View and evaluate the pauses found by VAD.

Two modes, run from the repo root:

1) Quick view, NO hand labels needed (listen and check yourself):
    uv run python -m scripts.eval_vad samples/a.wav
    uv run python -m scripts.eval_vad samples/a.wav --csv check_sheet.csv    # sheet to fill in listening results
    uv run python -m scripts.eval_vad samples/a.wav --sweep --csv sweep.csv  # see how pause count changes with params

2) Compare with hand labels from Audacity (computes recall, precision):
    uv run python -m scripts.eval_vad samples/a.wav samples/a_labels.txt
    uv run python -m scripts.eval_vad samples/a.wav samples/a_labels.txt --sweep --csv out.csv
    uv run python -m scripts.eval_vad samples/a.wav samples/a_labels.txt --export-labels pred.txt

This is the team's measurement tool, not part of the app, and it does not run in CI.
Audio files and labels are sensitive data, do not commit them to Git.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from src.audio_processing.contracts import AudioRejected, MasterAudio, Pause, SpeechSegment
from src.audio_processing.decode import decode_to_master
from src.audio_processing.vad import VadParams, detect_speech, find_pauses
# NOTE: adjust the "src." import lines to match how the repo imports.

# Limits used only by this tool (not read from the app config).
MAX_SECONDS = 1320
CAP_MARGIN_S = 10
DECODE_TIMEOUT_S = 120


# ---------- Audacity labels ----------

def load_labels(path: Path, tag: str = "p") -> list[Pause]:
    """Read an Audacity label file (each line: start<TAB>end<TAB>label, in seconds).

    Only keep lines whose label equals `tag`. Returns a sorted, non-overlapping list.
    """
    pauses: list[Pause] = []
    text = path.read_text(encoding="utf-8-sig")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.startswith("\\"):   # a "\" line is Audacity's frequency range
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            raise ValueError(f"{path}:{number}: expected 'start<TAB>end<TAB>label', got {line!r}")
        if parts[2].strip().lower() != tag.lower():
            continue
        try:
            start, end = (float(value.replace(",", ".")) for value in parts[:2])
        except ValueError:
            raise ValueError(f"{path}:{number}: start/end must be numbers, got {line!r}") from None
        if end <= start:
            raise ValueError(f"{path}:{number}: label {tag!r} must span a region (end > start)")
        pauses.append(Pause(start_s=start, end_s=end))

    pauses.sort(key=lambda p: p.start_s)
    for previous, following in zip(pauses, pauses[1:]):
        if following.start_s < previous.end_s:
            raise ValueError(
                f"{path}: labels overlap around {following.start_s:.3f}s; fix them in Audacity"
            )
    return pauses


def write_labels(path: Path, pauses: list[Pause], tag: str = "v") -> None:
    """Write predicted pauses as a label file to import into Audacity (File → Import → Labels)."""
    lines = [f"{p.start_s:.6f}\t{p.end_s:.6f}\t{tag}" for p in pauses]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


# ---------- matching ----------

def _iou(a: Pause, b: Pause) -> float:
    """Intersection over Union of two time ranges."""
    inter = min(a.end_s, b.end_s) - max(a.start_s, b.start_s)
    if inter <= 0:
        return 0.0
    return inter / (a.duration_s + b.duration_s - inter)


@dataclass(frozen=True)
class Matching:
    pairs: list[tuple[Pause, Pause]]   # (hand label, prediction)
    unmatched_reference: list[Pause]
    unmatched_predicted: list[Pause]


def match(reference: list[Pause], predicted: list[Pause], *, min_iou: float = 0.5) -> Matching:
    """Match hand-labelled pauses one-to-one with predicted pauses when IoU >= min_iou.

    Both lists must be sorted and non-overlapping within themselves.
    Walks two pointers in parallel, O(n + m) complexity.
    """
    pairs: list[tuple[Pause, Pause]] = []
    matched_ref: set[int] = set()
    matched_pred: set[int] = set()
    i = j = 0
    while i < len(reference) and j < len(predicted):
        ref, pred = reference[i], predicted[j]
        if _iou(ref, pred) >= min_iou:
            pairs.append((ref, pred))
            matched_ref.add(i)
            matched_pred.add(j)
            i += 1
            j += 1
        elif ref.end_s <= pred.end_s:     # whichever range ends first can no longer match
            i += 1
        else:
            j += 1
    return Matching(
        pairs=pairs,
        unmatched_reference=[r for k, r in enumerate(reference) if k not in matched_ref],
        unmatched_predicted=[p for k, p in enumerate(predicted) if k not in matched_pred],
    )


# ---------- metrics ----------

@dataclass(frozen=True)
class Report:
    min_pause_s: float
    n_reference: int            # all hand-labelled pauses
    n_reference_long: int       # hand-labelled pauses >= min_pause_s (recall denominator)
    n_predicted: int            # pauses VAD reports (filtered to >= min_pause_s)
    n_found_long: int           # long hand-labelled pauses that VAD caught
    n_matched: int              # number of matched pairs (error denominator)
    missed: list[Pause]         # long hand-labelled pauses that VAD missed
    false_alarms: list[Pause]   # pauses VAD reports with no matching hand label
    mean_duration_error_s: float | None       # prediction − hand label, signed (negative = VAD shorter)
    mean_abs_duration_error_s: float | None
    mean_start_error_s: float | None          # prediction − hand label, signed
    mean_end_error_s: float | None

    @property
    def recall(self) -> float | None:
        return self.n_found_long / self.n_reference_long if self.n_reference_long else None

    @property
    def precision(self) -> float | None:
        return self.n_matched / self.n_predicted if self.n_predicted else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize(reference: list[Pause], predicted: list[Pause], *,
              min_pause_s: float, min_iou: float = 0.5) -> Report:
    """Compute recall, precision and errors.

    Recall: of the hand-labelled pauses >= min_pause_s, how many VAD caught.
    Precision: of the pauses VAD reports, how many match any hand label
    (including labels shorter than the threshold, since that pause is real).
    """
    matching = match(reference, predicted, min_iou=min_iou)
    reference_long = [r for r in reference if r.duration_s >= min_pause_s]
    long_ids = {id(r) for r in reference_long}
    found_long = sum(1 for ref, _ in matching.pairs if id(ref) in long_ids)
    missed = [r for r in matching.unmatched_reference if id(r) in long_ids]

    duration_errors = [pred.duration_s - ref.duration_s for ref, pred in matching.pairs]
    return Report(
        min_pause_s=min_pause_s,
        n_reference=len(reference),
        n_reference_long=len(reference_long),
        n_predicted=len(predicted),
        n_found_long=found_long,
        n_matched=len(matching.pairs),
        missed=missed,
        false_alarms=matching.unmatched_predicted,
        mean_duration_error_s=_mean(duration_errors),
        mean_abs_duration_error_s=_mean([abs(e) for e in duration_errors]),
        mean_start_error_s=_mean([pred.start_s - ref.start_s for ref, pred in matching.pairs]),
        mean_end_error_s=_mean([pred.end_s - ref.end_s for ref, pred in matching.pairs]),
    )


# ---------- run pipeline ----------

def run_once(master: MasterAudio, reference: list[Pause], params: VadParams, *,
             min_pause_s: float, min_iou: float) -> tuple[Report, list[Pause]]:
    segments = detect_speech(master, params=params)
    predicted = find_pauses(segments, min_pause_s=min_pause_s)
    return summarize(reference, predicted, min_pause_s=min_pause_s, min_iou=min_iou), predicted


# ---------- display ----------

def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _sec(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.3f}s"


def format_report(report: Report, params: VadParams) -> str:
    lines = [
        f"VAD: threshold={params.threshold} min_speech={params.min_speech_duration_ms}ms "
        f"min_silence={params.min_silence_duration_ms}ms pad={params.speech_pad_ms}ms",
        f"Pause gán tay: {report.n_reference} (dài >= {report.min_pause_s}s: {report.n_reference_long})"
        f" | VAD báo (>= {report.min_pause_s}s): {report.n_predicted}",
        f"Recall    : {report.n_found_long}/{report.n_reference_long} = {_pct(report.recall)}",
        f"Precision : {report.n_matched}/{report.n_predicted} = {_pct(report.precision)}",
        f"Sai số độ dài (VAD − tay): trung bình {_sec(report.mean_duration_error_s)}, "
        f"tuyệt đối {_sec(report.mean_abs_duration_error_s)} (trên {report.n_matched} cặp khớp)",
        f"Sai số điểm đầu {_sec(report.mean_start_error_s)}, điểm cuối {_sec(report.mean_end_error_s)}",
    ]
    if report.missed:
        lines.append("Bỏ sót (nhãn tay dài, VAD không có):")
        lines += [f"  {p.start_s:8.3f} → {p.end_s:8.3f}  ({p.duration_s:.3f}s)" for p in report.missed]
    if report.false_alarms:
        lines.append("Báo thừa (VAD có, không khớp nhãn tay):")
        lines += [f"  {p.start_s:8.3f} → {p.end_s:8.3f}  ({p.duration_s:.3f}s)" for p in report.false_alarms]
    return "\n".join(lines)


CSV_COLUMNS = ["threshold", "min_speech_ms", "min_silence_ms", "pad_ms", "recall", "precision",
               "n_reference_long", "n_predicted", "missed", "false_alarms",
               "mean_duration_error_s", "mean_abs_duration_error_s"]


def _row(params: VadParams, report: Report) -> dict:
    return {
        "threshold": params.threshold,
        "min_speech_ms": params.min_speech_duration_ms,
        "min_silence_ms": params.min_silence_duration_ms,
        "pad_ms": params.speech_pad_ms,
        "recall": report.recall,
        "precision": report.precision,
        "n_reference_long": report.n_reference_long,
        "n_predicted": report.n_predicted,
        "missed": len(report.missed),
        "false_alarms": len(report.false_alarms),
        "mean_duration_error_s": report.mean_duration_error_s,
        "mean_abs_duration_error_s": report.mean_abs_duration_error_s,
    }


def format_table(rows: list[dict]) -> str:
    header = (f"{'min_speech':>10} {'min_silence':>11} {'pad':>4} {'recall':>8} {'precision':>9} "
              f"{'missed':>6} {'false':>5} {'dur_err':>9}")
    lines = [header]
    for r in rows:
        lines.append(
            f"{r['min_speech_ms']:>10} {r['min_silence_ms']:>11} {r['pad_ms']:>4} "
            f"{_pct(r['recall']):>8} {_pct(r['precision']):>9} {r['missed']:>6} "
            f"{r['false_alarms']:>5} {_sec(r['mean_duration_error_s']):>9}"
        )
    return "\n".join(lines)


# ---------- quick view mode (no hand labels needed) ----------

@dataclass(frozen=True)
class Overview:
    duration_s: float
    segments: list[SpeechSegment]
    pauses: list[Pause]        # gaps >= min_pause_s (these are the scored pauses)
    short_gaps: list[Pause]    # gaps from show_short_s up to below min_pause_s (reference only)

    @property
    def speech_s(self) -> float:
        return sum(segment.duration_s for segment in self.segments)

    @property
    def speech_ratio(self) -> float | None:
        return self.speech_s / self.duration_s if self.duration_s > 0 else None


def describe(segments: list[SpeechSegment], duration_s: float, *,
             min_pause_s: float, show_short_s: float = 0.10) -> Overview:
    floor = min(show_short_s, min_pause_s)
    gaps = find_pauses(segments, min_pause_s=floor)
    return Overview(
        duration_s=duration_s,
        segments=segments,
        pauses=[g for g in gaps if g.duration_s >= min_pause_s],
        short_gaps=[g for g in gaps if g.duration_s < min_pause_s],
    )


def clock(seconds: float) -> str:
    """Format m:ss.mmm to jump to the right spot in a media player."""
    total_ms = round(seconds * 1000)
    minutes, rest_ms = divmod(total_ms, 60_000)
    secs, ms = divmod(rest_ms, 1000)
    return f"{minutes}:{secs:02d}.{ms:03d}"


PAUSE_BUCKETS = [("dưới 0.5s", 0.0, 0.5), ("0.5–1s", 0.5, 1.0), ("1–2s", 1.0, 2.0), ("từ 2s", 2.0, float("inf"))]


def format_overview(overview: Overview, params: VadParams, *, min_pause_s: float,
                    show_segments: bool = False) -> str:
    ratio = overview.speech_ratio
    lines = [
        f"VAD: threshold={params.threshold} min_speech={params.min_speech_duration_ms}ms "
        f"min_silence={params.min_silence_duration_ms}ms pad={params.speech_pad_ms}ms",
        f"Thời lượng {clock(overview.duration_s)} | {len(overview.segments)} đoạn nói | "
        f"thời gian nói {overview.speech_s:.1f}s ({_pct(ratio)}) | "
        f"pause >= {min_pause_s}s: {len(overview.pauses)} | khoảng ngắt ngắn hơn: {len(overview.short_gaps)}",
    ]
    if not overview.segments:
        lines.append("Không phát hiện đoạn nói nào (file im lặng, hoặc tham số quá chặt).")
    if overview.pauses:
        counts = [sum(1 for p in overview.pauses if low <= p.duration_s < high)
                  for _, low, high in PAUSE_BUCKETS]
        lines.append("Phân bố độ dài pause: " + ", ".join(
            f"{name}: {count}" for (name, _, _), count in zip(PAUSE_BUCKETS, counts)))
        lines.append("Pause (được tính điểm):")
        lines += [f"  {i:>3}. {clock(p.start_s):>9} → {clock(p.end_s):>9}  dài {p.duration_s:.3f}s"
                  for i, p in enumerate(overview.pauses, start=1)]
    if overview.short_gaps:
        lines.append("Khoảng ngắt ngắn hơn ngưỡng (không tính điểm, chỉ để tham khảo):")
        lines += [f"       {clock(p.start_s):>9} → {clock(p.end_s):>9}  dài {p.duration_s:.3f}s"
                  for p in overview.short_gaps]
    if show_segments:
        lines.append("Đoạn nói:")
        lines += [f"  {i:>3}. {clock(s.start_s):>9} → {clock(s.end_s):>9}  dài {s.duration_s:.3f}s"
                  for i, s in enumerate(overview.segments, start=1)]
    return "\n".join(lines)


CHECK_SHEET_COLUMNS = ["start_s", "end_s", "duration_s", "start_clock", "vad_kind", "your_verdict", "note"]


def write_check_sheet(path: Path, overview: Overview) -> None:
    """Sheet to listen and fill in: each row is one gap VAD found.

    The last two columns (your_verdict, note) are left blank for you, e.g. "dung" / "sai" / "khong chac".
    """
    rows = [("pause", p) for p in overview.pauses] + [("short", p) for p in overview.short_gaps]
    rows.sort(key=lambda item: item[1].start_s)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:   # utf-8-sig so Excel reads it right
        writer = csv.writer(handle)
        writer.writerow(CHECK_SHEET_COLUMNS)
        for kind, p in rows:
            writer.writerow([f"{p.start_s:.3f}", f"{p.end_s:.3f}", f"{p.duration_s:.3f}",
                             clock(p.start_s), kind, "", ""])


OVERVIEW_CSV_COLUMNS = ["min_speech_ms", "min_silence_ms", "pad_ms", "segments", "pauses",
                        "short_gaps", "speech_ratio", "mean_pause_s"]


def _overview_row(params: VadParams, overview: Overview) -> dict:
    mean_pause = (sum(p.duration_s for p in overview.pauses) / len(overview.pauses)
                  if overview.pauses else None)
    return {
        "min_speech_ms": params.min_speech_duration_ms,
        "min_silence_ms": params.min_silence_duration_ms,
        "pad_ms": params.speech_pad_ms,
        "segments": len(overview.segments),
        "pauses": len(overview.pauses),
        "short_gaps": len(overview.short_gaps),
        "speech_ratio": overview.speech_ratio,
        "mean_pause_s": mean_pause,
    }


def format_overview_table(rows: list[dict]) -> str:
    lines = [f"{'min_speech':>10} {'min_silence':>11} {'pad':>4} {'segments':>8} {'pauses':>6} "
             f"{'short':>5} {'speech%':>8} {'mean_pause':>10}"]
    for r in rows:
        mean = "n/a" if r["mean_pause_s"] is None else f"{r['mean_pause_s']:.3f}s"
        lines.append(f"{r['min_speech_ms']:>10} {r['min_silence_ms']:>11} {r['pad_ms']:>4} "
                     f"{r['segments']:>8} {r['pauses']:>6} {r['short_gaps']:>5} "
                     f"{_pct(r['speech_ratio']):>8} {mean:>10}")
    return "\n".join(lines)


# ---------- command line ----------

def _int_list(text: str) -> list[int]:
    return [int(part) for part in text.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    default = VadParams()
    p = argparse.ArgumentParser(description="Xem pause do VAD tìm ra, hoặc so với nhãn gán tay từ Audacity.")
    p.add_argument("audio", type=Path, help="file âm thanh (wav/webm/mp3/...)")
    p.add_argument("labels", type=Path, nargs="?",
                   help="file nhãn Audacity (.txt). Bỏ trống để chạy chế độ xem nhanh")
    p.add_argument("--tag", default="p", help="nhãn dùng cho pause trong file nhãn (mặc định: p)")
    p.add_argument("--min-pause", type=float, default=0.35, help="ngưỡng pause (giây)")
    p.add_argument("--min-iou", type=float, default=0.5, help="IoU tối thiểu để coi là khớp (có nhãn)")
    p.add_argument("--show-short", type=float, default=0.10,
                   help="(xem nhanh) hiển thị thêm các khoảng ngắt từ ngần này giây trở lên")
    p.add_argument("--segments", action="store_true", help="(xem nhanh) in cả danh sách đoạn nói")
    p.add_argument("--threshold", type=float, default=default.threshold)
    p.add_argument("--min-speech-ms", type=int, default=default.min_speech_duration_ms)
    p.add_argument("--min-silence-ms", type=int, default=default.min_silence_duration_ms)
    p.add_argument("--pad-ms", type=int, default=default.speech_pad_ms)
    p.add_argument("--sweep", action="store_true", help="thử lưới tham số thay vì một bộ")
    p.add_argument("--pads", type=_int_list, default=[0, 10, 30])
    p.add_argument("--silences", type=_int_list, default=[100, 150, 250])
    p.add_argument("--min-speeches", type=_int_list, default=[250])
    p.add_argument("--csv", type=Path,
                   help="ghi CSV: bảng điền kết quả nghe (xem nhanh, một bộ tham số), "
                        "hoặc bảng so sánh tham số (--sweep)")
    p.add_argument("--export-labels", type=Path,
                   help="ghi pause VAD ra file nhãn để nhập vào Audacity (không dùng với --sweep)")
    return p


def _write_rows(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.sweep and args.export_labels:
        print("--export-labels không dùng cùng --sweep")
        return 2

    reference = load_labels(args.labels, args.tag) if args.labels else None
    base = VadParams(threshold=args.threshold, min_speech_duration_ms=args.min_speech_ms,
                     min_silence_duration_ms=args.min_silence_ms, speech_pad_ms=args.pad_ms)

    with tempfile.TemporaryDirectory() as tmp:   # Master is sensitive data, delete when done
        try:
            master = decode_to_master(args.audio, Path(tmp), max_seconds=MAX_SECONDS,
                                      cap_margin_s=CAP_MARGIN_S, timeout_s=DECODE_TIMEOUT_S)
        except AudioRejected as error:
            print(f"Không giải mã được file: [{error.code}] {error.message}")
            return 2
        for warning in master.warnings:
            print(f"[ffmpeg] {warning}")

        if args.sweep:
            rows = []
            for min_speech, silence, pad in itertools.product(
                    args.min_speeches, args.silences, args.pads):
                params = replace(base, min_speech_duration_ms=min_speech,
                                 min_silence_duration_ms=silence, speech_pad_ms=pad)
                if reference is None:
                    segments = detect_speech(master, params=params)
                    overview = describe(segments, master.duration_s, min_pause_s=args.min_pause,
                                        show_short_s=args.show_short)
                    rows.append(_overview_row(params, overview))
                else:
                    report, _ = run_once(master, reference, params,
                                         min_pause_s=args.min_pause, min_iou=args.min_iou)
                    rows.append(_row(params, report))
            columns = OVERVIEW_CSV_COLUMNS if reference is None else CSV_COLUMNS
            print(format_overview_table(rows) if reference is None else format_table(rows))
            if args.csv:
                _write_rows(args.csv, columns, rows)
                print(f"Đã ghi {len(rows)} dòng vào {args.csv}")
            return 0

        if reference is None:
            segments = detect_speech(master, params=base)
            overview = describe(segments, master.duration_s, min_pause_s=args.min_pause,
                                show_short_s=args.show_short)
            print(format_overview(overview, base, min_pause_s=args.min_pause,
                                  show_segments=args.segments))
            predicted = overview.pauses
            if args.csv:
                write_check_sheet(args.csv, overview)
                print(f"Đã ghi bảng kiểm tra vào {args.csv}")
        else:
            report, predicted = run_once(master, reference, base,
                                         min_pause_s=args.min_pause, min_iou=args.min_iou)
            print(format_report(report, base))
        if args.export_labels:
            write_labels(args.export_labels, predicted)
            print(f"Đã ghi {len(predicted)} nhãn vào {args.export_labels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())