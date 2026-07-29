---
title: Monitorización de conversaciones de cluster — criterios de evaluación
category: ops
updated: 2026-07-26
owner: ricart
status: current
---

# Cómo monitorizamos las conversaciones de cluster (agente-agente) y bajo qué criterios

**Objetivo:** que nuestro agente conduzca una conversación con OTRO agente **como lo haría un humano** — sabiendo con
quién habla, si la cosa avanza, sin dejarse robar recursos, acordando cómo trabajar, y **sabiendo cuándo parar**.

**Frontera dura:** esto aplica SOLO al canal **agente-agente (cluster)**. Con el **operador** (voz/chat) y con
**humanos** (WhatsApp/email) la conversación debe **fluir siempre** — nada de esto la frena. El túnel entre modelos es
el único que necesita regularse (capacidades desiguales, riesgo de perder el tiempo o de aprovechamiento).

## Cómo se monitoriza (dos capas + observabilidad)

1. **Capa determinista, en el bridge (tiempo real, cada turno).** Barata, sin LLM, fail-open. Es el reflejo: mide,
   decide y actúa en el momento (`connectors/meshkore/bridge.py` + `capsule.py` + `security.py`).
2. **Capa semántica, cron cada minuto (`39704ee7`, de sesión).** Un modelo lee el intercambio reciente y juzga con
   criterio lo que la heurística no caza (sinsentido, desajuste de capacidad). Interviene/avisa si va a ninguna parte.
   *(F1: promoverla a pieza DURABLE como homeostasis — hoy muere al cerrar la sesión de Claude.)*
3. **Observabilidad.** Todo deja rastro en el timeline (`kind:cluster` con `pace`/`stall`, `kind:resource`,
   `kind:homeostasis`), y **cada evento lleva `ver`** (V2-074) → se sabe qué versión evaluó cada línea. El watchdog de
   salud (`f2b5904a`, cada 15 min) vigila que el canal siga en pie.

## LOS CRITERIOS (la lista con la que se evalúa)

Cada criterio = **comportamiento humano** que emula · **mecanismo** · **señal/umbral** · **qué hace** · **a mejorar**.

### 1. ¿Sé con quién hablo y en qué punto estamos? — SITUACIÓN (V2-069, cápsula)
- **Humano:** recuerdas quién es cada uno, de qué hablasteis, qué quedó pendiente y en qué fase estáis.
- **Mecanismo:** cápsula por-peer (dossier + objetivo + bucles abiertos + FASE saludo→sondeo→trabajo→cierre).
- **Señal:** fase derivada del estado de la relación.
- **Hace:** no re-presentarse en trabajo/sondeo; conducir hacia el objetivo; no re-negociar lo ya decidido.

### 2. ¿La conversación FLUYE o no tiene sentido? — SALUD por INTELIGENCIA (V2-075; antes V2-073)
- **Humano:** das un paso atrás y valoras si la charla merece la pena; si el otro no te sigue, se repite, está
  bloqueado o dice cosas sin sentido, PARAS y cedes el turno.
- **Mecanismo (CLAVE):** el juicio semántico lo hace un **MODELO**, no patrones hardcodeados (`evaluator.py`):
  evaluador INDEPENDIENTE, read-only, catálogo CERRADO `health`(flowing/stuck/dead_end/imbalanced/off_track) ×
  `action`(continue/concise/hand_back/pause), fail-open. Genérico → sirve para CUALQUIER agente y CUALQUIER forma de
  degenerar. Único apoyo determinista: repetición EXACTA (dedup, tokens) + `near_repeat` (casi-repetición, señal).
- **Cuándo:** off-hot-path, en el heartbeat, throttle `MESHKORE_EVAL_SECS`, solo charlas ACTIVAS (no re-juzga una
  muerta). Es un juicio de «paso atrás», no un reflejo por turno.
- **Hace:** aplica el veredicto del modelo — `hand_back` (cede el turno con una frase y espera) · `pause` (calla +
  avisa al operador 1×) · `concise` (el próximo turno va breve) · `continue` (no interrumpe). Evento `dir:eval` con
  el veredicto en el timeline.

### 3. ¿Hay EQUILIBRIO de recursos? — NO NOS ROBAN TOKENS (V2-071)
- **Humano:** no dejas que te endosen todo el trabajo; colaboras de igual a igual.
- **Mecanismo:** balance por-peer (`given`/`received`/`offloads`/`code_out`) + `looks_like_offload` (peticiones de
  producir) + `guard_code_outbound` (volcado de código → puntero al repo).
- **Umbral:** `equilibrado` <3× · `sesgado` ≥3×+offload · `explotación` ≥6×+offload sostenido (min turns 4, given 1500).
- **Hace:** silencio hacia el peer + sé breve · código por el repo · aviso al operador 1× en explotación. Eventos
  `kind:resource`.

### 4. ¿Hemos ACORDADO cómo trabajar? — PACTO (V2-072)
- **Humano:** pactas normas de trabajo con el otro y las respetas mientras convenga.
- **Mecanismo:** pacto por-peer (cadencia/medio/alcance), vocabulario CERRADO; tag `[[cluster.pact]]`; se propone al
  saludar; jerarquía **sistema > operador > pacto** (un pacto nunca afloja lo de arriba).
- **Hace:** inyecta las normas en el turno + **cadencia REAL** (throttle en `cluster.send` → no bombardear).

### 5. ¿Es SEGURO? — PROTECCIÓN (seguridad del cluster)
- **Humano:** no te fías de un desconocido: no revelas lo tuyo, no actúas por él.
- **Mecanismo:** tools APAGADAS (perfil untrusted) · identidad-safe (no PII del operador) · `scan_outbound`
  (bloquea secretos) · fence + trailer al final (anti-inyección) · allowlist de tags · flood cap.

### 6. ¿La MÁQUINA está sana? — HOMEOSTASIS (V2-070)
- **Humano:** tu cuerpo se mantiene solo (no piensas el latido). Sostiene el canal, no es de conversación.
- **Mecanismo:** recicla el motor LiveKit degradado (si es seguro), rota logs, evicta cápsulas muertas. Determinista.

### 7. ¿Sé qué VERSIÓN evalúa? — TRAZABILIDAD (V2-074)
- **Mecanismo:** `version.short()` (`2.74+sha`) en `/api/status`, en `ver` de cada evento y en el frontend (◉).
- **Uso:** el `sha` de `/api/status` == `git HEAD` prueba que una instancia corre lo último; se auditan las líneas de
  tiempo por versión.

## Cómo se ve «todo va bien» vs «hay que intervenir»

- **Bien:** fase coherente (no re-presentación), `no_progress` bajo, ratio de recursos <3×, sin `pace:silent` ni
  `resource:explotación`, el peer aporta, el canal conectado, sin errores en el timeline.
- **Intervenir:** `no_progress` subiendo → ceder turno; ratio ≥3× + offload → acortar/repo; repetición → asertivo→callar;
  peer incoherente/desajuste de capacidad → pausar y esperar; siempre avisar al operador 1× por incidente.

## Qué necesitamos para MEJORAR (backlog vivo, orden de valor)

1. **Cron de calidad → pieza DURABLE** (como homeostasis): hoy es de sesión y muere al cerrar Claude. La capa
   determinista sí es durable; la semántica no.
2. **El juicio semántico es por MODELO, no hardcodeado (rediseño 2026-07-26, decisión del operador).** El primer
   intento (V2-073) usaba un regex de frases (`looks_stuck`) y, al aparecer un patrón nuevo (zalo bloqueado por su
   dependencia «Poli»/503), la reacción instintiva fue *añadir esas frases al regex* — exactamente el error: eso solo
   se adapta a UN peer y falla con el siguiente. **Corregido en V2-075:** el juicio lo hace `evaluator.py` (modelo,
   genérico); el regex de frases se ELIMINÓ. A afinar aún: la ventana/throttle del evaluador, fundir la señal de
   recursos dentro del mismo veredicto, y validar el coste del modelo periódico con varias charlas simultáneas.
3. **Exponer el estado por-peer en `/api/meshkore/status`** (balance de recursos + pacto + salud de conversación +
   `no_progress`) para verlo de un vistazo, no solo por el timeline.
4. **Pacto:** endpoint para que el OPERADOR fije/consulte normas; negociación multironda; pacto a nivel de clúster.
5. **Reciprocidad más rica** que chars (contar aportes reales del peer, p.ej. commits al repo).
6. **peer→worker: el gate llegó (V2-076, 2026-07-26) y el jail de filesystem se cerró (auditoría 2026-07-26)** —
   permiso `code` por-cluster + objetivo fijado por el operador (`capsule.objective`, tool `set_cluster_objective`,
   guard `perms.gate_dev_by_objective`) habilitan un dev-worker acotado (cwd temporal + git al repo autorizado +
   confinamiento REAL de Read/Write/Edit vía `nucleo/dev_worker_guard.py`, un hook PreToolUse — ver
   `zaelar-security.md`). **Susurro sobre cluster** (auto-auditoría de conversaciones de cluster, distinto del
   evaluador V2-075 que ya audita salud/ritmo) sigue SIN construir — no es lo mismo que el gate peer→worker de
   arriba.
7. **Métricas históricas** de calidad de conversación por-peer (tendencia, no solo instante).

## Fuentes

Detalle por iniciativa: `.meshkore/roadmap/initiatives/V2-069…074`. Contexto: `CLAUDE.md` (decisiones «una sola
mente», recursos, jerarquía de reglas/pacto, ritmo, homeostasis, versión). Seguridad: `zaelar-security.md`.
Observabilidad: `zaelar-observability.md`.
