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


async def _complete(text: str, spec: ModelSpec, max_tokens: int) -> str:
    from . import dialog
    messages = [
        {"role": "system", "content": build_cluster_system()},
        {"role": "user", "content": text},
    ]
    # NO-streaming (FastClient.complete): off-voz no necesita trocear, y un tier razonador no emite deltas hasta
    # terminar → con stream se colgaría. Sin tools: perfil untrusted, un peer no hace actuar a zaelar.
    out = await FastClient().complete(messages, spec=spec, max_tokens=max_tokens)
    return dialog.sanitize_reply(out).strip()


async def respond(text: str, *, spec: ModelSpec, on_chunk=None, timeout: float | None = None) -> str:
    """Un turno de cluster por el motor del FlashBrain, perfil untrusted. Devuelve el texto del modelo (el bridge
    parsea sus [[cluster.*]] y aplica el guard de salida). NUNCA ofrece tools. Acotado por `_TIMEOUT`. Propaga el
    error/timeout igual que el motor de voz (el bridge lo captura)."""
    max_tokens = int(os.getenv("MESHKORE_MAX_TOKENS", "220"))
    out = await asyncio.wait_for(_complete(text, spec, max_tokens), timeout=timeout or _TIMEOUT)
    if on_chunk and out:
        on_chunk(out)
    return out
