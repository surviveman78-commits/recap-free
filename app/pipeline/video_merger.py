"""Custom multi-clip merge and TikTok-oriented export."""
from pathlib import Path
from typing import Any, Dict, List
import json
import subprocess

from app.pipeline.gpu_utils import get_video_encoder_args


PROFILES = {
    "tiktok1080": {"width": 1080, "height": 1920, "target": 10_000_000, "maxrate": 14_000_000, "bufsize": 20_000_000},
    "tiktok2k": {"width": 1440, "height": 2560, "target": 18_000_000, "maxrate": 24_000_000, "bufsize": 36_000_000},
    "tiktok4k": {"width": 2160, "height": 3840, "target": 34_000_000, "maxrate": 42_000_000, "bufsize": 68_000_000},
}


def _probe(path: Path) -> Dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float((data.get("format") or {}).get("duration") or (video or {}).get("duration") or 0)
    if not video or duration <= 0:
        raise ValueError(f"Not a valid video file: {path.name}")
    return {"duration": duration, "has_audio": audio is not None, "width": video.get("width"), "height": video.get("height")}


def _safe_float(value: Any, default: float) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def merge_videos(input_paths: List[Path], clip_specs: List[Dict[str, Any]], output_path: Path,
                 profile_name: str = "tiktok1080", layout: str = "fit", fps: int = 30) -> Dict[str, Any]:
    if not 2 <= len(input_paths) <= 3:
        raise ValueError("Choose 2 or 3 video clips.")
    profile = PROFILES.get(profile_name, PROFILES["tiktok1080"])
    probes = [_probe(Path(path)) for path in input_paths]
    input_args: List[str] = []
    filter_parts: List[str] = []
    concat_inputs: List[str] = []
    input_index = 0
    durations: List[float] = []

    for index, (path, probe) in enumerate(zip(input_paths, probes)):
        spec = clip_specs[index] if index < len(clip_specs) else {}
        start = min(_safe_float(spec.get("start"), 0.0), max(0.0, probe["duration"] - 0.05))
        end = _safe_float(spec.get("end"), probe["duration"])
        end = min(probe["duration"], max(start + 0.05, end))
        clip_duration = end - start
        volume = min(2.0, max(0.0, _safe_float(spec.get("volume"), 1.0)))
        durations.append(clip_duration)
        input_args += ["-i", str(path)]
        video_input = input_index
        input_index += 1
        if layout == "crop":
            visual = f"scale={profile['width']}:{profile['height']}:force_original_aspect_ratio=increase,crop={profile['width']}:{profile['height']}"
        elif layout == "stretch":
            visual = f"scale={profile['width']}:{profile['height']}"
        else:
            visual = (
                f"scale={profile['width']}:{profile['height']}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={profile['width']}:{profile['height']}:(ow-iw)/2:(oh-ih)/2:color=black"
            )
        # Moderate clarity pass: preserve skin tones while improving contrast, color and edge detail.
        # This is intentionally restrained because TikTok applies another compression pass after upload.
        visual += ",eq=contrast=1.04:brightness=0.005:saturation=1.07,unsharp=5:5:0.30:5:5:0.0"
        filter_parts.append(
            f"[{video_input}:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,{visual},fps={fps},format=yuv420p[v{index}]"
        )
        if probe["has_audio"]:
            audio_input = video_input
            audio_label = f"[{audio_input}:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS,volume={volume:.3f},aformat=sample_rates=48000:channel_layouts=stereo[a{index}]"
        else:
            silent_index = input_index
            input_index += 1
            input_args += ["-f", "lavfi", "-t", f"{clip_duration:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            audio_label = f"[{silent_index}:a]atrim=duration={clip_duration:.3f},asetpts=PTS-STARTPTS,volume={volume:.3f}[a{index}]"
        filter_parts.append(audio_label)
        concat_inputs += [f"[v{index}][a{index}]"]

    filter_parts.append("".join(concat_inputs) + f"concat=n={len(input_paths)}:v=1:a=1[vout][aout]")
    filter_graph = ";".join(filter_parts)
    encoder = get_video_encoder_args(cq=18, crf=17)
    command = ["ffmpeg", "-y", *input_args, "-filter_complex", filter_graph,
               "-map", "[vout]", "-map", "[aout]", "-r", str(fps),
               *encoder, "-b:v", str(profile["target"]), "-maxrate", str(profile["maxrate"]),
               "-bufsize", str(profile["bufsize"]), "-profile:v", "high",
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
               "-movflags", "+faststart", "-shortest", str(output_path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Merge export failed: {result.stderr[-2500:]}")
    return {"duration": sum(durations), "profile": profile_name, "layout": layout, "fps": fps, "output": str(output_path)}
