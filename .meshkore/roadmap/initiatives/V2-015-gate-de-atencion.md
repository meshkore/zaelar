---
id: V2-015
title: Gate de ATENCIÓN — el micro abierto no actúa sobre lo que no le hablan
epic: v2-colmena
status: done
priority: critical
owner: ricart
modules: [voice, nucleo, connectors, frontend]
depends_on: [V2-004]
wall_order: 15
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09T14:36:47.433Z
commit_sha: fe04f7e8f46ca56788dda5b716d14230a8fae6d0
---
## Goal

Con el micro siempre abierto, zaelar trataba TODO lo oído como órdenes: en una reunión (o hablando con otro
agente) capturó voz ambiente, alucinó, abrió widgets, escaló tareas y no atendió a tiempo un "cierra los widgets".
Construir un **gate de atención**: zaelar solo ACTÚA cuando el turno va dirigido a él; el resto lo ignora.

## Diagnóstico (2026-07-09, timeline 16:09–16:15)

471 transcripts / 546 STT en minutos = una reunión entera capturada. STT en bucle sobre audio ambiente
("sí sí sí", "UOL UOL UOL"). zaelar ACTUÓ sobre frases ambiente: abrió la agenda ("abro mi agenda"), escaló al
SlowBrain ("quítame el descanso…"), inventó respuestas ("¿es la Taurus?"). El "cierra los widgets" se pidió a las
16:12:54 y 16:13:01 pero el `close` no llegó hasta 16:14:25: a las 16:13:16 el log muestra
`✂️ input recortado 14076→1600 chars` — el turno nunca terminó (voz continua), se acumuló un turno gigante y el
comando real quedó FUERA del recorte. Causa raíz: **sin gate de atención** + turn-taking roto por voz continua →
turnos gigantes que **entierran/truncan los comandos** + triaje de mensajería inyectando notas en cada turno.

## Qué se construye (diseño decidido)

- **Gate de atención** (`ZAELAR_ATTENTION` = `smart` | `wakeword` | `ptt` | `always`, default **`smart`**):
  un turno se considera **dirigido a zaelar** si (a) contiene wake-word ("zaelar" / "oye zaelar"), o (b) cae dentro
  de una **ventana de conversación activa** (N s tras un turno dirigido previo). Un turno **no dirigido NO produce
  acción NI respuesta** (se registra como `ambient` en el observer, no se ejecuta). `wakeword` = exige siempre
  wake-word; `ptt` = push-to-talk (botón/tecla); `always` = comportamiento antiguo (todo es turno).
- **Fin de turno acotado + comando preservado**: cortar el turno por silencio/longitud razonable (nunca acumular
  miles de chars); si hay que recortar, **priorizar el comando explícito** (cerrar/parar/mostrar) en vez de truncar
  a ciegas los últimos N chars.
- **Interrupción DURA siempre atendida**: "cierra/para/silencio/stop" se ejecuta de inmediato (barge-in + comando),
  aunque haya un turno en vuelo o cola; nunca queda enterrada.
- **Throttle del triaje de mensajería**: no inyectar system-notes en cada turno (agrupar/limitar); no abrir widgets
  desde audio no dirigido.
- **Señal en la UI/observer**: el operador ve cuándo zaelar está "escuchando pero no atendiendo" (ambient) vs
  "atendiendo".

## Tareas

- [x] T134 — Gate de atención (`ZAELAR_ATTENTION`, default `smart`): wake-word + ventana de conversación activa; turno no dirigido → `ambient`, sin acción ni respuesta. Config gestionada por la UI (⚙), no solo env.
- [x] T135 — Fin de turno acotado + preservación de comando: cap de longitud/silencio; al recortar, priorizar el comando explícito (nunca truncar un "cierra/para/muestra").
- [x] T136 — Interrupción DURA "cierra/para/silencio/stop": atendida de inmediato aunque haya turno/cola en vuelo.
- [x] T137 — Throttle del triaje de mensajería (no inyectar en cada turno; agrupar) + no disparar widgets desde audio no dirigido.
- [x] T138 — Verificación con el tester (simular audio ambiente/no dirigido: zaelar NO actúa; dirigido: sí) + señal UI ambient/atendiendo + **pasar la revisión de alineación** (docs + diagrama).

## Aceptación

- Con audio ambiente/no dirigido (una reunión), zaelar **NO abre widgets, NO escala, NO responde** — solo registra `ambient`.
- Un turno dirigido (wake-word o conversación activa) sí se atiende con normalidad.
- "Cierra los widgets / para / silencio" se ejecuta **siempre y de inmediato**, aunque haya ruido o cola.
- Ningún turno acumula miles de chars ni trunca un comando explícito.
- El triaje de mensajería no inunda el FlashBrain con notas por turno.

## Riesgos

- El gate `smart` no debe volverse molesto (pedir wake-word en mitad de una conversación real con zaelar) → la
  ventana de conversación activa lo cubre; ajustable por la UI.
- No romper la UX "siempre activo": `always` sigue disponible; `smart` es el default seguro.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T134 — Gate de atención `voice/attention.py` (`ZAELAR_ATTENTION` smart|wakeword|ptt|always, default smart) cableado en `nucleo.py::_run`: turno no dirigido → evento `ambient`, retorna sin actuar ni drenar notas. Wake-word "zaelar" + variantes fonéticas + ventana activa (`ZAELAR_ATTENTION_WINDOW` 30s). Chat/paste = dirigido; PTT por topic `zaelar-ptt`; reset por sesión. Config por la UI (⚙, `config/settings.py`).
- 2026-07-09 · T135 — `clamp_input()` acota el turno (`ZAELAR_FAST_MAX_INPUT` 1600) PRESERVANDO el comando explícito (cierra/abre/muestra/para): ya no se trunca a ciegas los últimos N chars (era como el "cierra los widgets" caía fuera del recorte de un turno de 14k).
- 2026-07-09 · T136 — `hard_interrupt()` ejecuta cierra-todo/para/silencio de inmediato, DETERMINISTA, sobre el texto completo y ANTES del gate → nunca queda enterrado en un turno gigante.
- 2026-07-09 · T137 — `connectors/messaging/notify.py` agrupa la nota `[SISTEMA]` por ventana (`_NOTE_GAP` 90s) en vez de una por batch/turno; deja de inundar el FlashBrain.
- 2026-07-09 · T138 — Verificado con el tester (zaelar vivo, nucleo, Ollama): turno ambiente → 1 evento `ambient`, 0 widgets, 0 escaladas, 0 respuesta; turno con wake-word (STT "Harvey" captado por la variante fonética) → atendido; siguiente turno dentro de ventana → atendido. Revisión de alineación pasada.
- 2026-07-09 · Ajuste de diseño (dentro de T134): el kickoff (saludo de zaelar) NO abre la ventana — evita un hueco inicial en el que la voz ambiente al arrancar en una reunión se cuele como dirigida y auto-extienda la ventana. El operador abre la conversación con la wake-word.
