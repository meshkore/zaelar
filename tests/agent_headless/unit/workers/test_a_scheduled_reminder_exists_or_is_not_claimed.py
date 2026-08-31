"""A SCHEDULED reminder really exists, or it is not claimed (V2-249).

The “self-evaluating pill” that the harness has been measuring over several rounds: a worker is tasked with
“remind him on Wednesday,” and durably writes to memory “SCHEDULED reminder … at 09:00”
**without any scheduler entry existing**. It was not disobedience: tested in the code, the capability **did not
exist**. `worker_policy._KNOWN_ACTS` had no scheduling action, so it was IMPOSSIBLE for the worker to do it.

The FlashBrain path did work (`nucleo/scheduler.py`, 109 green tests across its two files): the
hole opened only when the task was ESCALATED to a worker.

The harness set the bar and allows two acceptable outcomes: **the entry exists, or the pill does not say
“scheduled”**. This implements the first and, where that is not possible, enforces the second.

The framing is from the operator (2026-08-20), and corrects the one this agent initially used: **a Brain Worker already does
almost everything** —operates a widget’s data, creates and modifies its code, drives the browser, communicates with the
MeshKore network, writes to memory, uses MCP— and this system’s security **is not a short list of permissions, it is a
FILTER**. So the question was not “should it be able to?” but “what is its filter?”.
"""
import asyncio

import pytest

from nucleo import worker_api, worker_policy


class _Journal:
    """The REAL journal writes to the machine’s `zaelar.db`. A unit test does not touch live artifacts."""

    def __init__(self):
        self.entries = []

    def add(self, title, status="pending", detail=None):
        self.entries.append({"id": len(self.entries) + 1, "title": title, "status": status,
                             "detail": detail or {}})
        return len(self.entries)

    def list_entries(self, status=None):
        return [e for e in self.entries if status is None or e["status"] == status]


@pytest.fixture
def agenda(monkeypatch):
    from nucleo import scheduler
    j = _Journal()
    monkeypatch.setattr(scheduler, "_journal", j, raising=False)
    return j


class _Rec:
    task_id = "t7"
    goal = "recuérdale el miércoles llamar al fontanero"


def _act(payload):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        worker_api._exec_allow("schedule", payload, _Rec()))


# ── the capability exists ────────────────────────────────────────────────────────────────────────────────────

def test_programar_es_una_accion_CONOCIDA():
    """Previously it fell into “unknown action,” which the worker interpreted as a prohibition."""
    assert "schedule" in worker_policy._KNOWN_ACTS
    assert worker_policy.classify_act("schedule", {}) == worker_policy.ALLOW


def test_el_aviso_QUEDA_de_verdad(agenda):
    out = _act({"when": "el miércoles a las 9", "prompt": "recuérdale llamar al fontanero"})
    assert out["ok"], out
    assert len(agenda.entries) == 1, "esto es lo que no existía: la entrada"
    assert out["result"]["id"] and out["result"]["cuando"]


def test_el_aviso_dice_QUIEN_lo_puso(agenda):
    """The operator must be able to see where the thing that rings at 9 in the morning came from."""
    _act({"when": "mañana a las 9", "prompt": "llamar al fontanero"})
    assert "[worker:t7]" in agenda.entries[0]["title"]


# ── the FILTER ──────────────────────────────────────────────────────────────────────────────────────────────

def test_hay_un_TOPE_por_tarea(agenda):
    """Without a cap, a worker in a loop fills the operator’s agenda — and each entry then triggers a turn."""
    for i in range(worker_api._SCHEDULE_CAP):
        assert _act({"when": "mañana a las 9", "prompt": f"aviso {i}"})["ok"]
    out = _act({"when": "mañana a las 9", "prompt": "uno más"})
    assert not out["ok"] and "tope" in out["error"]
    assert len(agenda.entries) == worker_api._SCHEDULE_CAP


def test_el_tope_es_POR_TAREA_y_no_global(agenda, monkeypatch):
    """Two different tasks from the operator do not compete for the same slot."""
    for i in range(worker_api._SCHEDULE_CAP):
        _act({"when": "mañana a las 9", "prompt": f"aviso {i}"})

    class _Otro:
        task_id = "t9"
        goal = "otra cosa"

    out = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        worker_api._exec_allow("schedule", {"when": "mañana a las 9", "prompt": "de otra tarea"}, _Otro()))
    assert out["ok"], out


# ── and what CANNOT be done is stated, not faked ─────────────────────────────────────────────────────────────

def test_sin_CUANDO_no_se_programa_y_se_dice_como(agenda):
    out = _act({"prompt": "llamar al fontanero"})
    assert not out["ok"] and "when" in out["error"]
    assert "miércoles" in out["error"] or "every" in out["error"], "un fallo dice cómo se sale de él (V2-203)"
    assert not agenda.entries


def test_sin_QUE_decir_tampoco(agenda):
    out = _act({"when": "mañana a las 9"})
    assert not out["ok"] and "prompt" in out["error"] and not agenda.entries


def test_un_CUANDO_que_no_se_entiende_devuelve_las_formas_validas(agenda):
    out = _act({"when": "cuando salga la luna", "prompt": "x"})
    assert not out["ok"]
    assert "0 9 * * 3" in out["error"], "sin las formas válidas, el worker adivina o abandona"
    assert not agenda.entries


def test_un_fallo_del_diario_NO_se_devuelve_como_programado(agenda, monkeypatch):
    """Sensitivity: the worst thing this can do is say yes when it cannot. This is literally the defect it closes."""
    def _boom(*a, **k):
        raise RuntimeError("db bloqueada")

    monkeypatch.setattr(agenda, "add", _boom, raising=False)
    out = _act({"when": "mañana a las 9", "prompt": "x"})
    assert not out["ok"] and "no pude programarlo" in out["error"]


# ── and make sure the worker KNOWS it exists ─────────────────────────────────────────────────────────────────

def test_al_worker_se_le_DICE_que_puede_programar():
    """WIRING GUARD (V2-199): a capability the model does not know it has does not exist. That is exactly what
    happened with the interpreter on 2026-08-02 — the worker spent minutes guessing at something that already worked."""
    from nucleo import dispatch_prompts as dp
    p = dp._build_prompt("recuérdale el miércoles llamar al fontanero", "", True)
    assert "act schedule" in p
    assert '"when"' in p and '"prompt"' in p


def test_y_que_si_FALLA_no_diga_que_lo_ha_programado():
    """The other half of the harness’s bar: if it could not be done, the pill cannot say “scheduled”."""
    from nucleo import dispatch_prompts as dp
    p = dp._build_prompt("recuérdale el miércoles llamar al fontanero", "", True)
    assert "NO digas que lo has programado" in p


# ── the forms taught to it must really PARSE ─────────────────────────────────────────────────────────────────
# V2-219 already paid the price once: the worker died twice on the arity of our own CLI. A list of examples
# that do not parse is worse than none, because it sends the worker to retry the same thing. This is checked against the parser.

@pytest.mark.parametrize("cuando", ["mañana a las 9", "el miércoles a las 18:00", "every 30m", "0 9 * * 3"])
def test_cada_ejemplo_que_le_damos_SE_ENTIENDE(cuando, agenda):
    assert _act({"when": cuando, "prompt": "llamar al fontanero"})["ok"], f"«{cuando}» se enseña y no parsea"


def test_los_ejemplos_del_PROMPT_son_los_mismos_que_parsean():
    """And ensure the prompt does not teach forms the error does not mention (or vice versa): two different lists of examples
    drift apart without warning, and the worker ends up trying the invalid one."""
    from nucleo import dispatch_prompts as dp
    p = dp._build_prompt("recuérdale algo", "", True)
    for cuando in ("mañana a las 9", "el miércoles a las 18:00", "every 30m", "0 9 * * 3"):
        assert cuando in p, f"«{cuando}» parsea pero no se le enseña"


def test_lo_AMBIGUO_no_se_adivina(agenda):
    """`parse_when` deliberately returns "" for “this afternoon” or “soon”. A reminder placed on an invented date is
    worse than none: the operator keeps believing it is set and finds out on the day it does not ring."""
    for vago in ("esta tarde", "pronto", "cuando puedas"):
        out = _act({"when": vago, "prompt": "x"})
        assert not out["ok"], f"«{vago}» no puede convertirse en una fecha"
        assert "no lo adivino" in out["error"]
    assert not agenda.entries


# ── and make it VISIBLE, with its proof ──────────────────────────────────────────────────────────────────────
# memoria-dev pointed out that this closes ONE instance, not the class: memory stores as a durable fact an
# assertion by the SYSTEM about its own effects, and tomorrow recall confirms it. Today `remember_external` vetoes
# what a THIRD PARTY says and the REM gate verifies an insight against its pills; **nothing verifies a pill
# against the world**. The half that the person who EXECUTES the action can provide is to leave proof: a verifiable ref.

def test_el_aviso_devuelve_un_REF_comprobable(agenda):
    out = _act({"when": "mañana a las 9", "prompt": "llamar al fontanero"})
    assert out["result"]["ref"] == f"cron:{out['result']['id']}", \
        "sin un ref, una píldora que diga «programado» no se puede contrastar con nada"


def test_programar_DEJA_FILA_en_la_observabilidad(agenda, monkeypatch):
    """A reminder that rings in three days was created by a background task that no longer exists by then. Without a
    row, the operator encounters it without knowing where it came from."""
    vistos = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: vistos.append((a, k)), raising=False)
    _act({"when": "mañana a las 9", "prompt": "llamar al fontanero"})
    assert vistos, "programar en silencio es la mitad del problema que esto cierra"
    _, kw = vistos[0]
    assert kw.get("extra", {}).get("cron_id"), "la fila lleva el ID real, que es lo que permite comprobarlo"


def test_un_aviso_que_NO_se_pudo_poner_no_deja_fila(agenda, monkeypatch):
    """Sensitivity: a “⏰ scheduled reminder” row for something that was not scheduled is the same lie, in another
    place and with more authority."""
    vistos = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: vistos.append((a, k)), raising=False)
    _act({"when": "esta tarde", "prompt": "x"})
    assert not vistos


def test_la_TERCERA_puerta_al_scheduler_normaliza_como_las_otras_dos(agenda, monkeypatch):
    """V2-480 — `safe_reminder_prompt` says in its docstring that it exists “so that the TWO doors to the scheduler
    say the same thing”; this action is the THIRD, was created later (V2-249), and never called it.

    Measured in `find-a-future-release-and-remind-me` (2026-08-29): the task was scheduled with the operator’s
    RAW phrase inside, so when it rings the agent will read the operator their own words —
    and, worse, will read them as a request to note down, which is the loop this whole area exists to close.
    """
    from nucleo import scheduler

    creados: list[str] = []
    real = scheduler.create

    def _spy(prompt, spec, name):
        creados.append(prompt)
        return real(prompt, spec, name)

    monkeypatch.setattr(scheduler, "create", _spy, raising=False)
    out = _act({"when": "mañana a las 9", "prompt": "el jueves tengo que renovar el seguro del coche"})
    assert out.get("ok"), out
    assert creados and creados[0].startswith("AVISA al operador"), creados


def test_y_un_prompt_que_YA_es_una_orden_al_agente_no_se_toca(agenda, monkeypatch):
    """The other direction: over-normalizing would wrap a legitimate command inside another command."""
    from nucleo import scheduler

    creados: list[str] = []
    real = scheduler.create
    monkeypatch.setattr(scheduler, "create",
                        lambda p, s, n: (creados.append(p), real(p, s, n))[1], raising=False)
    _act({"when": "mañana a las 9", "prompt": "AVISA al operador: estreno de Dexter T2"})
    assert creados == ["AVISA al operador: estreno de Dexter T2"], creados
