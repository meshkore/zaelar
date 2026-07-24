# Ciclo de 1000 — memoria — resultados 2026-07-12

**GOLD (pasada de oro fresca 0→1032): 1032/1032, 0 ❌.**

- `gold-report.json` — report completo de la pasada de oro (cada request + capa + resultado).
- `tabla-1000-requests.html` — tabla navegable de las 1032 requests (tipología·capa·ancla·resultado) + resumen.
  Copia también en `~/.meshkore/tmp/zaelar-ciclo-1000-memoria.html`.

## Resumen
- **1032 requests** verificadas en verde por el camino REAL (escritura CORAZÓN LLM local + lectura FlashBrain sin LLM).
- **29 dimensiones** (A–Y + Z/AA/AB/AC). Núcleo ESTADO(A+Y)=64 · CORTO(B)=102 · LARGO(C)=206.
- **9 bugs de código reales** arreglados como mejora (no se ablandó ningún test). Ver playbook en
  `.meshkore/docs/ops/anexos/zaelar-memory-cycle-playbook.md` y la bitácora por ola en INI-013.
- Fronteras honestas documentadas: no-determinismo del CORAZÓN (~1-2% flaky) y recall-a-escala del embedding local
  (T176) — no son bugs, son límites del modelo; se prueban con anclas robustas.

## Cómo reproducir
Ver el playbook: `.meshkore/docs/ops/anexos/zaelar-memory-cycle-playbook.md`.
