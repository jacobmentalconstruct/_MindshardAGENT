"""Resource monitor — polls CPU/RAM/GPU metrics for the right panel.

Uses psutil for CPU/RAM. GPU/VRAM detection is best-effort via
nvidia-smi subprocess call. Falls back gracefully if unavailable.
GPU polling runs in a background thread to avoid blocking the UI.
"""

import subprocess
import re
import threading
from typing import NamedTuple

from src.core.runtime.runtime_logger import get_logger

log = get_logger("resource_monitor")


class ResourceSnapshot(NamedTuple):
    cpu_percent: float
    ram_used_gb: float
    ram_total_gb: float
    gpu_available: bool
    vram_used_gb: float
    vram_total_gb: float


def poll_resources() -> ResourceSnapshot:
    """Poll current system resource usage."""
    cpu = _get_cpu()
    ram_used, ram_total = _get_ram()
    gpu_avail, vram_used, vram_total = _get_gpu()

    return ResourceSnapshot(
        cpu_percent=cpu,
        ram_used_gb=ram_used,
        ram_total_gb=ram_total,
        gpu_available=gpu_avail,
        vram_used_gb=vram_used,
        vram_total_gb=vram_total,
    )


def _get_cpu() -> float:
    try:
        import psutil
        return psutil.cpu_percent(interval=None)
    except ImportError:
        return 0.0


def _get_ram() -> tuple[float, float]:
    try:
        import psutil
        mem = psutil.virtual_memory()
        return mem.used / (1024**3), mem.total / (1024**3)
    except ImportError:
        return 0.0, 0.0


_gpu_cache: tuple[bool, float, float] = (False, 0.0, 0.0)
_gpu_lock = threading.Lock()
_gpu_probe_running = False


def _probe_gpu_async() -> None:
    global _gpu_cache, _gpu_probe_running
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,nounits,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            line = result.stdout.strip().split("\n")[0]
            used_mb, total_mb = [float(x.strip()) for x in line.split(",")]
            with _gpu_lock:
                _gpu_cache = (True, used_mb / 1024, total_mb / 1024)
    except Exception:
        pass
    finally:
        global _gpu_probe_running
        _gpu_probe_running = False


def _get_gpu() -> tuple[bool, float, float]:
    """Best-effort GPU/VRAM — launches a background probe and returns cached result."""
    global _gpu_probe_running
    if not _gpu_probe_running:
        _gpu_probe_running = True
        threading.Thread(target=_probe_gpu_async, daemon=True, name="gpu-probe").start()
    with _gpu_lock:
        return _gpu_cache
