import os
import subprocess
import json
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from app.config import CUSTOM_FONTS_DIR, settings_manager
from app.pipeline.gpu_utils import get_video_encoder_args, get_active_encoder_name
from app.pipeline.burmese_text import grapheme_clusters, normalize_myanmar_text


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


def wrap_subtitle_text(text: str, max_chars: int = 28, max_lines: int = 2) -> str:
    """Wrap only the rendered subtitle; the original segment text stays unchanged for TTS."""
    text = normalize_myanmar_text(" ".join(str(text).split()))
    max_lines = 2
    if len(text) <= max_chars:
        return text
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars and len(lines) < max_lines - 1:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) == 2:
        return "\n".join(lines)
    # Burmese often has no spaces. Keep exactly two lines and split at the
    # nearest safe Unicode boundary instead of producing a third line.
    compact_clusters = grapheme_clusters("".join(lines))
    cut = min(max(1, max_chars), len(compact_clusters) - 1)
    return f"{''.join(compact_clusters[:cut])}\n{''.join(compact_clusters[cut:])}"


def split_sequential_subtitle_segments(
    segments: List[Dict[str, Any]], max_chars: int = 32
) -> List[Dict[str, Any]]:
    """Split long subtitle phrases into sequential one-line timed events."""
    expanded: List[Dict[str, Any]] = []
    for segment in segments:
        text = normalize_myanmar_text(str(segment.get("text", "")).strip())
        if not text:
            continue
        clusters = grapheme_clusters(text)
        parts: List[str] = []
        remaining = clusters[:]
        while len(remaining) > max_chars:
            cut = max_chars
            # Prefer a phrase boundary or word space near the visual limit.
            for index in range(max_chars, max(3, int(max_chars * 0.60)), -1):
                if remaining[index - 1].isspace() or remaining[index - 1] in "၊။!?…,:;—-":
                    cut = index
                    break
            parts.append("".join(remaining[:cut]).strip())
            remaining = remaining[cut:]
        tail = "".join(remaining).strip()
        if tail:
            parts.append(tail)
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start + 1.0))
        total_weight = max(1, sum(len(grapheme_clusters(part)) for part in parts))
        cursor = start
        for index, part in enumerate(parts):
            if index == len(parts) - 1:
                part_end = end
            else:
                part_end = cursor + (end - start) * len(grapheme_clusters(part)) / total_weight
            expanded.append({
                **segment,
                "text": part,
                "start": round(cursor, 3),
                "end": round(part_end, 3),
            })
            cursor = part_end
    return expanded


class SubtitleBurner:
    def __init__(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        self.progress_callback = progress_callback

    @staticmethod
    def _font_family_from_file(font_path: Path) -> str:
        try:
            family = subprocess.check_output(
                ["fc-scan", "--format=%{family}", str(font_path)],
                text=True, stderr=subprocess.DEVNULL,
            ).strip().split(",")[0].strip()
            if family:
                return family
        except Exception:
            pass
        return font_path.stem

    def _resolve_font(self, requested: str) -> (str, Optional[Path]):
        """Return the exact ASS family and custom file selected by the user."""
        requested = (requested or "Noto Sans Myanmar").strip()
        custom_path = Path(str(settings_manager.get("custom_font_path", "")))
        candidates = [custom_path] if custom_path.exists() else []
        if CUSTOM_FONTS_DIR.exists():
            candidates += sorted(CUSTOM_FONTS_DIR.glob("*.ttf"))
            candidates += sorted(CUSTOM_FONTS_DIR.glob("*.otf"))
        for font_path in candidates:
            family = self._font_family_from_file(font_path)
            if (family.casefold() == requested.casefold()
                    or font_path.stem.casefold() == requested.casefold()):
                return family, font_path
        if requested.casefold() in {"myanmar text", "myanmartext"}:
            requested = "Noto Sans Myanmar"
        return requested, None

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
        font_style: str = "Noto Sans Myanmar",
        pos_x_pct: float = 50.0,
        pos_y_pct: float = 82.0,
        auto_blur: bool = False
    ) -> (Path, Path):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ass_path = output_dir / "subtitles.ass"
        srt_path = output_dir / "subtitles.srt"

        # Calculate exact pixel coordinates from percentage drag
        target_x = int(video_width * (pos_x_pct / 100.0))
        target_y = int(video_height * (pos_y_pct / 100.0))

        # Auto Blur follows the reference image: compact, readable text whose
        # size does not become oversized on a tall 9:16 video.
        if auto_blur:
            # Readable on vertical videos: approximately 78px at 1320px width.
            scaled_font_size = max(56, min(84, int(round(video_width / 17.0))))
        else:
            scale_factor = video_height / 1080.0 if video_height > 0 else 1.0
            scaled_font_size = max(16, int(font_size_px * scale_factor))
        outline_size = max(2, int(scaled_font_size * 0.12))

        ass_color = hex_to_ass_color(font_color)
        safe_font, _ = self._resolve_font(font_style)

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
        if auto_blur:
            valid_segments = split_sequential_subtitle_segments(valid_segments)
        for idx, seg in enumerate(valid_segments):
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start + 1.0))
            text = normalize_myanmar_text(seg.get("text", "").strip())

            ass_start = format_ass_timestamp(start)
            ass_end = format_ass_timestamp(end)
            # Always render one subtitle line at a time; Auto Blur already
            # splits long phrases sequentially, and normal mode follows the
            # same no-stacking rule.
            subtitle_text = text
            clean_text = subtitle_text.replace("\n", "\\N")
            
            # Use \\an5\\pos(X, Y) tag for exact drag positioning matching CSS translate(-50%, -50%)!
            ass_lines.append(f"Dialogue: 0,{ass_start},{ass_end},Default,,0,0,0,,{{\\an5\\pos({target_x},{target_y})}}{clean_text}\n")

            srt_start = format_srt_timestamp(start)
            srt_end = format_srt_timestamp(end)
            srt_lines.append(f"{idx + 1}\n{srt_start} --> {srt_end}\n{subtitle_text}\n\n")

        # libass is more reliable across Kaggle FFmpeg builds when ASS is
        # written with an explicit UTF-8 BOM, as in the known-good renderer.
        with open(ass_path, "w", encoding="utf-8-sig") as f:
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
        font_style: str = "Noto Sans Myanmar",
        pos_x_pct: float = 50.0,
        pos_y_pct: float = 82.0,
        blur_band: Optional[Dict[str, float]] = None,
        auto_blur: bool = False
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
            pos_y_pct=pos_y_pct,
            auto_blur=auto_blur
        )

        encoder_name = get_active_encoder_name()
        encoder_args = get_video_encoder_args(cq=18, crf=17)

        if self.progress_callback:
            self.progress_callback(f"စာတန်းထိုးနေပါတယ်... (FFmpeg {encoder_name} rendering)", 50.0)

        # Resolve the selected font explicitly; this avoids missing-font fallback on Kaggle.
        fonts_dir_arg = ""
        safe_font, selected_font_path = self._resolve_font(font_style)
        try:
            match_font = safe_font
            font_file = subprocess.check_output(
                ["fc-match", "-f", "%{file}", match_font],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if font_file and Path(font_file).exists():
                fonts_dir_arg = f":fontsdir='{Path(font_file).parent.as_posix()}'"
        except Exception:
            pass

        # Always expose the custom directory when a custom font is selected;
        # otherwise a system fc-match result can silently win.
        if selected_font_path and CUSTOM_FONTS_DIR.exists():
            # Escape for FFmpeg filter on Windows
            clean_fonts_dir = str(CUSTOM_FONTS_DIR).replace('\\', '/').replace(':', '\\:')
            fonts_dir_arg = f":fontsdir='{clean_fonts_dir}'"

        # Use an absolute ASS path and the ASS filter. Relative paths and the
        # generic subtitles filter can resolve a stale/wrong file in queued
        # Kaggle jobs; the reference renderer uses this exact approach.
        ass_filter_path = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        sub_filter = f"ass='{ass_filter_path}'{fonts_dir_arg}"
        if blur_band:
            blur_top = max(0, min(height - 1, int(height * float(blur_band["top_percent"]) / 100.0)))
            blur_bottom = max(blur_top + 1, min(height, int(height * float(blur_band["bottom_percent"]) / 100.0)))
            blur_height = blur_bottom - blur_top
            filter_graph = (
                f"[0:v]split=2[base][blur_src];"
                f"[blur_src]crop=iw:{blur_height}:0:{blur_top},boxblur=12:2[blurred];"
                f"[base][blurred]overlay=0:{blur_top}:shortest=1[covered];"
                f"[covered]{sub_filter}[vout]"
            )
            filter_args = ["-filter_complex", filter_graph, "-map", "[vout]", "-map", "0:a?", "-c:a", "copy"]
        else:
            filter_args = ["-vf", sub_filter, "-c:a", "copy"]

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path.name),
            *filter_args,
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
            if "h264_nvenc" in encoder_args or "h264_mf" in encoder_args:
                print(f"[GPU WARNING] GPU subtitle burning failed, retrying with CPU (libx264): {result.stderr[:100]}")
                fallback_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video_path.name),
                    *filter_args,
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "17",
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
