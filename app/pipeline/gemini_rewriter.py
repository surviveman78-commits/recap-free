import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
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
    "id": "Indonesian"
}


class GeminiRewriter:
    def __init__(self, api_key: str, progress_callback: Optional[Callable[[str, float], None]] = None):
        if not api_key:
            raise ValueError("Gemini API Key is required. Please set it in Settings.")
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        self.progress_callback = progress_callback

    def process(
        self,
        groq_result: Dict[str, Any],
        output_dir: Path,
        mode: str = "translate",
        target_language: str = "my",
        model_name: str = "gemini-2.5-flash"
    ) -> Dict[str, Any]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self.progress_callback:
            self.progress_callback("စာသားကို ဘာသာပြန် / ပြန်လည်ရေးသားနေပါတယ်...", 10.0)

        segments = groq_result.get("segments", [])
        lang_name = TARGET_LANGUAGE_NAMES.get(target_language, target_language)

        if target_language == "my":
            task_directive = (
                "Translate the spoken transcript accurately into natural, compelling, storytelling Burmese (မြန်မာဘာသာ). "
                "Use standard modern Myanmar Unicode script. "
                "Craft the phrasing like an authentic recap narrator telling a smooth, continuous story, "
                "avoiding robotic literal word-for-word translation. Keep sentences natural and easy to speak."
            )
        elif target_language == "en":
            task_directive = (
                "Translate or rewrite the spoken transcript into fluent, natural, engaging English suitable for video recap narration."
            )
        else:
            task_directive = (
                f"Translate the spoken transcript accurately into fluent, natural, engaging {lang_name} suitable for video recap narration."
            )

        prompt = f"""
You are an expert video recap scriptwriter and subtitle translator.
Your task: Process the provided speech-to-text transcript segments from Groq.

DIRECTIVE:
{task_directive}

CRITICAL DUBBING RULES:
1. You MUST preserve the exact segment structure: retain the same 'id', 'start', and 'end' timestamp values for every segment.
2. For each segment, output the translated/processed text in the target language.
3. Keep the length of each sentence appropriate for its time duration (end - start) so the voice actor / TTS engine can speak it naturally without rushing.
4. Do NOT drop or combine segments. Every input segment must have a corresponding output segment.
5. Return ONLY a valid JSON object matching this schema:
{{
  "full_text": "Complete joined translated transcript string",
  "segments": [
    {{
      "id": 0,
      "start": 0.0,
      "end": 2.5,
      "text": "Translated segment text..."
    }}
  ]
}}

INPUT TRANSCRIPT SEGMENTS:
{json.dumps(segments, ensure_ascii=False, indent=2)}
"""

        if self.progress_callback:
            self.progress_callback("စာသားကို ဘာသာပြန် / ပြန်လည်ရေးသားနေပါတယ်... (Gemini API)", 45.0)

        model_candidates = [model_name, "gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
        unique_models = list(dict.fromkeys(model_candidates))

        last_err = None
        response_text = ""

        for candidate in unique_models:
            try:
                response = self.client.models.generate_content(
                    model=candidate,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        response_mime_type="application/json"
                    )
                )
                response_text = response.text
                break
            except Exception as e:
                last_err = e
                continue

        if not response_text:
            raise RuntimeError(f"Gemini API processing failed: {last_err}")

        if self.progress_callback:
            self.progress_callback("စာသားကို ဘာသာပြန် / ပြန်လည်ရေးသားနေပါတယ်... (Formatting)", 80.0)

        try:
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            parsed_data = json.loads(cleaned_text.strip())
        except Exception:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                parsed_data = json.loads(json_match.group(0))
            else:
                parsed_data = {"full_text": response_text, "segments": segments}

        processed_segments = parsed_data.get("segments", [])
        if not processed_segments and segments:
            processed_segments = segments

        processed_full_text = parsed_data.get("full_text") or "\n".join([s.get("text", "") for s in processed_segments])

        # Write processed_transcript.txt separately (MUST NOT overwrite Groq transcript.txt)
        processed_txt_path = output_dir / "processed_transcript.txt"
        with open(processed_txt_path, "w", encoding="utf-8") as f:
            f.write(processed_full_text.strip() + "\n\n--- PROCESSED SEGMENTS WITH TIMESTAMPS ---\n")
            for s in processed_segments:
                f.write(f"[{s.get('start', 0.0):.2f}s -> {s.get('end', 0.0):.2f}s] {s.get('text', '')}\n")

        processed_json_path = output_dir / "processed_transcript.json"
        with open(processed_json_path, "w", encoding="utf-8") as f:
            json.dump({
                "full_text": processed_full_text,
                "segments": processed_segments,
                "target_language": target_language,
                "mode": mode
            }, f, indent=2, ensure_ascii=False)

        if self.progress_callback:
            self.progress_callback("စာသားပြန်လည်ရေးသားခြင်း ပြီးပါပြီ။", 100.0)

        return {
            "txt_path": processed_txt_path,
            "json_path": processed_json_path,
            "full_text": processed_full_text,
            "segments": processed_segments
        }
