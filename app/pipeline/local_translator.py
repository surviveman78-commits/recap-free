"""Offline, meaning-preserving translation using NLLB-200."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

TARGET_LANGS = {
    "my": "mya_Mymr", "en": "eng_Latn", "th": "tha_Thai", "ja": "jpn_Jpan",
    "ko": "kor_Hang", "zh": "zho_Hans", "es": "spa_Latn", "fr": "fra_Latn",
    "de": "deu_Latn", "it": "ita_Latn", "ru": "rus_Cyrl", "vi": "vie_Latn",
    "hi": "hin_Deva", "id": "ind_Latn",
}


class LocalNLLBTranslator:
    _model = None
    _tokenizer = None
    _loaded_path = None

    def __init__(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        self.progress_callback = progress_callback

    def _load(self):
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        import torch

        model_path = os.getenv("RECAP_NLLB_MODEL", "facebook/nllb-200-distilled-1.3B")
        if self._model is None or self._loaded_path != model_path:
            if self.progress_callback:
                self.progress_callback("Local NLLB translation model ကို load လုပ်နေပါသည်...", 10.0)
            self._tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=os.getenv("RECAP_LOCAL_ONLY", "0") == "1")
            self._model = AutoModelForSeq2SeqLM.from_pretrained(
                model_path,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                local_files_only=os.getenv("RECAP_LOCAL_ONLY", "0") == "1",
            )
            if torch.cuda.is_available():
                device = os.getenv("RECAP_NLLB_DEVICE", "cuda:1")
                if device == "cuda:1" and torch.cuda.device_count() < 2:
                    device = "cuda:0"
                self._model = self._model.to(device)
            self._model.eval()
            self._loaded_path = model_path
        return self._tokenizer, self._model

    def translate(self, groq_result: Dict[str, Any], output_dir: Path, target_language: str = "my") -> Dict[str, Any]:
        import torch

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        source_segments = groq_result.get("segments", [])
        if not source_segments:
            raise ValueError("Transcript has no timed segments to translate.")
        target_code = TARGET_LANGS.get(target_language, target_language)
        tokenizer, model = self._load()
        source_code = groq_result.get("language", "eng")
        source_code = {"en": "eng_Latn", "my": "mya_Mymr", "zh": "zho_Hans", "ja": "jpn_Jpan"}.get(source_code, source_code)
        if source_code not in tokenizer.lang_code_to_id:
            source_code = "eng_Latn"
        tokenizer.src_lang = source_code

        translated: List[Dict[str, Any]] = []
        batch_size = int(os.getenv("RECAP_TRANSLATION_BATCH", "4"))
        texts = [str(s.get("text", "")).strip() for s in source_segments]
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            encoded = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=512)
            if torch.cuda.is_available():
                device = os.getenv("RECAP_NLLB_DEVICE", "cuda:1")
                if device == "cuda:1" and torch.cuda.device_count() < 2:
                    device = "cuda:0"
                encoded = {k: v.to(device) for k, v in encoded.items()}
            with torch.inference_mode():
                output = model.generate(
                    **encoded,
                    forced_bos_token_id=tokenizer.lang_code_to_id[target_code],
                    max_length=512,
                    num_beams=4,
                    do_sample=False,
                )
            results = tokenizer.batch_decode(output, skip_special_tokens=True)
            for original, text in zip(source_segments[start:start + batch_size], results):
                translated.append({
                    "id": original["id"], "start": float(original["start"]), "end": float(original["end"]),
                    "text": text.strip(),
                })
            if self.progress_callback:
                self.progress_callback(f"Local NLLB ဘာသာပြန်နေပါသည်... ({len(translated)}/{len(source_segments)})", min(95.0, 15.0 + len(translated) / len(source_segments) * 80.0))

        full_text = "\n".join(s["text"] for s in translated)
        metadata = {
            "content_type": "faithful_translation", "tone": "natural and faithful",
            "source_segment_count": len(source_segments),
            "meaning_policy": "faithful_natural_translation_no_summarization",
            "engine": "local_nllb",
        }
        (output_dir / "translation_analysis.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "processed_transcript.txt").write_text(
            full_text + "\n\n--- PROCESSED SEGMENTS WITH TIMESTAMPS ---\n" +
            "".join(f"[{s['start']:.2f}s -> {s['end']:.2f}s] {s['text']}\n" for s in translated), encoding="utf-8")
        result = {**metadata, "full_text": full_text, "segments": translated, "target_language": target_language, "mode": "translate"}
        (output_dir / "processed_transcript.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.progress_callback:
            self.progress_callback("Local NLLB ဘာသာပြန်ပြီးပါပြီ။", 100.0)
        return {"txt_path": output_dir / "processed_transcript.txt", "json_path": output_dir / "processed_transcript.json", "full_text": full_text, "segments": translated, "analysis": metadata}
