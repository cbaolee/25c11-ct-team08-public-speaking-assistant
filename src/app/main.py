import json
import shutil
import tempfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.audio_processing.contracts import (
    AudioRejected, 
    InsufficientAudio, 
    BaselineProfile,
    VadParams 
)
from src.audio_processing.pipeline import evaluate_session, analyze_baseline

WEB_DIR = Path(__file__).resolve().parents[1] / "web" 

app = FastAPI()
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")


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


@app.post("/api/evaluate")
async def evaluate_endpoint(
    audio: UploadFile = File(...),
    script: str = Form(...),
    baseline_profile: str = Form("")
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
            profile_data = json.loads(baseline_profile)
            baseline = BaselineProfile(**profile_data)
        except json.JSONDecodeError:
            pass
            
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
        
        return result


@app.post("/api/baseline")
async def baseline_endpoint(
    audio: UploadFile = File(...)
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
            profile = analyze_baseline(
                audio_path=audio_path,
                vad_params=vad_params
            )
            return profile
        except InsufficientAudio:
            # Xử lý trả về HTTP 200 kèm status khi file baseline không đủ chất lượng (tiếng nói < 30%)[cite: 1]
            return {"status": "insufficient_audio"}