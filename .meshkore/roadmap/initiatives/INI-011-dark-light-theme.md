---
id: INI-011
title: Dark/light theme — dark por defecto, contrato de tema para widgets
status: done
owner: ricart
modules: [frontend, widgets]
updated: 2026-07-06
---

## Goal

El frontend era 100% "white mode": una pantalla a tope de brillo blanco es molesta/dañina de noche. Meter un
**modo oscuro por defecto**, con toggle a claro, y —el reto real— hacer que el **sistema de widgets** (cartas
autónomas generadas por un agente headless, cada una con su propio `<style>` inyectado y colores hardcodeados)
también responda al tema, tanto los widgets ya existentes como los que se generen en el futuro por voz.

## Scope (entregado 2026-07-06)

- `frontend/app/styles.css` — paleta completa en variables CSS: `:root` (dark, default) +
  `:root[data-theme="light"]` (override). ~40 colores hardcodeados (fondos blancos, grises de texto, sombras)
  sustituidos por `var(...)`. Alias público `--hb-*` para que los widgets consuman el mismo contrato sin acoplarse
  a los nombres internos de la app.
- `frontend/app/core/store.js` — signal `theme` (`"dark"|"light"`, default `"dark"`), persistida en
  `localStorage.hb_theme` (mismo patrón que `micMuted`/`orbStyle`).
- `frontend/app/services/theme.js` (nuevo) — aplica `<html data-theme="…">` + `meta[name=theme-color]` vía un
  `createEffect`; `toggleTheme()`.
- `frontend/app/components/TopBar.js` — icono ☾/☀ nuevo junto a ⏰/⚙.
- `frontend/app/widgets/desktop.js` — el chrome de las ventanas (`hb-win`, `hb-grip`, `hb-x`, `hb-load`, `hb-cap`)
  pasa a `var(--hb-*, <fallback claro>)`.
- **Los 7 widgets existentes** (`clock`, `agenda`, `results`, `search`, `meteo-soria`,
  `meteo-tarragona-grafico`, `cluster-registro`) migrados a las variables `--hb-*` (incl. SVG `fill`/`stroke` en
  el gráfico de meteo-tarragona).
- `widgets/AGENTS.md` + `widgets/generator.py` (`_CONTRACT`) — el house style y el prompt del generador ahora
  EXIGEN el contrato `--hb-*` (con fallback hex) en vez de hex fijo, para que todo widget nuevo generado por el
  agente headless se adapte automáticamente a ambos temas.

## Bug encontrado durante la verificación

El comentario de cabecera de `styles.css` contenía literalmente `widgets/*/widget.js` — la secuencia `*/` cerraba
el comentario CSS a medias, y el navegador descartaba el bloque `:root` oscuro completo (`cssRules` confirmó 0
reglas para ese bloque). Efecto: la app seguía renderizando en blanco pese a `data-theme="dark"` correcto en el
DOM. Fix: reescribir la frase sin la secuencia `*/` literal. **Lección**: cualquier comentario CSS que mencione
un glob de ruta (`carpeta/*/archivo`) es una mina — evitar `*/` literal en comentarios `/* … */`.

## Verificación

`make test-widgets` (7/7 OK, contrato + golden shape + parse ES module intactos). Verificación visual con
Playwright (Chromium real) contra el servidor vivo: arranque en dark por defecto, toggle a light instantáneo,
modal ⚙ y panel ⏰ siguen el tema, dos widgets abiertos (`clock`, `agenda`) repintan de light→dark sin recargar
(pure CSS, cero JS), persistencia en `localStorage` tras reload, sin errores de consola.

## Follow-up (misma sesión, 2026-07-06) — bug de caché real + consolidación + evaluación de Tailwind

El operador reportó un widget ("Proyectos" = `results`) todavía en blanco/negro sin terminar de adaptarse. Causa
real: **`widgets/{wid}/widget.js` se servía sin `Cache-Control`** (`widgets/server_api.py`) — a diferencia de
`frontend/` (que sí manda `no-cache`, ver `server/__init__.py`), así que el navegador podía quedarse con una
copia vieja del módulo ES indefinidamente (el `import()` de `desktop.js` no lleva cache-busting en la carga
inicial). El fichero en disco ya estaba bien; el bug era de caché HTTP, no de cobertura. Fix: `Cache-Control:
no-cache` en esa ruta (fuerza revalidación, barato, mismo patrón que el resto del frontend). **Requiere reinicio
del servidor** (es una ruta Python, no un asset estático) — reiniciado con `make run-duo` (mismo `BRAIN` que
tenía la instancia previa) y verificado (`/api/brain` responde, `make test` OK).

El operador pidió además **estandarizar y simplificar al máximo** el sistema de estilos, ofreciendo Tailwind
como opción a mi criterio. Decisión: **NO Tailwind, seguir con CSS variables planas**:
- Introducir Tailwind exige o un build step (rompe la arquitectura documentada "no build, no npm" del frontend)
  o un CDN/JIT en navegador (dependencia de red en runtime — mal encaje para un asistente de voz local-first; y
  los widgets tienen la regla dura "self-contained, no CDN, no network" en `widgets/AGENTS.md`, validada
  estáticamente en `generator.py`).
- El problema real (tema dark/light) ya lo resuelve MEJOR una variable CSS que un framework de utilidades: un
  widget escribe `background:var(--hb-bg)` UNA vez y cambia solo; con Tailwind necesitaría un par
  `bg-white dark:bg-slate-900` en cada elemento, o togglear una clase `dark` — más código, no menos.
- En su lugar: **consolidado el namespace de variables a uno solo, `--hb-*`**, eliminando la capa de alias que
  había quedado del primer pase (antes había `--panel-bg`/`--muted`/`--ink`/… en la app + un alias `--hb-*` para
  widgets — dos nombres para lo mismo). Ahora la app y los widgets leen literalmente las mismas variables, un
  único sitio para razonar sobre la paleta (`frontend/app/styles.css`, cabecera del fichero).
- Añadido un **kit de clases opcionales `hbk-*`** (`hbk-card`, `hbk-hd`, `hbk-sub`, `hbk-muted`, `hbk-empty`,
  `hbk-chip`, `hbk-btn` — §WIDGET KIT en `styles.css`) para los patrones que se repetían literalmente en los 7
  widgets (cabecera título+subtítulo+timestamp, card, estado vacío, chip, botón). Documentado en
  `widgets/AGENTS.md` y mencionado en el prompt del generador (`widgets/generator.py`) — no obligatorio, un
  widget puede seguir siendo 100% CSS a medida si no encaja.
- **Repetí el MISMO bug del comentario `*/`** al escribir la nueva cabecera de `styles.css` (otra vez
  `widgets/*/widget.js` literal). Detectado y corregido de inmediato por la misma verificación con Playwright
  (cssRules a 0 para el bloque `:root` oscuro). Confirma que la verificación visual real (no solo
  `make test-widgets`) es la que atrapa esta clase de bug — el harness de widgets no toca `styles.css`.

Verificado de nuevo tras el fix: `make test-widgets` (7/7), 3 widgets abiertos a la vez (`results`, `clock`,
`agenda`) correctos en dark y light, sin errores de consola.
