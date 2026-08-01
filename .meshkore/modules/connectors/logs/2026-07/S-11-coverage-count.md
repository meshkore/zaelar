---
id: S-11
title: "S-11 · cobertura de bordes (secreto multi-línea, huella did:key) + recuento de tests"
status: done
priority: low
owner: ricart
initiative: INI-007
created: 2026-07-03
updated: 2026-07-03
---

# S-11 — Cobertura + recuento (INI-007)

## Qué se hizo

Tests de borde del regex "single-line" y actualización del recuento documentado.

- **Gap real encontrado y arreglado**: `scan_outbound` redactaba solo el prefijo literal `"did:key"`, dejando la
  huella multibase (`z6Mkha…`) — que ES el identificador — en el mensaje. `connectors/meshkore/security.py`
  `_identity_re()` ahora redacta la **huella completa** (`\bdid:key:z[1-9A-HJ-NP-Za-km-z]{20,}\b`, igual que
  `store.redact`); los términos de `MESHKORE_SECRET_TERMS` siguen literales.
- Cobertura añadida: secreto (private key / sk-) embebido en texto multi-línea → bloqueo; secreto en una línea
  posterior → bloqueo; did:key en medio de texto multi-línea → huella redactada entera.
- Actualizado el test viejo `test_redacts_did_key_fingerprint` a una huella de longitud realista (la anterior,
  `z6Mkabc123`, dependía de la redacción por prefijo que era el bug).
- **Recuento**: `zaelar-security.md` y el informe `harbee-audit-2026-07-02.md` pasan de **24 → 51** tests, con
  nota de que cada fix de INI-007 lleva su test adversarial (rojo pre-fix / verde post-fix) y del test XSS de
  agenda en `tests/browser/unit/agenda/test_xss.mjs`.

## Verificación

Suite completo `tests/cluster/unit/test_security.py`: **51 passed**. `make test-widgets`: 7/7. Los tests de
did:key (incluido el existente) FALLAN contra el código pre-fix (huella filtrada). `make run-hermes` sano.
