import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from groq import Groq


class GroqTranscriber:
    def __init__(self, api_key: str, progress_callback: Optional[Callable[[str, float], None]] = None):
        if not api_key:
            raise ValueError("Groq API Key is required. Please set it in Settings.")
        self.client = Groq(api_key=api_key)
        self.progress_callback = progress_callback

    def _ensure_audio_under_limit(self, audio_path: Path) -> Path:
        """Groq API has a 25MB upload limit. Compress to mp3 if needed."""
        size_mb = audio_path.stat().st_size / (1024 * 1024)
        if size_mb < 24.0:
            return audio_path

        # Compress to 64k mono MP3 for transcription
        compressed = audio_path.parent / "groq_audio_input.mp3"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(audio_path),
            "-acodec", "libmp3lame",
            "-b:a", "64k",
            "-ac", "1",
            str(compressed)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return compressed

    def transcribe(
        self,
        audio_path: Path,
        output_dir: Optional[Path] = None,
        model: str = "whisper-large-v3-turbo"
    ) -> Dict[str, Any]:
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if output_dir is None:
            output_dir = audio_path.parent
        else:
            output_dir = Path(output_dir)

        if self.progress_callback:
            self.progress_callback("Creating transcript...", 10.0)

        upload_file = self._ensure_audio_under_limit(audio_path)

        if self.progress_callback:
            self.progress_callback("Creating transcript... (Uploading to Groq API)", 40.0)

        with open(upload_file, "rb") as f:
            audio_bytes = f.read()

        transcription_resp = self.client.audio.transcriptions.create(
            file=(upload_file.name, audio_bytes),
            model=model,
            response_format="verbose_json",
            temperature=0.0
        )

        if self.progress_callback:
            self.progress_callback("Creating transcript... (Formatting transcript)", 85.0)

        # Convert response to dictionary
        if hasattr(transcription_resp, "model_dump"):
            data = transcription_resp.model_dump()
        elif isinstance(transcription_resp, dict):
            data = transcription_resp
        else:
            data = json.loads(transcription_resp) if isinstance(transcription_resp, str) else dict(transcription_resp)

        full_text = data.get("text", "")
        segments: List[Dict[str, Any]] = []

        raw_segments = data.get("segments") or []
        for idx, seg in enumerate(raw_segments):
            segments.append({
                "id": idx,
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": seg.get("text", "").strip()
            })

        # Save transcript.json
        transcript_json_path = output_dir / "transcript.json"
        with open(transcript_json_path, "w", encoding="utf-8") as f:
            json.dump({
                "text": full_text,
                "segments": segments,
                "language": data.get("language", "auto"),
                "duration": data.get("duration", 0.0)
            }, f, indent=2, ensure_ascii=False)

        # Save transcript.txt
        transcript_txt_path = output_dir / "transcript.txt"
        with open(transcript_txt_path, "w", encoding="utf-8") as f:
            f.write(full_text.strip() + "\n\n--- SEGMENTS WITH TIMESTAMPS ---\n")
            for seg in segments:
                f.write(f"[{seg['start']:.2f}s -> {seg['end']:.2f}s] {seg['text']}\n")

        if self.progress_callback:
            self.progress_callback("Transcript created successfully.", 100.0)

        return {
            "json_path": transcript_json_path,
            "txt_path": transcript_txt_path,
            "text": full_text,
            "segments": segments
        }
