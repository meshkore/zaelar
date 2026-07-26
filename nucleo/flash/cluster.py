"""nucleo/flash/cluster.py — el FlashBrain conduciendo un turno de CLUSTER (V2-069 «una sola mente»).

Hablar con el operador o con otro agente es el MISMO acto → un solo motor. El turno de peer corre por el MISMO motor
del FlashBrain — su cliente de modelo (`FastClient`, modelo POR INVOCACIÓN, métricas, arranque en frío) y sus
defensas de diálogo (`dialog`: anti-degeneración) — solo que con el **perfil UNTRUSTED**:

  · system identidad-SAFE (`prompt.build_cluster_system`, NUNCA toca `compose_state` → no filtra PII del operador),
  · **tools APAGADAS** (forzado aquí en código — un peer no confiable no puede hacer actuar a zaelar),
  · modelo del TIER del canal (lo pasa el llamador vía `spec`; ver `connectors/meshkore/brain.py`).

El contexto de la RELACIÓN (quién es el peer, de qué habéis hablado, objetivo, fase) lo inyecta el bridge en el
propio `text` (bloque de cápsula, contenido NUESTRO destilado) — por eso el motor es una llamada limpia por turno:
el estado vive en la cápsula (`connectors/meshkore/capsule.py`), no en el proceso.
"""
from __future__ import annotations

import asyncio
import os

from .fast_client import FastClient, ModelSpec
from .prompt import build_cluster_system

# Tope de tiempo del turno de cluster. Off-voz no hay presión de latencia de tiempo real, PERO el tier puede ser un
# RAZONADOR que a veces tarda: sin tope, un turno colgaría la task del bridge. Cap generoso pero acotado; al saltar
# lanza → el bridge lo captura y lo registra.
_TIMEOUT = float(os.getenv("MESHKORE_TIMEOUT", "120"))


def _gated_tools_and_handler(tool_names, escalate_ctx):
    """Monta (tools, on_tool_call) para un turno de cluster CON PERMISOS (V2-076). REUSA el catálogo del FlashBrain
    (`router.TOOLS`) filtrado a los nombres que el perfil del cluster permite, y un handler que enruta la ÚNICA vía
    de acción concedida a un peer: `escalate_to_slowbrain` → un worker ACOTADO (el contexto `escalate_ctx` lleva
    trusted=False + dev/repo/execute, lo enforcea `dispatch`). Sin duplicar router ni escalate."""
    from .router import TOOLS
    from .escalate import escalate_to_slowbrain
    names = set(tool_names or ())
    tools = [t for t in TOOLS if t.get("function", {}).get("name") in names]
    if not tools:
        return None, None

    def _on_tool_call(name: str, args: dict):
        # El peer nunca ejecuta directo: la única acción es escalar a un worker acotado por el contexto de permisos.
        if name == "escalate_to_slowbrain":
            req = (args or {}).get("request") or ""
            if req.strip():
                escalate_to_slowbrain(req, context=dict(escalate_ctx or {}))
        # web_search u otras: aún no se ejecutan desde un turno de cluster (follow-up) — se ignoran sin romper.

    return tools, _on_tool_call


async def _complete(text: str, spec: ModelSpec, max_tokens: int, tools=None, on_tool_call=None) -> str:
    from . import dialog
    messages = [
        {"role": "system", "content": build_cluster_system()},
        {"role": "user", "content": text},
    ]
    # NO-streaming (FastClient.complete): off-voz no necesita trocear, y un tier razonador no emite deltas hasta
    # terminar → con stream se colgaría. `tools` solo se pasa cuando el perfil del cluster los concede (V2-076); sin
    # ellos = perfil untrusted puro, un peer no hace actuar a zaelar (idéntico a antes).
    out = await FastClient().complete(messages, spec=spec, max_tokens=max_tokens,
                                      tools=tools, on_tool_call=on_tool_call)
    return dialog.sanitize_reply(out).strip()


async def respond(text: str, *, spec: ModelSpec, tool_names=None, escalate_ctx=None,
                  on_chunk=None, timeout: float | None = None) -> str:
    """Un turno de cluster por el motor del FlashBrain (V2-069). Devuelve el texto del modelo (el bridge parsea sus
    [[cluster.*]] y aplica el guard de salida). **Por defecto NO ofrece tools** (perfil untrusted, cero regresión);
    si el bridge pasa `tool_names` (del PERFIL DE PERMISOS del cluster, V2-076) ofrece ESE subconjunto del catálogo
    del FlashBrain y enruta la escalada con `escalate_ctx` (acotado). Acotado por `_TIMEOUT`; propaga error/timeout."""
    max_tokens = int(os.getenv("MESHKORE_MAX_TOKENS", "220"))
    tools, handler = _gated_tools_and_handler(tool_names, escalate_ctx)
    out = await asyncio.wait_for(_complete(text, spec, max_tokens, tools=tools, on_tool_call=handler),
                                 timeout=timeout or _TIMEOUT)
    if on_chunk and out:
        on_chunk(out)
    return out
