import os
import json
from pathlib import Path
from typing import Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
CUSTOM_VOICES_DIR = DATA_DIR / "custom_voices"
CUSTOM_FONTS_DIR = DATA_DIR / "custom_fonts"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)
CUSTOM_FONTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "groq_api_key": "",
    "gemini_api_key": "",
    "target_language": "my",              # Default target: Burmese (my)
    "target_language_name": "Burmese (မြန်မာဘာသာ)",
    "voice_engine": "edge_tts",          # "edge_tts" or "voxcpm2"
    "edge_tts_language": "my-MM",
    "edge_tts_voice": "my-MM-NilarNeural",
    "voxcpm_voice_name": "reference_speaker.wav",
    "voxcpm_voice_path": "",
    "voxcpm_reference_text": "",         # Persistent reference transcript for VoxCPM
    "font_color": "#FFFFFF",
    "font_size_px": 36,                  # Numeric size slider (18 - 72)
    "font_style": "Myanmar Text",
    "custom_font_name": "",
    "custom_font_path": "",
    "subtitle_pos_x": 50,                # Horizontal percentage (0-100%, 50 = center)
    "subtitle_pos_y": 82,                # Vertical percentage (0-100%, 82 = lower-third safe area)
    "enable_subtitles": True             # Whether to burn subtitles into video
}


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


class SettingsManager:
    def __init__(self):
        self._cache = self._load()

    def _load(self) -> Dict[str, Any]:
        settings = DEFAULT_SETTINGS.copy()
        if os.environ.get("GROQ_API_KEY"):
            settings["groq_api_key"] = os.environ.get("GROQ_API_KEY", "")
        if os.environ.get("GEMINI_API_KEY"):
            settings["gemini_api_key"] = os.environ.get("GEMINI_API_KEY", "")

        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                    settings.update(stored)
            except Exception:
                pass
        return settings

    def get_all(self, mask: bool = True) -> Dict[str, Any]:
        data = self._cache.copy()
        if mask:
            data["groq_api_key"] = mask_key(data.get("groq_api_key", ""))
            data["gemini_api_key"] = mask_key(data.get("gemini_api_key", ""))
            data["has_groq_key"] = bool(self._cache.get("groq_api_key"))
            data["has_gemini_key"] = bool(self._cache.get("gemini_api_key"))
        return data

    def save(self, new_settings: Dict[str, Any]) -> Dict[str, Any]:
        for k, v in new_settings.items():
            if k in ("groq_api_key", "gemini_api_key"):
                if v and not v.startswith("****") and "*" not in v:
                    self._cache[k] = v.strip()
            elif k in DEFAULT_SETTINGS:
                self._cache[k] = v

        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, indent=2, ensure_ascii=False)
        return self.get_all(mask=True)

    def get_groq_key(self) -> str:
        return self._cache.get("groq_api_key", "").strip()

    def get_gemini_key(self) -> str:
        return self._cache.get("gemini_api_key", "").strip()

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)


settings_manager = SettingsManager()
