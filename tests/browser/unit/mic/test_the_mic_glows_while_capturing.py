"""Mic capture glow — the mic lights up in the operator's color while capturing.

Operator 2026-09-19: the mic already grew with the voice; it must also GLOW so
capturing reads without comparing sizes. Three voices stay apart:
  GREEN (--hb-ok) = the operator capturing (this file),
  warm ORANGE     = the orb listening (services/visualizer.js),
  HELIOTROPE      = system on/active (.orbic.on).
The glow blur IS the meter: 0px at silence (invisible), up to 10px at full
level, driven by the same --vu Orb.js/DockBar.js already write.
"""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[4] / "frontend"
DESKTOP = FRONTEND / "app/styles.css"
MOBILE = FRONTEND / "mobile/app/styles.css"
VISUALIZER = FRONTEND / "app/services/visualizer.js"


def _rule(css: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, f"missing rule {selector}"
    return m.group(1)


def test_desktop_mic_glow_is_operator_green_driven_by_vu():
    """The mic halo is --hb-ok with a --vu-driven blur, next to the base halo."""
    body = _rule(DESKTOP.read_text(encoding="utf-8"), '.orbic[data-ctl="mic"].vu')
    assert "--hb-ok" in body, "operator green, not a fresh hex"
    assert "--vu" in body, "the glow blur follows the live level"
    assert "drop-shadow(0 0 4px currentColor)" in body, "the system base halo stays"


def test_desktop_glow_is_invisible_at_silence():
    """At --vu 0 the capture halo must be 0px — silence keeps exactly the old look."""
    body = _rule(DESKTOP.read_text(encoding="utf-8"), '.orbic[data-ctl="mic"].vu')
    assert re.search(r"calc\(\s*var\(--vu,\s*0\)\s*\*\s*[\d.]+px\s*\)", body), (
        "blur 0 at silence, growing with level")


def test_mobile_mic_carries_the_same_glow():
    """Same pass on the mobile dock — one meter, two shells."""
    css = MOBILE.read_text(encoding="utf-8")
    bodies = re.findall(r"\.zm-ic\[data-ctl=\"mic\"\]\.on\s*\{([^}]*)\}", css)
    assert bodies, 'missing rule .zm-ic[data-ctl="mic"].on'
    assert any("--hb-ok" in b and "--vu" in b for b in bodies)


def test_mobile_glow_reaches_only_the_mic():
    """The chat and dashboards buttons are `.zm-ic.on` too — the glow is the MIC's (review 2026-09-20).

    A bare `.zm-ic.on { filter: ... }` put a drop-shadow on all three: inert while `--vu` is only ever
    set on the mic, but a stacking context and a paint on two buttons that never asked for one, and one
    inherited `--vu` away from lighting the wrong control in the operator's green.
    """
    css = MOBILE.read_text(encoding="utf-8")
    unscoped = [b for b in re.findall(r"(?<!\])\.zm-ic\.on\s*\{([^}]*)\}", css) if "filter" in b]
    assert not unscoped, f"a filter on every active dock icon, not just the mic: {unscoped}"
    dock = (MOBILE.parent / "shell" / "DockBar.js").read_text(encoding="utf-8")
    assert '"data-ctl": "mic"' in dock, "the mic button must carry the marker the CSS is scoped to"


def test_orb_listening_color_untouched():
    """The orb keeps its warm-orange listening signal — this pass adds, not moves."""
    src = VISUALIZER.read_text(encoding="utf-8")
    assert "#FF9D3B" in src, "orb live orange must stay"


def test_system_on_color_untouched():
    """System active stays heliotrope — the mic glow must not re-tint it."""
    body = _rule(DESKTOP.read_text(encoding="utf-8"), ".orbic.on")
    assert "var(--hb-accent)" in body
