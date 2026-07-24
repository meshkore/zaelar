"""Hardware acceleration detection — pick the fastest LOCAL backend available.

Cross-platform + multi-device by design:
    Apple Silicon → "metal" (MLX)      · great experience on Mac
    NVIDIA GPU    → "cuda"             · faster-whisper / CTranslate2
    anything else → "cpu"              · universal fallback, works everywhere

Detection runs at startup; an explicit preference (``ZAELAR_WHISPER_DEVICE`` /
config) overrides it; if the preferred backend isn't usable we fall back down the
chain (metal → cuda → cpu). AMD/ROCm has no bundled STT backend yet, so those
machines land on CPU — adding a whisper.cpp-Vulkan/ROCm backend is a welcome PR:
add a detector here + a branch in the STT factory.

Ported from voice-lab-2 (INI-012 upgrade); only the logger name changed.
"""
from __future__ import annotations

import logging
import platform
import shutil

logger = logging.getLogger("zaelar.accel")

# fastest → universal. Devices we actually have a local STT backend for.
_PRIORITY = ["metal", "cuda", "cpu"]


def is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64")


def has_metal() -> bool:
    if not is_apple_silicon():
        return False
    try:
        import mlx.core as mx

        m = getattr(mx, "metal", None)
        return bool(m.is_available()) if m and hasattr(m, "is_available") else True
    except Exception:
        return False


def has_cuda() -> bool:
    try:
        import torch  # optional

        if torch.cuda.is_available():
            return True
    except Exception:
        pass
    return shutil.which("nvidia-smi") is not None


def has_rocm() -> bool:
    try:
        import torch

        if getattr(torch.version, "hip", None):
            return True
    except Exception:
        pass
    return shutil.which("rocminfo") is not None


def ram_gb() -> float | None:
    try:
        import psutil

        return round(psutil.virtual_memory().total / 1e9, 1)
    except Exception:
        return None


def detect() -> dict:
    d = {
        "platform": platform.system(),
        "arch": platform.machine(),
        "apple_silicon": is_apple_silicon(),
        "metal": has_metal(),
        "cuda": has_cuda(),
        "rocm": has_rocm(),
        "ram_gb": ram_gb(),
    }
    if d["rocm"] and "cuda" not in available_devices():
        logger.info("AMD/ROCm GPU detected but no ROCm STT backend bundled — using CPU. PRs welcome.")
    return d


def available_devices() -> list[str]:
    devs = []
    if has_metal():
        devs.append("metal")
    if has_cuda():
        devs.append("cuda")
    devs.append("cpu")  # always available
    return devs


def pick_device(preference: str = "auto") -> str:
    """Resolve the STT device: honor an explicit preference, else auto by priority."""
    avail = available_devices()
    pref = (preference or "auto").strip().lower()
    if pref and pref != "auto":
        if pref in avail:
            return pref
        logger.warning("preferred STT device %r unavailable (have: %s) — auto-selecting", pref, avail)
    for dev in _PRIORITY:
        if dev in avail:
            return dev
    return "cpu"
