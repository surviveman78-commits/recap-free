"""Offline transcription using faster-whisper with a pre-downloaded Kaggle model."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class LocalWhisperTranscriber:
    _models: Dict[str, Any] = {}

    def __init__(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        self.progress_callback = progress_callback

    def _load_model(self):
        from faster_whisper import WhisperModel

        model_path = os.getenv("RECAP_WHISPER_MODEL", "large-v3")
        device = os.getenv("RECAP_WHISPER_DEVICE", "cuda")
        device_index = int(os.getenv("RECAP_WHISPER_DEVICE_INDEX", "0"))
        cache_key = f"{model_path}|{device}|{device_index}|{os.getenv('RECAP_WHISPER_COMPUTE', 'float16')}"
        if cache_key not in self._models:
            compute_type = os.getenv("RECAP_WHISPER_COMPUTE", "float16" if device == "cuda" else "int8")
            self._models[cache_key] = WhisperModel(
                model_path,
                device=device,
                compute_type=compute_type,
                device_index=device_index,
                download_root=os.getenv("HF_HOME", "/kaggle/working/huggingface"),
            )
        return self._models[cache_key]

    def transcribe(self, audio_path: Path, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        audio_path = Path(audio_path)
        output_dir = Path(output_dir or audio_path.parent)
        output_dir.mkdir(parents=True, exist_ok=True)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if self.progress_callback:
            self.progress_callback("Local Whisper model ကို load လုပ်နေပါသည်...", 10.0)

        model = self._load_model()
        segments_iter, info = model.transcribe(
            str(audio_path),
            beam_size=int(os.getenv("RECAP_WHISPER_BEAM_SIZE", "5")),
            vad_filter=True,
            condition_on_previous_text=True,
            word_timestamps=False,
        )
        segments: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        for idx, segment in enumerate(segments_iter):
            text = (segment.text or "").strip()
            if not text:
                continue
            segments.append({"id": len(segments), "start": float(segment.start), "end": float(segment.end), "text": text})
            text_parts.append(text)
            if self.progress_callback:
                self.progress_callback(f"Local Whisper transcribe လုပ်နေပါသည်... ({len(segments)} segments)", min(90.0, 20.0 + len(segments) * 0.5))

        full_text = " ".join(text_parts).strip()
        language = getattr(info, "language", "auto") or "auto"
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        result = {"text": full_text, "segments": segments, "language": language, "duration": duration}
        (output_dir / "transcript.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        with (output_dir / "transcript.txt").open("w", encoding="utf-8") as f:
            f.write(full_text + "\n\n--- SEGMENTS WITH TIMESTAMPS ---\n")
            for seg in segments:
                f.write(f"[{seg['start']:.2f}s -> {seg['end']:.2f}s] {seg['text']}\n")
        if self.progress_callback:
            self.progress_callback("Local Whisper transcript ပြီးပါပြီ။", 100.0)
        return {"json_path": output_dir / "transcript.json", "txt_path": output_dir / "transcript.txt", **result}
