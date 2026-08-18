"""memory/contract.py — la FRONTERA de la memoria, escrita como código (V2-114 F0).

La memoria tiene que poder evolucionar (e incluso reimplementarse) sin que el agente se entere. Para eso hace
falta saber, sin ambigüedad, **qué le pide el agente a una memoria**. Este módulo lo declara: es documentación
ejecutable de la superficie que un sustituto debe cubrir, y la lista de quién tiene permiso para saltarse la
fachada.

Medido el 2026-08-18 sobre 48 ficheros de producción: **84 de ~108 imports ya pasan por `memory.api`**. La
frontera no hay que inventarla, hay que cerrarla — y sobre todo impedir que se vuelva a abrir, que es lo que
hace el trinquete de `tests/memory/unit/test_memory_boundary.py`.

**Qué NO es esto.** No es una capa de indirección: `memory/api.py` sigue siendo la implementación y nadie tiene
que pasar por aquí para llamarla. Es un `Protocol` (tipado estructural), así que `memory.api` lo cumple sin
heredar nada y sin coste en runtime. Sirve para (a) que un sustituto sepa qué implementar, (b) que un cliente
remoto (V2-114 F3) tenga una diana exacta, y (c) que el trinquete tenga contra qué comparar.

**Lo que deliberadamente queda FUERA del contrato**, y por qué:
  - `memory.vault*` — la bóveda de secretos es otro concern (cripto, passkeys, revelación out-of-band). Comparte
    fichero SQLite, no semántica de memoria. Un sustituto de la memoria no debería tener que reimplementarla.
  - `memory.rem` / `memory.consolidator` / `memory.reembed` — el eje del SUEÑO. Lo orquesta `nucleo/loop.py`, no
    el turno. Es mantenimiento de la implementación, no algo que el agente pida.
  - `memory.embeddings` / `memory.retriever` / `memory.writer` / `memory.db` — tripas. Si un sustituto no usa
    sqlite-vec, nada de esto tiene sentido para él.
  - `memory.concepts.derive_concepts` — función pura stdlib sin BD; es vocabulario compartido, no estado.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MemoryContract(Protocol):
    """Lo que el agente necesita de una memoria. Agrupado por VELOCIDAD, que es el eje que gobierna el diseño
    (V2-011/V2-013): el turno de voz solo puede permitirse las dos primeras familias."""

    # ── LECTURA µs · SIEMPRE en el prompt, nunca I/O pesado ──────────────────────────────────────────────
    def state(self) -> dict:
        """Tabla fija de estado (identidad, ubicación, objetivo, widgets abiertos…). Lectura directa."""
        ...

    def compose_state(self) -> tuple[str, str, dict]:
        """El bloque de ESTADO COMPARTIDO ya compuesto: `(bloque, op, stats)`. Lo cachea el llamador fuera del
        turno; esta función NO puede llamar a un LLM ni al retriever."""
        ...

    def recent_short(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Working set de corto plazo, completo y sobre-incluyente. µs."""
        ...

    def recent_window(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Ventana conversacional reciente, verbatim, para «de qué hablábamos»."""
        ...

    # ── LECTURA ms · BAJO DEMANDA, fuera del event loop, CERO LLM ────────────────────────────────────────
    def query(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Recall semántico del largo plazo. La única familia que tolera esperas — y aun así sin LLM."""
        ...

    def recent_by_source(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Lectura por FUENTE indexada (whatsapp/telegram/cluster/email…), sin retriever."""
        ...

    def by_concepts(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Lectura por concepto, para agregación por categoría."""
        ...

    def as_of(self, *args: Any, **kwargs: Any) -> Any:
        """Reconstrucción a fecha pasada: «¿qué creíamos cierto el día X?» (bi-temporal, schema v5)."""
        ...

    def critical_facts(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Hechos que deben aflorar SIEMPRE (alergias, medicación). Fuera del cap normal."""
        ...

    def salient_long(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Perfil durable saliente para el bloque de estado."""
        ...

    # ── ESCRITURA · puede ser LENTA, nunca en el camino caliente ─────────────────────────────────────────
    def write(self, *args: Any, **kwargs: Any) -> Any:
        """Encola una escritura (fire-and-forget). Devuelve None: quien necesite el id usa `write_now`."""
        ...

    def write_now(self, *args: Any, **kwargs: Any) -> int:
        """Escritura SÍNCRONA que devuelve el id. Para episódica y tests."""
        ...

    def ingest_message(self, *args: Any, **kwargs: Any) -> None:
        """Vía TIPADA para un dato entrante de una FUENTE, con `trust` (operator/external/untrusted).
        `untrusted` implica CUARENTENA: nunca en el prompt pasivo."""
        ...

    def set_state(self, *args: Any, **kwargs: Any) -> Any:
        """Parche del estado fijo."""
        ...

    def forget(self, *args: Any, **kwargs: Any) -> int:
        """Olvido a petición del operador. `hard=True` borra de verdad (derecho al olvido)."""
        ...

    def unforget(self, *args: Any, **kwargs: Any) -> int:
        """El operador se retracta de un olvido."""
        ...

    # ── ESTADO AUXILIAR · clave-valor durable que NO debe viajar en el prompt ────────────────────────────
    def kv_get(self, *args: Any, **kwargs: Any) -> Any: ...
    def kv_set(self, *args: Any, **kwargs: Any) -> Any: ...
    def kv_keys(self, *args: Any, **kwargs: Any) -> Any: ...
    def kv_del(self, *args: Any, **kwargs: Any) -> Any: ...


# ── Quién puede saltarse la fachada, y por qué ───────────────────────────────────────────────────────────
# El trinquete (`tests/memory/unit/test_memory_boundary.py`) FALLA si aparece un import de tripas de `memory`
# fuera de esta lista. Añadir una entrada es una decisión consciente que se justifica aquí; el objetivo es que
# la deuda declarada solo pueda BAJAR, mismo patrón que `test_roadmap_closure.py`.
#
# Estado medido el 2026-08-18: **24 fugas en producción**, en 13 submódulos. Buena sorpresa de la medición:
# `memory.db`, `memory.retriever`, `memory.queue`, `memory.consolidator`, `memory.episodic`, `memory.graph*` y
# `memory.clock` **NO se importan desde producción** — sus 78 apariciones eran todas de `tests/`, donde tocar
# tripas es legítimo. La frontera real estaba bastante más cerrada de lo que parecía.
BLESSED_INTERNAL_IMPORTS: dict[str, str] = {
    # ── concern aparte: cripto/passkeys/revelación out-of-band. Comparte fichero SQLite, no semántica ──
    "memory.vault": "bóveda de secretos — subsistema propio (V2-060), no memoria",
    "memory.vault_api": "router FastAPI de la bóveda",
    # ── cableado del servidor: un router tiene que importarse para montarse ──
    "memory.server_api": "router FastAPI de memoria/episódica",
    # ── eje del SUEÑO: lo orquesta nucleo/loop.py (~1 Hz), nunca el turno ──
    "memory.rem": "fase REM diaria, orquestada por el loop",
    "memory.reembed": "migración de espacio vectorial, verificada al arrancar",
    # ── vocabulario/gates compartidos: stdlib puro, sin BD ──
    "memory.concepts": "derive_concepts — función pura, sin estado",
    "memory.slots": "registro canónico de slots — la fuente de la que se GENERA el prompt del destilador",
    "memory.secrets": "detección fail-closed de secretos, corre ANTES de escribir",
    # ── candidatos REALES a cerrarse re-exportando por la fachada (deuda declarada, no bendición eterna) ──
    "memory.state": "tabla fija de estado — CERRABLE: re-exportar por la fachada",
    "memory.journal": "diario de tareas — CERRABLE: re-exportar por la fachada",
    # ── tripas con un llamador legítimo y acotado ──
    "memory.writer": "escritor único — lo toca memory_agent, que ES el escritor",
    "memory.rerank": "estado del reranker para el panel de configuración",
    "memory.embeddings": "estado/dimensión del backend para el panel y el arranque",
}
