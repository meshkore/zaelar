"""nucleo/truth.py — the product's own truth, read for a verifier (V2-776 L1).

`nucleo/verify.py` could read ONE kind of truth: a widget's declared collections, through `widgets/rows`.
Measured 2026-09-29 (four read-only maps of the brain): that reaches 3 of ~18 widgets, and the end states
the demo asks for live elsewhere — the desktop wallpaper is `config.settings.wallpaper()` and belongs to no
card; whether a card is ON SCREEN is the canvas report in `memory.state()`; «which video is playing», «which
section the document is at», «which layout the sheet shows» are scalars of a widget's `view_data()`.

Three readers, all synchronous and all fail-soft to `None` — the V2-660 rule: what cannot be read is not
false. Nothing here writes, and nothing here decides: a verifier asks, this answers.
"""
from __future__ import annotations

import importlib
import unicodedata

from loguru import logger

CANVAS_STATES = ("closed", "visible", "minimized", "maximized")


def fold(v) -> str:
    """Case and accents folded, as `widgets/rows` folds — the same equality for the same product."""
    n = unicodedata.normalize("NFKD", str(v if v is not None else ""))
    return "".join(c for c in n if not unicodedata.combining(c)).strip().lower()


def _base(wid: str) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def _instance_q(wid: str) -> str:
    """A `results::f92199-ls1` is read with its instance as `q`; a bare id reads the default view."""
    w = str(wid or "").strip().lower()
    return w.split("::", 1)[1] if "::" in w else ""


def widget_view(wid: str) -> dict | None:
    """`view_data(q)` of the widget, in-process (the same read `inbox_read` and the digests make), or None."""
    base = _base(wid)
    if not base:
        return None
    try:
        mod = importlib.import_module(f"widgets.{base}.data")
        fn = getattr(mod, "view_data", None)
        if not callable(fn):
            return None
        try:
            out = fn(q=_instance_q(wid))
        except TypeError:
            out = fn()
        return out if isinstance(out, dict) else None
    except Exception as e:  # noqa: BLE001
        logger.debug(f"truth: view of {wid} unreadable: {e}")
        return None


def widget_field(wid: str, path: str):
    """One scalar (or list) of the widget's view by dotted path. `None` when the view or the path is unreadable."""
    view = widget_view(wid)
    if view is None:
        return None
    # A widget that reports an ERROR with a value is not readable; an empty `error: ""` is healthy (the
    # markets/navegador/fotos/archivos seeds carry the key always — the harness read the KEY and called them
    # unverifiable for a month).
    if str(view.get("error") or "").strip():
        return None
    cur = view
    for part in str(path or "").split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part) - 1]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def canvas_state(wid: str) -> str | None:
    """closed · visible · minimized · maximized, from the canvas report. `open_widgets` INCLUDES minimized cards
    (demo pass 59, S1: a docked sheet counted as open), so «visible» is open minus minimized."""
    base = _base(wid)
    if not base:
        return None
    try:
        from memory import api as _memapi
        st = _memapi.state() or {}
    except Exception:  # noqa: BLE001
        return None
    opened = {_base(w) for w in (st.get("open_widgets") or [])}
    if base not in opened:
        return "closed"
    if base in {_base(w) for w in (st.get("minimized_widgets") or [])}:
        return "minimized"
    if base == _base(st.get("maximized_widget") or ""):
        return "maximized"
    return "visible"


def desktop_wallpaper() -> dict | None:
    """`{url, title}` of the persisted desktop wallpaper; `{}` when none; None when it cannot be read."""
    try:
        from config import settings as _settings
        out = _settings.wallpaper()
        return dict(out) if isinstance(out, dict) else {}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"truth: wallpaper unreadable: {e}")
        return None


def scalar_text(v) -> str:
    """What a scalar looks like for `has`/`is`: a dict is its values joined, a list its items joined."""
    if isinstance(v, dict):
        return " ".join(str(x) for x in v.values() if x not in (None, ""))
    if isinstance(v, (list, tuple)):
        return " ".join(scalar_text(x) for x in v)
    return str(v if v is not None else "")


def is_empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, (str, bytes, list, tuple, dict, set)):
        return len(v) == 0
    return False
