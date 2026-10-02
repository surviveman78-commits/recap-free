"""Small process-local pool for assigning one CUDA device per inference job."""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator, Optional


def cuda_device_count() -> int:
    """Return visible CUDA device count without making CUDA mandatory locally."""
    try:
        import torch
        if not torch.cuda.is_available():
            return 0
        return int(torch.cuda.device_count())
    except Exception:
        return 0


class CudaDevicePool:
    def __init__(self) -> None:
        count = cuda_device_count()
        forced = os.getenv("RECAP_CUDA_DEVICE_COUNT", "").strip()
        if forced.isdigit():
            count = min(count, int(forced)) if count else int(forced)
        self.devices = [f"cuda:{index}" for index in range(max(0, count))]
        self._available = set(self.devices)
        self._condition = threading.Condition()
        self._cpu_fallback_lock = threading.Lock()

    def try_acquire(self) -> Optional[str]:
        with self._condition:
            if not self._available:
                return None
            device = sorted(self._available)[0]
            self._available.remove(device)
            return device

    def release(self, device: Optional[str]) -> None:
        if device not in self.devices:
            return
        with self._condition:
            self._available.add(device)
            self._condition.notify_all()

    @contextmanager
    def device(self) -> Iterator[Optional[str]]:
        if not self.devices:
            with self._cpu_fallback_lock:
                yield None
            return
        selected = self.try_acquire()
        if selected is None and self.devices:
            with self._condition:
                while not self._available:
                    self._condition.wait(timeout=1.0)
                selected = sorted(self._available)[0]
                self._available.remove(selected)
        try:
            yield selected
        finally:
            self.release(selected)

    def status(self) -> dict:
        with self._condition:
            return {
                "devices": list(self.devices),
                "available": sorted(self._available),
                "busy": sorted(set(self.devices) - self._available),
            }


cuda_pool = CudaDevicePool()

__all__ = ["cuda_device_count", "CudaDevicePool", "cuda_pool"]
