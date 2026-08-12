# zaelar — Playbook de testing del bot ("lanza un test del bot")

> **Entrada operativa obligatoria para agentes:** leer primero `tests/README.md`. Ese archivo contiene el contrato
> conciso terminal↔UI, selección de suite, aislamiento, puertos y cómo añadir runners. Este playbook es la capa
> profunda para preparar escenarios vivos, diagnosticar resultados y archivar evidencia. Si hubiera contradicción,
> mandan el comportamiento del CLI actual + `tests/platform/SCHEMA.md`, y se deben alinear ambos documentos en el
> mismo cambio.

> **Trigger**: cuando el operador dice **"lanza un test del bot"**, **"lanza la batería (de escenarios)"**,
> **"prueba el bot en tuen"** o similar → ejecutar ESTE playbook de principio a fin. No hay que recordar los pasos
> de memoria: viven aquí. La descripción de las PIEZAS del sistema vive en `zaelar-architecture.md`/`CLAUDE.md`;
> este doc es SOLO **cómo se prueba** (qué, con qué prioridad, cómo se evalúa, dónde se archiva).

El bot se prueba **solo, sin micrófono humano**: un agente **tester** (`tests/voice/e2e/agent/`) se une a la sala LiveKit como 2º
participante, HABLA por TTS y ESCUCHA por STT; un **JUEZ** (GLM-4.6 vía Z.AI, fallback DeepSeek) evalúa el
comportamiento OBSERVABLE (acciones de frontend, tags del cerebro, escaladas, latencias) leyendo `GET /events`.
Detalle del arnés: **INI-013** (`.meshkore/roadmap/initiatives/INI-013-voice-tester.md`).

> **Entrada unificada + visor realtime (V2-077)** — `./.venv/bin/python -m tests run <suite>` ejecuta memoria,
> agent-headless, voz, browser, conectores, cluster o infraestructura con el mismo contrato. En local abre
> automáticamente **Zaelar Test Observatory** en `http://127.0.0.1:8765`; en CI usar `--no-open`. Cada nueva
> ejecución hace handoff sobre ese mismo puerto y sustituye el dashboard anterior, sin dejar servidores huérfanos. Cada test, turno,
> input/output, latencia, evento de agente y score se persiste en `tests/runs/<run-id>/events.jsonl`, y puede
> reabrirse con `python -m tests replay <run-id>`. Para voz real: `python -m tests run voice --live` con zaelar UP.

> **Mapa de tests navegable** — toda la superficie de pruebas es ahora recorrible por
> **`tests/run_testmap.py`** (eje **dominio → caso de uso → canal**, numerado `1.1`/`2.1`/…), con la narrativa en
> **`tests/TESTMAP.md`**. Son **9 dominios**; el **dominio 9 = HOMEOSTASIS** (la capa autónoma de salud de la
> máquina, `nucleo/homeostasis.py` / `tests/infrastructure/unit/core/test_homeostasis.py`, V2-070).

> **Contrato de mapa schema 2** — el Observatory consume un árbol común para TODOS los tipos principales:
> `suite → pasos ordenados → grupos → casos`. Cada caso tiene ID estable, input, expectativa, verificación, ruta
> interna, fuente y ejecución validada. Pytest se normaliza automáticamente y los corpus ricos se conectan con
> `catalog_provider` (Memoria, Voz y Headless ya migrados). Se puede ejecutar una suite completa, un grupo en orden
> o un caso desde el UI o con `python -m tests run <suite> --case <id>`. Especificación:
> `tests/platform/SCHEMA.md`.

> **Regla para Claude Code/Codex:** usar `--no-open` si no necesitan manejar el navegador. El Observatory se sigue
> levantando en `127.0.0.1:8765`, por lo que el operador puede ser espectador y luego lanzar casos desde la web.
> El motor real usa `127.0.0.1:43917`. No solapar dos runs del Observatory; no usar `make reset` como preparación
> rutinaria; y declarar con honestidad si solo se ejecutó lógica determinista o si también se cruzó la frontera
> real headless/Playwright/LiveKit.

> **Viaje causal compartido** — para cambios que cruzan dominios ejecutar
> `./.venv/bin/python -m tests run journey --no-open`. Son 26 pasos enlazados sobre un engine, memoria, canvas,
> agenda y registro de workers aislados. Cada caso declara `consumes`/`produces`; lanzar un caso intermedio
> reconstruye J001→caso. Incluye extracción natural, pronombres, widgets, cita, Wallapop, procesos, conectores,
> cluster, corrección temporal y checkpoint. No sustituye las fronteras físicas de micrófono/STT/LiveKit,
> Playwright o WebSocket remoto. Diseño completo: `tests/journey/README.md`.

---

## Un test VERDE tiene que significar algo — el aislamiento de la suite (2026-08-10)

La tarde del 2026-08-10 salieron **cuatro** fallos distintos que desde fuera se veían igual: un guarda que parece
cubrir y no cubre. Ninguno «fallaba» — todos MENTÍAN, que es peor, porque nadie va a mirar lo que ya está en verde.

| Lo que se veía | Lo que pasaba de verdad |
|---|---|
| dos tests verdes de frases al operador | verdes por la MÁQUINA (castellano en la config), rojos en cualquier otra y en CI |
| un fixture que probaba el reset REAL | **borraba los datos reales de los widgets del operador** en cada corrida |
| dos nodos del mapa numerados «7.6» | uno se contaba dos veces y el otro no existía |
| vaciar un widget | mutación sin evento: parecía un fallo de persistencia |

**El mecanismo, que es lo que hay que recordar:** fijar la variable no basta. `config/settings.load_into_env()`
copia `config/settings.json` ENCIMA del entorno, sin condición, porque en producción el store MANDA sobre el env —
regla correcta allí. En un test significa que la configuración PERSONAL del operador decide el resultado de la
suite: idioma, proveedor de STT/TTS, modo de atención y perfil del motor. Se apuntó al síntoma (el idioma) antes de
ver la puerta (el store).

**Invariantes que sostiene `conftest.py`** (raíz), y por qué cada una:

- **`ZAELAR_LOG_DIR` a un temporal** — los eventos de un test no pueden acabar en el timeline que el operador lee
  para post-mortems REALES (julio 2026: un «kind:error boom» de un test se auditó como incidente).
- **`SETTINGS_FILE` a un temporal VACÍO** — la config del operador no decide el resultado de la suite.
- **`ZAELAR_LANGUAGE=en` FORZADO** (no `setdefault`): con un default, un `ZAELAR_LANGUAGE` en el shell vuelve a
  cambiar qué significa «verde». **Probar otro idioma se declara EN el test**; probar los dos se hace comprobando
  los dos DENTRO del caso, nunca corriendo la suite dos veces con el entorno cambiado.
- **`ZAELAR_RESEARCH=0`** — el pre-vuelo de una escalada llama a un proveedor de verdad; en un test es una llamada
  de red no declarada que cuelga el caso hasta el timeout.
- Y cada test que toca datos de widgets **aísla `store.DATA_DIR`** él mismo.

Todo esto va **al nivel del módulo** del conftest, no en un fixture: los módulos de test se importan ANTES de que
corra cualquier fixture, así que un fixture llega tarde.

Guarda permanente: **nodo 7.10** (`tests/infrastructure/unit/test_suite_isolation.py`) — un guarda sobre los
guardas. Si alguna invariante se rompe, la suite vuelve a poder mentir y no se enteraría nadie hasta que un test
pasara aquí y fallara en otro sitio.

**Cómo se caza esta clase:** no con `grep`, con MEDICIÓN. Correr la suite con la variable sospechosa cambiada y
diffear los fallos — y antes, comprobar que el knob LLEGA de verdad dentro de un test (un barrido que no aplica lo
que cree aplicar es el mismo bug que se está buscando).

## Paso 0 — ALINEACIÓN tests ↔ sistema (SIEMPRE lo primero, antes de lanzar nada)

Antes de probar hay que garantizar que **los escenarios prueban la versión ACTUAL del sistema**. Checklist:

1. **Módulos principales cubiertos**: cada capacidad viva tiene al menos un escenario en `tests/voice/e2e/agent/scenarios.py`
   (ver el catálogo en `tests/voice/e2e/agent/anexos/catalogo-escenarios.md`): conversación · memoria (guardar/recall/corrección) ·
   widgets (mostrar/crear/borrar) · búsqueda web factual · navegación web profunda (Wallapop/coches.net) ·
   mensajería unificada · conectores · cluster · paste/chat · multiidioma · **seguridad de datos (bóveda, V2-060)**.
2. **Cambios de las últimas ~48 h**: `git log --oneline --since='48 hours ago'`. Por cada capacidad NUEVA o
   CAMBIADA (una tool nueva, un proveedor nuevo, un flujo nuevo), confirmar que hay escenario que la ejercita; si
   no, **añadirlo a `tests/voice/e2e/agent/scenarios.py` + al catálogo** antes de lanzar. Mira también las **decisiones clave** con
   marca `V2-0xx` recién añadidas en `CLAUDE.md`.
3. **Arranque real**: zaelar UP en `:43917` con la ÚLTIMA versión (si tocaste `.py`, reinicia — `make run` —, espera
   `/api/livekit` + `registered worker`, y confirma en el log el **prewarm** (`prewarm FlashBrain OK`) y
   `browser_search OK`).

> ⚠️ **REGLA DURA de VERSIÓN — el desarrollo vive en ESTA máquina; la última versión es el ÁRBOL DE TRABAJO LOCAL.**
> El testing se ejecuta SOBRE el código que YA está checked out en el repo local; el operador (y otros agentes)
> desarrollan aquí, así que **lo local es la fuente de verdad**, no `origin`. **NUNCA** hagas `git pull` / `fetch`
> + `merge` / `reset` / `checkout` de otra rama o commit para "traer la última versión" ni para poner el repo al
> día antes de un test: `origin` puede estar POR DETRÁS del trabajo local, y cualquier operación de git puede
> **DESTRUIR código local sin commitear** o cambiar de commit bajo los pies de otro agente que trabaja en el mismo
> árbol. Si necesitas asegurar el arranque, solo **reinicia el proceso** (`make run`) con lo que hay en disco. Si
> de verdad crees que falta algo, PREGUNTA al operador — no toques git. (Incidente 2026-07-12: un
> `merge --ff-only origin/main` en el arranque del test trajo una versión remota; no se perdió código de milagro
> porque fue fast-forward, pero era un riesgo real e innecesario.)

> Si el Paso 0 detecta deriva (un escenario prueba algo que ya no existe, o falta cubrir algo nuevo), **corrige los
> escenarios primero** y anótalo en el informe del día. Los tests desalineados dan veredictos inválidos.

---

## Prioridades — QUÉ nos importa probar (en orden)

1. **Latencia percibida** — (a) **1er turno** (el prewarm debe absorber el cold-start → ~1s, no 6-8s); (b) chat
   steady-state (~1.5s); (c) **búsqueda** (objetivo ≤ ~4-6s con la capa Google; DDG era 18-34s). Cualquier turno de
   charla > 3s en castellano es sospechoso.
2. **Coste bajo** — preferimos SIEMPRE lo gratis que funcione (Google vía navegador, Ollama local, Kokoro/Whisper
   Metal) antes que APIs de pago. Un test no debe asumir key de pago; si una capa de pago está presente, mejor, pero
   el default gratis tiene que ir bien.
3. **Memoria correcta** — guardar lo dicho, recall del mismo hilo Y de sesiones anteriores, **corrección** ("no, en
   realidad es X"), olvido, y que NO alucine datos. (La memoria tiene además su **propia** suite exhaustiva — aquí
   basta con 1-2 escenarios de humo; no duplicar.)
4. **Búsqueda precisa** — dato factual dicho de viva voz EN el turno (tiempo, resultado deportivo, cotización,
   "quién ganó"). Weather y resultado de partido deben salir EXACTOS (widgets de Google); para el resto, snippets
   de calidad → el cerebro sintetiza; nunca inventar un dato que no está.
5. **Navegación web profunda (con o sin login)** — el caso estrella del operador: "búscame un coche de <5000 € y
   <250.000 km en Wallapop/coches.net" → abre el **navegador Chromium en 2º plano**, navega, **extrae anuncios
   reales** (precio + km) y da top-3. **Requiere comparación** (ver abajo): ¿los coches existen y cumplen los
   criterios? De momento **sin autenticar** (si un sitio pide login, que lo diga; no forzamos credenciales).
6. **Robustez / turn-taking** — no quedarse mudo, no entrar en bucles de saludo, gestionar correcciones e
   interrupciones. (Ojo: buena parte de los "mutes" en batería son artefacto del arnés — ver Limitaciones.)
7. **Multiidioma** — un subconjunto en inglés; la voz/persona/STT nunca cruzados con el idioma.
8. **Seguridad de datos (V2-060)** — la **bóveda de secretos** cifrados (escenario `seguridad_datos`): GUARDAR un
   secreto (contraseña/IBAN/cripto) → PEDIRLO → zaelar pide la **passphrase** → SERVIR. El tester **NO usa
   biometría** (passkeys son hardware) → el desbloqueo va por **passphrase** (el modal nativo / la API
   `/api/vault/*`; el camino robusto es scriptar `create`+`unlock` por HTTP). **FAIL DURO** si el VALOR de un
   secreto aparece EN CLARO en cualquier evento/log/traza o zaelar lo recita de memoria — el invariante es que el
   valor solo viaja `DB(ciphertext)→/api/vault/reveal→frontend`, nunca por el LLM ni por el observer.

---

## Canal RÁPIDO por TEXTO — el probe del FlashBrain (3ª forma de testing, V2-032)

Antes de la batería de VOZ (lenta, con ruido de STT), para iterar sobre el **cerebro rápido / la conversación / el
prompt / la memoria-estado / las tools** hay un canal **headless por texto** que corre el turno REAL del FlashBrain
(mismo `build_flash_system` + modelo + `router.TOOLS` + defensas `dialog.py`) y devuelve un JSON evaluable — sin
voz, interfaz ni sala LiveKit. Es el más rápido para reproducir/validar un fix desde Claude Code.

```bash
make reset                 # memoria + observabilidad a CERO (conserva credenciales/auth; frontera en scripts/reset-memory.sh)
make flash-serve           # server HEADLESS (sin voz/navegador); en otra terminal:
make flash T="hola, ¿cómo te llamas?"     # one-shot  →  zaelar ▸ … [acción=… ⚠️BUCLE/DEGENERADO] (ms)
make flash-repl                            # conversación interactiva (/reset limpia la ventana)
curl -s localhost:43917/api/flash/say -H 'content-type: application/json' -d '{"text":"…","ingest":false}'
```

Respuesta: `{ok, reply, action, tool_calls, tags, degenerate, loop_run, turns, prompt_chars, spec, timings}`.
`action` = qué HARÍA el turno real (`chat`/`escalate`/`search`/`widget_data`/`delete_widget`/`canvas:show…`).
`ingest=true` (def) escribe a memoria como el turno real (contrasta con `curl /api/memory/map`); `ingest=false` =
charla aislada. `degenerate`/`loop_run` marcan las patologías del informe 2026-07-12 (empalme/repetición). El fix
vive en `nucleo/flash/dialog.py` (break-loop + poda + anti-degeneración), COMPARTIDO por voz y probe → lo que
validas por texto corre igual en voz. Endpoint solo con `BRAIN=nucleo`. Ver `nucleo/flash/probe.py`.

---

## Grupo «susurro» — auto-auditoría y MEJORA CONTINUA (V2-053)

Grupo ESPECIAL pedido por el operador: no prueba una feature sino **que el sistema se corrige a sí mismo** — el
modelo potente debe discernir dónde está el problema cuando algo sale mal y corregir. Tres anclas:

1. **Unit** — `tests/agent_headless/unit/susurro/test_susurro.py` (fricción es/en, catálogo, aplicadores, engine con LLM falso,
   cooldown, kill-switch). Corre con el pytest normal.
2. **Integración headless** — `tests/agent_headless/e2e/susurro/run_probe_suite.py` (server vivo): simula fricción por el probe
   (queja tras una acción), exige la MAQUINARIA completa (trigger → request CON payload → response → auditoría
   completa, eventos kind `susurro` en el timeline) y verifica que un `repair_say` sale HABLADO en el turno
   siguiente (el probe drena `brain_notes`). El JUICIO del modelo se reporta sin fallar la suite (decidir
   `corrections=[]` ante un tramo sano es correcto). **Cada run appendea a
   `tests/agent_headless/e2e/susurro/history.jsonl`** — el histórico LONGITUDINAL: con el tiempo debe bajar la fricción por
   sesión y mejorar la calidad de diagnóstico (revisar ese fichero al evaluar oleadas). Ojo al `cooldown_s`
   (def 60s) entre runs.
3. **Voz e2e** — escenario `susurro_reparacion` en `tests/voice/e2e/agent/scenarios.py` (rotación del cron): el tester se queja
   de viva voz y el juez verifica los eventos `susurro` + la reparación natural. Queja sin NINGÚN evento
   susurro = FAIL de maquinaria.

Al ARREGLAR un finding del Susurro (los consume el dev-loop desde `.meshkore/logs/susurro/findings.jsonl`),
tratar el finding como el hallazgo de una oleada: fix + test de control + re-verificar + documentar.

## Grupo «canal de cluster» — conversar con AGENTES (V2-069 «una sola mente»)

El canal de cluster es agente-a-agente (NO voz), así que el tester de voz no lo cubre — tiene su propio grupo, que
verifica la INTELIGENCIA de conducción (no re-presentarse, fase, objetivo presente, corte de bucle) y la SEGURIDAD
(perfil untrusted: tools off + identidad-safe). Dos anclas:

1. **Regresión determinista (sin LLM)** — `tests/cluster/unit/test_capsule.py` + `test_capsule_flow.py` +
   `test_security.py` (guard de atasco). Capturan el prompt EXACTO que el bridge da al cerebro por turno y verifican:
   NO re-presentarse tras el 1er contacto, progresión de fase (saludo→sondeo→trabajo), objetivo del operador presente,
   cápsula inyectada, `build_cluster_system` identidad-safe (cero PII del operador), tools-off estructural, y la
   escalada de atasco (repetición → 1 asertivo → callar + avisar). Corren con el pytest normal.
2. **e2e con el MOTOR REAL** — `tests/cluster/e2e/run_cluster_suite.py`: scriptea una conversación de peer y la pasa
   por `nucleo/flash/cluster.py::respond` (GLM-5.2) con el MISMO framing del bridge (cápsula + fence + trailer).
   Invariantes DUROS (maquinaria + identidad-safe + no-re-presentación) tumban la suite; el juicio blando
   (intro/on-goal/conciso) se reporta. Appendea a `tests/cluster/e2e/history.jsonl` (longitudinal). Requiere la key
   del tier del canal (carga `.env` + credential store solo).

---

## Cómo se LANZA

- **Batería completa** (todos los escenarios, con settle entre ellos para no saturar el worker THREAD):
  `bash tests/voice/e2e/agent/run_battery.sh` → escribe una tabla resumen `tests/voice/e2e/agent/runs/battery_summary_<hhmmss>.tsv` + un informe
  por escenario `tests/voice/e2e/agent/runs/report_*.{json,md}`. Variables: `BATTERY_SCENARIOS="a b c"` (subconjunto),
  `BATTERY_SETTLE=12` (s entre escenarios), `BATTERY_MAX_RUN=360` (watchdog por escenario).
- **Un solo tick** (rota por cursor): `bash tests/voice/e2e/agent/cron_tick.sh` — imprime un bloque `VERDICT status=…`.
- **Un escenario suelto**: `./.venv/bin/python -m tests run voice --case voice::scenario::<id> --no-open`
  (acción canónica observable), o directamente
  `./.venv/bin/python -m tests.voice.e2e.agent.run --scenario <id> --no-open --hold 0` para diagnosticar el arnés.
- **Loop autónomo test→fix cada 15 min** (cron de sesión): ver INI-013 §"Cron test→fix loop" (`cron_tick.sh` +
  prompt del cron). Cada disparo prueba UN caso, el juez puntúa, y el agente ARREGLA el código si hay bug real.

Requisitos: zaelar UP (Paso 0) + claves del tester en `.env`/`.meshkore/credentials/tester.env`
(`TESTER_AIMLAPI_KEY`, `CARTESIA_API_KEY`, `DEEPGRAM_API_KEY`, `TESTER_ZAI_KEY`).

---

## Cómo se EVALÚA (distinguir señal de ruido)

El juez da `overall` (1-5) + `scores{naturalidad,coherencia,utilidad,accion,latencia,robustez}` + `veredicto`.
Umbral: **`overall ≥ 4` = PASS**. Pero un FAIL **NO es automáticamente un bug de zaelar** — hay que discernir:

- **Bug REAL** → confírmalo en `.meshkore/logs/timeline-latest.jsonl` (eventos `brain`/`widget`/`search`/`error`/
  `transcript` correlacionados al informe). Solo entonces se toca código. Arregla → reinicia si tocó `.py` →
  **re-corre ESE escenario** → documenta.
- **Ruido de STT del tester** — el Deepgram del propio tester garbla ("zaelar"→"Arbe/Harvey/Árix", mezcla idiomas).
  Un input basura invalida el turno; NO es fallo de zaelar. **Ojo**: además **ensucia la memoria REAL** con nombres
  mal transcritos (se prueba contra la cuenta viva del operador).
- **Rigidez del juez** — a veces penaliza cosas correctas (dos `show` idempotentes = "duplicado"; leer bien "no lo
  encuentro" cuando el buscador no traía el dato = "alucinación"). Verifica antes de creerlo.
- **Contención del arnés** — un único worker THREAD; escenarios back-to-back sin settle → mutes/timeouts falsos
  (all-1s). `run_battery.sh` ya mete settle; aún así, un all-1s aislado suele ser esto.

**Navegación web = comparación explícita**: para los escenarios de coche/marketplace, además del juez, **comparar a
mano** lo extraído: ¿son anuncios REALES?, ¿cumplen precio y km?, ¿hay top-3 con datos?, ¿o alucinó/no entró? Anotar
el veredicto humano en el informe del día.

---

## Dónde se ARCHIVA (histórico consultable)

- **Catálogo de escenarios** (qué se prueba y por qué): `tests/voice/e2e/agent/anexos/catalogo-escenarios.md` — se mantiene
  alineado con `tests/voice/e2e/agent/scenarios.py` en el Paso 0.
- **Informe de cada sesión de test**: al cerrar una tanda, crear una carpeta **`tests/voice/e2e/agent/reports/<YYYYMMDD>-<desc>/`**
  (fecha invertida año-mes-día + descripción corta, p. ej. `tests/voice/e2e/agent/reports/20260711-bateria-v2024-google-prewarm/`)
  con: la tabla resumen (`.tsv`), los `report_*.{json,md}` relevantes, y un **`INFORME.md`** con: qué se probó, la
  tabla de resultados, hallazgos (bug real vs ruido), arreglos hechos, y latencias antes/después. Así, repetir la
  batería una semana después deja un histórico comparable. (Los `tests/voice/e2e/agent/runs/` son el scratch en crudo; `reports/`
  es el archivo curado.)

---

## Limitaciones CONOCIDas del arnés (no perseguir cada vez)
- `--goal` SIEMPRE usa canal VOZ (chat/paste solo por los escenarios fijos).
- STT Deepgram del tester garbla/mezcla idiomas → ante señal sucia, mira `timeline-latest.jsonl`, no el audio.
- Único worker THREAD embebido → settle entre escenarios (ya en `run_battery.sh`); no correr batería mientras el
  operador está EN VIVO en una sesión de voz (colisión) — `cron_tick.sh` ya SALTA si detecta voz activa.
- Docker SÍ se permite en el sistema de testing (aislamiento); el CORE de zaelar nunca depende de Docker.

## Ciclo de re-verificación de la MEMORIA (test-bot de 1000+ requests)

Aparte de la batería de voz, la memoria tiene su propio **ciclo de re-verificación**: el test-bot
(`tests/memory/e2e/bot/`) role-play una PERSONA a lo largo de 1000+ pasos y verifica por el CAMINO REAL (escritura
CORAZÓN LLM configurado + lectura FlashBrain sin LLM) que cada request cae/aflora donde debe, por **29 tipologías**
(ESTADO/CORTO/LARGO + dedup, grafo, multi-fuente, olvido, episódica, escala, contradicciones, adversarial,
memoria→acción, anti-alucinación, validez-temporal, identidad-cross-sesión…). Corre como **loop autónomo
avanzar-primero** (ola de 80 → triaje bug/flaky/test-flaw → commit) hasta una **pasada de ORO fresca 0→N en verde**.

La primera batería del Observatory es **`Diálogo natural → memoria · gateway real`** (`cases4.py`): 15 turnos
ordinarios multi-hecho que prueban extracción y descarte, división en píldoras, importancia/capa/TTL, slots y
estado vigentes, correcciones y recall diferido. No utiliza frases artificiales «recuerda X». Run de control
2026-08-01: **15/15 PASS** con el CORAZÓN real `gpt-4.1-mini`; la evidencia completa queda en
`tests/runs/20260801-133729-memory-080645/`. Esta batería descubrió la pérdida de un incidente significativo dentro
de una parrafada y la promoción indebida de café/cansancio a largo plazo; ambos criterios quedaron corregidos.

La segunda batería es **`Vida cronológica · 180 días`** (`tests/memory/e2e/timeline/`): 966 operaciones sobre una
única BD con reloj inyectado. Simula actividad diaria, TTL 2/20/90 días, objetivos durables, corrección
Sevilla→Segovia en el día 45, refuerzo por frecuencia de consulta, consolidación nocturna, **REM diario durante los
180 días**, y presión de capacidad. Un caso aislado reproduce siempre su prefijo causal. La cronología usa átomos
estructurados para aislar el lifecycle; la extracción semántica pertenece al gateway v4 y a los corpus históricos.
Run de control 2026-08-01: **966/966 PASS**, vivienda 26 accesos/peso 0,995; arquitectura 4/peso 0,970; 35
recuerdos activos al final. La creación del corpus detectó y corrigió tres fallos reales: TTL almacenado pero no
aplicado, doble borrado FTS tras prune+evict y refuerzo indiscriminado de todo el paquete de contexto.
La metodología completa, cómo repetirla desde cero, la clasificación de fallos, cada-cuánto-se-cuestiona y las
fronteras conocidas (no-determinismo del CORAZÓN, recall-a-escala del embedding local) están en el **playbook
reutilizable**: `.meshkore/docs/ops/anexos/zaelar-memory-cycle-playbook.md`. Última corrida: 2026-07-12, **GOLD
1032/1032, 9 bugs de código arreglados** (resultados en `tests/memory/e2e/bot/resultados/20260712-ciclo-1000/`).
