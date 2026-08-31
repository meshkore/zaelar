"""`INFRA` without a reason is an operational hole, not a stylistic one.

The four gates that lead to INFRA require **opposite** actions: the harness crashed (an instrument bug),
the turns came back empty (reload a provider), semantic recall was degraded (bring up the
prewarm), or the judge gave no score (inspect its chain). From the board, all four look exactly the same.

Measured on 2026-08-28 with the 24/7 setup already running: two rows went from FAIL to INFRA in an hour, and
reconstructing which of the four branches had moved them was **impossible** — the round dict no longer exists
when someone reads the board. In a loop nobody watches for eight hours, that is the difference between
“it is measuring” and “it has been producing garbage at full speed all night,” and the latter is worse than
being stopped because a stopped system is noticeable.
"""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import status as S


def _ronda(**kw):
    base = {"scenario": "x__es", "tier": 2,
            "run": {"transcript": [{}] * 12, "mechanism_report": {}},
            "verdict": {"overall": 3, "scores": {"mecanismo": 3}, "veredicto": "bien"}}
    base.update(kw)
    return base


def test_turnos_vacios_lo_dicen_con_su_cuenta():
    r = _ronda(run={"transcript": [{}] * 12, "mechanism_report": {"mute_turns": {"n": 5}}})
    assert S._state(3, r) == "INFRA"
    assert "VACÍOS" in r["_infra_reason"] and "5 de 6" in r["_infra_reason"]


def test_el_recall_degradado_nombra_su_backend():
    r = _ronda(run={"transcript": [{}] * 12,
                    "mechanism_report": {"embeddings": {"degraded": True, "backend": "hash"}}})
    assert S._state(3, r) == "INFRA"
    assert "recall" in r["_infra_reason"] and "hash" in r["_infra_reason"]


def test_una_excepcion_de_verdad_y_el_juez_mudo_son_distintos():
    """Rewritten 2026-08-28, NOT inverted: the property —two gates, two distinct reasons— remains the same. What
    changed is that `crashed` is no longer translated into an invented phrase; instead, the phrase it contains is
    printed, so the fixture passes the real exception phrase instead of a bare `True`."""
    a = _ronda(run={"crashed": "ZeroDivisionError en el juez · autopsia: …",
                    "transcript": [], "mechanism_report": {}})
    S._state(3, a)
    b = _ronda()
    S._state(None, b)
    assert a["_infra_reason"] != b["_infra_reason"]
    assert "ZeroDivisionError" in a["_infra_reason"] and "juez no devolvió nota" in b["_infra_reason"]


def test_una_ronda_SANA_no_lleva_motivo():
    """Half of the sensitivity check: a reason that always appears stops being a reason."""
    r = _ronda()
    assert S._state(3, r) == "FAIL"
    assert "_infra_reason" not in r


def test_el_motivo_llega_a_la_fila_y_al_tablero(tmp_path, monkeypatch):
    """The whole chain: if it remains in the round dict, nobody reads it."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([_ronda(run={"transcript": [{}] * 12, "mechanism_report": {"mute_turns": {"n": 5}}})],
             sandboxed=True)
    fila = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))["scenarios"]["x__es"]
    assert fila["state"] == "INFRA" and "VACÍOS" in (fila["infra_reason"] or "")
    tablero = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "INFRA —" in tablero and "VACÍOS" in tablero


def test_en_una_fila_INFRA_el_motivo_manda_sobre_el_veredicto(tmp_path, monkeypatch):
    """The verdict describes a product that was NOT measured in that round. Reading it as though it was invites
    exactly the wrong diagnosis, which is the mistake this node exists to prevent repeating."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    r = _ronda(run={"transcript": [{}] * 12, "mechanism_report": {"mute_turns": {"n": 5}}})
    r["verdict"]["veredicto"] = "el producto no entregó nada"
    S.record([r], sandboxed=True)
    fila = [l for l in (tmp_path / "STATUS.md").read_text(encoding="utf-8").splitlines() if "x__es" in l][0]
    assert fila.index("INFRA —") < fila.index("el producto no entregó nada")
    assert "no medible" in fila


def test_el_motivo_que_YA_venia_escrito_no_se_sustituye_por_una_suposicion():
    """`crashed` does not mean “it crashed”: it is a field with THREE occupants —the driver out of role (V2-313), an
    unreadable source of truth (V2-396), and a real exception with its autopsy— and **each one already contains its
    phrase**. The first version of this node used a generic reason, and it was false for all three.

    Measured an hour after writing it, on `best-plumber-same-day__us`: the board said “the harness crashed,” the
    log did not contain a traceback, and the verdict was a perfectly normal 2/5 product score. The real phrase,
    which was in the field, said “the driver went out of role in 1 transcript line(s) (turn 13): the round does
    not measure the product” — something else, with a different action required.

    Guessing a reason when the correct one is right in front of you is the same mistake this node exists to fix.
    """
    frase = "el conductor se salió de su papel en 1 línea(s) del transcript (turno(s) 13)"
    r = _ronda(run={"crashed": frase, "transcript": [{}] * 12, "mechanism_report": {}})
    assert S._state(2, r) == "INFRA"
    assert r["_infra_reason"] == frase, "se sustituyó el motivo real por uno inventado"


def test_y_el_juez_marcando_INFRA_es_OTRA_cosa():
    """Half of the sensitivity check: the two gates were combined in one condition and said the same thing."""
    r = _ronda(verdict={"overall": 1, "scores": {}, "veredicto": "INFRA: no hubo respuesta"})
    assert S._state(1, r) == "INFRA"
    assert "juez" in r["_infra_reason"] and "conductor" not in r["_infra_reason"]


# ── A green row cannot hide that the judge said no ───────────────────────────────────────────────────────────
def test_una_fila_VERDE_cuyo_juez_dice_que_NO_lo_enseña(tmp_path, monkeypatch):
    """`PASS` is the harness threshold (overall ≥ 4 and mechanism ≥ 3), while “ready for production” is the judge's
    opinion: two different questions, both valid, and they are not forced to agree. What cannot be hidden is this
    — a green row that opens with “Not ready for production” gives the reader two contradictory things on the same
    line, and the one that remains is the icon.

    Measured on 2026-08-28: 2 of the board's 13 green rows, both from that early morning.
    """
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([_ronda(verdict={"overall": 4, "scores": {"mecanismo": 4},
                              "veredicto": "No está listo para producción: el bloqueador nº1 es…"})],
             sandboxed=True)
    fila = [l for l in (tmp_path / "STATUS.md").read_text(encoding="utf-8").splitlines() if "x__es" in l][0]
    assert "✅" in fila and "el juez dice que NO está listo" in fila


def test_y_una_verde_conforme_no_arrastra_el_aviso(tmp_path, monkeypatch):
    """A warning that appears in every green row stops being a warning."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([_ronda(verdict={"overall": 5, "scores": {"mecanismo": 5},
                              "veredicto": "Sí, está listo para producción: la ejecución es impecable."})],
             sandboxed=True)
    fila = [l for l in (tmp_path / "STATUS.md").read_text(encoding="utf-8").splitlines() if "x__es" in l][0]
    assert "✅" in fila and "NO está listo" not in fila


def test_solo_se_mira_el_ARRANQUE_del_veredicto():
    """In the body, the same phrase is often negated, and searching for it anywhere would flag rows that say
    exactly the opposite."""
    assert S._judge_says_not_ready("No está listo para producción: …")
    assert not S._judge_says_not_ready("El caso funciona; sería falso decir que no está listo.")
    assert not S._judge_says_not_ready("")


# ── and the infrastructure round must be STATED, not merely stored (2026-08-30) ───────────────────────────
def test_el_supervisor_no_puede_leer_una_ronda_INFRA_como_FAIL():
    """`status.py::_infra` already marked the INFRA row with its reason, and its own comment warns that merging
    INFRA with FAIL “is how a scoreboard starts lying.” But the SUPERVISOR classifies by reading the runner's
    OUTPUT, not the report — so it saw “PASSED 0/1” and recorded FAIL.

    Measured: the 14:26 round ran with degraded recall (the embeddings provider crashed halfway through),
    `status.json` stored it as `state: INFRA` with its reason, and the line the operator reads said FAIL. Two
    views of the same data disagreed, and the one being read was the wrong one — which is exactly how an
    infrastructure round ends up attributed to the product.
    """
    from tests.use_cases.e2e.agent.supervisor import _veredicto_de_cola

    cola = "INFRA: recall semántico DEGRADADO en esta ronda (backend: cloud)\nPASSED 0/1 (overall>=4)"
    assert _veredicto_de_cola(cola) == "INFRA", "una ronda con la infraestructura caída se anota como fallo del producto"

    # The counterweights, without which this would be “mark everything INFRA”: a normal round that fails remains
    # FAIL, and one that passes remains PASS.
    assert _veredicto_de_cola("PASSED 0/1 (overall>=4)") == "FAIL"
    assert _veredicto_de_cola("PASSED 1/1 (overall>=4)") == "PASS"


def test_el_runner_ANUNCIA_el_motivo_no_solo_la_palabra():
    """With only “INFRA,” the supervisor classifies correctly but the operator still does not know which of the
    four gates it was: crashed harness, empty turns, degraded recall, or a judge with no score require OPPOSITE
    actions."""
    import inspect

    from tests.use_cases.e2e.agent import run as R

    src = inspect.getsource(R)
    assert 'print(f"INFRA: {r[\'_infra_reason\']}")' in src or "INFRA: {r['_infra_reason']}" in src, \
        "el runner anuncia INFRA sin decir de cuál — el motivo ya lo tiene delante"


def test_SANO_lo_decide_el_motor_no_una_copia_del_arnes():
    """This rule said `backend != "ollama"`, and that was true until the morning of 2026-08-30: Ollama was the
    primary provider. V2-501 moved the primary provider to a CLOUD provider, but the line kept the old idea of
    “healthy,” so **16 rounds that day were marked “DEGRADED recall” with memory working**: the endpoint answered
    in 0.29 s and the setup reported memory OK. Sixteen rounds archived as INFRA because of a rule that became
    outdated in one morning.

    That is why the list is not copied: it is imported from the component that decides it. If the engine changes
    its primary provider, the harness changes with it and nobody has to remember.
    """
    from memory.embeddings import _HEALTHY
    from tests.use_cases.e2e.agent import verify

    assert verify._backends_sanos() == tuple(_HEALTHY), (
        "el arnés guarda su propia idea de «sano» — es la que envejeció y archivó 16 rondas buenas")
    # And the property that matters in both directions: today's primary provider is NOT degraded, and the fallback IS.
    assert "cloud" in verify._backends_sanos()
    assert "hash" not in verify._backends_sanos(), "el hashing léxico no puede pasar por memoria sana"


def test_un_plato_SIN_NAVEGADOR_no_mide_una_busqueda():
    """Measured on 2026-08-30: Chromium in the US setup crashed and never came back. The log repeated “Waiting for
    the browser to settle before retrying” with HARD RESET every few minutes, and the rounds came back with an
    EMPTY sheet — indistinguishable from “the product finds nothing.” The settled series fell 3→3→2→1→0→0, and I
    was one message away from sending it as an extraction defect.

    The signature is unambiguous and cannot be confused with searching badly: **a worker that searches badly lands
    on bad pages; one without a browser lands on none.**
    """
    from tests.use_cases.e2e.agent.status import _state

    r = {"run": {"mechanism_report": {
        "page_journey": {"read": True, "n_pages": 0, "n_walls": 0},
        "worker_outcome": {"navigations": 3, "extractions": 0},
    }}, "verdict": {"overall": 2}}
    assert _state(2, r) == "INFRA"
    assert "NO tiene navegador" in r["_infra_reason"] and "3 intento" in r["_infra_reason"]


def test_pero_una_busqueda_MALA_sigue_siendo_del_producto():
    """The counterweight, without which this would archive every weak round as INFRA: if the worker DID land on
    pages, it searched badly, and that is a product issue."""
    from tests.use_cases.e2e.agent.status import _state

    r = {"run": {"mechanism_report": {
        "page_journey": {"read": True, "n_pages": 6, "n_walls": 0},
        "worker_outcome": {"navigations": 6, "extractions": 2},
    }}, "verdict": {"overall": 2}}
    assert _state(2, r) != "INFRA", "una búsqueda mala se está archivando como avería del plató"


def test_y_sin_poder_leer_el_recorrido_no_se_ACUSA():
    """An absence of data is not data: if the journey could not be read, we cannot say there was no browser."""
    from tests.use_cases.e2e.agent.status import _state

    r = {"run": {"mechanism_report": {
        "page_journey": {"read": False, "n_pages": 0},
        "worker_outcome": {"navigations": 3},
    }}, "verdict": {"overall": 2}}
    assert _state(2, r) != "INFRA"


def test_un_puente_que_no_contesta_tampoco_mide_una_busqueda():
    """The variant that slipped through (2026-08-30, `search-secondhand-monitor__es`): all 7 calls died AT THE
    BRIDGE, `navigations` remained at 0, and the no-browser-setup condition —which requires navigation attempts—
    saw nothing. The round came out FAIL even though it was an outage.

    The signature: the worker NAMED `nav_cli` (meaning it tried), its session died with Exit code 2, and not a
    single page was reached. A worker that decides not to navigate does not name `nav_cli`."""
    from tests.use_cases.e2e.agent.status import _state

    r = {"run": {"mechanism_report": {
        "page_journey": {"read": True, "n_pages": 0},
        "worker_outcome": {"navigations": 0},
        "worker_bridges": {"read": True, "by_bridge": {"nav_cli": 1}, "sessions_with_exit2": 1},
    }}, "verdict": {"overall": 2}}
    assert _state(2, r) == "INFRA"
    assert "puente del navegador no contestó" in r["_infra_reason"]

    # Counterweight: a worker that did not even try the browser (a conversational case) is not an outage.
    r2 = {"run": {"mechanism_report": {
        "page_journey": {"read": True, "n_pages": 0},
        "worker_outcome": {"navigations": 0},
        "worker_bridges": {"read": True, "by_bridge": {"mem_cli": 2}, "sessions_with_exit2": 0},
    }}, "verdict": {"overall": 2}}
    assert _state(2, r2) != "INFRA"
