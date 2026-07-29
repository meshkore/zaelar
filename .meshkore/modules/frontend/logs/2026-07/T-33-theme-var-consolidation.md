---
id: T-33
title: "Consolidar variables de tema a un único namespace --hb-*; Tailwind evaluado y descartado"
status: done
priority: low
owner: ricart
initiative: INI-011
created: 2026-07-06
updated: 2026-07-06
---

# Consolidación de variables CSS + evaluación de Tailwind

## Qué se hizo

Tras `T-32` (dark/light theme), el operador pidió estandarizar y simplificar el sistema de estilos al máximo,
dejando Tailwind como opción a mi criterio. Decisión: **no Tailwind** — ver el razonamiento completo en
`INI-011 §Follow-up`. Resumen: rompería "no build, no npm" (frontend) o "self-contained, no CDN" (widgets), y
el problema de tema ya lo resuelve mejor una variable CSS (`var(--hb-bg)`, cambia sola) que pares
`bg-white dark:bg-slate-900` por elemento.

En su lugar:
- `app/styles.css`: eliminada la capa de alias `--hb-*` → `--panel-bg`/`--muted`/`--ink`/… del primer pase.
  Ahora hay UN solo namespace (`--hb-bg`, `--hb-bg-soft`, `--hb-bg-a`, `--hb-ink`, `--hb-muted`, `--hb-muted-2`,
  `--hb-line`, `--hb-accent`/`--hb-accent2`, `--hb-risk`/`--hb-risk-soft`, `--hb-neutral`, `--hb-bubble`,
  `--hb-hover`, `--hb-shadow-1`/`--hb-shadow-2`, `--hb-warn-bg`/`--hb-warn-border`/`--hb-warn-ink`) que usan
  tanto el chrome de la app como los widgets — cero duplicación de nombres para el mismo valor.
  `--canvas`/`--canvas-glow`/`--chrome-line`/`--mono`/`--sans`/`--banner-h` quedan sin prefijo (estructura del
  app-shell, no forman parte del contrato de color de los widgets).
- Nuevo §WIDGET KIT en `styles.css`: clases opcionales `hbk-card`/`hbk-hd`/`hbk-sub`/`hbk-muted`/`hbk-empty`/
  `hbk-chip`/`hbk-btn` para los patrones que se repetían en los 7 widgets (cabecera, card, vacío, chip, botón).
- `app/widgets/desktop.js`: actualizado a los nuevos nombres (`--hb-shadow-2`, `--hb-bubble`).

## Bug repetido (mismo patrón que T-32)

Al reescribir la cabecera de `styles.css` volví a escribir `widgets/*/widget.js` literal en un comentario CSS —
el `*/` cerró el comentario a medias y tumbó el bloque `:root` oscuro otra vez (mismo síntoma: `cssRules` a 0
para ese bloque). Detectado de inmediato por la MISMA verificación con Playwright que ya tenía montada. Fix:
reescribir sin la secuencia `*/` literal. Confirma que la verificación visual real —no solo el harness de
widgets, que no toca `styles.css`— es la que atrapa esta clase de error.

## Ficheros tocados

`frontend/app/styles.css`, `frontend/app/widgets/desktop.js`, `widgets/AGENTS.md`, `widgets/generator.py`.

## Verificación

`make test-widgets` (7/7). Playwright: 3 widgets abiertos a la vez (`results`, `clock`, `agenda`), correctos en
dark y light tras la consolidación, sin errores de consola.
