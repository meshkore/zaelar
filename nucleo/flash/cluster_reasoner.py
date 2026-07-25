"""nucleo/flash/cluster_reasoner.py — el FlashBrain conduciendo un turno de CLUSTER (V2-069 «una sola mente»).

Antes había DOS cerebros conversando: el FlashBrain (voz/operador) y un `_direct_reasoner` paralelo y tonto para
el canal de cluster (una llamada OpenAI pelada, sin la maquinaria del motor). Esto los UNIFICA: el turno de peer
corre por el MISMO motor del FlashBrain — su cliente de modelo (`FastClient`, modelo POR INVOCACIÓN, métricas,
arranque en frío), sus defensas de diálogo (`dialog`: anti-degeneración) — solo que con el **perfil UNTRUSTED**:

  · system identidad-SAFE (`prompt.build_cluster_system`, NUNCA toca `compose_state` → no filtra PII del operador),
  · **tools APAGADAS** (lista vacía, forzado aquí en código — un peer no confiable no puede hacer actuar a zaelar),
  · modelo del TIER de razonamiento del canal (lo pasa el llamador vía `spec` — hoy GLM-5.2, off-voz sin presión de
    latencia; ver `connectors/meshkore/reasoner.py::_resolve_endpoint`).

El contexto de la RELACIÓN (quién es el peer, de qué habéis hablado, objetivo, fase) lo inyecta el bridge en el
propio `text` (bloque de cápsula, contenido NUESTRO destilado) — por eso aquí el motor sigue siendo una llamada
limpia por turno: el estado vive en la cápsula, no en el proceso.
"""
from __future__ import annotations

import asyncio
import os

from .fast_client import FastClient, ModelSpec
from .prompt import build_cluster_system

# Tope de tiempo del turno de cluster. Off-voz no hay presión de latencia de tiempo real, PERO el tier puede ser un
# RAZONADOR (GLM-5.2) que a veces tarda mucho: sin tope, un turno colgaría la task del bridge indefinidamente. Cap
# generoso pero acotado (igual que el reasoner viejo). Al saltar, lanza → el bridge lo captura y registra.
_TIMEOUT = float(os.getenv("MESHKORE_TIMEOUT", "120"))


async def _complete(text: str, spec: ModelSpec, max_tokens: int) -> str:
    from . import dialog
    messages = [
        {"role": "system", "content": build_cluster_system()},
        {"role": "user", "content": text},
    ]
    # NO-streaming (FastClient.complete): off-voz no necesita trocear, y un tier razonador (GLM-5.2) no emite deltas
    # hasta terminar → con stream se colgaría. No se pasan tools: perfil untrusted, un peer no hace actuar a zaelar.
    out = await FastClient().complete(messages, spec=spec, max_tokens=max_tokens)
    return dialog.sanitize_reply(out).strip()


async def reason(text: str, *, spec: ModelSpec, on_chunk=None, timeout: float | None = None) -> str:
    """Un turno de cluster por el motor del FlashBrain, perfil untrusted. Devuelve el texto del modelo (el bridge
    parsea sus [[cluster.*]] y aplica el guard de salida). NUNCA ofrece tools. Acotado por `_TIMEOUT` (un tier
    razonador lento no debe colgar la task). Propaga el error/timeout igual que el motor de voz (el bridge lo captura)."""
    max_tokens = int(os.getenv("MESHKORE_MAX_TOKENS", "220"))
    out = await asyncio.wait_for(_complete(text, spec, max_tokens), timeout=timeout or _TIMEOUT)
    if on_chunk and out:
        on_chunk(out)
    return out
