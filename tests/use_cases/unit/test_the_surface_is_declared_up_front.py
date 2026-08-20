"""Which surface the engine declared when the errand was COMMISSIONED (V2-227 A).

Two reasons to keep it, and the second is the one that is not obvious. The results sheet with its
process tab only opens for `lista`/`item`, so without this a round with no process tab cannot be told
apart from a round that never asked for one. And a badly chosen surface betrays the same defect we chase
elsewhere: declaring `lista` for "what time does the Prado open?" is the same overreaction as spawning a
browser for a direct fact, caught one step earlier.
"""
import json
import sqlite3

from tests.use_cases.e2e.agent import verify


def _db(tmp_path, payloads):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (topic TEXT, ts_ms INT, kind TEXT, label TEXT, payload TEXT)")
    con.executemany("INSERT INTO events VALUES ('observer',?,'task','',?)",
                    [(1000 + i, json.dumps(d)) for i, d in enumerate(payloads)])
    con.commit()
    con.close()
    return str(p)


def test_the_declared_surface_is_read(tmp_path):
    assert verify.declared_surfaces(_db(tmp_path, [{"id": "1", "surface": "lista"}])) == ["lista"]


def test_several_errands_keep_their_order_without_repeating(tmp_path):
    got = verify.declared_surfaces(_db(tmp_path, [
        {"surface": "lista"}, {"surface": "lista"}, {"surface": "widget"}]))
    assert got == ["lista", "widget"]


def test_it_is_found_where_the_real_round_puts_it(tmp_path):
    """The shape copied from a real round: `context.surface` on `escalate.requested` — neither at the top
    level nor in `extra`, which were the two places looked at first."""
    assert verify.declared_surfaces(_db(tmp_path, [{"context": {"surface": "lista"}}])) == ["lista"]


def test_it_is_also_found_one_level_down(tmp_path):
    """Emitters differ; reading only one level is how a field disappears in silence."""
    assert verify.declared_surfaces(_db(tmp_path, [{"extra": {"surface": "voz"}}])) == ["voz"]


def test_no_declaration_is_an_empty_list_not_an_exception(tmp_path):
    assert verify.declared_surfaces(_db(tmp_path, [{"id": "1"}])) == []


def test_an_unreadable_database_never_costs_a_round(tmp_path):
    assert verify.declared_surfaces(str(tmp_path / "nope.db")) == []
