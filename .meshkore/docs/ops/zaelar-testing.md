# zaelar — Playbook de testing del bot ("lanza un test del bot")

> **Trigger**: cuando el operador dice **"lanza un test del bot"**, **"lanza la batería (de escenarios)"**,
> **"prueba el bot en tuen"** o similar → ejecutar ESTE playbook de principio a fin. No hay que recordar los pasos
> de memoria: viven aquí. La descripción de las PIEZAS del sistema vive en `zaelar-architecture.md`/`CLAUDE.md`;
> este doc es SOLO **cómo se prueba** (qué, con qué prioridad, cómo se evalúa, dónde se archiva).

El bot se prueba **solo, sin micrófono humano**: un agente **tester** (`tester/`) se une a la sala LiveKit como 2º
participante, HABLA por TTS y ESCUCHA por STT; un **JUEZ** (GLM-4.6 vía Z.AI, fallback DeepSeek) evalúa el
comportamiento OBSERVABLE (acciones de frontend, tags del cerebro, escaladas, latencias) leyendo `GET /events`.
Detalle del arnés: **INI-013** (`.meshkore/roadmap/initiatives/INI-013-voice-tester.md`).

> **Mapa de tests navegable** — toda la superficie de pruebas es ahora recorrible por
> **`tests/run_testmap.py`** (eje **dominio → caso de uso → canal**, numerado `1.1`/`2.1`/…), con la narrativa en
> **`tests/TESTMAP.md`**. Son **9 dominios**; el **dominio 9 = HOMEOSTASIS** (la capa autónoma de salud de la
> máquina, `nucleo/homeostasis.py` / `nucleo/test_homeostasis.py`, V2-070).

---

## Paso 0 — ALINEACIÓN tests ↔ sistema (SIEMPRE lo primero, antes de lanzar nada)

Antes de probar hay que garantizar que **los escenarios prueban la versión ACTUAL del sistema**. Checklist:

1. **Módulos principales cubiertos**: cada capacidad viva tiene al menos un escenario en `tester/scenarios.py`
   (ver el catálogo en `tester/anexos/catalogo-escenarios.md`): conversación · memoria (guardar/recall/corrección) ·
   widgets (mostrar/crear/borrar) · búsqueda web factual · navegación web profunda (Wallapop/coches.net) ·
   mensajería unificada · conectores · cluster · paste/chat · multiidioma · **seguridad de datos (bóveda, V2-060)**.
2. **Cambios de las últimas ~48 h**: `git log --oneline --since='48 hours ago'`. Por cada capacidad NUEVA o
   CAMBIADA (una tool nueva, un proveedor nuevo, un flujo nuevo), confirmar que hay escenario que la ejercita; si
   no, **añadirlo a `tester/scenarios.py` + al catálogo** antes de lanzar. Mira también las **decisiones clave** con
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

1. **Unit** — `nucleo/susurro/test_susurro.py` (fricción es/en, catálogo, aplicadores, engine con LLM falso,
   cooldown, kill-switch). Corre con el pytest normal.
2. **Integración headless** — `tests/e2e/susurro/run_probe_suite.py` (server vivo): simula fricción por el probe
   (queja tras una acción), exige la MAQUINARIA completa (trigger → request CON payload → response → auditoría
   completa, eventos kind `susurro` en el timeline) y verifica que un `repair_say` sale HABLADO en el turno
   siguiente (el probe drena `brain_notes`). El JUICIO del modelo se reporta sin fallar la suite (decidir
   `corrections=[]` ante un tramo sano es correcto). **Cada run appendea a
   `tests/e2e/susurro/history.jsonl`** — el histórico LONGITUDINAL: con el tiempo debe bajar la fricción por
   sesión y mejorar la calidad de diagnóstico (revisar ese fichero al evaluar oleadas). Ojo al `cooldown_s`
   (def 60s) entre runs.
3. **Voz e2e** — escenario `susurro_reparacion` en `tester/scenarios.py` (rotación del cron): el tester se queja
   de viva voz y el juez verifica los eventos `susurro` + la reparación natural. Queja sin NINGÚN evento
   susurro = FAIL de maquinaria.

Al ARREGLAR un finding del Susurro (los consume el dev-loop desde `.meshkore/logs/susurro/findings.jsonl`),
tratar el finding como el hallazgo de una oleada: fix + test de control + re-verificar + documentar.

## Grupo «canal de cluster» — conversar con AGENTES (V2-069 «una sola mente»)

El canal de cluster es agente-a-agente (NO voz), así que el tester de voz no lo cubre — tiene su propio grupo, que
verifica la INTELIGENCIA de conducción (no re-presentarse, fase, objetivo presente, corte de bucle) y la SEGURIDAD
(perfil untrusted: tools off + identidad-safe). Dos anclas:

1. **Regresión determinista (sin LLM)** — `connectors/meshkore/test_capsule.py` + `test_capsule_flow.py` +
   `test_security.py` (guard de atasco). Capturan el prompt EXACTO que el bridge da al cerebro por turno y verifican:
   NO re-presentarse tras el 1er contacto, progresión de fase (saludo→sondeo→trabajo), objetivo del operador presente,
   cápsula inyectada, `build_cluster_system` identidad-safe (cero PII del operador), tools-off estructural, y la
   escalada de atasco (repetición → 1 asertivo → callar + avisar). Corren con el pytest normal.
2. **e2e con el MOTOR REAL** — `tests/e2e/cluster/run_cluster_suite.py`: scriptea una conversación de peer y la pasa
   por `nucleo/flash/cluster.py::respond` (GLM-5.2) con el MISMO framing del bridge (cápsula + fence + trailer).
   Invariantes DUROS (maquinaria + identidad-safe + no-re-presentación) tumban la suite; el juicio blando
   (intro/on-goal/conciso) se reporta. Appendea a `tests/e2e/cluster/history.jsonl` (longitudinal). Requiere la key
   del tier del canal (carga `.env` + credential store solo).

---

## Cómo se LANZA

- **Batería completa** (todos los escenarios, con settle entre ellos para no saturar el worker THREAD):
  `bash tester/run_battery.sh` → escribe una tabla resumen `tester/runs/battery_summary_<hhmmss>.tsv` + un informe
  por escenario `tester/runs/report_*.{json,md}`. Variables: `BATTERY_SCENARIOS="a b c"` (subconjunto),
  `BATTERY_SETTLE=12` (s entre escenarios), `BATTERY_MAX_RUN=360` (watchdog por escenario).
- **Un solo tick** (rota por cursor): `bash tester/cron_tick.sh` — imprime un bloque `VERDICT status=…`.
- **Un escenario suelto**: `./.venv/bin/python -m tester.run --scenario <id> --no-open --hold 0`.
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

- **Catálogo de escenarios** (qué se prueba y por qué): `tester/anexos/catalogo-escenarios.md` — se mantiene
  alineado con `tester/scenarios.py` en el Paso 0.
- **Informe de cada sesión de test**: al cerrar una tanda, crear una carpeta **`tester/reports/<YYYYMMDD>-<desc>/`**
  (fecha invertida año-mes-día + descripción corta, p. ej. `tester/reports/20260711-bateria-v2024-google-prewarm/`)
  con: la tabla resumen (`.tsv`), los `report_*.{json,md}` relevantes, y un **`INFORME.md`** con: qué se probó, la
  tabla de resultados, hallazgos (bug real vs ruido), arreglos hechos, y latencias antes/después. Así, repetir la
  batería una semana después deja un histórico comparable. (Los `tester/runs/` son el scratch en crudo; `reports/`
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
(`tests/e2e/memory/bot/`) role-play una PERSONA a lo largo de 1000+ pasos y verifica por el CAMINO REAL (escritura
CORAZÓN LLM local + lectura FlashBrain sin LLM) que cada request cae/aflora donde debe, por **29 tipologías**
(ESTADO/CORTO/LARGO + dedup, grafo, multi-fuente, olvido, episódica, escala, contradicciones, adversarial,
memoria→acción, anti-alucinación, validez-temporal, identidad-cross-sesión…). Corre como **loop autónomo
avanzar-primero** (ola de 80 → triaje bug/flaky/test-flaw → commit) hasta una **pasada de ORO fresca 0→N en verde**.
La metodología completa, cómo repetirla desde cero, la clasificación de fallos, cada-cuánto-se-cuestiona y las
fronteras conocidas (no-determinismo del CORAZÓN, recall-a-escala del embedding local) están en el **playbook
reutilizable**: `.meshkore/docs/ops/anexos/zaelar-memory-cycle-playbook.md`. Última corrida: 2026-07-12, **GOLD
1032/1032, 9 bugs de código arreglados** (resultados en `tests/e2e/memory/bot/resultados/20260712-ciclo-1000/`).
