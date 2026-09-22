#
# test_one_headline_and_one_stand_in.py — V2-750. The model table says ONE titular and ONE stand-in, and the
# stand-in has to be a real second door: a different provider, and never OpenAI in the first seat.
#
# WHAT WAS WRONG (measured 2026-09-22, his own engine). The panel read «deepseek-v4-pro · DeepSeek · no
# responde» while DeepSeek, probed in that same minute, answered `/models` 200, reported a $2.77 balance and
# completed a chat in 1.22 s. Two separate faults met there:
#
#   1. `voice_brain.failover` was `null`, documented as a KNOWN RISK awaiting an operator decision. So a real
#      DeepSeek outage takes the voice brain, the brief composer, the triage and the susurro with it.
#   2. The chain that was supposed to relay named ONE tier and it pointed at `api.deepseek.com` — the same
#      host as the titular. A stand-in that shares a provider is a second door into the same outage.
#
# The operator's rules, verbatim (2026-09-22): «solo quiero un modelo principal o una API principal y un
# failover», «yo prefiero que vayas siempre por proveedores nativos… hay más posibilidades de que se caiga
# IML que que se caiga el proveedor original», and «OpenAI siempre tiene que ser failover: tenemos modelos
# baratos como titulares, los más potentes a nuestra disposición».
#
from urllib.parse import urlparse

import pytest

from config import models

#: The ONE row the «OpenAI is never a titular» rule cannot reach, and why. An embedding model DEFINES the
#: vector space every stored pill lives in, so swapping it does not change a provider — it invalidates the
#: memory. Moving it is a migration (re-embed, then switch), never a config edit. Declared here so the
#: exception is a decision somebody wrote down, not a test that quietly skips a row.
_EMBEDDING_EXCEPTION = "embeddings"


def _services() -> dict:
    return models.services()


def test_no_service_has_more_than_one_stand_in():
    """«Solo quiero un modelo principal y un failover». The reader enforces it; this asserts the FILE, so a
    third rung cannot be smuggled in as a list."""
    for name, svc in _services().items():
        f = svc.get("failover")
        assert not isinstance(f, list), f"{name}: failover is a LIST — the rule is one, and one is not a list"
        assert len(models.rungs(name)) <= 2, f"{name}: {len(models.rungs(name))} rungs"


@pytest.mark.parametrize("name", sorted(_services()))
def test_a_stand_in_never_shares_a_provider_with_its_titular(name):
    """The fault that made the ladder decorative. Compared by HOST, because the provider FIELD can say the
    same thing about two different companies: `brain_worker` runs both rungs through the Claude Code CLI
    (provider `claude_code`) while the endpoints are z.ai and DeepSeek — that is a real second door."""
    svc = _services()[name]
    t, f = svc.get("titular") or {}, svc.get("failover") or {}
    if not f:
        return
    ht, hf = urlparse(t.get("base_url") or "").netloc, urlparse(f.get("base_url") or "").netloc
    if not ht or not hf:
        return                      # STT/TTS rows name a vendor, not an endpoint
    assert ht != hf, f"{name}: titular and stand-in both live at {ht} — one outage takes both"


def test_openai_is_never_a_titular():
    """Operator, 2026-09-22 — and it REVERSES his own 2026-09-10 directive that put OpenAI at the head of the
    memory services. The newer rule is general and wins: cheap models lead, the expensive one stands by."""
    offenders = [n for n, s in _services().items()
                 if (s.get("titular") or {}).get("provider") == "openai" and n != _EMBEDDING_EXCEPTION]
    assert not offenders, f"OpenAI is heading {offenders} — it may only ever be the stand-in"


def test_the_embedding_exception_is_declared_rather_than_silent():
    """A test that skips a row without saying so is how an exception becomes a hole. The row has to carry its
    own reason, in the file everyone reads."""
    why = (_services()[_EMBEDDING_EXCEPTION].get("why") or "")
    assert "vector space" in why or "espacio vectorial" in why, \
        "the embeddings row must SAY why the rule cannot reach it — a migration, not a config edit"


def test_the_voice_brain_has_a_stand_in_at_all():
    """The specific hole the operator hit: `failover: null` on the row that answers him."""
    f = models.failover("voice_brain")
    assert f and f.get("provider"), "the voice brain with no stand-in is the whole outage, measured 2026-09-22"


def test_the_voice_titular_is_a_model_the_api_actually_lists():
    """⚠️ AN ANNOUNCEMENT IS NOT A MODEL, and this repo has now paid that twice. Probed 2026-09-22 against
    the real endpoint: `deepseek-v4.1-flash` and `deepseek-v4.1` both answer 400 with «The supported API
    model names are deepseek-flash, deepseek-v4-pro». Any id outside that set is a rung that 400s on its
    first real turn — the same shape as the Groq rung whose model had silently stopped existing."""
    listed = {"deepseek-flash", "deepseek-v4-pro"}
    for name, svc in _services().items():
        for seat in ("titular", "failover"):
            row = svc.get(seat) or {}
            if (row.get("provider") or "") != "deepseek":
                continue
            assert row.get("model") in listed, \
                f"{name}.{seat}: «{row.get('model')}» is not a name api.deepseek.com serves ({sorted(listed)})"


def test_a_retired_provider_has_not_crept_back_in():
    """xAI (403, credits gone) and Groq (404, the model stopped existing) were retired on measurement and
    re-measured dead on 2026-09-22. A rung with an expired name is worse than no rung."""
    dead = set(models.retired())
    for name, svc in _services().items():
        for seat in ("titular", "failover"):
            p = ((svc.get(seat) or {}).get("provider") or "")
            assert p not in dead, f"{name}.{seat} points at «{p}», which is in the retired list"


# ── AND THE WIRING, which is the half that failed in silence ──────────────────────────────────────────
def test_the_voice_chain_actually_CARRIES_the_stand_in(monkeypatch):
    """The table saying `failover` is not the same as the engine having one. Before V2-750 the voice chain
    named its own hardcoded tier and ignored this file entirely — two documents, and the wrong one was the
    code. The ONLY symptom was a bill that did not fall and an agent that went mute instead of relaying."""
    import os
    from config import credentials as C
    from nucleo.flash import provider_chain as pc
    for env in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(env, C.get(env) or "test-key-for-the-chain")
    names = [t.get("base_url") for t in pc.chain(pc.ROLE_VOICE)]
    assert len(names) >= 2, f"the voice chain has no stand-in: {names}"
    assert any("openai" in (u or "") for u in names), \
        f"the stand-in the table declares never reached the chain: {names}"


def test_a_rung_whose_key_is_missing_is_not_in_the_chain(monkeypatch):
    """«Sin credencial no es un escalón, es un espejismo» — and it is what replaced the old cloud-account
    gate. A self-hoster with no OpenAI key must never be moved onto a provider he did not set up; the honest
    test of that is whether the key is there, not who is running the engine."""
    import os
    from config import credentials as C
    from nucleo.flash import provider_chain as pc
    monkeypatch.setenv("DEEPSEEK_API_KEY", C.get("DEEPSEEK_API_KEY") or "test-key-for-the-chain")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    names = [t.get("base_url") for t in pc.chain(pc.ROLE_VOICE)]
    assert not any("openai" in (u or "") for u in names), \
        f"a rung with no credential is in the chain: {names}"
