import subprocess
from pathlib import Path
from typing import Optional, Callable


class AudioExtractor:
    def __init__(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        self.progress_callback = progress_callback

    def extract(self, video_path: Path, output_path: Optional[Path] = None) -> Path:
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if output_path is None:
            output_path = video_path.parent / "original_audio.wav"
        else:
            output_path = Path(output_path)

        if self.progress_callback:
            self.progress_callback("Extracting audio...", 0.0)

        # Extract audio as 16kHz mono 16-bit PCM WAV (ideal for Whisper/Groq STT)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_path)
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr}")

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("Audio extraction produced an empty or missing file.")

        if self.progress_callback:
            self.progress_callback("Audio extraction complete.", 100.0)

        return output_path
