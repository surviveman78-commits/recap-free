import subprocess
import shutil
from typing import List

_GPU_ENCODER_CHECKED = False
_GPU_ENCODER_AVAILABLE = False
_DETECTED_ENCODER = "libx264"


def check_gpu_nvenc_available() -> bool:
    """
    Checks if NVIDIA NVENC hardware-accelerated video encoding is supported by
    both FFmpeg and the current machine's GPU/driver.
    Caches the result after the first check.
    """
    global _GPU_ENCODER_CHECKED, _GPU_ENCODER_AVAILABLE, _DETECTED_ENCODER

    if _GPU_ENCODER_CHECKED:
        return _GPU_ENCODER_AVAILABLE

    _GPU_ENCODER_CHECKED = True

    if not shutil.which("ffmpeg"):
        _GPU_ENCODER_AVAILABLE = False
        _DETECTED_ENCODER = "libx264"
        return False

    try:
        # 1. Check if FFmpeg has h264_nvenc compiled in
        proc = subprocess.run(
            ["ffmpeg", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        if "h264_nvenc" not in proc.stdout:
            _GPU_ENCODER_AVAILABLE = False
            _DETECTED_ENCODER = "libx264"
            return False

        # 2. Test actual NVENC hardware initialization with a 1-frame dummy test
        # (This ensures NVIDIA driver and CUDA hardware are truly operational, e.g. on Kaggle T4 or local RTX)
        test_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.04",
            "-c:v", "h264_nvenc",
            "-f", "null", "-"
        ]
        test_proc = subprocess.run(
            test_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8
        )
        if test_proc.returncode == 0:
            _GPU_ENCODER_AVAILABLE = True
            _DETECTED_ENCODER = "h264_nvenc"
            print("[GPU ACCELERATION] NVIDIA NVENC hardware encoding is active and verified.")
            return True
        else:
            _GPU_ENCODER_AVAILABLE = False
            _DETECTED_ENCODER = "libx264"
            print(f"[GPU ACCELERATION] NVENC test failed (falling back to CPU libx264): {test_proc.stderr[:120]}")
            return False

    except Exception as e:
        _GPU_ENCODER_AVAILABLE = False
        _DETECTED_ENCODER = "libx264"
        print(f"[GPU ACCELERATION] GPU check exception (using CPU fallback): {e}")
        return False


def get_video_encoder_args(cq: int = 20, crf: int = 18) -> List[str]:
    """
    Returns optimal FFmpeg video encoder arguments.
    If GPU (NVIDIA NVENC) is available, uses h264_nvenc for ultra-fast rendering.
    Otherwise, gracefully falls back to CPU libx264.
    """
    if check_gpu_nvenc_available():
        return [
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-cq", str(cq),
            "-pix_fmt", "yuv420p"
        ]
    else:
        return [
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", str(crf),
            "-pix_fmt", "yuv420p"
        ]


def get_active_encoder_name() -> str:
    """Returns the name of the currently active video encoder ('h264_nvenc' or 'libx264')."""
    check_gpu_nvenc_available()
    return _DETECTED_ENCODER
