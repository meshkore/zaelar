---
title: Zaelar Audit Workflow
category: ops
updated: 2026-07-09
owner: ricart
status: current
---

# Workflow de auditoría de zaelar — "pasa la auditoría"

**Disparador:** cuando el operador dice **"pasa la auditoría"** (o "audita el sistema", "revisa que todo está
bien construido"), el agente ejecuta ESTE workflow de principio a fin. El objetivo es tener un procedimiento
**repetible** para, cada vez que el proyecto evoluciona (nueva feature, refactor, módulo nuevo), volver a
verificar que **el código, la arquitectura, la documentación canónica y el módulo de seguridad siguen alineados**
— sin depender de recordar de memoria qué mirar.

> Alcance: revisión **completa** del sistema. Para revisar solo un dominio (p. ej. tras tocar widgets), correr
> únicamente la fase de fan-out de ese dominio (§3) + la fase de alineación docs (§4). El workflow completo es el
> que se corre en hitos: antes de un release mayor, tras un refactor de estructura, o cuando el operador lo pide.

> Complementa a [[zaelar-change-protocol]]: el *change protocol* cierra **un** cambio; **este** workflow audita
> **todo el sistema** de forma transversal. Se pueden encadenar (auditar → arreglar → pasar el protocolo de cada fix).

---

## 0. Principios de esta auditoría (cómo se mira, no solo qué)

1. **La fuente de verdad es el código, la documentación es la hipótesis.** Cada claim documentado se verifica
   contra el código con evidencia `fichero:línea`. No se confía en los nombres — un módulo llamado `security.py`
   no está auditado hasta leer lo que hace.
2. **Skeptical / adversarial.** En seguridad no basta con confirmar que el control existe: hay que **intentar
   romperlo** pensando como un atacante (peer no confiable en el cluster, dato del brain hacia un widget, etc.).
3. **Fan-out por dominios en paralelo.** El sistema se parte en dominios independientes y se lanza **un subagente
   por dominio a la vez** (`Agent`/`general-purpose`, en paralelo). Cada uno devuelve un informe estructurado; el
   agente principal **sintetiza**, no re-hace el trabajo.
4. **Alineación en tres capas.** Todo lo que se descubra debe coincidir con: (a) el **diagrama + módulos** de
   `.meshkore/docs/architecture` y `modules`, (b) el **contexto** de `.meshkore/docs/product` + `security`, y (c)
   los **diagramas públicos** de `/technology` (`web/src/pages/technology/*.astro`), que son doc de cara al
   usuario y deben reflejar el estado actual (aunque, desde 2026-07-24, su sync ya no es automático — es un paso
   MANUAL; una deriva aquí es de menor urgencia que en el resto, ver nota abajo). Toda deriva se reporta como fix concreto.
5. **Salida = informe + plan priorizado.** El entregable es un informe con hallazgos por severidad y un **plan de
   mejora priorizado P0→P3**. El informe HTML va a `~/.meshkore/tmp/*.html` (ver [[feedback-reports-local]]),
   **nunca** como artifact.

---

## 1. Fase de reconocimiento (situarse — SIEMPRE primero)

Leer, en este orden, para cargar el modelo mental antes de tocar nada:

1. **`CLAUDE.md`** (raíz) — reglas duras, decisiones clave, layout de módulos, protocolo de cambio.
2. **`.meshkore/public/cluster.yaml`** — módulos declarados + `admission` (reglas de proyecto) + `version`.
3. **Contexto canónico** (`.meshkore/docs/`):
   - `product/zaelar-product.md` — qué es zaelar, las piezas, contratos, decisiones (single source of truth de onboarding).
   - `architecture/zaelar-architecture.md` — modelo mental, seams, cómo encajan el cerebro `nucleo/`, `memory/` y
     `bus/`, diagrama ASCII.
   - `architecture/zaelar-memory.md` — diseño de la memoria central (SQLite `zaelar.db`, retriever, consolidador).
   - `modules/zaelar-modules.md` — tabla de módulos + mapa detallado del frontend + del connector meshkore.
   - `security/zaelar-security.md` — modelo de amenaza y controles del canal de cluster (el módulo de seguridad).
4. **Estructura real del repo** — listar ficheros fuente (excluyendo `.venv/.git/.pytest_cache/node_modules`) y
   `git status --short` (para detectar trabajo sin commitear, p. ej. widgets nuevos).
5. **Los diagramas públicos** — `web/src/pages/technology/*.astro` + `web/src/lib/diagrams/*.ts` (el panel interno
   `frontend/pages/architecture.html` se RETIRÓ el 2026-07-24): doc curada de cara a fuera, entra en la
   comparación de alineación (§4) pero con prioridad menor — ya no es un espejo automático del código.

Referencias de contexto vivo DENTRO del repo (el cerebro es NUESTRO, ya no hay agente externo): `config/v2.json`
(routing de modelos real `fast`/`code_agent`, gestionado por la UI) y la memoria central `memory/_data/zaelar.db`
(persona + hechos del operador). Único resto externo: `~/.hermes` es solo la fuente de un **seed one-shot** de solo
lectura (`memory/seed_from_hermes.py`) — leer si el hallazgo lo requiere, **no** modificar.

---

## 2. Dominios de auditoría (el sistema partido en piezas)

zaelar se audita en **cuatro dominios**. Son los mismos cuatro cada vez — se amplían si aparece un módulo nuevo
(entonces se añade su dominio o se asigna al más cercano).

| # | Dominio | Cubre | Docs de referencia |
|---|---|---|---|
| A | **Núcleo voz + cerebro (nucleo) + memory + bus + server** | `voice/`, `nucleo/` (FlashBrain + SlowBrain), `memory/`, `bus/`, `server/`, `config/` — pipeline, dos velocidades, escalado, memoria central, sistema nervioso, routers, settings | architecture §0-8, memory (todo), product §2/§4/§5 |
| B | **Frontend + widgets** | `frontend/`, `widgets/` — shell reactivo, aislamiento de widgets, contrato de widget, generador, SSE | modules §Frontend, architecture §1-5, product §2/§4/§6, `widgets/AGENTS.md` |
| C | **Seguridad del canal cluster** | `connectors/meshkore/` (canal en perfil untrusted: `brain.py`→`nucleo/flash/cluster.py`, tools off) + controles duros en `security.py`, `bridge.py`, `voice/tag_protocol.py` | security (todo), logs MK-003/MK-004 |
| D | **Alineación docs ↔ código ↔ cluster.yaml** | los `.meshkore/docs/`, `cluster.yaml`, roadmap/initiatives, los diagramas de `/technology` (web/), `CLAUDE.md`, `.env.example`, Makefile | modules, product, architecture, ops, todo el estándar |

**Regla del estándar MeshKore:** cada dominio mapea a los módulos declarados en `cluster.yaml`. Si se declara un
módulo nuevo (p. ej. `importers/` cuando exista), **añadir su chequeo al dominio correspondiente** aquí.

---

## 3. Fan-out: qué verifica cada dominio (los checkpoints)

Lanzar **un subagente `general-purpose` por dominio, en paralelo** (todos en el mismo mensaje). A cada uno se le
da: (a) el contexto de §1, (b) su lista de checkpoints de abajo, (c) el formato de salida (§5). Cada subagente
lee el código real y devuelve, por checkpoint, **VEREDICTO (OK / DRIFT / BROKEN) + evidencia `fichero:línea` +
explicación de una línea**, y al final una lista de **Findings ordenados por severidad**.

### Dominio A — Núcleo voz + cerebro (nucleo) + memory + bus + server
1. **Entrypoint + composition root**: `python -m server` (`server/__main__.py`); `server/__init__.py create_app`
   monta routers y arranca en el lifespan el worker LiveKit EMBEBIDO, el loop de `nucleo/`, el supervisor de widgets
   `backed` y el consumidor de la cola de `memory/`. Mapear qué routers hay y cómo se montan.
2. **Montaje condicional por cerebro**: `active_brain()` (env-first `BRAIN`, default `nucleo`; `direct`/`local` =
   baselines pelados) decide qué se monta; el loop orquestador + `/api/cron` **solo** con `BRAIN=nucleo`. La UI debe
   consultar `/api/brain` antes de hacer polling. Nada específico de un cerebro cableado sin condición.
3. **Dos velocidades — FlashBrain**: `nucleo/flash/` (provider `voice/engine/llm/providers/nucleo.py`) atiende cada
   turno en ~1s con modelo POR INVOCACIÓN (no env global) y decide cuándo escalar. Verificar que sus tools reales
   `escalate_to_slowbrain`/`set_style_directive` están declaradas en `nucleo/flash/router.py` y que el escalado
   está forzado en código (no solo en el prompt) para lo que el Flash no puede hacer.
4. **Dos velocidades — SlowBrain**: `nucleo/dispatch.py` compone el prompt [contexto+tarea] → `CodeAgent`
   (`nucleo/agentes/`) async, consume `escalate.requested` del bus y entrega por `voice/proactive` (voz+UI);
   `nucleo/memory_agent.py` es el ÚNICO escritor de `memory/`. Buscar que el SlowBrain nunca bloquee la ruta caliente
   de voz y que el modelo del CodeAgent sea por invocación (`config/v2.py` sección `code_agent`).
5. **Loop orquestador + cron PROPIO**: `nucleo/loop.py` (~1 Hz) + `nucleo/scheduler.py` (cron respaldado por
   `memory.journal`) + `nucleo/cron_api.py` (`/api/cron`) + `nucleo/sparks.py` (chispas doble-gate) — tareas
   programadas + proactividad + dispara el consolidador de memoria off-hot-path. Un solo loop, montado en el
   lifespan; buscar doble-start o rutas que lo arranquen fuera del lifespan.
6. **Coordinación de turnos loop-agnóstica**: la voz corre en el job-thread de LiveKit, uvicorn en otro loop → la
   entrega cross-loop usa `bus.emit_sync`/`call_soon_threadsafe` (`bus/`), NO un `asyncio.Lock` compartido. El
   turn-taking/VAD/barge-in los gobierna LiveKit (VAD Silero + turn-detector). Verificar que no reaparece un lock
   que asuma un solo event loop.
7. **Orden del pipeline** en `voice/engine/pipeline/agent.py` (`input → VAD → stt → brain(nucleo) → tts → output`);
   STT/TTS fuera del event loop; el motor LiveKit es dueño de streaming/turnos/barge-in/preemptive-gen.
8. **Tag protocol** (`voice/tag_protocol.py` + el provider `nucleo.py`): tags nunca llegan a TTS, seguridad de tag
   partido entre chunks, qué tags se reconocen (widget + `msg.*` + `cluster.*` + `cron.*` + `architect.*`).
9. **Sistema nervioso** (`bus/`): pub/sub in-process (fnmatch + `emit_sync` cross-loop), `bus/log.py` log durable
   SQLite, `bus/sse.py` puente SSE (`GET /events`). Verificar que las señales clave (`escalate.requested`,
   `memory.updated`, `widget`, `observer`) tienen productor y consumidor, y que nada introduce un broker externo.
10. **Memoria central** (`memory/`, ver `zaelar-memory.md`): un solo SQLite `zaelar.db` (WAL); **único escritor** =
    `nucleo/memory_agent.py` vía la cola/writer; el retriever lee en la ruta caliente (ms). Verificar que no hay un
    2º escritor directo, que la capa episódica absorbió el antiguo `files/` (upload en `memory/server_api.py`), y que
    `seed_from_hermes.py` es solo-lectura best-effort.
11. **Layering / imports**: ¿`voice/` importa internals de `nucleo/`/`memory/`/`widgets/`/`connectors/` directo (el
    acoplamiento debe ir por el provider `nucleo.py` + `bus/`, no por rutas internas)? ¿`nucleo/` importa `voice/`?
    ¿algo importa `server/` hacia arriba? Mapear aristas reales y marcar las no documentadas.
12. **Config**: `config/settings.py`→`settings.json` (⚙) y `config/v2.py`→`v2.json` (routing `fast`/`code_agent`)
    se aplican al boot; vista pública redactada (secretos → `<clave>_set: bool`); buscar modelos RAZONADORES ofrecidos
    para el path de voz (regla dura) o una env global de modelo (viola "por invocación"), y deriva con docs.
13. **Dead code / orphans / bugs**: comprobar si módulos sueltos están cableados o son restos (p. ej. `files/` como
    shim, `endpointing.py` como referencia); restos de `brains/` que ya no existen; TODOs; bugs a la vista.

### Dominio B — Frontend + widgets
1. **Estructura del frontend** coincide con el mapa documentado (core reactivo Solid-compatible, dom.js `h()`,
   store, services framework-free, components, lib, `widgets/desktop.js`). Marcar lo presente-no-documentado y
   lo documentado-ausente.
2. **"Sin lógica de negocio en el cliente"**: services/components no deben llevar lógica que va en servidor.
3. **Aislamiento de widgets (CLAIM CLAVE)**: cross-imports en ambos sentidos (`widgets/*.py` ↔ `voice/`/`nucleo/`/
   `server/`/`connectors/`; y si el core importa widgets más allá del bridge `widgets/brief.py`). Un widget roto
   NO puede tumbar el audio; un owner `backed` que revienta lo aísla el supervisor (`widgets/supervisor.py`).
   `desktop.js` solo habla el contrato HTTP de widgets.
4. **Contrato + XSS por widget**: auditar CADA carpeta `widgets/<id>/` — manifest completo, `render(el,data,ctx)`,
   self-contained (sin CDN/red desde JS), estilo inyectado una vez, **`textContent` para dato no confiable/web**
   (buscar `innerHTML` con dato del brain o transcripción → XSS). En `data.py`: solo stdlib, timeouts, sin fetch
   sin límite, sin secretos.
5. **`widgets/generator.py`**: agente `claude -p` atómico — prompt por stdin, `--allowedTools "Write Edit Read"`
   (sin Bash), `acceptEdits`, cwd, timeout, lock de proceso, no sobrescribe id existente, `_validate` (manifest,
   `render`, `data.py` compila, `__init__.py`). Riesgo de inyección (id/spec → path traversal), y si la validación
   basta (¿valida reglas de la casa: `innerHTML`/red/imports no-stdlib en la salida generada?).
6. **`widgets/server_api.py`**: rutas según docs; `wid` normalizado en el borde (sin traversal). Buscar rutas inseguras.
7. **`widgets/store.py`**: JSON aislado por widget, escritura atómica, con lock.
8. **`widgets/runtime.py`**: auto-discovery del catálogo por `manifest.json`, cache por mtime.
9. **Ruta de eventos SSE**: tag del brain → `llm_processor`/`observer` → SSE → `services/sse.js` → desktop;
   `Desktop._resolve()` id-drift (exact→prefix→contains). Confirmar el cableado.
10. **Muerto/duplicado/inconsistente**: carpetas sin manifest/`__init__.py`, solapamiento de nombres
    (`widgets/brief.py` vs `connectors/meshkore/brief.py`), widgets sin commitear.

### Dominio C — Seguridad del canal cluster (ADVERSARIAL — intentar romper cada control)
> El canal cluster recibe mensajes de agentes **externos no confiables**. El canal corre por el motor del FlashBrain en **perfil UNTRUSTED — SIN tools + identidad-safe**
> (`connectors/meshkore/brain.py`→`nucleo/flash/cluster.py`): puede razonar y hablar con peers, nunca ejecutar
> comandos/ficheros/tools. Por cada claim: verificar en código Y **construir el ataque** que lo intenta sortear.
1. **Perfil untrusted sin superficie de tools POR DEFECTO**: `nucleo/flash/cluster.py` no ofrece tools con permiso
   cero; verificar que sin permiso concedido NINGUNA ruta de cluster llega al `CodeAgent`/dev-worker (fail-closed
   por construcción). **V2-076 (2026-07-26) construyó la versión permission-gated de lo que V2-010 acotaba**:
   `connectors/meshkore/perms.py`+`store.py` (perfil por-cluster, deny-all default) pueden abrir
   `escalate_to_slowbrain` a un dev-worker acotado (cwd temporal + `Bash` solo a `nucleo/git_cli.py`, repo
   autorizado, re-verificado en cada commit/push). Verificar TAMBIÉN el guard de objetivo (`perms.
   gate_dev_by_objective`): el permiso `code` NO debe bastar por sí solo sin `capsule.objective` fijado por el
   operador (el operador lo fija con la tool `set_cluster_objective`, operator-only). **Cerrado 2026-07-26:** el
   jail de Read/Write/Edit/Glob/Grep del dev-worker es código real (`nucleo/dev_worker_guard.py`, hook
   PreToolUse), no solo convención de prompt — verificar en la próxima auditoría que sigue cableado (`--settings`
   en `claude_session.py`) y que el fichero de settings sigue viviendo FUERA del workdir del propio worker.
2. **Allowlist de tags de cluster**: solo `cluster.send`/`cluster.done` desde turno de peer; `connect`/`disconnect`
   operator-only. ¿Puede un peer colar `[[create:...]]`/`[[cron.create]]` en su reply? Ver qué hace `_route_reply`
   con tags no-cluster.
3. **`fence_untrusted`**: neutraliza `⟦ ⟧` y sentinels. Probar bypasses (homoglyphs, fences anidados, zero-width) y —
   crítico— comprobar que el **trailer va SIEMPRE al final** en TODA ruta donde texto de peer entra a un prompt,
   **incluyendo metadatos de identidad** (handle/nombre del peer) y la inyección de journal/brief hacia el **kickoff
   de voz** (donde el turno corre con tools auto-aprobadas).
4. **`scan_outbound`**: bloqueo de secreto duro / redacción de huellas, en TODA salida: tag `[[cluster.send]]`, REST
   `/send`, heartbeat/nudge, ack/error, **y el campo `media`** de cualquier `client.send`.
5. **REST guard** `/api/meshkore/*`: loopback-only + anti DNS-rebind (Host/Origin) o token; TODA ruta guardada
   (incl. `/status`), compare de token constant-time, sin fuga de credenciales en respuestas.
6. **Transporte**: `wss://` obligatorio salvo `MESHKORE_ALLOW_INSECURE=1`; token en query redactado en TODO log/excepción/journal.
7. **Flood cap** `MESHKORE_MAX_INFLIGHT`: decremento en TODAS las salidas (excepción en el turno → ¿leak que atasca el canal?).
8. **`store.py`**: `meshkore.json` chmod 600, redacción en journal/SSE/timeline (incl. **texto de peer inbound**).
9. **Validación de frames inbound**: oversized, JSON malformado, `kind` inesperado (protocolo usa `kind`, no `type`),
   trucos unicode en nombres de agente/cluster (¿un handle `[SECURITY]` o con `⟦` rompe el etiquetado del fence?),
   URLs en payload (¿se fetchean en servidor = SSRF?).
10. **Correr los tests**: `.venv/bin/python -m pytest connectors/meshkore/test_security.py -q`; contar casos vs los
    que dice la doc; evaluar huecos de cobertura frente a los ataques de arriba.

### Dominio D — Alineación docs ↔ código ↔ cluster.yaml
1. **Módulos declarados vs realidad**: cada path de `cluster.yaml` existe y no está vacío; marcar módulos fantasma
   (declarados y no existen) y directorios raíz no declarados; `git status` para trabajo sin commitear.
2. **Coherencia de versión**: `cluster.yaml version` = git tag = commits; `state.json` (generado, NO editar a mano);
   routing real de modelos (`config/v2.json` secciones `fast`/`code_agent`) vs lo que dicen las docs (nota de routing
   de `CLAUDE.md`, `zaelar-model-benchmarks.md`, los diagramas de `web/src/pages/technology/`.
3. **Los diagramas públicos** (`web/src/pages/technology/*.astro` + `web/src/lib/diagrams/*.ts`): comparar su
   narrativa/topología contra `architecture.md` + `modules.md`. Citar cada fragmento obsoleto. Es contenido
   curado y RECORTADO a propósito para audiencia externa (sin rutas de fichero internas, sin incidentes/costes) —
   no esperar el mismo detalle que en las docs canónicas; solo señalar si cuenta una arquitectura YA SUPERADA
   (p.ej. si describiera un "SlowBrain" separado, o no reflejara que el cluster comparte el mismo motor).
4. **Roadmap/initiatives**: estados coherentes con la realidad (INI-005 WIP, INI-003 parked, INI-004 done…);
   iniciativa que diga done-pero-no o active-pero-stale.
5. **Ops/deploy/conventions/change-protocol/audit**: contenido obsoleto (paths que ya no existen, comandos que no
   casan con el Makefile — cruzar cada `make` citado, env vars vs `config/.env.example`).
6. **`CLAUDE.md` vs realidad**: logging a `.meshkore/logs/`, raíz sin `.py`/`.html` sueltos, decisiones vigentes.
7. **Higiene del estándar**: sin `docs/` ad-hoc, logs de módulo bajo `.meshkore/modules/<id>/logs/` cuadran con los
   ids declarados; sin carpetas de módulos no declarados ni módulos sin carpeta de log.

---

## 4. Síntesis (el agente principal, tras el fan-out)

Cuando los cuatro subagentes devuelven, el agente principal **cruza y consolida** — NO re-audita:
1. Fusionar hallazgos; deduplicar los que aparecen en varios dominios (p. ej. la claim "cero cross-imports" la ven
   B y A; la deriva de nombre de modelo la ven A, C-adyacente y D).
2. Clasificar por severidad transversal: **seguridad > bugs de arquitectura/correctitud > deriva doc > cosmético**.
3. Confirmar la **alineación en tres capas** (§0.4): ¿el diagrama, los módulos, el contexto y los diagramas
   públicos de `/technology` dicen lo mismo que el código? Cada divergencia = un fix concreto en el plan.
4. Construir el **plan de mejora priorizado** (ver §5).

---

## 5. Salida — formato del entregable

**A) Informe de auditoría — DOS soportes:**
- **Persistente en MeshKore (obligatorio, no se pierde):** un doc fechado
  `.meshkore/docs/architecture/zaelar-audit-<YYYY-MM-DD>.md` (categoría architecture, junto al histórico
  `zaelar-audit.md`) con: resumen ejecutivo (3-5 líneas), veredictos por checkpoint y dominio con evidencia
  `fichero:línea`, y hallazgos consolidados por severidad (id, severidad, `fichero:línea`, escenario/impacto, fix).
  Registrar el commit/versión auditado en el frontmatter (`audit_of:`).
- **Efímero para el operador (opcional):** el mismo contenido como HTML en `~/.meshkore/tmp/zaelar-audit-<fecha>.html`
  (ver [[feedback-reports-local]]) si el operador quiere leerlo en el navegador.

**B) Plan de mejora priorizado — como INICIATIVA de roadmap (obligatorio):** crear `INI-00N-audit-remediation.md`
en `.meshkore/roadmap/initiatives/` con las tareas **una por una** (checkbox `[ ]`, id `T-NN`), cada una anclada a
un hallazgo del informe (`fichero:línea` + fix + si requiere decisión del operador), agrupadas por prioridad:
- **P0 — Seguridad** (bypass de controles duros, XSS, exfiltración, fuga de credenciales). Se arregla primero.
- **P1 — Bugs de arquitectura / correctitud** (event-loop stalls, update que no reinicia el brain, races, fire-and-forget).
- **P2 — Deriva doc ↔ código** (`cluster.yaml` primero por ser lo que lee el daemon, luego docs `.md`,
  `CLAUDE.md`, `.env.example`; los diagramas de `web/` van últimos — su sync ya es manual por diseño).
- **P3 — Cosmético / dead code / housekeeping.**

Así el trabajo de remediación queda en el roadmap y no se pierde; cada tarea se cierra individualmente con [[zaelar-change-protocol]].

**C) Regla:** la auditoría **no arregla nada por su cuenta**. Reporta y para. Los fixes se aplican solo con OK del
operador y cada uno se cierra con [[zaelar-change-protocol]] ("pasa el protocolo").

---

## 6. Cómo repetirla (checklist rápida para el agente)
1. `TodoWrite` con las fases (reconocimiento → 4 dominios → síntesis → informe).
2. Fase §1 reconocimiento (leer los 5 grupos de contexto).
3. Lanzar los 4 subagentes de §3 **en paralelo** (un `Agent general-purpose` por dominio, con sus checkpoints).
4. Al volver todos, §4 síntesis + §5 informe + plan P0-P3.
5. Reportar al operador y esperar decisión sobre qué arreglar. No tocar código en la propia auditoría.

> **Al evolucionar el proyecto:** si se añade un módulo, actualizar §2 (tabla de dominios) y §3 (checkpoints) de
> este workflow para que la próxima auditoría lo cubra. Este doc es parte del contexto que viaja con zaelar.
