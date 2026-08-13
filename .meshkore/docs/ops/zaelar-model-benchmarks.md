# zaelar — Registro de benchmarks de modelos y latencia (canónico)

> **Propósito**: la "parada de benchmarkings". Un ÚNICO sitio donde viven TODAS las pruebas de modelos de lenguaje
> (FlashBrain, navegador, tester), sus latencias reales, y las decisiones tomadas — para no re-experimentar
> y poder decidir con conocimiento de causa al cambiar de modelo. Antes estaba repartido entre INI-008 (Fases 2d/2e)
> e INI-013; esto lo consolida. **Mantener vivo**: cada prueba de modelo nueva AÑADE una fila/entrada fechada aquí.
> Detalle narrativo de cada ronda → sigue en la iniciativa correspondiente; la TABLA de resultados vive aquí.
>
> **RÉPLICA VISIBLE AL USUARIO (V2-077, 2026-07-26):** `engine/config/model_benchmarks.py` (sirve
> `GET /api/config/benchmarks`, pintado por `engine/frontend/app/components/BenchmarksPanel.js` — botón "¿Quieres
> ver los benchmarks…?" al fondo de Config → Cerebro rápido) es un resumen CURADO de este doc para el operador,
> igual que `web/technology` es una foto curada de la arquitectura — no un parser automático. **Toda decisión de
> modelo nueva que añadas aquí, añádela TAMBIÉN allí** (coste, latencia, tool-calling/alucinación, veredicto) o la
> réplica queda desactualizada silenciosamente.
>
> **ATAJO — «¿qué modelos usa la MEMORIA y por qué?»** (la pregunta que más se repite): respuesta canónica y
> autosuficiente en **`zaelar-memory.md §Modelos de la memoria`**. Detalle denso aquí en **§12.3** (CORAZÓN de
> escritura) y **§12.4** (sueño REM). **Informes CRUDOS de cada corrida, versionados**:
> `tests/memory/e2e/bot/resultados/` (ver su `README.md` — índice de corridas y cómo leer un `report.json`).
> Las tres capas dicen lo mismo a propósito: la corta para responder, la densa para justificar, y los datos
> crudos para que nadie tenga que fiarse de la palabra de nadie.

## 0. El modelo mental de latencia (leer primero)

zaelar "todo local" corre **STT (Whisper Metal), TTS (Kokoro Metal) y LLM (qwen Ollama) sobre la MISMA GPU Apple**.
Se pelean. Ésta es la causa raíz de "todo va lentísimo", más que la velocidad de ningún componente aislado.

Latencia percibida de un turno = `EOU` (fin-de-habla, VAD) + `STT dur` (transcribir, POST-habla) + `LLM ttft`
(primer token) + `TTS ttfb` (primer audio). El cuello de botella se MUEVE según qué tiene la GPU ocupada.

**Hallazgo clave (sesión real `20260708-105150`, ver §4):** el `STT dur` que se ve en los logs **NO es "lo que
hablaste"** — es cómputo real POST-habla, pero está inflado por CONTENCIÓN de GPU, no por Whisper. Prueba: `dur` y
`audio` están desacoplados — 13 s de audio → `dur=0.66s` (GPU libre), pero un "No" de 1,86 s → `dur=5.75s` (GPU
ocupada por el LLM/TTS). Whisper turbo en M4 Max es sub-segundo cuando tiene la GPU para él. **Corolario de
diseño: sacar el LLM de la GPU local (capa rápida a una API cloud) libera la GPU para STT+TTS → doble mejora
(STT vuelve a sub-segundo Y el LLM corre en paralelo sin pelear).**

---

## 1. Capa rápida (FlashBrain) — modelos LOCALES (Ollama), M4 Max / 48 GB

Arnés: prompt real (`build_flash_system`) + las 2 funciones reales (`escalate_to_slowbrain`/`set_style_directive`),
13+2 casos (oleada A de INI-013) salvo nota. "Fiabilidad tool-calling" = % que invocó la función nativa cuando
debía. Detalle: INI-008 Fases 2d/2e.

| Modelo | Disco | Fiabilidad tool-calling | TTFT (caliente) | Veredicto |
|---|---|---|---|---|
| **`qwen2.5:14b-instruct`** ⬅ producción actual | 9 GB | **~45%** (6/13; 14/31 con más muestras) | 0,3–2 s (picos por contención) | mejor local, pero techo ~45% |
| `qwen2.5:7b-instruct` | 4 GB | baja (a veces escribe la llamada como texto) | 0,3–1 s | descartado |
| `qwen2.5:32b-instruct` | ~20 GB | media (mejor en casos, huella de memoria muy justa) | 0,9–4 s | descartado por riesgo memoria |
| `hermes3:8b` (especialista FC) | 5 GB | peor que baseline; filtró `<THINKING>` crudo | — | descartado |
| `firefunction-v2` (especialista FC) | 39 GB | 0/15 (todos timeout, fallback CPU) | — | inviable en este HW |
| `qwen3:14b` / `qwen3:30b-a3b` | 9–18 GB | modo "thinking" ON por defecto → viola no-razonadores | 8–78 s | TODA la familia qwen3 descartada |
| `gemma3:27b` | 17 GB | 0/15 — Ollama: "does not support tools" | — | sin FC, descartado de raíz |
| `mistral-small` | 14 GB | 3/15; inventó fuga de formato nueva | ~0,7 s + picos | descartado |
| `llama3.3:70b` | 42 GB | no completado (timeout warm, fallback CPU 28%) | >240 s | inviable en 48 GB compartidos |

**Nota HW menos potente**: `firefunction-v2`/`llama3.3:70b` ya hacen fallback a CPU aquí → inutilizables en máquinas
con menos RAM unificada. qwen3 = desactivar "thinking" antes de considerarla. gemma3 = sin FC en ningún HW.

---

## 2. Capa rápida (FlashBrain) — modelos CLOUD vía AIMLAPI (research 2026-07-08)

⚠️ **Los TTFT de abajo son de la API NATIVA (artificialanalysis.ai / proveedor), NO de AIMLAPI.** AIMLAPI añade un
hop + Cloudflare → **el TTFT real por AIMLAPI es MÁS ALTO** (los ~0,4–0,6 s nativos se sienten ~1,1–1,6 s, según
nuestros propios logs). Usar como señal de RANKING, no como el número que se siente. Ids verificados contra
`docs.aimlapi.com`.

| Modelo (id AIMLAPI) | TTFT nativo | tps | Precio /1M (in/out) | Tool-calling | Nota |
|---|---|---|---|---|---|
| `google/gemini-2.5-flash-lite-preview` (thinking OFF) | ~0,37 s | 226 | ~muy barato | ✅ confirmado AIMLAPI | el más rápido; el "menos listo"; verboso |
| `x-ai/grok-4-fast-non-reasoning` | ~0,5–0,6 s | ~207 | $0,21 / $0,53 | ✅ confirmado AIMLAPI | no-razonador POR CONSTRUCCIÓN (sin trampa thinking); buen equilibrio |
| `google/gemini-2.5-flash` | ~0,45 s | ~205 | ~$0,30 / $2,50 | ✅ confirmado AIMLAPI | el más listo del trío rápido; puede activar thinking; verboso |
| `anthropic/claude-haiku-4.5` | ~0,60 s | ~120 | $1,3 / $6,5 | ✅ (tools nativas Anthropic) | mejor fiabilidad FC + español; el más caro |
| `deepseek/deepseek-v4-flash` | ~1,26 s | 111 | **$0,182 / $0,364** | ✅ confirmado AIMLAPI | el más barato; el MÁS LENTO del shortlist |
| `moonshot/kimi-k2-6` / `k2-5` | 0,4–2,5 s (varía) | 77–431 | $0,21–0,78 / $3,9–5,2 | fuerte agéntico; FC en AIMLAPI SIN confirmar | medir TTFT por AIMLAPI antes de usar |

**⚠️ Trampa Gemini 3.x flash-lite**: `gemini-3-1-flash-lite` mide **~5,75 s TTFT** porque trae reasoning ON por
defecto = razonador en el path de voz (prohibido). Para Gemini quedarse en **2.5-flash/2.5-flash-lite con thinking
OFF**; un 3.x flash solo tras fijar thinking off y RE-MEDIR.

**Cerebras/Groq/SambaNova**: NO confirmados como modelos dedicados en AIMLAPI. Para esa velocidad habría que ir
directo al proveedor, no por AIMLAPI.

**AIMLAPI reliability**: tras Cloudflare → 403/1010 intermitentes por firma del request
(`nucleo/flash/fast_client.py` spoofea UA de navegador + degrada al SlowBrain; mantener). TTFT más alto/variable
que nativo.

### Head-to-head REAL (2026-07-08) — prompt + `_TOOLS` reales del FlashBrain, escenario Wallapop que falló en vivo
Arnés: `build_flash_system` real (33 KB) + los 4 `_TOOLS` reales (`browse_web`/`automate_web`/`escalate_to_slowbrain`/
`set_style_directive`), 7 casos, TTFT real POR AIMLAPI (no nativo). Script: `scratchpad/bench_fastbrain.py`.
Caso clave = `search_IN_wallapop` ("con Wallapop abierto, búscame ahí una moto…") → debe llamar `automate_web`.

| Modelo | Routing OK (7 casos) | `search_IN_wallapop`→automate | TTFT típico | Veredicto |
|---|---|---|---|---|
| **`x-ai/grok-4-fast-non-reasoning`** | **7/7 ✅** | ✅ **1,35 s** | **~0,8–1,8 s** | 🏆 ELEGIDO |
| `google/gemini-2.5-flash` | 7/7 ✅ | ✅ 1,66 s | ~1,1–1,9 s | muy bueno (alt) |
| `deepseek/deepseek-v4-flash` | 7/7 ✅ | ✅ 2,38 s | ~1,0–1,3 s (dur 2–4,6 s) | bueno, el más barato (alt) |
| `anthropic/claude-haiku-4.5` | 7/7 ✅ | ✅ 2,78 s | ~1,7–3,6 s | fiable, el más lento/caro (alt) |
| `google/gemini-2.5-flash-lite-preview` | **4/7 ❌** | ❌ (no llamó nada) | ~0,8–1,7 s | rápido pero tonto en routing — DESCARTADO |
| `qwen2.5:14b-instruct` (LOCAL, era prod) | 5/7, pero… | ✅ pero **27 s ttft** | **timeout 45 s** en "abre Wallapop" | 💀 confirma el desastre en vivo |

Conclusión: en el caso EXACTO que falló en producción, qwen local tardó 27 s (y timeout 45 s sin llamar nada al
abrir Wallapop). grok lo clava en 1,35 s con 7/7 de routing. `gemini-flash-lite` (el "rápido barato") confirmó el
aviso de la §2: 4/7, no invoca las tools. **Decisión: capa rápida → `x-ai/grok-4-fast-non-reasoning` (§5).**

### Shortlist para "sub-segundo + tool-calling fiable + español + barato"
1. **`grok-4-fast-non-reasoning`** — mejor equilibrio; no-razonador por construcción (sin trampa). ⬅ recomendado.
2. **`gemini-2.5-flash-lite-preview` (thinking off)** — el más rápido/barato; el menos listo (riesgo en enrutado de tools).
3. **`gemini-2.5-flash`** — el más listo del trío rápido; para desambiguar/enrutar tools mejor.
4. **`claude-haiku-4.5`** — máxima fiabilidad FC + español; caro (reservar si el enrutado de tools sigue fallando).
5. **`deepseek/deepseek-v4-flash`** — suelo de coste / fallback; TTFT el peor del grupo.

---

## 3. Otros carriles (referencia)

- **Navegador — automatizador** (`NAVEGADOR_AGENT_*`, bucle `automate_web`): por defecto `anthropic/claude-haiku-4.5`
  vía AIMLAPI (un cerebro barato DEDICADO, NO el SlowBrain de `nucleo/`). Es un modelo cloud decente ya; el fallo de
  la sesión `105150` NO fue del automatizador sino de la CAPA RÁPIDA (FlashBrain) enrutando mal (mandó la tarea a
  `browse_web/search`→Bing en vez de `automate_web` sobre Wallapop).
- **Tester (INI-013)**: DRIVE = DeepSeek vía AIMLAPI (barato); JUEZ = GLM-4.6 vía Z.AI (fallback DeepSeek).
- **Reasoners (GLM-4.6/5.2)**: NUNCA en el path de voz. Solo cluster/uso específico async.

---

## 4. Latencias de sesiones REALES

### Sesión `20260708-105150` (BRAIN=duo, `qwen2.5:14b` local, STT/TTS Metal locales)
- **STT** (`dur` vs `audio`): GPU libre → sub-segundo aun con frases largas (`0.66s`/13 s, `0.42s`/8 s); GPU
  contendida → 5–18 s desacoplado de la longitud (`5.75s`/1,86 s; `18.23s`/40,9 s). = **contención de GPU**, no Whisper.
- **LLM ttft**: primer turno (saludo) **69,9 s** (prompt-eval frío del 14b con contexto grande); en conversación
  **0,35–1,1 s** (GPU libre) vs **8–25 s** (contención/escalado).
- **TTS ttfb**: normal 0,1–2,6 s; picos **5,4–5,6 s** bajo saturación de GPU.
- **Intelligence**: la capa rápida enrutó MAL el navegador (Bing en vez de Wallapop), no encadenó open→automate,
  casi no escaló, se quedó conversacional. Tools bien diseñadas; el modelo local no es lo bastante listo para
  enrutar entre varias tools. → argumento para capa rápida cloud.

### V2-011 (2026-07-09) — regresión de latencia del port a `nucleo/` y su fix (memoria fuera del turno)

El port a `nucleo/` (V2-004) metió el retriever COMPLETO de memoria en el camino caliente del turno:
`build_flash_system(recall_query=text)` disparaba `memory.query()` (embeddings HTTP a Ollama + RRF + graph +
refuerzo) **síncrono en el event loop, cada turno, antes del LLM**. Medido con el desglose de T113 (evento `timing`
en `/debug`): `mem_query_ms` = **112–452 ms por turno** era TODO el coste de armar el prompt (`mem_state_ms`≈0,1,
`briefs_ms`≈1–2, `live_ms`≈0) — y bloqueaba el loop, así que se sumaba al TTFT y frenaba el TTS.

**Fix (V2-011, T114–T116):** estado cacheado por sesión (`memory_cache`, TTL 300 s, refresco async, invalidación
por `memory.updated`) → `mem_state_ms`≈0; recall semántico **bajo demanda** (heurística `needs_recall`) y **fuera
del loop** (`asyncio.to_thread`) → solo dispara embeddings cuando el turno pide recordar, y sin bloquear el loop.

Medición con el tester (mismo M4 Max, grok-4-fast-non-reasoning cloud, STT/TTS Metal locales; `fast_ms` = del
turno cerrado del FlashBrain, `ttft_ms` = primer token):

| Escenario | ANTES (V2-004) | DESPUÉS (V2-011) `fast_ms` | `ttft_ms` | Notas |
|---|---|---|---|---|
| `memory`   | 3726 avg / 4742 max | **p50 1139 · avg 1132 · max 1247** | p50 1031 | recall correcto ("coche en el taller") en 2 turnos; `mem_query` 137/172 ms OFF-LOOP, solo en esos 2 |
| `widget`   | 5885 avg / 8900 max | **p50 1031 · avg 1045 · max 1347** | p50 864  | ningún turno tocó el retriever |
| `conversation` | — | p50 1605 · avg 2158 · max 4075 | p50 1432 | el max/avg lo infla el 1er turno frío (4 s, kickoff) + turnos que ESCALAN (coste de escalada, ajeno a V2-011); charla pura 751–2070 ms |

**Resultado:** la regresión de memoria eliminada — `mem_state`=0 (caché), `mem_query` solo en turnos de recall y
fuera del loop. `memory`/`widget` p50 ~1 s (×3–6 más rápido, sin picos); recall REAL conservado. Los picos que
quedan en `conversation` son cold-start del 1er turno + escaladas, no la memoria.

---

## 5. Decisión y config actual

- **Producción (desde 2026-07-15)**: `grok-4.20-0309-non-reasoning` vía **xAI DIRECTO**
  (`config/v2.json §fast` → `provider:"xai"`, `base_url:"https://api.x.ai/v1"`, key = `XAI_API_KEY` en el credential
  store). Se pasó de AIMLAPI a xAI directo porque el store solo tiene `XAI_API_KEY`/`GROQ_API_KEY` (no `AIMLAPI_KEY`):
  el default heredado (Haiku vía AIMLAPI) dejaba el turno sin credencial → fallback "Uf, se me ha ido un momento".
  `fast_client.py::resolved_api_key()` resuelve la key **por endpoint** (x.ai/groq.com/aimlapi/gemini). Historial:
  fue `x-ai/grok-4-fast-non-reasoning` vía AIMLAPI (desde 2026-07-08), luego Haiku 4.5 vía AIMLAPI (V2-034,
  2026-07-12, por fiabilidad de routing). Alternativas hoy: Haiku/AIMLAPI o Groq (`llama-3.3-70b-versatile`) metiendo
  su key en el store. NUNCA local en la voz: `qwen2.5:14b-instruct` medido ~19 s/turno + patoso (contención de GPU).
  Bonus arquitectónico (se mantiene): el LLM en la nube saca la GPU Metal → libera STT (Whisper) + TTS (Kokoro) locales.
- **Alternativas validadas** (mismo benchmark, todas 7/7 routing) por si grok da problemas de fiabilidad/Cloudflare:
  `google/gemini-2.5-flash`, `deepseek/deepseek-v4-flash` (más barato), `anthropic/claude-haiku-4.5` (más fiable, caro).
  Camino de vuelta a LOCAL documentado en el `.env` (bloque comentado).
- **Pendiente de medir en producción**: TTFT real de grok en sesión de voz completa (no solo el benchmark aislado) y
  confirmar que la latencia percibida baja de verdad al liberar la GPU (comparar STT `dur` antes/después).
- Cambiar de modelo → actualizar este doc (fila §1/§2 + entrada §5) Y el `.env` Y la nota de routing de CLAUDE.md.

### Ronda 2026-07-08 (tarde) — proveedores DIRECTOS + recorte de prompt (arnés `scratchpad/bench_fastbrain.py`)

Objetivo: bajar el TTFT de ~1 s (grok por AIMLAPI) yendo a un proveedor directo. **Conclusión: no hay salto de
latencia posible por cambio de proveedor — grok es ~1 s por sí mismo; el proxy AIMLAPI NO era el cuello.**

| Proveedor · modelo | Routing (7 casos) | TTFT | Veredicto |
|---|---|---|---|
| **AIMLAPI `x-ai/grok-4-fast-non-reasoning`** (producción) | **7/7** | ~1,0 s | 🏆 se mantiene (unifica coste en un sitio) |
| Groq `llama-3.3-70b-versatile` | 3/7 (rechazó tool-calls) | rate-limited 57 s (free) | ❌ |
| Groq `meta-llama/llama-4-scout-17b-16e` | 4/7 (no escala memoria/estilo) | 1–21 s (rate-limit) | ❌ |
| Groq `openai/gpt-oss-120b` | 0/7 (413 request too large; razonador) | — | ❌ (viola no-razonadores) |
| Groq: **NO hospeda Kimi K2** en la cuenta | — | — | descartado como capa rápida |
| xAI directo `grok-4.20-0309-non-reasoning` | 6/7 (falló escalar memoria) | ~0,97 s | tie en latencia, peor routing → guardado como perfil de demo |

- **Groq descartado**: su catálogo no tiene un no-razonador que enrute nuestras 4 tools; free tier limita por tamaño/rate.
- **xAI directo**: mismo ~1 s que AIMLAPI (el proxy no añadía latencia relevante) y 6/7 con el modelo nuevo. Key en el
  store de credenciales por si se usa como perfil de demo (evita los 403 de Cloudflare de AIMLAPI), pero NO es más rápido.
- **Recorte de prompt (capa rápida)**: `build_flash_system` 32,9K→~29,4K chars (`_FAST_RULES` −20%, briefs por
  DISPONIBILIDAD). Re-benchmark contra AIMLAPI grok: **7/7 mantenido**, TTFT 0,95 s. Lección: **a 28-33K el tamaño del
  prompt NO mueve el TTFT de grok** (0,95–1,1 s con 28K/29K/33K) → el recorte gana COSTE (~10% tokens/turno) y
  ESCALABILIDAD, no latencia. Un recorte inicial demasiado agresivo bajó a 6/7 (rompió `search_IN_wallapop`→automate);
  el gate del benchmark lo pilló y se reforzó la distinción browse/automate → 7/7. **Nunca trimar el prompt de routing
  sin re-pasar el benchmark.**
- **Pendiente (siguiente)**: composición DINÁMICA del prompt — esqueleto siempre + módulos de dominio por heurística
  sobre el texto del turno (para que el prompt no crezca linealmente al añadir conectores). Requiere benchmark AMPLIADO
  (más casos por dominio) como gate + pasar el texto del turno a `build_flash_system` (1 línea en el provider
  `voice/engine/llm/providers/nucleo.py`).

## Metodología (para no sobre-interpretar)
- Latencia ABSOLUTA de un candidato solo es fiable si es el ÚNICO modelo cargado y la GPU no está saturada por
  otra ronda (cargar/descargar muchos modelos infla picos aislados; ver nota INI-008 Fase 2e).
- Ollama descarga el modelo tras ~5 min idle → `keep_alive:"30m"` en cada turno (ya en `nucleo/flash/fast_client.py`).
- La comparación de TASA DE ACIERTOS (tool-calling) entre modelos sí es válida bajo misma metodología imperfecta.
- Para cloud: medir TTFT REAL por AIMLAPI (no el nativo) antes de tomarlo como definitivo.

## 6. Reranker del recall LARGO — A/B a escala (V2-030, 2026-07-12)

**Problema medido:** a escala (442 recuerdos durables) el embedding local bi-encoder (embeddinggemma) ordena
"borroso" — la respuesta correcta está en el top-10 el ~82% de las veces, pero solo el 62% llega al top-3 y el 42%
al top-1. **Palanca:** un **reranker** (cross-encoder) que reordena el top-N del RRF leyendo query+recuerdo JUNTOS.

Harness: `tests/memory/e2e/bot/scale_eval.py` — 281 queries de recall largo (`t=query`, `via=long`, con ancla)
por `memory/retriever.search` sobre la BD aislada del bot. Métrica = rango del primer resultado con el ancla.

| proveedor | modelo | recall@1 | recall@3 | recall@5 | recall@10 | MRR | lat p50 | coste/privacidad |
|---|---|---|---|---|---|---|---|---|
| **off** (baseline) | — | 41.6% | 62.3% | 71.9% | 80.8% | 0.544 | 114 ms | — |
| **local** ⬅ producción | `jinaai/jina-reranker-v2-base-multilingual` (fastembed ONNX/CPU) | **56.2%** | **68.7%** | **74.4%** | 80.8% | 0.642 | 260 ms | gratis · 100% local |
| openai (techo) | `gpt-4o-mini` (LLM listwise) | 64.8% | 69.0% | 73.0% | 81.5% | 0.686 | 849 ms | API € · datos a la nube |

**Decisión: LOCAL por defecto.** Captura la mayor parte del salto (recall@1 +14.6 pts), **empata a OpenAI en
recall@3** (68.7 vs 69.0) y **lo supera en recall@5**, a 1/3 de la latencia, gratis, sin GPU (ONNX/CPU → no compite
con STT/TTS Metal) y sin que nada salga de la máquina. OpenAI solo gana claro en recall@1 (+8.6 pts) → queda como
**techo cloud opcional** (`rerank_provider=openai`), listo para la versión cloud. Ambos por la misma abstracción
`memory/rerank.py` (model-agnostic, `config/v2.py §memory`, fail-open, off-hot-path, solo recall LARGO). El modelo
local se calienta en el arranque (`prewarm._warm_rerank`).

**Techo honesto = found@10 (~82%):** lo que el retriever NO trae, el reranker no lo arregla. Para pasar de ahí →
embedding más fuerte (exige re-embed, `memory/reembed.py`) o consolidación semántica (`summarize_fn`) — ver
`zaelar-memory.md §Re-ranking · Palancas futuras`.

**Metodología:** la BD del bot es role-play SINTÉTICO (no el perfil real) → medir OpenAI mandando ese corpus a la
nube no tiene coste de privacidad. Latencia local en CPU (no compite con la GPU). El reranker NUNCA entra en
ESTADO/CORTO (lectura µs sin modelo) — solo en el recall LARGO, que ya es bajo demanda + `asyncio.to_thread`.

## 7. Embedding a escala + WRITE-completeness — el techo NO es el embedding (V2-031 T1, 2026-07-12)

Continuación de §6. Buscábamos subir el techo `found@10` (~82%). Se hizo la **dim provider-driven** (embeddings de
1024d posibles) + `tests/memory/e2e/bot/embed_bench.py` (re-embed del corpus con un modelo candidato + `scale_eval`).

| embedding local | dim | found@10 | recall@1 | veredicto |
|---|---|---|---|---|
| embeddinggemma | 768 | ~82% | ~56% | baseline |
| **bge-m3** (SOTA multilingüe) | 1024 | **~82%** | ~56% | **no mejora** |

**Un embedding local más fuerte NO sube el techo.** El diagnóstico de los ~50 casos que ni entran al top-10:
la **mayoría NO están guardados** (0 filas en la BD para `lisboa`/`tokio`/`150`/`macbook`/`2018`…) o están
invalidados (`toby`/`611`); solo unos pocos (`girona`/`pasaporte`) están guardados y no se recuperan. → **el techo
es WRITE-completeness + retrieval de lo guardado + reparación activa, no la calidad del bi-encoder.** Re-prioriza
V2-031 (embedding baja de prioridad; write-completeness y la memoria auto-evaluativa suben).

### ⚠️ Caveat de metodología (IMPORTANTE, no repetir el error)
El **test bot SIEMBRA con embeddings `hash`** (léxicos, deterministas, rápidos — `runner.py:702`, para sembrar miles
sin coste). Medir el recall **SEMÁNTICO** contra esos vectores es un MISMATCH de espacio (query embeddinggemma vs
store hash). Para una medición válida hay que **re-embeber el corpus con el modelo real por AMBOS lados** (lo hace
`embed_bench.py` vía `memory/reembed.py`). En **producción** siempre se escribe con embeddinggemma, no hash. Además
la BD acumulada del bot (`--next` incremental) está INCOMPLETA → para el número honesto, medir sobre BD fresca de
corpus completo re-embebida. Regla: **antes de concluir sobre recall a escala, confirmar con qué embedding está
indexada la BD** (`memory/reembed.py::signature()` / `<db>.embedsig`).

## 8. Catálogo SOTA de recuperación por TIER (embeddings + rerankers, 2026) — V2-031 T6

Referencia para elegir modelo de memoria sin re-investigar. **Regla de producto:** LOCAL por defecto (gratis,
model-agnostic vía `config/v2.py §memory`); los MISMOS pesos abiertos en nuestro **VPS-GPU** cuando escale; los
**externos de pago SOLO para un tier premium** (nunca default — insostenible en coste). Todo se cambia por config,
sin refactor. Recuerda el hallazgo T1: a la escala de un perfil personal, un embedding mayor **no** subió el techo
(el cuello es write-completeness + retrieval), así que el salto de tier es sobre TODO escala/serving, no recall en
perfiles pequeños.

### Embeddings
| Tier | Modelo | Dim | Licencia | Nota |
|---|---|---|---|---|
| **LOCAL (actual)** | `embeddinggemma` (Ollama) | 768 | Gemma | en producción; multilingüe, on-device, gratis |
| LOCAL (candidatos) | `Qwen3-Embedding-0.6B` · `bge-m3` | 1024 | Apache-2.0 · MIT | **#1 MTEB multilingüe** (familia Qwen3) / workhorse dense+sparse+multivector. `bge-m3` medido ≈ embeddinggemma a nuestra escala (§7) |
| **VPS-GPU propio** | `Qwen3-Embedding-4B/8B` · `bge-m3` | 1024–4096 | Apache-2.0 · MIT | mismos pesos servidos por nosotros (TEI en GPU); Qwen3-Embedding-8B lidera MTEB v2 (~70.6 multiling.); 100+ idiomas, 32K ctx; coste/llamada 0, datos NO salen |
| **PREMIUM externo** | OpenAI `text-embedding-3-large` · Cohere `embed-4` · `voyage-3` | var. | API pago | máxima calidad gestionada; €/llamada + datos a la nube. SOLO tier premium |

### Rerankers (cross-encoder)
| Tier | Modelo | Licencia | Nota |
|---|---|---|---|
| **LOCAL (actual)** | `jina-reranker-v2-base-multilingual` (fastembed ONNX/CPU) | Apache-2.0 | en producción (V2-030); multilingüe, cero GPU, recall@1 42→56% |
| LOCAL (candidatos) | `bge-reranker-v2-m3` · `Qwen3-Reranker-0.6B` · `mxbai-rerank-large-v2` | MIT/Apache-2.0 | `bge-reranker-v2-m3` = default seguro self-host (ligero, multilingüe, TEI); `Qwen3-Reranker` = 1er open a probar (100+ idiomas, 32K); comparar en T3 |
| **VPS-GPU propio** | `Qwen3-Reranker-4B` · `bge-reranker-v2-m3` | Apache-2.0/MIT | mismos, servidos en GPU (TEI); más calidad, coste/llamada 0, datos NO salen |
| **PREMIUM externo** | Cohere `Rerank 3.5/4` · `voyage rerank-2.5` | API pago | ~595–603 ms; SLA gestionado. SOLO tier premium (ya enchufado: `rerank_provider=cohere/voyage`) |

**Cómo se cambia de tier:** `config/v2.py §memory` (`embed_provider`/`embed_model`, `rerank_provider`/`rerank_model`).
Cambiar de embedding EXIGE re-embed (`memory/reembed.py`, firma de modelo). El reranker es hot-swap (fail-open).

Fuentes (2026): [MTEB/embeddings SOTA](https://www.codesota.com/benchmarks/mteb) ·
[Qwen3-Embedding](https://github.com/QwenLM/Qwen3-Embedding) ·
[open-weight embeddings 2026](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models) ·
[rerankers 2026](https://futureagi.com/blog/best-rerankers-for-rag-2026/) ·
[reranker open vs API](https://docs.bswen.com/blog/2026-02-25-best-reranker-models/) ·
[self-host TEI GPU](https://www.spheron.network/blog/self-host-embedding-reranker-tei-gpu-cloud/).

---

## 9. Política de modelos POR MÓDULO — matriz canónica (2026-07-17)

> **Regla de oro (operador):** *más que especular, PRUEBAS.* Antes de confiar un modelo a un módulo se le pasa su
> tarea real (routing / write-completeness / clasificación) y se anota aquí el veredicto — para no repetir errores.
> **Dos directrices duras del operador (2026-07-17):** (a) el **motor de memoria SIEMPRE por OpenAI**; (b) **cero
> ejecución local por batería** — ningún módulo debe apuntar a Ollama/qwen local (salvo que el operador lo reactive).

Config: cada pieza es elegible por la UI (`server/config_api.py::_PROVIDER_CATALOG`) y persiste en `config/v2.json`
(gitignored). La key va vacía → se resuelve del entorno por endpoint (OpenAI→`OPENAI_API_KEY`, xAI→`XAI_API_KEY`).

### 9.1 FlashBrain — capa RÁPIDA de VOZ (`config §fast`)
Restricción: **no-razonador**, tool-calling FIABLE, sub-segundo. Cierra el turno; un fallo de routing = zaelar inútil.

| Modelo | Proveedor | Veredicto | Evidencia |
|---|---|---|---|
| **gpt-4o-mini** | OpenAI | ✅ **EN USO** | A/B 2026-07-17 (turno "dime cuándo es la cita ITV"): responde de memoria + `web_search` solo en consultas reales. Barato. |
| grok-4-fast-non-reasoning | AIMLAPI | ✅ válido (histórico) | head-to-head 2026-07-08: 7/7 routing (§2). ⚠️ es OTRO modelo que el de xAI directo. |
| gemini-2.5-flash | AIMLAPI | ✅ válido | 7/7 routing (§2). |
| claude-haiku-4.5 | AIMLAPI | ✅ válido, caro | 7/7, mejor fiabilidad FC (§2). |
| **grok-4.20-0309-non-reasoning** | **xAI directo** | ❌ **NO USAR en FlashBrain** | A/B 2026-07-17 MISMO turno: contestó "Hecho" + llamó `widget_data` a una PREGUNTA de memoria (mis-routing), teniendo la respuesta en el prompt. Enruta preguntas a acciones. |
| gemini-2.5-flash-lite | AIMLAPI | ❌ NO USAR | 4/7 routing, no invoca tools (§2). |
| cualquier `*-reasoning` / grok-4.3/4.5 / gemini-3.x-flash | — | ❌ PROHIBIDO en voz | razonadores → +segundos de thinking → zaelar lento/mudo (regla dura). |
| qwen2.5:14b local (Ollama) | local | ❌ NO USAR en voz | ~19s/turno + contiende GPU con STT/TTS (§1, §4). |

#### 9.1.b Re-validación del veto a grok con la generación NUEVA (2026-08-03)

El operador preguntó por «un grok nuevo que es ultra rápido». Lo es — y sigue vetado. Barrido con el banco
`bench_fast_model.py` (nodo 2.13), **3 rondas × 14 casos contra el prompt REAL**, incluyendo por primera vez las
dos trampas **PREGUNTA ≠ ORDEN** (entre ellas el turno literal que lo vetó en 2026-07-17, «dime cuándo es la cita
de la ITV»). Un fallo **GRAVE** = convertir una pregunta en una acción; no es quedarse corto, es hacer lo que
nadie pidió.

| Modelo | Acierto | GRAVES | p50 | Peor | Veredicto |
|---|---|---|---|---|---|
| `deepseek-v4-flash` (AIMLAPI, en uso) | **40/42** | **0** | 2.921 ms | **76.392 ms** ⚠️ | ✅ sigue siendo el mejor enrutador |
| `grok-4.20-0309-non-reasoning` (xAI directo) | 33/42 | 1 | **1.030 ms** | 2.791 ms | ❌ el veto se reproduce |
| `x-ai/grok-4-1-fast-non-reasoning` (AIMLAPI) | 32/42 | 1 | 1.285 ms | 2.433 ms | ❌ mismo fallo |
| `mistral-medium-latest` (directo) | 33/42 | **3** | 1.977 ms | 15.214 ms | ❌ falla la pregunta SIEMPRE |

**Lo que confirma:** grok es de verdad ultra rápido (1 s de mediana y **jamás se dispara** — su peor caso es
2,8 s), pero repitió el fallo exacto de julio: a «dime cuándo es la cita de la ITV» respondió llamando a
`web_search` + `widget_data`. Y añade uno peor para el caso de uso que el operador está probando ahora mismo:
enruta «investiga y ponme un informe en pantalla» a `web_search` **3 de 3 veces**, en vez de lanzar un Brain
Worker — es decir, contestaría con un dato suelto donde se espera una investigación. **El veto se mantiene.**

**Hallazgo colateral, más preocupante que grok:** DeepSeek enruta perfecto pero tuvo un turno de **76 segundos**
(1 de 42). No hay timeout de turno en la capa de voz — `providers/nucleo.py` acota el recall (800 ms) y la
conversación reciente (500 ms), pero la llamada al modelo solo topa contra el read-timeout de httpx (60 s) y sus
reintentos. Para voz eso es minuto y cuarto de silencio. **Pendiente**: presupuesto de turno con frase de reserva.

### 9.2 Motor de MEMORIA — CORAZÓN de escritura / distiller (`config §memory.mem_processor_*`)
Restricción: **OFF-hot-path** (la latencia NO toca la voz) → prioriza **write-completeness** (palanca nº1 del recall,
V2-031).

> ⚠️ **SECCIÓN HISTÓRICA — superada por §12.3 (2026-08-09).** El titular es hoy
> **`deepseek/deepseek-v4-flash` vía AIMLAPI**, y la **directriz «SIEMPRE OpenAI» queda DEROGADA**: se tomó cuando
> el único contendiente barato medido era `gpt-4o-mini` sobre 16 casos. El barrido de 21 candidatos × 34 casos
> encontró modelos no-OpenAI que igualan la calidad útil a menos de la mitad de precio. También caduca la fila de
> `gpt-4o-mini` de abajo: hoy SÍ capta la alergia; su fallo se movió al metadato (le pone `slot=operator.diet`
> cuando se dice en inglés), que es peor. La tabla se conserva por trazabilidad de cómo se decidió entonces.

| Modelo | Veredicto | Evidencia (prueba write-completeness es, 2026-07-17) |
|---|---|---|
| **gpt-4.1-mini** | ✅ **EN USO** | 4/4 casos difíciles; capta "alérgico a penicilina y marisco" → 2 píldoras. Más barato que 4o. |
| gpt-4o | ✅ válido, más caro | 4/4 igual que 4.1-mini; sin ventaja que justifique el coste. |
| gpt-4o-mini | ❌ insuficiente para memoria | **se COME la alergia (0 píldoras)**; 3/4. Vale para voz, NO para el distiller. |
| qwen2.5:7b local | ✅ (pero LOCAL) | 12/12 write-completeness (auditoría 2026-07-14); descartado por la regla de cero ejecución local. |
| qwen2.5:3b local | ❌ | 3/12 (era el cuello de botella real del recall). |
| deepseek/deepseek-v4-flash | ⚠️ NO probado aquí | el operador lo puso pero SIN endpoint → se mandaba a Ollama y fallaba a heurística (memoria degradada). Requiere key propia de DeepSeek (no la hay). |

### 9.3 TRIAJE de mensajería (`config §triage`)
Tarea: clasificación de relevancia de mensajes (NO tool-routing) → tolera un modelo más simple. **⚠️ PRIVACIDAD:**
antes local (qwen2.5:3b) para que nada personal saliera; ahora EXTERNO por decisión del operador (batería) → los
mensajes personales SALEN a la nube.

| Modelo | Veredicto |
|---|---|
| **grok-4.20-0309-non-reasoning** (xAI) | ✅ **EN USO** — barato, aprovecha el saldo xAI; clasificación simple donde su debilidad de routing no aplica. |
| gpt-4o-mini (OpenAI) | ✅ alternativa fiable. |
| qwen2.5:3b (local) | ⛔ retirado (regla cero-local); era el más PRIVADO. |

### 9.4 Otros módulos de lenguaje
- **Workers / SlowBrain** (`config §code_agent`): `claude_code` (CLI) — sin cambios.
- **Reranker del recall largo** (`config §memory.rerank_provider`): **`local` = jina cross-encoder vía fastembed
  (CPU/ONNX, NO Ollama/GPU)**. Sube recall@1 41.6→56.2% gratis (§6). Es LOCAL pero CPU-ligero → no es el consumo de
  batería que preocupa. Alternativa cloud: `openai` (listwise, +8.6pts recall@1, coste/query, datos a la nube).
- **Embeddings** (`config §memory.embed_provider`): **`fastembed` (CPU/ONNX local, NO Ollama/GPU)**. ⚠️ Cambiarlo a
  cloud (OpenAI/Voyage) EXIGE **re-embed de toda la BD** (`memory/reembed.py`; nunca mezclar espacios vectoriales) +
  añade latencia de red a CADA recall (embedding en el hot-path de lectura). Recomendación: **mantener local CPU**.
- **STT (voz→texto)** (`config/settings.py`, NO v2.json): hoy **`whisper_local` (Metal/GPU)** — es el ÚNICO consumidor
  de GPU local que queda tras mover memoria+triaje a la nube. Para "cero local" real habría que pasar a **Deepgram**
  (hay `DEEPGRAM_API_KEY` en `.env`) u otro STT cloud. PENDIENTE de decisión del operador (coste vs batería).
- **TTS**: `elevenlabs` (cloud) — ya externo.

### 9.5 Estado de config tras esta ronda (2026-07-17)
`fast`=OpenAI gpt-4o-mini · `memory`=OpenAI gpt-4.1-mini · `triage`=xAI grok · `code_agent`=claude_code ·
`rerank`=local jina (CPU) · `embed`=fastembed (CPU) · **STT=whisper_local (GPU) ← único local pesado pendiente**.

## 10. «Susurro» (V2-053) — modelo del auditor conversacional

Carril NUEVO fuera del camino de voz → **aquí un RAZONADOR sí vale** (la regla dura solo veta el path de voz).
Lo que importa: calidad de DIAGNÓSTICO (¿señala la causa real del fallo del tramo?), disciplina de catálogo
(JSON válido, correcciones quirúrgicas, `corrections=[]` ante un tramo sano) y coste (se paga por fricción, no
por turno). Config: `config/v2.py §susurro` (UI, key por endpoint).

| Modelo | Vía | Probado | Resultado |
|---|---|---|---|
| **gpt-4.1-mini** | OpenAI | **2026-07-17, e2e en vivo** (suite `tests/agent_headless/e2e/susurro/run_probe_suite.py`) | ✅ **DEFAULT actual** — diagnóstico correcto en el caso reloj-vs-agenda (queja simulada), repair natural + finding P1 bien clasificado; ciclo completo 2.4-2.9s; JSON impecable con `response_format json_object` |
| gpt-4.1 / gpt-4o | OpenAI | pendiente | candidatos si el mini se queda corto en tramos complejos (multi-worker, rails encadenados) |
| o4-mini / razonadores OpenAI | OpenAI | pendiente | el carril ADMITE razonamiento; medir si el thinking mejora el diagnóstico lo bastante para pagar su latencia (aquí no bloquea nada) |
| grok (xAI) | xAI | no | descartado de entrada para AUDITAR: si mis-rutea como FlashBrain (§9), no puede juzgar routing ajeno |

**Cómo re-evaluar:** correr la suite e2e N veces con `SUSURRO_MODEL=<candidato>` sobre los MISMOS casos de
fricción y comparar assessment/correcciones a mano + `history.jsonl` (calidad longitudinal). No especular:
cambiar el default solo con evidencia.

## 11 · FAST layer de voz — TTFT + routing (consolidado 2026-07-19)

El hueco que hace que la charla "no parezca charla" es el **TTFT (tiempo al primer token)**: el silencio entre que
el operador calla y zaelar empieza. Medido con streaming real + routing con las tools REALES del flash (memoria =
6 preguntas de recuperar dato guardado que NO deben ir a `widget_data`; general = 6 rutas web/show/música/escalar/
cálculo/charla). **Titular: `gpt-4o-mini`.** Tabla única — NO re-litigar estos modelos:

| Modelo | TTFT | Routing memoria | Routing general | Coste vs 4o-mini | Veredicto |
|---|---|---|---|---|---|
| **gpt-4o-mini (OpenAI) — TITULAR** | ~660-1098 ms | 0/6 ✅ | 7/7 ✅ | 1× ($0.15/$0.60) | **SE QUEDA** — rápido+fiable+barato |
| **gemini-2.5-flash (vía AIMLAPI)** | full ~1.1-1.5 s | 0/6 ✅ | 6/6 ✅ | output más caro ($2.50) | ✅ **FALLBACK validado de un clic** (thinking OFF). No migrar: ni más rápido ni más barato + AIMLAPI tras Cloudflare (403 intermitente) |
| gpt-4.1-mini (OpenAI) | ~540-576 ms ⚡ | 0/6 ✅ | 7/7 ✅ | **~2.7×** ($0.40/$1.60) | ⚠️ superior técnicamente pero no compensa 2.7× por ~140 ms en cada turno. Promover solo si el coste deja de importar |
| grok-4.20-0309-non-reasoning (xAI) | ~530-826 ms ⚡ | **2/6 MAL** ❌ | 7/7 | funded | ❌ **BANEADO** — dice `widget_data`/"Hecho" a una PREGUNTA (causa de conversaciones absurdas) |
| grok-4.3 / grok-4.5 (xAI) | 2633 / 3501 ms 🐢 | 0/6 ✅ | — | funded | ❌ RAZONADORES (rutean bien pero 3-5× más lentos; sin variante `-non-reasoning`) — violan "voz=no-razonador" |
| grok-3-mini (xAI) | 3442 ms 🐢 | — | — | funded | ❌ razonador |
| gemini-3.5-flash / 3-flash (AIMLAPI) | — | — | — | barato | ❌ 3.5 trae **thinking ON** (no se apaga vía AIMLAPI); 3-flash da 404 |
| Groq LPU llama (api.groq.com ≠ xAI) | ~300-500 ms típico (sin medir) | — | — | barato | ⏸️ el ÚNICO genuinamente más rápido, pero `GROQ_API_KEY` da **403**. Acción operador: refrescar para A/B |
| gemini-3.5-flash (Google directo) | — | — | — | barato | ⏸️ `GEMINI_API_KEY` da **429** (sin billing). Acción operador: poner saldo |

**Reglas duras (para no re-probar):**
- **grok NUNCA en el fast layer de voz**: el único rápido (4.20-nr) mis-rutea memoria; los correctos (4.3/4.5) razonan → lentos. No existe un grok rápido Y correcto.
- **El paso heurístico rápido YA existe y es 0 ms** (`nucleo/flash/router.py`, determinista). Lo que baja el TTFT no es un clasificador LLM en serie (suma latencia) — es un modelo base más rápido.
- **Tiered por complejidad**: útil para INTELIGENCIA (router 0 ms → gpt-4o-mini → workers, ya en embrión), no para latencia salvo con un tier rápido real.
- **Palancas reales de latencia pendientes**: (1) refrescar **Groq** (LPU, el más rápido) y A/B routing; (2) poner billing a **Gemini** y medir 3.5-flash con thinking OFF; (3) aceptar gpt-4.1-mini pagando 2.7×.
- **Mitigación de síntoma YA aplicada**: lead-in filler timer-gated (`ZAELAR_FILLER_MS`, def 600 ms) — rellena SOLO los turnos lentos; no baja el TTFT real, mejora la latencia PERCIBIDA.

## 12. Módulo de MEMORIA — ronda V2-056 (2026-07-20): destilador + síntesis REM, con router interno

> Contexto: auditoría profunda 2026-07-19 (informe `~/.meshkore/tmp/auditoria-memoria-20260719.html`) + orden del
> operador de elegir los modelos del módulo CON DATOS (catálogo AIMLAPI disponible, respetar descartes previos §9).
> **Router interno del módulo**: cada tarea de LLM de la memoria es elegible POR CONFIG con key POR ENDPOINT —
> `nucleo/memllm.py` (tareas `rem`, futuras) + `mem_processor` (tarea `distill`, su propia cola/semántica).
> Config: `config/v2.json §memory.{mem_processor_*, rem_*}`. Los benches son REPRODUCIBLES (scripts versionados).

### 12.1 DESTILADOR (CORAZÓN de escritura) — `tests/memory/e2e/bot/distiller_bench.py`

16 casos duros por el CAMINO real (`mem_processor.process`): write-completeness (multi-hecho médico, precio,
mudanza slot+change, corrección identidad, compromiso, rutina, reversión, observación, nombre propio en PARRAFADA
[T181], telegráfico, EN→ES, familia con nombres) + PRECISIÓN (4 descartes: pregunta, efímera, ack, comando) +
penalización de idioma (regla monolingüe).

| modelo | endpoint | score | p50 | veredicto |
|---|---|---|---|---|
| **gpt-4.1-mini** | OpenAI | **98.3%** (28.5/29) | 1.1s | ✅ **TITULAR confirmado** (ya era el default por la regla «memoria=OpenAI») |
| gemini-2.5-flash | AIMLAPI | 96.6% | 3.3s | ✅ fallback nº1 si OpenAI cae (pero ver 12.2: NO vale para REM) |
| claude-haiku-4.5 | AIMLAPI | 94.8% | 1.5s | ✅ válido, algo más caro |
| deepseek-v4-flash | AIMLAPI | 94.8% | 4.0s | ✅ válido (por fin probado CON endpoint — §9.2 lo tenía pendiente) |
| qwen2.5:7b local | Ollama | 86.2% | 2.2s | ⚠️ opción local (batería/privacidad); pierde precisión en descartes |
| qwen3.5-flash | AIMLAPI | 17.2% | 18.7s | ❌ NO USAR (thinking ON → timeouts; consistente con §11) |

### 12.2 SÍNTESIS del sueño REM — `tests/memory/e2e/bot/rem_synth_bench.py`

Tarea real (`memllm.synthesize_concept_groups`): 3 grupos por concepto → 1 insight/grupo; puntúa retención de
nombres/cifras (anti-T181), castellano, brevedad, abstracción (no repetir píldoras verbatim). 2 pasadas.

| modelo | score | p50 | veredicto |
|---|---|---|---|
| **gpt-4.1-mini** | **100%** | 2.3s | ✅ **TITULAR** (`§memory.rem_model` default) |
| deepseek-v4-flash | 100% | 7.4s | ✅ fallback (3× más lento, mismo resultado) |
| claude-haiku-4.5 | 90% | 3.1s | ✅ válido |
| gemini-2.5-flash | 50% | 7.3s | ❌ NO para síntesis (pierde claves/forma) — aunque destila bien (12.1) |

**Conclusión de la ronda:** `gpt-4.1-mini` titular en las DOS tareas de LLM del módulo de memoria (distill + REM);
cadena de fallback documentada por tarea (distill: gemini-2.5-flash → haiku-4.5; REM: deepseek-v4-flash →
haiku-4.5). ⚠️ AIMLAPI por urllib exige UA de navegador (Cloudflare 403 — mismo workaround que fast_client, ya
aplicado en memllm). Embeddings: restaurado `auto` (ollama/embeddinggemma, firma re-sellada + re-embed 261/261)
tras el incidente de mezcla de espacios (fastembed/bge-EN); el enforcement del writer impide que se repita.

> ⚠️ **SUPERSEDIDO ENTERO: el destilador por §12.3 y la síntesis REM por §12.4 (ambas 2026-08-09).** Las dos
> tareas del módulo pasan a `deepseek/deepseek-v4-flash`. **Los números de §12.2 miden un código que dejó de
> ejecutarse poco después**: la interpolación `{lang}` de la regla monolingüe rompió `synthesize_concept_groups`
> con un `KeyError` (ver §12.4), así que desde entonces y hasta el 2026-08-09 la síntesis no escribió NADA. Se
> conserva por trazabilidad, no como evidencia vigente.

### 12.3 DESTILADOR — ronda de PRECIO (2026-08-09): `deepseek-v4-flash` sustituye a `gpt-4.1-mini`

> Encargo del operador: *«modelos que den IGUAL O MEJOR calidad más baratos»* para el CORAZÓN, y **un solo modelo
> comercial que sirva igual en self-host y en la nube** (se retira la vía Ollama local: obligaba a dos ganadores).

**Por qué el precio es el eje correcto aquí, y la velocidad no.** Escribir va **off-hot-path** (cola async,
fire-and-forget) y **leer no usa ningún LLM** (retriever sqlite-vec + FTS5 + reranker). Así que la latencia del
destilador no la paga nadie: un modelo lento y barato es perfectamente válido. Lo que NO es tolerable es perder un
hecho durable — write-completeness es la palanca nº1 del recall (V2-031: la mayoría de los "no recuperados" ni
siquiera están GUARDADOS).

**Metodología** (`tests/memory/e2e/bot/distiller_bench.py`, reescrito): **34 casos** (antes 16) por el camino REAL
`mem_processor.process`, y **cuatro ejes SEPARADOS** en vez de un único % que escondía de qué flojeaba cada modelo:

1. **write-completeness** (24 casos, 90 hechos) — ¿capta el hecho durable?
2. **precisión / no-pollution** (10 descartes) — ¿deja la memoria limpia? Puntúa solo si devuelve `[]`. Las píldoras
   EXTRA en casos KEEP **no** se penalizan: el prompt PIDE inferir intereses/intenciones.
3. **capa/slot** (18 comprobaciones) — `dest`/`slot`/`change`/`kind`. Incluye la regla ADITIVA: una alergia lleva
   `slot=null`, nunca `operator.diet`.
4. **$/1k turnos** — tokens REALES del proveedor (`mem_processor.last_usage()`, capturado desde esta ronda) ×
   tarifa publicada (`prices.json`). El prompt son ~3.700 tokens de INPUT fijos → el coste lo domina el input.

Casos nuevos que separan de verdad: alergia en INGLÉS y mudanza en CATALÁN (regla monolingüe), secreto que el
operador pide guardar, compromiso ajeno, corrección de fecha, interés+intención inferidos, cotidiano que NO debe
promocionar a durable, garble de STT con dato bueno.

| modelo (id AIMLAPI salvo nota) | write-compl. | precisión | capa/slot | $/1k turnos | pasadas | p50 | veredicto |
|---|---|---|---|---|---|---|---|
| **`deepseek/deepseek-v4-flash`** | **98,5%** | **100%** | 94,4% | **$0,680** | 3 | 4,1s | ✅ **TITULAR** — −55% de coste |
| `openai/gpt-4.1-mini` | 98,9% | 100% | 100% | $1,516 | 3 | 1,7s | ✅ titular ANTERIOR; último de la cadena |
| `openai/gpt-4o-mini` | 98,9% | 100% | 94,4% | $0,567 | 3 | 1,4s | ⛔ **VETADO** — mete la alergia en `operator.diet` |
| `openai/gpt-5-mini` | 98,9% | **50%** | 100% | $2,517 | 1 | 13,0s | ❌ razonador: capta bien pero ENSUCIA |
| `mistralai/ministral-8b` (directo) | 97,8% | **73,3%** | 100% | $0,393 | 3 | 1,0s | ❌ el más barato del lote, pero ensucia |
| `google/gemini-2.5-flash` | 96,7% | 100% | 100% | $1,232 | 3 | 2,5s | ✅ **fallback nº1** (metadato perfecto) |
| `anthropic/claude-haiku-4.5` | 96,7% | 100% | 100% | $4,607 | 1 | 1,8s | ✅ válido, 6,8× el precio del titular |
| `x-ai/grok-4-20-non-reasoning` (xAI directo) | 96,7% | 100% | 100% | $4,749 | 1 | 1,1s | ✅ válido pero CARO ($1,25/$2,50) |
| `google/gemini-2.5-flash-lite` | 96,7% | 90% | 94,4% | $0,390 | 3 | 0,9s | ❌ reifica una PREGUNTA + falla el slot de mudanza |
| `zhipu/glm-4.7` | 96,7% | 90% | 94,4% | $3,793 | 1 | 28,9s | ❌ caro y lentísimo por el broker |
| `openai/gpt-5-nano` | 96,7% | **60%** | 83,3% | $1,134 | 1 | 16,3s | ❌ razonador: ensucia (2.388 tok de salida) |
| `x-ai/grok-4-fast-non-reasoning` | 95,6% | 100% | 100% | $0,762 | 3 | 1,1s | ✅ **alternativa CONSERVADORA** (metadato 100%) |
| `deepseek/deepseek-chat` | 95,6% | 100% | 94,4% | $0,579 | 3 | 2,0s | ✅ válido; −3 pts de completeness vs v4-flash |
| `moonshot/kimi-k2-6` | 95,6% | 100% | 94,4% | $7,031 | 1 | 10,1s | ❌ el MÁS CARO del barrido |
| `meta-llama/llama-3.3-70b` | 95,6% | 80% | 100% | $2,379 | 1 | 0,9s | ❌ ensucia + más caro que el titular |
| `Qwen/Qwen2.5-7B-Instruct-Turbo` | 94,4% | **20%** | 94,4% | $1,201 | 1 | 1,5s | ❌ ensucia 8 de cada 10 descartes |
| `openai/gpt-4.1-nano` | **68,9%** | 100% | **38,9%** | $0,377 | 1 | 1,0s | ❌ pierde 1/3 de los hechos y 6/10 slots |

**No medibles (fallo de CUENTA, no del modelo — no son veredictos):** `llama-3.3-70b` por Groq directo (29 llamadas
muertas, HTTP 429 de rate-limit) y `glm-4.7-flash` por Z.AI directo (33 muertas, HTTP 429 código 1113, saldo).
También `gpt-4o-mini` por **OpenAI directo** dio 21 muertas de 102 con 6 llamadas en vuelo → esa cuenta va muy
limitada de tasa (mismo motivo del p50 de 20 s de `gpt-4.1-mini@openai`). **Norma para la próxima ronda: medir
siempre por el broker**, no por OpenAI directo, o el rate-limit se disfraza de mala calidad.

**Por qué gana `deepseek-v4-flash` y no el más barato.** Empata con el titular en los **dos ejes que destruyen
datos** —captar el hecho (98,5 vs 98,9%: UN hecho de 90, dentro del ruido; su spread por pasada fue 96,7-100%) y no
ensuciar (100% los dos)— por **$0,68 frente a $1,516 los 1.000 turnos**. Sus dos fallos de capa/slot son
reproducibles y están caracterizados: (a) pierde el «somos **cinco**» de una enumeración familiar —los nombres sí
los guarda, y el número es derivable de la enumeración— y (b) no marca `change=update` en una NEGACIÓN pura («ya no
trabajo en X»), donde no hay valor nuevo con el que superseder; el hecho se guarda igual, solo que el viejo no se
invalida. **Ninguno destruye lo ya escrito.**

**El veto de `gpt-4o-mini` (más barato: $0,567) es la decisión importante de esta ronda.** Con la alergia dicha en
**inglés** le pone `slot=operator.diet` — 3/3 pasadas del bench y 3/3 en reproducción directa aparte. Un `slot`
**invalida todas las píldoras anteriores con ese slot**, así que un futuro «ahora soy vegetariano» borraría la
alergia al marisco. Es exactamente el error que el prompt del CORAZÓN advierte por escrito, y en una memoria
personal es pérdida de datos silenciosa, no un punto porcentual. Nota: la MISMA frase en castellano la resuelve
bien (`slot=null`) — lo que rompe es el cruce de idioma. También **caduca el hallazgo de §9.2** («se comía la
alergia, 0 píldoras»): hoy la capta; el fallo se ha movido del texto al metadato.

**Los razonadores NO valen para destilar** (hallazgo nuevo y consistente): `gpt-5-mini` 50% y `gpt-5-nano` 60% de
precisión — captan bien pero convierten preguntas y órdenes en píldoras. Un razonador «encuentra sentido» a un
turno que había que tirar. Coincide con el descarte de `qwen3.5-flash` en §12.1, por otra vía.

**Cadena de fallback del destilador:** `deepseek-v4-flash` → `google/gemini-2.5-flash` (96,7/100/100) →
`openai/gpt-4.1-mini`. La alternativa CONSERVADORA, para quien prefiera metadato perfecto a 3 puntos de
completeness, es `x-ai/grok-4-fast-non-reasoning` ($0,762, 100% en precisión y capa/slot, varianza cero).

**Deroga la directriz «memoria = SIEMPRE OpenAI»** (§9.2, 2026-07-17): se tomó cuando el único contendiente barato
medido era `gpt-4o-mini` sobre 16 casos. Con 21 candidatos y 34 casos, hay modelos no-OpenAI que igualan la calidad
útil a menos de la mitad de precio. Lo que SÍ se mantiene como regla: **el destilador se elige con el bench, nunca
por reputación del proveedor.**

**Notas de coste.** Los $/1k son con tarifa NATIVA del proveedor (`prices.json`, verificada por web el 2026-08-09);
AIMLAPI cobra encima un margen de ~1,0-1,3× según modelo, común a todos los candidatos → no altera el ranking, sí
el absoluto (el titular real en nube ≈ $0,88/1k). `deepseek-v4-flash` DIRECTO (`api.deepseek.com`, sin el margen del
broker) ahorraría otro ~30%, pero no hay `DEEPSEEK_API_KEY` — pendiente, igual que en §9.1 para el FlashBrain.
**Palanca no explorada, mayor que el cambio de modelo:** el prompt son ~3.700 tokens de input FIJOS por turno
(system + 8 pares de few-shot); un proveedor con *prompt caching* recortaría el coste bastante más que cualquier
sustitución de modelo.

**Gap de facturación cerrado de paso:** el CORAZÓN era la ÚNICA llamada LLM de nube que no reportaba a Energy
(`report_llm_usage` solo se llamaba desde `fast_client`, los Brain Workers y el generador de widgets) → en una
cuenta cloud destilaba gratis en el contador. Ya reporta, y `energy_meter` lleva la tarifa del titular y de toda la
cadena de fallback. **Bug de producción encontrado por el preflight:** AIMLAPI devuelve **HTTP 201** con un cuerpo
válido para algunos modelos (`zhipu/glm-4.7`); el CORAZÓN exigía `== 200` → lo trataba como error y caía a la
heurística lossy en silencio, en cada turno. Ahora acepta cualquier 2xx.

### 12.4 SÍNTESIS del sueño REM — ronda 2026-08-09: `deepseek-v4-flash`, y **la fase llevaba semanas muerta**

> Detonante: el operador pregunta por qué REM se quedaba en `gpt-4.1-mini` mientras el CORAZÓN pasaba a DeepSeek,
> y si una tarea así no pediría un modelo **más potente**. Respuesta corta: el modelo estaba HEREDADO de §12.2, no
> elegido con datos nuevos — y al montar el bench apareció algo peor que un modelo mal elegido.

**🔴 HALLAZGO PRINCIPAL — la síntesis no se ejecutaba.** `_REM_SYSTEM` termina con el ejemplo del contrato de
salida —`[{"concept": str, "insight": str|null}]`— y se interpolaba con `str.format(lang=…)`: Python lee esas
llaves literales como marcadores y lanza `KeyError: '"concept"'` en CADA llamada. `memory/rem.py::synthesize`
captura cualquier excepción del hook, escribe un `warning` y devuelve 0 → **la fase 3 del sueño profundo (los
INSIGHTS por concepto) no escribió una sola píldora desde que se añadió la regla monolingüe hasta el 2026-08-09**.
Fail-open perfecto y silencioso: el síntoma era «la memoria no consolida», nunca un error. Misma clase de avería
que dejó el CORAZÓN dos días caído en julio. Arreglado (`.replace`, el idioma que ya usaba `mem_processor`),
blindado con `tests/memory/unit/test_rem_prompt.py` (que **prohíbe explícitamente** volver a `.format` sobre ese
prompt) y el fallo deja de ser invisible: log a ERROR + `health_state.record("memory")` → lo pinta el ◉.
⚠️ Por el lío de sesiones concurrentes de ese día, el fix viajó dentro del commit `1b7eb48`, cuyo título habla de
observabilidad. Se anota aquí porque en el log no se encuentra buscando "REM".

**Por qué aquí manda la CALIDAD y no el precio — al revés que en §12.3.** No es criterio, es la forma del código:
`rem.py` manda **TODOS los grupos en UNA sola llamada**, con `MAX_GROUPS=8` × `pills[:12]`, **una vez al día**
(`rem_every_hours=24`). Son ~365 llamadas al año con la entrada ACOTADA por diseño: **el coste NO escala con el
tamaño de la memoria** (la preocupación razonable del operador la resuelven ya los topes). Todo el barrido cabe
entre **$0,14 y $2,17 AL AÑO** por usuario — el modelo más caro cuesta dos euros anuales. En cambio un insight malo
se escribe como píldora durable con `slot=insight:<concepto>` y el retriever puede devolverlo como si fuera un
hecho del operador. Con ese reparto, optimizar el precio aquí sería optimizar el ruido.

**Metodología** (`tests/memory/e2e/bot/rem_synth_bench.py`, reescrito): 8 grupos-fixture (antes 3), 3 pasadas,
**seis ejes**: validez · retención de CLAVES (nombres/cifras, anti-T181) · forma (castellano, ≤260 chars, no
copiar verbatim) · **disciplina de NULL** (un grupo flojo DEBE volver `null`, lo pide el prompt — el bench viejo
no lo medía) · **NO-INVENCIÓN** (términos plausibles pero ausentes de las píldoras) · $/año medido. Grupos nuevos:
evolución contradictoria (Madrid→Valencia), cifras densas, grupo de 12 píldoras, multilingüe, y uno de
trivialidades que no merece insight.

| modelo | calidad | validez | claves | forma | null | no-inv. | $/año | p50 |
|---|---|---|---|---|---|---|---|---|
| **`deepseek/deepseek-v4-flash`** | **97,8-99,0%** | 100% | 98,4-100% | 90,5-95,2% | 100% | 100% | **$0,25** | 14s | ✅ **TITULAR** |
| `x-ai/grok-4-fast-non-reasoning` | 97,8-98,7% | 100% | 88,9-93,7% | 100% | 100% | 100% | $0,14 | 3s | ✅ **alternativa / fallback** |
| `zhipu/glm-4.7` | 99,0% | 100% | 95,2% | 100% | 100% | 100% | $1,69 | 49s | ✅ válido, 7× el precio y lentísimo |
| `deepseek/deepseek-v4-pro` | 98,1% | 100% | 95,2% | 95,2% | 100% | 100% | $0,78 | 25s | ⚠️ el POTENTE **no mejora** al flash |
| `deepseek/deepseek-reasoner` | 97,1% | 100% | 100% | 85,7% | 100% | 100% | $1,71 | 12s | ⚠️ razonar no aporta; insights largos |
| `openai/gpt-4.1` | 96,8% | 100% | 98,4% | 85,7% | 100% | 100% | $2,17 | 4s | ⚠️ el más caro del lote útil |
| `deepseek/deepseek-thinking-v3.2-exp` | 92,4% | 100% | 90,5% | 71,4% | 100% | 100% | $0,20 | 20s | ❌ pierde claves y se alarga |
| `anthropic/claude-haiku-4.5` | 91,4% | 100% | 95,2% | **61,9%** | 100% | 100% | $1,70 | 8s | ❌ insights demasiado largos |
| `openai/gpt-4.1-mini` (titular previo) | **78,1%** | 100% | 100% | 90,5% | **0%** | 100% | $0,44 | 7s | ❌ **nunca calla** (ver abajo) |
| `google/gemini-2.5-flash` | 20% | **0%** | — | — | n/a | 0% | $0,16 | 7s | ❌ no devuelve nada usable |
| `openai/gpt-5-mini` | 20% | **0%** | — | — | n/a | 0% | $0,93 | 20s | ❌ 1.152 tokens de salida para nada |

**Por qué cae el titular anterior.** `gpt-4.1-mini` es impecable en todo… salvo en el eje que el bench viejo no
medía: **disciplina de NULL, 0% en las 3 pasadas**. Ante el grupo de trivialidades («tomó un café», «estaba
cansado», «hizo buen tiempo», «se le olvidó dónde dejó las llaves») fabrica siempre un insight —*«En su día a día
experimenta pequeños olvidos como perder las llaves, nota variaciones en su estado…»*— que se escribiría como
píldora DURABLE. Es decir: convierte un despiste en un rasgo del operador. Callar cuando no hay patrón es parte de
la tarea, no una omisión.

**La hipótesis "más potente" queda MEDIDA y descartada.** `deepseek-v4-pro` (98,1%), `deepseek-reasoner` (97,1%),
`gpt-4.1` (96,8%) y `deepseek-thinking` (92,4%) **no superan** al flash, y cuestan entre 3× y 9× más. `gpt-5-mini`
directamente falla. La síntesis REM es mecánica —agrupar, abstraer, conservar claves— y razonar sobre ella añade
verbosidad e inestabilidad, no criterio. Es el mismo patrón que en §12.3 con los razonadores del destilador.

**Dos topes latentes que truncaban en SILENCIO** (encontrados persiguiendo una inestabilidad de DeepSeek, que
oscilaba entre 99,0% y 64,5% según la tanda):
- **`max_tokens=1200`** era insuficiente con 8 grupos para un modelo que RAZONA aunque no se le pida
  (`deepseek-v4-flash`, ya documentado para el FlashBrain): el pensamiento agota el presupuesto ANTES de cerrar el
  array → JSON truncado → `[]` → «sin insights» sin error. Medido aislando la variable: con 1200, **1 de cada 3**
  llamadas fallaba (una topó exactamente en 1200 tokens); con 4000, **3/3 válidas emitiendo solo ~1.100** — el
  techo alto no cuesta nada, se paga lo emitido. Subido a 4000.
- **`timeout=60s`**: una tanda lenta del broker se comía la noche entera de consolidación por una prisa que nadie
  tiene (REM corre de madrugada, en `to_thread`). Subido a 240s.

**Conclusión de la ronda:** `deepseek-v4-flash` titular en las DOS tareas de LLM de la memoria (destilar y
consolidar) — un solo modelo, una sola cuenta, una sola cosa que vigilar. Se elige sobre `grok-4-fast` (que gana
en forma y precio) porque **retiene mejor los datos clave** (98,4-100% vs 88,9-93,7%: grok perdía «Marta Ruiz»),
y perder un nombre propio en una síntesis destruye información, mientras que pasarse de 260 chars es cosmético.
Fallback: `grok-4-fast-non-reasoning` → `glm-4.7`.

**Artefacto de marcador corregido de paso:** un modelo que no devolvía NADA aprobaba el eje `null` al 100% (el
grupo flojo «salió null», como todos) y se llevaba un 20% en vez de un 0%. Un no-resultado no es disciplina: ahora
ese eje queda `n/a` y no promedia.

### §12.5 — Los DOS restos de OpenAI directo, y el modelo de i18n (2026-08-09)

Cerrada la elección de modelos de la memoria, el operador fija la norma general: **nada sale por OpenAI directo;
todo pasa por el broker AIMLAPI** (una sola cuenta de API que gestionar). Z.AI y Groq/xAI van aparte, con su
propia credencial, y solo donde hacen falta. Un modelo llamado `openai/gpt-4.1-mini` servido por el broker NO es
una cuenta de OpenAI — la confusión es fácil y conviene decirlo por escrito.

Quedaban DOS apuntando a `api.openai.com`, los dos con el defecto latente que ya había matado al REM: **en la nube
no existe `OPENAI_API_KEY`**, así que la llamada habría fallado en silencio (fail-open, sin error visible).

- **Susurro** (`config/v2.py §susurro`) → movido al broker **conservando su modelo exacto** (`openai/gpt-4.1-mini`).
  Cambia el camino, no el modelo: no hay calidad que re-medir. Verificado con una llamada real (auditoría de un
  tramo con fricción, 2.927 ms, 1.431 in / 136 out, diagnóstico correcto). El `§10` de este doc —elegir el modelo
  del Susurro con datos— sigue PENDIENTE; esto no lo resuelve, solo lo saca de una cuenta que no existe en la nube.
  De paso, su cliente manda ya el User-Agent de navegador como los demás; **comprobado que el UA por defecto de
  `aiohttp` SÍ pasa el Cloudflare de AIMLAPI** (HTTP 200) — el que se bloqueaba era el de `urllib`. Se manda igual
  porque el fail-open del Susurro es silencioso por diseño y no conviene depender de la política de un CDN.
- **i18n init** (`nucleo/memllm.py::_DEFAULTS["i18n"]`, traducir el UI a un idioma nuevo) → apuntaba a `gpt-4o`
  directo. Aquí SÍ había que elegir modelo, así que se midió antes.

**Sonda de i18n — al tamaño REAL del lote.** No es un bench de los de §12 (una tarea que se ejecuta una vez por
idioma no justifica 3 pasadas × 21 candidatos); es la comprobación de que mover el endpoint no rompe la tarea.
Corpus: claves REALES de `i18n/bundles/en.json`, **50 por lote (`_BATCH`)** con 15 que llevan `{placeholder}`,
hacia **japonés y árabe** (los scripts no-latinos son lo que discrimina). Ejes: cobertura (¿devuelve TODAS las
claves?), placeholders intactos, y script destino correcto.

| candidato | ja | ar | out_tok (lote de 50) | veredicto |
|---|---|---|---|---|
| **`anthropic/claude-haiku-4.5`** | 100% · 15/15 | 100% · 15/15 | ~1.050-1.200 | **ELEGIDO** — limpio en los dos, 7-10s |
| `google/gemini-2.5-flash` | 100% · 15/15 | **0%** (respuesta cortada a 160 tok) | ~740 | descartado por el fallo de árabe |
| `deepseek/deepseek-v4-flash` | 100% · 15/15 | 100% · 15/15 | **6.777-8.560** | descartado: razona, 48-59s por lote |

El fallo de `gemini` no se repitió al reintentar 3 veces (813-925 tokens, JSON completo), o sea es intermitente —
que es justo lo que no quieres en una tarea que corre UNA vez: **un lote perdido = 50 strings de UI en inglés**,
y no hay una segunda pasada que lo arregle. El de `deepseek` es el perfil que ya truncó el REM (§12.4): emite
6-8× más tokens de los que entrega. Coste del ganador: 514 claves = 11 lotes ≈ **$0,08 por idioma**, una vez —
a ese precio la fiabilidad se paga sola.

Con esto los CUATRO caminos de LLM off-hot-path (CORAZÓN · REM · i18n · Susurro) salen por el mismo broker, más el
FlashBrain que ya estaba. Fuera del broker quedan, a propósito: `code_agent` (Z.AI, plan de suscripción) y
`triage` (xAI, crédito propio). **La sonda correcta mira los DEFAULTS resueltos, no las menciones en el código**:
`api.openai.com` sigue apareciendo a propósito en el catálogo de opciones de la UI, en la resolución de key por
endpoint y en la tabla de tarifas de Energy. El script de verificación está en `zaelar-memory.md §Ningún camino
sale por OpenAI directo`; debe imprimir `api.aimlapi.com` en las cuatro tareas, con y sin `config/v2.json`
(comprobado en las dos formas el 2026-08-09, incluida la de repo recién clonado).

## 13. Candidatos en el radar (aún no evaluados/adoptados)

### 13.1 Xiaomi MiMo-V2.5-Pro-UltraSpeed — candidato Nº1 para FlashBrain cuando sea comercial (2026-07-22)

Xiaomi + TileRT_AI lanzaron (~2026-06-08) el primer modelo de **1T parámetros** (MoE, 42B activos) sirviendo
**>1000 tok/s de decode** en GPUs de 8 unidades COMMODITY (sin silicio wafer-scale tipo Cerebras) — FP4 cuantizado
en las matrices MoE (router+atención en precisión más alta) + "block-level masked parallel drafting"
(speculative decoding en bloques, acceptance ~4.3-6.3 tokens/ronda). Esto sería un salto de latencia real para
el FlashBrain/voz si la calidad de tool-routing aguanta (pendiente de A/B — ver §9.1/§11 metodología).

**Estado de acceso (verificado 2026-07-22):**
- `MiMo-V2.5-Pro` (el modelo BASE, sin UltraSpeed) SÍ está en AIMLAPI (`xiaomi/mimo-v2.5-pro`, $1.3/$3.9 por
  millón tok in/out, contexto 1M, compatible OpenAI Chat Completions) — pero es la velocidad NORMAL, no aporta el
  salto de los 1000 tok/s.
- `MiMo-V2.5-Pro-UltraSpeed` (la variante rápida) NO está en AIMLAPI ni en ningún proveedor tercero — solo se sirve
  desde `api.xiaomimimo.com/v1` (protocolo OpenAI y Anthropic), en un **trial limitado por tiempo** (ventana
  9-23 junio 2026 vista en el anuncio, condiciones cambiantes) con **aprobación diaria/solicitud**, prioridad para
  organizaciones — no self-serve. Precio trial: ~3× el modelo base por ~10× la velocidad.

**Decisión del operador (2026-07-22): ESPERAR a la versión COMERCIAL** (self-serve, sin aprobación, disponible vía
AIMLAPI u otro proveedor agregador) antes de integrarlo — no vale la pena cablear un piloto de acceso restringido
para un día de pruebas. **Cuando UltraSpeed sea comercial, es uno de los PRIMEROS candidatos a evaluar para
`config §fast`** (junto a los ya tested en §9.1/§11): A/B con el mismo arnés de siempre (prompt+`_TOOLS` reales,
medir TTFT real y fiabilidad de routing, no solo velocidad de decode nominal).

**Sobre el `MiMo-V2.5-Pro` normal (ya disponible hoy):** NO incorporar salvo que un A/B muestre ventaja real sobre
los modelos ya tested (grok-4.20-non-reasoning, gpt-4o-mini, haiku-4.5…) al mismo precio — de momento no hay razón
para añadirlo solo por ser nuevo.

## 14. BRAIN WORKERS — qué CLI conduce y qué modelo razona (2026-08-13)

Hasta hoy «el proveedor de los Brain Workers» era una sola casilla, y eso escondía que en realidad son **dos
decisiones independientes**: **quién CONDUCE** (el CLI headless: lee ficheros, ejecuta comandos, llama a nuestros
puentes) y **quién RAZONA** por debajo (el endpoint + su modelo). Una opción de worker es la TERNA completa. Elegir
las piezas por separado es lo que producía desajustes silenciosos (`glm-5.2` pedido a Codex, `gpt-5.5` pedido a
Z.AI): el fallo no aparecía al guardar sino minutos después, dentro de una tarea muerta. De ahí los **presets** de
`server/config_api.py`, que las mueven juntas.

### 14.1 Los tres CLIs, comparados por lo que de verdad los distingue

| | Claude Code | **Grok Build** | Codex |
|---|---|---|---|
| Transporte headless | `--output-format stream-json` | `--output-format streaming-messages-json` (**mismo vocabulario**) | `exec --json` (JSONL propio) |
| Entrega del prompt | stdin (stream-json) | **`--prompt-file`** (⚠️ `-p -` NO lee stdin) | stdin (`exec -`) |
| Allowlist de tools | `--allowedTools "Bash(cmd:*)"` | **`--allow 'Bash(cmd:*)'` — MISMA sintaxis, y la APLICA** | ❌ no existe (solo modos de sandbox) |
| Inyección en vivo | ✅ turnos por stdin | ❌ un turno (piggyback) | ❌ un turno (piggyback) |
| Reanudar | `--resume <sid>` | `--resume <sid>` | `exec resume <thread_id>` |
| Reporta coste | ✅ `total_cost_usd` | ✅ `total_cost_usd` | ❌ solo `usage` (lo tarifamos nosotros) |
| Sostiene el escritor único | ✅ | ✅ | ❌ |

**La fila que decide la arquitectura es la de la allowlist.** El invariante del ESCRITOR ÚNICO de la memoria se
sostiene acotando el `Bash` del worker a nuestros puentes; sin ese eje, un worker inducido por contenido web hostil
podría abrir la SQLite en paralelo. Claude Code y Grok Build pueden expresarlo — **verificado en Grok, no supuesto**:
con `--deny 'Bash(whoami:*)'` el CLI devolvió «Tool `run_terminal_command` was not executed: Denied by permission
policy: deny rule on bash matching "whoami"». Codex no puede, y headless necesita `workspace-write`, o sea shell
completo: por eso `registry.get_backend` es **mezclable por CAPACIDAD** y desvía a `claude_code` las tareas que
existen para estar acotadas (`deny_tools`, `kind="dev"`) aunque la config diga Codex.

**Grok Build hereda el traductor de Claude Code** (`GrokSession(ClaudeCodeSession)`) porque el wire format es el
mismo; solo se sobrescribe su vocabulario a través de una costura de tres métodos. Lo que cambia de verdad:

1. `run_terminal_command`/`read_file`/`search_replace`/`list_dir`/`grep`/`web_search` → se traducen a
   `Bash`/`Read`/`Edit`/`Glob`/`Grep`/`WebSearch` para que el panel hable el MISMO idioma con los tres backends.
2. **`read_file` manda `target_file`, no `path`** (verificado sondeando, no leído en la doc): con el nombre mal la
   fila salía «lee» sin decir QUÉ lee, que es el dato que hace auditable el paso.
3. Cada tool envuelve su evidencia distinto — `output_for_prompt` (Bash), `FileContent.content` (ReadFile) y
   **`stdout` como LISTA DE BYTES** (GrepSearch), que se pintaba «[60,119,111,…]».
4. `thinking` NO se convierte en fila: el panel muestra trabajo, no monólogo.

### 14.2 ⚠️ El prompt que no llega: la avería más CARA y más MUDA

`grok -p -` **no lee stdin** — toma el `-` como el prompt literal. Y no da error: el CLI arranca con un prompt sin
sentido y el modelo hace algo razonable por su cuenta. Medido:

| | tokens de entrada | coste | qué hizo |
|---|---|---|---|
| Prompt PERDIDO (`-p -`) | **447.559** | **$0,73** | exploró el repo entero y redactó un informe del proyecto |
| Prompt entregado (`--prompt-file`) | 59.825 | $0,087 | ejecutó el comando pedido y contestó en una línea |

Mismo CLI, mismo modelo (`grok-4.20-non-reasoning`), misma clase de tarea: **×8 en coste y cero utilidad**. Es la
razón de que el guard viva en tests (`test_grok_session.py`) y no solo en un comentario.

**Nota de coste que aplica a los tres:** el prompt de sistema + el catálogo de tools de estos CLIs es grande, así
que **un turno trivial ya cuesta céntimos** (~$0,03-0,09 aquí). El coste de un worker NO escala con lo pequeña que
sea la tarea; escala con cuántas vueltas dé. Un worker que se desorienta es caro por definición.

### 14.3 Los escalones de razonamiento (endpoint + modelo)

- **Z.AI / GLM coding plan** (`api.z.ai/api/anthropic`) — **suscripción**, que es la regla del operador (forfait,
  nunca por token). Su cuota es SEMANAL y cuando se agota todo el escalón muere de golpe: es justo para eso que
  existe la cadena de relevo de `workers/providers.py`. Ojo, tiene DOS cuotas independientes (los prompts del
  modelo y sus tools MCP internas) y solo la primera la ve la cadena.
- **DeepSeek** (`api.deepseek.com/anthropic`) — pago por token, el más barato (~$0,14/$0,28 por Mtok en v4-flash).
  Su gateway **MAPEA alias de Claude**: `sonnet`/`haiku` → `deepseek-v4-flash`, `opus` → `deepseek-v4-pro`. O sea
  que el modelo que se le manda es el ALIAS de Claude, no un nombre de DeepSeek — mandarle `deepseek-v4-flash` a
  pelo no es lo que espera. Va DESPUÉS de los planes de suscripción por ser por-token.
- **Grok 4.5 / 4.6** vía Grok Build — por token; 4.6 son $2/$6 por Mtok con 500k de contexto y razonamiento.
- **Licencia local de Claude Code** — último escalón y **SOLO en local**: un login de navegador no existe dentro de
  un contenedor, así que en la nube la cobertura la tienen que dar tokens de suscripción, nunca la licencia.

### 14.4 El banco: una tarea REAL de varias piezas, cada preset por turno (2026-08-13)

Comparar CLIs por sus flags no dice quién sirve. El banco (`bench_workers.py`, serializado — nunca en paralelo:
compartirían el pool y la red y los tiempos no serían comparables) manda una tarea de **tres piezas encadenadas**
—ferry + hotel + restaurante, con **enlace y precio por pieza** y obligación de marcar como **PROVISIONAL** lo que
no se pueda confirmar— y saca de la observabilidad lo que permite decidir.

**Una VARIANTE por corrida, y no es un capricho.** La primera pasada mandó la MISMA petición al segundo preset y el
FlashBrain, con toda la razón, **no escaló**: contestó «ya tienes los 10 planes en pantalla» resumiendo con exactitud
el resultado anterior. Es el producto funcionando bien —no repite trabajo que acaba de hacer— pero deja al banco sin
nada que medir. Las variantes son estructuralmente idénticas y solo cambian destino y fechas.

| | **Claude Code + Z.AI (glm-5.2)** | Grok Build + grok-4.5 | Claude Code + DeepSeek |
|---|---|---|---|
| Entrega | ✅ 10 propuestas completas | ⛔ ninguna (3 corridas) | — |
| Tiempo | 734 s (12 min) | 88 s hasta morir | — |
| Tokens (in/out) | 112.326 / 23.369 | 73.851 / 1.231 | — |
| Coste de la corrida | **$2,47** | $0,20-0,22 por corrida abortada | — |
| Evidencia recogida | 18 respuestas del mundo | 9 | — |
| Consultas a memoria | 26 | sí (sacó su 4x4 sin que nadie lo nombrara) | — |
| Honestidad | ✅ marcó PROVISIONAL lo no confirmable | no llegó a entregar | — |

**Lo que hace bueno al resultado de Z.AI no es la elocuencia: es lo que se NEGÓ a afirmar.** Confirmó con fuente lo
duro (Baleària único operador, *Eleanor Roosevelt*, ~2h15, servicio diario en septiembre, ~73-77 €/trayecto) y dejó
marcado como provisional lo que vive dentro del motor de reservas (horarios exactos, precio cerrado) y los precios de
hotel que estimó. Un worker que hubiera rellenado esos huecos habría producido una entrega **más bonita y peor que
nada**, porque el operador la usaría para reservar.

**Y lo hizo con la búsqueda web AGOTADA.** La cuota MCP de Z.AI estaba consumida hasta el 2026-08-30
(`MCP error -429 … Weekly/Monthly Limit Exhausted`), así que sus dos tools de servidor —`web_search_prime` y
`webReader`— devolvían el error. El worker lo leyó, lo dijo («no hay problema: ataco directamente las webs con
WebFetch») y siguió a mano: 403 de DirectFerries, 403 de Baleària, Booking sirviendo la búsqueda por JS, 404 de dos
agregadores, y sacó el dato de Ferryhopper y TripAdvisor. **Dato de producto: son DOS cuotas independientes** —la de
los prompts del modelo y la de sus tools MCP— y la cadena de relevo de `workers/providers.py` solo ve la primera. Un
candidato que solo funcione con la búsqueda buena no vale; este siguió con la mala.

⚠️ **`WebFetch` es la pata que hizo el trabajo, y Grok Build NO la tiene** (catálogo sondeado entero: solo
`web_search`). En ese backend la sustituyen los puentes —la `web_search` propia de Zaelar y el navegador real— no el
CLI.

#### Lo que el banco encontró, que es más valioso que la tabla

Ninguno de estos se ve leyendo código; los cuatro salieron de correrlo:

1. **La hoja de resultados enrutaba al GENERADOR de widgets.** Pedir la entrega «en el widget results» hacía que
   `looks_like_create_widget` viera una orden de CREAR un widget → se generó el widget basura
   `prepara-ricart-viaje` en vez de investigar. La hoja de resultados es la superficie de entrega de **toda**
   investigación, así que esto estaba en el camino más transitado del sistema. Arreglado en `flash/router.py`
   neutralizando el widget de DESTINO antes de clasificar (familia V2-081).
2. **Susurro inventó una acción y la EJECUTÓ.** Con el buffer conversacional vacío la ventana de auditoría salió sin
   sección de conversación (el ensamblador omite las vacías sin decir que faltan), y el auditor rellenó el hueco con
   el caso de EJEMPLO de su propio prompt de sistema: afirmó como hecho «el operador pidió cancelar una cita» y
   despachó un worker real a cancelarla. Dos defensas nuevas: no auditar sin conversación (`window.has_conversation`)
   y exigir ANCLAJE en la ventana a `worker_action`, la única corrección que ACTÚA.
3. **El worker de Grok se quedaba sin escritura y luego sin permisos.** Dos capas del mismo fallo, ambas mudas para
   quien mira el código: `_GROK_TOOLS` solo traía lectura, así que al ir a dejar su informe rodeaba por la terminal y
   la allowlist lo denegaba; y al añadir `write`, seguía muriendo porque **con una sola regla `--allow` la allowlist
   pasa a ser ESTRICTA** y ninguna tool tenía la suya. Encima, Grok presenta una denegación como «**User cancelled
   the execution**», que un modelo lee como que el humano lo abortó — así que **paraba con entrega vacía tras haber
   trabajado bien**. Tres corridas perdidas y ~$0,60 en aprender que la reja hay que explicarla, no solo ponerla.
4. **El accounting de pasos del banco era falso.** Contaba `task · paso` del log durable y daba 2 en una corrida que
   hizo 6: los pasos NO viven todos ahí, cada puente los emite bajo SU familia (el visor ◷ los agrega, el log no), y
   `/api/tasks` recorta a los **últimos 6** (`dispatch.py:364`). Se mide por familias del log durable, que en un
   banco serializado es atribución suficiente.

**Estado de las tres opciones:**

- **1 · Claude Code + Z.AI** — la única PROBADA de punta a punta sobre una tarea real. Es la de producción.
- **2 · Claude Code + DeepSeek** — **sin probar, y es la que más interesa**: 10 veces más barata que las otras dos.
  Bloqueada por credencial (no hay ninguna `DEEPSEEK_API_KEY` en ningún store).
- **3 · Grok Build + grok-4.5** — el backend ya es correcto (traduce su stream, usa los puentes, trae evidencia real,
  lee la memoria del operador) y los tres defectos del adaptador están arreglados con guards. Falta una entrega
  completa medida para poder compararlo de verdad.
