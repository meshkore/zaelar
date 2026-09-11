"""The NATIVE "choose a folder" dialog — self-host only (V2-672).

The operator, on the first-run flow: *«en la versión local haría falta un selector de archivos para ver dónde
el usuario quiere guardar los archivos de Zaelar… no le vamos a permitir ir por las carpetas diciendo a cuál
le damos permiso, sino que le podemos obligar a escoger una carpeta donde se van a guardar los archivos
descargados, generados, etc.»*

WHY A SERVER-SIDE DIALOG AT ALL. The browser cannot answer this question. `<input webkitdirectory>` hands
over file entries with no absolute path, and `showDirectoryPicker()` hands over a handle that only that
browser tab can use — neither gives the engine a path it can write to. A self-hosted engine runs on the same
machine as the person using it, so the OS picker is the one thing that can.

AND WHY IT IS NOT THE ONLY WAY IN. This is best-effort by construction: there may be no display (a headless
box, a container, SSH), no `zenity`/`kdialog` installed, or the platform may be one we have no recipe for.
Every one of those answers `{"ok": False, "reason": "unavailable"}` and the caller falls back to a typed
path — which goes through the SAME validator (`paths.check_base`), so nothing depends on which door was used.

NEVER IN THE CLOUD: there the Volume IS the storage, the process has no desktop to draw on, and the caller
(`library/server_api.py`) refuses before reaching this module.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

_TIMEOUT_S = 180.0     # a person browsing their disk is slow; the cap is against a dialog nobody ever answers


def available() -> bool:
    """Whether a picker can plausibly be drawn. Cheap and honest: presence of the tool, plus a DISPLAY on
    the platforms that need one — a `zenity` on a headless box hangs instead of failing."""
    if sys.platform == "darwin":
        return bool(shutil.which("osascript"))
    if sys.platform.startswith("win"):
        return bool(shutil.which("powershell") or shutil.which("powershell.exe"))
    if not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")):
        return False
    return bool(shutil.which("zenity") or shutil.which("kdialog"))


def _argv(prompt: str) -> list[str] | None:
    if sys.platform == "darwin":
        # `choose folder` returns an alias; `POSIX path of` turns it into the path we can actually use.
        # The prompt is passed as a quoted AppleScript string — it is OUR text, never the operator's.
        return ["osascript", "-e",
                f'POSIX path of (choose folder with prompt "{prompt}")']
    if sys.platform.startswith("win"):
        ps = shutil.which("powershell") or shutil.which("powershell.exe")
        return [ps, "-NoProfile", "-Command",
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "if ($d.ShowDialog() -eq 'OK') { Write-Output $d.SelectedPath }"]
    if shutil.which("zenity"):
        return ["zenity", "--file-selection", "--directory", f"--title={prompt}"]
    if shutil.which("kdialog"):
        return ["kdialog", "--getexistingdirectory", os.path.expanduser("~")]
    return None


def choose(prompt: str = "Choose a folder for Zaelar's files") -> dict:
    """Open the OS folder picker and return what came back, VALIDATED.

    `{"ok": True, "path": "/…"}` · `{"ok": False, "reason": "cancelled|unavailable|<validator reason>"}`.
    Cancelling is not an error and says so, because the caller offers a «skip» and must not paint a failure
    over a deliberate choice not to answer.
    """
    if not available():
        return {"ok": False, "reason": "unavailable"}
    argv = _argv(prompt)
    if not argv:
        return {"ok": False, "reason": "unavailable"}
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout"}
    except Exception:  # noqa: BLE001
        return {"ok": False, "reason": "unavailable"}
    picked = (proc.stdout or "").strip()
    if proc.returncode != 0 or not picked:
        return {"ok": False, "reason": "cancelled"}
    from . import paths
    got = paths.check_base(picked)
    return {"ok": True, "path": got["path"]} if got["ok"] else {"ok": False, "reason": got["reason"]}


__all__ = ["available", "choose"]
