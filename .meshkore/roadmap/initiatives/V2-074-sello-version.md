# V2-074 — Sello de versión (instancia + observabilidad + frontend)

**Estado:** F0 CONSTRUIDO (rama `feat/v2-069-una-sola-mente`, commit engine `a8ac509`). 2026-07-26.

## Origen

Necesidad del operador tras varios reinicios con código nuevo: **saber sin ambigüedad qué versión corre en una
instancia y qué versión generó cada línea de la observabilidad** (líneas de tiempo de sesiones, para confirmar que
las versiones realmente se actualizaron). Detonante concreto: no había forma de verificar que el reinicio había
cargado el código nuevo — la duda paralizaba la validación.

## Qué hace

`version.py`: `VERSION` semántica (se sube a mano en cambios notables) + **SHA corto de git** (cambia por commit) +
epoch de arranque del proceso; todo cacheado. `short()` → `"2.74+<sha>"`. Se sella en TRES sitios:

1. **Instancia** — item `version` en `/api/status` (`short` + uptime + `extra` con el detalle). Con esto, `sha` de
   `/api/status` == `git rev-parse --short HEAD` **prueba** que el reinicio cargó lo nuevo (si no coincide, no lo hizo).
2. **Observabilidad** — `voice/observer.emit` añade `ver` a **CADA** evento del timeline (`timeline-latest.jsonl` +
   sesiones + SSE) → cada línea dice qué versión la produjo; se distinguen sesiones/reinicios de un vistazo.
3. **Frontend** — el `StatusPanel` (◉) pinta los items de `/api/status` de forma genérica → la Versión aparece sola,
   sin tocar el frontend.

## Uso / operativa

- **Verificar un reinicio:** `curl /api/status` → el `version.sha` debe ser el `HEAD` actual.
- **Subir la versión:** editar `VERSION` en `version.py` al cerrar un bloque notable (el SHA se mueve solo por commit).
- Coste: `ver` es una constante en runtime (µs); ~10 bytes por línea de timeline.

## Testing

`tests/infrastructure/unit/test_version.py` (3): forma de `info()`, estabilidad de `short()`, y que el observer sella `ver` en cada
evento. **Nodo 7.5** del mapa de tests.

## Nota adjunta — fix del criterio de ritmo (V2-073)

En la misma sesión, al validar V2-073 en vivo se detectó que `capsule` de zalo tenía `no_progress=0` pese al bucle:
un peer embuclado intercala mensajes pseudo-sustantivos que puntúan como «avanza» y **reseteaban** el contador a 0 →
en un bucle MIXTO nunca alcanzaba el umbral y seguíamos respondiendo. **Fix:** en `bridge.py`, al avanzar el peer el
`no_progress` **DECAE −1** (no se resetea) y solo se sale de la pausa cuando vuelve a 0 → el no-progreso sostenido se
acumula igual. Verificado en vivo: `no_progress` empezó a subir (0→1→…) tras el reinicio.

## Fases

- **F0 (hecho):** version.py + sello en instancia/observabilidad/frontend + test + fix del criterio de ritmo.
- **F1 (abierto):** badge de versión SIEMPRE visible en el TopBar (no solo en ◉); versión también en el visor de
  Trazas/debug como filtro; incluir `built_at`/rama; versión en la web pública si procede.
