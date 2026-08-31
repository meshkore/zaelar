"""V2-343 — we captured every 4 seconds and displayed every 162: the browser step reaches the tab.

Measured in session `7575e81a` (2026-08-26), over the 21.6 minutes of the `search-buy-used-car` task:

    🧭 browser (browser + parsing)     292 events   one every   4 s   → log ONLY
    💬 worker (what it narrates)        82 events   one every  16 s   → log ONLY
    · step                              34 events   one every  38 s   → log ONLY
    phase → PROCESS tab                  8 events   one every 162 s   → the only one on screen

The engine already knew twenty times more than it displayed. And —this matters so we do not fix what was not
broken— **dedup was not eating anything**: the 8 that arrived were the 8 distinct and informative ones («14
results on the page», «Coches.net does not respond → I try Wallapop»). The defect was that nobody sent the rest.

The two paths were blocked separately:
  · `_say_phase` had ONE caller, `found()` after extraction. Not the 36 navigations, 27 clicks, and 13 scrolls.
  · the worker stream sees every step, but it drives the browser through Bash → `where=sistema, action=ejecuta`
    → «executing a step», a CONSTANT that dedup collapses to one line. And rightly so.

Why this is a PRODUCT defect and not an instrumentation one: while the screen has nothing new to say, the only
thing the turn can answer is «I am still working on it» — which is exactly what the judge scores as vagueness
round after round. The frequency of the information IS the information.
"""
import asyncio

import pytest

from nucleo import sheets as SH
from widgets.navegador import act_api


class _Tab:
    async def ensure(self):
        return None

    async def navigate(self, url, **kw):
        return {"ok": True, "url": url}

    async def snapshot_for_agent(self):
        return {"url": "https://x", "title": "t"}

    page = None


@pytest.fixture
def dicho(monkeypatch):
    """Collects what the bridge sends to the tab, through the REAL path."""
    out = []
    monkeypatch.setattr(act_api, "_emit_nav", lambda *a, **k: None)
    monkeypatch.setattr(act_api, "_say_phase", lambda tid, frase: out.append(frase) if frase else None)
    from widgets.navegador import owner
    monkeypatch.setitem(owner._task_browsers, "t1", _Tab())
    return out


def _act(action, args):
    return asyncio.run(act_api.navegador_act(task_id="t1", action=action, args=args))


# ── the phrase for each step ────────────────────────────────────────────────────────────────────────────────
def test_navigating_says_WHERE_it_is_going(dicho):
    """The host is what makes one navigation different from the next — and therefore what gets past dedup."""
    _act("navigate", {"url": "https://www.coches.net/ocasion/?cf=diésel"})
    assert dicho and "coches.net" in dicho[0]


def test_two_different_sites_are_two_different_lines(dicho):
    """The measured case: three portals in a task. If the phrase did not include the host, they would be one line."""
    _act("navigate", {"url": "https://www.coches.net"})
    _act("navigate", {"url": "https://www.milanuncios.com/coches-de-segunda-mano/"})
    assert len(set(dicho)) == 2, f"dos sitios distintos tienen que sonar distinto: {dicho}"


def test_the_parsing_step_announces_itself(dicho):
    """The operator asked to see PARSING by name. Extract says that it extracts; how many came out is stated by
    `found()` right afterward, and the two phrases are intentionally different: «I am starting» and «this came out»."""
    _act("extract", {"limit": 14})
    assert any("página" in f for f in dicho)


def test_an_empty_action_says_nothing(dicho):
    """SENSITIVITY: increasing the frequency cannot turn into talking for the sake of talking."""
    _act("", {})
    assert dicho == []


# ── the counterweight: dedup continues to protect ──────────────────────────────────────────────────────────
class _Rec:
    def __init__(self):
        self.phases = []


def test_three_identical_steps_are_still_ONE_line():
    """SENSITIVITY, and it is the half that keeps this fix from becoming noise: three consecutive scrolls
    produce «scrolling through the page» three times, and three identical lines look like progress without being it."""
    r = _Rec()
    for _ in range(3):
        SH.record_phase(r, "recorriendo la página", 40)
    assert len(r.phases) == 1


def test_but_a_line_that_CHANGED_gets_through():
    """The other direction: without this, «fixed» and «dedup eats everything» get confused."""
    r = _Rec()
    SH.record_phase(r, "entrando en coches.net", 40)
    SH.record_phase(r, "14 resultados en la página", 40)
    SH.record_phase(r, "entrando en milanuncios.com", 40)
    assert [p["s"] for p in r.phases] == [
        "entrando en coches.net", "14 resultados en la página", "entrando en milanuncios.com"]


# ── WIRING guard: the decision without a caller is the fix that does not exist (V2-199) ─────────────────────
def test_the_bridge_actually_calls_it_before_dispatching():
    """About the SOURCE without comments: the notice comes BEFORE executing the action, because what the operator
    needs is «entering coches.net» WHILE it enters. Checking only the helper would pass with the call
    deleted — which is exactly the state in which this file found the code."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("widgets/navegador/act_api.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    i = src.index("async def navegador_act")
    cuerpo = src[i:i + 1200]
    assert "_say_phase(task_id, _phase_for_action(action, args))" in cuerpo
    assert cuerpo.index("_say_phase(task_id, _phase_for_action") < cuerpo.index("from widgets.navegador import owner")
