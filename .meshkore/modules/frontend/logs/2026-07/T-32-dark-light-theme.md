---
id: T-32
title: "Dark/light theme — dark por defecto, toggle ☾/☀ en TopBar"
status: done
priority: medium
owner: ricart
initiative: INI-011
created: 2026-07-06
updated: 2026-07-06
---

# Dark/light theme para el frontend

## Qué se hizo

El operador reportó que el frontend en "white mode" brillaba demasiado de noche. Se añadió un sistema de tema
completo, **dark por defecto**:

- `app/styles.css`: paleta migrada a variables CSS (`--canvas`, `--ink`, `--line`, `--panel-bg`, `--panel-bg-soft`,
  `--muted`, `--muted-2`, `--neutral`, `--shadow-1/2`, `--warn-*`, `--bubble-bg`, `--hover-bg`, `--risk-soft`, …)
  en `:root` (dark) con override en `:root[data-theme="light"]`. ~40 hex hardcodeados reemplazados. Alias público
  `--hb-*` añadido para el contrato de widgets (ver entrada `W-008` en `widgets/logs/`).
- `app/core/store.js`: signal `theme` (`localStorage.hb_theme`, default `"dark"`).
- `app/services/theme.js` (nuevo): `initTheme()` aplica `<html data-theme>` + `meta#themeColorMeta` vía
  `createEffect`; `toggleTheme()`.
- `app/components/TopBar.js`: icono ☾/☀ nuevo (entre ⏰ y ⚙).
- `app/widgets/desktop.js`: el chrome de las ventanas de widget (`hb-win`/`hb-grip`/`hb-x`/`hb-load`/`hb-cap`)
  pasa a `var(--hb-*, fallback)`.
- `index.html`: `meta[name=theme-color]` con id `themeColorMeta` para que `theme.js` lo actualice en runtime.

## Ficheros tocados

`frontend/app/styles.css`, `frontend/app/core/store.js`, `frontend/app/services/theme.js` (nuevo),
`frontend/app/components/TopBar.js`, `frontend/app/widgets/desktop.js`, `frontend/index.html`.

## Bug encontrado + fix

El comentario de cabecera de `styles.css` contenía `widgets/*/widget.js` — el `*/` cerraba el comentario CSS a
medias y el navegador descartaba el bloque `:root` oscuro entero (confirmado con `document.styleSheets[0].cssRules`
en Chromium real: 0 reglas para ese bloque, mientras `:root[data-theme="light"]` sí parseaba). La app quedaba
blanca pese a `data-theme="dark"` correcto en el DOM. Fix: reescribir la frase evitando la secuencia `*/` literal.

## Verificación

Playwright (Chromium real) contra el servidor vivo en `:8473`: tema dark al cargar, toggle a light instantáneo
(icono cambia a ☀), modal ⚙ y panel ⏰ correctos en ambos temas, persistencia en `localStorage` tras reload,
`console --errors` limpio. Ver también `widgets/logs/2026-07/W-008-widget-theme-contract.md` para la parte de
widgets.
