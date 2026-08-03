#
# El cerebro del canal MeshKore = el MOTOR del FlashBrain en perfil UNTRUSTED (V2-069 «una sola mente»).
#
# Hablar con el operador o con otro agente es el MISMO acto → un solo motor. Este módulo NO razona: (1) resuelve el
# TIER de modelo del canal (off-voz, sin presión de latencia de tiempo real) y (2) delega el turno en el motor del
# FlashBrain con perfil UNTRUSTED (`nucleo.flash.cluster`, tools apagadas en código + system identidad-safe).
#
# Seam de cableado: `make_brain()` (lo llama el lifespan del server) devuelve un `async brain(text, on_chunk=None)
# -> str`, así el bridge/connector siguen siendo agnósticos del cerebro.
#
# Seguridad: el peer no tiene superficie de tools (se fuerza en `nucleo.flash.cluster`), el system nunca toca la
# memoria/PII del operador, y el bridge antepone el trailer de seguridad al final del turno.
#
# RELEVO (2026-08-03): el tier YA NO se fija una vez al arrancar — `nucleo.flash.provider_chain.pick()` se
# consulta EN CADA turno (barato: un dict de cooldowns en memoria, no una llamada de red) y, si el turno falla por
# el proveedor (cuota/credencial — ver `provider_chain.classify_failure`), se releva y se REINTENTA ese mismo turno
# una vez antes de rendirse. Antes: un 429 de Z.AI moría el turno y el siguiente heartbeat repetía la MISMA llamada
# rota — sin relevo, sin aviso (diagnosticado con el operador 2026-08-03: el heartbeat de `bridge.py` insistía en
# responder a un peer mientras Z.AI daba 429 sin parar, en bucle).
from loguru import logger


def _spec():
    """El `ModelSpec` del escalón ACTUAL de la cadena (compat: lo usa `bridge.py`'s V2-075 evaluator, que solo
    necesita ALGÚN spec razonable para juzgar la conversación — no participa del relevo de `_brain`)."""
    from nucleo.flash import provider_chain
    tier = provider_chain.pick()
    if not tier:
        raise RuntimeError("MeshKore: ningún proveedor de cerebro de cluster con credencial disponible")
    return provider_chain.spec_for(tier)


def make_brain():
    """Devuelve el cerebro del canal: el MOTOR del FlashBrain (perfil untrusted), con RELEVO automático de
    proveedor. El tier se elige por turno vía `provider_chain.pick()`; el turno lo conduce
    `nucleo.flash.cluster.respond`."""
    from nucleo.flash import cluster, provider_chain
    chain_now = provider_chain.chain()
    logger.info("MeshKore: canal conducido por el FlashBrain (perfil untrusted · sin tools) · cadena: "
                + (" → ".join(t["name"] for t in chain_now) if chain_now else "(sin credencial configurada)"))

    async def _brain(text: str, on_chunk=None, *, tool_names=None, escalate_ctx=None) -> str:
        # V2-076: por defecto sin tools (perfil untrusted, como siempre). El bridge solo pasa tool_names/escalate_ctx
        # cuando el PERFIL DE PERMISOS del cluster (que fijó el operador al conectar) concede alguna capacidad.
        tier = provider_chain.pick()
        if not tier:
            raise RuntimeError("MeshKore: ningún proveedor de cerebro de cluster con credencial disponible")
        spec = provider_chain.spec_for(tier)
        try:
            return await cluster.respond(text, spec=spec, on_chunk=on_chunk,
                                         tool_names=tool_names, escalate_ctx=escalate_ctx)
        except Exception as e:  # noqa: BLE001 — clasificar y, si hay relevo, reintentar ESTE turno una vez
            nxt = provider_chain.note_failure(str(e), tier=tier)
            if not nxt:
                raise
            spec2 = provider_chain.spec_for(nxt)
            logger.warning(f"MeshKore: relevo «{tier['name']}»→«{nxt['name']}» a mitad de turno, reintentando")
            return await cluster.respond(text, spec=spec2, on_chunk=on_chunk,
                                         tool_names=tool_names, escalate_ctx=escalate_ctx)

    return _brain
