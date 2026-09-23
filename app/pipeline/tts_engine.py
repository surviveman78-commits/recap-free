import os
import sys
import time
import asyncio
import subprocess
import json
import multiprocessing as mp
import soundfile as sf
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Tuple
import edge_tts

# Dynamic candidate directories for VoxCPM repo (Windows local, Kaggle, Linux, Colab)
CANDIDATE_VOXCPM_DIRS = [
    Path(r"C:\Users\Zimmimoo\VoxCPM"),
    Path("/kaggle/working/VoxCPM"),
    Path.cwd() / "VoxCPM",
    Path.cwd().parent / "VoxCPM",
    Path.home() / "VoxCPM"
]

VOXCPM_REPO_DIR = None
for _cand in CANDIDATE_VOXCPM_DIRS:
    if _cand.exists():
        VOXCPM_REPO_DIR = _cand
        _src = _cand / "src"
        if _src.exists() and str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        elif str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break


class VoxCPMManager:
    _models = {}

    @classmethod
    def get_model(cls, device: Optional[str] = None):
        device = device or os.getenv("VOXCPM_DEVICE", "auto")
        if device not in cls._models:
            try:
                import voxcpm
                print(f"Loading VoxCPM2 model on {device}...")
                model_id = os.getenv("VOXCPM_MODEL_ID", "openbmb/VoxCPM2")
                cls._models[device] = voxcpm.VoxCPM.from_pretrained(
                    model_id,
                    load_denoiser=False,
                    device=device,
                )
                print(f"VoxCPM2 loaded successfully on {device}.")
            except Exception as e:
                print(f"Error loading VoxCPM2: {e}")
                raise RuntimeError(f"VoxCPM2 engine failed to initialize: {e}")
        return cls._models[device]


class TTSEngine:
    def __init__(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        self.progress_callback = progress_callback

    @staticmethod
    async def get_edge_catalog() -> Dict[str, Any]:
        """Fetch Edge TTS voices organized strictly by language."""
        try:
            voices = await edge_tts.list_voices()
        except Exception:
            voices = [
                {"ShortName": "my-MM-NilarNeural", "Locale": "my-MM", "Gender": "Female"},
                {"ShortName": "my-MM-ThihaNeural", "Locale": "my-MM", "Gender": "Male"},
                {"ShortName": "en-US-ChristopherNeural", "Locale": "en-US", "Gender": "Male"},
                {"ShortName": "en-US-JennyNeural", "Locale": "en-US", "Gender": "Female"}
            ]

        language_labels = {
            "my-MM": "Burmese (မြန်မာ)",
            "en-US": "English (United States)",
            "en-GB": "English (United Kingdom)",
            "th-TH": "Thai (Thailand)",
            "ja-JP": "Japanese (Japan)",
            "ko-KR": "Korean (South Korea)",
            "zh-CN": "Chinese (Mandarin, Simplified)",
            "es-ES": "Spanish (Spain)",
            "fr-FR": "French (France)",
            "de-DE": "German (Germany)",
            "it-IT": "Italian (Italy)",
            "ru-RU": "Russian (Russia)",
            "vi-VN": "Vietnamese (Vietnam)",
            "hi-IN": "Hindi (India)",
            "id-ID": "Indonesian (Indonesia)",
            "pt-BR": "Portuguese (Brazil)",
            "ar-SA": "Arabic (Saudi Arabia)"
        }

        languages_map: Dict[str, List[Dict[str, str]]] = {}

        for v in voices:
            locale = v.get("Locale", "")
            if not locale:
                continue
            if locale not in languages_map:
                languages_map[locale] = []
            gender = v.get("Gender", "")
            short_name = v.get("ShortName", "")
            languages_map[locale].append({
                "id": short_name,
                "name": f"{short_name} ({gender})"
            })

        languages_list = []
        for loc in language_labels:
            if loc in languages_map:
                languages_list.append({
                    "code": loc,
                    "name": language_labels[loc],
                    "count": len(languages_map[loc])
                })

        for loc, vlist in sorted(languages_map.items()):
            if loc not in language_labels:
                languages_list.append({
                    "code": loc,
                    "name": f"{loc}",
                    "count": len(vlist)
                })

        return {
            "languages": languages_list,
            "voices_by_language": languages_map
        }

    @staticmethod
    def get_voxcpm_voices() -> List[Dict[str, str]]:
        voices = []
        custom_dir = Path(__file__).resolve().parent.parent.parent / "data" / "custom_voices"
        if custom_dir.exists():
            for f in sorted(custom_dir.glob("*.*")):
                if f.suffix.lower() in ('.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus', '.aac', '.webm'):
                    voices.append({
                        "id": f.name,
                        "name": f"Uploaded: {f.name}",
                        "path": str(f)
                    })

        if VOXCPM_REPO_DIR and (VOXCPM_REPO_DIR / "examples").exists():
            for f in (VOXCPM_REPO_DIR / "examples").glob("*.wav"):
                voices.append({
                    "id": f.name,
                    "name": f"VoxCPM Sample: {f.name}",
                    "path": str(f)
                })

        return voices

    def _prepare_reference_audio(self, audio_path: str) -> Optional[str]:
        if not audio_path or not os.path.exists(audio_path):
            return None

        p = Path(audio_path)
        converted_wav = p.parent / f"{p.stem}_voxcpm.wav"
        if not converted_wav.exists():
            cmd = [
                "ffmpeg", "-y",
                "-i", str(p),
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                str(converted_wav)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return str(converted_wav)

    def _generate_edge_segment(self, text: str, voice: str, output_path: Path):
        """Edge TTS MUST ALWAYS use fixed pitch = +20Hz and rate = +20% with retry resilience."""
        async def _run():
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                pitch="+20Hz",
                rate="+20%"
            )
            await communicate.save(str(output_path))

        last_err = None
        for attempt in range(3):
            try:
                asyncio.run(_run())
                if output_path.exists() and output_path.stat().st_size > 0:
                    return
            except Exception as e:
                last_err = e
                time.sleep(1.0 * (attempt + 1))

        if last_err:
            raise last_err

    def _generate_voxcpm_segment(
        self,
        text: str,
        voice_path: Optional[str],
        reference_text: Optional[str],
        output_path: Path,
        device: Optional[str] = None
    ):
        """VoxCPM2 speech generation with prompt text. Edge TTS pitch/speed MUST NOT apply."""
        model = VoxCPMManager.get_model(device=device)
        generate_kwargs = {
            "text": text,
            # Lower guidance is more stable for long Burmese recap narration.
            "cfg_value": float(os.getenv("RECAP_VOXCPM_CFG", "1.6")),
            "inference_timesteps": int(os.getenv("RECAP_VOXCPM_STEPS", "20")),
            "retry_badcase": True,
            "normalize": True,
        }
        clean_ref = self._prepare_reference_audio(voice_path) if voice_path else None
        if clean_ref:
            generate_kwargs["reference_wav_path"] = clean_ref
            # Use the uploaded sample together with its exact transcript so
            # VoxCPM follows the submitted speaker more closely. The UI/API
            # require this text before a reference audio can be saved.
            if reference_text and reference_text.strip() and os.getenv("RECAP_VOXCPM_HIFI", "1") == "1":
                generate_kwargs["prompt_wav_path"] = clean_ref
                generate_kwargs["prompt_text"] = reference_text.strip()

        try:
            wav = model.generate(**generate_kwargs)
        except TypeError:
            # Compatibility fallback for older VoxCPM builds without the
            # optional retry/normalization keyword arguments.
            for key in ("retry_badcase", "normalize"):
                generate_kwargs.pop(key, None)
            wav = model.generate(**generate_kwargs)
        sample_rate = getattr(model.tts_model, "sample_rate", 24000)
        sf.write(str(output_path), wav, sample_rate)

    def _get_audio_duration(self, audio_path: Path) -> float:
        try:
            info = sf.info(str(audio_path))
            return float(info.duration)
        except Exception:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return float(res.stdout.strip() or 0.0)

    def _trim_audio_silence(self, data: np.ndarray, sr: int, thresh: float = 0.008, pad_ms: int = 25) -> np.ndarray:
        if len(data) == 0:
            return data
        abs_d = np.abs(data)
        non_silent = np.where(abs_d > thresh)[0]
        if len(non_silent) == 0:
            return data
        pad_samples = int(sr * (pad_ms / 1000.0))
        start_idx = max(0, non_silent[0] - pad_samples)
        end_idx = min(len(data), non_silent[-1] + pad_samples)
        return data[start_idx:end_idx]

    def generate(
        self,
        segments: List[Dict[str, Any]],
        output_dir: Path,
        engine: str = "edge_tts",
        voice: str = "my-MM-NilarNeural",
        voxcpm_ref_path: Optional[str] = None,
        voxcpm_ref_text: Optional[str] = None,
        voxcpm_device: Optional[str] = None
    ) -> Tuple[Path, List[Dict[str, Any]]]:
        """Run VoxCPM in a separate process; Edge TTS stays lightweight in-process."""
        if engine != "voxcpm2" or os.getenv("RECAP_VOXCPM_CHILD") == "1":
            return self._generate_impl(segments, output_dir, engine, voice, voxcpm_ref_path, voxcpm_ref_text, voxcpm_device)

        output_dir = Path(output_dir)
        result_path = output_dir / "voxcpm_worker_result.json"
        if result_path.exists():
            result_path.unlink()
        ctx = mp.get_context("spawn")
        proc = ctx.Process(
            target=_voxcpm_job_worker,
            args=(segments, str(output_dir), voice, voxcpm_ref_path, voxcpm_ref_text, voxcpm_device, str(result_path)),
        )
        proc.start()
        proc.join()
        if proc.exitcode != 0 or not result_path.exists():
            raise RuntimeError(f"VoxCPM worker failed (exit code {proc.exitcode}). Check job logs.")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result_path.unlink(missing_ok=True)
        return Path(result["audio_path"]), result["segments"]

    def _generate_impl(
        self,
        segments: List[Dict[str, Any]],
        output_dir: Path,
        engine: str = "edge_tts",
        voice: str = "my-MM-NilarNeural",
        voxcpm_ref_path: Optional[str] = None,
        voxcpm_ref_text: Optional[str] = None,
        voxcpm_device: Optional[str] = None
    ) -> Tuple[Path, List[Dict[str, Any]]]:
        """
        Generates a continuous, seamless recap narration without unnatural pauses.
        Returns (final_tts_audio_path, synced_segments_with_new_timestamps).
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        snippets_dir = output_dir / "tts_snippets"
        snippets_dir.mkdir(parents=True, exist_ok=True)

        final_tts_path = output_dir / "tts_audio.wav"

        valid_segments = [s for s in segments if s.get("text", "").strip()]
        if not valid_segments:
            sf.write(str(final_tts_path), np.zeros(44100, dtype=np.int16), 44100)
            return final_tts_path, segments

        total_segments = len(valid_segments)

        # Resolve voice reference path for VoxCPM if chosen
        ref_path = None
        if engine == "voxcpm2":
            if voxcpm_ref_path:
                if not os.path.exists(voxcpm_ref_path):
                    raise FileNotFoundError(
                        f"Selected VoxCPM reference audio is missing: {voxcpm_ref_path}"
                    )
                ref_path = voxcpm_ref_path
            else:
                raise FileNotFoundError(
                    "No VoxCPM reference audio is selected. Upload a reference audio file first."
                )

        # Step 1: Synthesize each sentence snippet
        raw_snippets = []
        for idx, seg in enumerate(valid_segments):
            text = seg.get("text", "").strip()
            seg_file = snippets_dir / f"seg_{idx:04d}.wav"

            pct = 10.0 + (idx / total_segments) * 75.0
            if self.progress_callback:
                self.progress_callback(f"အသံဖိုင် ဖန်တီးနေပါတယ်... ({idx + 1}/{total_segments})", pct)

            if engine == "voxcpm2":
                self._generate_voxcpm_segment(text, ref_path, voxcpm_ref_text, seg_file, voxcpm_device)
            else:
                self._generate_edge_segment(text, voice, seg_file)

            dur = self._get_audio_duration(seg_file)
            raw_snippets.append({
                "path": seg_file,
                "text": text,
                "duration": dur,
                "original_id": seg.get("id", idx)
            })

        if self.progress_callback:
            self.progress_callback("ဇာတ်လမ်းပြော အသံဖိုင် စီစဉ်ပေါင်းစပ်နေပါတယ်...", 90.0)

        # Step 2: Assemble into ONE continuous, seamless narration track
        # Trim leading/trailing silences and use tight 0.06s cadence so voice never pauses or halts
        pause_duration = 0.06
        target_sr = 44100
        pause_samples = int(pause_duration * target_sr)

        audio_parts = []
        synced_segments = []
        current_time = 0.0

        for idx, item in enumerate(raw_snippets):
            data, sr = sf.read(str(item["path"]))
            if data.ndim > 1:
                data = data.mean(axis=1)
            if sr != target_sr:
                num_target = int(len(data) * (target_sr / sr))
                data = np.interp(
                    np.linspace(0, len(data), num_target, endpoint=False),
                    np.arange(len(data)),
                    data
                )

            # Strip dead air at start/end of TTS snippet
            data = self._trim_audio_silence(data, target_sr, thresh=0.008, pad_ms=25)

            # Micro-fade to avoid clicking
            fade_len = min(int(target_sr * 0.004), len(data) // 4)
            if fade_len > 0:
                data[:fade_len] *= np.linspace(0, 1, fade_len)
                data[-fade_len:] *= np.linspace(1, 0, fade_len)

            start_t = current_time
            dur = len(data) / target_sr
            end_t = start_t + dur

            synced_segments.append({
                "id": item["original_id"],
                "start": round(start_t, 3),
                "end": round(end_t, 3),
                "text": item["text"]
            })

            audio_parts.append(data)
            # Add small breath pause between sentences (skip on final segment)
            if idx < len(raw_snippets) - 1:
                audio_parts.append(np.zeros(pause_samples, dtype=np.float32))
                current_time = end_t + pause_duration
            else:
                current_time = end_t

        # Concatenate into one continuous master track
        full_audio = np.concatenate(audio_parts) if audio_parts else np.zeros(target_sr, dtype=np.float32)
        peak = np.max(np.abs(full_audio)) if len(full_audio) > 0 else 0
        if peak > 0.95:
            full_audio = (full_audio / peak) * 0.92

        audio_int16 = (full_audio * 32767).astype(np.int16)
        sf.write(str(final_tts_path), audio_int16, target_sr, subtype="PCM_16")

        return final_tts_path, synced_segments



def _voxcpm_job_worker(segments, output_dir, voice, ref_path, ref_text, device, result_path):
    """Spawn-safe worker: one Python process owns one CUDA device/model."""
    os.environ["RECAP_VOXCPM_CHILD"] = "1"
    try:
        engine = TTSEngine()
        audio_path, synced = engine._generate_impl(
            segments=segments,
            output_dir=Path(output_dir),
            engine="voxcpm2",
            voice=voice,
            voxcpm_ref_path=ref_path,
            voxcpm_ref_text=ref_text,
            voxcpm_device=device,
        )
        Path(result_path).write_text(
            json.dumps({"audio_path": str(audio_path), "segments": synced}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[VoxCPM worker] {exc}", flush=True)
        raise
