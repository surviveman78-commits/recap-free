import subprocess
import shutil
import re
from typing import List

_GPU_ENCODER_CHECKED = False
_GPU_ENCODER_AVAILABLE = False
_DETECTED_ENCODER = "libx264"
_ENCODER_DESC = "libx264 (CPU Fallback)"


def _detect_gpu_encoder():
    global _GPU_ENCODER_CHECKED, _GPU_ENCODER_AVAILABLE, _DETECTED_ENCODER, _ENCODER_DESC

    if _GPU_ENCODER_CHECKED:
        return

    _GPU_ENCODER_CHECKED = True

    if not shutil.which("ffmpeg"):
        _GPU_ENCODER_AVAILABLE = False
        _DETECTED_ENCODER = "libx264"
        _ENCODER_DESC = "libx264 (CPU Fallback)"
        return

    # 1. Try h264_nvenc (Standard Linux / Kaggle / Supported Windows drivers)
    try:
        test_nvenc = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.04",
            "-c:v", "h264_nvenc",
            "-f", "null", "-"
        ]
        p = subprocess.run(test_nvenc, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8)
        if p.returncode == 0:
            _GPU_ENCODER_AVAILABLE = True
            _DETECTED_ENCODER = "h264_nvenc"
            _ENCODER_DESC = "NVIDIA NVENC (GPU)"
            print("[GPU ACCELERATION] NVIDIA NVENC hardware encoding is active and verified.")
            return
    except Exception:
        pass

    # 2. Try h264_mf with hardware encoding (Windows NVIDIA RTX / DirectX MFT)
    try:
        test_mf = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.04",
            "-pix_fmt", "nv12",
            "-c:v", "h264_mf",
            "-hw_encoding", "true",
            "-f", "null", "-"
        ]
        p = subprocess.run(test_mf, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8)
        if p.returncode == 0:
            _GPU_ENCODER_AVAILABLE = True
            _DETECTED_ENCODER = "h264_mf"
            m = re.search(r"MFT name:\s*'([^']+)'", p.stderr)
            mft_name = m.group(1) if m else "GPU Hardware Encoder"
            _ENCODER_DESC = f"{mft_name} (GPU)"
            print(f"[GPU ACCELERATION] Hardware MFT encoding is active and verified: {_ENCODER_DESC}")
            return
    except Exception:
        pass

    # 3. Fallback to CPU libx264
    _GPU_ENCODER_AVAILABLE = False
    _DETECTED_ENCODER = "libx264"
    _ENCODER_DESC = "libx264 (CPU Fallback)"
    print("[GPU ACCELERATION] No hardware GPU encoder available. Using CPU libx264 fallback.")


def check_gpu_nvenc_available() -> bool:
    """Returns True if any GPU hardware-accelerated video encoder is available."""
    _detect_gpu_encoder()
    return _GPU_ENCODER_AVAILABLE


def get_video_encoder_args(cq: int = 18, crf: int = 17) -> List[str]:
    """
    Returns optimal FFmpeg video encoder arguments for high quality 4K output.
    If NVIDIA NVENC or Hardware MFT is available, uses GPU encoding for ultra-fast rendering.
    Otherwise, gracefully falls back to CPU libx264 with CRF=17.
    """
    _detect_gpu_encoder()

    if _DETECTED_ENCODER == "h264_nvenc":
        return [
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-cq", str(cq),
            "-b:v", "0",
            "-pix_fmt", "yuv420p"
        ]
    elif _DETECTED_ENCODER == "h264_mf":
        return [
            "-c:v", "h264_mf",
            "-hw_encoding", "true",
            "-rate_control", "quality",
            "-quality", "95",
            "-pix_fmt", "nv12"
        ]
    else:
        return [
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", str(crf),
            "-pix_fmt", "yuv420p"
        ]


def get_active_encoder_name() -> str:
    """Returns the name of the currently active video encoder."""
    _detect_gpu_encoder()
    return _DETECTED_ENCODER


def get_encoder_hardware_desc() -> str:
    """Returns human-readable hardware description."""
    _detect_gpu_encoder()
    return _ENCODER_DESC
