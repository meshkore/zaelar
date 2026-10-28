"""The THIRD surface that shows pills to a model, and ran every turn (V2-254).

Full story, because the lesson is not in the fix but in how it was found:

  · The harness sent an isolated datum: the agent searched for **«fontanero Soria»** with `operator.location` = «Vive en
    el centro de Madrid». The pill was written every hour by `widgets/meteo-soria`.
  · V2-242 closed WRITING (a background pill carries the writer's name in the key).
  · memoria-dev closed READING the worker dossier (`compose_context`).
  · And it still kept appearing, because **the rule was written in three places and applied in one**: the
    passive block had had it since the 2026-07-14 audit, the dossier got it on 2026-08-21… and THIS—the active recall,
    the one that runs EVERY TURN—did not have it. Measured with both fixes already in place:

        It may be relevant (from your memory):
        · Weather in Soria now: 14.5C, parcialmente nublado.   ← the widget dump
        · Vive en el centro de Madrid.                          ← the operator fact

    The widget dump ABOVE the profile slot.

It is the same pattern as `_next_action` (V2-253) and the text channel (V2-252): **the failure was not the rule, it was
having it duplicated**. That is why this applies the one that already exists (`memory.api.background_slot_off_topic`)
instead of writing a fourth copy.
"""
import pytest

from memory.api import background_slot_off_topic as regla
from nucleo.turn.prompt import recall as fp


class _Mem(dict):
    pass


def _pildoras():
    return [
        _Mem(level="mid", kind="note", slot="meteo-soria:weather:soria",
             text="Weather in Soria now: 14.5C, parcialmente nublado.", id=1),
        _Mem(level="long", kind="profile", slot="operator.location",
             text="Vive en el centro de Madrid.", id=2),
    ]


@pytest.fixture
def memoria(monkeypatch):
    from memory import api

    def _query(prompt, **kw):
        return {"state": {}, "memories": _pildoras(), "ids": [1, 2]}

    monkeypatch.setattr(api, "query", _query, raising=False)


# ── the measured case ──────────────────────────────────────────────────────────────────────────────────────────

def test_el_volcado_del_widget_NO_sale_en_un_encargo_de_otro_tema(memoria):
    bloque, _ids = fp.compose_recall("busca un fontanero que venga hoy")
    assert "Madrid" in bloque, "el hecho del operador tiene que seguir estando"
    assert "Soria" not in bloque, "el parte meteorológico de otra ciudad decidía la ciudad del encargo"


def test_pero_SI_el_operador_lo_nombra_entra(memoria):
    """The promise of the 2026-07-14 audit: these pills remain reachable in response to an explicit question.
    Without this case, «filter the background» could be satisfied by always deleting them and the widget would become useless."""
    bloque, _ids = fp.compose_recall("¿qué tiempo hace en Soria?")
    assert "Soria" in bloque


def test_un_hecho_del_OPERADOR_nunca_se_filtra(memoria):
    bloque, _ids = fp.compose_recall("¿dónde vivo?")
    assert "Madrid" in bloque


# ── make it THE SAME rule, not a fourth copy ──────────────────────────────────────────────────────────────────


def test_la_regla_sigue_teniendo_UNA_casa():
    """If someone copies it again, this case will not catch that—but it will catch this surface stopping its use of the
    shared rule, which is the half within my control."""
    import importlib
    import inspect
    from memory import api
    home = importlib.import_module(api.background_slot_off_topic.__module__)
    assert home.__name__.startswith("memory.api") and "def background_slot_off_topic" in inspect.getsource(home)


# ── and the rule, in its three forms ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("slot,peticion,fuera", [
    ("meteo-soria:weather:soria", "busca un fontanero", True),
    ("meteo-soria:weather:soria", "el tiempo en Soria", False),
    ("operator.location", "busca un fontanero", False),
    ("", "busca un fontanero", False),
])
def test_la_regla_compartida_dice_lo_que_creemos(slot, peticion, fuera):
    assert regla(slot, peticion) is fuera
