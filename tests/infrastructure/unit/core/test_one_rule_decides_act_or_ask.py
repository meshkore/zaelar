"""V2-712 T0 · ONE rule decides act-or-ask, and it is not a table of verbs.

## What the operator said (2026-09-16), which is the specification

> «Estoy un poco hasta los huevos de tener que confirmar las cosas. Si le digo borra una cita de la agenda
> llamada tal, la borras y punto. A menos que haya dos que se llamen igual […]. Si te digo que reserves mesa
> en un restaurante, tú ya tienes que saber quién soy yo, cuál es mi teléfono, cuál es mi email. Y si no lo
> sabes, obviamente preguntas. Pero una vez ya lo sepas y lo tengas en el estado, no hace falta preguntar.»

> «No forzamos las preguntas de forma hardcodeada. Tiene que ser el propio sistema el que tenga una regla
> para todo el sistema […]. Cuando hagamos un widget diremos cuál es el nivel de seguridad, y pondremos de
> momento a todos por defecto nivel estándar. […] Por defecto no autorrespondemos ningún mensaje. Eso es una
> regla de usuario preseteada en el Génesis. Pero si el usuario decide cambiarla, que la cambie.»

## What is pinned here

The four questions in HIS order (missing fact → doubt → radius → class), that a resolved single target with
complete data RUNS, that the V2-707 radius rail survives the whole thing, that `critical` still stops money,
that every level is DECLARED data rather than a name being matched, and that a factory rule of the Genesis is
the operator's to change by speaking — with the other factory rules surviving the change.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from nucleo import consent


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """A THROWAWAY workspace: the override file must never be the operator's real one."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    consent._reset_for_tests()
    yield
    consent._reset_for_tests()


# ── 1 · his examples, as cases ──────────────────────────────────────────────────────────────────────────

def test_borra_la_cita_del_dentista_y_punto():
    """One appointment matches, nothing is missing, the radius is one. There is no question left to ask."""
    v = consent.decide(level="sensitive", radius=1, bounded=True)
    assert v["verdict"] == consent.RUN


def test_dos_citas_que_se_llaman_igual_preguntan_CUAL_no_si():
    """«A menos que haya dos que se llamen igual» — and the useful question names them."""
    v = consent.decide(level="sensitive", candidates=["Dentista 10:00", "Dentista 17:30"])
    assert v["verdict"] == consent.ASK_WHICH
    assert v["candidates"] == ["Dentista 10:00", "Dentista 17:30"]


def test_reserva_mesa_con_los_datos_en_el_estado_no_pregunta_nada():
    v = consent.decide(level="standard", missing=[], radius=1, bounded=True)
    assert v["verdict"] == consent.RUN


def test_reserva_mesa_SIN_el_telefono_pide_EL_TELEFONO_no_permiso():
    """«Y si no lo sabes, obviamente preguntas» — the difference that matters is WHAT is asked."""
    v = consent.decide(level="standard", missing=["operator.phone"], radius=1)
    assert v["verdict"] == consent.ASK_FACT
    assert v["needs"] == ["operator.phone"], "the question must name the datum, not ask for a yes"


def test_vaciar_la_agenda_sigue_preguntando_porque_el_radio_no_es_uno():
    """V2-707's rail, untouched: this is the class born from 147 DELETEs on his real calendar."""
    assert consent.decide(level="standard", bounded=False)["verdict"] == consent.ASK_CONSENT
    assert consent.decide(level="standard", radius=34, bounded=True)["verdict"] == consent.ASK_CONSENT


def test_el_dinero_que_sale_de_sus_cuentas_pregunta_aunque_todo_este_claro():
    """`critical` is the one level a clear order does not clear. Rail on the CONSEQUENCE."""
    v = consent.decide(level="critical", radius=1, bounded=True)
    assert v["verdict"] == consent.ASK_CONSENT and "critical" in v["why"]


# ── 2 · the order of the four questions is the operator's ───────────────────────────────────────────────

def test_a_missing_fact_beats_everything_else():
    """Asking «which one of the three» when we could not act on any of them anyway wastes his turn."""
    v = consent.decide(level="critical", missing=["operator.email"], candidates=["a", "b"], bounded=False)
    assert v["verdict"] == consent.ASK_FACT


def test_doubt_beats_the_radius_and_the_class():
    v = consent.decide(level="critical", candidates=["a", "b"], bounded=False)
    assert v["verdict"] == consent.ASK_WHICH


def test_the_radius_beats_the_class_so_the_reason_given_is_the_true_one():
    """A sweep of 30 routine rows is stopped BY ITS RADIUS; saying «es una acción sensible» would be a lie."""
    v = consent.decide(level="routine", radius=30, bounded=True)
    assert v["verdict"] == consent.ASK_CONSENT and "alcance" in v["why"]


# ── 3 · the level is DECLARED, never guessed from a name ────────────────────────────────────────────────

def test_an_undeclared_action_of_an_undeclared_widget_is_standard():
    """«Pondremos de momento a todos por defecto nivel estándar» — including a widget written tomorrow."""
    assert consent.level_of({}) == "standard"
    assert consent.level_of(None) == "standard"


def test_todays_confirm_flag_is_READ_as_sensitive_so_nothing_changes_by_accident():
    """The twenty `confirm:true` actions in the catalog are not deleted: they are read. Only what V2-712
    says changes, changes."""
    assert consent.level_of({"confirm": True}) == "sensitive"
    assert consent.level_of({"irreversible": True}) == "sensitive"


def test_a_view_action_is_routine_and_an_explicit_level_wins_over_everything():
    assert consent.level_of({"view": True}) == "routine"
    assert consent.level_of({"confirm": True, "sensitivity": "routine"}) == "routine"
    assert consent.level_of({}, widget_security="critical") == "critical"


def test_a_garbage_level_falls_back_to_standard_rather_than_crashing_a_turn():
    assert consent.level_of({"sensitivity": "muy peligroso"}) == "standard"
    assert consent.decide(level="banana", radius=1)["level"] == "standard"


# ── 4 · the Genesis rule is his to change, and the others survive the change ────────────────────────────

def test_the_autoresponder_is_OFF_by_default_as_a_preset_rule_not_a_hardcoded_one():
    """His own example. It lives in `genesis.json`, so it is data — and `REFUSE` is the honest verdict: a
    standing «never» is not a question to put to him again."""
    assert consent.class_policy("messaging.autorespond") == "never"
    v = consent.decide(level="standard", radius=1, policy_key="messaging.autorespond")
    assert v["verdict"] == consent.REFUSE


def test_the_operator_changes_it_by_saying_so_and_it_governs_the_next_decision():
    consent.set_class("messaging.autorespond", "allow")
    assert consent.class_policy("messaging.autorespond") == "allow"
    v = consent.decide(level="standard", radius=1, policy_key="messaging.autorespond")
    assert v["verdict"] == consent.RUN, "«si el usuario decide cambiarla, que la cambie»"


def test_changing_ONE_class_rule_does_not_wipe_the_other_factory_ones():
    """A whole-dict replace would silently drop the rules he never touched — the kind of loss that is only
    noticed the day one of them was load-bearing."""
    consent.set_class("messaging.autorespond", "allow")
    assert consent.class_policy("payment.authorize") == "ask"
    assert consent.class_policy("account.disconnect") == "allow"


def test_an_allow_rule_still_does_not_clear_a_SWEEP():
    """Standing permission for a class is permission for the act he named, never for an unbounded one."""
    consent.set_class("messaging.autorespond", "allow")
    v = consent.decide(level="standard", bounded=False, policy_key="messaging.autorespond")
    assert v["verdict"] == consent.ASK_CONSENT


# ── 5 · «no me preguntes» is a policy, not a prompt sentence ────────────────────────────────────────────

def test_ejecuta_sin_parar_is_understood_and_persisted():
    assert consent.apply_directive("hazlo directamente, no me preguntes más") == {"ask_at": "critical"}
    assert json.loads((pathlib.Path(consent._overrides_path())).read_text())["ask_at"] == "critical"


def test_he_can_ask_for_MORE_friction_too_and_it_reaches_the_verdict():
    consent.apply_directive("pregúntame siempre antes de tocar nada")
    assert consent.ask_at() == "sensitive"
    v = consent.decide(level="sensitive", radius=1, bounded=True)
    assert v["verdict"] == consent.ASK_CONSENT, "his rule has to change a DECISION, not just a prompt line"


def test_retracting_the_rule_goes_back_to_the_genesis_default():
    consent.apply_directive("pregúntame siempre antes de tocar nada")
    assert consent.ask_at() == "sensitive"
    consent.retract_directive("olvida lo de preguntarme antes")
    assert consent.ask_at() == "critical"


def test_prose_that_names_no_flag_stores_NOTHING_instead_of_guessing():
    """The same boundary its sibling `style_policy` draws: the model still gets the sentence as a rule, so
    nothing is lost — but a policy nobody can audit is never written from a guess."""
    assert consent.apply_directive("me gustan las cosas bien hechas") == {}
    assert consent.set_class("messaging.autorespond", "quizá") == {}


# ── 6 · the module decides, it does not SPEAK ───────────────────────────────────────────────────────────

def test_the_rule_returns_DATA_and_never_a_sentence_the_operator_hears():
    """A module that writes the question is a rail on judgement (`principles.md`). The caller phrases it,
    because only the caller knows whether it is a card, a voice turn or a browser task."""
    src = pathlib.Path(consent.__file__).read_text(encoding="utf-8")
    body = src.split('# ── THE RULE')[1].split('# ── Spoken overrides')[0]
    assert "¿" not in body, "a question mark in the decision means it is writing the operator's sentence"
    for v in (consent.decide(level="critical", radius=1), consent.decide(missing=["x"])):
        assert set(v) == {"verdict", "why", "needs", "candidates", "n", "level"}


def test_asks_is_one_accessor_so_no_caller_re_derives_it():
    assert consent.asks(consent.decide(missing=["x"])) is True
    assert consent.asks(consent.decide(level="standard", radius=1, bounded=True)) is False
    assert consent.asks(consent.REFUSE) is True


# ── 7 · a fact is looked for where it actually LIVES ────────────────────────────────────────────────────

def test_a_slot_is_found_through_its_STATE_FIELD_not_its_slot_name(monkeypatch):
    """⚠️ The defect this pins was real and mine. `memory/slots.py` reflects `operator.name` into the state
    as `operator_name`, and the first version of the reader guessed the last path segment (`name`) — which
    matches nothing. It would have asked him for a name the system had had all along."""
    from memory import api as _mem
    monkeypatch.setattr(_mem, "state", lambda: {"operator_name": "Ricart"})
    monkeypatch.setattr(_mem, "by_slot_prefix", lambda *a, **k: [])
    assert consent.missing_facts(["operator.name"]) == []


def test_a_slot_with_NO_state_field_is_looked_for_in_the_pills(monkeypatch):
    """`operator.phone`, `.email` and `.address` — the three a booking form actually wants — have no state
    reflection at all. A reader that only looked at `state()` reported every one of them missing."""
    from memory import api as _mem
    monkeypatch.setattr(_mem, "state", lambda: {})
    monkeypatch.setattr(_mem, "by_slot_prefix", lambda slot, **k: [{"slot": slot}] if "phone" in slot else [])
    assert consent.missing_facts(["operator.phone", "operator.email"]) == ["operator.email"]


def test_an_unreadable_memory_ASKS_rather_than_inventing_a_phone_number(monkeypatch):
    """Fails toward asking, deliberately: the alternative is a made-up number in somebody's real booking."""
    from memory import api as _mem
    monkeypatch.setattr(_mem, "state", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    assert consent.missing_facts(["operator.phone"]) == ["operator.phone"]
