---
id: S-01-02
title: "S-01/S-02 · neutralizar identity strings de peer antes de todo prompt (V1 crítica / V2 alta)"
status: done
priority: critical
owner: ricart
initiative: INI-007
created: 2026-07-03
updated: 2026-07-03
---

# S-01/S-02 — Fence de handles de peer hacia los prompts (INI-007 · V1/V2)

## Vector

Los strings de **identidad** elegidos por peers no confiables (handles, nombres de cluster, presencia) NO son
mensajes libres (esos ya iban dentro del fence `⟦UNTRUSTED PEER MESSAGE⟧`): se interpolaban CRUDOS en prompts,
FUERA del fence, junto a instrucciones de confianza —

- **V1 (crítica)**: `connectors/meshkore/brief.py` metía `c['online']` (+ `c['name']`) en el kickoff de voz
  (`voice/agent.py`), que corre con **tools auto-aprobadas** → un handle diseñado podía forjar un fence-close +
  un trailer `[SECURITY]` falso dentro del contexto de confianza (bypass del tool-gate).
- **V2 (alta)**: `connectors/meshkore/bridge.py` metía `frm`/`ag`/`online` en las etiquetas de los turnos de
  cluster, también fuera del fence.

## Fix

- `connectors/meshkore/security.py`: nuevo helper público **`neutralize_identity(s, max_len=64)`** — reutiliza el
  `_neutralize` existente (borra los centinelas `⟦⟧`, `[SECURITY`, `UNTRUSTED PEER MESSAGE`), colapsa
  espacios/saltos y trunca. Siempre activo (una identidad siempre es no confiable).
- `brief.py`: neutraliza nombre de cluster y cada handle online antes de renderizar el snapshot.
- `bridge.py`: neutraliza `frm` (label del mensaje), `ag` (presencia) y cada `online` (ready) antes de
  interpolarlos en el prompt del brain. El texto del peer sigue yendo por `fence_untrusted()`.

## Verificación (adversarial — rojo pre-fix, verde post-fix)

`connectors/meshkore/test_security.py` (+5 tests): `neutralize_identity` borra fence/trailer forjados y clampa
longitud/saltos; `brief.for_brain()` no deja `⟦`/`UNTRUSTED`/`[SECURITY` en el snapshot con un handle malicioso;
las etiquetas de `on_event` (message/ready) neutralizan el handle antes del prompt. Confirmado que los tests de
brief y bridge FALLAN contra el código pre-fix. Suite completo: 29 passed. `make run-hermes` sano.
