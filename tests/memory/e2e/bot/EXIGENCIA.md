# PROMPT DE EXIGENCIA — el control de calidad que se pasa CADA 50 casos nuevos

> **Mandato del operador (2026-07-11):** «Cada 50 passes, cuestiónate si vamos en la buena dirección: si estamos
> duplicando tests, si hay que cambiar el approach, si hay que buscar información para machacar la memoria, qué nos
> falta por probar, y cómo podríamos EVOLUCIONAR y mejorar esa memoria — hacer una iteración de mejora y luego
> machacar las pruebas otra vez.»
>
> De ~400 a 1000 hay **12 puntos de control** (450, 500, 550, … 1000). En CADA uno, PARA de producir casos y pasa
> esta checklist. No es opcional: es la diferencia entre 600 tests que valen y 600 que rellenan.

## Cuándo se dispara

En cada iteración autónoma, tras correr la tanda: si `len(CASES)` ha cruzado un múltiplo de 50 desde la última vez
→ **antes de seguir**, ejecuta este audit y escribe su veredicto (5-8 líneas) en `INI-013` con fecha. Si no lo ha
cruzado, sigue con la iteración normal.

## La checklist (respóndela por ESCRITO, sin autocomplacencia)

1. **¿DUPLICAMOS?** Corre `--coverage`. Mira las 2-3 dimensiones con más casos. ¿Los últimos casos de esas
   dimensiones cazan un modo de fallo DISTINTO, o repiten «doy dato → lo guarda → lo leo» con otro disfraz? Regla
   dura: **un dato que ya sabemos que se guarda y se lee bien NO se vuelve a testear**. Si encuentras duplicados,
   bórralos (bajar el contador es legítimo) y anótalo.

2. **¿VARIEDAD real?** ¿La tanda de estos 50 tocó los EJES del operador?
   - **Longitud de input**: telegráfico (1-4 palabras) ↔ parrafada (100-300 palabras) con la aguja enterrada (dim V).
   - **Volumen**: cientos ↔ miles de recuerdos y luego preguntar por algunos (dim K, harness `scale`).
   - **Las 3 velocidades por separado**: ESTADO (perfil, siempre en prompt), CORTO (recencia/working-set),
     LARGO (recall semántico bajo demanda). ¿Probamos cada una de forma aislada, no siempre mezcladas?
   Si algún eje no se tocó en 50 casos, el siguiente bloque lo ataca.

3. **¿QUÉ NOS FALTA?** Repasa las 23 dimensiones (A–W) + el mapa de habilidades de la literatura (abajo). ¿Cuál
   está a 0 o infra-cubierta respecto a su importancia? La #1 del operador es **K (escala)**. ¿Hay una habilidad
   del estado del arte (multi-hop, temporal, knowledge-update, abstención, conflicto multi-fuente) que aún no
   tenga un probe INCISIVO (no amable)?

4. **¿CAMBIO DE APPROACH?** ¿El harness sigue siendo fiel al camino real (`_brain_view` = lo que ve el FlashBrain,
   sin LLM)? ¿Hay un tipo de fallo que el harness ACTUAL no puede ver (p. ej. abstención query-time, que es
   comportamiento del LLM → no del membot → va al tester en vivo INI-013)? Si un test no puede afirmar algo real,
   NO lo escribas: documenta el límite.

5. **¿BUSCAR MÁS MUNICIÓN?** Cada 100 casos (o si la checklist huele a agotamiento de ideas): **WebSearch** de
   benchmarks de memoria (LongMemEval, LoCoMo, MemBench, MemoryAgentBench, MemConflict, BEAM, mem0 report…). Trae
   ≥1 arquetipo de prueba nuevo que no tengamos y conviértelo en dimensión o batch.

6. **¿EVOLUCIONAR LA MEMORIA?** El testing no es solo cazar; es guiar mejoras. Si una dimensión falla de forma
   ESTRUCTURAL (no un anchor mal puesto), esa es una señal de MEJORA de la memoria, no solo del test. Propón la
   mejora (feature en `memory/` o `nucleo/`), impleméntala, y LUEGO vuelve a machacar con tests más duros. Alterna:
   **machacar → detectar → mejorar la memoria → machacar más fuerte**. Anota la hipótesis de mejora aunque no la
   implementes esta vuelta.

7. **HIGIENE**: pytest verde (`tests/test_memory_*.py` + `test_memory_agent.py`). `--coverage` actualizado en
   `TAXONOMY.md`. Anclas inequívocas (marker/want único del dato objetivo, sin colisiones). Cada caso con su `dim`.

## Veredicto (formato para pegar en INI-013)

```
### Audit de exigencia @N casos — <fecha>
- Duplicación: <ninguna / borré X / riesgo en dim Y>
- Variedad (longitud/volumen/3 velocidades): <cubierta / hueco en …>
- Hueco prioritario ahora: <dim + por qué>
- Approach: <sin cambios / cambié … / límite documentado: …>
- Munición nueva (web): <n/a esta vez / arquetipo nuevo: …>
- Mejora de la memoria propuesta/hecha: <hipótesis o feature>
- pytest: <N passed>
```

## Mapa de habilidades del estado del arte → nuestras dimensiones (para el punto 3)

Síntesis de la literatura (LongMemEval ICLR 2025 · LoCoMo · MemBench · MemoryAgentBench · MemConflict · BEAM):

| Habilidad canónica del campo | Nuestra dim | Notas |
|---|---|---|
| Information extraction (single-hop) | A / B / C | cimientos |
| Multi-hop / multi-session reasoning | **U** | el recall aflora TODOS los eslabones |
| Temporal reasoning | J | gap conocido (T151) — reforzar |
| Knowledge updates | M / D | corrección + supersede |
| Abstention (unanswerable → no alucinar) | E (write) | query-time NO es del membot → tester en vivo |
| Preference / instruction following | I / **W** | preferencia + directiva permanente |
| Contradiction / conflict handling | M | falta CONFLICTO multi-fuente (MemConflict) |
| Scale, distractors, needle-in-haystack | **K** | harness `scale` graduado + falsos-amigos |
| Verbosity / extraction robustness | **V** | telegráfico ↔ parrafada |
