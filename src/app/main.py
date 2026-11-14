import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.audio_processing.contracts import (
    AudioRejected,
    BaselineProfile,
    InsufficientAudio,
    VadParams,
)
from src.audio_processing.pipeline import analyze_baseline, evaluate_session
from src.audio_processing.result_schema import BaselineResponse
from src.text_processing.contracts import (
    CATEGORY_SLUG_MAP,
    ScriptGenerationError,
    ScriptGenerationRequest,
)
from src.text_processing.pipeline import ScriptGenerationPipeline

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app = FastAPI()
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")

_script_pipeline: ScriptGenerationPipeline | None = None


def get_script_pipeline() -> ScriptGenerationPipeline:
    """Return the process-wide `ScriptGenerationPipeline` singleton."""
    global _script_pipeline
    if _script_pipeline is None:
        _script_pipeline = ScriptGenerationPipeline()
    return _script_pipeline


class SaveScriptPayload(BaseModel):
    """Request body for `POST /api/scripts`."""

    title: str = "Untitled Script"
    script: str
    duration_min: int | None = None
    source: str = "user"



@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "demo_ui.html")


@app.exception_handler(AudioRejected)
async def audio_rejected_handler(request: Request, exc: AudioRejected):
    """
    Xử lý lỗi HTTP 422 khi probe hoặc decode từ chối file audio[cite: 1].
    """
    return JSONResponse(
        status_code=422,
        content={"error_code": exc.code, "message": exc.message}
    )


_BASELINE_REQUIRED = ("median_pause_s", "hesitation_threshold_s", "median_f0_hz", "flags")


def _num(value, name: str, *, nullable: bool) -> float | None:
    if value is None and nullable:
        return None
    msg = f"{name} phải là số hữu hạn" + (" hoặc null" if nullable else "")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(msg)
    try:
        x = float(value)  # int rất lớn -> OverflowError, đổi thành ValueError (422, không phải 500)
    except OverflowError:
        raise ValueError(msg) from None
    if not math.isfinite(x):
        raise ValueError(msg)
    return x


# Cờ mà baseline có thể sinh ra: compute_baseline_pause_profile ("baseline_pause_unreliable")
# và compute_baseline_f0 ("no_f0"). "no_baseline" bị loại: gửi baseline mà kèm cờ đó là mâu thuẫn.
_BASELINE_ALLOWED_FLAGS = frozenset({"baseline_pause_unreliable", "no_f0"})


def _parse_baseline(raw: str) -> BaselineProfile:
    """Dựng BaselineProfile từ JSON client; sai JSON, thiếu/thừa trường, sai kiểu hoặc sai miền
    giá trị -> ValueError (endpoint trả 422 invalid_baseline).

    mean_loudness_db không bắt buộc (thiếu -> None, D11).

    TỰ CHỌN (CLAUDE.md 1.9.2 #23): kiểm miền giá trị, suy trực tiếp từ scoring_framework §5.2/§6.2,
    không thêm ngưỡng chấm điểm mới. So sánh sau round(x, 6) để khỏi vướng nhiễu float
    (vd 2 * 0.34999999999999987 = 0.6999999999999997):
      - hesitation_threshold_s trong [0.7, 1.2]  (§5.2: ngưỡng luôn trong khoảng này)
      - median_pause_s: None hoặc >= 0.35        (§5.2: chỉ tính khoảng lặng từ 0.35 s)
      - median_f0_hz: None hoặc > 0
      - mean_loudness_db: None hoặc số hữu hạn bất kỳ (không đặt khoảng)
      - flags chỉ thuộc {"baseline_pause_unreliable", "no_f0"}

    Giới hạn còn lại: client vẫn chọn được bất kỳ giá trị nào trong khoảng hợp lệ (ví dụ luôn
    ngưỡng 1.2 s để ít bị tính ngập ngừng, hoặc F0 chuẩn tuỳ ý). Cách khắc phục triệt để là lưu
    baseline phía server rồi tra theo user (M6), không nhận từ client.
    """
    data = json.loads(raw)  # JSONDecodeError là con của ValueError
    if not isinstance(data, dict):
        raise ValueError("baseline_profile phải là JSON object")
    missing = [k for k in _BASELINE_REQUIRED if k not in data]
    extra = set(data) - set(_BASELINE_REQUIRED) - {"mean_loudness_db"}
    if missing or extra:
        raise ValueError(f"trường thiếu: {missing}, trường lạ: {sorted(extra)}")
    flags = data["flags"]
    if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
        raise ValueError("flags phải là list[str]")
    bad_flags = sorted(set(flags) - _BASELINE_ALLOWED_FLAGS)
    if bad_flags:
        raise ValueError(f"flags không hợp lệ: {bad_flags}")
    median_pause_s = _num(data["median_pause_s"], "median_pause_s", nullable=True)
    threshold = _num(data["hesitation_threshold_s"], "hesitation_threshold_s", nullable=False)
    median_f0_hz = _num(data["median_f0_hz"], "median_f0_hz", nullable=True)
    if not 0.7 <= round(threshold, 6) <= 1.2:
        raise ValueError("hesitation_threshold_s phải nằm trong [0.7, 1.2]")
    if median_pause_s is not None and round(median_pause_s, 6) < 0.35:
        raise ValueError("median_pause_s phải là null hoặc >= 0.35")
    if median_f0_hz is not None and median_f0_hz <= 0:
        raise ValueError("median_f0_hz phải là null hoặc > 0")
    return BaselineProfile(
        median_pause_s=median_pause_s,
        hesitation_threshold_s=threshold,
        median_f0_hz=median_f0_hz,
        mean_loudness_db=_num(data.get("mean_loudness_db"), "mean_loudness_db", nullable=True),
        flags=flags,
    )


@app.post("/api/evaluate")
async def evaluate_endpoint(
    audio: Annotated[UploadFile, File(...)],
    script: Annotated[str, Form(...)],
    baseline_profile: Annotated[str, Form()] = "",
):
    """
    Endpoint xử lý chấm điểm phiên luyện tập thuyết trình[cite: 1].
    """
    # Khởi tạo trực tiếp cấu hình VAD mặc định
    vad_params = VadParams()

    # Parse BaselineProfile từ JSON string nếu client có gửi lên[cite: 1]
    baseline = None
    if baseline_profile:
        try:
            baseline = _parse_baseline(baseline_profile)
        except (TypeError, KeyError, ValueError) as exc:
            return JSONResponse(
                status_code=422,
                content={"error_code": "invalid_baseline", "message": str(exc)},
            )

    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = Path(temp_dir) / (audio.filename or "uploaded.wav")
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        # Không cần truyền settings nữa vì pipeline.py đã tự import
        result = evaluate_session(
            audio_path=audio_path,
            script=script,
            baseline=baseline,
            vad_params=vad_params
        )

        return result.model_dump(mode="json")


@app.post("/api/baseline")
async def baseline_endpoint(
    audio: Annotated[UploadFile, File(...)]
):
    """
    Endpoint xử lý phân tích giọng baseline mẫu[cite: 1].
    """
    vad_params = VadParams()

    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = Path(temp_dir) / (audio.filename or "baseline.wav")
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        try:
            # D12: một dạng JSON {schema_version, status, reason, profile, flags}
            payload = analyze_baseline(
                audio_path=audio_path,
                vad_params=vad_params
            )
        except InsufficientAudio:
            payload = {
                "schema_version": "2.0", "status": "insufficient_audio",
                "reason": "low_voiced_ratio", "profile": None, "flags": [],
            }
        return BaselineResponse(**payload).model_dump(mode="json")


@app.exception_handler(ScriptGenerationError)
async def script_generation_error_handler(_: Request, exc: ScriptGenerationError) -> JSONResponse:
    """Return structured JSON `{error_code, message}` for Script Generation errors (Brief §5.7)."""
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


def _resolve_user_id(request: Request, explicit_user_id: str | None = None) -> str:
    if explicit_user_id and explicit_user_id.strip():
        return explicit_user_id.strip()
    header_uid = request.headers.get("X-User-Id", "").strip()
    return header_uid or "anonymous"


@app.get("/api/topics")
async def list_topics_endpoint(category: str | None = None) -> dict[str, Any]:
    """Return template topics grouped/filtered by category with `duration_min` (Brief §5.7)."""
    pipeline = get_script_pipeline()
    slug = None
    if category and category.strip():
        raw_cat = category.strip().lower()
        rev_map = {v.lower(): k for k, v in CATEGORY_SLUG_MAP.items()}
        slug = rev_map.get(raw_cat, raw_cat)
    topics = [t.to_dict() for t in pipeline.template_store.list_topics(category_slug=slug)]
    return {"topics": topics, "categories": CATEGORY_SLUG_MAP}


@app.post("/api/generate-script", status_code=202)
async def generate_script_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    topic: Annotated[str, Form(...)],
    category: Annotated[str, Form()] = "",
    duration_min: Annotated[int, Form()] = 5,
    greeting: Annotated[str, Form()] = "",
    raw_text: Annotated[str, Form()] = "",
    pdf: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    """Queue a background script generation job and return `202 {job_id, status}` (Brief §5.5)."""
    pipeline = get_script_pipeline()
    user_id = _resolve_user_id(request)
    pdf_path: str | None = None
    if pdf is not None and pdf.filename:
        suffix = Path(pdf.filename).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            shutil.copyfileobj(pdf.file, tmp_file)
            pdf_path = tmp_file.name

    req = ScriptGenerationRequest(
        topic=topic,
        category=category or None,
        duration_min=duration_min,
        pdf_path=pdf_path,
        raw_text=raw_text or None,
        greeting=greeting or None,
        user_id=user_id,
    )
    job = pipeline.create_job(user_id=user_id)
    background_tasks.add_task(pipeline.run_job, job.job_id, req, True)
    return {"job_id": job.job_id, "status": job.status}


@app.get("/api/generate-script/{job_id}")
async def get_generate_script_job_endpoint(job_id: str) -> JSONResponse:
    """Poll status, progress, and result of a script generation job (Brief §5.5)."""
    job = get_script_pipeline().get_job(job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error_code": "job_not_found", "message": f"Job '{job_id}' not found."},
        )
    return JSONResponse(status_code=200, content=job.to_dict())


@app.post("/api/scripts", status_code=201)
async def create_saved_script_endpoint(
    request: Request, payload: SaveScriptPayload
) -> dict[str, Any]:
    """Save a generated or user-written script after Stage 4 moderation (Brief §5.7, §5.8)."""
    user_id = _resolve_user_id(request)
    return get_script_pipeline().save_script(
        user_id=user_id,
        title=payload.title,
        script=payload.script,
        duration_min=payload.duration_min,
        source=payload.source,
    )


@app.get("/api/scripts")
async def list_saved_scripts_endpoint(request: Request) -> dict[str, Any]:
    """List saved scripts for the current user."""
    user_id = _resolve_user_id(request)
    return {"scripts": get_script_pipeline().list_scripts(user_id=user_id)}


@app.get("/api/scripts/{script_id}")
async def get_saved_script_endpoint(script_id: str, request: Request) -> JSONResponse:
    """Get a single saved script owned by the current user."""
    user_id = _resolve_user_id(request)
    item = get_script_pipeline().get_script(script_id=script_id, user_id=user_id)
    if item is None:
        return JSONResponse(
            status_code=404,
            content={"error_code": "script_not_found", "message": "Script not found."},
        )
    return JSONResponse(status_code=200, content=item)


@app.delete("/api/scripts/{script_id}")
async def delete_saved_script_endpoint(script_id: str, request: Request) -> JSONResponse:
    """Delete a saved script owned by the current user."""
    user_id = _resolve_user_id(request)
    deleted = get_script_pipeline().delete_script(script_id=script_id, user_id=user_id)
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={"error_code": "script_not_found", "message": "Script not found."},
        )
    return JSONResponse(status_code=200, content={"deleted": True, "id": script_id})
