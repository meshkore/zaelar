#
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
_PROVIDER_BY_HOST = (
    ("aimlapi.com", "aimlapi"),
    ("api.x.ai", "xai"),
    ("api.z.ai", "zai"),
    ("mistral.ai", "mistral"),
)


def mediated() -> bool:
    """Does this deployment send calls through mediated egress?"""
    from nucleo import cloud_account
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
    """
    if is_local_endpoint(base_url) or not mediated():
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


def bills_upstream() -> bool:
    """Who records the expense in the ledger?

    With mediated egress, the party that actually made the call — not this process. Counting it here as well
    would duplicate the charge, and a client paying twice per turn is a worse failure than not charging.
    What this process DOES continue to do is deduct from its local lease (`energy_lease`): that
    counter is a safety ceiling, not an invoice, and must keep working even when the link
    to the cloud is down.
    """
    return mediated()
