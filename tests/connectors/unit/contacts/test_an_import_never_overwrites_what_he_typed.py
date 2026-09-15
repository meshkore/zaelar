"""V2-699 — importing the Google address book, and the one rule that governs it.

The operator asked «si era posible importar del conector de Google». The interesting half is not the
fetch: it is what happens the SECOND time, to a contact he has since corrected by hand or by voice.

The policy, in one line: **his edits win — Google only fills in what is empty here.** A re-import that
overwrote a field he had fixed would silently undo the correction, and he would have no way to tell which
of the two surfaces was lying. That is the same failure family as the agenda's `status` field in V2-697,
where one name meant two things depending on provenance.

The connector FETCHES and shapes; `widgets/contactos/data.py` MERGES, because it is the only module that
knows which fields the operator typed himself.
"""
from __future__ import annotations

import pytest

from connectors.contacts import google_people as gp
from connectors.contacts import providers as pv


# ── shaping one Google person ───────────────────────────────────────────────────────────────────────────

def _person(**over):
    p = {"resourceName": "people/c777",
         "names": [{"displayName": "Marta Ruiz", "metadata": {"primary": True}}],
         "emailAddresses": [{"value": "marta@example.com", "metadata": {"primary": True}}],
         "phoneNumbers": [{"value": "+34600111222", "metadata": {"primary": True}}],
         "addresses": [{"formattedValue": "C/ Mayor 1, Soria", "city": "Soria",
                        "metadata": {"primary": True}}]}
    p.update(over)
    return p


def test_a_person_becomes_the_record_the_directory_already_stores():
    c = gp.person_to_contact(_person())
    assert c["name"] == "Marta Ruiz"
    assert c["email"] == "marta@example.com"
    assert c["phone"] == "+34600111222"
    assert c["city"] == "Soria"
    assert c["googleId"] == "people/c777"
    assert c["kind"] == "person"


def test_the_primary_row_wins_over_the_first_one():
    """Google does not always mark a primary, but when it does, taking `[0]` is how an old work address
    becomes somebody's only address."""
    c = gp.person_to_contact(_person(emailAddresses=[
        {"value": "old@work.example"},
        {"value": "marta@example.com", "metadata": {"primary": True}}]))
    assert c["email"] == "marta@example.com"


def test_a_row_with_neither_a_name_nor_an_email_is_not_a_contact():
    """«Other contacts» is full of these. A blank line in the directory is one he can neither search for
    nor act on, and it would bury the twelve people he actually cares about."""
    assert gp.person_to_contact({"resourceName": "people/x", "phoneNumbers": [{"value": "+34600"}]}) is None
    assert gp.person_to_contact({}) is None
    assert gp.person_to_contact("not a dict") is None


def test_an_email_only_row_is_named_after_its_address():
    c = gp.person_to_contact({"resourceName": "people/x",
                              "emailAddresses": [{"value": "gavin.hayes@zerohash.com"}]})
    assert c["name"] == "gavin.hayes"


def test_his_star_in_google_is_his_star_here():
    """Importing `starred` as a group called «starred» would have made him re-star everyone by hand."""
    c = gp.person_to_contact(_person(memberships=[
        {"contactGroupMembership": {"contactGroupId": "starred"}}]))
    assert c["favorite"] is True
    assert "starred" not in c["groups"]


def test_googles_labels_become_our_group_labels():
    c = gp.person_to_contact(_person(memberships=[
        {"contactGroupMembership": {"contactGroupId": "7a1"}},
        {"contactGroupMembership": {"contactGroupId": "myContacts"}}]), {"7a1": "Trabajo"})
    assert c["groups"] == ["Trabajo"], "the system labels are plumbing, not groups he chose"


def test_every_string_is_capped_at_the_boundary():
    """Anybody who emails him can land in «Other contacts» with a display name they chose, so the trim
    happens HERE — the card, the prompt digest and the voice payloads read the same row and only one of
    them would have remembered to do it."""
    c = gp.person_to_contact(_person(names=[{"displayName": "A" * 500}],
                                     biographies=[{"value": "B" * 900}]))
    assert len(c["name"]) <= 80
    assert len(c["notes"]) <= 300


# ── the registry ────────────────────────────────────────────────────────────────────────────────────────

def test_the_default_tier_asks_only_for_the_address_book_he_curated():
    p = pv.get("google-contacts")
    assert p.tier().scopes == ("https://www.googleapis.com/auth/contacts.readonly",)
    assert "other" not in " ".join(p.tier().scopes), "«Other contacts» is opt-in, never the default"


def test_writing_back_is_a_tier_OF_ITS_OWN_and_never_the_default():
    """The operator asked for a two-way link («si se modifica algo en nuestro agente, también se modifica
    en Google»), so the write scope is real. What must not happen is anybody GETTING it without choosing
    it: a connect that silently asked for write would hand Google's copy of his address book to a bug.
    """
    p = pv.get("google-contacts")
    assert p.tier().writes is False, "the default connect stays read-only"
    sync = p.tier("sync")
    assert sync.writes is True
    assert sync.scopes == ("https://www.googleapis.com/auth/contacts",)


def test_the_only_write_scope_we_ever_ask_for_is_the_contacts_one():
    """Nothing wider sneaks in beside it — `contacts` covers exactly the address book and nothing else."""
    every = {s for p in pv.PROVIDERS.values() for t in p.tiers for s in t.scopes}
    writing = {s for s in every if not s.endswith(".readonly")}
    assert writing == {"https://www.googleapis.com/auth/contacts"}, every


def test_a_tier_that_can_write_is_ASKED_never_guessed_from_the_scope_string():
    """`service.can_write` reads the flag off the granted tier. A surface that re-derived it by grepping
    the scope text would eventually guess wrong in the direction that loses data."""
    assert pv.writes("google-contacts", "sync") is True
    assert pv.writes("google-contacts", "saved") is False
    assert pv.writes("google-contacts", "saved+other") is False
    assert pv.writes("google-contacts", "") is False, "no tier granted is not a licence to write"


# ── the merge, which is the widget's ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def ct(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real directory, and a fresh one PER TEST.

    ⚠️ The root `conftest.py` sandboxes the widget data dir for the session, which keeps the suite off his
    real contacts but lets rows pile up from one test into the next. Every case here counts rows, so a
    shared store makes them pass or fail on execution order rather than on the merge.
    """
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as _d
    return _d


def _imported(monkeypatch, rows):
    """Stand in for the network, at the SERVICE boundary — the merge is what is under test."""
    import connectors.contacts.service as svc
    monkeypatch.setattr(svc, "fetch", lambda provider_id="google-contacts", **kw: {
        "ok": True, "contacts": rows, "total": len(rows), "truncated": False, "included_other": False})


def test_an_import_fills_in_what_is_empty(ct, monkeypatch):
    ct.apply_action("add_contact", {"name": "Marta Ruiz"})
    _imported(monkeypatch, [{"name": "Marta Ruiz", "kind": "person", "email": "marta@example.com",
                             "phone": "+34600111222", "city": "Soria", "address": "", "notes": "",
                             "groups": [], "favorite": False, "googleId": "people/c777"}])
    res = ct.apply_action("import_google", {})
    assert res["ok"] and res["result"]["updated"] == 1 and res["result"]["added"] == 0
    c = ct.load_db()["contacts"][0]
    assert c["email"] == "marta@example.com" and c["city"] == "Soria"


def test_an_import_NEVER_overwrites_what_he_typed(ct, monkeypatch):
    """The whole policy, and the reason a second import is safe to run."""
    ct.apply_action("add_contact", {"name": "Marta Ruiz", "city": "Barcelona",
                                    "phone": "+34699999999"})
    _imported(monkeypatch, [{"name": "Marta Ruiz", "kind": "person", "email": "marta@example.com",
                             "phone": "+34600111222", "city": "Soria", "address": "", "notes": "",
                             "groups": [], "favorite": False, "googleId": "people/c777"}])
    ct.apply_action("import_google", {})
    c = ct.load_db()["contacts"][0]
    assert c["city"] == "Barcelona", "he corrected this; Google does not get to undo it"
    assert c["phone"] == "+34699999999"
    assert c["email"] == "marta@example.com", "but an EMPTY field is still filled in"


def test_a_star_travels_one_way_only(ct, monkeypatch):
    ct.apply_action("add_contact", {"name": "Marta Ruiz", "favorite": True})
    _imported(monkeypatch, [{"name": "Marta Ruiz", "kind": "person", "email": "", "phone": "", "city": "",
                             "address": "", "notes": "", "groups": [], "favorite": False,
                             "googleId": "people/c777"}])
    ct.apply_action("import_google", {})
    assert ct.load_db()["contacts"][0]["favorite"] is True, "un-starring in Google never un-stars here"


def test_importing_twice_does_not_duplicate_anybody(ct, monkeypatch):
    rows = [{"name": "Marta Ruiz", "kind": "person", "email": "marta@example.com", "phone": "", "city": "",
             "address": "", "notes": "", "groups": [], "favorite": False, "googleId": "people/c777"}]
    _imported(monkeypatch, rows)
    first = ct.apply_action("import_google", {})
    second = ct.apply_action("import_google", {})
    assert first["result"]["added"] == 1
    assert second["result"]["added"] == 0 and second["result"]["unchanged"] == 1
    assert len(ct.load_db()["contacts"]) == 1


def test_a_renamed_contact_is_still_the_same_person(ct, monkeypatch):
    """`googleId` outranks the name, so correcting somebody's name here does not make them import twice."""
    rows = [{"name": "Marta Ruiz", "kind": "person", "email": "", "phone": "", "city": "", "address": "",
             "notes": "", "groups": [], "favorite": False, "googleId": "people/c777"}]
    _imported(monkeypatch, rows)
    ct.apply_action("import_google", {})
    cid = ct.load_db()["contacts"][0]["id"]
    ct.apply_action("update_contact", {"contactId": cid, "name": "Marta (del trabajo)"})
    ct.apply_action("import_google", {})
    assert len(ct.load_db()["contacts"]) == 1


def test_one_email_address_is_one_person(ct, monkeypatch):
    """The rule V2-693 already settled for Telegram: an address is an account, so two rows sharing one are
    one person — even when the names do not match at all."""
    ct.apply_action("add_contact", {"name": "Cryptonite",
                                    "channels": [{"platform": "email", "handle": "hola@cryptonite.fund"}]})
    _imported(monkeypatch, [{"name": "Cryptonite Fund SL", "kind": "person",
                             "email": "hola@cryptonite.fund", "phone": "+34600", "city": "", "address": "",
                             "notes": "", "groups": [], "favorite": False, "googleId": "people/c9"}])
    ct.apply_action("import_google", {})
    assert len(ct.load_db()["contacts"]) == 1
    assert ct.load_db()["contacts"][0]["name"] == "Cryptonite", "his name for them wins"


def test_a_city_google_knows_and_he_never_typed_is_not_a_second_person(ct, monkeypatch):
    """The counterweight to the name+city rule, and the reason a re-import is idempotent.

    `add_contact` can demand a matching city because the operator is looking at the answer. Google
    routinely knows a city he never typed, so name+city alone would import a SECOND «Marta Ruiz» on every
    single pass — the duplicate class V2-693 already paid for.
    """
    ct.apply_action("add_contact", {"name": "Marta Ruiz"})
    _imported(monkeypatch, [{"name": "Marta Ruiz", "kind": "person", "email": "", "phone": "",
                             "city": "Soria", "address": "", "notes": "", "groups": [],
                             "favorite": False, "googleId": "people/c777"}])
    ct.apply_action("import_google", {})
    ct.apply_action("import_google", {})
    assert len(ct.load_db()["contacts"]) == 1


def test_two_people_with_the_same_name_are_never_folded_into_one(ct, monkeypatch):
    """Where the name-alone fallback STOPS. Adding a duplicate he can merge beats silently merging two
    people, which he cannot undo."""
    ct.apply_action("add_contact", {"name": "Juan", "city": "Soria"})
    ct.apply_action("add_contact", {"name": "Juan", "city": "Barcelona"})
    _imported(monkeypatch, [{"name": "Juan", "kind": "person", "email": "", "phone": "+34600",
                             "city": "", "address": "", "notes": "", "groups": [], "favorite": False,
                             "googleId": "people/c9"}])
    ct.apply_action("import_google", {})
    rows = ct.load_db()["contacts"]
    assert len(rows) == 3, "an ambiguous name adds a row rather than guessing which Juan it is"
    assert [r["phone"] for r in rows if r["city"] == "Soria"] == [""], "neither existing Juan was touched"
    assert [r["phone"] for r in rows if r["city"] == "Barcelona"] == [""]


def test_a_dormant_connector_says_so_instead_of_pretending(ct, monkeypatch):
    import connectors.contacts.service as svc
    monkeypatch.setattr(svc, "fetch", lambda provider_id="google-contacts", **kw: {
        "ok": False, "error": "no hay conexión con Google Contacts — pulsa «Conectar»"})
    res = ct.apply_action("import_google", {})
    assert res["ok"] is False and "Conectar" in res["error"]
    assert ct.load_db()["contacts"] == [], "a failed import writes NOTHING"


# ── the OTHER direction: what we send back (V2-699, his second ask) ──────────────────────────────────────
# «Si se modifica algo en nuestro agente, un nombre, un teléfono, también se modifica en Google.»

def test_our_record_becomes_the_person_body_google_expects():
    body = gp.contact_to_person({"name": "Marta Ruiz", "email": "marta@example.com",
                                 "phone": "+34600111222", "city": "Soria",
                                 "address": "C/ Mayor 1", "notes": "del trabajo"})
    assert body["names"] == [{"displayName": "Marta Ruiz"}]
    assert body["emailAddresses"] == [{"value": "marta@example.com"}]
    assert body["addresses"][0]["city"] == "Soria"
    assert body["biographies"][0]["contentType"] == "TEXT_PLAIN"


def test_an_empty_field_is_never_SENT_because_sending_it_would_clear_it():
    """⚠️ `updatePersonFields` is a whitelist and everything listed is REPLACED — so a field we name but
    do not fill is DELETED on Google's side. Building the body from the values present, and the field mask
    from the body, is what keeps a blank local note from wiping the note on his phone."""
    body = gp.contact_to_person({"name": "Marta Ruiz", "email": "", "phone": "", "notes": ""})
    assert set(body) == {"names"}
    fields = [k for k in gp.WRITABLE if k in body]
    assert fields == ["names"]


def test_a_contact_with_no_name_is_not_created_in_google():
    """The guard is in `create_person`, not in the shaping: the body of a nameless row is legitimate for
    an UPDATE (it just does not touch the name), and only a CREATE needs a name to exist at all."""
    body = gp.contact_to_person({"phone": "+34600"})
    assert "names" not in body

    class _Refuses:
        def post(self, *a, **k):
            raise AssertionError("create_person must refuse before it reaches the network")

    res = gp.create_person(_Refuses(), "https://people.googleapis.com/v1", "tok", {"phone": "+34600"})
    assert res["ok"] is False and "nombre" in res["error"]


def test_a_read_only_connection_REFUSES_to_push_instead_of_failing_silently(monkeypatch):
    import connectors.contacts.oauth as oa
    import connectors.contacts.service as svc
    monkeypatch.setattr(oa, "account", lambda pid="google-contacts": {"tier": "saved", "refresh_token": "x"})
    assert svc.can_write("google-contacts") is False
    res = svc.push([{"id": "c1", "name": "Marta"}], "google-contacts")
    assert res["ok"] is False and "solo lectura" in res["error"]


def test_the_push_half_runs_BEFORE_the_pull_half(ct, monkeypatch):
    """Order is load-bearing. Pulling first would fetch a stale Google row, merge it in, and then push the
    result back — laundering a stale value into a fresh one. Pushing first means the pull sees what we
    just wrote and finds nothing to undo."""
    from widgets.contactos import gcontacts
    import connectors.contacts.service as svc
    order = []
    monkeypatch.setattr(svc, "can_write", lambda provider_id="google-contacts", **kw: True)
    monkeypatch.setattr(svc, "push", lambda rows, pid="google-contacts", **kw: (order.append("push"),
                                                                 {"ok": True, "sent": 1, "created": 0,
                                                                  "failed": 0})[1])
    monkeypatch.setattr(svc, "fetch", lambda provider_id="google-contacts", **kw: (order.append("fetch"),
                                                                    {"ok": True, "contacts": []})[1])
    ct.apply_action("add_contact", {"name": "Marta Ruiz"})
    ct.apply_action("sync_contacts", {})
    assert order == ["push", "fetch"]


def test_a_refused_push_does_not_cancel_the_pull(ct, monkeypatch):
    """A one-way connection still has a job to do. Reporting the refusal and doing the half that works
    beats refusing everything and leaving him with nothing."""
    from widgets.contactos import gcontacts
    import connectors.contacts.service as svc
    monkeypatch.setattr(svc, "can_write", lambda provider_id="google-contacts", **kw: True)
    monkeypatch.setattr(svc, "push", lambda rows, pid="google-contacts", **kw: {"ok": False, "error": "solo lectura"})
    monkeypatch.setattr(svc, "fetch", lambda provider_id="google-contacts", **kw: {
        "ok": True, "contacts": [{"name": "Gavin", "kind": "person", "email": "g@x.com", "phone": "",
                                  "city": "", "address": "", "notes": "", "groups": [],
                                  "favorite": False, "googleId": "people/c1"}]})
    ct.apply_action("add_contact", {"name": "Marta Ruiz"})     # something for the push half to refuse on
    res = ct.apply_action("sync_contacts", {})
    assert res["ok"] is True
    assert res["result"]["pushError"] == "solo lectura"
    assert res["result"]["added"] == 1


def test_a_contact_he_created_here_is_pushed_even_though_google_has_never_seen_it():
    from widgets.contactos import gcontacts
    assert gcontacts._is_ours({"name": "Marta", "googleId": "", "updated": "2020-01-01"}, 9e9) is True
    assert gcontacts._is_ours({"name": "", "googleId": ""}, 0) is False, "a nameless row is not pushable"


def test_the_sync_records_when_it_ran_so_the_box_is_not_guessing(ct, monkeypatch):
    import connectors.contacts.service as svc
    monkeypatch.setattr(svc, "can_write", lambda provider_id="google-contacts", **kw: False)
    monkeypatch.setattr(svc, "fetch", lambda provider_id="google-contacts", **kw: {"ok": True, "contacts": []})
    assert ct.view_data()["sync"]["last"] == 0.0
    ct.apply_action("sync_contacts", {})
    assert ct.view_data()["sync"]["last"] > 0


def test_the_retired_name_still_answers(ct, monkeypatch):
    """`import_google` shipped in the manifest for one build. A model that learned it must not start
    getting «acción desconocida» for asking the same thing."""
    import connectors.contacts.service as svc
    monkeypatch.setattr(svc, "can_write", lambda provider_id="google-contacts", **kw: False)
    monkeypatch.setattr(svc, "fetch", lambda provider_id="google-contacts", **kw: {"ok": True, "contacts": []})
    assert ct.apply_action("import_google", {})["ok"] is True


# ── the two cases a GREEN disarm exposed ────────────────────────────────────────────────────────────────
# Both were «tested» by assertions that re-implemented the product line instead of running it, so breaking
# the product left them passing. `feedback_un_test_que_reimplementa_no_prueba_el_producto`, paid again.

class _Recorder:
    """A stand-in HTTP client that records the call instead of making it."""

    def __init__(self, person=None):
        self.person = person if person is not None else {"etag": "%etag%", "resourceName": "people/c1"}
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, params))
        return _Resp(200, self.person)

    def patch(self, url, params=None, json=None, headers=None, timeout=None):
        self.calls.append(("PATCH", url, params, json))
        return _Resp(200, {"resourceName": "people/c1"})


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._b, self.text = status, body, ""

    def json(self):
        return self._b


def test_the_field_mask_NAMES_only_what_is_being_sent():
    """⚠️ `updatePersonFields` is a whitelist and everything listed is REPLACED. A constant mask would
    DELETE, on Google's side, every field this contact happens to have empty here — his note, his address,
    his phone — and return 200 while doing it.

    Measured against the real request, not against a list comprehension that repeats the product's own
    line: a disarm replacing the mask with `",".join(WRITABLE)` stayed green until this case existed.
    """
    c = _Recorder()
    res = gp.update_person(c, "https://people.googleapis.com/v1", "tok",
                           "people/c1", {"name": "Marta Ruiz", "phone": "", "notes": ""})
    assert res["ok"] is True
    patch = [x for x in c.calls if x[0] == "PATCH"][0]
    assert patch[2]["updatePersonFields"] == "names", patch[2]
    assert set(patch[3]) == {"names", "etag"}


def test_an_update_carries_the_etag_it_just_read():
    """The etag is what stops us overwriting an edit made on his phone since we last read — so the write
    is a READ-MODIFY-WRITE, the shape V2-697's calendar RSVP had to become."""
    c = _Recorder()
    gp.update_person(c, "https://people.googleapis.com/v1", "tok", "people/c1", {"name": "Marta"})
    assert [x[0] for x in c.calls] == ["GET", "PATCH"], "it reads before it writes"
    assert [x for x in c.calls if x[0] == "PATCH"][0][3]["etag"] == "%etag%"


def test_an_update_without_an_etag_refuses_rather_than_guessing():
    c = _Recorder(person={"resourceName": "people/c1"})
    res = gp.update_person(c, "https://people.googleapis.com/v1", "tok", "people/c1", {"name": "Marta"})
    assert res["ok"] is False and "etag" in res["error"]
    assert not [x for x in c.calls if x[0] == "PATCH"], "nothing was written"


def test_the_sync_box_only_claims_two_ways_when_the_GRANTED_tier_can_write(ct, monkeypatch):
    """`sync_state` is what paints the ⇄. Deriving it from «connected» alone would promise a write-back
    that Google refuses — a disarm doing exactly that stayed green until this case existed."""
    import connectors.contacts.oauth as oa
    monkeypatch.setattr(oa, "tokens_present", lambda pid="google-contacts": True)

    monkeypatch.setattr(oa, "account", lambda pid="google-contacts": {"tier": "saved", "refresh_token": "x"})
    st = ct.view_data()["sync"]
    assert st["connected"] is True and st["twoWay"] is False

    monkeypatch.setattr(oa, "account", lambda pid="google-contacts": {"tier": "sync", "refresh_token": "x"})
    assert ct.view_data()["sync"]["twoWay"] is True

    monkeypatch.setattr(oa, "tokens_present", lambda pid="google-contacts": False)
    st = ct.view_data()["sync"]
    assert st["connected"] is False and st["twoWay"] is False, "disconnected is never two-way"
