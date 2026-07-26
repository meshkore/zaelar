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
import os

from loguru import logger


def _resolve_endpoint() -> tuple[str, str, str, str]:
    """(api_key, base_url, model, provider) del TIER de modelo del canal, tolerante a la credencial DISPONIBLE.

    Z.AI DIRECTO tiene prioridad si hay `Z_AI_API_KEY` (fix de coste 2026-07-26, auditoría): el tier off-voz venía
    corriendo GLM vía AIMLAPI como proxy — con margen — aunque el operador ya tiene cuenta Z.AI propia (su plan de
    coding cubre exactamente este tráfico, probado en vivo). Respeta los overrides explícitos (LLM_API_KEY/
    LLM_BASE_URL + MESHKORE_MISSION_MODEL/LLM_MODEL, que siguen apuntando a AIMLAPI por defecto); si no hay NINGUNA
    key directa, cae a las mismas capas que el FlashBrain (xAI directo → Groq). Off-voz puede usar un modelo más
    fuerte — la regla dura no-razonador es SOLO para el turno síncrono de voz."""
    override_model = os.getenv("MESHKORE_MISSION_MODEL") or os.getenv("ASSISTANT_LLM_MODEL") or os.getenv("LLM_MODEL")
    if os.getenv("Z_AI_API_KEY") and not (os.getenv("LLM_API_KEY") or os.getenv("LLM_BASE_URL")):
        # explicit LLM_API_KEY/LLM_BASE_URL overrides still win (operator picked a specific endpoint on purpose)
        zai_model = os.getenv("MESHKORE_MISSION_MODEL_ZAI", "glm-5.2")   # el nombre PLANO de Z.AI, sin prefijo aimlapi
        return (os.getenv("Z_AI_API_KEY"), "https://api.z.ai/api/anthropic", zai_model, "zai")
    base = os.getenv("LLM_BASE_URL")
    key = os.getenv("LLM_API_KEY")
    if key or base or os.getenv("AIMLAPI_KEY"):        # ruta AIMLAPI explícita/heredada
        return (key or os.getenv("AIMLAPI_KEY") or "",
                base or "https://api.aimlapi.com/v1",
                override_model or "deepseek/deepseek-v4-flash", "aimlapi")
    if os.getenv("XAI_API_KEY"):                       # xAI DIRECTO (sin proxy AIMLAPI)
        return (os.getenv("XAI_API_KEY"), "https://api.x.ai/v1",
                override_model or "grok-4.20-0309-non-reasoning", "aimlapi")
    if os.getenv("GROQ_API_KEY"):
        return (os.getenv("GROQ_API_KEY"), "https://api.groq.com/openai/v1",
                override_model or "llama-3.3-70b-versatile", "aimlapi")
    return ("", "https://api.aimlapi.com/v1", override_model or "deepseek/deepseek-v4-flash", "aimlapi")


def _spec():
    """ModelSpec del canal desde `_resolve_endpoint()` (modelo POR INVOCACIÓN, nunca env global)."""
    from nucleo.flash.fast_client import ModelSpec
    api_key, base_url, model, provider = _resolve_endpoint()
    return ModelSpec(model=model, base_url=base_url, api_key=api_key, provider=provider)


def make_brain():
    """Devuelve el cerebro del canal: el MOTOR del FlashBrain (perfil untrusted). El spec (tier de modelo del canal)
    se fija al cablear; el turno lo conduce `nucleo.flash.cluster.respond`."""
    from nucleo.flash import cluster
    spec = _spec()
    logger.info(f"MeshKore: canal conducido por el FlashBrain (perfil untrusted · sin tools) · tier {spec.model}")

    async def _brain(text: str, on_chunk=None, *, tool_names=None, escalate_ctx=None) -> str:
        # V2-076: por defecto sin tools (perfil untrusted, como siempre). El bridge solo pasa tool_names/escalate_ctx
        # cuando el PERFIL DE PERMISOS del cluster (que fijó el operador al conectar) concede alguna capacidad.
        return await cluster.respond(text, spec=spec, on_chunk=on_chunk,
                                     tool_names=tool_names, escalate_ctx=escalate_ctx)

    return _brain
