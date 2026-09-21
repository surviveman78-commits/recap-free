import os
import json
import time
import uuid
import queue
import asyncio
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from app.config import settings_manager, DATA_DIR
from app.pipeline.orchestrator import PipelineOrchestrator, STAGES

JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


class JobQueueManager:
    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.event_queues: Dict[str, List[asyncio.Queue]] = {}
        self.job_queue: queue.Queue = queue.Queue()
        self.active_job_id: Optional[str] = None
        self.lock = threading.RLock()

        # Load existing jobs from disk into cache
        self._load_existing_jobs()

        # Start background worker thread
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _load_existing_jobs(self):
        """Scans disk for previous jobs to restore history on startup."""
        if not JOBS_DIR.exists():
            return
        for job_folder in JOBS_DIR.iterdir():
            if not job_folder.is_dir() or not job_folder.name.startswith("job_"):
                continue
            job_id = job_folder.name
            summary_file = job_folder / "job_summary.json"
            created_time = job_folder.stat().st_ctime
            
            if summary_file.exists():
                try:
                    with open(summary_file, "r", encoding="utf-8") as f:
                        summary_data = json.load(f)
                    self.jobs[job_id] = {
                        "job_id": job_id,
                        "status": "completed",
                        "stage": STAGES[7],
                        "progress": 100.0,
                        "created_at": created_time,
                        "summary": summary_data,
                        "video_url": f"/api/jobs/{job_id}/files/final_video.mp4",
                        "srt_url": f"/api/jobs/{job_id}/files/subtitles.srt"
                    }
                except Exception:
                    pass
            else:
                # Incomplete or interrupted job
                self.jobs[job_id] = {
                    "job_id": job_id,
                    "status": "failed",
                    "stage": "မအောင်မြင်ပါ",
                    "progress": 0.0,
                    "created_at": created_time,
                    "error": "စနစ်ပြန်လည်စတင်ချိန်တွင် ရပ်တန့်သွားခဲ့ပါသည်"
                }

    def broadcast_event(self, job_id: str, event: Dict[str, Any]):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]["latest_event"] = event
                self.jobs[job_id]["stage"] = event.get("stage")
                self.jobs[job_id]["progress"] = event.get("progress", 0.0)

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

    def _get_queue_position_unlocked(self, job_id: str) -> int:
        """Returns 1-based position in queue, or 0 if active/not queued (caller must hold lock or accept snapshot)."""
        if self.active_job_id == job_id:
            return 0
        items = list(self.job_queue.queue)
        for idx, item in enumerate(items):
            if item["job_id"] == job_id:
                return idx + 1
        return 0

    def get_queue_position(self, job_id: str) -> int:
        """Returns 1-based position in queue, or 0 if active/not queued."""
        with self.lock:
            return self._get_queue_position_unlocked(job_id)

    def submit_job(
        self,
        video_url: Optional[str] = None,
        uploaded_video_path: Optional[Path] = None,
        target_language: Optional[str] = None,
        enable_subtitles: bool = True,
        font_color: Optional[str] = None,
        font_size_px: Optional[int] = None,
        font_style: Optional[str] = None,
        subtitle_pos_x: Optional[float] = None,
        subtitle_pos_y: Optional[float] = None
    ) -> str:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        job_data = {
            "job_id": job_id,
            "job_dir": str(job_dir),
            "video_url": video_url,
            "uploaded_video_path": str(uploaded_video_path) if uploaded_video_path else None,
            "target_language": target_language or settings_manager.get("target_language", "my"),
            "enable_subtitles": enable_subtitles,
            "font_color": font_color or settings_manager.get("font_color", "#FFFFFF"),
            "font_size_px": font_size_px or int(settings_manager.get("font_size_px", 36)),
            "font_style": font_style or settings_manager.get("font_style", "Myanmar Text"),
            "subtitle_pos_x": subtitle_pos_x if subtitle_pos_x is not None else float(settings_manager.get("subtitle_pos_x", 50.0)),
            "subtitle_pos_y": subtitle_pos_y if subtitle_pos_y is not None else float(settings_manager.get("subtitle_pos_y", 82.0)),
            "created_at": time.time(),
            "status": "queued",
            "stage": "တန်းစီဇယားတွင် စောင့်ဆိုင်းနေပါသည်...",
            "progress": 0.0
        }

        with self.lock:
            self.jobs[job_id] = job_data
            self.event_queues[job_id] = []
            self.job_queue.put(job_data)
            queue_pos = self.job_queue.qsize()

        # Send initial queued notification
        self.broadcast_event(job_id, {
            "job_id": job_id,
            "stage": "တန်းစီဇယားတွင် စောင့်ဆိုင်းနေပါသည်...",
            "stage_index": 0,
            "total_stages": len(STAGES),
            "queue_position": queue_pos,
            "message": f"Queue တွင် စောင့်ဆိုင်းနေပါသည် (နံပါတ် #{queue_pos})...",
            "progress": 0.0
        })

        return job_id

    def _worker_loop(self):
        """Sequential single-job execution worker to prevent hardware/ffmpeg congestion."""
        while True:
            try:
                job_data = self.job_queue.get()
                job_id = job_data["job_id"]
                job_dir = Path(job_data["job_dir"])

                with self.lock:
                    self.active_job_id = job_id
                    self.jobs[job_id]["status"] = "running"
                    self.jobs[job_id]["stage"] = STAGES[0]

                # Update any other remaining queued jobs about their new positions
                with self.lock:
                    queued_items = list(self.job_queue.queue)
                for idx, q_item in enumerate(queued_items):
                    pos = idx + 1
                    self.broadcast_event(q_item["job_id"], {
                        "job_id": q_item["job_id"],
                        "stage": "တန်းစီဇယားတွင် စောင့်ဆိုင်းနေပါသည်...",
                        "stage_index": 0,
                        "total_stages": len(STAGES),
                        "queue_position": pos,
                        "message": f"Queue တွင် စောင့်ဆိုင်းနေပါသည် (နံပါတ် #{pos})...",
                        "progress": 0.0
                    })

                self._execute_pipeline(job_data, job_dir)

            except Exception as e:
                print(f"[QueueWorker] Unexpected error in worker loop: {e}")
            finally:
                with self.lock:
                    self.active_job_id = None
                self.job_queue.task_done()

    def _execute_pipeline(self, job_data: Dict[str, Any], job_dir: Path):
        job_id = job_data["job_id"]
        groq_key = settings_manager.get_groq_key()
        gemini_key = settings_manager.get_gemini_key()
        target_lang = job_data["target_language"]
        uploaded_path = Path(job_data["uploaded_video_path"]) if job_data.get("uploaded_video_path") else None

        orchestrator = PipelineOrchestrator(
            job_id=job_id,
            job_dir=job_dir,
            event_callback=lambda evt: self.broadcast_event(job_id, evt)
        )

        try:
            res = orchestrator.run(
                video_url=job_data.get("video_url"),
                uploaded_video_path=uploaded_path,
                groq_api_key=groq_key,
                gemini_api_key=gemini_key,
                voice_engine=settings_manager.get("voice_engine", "edge_tts"),
                edge_tts_voice=settings_manager.get("edge_tts_voice", "my-MM-NilarNeural"),
                voxcpm_voice_path=settings_manager.get("voxcpm_voice_path", ""),
                voxcpm_ref_text=settings_manager.get("voxcpm_reference_text", ""),
                gemini_mode=settings_manager.get("gemini_prompt_mode", "translate"),
                target_language=target_lang,
                font_color=job_data["font_color"],
                font_size_px=job_data["font_size_px"],
                font_style=job_data["font_style"],
                pos_x_pct=job_data["subtitle_pos_x"],
                pos_y_pct=job_data["subtitle_pos_y"],
                enable_subtitles=job_data["enable_subtitles"]
            )

            with self.lock:
                self.jobs[job_id]["status"] = "completed"
                self.jobs[job_id]["stage"] = STAGES[7]
                self.jobs[job_id]["progress"] = 100.0
                self.jobs[job_id]["summary"] = res
                self.jobs[job_id]["video_url"] = f"/api/jobs/{job_id}/files/final_video.mp4"
                self.jobs[job_id]["srt_url"] = f"/api/jobs/{job_id}/files/subtitles.srt"

            self.broadcast_event(job_id, {
                "job_id": job_id,
                "status": "completed",
                "stage": STAGES[7],
                "stage_index": len(STAGES),
                "message": "ဗီဒီယို ဖန်တီးခြင်း အောင်မြင်စွာ ပြီးဆုံးပါပြီ!",
                "progress": 100.0,
                "data": res
            })

        except Exception as e:
            with self.lock:
                self.jobs[job_id]["status"] = "failed"
                self.jobs[job_id]["stage"] = "မအောင်မြင်ပါ"
                self.jobs[job_id]["error"] = str(e)

            self.broadcast_event(job_id, {
                "job_id": job_id,
                "status": "failed",
                "stage": "မအောင်မြင်ပါ",
                "stage_index": 0,
                "message": f"Error: {str(e)}",
                "progress": 0.0,
                "data": {"error": str(e)}
            })

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            job = self.jobs.get(job_id)
            if job:
                # Add queue position if applicable
                q_pos = self._get_queue_position_unlocked(job_id)
                res = job.copy()
                res["queue_position"] = q_pos
                return res

        # Try disk if not in memory
        job_dir = JOBS_DIR / job_id
        if job_dir.exists():
            summary_file = job_dir / "job_summary.json"
            if summary_file.exists():
                try:
                    with open(summary_file, "r", encoding="utf-8") as f:
                        summary_data = json.load(f)
                    return {
                        "job_id": job_id,
                        "status": "completed",
                        "stage": STAGES[7],
                        "progress": 100.0,
                        "created_at": job_dir.stat().st_ctime,
                        "summary": summary_data,
                        "video_url": f"/api/jobs/{job_id}/files/final_video.mp4",
                        "srt_url": f"/api/jobs/{job_id}/files/subtitles.srt"
                    }
                except Exception:
                    pass
        return None

    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns sorted list of all jobs for History view."""
        history = []
        with self.lock:
            all_cached_ids = set(self.jobs.keys())

        # Also inspect directories in case disk has more
        for f in JOBS_DIR.iterdir():
            if f.is_dir() and f.name.startswith("job_"):
                all_cached_ids.add(f.name)

        for j_id in all_cached_ids:
            j_info = self.get_job(j_id)
            if not j_info:
                continue

            summary = j_info.get("summary", {})
            created = j_info.get("created_at", 0)
            
            item = {
                "job_id": j_id,
                "status": j_info.get("status", "unknown"),
                "stage": j_info.get("stage", ""),
                "created_at": created,
                "created_at_formatted": time.strftime("%Y-%m-%d %H:%M", time.localtime(created)),
                "duration": summary.get("final_duration_formatted", "--:--"),
                "processed_text_snippet": (summary.get("processed_text") or "")[:120],
                "video_url": f"/api/jobs/{j_id}/files/final_video.mp4" if (JOBS_DIR / j_id / "final_video.mp4").exists() else None,
                "srt_url": f"/api/jobs/{j_id}/files/subtitles.srt" if (JOBS_DIR / j_id / "subtitles.srt").exists() else None,
                "has_video": (JOBS_DIR / j_id / "final_video.mp4").exists(),
                "has_srt": (JOBS_DIR / j_id / "subtitles.srt").exists()
            }
            history.append(item)

        history.sort(key=lambda x: x["created_at"], reverse=True)
        return history[:limit]


job_queue_manager = JobQueueManager()
