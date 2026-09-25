import os
import json
import shutil
from zipfile import ZipFile
from pathlib import Path
from typing import Dict, Any

# Kaggle uses /kaggle/working; local runs continue to use the repository root.
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.getenv("RECAP_CONFIG_DIR", str(BASE_DIR / "config"))).expanduser()
DATA_DIR = Path(os.getenv("RECAP_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
SETTINGS_FILE = CONFIG_DIR / "settings.json"
CUSTOM_VOICES_DIR = DATA_DIR / "custom_voices"
CUSTOM_FONTS_DIR = DATA_DIR / "custom_fonts"
BUNDLED_FONTS_DIR = BASE_DIR / "assets" / "fonts"

for directory in (CONFIG_DIR, DATA_DIR, CUSTOM_VOICES_DIR, CUSTOM_FONTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def _seed_bundled_fonts() -> None:
    """Copy tracked fonts into the writable runtime directory on first use."""
    if not BUNDLED_FONTS_DIR.exists():
        return
    for source in BUNDLED_FONTS_DIR.iterdir():
        if source.suffix.lower() in {".ttf", ".otf"}:
            target = CUSTOM_FONTS_DIR / source.name
            if not target.exists():
                shutil.copy2(source, target)
    archive = BUNDLED_FONTS_DIR / "unicode_font_styles.zip"
    if archive.is_file():
        try:
            with ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    name = member.filename.replace("\\", "/")
                    if member.is_dir() or Path(name).suffix.lower() not in {".ttf", ".otf"}:
                        continue
                    target = CUSTOM_FONTS_DIR / Path(name).name
                    if not target.exists():
                        target.write_bytes(bundle.read(member))
        except (OSError, ValueError, KeyError):
            pass


_seed_bundled_fonts()

DEFAULT_SETTINGS: Dict[str, Any] = {
    "groq_api_key": "",
    "gemini_api_key": "",
    "target_language": "my",
    "target_language_name": "Burmese (မြန်မာဘာသာ)",
    "gemini_prompt_mode": "translate",
    "ai_mode": "local",
    "voice_engine": "edge_tts",
    "edge_tts_language": "my-MM",
    "edge_tts_voice": "my-MM-NilarNeural",
    "voxcpm_voice_name": "reference_speaker.wav",
    "voxcpm_voice_path": "",
    "voxcpm_reference_text": "",
    "font_color": "#FFFFFF",
    "font_size_px": 70,
    "font_style": "Z10-Cartoon",
    "custom_font_name": "",
    "custom_font_path": "",
    "subtitle_pos_x": 50,
    "subtitle_pos_y": 82,
    "output_resolution": "1080p",
    "enable_subtitles": True,
    "auto_blur_subtitles": False,
    "auto_blur_padding_pct": 1.5,
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
        if SETTINGS_FILE.exists():
            try:
                with SETTINGS_FILE.open("r", encoding="utf-8") as f:
                    settings.update(json.load(f))
            except (OSError, ValueError, TypeError):
                pass
        # One-time compatibility migration for the old built-in defaults.
        # A deliberately selected bundled/uploaded font is left untouched.
        if settings.get("font_style") in {"Noto Sans Myanmar", "Myanmar Text", "Padauk"}:
            settings["font_style"] = DEFAULT_SETTINGS["font_style"]
            settings["font_size_px"] = DEFAULT_SETTINGS["font_size_px"]
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
        for key, value in new_settings.items():
            if key in ("groq_api_key", "gemini_api_key"):
                if value and not value.startswith("****") and "*" not in value:
                    self._cache[key] = value.strip()
            elif key in DEFAULT_SETTINGS:
                self._cache[key] = value
        SETTINGS_FILE.write_text(json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.get_all(mask=True)

    def get_groq_key(self) -> str:
        return self._cache.get("groq_api_key", "").strip()

    def get_gemini_key(self) -> str:
        return self._cache.get("gemini_api_key", "").strip()

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)


settings_manager = SettingsManager()

__all__ = ["BASE_DIR", "CONFIG_DIR", "DATA_DIR", "SETTINGS_FILE", "CUSTOM_VOICES_DIR", "CUSTOM_FONTS_DIR", "settings_manager"]
