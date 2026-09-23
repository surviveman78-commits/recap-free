import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from google import genai
from google.genai import types


class GeminiSubtitleBandDetector:
    """Find the hardcoded subtitle band from exactly three video screenshots."""

    MODELS = [
        "gemini-flash-latest",
        "gemini-3.8-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ]

    def __init__(self, api_key: str, progress_callback: Optional[Callable[[str, float], None]] = None):
        if not api_key:
            raise ValueError("Gemini API Key is required for Auto Blur.")
        self.client = genai.Client(api_key=api_key)
        self.progress_callback = progress_callback

    @staticmethod
    def _json_object(text: str) -> Dict[str, Any]:
        cleaned = (text or "").strip().removeprefix("```json").removesuffix("```").strip()
        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", text or "")
            if not match:
                raise ValueError("Gemini did not return a JSON object.")
            return json.loads(match.group(0))

    @staticmethod
    def _duration(video_path: Path) -> float:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, check=True,
        )
        return max(0.1, float(result.stdout.strip() or 0.1))

    @staticmethod
    def _frame(video_path: Path, timestamp: float, output_path: Path) -> bytes:
        result = subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{timestamp:.3f}", "-i", str(video_path),
             "-frames:v", "1", "-vf", "scale=1280:-2", "-q:v", "3", str(output_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"Could not extract screenshot: {result.stderr[-500:]}")
        return output_path.read_bytes()

    def _ask(self, images: List[bytes]) -> Dict[str, Any]:
        prompt = """
You are detecting burned-in dialogue subtitles in a video frame set.
Analyze all 3 images together. Ignore menus, posters, signs, logos, watermarks,
TikTok UI, and any text that is part of the scene. Find only the repeated
on-screen dialogue/caption subtitle band that should be covered before adding
a translated subtitle.

Return ONLY JSON with this exact shape:
{
  "has_hardcoded_subtitle": true,
  "top_percent": 70.0,
  "bottom_percent": 82.0,
  "confidence": 0.95,
  "reason": "short reason"
}

Coordinates are percentages of the full video frame height, from 0 at the top
to 100 at the bottom. The left and right coordinates are intentionally absent:
the application will cover the entire video width. Set top_percent and
bottom_percent to the tight outer boundary of the subtitle text, including its
outline/shadow but not unrelated scene content. If there is no hardcoded
subtitle, return has_hardcoded_subtitle false.
"""
        contents: List[Any] = [prompt]
        contents.extend(types.Part.from_bytes(data=image, mime_type="image/jpeg") for image in images)
        last_error = None
        for model in self.MODELS:
            for attempt in range(2):
                try:
                    response = self.client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            response_mime_type="application/json",
                        ),
                    )
                    return self._json_object(response.text or "")
                except Exception as exc:
                    last_error = exc
                    if attempt == 0:
                        time.sleep(1.5)
        raise RuntimeError(f"Gemini subtitle-band detection failed: {last_error}")

    def detect(self, video_path: Path, output_dir: Path) -> Dict[str, Any]:
        video_path = Path(video_path)
        output_dir = Path(output_dir)
        frame_dir = output_dir / "auto_blur_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        duration = self._duration(video_path)
        timestamps = [0.0, max(0.0, duration / 2.0), max(0.0, duration - min(0.5, duration / 10.0))]
        images = []
        for index, timestamp in enumerate(timestamps):
            path = frame_dir / f"frame_{index + 1}.jpg"
            images.append(self._frame(video_path, timestamp, path))

        if self.progress_callback:
            self.progress_callback("Gemini Vision ဖြင့် frame ၃ ခုမှ မူရင်းစာတန်းနေရာရှာနေပါသည်...", 45.0)
        raw = self._ask(images)
        has_subtitle = bool(raw.get("has_hardcoded_subtitle", False))
        top = float(raw.get("top_percent", 0.0))
        bottom = float(raw.get("bottom_percent", 0.0))
        confidence = float(raw.get("confidence", 0.0))
        if has_subtitle and 0.0 <= top < bottom <= 100.0:
            # One Gemini result covers all three screenshots, so keep the band
            # stable across the whole video and only add the requested vertical padding later.
            result = {
                "enabled": True,
                "has_hardcoded_subtitle": True,
                "top_percent": top,
                "bottom_percent": bottom,
                "confidence": max(0.0, min(1.0, confidence)),
                "sample_timestamps": timestamps,
                "reason": str(raw.get("reason", "")),
            }
        else:
            result = {
                "enabled": True,
                "has_hardcoded_subtitle": False,
                "top_percent": 0.0,
                "bottom_percent": 0.0,
                "confidence": max(0.0, min(1.0, confidence)),
                "sample_timestamps": timestamps,
                "reason": str(raw.get("reason", "No hardcoded subtitle detected.")),
            }
        (output_dir / "auto_blur_detection.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result


def padded_band(detection: Dict[str, Any], padding_pct: float = 1.5) -> Optional[Dict[str, float]]:
    if not detection.get("has_hardcoded_subtitle"):
        return None
    top = max(0.0, float(detection["top_percent"]) - float(padding_pct))
    bottom = min(100.0, float(detection["bottom_percent"]) + float(padding_pct))
    return {"top_percent": top, "bottom_percent": bottom}


__all__ = ["GeminiSubtitleBandDetector", "padded_band"]


if __name__ == "__main__":
    raise SystemExit("Use GeminiSubtitleBandDetector from the pipeline.")
