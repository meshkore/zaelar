#
# test_architect.py — el conector Architect sin daemon real: parsing de tags (protocolo compartido) y el ciclo
# de encargo completo (ask → poll → entrega) con un cliente falso. Ejecutar: .venv/bin/pytest connectors/architect/
#
import asyncio

import pytest

from voice import brain_notes
from voice.tag_protocol import strip_tags
from connectors.architect import service


# ── tags ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _collect(text: str, chunks: bool = False):
    got = []
    emit = lambda a, e: got.append((a, e))
    if not chunks:
        spoken, _ = strip_tags(text, emit, True)
        return got, spoken
    # stream en trozos pequeños, como llega del LLM: la tag partida debe retenerse y emitirse entera
    buf, spoken = "", []
    for i in range(0, len(text), 7):
        buf += text[i:i + 7]
        out, buf = strip_tags(buf, emit, False)
        spoken.append(out)
    out, _ = strip_tags(buf, emit, True)
    spoken.append(out)
    return got, "".join(spoken)


def test_architect_ask_tag_parses_and_is_silent():
    got, spoken = _collect("Voy a ello. [[architect.ask:meshkore-main]]¿Qué hay en el roadmap?[[/architect.ask]]")
    assert got == [("architect.ask", {"project": "meshkore-main", "request": "¿Qué hay en el roadmap?"})]
    assert "architect" not in spoken and spoken.strip() == "Voy a ello."


def test_architect_new_tag_parses_json():
    got, _ = _collect('[[architect.new]]{"name":"scraper","parent":"/tmp/prj"}[[/architect.new]]')
    assert got == [("architect.new", {"data": {"name": "scraper", "parent": "/tmp/prj"}})]


def test_architect_tag_split_across_chunks_never_leaks():
    got, spoken = _collect("Me pongo. [[architect.ask:ikamiro]]mejora el módulo de imágenes[[/architect.ask]]",
                           chunks=True)
    assert got == [("architect.ask", {"project": "ikamiro", "request": "mejora el módulo de imágenes"})]
    assert "[[" not in spoken


# ── service (cliente falso) ───────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def fast_polls(monkeypatch):
    monkeypatch.setenv("ARCHITECT_TOKEN", "test-token")
    monkeypatch.setattr(service, "_POLL_FAST", 0.01)
    monkeypatch.setattr(service, "_POLL_SLOW", 0.01)
    brain_notes.drain()                      # empieza con el buzón limpio
    yield
    brain_notes.drain()


def _silence_proactive(monkeypatch, spoken: list):
    from voice import proactive

    async def fake_notify(title, text, **kw):
        spoken.append((title, text))

    monkeypatch.setattr(proactive, "notify", fake_notify)


def test_ask_happy_path_delivers_note_and_voice(monkeypatch, fast_polls):
    from connectors.architect import client
    calls = {"polls": 0}

    async def fake_ask(project, text):
        assert (project, text) == ("zaelar", "estado del roadmap")
        return {"request_id": "r1", "conv": "c1"}

    async def fake_poll(project, rid):
        calls["polls"] += 1
        return {"status": "done", "result_text": "Roadmap: INI-010 en curso."} if calls["polls"] >= 2 \
            else {"status": "running"}

    monkeypatch.setattr(client, "ask", fake_ask)
    monkeypatch.setattr(client, "poll", fake_poll)
    spoken = []
    _silence_proactive(monkeypatch, spoken)

    asyncio.run(service.ask("zaelar", "estado del roadmap"))

    notes = brain_notes.drain()
    assert any("ha terminado" in n and "INI-010" in n for n in notes)
    assert spoken and spoken[0][0] == "Architect · zaelar" and "INI-010" in spoken[0][1]
    assert not service.inflight()            # el encargo se des-registra al acabar


def test_second_ask_to_same_project_is_rejected_not_queued(monkeypatch, fast_polls):
    from connectors.architect import client
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_ask(project, text):
        started.set()
        await release.wait()
        return {"request_id": "r1"}

    async def fake_poll(project, rid):
        return {"status": "done", "result_text": "ok"}

    monkeypatch.setattr(client, "ask", slow_ask)
    monkeypatch.setattr(client, "poll", fake_poll)
    _silence_proactive(monkeypatch, [])

    async def run():
        t = asyncio.create_task(service.ask("zaelar", "primero"))
        await started.wait()
        await service.ask("zaelar", "segundo")          # debe rebotar con nota, sin encolar
        notes = brain_notes.drain()
        assert any("YA tiene un encargo en curso" in n for n in notes)
        release.set()
        await t

    asyncio.run(run())


def test_ask_error_status_reports_failure(monkeypatch, fast_polls):
    from connectors.architect import client

    async def fake_ask(project, text):
        return {"request_id": "r1"}

    async def fake_poll(project, rid):
        return {"status": "error", "result_text": "boom"}

    monkeypatch.setattr(client, "ask", fake_ask)
    monkeypatch.setattr(client, "poll", fake_poll)
    spoken = []
    _silence_proactive(monkeypatch, spoken)

    asyncio.run(service.ask("zaelar", "algo"))
    notes = brain_notes.drain()
    assert any("ERROR" in n and "boom" in n for n in notes)


def test_ask_without_token_notes_missing_config(monkeypatch, fast_polls):
    monkeypatch.delenv("ARCHITECT_TOKEN", raising=False)
    asyncio.run(service.ask("zaelar", "algo"))
    assert any("ARCHITECT_TOKEN" in n for n in brain_notes.drain())


def test_new_project_requires_name_and_parent(monkeypatch, fast_polls):
    monkeypatch.delenv("ARCHITECT_PARENT", raising=False)
    _silence_proactive(monkeypatch, [])
    asyncio.run(service.new_project({"name": ""}))
    asyncio.run(service.new_project({"name": "demo"}))
    notes = brain_notes.drain()
    assert any('sin "name"' in n for n in notes)
    assert any("ARCHITECT_PARENT" in n for n in notes)


def test_brief_without_token_says_not_operational(monkeypatch):
    monkeypatch.delenv("ARCHITECT_TOKEN", raising=False)
    from connectors.architect import brief
    out = brief.for_brain()
    assert "SIN token" in out and "architect.ask" in out
