"""Safe handling of uploaded files: fixed file names and a size limit while writing."""

import json
from pathlib import Path

from fastapi import UploadFile

from src.audio_processing.contracts import AudioRejected

# Suffixes kept from the client's file name; anything else is dropped (ffprobe decides the format).
ALLOWED_UPLOAD_SUFFIXES = frozenset(
    {".wav", ".mp3", ".ogg", ".oga", ".opus", ".flac", ".webm", ".mka", ".m4a", ".pdf"}
)
CHUNK_BYTES = 1024 * 1024


def too_large_message(max_bytes: int) -> str:
    return (
        f"The file is too large (maximum {max_bytes // (1024 * 1024)} MB). "
        "Please choose a smaller file."
    )


def safe_upload_path(directory: Path, filename: str | None, *, stem: str = "upload") -> Path:
    """Return `directory/<stem><suffix>`; the client's name is never used as a path.

    Only the suffix is kept, and only when it is in ALLOWED_UPLOAD_SUFFIXES, so names such as
    "../../main.py" or "/etc/passwd" cannot leave `directory`.
    """
    # Windows clients may send "C:\\x\\a.wav"; treat both separators the same.
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        suffix = ""
    return directory / f"{stem}{suffix}"


def save_upload_limited(upload: UploadFile, dest: Path, *, max_bytes: int) -> int:
    """Copy `upload` to `dest` in chunks and stop as soon as it exceeds `max_bytes`.

    Raises AudioRejected("too_large") and removes the partial file. Returns the bytes written.
    """
    written = 0
    try:
        with open(dest, "wb") as out:
            # Starlette has already spooled the upload; read its file object in chunks.
            while chunk := upload.file.read(CHUNK_BYTES):
                written += len(chunk)
                if written > max_bytes:
                    raise AudioRejected("too_large", too_large_message(max_bytes))
                out.write(chunk)
    except AudioRejected:
        dest.unlink(missing_ok=True)
        raise
    return written


class BodySizeLimitMiddleware:
    """Pure ASGI middleware: answer 413 when a request body is larger than `max_bytes`.

    Checks Content-Length first; for bodies without it, counts bytes while they arrive.
    FastAPI turns errors raised while it parses a form into a 400, so instead of raising, the
    middleware remembers the overflow and replaces whatever response comes back with the 413.
    """

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def _send_413(self, send) -> None:
        body = json.dumps(
            {"error_code": "too_large", "message": too_large_message(self.max_bytes)}
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for key, value in scope.get("headers", []):
            if key == b"content-length":
                try:
                    if int(value) > self.max_bytes:
                        await self._send_413(send)
                        return
                except ValueError:
                    pass
                break

        received = 0
        overflow = False
        replaced = False

        async def limited_receive():
            nonlocal received, overflow
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    overflow = True
                    # Stop feeding the app: an empty final chunk ends the body here.
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def guarded_send(message):
            nonlocal replaced
            if overflow:
                if not replaced:
                    replaced = True
                    await self._send_413(send)
                return
            await send(message)

        await self.app(scope, limited_receive, guarded_send)
