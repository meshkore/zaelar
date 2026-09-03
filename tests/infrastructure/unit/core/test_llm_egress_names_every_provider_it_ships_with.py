"""V2-560 — a provider the allocation table ships must be NAMEABLE by mediated egress.

Measured on a real cloud account (2026-09-03). Every Machine is provisioned with
`FAST_BASE_URL=https://api.deepseek.com`, the allocation table names DeepSeek as the titular of the
voice brain, and the operator's DeepSeek account had balance. The user still got «no credits».

The gap was one row. `_PROVIDER_BY_HOST` did not contain `deepseek.com`, so `provider_of()` returned
"", `_headers()` sent no `X-Zaelar-Provider` at all, and the gateway did what it must do with a
request that names no provider: it used its own default. That default was AIMLAPI, which had run out
of funds. Nothing anywhere was red — the header is OPTIONAL by design, so "absent" is indistinguishable
from "no preference", and the failure surfaced as a third party's billing message.

This is the ratchet against that shape: whatever the shipped table names as a titular or a failover has
to be a family this module can name. It reads the REAL table (`config/models.default.json`, the single
source since V2-500) rather than a list written here, because a second hand-written list is exactly the
thing that drifted.
"""
import json
import pathlib

import pytest

from nucleo import llm_egress

ENGINE = pathlib.Path(__file__).resolve().parents[4]
TABLE = ENGINE / "config" / "models.default.json"

#: Services whose calls do NOT go through mediated LLM egress: speech and embeddings speak their own
#: protocols to their own endpoints, and `off` is not a provider at all.
_NOT_CHAT = {"stt", "tts", "embeddings", "reranker"}


def _rungs():
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    for sid, svc in (table.get("services") or {}).items():
        if sid in _NOT_CHAT:
            continue
        for role in ("titular", "failover"):
            rung = svc.get(role) or {}
            base = str(rung.get("base_url") or "").strip()
            if base:
                yield sid, role, rung.get("provider"), base


def test_the_table_is_where_it_says_it_is():
    """Without this, a moved file turns every assertion below into a vacuous pass."""
    assert TABLE.exists(), f"{TABLE} — la tabla única de V2-500 no está donde se busca"
    assert list(_rungs()), "la tabla no declaró ni un escalón con base_url: el lector mide otra cosa"


@pytest.mark.parametrize("sid,role,provider,base", list(_rungs()))
def test_every_shipped_rung_can_be_named(sid, role, provider, base):
    named = llm_egress.provider_of(base)
    assert named, (
        f"{sid}.{role} envía a {base} y `provider_of` no sabe nombrarlo: la cabecera "
        "`X-Zaelar-Provider` saldría VACÍA y el gateway usaría su propio defecto — que es "
        "exactamente cómo la voz de la nube acabó en un proveedor sin fondos que nadie eligió."
    )


def test_deepseek_is_named_because_that_is_the_one_that_cost_a_day():
    assert llm_egress.provider_of("https://api.deepseek.com") == "deepseek"
    assert llm_egress.provider_of("https://api.deepseek.com/v1") == "deepseek"


def test_an_unknown_host_still_returns_empty_and_does_not_guess():
    """The empty string has to stay meaningful: it is «no preference», not «pick something».
    Inventing a family here would move the same silent-misrouting bug one layer down."""
    assert llm_egress.provider_of("https://api.example.invalid/v1") == ""
    assert llm_egress.provider_of("") == ""
