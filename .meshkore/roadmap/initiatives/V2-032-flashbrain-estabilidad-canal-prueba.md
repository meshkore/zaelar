# V2-032 — Estabilidad conversacional del FlashBrain + canal de prueba headless

**Estado:** DONE (2026-07-12). Origen: informe de iteración 2026-07-12 (bloqueante #1 = estabilidad conversacional
del FlashBrain). Hermano de **V2-033** (precisión de escritura de memoria, handoff al equipo de memoria).

## Problema

El modelo pequeño no-razonador (Grok-fast) DEGENERA bajo repetición: repite la misma frase turno a turno ("No
tengo acceso…" ×5), empalma plantillas ("Déjame comprobar Déjame comprobar") y pierde el hilo (ejecuta una acción y
al turno siguiente responde "no te entendí"). No había gestor de diálogo ni control anti-degeneración. Además, para
ARREGLARLO hacía falta una forma **rápida** de inyectar texto al FlashBrain y leer su respuesta sin voz/interfaz.

## Qué se hizo

### 1. Defensas de diálogo — `nucleo/flash/dialog.py` (deterministas, es/en, sin LLM)
- **`loop_nudge(window)`** — BREAK-LOOP: si el asistente lleva ≥2 respuestas casi idénticas, añade al system prompt
  una instrucción que OBLIGA a cambiar de estrategia (reformular / admitir el límite / preguntar otra cosa).
- **`prune_window(window)`** — colapsa respuestas de asistente gemelas antes de reinyectarlas (el modelo deja de
  ver el patrón y de continuarlo).
- **`sanitize_reply(text)`** — anti-degeneración del output: colapsa palabras/frases duplicadas y empalmes. Se aplica
  a lo que se GUARDA en la ventana → corta el bucle de realimentación que degrada al modelo.
- Compartidas por el turno de VOZ (`voice/engine/llm/providers/nucleo.py::_run`) y el canal de prueba → lo que se
  valida por texto corre igual en voz. Tests: `tests/agent_headless/unit/flash/test_dialog.py` (11).

### 2. Canal de prueba headless — `nucleo/flash/probe.py` (3ª forma de testing)
- `run_turn(text, sid, ingest)` reproduce el NÚCLEO del turno real (mismo `build_flash_system`, `FastClient`,
  `router.TOOLS`, `dialog.py`) sin audio ni ejecución de widgets: en vez de actuar, REPORTA la acción (tool/tag) +
  el texto + latencias + señales (`degenerate`, `loop_run`, `prompt_chars`).
- HTTP `POST /api/flash/say` y `POST /api/flash/reset` (montados con `BRAIN=nucleo`, `server/__init__.py`).
- CLI `python -m nucleo.flash.probe` (one-shot / REPL / `--json`).
- Makefile: `make flash-serve` (server headless), `make flash T="…"` (one-shot), `make flash-repl` (interactivo).
- Documentado en CLAUDE.md (§tercera forma de testing) y `zaelar-testing.md`.

## Validación
- `make flash-serve` + `curl /api/flash/say` en vivo (db temporal aislada): turno real, ~0.9 s, JSON evaluable.
- `test_dialog.py` verde (anti-degeneración, break-loop, poda).

## Fuera de alcance → V2-033
La precisión de ESCRITURA de la memoria (el CORAZÓN guarda ruido/garble/preferencias efímeras como durables) es
trabajo del equipo de memoria: ver `.meshkore/roadmap/initiatives/V2-033-memoria-precision-escritura.md`.
