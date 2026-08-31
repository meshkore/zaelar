"""The triage's key comes from the SHARED endpoint map, and its failures say what actually happened.

Real cost, 2026-08-31. The operator's §triage pointed at `https://api.deepseek.com`. `triage_key()` carried its
own hand-rolled `if "x.ai" … elif "openai.com" …` chain — a FIFTH copy of the map `nucleo/provider_keys.py` was
created to end (its docstring names the four that had already diverged, and warns in as many words that an
unknown endpoint "resolves the key to ''/'local' and fails auth SILENTLY"). DeepSeek was not in that chain, so
every batch went out with the literal string `local` as its bearer token and came back:

    HTTP 401 · "Authentication Fails, Your api key: ****ocal is invalid"

And because the caller read `data["choices"]` straight off, the log said `triaje falló (deepseek-v4-flash):
'choices'` — for hours. The operator, reading a message that named neither the status nor the reason, went to
check whether he had burned through the credit he had topped up that morning. The engine held a perfectly good
`DEEPSEEK_API_KEY` the whole time.

Two rules, one per half:
  · **One list, everyone reads it.** A local re-implementation of the endpoint→key map is the bug, whatever it
    happens to contain today — a correct copy is one endpoint away from being a wrong one.
  · **If you have the answer, print it.** A 401 (the key), a 402 (the balance) and a 400 (the model) each need a
    DIFFERENT action from the operator, and the provider already says which one it is. Collapsing all three into
    a KeyError about our own parsing sends him to the wrong place.
"""
import aiohttp
import pytest

from connectors.messaging import config, triage


@pytest.fixture(autouse=True)
def _no_inline_key(monkeypatch):
    """The inline/env overrides win first and would mask what is under test."""
    monkeypatch.setattr(config, "_cfg", lambda k: "")
    monkeypatch.delenv("MSG_TRIAGE_KEY", raising=False)
    monkeypatch.delenv("WA_TRIAGE_KEY", raising=False)


# ── the key ───────────────────────────────────────────────────────────────────────────────────────────────
def test_the_key_comes_from_the_shared_endpoint_map(monkeypatch):
    """DeepSeek is the endpoint that actually broke, and it is in the shared map — it was never in this one."""
    monkeypatch.setattr(config, "triage_url", lambda: "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-real")
    assert config.triage_key() == "sk-real", \
        "sending `local` to a real provider is a 401 that looks like nothing — resolve the key for THIS endpoint"


def test_an_endpoint_the_map_does_not_know_still_falls_back_to_local():
    """Counterweight: Ollama needs any non-empty string, and the default must stay that sentinel — this must not
    become an exception on a local install that never had a key at all."""
    assert config.triage_key() == "local"


def test_every_endpoint_the_shared_map_knows_resolves_here_too(monkeypatch):
    """The point of the shared list: adding an endpoint THERE is enough. If this file grew its own copy again,
    a provider added to `provider_keys` would silently keep failing auth here."""
    from nucleo import provider_keys
    for needle, env_name in provider_keys._ENDPOINTS:
        monkeypatch.setenv(env_name, f"key-for-{env_name}")
        monkeypatch.setattr(config, "triage_url", lambda n=needle: f"https://api.{n}/v1")
        assert config.triage_key() == f"key-for-{env_name}", \
            f"{needle} is in the shared map but this triage cannot resolve its key"


# ── the message ───────────────────────────────────────────────────────────────────────────────────────────
class _FakeResponse:
    def __init__(self, status, payload):
        self.status, self._payload = status, payload

    async def json(self, **_):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, status, payload):
        self._status, self._payload = status, payload

    def post(self, *a, **k):
        return _FakeResponse(self._status, self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _classify_against(monkeypatch, status, payload):
    """Captures loguru's line directly — `caplog` is stdlib logging and never sees it, which would make every
    assertion below pass against an empty string."""
    said = []

    class _Rec:
        def warning(self, msg):
            said.append(str(msg))

        def __getattr__(self, _):
            return lambda *a, **k: None

    monkeypatch.setattr(triage, "logger", _Rec())
    monkeypatch.setattr(aiohttp, "ClientSession", lambda **k: _FakeSession(status, payload))
    import asyncio
    out = asyncio.run(triage.classify([{"body": "hola", "from": "Pablo"}]))
    return out, "\n".join(said)


def test_a_401_says_401_and_not_choices(monkeypatch):
    """The exact answer the operator's engine was getting, and the exact message that hid it."""
    payload = {"error": {"message": "Authentication Fails, Your api key: ****ocal is invalid",
                         "type": "authentication_error"}}
    _, log = _classify_against(monkeypatch, 401, payload)
    assert "401" in log, "the status is the first thing that tells him WHICH problem this is"
    assert "Authentication Fails" in log, "the provider already said why — pass it through"
    assert "'choices'" not in log, \
        "a KeyError about our own parsing points at the wrong system: he went to check his balance"


def test_a_402_reads_differently_from_a_401(monkeypatch):
    """The whole point: no balance, a bad key and a bad model need three different actions from him."""
    _, log = _classify_against(monkeypatch, 402, {"error": {"message": "Insufficient Balance"}})
    assert "402" in log and "Insufficient Balance" in log


def test_the_model_and_the_endpoint_are_named(monkeypatch):
    """`§triage` is configured separately from the voice chain, so «DeepSeek fails» is ambiguous while the
    FlashBrain is visibly answering on the same host. Name what THIS caller asked, and where."""
    _, log = _classify_against(monkeypatch, 400, {"error": {"message": "Model Not Exist"}})
    assert config.triage_model() in log and config.triage_url() in log


def test_a_provider_refusal_still_fails_OPEN_toward_the_operator(monkeypatch):
    """Counterweight, and it must never regress: a triage that cannot classify marks everything UNCERTAIN and
    shows it. Turning the clearer error into a raise that swallows the batch would silence real messages."""
    out, _ = _classify_against(monkeypatch, 401, {"error": {"message": "nope"}})
    assert len(out) == 1 and out[0]["importante"] is True, \
        "when unsure, show it — a message hidden by an infrastructure failure is the worst outcome"
