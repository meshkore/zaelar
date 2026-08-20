"""The memory's canonical language is ASKED OF THE ENGINE, because assuming it cost a false finding.

2026-08-20: an ES scenario seeded "me da vértigo la altura", the harness grepped the turn's prompt for
"vértigo", found nothing and reported that the preference had never reached the model. It had reached it — as
"The operator has a fear of heights". The memory is monolingual in the operator's canonical language and that
sandbox's was still `en`, so the datum sat in the prompt in the one language nobody looked in. The memory agent
found it by searching both, and the real defect underneath was better than the one reported.

The second trap is levels, and it is the same class again: `state.language` is stored `null` when nobody chose
explicitly and `state.read()` resolves it against the active configuration. So the raw row can say null while
the distiller writes Spanish. Reading the column and calling that "unknown" does not fail — it invents. The
engine is asked first; the row is a labelled fallback.
"""
from __future__ import annotations

import json
import sqlite3

from tests.use_cases.e2e.agent import judge as J, probe_client, verify as V


def _db(tmp_path, language):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE state (id INTEGER PRIMARY KEY, data TEXT)")
    con.execute("INSERT INTO state (id, data) VALUES (1, ?)",
                (json.dumps({"assistant_name": "Zaelar", "language": language}),))
    con.commit()
    con.close()
    return p


def test_the_ENGINE_is_asked_first(monkeypatch):
    """The engine returns the RESOLVED value, which is the one the distiller actually used."""
    monkeypatch.setattr(probe_client, "memory_map", lambda: {"state": {"language": "es"}})
    got = V.memory_language("/nonexistent.db")
    assert got == {"effective": "es", "explicit": True, "source": "engine"}


def test_a_NULL_row_is_not_reported_as_unknown_when_the_engine_can_answer(monkeypatch, tmp_path):
    """The precision that matters: null in the row means "nobody pinned one", not "no language". If the engine
    says `es`, the round was measured in Spanish no matter what the column holds."""
    monkeypatch.setattr(probe_client, "memory_map", lambda: {"state": {"language": "es"}})
    assert V.memory_language(_db(tmp_path, None))["effective"] == "es"


def test_the_row_is_a_LABELLED_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(probe_client, "memory_map", lambda: (_ for _ in ()).throw(RuntimeError("no engine")))
    got = V.memory_language(_db(tmp_path, "en"))
    assert got == {"effective": "en", "explicit": True, "source": "db"}


def test_and_says_so_when_NOTHING_can_answer(monkeypatch, tmp_path):
    monkeypatch.setattr(probe_client, "memory_map", lambda: (_ for _ in ()).throw(RuntimeError("no engine")))
    got = V.memory_language(_db(tmp_path, None))
    assert got == {"effective": "", "explicit": False, "source": "db"}
    assert V.memory_language("")["source"] == ""


def test_the_judge_is_warned_when_memory_and_locale_DISAGREE():
    txt = J.mechanism_facts({"memory_language": {"effective": "en"}, "locale": "es"})
    assert "destila en «en»" in txt
    assert "no te fíes de no ver la palabra en castellano" in txt


def test_and_NOT_warned_when_english_memory_is_correct():
    """Sensitivity: `en` is right for a US case. A warning that fires on half the catalogue stops being read."""
    assert "destila en" not in J.mechanism_facts({"memory_language": {"effective": "en"}, "locale": "us"})
    assert "destila en" not in J.mechanism_facts({"memory_language": {"effective": "es"}, "locale": "es"})


def test_and_says_nothing_when_it_could_not_be_read():
    assert "destila en" not in J.mechanism_facts({"memory_language": {"effective": ""}, "locale": "es"})
