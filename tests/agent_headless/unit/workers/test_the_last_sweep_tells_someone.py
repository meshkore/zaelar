"""What the browser's FINAL sweep leaves in the sheet has to reach the conversation.

Measured by the harness on 2026-08-24 in three cases (guitar 49 s, hotel 42 s, flights 113 s): the rows entered the
sheet TENS OF SECONDS before the last turn and the agent kept saying «I still don't have anything».

The cause is structural and is not a one-off omission. `results.intake.push` is the rows' ONLY entry point
(V2-257) but does NOT carry a note: the caller pushes the note. Of the three callers, two push it
(`act_api._hand_over`, `owner.py`) and the third —`dispatch._finalize_web`, which performs its own final extraction
when the worker finishes or dies— wrote the rows and said nothing.

The other half, and why the test enforces it just as strongly: it must NOT report it twice. If the extraction from that
tab has already gone out in `_hand_over`'s note, the final sweep is almost the same page again, and a second note is
read as «it found more» when it found the same thing.
"""
from __future__ import annotations

import pytest

from nucleo.workers import findings
from widgets.navegador import act_api


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    empujadas = []
    monkeypatch.setattr("voice.brain_notes.push", lambda t: empujadas.append(t), raising=False)
    monkeypatch.setattr(act_api, "_HANDED", {})
    monkeypatch.setattr(findings, "_HANDED", {})
    yield empujadas


FILAS = [{"title": "Fender Stratocaster", "price": "450 €", "url": "https://x/1"},
         {"title": "Gibson Les Paul", "price": "900 €", "url": "https://x/2"}]


def test_la_barrida_final_lo_cuenta(_limpio):
    assert findings.hand_sheet_finding("nav1", FILAS, "una guitarra de segunda mano") is True
    assert len(_limpio) == 1
    nota = _limpio[0]
    assert "Fender Stratocaster" in nota and "450 €" in nota, "la nota no nombra lo que encontró"
    assert "guitarra" in nota, "la nota no dice de qué encargo habla"


def test_no_lo_cuenta_DOS_veces_si_ya_salio_por_la_otra_puerta(_limpio):
    """`act_api._HANDED` marks the tabs whose extraction has already gone out as a note. The condition is on the
    TAB and deliberately not on these rows: the final sweep is almost the same page again."""
    act_api._HANDED["nav1"] = "una-firma-cualquiera"
    assert findings.hand_sheet_finding("nav1", FILAS, "una guitarra") is False
    assert _limpio == []


def test_una_pestana_DISTINTA_no_queda_callada_por_la_de_al_lado(_limpio):
    """The symmetric defect: looking at the entire dictionary instead of THIS tab would leave a request silent because
    another one, in parallel, has already spoken."""
    act_api._HANDED["otra"] = "firma"
    assert findings.hand_sheet_finding("nav1", FILAS, "una guitarra") is True


def test_sin_filas_no_se_dice_nada(_limpio):
    """A note saying «I'm done and I have nothing» is already provided by the worker's shutdown. Here, stay silent."""
    assert findings.hand_sheet_finding("nav1", [], "una guitarra") is False
    assert findings.hand_sheet_finding("nav1", [{"nada": "util"}], "una guitarra") is False
    assert _limpio == []


def test_dice_cuantas_MAS_hay_sin_soltarlas_todas(_limpio):
    """The note enters the turn's prompt: there are three, and it says how many remain. Silently losing the
    information that there were more is the doctrine of `observability/evidence.py`."""
    muchas = FILAS + [{"title": f"Guitarra {i}", "price": "100 €"} for i in range(5)]
    findings.hand_sheet_finding("nav1", muchas, "una guitarra")
    assert "y 4 más" in _limpio[0], _limpio[0]


def test_si_no_puede_saber_si_ya_se_contó_lo_cuenta(monkeypatch, _limpio):
    """Fail-soft with good judgment: being unable to check the marker cannot mean staying silent. A repeated note is
    noise; a missing note is the operator waiting in front of a full sheet."""
    import builtins
    real = builtins.__import__

    def _boom(name, *a, **k):
        if name == "widgets.navegador.act_api":
            raise RuntimeError("no disponible")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _boom)
    assert findings.hand_sheet_finding("nav1", FILAS, "una guitarra") is True


# ── the WIRING: ensure `_finalize_web` calls it ────────────────────────────────────────────────────────────────

def test_finalize_web_llama_a_la_nota_justo_donde_escribe_las_filas():
    """AST wiring guard. The function can be perfect and still be useless if the only path that
    needed it does not call it — which is literally the defect it fixes."""
    import ast
    src = ast.parse(open("nucleo/dispatch.py", encoding="utf8").read())
    fn = next(n for n in ast.walk(src)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_finalize_web")
    llamadas = [getattr(c.func, "attr", getattr(c.func, "id", "")) for c in ast.walk(fn) if isinstance(c, ast.Call)]
    assert "push" in llamadas, "…¿ya no entrega a la hoja?"
    assert "hand_sheet_finding" in llamadas, \
        "`_finalize_web` escribe las filas en la hoja y no se lo cuenta a nadie: el operador las tiene delante " \
        "y el agente sigue diciendo que no hay nada"
