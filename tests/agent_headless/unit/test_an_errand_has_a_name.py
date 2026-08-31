"""An errand is CALLED something, and that is not the same string as what it was ASKED (V2-530, 2026-08-31).

Measured on the operator's own engine, session `7cab1afd`. Two results sheets side by side, one per errand,
and the titles he read on them were:

    «Sanidad con Sanitas en Soria»
    «Me parece bien. Oye, una cosita, estabas buscándome un médico. ¿Eres…»

The second is a slice of the conversation, and it is a slice that ends BEFORE the errand is even mentioned.
The same string was also what the voice read out when the worker needed something («Oye, el proceso "Me parece
bien. Oye, una cosita, estabas" pregunta: …»), so the defect was audible as well as visible — and it made the
disambiguation question unanswerable, since one of its two options was a pleasantry.

Why the goal reads like that, and why fixing the GOAL would be the wrong fix: it is the operator's own words on
purpose. The promise backstop escalates the raw turn (`nucleo/flash/router_guards`) because fidelity is what
lets the worker do the right thing — he said «invéntate el apellido si te lo piden» and that has to survive
verbatim. So the goal stays a BRIEF, and the NAME becomes its own field.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from nucleo import errand_title as et

ENGINE = Path(__file__).resolve().parents[3]


# ── the instant title ─────────────────────────────────────────────────────────────────────────────────────

def test_a_short_goal_is_its_own_title():
    assert et.provisional("Pedir cita de traumatología") == "Pedir cita de traumatología"


def test_a_long_goal_is_cut_on_a_WORD_boundary():
    """The one defect the instant path fixes by itself. `goal[:40]` of the measured turn produced «Me parece
    bien. Oye, una cosita, estabas» — the cut landed mid-phrase, before the errand, and read as gibberish."""
    goal = "Me parece bien. Oye, una cosita, estabas buscándome un médico. ¿Eres capaz de pedir cita tú solo?"
    out = et.provisional(goal)
    assert len(out) <= et.TITLE_MAX + 1        # +1 for the ellipsis
    assert out.endswith("…"), "a truncated title must SAY it is truncated"
    kept = out.rstrip("…").strip()
    assert kept in " ".join(goal.split()), "it must not invent words"
    # The whole point: the last word survives WHOLE. `goal[:56]` alone lands inside «médico», and the
    # earlier version of this assertion could not tell that apart from a clean cut.
    words = " ".join(goal.split()).split(" ")
    assert kept.split(" ")[-1] in words, f"cut mid-word: …{kept[-14:]!r}"


def test_whitespace_is_normalised_so_a_dictated_goal_does_not_look_broken():
    assert et.provisional("Pedir   cita\n\nen PAMA") == "Pedir cita en PAMA"


def test_provisional_is_NOT_clever_and_that_is_the_point():
    """Everything a heuristic could do here — drop the greeting, find the request clause — it would do by
    GUESSING, and a wrong guess renames the operator's errand to something he never said. Naming needs
    understanding; that is what `compose` is for."""
    goal = "Oye, una cosita, búscame un traumatólogo"
    assert et.provisional(goal) == goal, "no clause surgery on the instant path"


# ── reading the model's answer ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,want", [
    ("Pedir cita de traumatología en PAMA", "Pedir cita de traumatología en PAMA"),
    ("«Pedir cita en PAMA»", "Pedir cita en PAMA"),
    ('"Cita de traumatología"', "Cita de traumatología"),
    ("Título: Cita en PAMA", "Cita en PAMA"),
    ("  Cita en PAMA.  ", "Cita en PAMA"),
])
def test_a_model_answer_is_read_generously(raw, want):
    assert et.clean(raw) == want


def test_but_a_paragraph_is_not_a_title():
    """Rejecting is the safe direction: the provisional title is already on screen and already truthful, so a
    dubious replacement buys nothing and can lose meaning the operator's own words carried."""
    assert et.clean("Claro, aquí tienes el nombre. " * 20) == ""
    assert et.clean("") == ""


def test_a_composed_title_never_exceeds_the_cap():
    assert len(et.clean("x" * 80)) <= et.TITLE_MAX


# ── composing ─────────────────────────────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def test_compose_returns_empty_when_disabled(monkeypatch):
    monkeypatch.setenv("ZAELAR_TITLE_MODEL", "off")
    assert _run(et.compose("Pedir cita")) == ""
    assert not et.enabled()


def test_compose_NEVER_raises_and_empty_means_keep_the_provisional(monkeypatch):
    """A slow or dead provider can only cost a box that keeps the name it already had. Nothing upstream waits
    for this, so nothing upstream may be broken by it."""
    monkeypatch.setenv("ZAELAR_TITLE_MODEL", "on")

    class _Boom:
        def complete(self, *a, **k):
            raise RuntimeError("provider down")

    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _Boom)
    assert _run(et.compose("Pedir cita de traumatología")) == ""


def test_compose_reads_the_model_and_a_dash_means_no_errand_inside(monkeypatch):
    monkeypatch.setenv("ZAELAR_TITLE_MODEL", "on")
    seen = {}

    class _Fake:
        def __init__(self, answer):
            self.answer = answer

        async def complete(self, msgs, **k):
            seen["msgs"] = msgs
            return self.answer

    monkeypatch.setattr("nucleo.research._spec", lambda: (object(), None))

    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda: _Fake("Cita de traumatología en PAMA"))
    assert _run(et.compose("Oye, una cosita… pídeme cita")) == "Cita de traumatología en PAMA"
    assert "Oye, una cosita" in seen["msgs"][-1]["content"], "the model must see the operator's own words"

    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda: _Fake("-"))
    assert _run(et.compose("mmm")) == "", "no errand inside → keep the provisional, do not invent one"


def test_no_provider_available_is_not_an_error(monkeypatch):
    monkeypatch.setenv("ZAELAR_TITLE_MODEL", "on")
    monkeypatch.setattr("nucleo.research._spec", lambda: (None, None))
    assert _run(et.compose("Pedir cita")) == ""


# ── the seam ──────────────────────────────────────────────────────────────────────────────────────────────

def test_the_sheet_the_task_and_the_voice_all_read_the_SAME_name():
    """One function because there are three readers — the sheet header, the disambiguation question that names
    open sheets, and the voice relaying a worker's question. A rule written three times is how it comes to be
    missing from one of them (four times this month, by this file's own count)."""
    from nucleo import sheets

    class _Rec:
        goal = "Me parece bien. Oye, una cosita, estabas buscándome un médico. ¿Eres capaz de pedir cita?"
        title = ""

    r = _Rec()
    assert sheets.title_of(r) == et.provisional(r.goal)
    r.title = "Cita de traumatología en PAMA"
    assert sheets.title_of(r) == "Cita de traumatología en PAMA", "a composed title wins over the brief"


def test_a_rec_with_no_goal_does_not_blow_up():
    from nucleo import sheets
    assert sheets.title_of(object()) == ""


def test_renaming_a_sheet_keeps_everything_it_HOLDS(tmp_path, monkeypatch):
    """Separate from `begin_task` because that one ESTRENA — it is the errand's opening gesture and wipes items,
    tabs and process. Renaming happens later, on a sheet the operator is already looking at; reusing
    `begin_task(fresh=True)` for it would erase the very results it is naming."""
    from widgets import store
    from widgets.results import data as sheet

    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()

    sheet.begin_task("Me parece bien. Oye, una cosita, estabas", fresh=True, sheet="t1")
    sheet.apply_action("present", {"title": "x", "sheet": "t1",
                                   "items": [{"title": "Centro Médico PAMA"}]})
    before = sheet.view_data("t1")["items"]

    out = sheet.rename_task("Cita de traumatología en PAMA", sheet="t1")
    after = sheet.view_data("t1")

    assert out["ok"] and after["title"] == "Cita de traumatología en PAMA"
    assert after["items"] == before, "renaming must not touch what the sheet holds"
    assert not sheet.rename_task("", sheet="t1")["ok"], "an empty name is not a rename"


def test_opening_the_sheet_ACTUALLY_names_it_with_the_errands_title(tmp_path, monkeypatch):
    """The wiring, and it is the half a source guard cannot cover: with `_sheet_open` reverted to the raw goal
    every other case in this file still passes — a decision nobody calls only proves the code compiles (V2-199,
    and the same disarm came back green here on the first try)."""
    from nucleo import sheets
    from widgets import store
    from widgets.results import data as sheet

    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()

    class _Rec:
        task_id = "7"
        goal = "Me parece bien. Oye, una cosita, estabas buscándome un médico. ¿Eres capaz de pedir cita?"
        title = "Cita de traumatología en PAMA"
        sheet = ""
        surface = "lista"

    rec = _Rec()
    sheets._sheet_open(rec)
    assert sheet.view_data(sheets.sheet_of(rec))["title"] == "Cita de traumatología en PAMA"


def test_and_retitling_an_OPEN_sheet_reaches_it(tmp_path, monkeypatch):
    """The other end: the composed name lands seconds later, on a sheet already on screen."""
    from nucleo import sheets
    from widgets import store
    from widgets.results import data as sheet

    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()

    class _Rec:
        task_id = "9"
        goal = "Oye, una cosita, estabas buscándome un médico"
        title = ""
        sheet = ""
        surface = "lista"

    rec = _Rec()
    sheets._sheet_open(rec)
    assert sheet.view_data(sheets.sheet_of(rec))["title"] == et.provisional(rec.goal)
    rec.title = "Cita de traumatología en PAMA"
    sheets.retitle(rec)
    assert sheet.view_data(sheets.sheet_of(rec))["title"] == "Cita de traumatología en PAMA"


def test_the_voice_relays_the_NAME_and_not_the_raw_brief():
    """`goal[:40]` of a raw turn is what made the voice say «el proceso "Me parece bien. Oye, una cosita,
    estabas" pregunta: …» — the cut landed before the errand was even mentioned."""
    # Scanned WITHOUT comments: the explanatory comment beside the fix names the old expression, and a
    # substring guard cannot tell a citation from a call — this file's own sibling guards were bitten by
    # exactly that (V2-426).
    lines = (ENGINE / "nucleo/loop.py").read_text(encoding="utf-8", errors="replace").splitlines()
    body = "\n".join(ln for ln in lines if not ln.strip().startswith("#"))
    assert 's.get("title") or s.get("goal")' in body, "the relay must prefer the errand's name"
    assert "goal[:40]" not in body, "a name read aloud with its last word amputated is worse than a longer one"


def test_the_live_projection_carries_the_name_BESIDE_the_brief_never_instead():
    """`goal` still carries the operator's own words — dedup compares them and the master audits them. `title`
    is what a human reads or hears."""
    body = (ENGINE / "nucleo/dispatch.py").read_text(encoding="utf-8", errors="replace")
    assert '"goal": r.goal[:120]' in body, "the brief must not be replaced by the name"
    assert '"title": _sheets.title_of(r)' in body


def test_naming_is_fire_and_forget_so_nothing_upstream_waits_for_it():
    # Comments stripped: commenting the call out left this guard green on the first disarm — a substring
    # scan cannot tell a live call from its own citation.
    lines = (ENGINE / "nucleo/dispatch.py").read_text(encoding="utf-8", errors="replace").splitlines()
    # …and the `def _name_errand(rec)` line matches the same substring, so the CALL is what gets counted.
    body = [ln.split("#", 1)[0] for ln in lines if not ln.lstrip().startswith("def ")]
    assert any("_name_errand(rec)" in ln for ln in body), \
        "the composer must be CALLED when the errand is created, not merely defined"
    body = "\n".join(body)
    assert "await _name_errand" not in body, "the errand may never wait for its own name"
