"""C11 — a free errand and a document: the row carries its playbook, and the worker's brief is under the prompt
ceiling; changing one word of the request changes nothing in the mechanism (V2-851 §5, §6, §9).

The ceiling is the battery's (F0): the frozen worker's first message measured 28 581 chars for the hotel errand
(2026-11-05, Claude Code transcript). §5's two-layer catalogue — headline in the brief, a family's set on request —
is held to roughly half of that — the number is the engine's own measured ceiling (V2-851 F3)."""
from __future__ import annotations

import pytest

from .probe import WORKER_PROMPT_FIELD, brief, payload
from .script import ERRAND, LANGS, visible_rows_since, wait_worker

from nucleo.workers.prompts.catalog import PROMPT_CEILING_CHARS as WORKER_PROMPT_CEILING_CHARS  # noqa: E402


@pytest.mark.parametrize("errand", ["hotel", "hostel", "document"])
@pytest.mark.parametrize("lang", LANGS)
def test_c11_a_free_errand_carries_its_playbook(probe_for, check, lang, errand, rep):
    p = probe_for(lang)
    turn = p.say(ERRAND[lang][errand])
    ws = wait_worker(p, turn.since)
    rows = visible_rows_since(p, turn.t0)
    row = rows[-1] if rows else {}
    check.that("the row carries its playbook", bool(row.get("playbook")), brief(row) or "no row")
    size = payload(ws or {}).get(WORKER_PROMPT_FIELD)
    check.that("the worker's prompt size is in its flow", isinstance(size, int), brief(ws or {}) or "no worker_start")
    check.that("the brief is under the ceiling", isinstance(size, int) and size <= WORKER_PROMPT_CEILING_CHARS, size)
    check.done(expected_red=check.expected)
