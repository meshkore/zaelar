---
id: W-003
title: "W-2 · ciclo de vida completo por voz — [[delete:id]] + borrado del store privado"
status: done
priority: high
owner: ricart
initiative: INI-006
created: 2026-07-02
updated: 2026-07-02
---

# W-003 — Tag `[[delete:id]]` + limpieza del store (INI-006 · W-2)

## Qué se hizo

El ciclo de vida por voz tenía create/modify/show/close pero no **delete**: no había forma de retirar un widget
por voz, y aunque se borrase la carpeta a mano, su `widgets/_data/<id>.json` quedaba **huérfano** (rompía el
espíritu del invariante (b): el storage por widget vive y muere con su widget).

Cadena completa añadida:

1. **`voice/tag_protocol.py`** — `TAG_RE` acepta `delete` (self-closing, mismo formato que show/close); un
   `[[delete]]` sin id emite id vacío y no hace nada aguas abajo.
2. **`frontend/app/services/sse.js`** — `label === "delete"` → `desktop.deleteWidget(id)`.
3. **`frontend/app/widgets/desktop.js`** — `deleteWidget()`: cierra la tarjeta, `DELETE /widgets/{id}`, e
   invalida el catálogo cacheado (`_ids`/`_meta`). Respeta `_busy` (no borra bajo un agente que edita).
4. **`widgets/server_api.py`** — `DELETE /widgets/{wid}`: valida `_safe`, exige `manifest.json` (404 si no),
   `shutil.rmtree` off-loop + `store.delete(wid)`, y deja nota `[SISTEMA]` al brain ("ya no existe, no lo
   muestres"). El cache del catálogo se re-sincroniza solo (firma por mtime).
5. **`widgets/store.py`** — helper público `delete(widget_id)` (con lock).
6. **`widgets/brief.py`** — el TAG_PROTOCOL enseña `[[delete:ID]]` con la advertencia "PARA SIEMPRE, solo si el
   operador lo pide explícitamente".

## Verificación

- Test dirigido (scratchpad `test_w2.py`): el tag parsea entero, bare y partido entre chunks (sin hablar el
  tag); E2E contra el servidor vivo: widget desechable creado → `DELETE` → carpeta Y `_data/<id>.json`
  eliminados (`store_deleted: true`); widget inexistente → 404.
- `make run-hermes` sano tras el cambio.
