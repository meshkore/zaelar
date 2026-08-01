# tests/voice/e2e/agent/reports — histórico de sesiones de test (consultable)

Una carpeta por **sesión/tanda de test**, nombrada **`<YYYYMMDD>-<descripción-corta>/`** (fecha invertida
año-mes-día + descripción), calcando la convención de los tests de memoria. Ejemplos:
`20260711-bateria-v2024-google-prewarm/`, `20260718-regresion-semanal/`.

Cada carpeta contiene:
- **`INFORME.md`** — qué se probó, tabla de resultados (por escenario: estado/overall/scores/latencia), hallazgos
  (bug real vs ruido de STT vs rigidez del juez), arreglos hechos, y **latencias antes/después**. Para navegación
  web: el veredicto HUMANO de si extrajo datos reales que cumplen los criterios (✋).
- La **tabla resumen** de la batería (`battery_summary_*.tsv`) y los `report_*.{json,md}` relevantes de esa tanda.

Objetivo: repetir la batería una semana después y **comparar** contra el histórico. Los
`tests/voice/e2e/agent/runs/` son scratch en crudo (se sobrescriben/acumulan);
`tests/voice/e2e/agent/reports/` es el archivo curado que se conserva.

> Cómo se genera: al cerrar una tanda, el agente (o el operador) crea la carpeta del día y vuelca ahí el INFORME +
> los artefactos. Ver el playbook `.meshkore/docs/ops/zaelar-testing.md` §"Dónde se archiva".
