"""V2-712 T1 · A clear order is not confirmed twice — the catalog, measured.

## What the operator said (2026-09-16)

> «Estoy un poco hasta los huevos de tener que confirmar las cosas. Si le digo borra una cita de la agenda
> llamada tal, la borras y punto. A menos que haya dos que se llamen igual, parecidas, que exista alguna duda.»

## What was measured before this

Consent was decided by `action_mode()` → `widgets/actions.classify()` → the manifest's `confirm:true`, which
is a property of the ACTION and knows nothing about the CALL. Meanwhile `widgets/refs.resolve()` had already
asked «which one?» when the reference was ambiguous. So a reference that resolved to exactly ONE item passed
the useful question and then hit a second one that added no information. That second question is the friction.

## What is pinned

That a named single target RUNS, that a sweep still ASKS (V2-707's rail, born from 147 DELETE requests
against his real calendar), that the difference between them is DECLARED in the manifest rather than decided
by a verb anywhere in the path, and that a widget written tomorrow inherits `standard` without declaring it.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from nucleo.flash import frontend as fe
from widgets import actions as wa

ENGINE = pathlib.Path(__file__).resolve().parents[4]


# ── 1 · his own sentence, as the catalog answers it ─────────────────────────────────────────────────────

_RUNS = [
    ("agenda", "cancel_meeting", {"title": "Dentista"}, "borra la cita del dentista"),
    ("contactos", "remove_contact", {"contactId": "c17"}, "borra el contacto Juan"),
    ("archivos", "delete_file", {"fileId": "f9"}, "borra el informe.pdf"),
    ("mensajeria", "trash", {"n": 3}, "tira ese correo"),
    ("youtube", "delete_list", {"name": "Rock"}, "borra la lista Rock"),
    ("archivos", "torrent_remove", {"id": "t3"}, "cancela esa descarga"),   # V2-764: was torrent:remove
    ("musica", "disconnect", {}, "desconecta Spotify"),
    ("agenda", "disconnect", {}, "desconecta el calendario"),
    ("mensajeria", "send_draft", {}, "envía el borrador"),
]

_STILL_ASK = [
    ("agenda", "clear_all", {}, "vacía la agenda"),
    ("agenda", "clear_range", {}, "borra las citas de octubre"),
    ("agenda", "dedupe_meetings", {}, "quita las citas repetidas"),
    ("agenda", "drop_project", {"projectId": "p2"}, "congela el proyecto entero"),
    ("youtube", "clear_history", {}, "borra el historial"),
    ("mensajeria", "clear_signature", {}, "borra mi firma"),
    ("mensajeria", "set_autoresponder", {"text": "estoy fuera"}, "activa el autorrespondedor"),
]


@pytest.mark.parametrize("wid,act,payload,order", _RUNS, ids=[c[3] for c in _RUNS])
def test_a_named_single_target_runs(wid, act, payload, order):
    assert fe.action_mode_now(wid, act, payload) == wa.FAST, (
        f"«{order}» still asks a second time after the reference already resolved to one thing")


@pytest.mark.parametrize("wid,act,payload,order", _STILL_ASK, ids=[c[3] for c in _STILL_ASK])
def test_a_sweep_still_asks_because_its_radius_is_not_what_he_named(wid, act, payload, order):
    """The counterweight, and the half that must never be traded for speed: «vacía la agenda» is a different
    act from «borra la cita del dentista», and the friction belongs to the radius."""
    assert fe.action_mode_now(wid, act, payload) == wa.CONFIRM, f"«{order}» stopped asking"


def test_an_empty_selector_on_a_targeted_action_still_asks():
    """An action that NAMES what it hits and arrives with that name empty did not understand the order, and
    acting on everything is never the repair."""
    assert fe.action_mode_now("contactos", "remove_contact", {}) == wa.CONFIRM


def test_the_empty_selector_of_a_FAST_action_is_still_refused_where_it_always_was():
    """⚠️ Measured while writing this file: `agenda:cancel_meeting` is FAST by design (V2-707 F1 — one row
    with a selector runs, N>1 asks by radius), so the consent rule never sees it and an empty `title` comes
    back FAST from here. That is not a hole: the V2-705 contract refuses it at the single funnel, one layer
    down, and that is where this belongs. Asserted here so the next reader does not mistake this door's
    silence for permission — the two rails are about different questions and both have to be true."""
    from widgets import contract
    assert fe.action_mode_now("agenda", "cancel_meeting", {"title": "  "}) == wa.FAST
    refusal = contract.guard("agenda", "cancel_meeting", {"title": "  "})
    assert refusal is not None and refusal.get("error") == contract.SELECTOR_MISSING


# ── 2 · the difference is DECLARED, not decided by a verb ───────────────────────────────────────────────

def test_every_shipped_widget_declares_its_security_level_and_they_are_all_standard():
    """His instruction verbatim: «cuando hagamos un widget diremos cuál es el nivel de seguridad, y pondremos
    de momento a todos por defecto nivel estándar»."""
    levels = {}
    for p in sorted((ENGINE / "widgets").glob("*/manifest.json")):
        man = json.loads(p.read_text(encoding="utf-8"))
        levels[man.get("id") or p.parent.name] = man.get("security")
    assert levels, "no manifests found — the test is measuring nothing"
    assert set(levels.values()) == {"standard"}, f"a widget declares something else: {levels}"


def test_no_verb_is_matched_anywhere_in_the_consent_path():
    """The doctrine's third question, made mechanical: «¿es lo que añado una frase sobre cómo comportarse?».
    A regex over Spanish/English verbs in this path would be a rail on judgement wearing a safety hat."""
    from nucleo import consent
    src = pathlib.Path(consent.__file__).read_text(encoding="utf-8")
    decision = src.split("# ── THE RULE")[1].split("# ── Spoken overrides")[0]
    for verb in ("borrar", "eliminar", "pagar", "enviar", "delete", "pay", "send", "publicar"):
        assert verb not in decision.lower(), f"the rule matches the verb «{verb}» — that is a verb table"


def test_a_singleton_and_a_sweep_are_told_apart_by_the_manifest_not_by_the_missing_selector():
    """Both declare no selector and they are opposite acts: `musica:disconnect` touches the one linked
    account, `agenda:clear_all` touches every appointment. Reading «no selector» as «unbounded» charged a
    sweep's friction to a singleton, which is the shape of the complaint."""
    man = json.loads((ENGINE / "widgets" / "musica" / "manifest.json").read_text(encoding="utf-8"))
    assert man["actions"]["disconnect"].get("singleton") is True
    agenda = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))
    assert agenda["actions"]["clear_all"].get("singleton") is not True
    assert agenda["actions"]["drop_project"].get("fans_out") is True, "one selector, many tasks discarded"


# ── 3 · nothing that was not about friction moved ───────────────────────────────────────────────────────

def test_an_undeclared_action_is_still_undeclared_and_an_escalation_still_escalates():
    """This decides FRICTION and must never decide whether something is code work."""
    assert fe.action_mode_now("agenda", "inexistente", {}) is None
    assert fe.action_mode_now("navegador", "automate", {}) == wa.ESCALATE


def test_a_plain_fast_action_is_untouched():
    assert fe.action_mode_now("agenda", "add_meeting", {"title": "x"}) == wa.FAST


def test_an_unreadable_verdict_keeps_the_friction_it_had_rather_than_dropping_it():
    """Fails toward the OLD behaviour: a malformed widget loses the improvement, never the guard."""
    import nucleo.consent as consent
    real = consent.asks
    consent.asks = lambda v: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        assert fe.action_mode_now("contactos", "remove_contact", {"contactId": "c17"}) == wa.CONFIRM
    finally:
        consent.asks = real
    assert fe.action_mode_now("contactos", "remove_contact", {"contactId": "c17"}) == wa.FAST
