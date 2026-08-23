"""Sanctioned writes from OUTSIDE the voice turn: widgets, workers, connectors.

Split out VERBATIM (audit 2026-08-23). `remember_external` never touches `state` nor identity slots
(V2-033 promise, incident 2026-07-14).
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from nucleo.memory_agent.dossier import _derive_concepts  # noqa: F401
from nucleo.memory_agent.classify import classify
from nucleo.memory_agent.gates import (  # noqa: F401
    _memslots,    _IDENTITY_SLOTS, _atom_value_invalid, _precision_reject_atom)


async def remember(item: dict[str, Any]) -> None:
    """Encola en la memoria lo que merece guardarse. **Único escritor** del SlowBrain.

    `item`:
      - `text`         — el recuerdo (obligatorio para escribir un `memories`).
      - `kind`         — 'fact'|'pref'|'summary'|'result'|'event'|'profile' (default: auto-clasificado).
      - `level`        — 'short'|'mid'|'long' (default: auto-clasificado; `None` = skip).
      - `importance`   — 0..1 opcional; `pinned` — bool.
      - `slot`         — clave canónica del hecho singular (`operator.name`…) → supersede/dedup EXACTO (V2-013).
      - `meta`         — dict/JSON: píldora de metadatos (source/path/raw/state_patch/said_at…) para visor/grafo.
      - `ttl_days`     — float opcional: caducidad (None = no caduca).
      - `state_patch`  — dict opcional: merge superficial en la tabla `state`.
      - `auto`         — bool (default True): si el caller no fija `level`/`kind`/`state_patch`, se auto-clasifica
                         `text` con `classify()` para no perder perfil (nombre, ubicación, etc.).
    Best-effort: cualquier fallo se traga (la memoria no es crítica para cerrar el turno)."""
    if not isinstance(item, dict):
        return
    try:
        from memory import api as memory
    except Exception:
        return

    text = (item.get("text") or "").strip()
    level = item.get("level")
    kind = item.get("kind")
    importance = item.get("importance")
    pinned = bool(item.get("pinned", False))
    patch = item.get("state_patch") or {}
    slot = item.get("slot")
    meta = item.get("meta")
    ttl_days = item.get("ttl_days")
    concepts = item.get("concepts")   # V2-013 T126: etiquetas de concepto ligeras → nodos/aristas del grafo

    # Auto-clasificación para DERIVAR el level cuando el caller no lo fijó (aunque haya dado kind/importance):
    # `remember({text, kind:"result"})` DEBE escribirse — antes el guard `not kind` lo dejaba con level=None y no
    # escribía nada (test_remember_writes_to_memory en rojo). Respeta lo que el caller SÍ fijó (kind/patch/…).
    auto = bool(item.get("auto", True))
    if auto and text and level is None:
        plan = classify(text)
        if not patch:
            patch = plan["state_patch"] or {}
        level = plan["level"]
        kind = kind or plan["kind"]
        if importance is None:
            importance = plan["importance"]
        pinned = pinned or plan["pinned"]
        if slot is None:
            slot = plan.get("slot")

    # Backstop de conceptos (T126): si es DURABLE y el LLM no etiquetó, deriva por keywords → cobertura garantizada
    # del grafo (que el recall por categoría no dependa de la consistencia del modelo pequeño).
    if not concepts and text and level in ("mid", "long"):
        concepts = _derive_concepts(text) or None

    if text and level:                          # `level=None` = skip explícito del clasificador
        try:
            memory.write(
                text,
                kind=kind or "result",
                level=level,
                importance=importance,
                pinned=pinned,
                ttl_days=ttl_days,
                slot=slot,
                meta=meta,
                concepts=concepts,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"memory_agent.remember write falló: {e}")

    if isinstance(patch, dict) and patch:
        try:
            memory.set_state(patch)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"memory_agent.remember state_patch falló: {e}")


async def remember_external(item: dict, *, source: str = "external") -> dict:
    """Escritura que llega de FUERA del proceso (Brain Workers vía `hbmem` → `POST /api/memory/remember`).

    Auditoría 2026-07-14: el endpoint enrutaba a `remember(auto=True)`, que clasifica el texto y podía derivar
    un `state_patch` → un worker (o cualquier proceso local) PISABA la identidad del operador en `state` sin
    pasar por la cuarentena V2-033 — cosa que el mismo texto dicho por VOZ no haría. Política de esta vía:
      - **NUNCA toca `state`** (un worker no habla por el operador; `auto=False`, sin state_patch).
      - **Gate de precisión** (P0a): una pregunta/petición reificada no se persiste.
      - **Slots de IDENTIDAD vetados**: `--slot operator.name` y familia se DEGRADAN a hecho suelto (el linaje
        de identidad solo lo escribe el turno del operador); los slots de trabajo (`goal.moto`, `weather:x`,
        namespaced) pasan normal — el supersede exacto sigue siendo suyo.
      - **Procedencia estampada** (`meta.source="worker:<id>"`): auditable y limpiable por origen.
    Devuelve un dict-resumen para el endpoint (ok/reason)."""
    if not isinstance(item, dict):
        return {"ok": False, "reason": "bad-item"}
    text = (item.get("text") or "").strip()
    if not text:
        return {"ok": False, "reason": "empty"}
    if _precision_reject_atom({"text": text, "kind": item.get("kind") or "result"}, raw=text):
        return {"ok": False, "reason": "precision"}
    slot = _memslots.canonical(item.get("slot"))
    identity_dropped = False
    if slot and slot in _IDENTITY_SLOTS:
        slot, identity_dropped = None, True
    meta = dict(item.get("meta") or {})
    meta.setdefault("source", source)
    await remember({
        "text": text,
        "kind": item.get("kind") or "result",
        "level": item.get("level") or "mid",
        "importance": item.get("importance"),
        "ttl_days": item.get("ttl_days"),
        "slot": slot,
        "meta": meta,
        "auto": False,                          # jamás re-clasificar: esta vía no deriva state_patch
    })
    return {"ok": True, "identity_slot_dropped": identity_dropped}


# Serializa las llamadas a ingest_utterance en el ORDEN en que se dispararon (maratón de testing 2026-07-22):
# tanto la voz real (nucleo.py) como el probe la lanzan `fire-and-forget` (asyncio.create_task) para no bloquear
# el turno — correcto para latencia, pero sin esto dos turnos consecutivos y rápidos ("apunta que mi talla es
# M" seguido a los 2s de "olvida eso de la talla") pueden completarse en el orden EQUIVOCADO: el olvido (rápido,
# determinista, sin LLM) puede terminar y no encontrar nada que invalidar ANTES de que el recordatorio (lento,
# pasa por el CORAZÓN/LLM) termine de escribirse — el dato "olvidado" sobrevive. Un lock module-level asegura
# que cada ingesta se procesa de principio a fin antes de empezar la siguiente, en el mismo orden de llegada
# (asyncio.Lock es FIFO); no afecta la latencia del turno (sigue siendo fire-and-forget desde el llamante).
