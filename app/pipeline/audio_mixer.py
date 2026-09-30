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

    @staticmethod
    def _atempo_chain(speed: float) -> str:
        """Build valid atempo filters for any positive duration ratio."""
        if speed <= 0:
            return "atempo=1.0"
        filters = []
        # FFmpeg's atempo accepts 0.5..2.0 per filter. Chain filters for
        # longer/shorter stretches instead of silently truncating the bed.
        while speed > 2.0:
            filters.append("atempo=2.0")
            speed /= 2.0
        while speed < 0.5:
            filters.append("atempo=0.5")
            speed /= 0.5
        filters.append(f"atempo={speed:.6f}")
        return ",".join(filters)

    def mix(
        self,
        video_path: Path,
        tts_audio_path: Path,
        output_path: Optional[Path] = None,
        resolution: str = "1080p",
        background_audio_path: Optional[Path] = None,
        enable_4k_filter: bool = False,
        mirror_mode_7s: bool = False,
    ) -> Path:
        video_path = Path(video_path)
        tts_audio_path = Path(tts_audio_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        if not tts_audio_path.exists():
            raise FileNotFoundError(f"TTS audio not found: {tts_audio_path}")
        if background_audio_path is not None and not Path(background_audio_path).exists():
            raise FileNotFoundError(f"Background audio not found: {background_audio_path}")

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

        # Build FFmpeg command. Legacy mode maps TTS alone; background mode
        # keeps Demucs' music/effects stem underneath the new narration.
        input_args = ["-i", str(video_path), "-i", str(tts_audio_path)]
        visual_filters = [f"setpts={pts_factor:.6f}*PTS", scale_filter]
        if enable_4k_filter:
            # A restrained enhancement pass: upscale/scale first, then improve
            # contrast, color and perceived detail without changing the audio.
            visual_filters.append("eq=contrast=1.08:brightness=0.02:saturation=1.08")
            visual_filters.append("unsharp=5:5:0.45:5:5:0.0")
        if mirror_mode_7s:
            # Alternate orientation in seven-second windows: normal [0,7),
            # flipped [7,14), then repeat. hflip supports FFmpeg timeline expr.
            visual_filters.append("hflip=enable='gte(mod(t,14),7)'")
        visual_filters.append("fps=30")
        filter_complex = f"[0:v]{','.join(visual_filters)}[v]"
        audio_map = "1:a:0"
        if background_audio_path is not None:
            input_args += ["-i", str(background_audio_path)]
            background_dur = self._get_duration(Path(background_audio_path))
            if background_dur <= 0:
                background_dur = tts_dur
            # The source bed follows the rendered video source duration. It
            # must be stretched/compressed to the same TTS duration before
            # mixing, otherwise music/SFX will drift or end early.
            background_speed = background_dur / tts_dur
            background_atempo = self._atempo_chain(background_speed)
            filter_complex += (
                f";[2:a]atrim=duration={background_dur:.3f},asetpts=N/SR/TB,"
                f"{background_atempo},volume=0.7,apad=whole_dur={tts_dur:.3f},"
                f"atrim=duration={tts_dur:.3f}[bg]"
                f";[1:a]atrim=duration={tts_dur:.3f},asetpts=N/SR/TB[tts]"
                ";[bg][tts]amix=inputs=2:duration=longest:dropout_transition=0.2:normalize=0[a]"
            )
            audio_map = "[a]"
        cmd = [
            "ffmpeg", "-y", *input_args,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", audio_map,
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
                    "ffmpeg", "-y", *input_args,
                    "-filter_complex", filter_complex,
                    "-map", "[v]",
                    "-map", audio_map,
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
