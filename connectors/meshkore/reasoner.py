#
# Adaptador del canal MeshKore al MOTOR ÚNICO (V2-069 «una sola mente»).
#
# ANTES este módulo era un SEGUNDO cerebro: una llamada OpenAI pelada (`_direct_reasoner`) con su propio system
# prompt, sin nada de la maquinaria del FlashBrain. El operador lo señaló: hablar con el operador o con otro agente
# es lo MISMO acto → no debe haber dos motores. Ahora este módulo NO razona: solo (1) resuelve el TIER de modelo del
# canal (off-voz, sin presión de latencia → un modelo razonador, hoy GLM-5.2) y (2) delega el turno en el motor del
# FlashBrain con perfil UNTRUSTED (`nucleo.flash.cluster_reasoner`, tools apagadas + system identidad-safe).
#
# El seam sigue siendo el mismo `make_reasoner()` que cablea el lifespan del server (`server/__init__.py`): devuelve
# un `async reasoner(text, on_chunk=None) -> str`, así el bridge/connector siguen siendo agnósticos del cerebro.
#
# Seguridad intacta: el peer sigue sin superficie de tools (se fuerza en `cluster_reasoner`), el system nunca toca
# la memoria/PII del operador, y el bridge antepone el trailer de seguridad al final del turno.
#
import os

from loguru import logger


def _resolve_endpoint() -> tuple[str, str, str]:
    """(api_key, base_url, model) del TIER de modelo del canal de cluster, tolerante a la credencial DISPONIBLE.
    Respeta los overrides explícitos (LLM_API_KEY/LLM_BASE_URL + MESHKORE_MISSION_MODEL/LLM_MODEL); si no hay key de
    AIMLAPI, cae a las mismas capas que el FlashBrain (xAI directo → Groq). Off-voz puede usar un modelo más fuerte
    (razonador) — la regla dura no-razonador es SOLO para el turno síncrono de voz."""
    override_model = os.getenv("MESHKORE_MISSION_MODEL") or os.getenv("ASSISTANT_LLM_MODEL") or os.getenv("LLM_MODEL")
    base = os.getenv("LLM_BASE_URL")
    key = os.getenv("LLM_API_KEY")
    if key or base or os.getenv("AIMLAPI_KEY"):        # ruta AIMLAPI explícita/heredada
        return (key or os.getenv("AIMLAPI_KEY") or "",
                base or "https://api.aimlapi.com/v1",
                override_model or "deepseek/deepseek-v4-flash")
    if os.getenv("XAI_API_KEY"):                       # xAI DIRECTO (sin proxy AIMLAPI)
        return (os.getenv("XAI_API_KEY"), "https://api.x.ai/v1", override_model or "grok-4.20-0309-non-reasoning")
    if os.getenv("GROQ_API_KEY"):
        return (os.getenv("GROQ_API_KEY"), "https://api.groq.com/openai/v1", override_model or "llama-3.3-70b-versatile")
    return ("", "https://api.aimlapi.com/v1", override_model or "deepseek/deepseek-v4-flash")


def _spec():
    """Construye el ModelSpec del canal desde `_resolve_endpoint()` (modelo POR INVOCACIÓN, nunca env global)."""
    from nucleo.flash.fast_client import ModelSpec
    api_key, base_url, model = _resolve_endpoint()
    return ModelSpec(model=model, base_url=base_url, api_key=api_key, provider="aimlapi")


def make_reasoner():
    """Devuelve el reasoner del canal: el MOTOR del FlashBrain (perfil untrusted), no un cerebro aparte. El spec
    (tier de modelo del cluster) se fija al cablear; el turno lo conduce `cluster_reasoner.reason`."""
    from nucleo.flash import cluster_reasoner
    spec = _spec()
    logger.info(f"MeshKore reasoner: motor ÚNICO (FlashBrain · perfil untrusted, sin tools) · tier {spec.model}")

    async def _reason(text: str, on_chunk=None) -> str:
        return await cluster_reasoner.reason(text, spec=spec, on_chunk=on_chunk)

    return _reason
