"""A Machine says what it RUNS, and the image decides it: the versions ride with every lease renewal, and the `claude`
CLI the brain workers drive is pinned in the image and never updates itself there.

Measured 2026-11-04: a cloud Machine on an image built 2026-11-01 ran Claude Code 2.1.197 while 2.1.318 was current.
The Dockerfile installed it unpinned, so the builder's layer cache froze it at the version it first resolved, and no
record anywhere said which version each Machine ran.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

import version
from nucleo.energy import lease as energy_lease

DOCKERFILE = Path(__file__).resolve().parents[4] / "Dockerfile"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    energy_lease._reset_for_tests()
    monkeypatch.setattr(energy_lease, "_persist", lambda: None)
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    yield
    energy_lease._reset_for_tests()


def test_a_lease_renewal_carries_the_versions(monkeypatch):
    import httpx
    sent = {}

    class _R:
        status_code = 200
        def json(self): return {"ok": True, "lease_id": "L1", "energy": 10, "ttl_s": 1800, "balance": 50}

    class _C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            sent.update(json or {})
            return _R()

    monkeypatch.setattr(httpx, "AsyncClient", _C)
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://cp.example.test")
    monkeypatch.setattr(version, "_COMPONENTS", {"engine": "3.45", "build": 99, "claude_code": "2.1.318"})
    assert asyncio.run(energy_lease.ensure(reason="boot", force=True))
    assert sent["versions"]["claude_code"] == "2.1.318" and sent["versions"]["build"] == 99


def test_the_components_name_every_part_and_read_a_tool_once(monkeypatch):
    asked = []
    monkeypatch.setattr(version, "_COMPONENTS", {})
    monkeypatch.setattr(version, "_tool_version", lambda cmd: asked.append(cmd[0]) or "1.2.3")
    monkeypatch.setenv("FLY_IMAGE_REF", "registry.fly.io/app:deployment-X")
    c = version.components()
    assert {"engine", "build", "commit", "claude_code", "node", "playwright", "image"} <= set(c)
    assert c["claude_code"] == "1.2.3" and c["image"] == "registry.fly.io/app:deployment-X"
    version.components()
    assert sorted(asked) == ["claude", "node"], "read once per process"


def test_a_missing_tool_is_unknown_not_an_error():
    assert version._tool_version(["a-tool-that-does-not-exist-zaelar"]) == "unknown"


def test_the_image_pins_the_cli_and_turns_its_updater_off():
    text = DOCKERFILE.read_text(encoding="utf-8")
    pin = re.search(r"^ARG CLAUDE_CODE_VERSION=(\d+\.\d+\.\d+)$", text, re.M)
    assert pin, "the CLI version is an ARG with an exact version"
    assert "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" in text, "the install uses the pin"
    assert not re.search(r"npm install -g @anthropic-ai/claude-code(\s|\\\\|$)", text), "no unpinned install left"
    assert re.search(r"^ENV DISABLE_AUTOUPDATER=1$", text, re.M)
