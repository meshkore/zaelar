"""nucleo/flash/cluster.py — the FlashBrain conduciendo a turn of CLUSTER (V2-069 «a sola mente»).

Hablar with the operator or with another agent es the MISMO acto → a only motor. El turn of peer corre by the MISMO motor
of the FlashBrain — su cliente of model (`FastClient`, model POR INVOCACIÓN, metricas, arranque in frio) and sus
defensas of dialogo (`dialog`: anti-degeneracion) — only that with the **perfil UNTRUSTED**:

  · system identidad-SAFE (`prompt.build_cluster_system`, NUNCA touches `compose_state` → no filtra PII of the operator),
  · **tools APAGADAS** (forzado here in code — a peer no confiable no can do actuar a zaelar),
  · model of the TIER of the canal (it pasa the llamador via `spec`; ver `connectors/meshkore/brain.py`).

El contexto of the RELACIÓN (who es the peer, of what habeis hablado, objetivo, fase) it inyecta the bridge in the
own `text` (bloque of capsula, contenido NUESTRO destilado) — by eso the motor es a llamada limpia by turn:
the state lives in the capsula (`connectors/meshkore/capsule.py`), no in the proceso.
"""
from __future__ import annotations

import asyncio
import os

from .fast_client import FastClient, ModelSpec
from .prompt import build_cluster_system

# Tope of time of the turn of cluster. Off-voice no there is presion of latencia of time real, PERO the tier can ser a
# RAZONADOR that a veces tarda: without cap, a turn colgaria the task of the bridge. Cap generoso but acotado; al trigger
# lanza → the bridge it captura and it registra.
_TIMEOUT = float(os.getenv("MESHKORE_TIMEOUT", "120"))


def _gated_tools_and_handler(tool_names, escalate_ctx):
    """Monta (tools, on_tool_call) for a turn of cluster CON PERMISOS (V2-076). REUSA the catalogo of the FlashBrain
    (`router.TOOLS`) filtered a the names that the perfil of the cluster allows, and a handler that routes the ÚNICA via
    of action concedida a a peer: `escalate_to_slowbrain` → a worker ACOTADO (the contexto `escalate_ctx` lleva
    trusted=False + dev/repo/execute, it enforcea `dispatch`). Sin duplicar router ni escalate."""
    from .router import TOOLS
    from .escalate import escalate_to_slowbrain
    names = set(tool_names or ())
    tools = [t for t in TOOLS if t.get("function", {}).get("name") in names]
    if not tools:
        return None, None

    def _on_tool_call(name: str, args: dict):
        # El peer never ejecuta directly: the only action es escalar a a worker acotado by the contexto of permissions.
        if name == "escalate_to_slowbrain":
            req = (args or {}).get("request") or ""
            if req.strip():
                escalate_to_slowbrain(req, context=dict(escalate_ctx or {}))
        # web_search u otras: aun no is ejecutan from a turn of cluster (follow-up) — is ignore without romper.

    return tools, _on_tool_call


async def _complete(text: str, spec: ModelSpec, max_tokens: int, tools=None, on_tool_call=None) -> str:
    from . import dialog
    messages = [
        {"role": "system", "content": build_cluster_system()},
        {"role": "user", "content": text},
    ]
    # NO-streaming (FastClient.complete): off-voice no needs trocear, and a tier razonador no emite deltas until
    # finish → with stream is colgaria. `tools` only is pasa when the perfil of the cluster the grants (V2-076); without
    # ellos = perfil untrusted pure, a peer no does actuar a zaelar (identico a before).
    out = await FastClient().complete(messages, spec=spec, max_tokens=max_tokens,
                                      tools=tools, on_tool_call=on_tool_call)
    return dialog.sanitize_reply(out).strip()


async def respond(text: str, *, spec: ModelSpec, tool_names=None, escalate_ctx=None,
                  on_chunk=None, timeout: float | None = None) -> str:
    """Un turn of cluster by the motor of the FlashBrain (V2-069). Devuelve the texto of the model (the bridge parsea sus
    [[cluster.*]] and aplica the guard of salida). **Por defecto NO ofrece tools** (perfil untrusted, cero regresion);
    if the bridge pasa `tool_names` (of the PERFIL DE PERMISOS of the cluster, V2-076) ofrece ESE subconjunto of the catalogo
    of the FlashBrain and routes the escalada with `escalate_ctx` (acotado). Acotado by `_TIMEOUT`; propaga error/timeout."""
    max_tokens = int(os.getenv("MESHKORE_MAX_TOKENS", "220"))
    tools, handler = _gated_tools_and_handler(tool_names, escalate_ctx)
    out = await asyncio.wait_for(_complete(text, spec, max_tokens, tools=tools, on_tool_call=handler),
                                 timeout=timeout or _TIMEOUT)
    if on_chunk and out:
        on_chunk(out)
    return out
