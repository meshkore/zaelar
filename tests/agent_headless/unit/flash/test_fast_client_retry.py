#
# Retry on TRANSIENT model-client failures (fast_client, 2026-07-25).
# Run: .venv/bin/pytest tests/agent_headless/unit/flash/test_fast_client_retry.py -q
#
# A SINGLE connection blip (AIMLAPI behind Cloudflare) MUST NOT drop the turn — real symptom: the operator's chat
# was left without a response / with "Oops, it got away from me." Verifies: retries on transient failure and succeeds;
# does NOT retry on request error (4xx auth/input).
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
    """create() fails `fail_n` times with `exc`, then returns `_Resp(content)`."""
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
    monkeypatch.setattr(fc, "_RETRY_BACKOFF_S", 0.0)   # no wait in test


def _spec():
    return ModelSpec(model="m", base_url="https://api.aimlapi.com/v1", api_key="k", provider="aimlapi")


def test_complete_retries_transient_then_succeeds(monkeypatch):
    fake = _FakeClient(fail_n=2, exc=ConnectionError("Connection error."), content="hola")
    monkeypatch.setattr(FastClient, "_client_for", lambda self, spec: fake)
    out = asyncio.run(FastClient().complete([{"role": "user", "content": "hi"}], spec=_spec()))
    assert out == "hola"
    assert fake.calls == 3          # 2 failures + 1 success


def test_complete_gives_up_after_retries(monkeypatch):
    fake = _FakeClient(fail_n=99, exc=ConnectionError("Connection error."))
    monkeypatch.setattr(FastClient, "_client_for", lambda self, spec: fake)
    with pytest.raises(Exception):
        asyncio.run(FastClient().complete([{"role": "user", "content": "hi"}], spec=_spec()))
    assert fake.calls == 3          # initial attempt + 2 retries, then gives up


def test_complete_does_not_retry_request_error(monkeypatch):
    # a request 4xx (auth/input) is NOT retried (retrying will not fix it)
    err = type("BadRequest", (Exception,), {"status_code": 400})()
    fake = _FakeClient(fail_n=99, exc=err)
    monkeypatch.setattr(FastClient, "_client_for", lambda self, spec: fake)
    with pytest.raises(Exception):
        asyncio.run(FastClient().complete([{"role": "user", "content": "hi"}], spec=_spec()))
    assert fake.calls == 1          # no retries


def test_is_transient_classification():
    assert _is_transient(ConnectionError("Connection error."))
    assert _is_transient(TimeoutError("timed out"))
    assert _is_transient(type("E", (Exception,), {"status_code": 503})())
    assert not _is_transient(type("E", (Exception,), {"status_code": 400})())
    assert not _is_transient(ValueError("bad input schema"))


# ── the 429 BODY travels with the exception (2026-08-03) ────────────────────────────────────────────────────
# Without this, Z.AI's 429 (`_complete_zai`/`_stream_zai`, which use raw httpx rather than the OpenAI SDK) arrives as
# httpx's generic message ("429 Too Many Requests", with nothing else), and `nucleo.flash.provider_chain.classify_failure`
# (and its counterpart in `nucleo.workers.providers`) cannot distinguish an exhausted WEEKLY quota from a transient blip —
# both produce the SAME bare 429. Verified with the operator's real diagnostics on 2026-08-03.
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
    asyncio.run(fc._raise_with_body(resp))    # does not raise


def test_raise_with_body_is_a_coroutine_and_must_be_awaited():
    """Real bug (2026-08-09), discovered by Python's «coroutine never awaited» warning during the research director's first
    run: `_complete_zai` called `_raise_with_body(resp)` WITHOUT await. Without await it raises nothing — Python creates
    the coroutine object and discards it — so a 429/500 was treated as successful and the flow continued to
    `resp.json()` on an error body, turning a clear provider failure into a confusing parse error later (and, worse,
    without classifying the quota → without switching providers)."""
    import inspect
    from nucleo.flash import fast_client
    assert inspect.iscoroutinefunction(fast_client._raise_with_body)
    src = inspect.getsource(fast_client)
    for line in src.splitlines():
        s = line.strip()
        if "_raise_with_body(" in s and not s.startswith(("#", "async def", "def")):
            assert "await" in s, f"call without await will raise nothing: {s}"
