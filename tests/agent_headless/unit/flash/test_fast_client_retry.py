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


# ── el CUERPO del 429 viaja con la excepción (2026-08-03) ────────────────────────────────────────────────────
# Sin esto, el 429 de Z.AI (`_complete_zai`/`_stream_zai`, que hablan httpx crudo, no el SDK OpenAI) llega como el
# mensaje genérico de httpx («429 Too Many Requests», sin más) y `nucleo.flash.provider_chain.classify_failure`
# (y su hermano de `nucleo.workers.providers`) no puede distinguir cuota SEMANAL agotada de un blip pasajero — los
# dos dan el MISMO 429 desnudo. Verificado con el diagnóstico real del operador 2026-08-03.
class _FakeHttpxResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.reason_phrase = "Too Many Requests" if status_code == 429 else "Error"
        self._body = body
        self.request = None
    async def aread(self):
        pass
    @property
    def text(self):
        return self._body


def test_raise_with_body_embeds_the_response_text_for_exhaustion():
    from nucleo.workers.providers import classify_failure
    resp = _FakeHttpxResp(429, '{"error":{"message":"[1310][Weekly Limit Exhausted. reset at 2026-08-04]"}}')
    with pytest.raises(Exception) as ei:
        asyncio.run(fc._raise_with_body(resp))
    assert classify_failure(str(ei.value)) == "exhausted"


def test_raise_with_body_is_a_noop_on_success():
    resp = _FakeHttpxResp(200, "")
    asyncio.run(fc._raise_with_body(resp))    # no lanza


def test_raise_with_body_is_a_coroutine_and_must_be_awaited():
    """Bug real (2026-08-09), encontrado por el aviso de Python «coroutine never awaited» durante la primera corrida
    del director de investigación: en `_complete_zai` se llamaba `_raise_with_body(resp)` SIN await. Sin await no
    lanza nada —Python crea el objeto corrutina y lo descarta— así que un 429/500 pasaba por bueno y el flujo seguía
    hasta `resp.json()` sobre un cuerpo de error, convirtiendo un fallo de proveedor claro en un error de parseo
    confuso más adelante (y, peor, sin clasificar la cuota → sin relevo de proveedor)."""
    import inspect
    from nucleo.flash import fast_client
    assert inspect.iscoroutinefunction(fast_client._raise_with_body)
    src = inspect.getsource(fast_client)
    for line in src.splitlines():
        s = line.strip()
        if "_raise_with_body(" in s and not s.startswith(("#", "async def", "def")):
            assert "await" in s, f"llamada sin await, no lanzará nada: {s}"
