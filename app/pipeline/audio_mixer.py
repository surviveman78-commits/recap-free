import subprocess
import soundfile as sf
from pathlib import Path
from typing import Optional, Callable, Dict, List

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

    @staticmethod
    def _build_scene_groups(sync_segments: Optional[List[Dict]], video_dur: float, tts_dur: float) -> List[Dict[str, float]]:
        """Map transcript/TTS clocks into bounded scene-like retiming groups.

        A group breaks on a meaningful transcript gap or after 30 seconds. This
        prevents one global setpts stretch from accumulating drift on long
        videos, while keeping short videos on the proven legacy path.
        """
        usable = []
        for seg in sync_segments or []:
            try:
                source_start = float(seg.get("source_start", 0.0))
                source_end = float(seg.get("source_end", 0.0))
                tts_start = float(seg.get("start", 0.0))
                tts_end = float(seg.get("end", 0.0))
            except (TypeError, ValueError):
                continue
            if source_end > source_start + 0.05 and tts_end > tts_start + 0.05:
                usable.append((source_start, source_end, tts_start, tts_end))
        if len(usable) < 2 or video_dur < 120.0:
            return []
        usable.sort(key=lambda item: item[0])
        groups = []
        current = [usable[0]]
        for item in usable[1:]:
            source_gap = max(0.0, item[0] - current[-1][1])
            current_source_span = current[-1][1] - current[0][0]
            if source_gap >= 2.0 or current_source_span >= 30.0:
                groups.append(current)
                current = [item]
            else:
                current.append(item)
        groups.append(current)

        result = []
        for index, group in enumerate(groups):
            # Keep every source frame. A transcript gap becomes part of the
            # following group instead of being silently dropped at concat.
            source_start = 0.0 if index == 0 else groups[index - 1][-1][1]
            source_end = video_dur if index == len(groups) - 1 else group[-1][1]
            tts_start = 0.0 if index == 0 else groups[index - 1][-1][3]
            tts_end = tts_dur if index == len(groups) - 1 else group[-1][3]
            if source_end > source_start + 0.05 and tts_end > tts_start + 0.05:
                result.append({"source_start": source_start, "source_end": source_end,
                               "tts_start": tts_start, "tts_end": tts_end})
        return result

    def mix(
        self,
        video_path: Path,
        tts_audio_path: Path,
        output_path: Optional[Path] = None,
        resolution: str = "1080p",
        background_audio_path: Optional[Path] = None,
        enable_4k_filter: bool = False,
        mirror_mode_7s: bool = False,
        sync_segments: Optional[List[Dict]] = None,
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

        scene_groups = self._build_scene_groups(sync_segments, video_dur, tts_dur)
        # Keep the legacy global factor for short videos and as a safe fallback.
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
            "tiktok1080": 1920,
            "2k": 2560,
            "tiktok2k": 2560,
            "4k": 3840,
            "tiktok4k": 3840,
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
        if scene_groups:
            scene_parts = []
            for index, group in enumerate(scene_groups):
                source_span = group["source_end"] - group["source_start"]
                target_span = group["tts_end"] - group["tts_start"]
                ratio = target_span / max(source_span, 0.05)
                scene_parts.append(
                    f"[0:v]trim=start={group['source_start']:.3f}:end={group['source_end']:.3f},"
                    f"setpts=PTS-STARTPTS,setpts={ratio:.6f}*PTS[scene{index}]"
                )
            scene_labels = "".join(f"[scene{index}]" for index in range(len(scene_parts)))
            visual_filters = scene_parts + [
                f"{scene_labels}concat=n={len(scene_parts)}:v=1:a=0[vretimed]",
                f"[vretimed]{scale_filter}[vscaled]",
            ]
            video_label = "[vscaled]"
        else:
            visual_filters = [f"setpts={pts_factor:.6f}*PTS", scale_filter]
            video_label = "[0:v]"
        if scene_groups:
            # Effects are appended to the already retimed/scaled stream below.
            post_filters = []
            if enable_4k_filter:
                post_filters.extend(["eq=contrast=1.08:brightness=0.02:saturation=1.08", "unsharp=5:5:0.45:5:5:0.0"])
            if mirror_mode_7s:
                post_filters.append("hflip=enable='gte(mod(t,14),7)'")
            post_filters.append("fps=30")
            filter_complex = ";".join(visual_filters) + f";{video_label}{','.join(post_filters)}[v]"
        else:
            if enable_4k_filter:
                # A restrained enhancement pass: upscale/scale first, then
                # improve contrast, color and perceived detail.
                visual_filters.extend(["eq=contrast=1.08:brightness=0.02:saturation=1.08", "unsharp=5:5:0.45:5:5:0.0"])
            if mirror_mode_7s:
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
            if scene_groups:
                bg_parts = []
                for index, group in enumerate(scene_groups):
                    source_span = group["source_end"] - group["source_start"]
                    target_span = group["tts_end"] - group["tts_start"]
                    bg_speed = source_span / max(target_span, 0.05)
                    bg_parts.append(
                        f"[2:a]atrim=start={group['source_start']:.3f}:end={group['source_end']:.3f},"
                        f"asetpts=PTS-STARTPTS,{self._atempo_chain(bg_speed)}[bg{index}]"
                    )
                bg_labels = "".join(f"[bg{index}]" for index in range(len(bg_parts)))
                filter_complex += ";" + ";".join(bg_parts)
                filter_complex += f";{bg_labels}concat=n={len(bg_parts)}:v=0:a=1,volume=0.7,atrim=duration={tts_dur:.3f}[bg]"
            else:
                background_speed = background_dur / tts_dur
                background_atempo = self._atempo_chain(background_speed)
                filter_complex += (
                    f";[2:a]atrim=duration={background_dur:.3f},asetpts=N/SR/TB,"
                    f"{background_atempo},volume=0.7,apad=whole_dur={tts_dur:.3f},"
                    f"atrim=duration={tts_dur:.3f}[bg]"
                )
            filter_complex += (
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
        if resolution_key in {"tiktok1080", "tiktok2k"}:
            # Use TikTok-compatible H.264 profiles while keeping the source
            # aspect ratio. The final subtitle stage applies its bitrate cap
            # when subtitles are enabled; this also covers subtitle-off jobs.
            # Do not force a fixed H.264 level here.  The app preserves the
            # source ratio, so square/ultrawide outputs can exceed the macroblock
            # limits of a nominal TikTok level and NVENC rejects the encode.
            # Let the selected encoder choose a valid level automatically.
            cmd[-1:-1] = ["-profile:v", "high", "-tag:v", "avc1"]

        if self.progress_callback:
            self.progress_callback(f"{resolution_key} ဗီဒီယိုနှင့် အသံဖိုင် ပေါင်းစပ် rendering ပြုလုပ်နေပါသည် ({encoder_name})...", 65.0)

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        (output_path.parent / "ffmpeg_audio_mixer_gpu.log").write_text(
            result.stderr or "", encoding="utf-8", errors="replace"
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
                (output_path.parent / "ffmpeg_audio_mixer_cpu.log").write_text(
                    fallback_res.stderr or "", encoding="utf-8", errors="replace"
                )
                if fallback_res.returncode != 0:
                    detail = (fallback_res.stderr or result.stderr or "").strip()[-1800:]
                    raise RuntimeError(f"Video rendering failed after CPU fallback: {detail}")
            else:
                detail = (result.stderr or "").strip()[-1800:]
                raise RuntimeError(f"Video speed adjustment failed: {detail}")

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("Audio mixing produced empty or missing file.")

        if self.progress_callback:
            self.progress_callback("ဗီဒီယိုနှင့် အသံဖိုင် ပေါင်းစပ်ပြီးပါပြီ။", 100.0)

        return output_path
