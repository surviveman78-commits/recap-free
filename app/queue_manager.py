import asyncio
import json
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import DATA_DIR, settings_manager
from app.pipeline.orchestrator import PipelineOrchestrator, STAGES

JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

EDGE_MAX_CONCURRENT = 3
VOXCPM_MAX_CONCURRENT = 1


class JobQueueManager:
    """Engine-aware scheduler with isolated job folders and bounded concurrency."""

    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.event_queues: Dict[str, List[asyncio.Queue]] = {}
        self.pending_jobs: List[Dict[str, Any]] = []
        self.active_jobs: Dict[str, Dict[str, Any]] = {}
        self.active_job_id: Optional[str] = None
        self.active_counts = {"edge_tts": 0, "voxcpm2": 0}
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.executor = ThreadPoolExecutor(max_workers=EDGE_MAX_CONCURRENT + VOXCPM_MAX_CONCURRENT)
        self._load_existing_jobs()
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()

    @staticmethod
    def _engine(value: Optional[str]) -> str:
        return "voxcpm2" if str(value or "").lower() == "voxcpm2" else "edge_tts"

    def _load_existing_jobs(self):
        if not JOBS_DIR.exists():
            return
        for folder in JOBS_DIR.iterdir():
            if not folder.is_dir() or not folder.name.startswith("job_"):
                continue
            summary_file = folder / "job_summary.json"
            created = folder.stat().st_ctime
            if summary_file.exists():
                try:
                    summary = json.loads(summary_file.read_text(encoding="utf-8"))
                    self.jobs[folder.name] = {
                        "job_id": folder.name, "status": "completed", "stage": STAGES[7],
                        "progress": 100.0, "created_at": created, "summary": summary,
                        "video_url": f"/api/jobs/{folder.name}/files/final_video.mp4",
                        "srt_url": f"/api/jobs/{folder.name}/files/subtitles.srt",
                    }
                except Exception:
                    pass
            elif folder.name not in self.jobs:
                self.jobs[folder.name] = {
                    "job_id": folder.name, "status": "failed", "stage": "မအောင်မြင်ပါ",
                    "progress": 0.0, "created_at": created,
                    "error": "စနစ်ပြန်လည်စတင်ချိန်တွင် ရပ်တန့်သွားခဲ့ပါသည်",
                }

    def broadcast_event(self, job_id: str, event: Dict[str, Any]):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]["latest_event"] = event
                self.jobs[job_id]["stage"] = event.get("stage", self.jobs[job_id].get("stage"))
                self.jobs[job_id]["progress"] = event.get("progress", self.jobs[job_id].get("progress", 0.0))
                if event.get("message"):
                    self.jobs[job_id]["message"] = event["message"]
            queues = list(self.event_queues.get(job_id, []))
        for q in queues:
            try:
                loop = getattr(q, "_loop", None)
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(q.put_nowait, event)
                else:
                    q.put_nowait(event)
            except Exception:
                pass

    def _capacity(self, engine: str) -> int:
        return VOXCPM_MAX_CONCURRENT if engine == "voxcpm2" else EDGE_MAX_CONCURRENT

    def _can_start(self, engine: str) -> bool:
        return self.active_counts.get(engine, 0) < self._capacity(engine)

    def _get_queue_position_unlocked(self, job_id: str) -> int:
        for index, item in enumerate(self.pending_jobs):
            if item["job_id"] == job_id:
                return index + 1
        return 0

    def get_queue_position(self, job_id: str) -> int:
        with self.lock:
            return self._get_queue_position_unlocked(job_id)

    def submit_job(self, video_url=None, uploaded_video_path=None, target_language=None,
                   enable_subtitles=True, font_color=None, font_size_px=None,
                   font_style=None, subtitle_pos_x=None, subtitle_pos_y=None,
                   output_resolution=None) -> str:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        engine = self._engine(settings_manager.get("voice_engine", "edge_tts"))
        job_data = {
            "job_id": job_id, "job_dir": str(job_dir), "video_url": video_url,
            "uploaded_video_path": str(uploaded_video_path) if uploaded_video_path else None,
            "target_language": target_language or settings_manager.get("target_language", "my"),
            "enable_subtitles": enable_subtitles,
            "font_color": font_color or settings_manager.get("font_color", "#FFFFFF"),
            "font_size_px": font_size_px or int(settings_manager.get("font_size_px", 36)),
            "font_style": font_style or settings_manager.get("font_style", "Noto Sans Myanmar"),
            "ai_mode": "local" if settings_manager.get("ai_mode", "local") == "local" else "cloud",
            "subtitle_pos_x": subtitle_pos_x if subtitle_pos_x is not None else float(settings_manager.get("subtitle_pos_x", 50.0)),
            "subtitle_pos_y": subtitle_pos_y if subtitle_pos_y is not None else float(settings_manager.get("subtitle_pos_y", 82.0)),
            "auto_blur_subtitles": bool(settings_manager.get("auto_blur_subtitles", False)),
            "auto_blur_padding_pct": float(settings_manager.get("auto_blur_padding_pct", 1.5)),
            "voxcpm_voice_path": str(settings_manager.get("voxcpm_voice_path", "") or ""),
            "voxcpm_voice_name": str(settings_manager.get("voxcpm_voice_name", "") or ""),
            "voxcpm_reference_text": str(settings_manager.get("voxcpm_reference_text", "") or ""),
            "output_resolution": str(output_resolution or settings_manager.get("output_resolution", "1080p") or "1080p").lower(),
            "voice_engine": engine, "created_at": time.time(), "status": "queued",
            "stage": "တန်းစီဇယားတွင် စောင့်ဆိုင်းနေပါသည်...", "progress": 0.0,
        }
        with self.condition:
            self.jobs[job_id] = job_data
            self.event_queues[job_id] = []
            self.pending_jobs.append(job_data)
            position = self._get_queue_position_unlocked(job_id)
            self.condition.notify_all()
        self.broadcast_event(job_id, {
            "job_id": job_id, "stage": job_data["stage"], "stage_index": 0,
            "total_stages": len(STAGES), "queue_position": position,
            "message": f"{engine} slot ရရှိရန် စောင့်ဆိုင်းနေပါသည် (နံပါတ် #{position})...",
            "progress": 0.0, "voice_engine": engine,
        })
        return job_id

    def _scheduler_loop(self):
        while True:
            with self.condition:
                while not self.pending_jobs:
                    self.condition.wait(timeout=1.0)
                selected = None
                for item in self.pending_jobs:
                    if self._can_start(item["voice_engine"]):
                        selected = item
                        break
                if selected is None:
                    self.condition.wait(timeout=0.5)
                    continue
                self.pending_jobs.remove(selected)
                job_id = selected["job_id"]
                engine = selected["voice_engine"]
                self.active_jobs[job_id] = selected
                self.active_counts[engine] += 1
                self.active_job_id = next(iter(self.active_jobs), None)
                self.jobs[job_id]["status"] = "running"
                self.jobs[job_id]["slot"] = f"{engine}:{self.active_counts[engine]}/{self._capacity(engine)}"
                if engine == "voxcpm2":
                    selected["voxcpm_device"] = f"cuda:{self.active_counts[engine] - 1}"
                    self.jobs[job_id]["voxcpm_device"] = selected["voxcpm_device"]
            self.executor.submit(self._run_one, selected)

    def _run_one(self, job_data: Dict[str, Any]):
        job_id = job_data["job_id"]
        try:
            self._execute_pipeline(job_data, Path(job_data["job_dir"]))
        except Exception as exc:
            self._mark_failed(job_id, exc)
        finally:
            with self.condition:
                engine = job_data["voice_engine"]
                self.active_counts[engine] = max(0, self.active_counts[engine] - 1)
                self.active_jobs.pop(job_id, None)
                self.active_job_id = next(iter(self.active_jobs), None)
                self.condition.notify_all()

    def _mark_failed(self, job_id: str, exc: Exception):
        error = str(exc)
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(status="failed", stage="မအောင်မြင်ပါ", error=error)
        self.broadcast_event(job_id, {
            "job_id": job_id, "status": "failed", "stage": "မအောင်မြင်ပါ", "stage_index": 0,
            "message": f"Error: {error}", "progress": 0.0, "data": {"error": error},
        })

    def _execute_pipeline(self, job_data: Dict[str, Any], job_dir: Path):
        job_id = job_data["job_id"]
        uploaded_path = Path(job_data["uploaded_video_path"]) if job_data.get("uploaded_video_path") else None
        orchestrator = PipelineOrchestrator(
            job_id=job_id, job_dir=job_dir,
            event_callback=lambda evt: self.broadcast_event(job_id, evt),
        )
        result = orchestrator.run(
            video_url=job_data.get("video_url"), uploaded_video_path=uploaded_path,
            groq_api_key=settings_manager.get_groq_key(), gemini_api_key=settings_manager.get_gemini_key(),
            ai_mode=job_data.get("ai_mode", "local"),
            voice_engine=job_data["voice_engine"],
            edge_tts_voice=settings_manager.get("edge_tts_voice", "my-MM-NilarNeural"),
            voxcpm_voice_path=job_data.get("voxcpm_voice_path", ""),
            voxcpm_ref_text=job_data.get("voxcpm_reference_text", ""),
            voxcpm_device=job_data.get("voxcpm_device"),
            gemini_mode=settings_manager.get("gemini_prompt_mode", "translate"),
            target_language=job_data["target_language"], font_color=job_data["font_color"],
            font_size_px=job_data["font_size_px"], font_style=job_data["font_style"],
            pos_x_pct=job_data["subtitle_pos_x"], pos_y_pct=job_data["subtitle_pos_y"],
            enable_subtitles=job_data["enable_subtitles"],
            auto_blur_subtitles=job_data.get("auto_blur_subtitles", False),
            auto_blur_padding_pct=job_data.get("auto_blur_padding_pct", 1.5),
            output_resolution=job_data.get("output_resolution", "1080p"),
        )
        with self.lock:
            self.jobs[job_id].update(
                status="completed", stage=STAGES[7], progress=100.0, summary=result,
                video_url=f"/api/jobs/{job_id}/files/final_video.mp4",
                srt_url=f"/api/jobs/{job_id}/files/subtitles.srt",
            )
        self.broadcast_event(job_id, {
            "job_id": job_id, "status": "completed", "stage": STAGES[7],
            "stage_index": len(STAGES), "message": "ဗီဒီယို ဖန်တီးခြင်း အောင်မြင်စွာ ပြီးဆုံးပါပြီ!",
            "progress": 100.0, "data": result,
        })

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            job = self.jobs.get(job_id)
            if job:
                result = job.copy()
                result["queue_position"] = self._get_queue_position_unlocked(job_id)
                result["running_count"] = len(self.active_jobs)
                result["edge_running"] = self.active_counts["edge_tts"]
                result["voxcpm_running"] = self.active_counts["voxcpm2"]
                return result
        return None

    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        items = []
        with self.lock:
            ids = list(self.jobs.keys())
        for job_id in ids:
            job = self.get_job(job_id)
            if not job:
                continue
            folder = JOBS_DIR / job_id
            summary = job.get("summary", {}) or {}
            items.append({
                "job_id": job_id, "status": job.get("status", "unknown"),
                "stage": job.get("stage", ""), "created_at": job.get("created_at", 0),
                "created_at_formatted": time.strftime("%Y-%m-%d %H:%M", time.localtime(job.get("created_at", 0))),
                "duration": summary.get("final_duration_formatted", "--:--"),
                "processed_text_snippet": (summary.get("processed_text") or "")[:120],
                "video_url": f"/api/jobs/{job_id}/files/final_video.mp4" if (folder / "final_video.mp4").exists() else None,
                "srt_url": f"/api/jobs/{job_id}/files/subtitles.srt" if (folder / "subtitles.srt").exists() else None,
                "has_video": (folder / "final_video.mp4").exists(), "has_srt": (folder / "subtitles.srt").exists(),
                "voice_engine": job.get("voice_engine", "edge_tts"),
            })
        items.sort(key=lambda x: x["created_at"], reverse=True)
        return items[:limit]


job_queue_manager = JobQueueManager()
