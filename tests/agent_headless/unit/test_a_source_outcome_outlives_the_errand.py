"""V2-798 — what a source did to one errand is known to the next worker, with a date, and it expires.

The class: every Brain Worker started from zero. A site that answered 403 yesterday was opened again today, a
network agent that timed out was asked again with the same timeout, a provider out of quota was tried again — the
facts were all observed (wall detector, extract counter, the provider's 429, the mesh timeout) and none outlived
the process that saw it.

Pinned here, each with its disarm:
  1. the record: newest fact wins, a success replaces a failure, a repeated failure lives longer, everything expires;
  2. the doors write it: `nav_cli` (wall / extract), `providers.note_tool_blindness` (quota);
  3. the worker's step 0 carries ONE line when something is known and NOTHING when not (zero prompt growth by default).

Domain-free on purpose: the sources below are a restaurant site, a car classifieds site and a search provider.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch_prompts as dp
from nucleo.cli import nav as nav_cli
from nucleo import source_outcomes as so

DAY = 24 * 3600
T0 = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _clean_record():
    so.forget()
    yield
    so.forget()


# ── 1. the record ─────────────────────────────────────────────────────────────────────────────────────────────

def test_a_wall_is_a_fact_with_a_date_and_it_expires():
    so.note("tables.example", so.WALL, detail="403", now=T0)
    v = so.verdict("tables.example", now=T0 + 60)
    assert v and v["outcome"] == so.WALL
    assert so.is_failing("tables.example", now=T0 + 60)
    # three days later the site is worth retrying: nothing current is known, so nothing is said
    assert so.verdict("tables.example", now=T0 + 3 * DAY + 1) is None


def test_a_repeated_wall_lives_longer_but_still_expires():
    for i in range(3):
        so.note("cars.example", so.WALL, now=T0 + i * 600)        # three separate sightings
    assert so.verdict("cars.example", now=T0 + 5 * DAY)["n"] == 3
    assert so.verdict("cars.example", now=T0 + 10 * DAY) is None   # capped at ×3 of three days


def test_the_same_wall_seen_across_actions_on_one_page_is_one_sighting():
    so.note("cars.example", so.WALL, now=T0)
    so.note("cars.example", so.WALL, now=T0 + 30)                  # the next action on the same walled page
    assert so.verdict("cars.example", now=T0 + 31)["n"] == 1


def test_a_later_success_is_the_newer_truth():
    so.note("tables.example", so.WALL, now=T0)
    so.note("tables.example", so.SERVED, detail="9 rows", now=T0 + 3600)
    v = so.verdict("tables.example", now=T0 + 3700)
    assert v["outcome"] == so.SERVED and not so.is_failing("tables.example", now=T0 + 3700)


def test_a_quota_lasts_until_the_provider_said_it_comes_back():
    so.note("search:provider-x", so.QUOTA, kind="search", until=T0 + 4 * DAY, now=T0)
    assert so.verdict("search:provider-x", now=T0 + 3 * DAY)["outcome"] == so.QUOTA
    assert so.verdict("search:provider-x", now=T0 + 4 * DAY + 1) is None


def test_an_empty_answer_depends_on_the_query_and_does_not_demote_the_source():
    so.note("agent-a", so.EMPTY, kind="agent", now=T0)
    so.note("agent-b", so.TIMEOUT, kind="agent", now=T0)
    assert not so.is_failing("agent-a", now=T0 + 60)
    assert so.is_failing("agent-b", now=T0 + 60)


def test_disarmed_the_expiry_turns_a_bad_minute_into_a_fence():
    """RED proof: with negative facts never expiring, the wall above is still there a month later — the expiry
    test is measuring the TTL, not a constant. Restored in `finally`."""
    saved = dict(so._TTL_S)
    try:
        so._TTL_S[so.WALL] = 10 ** 9
        so.note("tables.example", so.WALL, now=T0)
        assert so.verdict("tables.example", now=T0 + 30 * DAY) is not None
    finally:
        so._TTL_S.clear()
        so._TTL_S.update(saved)
    assert so.verdict("tables.example", now=T0 + 30 * DAY) is None


# ── 2. the doors write it ─────────────────────────────────────────────────────────────────────────────────────

def test_the_browser_bridge_records_a_wall_by_host():
    nav_cli._note_source("navigate", {"ok": True, "url": "https://www.tables.example/madrid",
                                      "wall": "el sitio nos ha bloqueado el acceso (respuesta 403)"})
    v = so.verdict("tables.example")
    assert v and v["outcome"] == so.WALL and "403" in v["detail"]


def test_the_browser_bridge_records_what_extract_found():
    nav_cli._note_source("extract", {"ok": True, "url": "https://maps.example/search?q=x", "listings": []})
    assert so.verdict("maps.example")["outcome"] == so.EXTRACT_EMPTY
    nav_cli._note_source("extract", {"ok": True, "url": "https://cars.example/list",
                                     "listings": [{"title": "Car A", "url": "u"}, {"title": "", "url": "v"}]})
    v = so.verdict("cars.example")
    assert v["outcome"] == so.SERVED and v["detail"] == "1 rows"   # only NAMED rows count


def test_a_provider_out_of_quota_is_recorded_until_its_reset(monkeypatch):
    from nucleo.workers import providers
    monkeypatch.setattr(providers, "classify_tool_failure", lambda text: "quota")
    monkeypatch.setattr(providers, "_reset_epoch", lambda text: T0 + 2 * DAY)
    assert providers.note_tool_blindness("429 limit exhausted", tool="web_search", provider="provider-x")
    v = so.verdict("search:provider-x", now=T0)
    assert v and v["outcome"] == so.QUOTA and v["expires_at"] == T0 + 2 * DAY


# ── 3. the worker's step 0 ────────────────────────────────────────────────────────────────────────────────────

GOAL = "Find me a used estate car under 9000 EUR near Valencia"


def test_nothing_known_costs_the_prompt_nothing():
    assert so.worker_line() == ""
    p = dp._build_prompt(GOAL, "", True, None)
    assert "VISTO EN ENCARGOS ANTERIORES" not in p


def test_what_is_known_reaches_both_worker_prompts_as_one_dated_line():
    so.note("cars.example", so.WALL)
    so.note("agent-a", so.SERVED, kind="agent")
    line = so.worker_line("py")
    assert line.count("\n") == 1 and "cars.example bloqueó" in line and "agent-a funcionó" in line
    assert "py -m nucleo.source_outcomes" in line
    for p in (dp._build_prompt(GOAL, "", True, None), dp._web_prompt(GOAL, "", None)):
        assert "cars.example bloqueó" in p


def test_the_line_is_bounded_however_much_is_known():
    for i in range(40):
        so.note(f"site{i}.example", so.WALL)
    line = so.worker_line()
    assert line.count(" bloqueó ") == so._LINE_ITEMS and len(line) < 600


def test_disarmed_the_prompt_wiring_hides_what_is_known(monkeypatch):
    """RED proof: with the step-0 seam cut, the record exists and the worker never sees it."""
    so.note("cars.example", so.WALL)
    monkeypatch.setattr(dp, "_sources_line", lambda py="python": "")
    assert "cars.example" not in dp._build_prompt(GOAL, "", True, None)
    monkeypatch.undo()
    assert "cars.example" in dp._build_prompt(GOAL, "", True, None)


def test_the_cli_prints_the_record_as_json(capsys):
    import json
    so.note("cars.example", so.WALL, detail="403")
    assert so.main([]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["sources"][0]["source"] == "cars.example"
