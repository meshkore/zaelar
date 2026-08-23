"""memory/model_cache.py — where the local ONNX models live on disk, and why not where fastembed puts them.

`fastembed` defaults its cache to the system TEMP directory (measured on this machine:
`/var/folders/.../T/fastembed_cache`, holding 1.8 GB — the cross-encoder plus the embedding fallback). That is
the wrong home for a multi-gigabyte artifact, and it fails in a way nobody attributes to a cache:

  - **Temp gets purged.** macOS sweeps `/var/folders/.../T` periodically and some reboots clear it outright;
    a container's temp is gone the moment it stops. So the download is not a one-time cost paid at install —
    it comes back, on a machine that already had the model, at whatever moment the sweep happened to run.
  - **The failure it produces is the loudest possible one in the quietest possible place**: the first LONG
    recall after the purge pays a full re-download inside a live turn (see `rerank_local.py` for the clock
    that now bounds that wait).
  - **It also hides the model from the operator.** Nothing under `~` or in the repo shows those gigabytes, so
    "why is my disk full" and "why did memory go cold again" have no visible cause.

So it is pinned to a real, persistent, per-USER cache instead — `~/.cache/zaelar/models` (or `XDG_CACHE_HOME`
where set, and `ZAELAR_MODEL_CACHE` to override outright).

**Deliberately NOT under `memory/_data/`**, which is where the rest of memory's local state lives: that
directory follows `ZAELAR_WORKSPACE`, and a model is a MACHINE-level artifact, not workspace data. Tying it to
the workspace would make every isolated sandbox (the use-case harness creates one per batch) start from zero
and re-download the same gigabytes — trading a periodic purge for a guaranteed one. It also keeps this module
free of any `nucleo` import, so memory owes the engine nothing for it.
"""
from __future__ import annotations

import os
import pathlib


def models_dir() -> str | None:
    """Absolute path for the local model cache, created if missing. `None` if it cannot be made.

    `None` means "no opinion": the caller passes nothing and the library keeps its own default. That is the
    honest degradation — a model in the wrong place still works, while raising here would take down recall
    over a directory."""
    override = (os.getenv("ZAELAR_MODEL_CACHE") or "").strip()
    if override:
        base = pathlib.Path(override).expanduser()
    else:
        xdg = (os.getenv("XDG_CACHE_HOME") or "").strip()
        root = pathlib.Path(xdg).expanduser() if xdg else pathlib.Path.home() / ".cache"
        base = root / "zaelar" / "models"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    return str(base)
