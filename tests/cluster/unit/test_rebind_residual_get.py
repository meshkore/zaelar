# A DNS-rebound page cannot read the cluster control plane with a SAME-origin GET (V2-601 T-14, audit C-2).
#
# The guard's Origin check is right and stays — but a same-origin fetch from a REBOUND page (attacker domain
# re-resolved to 127.0.0.1) sends NO Origin header at all, so it sailed past: the request arrives from loopback,
# originless, and /api/meshkore/status disclosed clusters + peer handles + engagement to a page the operator
# merely visited. What betrays the rebind is the Host header: the browser still names the site it THINKS it is
# on. Exact hostname match against the loopback names (plus local.zaelar.com, pinned to 127.0.0.1 by design).
#
# Run: .venv/bin/pytest tests/cluster/unit/test_rebind_residual_get.py -q
import asyncio

import httpx
import pytest
from fastapi import FastAPI

from connectors.meshkore.server_api import router


def _get(path: str, host: str, origin: str | None = None) -> int:
    app = FastAPI()
    app.include_router(router)

    async def go():
        headers = {"host": host}
        if origin is not None:
            headers["origin"] = origin
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 5555)),
                                     base_url="http://placeholder") as c:
            return (await c.get(path, headers=headers)).status_code
    return asyncio.run(go())


def test_a_rebound_host_is_refused_even_with_no_origin(monkeypatch):
    monkeypatch.delenv("MESHKORE_API_TOKEN", raising=False)
    assert _get("/api/meshkore/status", host="evil.example:43917") == 403


def test_a_single_label_attacker_host_is_refused_too(monkeypatch):
    monkeypatch.delenv("MESHKORE_API_TOKEN", raising=False)
    assert _get("/api/meshkore/status", host="testserver") == 403


@pytest.mark.parametrize("host", ["localhost:43917", "127.0.0.1:43917", "local.zaelar.com:44317", "[::1]:43917"])
def test_the_legitimate_loopback_names_still_pass(monkeypatch, host):
    """Counterweight: the frontend (both origins) and the internal bridges keep working — the route answers,
    whatever its payload, instead of 403."""
    monkeypatch.delenv("MESHKORE_API_TOKEN", raising=False)
    assert _get("/api/meshkore/status", host=host) != 403


def test_origin_check_still_bites_when_origin_is_present(monkeypatch):
    """The old defense is not traded away: a cross-origin browser call with a loopback Host still loses."""
    monkeypatch.delenv("MESHKORE_API_TOKEN", raising=False)
    assert _get("/api/meshkore/status", host="localhost:43917", origin="http://localhost.attacker.com") == 403
