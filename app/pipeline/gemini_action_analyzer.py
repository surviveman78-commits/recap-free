"""Selective Gemini Vision analysis for transcript-free Story Mode gaps."""

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from google import genai
from google.genai import types


class GeminiActionGapAnalyzer:
    """Describe only meaningful visual action inside speech-free video gaps."""

    MODELS = ["gemini-flash-latest", "gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"]
    MIN_GAP_SECONDS = 2.5
    MAX_GAP_SECONDS = 45.0

    def __init__(self, api_key: str, progress_callback: Optional[Callable[[str, float], None]] = None):
        if not api_key:
            raise ValueError("Gemini API Key is required for Story action analysis.")
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
                raise ValueError("Gemini did not return an action JSON object.")
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
             "-frames:v", "1", "-vf", "scale=1280:-2", "-q:v", "4", str(output_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"Could not extract action frame: {result.stderr[-500:]}")
        return output_path.read_bytes()

    @classmethod
    def find_gaps(cls, segments: List[Dict[str, Any]], duration: float) -> List[Dict[str, float]]:
        """Find transcript-free windows, keeping only useful-sized gaps."""
        timed = []
        for segment in segments or []:
            try:
                start = max(0.0, float(segment.get("start", 0.0)))
                end = min(duration, float(segment.get("end", 0.0)))
            except (TypeError, ValueError):
                continue
            if end > start:
                timed.append((start, end))
        timed.sort()
        gaps: List[Dict[str, float]] = []
        cursor = 0.0
        for start, end in timed:
            if start - cursor >= cls.MIN_GAP_SECONDS:
                gaps.append({"start": cursor, "end": start})
            cursor = max(cursor, end)
        if duration - cursor >= cls.MIN_GAP_SECONDS:
            gaps.append({"start": cursor, "end": duration})
        # Very long silent windows are sampled in bounded windows so one vision
        # call never has to explain an entire act of a movie.
        bounded: List[Dict[str, float]] = []
        for gap in gaps:
            start, end = gap["start"], gap["end"]
            while end - start > cls.MAX_GAP_SECONDS:
                bounded.append({"start": start, "end": start + cls.MAX_GAP_SECONDS})
                start += cls.MAX_GAP_SECONDS
            if end - start >= cls.MIN_GAP_SECONDS:
                bounded.append({"start": start, "end": end})
        return bounded

    def _ask(self, images: List[bytes], start: float, end: float) -> Dict[str, Any]:
        prompt = f"""
You are analyzing a silent or speech-free movie segment from {start:.2f}s to {end:.2f}s.
The images are ordered from the beginning to the end of this segment.
Describe only clearly visible, story-relevant actions that connect the surrounding
movie narrative. Do not guess dialogue, names, motives, thoughts, identities, or
objects that cannot be seen. If the frames show only atmosphere, scenery, or an
action that does not matter to the plot, return has_meaningful_action=false.
Use neutral Burmese narration-ready wording only when confidence is at least 0.70.
Return ONLY JSON:
{{
  "has_meaningful_action": true,
  "action_burmese": "short chronological narration of the visible action",
  "confidence": 0.0,
  "reason": "short reason"
}}
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
                        config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
                    )
                    return self._json_object(response.text or "")
                except Exception as exc:
                    last_error = exc
                    if attempt == 0:
                        time.sleep(1.5)
        raise RuntimeError(f"Gemini action-gap analysis failed: {last_error}")

    def analyze(self, video_path: Path, transcript_segments: List[Dict[str, Any]], duration: float,
                output_dir: Path) -> List[Dict[str, Any]]:
        output_dir = Path(output_dir)
        frame_dir = output_dir / "story_action_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        gaps = self.find_gaps(transcript_segments, duration)
        results: List[Dict[str, Any]] = []
        for index, gap in enumerate(gaps):
            start, end = gap["start"], gap["end"]
            timestamps = [start + (end - start) * fraction for fraction in (0.15, 0.5, 0.85)]
            images = []
            for frame_index, timestamp in enumerate(timestamps):
                images.append(self._frame(video_path, timestamp, frame_dir / f"gap_{index:03d}_{frame_index}.jpg"))
            if self.progress_callback:
                self.progress_callback(f"Story action-only gap ကို Vision ဖြင့်စစ်နေပါသည်... ({index + 1}/{len(gaps)})", 20.0 + (index / max(1, len(gaps))) * 45.0)
            raw = self._ask(images, start, end)
            confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0) or 0.0)))
            action = str(raw.get("action_burmese", "")).strip()
            if bool(raw.get("has_meaningful_action")) and confidence >= 0.70 and action:
                results.append({
                    "id": f"vision_gap_{index}", "start": start, "end": end,
                    "text": action, "display_text": action, "tts_text": action,
                    "role": "visual_action", "vision_confidence": confidence,
                    "vision_reason": str(raw.get("reason", "")),
                })
        (output_dir / "story_action_analysis.json").write_text(
            json.dumps({"gaps": gaps, "visual_segments": results}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return results


__all__ = ["GeminiActionGapAnalyzer"]
