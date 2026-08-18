"""tests/memory/e2e/bot/distiller_tape.py — GRABA y REPLICA el CORAZÓN de escritura (V2-114 F1).

**El problema que resuelve.** La única medición seria de la memoria (`scale_eval --fresh`) repuebla el corpus
llamando al destilador REAL 579 veces: ~90 minutos y dinero de API por hipótesis. Con ese ciclo no se pueden
probar ideas, solo confirmarlas de vez en cuando. La auditoría del 2026-08-18 lo señaló como el cuello real de
la iteración — por delante de cualquier reorganización arquitectónica.

**La idea.** `nucleo/mem_processor.process()` es una costura estrecha y bien definida: entra una frase, salen
píldoras. Se graba UNA vez lo que el LLM decidió y se replica indefinidamente. El fixture congela **la decisión
del modelo**, no lo que la memoria hizo con ella — así una corrida `--replay` prueba la MEMORIA (writer,
supersede, retriever, grafo, REM) y no el destilador. Es justo la frontera que queremos poder cambiar rápido.

**Por qué una cinta SECUENCIAL y no un diccionario texto→píldoras.** `memory_agent` reintenta una vez cuando
`process()` devuelve `None` (V2-103: blip de red del CORAZÓN), así que una misma frase puede producir DOS
llamadas. Un diccionario por texto no puede representar eso; una cinta en orden de llamada sí, y al replicarla
el reintento vuelve a disparar exactamente donde disparó al grabar. Reproducción fiel, incluido el camino de
degradación a la heurística.

Los tres valores de retorno se conservan con su semántica (importa: son ramas distintas del llamador):
  `None` = el modelo no estaba disponible → el llamador cae a la heurística
  `[]`   = corrió y decidió que no hay nada memorable (DESCARTE legítimo)
  `[…]`  = píldoras curadas

Uso:
    with tape.record("fixtures/corpus-v1.jsonl"):
        await runner.run_range(0, 10_000, fresh=True)     # ~90 min, UNA vez

    with tape.replay("fixtures/corpus-v1.jsonl") as t:
        await runner.run_range(0, 10_000, fresh=True)     # segundos, sin red
        print(t.stats())
"""
from __future__ import annotations

import contextlib
import json
import pathlib
import threading


class _Tape:
    """Estado compartido de una sesión de grabación o réplica. Con lock: el destilador es serial por diseño
    (un semáforo en `mem_processor`), pero el runner puede invocarlo desde hilos distintos vía `to_thread`."""

    def __init__(self, path: str | pathlib.Path):
        self.path = pathlib.Path(path)
        self.entries: list[dict] = []
        self.pos = 0
        self.hits = 0
        self.misses = 0
        self.out_of_order = 0
        self._lock = threading.Lock()

    # ── grabación ──────────────────────────────────────────────────────────────────────────────────────
    def append(self, text: str, atoms: list[dict] | None) -> None:
        with self._lock:
            self.entries.append({"i": len(self.entries), "text": text, "atoms": atoms})

    def flush(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            for e in self.entries:
                fh.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        return len(self.entries)

    # ── réplica ────────────────────────────────────────────────────────────────────────────────────────
    def load(self) -> int:
        self.entries = [json.loads(ln) for ln in
                        self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return len(self.entries)

    def next_for(self, text: str) -> tuple[bool, list[dict] | None]:
        """Devuelve `(encontrado, atoms)` para la siguiente llamada. En orden estricto mientras el texto case;
        si no casa (se está replicando un SUBRANGO, o el corpus cambió), busca hacia delante la próxima entrada
        con ese texto y lo cuenta como desorden — degradar es mejor que mentir con las píldoras de otra frase."""
        with self._lock:
            if self.pos < len(self.entries) and self.entries[self.pos]["text"] == text:
                e = self.entries[self.pos]
                self.pos += 1
                self.hits += 1
                return True, e["atoms"]
            for j in range(self.pos, len(self.entries)):
                if self.entries[j]["text"] == text:
                    e = self.entries[j]
                    self.pos = j + 1
                    self.hits += 1
                    self.out_of_order += 1
                    return True, e["atoms"]
            self.misses += 1
            return False, None

    def stats(self) -> dict:
        return {"entries": len(self.entries), "hits": self.hits, "misses": self.misses,
                "out_of_order": self.out_of_order,
                "coverage": round(self.hits / (self.hits + self.misses), 4) if (self.hits + self.misses) else 0.0}


@contextlib.contextmanager
def record(path: str | pathlib.Path):
    """Envuelve `mem_processor.process` para grabar cada llamada REAL. No cambia el comportamiento: delega en
    el original y guarda lo que devolvió, así la corrida grabada es también una corrida válida."""
    from nucleo import mem_processor

    t = _Tape(path)
    original = mem_processor.process

    async def _recording(text: str, *, state: dict | None = None):
        atoms = await original(text, state=state)
        t.append(text, atoms)
        return atoms

    mem_processor.process = _recording          # type: ignore[assignment]
    try:
        yield t
    finally:
        mem_processor.process = original        # type: ignore[assignment]
        n = t.flush()
        print(f"⏺  cinta del destilador grabada: {n} llamadas → {t.path}")


@contextlib.contextmanager
def replay(path: str | pathlib.Path, *, strict: bool = False):
    """Sustituye `mem_processor.process` por la cinta: cero red, cero coste, determinista.

    También fuerza `enabled()` a True — el llamador lo consulta para decidir si reintenta tras un `None`
    (`memory_agent.py:1096`), y sin esto una entrada `None` grabada no reproduciría el reintento que SÍ ocurrió
    al grabar. `strict=True` lanza ante una frase que no está en la cinta en vez de degradar a la heurística;
    útil para un test que exija cobertura total del fixture."""
    from nucleo import mem_processor

    t = _Tape(path)
    n = t.load()
    original = mem_processor.process
    original_enabled = mem_processor.enabled

    async def _replaying(text: str, *, state: dict | None = None):
        found, atoms = t.next_for(text)
        if not found:
            if strict:
                raise AssertionError(f"cinta sin entrada para {text[:80]!r} (cobertura incompleta del fixture)")
            return None                          # el llamador cae a la heurística, como con el CORAZÓN caído
        return atoms

    mem_processor.process = _replaying          # type: ignore[assignment]
    mem_processor.enabled = lambda: True        # type: ignore[assignment]
    print(f"▶  replicando la cinta del destilador: {n} llamadas desde {t.path} (sin red)")
    try:
        yield t
    finally:
        mem_processor.process = original        # type: ignore[assignment]
        mem_processor.enabled = original_enabled  # type: ignore[assignment]
