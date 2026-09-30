"""Vocal/dialogue separation for modes that preserve original music and SFX.

Demucs produces the background stem used by Recap and Dubbing. Story Mode
intentionally skips this module and uses TTS without the original audio bed.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional


class VocalSeparator:
    def __init__(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        self.progress_callback = progress_callback

    def extract_source_audio(self, video_path: Path, output_path: Path) -> Path:
        """Extract a stereo, full-quality source for music/effects separation.

        Whisper intentionally receives mono 16 kHz audio elsewhere. Demucs
        needs the original stereo image so music and effects are not degraded
        before vocal removal.
        """
        video_path, output_path = Path(video_path), Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([
            "ffmpeg", "-y", "-i", str(video_path), "-vn",
            "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(output_path)
        ], capture_output=True, text=True)
        if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError(f"Full-quality source audio extraction failed: {(result.stderr or '').strip()[-1200:]}")
        return output_path

    def separate_background(self, audio_path: Path, output_dir: Path) -> Path:
        audio_path = Path(audio_path)
        output_dir = Path(output_dir)
        if not audio_path.is_file():
            raise FileNotFoundError(f"Original audio not found: {audio_path}")
        output_dir.mkdir(parents=True, exist_ok=True)
        work_dir = output_dir / "demucs_stems"
        work_dir.mkdir(parents=True, exist_ok=True)
        expected = work_dir / "htdemucs" / audio_path.stem / "no_vocals.wav"
        if expected.is_file() and expected.stat().st_size:
            return expected

        if self.progress_callback:
            self.progress_callback("မူရင်း voiceover ကို music/effects မှ ခွဲနေပါသည်...", 15.0)

        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"

        command = [
            "python3", "-m", "demucs",
            "--two-stems=vocals",
            "-n", "htdemucs",
            "-d", device,
            "--out", str(work_dir),
            str(audio_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Demucs failed").strip()[-1600:]
            raise RuntimeError(f"Vocal separation failed: {detail}")

        candidates = list(work_dir.glob("**/no_vocals.wav"))
        if not candidates:
            raise RuntimeError("Vocal separation completed but no background stem was produced.")
        background = candidates[0]
        if background.resolve() != expected.resolve():
            expected.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(background, expected)
            background = expected
        if self.progress_callback:
            self.progress_callback("မူရင်း background music/effects ကို ထိန်းထားပါပြီ။", 100.0)
        return background


__all__ = ["VocalSeparator"]
