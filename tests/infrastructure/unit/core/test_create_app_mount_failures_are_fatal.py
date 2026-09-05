# A configured brain that fails to MOUNT kills the boot — it does not become one warning (V2-554 → V2-601 T-08).
#
# The incident this closes: `config/models.default.json` missing from the cloud image (V2-554) crashed the
# Colmena import chain inside create_app's old broad try/except — the app booted "green", /healthz answered 200,
# the release smoke passed, and the product shipped with no probe, no worker plane and no browser bridge, behind
# ONE warning line among hundreds of INFO. The two cases get opposite treatment now:
#   · brain deliberately NOT nucleo → the four routers are simply skipped (a baseline profile is a choice);
#   · brain IS nucleo and a mount fails → create_app RAISES, so the boot dies where the smoke can see it.
#
# Run: .venv/bin/pytest tests/infrastructure/unit/core/test_create_app_mount_failures_are_fatal.py -q
import asyncio
import sys

import httpx
import pytest


def _status(app, method: str, path: str) -> int:
    """Route presence is checked with a REQUEST, never by reading `app.routes` — that listing came back empty
    over perfectly mounted routes once already (V2-557: this FastAPI keeps them wrapped). ASGITransport runs no
    lifespan, so the engine itself never starts here."""
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return (await c.request(method, path)).status_code
    return asyncio.run(go())


def test_a_failed_router_mount_raises_instead_of_warning(monkeypatch):
    """Poisoning one of the four Colmena routers' modules must kill create_app, not degrade it."""
    import server
    monkeypatch.setenv("BRAIN", "nucleo")
    # `None` in sys.modules makes `from nucleo.flash.probe_api import router` raise ImportError — the same
    # shape as the real incident's failed import chain, without touching any file on disk.
    monkeypatch.setitem(sys.modules, "nucleo.flash.probe_api", None)
    with pytest.raises(ImportError):
        server.create_app()


def test_a_deliberate_non_nucleo_brain_still_boots_quietly(monkeypatch):
    """Counterweight: BRAIN=direct is a choice, not a fault — the app builds and the four routers are absent."""
    import server
    monkeypatch.setenv("BRAIN", "direct")
    monkeypatch.setitem(sys.modules, "nucleo.flash.probe_api", None)   # would raise IF the branch ran
    app = server.create_app()
    assert _status(app, "POST", "/api/flash/say") == 404


def test_with_nucleo_the_four_routers_actually_mount(monkeypatch):
    """The positive half: the four surfaces the old swallow used to lose are really there under nucleo."""
    import server
    monkeypatch.setenv("BRAIN", "nucleo")
    app = server.create_app()
    for method, path in (("POST", "/api/flash/say"), ("POST", "/api/agent/report"),
                         ("POST", "/api/worker/act"), ("POST", "/api/navegador/act")):
        assert _status(app, method, path) != 404, f"router for {path} not mounted"
