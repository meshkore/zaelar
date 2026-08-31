"""`results::82d86e-2` and `82d86e-2` are the same sheet expressed in two ways, and one returned empty.

The canvas names an instance `results::<corr>`; `view_data` expects the bare INSTANCE. Without accepting the
first form, sanitization swallowed the colons and composed the key `results--results82d86e-2`, which **does not
exist** — so `view_data` returned an EMPTY sheet.

The tolerance lives in `sheet_key`, not in `_safe_sheet`: it fits on the line that was already there, and
`widgets/results/data.py` is a ratchet god-file — 1030 lines of ceiling — that two previous attempts skipped.

And an empty sheet is indistinguishable from “the job has not found anything yet”: the failure makes no noise,
it changes the response. It is the same family of bug that lasted all night: *the system has the data and says it
does not.*

Found on 2026-08-28 while investigating why the prompt’s row block had not fired EVEN ONCE in 45 measured
rounds. **It has not been proven to be the cause of that** — the path that was measured already passed the
bare instance — but it is a loose thread anyone could pull, quietly.
"""
from __future__ import annotations

from widgets.results import data as D


def test_las_dos_formas_son_la_misma_hoja():
    assert D.sheet_key("results::82d86e-2") == D.sheet_key("82d86e-2") == "results--82d86e-2"


def test_la_hoja_SIN_instancia_no_se_mueve():
    """The bare sheet is the usual one, byte for byte: touching it would break everything already stored."""
    assert D.sheet_key("") == "results"
    assert D.sheet_key(None) == "results"


def test_solo_se_quita_el_prefijo_PROPIO():
    """Removing anything before `::` would turn another widget's sheet into ours."""
    assert D.sheet_key("otro::82d86e-2") != "results--82d86e-2"
    assert "otro" in D.sheet_key("otro::82d86e-2")


def test_el_saneado_sigue_apretado():
    """The key goes to disk: only alphanumeric characters, hyphens, and underscores, and bounded in length."""
    k = D.sheet_key("results::../../etc/passwd")
    assert "/" not in k and ".." not in k
    assert len(D.sheet_key("results::" + "x" * 200)) <= len("results--") + 64
