import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from app.config import DATA_DIR
from app.pipeline.tts_engine import TTSEngine
from app.pipeline.burmese_text import prepare_burmese_tts_text

VOICE_CLONE_DIR = DATA_DIR / "voice_clone_jobs"
VOICE_CLONE_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = VOICE_CLONE_DIR / "history.json"
_lock = threading.Lock()
_voxcpm_slot = threading.Semaphore(1)
_jobs: Dict[str, Dict[str, Any]] = {}


def _load_history() -> None:
    if not HISTORY_FILE.exists():
        return
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("job_id"):
                    _jobs[item["job_id"]] = item
    except (OSError, ValueError, TypeError):
        return


_load_history()


def _save_history() -> None:
    HISTORY_FILE.write_text(
        json.dumps(list(_jobs.values()), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _split_script(text: str, max_chars: int = 220) -> List[Dict[str, Any]]:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[။!?])\s*|(?<=[.!?])(?=\s|$)", cleaned) if part.strip()]
    chunks: List[str] = []
    current = ""
    for sentence in sentences or [cleaned]:
        if len(sentence) <= max_chars and not current:
            current = sentence
        elif len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            while len(sentence) > max_chars:
                chunks.append(sentence[:max_chars].strip())
                sentence = sentence[max_chars:].strip()
            current = sentence
    if current:
        chunks.append(current)
    return [{"id": index, "text": chunk} for index, chunk in enumerate(chunks)]


def list_jobs() -> List[Dict[str, Any]]:
    with _lock:
        return sorted((item.copy() for item in _jobs.values()), key=lambda item: item.get("created_at", 0), reverse=True)


def get_job(job_id: str) -> Dict[str, Any] | None:
    with _lock:
        item = _jobs.get(job_id)
        return item.copy() if item else None


def create_job(reference_path: str, reference_name: str, reference_text: str, script: str) -> str:
    job_id = f"vc_{uuid.uuid4().hex[:10]}"
    job_dir = VOICE_CLONE_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    item = {
        "job_id": job_id,
        "status": "queued",
        "stage": "Queue တွင် စောင့်ဆိုင်းနေပါသည်...",
        "progress": 0,
        "reference_name": reference_name,
        "script_preview": script[:140],
        "script_chars": len(script),
        "created_at": time.time(),
        "output_path": str(job_dir / "voice_clone.wav"),
    }
    with _lock:
        _jobs[job_id] = item
        _save_history()
    thread = threading.Thread(target=_run_job, args=(job_id, reference_path, reference_text, script), daemon=True)
    thread.start()
    return job_id


def _update(job_id: str, **changes: Any) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(changes)
            _save_history()


def _run_job(job_id: str, reference_path: str, reference_text: str, script: str) -> None:
    try:
        _update(job_id, status="queued", stage="VoxCPM2 slot လွတ်ရန် စောင့်နေပါသည်...", progress=1)
        with _voxcpm_slot:
            _update(job_id, status="running", stage="VoxCPM2 model load / voice clone စတင်နေပါသည်...", progress=5)
            segments = _split_script(script)
            if not segments:
                raise ValueError("ပြောစေချင်တဲ့စာသား မရှိပါ။")
            for segment in segments:
                segment["display_text"] = segment["text"]
                segment["tts_text"] = prepare_burmese_tts_text(segment["text"])
            output_dir = VOICE_CLONE_DIR / job_id
            with _lock:
                reference_text = reference_text.strip()
            # The engine's VoxCPM path uses the selected reference audio and exact text.
            engine = TTSEngine(progress_callback=lambda stage, progress: _update(job_id, stage=stage, progress=round(progress, 1)))
            audio_path, _ = engine.generate(
                segments=segments,
                output_dir=output_dir,
                engine="voxcpm2",
                voice="",
                voxcpm_ref_path=reference_path,
                voxcpm_ref_text=reference_text,
                voxcpm_device=None,
            )
            final_path = output_dir / "voice_clone.wav"
            Path(audio_path).replace(final_path)
            _update(job_id, status="completed", stage="ပြီးပါပြီ ✓", progress=100, output_path=str(final_path))
    except Exception as exc:
        _update(job_id, status="failed", stage="မအောင်မြင်ပါ", progress=0, error=str(exc))
