"""V2-605 — a CAPTCHA is an offer to make, not a dead end to narrate.

Session `43b7bf79`, 2026-09-07. The operator, watching a worker drive TheFork, offered the one thing that
actually unblocks an anti-bot wall:

    o me abres el navegador para que yo lo vea, y te confirme el captcha, o si no, creo que no vas a poder

`authenticate_web` — which opens the REAL browser window on his machine for exactly this — was in that turn's
tool list, and in every turn's tool list. It was described as a LOGIN tool and nothing else, so from the model's
seat there was no relation between «pass this captcha for you» and the capability that does it. **An undeclared
capability is one the model narrates instead of using** (V2-540), and this one was declared for half its job.

V2-835 took the wall NOTE's half away: a note that sent the conversation to the login tool made two actors decide on
one errand and offered a window where none could reach him. The note now only informs
(`test_a_window_nobody_sees_is_never_offered.py`); the tool keeps declaring the captcha case for when HE offers.
"""
from pathlib import Path

import pytest

from widgets.navegador import tasks

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _registry():
    _saved = dict(tasks._tasks)
    tasks._tasks.clear()
    yield
    tasks._tasks.clear()
    tasks._tasks.update(_saved)


# ── 1) the tool DECLARES the captcha case ─────────────────────────────────────────────────────────────────────

def _auth_tool() -> dict:
    from nucleo.flash import router_catalog
    for t in router_catalog.TOOLS:
        fn = t.get("function") or t
        if fn.get("name") == "authenticate_web":
            return fn
    raise AssertionError("authenticate_web no está en el catálogo")


def test_the_handoff_tool_declares_the_captcha_case_not_only_login():
    desc = _auth_tool()["description"].lower()
    assert "captcha" in desc
    assert "bloquead" in desc or "muro" in desc


def test_the_handoff_tool_says_it_is_not_show_widget():
    """The measured wrong answer. Showing a card lets him LOOK; only this lets him TOUCH."""
    assert "show_widget" in _auth_tool()["description"]


def test_the_hard_exclusions_survive():
    """Music and messaging connect from their own card, never through the browser — unchanged."""
    desc = _auth_tool()["description"]
    assert "MÚSICA" in desc and "MENSAJERÍA" in desc and "JAMÁS" in desc


# ── 2) both channels resolve the card the same way (V2-539's parallel-channel trap) ───────────────────────────

#: Where each channel calls the shared decision: voice in `widget_intent`, text in `show_target` (the body
#: extracted from `probe.py` on this pass's ratchet). Named per CHANNEL, not per file — this very guard went red
#: when the extraction moved the call, which is the behaviour a source guard has to have (V2-555).
@pytest.mark.parametrize("rel", ["voice/engine/llm/providers/widget_intent.py"])   # the text channel went (refactor2710-01)
def test_both_channels_pass_the_last_spoken_line_to_the_resolver(rel):
    """The anti-loop hangs on `last_spoken`. A channel that does not pass it goes on asking forever, and it does
    so in GREEN — the resolver still answers, it just never learns it already asked."""
    import ast
    tree = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) == "resolve_show"]
    assert calls, f"{rel} ya no llama a resolve_show — ¿se movió el canal?"
    for c in calls:
        n_args = len(c.args) + len(c.keywords)
        assert n_args >= 4, (f"{rel}:{c.lineno} llama a resolve_show con {n_args} argumentos: sin `last_spoken` "
                             f"este canal repite la pregunta para siempre, y lo hace en VERDE")
