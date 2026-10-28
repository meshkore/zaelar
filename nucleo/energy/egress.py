# MODEL EGRESS — where an LLM call actually goes and with which credential.
#
# ONE CODEBASE, TWO DEPLOYMENTS. A self-hosted deployment talks to providers directly using
# ITS own keys: it is its account, its expense, and its decision, and this module changes nothing for it. In a
# managed deployment, egress is mediated, and this module is the seam where that happens — a
# PORT, not a special case scattered across ten files.
#
# What is described here is the MECHANISM: if the environment declares mediated egress, it is used; otherwise, it
# talks directly. The policy explaining why a deployment chooses one or the other does not live in this repo.
#
# THE INVERSION THAT MATTERS. Without this, each call site chose an endpoint AND carried the credential. With this,
# the call site declares what it WANTS (a model), and egress decides WHERE it goes. As long as a process
# can name the endpoint and has the key, the key has to be on its side — which is exactly what
# we want to stop doing.
#
# FAIL-CLOSED, BY DESIGN. If the deployment declares mediated egress and the credential needed to
# use it is missing, this does NOT fall back to talking directly to the provider. A silent fallback
# would turn an incomplete deployment into a working leak — the same
# “guarded-until-configured” pattern that left an exposed surface open for nine days. It prefers to break and say so.
#
from __future__ import annotations

import os

from loguru import logger

# The mediated endpoint and the credential with which this process identifies itself to it.
_URL_ENV = "ZAELAR_GATEWAY_URL"
_TOKEN_ENV = "CONTROL_PLANE_SERVICE_TOKEN"

# Provider base_url → short name understood by mediated egress. It is a ROUTING MAP, not a
# credential: it says “this call was intended for this family,” and whoever has the key decides.
# The FAMILY a base_url belongs to. A host missing from this table is not a small gap: `provider_of` returns "",
# `_headers` then sends NO `X-Zaelar-Provider`, and mediated egress falls back to ITS default — so the call is
# billed to, and answered by, a provider nobody chose.
#
# Example: with `deepseek.com` absent from this table while FAST_BASE_URL=https://api.deepseek.com, every voice
# turn silently went to the gateway's default provider instead — and when that one had run out of funds the user
# was told there were no credits, although the DeepSeek account had balance. Nothing was red: the header is optional by design, so its absence is indistinguishable
# from "no preference". `test_llm_egress_names_every_provider_it_ships_with` now pins this against the shipped
# allocation table so the two cannot drift apart again.
_PROVIDER_BY_HOST = (
    ("deepseek.com", "deepseek"),
    ("aimlapi.com", "aimlapi"),
    ("api.x.ai", "xai"),
    ("api.z.ai", "zai"),
    ("mistral.ai", "mistral"),
    # 2026-09-10 — the memory services' titular moved to OpenAI DIRECT (operator directive, see the table's
    # memory_writer/memory_rem rows): without this entry the `X-Zaelar-Provider` header goes out EMPTY on every
    # mediated memory write and the gateway falls back to its own default provider.
    ("api.openai.com", "openai"),
    # V2-809 — the chat's image reader (`image_reader` in the model table) speaks Gemini's OpenAI-compatible API.
    ("generativelanguage.googleapis.com", "gemini"),
)


# A client that names itself. Mediated egress sits behind an edge that refuses the default `Python-urllib/x.y`
# agent (Cloudflare error 1010, measured 2026-10-24): every urllib call through it — the decision model, the
# embeddings — came back 403 while the httpx-based calls went through. Any call site that builds its own urllib
# request toward egress sends this.
USER_AGENT = "zaelar-engine"


def post_json(url: str, key: str, body: bytes, timeout_s: float) -> dict:
    """POST JSON bytes with a bearer key under this engine's own client name; the decoded JSON answer."""
    import json
    import urllib.request
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def mediated() -> bool:
    """Does this deployment send calls through mediated egress?"""
    from nucleo.energy import account as cloud_account
    return cloud_account.is_cloud_account() and bool((os.getenv(_URL_ENV) or "").strip())


def is_local_endpoint(base_url: str) -> bool:
    u = (base_url or "").lower()
    return "11434" in u or "localhost" in u or "127.0.0.1" in u


def provider_of(base_url: str) -> str:
    u = (base_url or "").lower()
    for needle, name in _PROVIDER_BY_HOST:
        if needle in u:
            return name
    return ""


def route(base_url: str, api_key: str) -> tuple[str, str, dict]:
    """Effective `(base_url, api_key, headers_extra)` for this call.

    Without mediated egress, returns exactly what it was given — self-host remains byte-identical. A LOCAL endpoint
    (Ollama) is also never touched: it costs no money and there is nothing to mediate.

    THE LEASE GATE. Every hosted-model call resolves its destination here, which makes this the door where a
    machine that holds no energy lease is told no BEFORE the request leaves (`energy_lease.admit` raises
    `OutOfEnergy`; always admits without a cloud account).
    """
    if is_local_endpoint(base_url):
        return base_url, api_key, {}
    from nucleo.energy import lease as energy_lease
    energy_lease.admit("llm")
    if not mediated():
        return base_url, api_key, {}

    token = (os.getenv(_TOKEN_ENV) or "").strip()
    if not token:
        # See the fail-closed note in the header. Warn loudly and return the mediated destination
        # WITHOUT a credential: the call will fail with 401 at egress, which is a visible and contained failure,
        # instead of escaping through the back door with the provider key.
        logger.error(
            f"llm_egress: egress mediado declarado pero sin {_TOKEN_ENV} — la llamada fallará. "
            "NO se cae hacia atrás a hablar directo con el proveedor: eso convertiría un despliegue "
            "incompleto en una fuga que funciona."
        )
    # The SDK composes `<base>/chat/completions`, so the base must end where the provider's did:
    # in `/v1`. Without this, the call goes to `<egress>/chat/completions` and egress returns
    # 404 — which is how it broke on the first real startup, and the symptom (“prewarm skipped”) did not
    # point to the cause at all.
    base = (os.getenv(_URL_ENV) or "").strip().rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base, token, _headers(base_url)


def _headers(base_url: str) -> dict:
    """The family the call was intended for. It goes in a header and NOT in the body so that
    egress can route without opening the JSON, and because the model composes the body — we do not want
    something a model writes to be able to change which provider is billed."""
    p = provider_of(base_url)
    return {"X-Zaelar-Provider": p} if p else {}


# ── WHICH TASK A WORKER CALL SERVES ─────────────────────────────────────────────────────────────────────────
# A Brain Worker re-reads its whole context on every step, so one errand is many calls. When those calls go
# through mediated egress, the worker names the task it serves in `X-Zaelar-Task` (the CLI sends
# `ANTHROPIC_CUSTOM_HEADERS` on every request), and egress can add the usage up per task. Talking to a provider
# directly, nothing is sent: the header is for egress and no provider needs to see it.
def _a_plain_token(task_id: str) -> bool:
    """1-80 characters, letters/digits and `_.:-` only — what can ride a header unescaped."""
    t = task_id or ""
    return 0 < len(t) <= 80 and all(c.isalnum() or c in "_.:-" for c in t)


def task_header_env(base_url: str, task_id: str) -> dict:
    """`{"ANTHROPIC_CUSTOM_HEADERS": "X-Zaelar-Task: <id>"}` when `base_url` is mediated egress and the id is a
    plain token; `{}` otherwise. Pure apart from reading where egress is."""
    egress = root()
    if not egress or not (base_url or "").startswith(egress) or not _a_plain_token(task_id):
        return {}
    return {"ANTHROPIC_CUSTOM_HEADERS": f"X-Zaelar-Task: {task_id}"}


# ── EVERY PAID CALL, NOT JUST CHAT (2026-10-23) ─────────────────────────────────────────────────────────────
# `route()` covers the OpenAI-shaped chat calls. Embeddings, search, the triage model and the Brain Worker's
# Anthropic-shaped endpoint spoke to their providers directly, with a provider key read from the environment —
# in the one process where the code a user asked for also runs. Mediated egress now carries them through ONE
# convention: `<egress>/p/<family>/<the provider's own path>`. Egress keeps a closed list of paths per family;
# the call site keeps its provider's URL and hands it to `route_url`.
#
# The families egress can carry, by the base each provider's own SDK or call site already uses. LONGEST FIRST:
# `api.deepseek.com/anthropic` must win over `api.deepseek.com`.
_UPSTREAMS: tuple[tuple[str, str], ...] = (
    ("zai_anthropic", "https://api.z.ai/api/anthropic"),
    ("deepseek_anthropic", "https://api.deepseek.com/anthropic"),
    ("zai", "https://api.z.ai/api/paas/v4"),
    ("openai", "https://api.openai.com/v1"),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta"),
    ("xai", "https://api.x.ai/v1"),
    ("deepseek", "https://api.deepseek.com"),
    # Voice: the streaming sockets go through egress too (it opens its own socket to the provider with the key).
    ("deepgram", "https://api.deepgram.com/v1"),
    ("elevenlabs", "https://api.elevenlabs.io/v1"),
    ("inworld", "https://api.inworld.ai"),
    # The decision model. Without it a mediated deployment had no key and no route, so `jev.enabled()` was False on
    # every turn and no verdict ever reached the guards that are meant to read one.
    ("typesafe", "https://api.typesafe.ai"),
)

#: The provider keys this process's own egress credential STANDS IN FOR (see `stand_in_for_provider_keys`): the
#: key of every endpoint (`provider_keys`) whose host is one egress carries. Only those: a key whose calls egress
#: cannot route is left alone, because standing in for it would break the feature, not protect the key.
from nucleo.energy.keys import _ENDPOINTS as _KEYS_BY_ENDPOINT  # noqa: E402

_STANDS_IN_FOR: tuple[str, ...] = tuple(dict.fromkeys(
    env for needle, env in _KEYS_BY_ENDPOINT if any(needle in base for _name, base in _UPSTREAMS)))


def root() -> str:
    """Egress's own address, without the OpenAI-compatible `/v1` the chat SDKs compose on."""
    gateway = (os.getenv(_URL_ENV) or "").strip().rstrip("/")
    return gateway[:-3] if gateway.endswith("/v1") else gateway


def credential() -> str:
    """This process's egress credential — the account's own, never a provider's."""
    return (os.getenv(_TOKEN_ENV) or "").strip()


def base_of(family: str) -> str:
    """The provider's own base for `family` — what a call site starts from before `route_url`. Pure."""
    return dict(_UPSTREAMS)[family]


def upstream_of(url: str) -> tuple[str, str]:
    """`(family, base)` of a provider URL, or `("", "")` when egress does not carry it. Pure."""
    low = (url or "").strip().lower()
    for name, base in _UPSTREAMS:
        if low == base or low.startswith(base + "/") or low.startswith(base + "?") or low.startswith(base + ":"):
            return name, base
    return "", ""


def route_url(url: str, key: str) -> tuple[str, str]:
    """Effective `(url, key)` for a call to a provider's FULL url (or the base an SDK composes on).

    Self-host: unchanged. Mediated: `<egress>/p/<family><rest of the url>` with this process's egress credential.
    A provider egress does not carry comes back unchanged — and, in a mediated deployment, its key is the stand-in
    token, so the provider answers 401: a visible failure, never a call paid with a master key."""
    if is_local_endpoint(url) or not mediated():
        return url, key
    name, base = upstream_of(url)
    if not name:
        logger.error(f"llm_egress: {url.split('?')[0][:80]} is not a family egress carries — the call is not routed")
        return url, key
    return f"{root()}/p/{name}{url.strip()[len(base):]}", credential()


def stand_in_for_provider_keys() -> list[str]:
    """In a mediated deployment, make this process's egress credential stand in for every provider key egress
    can carry. Called once at boot, before anything reads a key. Returns the NAMES it replaced.

    Why at the door and not at each reader: «is there a key for X?» is asked in a dozen places (the model chains,
    the search health, the worker tiers, the panels), and each of them would otherwise conclude that a provider
    whose key was taken away no longer exists. With the stand-in every one of them keeps working, every routed
    call goes through egress with the right credential, and an unrouted one carries a token that is worthless
    outside egress. The real key is never read again by this process, whether or not it is still in the
    environment — removing it from the deployment then changes nothing that works."""
    if not mediated():
        return []
    token = (os.getenv(_TOKEN_ENV) or "").strip()
    if not token:
        logger.error(f"llm_egress: mediated egress without {_TOKEN_ENV} — provider keys are not stood in for")
        return []
    for name in _STANDS_IN_FOR:
        os.environ[name] = token
    return list(_STANDS_IN_FOR)


def bills_upstream() -> bool:
    """Who records the expense in the ledger?

    With mediated egress, the party that actually made the call — not this process. Counting it here as well
    would duplicate the record.
    What this process DOES continue to do is deduct from its local lease (`energy_lease`): that
    counter is a safety ceiling, not a ledger, and must keep working even when the link
    to the lease endpoint is down.
    """
    return mediated()
