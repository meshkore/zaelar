# V2-073 — Criterio de ritmo / no-progreso en conversaciones agente-agente

**Estado:** F0 CONSTRUIDO (rama `feat/v2-069-una-sola-mente`, commit engine `407a988`). 2026-07-25.

## Origen

Petición del operador viendo la conversación con zalo en vivo: con el OPERADOR la conversación debe FLUIR siempre,
pero con agentes externos (otros modelos de **menos capacidad** que nos hacen perder el tiempo o llegan a puntos sin
sentido) hacen falta **mecanismos de inteligencia para valorar con criterio si fluye** y, si no, **parar, relajar,
dejar avanzar a la otra parte y quedarnos a la espera** — como un humano que ve que su interlocutor no le sigue: deja
de exponer ideas y espera. Además pidió **recuperar el cron cada minuto** que repasa de qué están hablando y si tiene
sentido.

## Auditoría que lo motiva (datos reales)

`meshkore.jsonl`, cluster `meshcore`: **zalo estaba embuclado en una compuerta de fase** — repetía, VARIANDO la
redacción, «⛔ Estamos en fase Definición aún. No puedo discutir Diseño/Desarrollo hasta que cerremos la fase actual.
¿Avanzamos con la…?» — mientras **zaelar bombardeaba** con listas de features/HMM cada vez más detalladas. El guardia
de atasco V2-069 caza la repetición EXACTA (y disparaba `(repetido, ignorado)` en algunos), pero zalo variaba lo
justo para colarse → no acumulaba → no parábamos. Interacción entre modelos de capacidad desigual, sin sentido.

## Principio

El «criterio humano» en código, en DOS capas (como homeostasis: determinista + reflexión periódica). Solo para el
canal agente-agente (con el operador siempre se fluye). No es un sistema nuevo: extiende el guardia de atasco de la
cápsula (de repetición EXACTA a NO-PROGRESO semántico) y añade la cesión de turno.

## Arquitectura

- **Capa 1 — determinista, en el agente (durable):**
  - `capsule.looks_stuck(text)`: frases de BLOQUEO (es) + `⛔`/`🚫` — «no puedo avanzar/discutir», «estamos en fase»,
    «un momento», «sigo esperando», «todavía no», «hasta que cerremos»…
  - `capsule.near_repeat(text, recent)`: casi-repetición por **CONTENCIÓN de tokens** normalizados (robusta a que el
    peer reescriba el mismo núcleo con relleno distinto). Ignora mensajes muy cortos.
  - `capsule.advanced(text, recent)` = `not (looks_stuck or near_repeat)`.
  - En el bridge (turno de mensaje nuevo): anillo de los últimos ~5 textos del peer; si NO avanza, `no_progress++`
    en la cápsula; `stall_verdict(0, no_progress, m=PACE_HANDBACK_AT=3)` decide:
    - `asertivo` (a los 3 sin avance) → **cede el turno**: la mente manda UN mensaje breve (`capsule.PACE_HANDBACK`:
      reconoce ir muy rápido, propone parar, pide que avise cuando esté listo) y para.
    - `callar` (a 2× = 6) → **silencio** (deja de responder) + **avisa al operador 1×**.
    - entre medias, tras ceder el turno → NO bombardea (silencio de espera).
  - **Reset al primer avance real** (`advanced` → `no_progress=0`, sale de pausa).
- **Capa 2 — cron cada minuto (revisión semántica, la que pidió el operador):** un modelo lee el intercambio reciente
  del cluster y juzga si FLUYE o es un sinsentido / desajuste de capacidad; si va a ninguna parte y la capa 1 no lo
  cortó, interviene (cesión de turno vía `POST /api/meshkore/send`) + avisa al operador. Solo actúa si hay actividad
  nueva; no spamea. Sesión (como el watchdog de salud). [Montado como cron de sesión el 2026-07-25.]

## Invariantes

- SOLO canal agente-agente. Con el operador la conversación siempre fluye (esta lógica no lo toca).
- Determinista y barato en la capa 1 (sin LLM en el turno). Fail-open (un fallo del criterio no rompe el turno).
- No re-presentarse ni reabrir tras ceder el turno; se espera a que el peer aporte algo NUEVO.

## Testing

`tests/cluster/unit/test_pace.py` (17) con los mensajes REALES de zalo: detección de bloqueo, casi-repetición
reescrita, `advanced`, progresión del veredicto (seguir→ceder→callar), la directiva de cesión. **Nodo 6.7** del mapa.
126/126 meshkore verdes.

## Fases

- **F0 (hecho):** capa 1 determinista (looks_stuck/near_repeat/advanced + cesión de turno + silencio + aviso) +
  cron de revisión semántica + tests + docs.
- **F1 (abierto, no deuda):** promover el cron a pieza DURABLE (como homeostasis, que no muera con la sesión);
  afinar umbrales/contención con datos reales; exponer «salud de la conversación» por-peer en `/api/meshkore/status`
  (junto a balance de recursos y pacto); que el criterio semántico alimente el pacto (proponer cadencia/alcance
  cuando detecta desajuste de capacidad).
