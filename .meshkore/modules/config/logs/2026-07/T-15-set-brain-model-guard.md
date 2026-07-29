---
id: T-15
title: "T-15 · set_brain_model: gate a brain hermes + validación de charset del id de modelo"
status: done
priority: high
owner: ricart
initiative: INI-006
created: 2026-07-02
updated: 2026-07-02
---

# T-15 — `set_brain_model` gate + sanitización (INI-006 · A3)

## Qué se hizo

`config/settings.py set_brain_model()` escribía `model.default` en `~/.hermes/config.yaml` (1) aunque el brain
activo fuese `direct` (una feature de un brain concreto no puede cablearse incondicionalmente — decisión clave
de CLAUDE.md), y (2) interpolando el id de modelo tal cual en el YAML: una comilla o un salto de línea desde el
campo free-text del ⚙ (`/api/settings`) corrompía la config de Hermes.

Fix:

- **Gate**: `active_brain() != "hermes"` → no-op con warning (un run `direct` jamás toca la config de Hermes).
- **Charset**: `^[A-Za-z0-9][A-Za-z0-9._/:-]{0,127}$` (ids tipo `deepseek/deepseek-v4-flash`, `gpt-4.1`) antes
  de interpolar; inválido → no se escribe.
- `update()` coacciona `brain_model` a str antes de `.strip()` (un payload no-string lanzaba AttributeError).

## Ficheros tocados

- `config/settings.py` — `_MODEL_ID_RE`, gate + validación en `set_brain_model()`, coerción en `update()`.

## Verificación

- Test dirigido (scratchpad `test_t15.py`, con `HERMES_HOME` y `SETTINGS_FILE` en temporales): con
  `BRAIN=direct` no escribe; ids con comillas/saltos/espacios/overlong rechazados con el YAML intacto; id válido
  escribe exactamente la línea `default:` (resto del YAML intacto); payload no-string no lanza.
- `make test` OK.
