---
id: T-19
title: "T-19 · bugs menores: path .env, /api/doc muerto, TURN fetch en import, zombie en cron"
status: done
priority: medium
owner: ricart
initiative: INI-006
created: 2026-07-02
updated: 2026-07-02
---

# T-19 — Bugs menores A6/A7/A8 (INI-006)

## Qué se hizo

1. **`voice/llm.py` path del `.env`** — `PROTO = dirname(dirname(HERE))` apuntaba al PADRE del repo
   (`asimovia/.env`, resto de la era "prototype"): `load_key()` solo funcionaba por el fallback de
   `os.environ`. Ahora `ROOT = dirname(HERE)` = raíz del repo.
2. **`/api/doc/{name}` borrado** (`server/pages.py`) — servía markdown desde `docs/`, carpeta que ya no existe
   (la doc vive en `.meshkore/docs/`, dentro del repo, no servida por HTTP). Su único caller (pestaña Context de
   `frontend/pages/architecture.html`) ahora muestra un puntero estático a `.meshkore/docs/` (la pestaña se
   remata en T-21).
3. **TURN fetch fuera del import** (`server/voice_api.py`) — `SmallWebRTCRequestHandler` se construía a nivel de
   módulo y con `CF_TURN_*` configurado eso es un fetch de red de hasta 8s **durante el import** (congelaba el
   arranque en prod). Ahora es un singleton perezoso (`_get_handler()`, con lock) construido en el primer
   `/api/offer` vía `asyncio.to_thread` (el fetch tampoco bloquea el loop).
4. **Zombie en `brains/hermes/cron.py`** — en el timeout de `_run()` se hacía `proc.kill()` sin `await
   proc.wait()`: el hijo matado quedaba zombie. Añadido el `wait()` (reap determinista).

## Ficheros tocados

- `voice/llm.py` · `server/pages.py` · `frontend/pages/architecture.html` · `server/voice_api.py` ·
  `brains/hermes/cron.py`

## Verificación

- Test dirigido (scratchpad `test_t19.py`): `load_key()` encuentra la key en `zaelar/.env`; el handler WebRTC
  no existe tras el import y es singleton bajo demanda; `_run()` con timeout mata Y reapea al hijo
  (`waitpid(WNOHANG)` no encuentra zombies).
- Servidor reiniciado: `/api/doc/CONTEXT` → 404, `/architecture` → 200, `/api/ice-servers` OK (STUN local),
  `/api/brain` → hermes, 0 errores en log.
