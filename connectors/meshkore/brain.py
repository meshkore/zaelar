#
# MeshKore channel brain = the FlashBrain ENGINE in UNTRUSTED profile (V2-069 «one mind»).
#
# Talking to the operator or to another agent is the SAME act → one engine. This module does NOT reason: (1) resolve
# the channel model TIER (off-voice, no real-time latency pressure), and (2) delegate the turn to the FlashBrain
# engine with the UNTRUSTED profile (`nucleo.flash.cluster`, tools disabled in code + identity-safe system).
#
# Wiring seam: `make_brain()` (called by server lifespan) returns an `async brain(text, on_chunk=None) -> str`, so
# the bridge/connector remain brain-agnostic.
#
# Security: the peer has no tools surface (forced in `nucleo.flash.cluster`), the system never touches operator
# memory/PII, and the bridge appends the security trailer at the end of the turn.
#
# RELAY (2026-08-03): the tier is NO LONGER fixed once at boot — `nucleo.flash.provider_chain.pick()` is queried ON
# EACH turn (cheap: an in-memory cooldown dict, not a network call) and, if the turn fails because of the provider
# (quota/credential — see `provider_chain.classify_failure`), it relays and RETRIES that same turn once before
# giving up. Before: a Z.AI 429 killed the turn and the next heartbeat repeated the SAME broken call — no relay, no
# warning (diagnosed with the operator 2026-08-03: `bridge.py` heartbeat kept trying to answer a peer while Z.AI
# returned endless 429s, in a loop).
from loguru import logger


def _spec():
    """`ModelSpec` for the CURRENT chain tier (compat: used by `bridge.py`'s V2-075 evaluator, which only needs SOME
    reasonable spec to judge the conversation — it does not participate in `_brain` relay)."""
    from nucleo.flash import provider_chain
    tier = provider_chain.pick()
    if not tier:
        raise RuntimeError("MeshKore: ningún proveedor de cerebro de cluster con credencial disponible")
    return provider_chain.spec_for(tier)


def make_brain():
    """Return the channel brain: the FlashBrain ENGINE (untrusted profile), with automatic provider RELAY. The tier
    is chosen per turn via `provider_chain.pick()`; the turn is driven by `nucleo.flash.cluster.respond`."""
    from nucleo.flash import cluster, provider_chain
    chain_now = provider_chain.chain()
    logger.info("MeshKore: canal conducido por el FlashBrain (perfil untrusted · sin tools) · cadena: "
                + (" → ".join(t["name"] for t in chain_now) if chain_now else "(sin credencial configurada)"))

    async def _brain(text: str, on_chunk=None, *, tool_names=None, escalate_ctx=None) -> str:
        # V2-076: default has no tools (untrusted profile, as always). The bridge only passes tool_names/escalate_ctx
        # when the cluster PERMISSION PROFILE (set by the operator on connect) grants some capability.
        tier = provider_chain.pick()
        if not tier:
            raise RuntimeError("MeshKore: ningún proveedor de cerebro de cluster con credencial disponible")
        spec = provider_chain.spec_for(tier)
        try:
            return await cluster.respond(text, spec=spec, on_chunk=on_chunk,
                                         tool_names=tool_names, escalate_ctx=escalate_ctx)
        except Exception as e:  # noqa: BLE001 — classify and, if there is a relay, retry THIS turn once
            nxt = provider_chain.note_failure(str(e), tier=tier)
            if not nxt:
                raise
            spec2 = provider_chain.spec_for(nxt)
            logger.warning(f"MeshKore: relevo «{tier['name']}»→«{nxt['name']}» a mitad de turno, reintentando")
            return await cluster.respond(text, spec=spec2, on_chunk=on_chunk,
                                         tool_names=tool_names, escalate_ctx=escalate_ctx)

    return _brain
