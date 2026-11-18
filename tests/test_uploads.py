"""Upload safety: fixed file names (no path traversal) and size limits."""

import io
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient

from src.app.uploads import BodySizeLimitMiddleware, safe_upload_path, save_upload_limited
from src.audio_processing.contracts import AudioRejected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("take.webm", "upload.webm"),
        ("TAKE.WAV", "upload.wav"),
        ("../../src/app/main.py", "upload"),
        ("../../evil.wav", "upload.wav"),
        ("/etc/passwd", "upload"),
        ("C:\\Users\\a\\..\\b.mp3", "upload.mp3"),
        ("", "upload"),
        (None, "upload"),
        ("noext", "upload"),
    ],
)
def test_safe_upload_path_stays_in_directory(tmp_path, filename, expected):
    path = safe_upload_path(tmp_path, filename)
    assert path == tmp_path / expected
    assert path.resolve().parent == tmp_path.resolve()


def test_safe_upload_path_custom_stem(tmp_path):
    assert safe_upload_path(tmp_path, "x.webm", stem="baseline") == tmp_path / "baseline.webm"


def _upload(data: bytes) -> UploadFile:
    return UploadFile(filename="a.wav", file=io.BytesIO(data))


def test_save_upload_limited_writes_file(tmp_path):
    dest = tmp_path / "upload.wav"
    assert save_upload_limited(_upload(b"abc"), dest, max_bytes=3) == 3
    assert dest.read_bytes() == b"abc"


def test_save_upload_limited_stops_and_removes_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr("src.app.uploads.CHUNK_BYTES", 4)
    dest = tmp_path / "upload.wav"
    with pytest.raises(AudioRejected) as err:
        save_upload_limited(_upload(b"0123456789"), dest, max_bytes=5)
    assert err.value.code == "too_large"
    assert not dest.exists()


def _limited_app(max_bytes: int) -> TestClient:
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_bytes)

    @app.post("/up")
    async def up(audio: Annotated[UploadFile, File()]):
        return {"size": len(audio.file.read())}

    return TestClient(app)


def test_middleware_allows_small_body():
    r = _limited_app(10_000).post("/up", files={"audio": ("a.wav", b"x" * 100)})
    assert r.status_code == 200
    assert r.json() == {"size": 100}


def test_middleware_rejects_large_content_length():
    r = _limited_app(1_000).post("/up", files={"audio": ("a.wav", b"x" * 5_000)})
    assert r.status_code == 413
    assert r.json()["error_code"] == "too_large"


def test_middleware_rejects_large_body_without_content_length():
    """A streamed (chunked) multipart body has no Content-Length; bytes are counted instead."""
    boundary = "b0undary"
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; '
        'filename="a.wav"\r\nContent-Type: audio/wav\r\n\r\n'
    ).encode()

    def chunks():
        yield head
        for _ in range(10):
            yield b"x" * 500
        yield f"\r\n--{boundary}--\r\n".encode()

    r = _limited_app(1_000).post(
        "/up",
        content=chunks(),
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )
    assert r.status_code == 413
    assert r.json()["error_code"] == "too_large"


def test_evaluate_endpoint_ignores_client_path(monkeypatch, tmp_path):
    """The uploaded name '../../x.wav' must not be used as the saved path."""
    from src.app import main

    seen: dict[str, Path] = {}

    def fake_evaluate(audio_path, script, baseline, *, vad_params, **callbacks):
        seen["path"] = audio_path
        raise AudioRejected("corrupt", "stop here")

    monkeypatch.setattr(main.settings, "baseline_required", False)
    monkeypatch.setattr(main, "evaluate_session", fake_evaluate)
    client = TestClient(main.app)
    r = client.post(
        "/api/evaluate",
        files={"audio": ("../../x.wav", b"RIFF", "audio/wav")},
        data={"script": "Hello."},
    )
    assert r.status_code == 202
    job = client.get(f"/api/evaluate/{r.json()['job_id']}").json()
    assert job["status"] == "failed"
    assert job["error_code"] == "corrupt"
    assert seen["path"].name == "upload.wav"
