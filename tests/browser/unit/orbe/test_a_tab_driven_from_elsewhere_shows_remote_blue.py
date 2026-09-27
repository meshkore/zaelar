"""A tab whose voice session is held elsewhere shows the ⏻ in remote-control BLUE, blinking — not the amber fault.

Operator, 2026-09-27, watching his own tab while an agent drove the engine remotely: the blinking ⏻ is right, and
blue is the colour of every remote-control indicator. Before this, «another session holds the voice» painted
`stalled` — the amber alarm meant for a dead agent — though nothing was broken.
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
APP = ROOT / "frontend" / "app"


def _code(p):
    return "\n".join(s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines())
                     if s and not s.startswith("//"))


def test_the_state_is_remote_while_another_session_holds_the_voice():
    store = _code(APP / "core" / "store.js")
    body = store[store.index("export const agentState"):store.index("export const agentLive")]
    assert 'if (remoteHeld()) return "remote";' in body
    assert body.index('return "live"') < body.index('return "remote"') < body.index('return "stalled"'), \
        "a live session wins; remote is decided before the stalled fallback"


def test_the_blocked_start_marks_it_and_a_real_start_clears_it():
    s = _code(APP / "services" / "session-lk.js")
    blocked = s[s.index('t("voice.session_open_other_tab")'):s.index("_blockedRetry = setTimeout")]
    assert "store.setRemoteHeld(true)" in blocked
    assert "store.setStarted(true); store.setRemoteHeld(false);" in s


def test_the_power_button_is_blue_and_blinks():
    css = (APP / "styles.css").read_text(encoding="utf-8")
    rule = re.search(r"\.orbic\.pwr-remote\{([^}]*)\}", css)
    assert rule and "var(--hb-remote)" in rule.group(1) and "animation:" in rule.group(1)
    pal = (APP / "core" / "palette.css").read_text(encoding="utf-8")
    assert pal.count("--hb-remote:") >= 2 and "--hb-remote-ink:#FFFFFF" in pal, "dark and light themes, white ink"


def test_its_title_is_translated():
    for lang in ("es", "en"):
        b = json.loads((ROOT / "i18n" / "bundles" / f"{lang}.json").read_text(encoding="utf-8"))
        assert b.get("orb.power_remote"), lang
