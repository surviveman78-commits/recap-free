import subprocess
import soundfile as sf
from pathlib import Path
from typing import Optional, Callable

from app.pipeline.gpu_utils import get_video_encoder_args, get_active_encoder_name


class AudioMixer:
    def __init__(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        self.progress_callback = progress_callback

    def _get_duration(self, file_path: Path) -> float:
        try:
            if file_path.suffix.lower() == ".wav":
                info = sf.info(str(file_path))
                return float(info.duration)
        except Exception:
            pass

        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            return float(res.stdout.strip())
        except ValueError:
            return 0.0

    def mix(
        self,
        video_path: Path,
        tts_audio_path: Path,
        output_path: Optional[Path] = None,
        resolution: str = "1080p"
    ) -> Path:
        video_path = Path(video_path)
        tts_audio_path = Path(tts_audio_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        if not tts_audio_path.exists():
            raise FileNotFoundError(f"TTS audio not found: {tts_audio_path}")

        if output_path is None:
            output_path = video_path.parent / "dubbed_video.mp4"
        else:
            output_path = Path(output_path)

        if self.progress_callback:
            self.progress_callback("ဗီဒီယိုနဲ့ အသံ ပေါင်းနေပါတယ်...", 10.0)

        video_dur = self._get_duration(video_path)
        tts_dur = self._get_duration(tts_audio_path)

        if tts_dur <= 0:
            raise RuntimeError("TTS narration audio duration is invalid.")
        if video_dur <= 0:
            video_dur = tts_dur

        # Calculate exact speed stretching factor so video matches the continuous recap narration duration
        pts_factor = tts_dur / video_dur

        if self.progress_callback:
            self.progress_callback(
                f"ဗီဒီယို speed ညှိနေပါသည် (မူရင်း: {video_dur:.1f}s → ဇာတ်လမ်းပြော: {tts_dur:.1f}s)...",
                35.0
            )

        encoder_name = get_active_encoder_name()
        encoder_args = get_video_encoder_args(cq=18, crf=17)

        resolution_sizes = {
            "1080p": 1920,
            "2k": 2560,
            "4k": 3840,
        }
        resolution_key = str(resolution or "1080p").strip().lower()
        target_short_edge = resolution_sizes.get(resolution_key, 1080)
        # Preserve orientation: the selected value is the portrait height or
        # landscape width, with the other dimension calculated automatically.
        scale_filter = (
            f"scale=w='if(gte(iw,ih),{target_short_edge},-2)':"
            f"h='if(gte(iw,ih),-2,{target_short_edge})':flags=lanczos"
        )

        # Build FFmpeg command with GPU or CPU encoder
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(tts_audio_path),
            "-filter_complex", f"[0:v]setpts={pts_factor:.6f}*PTS,{scale_filter},fps=30[v]",
            "-map", "[v]",
            "-map", "1:a:0",
            "-t", f"{tts_dur:.3f}",
            *encoder_args,
            "-c:a", "aac",
            "-b:a", "192k",
            "-vsync", "cfr",
            "-movflags", "+faststart",
            str(output_path)
        ]

        if self.progress_callback:
            self.progress_callback(f"{resolution_key} ဗီဒီယိုနှင့် အသံဖိုင် ပေါင်းစပ် rendering ပြုလုပ်နေပါသည် ({encoder_name})...", 65.0)

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            # If GPU encoding failed, retry once with CPU libx264 as safety fallback
            if "h264_nvenc" in encoder_args or "h264_mf" in encoder_args:
                print("[GPU WARNING] GPU rendering failed; retrying with CPU libx264.")
                fallback_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-i", str(tts_audio_path),
                    "-filter_complex", f"[0:v]setpts={pts_factor:.6f}*PTS,{scale_filter},fps=30[v]",
                    "-map", "[v]",
                    "-map", "1:a:0",
                    "-t", f"{tts_dur:.3f}",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "17",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-vsync", "cfr",
                    "-movflags", "+faststart",
                    str(output_path)
                ]
                fallback_res = subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if fallback_res.returncode != 0:
                    raise RuntimeError("Video rendering failed after CPU fallback. Please check the video format and FFmpeg setup.")
            else:
                raise RuntimeError("Video speed adjustment failed. Please check the video format and FFmpeg setup.")

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("Audio mixing produced empty or missing file.")

        if self.progress_callback:
            self.progress_callback("ဗီဒီယိုနှင့် အသံဖိုင် ပေါင်းစပ်ပြီးပါပြီ။", 100.0)

        return output_path
