---
id: V2-016
title: Control de atención desde la UI (icono robot) + detección inteligente de interlocutor
epic: v2-colmena
status: next
priority: high
owner: ricart
modules: [frontend, voice, config]
depends_on: [V2-015]
wall_order: 16
created: 2026-07-09
updated: 2026-07-09
---

## Goal

Dar al operador control del gate de atención desde la UI y, sobre todo, hacerlo INTELIGENTE: por defecto zaelar
escucha y responde siempre (modo `always`, decidido 2026-07-09), pero debe distinguir cuándo el operador le habla
A ÉL vs cuando habla con otra persona en la sala / hay ruido de fondo / aparecen otras voces — sin obligar a decir
la wake-word.

## Contexto

V2-015 construyó el gate (`voice/attention.py`, modos `always`/`smart`/`wakeword`/`ptt`). El default `smart` dejaba
a zaelar mudo si no decías "zaelar" → se cambió el default a `always` (escucha siempre). Falta: (1) un control en la
UI para pasar a modo wake-word cuando el operador quiera (reuniones), y (2) la parte potente — inteligencia que
detecte al interlocutor incluso en `always`, para no actuar sobre lo que claramente no va dirigido a zaelar.

## Qué se construye

- **Icono 🤖 (robot) bajo el orbe**, junto a 🔊 (silenciar) y 📝 (subtítulos) en `frontend/app/components/Orb.js`:
  toggle que alterna entre `always` (OFF, default — escucha y responde a todo) y wake-word (ON — exige "zaelar/
  harvis"). Estado visual activo/inactivo como los otros iconos; aplica EN VIVO (sin reiniciar).
- **Endpoint de modo en caliente**: aplica `attention_mode` al vuelo y lo persiste en `config/settings.json` (la
  config la gestiona la UI; env = fallback). Reutiliza la costura de settings live existente.
- **Detección inteligente de interlocutor** (lo potente): incluso en `always`, gatear la ACCIÓN (no la escucha)
  cuando el turno claramente NO va dirigido a un asistente — señales a explorar: clasificador ligero "¿esto va
  dirigido a zaelar?" (orden/pregunta a un asistente vs charla entre terceros), diarización / multi-hablante,
  patrones de conversación, energía/solapamiento. Empezar por el clasificador de "addressing" (barato, off-loop) y
  medir con el tester; escalar a diarización si hace falta.

## Tareas

- [x] T139 — Icono 🤖 (robot) bajo el orbe junto a 🔊/📝 (`Orb.js`): toggle always↔wake-word, estado visual, aplica en vivo. `done` 2026-07-09 · commit 2cd7617
- [x] T140 — Endpoint/costura para cambiar `attention_mode` en caliente + persistir en `config/settings.json` (sin reiniciar). `done` 2026-07-09 · commit 2cd7617 (seam existente reutilizado)
- [ ] T141 — Detección INTELIGENTE de interlocutor: clasificador ligero "¿va dirigido a zaelar?" que gatea la ACCIÓN incluso en `always` (charla entre terceros / ruido → no actúa); off-loop, por invocación. Explorar diarización si el texto no basta.
- [ ] T142 — Verificación con el tester (operador dirigido → actúa; charla entre terceros / ambiente → no) + **pasar la revisión de alineación** (docs + diagrama + el nuevo icono).

## Aceptación

- El icono 🤖 bajo el orbe alterna entre "escucha siempre" y "solo con wake-word", en vivo, con estado visual claro.
- El modo elegido persiste (config de la UI) y sobrevive a reconexión.
- Con el clasificador de interlocutor, en `always` zaelar NO actúa sobre charla claramente no dirigida a él, sin exigir wake-word.

## Riesgos

- El clasificador de interlocutor puede tener falsos negativos (ignorar una orden real) → calibrar con el tester;
  el toggle wake-word y `always` puro siguen disponibles como respaldo.
- Diarización real puede requerir señal de audio (no solo texto) → evaluar coste antes de construirla.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T139 — Añadido tercer control 🤖 bajo el orbe en `Orb.js` (junto a 🔊/📝): toggle de dos estados (OFF/gris=`always`, ON/azul=`wakeword`) con `createSignal` local; lee el modo real al cargar (`api.getSettings` → knob `attention_mode`) y al pulsar escribe EN VIVO por `POST /api/settings` (misma costura del ⚙). Tooltip claro por estado, tema `--hb-*` (clases `.orbic .on/.off`), cero hex. commit 2cd7617.
- 2026-07-09 · T140 — El cambio de `attention_mode` aplica EN CALIENTE sin endpoint nuevo: `config/settings.update()` (ya existente) escribe `config/settings.json` + `os.environ["ZAELAR_ATTENTION"]` y `voice/attention.py::mode()` lo lee cada turno → sin reconectar. Ciclo verificado por curl: pulsar→`wakeword` en settings.json + knob efectivo refleja→volver a `always`; persiste. `voice/test_attention.py` 34/34 verde. commit 2cd7617.
