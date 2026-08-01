#
# Reintento en TRANSITORIOS del cliente del modelo (fast_client, 2026-07-25).
# Run: .venv/bin/pytest tests/agent_headless/unit/flash/test_fast_client_retry.py -q
#
# Un blip PUNTUAL de conexión (AIMLAPI tras Cloudflare) NO debe tirar el turno — síntoma real: el chat del operador
# se quedaba sin respuesta / con "Uf, se me ha ido". Verifica: reintenta en transitorio y acierta; NO reintenta en
# error de petición (4xx auth/entrada).
#
import asyncio

import pytest

from nucleo.flash import fast_client as fc
from nucleo.flash.fast_client import FastClient, ModelSpec, _is_transient


class _Msg:
    def __init__(self, content): self.message = type("M", (), {"content": content})


class _Resp:
    def __init__(self, content): self.choices = [_Msg(content)]


class _FakeClient:
    """create() falla `fail_n` veces con `exc`, luego devuelve `_Resp(content)`."""
    def __init__(self, fail_n, exc, content="ok"):
        self.fail_n = fail_n; self.exc = exc; self.content = content; self.calls = 0
        self.chat = type("C", (), {"completions": self})()
    async def create(self, **kw):
        self.calls += 1
        if self.calls <= self.fail_n:
            raise self.exc
        return _Resp(self.content)


@pytest.fixture(autouse=True)
def _fast_retry(monkeypatch):
    monkeypatch.setattr(fc, "_CONNECT_RETRIES", 2)
    monkeypatch.setattr(fc, "_RETRY_BACKOFF_S", 0.0)   # sin espera en test


def _spec():
    return ModelSpec(model="m", base_url="https://api.aimlapi.com/v1", api_key="k", provider="aimlapi")


def test_complete_retries_transient_then_succeeds(monkeypatch):
    fake = _FakeClient(fail_n=2, exc=ConnectionError("Connection error."), content="hola")
    monkeypatch.setattr(FastClient, "_client_for", lambda self, spec: fake)
    out = asyncio.run(FastClient().complete([{"role": "user", "content": "hi"}], spec=_spec()))
    assert out == "hola"
    assert fake.calls == 3          # 2 fallos + 1 éxito


def test_complete_gives_up_after_retries(monkeypatch):
    fake = _FakeClient(fail_n=99, exc=ConnectionError("Connection error."))
    monkeypatch.setattr(FastClient, "_client_for", lambda self, spec: fake)
    with pytest.raises(Exception):
        asyncio.run(FastClient().complete([{"role": "user", "content": "hi"}], spec=_spec()))
    assert fake.calls == 3          # intento inicial + 2 reintentos, luego se rinde


def test_complete_does_not_retry_request_error(monkeypatch):
    # un 4xx de petición (auth/entrada) NO se reintenta (reintentar no lo arregla)
    err = type("BadRequest", (Exception,), {"status_code": 400})()
    fake = _FakeClient(fail_n=99, exc=err)
    monkeypatch.setattr(FastClient, "_client_for", lambda self, spec: fake)
    with pytest.raises(Exception):
        asyncio.run(FastClient().complete([{"role": "user", "content": "hi"}], spec=_spec()))
    assert fake.calls == 1          # sin reintentos


def test_is_transient_classification():
    assert _is_transient(ConnectionError("Connection error."))
    assert _is_transient(TimeoutError("timed out"))
    assert _is_transient(type("E", (Exception,), {"status_code": 503})())
    assert not _is_transient(type("E", (Exception,), {"status_code": 400})())
    assert not _is_transient(ValueError("bad input schema"))
