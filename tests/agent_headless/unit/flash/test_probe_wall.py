"""V2-461 — the conversation over the API is also VISIBLE: the text channel renders the chat wall.

Operator rule (2026-08-28), after watching an unattended run drive the agent with the chat blank:
“if operating by voice, it is transcribed into the chat, and if operating by chat, the text is visible, whether it is done
manually on the chat widget or whether we are handling the conversation through the API.”

This was missing because this channel was born as a HEADLESS surface (V2-032): nobody was going to watch. That stopped being true the
day the studio agents got a fixed port so the operator could watch them work — and an agent
working silently is indistinguishable from one that is hung.
"""
from __future__ import annotations

import asyncio
import pathlib

import pytest

from nucleo.flash import probe_api

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _sin_detector_de_idioma(monkeypatch):
    """`say()` is the HTTP EDGE, and that is where the first-start detector (V2-170) lives; it PERSISTS the language
    in `settings.json`. In a unit test, that breaks the suite invariant (“the settings file
    starts empty”, `conftest.py`) — and does so in an order-dependent way, which is the worst way. It is
    disabled here: these cases measure the WALL, not detection."""
    import i18n.init.detect as _d
    monkeypatch.setattr(_d, "ensure_for_text", lambda *a, **k: None, raising=False)


def _capture(monkeypatch) -> list[dict]:
    """The wall is fed by the observer, so it is measured there rather than in a log (`loguru` does not go through the
    standard logging system: a `caplog` here is EMPTY, and the test would certify the opposite of what it says)."""
    seen: list[dict] = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit",
                        lambda kind, label, text="", role="", extra=None:
                        seen.append({"kind": kind, "label": label, "text": text, "role": role,
                                     "extra": extra or {}}))
    return seen


# ── what reaches the wall ─────────────────────────────────────────────────────────────────────────────────
def test_los_DOS_lados_de_la_conversacion_salen(monkeypatch):
    seen = _capture(monkeypatch)
    probe_api._wall("user", "enséñame una foto del Amalfi")
    probe_api._wall("agent", "Te las busco ahora mismo.")
    assert [e["extra"].get("wall") for e in seen] == ["you", "agent"]
    assert [e["role"] for e in seen] == ["user", "assistant"]
    assert seen[0]["text"] == "enséñame una foto del Amalfi"


def test_se_marca_con_un_CAMPO_y_no_con_el_texto_del_label(monkeypatch):
    """The frontend distinguishes by `wall`. A substring comparison on the label would be a contract that
    cannot be seen from either side and that breaks the day someone improves the wording."""
    seen = _capture(monkeypatch)
    probe_api._wall("user", "hola")
    assert seen[0]["extra"]["wall"] == "you"
    assert seen[0]["kind"] == "brain", "va por una familia a la que el muro ya está suscrito"


def test_NO_sale_como_transcript(monkeypatch):
    """The other branch rendered by the wall ALSO feeds the browser's voice-command shortcut
    (`handleWidgetVoice`). A probe turn saying “close the calendar” would execute TWICE: once through the
    channel, which already executes actions, and once through the screen. Showing a conversation cannot change what it
    does."""
    seen = _capture(monkeypatch)
    probe_api._wall("user", "cierra la agenda")
    assert all(e["kind"] != "transcript" for e in seen)


def test_un_turno_mudo_no_pinta_una_burbuja_vacia(monkeypatch):
    seen = _capture(monkeypatch)
    for vacio in ("", "   ", None):
        probe_api._wall("agent", vacio)
    assert seen == []


def test_enseñar_la_conversacion_JAMAS_tumba_el_turno(monkeypatch):
    """The wall is a window into the turn, not part of it."""
    import voice.observer as obs

    def _boom(*a, **k):
        raise RuntimeError("el bus del observador está caído")

    monkeypatch.setattr(obs, "emit", _boom)
    probe_api._wall("user", "esto no puede reventar")     # does not raise


# ── order matters ────────────────────────────────────────────────────────────────────────────────────
def test_lo_PEDIDO_se_pinta_ANTES_de_ejecutar_el_turno(monkeypatch):
    """If the operator's line were rendered at the end, the screen would be silent precisely while the agent
    works — which is the only time anyone watches it."""
    orden: list[str] = []
    monkeypatch.setattr(probe_api, "_wall", lambda role, text: orden.append(f"wall:{role}"))

    async def _run_turn(text, **kw):
        orden.append("turno")
        return {"ok": True, "reply": ["Te las busco ahora mismo."]}

    monkeypatch.setattr(probe_api, "run_turn", _run_turn)
    asyncio.run(probe_api.say(text="una foto del Amalfi", session="t", ingest=False,
                              prompt=False, model="", execute=False))
    assert orden == ["wall:user", "turno", "wall:agent"]


def test_la_respuesta_es_una_LISTA_de_frases_y_se_UNE(monkeypatch):
    """`run_turn` returns `reply` as a list (a turn can say several sentences). Calling `str()` on it
    would render `['Te las busco ahora mismo.']` on the wall, including brackets and quotation marks."""
    dicho: list[str] = []
    monkeypatch.setattr(probe_api, "_wall", lambda role, text: dicho.append(text) if role == "agent" else None)

    async def _run_turn(text, **kw):
        return {"ok": True, "reply": ["Te las busco ahora mismo.", "Son 12."]}

    monkeypatch.setattr(probe_api, "run_turn", _run_turn)
    asyncio.run(probe_api.say(text="x", session="t", ingest=False, prompt=False, model="", execute=False))
    assert dicho == ["Te las busco ahora mismo. Son 12."]
    assert "[" not in dicho[0]


# ── the other half, which lives in the browser ─────────────────────────────────────────────────────────────
def test_el_frontend_lee_ESE_campo():
    """Wiring up only one side does not fail noisily: it fails by producing nothing, which is the defect being
    fixed. The source is checked because the contract spans two files in two languages."""
    js = (ENGINE / "frontend" / "app" / "services" / "sse.js").read_text(encoding="utf-8")
    assert 'd.kind === "brain" && d.wall' in js
    assert 'd.wall === "you"' in js and "pushChat" in js
