---
id: S-07
title: "S-07 · redactar el texto de peer inbound en la copia SSE/timeline (V6 media)"
status: done
priority: medium
owner: ricart
initiative: INI-007
created: 2026-07-03
updated: 2026-07-03
---

# S-07 — Redacción de peer inbound a SSE/timeline (INI-007 · V6)

## Vector

En `bridge.on_event` (message), el `_emit("cluster", …, text=text, …)` mandaba el texto del peer **crudo** a la
copia observable (observer → /debug + SSE a la UI + ficheros de timeline + journal). Un peer podía incluir un
valor con forma de secreto (o reflejar de vuelta uno de nuestros propios tokens) y quedaba persistido/streameado
sin redactar.

## Fix (`connectors/meshkore/bridge.py`)

- El `_emit` usa `store.redact(text)` (helper existente para strings con destino logs/timeline/SSE) → la copia
  operador-facing sale enmascarada. También se neutraliza el handle en el label/`peer` del emit (consistente con
  S-02).
- La copia que va al **brain** (`note` → `fence_untrusted`) sigue **cruda**: Hermes necesita el contenido real
  para colaborar y el fence + trailer gobiernan la confianza. La redacción es solo para la superficie de logs.

## Verificación (adversarial — rojo pre-fix, verde post-fix)

`test_security.py` (+1): un peer manda un GitHub token; se captura tanto el `_emit` como el prompt del brain →
el token NO aparece en la copia SSE (redactado) pero SÍ en el prompt del brain (crudo, fenced). Confirmado rojo
contra el código pre-fix. Suite: 38 passed. `make run-hermes` sano.
