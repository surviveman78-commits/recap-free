import os
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from app.config import CUSTOM_FONTS_DIR
from app.pipeline.gpu_utils import get_video_encoder_args, get_active_encoder_name


def hex_to_ass_color(hex_str: str) -> str:
    hex_clean = hex_str.strip().lstrip('#')
    if len(hex_clean) == 3:
        hex_clean = "".join([c*2 for c in hex_clean])
    if len(hex_clean) != 6:
        return "&H00FFFFFF"
    r = hex_clean[0:2]
    g = hex_clean[2:4]
    b = hex_clean[4:6]
    return f"&H00{b.upper()}{g.upper()}{r.upper()}"


def format_ass_timestamp(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hrs:d}:{mins:02d}:{secs:02d}.{centis:02d}"


def format_srt_timestamp(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


class SubtitleBurner:
    def __init__(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        self.progress_callback = progress_callback

    def _get_video_dimensions(self, video_path: Path) -> (int, int):
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                str(video_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            info = json.loads(res.stdout)
            width = int(info["streams"][0]["width"])
            height = int(info["streams"][0]["height"])
            return width, height
        except Exception:
            return 1080, 1920

    def generate_subtitles(
        self,
        segments: List[Dict[str, Any]],
        output_dir: Path,
        video_width: int,
        video_height: int,
        font_color: str = "#FFFFFF",
        font_size_px: int = 36,
        font_style: str = "Myanmar Text",
        pos_x_pct: float = 50.0,
        pos_y_pct: float = 82.0
    ) -> (Path, Path):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ass_path = output_dir / "subtitles.ass"
        srt_path = output_dir / "subtitles.srt"

        # Calculate exact pixel coordinates from percentage drag
        target_x = int(video_width * (pos_x_pct / 100.0))
        target_y = int(video_height * (pos_y_pct / 100.0))

        # Scaled font size relative to video height (base 1080p)
        scale_factor = video_height / 1080.0 if video_height > 0 else 1.0
        scaled_font_size = max(16, int(font_size_px * scale_factor))
        outline_size = max(2, int(scaled_font_size * 0.12))

        ass_color = hex_to_ass_color(font_color)
        safe_font = font_style or "Myanmar Text"

        # ASS header
        ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{safe_font},{scaled_font_size},{ass_color},&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,{outline_size},1,5,50,50,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        ass_lines = [ass_header]
        srt_lines = []

        valid_segments = [s for s in segments if s.get("text", "").strip()]
        for idx, seg in enumerate(valid_segments):
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start + 1.0))
            text = seg.get("text", "").strip()

            ass_start = format_ass_timestamp(start)
            ass_end = format_ass_timestamp(end)
            clean_text = text.replace("\n", "\\N")
            
            # Use \\an5\\pos(X, Y) tag for exact drag positioning matching CSS translate(-50%, -50%)!
            ass_lines.append(f"Dialogue: 0,{ass_start},{ass_end},Default,,0,0,0,,{{\\an5\\pos({target_x},{target_y})}}{clean_text}\n")

            srt_start = format_srt_timestamp(start)
            srt_end = format_srt_timestamp(end)
            srt_lines.append(f"{idx + 1}\n{srt_start} --> {srt_end}\n{text}\n\n")

        with open(ass_path, "w", encoding="utf-8") as f:
            f.writelines(ass_lines)

        with open(srt_path, "w", encoding="utf-8") as f:
            f.writelines(srt_lines)

        return ass_path, srt_path

    def burn(
        self,
        video_path: Path,
        segments: List[Dict[str, Any]],
        output_path: Optional[Path] = None,
        font_color: str = "#FFFFFF",
        font_size_px: int = 36,
        font_style: str = "Myanmar Text",
        pos_x_pct: float = 50.0,
        pos_y_pct: float = 82.0
    ) -> Path:
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if output_path is None:
            output_path = video_path.parent / "final_video.mp4"
        else:
            output_path = Path(output_path)

        if self.progress_callback:
            self.progress_callback("စာတန်းထိုးနေပါတယ်...", 15.0)

        width, height = self._get_video_dimensions(video_path)
        ass_path, srt_path = self.generate_subtitles(
            segments=segments,
            output_dir=video_path.parent,
            video_width=width,
            video_height=height,
            font_color=font_color,
            font_size_px=font_size_px,
            font_style=font_style,
            pos_x_pct=pos_x_pct,
            pos_y_pct=pos_y_pct
        )

        encoder_name = get_active_encoder_name()
        encoder_args = get_video_encoder_args(cq=20, crf=18)

        if self.progress_callback:
            self.progress_callback(f"စာတန်းထိုးနေပါတယ်... (FFmpeg {encoder_name} rendering)", 50.0)

        sub_rel = ass_path.name
        
        # Check custom fonts directory
        fonts_dir_arg = ""
        if CUSTOM_FONTS_DIR.exists() and any(CUSTOM_FONTS_DIR.iterdir()):
            # Escape for FFmpeg filter on Windows
            clean_fonts_dir = str(CUSTOM_FONTS_DIR).replace('\\', '/').replace(':', '\\:')
            fonts_dir_arg = f":fontsdir='{clean_fonts_dir}'"

        sub_filter = f"subtitles='{sub_rel}'{fonts_dir_arg}"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path.name),
            "-vf", sub_filter,
            "-c:a", "copy",
            *encoder_args,
            str(output_path.name)
        ]

        result = subprocess.run(
            cmd,
            cwd=str(video_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            # If GPU encoding failed, retry once with CPU libx264 as safety fallback
            if "h264_nvenc" in encoder_args:
                print(f"[GPU WARNING] NVENC subtitle burning failed, retrying with CPU (libx264): {result.stderr[:100]}")
                fallback_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video_path.name),
                    "-vf", sub_filter,
                    "-c:a", "copy",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "18",
                    "-pix_fmt", "yuv420p",
                    str(output_path.name)
                ]
                fallback_res = subprocess.run(fallback_cmd, cwd=str(video_path.parent), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if fallback_res.returncode != 0:
                    raise RuntimeError(f"FFmpeg subtitle burning failed: {fallback_res.stderr}")
            else:
                raise RuntimeError(f"FFmpeg subtitle burning failed: {result.stderr}")

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("Subtitle burning produced empty or missing file.")

        if self.progress_callback:
            self.progress_callback("စာတန်းထိုးပြီးပါပြီ။", 100.0)

        return output_path
