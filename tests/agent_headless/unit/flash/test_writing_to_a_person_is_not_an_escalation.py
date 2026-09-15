"""V2-705 · ONE doctrine of ownership: a widget with a connector IS the source — written once, read by all.

Measured 2026-09-15 (session 878b0122). Three prompts said the opposite of the code, each in its own words:
the escalation tool's YES-list («ESCRIBIR a una persona o gestionar CON ella… el widget es solo su espejo»,
added by V2-693 two days earlier), the `widget_data` description («cancelar un COMPROMISO real… la acción va
en su sitio → escalate»), the worker's method («los widgets son solo ESPEJOS locales, NUNCA el objetivo»),
and the auditor's risk signal («¿reflejo local de una acción real no ejecutada?»). The code, meanwhile:
the agenda IS the calendar (V2-643, two-way Google sync) and `send_to` executes an order directly and opens
the engine-owned errand (V2-692). Result: «write to Kryptonite and organise a meeting» went to a shell
worker for six minutes with zero messages, and one `cancel_meeting` was executed twice by two executors.

These cases pin that the four surfaces now say the SAME thing, so the next fix to one of them cannot
silently re-open the contradiction.
"""
from __future__ import annotations

import json
import pathlib
import re

ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _tool(name: str) -> dict:
    from nucleo.flash import router
    return next(t["function"] for t in router.TOOLS if t["function"]["name"] == name)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").lower()


# ── the escalation tool ─────────────────────────────────────────────────────────────────────────────────

def test_writing_to_a_person_is_named_as_NOT_an_escalation():
    desc = _norm(_tool("escalate_to_slowbrain")["description"])
    yes, no = desc.split("no:", 1)
    assert "escribir a un" not in yes, "writing to a person is back in the YES-list (the V2-693 regression)"
    assert "send_to" in no and "escribir a un contacto" in no


def test_the_escalation_tool_no_longer_calls_the_widget_a_mirror():
    desc = _norm(_tool("escalate_to_slowbrain")["description"])
    assert "espejo" not in desc and "mirror" not in desc
    assert "sitio sin conector" in desc, (
        "what DOES escalate is a commitment made on a site with no connector — that boundary must stay named")


def test_a_calendar_appointment_is_the_widgets_business():
    desc = _norm(_tool("escalate_to_slowbrain")["description"])
    assert "la agenda es el calendario" in desc


# ── widget_data ─────────────────────────────────────────────────────────────────────────────────────────

def test_widget_data_says_the_connected_widget_is_the_source():
    desc = _norm(_tool("widget_data")["description"])
    assert "es la fuente" in desc
    assert "espejo" not in desc and "mirror" not in desc
    assert "compromiso real" not in desc, "the «real commitment → escalate» clause was the double-executor rule"


def test_widget_data_tells_the_model_that_removing_requires_naming():
    desc = _norm(_tool("widget_data")["description"])
    assert "vacío no borra nada" in desc


def test_the_catalog_still_fits_its_ceiling():
    """Every change here was paid by REPLACEMENT — the ceiling test in `test_router.py` is the authority; this is
    the same fact stated next to the doctrine it protects, so a future edit sees both at once."""
    from nucleo.flash import router
    from tests.agent_headless.unit.flash.test_router import MAX_CATALOG_CHARS
    assert len(json.dumps(router.TOOLS, ensure_ascii=False)) <= MAX_CATALOG_CHARS


# ── the worker's method ─────────────────────────────────────────────────────────────────────────────────

def test_the_worker_is_told_the_connected_widget_is_the_source():
    from nucleo import dispatch_prompts as dp
    text = _norm(dp._METHOD_BLOCK)
    assert "es la fuente" in text and "la agenda es el calendario" in text
    assert "solo espejos" not in text and "nunca el objetivo" not in text


def test_the_worker_operates_a_connected_widget_with_the_cli_never_its_web():
    from nucleo import dispatch_prompts as dp
    text = _norm(dp._METHOD_BLOCK)
    assert "nunca conduciendo su web" in text


# ── the auditor ─────────────────────────────────────────────────────────────────────────────────────────

def test_a_widget_data_op_is_not_a_risk_signal_for_the_auditor():
    from nucleo.susurro import friction
    assert friction.risky_decision({"data_done": True}) == ""
    assert friction.risky_decision({"data_done": True, "clarify": True}) == ""


def test_the_phantom_data_op_still_is():
    """The OPPOSITE case stays: chatting «done» about a named widget without acting is still audited."""
    from nucleo.susurro import friction
    assert friction.phantom_dataop  # the signal exists; its own tests pin its behaviour


# ── the four surfaces agree, structurally ───────────────────────────────────────────────────────────────

def test_no_prompt_surface_teaches_the_mirror_doctrine_any_more():
    """Source-level: the word that named the retired doctrine may survive in comments explaining WHY it was
    retired, never in a string the model reads."""
    for rel in ("nucleo/flash/router_catalog.py", "nucleo/dispatch_prompts.py"):
        src = (ENGINE / rel).read_text(encoding="utf-8")
        code = re.sub(r"(?m)^\s*#.*$", "", src)                       # drop comment lines
        strings = re.findall(r'"([^"\n]*)"', code)
        offenders = [x for x in strings if re.search(r"\bespejos?\b", x, re.I) and "solo nombra" not in x
                     and "hecho fuera" not in x.lower()]
        assert not offenders, f"{rel} still teaches the mirror doctrine: {offenders[:3]}"
