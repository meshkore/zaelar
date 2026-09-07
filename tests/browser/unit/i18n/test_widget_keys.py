#
# V2-613 — the widget-layer i18n ratchet. Mirrors the mobile shell's own key-existence check
# (tests/browser/unit/mobile/test_mobile_host_contract.mjs) for the widget catalog: any `widget.js` that calls
# `ctx.t(...)` (directly, or through a local alias like `const tr = ctx.t`) must have EVERY key it asks for in
# BOTH bundles — `t()` returns the literal key on a miss, and a key is truthy, so a silent gap renders as
# `widgets.timer.pause` on screen instead of failing anywhere loud.
#
from __future__ import annotations

import json
import re
from pathlib import Path

_ENGINE = Path(__file__).resolve().parents[4]
_WIDGETS_DIR = _ENGINE / "widgets"

# Matches `ctx.t("key")`, `tr("key")` (the alias every migrated widget uses so far), or `t("key")` — never a
# bare `t(` inside an unrelated word, hence the boundary.
_CALL_RE = re.compile(r"\b(?:ctx\.t|tr|t)\(\s*[\"']([a-zA-Z0-9_.]+)[\"']")
_FALLBACK_RE = re.compile(r"\b(?:ctx\.t|tr|t)\([^)]*\)\s*\|\|")


def _widget_js_files() -> list[Path]:
    # `_user/` forks are the OPERATOR's own customization, made AFTER their language is already known — out of
    # scope by the same reasoning V2-613's initiative states for a one-off generated widget.
    return sorted(p for p in _WIDGETS_DIR.glob("*/widget.js") if "_user" not in p.parts)


def _bundle(code: str) -> dict:
    return json.loads((_ENGINE / "i18n" / "bundles" / f"{code}.json").read_text(encoding="utf-8"))


def test_every_widget_translation_key_exists_in_both_bundles():
    en, es = _bundle("en"), _bundle("es")
    missing = {}
    for f in _widget_js_files():
        src = f.read_text(encoding="utf-8")
        keys = {m.group(1) for m in _CALL_RE.finditer(src) if m.group(1).startswith("widgets.")}
        gone = sorted(k for k in keys if k not in en or k not in es)
        if gone:
            missing[str(f.relative_to(_ENGINE))] = gone
    assert not missing, f"widget i18n keys missing from a bundle: {missing}"


def test_no_dead_or_fallback_pattern_after_a_translation_call():
    """`t()`/`ctx.t()` never returns falsy (worst case: the literal key), so `t(...) || "fallback"` is dead code
    that reads like a working fallback and never runs — the exact trap the mobile shell's own test already
    guards against (found there 2026-08-29)."""
    offenders = [str(f.relative_to(_ENGINE)) for f in _widget_js_files() if _FALLBACK_RE.search(f.read_text(encoding="utf-8"))]
    assert not offenders, f"dead `t(...) || fallback` pattern in: {offenders}"


def test_the_pilot_widgets_actually_use_ctx_t():
    """A ratchet with nothing to ratchet proves nothing — pins that at least the pilot widget migrated for
    V2-613 is actually exercised by the scan above, so a regex drift shows up as a COUNT going to zero, not as
    a silently-empty, always-green check."""
    timer_src = (_WIDGETS_DIR / "timer" / "widget.js").read_text(encoding="utf-8")
    keys = {m.group(1) for m in _CALL_RE.finditer(timer_src) if m.group(1).startswith("widgets.timer.")}
    assert len(keys) >= 8, f"expected the timer widget's translated strings, found only {sorted(keys)}"
