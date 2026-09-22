import os
import json
import time
import shutil
import traceback
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from app.pipeline.downloader import VideoDownloader
from app.pipeline.audio_extractor import AudioExtractor
from app.pipeline.groq_transcriber import GroqTranscriber
from app.pipeline.gemini_rewriter import GeminiRewriter
from app.pipeline.tts_engine import TTSEngine
from app.pipeline.audio_mixer import AudioMixer
from app.pipeline.subtitle_burner import SubtitleBurner

# Exact Burmese stage labels
STAGES = [
    "ဗီဒီယို ဒေါင်းလုဒ်လုပ်နေပါတယ်...",
    "အသံဖိုင် ထုတ်ယူနေပါတယ်...",
    "အသံကို စာသားအဖြစ် ပြောင်းနေပါတယ်...",
    "စာသားကို ဘာသာပြန် / ပြန်လည်ရေးသားနေပါတယ်...",
    "အသံဖိုင် ဖန်တီးနေပါတယ်...",
    "ဗီဒီယိုနဲ့ အသံ ပေါင်းနေပါတယ်...",
    "စာတန်းထိုးနေပါတယ်...",
    "ပြီးပါပြီ ✓"
]


class PipelineOrchestrator:
    def __init__(
        self,
        job_id: str,
        job_dir: Path,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.job_id = job_id
        self.job_dir = Path(job_dir)
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.event_callback = event_callback
        self.status = "idle"
        self.current_stage = ""
        self.artifacts: Dict[str, str] = {}

    def _notify(self, stage: str, stage_index: int, message: str, progress: float, data: Optional[Dict[str, Any]] = None):
        self.current_stage = stage
        payload = {
            "job_id": self.job_id,
            "stage": stage,
            "stage_index": stage_index,
            "total_stages": len(STAGES),
            "message": message,
            "progress": round(progress, 1),
            "timestamp": time.time(),
            "data": data or {}
        }
        if self.event_callback:
            self.event_callback(payload)

    def _get_media_duration(self, file_path: Path) -> float:
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return float(res.stdout.strip() or 0.0)
        except Exception:
            return 0.0

    def run(
        self,
        video_url: Optional[str],
        uploaded_video_path: Optional[Path],
        groq_api_key: str,
        gemini_api_key: str,
        voice_engine: str = "edge_tts",
        edge_tts_voice: str = "my-MM-NilarNeural",
        voxcpm_voice_path: Optional[str] = None,
        voxcpm_ref_text: Optional[str] = None,
        voxcpm_device: Optional[str] = None,
        gemini_mode: str = "translate",
        target_language: str = "my",
        font_color: str = "#FFFFFF",
        font_size_px: int = 36,
        font_style: str = "Myanmar Text",
        pos_x_pct: float = 50.0,
        pos_y_pct: float = 82.0,
        enable_subtitles: bool = True
    ) -> Dict[str, Any]:
        try:
            self.status = "running"

            # ----------------------------------------------------
            # STAGE 1: ဗီဒီယို ဒေါင်းလုဒ်လုပ်နေပါတယ်...
            # ----------------------------------------------------
            stage_1 = STAGES[0]
            self._notify(stage_1, 1, "ဒေါင်းလုဒ် စတင်နေပါပြီ...", 0.0)
            if uploaded_video_path and Path(uploaded_video_path).exists():
                video_file = self.job_dir / f"downloaded_video{Path(uploaded_video_path).suffix}"
                shutil.copy2(str(uploaded_video_path), str(video_file))
                self._notify(stage_1, 1, "တင်ထားသော ဗီဒီယိုဖိုင်ကို အသုံးပြုနေပါသည်...", 100.0)
            elif video_url:
                downloader = VideoDownloader(
                    self.job_dir,
                    progress_callback=lambda msg, pct: self._notify(stage_1, 1, msg, pct)
                )
                video_file = downloader.download(video_url)
            else:
                raise ValueError("ဗီဒီယို Link သို့မဟုတ် Video ဖိုင် ထည့်သွင်းပေးပါ။")

            self.artifacts["downloaded_video"] = video_file.name

            # ----------------------------------------------------
            # STAGE 2: အသံဖိုင် ထုတ်ယူနေပါတယ်...
            # ----------------------------------------------------
            stage_2 = STAGES[1]
            self._notify(stage_2, 2, "FFmpeg ဖြင့် အသံဖိုင် ထုတ်ယူနေပါသည်...", 10.0)
            extractor = AudioExtractor(
                progress_callback=lambda msg, pct: self._notify(stage_2, 2, msg, pct)
            )
            original_audio = extractor.extract(video_file)
            self.artifacts["original_audio"] = original_audio.name

            # ----------------------------------------------------
            # STAGE 3: အသံကို စာသားအဖြစ် ပြောင်းနေပါတယ်... (Groq STT)
            # ----------------------------------------------------
            stage_3 = STAGES[2]
            self._notify(stage_3, 3, "Groq API ဖြင့် အသံကို စာသားပြောင်းနေပါသည်...", 15.0)
            transcriber = GroqTranscriber(
                api_key=groq_api_key,
                progress_callback=lambda msg, pct: self._notify(stage_3, 3, msg, pct)
            )
            groq_res = transcriber.transcribe(original_audio, self.job_dir)
            self.artifacts["transcript_json"] = "transcript.json"
            self.artifacts["transcript_txt"] = "transcript.txt"

            self._notify(
                stage_3, 3,
                f"စာသားပြောင်းလဲခြင်း ပြီးပါပြီ ({len(groq_res['segments'])} segments)",
                100.0,
                data={
                    "groq_text": groq_res["text"],
                    "groq_segments": groq_res["segments"]
                }
            )

            # ----------------------------------------------------
            # STAGE 4: စာသားကို ဘာသာပြန် / ပြန်လည်ရေးသားနေပါတယ်... (Gemini)
            # ----------------------------------------------------
            stage_4 = STAGES[3]
            self._notify(stage_4, 4, "Gemini API ဖြင့် ဇာတ်လမ်းပြောစာသား စီစဉ်နေပါသည်...", 15.0)
            rewriter = GeminiRewriter(
                api_key=gemini_api_key,
                progress_callback=lambda msg, pct: self._notify(stage_4, 4, msg, pct)
            )
            gemini_res = rewriter.process(
                groq_result=groq_res,
                output_dir=self.job_dir,
                mode=gemini_mode,
                target_language=target_language
            )
            self.artifacts["processed_transcript_txt"] = "processed_transcript.txt"
            self.artifacts["processed_transcript_json"] = "processed_transcript.json"

            self._notify(
                stage_4, 4,
                "ဇာတ်လမ်းပြောစာသား ပြင်ဆင်ခြင်း ပြီးပါပြီ။",
                100.0,
                data={
                    "processed_text": gemini_res["full_text"],
                    "processed_segments": gemini_res["segments"]
                }
            )

            # ----------------------------------------------------
            # STAGE 5: အသံဖိုင် ဖန်တီးနေပါတယ်... (Continuous Narration)
            # ----------------------------------------------------
            stage_5 = STAGES[4]
            self._notify(stage_5, 5, f"ဇာတ်လမ်းပြော အသံဖိုင် ဖန်တီးနေပါသည် ({voice_engine})...", 10.0)
            tts_engine = TTSEngine(
                progress_callback=lambda msg, pct: self._notify(stage_5, 5, msg, pct)
            )
            tts_audio, synced_segments = tts_engine.generate(
                segments=gemini_res["segments"],
                output_dir=self.job_dir,
                engine=voice_engine,
                voice=edge_tts_voice,
                voxcpm_ref_path=voxcpm_voice_path,
                voxcpm_ref_text=voxcpm_ref_text,
                voxcpm_device=voxcpm_device
            )
            self.artifacts["tts_audio"] = tts_audio.name

            # ----------------------------------------------------
            # STAGE 6: ဗီဒီယိုနဲ့ အသံ ပေါင်းနေပါတယ်... (Speed Matching via setpts)
            # ----------------------------------------------------
            stage_6 = STAGES[5]
            self._notify(stage_6, 6, "ဗီဒီယို speed ကို ဇာတ်လမ်းပြောအသံနှင့် ကိုက်ညီအောင် ညှိနေပါသည်...", 15.0)
            mixer = AudioMixer(
                progress_callback=lambda msg, pct: self._notify(stage_6, 6, msg, pct)
            )
            dubbed_video = mixer.mix(video_file, tts_audio)
            self.artifacts["dubbed_video"] = dubbed_video.name

            # ----------------------------------------------------
            # STAGE 7: စာတန်းထိုးနေပါတယ်... (Custom pos(x,y) burning or export)
            # ----------------------------------------------------
            stage_7 = STAGES[6]
            burner = SubtitleBurner(
                progress_callback=lambda msg, pct: self._notify(stage_7, 7, msg, pct)
            )
            if enable_subtitles:
                self._notify(stage_7, 7, "စာတန်းထိုး ထည့်သွင်းနေပါသည်...", 15.0)
                final_video = burner.burn(
                    video_path=dubbed_video,
                    segments=synced_segments,
                    font_color=font_color,
                    font_size_px=font_size_px,
                    font_style=font_style,
                    pos_x_pct=pos_x_pct,
                    pos_y_pct=pos_y_pct
                )
            else:
                self._notify(stage_7, 7, "စာတန်းထိုးဖိုင် (SRT) ထုတ်ယူနေပါသည်...", 50.0)
                width, height = burner._get_video_dimensions(dubbed_video)
                burner.generate_subtitles(
                    segments=synced_segments,
                    output_dir=self.job_dir,
                    video_width=width,
                    video_height=height,
                    font_color=font_color,
                    font_size_px=font_size_px,
                    font_style=font_style,
                    pos_x_pct=pos_x_pct,
                    pos_y_pct=pos_y_pct
                )
                final_video = self.job_dir / "final_video.mp4"
                shutil.copy2(dubbed_video, final_video)

            self.artifacts["final_video"] = final_video.name
            self.artifacts["subtitles_ass"] = "subtitles.ass"
            self.artifacts["subtitles_srt"] = "subtitles.srt"

            # ----------------------------------------------------
            # STAGE 8: ပြီးပါပြီ ✓ (Complete)
            # ----------------------------------------------------
            stage_8 = STAGES[7]
            self.status = "completed"
            final_dur = self._get_media_duration(final_video)
            mins = int(final_dur // 60)
            secs = int(final_dur % 60)
            formatted_duration = f"{mins:02d}:{secs:02d}"

            summary_data = {
                "job_id": self.job_id,
                "artifacts": self.artifacts,
                "groq_text": groq_res["text"],
                "processed_text": gemini_res["full_text"],
                "segments_count": len(synced_segments),
                "final_duration_seconds": round(final_dur, 2),
                "final_duration_formatted": formatted_duration,
                "final_video_url": f"/api/jobs/{self.job_id}/files/final_video.mp4"
            }

            with open(self.job_dir / "job_summary.json", "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)

            self._notify(stage_8, 8, "ဗီဒီယို လုပ်ငန်းစဉ် အောင်မြင်စွာ ပြီးဆုံးပါပြီ။", 100.0, data=summary_data)
            return summary_data

        except Exception as e:
            self.status = "failed"
            err_msg = str(e)
            stack = traceback.format_exc()
            print(f"Error in pipeline job {self.job_id}:\n{stack}")
            sanitized_msg = err_msg.replace(groq_api_key, "***") if groq_api_key else err_msg
            if gemini_api_key:
                sanitized_msg = sanitized_msg.replace(gemini_api_key, "***")
            self._notify("မအောင်မြင်ပါ", -1, f"အမှားဖြစ်ပေါ်ပါသည်: {sanitized_msg}", 0.0, data={"error": sanitized_msg})
            raise RuntimeError(sanitized_msg)
