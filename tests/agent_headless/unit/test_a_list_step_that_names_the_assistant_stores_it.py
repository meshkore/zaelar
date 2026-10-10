"""A list step that names the assistant leaves the name STORED, or the list does not count it (V2-781).

Measured on `demo-initialization__es` (2026-10-10 20:08): the INIT's first section ran as one step —
«Te llamas Johnny. Cuando diga «Johnny», te estoy hablando a ti. Actúa como mi asistente…» — the model answered
as Johnny, `state.assistant_name` stayed «Zaelar», and the list closed «28 de 28». The rename lane read the
whole step as one sentence and extracted «Johnny. Cuando diga «Johnny»», which is not a name.
"""
import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from nucleo.batch import identity, runner

ES = ("Te llamas Johnny. Cuando diga «Johnny», te estoy hablando a ti. Actúa como mi asistente digital personal. "
      "Usa lo que ya sabes de mí cuando venga al caso en vez de pedirme que lo repita.")
EN = ("Your name is Johnny. When I say “Johnny”, I am talking to you. Act as my personal digital assistant. "
      "Use information you already know about me when it is relevant instead of asking me to repeat it.")


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    mememb.reset(); memdb.reset_db(); memdb.get_db()
    monkeypatch.setattr(runner, "_SETTLE_S", 0.0)
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "done")
    yield
    memdb.reset_db(); mememb.reset()


def _run(steps):
    async def turn(text, **kw):
        return {"ok": True, "reply": ["Entendido, soy Johnny."]}      # the model plays the part, writes nothing

    async def ingest(text):
        await asyncio.sleep(0)

    async def notify(title, text):
        pass
    uid = runner.create("msg", steps, origin="chat")
    asyncio.run(runner.run(uid, turn=turn, ingest=ingest, notify=notify, worker_wait_s=0.1))
    return runner.summary(uid)


@pytest.mark.parametrize("say", [ES, EN])
def test_the_measured_identity_step_stores_the_name(say):
    s = _run([{"title": "identidad", "kind": "identity", "say": say}])
    assert (memapi.state().get("assistant_name") or "").lower() == "johnny"
    assert len(s["done"]) == 1 and not s["failed"]


@pytest.mark.parametrize("say", [ES, EN])
def test_the_name_is_read_from_its_own_sentence(say):
    assert identity.named_in(say) == "Johnny"


def test_a_step_that_does_not_name_the_assistant_is_left_alone():
    assert identity.named_in("Recuerda: mi perro se llama Pixel. ¿Cómo te llamas?") is None
    s = _run([{"title": "perfil", "kind": "memory", "say": "Recuerda: me llamo Rowan y vivo en Valencia."}])
    assert (memapi.state().get("assistant_name") or "") != "Rowan"
    assert len(s["done"]) == 1


def test_a_name_that_could_not_be_stored_fails_the_step(monkeypatch):
    """«N of N» never counts the step whose point did not happen."""
    async def _broken(name):
        raise RuntimeError("disk full")
    from nucleo.flash import identity_actions
    monkeypatch.setattr(identity_actions, "persist_rename", _broken)
    s = _run([{"title": "identidad", "kind": "identity", "say": EN},
              {"title": "perfil", "kind": "memory", "say": "Remember: I live in Los Angeles."}])
    assert [r["title"] for r in s["failed"]] == ["identidad"]
    assert len(s["done"]) == 1
