import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple

from google import genai
from google.genai import types
from app.pipeline.burmese_text import normalize_myanmar_text

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
    FALLBACK_MODELS = [
        "gemini-flash-latest",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
    ]

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
                "text": normalize_myanmar_text(str(dst.get("text", "")).strip()),
            }
            for src, dst in zip(source, output)
        ]

    def _generate(self, prompt: str, model_candidates: List[str]) -> str:
        last_err = None
        for candidate in dict.fromkeys(model_candidates):
            for attempt in range(1, 4):
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
                    last_err = RuntimeError(f"{candidate} returned an empty response")
                    break
                except Exception as exc:
                    last_err = exc
                    error_text = str(exc).lower()
                    transient = any(code in error_text for code in ("503", "429", "500", "temporarily unavailable", "overloaded"))
                    if transient and attempt < 3:
                        time.sleep(2 * attempt)
                        continue
                    break
        raise RuntimeError(f"Gemini API processing failed: {last_err}")

    def _available_model_candidates(self) -> List[str]:
        """Add generate-capable Gemini models exposed by the current API key."""
        candidates = list(self.FALLBACK_MODELS)
        try:
            for item in self.client.models.list():
                name = getattr(item, "name", "") or ""
                actions = getattr(item, "supported_actions", None) or []
                if name.startswith("models/"):
                    name = name[7:]
                if name.startswith("gemini") and (not actions or "generateContent" in actions):
                    candidates.append(name)
        except Exception:
            # Model listing is optional; the fixed list still provides fallback.
            pass
        return list(dict.fromkeys(candidates))

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
Translate the transcript into natural spoken {lang_name} for movie recap voice-over.

Rules:

* Translate the MEANING, not word-for-word.
* Make it sound like a native speaker naturally telling a story, NOT like a book or machine translation.
* Do not copy the original sentence structure if it sounds unnatural.
* Do not summarize or remove important information.
* Do not add explanations, details, opinions, or information that is not in the original.
* Keep the translated length reasonably close to the original. Do not make it unnecessarily shorter or longer.
* Use natural conversational grammar and expressions.
* Avoid overly formal/literary language.
* Avoid unnecessary pronouns and words such as “၎င်း”, “၎င်းတို့”, “ဖြစ်သည်”, “ဖြစ်ကြသည်” in Burmese when they make the sentence sound unnatural.
* Preserve names, numbers, actions, events, and important details accurately.
* Make every sentence smooth and easy to understand when heard through TTS.
* Think like a native speaker explaining what happened in a movie to a friend.
* Translate the story, not the words.

SOURCE-COVERAGE SAFETY:
* Translate every sentence and every proposition in every source segment.
* The output for each segment must carry the complete meaning of its corresponding source segment.
* Do not remove details, qualifiers, uncertainty, repetition that carries emphasis, or emotional meaning.
* Keep every segment. Do not merge, split, reorder, or invent segments.
* Keep every input id, start, and end EXACTLY unchanged.
* Use the full transcript only to resolve pronouns or context; never use it to summarize segments.

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
        # Try all known Flash fallbacks, then models exposed by this API key.
        model_order = self._available_model_candidates()
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
