---
id: S-03
title: "S-03 · escanear el campo media en salida al cluster (V3 alta — exfil por media[].url/b64)"
status: done
priority: high
owner: ricart
initiative: INI-007
created: 2026-07-03
updated: 2026-07-03
---

# S-03 — Escaneo de `media` de salida (INI-007 · V3)

## Vector

En `cluster.send` (`connectors/meshkore/bridge.py`) solo el `text` pasaba por `scan_outbound`; el `media` del
reply (`data.get("media")`) se reenviaba **sin escanear** → un secreto podía exfiltrarse por `media[].url` o por
un blob `media[].b64`, dejando el escaneo del texto puramente cosmético.

## Fix

- `security.scan_media_outbound(media) -> (media_segura, motivo_bloqueo)`: aplica la MISMA política que el texto a
  cada adjunto — escanea `url` y `mime` con `scan_outbound` (secreto duro → bloqueo del mensaje entero; identidad
  → redacción en sitio), y para `b64` lo escanea en crudo y también decodificado best-effort (secreto colado
  dentro del blob). Media malformada → bloqueo.
- `bridge.py cluster.send`: tras escanear el texto, escanea el media; si bloquea, registra en journal, avisa al
  operador y NO envía nada. Se manda `media` (ya redactada) en vez del crudo.

## Verificación (adversarial — rojo pre-fix, verde post-fix)

`test_security.py` (+4): secreto en `media[].url` → bloqueado; secreto dentro de `media[].b64` (base64) →
bloqueado; adjunto limpio → pasa intacto; media malformada → bloqueada. Confirmado rojo contra el código
pre-fix (helper inexistente). Suite: 33 passed. `make run-hermes` sano.
