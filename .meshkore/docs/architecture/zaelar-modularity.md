# zaelar — Modularidad y contratos de acoplamiento

> Doc canónica del **mapa de piezas**: cómo se conectan los módulos, qué contratos existen (evento / llamada de
> fachada / BD), el inventario de kill-switches y las reglas para añadir piezas nuevas. Nacida del audit de
> modularidad previo a V2-053 (2026-07-17, 4 dominios auditados en paralelo). Mantener alineada cuando cambie la
> topología (es parte del docs-sync).

## 1 · Principio rector

zaelar es **un solo proceso** con módulos aislados que se conectan SOLO por tres tipos de costura:

1. **EVENTOS** — el bus (`bus/`, pub/sub fnmatch + `emit_sync` loop-agnóstico) para lo async/fan-out; el
   observer (`voice/observer.py::emit`) para telemetría de turno, PUENTEADO al bus como topic `observer`.
2. **LLAMADAS de fachada** — cada dominio expone una superficie pública; la ruta caliente de voz usa llamadas
   directas (nunca esperar un evento en el turno).
3. **BD** — un solo SQLite `zaelar.db` con **escritor único** (cola `memory/queue.py` → `writer.py`); lecturas
   WAL concurrentes.

**Regla de oro:** una pieza nueva se monta en el lifespan (`server/__init__.py`) con gate de config/env, expone
`start()`/`stop()` idempotentes, se suscribe al bus (no importa internals de otros dominios), y su fallo NUNCA
tumba la voz (try/except "voice/chat unaffected").

## 2 · Fachadas por dominio (la superficie pública)

| Dominio | Fachada | Notas |
|---|---|---|
| `memory/` | **`memory/api.py`** (import como `from memory import api as memory`) + `memory/journal.py` (continuidad de tareas) | `__all__` declarado en `api.py` (añadido 2026-07-17). Escrituras por cola; `set_state`/`forget`/user-rules son directas (RLock, decisión: efecto inmediato) |
| `bus/` | `bus.publish/emit_sync/subscribe/add_sink` + `bus.log.recent/count` | `bus/log.py` es un **sink que persiste TODO evento** del bus (tabla `events`) — sustrato de auditoría durable |
| `widgets/` | `widgets.dispatch_tag` + `widgets/server_api.py` (HTTP + `brain_action` + `run_widget_action`) + `runtime.catalog/identify/get` + `generator` | El pool de `_run_widget` (4 hilos + timeout 8s) aísla todo `data.py` |
| `voice/` (contrato del cerebro) | `observer.emit/turn_detail`, `brain_notes.push/drain`, `proactive.notify`, `trace.begin/adopt/scope`, `attention`, `speech`, `tag_protocol` | Nivel superior agnóstico del transporte; `voice/engine/` es el MOTOR (LiveKit) y sus internals no son fachada |
| `nucleo/` | provider `voice/engine/llm/providers/nucleo.py` (borde con la voz) + `dispatch` (fachada de sesiones: `active_sessions/has_active/resolve_sessions/inject_soon/cancel_soon`) + `escalate` + `memory_agent` | El registro `dispatch._SESSIONS` es RAM privada; se lee SOLO por su fachada |
| `connectors/` | `connectors/<x>/service.py` por conector + `connectors/messaging/ingest.py` (topics) | |
| `config/` | módulo dueño por store (`settings.py`/`connectors.py`/`v2.py`) con vista pública redactada | |

## 3 · Contratos de EVENTO (topics del bus)

Todo topic queda ADEMÁS persistido en `zaelar.db·events` por `bus/log.py` (si `ZAELAR_BUS_LOG=1`).

| Topic | Emisor | Suscriptor(es) | Payload clave |
|---|---|---|---|
| `observer` | `voice/observer.emit` (puente `bus/sse.py`) — TODO evento de timeline | SSE `GET /events`, visor, juez del tester, **Susurro** | `{kind,label,text,role,extra,trace,span}` |
| **`turn.completed`** | `voice/observer.turn_detail` (V2-053 — lo llaman AMBOS caminos: provider de voz y probe) | **Susurro** | turno completo: `{user, reply, system_prompt, window, tools, decision, engine, trace}` |
| `memory.updated` | `memory/queue`, `api._emit`, prompt(query) | puente SSE (coalescado), `memory_cache` (sink) | `{op, ids}` |
| `escalate.requested` / `escalate.done` | `nucleo/flash/escalate` | `nucleo/dispatch` (único consumidor) | `{id, request, context{trace}}` |
| `worker.spawned/phase/result/say/done/error/cancelled` | `nucleo/workers/session` | log/UI | por sesión |
| `worker.ask` / `worker.say` | `nucleo/worker_api` | log/loop | `{id, question, corr_id}` |
| `worker.stuck` / `worker.budget_nudge` / `worker.budget_kill` | `nucleo/loop` (supervisor) | log, **Susurro (fricción)** | `{id, age_s}` |
| `loop.tick` / `loop.scheduled_fired` / `loop.spark` / `loop.consolidated` | `nucleo/loop` | pulse SSE / log | |
| `connector.msg` / `connector.status` / `msg.mark_read` / `msg.reply` | `connectors/messaging/ingest` | owner de `mensajeria`, consumers | |
| `susurro.finding` (V2-053) | `nucleo/susurro` | dev-loop (cron test→fix) | finding estructurado |

**Eventos observer relevantes por `kind`** (todos con `trace`/`span` sellados automáticamente por `emit()`):
`transcript` (🗣 user / zaelar), `brain` (prompt/reply/notas/escalada/promesa-sin-acción), `perf` (turn_detail
forense: system+window+tools+**decision**), `widget`/`backed`/`background`, `music`, `search`, `task`
(phase/dedup/resume), `rail` (incl. `fail` → `sin_resolver`), `vad` (barge-in/falsa interrupción), `alert`+`error`
(turno degradado), `ambient`, `memory`, `timing`, `trace` (raíz), `susurro` (V2-053), `homeostasis` (V2-070 — capa
autónoma de salud de la MÁQUINA, `nucleo/homeostasis.py`; labels `start`/`degraded`/`recycle`/`rotate`/`evict`/`alert`).

**Pacto de conversación agente-agente (V2-072).** El puente del cluster (`connectors/meshkore/bridge.py`) emite
eventos observer del canal con un campo **`pact`** en el evento **`🤝 pact updated`** cuando se sella un pacto por-peer
(cadencia / medio / alcance negociados). El tag `cluster.pact` está **permitido desde un turno de cluster** — se añade
al allowlist de tags de turno-cluster junto a `cluster.send`/`cluster.done` (el resto de tags de capacidad del
operador siguen bloqueados desde un turno de peer). El pacto es el TERCER nivel de reglas (sistema/hard > operador >
pacto), vive en la cápsula por-peer (`capsule.pact`), solo RESTRINGE nuestra conducta (nunca concede capacidades,
vocabulario cerrado) y su cadencia se aplica de verdad con un throttle en `cluster.send` (`capsule.cadence_wait`).
Detalle en `.meshkore/docs/security/zaelar-security.md`; iniciativa `V2-072-pacto-conversacion-agente-agente.md`.

## 4 · Kill-switches (inventario)

**Gates de arranque** (lifespan; patrón `active_brain()=="nucleo" and os.getenv(X,"1")=="1"`):
`ZAELAR_MEMORY` · `ZAELAR_LOOP` · `ZAELAR_SLOWBRAIN` · `ZAELAR_BUS_LOG`(def 0) · `MESHKORE_AUTORECONNECT` ·
**`ZAELAR_SUSURRO` + config `susurro.enabled`** (V2-053) · **`ZAELAR_HOMEOSTASIS`** (V2-070 — la capa autónoma de
salud de la máquina, `nucleo/homeostasis.py`).

**Por pieza:** `MEM_PROCESSOR` (CORAZÓN) · `BROWSER_SEARCH` · `MESHKORE_MEMORY` · `ZAELAR_LOG_PROMPTS`
(captura forense turn_detail; ⚠️ el Susurro la necesita — si se apaga, el Susurro degrada a señales sueltas) ·
`MEM_SEMANTIC_DEDUP` · `MEMORY_RERANK*` · `WIDGETS_BACKED_MAX_FAILS` · flags de config `flags.brain`,
`memory.rerank_provider='off'`, `attention_mode`.

**Huecos conocidos (deuda, no bloqueante):** no hay kill-switch global del sistema de widgets ni disable
por-widget de background; no hay modo "memoria solo-lectura" (dry-run).

## 5 · Violaciones detectadas (audit 2026-07-17) y estado

| # | Violación | Estado |
|---|---|---|
| 1 | `nucleo/worker_api.py` importaba **privados** `_MISSING`/`_run_widget` de `widgets/server_api` | **ARREGLADO** — fachada pública `widgets.server_api.run_widget_action()` |
| 2 | `connectors/messaging/store.py` importaba `widgets.store` a nivel de módulo (único no-lazy) | **ARREGLADO** — lazy |
| 3 | `widgets/__init__.py` citaba `providers/duo.py` (muerto) | **ARREGLADO** — docstring |
| 4 | `memory/api.py` sin `__all__` (fachada sin contrato explícito) | **ARREGLADO** — `__all__` declarado |
| 5 | No existía topic semántico de fin de turno (Susurro habría tenido que agregar N eventos observer) | **ARREGLADO** — `turn.completed` emitido desde `observer.turn_detail` (punto ÚNICO que ya llamaban voz y probe) |
| 6 | `voice.engine.core.langs` importado desde nucleo/dispatch/prompt/probe (~10 sitios) — utilería de idioma enterrada en el motor | DEUDA documentada — regla: código nuevo NO añade sitios; mover a módulo neutro cuando se toque esa zona |
| 7 | `widgets.navegador.tasks/owner` y `widgets.mensajeria.data` importados desde el provider/nucleo (el core conoce widgets por nombre) | DEUDA — aceptada para los 2 widgets backed de 1ª clase; no extender el patrón |
| 8 | Acoplamiento inverso lazy `memory/server_api.py`→`nucleo.memory_agent` | DEUDA — es el enforcement del escritor único vía HTTP; documentado |
| 9 | `set_state` sin allowlist (merge ciego; identidad parcheable) | Pendiente F3 de V2-053 (allowlist para el aplicador del Susurro) |
| 10 | El probe NO drenaba `brain_notes` (paridad voz/probe rota para notas [SISTEMA]) | **ARREGLADO** en F1 (el probe drena igual que el provider) |

## 6 · Reglas para una pieza nueva (checklist)

1. Módulo propio declarado en `cluster.yaml`; `start()`/`stop()` idempotentes; montado en lifespan con gate
   (config store manda, env fallback) y try/except aislante.
2. Se conecta por **bus** (subscribe) y **fachadas** — nunca imports profundos de otro dominio ni privados `_x`.
3. Escrituras de memoria por `memory.api` (cola/gates); NUNCA BD directa.
4. Telemetría por `observer.emit` con kind propio (el trace se sella solo); eventos de dominio por `bus.emit_sync`
   con topic `dominio.suceso`.
5. Fail-open: su caída no afecta a la voz; sin locks compartidos con el turno; I/O fuera del event loop del turno.
6. Estado global mutable mínimo, con `reset()` para tests.
7. Docs-sync: entrada en CLAUDE.md + doc de categoría + diagrama `/architecture` + esta doc si cambia topología.

## 7 · Dependency directions — measured, frozen, guarded (2026-09-03)

Row 6 of §5 is the cautionary tale for this whole section: the July audit found ~10 files importing
`voice.engine.core.langs` and wrote the rule «new code adds no sites». Nothing measured it, and by September
the 10 sites were **30** — a rule each caller has to remember is not a rule. So the directions are now a
ratchet, like the size table: `tests/infrastructure/unit/test_dependency_directions_only_improve.py`
(testmap **7.32**, sibling of 7.22).

What it freezes, from a full AST measurement of the tree:

- **42 (file → module) pairs reach `voice.engine.*` from outside `voice/`** — the boundary §2 already declared
  («the motor's internals are not a facade»). The inventory can only shrink; a NEW pair is red with the fix in
  the message: use the facade, or extract the shared thing to a lower layer. `voice.observer` / `proactive` /
  `tag_protocol` are the blessed brain-contract surface and are NOT in scope.
- **Exactly 1 private (`_x`) name crosses a domain boundary** in the whole engine
  (`nucleo/workers/findings.py` → `widgets.navegador.act_api._HANDED`, allowlisted). The number being 1 is
  what makes the guard cheap: a second offender is a decision, not noise.

**The named debt** (the honest exit, not more rows): `voice/engine/core/langs.py` is a shared language
utility that happens to live inside the motor — 30 of the 42 pairs are it, almost all imported lazily, which
is this codebase's documented way of papering over an import cycle. The fix is a home in a low layer with a
re-export shim at the old path (the `text_norm.py` / `errors.brief` precedent), tracked in V2-569. Until that
extraction, the frozen inventory holds the line the July rule could not.

**Growth doctrine, in one paragraph** (operator's directive, 2026-09-03): as the tree grows, prefer a
thousand small pieces over one giant one — the size ratchet (7.22) enforces the *pieces*, this one enforces
the *joints*. A file that outgrows its ceiling pays by extracting a cohesive concern behind aliases, never by
raising the ceiling; a module that needs another domain goes through §2's facade, never through its
internals; anything two domains both need gets extracted DOWN, not imported ACROSS.
