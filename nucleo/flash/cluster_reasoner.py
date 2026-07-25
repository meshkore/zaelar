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

import os

from .fast_client import FastClient, ModelSpec
from .prompt import build_cluster_system


async def reason(text: str, *, spec: ModelSpec, on_chunk=None) -> str:
    """Un turno de cluster por el motor del FlashBrain, perfil untrusted. Devuelve el texto del modelo (el bridge
    parsea sus [[cluster.*]] y aplica el guard de salida). NUNCA ofrece tools. Propaga el error del proveedor igual
    que el motor de voz (el bridge lo captura y lo registra)."""
    from . import dialog

    messages = [
        {"role": "system", "content": build_cluster_system()},
        {"role": "user", "content": text},
    ]
    max_tokens = int(os.getenv("MESHKORE_MAX_TOKENS", "220"))
    buf = ""
    # tools=None → el modelo NO recibe ninguna herramienta (perfil untrusted, forzado en código).
    async for delta in FastClient().stream(messages, spec=spec, tools=None, max_tokens=max_tokens):
        buf += delta
    out = dialog.sanitize_reply(buf).strip()
    if on_chunk and out:
        on_chunk(out)
    return out
