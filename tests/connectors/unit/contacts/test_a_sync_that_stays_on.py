"""V2-701 — a sync that STAYS ON, and stays a mirror.

The operator, after watching a one-off pass bring 2 685 people in:

> «El tema de la sincronización de contactos no es algo que deberíamos hacer de forma puntual, deberíamos
> realmente marcar un botón de sincronización y eso debería quedarse conectado de forma permanente.»

and, clarifying what «sincronizado» means to him:

> «La sincronización es bidireccional una vez está activa, se modifica en un sitio o en otro, todo se
> sincroniza linealmente y es un espejo nuestro sistema, así como Google Contacts. Entiendo que si eso está
> conectado a un teléfono y se modifica en el teléfono, todo el sistema se sincronizará.»

Three things had to become true for that sentence to be honest, and each has its section below:

1. **A pass has to be cheap enough to repeat.** 2 685 contacts is six pages; a full re-read every minute is
   a request budget spent to learn that nothing happened. The sync TOKEN is what makes a quiet minute one
   round-trip — and it is also what tells the merge that a row it is holding is one Google CHANGED.
2. **A push has to know what it has already sent.** The old test was a DATE («edited today»), which is
   harmless for a button pressed now and then and is a PATCH per contact per minute on a timer.
3. **A deletion is a change like any other.** Both directions, or it is not a mirror.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from connectors.contacts import google_people as gp
from connectors.contacts import service as svc
from widgets.contactos import gcontacts

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture()
def ct(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real directory, and a fresh one PER TEST."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as _d
    return _d


# ── 1 · THE PASS IS CHEAP, BECAUSE IT ASKS WHAT CHANGED ─────────────────────────────────────────────────

class _Recorder:
    """A fake httpx client that answers canned bodies and REMEMBERS the request it was asked to make.

    The point is to measure the parameters that actually reach Google. Re-deriving them in the test would
    be re-implementing the product and would pass whatever the product did (V2-699 paid for that once).
    """

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        body = self.pages.pop(0) if self.pages else {}
        return _Resp(200, body)


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


def test_a_pass_always_asks_for_a_sync_token_and_never_sorts():
    """Two rules of Google's, both load-bearing, both easy to break by editing one branch:

      · `sortOrder` is «only used if sync is not requested» — so a sorted list request cannot also ask for
        a token, and the sort was the thing worth losing;
      · «when the syncToken is specified, all other request parameters must match the first call» — which
        is why there is exactly ONE parameter set here rather than a full one and an incremental one.
    """
    cl = _Recorder([{"connections": [], "nextSyncToken": "tok-1"}])
    res = gp.list_people(cl, "https://people.googleapis.com/v1", "T")
    q = cl.calls[0]["params"]
    assert q.get("requestSyncToken") == "true"
    assert "sortOrder" not in q, "a sorted request may not ask for a token, and the token is what matters"
    assert res["syncToken"] == "tok-1"


def test_the_second_pass_sends_the_token_it_was_given():
    cl = _Recorder([{"connections": [], "nextSyncToken": "tok-2"}])
    gp.list_people(cl, "https://people.googleapis.com/v1", "T", sync_token="tok-1")
    assert cl.calls[0]["params"]["syncToken"] == "tok-1"


def test_the_parameters_are_IDENTICAL_in_both_regimes():
    """Google refuses a token whose request does not match the one that issued it. Two parameter sets that
    drift apart is a 429 on every pass, and nothing in the product would say why."""
    a = _Recorder([{"connections": []}])
    b = _Recorder([{"connections": []}])
    gp.list_people(a, "https://x/v1", "T")
    gp.list_people(b, "https://x/v1", "T", sync_token="tok-1")
    first, second = dict(a.calls[0]["params"]), dict(b.calls[0]["params"])
    second.pop("syncToken")
    assert first == second


def test_a_deleted_person_is_separated_instead_of_being_dropped():
    """Google reports a deletion as a person with `metadata.deleted` and NOTHING else — no name, no email.
    Handed to the shaper it becomes None and vanishes, which is exactly how a mirror stops mirroring."""
    cl = _Recorder([{"connections": [
        {"resourceName": "people/gone", "metadata": {"deleted": True}},
        {"resourceName": "people/here", "names": [{"displayName": "Marta"}]}]}])
    res = gp.list_people(cl, "https://x/v1", "T", sync_token="tok-1")
    assert res["deleted"] == ["people/gone"]
    assert [p["resourceName"] for p in res["people"]] == ["people/here"]


@pytest.mark.parametrize("status,body", [(410, "gone"), (429, '{"reason":"EXPIRED_SYNC_TOKEN"}')])
def test_an_expired_token_is_recognised_however_google_words_it(status, body):
    assert gp.is_expired_sync_token({"status": status, "error": body}) is True


def test_a_live_token_is_not_mistaken_for_an_expired_one():
    assert gp.is_expired_sync_token({"status": 200, "error": ""}) is False
    assert gp.is_expired_sync_token({"status": 429, "error": "rate limit"}) is False


def test_two_lists_two_tokens_one_field():
    """«Connections» and «other contacts» each get a token of their own; the widget stores one string and
    never has to know that."""
    joined = svc._join({"main": "A", "other": "B"})
    assert svc._split(joined) == {"main": "A", "other": "B"}
    assert svc._split(svc._join({"main": "A", "other": ""})) == {"main": "A", "other": ""}
    assert svc._split("") == {"main": "", "other": ""}


def test_a_TRUNCATED_read_throws_its_token_away(ct, monkeypatch):
    """A read that stopped at `max_pages` never saw the last pages. A token stamped there would make
    everything it skipped invisible FOREVER — the worst kind of bug, because the card would keep saying
    «sin cambios» and be telling the truth about a question it never asked."""
    monkeypatch.setattr(svc, "can_write", lambda provider_id="google-contacts", **kw: False)
    monkeypatch.setattr(svc, "fetch", lambda provider_id="google-contacts", **kw: {
        "ok": True, "contacts": [], "truncated": True, "syncToken": "tok-9", "full": True, "deleted": []})
    db = {"contacts": [], "sync": {"token": "tok-old"}}
    gcontacts.sync(db, merge=ct._merge_imported, remove=ct._drop_deleted)
    assert db["sync"]["token"] == "", "a partial read is not a place to resume from"


def test_a_complete_pass_KEEPS_the_token_it_was_given(ct, monkeypatch):
    monkeypatch.setattr(svc, "can_write", lambda provider_id="google-contacts", **kw: False)
    monkeypatch.setattr(svc, "fetch", lambda provider_id="google-contacts", **kw: {
        "ok": True, "contacts": [], "truncated": False, "syncToken": "tok-9", "full": False, "deleted": []})
    db = {"contacts": [], "sync": {}}
    res = gcontacts.sync(db, merge=ct._merge_imported, remove=ct._drop_deleted)
    assert db["sync"]["token"] == "tok-9"
    assert res["incremental"] is True


def test_the_token_it_HAS_is_the_one_it_sends(ct, monkeypatch):
    seen = {}
    monkeypatch.setattr(svc, "can_write", lambda provider_id="google-contacts", **kw: False)

    def _fetch(provider_id="google-contacts", *, sync_token=""):
        seen["token"] = sync_token
        return {"ok": True, "contacts": [], "truncated": False, "syncToken": "n", "full": False, "deleted": []}

    monkeypatch.setattr(svc, "fetch", _fetch)
    gcontacts.sync({"contacts": [], "sync": {"token": "tok-keep"}}, merge=ct._merge_imported)
    assert seen["token"] == "tok-keep"


# ── 2 · THE PUSH KNOWS WHAT IT HAS ALREADY SENT ─────────────────────────────────────────────────────────

def test_a_row_we_just_sent_is_not_sent_again():
    """THE regression this batch exists to prevent. With a date («edited today») a contact he corrected at
    09:00 is «ours» until midnight, so a pass every minute PATCHes it ~900 times. Nobody would have seen
    it: every one of those writes succeeds and writes the same values."""
    c = {"name": "Marta", "googleId": "people/c1", "updated": "2026-09-15"}
    assert gcontacts._is_ours(c, 0) is True, "an edited row is ours until Google has been told"
    gcontacts._mark_pushed([c])
    assert gcontacts._is_ours(c, 0) is False, "…and stops being ours the moment it has been"


def test_an_edit_AFTER_the_push_is_ours_again():
    c = {"name": "Marta", "googleId": "people/c1"}
    gcontacts._mark_pushed([c])
    c["touchedAt"] = c["pushedAt"] + 1
    assert gcontacts._is_ours(c, 0) is True


def test_a_contact_he_created_here_is_pushed_even_though_google_has_never_seen_it():
    assert gcontacts._is_ours({"name": "Nuevo", "googleId": ""}, 0) is True
    assert gcontacts._is_ours({"name": "", "googleId": ""}, 0) is False


def test_a_row_written_before_any_of_this_still_gets_ONE_chance():
    """Rows in his store carry neither clock. Reading them as «never touched» would silently drop every
    correction he made before today; reading them by date once, and stamping them on the way out, gets
    them onto the precise path without losing anything."""
    old = {"name": "Marta", "googleId": "people/c1", "updated": "2026-09-15"}
    assert gcontacts._is_ours(old, 0) is True
    gcontacts._mark_pushed([old])
    assert old.get("touchedAt") and old.get("pushedAt")
    assert gcontacts._is_ours(old, 0) is False


def test_the_operator_touching_a_contact_stamps_the_clock_the_sync_reads(ct):
    ct.apply_action("add_contact", {"name": "Marta Ruiz"})
    c = ct.load_db()["contacts"][0]
    assert float(c.get("touchedAt") or 0) > 0
    ct.apply_action("update_contact", {"contactId": c["id"], "phone": "+34600111222"})
    assert float(ct.load_db()["contacts"][0]["touchedAt"]) >= float(c["touchedAt"])


def test_GOOGLE_filling_in_a_blank_does_NOT_count_as_him_touching_it(ct):
    """The loop this closes: an import fills an empty city → the row looks «edited» → the next push sends
    Google its own value back → and around again, every minute, forever."""
    db = {"contacts": [{"id": "c1", "name": "Marta", "googleId": "people/c1", "city": "",
                        "groups": [], "updated": "2026-09-14"}], "next_id": 2}
    ct._merge_imported(db, [{"name": "Marta", "googleId": "people/c1", "city": "Soria", "groups": []}])
    c = db["contacts"][0]
    assert c["city"] == "Soria"
    assert "touchedAt" not in c, "an import is not an operator edit and must not read as one"


# ── 3 · A MIRROR REFLECTS CHANGES, NOT JUST ADDITIONS ───────────────────────────────────────────────────

def _row(**over):
    c = {"id": "c1", "name": "Marta", "googleId": "people/c1", "city": "Soria", "phone": "+34600111222",
         "email": "", "address": "", "notes": "", "groups": [], "favorite": False,
         "touchedAt": 100.0, "pushedAt": 100.0}
    c.update(over)
    return c


def test_a_change_made_on_his_PHONE_reaches_the_directory(ct):
    """His own example: «si eso está conectado a un teléfono y se modifica en el teléfono, todo el sistema
    se sincronizará». The phone writes to Google; Google hands it to us through the sync token; and because
    we have nothing pending on that row, Google touched it last and Google wins."""
    db = {"contacts": [_row()], "next_id": 2}
    ct._merge_imported(db, [{"name": "Marta", "googleId": "people/c1", "city": "Soria",
                             "phone": "+34699000111", "groups": []}], authoritative=True)
    assert db["contacts"][0]["phone"] == "+34699000111"


def test_a_change_he_has_NOT_sent_yet_still_wins(ct):
    """The row is waiting its turn in the push half. Letting Google win here would delete his edit before
    it ever left the house — «whoever touched it last», measured rather than assumed."""
    db = {"contacts": [_row(touchedAt=200.0, pushedAt=100.0, phone="+34611111111")], "next_id": 2}
    ct._merge_imported(db, [{"name": "Marta", "googleId": "people/c1", "phone": "+34699000111",
                             "groups": []}], authoritative=True)
    assert db["contacts"][0]["phone"] == "+34611111111"


def test_a_FULL_re_read_never_overwrites_anything(ct):
    """V2-699's rule, and it survives intact: in a full read «changed» is unknown, so treating every row as
    fresh would undo his corrections wholesale on the first pass after a token expires."""
    db = {"contacts": [_row()], "next_id": 2}
    ct._merge_imported(db, [{"name": "Marta", "googleId": "people/c1", "phone": "+34699000111",
                             "groups": []}], authoritative=False)
    assert db["contacts"][0]["phone"] == "+34600111222"


def test_an_authoritative_pass_still_only_fills_a_blank_it_is_given(ct):
    db = {"contacts": [_row()], "next_id": 2}
    ct._merge_imported(db, [{"name": "Marta", "googleId": "people/c1", "groups": []}], authoritative=True)
    assert db["contacts"][0]["phone"] == "+34600111222", "an absent field is not an erased one"


def test_a_contact_deleted_in_google_disappears_here(ct):
    db = {"contacts": [_row(), _row(id="c2", googleId="people/c2", name="Iván")], "next_id": 3}
    assert ct._drop_deleted(db, ["people/c2"]) == 1
    assert [c["id"] for c in db["contacts"]] == ["c1"]


def test_a_contact_he_has_JUST_EDITED_is_not_google_s_to_delete(ct):
    """He touched it last. The same rule that decides every other conflict in this connector decides this
    one, and it is the direction that cannot be undone."""
    db = {"contacts": [_row(touchedAt=300.0, pushedAt=100.0)], "next_id": 2}
    assert ct._drop_deleted(db, ["people/c1"]) == 0
    assert len(db["contacts"]) == 1


def test_a_deletion_of_somebody_we_never_linked_removes_nobody(ct):
    db = {"contacts": [_row(googleId="")], "next_id": 2}
    assert ct._drop_deleted(db, ["people/c1"]) == 0
    assert ct._drop_deleted(db, []) == 0


def test_TOO_MANY_deletions_at_once_removes_NOBODY_and_says_so(ct):
    """A circuit breaker around our OWN code, not a theory about how many contacts a person deletes in a
    minute. The failure mode of a sync token gone wrong is «everything looks deleted», and the difference
    between a bug and a catastrophe is whether anything acted on it."""
    rows = [_row(id=f"c{i}", googleId=f"people/c{i}") for i in range(100)]
    db = {"contacts": rows, "next_id": 101}
    assert ct._drop_deleted(db, [f"people/c{i}" for i in range(60)]) == 0
    assert len(db["contacts"]) == 100
    assert db["sync"]["blockedDeletes"] == 60, "a guard that protects silently is one he cannot trust"


def test_a_believable_number_of_deletions_still_goes_through(ct):
    rows = [_row(id=f"c{i}", googleId=f"people/c{i}") for i in range(100)]
    db = {"contacts": rows, "next_id": 101}
    assert ct._drop_deleted(db, [f"people/c{i}" for i in range(5)]) == 5


def test_deleting_a_contact_HERE_queues_it_for_google(ct):
    """The half a pull can never carry: once the row is gone from this store there is nothing left to
    compare, so the intention is written down and spent by the next push. Without it, his deletion comes
    back on the next full re-read and he has no way to tell why."""
    ct.apply_action("add_contact", {"name": "Marta Ruiz"})
    db = ct.load_db()
    db["contacts"][0]["googleId"] = "people/c1"
    from widgets import store
    store.save(ct.WIDGET_ID, db)
    ct.apply_action("remove_contact", {"contactId": db["contacts"][0]["id"]})
    assert ct.load_db()["sync"]["pendingDeletes"] == ["people/c1"]


def test_deleting_a_contact_google_never_had_queues_nothing(ct):
    ct.apply_action("add_contact", {"name": "Solo Local"})
    cid = ct.load_db()["contacts"][0]["id"]
    ct.apply_action("remove_contact", {"contactId": cid})
    assert not (ct.load_db().get("sync") or {}).get("pendingDeletes")


def test_the_queue_is_spent_only_when_google_actually_took_it(ct, monkeypatch):
    sent = {}
    monkeypatch.setattr(svc, "can_write", lambda provider_id="google-contacts", **kw: True)
    monkeypatch.setattr(svc, "push", lambda rows, pid="google-contacts", *, gone=None: (
        sent.update({"gone": list(gone or [])}), {"ok": True, "sent": 0, "created": 0, "removed": 1})[1])
    monkeypatch.setattr(svc, "fetch", lambda provider_id="google-contacts", **kw: {
        "ok": True, "contacts": [], "truncated": False, "full": False, "deleted": [], "syncToken": "t"})
    db = {"contacts": [], "sync": {"pendingDeletes": ["people/c1"]}}
    gcontacts.sync(db, merge=ct._merge_imported, remove=ct._drop_deleted)
    assert sent["gone"] == ["people/c1"]
    assert db["sync"]["pendingDeletes"] == []


def test_a_REFUSED_push_keeps_the_deletion_for_next_time(ct, monkeypatch):
    """Clearing it here would lose the deletion silently, and the next full read would resurrect the row."""
    monkeypatch.setattr(svc, "can_write", lambda provider_id="google-contacts", **kw: True)
    monkeypatch.setattr(svc, "push", lambda rows, pid="google-contacts", *, gone=None: {
        "ok": False, "error": "solo lectura"})
    monkeypatch.setattr(svc, "fetch", lambda provider_id="google-contacts", **kw: {
        "ok": True, "contacts": [], "truncated": False, "full": False, "deleted": [], "syncToken": "t"})
    db = {"contacts": [], "sync": {"pendingDeletes": ["people/c1"]}}
    gcontacts.sync(db, merge=ct._merge_imported, remove=ct._drop_deleted)
    assert db["sync"]["pendingDeletes"] == ["people/c1"]


def test_a_person_google_no_longer_has_counts_as_DELETED_not_as_a_failure():
    """404 is the end state he asked for: it is not there."""
    class _Cl:
        def delete(self, url, headers=None, timeout=None):
            return _Resp(404, {})
    assert gp.delete_person(_Cl(), "https://x/v1", "T", "people/c1") == {"ok": True, "already": True}


def test_deleting_needs_a_resource_name():
    assert gp.delete_person(None, "https://x/v1", "T", "")["ok"] is False


# ── 4 · IT STAYS ON ─────────────────────────────────────────────────────────────────────────────────────

class _Ctx:
    def __init__(self):
        self.saved = []

    def save(self, db):
        self.saved.append(db)


def _linked(monkeypatch, *, connected=True):
    import connectors.contacts.oauth as oa
    monkeypatch.setattr(oa, "tokens_present", lambda pid="google-contacts": connected)


def test_a_dormant_account_is_never_polled(ct, monkeypatch):
    _linked(monkeypatch, connected=False)
    called = []
    monkeypatch.setattr(gcontacts, "sync", lambda *a, **k: called.append(1))
    gcontacts.tick(_Ctx())
    assert called == []


def test_the_switch_being_OFF_stops_the_next_pass(ct, monkeypatch):
    _linked(monkeypatch)
    from widgets import store
    store.save(ct.WIDGET_ID, {"contacts": [], "next_id": 1, "sync": {"auto": False}})
    called = []
    monkeypatch.setattr(gcontacts, "sync", lambda *a, **k: called.append(1))
    gcontacts.tick(_Ctx())
    assert called == [], "there is nothing to cancel: the tick reads the state every pass"


def test_a_pass_that_just_ran_does_not_run_again(ct, monkeypatch):
    """The scheduler wakes this module far more often than it should talk to Google. The period lives HERE,
    so it can change without touching the manifest and a card reopening never triggers a pass."""
    import time
    _linked(monkeypatch)
    from widgets import store
    store.save(ct.WIDGET_ID, {"contacts": [], "next_id": 1, "sync": {"auto": True, "last": time.time()}})
    called = []
    monkeypatch.setattr(gcontacts, "sync", lambda *a, **k: called.append(1))
    gcontacts.tick(_Ctx())
    assert called == []


def test_a_due_pass_runs_and_SAVES(ct, monkeypatch):
    _linked(monkeypatch)
    from widgets import store
    store.save(ct.WIDGET_ID, {"contacts": [], "next_id": 1, "sync": {"auto": True, "last": 0.0}})
    monkeypatch.setattr(gcontacts, "sync", lambda db, **k: {"ok": True, "added": 1})
    ctx = _Ctx()
    gcontacts.tick(ctx)
    assert len(ctx.saved) == 1, "a pass nobody saves is a pass the open card never sees"


def test_a_FAILED_pass_still_moves_the_clock(ct, monkeypatch):
    """Otherwise a dead token makes every tick retry immediately, from a loop nobody is watching, against
    somebody else's rate limit."""
    _linked(monkeypatch)
    from widgets import store
    store.save(ct.WIDGET_ID, {"contacts": [], "next_id": 1, "sync": {"auto": True, "last": 0.0}})
    monkeypatch.setattr(gcontacts, "sync", lambda db, **k: {"ok": False, "error": "Google dice que no"})
    ctx = _Ctx()
    gcontacts.tick(ctx)
    assert ctx.saved[0]["sync"]["last"] > 0
    assert "Google dice que no" in ctx.saved[0]["sync"]["lastResult"]["error"]


def test_the_switch_is_a_STATE_the_store_keeps(ct):
    assert ct.apply_action("set_auto", {"auto": False})["ok"] is True
    assert ct.load_db()["sync"]["auto"] is False
    ct.apply_action("set_auto", {"auto": True})
    assert ct.load_db()["sync"]["auto"] is True


def test_the_card_is_told_how_often_it_runs(ct):
    """A label with a hardcoded «cada minuto» is one nobody keeps in step with the scheduler."""
    s = gcontacts.sync_state({})
    assert s["every"] == int(gcontacts.PERIOD)
    assert s["auto"] is True, "connected and syncing is the default — he asked for permanent"


def test_the_widget_declares_the_cycle_or_nothing_ever_calls_tick():
    """`tick` is only ever called because `manifest.json` declares a cycle. A tick with no declaration is a
    function that exists, passes its unit tests, and never runs — the «módulo que nace muerto» family."""
    m = json.loads((ENGINE / "widgets" / "contactos" / "manifest.json").read_text(encoding="utf-8"))
    from widgets.background import background_period
    assert background_period(m), "no background cycle: the permanent sync would never happen"
    from widgets.contactos import data as d
    assert callable(getattr(d, "tick", None)), "the scheduler's contract needs `tick` in data.py"
