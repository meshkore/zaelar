"""We were telling the worker to do the exact thing our own permission gate refuses.

Measured across the whole first US batch (2026-08-27): every one of the four rounds carried the same internal
errors — `Contains simple_expansion`, `Contains brace with quote character (expansion obfuscation)` — and in
`cheapest-monitor__us` they cost the round: three navigations, ten searches, **zero structured products**.

The cause was ours. `worker_bridge act` is how the worker ASKS for a web search, and the prompt taught it as
`act <action> <json>` with the JSON pasted on the command line — which is precisely what the gate blocks. The
same prompt already taught the correct two-step `@file` form for the results sheet, and `read_payload` had
grown `@file` support for `act` on that same day (V2-379); only the sentence that teaches it was left behind.
So the worker hit a wall it had been aimed at, improvised, and sometimes never recovered.

These tests pin the shape of the instruction, not its wording: what must never come back is a prompt that
shows inline JSON for a bridge, or that stays silent about the two rejections a worker will actually meet.
"""
from __future__ import annotations

import json
import pathlib
import re

from nucleo import dispatch_prompts as DP


def _worker_prompt() -> str:
    """What the worker actually READS — built, not scraped from module constants.

    Both halves are built per worker: `_build_prompt` carries the bridge instructions and `_drawer_rules` the
    shell ones. Reading module constants instead would have made the first test pass on an empty string.
    """
    return "\n".join([
        DP._build_prompt("busca hoteles", "", True),
        DP._drawer_rules("/usr/bin/python"),
    ])


def test_no_bridge_is_taught_with_inline_json():
    """`act <action> {json}` is the pattern the gate refuses. Any bridge shown that way is a trap we set."""
    text = _worker_prompt()
    offenders = re.findall(r"worker_bridge act [^\n@]*\{", text)
    assert not offenders, f"the prompt still teaches inline JSON to a bridge: {offenders}"


def test_the_file_form_is_taught_instead():
    text = _worker_prompt()
    assert "worker_bridge act" in text
    assert "@" in text and re.search(r"worker_bridge act [^\n]*@", text), \
        "the worker is never shown the `@file` form for the bridge it uses to ask for searches"


def test_and_the_two_rejections_it_will_meet_are_named():
    """A rule the worker cannot connect to the error it just got is a rule it will not apply. The gate's own
    words are what appears in its transcript, so the prompt uses them."""
    text = _worker_prompt()
    assert "simple_expansion" in text, "nothing tells the worker what the expansion rejection means"
    assert "brace with quote" in text, "nothing connects the JSON rejection to writing a file instead"


def test_the_shell_rules_still_forbid_the_expansions_themselves():
    """Sensitivity: naming the error must not replace forbidding the cause."""
    text = _worker_prompt()
    assert "$(…)" in text and "${…}" in text


def test_the_single_ampersand_is_forbidden_TOO_and_by_its_own_name():
    """Measured 2026-08-28 on `find-best-hotel-city__us` (24/7 lab): the worker ended a command with `&` and
    our own gate killed it — *«This command uses the `&` background operator, which defers execution past
    approval-time safety checks»*. The round died at 4 turns with six navigations and zero results.

    The rule listed `&&` and never a single `&`. They are different operators, and the rejection the worker
    reads for `&` is a THIRD message, unlike either of the two the prompt teaches — so a model that obeyed
    «no `&&`» to the letter had nothing to connect its error to. Same defect as the one this file was
    written for, one operator over.
    """
    text = _worker_prompt()
    assert "background operator" in text, "the worker is never told what the `&` rejection means"
    assert "`&` " in text or "un solo `&`" in text.lower() or "NI UN SOLO `&`" in text


def test_and_it_says_what_to_do_INSTEAD_of_backgrounding():
    """Forbidding without an alternative is how a worker ends up silent: the slow work IS asynchronous
    already, through the bridges, so there is nothing `&` was needed for."""
    text = _worker_prompt()
    i = text.find("background operator")
    assert i > 0 and "wait" in text[i:i + 400], "no alternative offered next to the ban"


def test_the_double_ampersand_rule_survives():
    """Sensitivity: the new rule must not have replaced the old one — they are different operators and both
    are blocked."""
    assert "`&&`" in _worker_prompt()


def test_the_cd_rejection_is_named_too_and_the_false_premise_is_answered():
    """`cd` blocked is the THIRD most common measured anomaly on the board (9 across two variants,
    2026-08-28) — and the worker is not being careless. `python -m nucleo.nav_cli` LOOKS like it needs the
    repo root, so changing into it is a correct inference from what we showed it; the environment already
    carries the path, and nothing said so.

    The rule ("don't leave your directory") was there and still is. What was missing is the same thing that
    was missing for `&`: the words the worker actually reads when it gets stopped, so it can connect its
    error to the rule instead of trying another spelling of the same command.
    """
    text = _worker_prompt()
    assert "was blocked" in text and "allowed working directories" in text
    assert "PARECE pedir que te muevas" in text, "the false premise behind the `cd` is never answered"
    # And it must answer that premise WITHOUT naming the place, because naming it is what caused the bug in
    # the first place: `test_y_NINGUNO_afirma_que_el_worker_corre_en_la_raiz_del_repo` forbids the phrase
    # outright, and a substring scan cannot tell an assertion from its denial. That guard fired on this very
    # sentence while it was being written, which is exactly what it is for.
    assert "raíz del repo" not in text


def test_and_it_says_there_is_no_way_around_it():
    """Some rejections are a wrong spelling and some are a closed door. Telling them apart is what stops the
    worker burning turns on a rewrite that cannot work — the same failure as "if a command asks you for
    approval, you wrote it incorrectly," applied to the case where it did NOT."""
    text = _worker_prompt()
    i = text.find("allowed working directories")
    assert i > 0 and "no hay rodeo" in text[i:i + 260]


# ── the recipe must teach a command that WORKS (V2-549) ──────────────────────────────────────────────────────
# Same family, other half. Above: we taught a form our own gate refuses. Here: a recipe carries a literal
# payload, and a literal in a prompt is written once and then nobody ever runs it. This repo has paid for that
# twice — V2-219 taught `in 2 hours` to a parser that does not accept it, and V2-249 answered it by checking
# EVERY example a prompt teaches against the parser that will read it. §4d teaches the worker how to fill the
# reading sheet; if that JSON, or the action it names, is not what the widget accepts, the worker follows our
# instructions and the sheet stays empty.
def _sheet_recipe() -> str:
    text = _worker_prompt()
    i = text.find("widget_cli data documento show")
    assert i > 0, "the recipe that fills the reading sheet is not in the worker's prompt at all"
    return text[text.rfind("\n", 0, i) + 1: text.find("\n", i)]


def test_the_payload_the_recipe_teaches_is_one_the_sheet_ACCEPTS(tmp_path, monkeypatch):
    """Not «the JSON parses» — the widget is DRIVEN with the literal we teach, in a private store, and has to
    come back ok with the body on the sheet. A key we renamed in the widget and forgot here would leave the
    recipe reading perfectly while every worker that follows it delivers nothing."""
    payload = json.loads(re.search(r"\{\"kind\".*?\}\)", _sheet_recipe()).group(0)[:-1])

    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    import importlib
    from nucleo import workspace
    from widgets import store as wstore
    importlib.reload(workspace)
    importlib.reload(wstore)
    from widgets.documento import data as mod
    importlib.reload(mod)
    try:
        out = mod.apply_action("show", payload)
        assert out.get("ok"), f"the sheet refuses the payload we teach: {out}"
        assert mod.view_data()["body"], "the recipe ran and left the sheet empty"
    finally:
        importlib.reload(workspace)
        importlib.reload(wstore)


def test_every_sheet_action_the_recipe_names_is_DECLARED_by_the_widget():
    """An action `apply_action` handles but the manifest does not declare is invisible to the brain (V2-520),
    so teaching one is teaching a dead command."""
    declared = set(json.loads(
        (pathlib.Path(DP.__file__).resolve().parents[1] / "widgets" / "documento" / "manifest.json")
        .read_text(encoding="utf-8"))["actions"])
    named = set(re.findall(r"data documento (\w+)", _worker_prompt()))
    assert named, "the recipe names no action at all"
    assert named <= declared, f"the recipe teaches actions the manifest never declares: {sorted(named - declared)}"
