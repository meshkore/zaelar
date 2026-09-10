"""V2-653 F0 — the canvas arbiter: ONE decision tree for every canvas mutation, in shadow.

This file is the CONFORMANCE SUITE the migration leans on: each case is a MEASURED incident from the
last month of initiatives, replayed against `decide()`. When a door is armed (F1/F2) and its ad-hoc
guard retired, these cases are what proves the behaviour survived the move. The leaves are the proven
license modules (`canvas_license`, `close_guards`, manifest-driven `producers`/`actions`/`runtime`),
so a red here means the TREE disagrees with doctrine that already held live — investigate before
touching either.

Shadow contract also pinned: the tap assembles context from the observer stream, judges every widget
command, emits `kind="arbiter"` verdicts, never raises, and dies with ZAELAR_ARBITER_SHADOW=0.
"""
import re
from pathlib import Path

import pytest

from nucleo import canvas_arbiter as arb
from nucleo.flash import canvas_license as lic

ENGINE = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _fresh_reopen_state():
    lic._RECENT_CLOSES.clear()
    yield
    lic._RECENT_CLOSES.clear()


# ── level 1 · WHO: the closed provenance set ─────────────────────────────────────────────────────────────

def test_the_operators_hands_are_always_licensed():
    assert arb.decide("show", "agenda", "user").allow is True
    assert arb.decide("close", "youtube", "user").allow is True


def test_lifecycle_and_system_writes_pass():
    assert arb.decide("show", "agenda", "system").rule == "lifecycle"


def test_a_worker_mutation_rides_its_task():
    v = arb.decide("data", "results", "worker:t3", action="present")
    assert v.allow is True and v.rule == "task-owned" and v.evidence.get("tid") == "t3"


def test_the_action_maps_seeded_phrase_is_the_license():
    assert arb.decide("close", "mensajeria", "actionmap").rule == "seeded-grammar"


def test_an_unknown_provenance_is_judged_like_the_model_not_waved_through():
    """Anything unrecognized lands on the strictest branch — a new door cannot grant itself a pass."""
    assert arb.decide("show", "agenda", "quien-sabe", text="bla bla").allow is False


# ── level 2 · turn credit and backstop duplication ───────────────────────────────────────────────────────

def test_an_ambient_turn_licenses_nothing():
    """The V2-647 class, server-side: room speech may not mutate the canvas."""
    v = arb.decide("show", "agenda", "flash", text="enséñame la agenda", turn_credit=False)
    assert v.allow is False and v.rule == "ambient-turn"


def test_a_backstop_never_duplicates_a_turn_that_already_acted():
    v = arb.decide("data", "agenda", "backstop", action="add_meeting", model_acted=True)
    assert v.allow is False and v.rule == "backstop-duplicate"


# ── level 3 · the license leaves, replayed from the measured incidents ──────────────────────────────────

def test_an_insult_does_not_close_a_widget():
    """V2-635, session 34386d8f: «Johnny eres tonto» closed the video widget."""
    assert arb.decide("close", "youtube", "flash", text="Johnny eres tonto").rule == "close-drag"
    assert arb.decide("close", "youtube", "flash",
                      text="Vale, Johnny, cierra el vídeo").rule == "close-grammar"


def test_pausing_is_not_fullscreen():
    """V2-635: «Johnny pausa el vídeo» became fullscreen — no screen-size words, no screen op."""
    assert arb.decide("screen", "youtube", "flash", text="pausa el vídeo").rule == "screen-drag"
    assert arb.decide("screen", "youtube", "flash",
                      text="ponlo a pantalla completa").evidence.get("direction") == "fullscreen"
    assert arb.decide("screen", "youtube", "flash",
                      text="minimiza el vídeo").evidence.get("direction") == "minimize"


def test_a_close_order_licenses_no_show():
    """V2-567: «Cierra los contactos» was answered with show_widget(mensajeria)."""
    v = arb.decide("show", "mensajeria", "flash", text="Cierra los contactos")
    assert v.allow is False and v.rule == "show-against-close-order"


def test_chatter_does_not_reopen_a_just_closed_widget_but_an_order_does():
    """V2-650b, sid 3d394…: room chatter re-emitted a DISCARDED show 8s after his close."""
    lic.note_operator_close("youtube")
    chatter = arb.decide("show", "youtube", "flash",
                         text="Avisando de que aquí está pasando algo")
    assert chatter.allow is False and chatter.rule == "reopen-unlicensed"
    assert arb.decide("show", "youtube", "flash", text="pon otro vídeo de Ronaldinho").allow is True


def test_a_replayed_play_order_is_an_order_and_the_dentist_duplicate_stays_dead():
    """V2-650 both halves: «dale al play» re-licenses a DECLARED production; agenda declares none, so
    an identical add_meeting with no overlap in the turn stays drag."""
    play = arb.decide("data", "musica", "flash", action="play_playlist",
                      payload={"playlist": "true-blue"},
                      text="Vamos, dale al play, a la primera canción")
    assert play.allow is True and play.rule == "replay-order"
    drag = arb.decide("data", "agenda", "flash", action="add_meeting",
                      payload={"title": "cita agencia tributaria"},
                      text="Veo, además, que has colocado el dos ítems.")
    assert drag.allow is False and drag.rule == "data-drag"


def test_a_write_the_turn_names_is_licensed():
    """The V2-038 escape as a positive rule: «Añade… la agencia tributaria» names its payload."""
    v = arb.decide("data", "agenda", "flash", action="add_meeting",
                   payload={"title": "Cita Agencia Tributaria", "startTime": "11:30"},
                   text="Añade en la agenda mañana una cita a las once treinta en la agencia tributaria")
    assert v.allow is True and v.rule == "payload-in-turn"


def test_a_view_op_is_a_lens_and_passes():
    """V2-545: a declared view action never writes anything to undo — «enséñame el correo»."""
    v = arb.decide("data", "mensajeria", "flash", action="show_view",
                   payload={"platform": "email"}, text="enséñame el correo")
    assert v.allow is True and v.rule == "view-op"


def test_a_show_the_turn_mentions_resolves_through_the_manifest():
    """Fork-safe by construction: the license is the widget's OWN aliases (V2-082), not our code."""
    assert arb.decide("show", "agenda", "flash", text="enséñame la agenda").rule == "turn-mention"
    assert arb.decide("show", "agenda", "flash", text="qué bonito día hace hoy").allow is False


def test_the_tree_never_raises_on_garbage_and_an_unknown_op_inherits_nobodys_pass():
    """Found by this very case's first run: `op=None` with an unattributed src walked out as
    `lifecycle` — the op vocabulary is validated BEFORE the provenance ladder."""
    v = arb.decide(None, None, None, action=None, payload="not-a-dict", text=None)  # type: ignore
    assert v.allow is False and v.rule == "unknown-op"
    assert arb.decide("teleport", "agenda", "system").rule == "unknown-op"


# ── the shadow tap ───────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def verdicts(monkeypatch):
    """Capture the arbiter's own emits without touching the real observer (no file writes in a unit)."""
    import voice.observer as obs
    out = []
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        out.append({"kind": kind, "label": label, "text": text, **(extra or {})}))
    arb._last_turn.update(text="", ts=0.0, credit=True)
    return out


def test_the_tap_judges_a_widget_command_with_the_assembled_turn(verdicts):
    arb.shadow_tap("transcript", "🗣", "cierra el widget de youtube", "user", None)
    arb.shadow_tap("widget", "close", "", "", {"id": "youtube", "src": "flash"})
    assert len(verdicts) == 1
    v = verdicts[0]
    assert v["kind"] == "arbiter" and v["allow"] is True and v["rule"] == "close-grammar"
    assert v["shadow"] is True, "F0 verdicts must say they are shadow — nothing is enforced yet"


def test_a_data_event_carries_its_own_phrase_and_is_judged_on_it(verdicts):
    """`data:*` events already log the originating phrase (V2-039) — the tap must use IT, not the
    assembled turn, so a stale transcript cannot mislabel a fresh data-op."""
    arb.shadow_tap("transcript", "🗣", "algo viejo sin relación", "user", None)
    arb.shadow_tap("widget", "data:add_meeting",
                   "Añade una cita mañana en la agencia tributaria", "",
                   {"id": "agenda", "action": "add_meeting", "src": "flash",
                    "payload": {"title": "cita agencia tributaria", "date": "2026-09-11"}})
    assert verdicts and verdicts[0]["rule"] == "payload-in-turn"
    assert verdicts[0]["allow"] is True


def test_an_ambient_verdict_removes_the_turns_credit(verdicts):
    arb.shadow_tap("transcript", "🗣", "enséñame la agenda", "user", None)
    arb.shadow_tap("ambient", "🙉 ambiente — no dirigido a zaelar", "", "user", None)
    arb.shadow_tap("widget", "show", "", "", {"id": "agenda", "src": "flash"})
    assert verdicts and verdicts[0]["rule"] == "ambient-turn" and verdicts[0]["allow"] is False


def test_the_kill_switch_silences_the_shadow(verdicts, monkeypatch):
    monkeypatch.setenv("ZAELAR_ARBITER_SHADOW", "0")
    arb.shadow_tap("widget", "show", "", "", {"id": "agenda", "src": "flash"})
    assert verdicts == []


def test_the_tap_never_raises_even_on_garbage(verdicts):
    arb.shadow_tap("widget", "show", None, None, "not-a-dict")  # type: ignore
    arb.shadow_tap("widget", "data:", None, None, {})  # type: ignore


# ── the wiring, structural (comment-stripped, per the V2-573 lesson) ────────────────────────────────────

def _stripped(path: str) -> str:
    src = (ENGINE / path).read_text(encoding="utf-8")
    return re.sub(r"(?m)#.*$", "", src)


def test_the_observer_calls_the_tap_and_classifies_the_kind():
    src = _stripped("voice/observer.py")
    assert "_arb.shadow_tap(kind, label, text, role, extra)" in src, (
        "the F0 wiring is ONE call in observer.emit — without it the shadow measures nothing")
    import voice.observer as obs
    assert obs._CAT.get("arbiter") == "widget", "the verdict kind must belong to a viewer family"


def test_the_data_op_log_carries_its_payload_for_the_arbiter():
    """The OTHER half of the payload-in-turn license: the tap reads `extra['payload']`, and the ONLY
    writer of that key is `_log_dataop`'s emit in the voice provider. A first disarm of that emit came
    back GREEN because the tap test hands in its own dict — this pins the carrier itself."""
    src = _stripped("voice/engine/llm/providers/nucleo.py")
    i = src.find('emit("widget", f"data:{action_name}"')
    assert i >= 0, "the data-op order log (_log_dataop) must still exist"
    window = src[i:i + 400]
    assert '"payload"' in window, (
        "the data:* event must carry the op's payload — without it the arbiter cannot judge "
        "payload-in-turn and every legitimate agenda write reads as a veto in shadow")
