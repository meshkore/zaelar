# El MAPA DE TESTS de zaelar — segunda opinión + índice navegable

> **Agentes:** empezar por `tests/README.md`. Este fichero explica la taxonomía; `tests/README.md` explica cómo
> ejecutar, aislar y reportar pruebas desde terminal mientras el operador observa `127.0.0.1:8765`.

> **Contrato canónico:** `tests/<suite>/suite.json` declara el test principal y sus pasos; el mapa numerado existente
> aporta durante la migración las rutas pytest. `tests/platform/catalog.py` los normaliza con los proveedores de
> corpus en un solo schema 2. La especificación está en `tests/platform/SCHEMA.md`.

## Entrada unificada y observabilidad en tiempo real

La plataforma canónica vive en `tests/platform/`. Mantiene el mapa numerado, pero añade un runner común, eventos
JSONL durables y un dashboard local que se abre automáticamente. Es la entrada preferida para personas, Codex y
Claude Code:

```bash
./.venv/bin/python -m tests list
./.venv/bin/python -m tests run memory            # deterministas; abre/reemplaza el visor en :8765
./.venv/bin/python -m tests run memory --case memory::group::1.4::v4           # gateway conversacional principal
./.venv/bin/python -m tests run memory --case memory::group::1.4::timeline-6m  # cronología/lifecycle
./.venv/bin/python -m tests run journey           # historia causal memoria→widgets→worker→cluster
./.venv/bin/python -m tests run agent-headless
./.venv/bin/python -m tests run voice --live      # requiere `make run`
./.venv/bin/python -m tests run voice --case voice::scenario::agenda
./.venv/bin/python -m tests run memory --case memory::v1::0000
./.venv/bin/python -m tests run all --no-open     # CI / terminal pura
./.venv/bin/python -m tests replay <run-id>
```

Cada ejecución queda en `tests/runs/<run-id>/` (gitignored): `run.json`, `events.jsonl`, artefactos y el log del
dashboard. El exit code sigue siendo el de la suite. El **pass rate determinista** y el **score del juez LLM** se
presentan separados; un juez nunca puede convertir en verde una aserción fallida.

La estructura física está unificada por dominio en `tests/<suite>/`. Todas las suites exponen exactamente el mismo
árbol `suite → pasos ordenados → grupos → casos`. Pytest se adapta automáticamente; Memoria, Voz y Headless añaden
corpus ricos mediante `catalog_provider`. Cada caso conserva input, expectativa, verificación, ruta interna, fuente,
acción ejecutable y resultado. Un pytest no asociado aparece como `unmapped` en vez de desaparecer silenciosamente.

`--no-open` es el modo normal para Codex/Claude Code: evita abrir una ventana, pero mantiene el servidor y la
telemetría del Observatory para el espectador humano. No significa "sin UI" ni cambia el resultado del test.

En **Memoria**, la primera sección es `Diálogo natural → memoria`: 15 turnos focalizados que atraviesan el gateway
real CORAZÓN y muestran texto original, píldoras extraídas, descarte, capas, slots, estado, correcciones y recall.
Después aparece `Vida cronológica · 180 días`: 966 operaciones sobre una sola BD aislada. Avanza el reloj real,
inserta actividad, refuerza objetivos, corrige hechos, consolida y ejecuta REM cada día (180 veces), y verifica
expiración/retención. Todo caso stateful reconstruye obligatoriamente su prefijo causal desde una BD fresca.

En **Viaje integral**, 26 pasos comparten un único engine y workspace desechables. El plan hace explícitos sus
`consumes`/`produces`: una ubicación memorizada alimenta tiempo y widgets; una cita creada se consulta después; una
búsqueda Wallapop se observa y refina sin duplicarla; una mudanza corrige el estado y sobrevive a otro reset. Es la
prueba de interacción compleja. Micrófono/STT/WebRTC, render Playwright y WebSocket remoto siguen siendo fronteras
vivas separadas y no se consideran verdes por haber pasado este recorrido.

## Cómo se responde «¿funciona todo bien?»

```
./.venv/bin/python tests/run_testmap.py          # árbol numerado + veredicto (solo deterministas, sin servidor)
./.venv/bin/python tests/run_testmap.py --domain 6   # un dominio
./.venv/bin/python tests/run_testmap.py --list       # solo la taxonomía
./.venv/bin/python tests/run_testmap.py --live       # + la lista de nodos VIVOS y su comando
```

A "¿el 1 funciona?" → "1.1 ✅, 1.2 ✅, …". Estado 2026-07-25: **~940 tests deterministas, 9 dominios, TODO VERDE.**

## La espina: DOMINIO → CASO DE USO → CANAL

Nueve dominios. Cada caso de uso `N.M` declara su **canal de entrada** — por dónde entra el estímulo, que es lo que
de verdad distingue "la voz funciona pero el chat no":

- **unidad** — lógica pura, sin servidor (pytest, corre en CI).
- **http** — contra `POST /api/...` del servidor (pytest o runner).
- **voz** — sesión LiveKit real con STT/TTS (VIVO).
- **chat-sobre-livekit** — data-channel `zaelar-text` → agent → SSE, el camino EXACTO del navegador (VIVO).
- **peer-de-cluster** — turno de un agente externo por el bridge de meshkore.

| # | Dominio | Casos de uso |
|---|---------|--------------|
| 1 | MEMORIA | 1.1 BD/estado · 1.2 recuperación · 1.3 escritura · 1.4 recall(vivo) · 1.5 REM · 1.6 bóveda · 1.7 API · 1.8 UI-estado |
| 2 | FLASHBRAIN | 2.1 enrutado · 2.2 diálogo · 2.3 prompt · 2.4 cliente-LLM · 2.5 escalado/workers · 2.6 scheduler/rails · 2.7 Susurro · 2.8 búsqueda(vivo) · 2.11 conversación+juez(vivo) |
| 3 | VOZ | 3.1 atención/VAD · 3.2 puente-nucleo · 3.3 mic→STT(vivo) · 3.4 bucle-voz(vivo) |
| 4 | WIDGETS | 4.1 ciclo/acciones/generador · 4.2 navegador · 4.3 música · 4.4 youtube · 4.5 mensajería · 4.6 agenda-XSS |
| 5 | CONECTORES | 5.1 email · 5.2 mensajería · 5.3 música/spotify · 5.4 architect · 5.5 WhatsApp-allowlist |
| 6 | CLUSTER | 6.1 cápsula/framing · 6.2 seguridad · 6.3 ingesta→memoria · 6.4 conversación-peer(vivo) |
| 7 | SERVER/OBS | 7.1 bus/log · 7.2 SSE · 7.3 chat-transporte-real(vivo) · 7.4 smoke-integral(vivo) |
| 8 | ENERGÍA/CONFIG | 8.1 energía/límites · 8.2 perfiles/v2/doctor/credenciales |
| 9 | HOMEOSTASIS | 9.1 detección/seguridad/eviction/rotación · 9.2 salud-viva(vivo) |

## Segunda opinión (qué está bien y qué falta)

**Bien:** la cobertura determinista es amplia y honesta — memoria (1.x) y FlashBrain (2.x) están muy probados; la
seguridad del cluster tiene 48 tests (6.2); el hueco del 2026-07-25 (chat por transporte real) ya tiene su e2e (7.3).

**Huecos conocidos (no falso-verde):**
- **7.3 / 9.2 / 1.4 / 2.8 / 3.x / 6.4 son VIVOS** — exigen `make run` + proveedores. No corren en CI; el smoke
  integral (7.4) es la red de "el sistema entero está en pie".
- **Voz (3.3/3.4)** no tiene test CI-safe: todo lo que toca LiveKit/STT/TTS es vivo por naturaleza.
- **Widgets (4.x), conectores (5.x), energía (8.x)** son unit-only: no hay e2e que ejerza mensaje-entrante-real →
  respuesta a través del cerebro vivo. Candidatos a e2e futuros.
- **Frontend**: cero tests (`frontend/` no tiene specs).

**Duplicación a consolidar (deuda, no bug):**
- **Enrutado (2.1)** se prueba por cuatro vías vivas solapadas (`tests/voice/e2e/agent/chain_suite.py`, `loop_cycle.py`,
  `domain_sea.py` + el unit `test_router.py`) — unificables en una suite parametrizada.
- **Tres "smoke"** en dos sitios (`tests/voice/e2e/agent/smoke.py` voz · `tests/infrastructure/e2e/smoke/run_full_smoke.py` integral ·
  `run_chat_over_livekit.py` chat). `run_full_smoke.py` es el paraguas.
- **Regresiones de escritura fechadas** (`test_write_precision_v2033.py` vs `v2050`, `test_write_changes_20260712.py`)
  van acumulándose — revisar si `v2033` queda subsumido por `v2050`.
- **`tests/agent_headless/harness/`** (user_sim↔brain↔judge de texto) es el framework e2e más antiguo, solapado
  por los bot-runners de cada dominio — candidato a converger en un único formato de escenario.

**Ruido bajo carpetas de test** (no son tests): `tests/runs/agent/*`, `tests/memory/e2e/bot/resultados|runs/*` son SALIDAS
históricas — deberían estar gitignoradas, fuera de la taxonomía.

## Cómo se EXTIENDE (1000→10000)

Añadir casos a los `paths` de un nodo, o un nodo `N.M` nuevo bajo su dominio (o un dominio nuevo). La espina no se
reescribe: crece por hojas. Un caso de uso nuevo del sistema = un nodo nuevo aquí + su test, en el mismo commit.
