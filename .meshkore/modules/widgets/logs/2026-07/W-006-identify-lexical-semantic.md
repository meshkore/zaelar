---
id: W-006
title: "W-5 · identify() léxico-semántico (stdlib) + plan documentado del salto a embeddings"
status: done
priority: medium
owner: ricart
initiative: INI-006
created: 2026-07-03
updated: 2026-07-03
---

# W-006 — Evolución de `identify()` (INI-006 · W-5)

## Qué se hizo

`runtime.identify()` hacía substring-matching plano de keywords: sensible a acentos (por eso los manifests
duplicaban "previsión"/"prevision"), sin tolerancia a typos del STT, con falsos positivos por subcadena
("consola" disparaba una keyword "sol") y sin usar description/whenToUse. Suficiente para decenas, débil para
el objetivo de miles.

**Implementado ahora (abarcable, stdlib-only, misma API `match/ambiguous/candidates`):**

- Normalización **accent-insensitive** (`unicodedata`) de query e índice.
- **Índice cacheado por firma del catálogo** (mtimes, como el cache de `catalog()`): keywords normalizadas,
  tokens de id/título y tokens descriptivos pre-computados → el coste por llamada es solo la query
  (~0.23 ms/call en caliente; corre en cada transcript).
- Frases-keyword **alineadas a palabra** (adiós falsos positivos por subcadena), pesos clásicos (2/1).
- **Fuzzy por token** (`difflib`, cutoff 0.84) para typos de voz ("tarrgona" → meteo-tarragona).
- id/título dominan (+3); solape con description/whenToUse aporta señal **capada** (máx 1.5) que desempata pero
  **nunca** invoca un widget por prosa sola (umbral de score ≥1).
- Stopwords es/en fuera del ruido.

**Diseñado y documentado (siguiente etapa, cuando el catálogo desborde el recall léxico):** tier semántico con
embeddings locales (encoder pequeño ONNX), vector por manifest calculado al indexar el catálogo y por query al
preguntar, ranking por coseno, catálogo como única fuente de verdad y el scorer léxico como fast-path/fallback.
Documentado en `zaelar-modules.md §Widgets → Voice→widget identification` (junto con el tag `[[delete]]` de W-2
y el `DELETE /widgets/{id}` en el contrato HTTP).

## Ficheros tocados

- `widgets/runtime.py` — `_norm()`, índice `_identify_index()` cacheado, `identify()` reescrito (misma API).
- `.meshkore/docs/modules/zaelar-modules.md` — párrafo de identificación por voz + plan de embeddings; tag
  protocol actualizado con delete.

## Verificación

- Test dirigido (scratchpad `test_w5.py`): las peticiones clásicas siguen resolviendo (agenda/clock/registro);
  acentos en ambos sentidos; typo "tarrgona" resuelve; petición genérica de tiempo mantiene ambos meteo como
  candidatos; charla sin relación → sin match; sin falsos positivos por subcadena; 0.23 ms/call.
- Servidor vivo: `/widgets/identify?q=previsión en tarragona` → meteo-tarragona-grafico (score 7.0) con
  meteo-soria como candidato.
