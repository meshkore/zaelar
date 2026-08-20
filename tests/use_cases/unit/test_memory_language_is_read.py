"""The memory's canonical language is READ, because assuming it cost a false finding.

2026-08-20: an ES scenario seeded "me da vértigo la altura", the harness grepped the turn's prompt for
"vértigo", found nothing and reported that the preference had never reached the model. It had reached it — as
"The operator has a fear of heights". The memory is monolingual in the operator's canonical language and that
sandbox's was still `en`, so the datum sat in the prompt in the one language nobody looked in. The memory agent
found it by searching both.

Hence the rule the report now carries: about memory, grep in the language `state.language` names, never in the
language of the conversation.
"""
from __future__ import annotations

import json
import sqlite3

from tests.use_cases.e2e.agent import judge as J, verify as V


def _db(tmp_path, language):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE state (id INTEGER PRIMARY KEY, data TEXT)")
    con.execute("INSERT INTO state (id, data) VALUES (1, ?)",
                (json.dumps({"assistant_name": "Zaelar", "language": language}),))
    con.commit()
    con.close()
    return p


def test_it_reads_the_canonical_language(tmp_path):
    assert V.memory_language(_db(tmp_path, "en")) == "en"
    other = tmp_path / "other"
    other.mkdir()
    assert V.memory_language(_db(other, "es")) == "es"


def test_a_null_language_reads_as_unknown_not_as_english(tmp_path):
    """After the language fix `None` means "not chosen yet". Reporting that as `en` would reintroduce exactly
    the assumption this function exists to remove."""
    assert V.memory_language(_db(tmp_path, None)) == ""


def test_an_unreadable_database_says_nothing(tmp_path):
    assert V.memory_language(tmp_path / "nope.db") == ""


def test_the_judge_is_warned_when_memory_and_locale_DISAGREE():
    txt = J.mechanism_facts({"memory_language": "en", "locale": "es"})
    assert "destila en «en»" in txt
    assert "no te fíes de no ver la palabra en castellano" in txt


def test_and_NOT_warned_when_english_memory_is_correct():
    """Sensitivity: `en` is right for a US case. Warning on the language alone would cry wolf on half the
    catalogue, and a warning that always fires stops being read."""
    assert "destila en" not in J.mechanism_facts({"memory_language": "en", "locale": "us"})
    assert "destila en" not in J.mechanism_facts({"memory_language": "es", "locale": "es"})


def test_and_says_nothing_when_it_could_not_be_read():
    assert "destila en" not in J.mechanism_facts({"memory_language": "", "locale": "es"})
