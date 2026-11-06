"""The connectors bench (V2-856) is scored by what each step RETURNED — an error, a refusal, a held send or an empty
read is never a pass — and it writes only to the test contact of the private file, never to anyone the inbox
names. No engine here: the plan and the scorer are pure.
"""
from __future__ import annotations

import json

from tests.connectors.live import bench


def test_nothing_leaves_without_send_and_with_it_only_to_the_private_contact() -> None:
    c = {"source": "inworld", "to": "test-address"}
    assert [s for s, _, _ in bench.plan("email", c, send=False, marker="m")] == ["fetch", "search"]
    sends = [p for s, a, p in bench.plan("email", c, send=True, marker="m") if a == "send_to"]
    assert sends == [{"contact": "test-address", "channel": "email", "text": "m"}]
    assert not [a for _, a, _ in bench.plan("telegram", {"chat": "x"}, send=True, marker="m") if a == "send_to"], \
        "no `to` in the file, no send"


def test_a_refusal_an_empty_read_and_a_held_send_are_failures() -> None:
    assert bench.score("search", {"ok": False, "error": "no_chat"})["ok"] is False
    assert bench.score("read", {"result": {"returned": 0}})["ok"] is False
    assert bench.score("send", {"held": True, "to": "x"})["ok"] is False
    assert bench.score("search", {"result": {"count": 3}}) == {"ok": True, "n": 3, "why": ""}
    assert bench.score("summarise", {"result": {"digests": [{"summary": "two open asks"}]}})["n"] == 13


def test_the_contacts_come_from_a_private_file_and_a_missing_one_skips(tmp_path, monkeypatch) -> None:
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"email": {"to": "a"}, "whatsapp": {"to": "b"}}), encoding="utf-8")
    assert bench.contacts(str(f)) == {"email": {"to": "a"}}, "only the platforms the bench knows"
    monkeypatch.setenv("ZAELAR_BENCH_CONTACTS", str(tmp_path / "absent.json"))
    assert bench.contacts() == {}
    assert ".meshkore/credentials" in str(bench.CONTACTS), "the default file is the gitignored credentials folder"
