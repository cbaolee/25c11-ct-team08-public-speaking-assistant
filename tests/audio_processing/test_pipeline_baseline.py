import inspect
import shutil
from pathlib import Path

import pytest

from src.audio_processing.contracts import AudioRejected, VadParams
from src.audio_processing.pipeline import analyze_baseline


def test_signature_has_no_settings_param():
    params = inspect.signature(analyze_baseline).parameters
    assert "settings" not in params
    assert "audio_path" in params
    assert "vad_params" in params


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
def test_garbage_file_is_rejected_not_type_error(tmp_path: Path):
    # Gọi đúng như main.py (/api/baseline): chỉ audio_path= và vad_params=.
    # Trước khi sửa: TypeError (thiếu keyword-only 'settings').
    bad = tmp_path / "garbage.wav"
    bad.write_bytes(b"this is not audio" * 100)
    with pytest.raises(AudioRejected) as info:
        analyze_baseline(audio_path=bad, vad_params=VadParams())
    assert info.value.code == "corrupt"
