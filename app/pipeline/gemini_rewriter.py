import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple

from google import genai
from google.genai import types

TARGET_LANGUAGE_NAMES = {
    "my": "Burmese (မြန်မာဘာသာ)",
    "en": "English",
    "th": "Thai (ထိုင်းဘာသာ)",
    "ja": "Japanese (ဂျပန်ဘာသာ)",
    "ko": "Korean (ကိုရီးယားဘာသာ)",
    "zh": "Chinese (Mandarin, Simplified)",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "ru": "Russian",
    "vi": "Vietnamese",
    "hi": "Hindi",
    "id": "Indonesian",
}


class GeminiRewriter:
    """Faithful, natural translation for timed subtitle segments."""

    DEFAULT_MODEL = "gemini-flash-latest"
    FALLBACK_MODEL = "gemini-3.8-flash"

    def __init__(self, api_key: str, progress_callback: Optional[Callable[[str, float], None]] = None):
        if not api_key:
            raise ValueError("Gemini API Key is required. Please set it in Settings.")
        self.client = genai.Client(api_key=api_key)
        self.progress_callback = progress_callback

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        cleaned = (text or "").strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        try:
            return json.loads(cleaned.strip())
        except Exception:
            match = re.search(r"\{[\s\S]*\}", text or "")
            if not match:
                raise ValueError("Model did not return a JSON object.")
            return json.loads(match.group(0))

    @staticmethod
    def _validate_segments(source: List[Dict[str, Any]], output: List[Dict[str, Any]]) -> Tuple[bool, str]:
        if len(source) != len(output):
            return False, f"segment count changed: expected {len(source)}, got {len(output)}"
        for index, (src, dst) in enumerate(zip(source, output)):
            if dst.get("id") != src.get("id"):
                return False, f"segment {index} id changed"
            if abs(float(dst.get("start", -1)) - float(src.get("start", -2))) > 0.01:
                return False, f"segment {index} start timestamp changed"
            if abs(float(dst.get("end", -1)) - float(src.get("end", -2))) > 0.01:
                return False, f"segment {index} end timestamp changed"
            if not isinstance(dst.get("text"), str) or not dst["text"].strip():
                return False, f"segment {index} has empty text"
        return True, "ok"

    @staticmethod
    def _normalise_segments(source: List[Dict[str, Any]], output: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Keep source timing/id authoritative even if the model formats numbers differently."""
        return [
            {
                "id": src["id"],
                "start": float(src["start"]),
                "end": float(src["end"]),
                "text": str(dst.get("text", "")).strip(),
            }
            for src, dst in zip(source, output)
        ]

    def _generate(self, prompt: str, model_candidates: List[str]) -> str:
        last_err = None
        for candidate in dict.fromkeys(model_candidates):
            try:
                response = self.client.models.generate_content(
                    model=candidate,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.15,
                        response_mime_type="application/json",
                    ),
                )
                if response.text:
                    return response.text
            except Exception as exc:
                last_err = exc
        raise RuntimeError(f"Gemini API processing failed: {last_err}")

    def process(
        self,
        groq_result: Dict[str, Any],
        output_dir: Path,
        mode: str = "translate",
        target_language: str = "my",
        model_name: str = DEFAULT_MODEL,
    ) -> Dict[str, Any]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        source_segments = groq_result.get("segments", [])
        if not source_segments:
            raise ValueError("Transcript has no timed segments to translate.")

        lang_name = TARGET_LANGUAGE_NAMES.get(target_language, target_language)
        source_text = groq_result.get("text", "")
        if self.progress_callback:
            self.progress_callback("Transcript အပြည့်ကို ဖတ်ပြီး video အမျိုးအစား ခွဲနေပါသည်...", 10.0)

        prompt = f"""
You are a professional human translator. Translate the timed transcript into {lang_name}.
This is a direct, faithful translation only. Do not summarize, rewrite, retell, explain,
adapt, improve, shorten, or add creative wording.

NON-NEGOTIABLE SOURCE-COVERAGE RULES:
- Translate every sentence and every proposition in every source segment.
- The output for each segment must carry the complete meaning of its corresponding source segment.
- If a sentence is difficult, translate it more literally rather than omitting or compressing information.
- Natural target-language grammar is required, but natural does not mean shorter or simplified.
- Do not add facts, explanations, jokes, opinions, hooks, conclusions, or dramatic language.
- Do not remove details, qualifiers, uncertainty, repetition that carries emphasis, or emotional meaning.
- Preserve names, numbers, dates, places, units, quoted terms, technical words, and relationships.
- Do not optimize text to fit the speaking time. Translation length may differ between languages;
  never delete meaning to make a segment shorter.
- Keep every segment. Do not merge, split, reorder, or invent segments.
- Keep every input id, start, and end EXACTLY unchanged.
- Do not use the full transcript to summarize the segments. Translate each timed segment against
  its own source text, using the full transcript only to resolve pronouns or context.

OUTPUT: Return ONLY valid JSON with this exact shape:
{{
  "content_type": "entertainment|educational|emotional_story|news_documentary|conversation",
  "tone": "short description",
  "glossary": [{{"source": "term", "target": "translation"}}],
  "full_text": "joined translated text",
  "segments": [
    {{"id": 0, "start": 0.0, "end": 2.5, "text": "translation"}}
  ]
}}

SOURCE FULL TRANSCRIPT:
{source_text}

SOURCE TIMED SEGMENTS:
{json.dumps(source_segments, ensure_ascii=False, indent=2)}
"""

        if self.progress_callback:
            self.progress_callback("Context-aware ဘာသာပြန်နေပါသည်... (meaning ကို ထိန်းထားပါသည်)", 35.0)
        # Deliberately ignore legacy caller defaults: v10 always tries the requested
        # latest Flash model first, then the explicit fallback model.
        model_order = [self.DEFAULT_MODEL, self.FALLBACK_MODEL]
        response_text = self._generate(prompt, model_order)
        try:
            parsed = self._extract_json(response_text)
            translated = parsed.get("segments", [])
            valid, reason = self._validate_segments(source_segments, translated)
        except Exception as exc:
            valid, reason, parsed = False, str(exc), {}

        if not valid:
            if self.progress_callback:
                self.progress_callback("ဘာသာပြန်ရလဒ်ကို မူရင်း timestamp နဲ့ ပြန်စစ်နေပါသည်...", 62.0)
            repair_prompt = f"""
Repair this translation JSON without rewriting the wording.
Return ONLY JSON with content_type, tone, glossary, full_text, and segments.
The segments list MUST have exactly the same count as SOURCE, and each id/start/end
MUST be copied exactly from SOURCE. Only fix missing/invalid structure; preserve text.
SOURCE={json.dumps(source_segments, ensure_ascii=False)}
BAD_RESULT={json.dumps(parsed, ensure_ascii=False)}
VALIDATION_ERROR={reason}
"""
            repaired = self._extract_json(self._generate(repair_prompt, model_order))
            translated = repaired.get("segments", [])
            valid, reason = self._validate_segments(source_segments, translated)
            parsed = repaired

        if not valid:
            raise RuntimeError(f"Translation validation failed: {reason}")

        processed_segments = self._normalise_segments(source_segments, translated)
        processed_full_text = "\n".join(s["text"] for s in processed_segments)
        metadata = {
            "content_type": parsed.get("content_type", "conversation"),
            "tone": parsed.get("tone", "natural and faithful"),
            "glossary": parsed.get("glossary", []),
            "source_segment_count": len(source_segments),
            "meaning_policy": "faithful_natural_translation_no_summarization",
            "model_order": model_order,
        }

        if self.progress_callback:
            self.progress_callback("ဘာသာပြန်ရလဒ်ကို အဓိပ္ပာယ်/အရှည် စစ်ဆေးနေပါသည်...", 85.0)

        (output_dir / "translation_analysis.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        processed_txt_path = output_dir / "processed_transcript.txt"
        processed_txt_path.write_text(
            processed_full_text + "\n\n--- PROCESSED SEGMENTS WITH TIMESTAMPS ---\n" +
            "".join(f"[{s['start']:.2f}s -> {s['end']:.2f}s] {s['text']}\n" for s in processed_segments),
            encoding="utf-8",
        )
        processed_json_path = output_dir / "processed_transcript.json"
        processed_json_path.write_text(
            json.dumps({**metadata, "full_text": processed_full_text, "segments": processed_segments,
                        "target_language": target_language, "mode": mode}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if self.progress_callback:
            self.progress_callback("Controlled natural ဘာသာပြန်ပြီးပါပြီ။", 100.0)
        return {
            "txt_path": processed_txt_path,
            "json_path": processed_json_path,
            "full_text": processed_full_text,
            "segments": processed_segments,
            "analysis": metadata,
        }
