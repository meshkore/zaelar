# notes — ejecuta-accion-real

- Creado (2026-07-25): sigue una acción del MUNDO REAL que el FlashBrain no pudo completar por sí solo (cancelar,
  comprar, enviar…) y que se escaló a un worker (patrón V2-061 hbwidget). Muestra `pendiente → en curso →
  verificada/fallida` con notas de avance en vivo; nunca da algo por hecho sin verificación. Foreground-only (no
  `background`): el worker empuja el estado vía `apply_action` (queue/progress/verified/failed), el widget solo
  pinta. Data-ops NO confirm — solo REFLEJAN lo que ya ocurrió de verdad, no causan nada irreversible por sí
  mismas. `retry` reabre una fallida; `dismiss` la quita de la vista (no borra histórico en memoria).
- (2026-07-28) Añadida línea de CONFIRMACIÓN visible en la tarjeta cuando `status==="verified"` ("✓ Completada y
  verificada en la realidad", `.eje-done` en `--hb-accent2`) — el operador ve claramente que la acción real (p.ej.
  mostrar la lista de tiendas de bicis) se COMPLETÓ de verdad, no solo que se anotó. Edición quirúrgica aditiva: no
  toca layout/estado/data-ops; el badge "verificada" sigue igual. Sin `confirm` (solo refleja lo ya ocurrido).
