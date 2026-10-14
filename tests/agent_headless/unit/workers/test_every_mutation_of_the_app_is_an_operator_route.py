"""Every mutation of the assembled app is an operator route, unless it is a NAMED worker door (2026-10-14).

The gate is default-deny for a worker: what is not listed in `operator_gate.WORKER_DOORS` is the operator's.
Pinned against the app as it is assembled, so a new route is covered the day it is mounted, and a new worker door
has to be named here — on purpose, with the reason it may skip his consent. Also pinned: the gate is mounted,
`api_guard` stays the outer middleware, and the CSRF/rebinding rules now reach the mutations his screen makes
outside `/api/` (`/widgets/{id}/action` was open to a cross-site POST).
"""
from __future__ import annotations

from server import api_guard, operator_gate

#: The only mutating routes a worker may call, each with its own check. Adding one here is a security decision.
EXPECTED_WORKER_DOORS = {
    "/api/worker/act": "the worker plane: classify_act + on_his_behalf decide",
    "/api/worker/say": "the worker plane",
    "/api/agent/report": "the worker's progress report",
    "/api/navegador/act": "the browser bridge (the click gate governs what leaves)",
    "/api/memory/recall": "a read",
    "/api/memory/remember": "per-task token; written as the worker's, never his",
    "/api/search/find": "the search service",
    "/api/search/route": "the search service",
}


def _walk(routes, prefix=""):
    for r in routes:
        inner = getattr(r, "original_router", None)          # FastAPI keeps an included router whole
        if inner is not None:
            ctx = getattr(r, "include_context", None)
            yield from _walk(inner.routes, prefix + (getattr(ctx, "prefix", "") or ""))
        else:
            for m in sorted(getattr(r, "methods", None) or ()):
                yield m, prefix + r.path


def _mutating_routes():
    from server import create_app
    routes = {(m, p) for m, p in _walk(create_app().routes) if m in api_guard.MUTATING}
    assert len(routes) > 80, "the walk found almost nothing: it is the walk that broke, not the app"
    return routes


def test_every_mutation_is_the_operators_or_a_named_worker_door():
    doors = {p for m, p in _mutating_routes() if not operator_gate.is_operator_route(p, m)}
    assert doors == set(EXPECTED_WORKER_DOORS), doors ^ set(EXPECTED_WORKER_DOORS)


def test_the_families_his_screen_uses_are_operator_routes():
    routes = set(_mutating_routes())
    for m, p in [("POST", "/widgets/{wid}/action"), ("POST", "/widgets/{wid}/confirm"),
                 ("DELETE", "/widgets/{wid}"), ("POST", "/api/messaging/{platform}/connect"),
                 ("POST", "/api/meshkore/send"), ("POST", "/api/contacts/connect"), ("POST", "/api/lists"),
                 ("POST", "/api/settings"), ("POST", "/api/config/credential"), ("POST", "/api/flash/say")]:
        assert (m, p) in routes, f"{m} {p} is not mounted any more — update the family list"
        assert operator_gate.is_operator_route(p, m)


def test_the_gate_is_mounted_inside_api_guard():
    from server import create_app
    names = [getattr(mw.kwargs.get("dispatch"), "__name__", "") for mw in create_app().user_middleware]
    assert "_operator_gate" in names and "_api_guard" in names
    assert names.index("_api_guard") < names.index("_operator_gate"), "api_guard must stay the outer one"


def test_a_cross_site_post_to_a_widget_is_refused():
    d = dict(peer="127.0.0.1", host="127.0.0.1:43917", token_given="", token_set="", cloud=False)
    assert not api_guard.decide(path="/widgets/contactos/action", method="POST", origin="https://evil.example",
                                fetch_site="cross-site", **d)[0]
    assert not api_guard.decide(path="/widgets/contactos/action", method="POST", origin="", fetch_site="",
                                **{**d, "host": "evil.example"})[0], "a rebound name"
    assert api_guard.decide(path="/widgets/contactos/action", method="POST", origin="http://127.0.0.1:43917",
                            fetch_site="same-origin", **d)[0]
    assert api_guard.decide(path="/widgets/contactos/data", method="GET", origin="", fetch_site="",
                            **{**d, "host": "evil.example"})[0], "reads outside /api/ are not this rule's (yet)"


def test_in_process_the_widget_route_still_answers():
    from fastapi.testclient import TestClient
    from server import create_app
    r = TestClient(create_app()).post("/widgets/no_such_widget/action", json={"action": "x", "payload": {}})
    assert r.status_code != 403, r.text
