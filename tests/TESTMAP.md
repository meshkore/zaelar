# El MAPA DE TESTS de zaelar — segunda opinión + índice navegable

> **Ejecutable:** `tests/run_testmap.py` es la ÚNICA fuente de verdad de la taxonomía (qué fichero cubre cada nodo).
> Este documento es la NARRATIVA: canales, veredicto, huecos y duplicación. Cuando muevas/añadas un test, toca el
> `.py`; esto solo si cambia la historia.

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
| 2 | FLASHBRAIN | 2.1 enrutado · 2.2 diálogo · 2.3 prompt · 2.4 cliente-LLM · 2.5 escalado/workers · 2.6 scheduler/rails · 2.7 Susurro · 2.8 búsqueda(vivo) |
| 3 | VOZ | 3.1 atención/VAD · 3.2 puente-nucleo · 3.3 mic→STT(vivo) · 3.4 bucle-voz(vivo) |
| 4 | WIDGETS | 4.1 ciclo/acciones/generador · 4.2 navegador · 4.3 música · 4.4 youtube · 4.5 mensajería |
| 5 | CONECTORES | 5.1 email · 5.2 mensajería · 5.3 música/spotify · 5.4 architect |
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
- **Enrutado (2.1)** se prueba por cuatro vías vivas solapadas (`tester/chain_suite.py`, `loop_cycle.py`,
  `domain_sea.py` + el unit `test_router.py`) — unificables en una suite parametrizada.
- **Tres "smoke"** en dos sitios (`tester/smoke.py` voz · `tests/e2e/smoke/run_full_smoke.py` integral ·
  `run_chat_over_livekit.py` chat). `run_full_smoke.py` es el paraguas.
- **Regresiones de escritura fechadas** (`test_write_precision_v2033.py` vs `v2050`, `test_write_changes_20260712.py`)
  van acumulándose — revisar si `v2033` queda subsumido por `v2050`.
- **`harness/`** (user_sim↔brain↔judge de texto) es el framework e2e más antiguo, solapado por los bot-runners
  nuevos (`tests/e2e/*/bot/`) — el más candidato a retirar.

**Ruido bajo carpetas de test** (no son tests): `tester/runs/*`, `tests/e2e/memory/bot/resultados|runs/*` son SALIDAS
históricas — deberían estar gitignoradas, fuera de la taxonomía.

## Cómo se EXTIENDE (1000→10000)

Añadir casos a los `paths` de un nodo, o un nodo `N.M` nuevo bajo su dominio (o un dominio nuevo). La espina no se
reescribe: crece por hojas. Un caso de uso nuevo del sistema = un nodo nuevo aquí + su test, en el mismo commit.
