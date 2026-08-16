# Vida cronológica de memoria · 270 días

Este corpus responde a una pregunta distinta de los pytest y de los corpus históricos: **¿cómo evoluciona una
misma memoria con el paso real del tiempo?**

- Una sola BD aislada: `memory/_data/zaelar.timeline.db`.
- **~1209 operaciones** estrictamente ordenadas del día 0 al 270 — 180 días de guion FIJO (regresión) + 90 días
  de **tramo REAL semilla-reproducible** (V2-105, ver más abajo).
- Cada ejecución completa borra esa BD y reconstruye la vida desde cero.
- Ejecutar un caso `N` reproduce primero `0..N-1`; nunca se permite una consulta sin sus escrituras causales.
- El reloj inyectable altera timestamps reales de writer, retriever, consolidación y REM; no son etiquetas de texto.

## Ciclo diario

1. Avanzar el reloj.
2. Insertar actividad cotidiana de baja importancia y TTL de 2/20 días.
3. Insertar episodios de importancia media cada 15 días y TTL trimestral.
4. Consultar/reforzar objetivos con distintas frecuencias.
5. Ejecutar sueño ligero: promoción, dedup, decay, expiración TTL, poda y eviction.
6. Ejecutar REM determinista cada día, tras el sueño ligero, igual que la cadencia productiva de 24 horas.
7. Verificar checkpoints de retención, corrección, pesos y tamaño activo.

El día 45 corrige «infancia en Sevilla» por «infancia en Segovia» después de cientos de operaciones. Al día 180
solo Segovia puede estar vigente. Vivienda se consulta semanalmente y arquitectura cuatro veces: el peso/acceso de
vivienda debe terminar por encima. La alergia a la penicilina es crítica/pinned y debe sobrevivir siempre.

```bash
# vida completa, DETERMINISTA (gratis, rápido — el hook de síntesis es Python puro)
./.venv/bin/python -m tests.memory.e2e.timeline.runner --all

# reconstruir desde cero hasta una operación concreta
./.venv/bin/python -m tests.memory.e2e.timeline.runner --target 500

# vida completa con REM REAL (DeepSeek V4 Flash, coste real — norma del operador 2026-08-17:
# "todas las pruebas tienen que ser reales... no nos importa el coste")
./.venv/bin/python -m tests.memory.e2e.timeline.runner --all --real

# plataforma unificada + Observatory
./.venv/bin/python -m tests run memory --case memory::group::1.4::timeline-6m
```

## Tramo REAL semilla-reproducible (V2-105, 2026-08-17)

Los primeros 180 días son un guion 100% fijo — perfectos para regresión, ciegos a la PRÓXIMA clase de bug: un
usuario real de 20-30 días se corrige a destiempo, repite el mismo hecho con otras palabras semanas después, o
dice dos cosas casi-simultáneas que compiten por el mismo dato. `cases.py::_real_tramo()` añade 90 días más
(181-270) generados con `random.Random(SEED)` — reproducible para una seed dada (mismo run = mismos casos
siempre), variedad real si se cambia la seed. Reutiliza el vocabulario de `op` YA existente
(`write`/`slot`/`recall`) — no hace falta ninguna rama nueva en `runner.py::_execute()`. Tres formas nuevas:

- **Contradicción diferida**: un hecho con `slot` sintético, y 5-35 días después una segunda escritura que lo
  confirma (30%) o lo corrige (70%) — comprueba el supersede bajo una ventana de TIEMPO real, no segundos.
- **Paráfrasis diferida**: el mismo hecho, sin `slot`, reformulado 14-55 días después con vocabulario distinto
  — verificado por RECALL (no se asume si el dedup exacto/semántico fusiona; depende del backend de embeddings
  activo, incierto de antemano — solo que el hecho SIGUE siendo recuperable).
- **Hecho en competencia**: dos valores distintos para un mismo `slot` sintético, separados 0-6 días — el más
  reciente debe ganar, aunque la ventana sea de días y no de segundos.

`--real` (flag nuevo de `main()`) cablea `nucleo/memllm.synthesize_concept_groups`/`verify_insight_grounded`/
`generate_paraphrases` REALES en vez de `_deterministic_hook`, y fuerza `ZAELAR_EMBED_BACKEND=fastembed` (evita
Ollama a propósito — norma del operador, 2026-08-17: el trabajo con modelos LOCALES queda aparcado hasta
validar todo contra el modelo de pago; se retomará entonces con el mismo benchmark). Sin `--real`, el corpus
sigue siendo 100% determinista y gratis, comportamiento por defecto sin cambios.

**Dos bugs reales encontrados construyendo esto** (ninguno hipotético — los cazó la primera corrida real):
(1) una resolución diferida programada para un día fuera del rango del bucle se perdía en silencio — la
escritura quedaba sin su comprobación; corregido acotando los márgenes de `gap`/`offset` por banco. (2) un
checkpoint `slot` sin `not_marker` explícito falla SIEMPRE — `_execute()` trata la ausencia como cadena vacía y
`"" in text` es cierto en Python para cualquier texto; corregido pasando siempre el valor excluido. Ambos
fijados como regresión en `tests/memory/unit/test_timeline_cases.py` (estructural, sin tocar la BD del
timeline — corre en cada commit).

## Qué no pretende cubrir

La clasificación semántica por LLM de cada frase ya se estresa en los corpus v1/v2. Esta simulación usa la API y
el writer reales con decisiones de importancia explícitas para aislar y medir el ciclo vital.

**Síntesis de REM (V2-103, 2026-08-16):** REM ejecuta las cuatro fases —reparación, dedup semántico, síntesis e
higiene— con un **hook determinista Python puro** (`runner.py::_deterministic_hook`, sin red/LLM: sigue sin
proveedor externo, pero ya no deja `synthesize()`/`demote_summarized()` sin ejercitar). Antes de esto, este era
el ÚNICO run largo/realista de toda la suite y corría con la síntesis explícitamente apagada
(`rem.run(None)`) — el hueco que dejó pasar el hallazgo de una auditoría manual: REM nunca demotaba las píldoras
que resumía, solo añadía el insight encima. El write recurrente "episodio relevante temporal" (cada 15 días)
lleva `concepts=["estudios"]`; a día 180 acumula ~6-7 referencias vigentes (por encima de `rem.MIN_GROUP=4`), y
los checkpoints finales (`insight_exists`, `pills_demoted`) verifican que REM sintetizó el insight Y demotó las
píldoras crudas — no solo que "algo se escribió".
