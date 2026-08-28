"""V2-461 — la conversación por API también SE VE: el canal de texto pinta el muro de chat.

Norma del operador (2026-08-28), mirando una ronda desatendida conducir al agente con el chat en blanco:
«si se opera por voz se transcribe al chat, y si se opera por chat se ve el texto, tanto si se hace
manualmente sobre el widget del chat como si estamos manejando la conversación a través de la API».

Faltaba porque este canal nació como superficie HEADLESS (V2-032): nadie iba a mirar. Dejó de ser verdad el
día que los agentes del plató tuvieron puerto fijo para que el operador los mirara trabajar — y un agente
que trabaja en silencio es indistinguible de uno colgado.
"""
from __future__ import annotations

import asyncio
import pathlib

from nucleo.flash import probe_api

ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _capture(monkeypatch) -> list[dict]:
    """El muro se alimenta del observador, así que se mide ahí y no en un log (`loguru` no pasa por el
    logging estándar: un `caplog` aquí pasa VACÍO y el caso certifica lo contrario de lo que dice)."""
    seen: list[dict] = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit",
                        lambda kind, label, text="", role="", extra=None:
                        seen.append({"kind": kind, "label": label, "text": text, "role": role,
                                     "extra": extra or {}}))
    return seen


# ── lo que sale al muro ─────────────────────────────────────────────────────────────────────────────────
def test_los_DOS_lados_de_la_conversacion_salen(monkeypatch):
    seen = _capture(monkeypatch)
    probe_api._wall("user", "enséñame una foto del Amalfi")
    probe_api._wall("agent", "Te las busco ahora mismo.")
    assert [e["extra"].get("wall") for e in seen] == ["you", "agent"]
    assert [e["role"] for e in seen] == ["user", "assistant"]
    assert seen[0]["text"] == "enséñame una foto del Amalfi"


def test_se_marca_con_un_CAMPO_y_no_con_el_texto_del_label(monkeypatch):
    """El frontend distingue por `wall`. Una comparación de subcadenas sobre el label sería un contrato que
    no se ve desde ninguno de los dos lados, y que se rompe el día que alguien mejora la redacción."""
    seen = _capture(monkeypatch)
    probe_api._wall("user", "hola")
    assert seen[0]["extra"]["wall"] == "you"
    assert seen[0]["kind"] == "brain", "va por una familia a la que el muro ya está suscrito"


def test_NO_sale_como_transcript(monkeypatch):
    """La otra rama que el muro pinta alimenta ADEMÁS el atajo de órdenes por voz del navegador
    (`handleWidgetVoice`). Un turno del probe que diga «cierra la agenda» se ejecutaría DOS veces: una por el
    canal, que ya ejecuta acciones, y otra por la pantalla. Enseñar una conversación no puede cambiar lo que
    hace."""
    seen = _capture(monkeypatch)
    probe_api._wall("user", "cierra la agenda")
    assert all(e["kind"] != "transcript" for e in seen)


def test_un_turno_mudo_no_pinta_una_burbuja_vacia(monkeypatch):
    seen = _capture(monkeypatch)
    for vacio in ("", "   ", None):
        probe_api._wall("agent", vacio)
    assert seen == []


def test_enseñar_la_conversacion_JAMAS_tumba_el_turno(monkeypatch):
    """El muro es una ventana al turno, no parte de él."""
    import voice.observer as obs

    def _boom(*a, **k):
        raise RuntimeError("el bus del observador está caído")

    monkeypatch.setattr(obs, "emit", _boom)
    probe_api._wall("user", "esto no puede reventar")     # no lanza


# ── el orden importa ────────────────────────────────────────────────────────────────────────────────────
def test_lo_PEDIDO_se_pinta_ANTES_de_ejecutar_el_turno(monkeypatch):
    """Si la línea del operador se pintara al final, la pantalla estaría muda justo mientras el agente
    trabaja — que es el único rato en el que se mira."""
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
    """`run_turn` devuelve `reply` como lista (un turno puede decir varias frases). Un `str()` sobre ella
    pintaría en el muro `['Te las busco ahora mismo.']`, corchetes y comillas incluidos."""
    dicho: list[str] = []
    monkeypatch.setattr(probe_api, "_wall", lambda role, text: dicho.append(text) if role == "agent" else None)

    async def _run_turn(text, **kw):
        return {"ok": True, "reply": ["Te las busco ahora mismo.", "Son 12."]}

    monkeypatch.setattr(probe_api, "run_turn", _run_turn)
    asyncio.run(probe_api.say(text="x", session="t", ingest=False, prompt=False, model="", execute=False))
    assert dicho == ["Te las busco ahora mismo. Son 12."]
    assert "[" not in dicho[0]


# ── la otra mitad, que vive en el navegador ─────────────────────────────────────────────────────────────
def test_el_frontend_lee_ESE_campo():
    """Cablear un solo lado no falla con ruido: falla saliendo vacío, que es el defecto que se está
    arreglando. Se comprueba la fuente porque el contrato son dos ficheros en dos lenguajes."""
    js = (ENGINE / "frontend" / "app" / "services" / "sse.js").read_text(encoding="utf-8")
    assert 'd.kind === "brain" && d.wall' in js
    assert 'd.wall === "you"' in js and "pushChat" in js
