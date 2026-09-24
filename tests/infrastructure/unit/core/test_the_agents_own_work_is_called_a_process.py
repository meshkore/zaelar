"""V2-744 — the agent's own work is a PROCESS (a JOB in English), and «tarea» belongs to the operator.

His rule, verbatim (2026-09-21): *«a las tareas que yo hago las llamo procesos (jobs en inglés) y las
separo de las tareas personales del operador que van en su agenda»*.

## Why this is a ratchet and not a one-off edit

A rename that lives only in the strings it touched comes back. There are ~1.500 keys in each bundle and a
new empty state, a new tooltip or a new panel is written every week; the word «tarea» is the natural one to
reach for, and nothing would have noticed. So the vocabulary is measured where the operator READS it: the
two shipped bundles, which are the single source of every label the frontend paints (V2-694).

## …and why it is not a plain grep for the word

«Tarea» is not banned — it was REASSIGNED. It is the right word in three places and this test says which:

  · `widgets.agenda.*` — the operator's own tasks, which is the whole point of the rename;
  · `reset.confirm.body` — «tu agenda —proyectos, tareas y citas—», his data, listed as what is KEPT;
  · `memory.zone_long_sub` — what durable memory holds, which now legitimately includes his tasks.

Everything else that means «the work the assistant is doing» says proceso / job. The allowlist is the
interesting half of this file: a new key that wants in has to be argued for here, in front of the rule.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]
BUNDLES = ENGINE / "i18n" / "bundles"

#: Key PREFIXES where «tarea»/«task» means the OPERATOR's own task and is therefore correct.
_HIS_OWN = ("widgets.agenda.", "reset.confirm.body", "memory.zone_long_sub")

_ES = re.compile(r"\btareas?\b", re.I)
_EN = re.compile(r"\btasks?\b", re.I)


def _bundle(lang: str) -> dict:
    return json.loads((BUNDLES / f"{lang}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("lang,rx", [("es", _ES), ("en", _EN)])
def test_no_label_the_operator_reads_calls_the_agents_work_a_task(lang, rx):
    bad = {k: v for k, v in _bundle(lang).items()
           if isinstance(v, str) and rx.search(v) and not k.startswith(_HIS_OWN)}
    assert not bad, (
        "these labels still call the assistant's own work a «tarea»/«task». It is a PROCESS (a JOB in "
        "English) — the operator's tasks are the agenda's, and only those:\n  "
        + "\n  ".join(f"{k} = {v!r}" for k, v in sorted(bad.items())))


def test_the_wall_tab_says_procesos_and_jobs():
    assert _bundle("es")["chat.tabTasks"] == "Procesos"
    assert _bundle("en")["chat.tabTasks"] == "Jobs"


def test_the_two_bundles_still_carry_the_same_keys():
    """A rename that lands in one language and not the other shows as a key the other cannot translate."""
    assert set(_bundle("es")) == set(_bundle("en"))


def test_the_tab_ID_moved_with_the_label_because_the_ID_is_what_a_voice_order_carries():
    """This is the half a «label change» would have skipped, and it is the half that ROUTES.

    `store.setChatTab` is reached by the voice (`show_panel` → SSE → this door) with the panel STRING. While
    it answered to «tareas», «ábreme las tareas» opened the agent's own job list — which is exactly the
    thing the operator asked to stop calling by that name."""
    store = (ENGINE / "frontend/app/core/store.js").read_text(encoding="utf-8")
    # V2-761 added «apps» (the widget catalogue); what this pins is that «tareas» is still NOT a tab id.
    assert 'const _TABS = ["chat", "procesos", "clusters", "conectores", "apps"];' in store
    wall = (ENGINE / "frontend/app/components/ChatWall.js").read_text(encoding="utf-8")
    assert 'store.setChatTab("procesos")' in wall
    assert 'store.setChatTab("tareas")' not in wall
    css = (ENGINE / "frontend/app/styles.css").read_text(encoding="utf-8")
    assert ".chatwall.tab-procesos .cw-tasks{display:flex}" in css, "the renamed tab must still be visible"


def test_a_stored_action_map_row_that_still_says_tareas_keeps_working():
    """The operator's own action map may hold rows recorded before today, and they meant this panel when
    he recorded them. A rename that breaks his saved phrases is a rename that costs him something."""
    import sys
    sys.path.insert(0, str(ENGINE))
    from nucleo.flash.panel_canon import canon_panel
    assert canon_panel("tareas") == "procesos"
    assert canon_panel("procesos") == "procesos"
    assert canon_panel("jobs") == "procesos"
    store = (ENGINE / "frontend/app/core/store.js").read_text(encoding="utf-8")
    assert 'tareas: ["procesos", "live"]' in store, "the frontend door has to absorb it too"


def test_the_tool_the_model_picks_tells_the_two_apart():
    """The only thing that can keep «ábreme las tareas» out of this panel is the prose the model reads:
    the canon has no third answer to give."""
    import sys
    sys.path.insert(0, str(ENGINE))
    from nucleo.flash import router
    fn = next(t["function"] for t in router.TOOLS if t["function"]["name"] == "show_panel")
    desc = fn["description"].lower()
    assert "procesos" in desc
    assert "agenda" in desc, "it has to say where his own tasks live, or the model has nowhere to send them"
    assert "'tareas'" not in desc, "the panel must not be OFFERED under that name any more"

    # Both halves, separately: `whenToUse` is the line that ROUTES a turn to a widget (`brief._purpose`,
    # capped at 300 chars), and `usage` is the one that says how to drive it once chosen. Asserting the
    # pair as one string lets either of them lose the boundary in silence while the other covers for it —
    # measured here, by disarming exactly that.
    manifest = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text(encoding="utf-8"))
    assert "proceso" in manifest["whenToUse"].lower(), manifest["whenToUse"]
    assert "proceso" in manifest["usage"].lower()
    from widgets.brief import _PURPOSE_CAP
    assert len(manifest["whenToUse"]) <= _PURPOSE_CAP, (
        "the routing line is cut before the model reads the boundary — the V2-547 failure")
