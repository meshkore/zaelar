# notes — ejecuta-accion-real

- Creado (2026-07-25): sigue una acción del MUNDO REAL que el FlashBrain no pudo completar por sí solo (cancelar,
  comprar, enviar…) y que se escaló a un worker (patrón V2-061 hbwidget). Muestra `pendiente → en curso →
  verificada/fallida` con notas de avance en vivo; nunca da algo por hecho sin verificación. Foreground-only (no
  `background`): el worker empuja el estado vía `apply_action` (queue/progress/verified/failed), el widget solo
  pinta. Data-ops NO confirm — solo REFLEJAN lo que ya ocurrió de verdad, no causan nada irreversible por sí
  mismas. `retry` reabre una fallida; `dismiss` la quita de la vista (no borra histórico en memoria).
