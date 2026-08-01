# Vida cronológica de memoria · 180 días

Este corpus responde a una pregunta distinta de los pytest y de los corpus históricos: **¿cómo evoluciona una
misma memoria con el paso real del tiempo?**

- Una sola BD aislada: `memory/_data/zaelar.timeline.db`.
- 966 operaciones estrictamente ordenadas del día 0 al 180.
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
# vida completa
./.venv/bin/python -m tests.memory.e2e.timeline.runner --all

# reconstruir desde cero hasta una operación concreta
./.venv/bin/python -m tests.memory.e2e.timeline.runner --target 500

# plataforma unificada + Observatory
./.venv/bin/python -m tests run memory --case memory::group::1.4::timeline-6m
```

## Qué no pretende cubrir

La clasificación semántica por LLM de cada frase ya se estresa en los corpus v1/v2. Esta simulación usa la API y
el writer reales con decisiones de importancia explícitas para aislar y medir el ciclo vital. REM ejecuta reparación,
dedup semántico e higiene; la síntesis de insights se omite para mantener el run determinista y sin proveedor externo.
