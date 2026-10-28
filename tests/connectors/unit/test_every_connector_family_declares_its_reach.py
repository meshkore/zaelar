"""Every connector family declares how far back it can see, through one door (refactor2710-13 T-02).

A worker's first step compares the spec with the resource's reach; when nothing declared it, an impossible spec
was retried in silence (V2-825 F6). The contract: `connectors.reach.reach(family)` answers for `mail`,
`cloud_files` and `messaging` with the same shape, from fixtures only — no credential, no network.
"""
from __future__ import annotations

import time

import pytest

from connectors import reach as R

FAMILIES = ("mail", "cloud_files", "messaging")


class _IMAP:
    """A mailbox with two messages; the oldest UID is 3."""
    def __init__(self):
        self.readonly, self.fetched = [], []

    def select(self, name, readonly=False):
        self.readonly.append(readonly)
        return "OK", [b"2"]

    def uid(self, cmd, *args):
        if cmd == "search":
            return "OK", [b"3 7"]
        self.fetched.append(args)
        return "OK", [(b'3 (UID 3 INTERNALDATE "01-Sep-2025 10:00:00 +0000")',)]

    def logout(self):
        pass


class _MB:
    def __init__(self, im):
        self.im = im

    def _imap(self):
        return self.im


class _Drive:
    def item(self, token, api_base, file_id):
        assert file_id == "" and token == "tok"
        return {"id": "root", "modified": "2019-03-02T08:00:00Z"}


def test_the_three_families_are_declared_and_answer_in_one_shape(monkeypatch, tmp_path):
    assert set(R.FAMILIES) == set(FAMILIES)
    from connectors.email import reach as mail_reach
    im = _IMAP()
    r = mail_reach.earliest_readable(_MB(im))
    assert r.earliest == "2025-09-01T10:00:00+00:00" and r.known and r.source == mail_reach.SOURCE
    assert im.readonly == [True] and im.fetched == [("3", "(INTERNALDATE)")], "read-only, one FETCH, no body"
    from connectors.files import reach as files_reach
    r = files_reach.earliest_readable("gdrive", prepared=(_Drive(), "tok", "https://x", ""))
    assert r.earliest == "2019-03-02T08:00:00Z" and r.provider == "gdrive"
    from connectors.messaging import archive
    monkeypatch.setattr(archive, "_db_path", lambda: str(tmp_path / "archive.db"))
    archive.reset()
    archive.record("telegram", "42", [{"id": "a", "ts": 1_700_000_000, "body": "old"},
                                      {"id": "b", "ts": 1_700_900_000, "body": "new"}], chat_name="Ana")
    archive.record("telegram", "43", [{"id": "c", "ts": 1_699_000_000, "body": "older"}], chat_name="Luis")
    r = R.reach("messaging", "telegram")
    assert r.earliest == "2023-11-03T08:26:40+00:00" and r.known
    assert R.reach("messaging", "whatsapp").earliest is None and R.reach("messaging", "whatsapp").detail == "empty"
    for fam in FAMILIES:
        out = R.reach(fam, "nothing").as_dict()
        assert set(out) == {"family", "provider", "earliest", "source", "known", "detail"} and out["known"]


def test_an_undeclared_family_says_so_instead_of_guessing():
    r = R.reach("carrier_pigeon")
    assert not r.known and r.earliest is None and r.detail == "family_not_declared"


def test_a_resource_that_cannot_answer_is_a_fact_not_a_crash(monkeypatch):
    from connectors.email import reach as mail_reach

    class _Dead:
        def _imap(self):
            raise OSError("no route")
    r = mail_reach.earliest_readable(_Dead())
    assert r.earliest is None and r.detail == "login:OSError"
    monkeypatch.setitem(R.FAMILIES, "mail", lambda p: 1 / 0)
    assert R.reach("mail").detail == "ZeroDivisionError" and R.reach("mail").known


def test_disarm_a_family_dropped_from_the_door_turns_the_contract_red(monkeypatch):
    monkeypatch.delitem(R.FAMILIES, "mail")
    with pytest.raises(AssertionError):
        assert set(R.FAMILIES) == set(FAMILIES)
    assert not R.reach("mail").known


def test_every_measurement_leaves_one_event_on_the_timeline(monkeypatch):
    """V2-826 §2b: a measurement nobody can see did not happen. One `spec`/`reach` event per call, family `worker`
    (the spec kind's family, mirrored by the Master), carrying the family, the value and how long it took."""
    from voice import observer
    seen = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: seen.append((kind, label, kw.get("extra"))))
    monkeypatch.setitem(R.FAMILIES, "mail", lambda p: R.Reach(family="mail", provider="email",
                                                              earliest="2025-09-01T10:00:00+00:00", source="x"))
    R.reach("mail")
    R.reach("carrier_pigeon")
    assert [(k, label) for k, label, _ in seen] == [("spec", "reach")] * 2
    first, second = seen[0][2], seen[1][2]
    assert first["family"] == "mail" and first["earliest"] == "2025-09-01T10:00:00+00:00" and first["ms"] >= 0
    assert second["detail"] == "family_not_declared" and not second["known"]
    assert observer._CAT.get("spec") == "worker", "the event's kind must keep a family the viewer and Master read"
