---
id: S-05-06
title: "S-05/S-06 · plano de control meshkore — guard en /status + anti DNS-rebind por host exacto (V4/V5)"
status: done
priority: medium
owner: ricart
initiative: INI-007
created: 2026-07-03
updated: 2026-07-03
---

# S-05/S-06 — Guard del control-plane (INI-007 · V4/V5)

## Vectores

- **V4**: `GET /api/meshkore/status` no tenía `Depends(_guard)` → cualquier proceso local o una página en
  DNS-rebind podía leer clusters conectados, handles de peers y estado de engagement.
- **V5**: la defensa anti DNS-rebind de `_guard` comparaba el `Origin` por **substring**
  (`any(h in origin for h in (...))`) → `http://localhost.attacker.com` **contiene** "localhost" y pasaba.

## Fix (`connectors/meshkore/server_api.py`)

- `status()` ahora lleva `_=Depends(_guard)`.
- `_guard`: parsea el `Origin` con `urllib.parse.urlparse` y hace **exact-match** del hostname contra
  `{localhost, 127.0.0.1, ::1}` (antes substring). Sin cambios en la rama por token ni en la loopback-only.

## Verificación (adversarial — rojo pre-fix, verde post-fix)

`test_security.py` (+4): loopback simple pasa; `Origin: http://localhost.attacker.com` → `HTTPException`;
`http://localhost:8473` pasa; `status()` declara la dependencia `Depends(_guard)` (introspección de firma).
Confirmado rojo contra el código pre-fix. En vivo: `/api/meshkore/status` loopback → 200, con Origin de rebind
→ 403. Suite: 37 passed.
