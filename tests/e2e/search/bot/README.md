# Test bot de BÚSQUEDA WEB (V2-022)

Prueba la capacidad de búsqueda del cerebro **empezando por el FlashBrain** y **sin la capa de voz/LiveKit por
encima** (aislado, para depurar limpio). Mismo patrón que el test bot de memoria (`tests/e2e/memory/bot/`).

## Qué verifica (por cada caso)

1. **Routing** — el FlashBrain decide por sí mismo (function-calling, sin clasificador). Comprobamos que elige la
   ruta correcta:
   - `search` → llama a `web_search` (dato del mundo real + síntesis).
   - `no_search` → lo responde él (memoria, matemáticas, charla, conocimiento estable). NO busca.
   - `escalate` → una TAREA en una web (navegar/comprar/comparar en un marketplace) → el navegador, no `web_search`.
2. **Respuesta** (solo si busca) — tras `websearch.search` + el 2º pase que compone la respuesta hablada (idéntico
   a `voice/engine/llm/providers/nucleo.py`), juzga si es correcta/precisa: subcadenas esperadas (`want`) + un
   **juez LLM** (GLM vía Z.AI, fallback DeepSeek).

> **Nota sobre el juez y los datos frescos:** para valores sensibles al tiempo (cotizaciones, marcadores, precios)
> el juez NO usa su propia memoria (está desactualizada respecto a la búsqueda en vivo) — solo marca fallo si la
> respuesta es evasiva, vacía, contradictoria o absurda. Para hechos estables (capitales, autores, mates) sí verifica.

## Cómo se ejecuta

```bash
# siguiente tanda (~10 casos) desde el progreso guardado
./.venv/bin/python -m tests.e2e.search.bot.runner --next 10
./.venv/bin/python -m tests.e2e.search.bot.runner --fresh --next 10   # reinicia y arranca de cero
./.venv/bin/python -m tests.e2e.search.bot.runner --range 0 10        # una tanda concreta
./.venv/bin/python -m tests.e2e.search.bot.runner --all               # todo el set
```

- BD **aislada** (`ZAELAR_DB=memory/_data/zaelar.searchbot.db`) — nunca toca el perfil real.
- Modelo rápido + keys se cargan como en producción (`server.common`); el juez usa los keys del tester.
- Progreso en `.meshkore/logs/searchbot/progress.json` · informe en `.meshkore/logs/searchbot/report.md`.

## El bucle de mejora (cada 10 min, hasta ~8h)

Diseñado para correr en bucle (`/loop 10m`): cada iteración corre una tanda, analiza los fallos, **arregla el
sistema de búsqueda en código** si hay un bug real (no ruido del juez), re-verifica, **crece el set** con casos
adversariales nuevos, y documenta. Termina cuando el set es amplio y estable (dos pasadas verdes) o se agota el
presupuesto de tiempo.

## Categorías (`scope`)

`factual_easy` · `factual_hard` · `current_events` · `imprecise` (vagas, exigen reformular) · `routing_math` ·
`routing_memory` · `routing_chat` · `routing_task` (marketplace → escalar) · `stable_knowledge` · `multilingual`.
