"""A config save is judged by what it LEAVES, not by what it carries (2026-09-11, V2-673).

Found on the operator's LIVE engine while verifying something else: `config/v2.json` held

    {"fast": {"provider": "aimlapi"}}

— one key, nothing else. The effective config was therefore `provider: aimlapi` with
`model: deepseek-v4-pro` and `base_url: https://api.deepseek.com`: a provider from one vendor, an endpoint
from another, and a model string AIMLAPI does not serve (it serves `deepseek/deepseek-v4-pro`). Observability
would have printed one name while the traffic went somewhere else — the V2-657 defect, arriving by a
different road. It also made the broker the TITULAR of the voice brain, which the model table's rule 3
forbids outright.

`server/config_api._model_mismatch()` exists to stop exactly this and let it through, because it compared
`patch["provider"]` against `patch["model"]`: a patch carrying ONLY a provider has no model IN IT to compare.
And a partial write is the NORMAL shape of a config edit, so the check was blind to the common case rather
than to an exotic one.

⚠️ Who sent that patch is NOT established. The only writer in the engine is `POST /api/config/v2`, both
frontend call sites send the whole section, and no `config.save` UI event was recorded in the window. What is
established is the SHAPE of what landed, and that the validator could not see it — which is what is fixed
here. A guard that reads the REQUEST instead of the resulting STATE is the general fault.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A real router over an ISOLATED store — this test must never touch the operator's own routing."""
    from config import v2
    monkeypatch.setattr(v2, "_PATH", tmp_path / "v2.json")
    from server.config_api import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _fast(api):
    from config import v2
    return v2.get("fast")


def test_a_provider_swapped_ALONE_is_refused(api):
    """The exact corruption found live. It carries no model, so the old check had nothing to compare."""
    r = api.post("/api/config/v2", json={"section": "fast", "patch": {"provider": "aimlapi"}})
    assert r.status_code == 400, r.json()
    assert "not served by" in r.json()["error"]
    assert _fast(api)["provider"] == "deepseek", "a refused save must change nothing"


def test_a_provider_swapped_WITH_its_model_and_endpoint_is_accepted(api):
    """The guard validates, it does not lock in: a coherent change still goes through."""
    r = api.post("/api/config/v2", json={"section": "fast", "patch": {
        "provider": "aimlapi", "model": "deepseek/deepseek-v4-pro",
        "base_url": "https://api.aimlapi.com/v1"}})
    assert r.status_code == 200, r.json()
    assert _fast(api)["provider"] == "aimlapi"


def test_an_endpoint_left_behind_is_refused_by_name(api):
    """A provider changed without its `base_url` prints one vendor's name over another's traffic — silent,
    and expensive to diagnose. The refusal says which endpoint was expected."""
    r = api.post("/api/config/v2", json={"section": "fast", "patch": {
        "provider": "aimlapi", "model": "deepseek/deepseek-v4-pro"}})
    assert r.status_code == 400
    assert "api.aimlapi.com" in r.json()["error"], r.json()["error"]


def test_a_model_saved_alone_is_still_checked_against_the_STANDING_provider(api):
    """The mirror image of the first case, and the old check missed it for the same reason: with no provider
    in the patch it returned early, so a model from another vendor could be written under the current one."""
    r = api.post("/api/config/v2", json={"section": "fast", "patch": {"model": "qwen2.5:14b-instruct"}})
    assert r.status_code == 400, r.json()
    assert "not served by" in r.json()["error"]


def test_a_save_that_changes_nothing_relevant_still_works(api):
    """The guard must not turn every unrelated edit into a refusal."""
    r = api.post("/api/config/v2", json={"section": "flags", "patch": {"brain": "nucleo"}})
    assert r.status_code == 200, r.json()


def test_an_unreadable_store_does_not_block_a_save(monkeypatch):
    """Fail-soft in the direction that keeps the panel usable: validate the PATCH alone rather than refuse
    every save because the store could not be read. Asserted on the validator directly — patching `v2.get`
    through the HTTP route would break `set()` too, and then the test would be measuring the wrong failure."""
    from config import v2
    from server.config_api import _model_mismatch
    monkeypatch.setattr(v2, "get", lambda section: (_ for _ in ()).throw(RuntimeError("boom")))
    assert _model_mismatch("fast", {"provider": "deepseek", "model": "deepseek-v4-pro",
                                    "base_url": "https://api.deepseek.com"}) == ""
    assert "not served by" in _model_mismatch("fast", {"provider": "aimlapi", "model": "deepseek-v4-pro"})
