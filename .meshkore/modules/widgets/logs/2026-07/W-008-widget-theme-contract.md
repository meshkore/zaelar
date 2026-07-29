---
id: W-008
title: "Contrato --hb-* para que los widgets sigan el tema dark/light del host"
status: done
priority: medium
owner: ricart
initiative: INI-011
created: 2026-07-06
updated: 2026-07-06
---

# Widgets adaptables a dark/light

## Qué se hizo

Cada widget vive aislado con su propio `<style>` inyectado y, hasta ahora, colores hex fijos asumiendo un canvas
claro (ver `T-32` en `frontend/logs/` para el sistema de tema del host). Al pasar el frontend a dark-por-defecto,
los widgets se habrían quedado con cartas blancas fijas sobre un canvas oscuro. Se definió un contrato público de
variables CSS (`--hb-bg`, `--hb-bg-soft`, `--hb-ink`, `--hb-muted`, `--hb-muted-2`, `--hb-line`, `--hb-accent`,
`--hb-accent2`, `--hb-risk`, `--hb-neutral`, `--hb-warn-bg/-border/-ink`) expuesto en `:root` por
`frontend/app/styles.css`, que cualquier widget hereda por vivir en el mismo DOM (sin import, sin acoplarse a los
nombres internos de la app).

- **Los 7 widgets existentes migrados**: `clock`, `agenda` (incl. el mapa `KIND` de colores por tipo de bloque y
  el botón "Replanificar" que usaba `style.cssText` inline), `results`, `search`, `meteo-soria`,
  `meteo-tarragona-grafico` (incl. `fill`/`stroke` de SVG), `cluster-registro`.
- `widgets/AGENTS.md` §Visual style: reescrito para documentar el contrato completo + la regla "nunca hex
  hardcodeado para algo theme-dependent", con el patrón de fallback `var(--hb-bg,#fff)`.
- `widgets/generator.py` (`_CONTRACT`, usado por `_CREATE_PROMPT`/`_MODIFY_PROMPT`): actualizado para que TODO
  widget nuevo generado por el agente headless use el contrato desde el día uno.

## Ficheros tocados

`widgets/AGENTS.md`, `widgets/generator.py`, `widgets/clock/widget.js`, `widgets/agenda/widget.js`,
`widgets/results/widget.js`, `widgets/search/widget.js`, `widgets/meteo-soria/widget.js`,
`widgets/meteo-tarragona-grafico/widget.js`, `widgets/cluster-registro/widget.js`.

## Verificación

`make test-widgets` → 7/7 OK (contrato + golden shape + parse ES module; las colisiones de keywords reportadas
son preexistentes, no relacionadas). Verificación visual con Playwright: `clock` y `agenda` abiertos a la vez,
repintan de light→dark y viceversa **sin recargar y sin re-render de JS** (el cambio es puramente CSS), tal como
exige el contrato.
