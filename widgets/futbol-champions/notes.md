# notes — futbol-champions

- Widget de resultados de la UEFA Champions League: por cada partido muestra equipo local y visitante con su
  marcador. Read-only, foreground-only (se computa al leer, sin background) — **no hay fuente en vivo keyless**,
  así que `data.py` devuelve una lista de resultados de EJEMPLO estáticos (constraint del usuario: "datos de
  ejemplo estáticos si no hay fuente en vivo"). Si algún día se cablea una fuente en vivo, sustituir
  `_static_results()` por un fetch stdlib manteniendo la MISMA shape y el fail-open.
- Diseño limpio: cada partido es una fila en grid `local | marcador | visitante`; local alineado a la derecha,
  visitante a la izquierda, marcador monoespaciado centrado en píldora. Contrato de tema `--hb-*` en todo (sin
  hex hardcodeado dependiente de tema). Clases prefijadas `ucl` para no colisionar con `frontend/app/styles.css`.
- Sin `apply_action` → sin `actions`/`usage` en el manifest. Sin `background`/`tick`.
