"""V2-723 — an action does not manufacture permission for its own side effects.

## Where this comes from

An external audit of the widget layer (2026-09-18) read the catalog, the single dispatch and the
browser-owned canvas as sound, and put the weak point exactly where the month's incidents live:

> «Authorizing an action is not the same as authorizing all its effects. […] An action cannot manufacture
> permission for its own side effects. An unauthorized effect should be suppressed — or require approval
> when essential to completing the action.»

Measured the day before: `musica:pause` is an action the operator asked for, and running it re-opened a
card he had closed, because the connector's result said `surface: "widget"`. One authorization was silently
spending a second one. Thirteen call sites emitted `show` directly, each with its own reasoning and none of
it written down, so the canvas could not tell an honest mount from a drag.

## What this pins

  1. **The vocabulary** (`widgets/effects.py`) — derived from the four declarations that already existed
     (`actions.classify`, `actions.is_view`, `runtime.produce/suspend/output`, plus whatever a manifest
     declares outright) instead of a fifth flag nobody keeps in sync.
  2. **The door** (`canvas_visibility.present`) — a presentation carries a declared REASON, the reason's
     claim is checked against the widget's declaration rather than believed, an open card is never raised
     again, and a refusal is EMITTED (the audit's «include suppressed effects»).
  3. **The ratchet** — the count of direct `emit("widget", "show")` sites may only go down, so the next one
     cannot be born anonymous while the remaining ones are migrated.
  4. **The down payment** — a bare «yes» licenses media only where we actually asked something. Measured
     2026-09-17: «Okay. What if» licensed a `resume` and restarted music the operator had paused by hand.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

from nucleo.flash import canvas_license as lic, canvas_visibility as cv
from widgets import effects as fx

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def shown():
    """Collects what the door would put on the bus, so a test reads EFFECTS and not mocks."""
    out: list[tuple] = []
    return out, (lambda kind, label, extra=None: out.append((kind, label, dict(extra or {}))))


# ── 1 · the vocabulary is derived from what the widgets already declare ──────────────────────────────────

def test_an_action_carries_the_effects_its_widget_declares():
    assert fx.of("musica", "play") == {fx.DATA_WRITE, fx.OUTPUT_START, fx.PRESENT_MOUNT}
    assert fx.of("musica", "pause") == {fx.DATA_WRITE, fx.OUTPUT_STOP}
    assert fx.of("musica", "volume_up") == {fx.DATA_WRITE}
    assert fx.of("musica", "open_view") == {fx.DATA_READ}        # a lens writes nothing to undo
    assert fx.of("agenda", "show_day") == {fx.DATA_READ}
    assert fx.of("agenda", "add_meeting") == {fx.DATA_WRITE}


def test_an_action_nobody_declared_carries_nothing():
    """«No declared effect» means «no authorization to spend», never «unknown, so allow»."""
    assert fx.of("musica", "no_such_action") == frozenset()
    assert fx.of("no_such_widget", "play") == frozenset()
    assert fx.of("", "") == frozenset()


def test_the_mount_rides_the_channel_the_widget_names(monkeypatch):
    """A producer needs its surface only when its output lives there. The declaration is `runtime.output`,
    and this is the case the tree has no example of yet: a widget that produces on NO exclusive channel
    (a recorder writing to disk, a process) starts producing without anything having to be on screen.
    Deriving the mount from `produce` alone would put its card in front of the operator for nothing."""
    assert fx.carries("musica", "play", fx.PRESENT_MOUNT)
    assert not fx.carries("agenda", "add_meeting", fx.PRESENT_MOUNT)

    from widgets import producers, runtime
    monkeypatch.setattr(runtime, "get", lambda wid: {"actions": {"start": {}},
                                                     "runtime": {"produce": ["start"]}})   # no `output`
    monkeypatch.setattr(producers, "starts_production", lambda w, a: a == "start")
    assert fx.of("grabadora", "start") == {fx.DATA_WRITE, fx.OUTPUT_START}
    assert not fx.carries("grabadora", "start", fx.PRESENT_MOUNT)


def test_a_manifest_may_declare_an_effect_and_a_typo_is_ignored(monkeypatch):
    from widgets import runtime
    monkeypatch.setattr(runtime, "get", lambda wid: {
        "actions": {"beam": {"effects": ["external.send", "not_an_effect"]}}})
    assert fx.of("x", "beam") == {fx.EXTERNAL_SEND, fx.DATA_WRITE}
    assert "not_an_effect" not in fx.of("x", "beam")


# ── 2 · the door: a reason, checked, or nothing happens ──────────────────────────────────────────────────

def test_a_presentation_without_a_reason_is_suppressed(shown):
    out, emit = shown
    assert cv.present("musica", reason="", action="play", known=[], emit=emit) is False
    assert out[0][1] == "🚫 presentación suprimida" and "sin motivo" in out[0][2]["detail"]
    assert not any(label == "show" for _, label, _ in out)


def test_a_made_up_reason_does_not_pass_either(shown):
    out, emit = shown
    assert cv.present("musica", reason="because-i-said-so", action="play", known=[], emit=emit) is False
    assert out[0][1] == "🚫 presentación suprimida"


def test_the_claim_is_checked_against_the_declaration_not_believed(shown):
    """The measured incident, as a claim: `pause` calling itself a mount. The door reads the manifest."""
    out, emit = shown
    assert cv.present("musica", reason="producer-mount", action="pause", known=[], emit=emit) is False
    assert "no declara" in out[0][2]["detail"]
    assert cv.present("musica", reason="producer-mount", action="play", known=[], emit=emit) is True
    assert out[-1][1] == "show" and out[-1][2]["reason"] == "producer-mount"


def test_an_open_card_is_never_raised_again(shown):
    out, emit = shown
    assert cv.present("musica", reason="turn-order", known=["musica::t1"], emit=emit) is False
    assert "ya está abierta" in out[0][2]["detail"]


def test_a_turn_order_opens_a_card_that_declares_no_production(shown):
    """The door is not «producers only»: most cards are presented because the operator asked."""
    out, emit = shown
    assert cv.present("agenda", reason="turn-order", known=[], emit=emit) is True
    assert out[-1][2]["reason"] == "turn-order" and out[-1][2]["id"] == "agenda"


def test_the_reason_travels_into_the_event(shown):
    """«Trace the full chain … include suppressed effects and disagreement reasons» — the audit's §5."""
    out, emit = shown
    cv.present("documento", reason="task-owned", src="worker:t9", known=[], emit=emit)
    kind, label, extra = out[-1]
    assert (kind, label) == ("widget", "show")
    assert extra["src"] == "worker:t9" and extra["reason"] == "task-owned"


def test_every_reason_in_the_vocabulary_is_one_the_door_can_act_on():
    assert cv.REASONS == {"operator-hands", "turn-order", "producer-mount", "task-owned",
                          "widget-handoff", "lifecycle"}


# ── 3 · nothing new is born anonymous ────────────────────────────────────────────────────────────────────

#: Direct `emit("widget", "show")` sites still outside the door, frozen on 2026-09-18. The voice lane, the
#: probe's music mirror and the video/intent paths were migrated first because they are where the measured
#: incidents happened; the rest (workers, sheets, the action map, the navigator's task cards) are a
#: MIGRATION, not a defect — each has a real authorization, it is simply not written down yet. The number
#: may only go down. The browser's own echo in `server/voice_api.py` is not one of these: that is the canvas
#: telling the engine what the operator did, the opposite direction.
# V2-728: 21 → 19. Asking git instead of the disk (see `_direct_show_sites`) showed the real count was
# already 19; the extra two were slack left over from presentations that had been closed without
# lowering the ceiling. A ratchet with slack does not bite the next addition, which is its whole job.
_ANONYMOUS_SHOWS_MAX = 19


def _direct_show_sites() -> list[str]:
    """Every direct `emit("widget", "show")` in the PRODUCTION tree, asked of git rather than of the disk.

    V2-728 — this used to `rglob` the checkout, which counts whatever the operator happens to keep in it.
    Measured the day this changed: `.meshkore/snapshots/` (GITIGNORED, the §20 pre-edit copies the daemon
    writes before an agent edits a file) holds verbatim copies of production modules, so editing one file
    twice added two phantom call sites and put the ratchet red over code that does not exist. Same shape and
    same fix as V2-727's model-name sweep: a rule about what the ENGINE does is a rule about what is
    COMMITTED, and asking git is both the correct question and the one that cannot reach his own files.
    """
    done = subprocess.run(["git", "ls-files", "-z", "*.py"], cwd=str(ENGINE),
                          capture_output=True, timeout=60)
    assert done.returncode == 0, "the sweep needs git to know what the tree IS"
    out = []
    for rel in done.stdout.decode("utf-8", errors="ignore").split("\0"):
        if not rel or rel.startswith(("tests/", ".venv/")) or rel.endswith("canvas_visibility.py"):
            continue
        if rel == "server/voice_api.py":
            continue
        p = ENGINE / rel
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:                      # tracked but not in the working tree
            continue
        for i, line in enumerate(lines, 1):
            if re.search(r'emit\("widget", "show"', line):
                out.append(f"{rel}:{i}")
    return out


def test_the_number_of_anonymous_presentations_only_goes_down():
    sites = _direct_show_sites()
    assert len(sites) <= _ANONYMOUS_SHOWS_MAX, (
        "a new presentation was emitted without a declared reason — it goes through "
        "`canvas_visibility.present(reason=…)`:\n  " + "\n  ".join(sites))


def test_the_voice_provider_holds_none_of_them():
    """The channel the incidents came from is fully migrated, so its own tests stay honest."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert 'emit("widget", "show"' not in src


# ── 4 · a «yes» is an answer only where there was a question ─────────────────────────────────────────────

def test_the_turn_that_restarted_the_music_licenses_nothing_now():
    """Session c553a1e0: «Okay. What if» — the operator starting an unrelated sentence — licensed a
    `resume`, and the music he had paused by hand came back."""
    assert lic.video_license("Okay. What if") is False
    assert lic.video_license("Okay. What if", "Now playing Bruce Springsteen - Hungry Heart.") is False


def test_a_yes_to_an_unrelated_question_licenses_nothing():
    """V2-724, the audit's adjacent correction: «we previously asked something» is necessary and NOT
    sufficient. Bound only to «a question existed», a «sí» to «¿te apunto la cita del dentista?» still
    licensed a video load — one proposal's answer spending another proposal's authority."""
    for offer in ("¿Te apunto la cita del dentista para el jueves?",
                  "¿Quieres que le escriba a Ivan?",
                  "Do you want me to delete the rest?"):
        assert lic.video_license("sí", offer) is False, offer
        assert lic.offer_of_media(offer) is False, offer


def test_the_proposals_class_is_read_from_the_widgets_own_words():
    """No table of ours: the certainty resolver first, then the vocabulary the PRODUCING widgets publish
    about themselves. A fork that adds a player brings its own words with it."""
    for offer in ("What kind of music, Richard? Give me a vibe or an artist.",
                  "¿Busco de nuevo el vídeo?",
                  "Shall I put the playlist back on?",
                  "¿Te pongo otra canción?"):
        assert lic.offer_of_media(offer) is True, offer
        assert lic.video_license("sí", offer) is True, offer


def test_a_statement_is_not_a_proposal():
    """Both halves are required: the class AND a question actually pending."""
    assert lic.offer_of_media("Now playing Bruce Springsteen - Hungry Heart.") is False
    assert lic.offer_of_media("") is False


def test_a_yes_still_answers_our_own_offer():
    """The escape exists for this and keeps working — that is why it is not simply deleted."""
    assert lic.video_license("sí", "¿Te busco otra vez el vídeo?") is True
    assert lic.video_license("sure", "Shall I put the playlist back on?") is True
    # …and the affirmative table is NOT widened to catch «go ahead»: growing a word list is the habit the
    # audit names, and he can always say it with a verb. What changed is the FACT it depends on.
    assert lic.video_license("go ahead", "Shall I put the playlist back on?") is False


def test_an_order_with_a_verb_never_needed_the_escape():
    for said in ("pon algo de rock", "reproduce la lista", "play the moonwalk video"):
        assert lic.video_license(said) is True, said


def test_the_reopen_license_binds_to_a_proposal_about_that_card():
    """Same correction, the other effect: a «vale» reopens a just-closed card only when the pending
    proposal was about THAT card. «¿Lo vuelvo a abrir?» names nothing, so it authorizes nothing — the safe
    direction, since the alternative is a card resurrected over an answer to something else."""
    lic.note_operator_close("youtube")
    try:
        assert lic.reopen_license("youtube", "vale") is False
        assert lic.reopen_license("youtube", "vale", last_reply="¿Te apunto la cita?") is False
        assert lic.reopen_license("youtube", "vale", last_reply="¿Lo vuelvo a abrir?") is False
        assert lic.reopen_license("youtube", "vale", last_reply="¿Vuelvo a abrir el vídeo?") is True
        # …and his own words still reopen it with no proposal at all, exactly as before.
        assert lic.reopen_license("youtube", "abre otra vez el vídeo de YouTube") is True
    finally:
        lic._RECENT_CLOSES.clear()


def test_both_channels_hand_over_what_we_said():
    """A fact only one channel reads is a mirror that drifts (V2-539): the provider, the probe and the
    arbiter's tap all pass the previous reply."""
    prov = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    arb = (ENGINE / "nucleo/canvas_arbiter.py").read_text(encoding="utf-8")
    assert "last_reply=brain._last_reply" in prov
    # V2-741 — the call gained the turn's brief so a verdict can overrule the verb table. This
    # channel fires no brief yet, so the argument is what keeps the two from drifting apart.
    assert "video_license(text, _last_assistant_line(sess.window), brief=" in probe
    assert 'role == "assistant"' in arb and "last_reply=str(_last_turn" in arb
