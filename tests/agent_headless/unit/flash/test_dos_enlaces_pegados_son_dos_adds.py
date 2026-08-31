"""V2-391 — “ONE data-op per turn” turned two pasted links into a hallucination.

The cap was deliberate and its reason is measured: the small model DUPLICATES an `add_meeting` (double
appointment) or ENUMERATES actions for “show me the agenda” (done/drop/snooze). Both remain blocked.

What it did not account for is that sometimes MULTIPLE are the request. Measured in
`build-a-video-playlist-from-links` (2026-08-27 13:36), and the entire chain starts there:

    tester  Te paso un par de vídeos: …dQw4w9WgXcQ y …9bZkp7q19f0 — móntame una lista con ellos.
    zaelar  Voy a cargar esos dos vídeos en tu lista de YouTube.
    …
    tester  Perfecto, ahora pásala al siguiente, porfa.
    zaelar  Hecho.
    tester  ¿Y qué está sonando ahora?
    zaelar  Ahora está sonando «PSY - GANGNAM STYLE (강남스타일) M/V».

`add` accepts one video, so two links are two calls, and only the first got through (`widget_ops: add: 1`).
`next` found only one video, the widget returned “No hay más vídeos,” and the turn announced the second
one anyway — it knew the title from the URL, not from the list. 1/5 in outcome because of a hallucination
that begins as one of our caps.

The new criterion is NARROWER than the old one where it matters: it only expands to the same action with
different payloads, and only FAST actions reach the code below (an irreversible action is CONFIRM and still
asks for approval).

The rule lives in `nucleo/flash/data_ops.py`, rather than in `router_guards`, because of the god-file ratchet:
what matters is that there is ONE decision, not which file it is in.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import data_ops as RG


def _op(wid, act, **payload):
    return {"widget_id": wid, "action": act, "payload": payload}


# ── the criterion ────────────────────────────────────────────────────────────────────────────────────────────

def test_dos_enlaces_DISTINTOS_entran_los_dos():
    """The case that was broken: same action, different payloads."""
    a, b = _op("youtube", "add", url="dQw4w9WgXcQ"), _op("youtube", "add", url="9bZkp7q19f0")
    assert RG.admite_data_op(a, []) is True
    assert RG.admite_data_op(b, [a]) is True


def test_un_duplicado_EXACTO_se_colapsa():
    """The double appointment, which is why the cap existed."""
    a = _op("agenda", "add_meeting", title="dentista", date="2026-09-03")
    assert RG.admite_data_op(dict(a), [a]) is False


def test_otra_ACCION_sobre_el_mismo_widget_no_entra():
    """The enumeration: “show me the agenda” → done/drop/snooze. Only the first one."""
    a = _op("agenda", "done", item=1)
    assert RG.admite_data_op(_op("agenda", "drop", item=1), [a]) is False


def test_otro_WIDGET_sigue_siendo_otra_cosa():
    """The restriction is per widget: touching two different widgets is not enumerating over one."""
    a = _op("youtube", "add", url="x")
    assert RG.admite_data_op(_op("musica", "play", query="algo"), [a]) is True


def test_hay_TECHO():
    """Five links at once is a request; fifty is a broken model."""
    ya = [_op("youtube", "add", url=f"v{i}") for i in range(RG.MAX_DATA_OPS)]
    assert RG.admite_data_op(_op("youtube", "add", url="uno-mas"), ya) is False


def test_una_op_SIN_widget_o_SIN_accion_no_entra():
    assert RG.admite_data_op({"action": "add"}, []) is False
    assert RG.admite_data_op({"widget_id": "youtube"}, []) is False


# ── the TEXT channel executes it ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def rail(monkeypatch):
    """The witness points to `brain_action` since V2-394: `dispatch_tag` swallows the result, so it stopped
    being used to determine whether the op occurred. What this file measures —how many get through and which
    ones— does not change."""
    despachadas = []

    async def _brain_action(wid, act, payload):
        despachadas.append({"id": wid, "data": {"action": act, "payload": payload}})
        return {"ok": True}

    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    from widgets import actions as _wa
    monkeypatch.setattr("nucleo.flash.frontend.action_mode", lambda wid, act: _wa.FAST)
    return despachadas


def _llamadas(*ops):
    return [{"name": "widget_data", "args": o} for o in ops]


def test_el_canal_de_texto_despacha_los_DOS_enlaces(rail):
    from nucleo.flash import widget_data_turn as WDT
    parte = asyncio.run(WDT.execute(_llamadas(_op("youtube", "add", url="dQw4w9WgXcQ"),
                                              _op("youtube", "add", url="9bZkp7q19f0"))))
    assert len(rail) == 2, "dos enlaces pegados son dos adds"
    assert [d["data"]["payload"]["url"] for d in rail] == ["dQw4w9WgXcQ", "9bZkp7q19f0"]
    assert parte["executed"] == "widget_data" and len(parte["ops"]) == 2


def test_lo_DESCARTADO_se_dice(rail):
    """A report that only counts what went well is how a “Done.” that is not done survives."""
    from nucleo.flash import widget_data_turn as WDT
    dup = _op("agenda", "add_meeting", title="dentista")
    parte = asyncio.run(WDT.execute(_llamadas(dup, dict(dup))))
    assert len(rail) == 1
    assert parte["descartadas"] == 1


def test_una_accion_que_pide_PERMISO_sigue_sin_ejecutarse(monkeypatch, rail):
    """The boundary that does NOT move: irreversible actions are CONFIRM and still require the operator’s yes."""
    from widgets import actions as _wa

    from nucleo.flash import widget_data_turn as WDT
    monkeypatch.setattr("nucleo.flash.frontend.action_mode", lambda wid, act: _wa.CONFIRM)
    parte = asyncio.run(WDT.execute(_llamadas(_op("agenda", "borrar_todo"))))
    assert rail == []
    assert parte["executed"] == "widget_data_skipped"


def test_el_parte_conserva_la_forma_singular_de_antes(rail):
    """The report and previous guards read `widget`/`act`: changing them to a list would break the
    reading without warning."""
    from nucleo.flash import widget_data_turn as WDT
    parte = asyncio.run(WDT.execute(_llamadas(_op("youtube", "add", url="x"))))
    assert parte["widget"] == "youtube" and parte["act"] == "add"


# ── and VOICE uses the SAME criterion ────────────────────────────────────────────────────────────────────────

def test_la_voz_decide_con_el_MISMO_guarda():
    """If each channel brings its own, they diverge — which is how this kind of failure survives (V2-176)."""
    from pathlib import Path
    src = Path("voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert "_data_ops.admite_data_op(args, _data_ops_hechas)" in src
    assert '"widget_data" in _tool_fired:\n                    return' not in src
