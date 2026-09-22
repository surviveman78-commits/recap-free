import os
import sys
import uuid
import json
import asyncio
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings_manager, DATA_DIR, CUSTOM_VOICES_DIR, CUSTOM_FONTS_DIR
from app.pipeline.orchestrator import PipelineOrchestrator, STAGES
from app.pipeline.tts_engine import TTSEngine
from app.pipeline.gpu_utils import get_active_encoder_name, check_gpu_nvenc_available, get_encoder_hardware_desc
from app.queue_manager import job_queue_manager

app = FastAPI(
    title="AI Video Recap Studio",
    description="Video Recap & Narration Pipeline",
    version="2.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

jobs_state: Dict[str, Dict[str, Any]] = {}
job_event_queues: Dict[str, List[asyncio.Queue]] = {}


class SettingsUpdateRequest(BaseModel):
    ai_mode: Optional[str] = None
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    target_language: Optional[str] = None
    gemini_prompt_mode: Optional[str] = None
    voice_engine: Optional[str] = None
    edge_tts_language: Optional[str] = None
    edge_tts_voice: Optional[str] = None
    voxcpm_voice_path: Optional[str] = None
    voxcpm_voice_name: Optional[str] = None
    voxcpm_reference_text: Optional[str] = None
    font_color: Optional[str] = None
    font_size_px: Optional[int] = None
    font_style: Optional[str] = None
    subtitle_pos_x: Optional[float] = None
    subtitle_pos_y: Optional[float] = None


class JobCreateRequest(BaseModel):
    video_url: Optional[str] = None
    target_language: Optional[str] = None
    subtitle_pos_x: Optional[float] = None
    subtitle_pos_y: Optional[float] = None
    font_style: Optional[str] = None
    font_size_px: Optional[int] = None
    font_color: Optional[str] = None
    subtitle_enabled: Optional[bool] = True


@app.get("/api/settings")
async def get_settings():
    return settings_manager.get_all(mask=True)


@app.post("/api/settings")
async def update_settings(payload: SettingsUpdateRequest):
    cleaned = payload.model_dump(exclude_unset=True)
    saved = settings_manager.save(cleaned)
    return {
        "status": "success",
        "message": "Settings saved securely.",
        "settings": saved
    }


@app.get("/api/fonts")
async def get_fonts():
    """Returns custom uploaded fonts and system fonts with Myanmar Text prioritized."""
    fonts_list = ["Noto Sans Myanmar", "Padauk"]

    # 1. Custom uploaded fonts
    if CUSTOM_FONTS_DIR.exists():
        for f in sorted(CUSTOM_FONTS_DIR.iterdir()):
            if f.suffix.lower() in ('.ttf', '.otf'):
                # Font family name or filename stem
                if f.stem not in fonts_list:
                    fonts_list.append(f.stem)

    # 2. System fonts
    preferred = [
        "Noto Sans Myanmar", "Padauk", "Arial", "Segoe UI", "Tahoma", "Calibri",
        "Verdana", "Impact", "Trebuchet MS", "Times New Roman",
        "Georgia", "Consolas", "Comic Sans MS"
    ]
    try:
        import matplotlib.font_manager as fm
        installed = set(f.name for f in fm.fontManager.ttflist)
        for p in preferred:
            if p in installed and p not in fonts_list:
                fonts_list.append(p)
        others = sorted([f for f in installed if f not in set(fonts_list) and not f.startswith("@")])
        fonts_list.extend(others[:35])
    except Exception:
        for p in preferred:
            if p not in fonts_list:
                fonts_list.append(p)

    return {"fonts": fonts_list}


@app.post("/api/fonts/upload")
async def upload_custom_font(file: UploadFile = File(...)):
    """Allow user to upload any TTF/OTF font (e.g. Pyidaungsu, Masterpiece, etc.)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ('.ttf', '.otf'):
        raise HTTPException(status_code=400, detail="Only .ttf and .otf font files are supported.")

    safe_filename = Path(file.filename).name.replace(" ", "_")
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    dest = CUSTOM_FONTS_DIR / safe_filename
    with open(dest, "wb") as f:
        f.write(await file.read())

    # Set as active font
    font_name = Path(safe_filename).stem
    settings_manager.save({
        "font_style": font_name,
        "custom_font_name": file.filename,
        "custom_font_path": str(dest)
    })

    return {
        "status": "success",
        "font_name": font_name,
        "filename": file.filename,
        "path": str(dest)
    }


@app.get("/api/languages")
async def get_target_languages():
    return {
        "languages": [
            {"code": "my", "name": "Burmese (မြန်မာဘာသာ)", "tts_locale": "my-MM"},
            {"code": "en", "name": "English", "tts_locale": "en-US"},
            {"code": "th", "name": "Thai (ထိုင်း)", "tts_locale": "th-TH"},
            {"code": "ja", "name": "Japanese (ဂျပန်)", "tts_locale": "ja-JP"},
            {"code": "ko", "name": "Korean (ကိုရီးယား)", "tts_locale": "ko-KR"},
            {"code": "zh", "name": "Chinese (တရုတ်)", "tts_locale": "zh-CN"},
            {"code": "es", "name": "Spanish (စပိန်)", "tts_locale": "es-ES"},
            {"code": "fr", "name": "French (ပြင်သစ်)", "tts_locale": "fr-FR"},
            {"code": "de", "name": "German (ဂျာမန်)", "tts_locale": "de-DE"},
            {"code": "it", "name": "Italian (အီတလီ)", "tts_locale": "it-IT"},
            {"code": "ru", "name": "Russian (ရုရှား)", "tts_locale": "ru-RU"},
            {"code": "vi", "name": "Vietnamese (ဗီယက်နမ်)", "tts_locale": "vi-VN"}
        ],
        "current_target": settings_manager.get("target_language", "my"),
        "current_mode": settings_manager.get("gemini_prompt_mode", "translate")
    }


@app.get("/api/voices")
async def list_voices():
    edge_catalog = await TTSEngine.get_edge_catalog()
    voxcpm_voices = TTSEngine.get_voxcpm_voices()
    return {
        "edge_languages": edge_catalog["languages"],
        "edge_voices_by_language": edge_catalog["voices_by_language"],
        "voxcpm_voices": voxcpm_voices,
        "current_engine": settings_manager.get("voice_engine", "edge_tts"),
        "current_edge_language": settings_manager.get("edge_tts_language", "my-MM"),
        "current_edge_voice": settings_manager.get("edge_tts_voice", "my-MM-NilarNeural"),
        "current_voxcpm_voice_name": settings_manager.get("voxcpm_voice_name", "reference_speaker.wav"),
        "current_voxcpm_voice_path": settings_manager.get("voxcpm_voice_path", ""),
        "current_voxcpm_ref_text": settings_manager.get("voxcpm_reference_text", "")
    }


@app.post("/api/voices/upload-reference")
async def upload_reference_audio(
    file: UploadFile = File(...),
    reference_text: Optional[str] = Form(None)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required.")

    ext = Path(file.filename).suffix.lower()
    # Browser and Kaggle uploads commonly use AAC/Opus/WebM containers.
    allowed = ('.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus', '.aac', '.webm')
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format '{ext or '(none)'}'. Allowed: WAV, MP3, M4A, FLAC, OGG, OPUS, AAC, WEBM.")

    safe_name = f"ref_{uuid.uuid4().hex[:6]}_{Path(file.filename).name.replace(' ', '_')}"
    dest = CUSTOM_VOICES_DIR / safe_name
    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="The selected audio file is empty.")
        if len(contents) > 200 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Reference audio is too large. Maximum size is 200 MB.")
        CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(contents)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not save reference audio: {exc}") from exc

    save_dict = {
        "voxcpm_voice_name": file.filename,
        "voxcpm_voice_path": str(dest)
    }
    if reference_text is not None:
        save_dict["voxcpm_reference_text"] = reference_text.strip()

    settings_manager.save(save_dict)

    return {
        "status": "success",
        "filename": file.filename,
        "path": str(dest),
        "reference_text": settings_manager.get("voxcpm_reference_text", "")
    }


@app.get("/api/gpu")
async def get_gpu_status():
    """Returns GPU hardware acceleration status and active video encoder."""
    has_gpu = check_gpu_nvenc_available()
    return {
        "gpu_accelerated": has_gpu,
        "encoder": get_active_encoder_name(),
        "hardware": get_encoder_hardware_desc()
    }


@app.get("/api/queue")
async def get_queue_info():
    """Returns concurrent active jobs, engine slots, and pending jobs."""
    with job_queue_manager.lock:
        active_ids = list(job_queue_manager.active_jobs.keys())
        queued_ids = [item["job_id"] for item in job_queue_manager.pending_jobs]
    return {
        "active_job_id": active_ids[0] if active_ids else None,
        "active_job_ids": active_ids,
        "running_count": len(active_ids),
        "queued_count": len(queued_ids),
        "queued_job_ids": queued_ids,
        "edge_running": job_queue_manager.active_counts["edge_tts"],
        "edge_limit": 5,
        "voxcpm_running": job_queue_manager.active_counts["voxcpm2"],
        "voxcpm_limit": 2,
    }


@app.get("/api/jobs")
async def list_jobs():
    """Return all jobs (active + queued + history) sorted newest first."""
    return {"jobs": job_queue_manager.list_jobs()}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Return current state of a single job."""
    job = job_queue_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.post("/api/jobs")
async def create_job(payload: JobCreateRequest):
    ai_mode = settings_manager.get("ai_mode", "local")
    if ai_mode != "local":
        if not settings_manager.get_groq_key():
            raise HTTPException(status_code=400, detail="Groq API Key ထည့်သွင်းပေးရန် လိုအပ်ပါသည်။ (Settings တွင် ထည့်ပါ)")
        if not settings_manager.get_gemini_key():
            raise HTTPException(status_code=400, detail="Gemini API Key ထည့်သွင်းပေးရန် လိုအပ်ပါသည်။ (Settings တွင် ထည့်ပါ)")

    if not payload.video_url:
        raise HTTPException(status_code=400, detail="Video Link ထည့်သွင်းပေးပါ။")

    updates = {}
    if payload.target_language:
        updates["target_language"] = payload.target_language
    if payload.subtitle_pos_x is not None:
        updates["subtitle_pos_x"] = payload.subtitle_pos_x
    if payload.subtitle_pos_y is not None:
        updates["subtitle_pos_y"] = payload.subtitle_pos_y
    if payload.font_style:
        updates["font_style"] = payload.font_style
    if payload.font_size_px:
        updates["font_size_px"] = payload.font_size_px
    if payload.font_color:
        updates["font_color"] = payload.font_color
    if updates:
        settings_manager.save(updates)

    subtitle_enabled = payload.subtitle_enabled if payload.subtitle_enabled is not None else True

    job_id = job_queue_manager.submit_job(
        video_url=payload.video_url,
        uploaded_video_path=None,
        target_language=payload.target_language,
        enable_subtitles=subtitle_enabled,
        font_color=payload.font_color,
        font_size_px=payload.font_size_px,
        font_style=payload.font_style,
        subtitle_pos_x=payload.subtitle_pos_x,
        subtitle_pos_y=payload.subtitle_pos_y
    )

    q_pos = job_queue_manager.get_queue_position(job_id)
    is_running_now = job_queue_manager.active_job_id == job_id

    return {
        "status": "success",
        "job_id": job_id,
        "queue_position": q_pos,
        "is_active": is_running_now
    }


@app.post("/api/jobs/upload")
async def create_job_upload(
    file: UploadFile = File(...),
    target_language: Optional[str] = Form(None),
    subtitle_pos_x: Optional[float] = Form(None),
    subtitle_pos_y: Optional[float] = Form(None),
    font_style: Optional[str] = Form(None),
    font_size_px: Optional[int] = Form(None),
    font_color: Optional[str] = Form(None),
    subtitle_enabled: Optional[str] = Form(None)
):
    ai_mode = settings_manager.get("ai_mode", "local")
    if ai_mode != "local":
        if not settings_manager.get_groq_key():
            raise HTTPException(status_code=400, detail="Groq API Key ထည့်သွင်းပေးရန် လိုအပ်ပါသည်။ (Settings တွင် ထည့်ပါ)")
        if not settings_manager.get_gemini_key():
            raise HTTPException(status_code=400, detail="Gemini API Key ထည့်သွင်းပေးရန် လိုအပ်ပါသည်။ (Settings တွင် ထည့်ပါ)")

    updates = {}
    if target_language:
        updates["target_language"] = target_language
    if subtitle_pos_x is not None:
        updates["subtitle_pos_x"] = subtitle_pos_x
    if subtitle_pos_y is not None:
        updates["subtitle_pos_y"] = subtitle_pos_y
    if font_style:
        updates["font_style"] = font_style
    if font_size_px:
        updates["font_size_px"] = font_size_px
    if font_color:
        updates["font_color"] = font_color
    if updates:
        settings_manager.save(updates)

    sub_enabled = True
    if subtitle_enabled is not None:
        sub_enabled = subtitle_enabled.lower() not in ("false", "0", "no")

    # Stash uploaded file in dedicated uploads folder
    upload_dir = DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = Path(file.filename).name.replace(" ", "_")
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    temp_dest = upload_dir / f"up_{uuid.uuid4().hex[:6]}_{safe_filename}"
    with open(temp_dest, "wb") as f:
        f.write(await file.read())

    job_id = job_queue_manager.submit_job(
        video_url=None,
        uploaded_video_path=temp_dest,
        target_language=target_language,
        enable_subtitles=sub_enabled,
        font_color=font_color,
        font_size_px=font_size_px,
        font_style=font_style,
        subtitle_pos_x=subtitle_pos_x,
        subtitle_pos_y=subtitle_pos_y
    )

    q_pos = job_queue_manager.get_queue_position(job_id)
    is_running_now = job_queue_manager.active_job_id == job_id

    return {
        "status": "success",
        "job_id": job_id,
        "queue_position": q_pos,
        "is_active": is_running_now
    }


@app.get("/api/jobs/{job_id}/stream")
async def stream_job_events(job_id: str):
    job = job_queue_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    q: asyncio.Queue = asyncio.Queue()
    with job_queue_manager.lock:
        if job_id not in job_queue_manager.event_queues:
            job_queue_manager.event_queues[job_id] = []
        job_queue_manager.event_queues[job_id].append(q)

    async def event_generator():
        try:
            latest = job.get("latest_event")
            if latest:
                yield f"data: {json.dumps(latest)}\n\n"
                if latest.get("stage") in (STAGES[7], "မအောင်မြင်ပါ") or latest.get("status") in ("completed", "failed"):
                    return
            else:
                q_pos = job_queue_manager.get_queue_position(job_id)
                init_event = {
                    "job_id": job_id,
                    "stage": job.get("stage", "တန်းစီဇယားတွင် စောင့်ဆိုင်းနေပါသည်..."),
                    "stage_index": 0 if q_pos > 0 else 1,
                    "total_stages": len(STAGES),
                    "queue_position": q_pos,
                    "message": f"Queue တွင် စောင့်ဆိုင်းနေပါသည် (နံပါတ် #{q_pos})..." if q_pos > 0 else "စတင်ပြင်ဆင်နေပါသည်...",
                    "progress": job.get("progress", 0.0),
                    "status": job.get("status", "queued")
                }
                yield f"data: {json.dumps(init_event)}\n\n"
                if job.get("status") in ("completed", "failed"):
                    return

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("stage") in (STAGES[7], "မအောင်မြင်ပါ") or event.get("status") in ("completed", "failed"):
                        break
                except asyncio.TimeoutError:
                    # Padding forces Cloudflare/browser proxies to flush the stream.
                    yield f": {('ping ' * 500)}\n\n"
        finally:
            with job_queue_manager.lock:
                if job_id in job_queue_manager.event_queues and q in job_queue_manager.event_queues[job_id]:
                    job_queue_manager.event_queues[job_id].remove(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



@app.get("/api/jobs/{job_id}/files/{filename}")
async def get_job_file(job_id: str, filename: str):
    job_dir = JOBS_DIR / job_id
    file_path = (job_dir / filename).resolve()
    if job_dir.resolve() not in file_path.parents:
        raise HTTPException(status_code=400, detail="Invalid file path.")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} not found.")

    media_type = "application/octet-stream"
    if filename.endswith(".mp4"):
        media_type = "video/mp4"
    elif filename.endswith(".wav"):
        media_type = "audio/wav"
    elif filename.endswith(".json"):
        media_type = "application/json"
    elif filename.endswith(".txt") or filename.endswith(".srt") or filename.endswith(".ass"):
        media_type = "text/plain; charset=utf-8"

    return FileResponse(file_path, media_type=media_type)


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
