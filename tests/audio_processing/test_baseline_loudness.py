"""Test baseline.loudness_series (E1).

Audio là sóng sin tổng hợp ghi vào tmp_path, không phải dữ liệu thật.
"""

import math
from pathlib import Path

import numpy as np
import parselmouth
import pytest

from src.audio_processing import baseline
from src.audio_processing.contracts import MasterAudio


def _sine_master(tmp_path: Path, duration_s: float = 2.2) -> MasterAudio:
    sr = 16000
    t = np.arange(int(sr * duration_s)) / sr
    values = 0.3 * np.sin(2 * math.pi * 220.0 * t)
    path = tmp_path / "sine.wav"
    parselmouth.Sound(values, sampling_frequency=sr).save(str(path), "WAV")
    return MasterAudio(path=path, duration_s=duration_s, warnings=[])


def test_loudness_series_shape_and_values(tmp_path):
    res = baseline.loudness_series(_sine_master(tmp_path, 2.2))
    assert res is not None
    assert res["start_s"] == 0.0 and res["step_s"] == 0.1
    # ceil(round(2.2 / 0.1, 9)) = 22, không phải 23 (sai số dấu phẩy động)
    assert len(res["values"]) == 22
    floats = [v for v in res["values"] if v is not None]
    assert len(floats) >= 1
    for v in res["values"]:
        assert v is None or (isinstance(v, float) and math.isfinite(v))


def test_loudness_series_other_duration(tmp_path):
    res = baseline.loudness_series(_sine_master(tmp_path, 1.0))
    assert res is not None and len(res["values"]) == 10  # ceil(1.0 / 0.1)


def test_loudness_series_custom_step(tmp_path):
    res = baseline.loudness_series(_sine_master(tmp_path, 1.0), step_s=0.5)
    assert res is not None
    assert res["step_s"] == 0.5 and len(res["values"]) == 2


def test_loudness_series_missing_file_is_none(tmp_path):
    master = MasterAudio(path=tmp_path / "khong_ton_tai.wav", duration_s=2.0, warnings=[])
    assert baseline.loudness_series(master) is None


def test_loudness_series_exception_gives_whole_series_none(tmp_path, monkeypatch):
    master = _sine_master(tmp_path, 1.0)

    def boom(*a, **k):
        raise RuntimeError("praat loi")

    monkeypatch.setattr(baseline.parselmouth, "Sound", boom)
    assert baseline.loudness_series(master) is None


def test_existing_loudness_helpers_unchanged(tmp_path):
    # extract_loudness_db vẫn lấy mẫu mỗi 0.5 s: 1.0 s -> tối đa 2 mẫu hữu hạn
    vals = baseline.extract_loudness_db(_sine_master(tmp_path, 1.0))
    assert len(vals) <= 2 and all(math.isfinite(v) for v in vals)
    assert baseline.mean_loudness_db([60.0, math.nan, 70.0]) == pytest.approx(65.0)
