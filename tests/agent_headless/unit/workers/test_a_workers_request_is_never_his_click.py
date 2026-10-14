"""A worker's request is never his click — on any route family his screen calls (2026-10-14).

A background worker has Bash on his machine. `curl -X POST 127.0.0.1:43917/widgets/<id>/action` was recorded as
HIS click (`provenance.note(wid, "user")`) and skipped `/api/worker/act` with its consent gate; the same held for
sending a message, adding a contact, an agenda row, a setting, or injecting a turn through `/api/flash/say`.
`server/operator_gate.decide` admits a mutation for his screen (the per-boot UI cookie) or a process the engine
did not spawn, and refuses a worker on every family. The worker's own doors stay open to it.
"""
from __future__ import annotations

import pytest

from server import operator_gate as G
from server import peer_process as P

#: One representative per family of routes that change something on his behalf.
FAMILIES = {
    "widget action": ("POST", "/widgets/contactos/action"),
    "widget confirm": ("POST", "/widgets/agenda/confirm"),
    "widget delete": ("DELETE", "/widgets/notas"),
    "messaging connect": ("POST", "/api/messaging/whatsapp/connect"),
    "cluster send": ("POST", "/api/meshkore/send"),
    "contacts import": ("POST", "/api/contacts/connect"),
    "agenda lists": ("POST", "/api/lists"),
    "agenda reminders": ("POST", "/api/cron/create"),
    "tasks": ("POST", "/api/tasks/reopen"),
    "settings": ("POST", "/api/settings"),
    "config credential": ("POST", "/api/config/credential"),
    "vault": ("POST", "/api/vault/reveal"),
    "his spoken turn": ("POST", "/api/flash/say"),
    "factory reset": ("POST", "/api/reset/full"),
    "legacy user route": ("POST", "/user"),
}


def _d(method, path, **kw):
    base = dict(path=path, method=method, cloud=False, in_process=False, holds_ui=False, kind=None,
                peer_loopback=True, token_ok=False)
    base.update(kw)
    return G.decide(**base)


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_a_worker_shaped_request_is_refused(family):
    method, path = FAMILIES[family]
    ok, reason, mint = _d(method, path, kind=P.WORKER)
    assert not ok and reason == "worker_is_not_the_operator" and not mint, family
    assert not _d(method, path, kind=P.WORKER, token_ok=True)[0], "the API token never makes a worker him"


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_a_ui_shaped_request_passes(family):
    method, path = FAMILIES[family]
    assert _d(method, path, holds_ui=True)[:2] == (True, "ui_session"), family
    ok, reason, mint = _d(method, path, kind=P.OUTSIDE)
    assert ok and mint, "his browser before its cookie, his terminal, the harness: admitted and minted"


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_what_cannot_be_attributed_is_refused(family):
    method, path = FAMILIES[family]
    assert not _d(method, path, kind=P.UNKNOWN)[0]
    assert not _d(method, path, kind=P.SELF)[0], "the engine's own fetches (the agent's tools) are not him"
    assert _d(method, path, kind=P.UNKNOWN, peer_loopback=False, token_ok=True)[0], \
        "a remote caller with ZAELAR_API_TOKEN: the door he opened on purpose"
    assert not _d(method, path, kind=P.UNKNOWN, peer_loopback=True, token_ok=True)[0], \
        "on loopback the token proves nothing: a worker inherits the environment"


@pytest.mark.parametrize("path", ["/api/worker/act", "/api/worker/say", "/api/agent/report",
                                  "/api/navegador/act", "/api/memory/remember", "/api/memory/recall",
                                  "/api/search/find"])
def test_the_workers_own_doors_stay_open_to_it(path):
    assert _d("POST", path, kind=P.WORKER)[0], path


def test_reads_are_not_operator_routes():
    assert _d("GET", "/widgets/agenda/data", kind=P.WORKER)[0]
    assert _d("GET", "/api/tasks", kind=P.WORKER)[0]


def test_the_shells_mint_his_cookie_and_never_a_workers():
    for shell in ("/", "/m"):
        assert _d("GET", shell, kind=P.OUTSIDE) == (True, "shell", True)
        assert _d("GET", shell, kind=P.WORKER) == (True, "shell", False), "the page is served, the cookie is not"
        assert _d("GET", shell, kind=P.SELF)[2] is False
        assert _d("GET", shell, holds_ui=True)[2] is False, "already holds it"


def test_cloud_and_in_process_are_not_this_gates_business():
    assert _d("POST", "/widgets/x/action", cloud=True, kind=None)[:2] == (True, "cloud_session")
    assert _d("POST", "/widgets/x/action", in_process=True)[:2] == (True, "in_process")
