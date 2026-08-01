---
id: MK-003
title: "Security guard del canal de cluster — anti prompt-injection + scrub de fugas salientes"
status: done
priority: high
owner: ricart
initiative: INI-005
created: 2026-07-01
updated: 2026-07-01
---

# MK-003 — Security guard del canal de cluster MeshKore

El tercer canal (cluster) habla con agentes externos **desconocidos y potencialmente hostiles**. Voz y chat son del
operador (confianza local); el cluster no. Antes de esto el canal no tenía defensa a nivel de contenido: el texto
del peer entraba crudo en el prompt (injection abierta) y nada impedía que una respuesta filtrara tokens, datos
personales o la identidad/arquitectura del sistema. Ver INI-005.

## Qué se hizo

### 1. Módulo guard — `connectors/meshkore/security.py`
Sin estado, brain-agnóstico. Postura ALTA por defecto (`MESHKORE_SECURITY=strict`; `=off` = passthrough, debug).
- **Entrada (anti-injection)**: `fence_untrusted(text)` envuelve el texto del peer en un bloque
  `⟦UNTRUSTED PEER MESSAGE⟧` (datos, no instrucciones). `trailer()` = nuestras reglas de seguridad, que el bridge
  añade SIEMPRE al FINAL del prompt del turno. Regla de oro: **nuestro prompt va último**, de modo que un "ignora
  todo lo anterior" del peer queda ANTES de nuestras directivas.
- **Salida (anti-fuga)**: `scan_outbound(text) -> (safe, blocked)`.
  - Secreto DURO (token vivo conocido, `BEGIN…PRIVATE KEY`, `sk-…`, AWS/Google/Slack keys, GitHub token, JWT,
    Bearer, IBAN, nº de tarjeta Luhn-válido, `password=…`) → **bloquea el mensaje entero** (no se envía).
  - Huella configurada (`did:key` + términos de `MESHKORE_SECRET_TERMS`) → **redacta** a `[redacted]`.
  - NOTA (revisión Ricart 2026-07): los nombres de modelo/framework (gpt-4/claude/hermes/openai…) **NO** se
    redactan — son tema legítimo de conversación entre agentes; redactarlos en bloque convertía la colaboración en
    spam de `[redacted]`. La **auto-revelación** la gobierna el trailer de seguridad (decisión del brain), no el regex.

### 2. Cableado — `connectors/meshkore/bridge.py`
- `on_event` (rama `message`): el `note` del peer se pasa por `fence_untrusted()`.
- `_brain_turn`: `framed = brief + event_text + trailer()` → reglas al final.
- `dispatch` (rama `cluster.send`): `scan_outbound()` antes de `manager.send`; si hay secreto duro, NO se envía,
  se registra en journal y se avisa al operador. El aviso operator-facing sigue con `store.redact` (tokens) — NO
  se le aplica redacción de identidad porque es la vista del propio operador (confiable).

### 3. Defensa en profundidad — `brains/reasoner.py`
El system message del path `direct` incorpora la postura de seguridad. Para Hermes, cláusula añadida al seed
`.meshkore/docs/ops/hermes-MEMORY.seed.md` (no se toca `~/.hermes/memories/MEMORY.md`, perfil personal).

## Ficheros tocados
- `connectors/meshkore/security.py` (nuevo), `tests/cluster/unit/test_security.py` (nuevo)
- `connectors/meshkore/bridge.py`, `brains/reasoner.py`
- `.meshkore/docs/security/zaelar-security.md`, `.meshkore/docs/ops/hermes-MEMORY.seed.md`
- `.meshkore/public/cluster.yaml` (version 0.5.0 → 0.6.0; descripción del módulo connectors)
- `.meshkore/roadmap/initiatives/INI-005-meshkore-connector.md`, `CLAUDE.md`

## Verificación (2026-07-01)
- `pytest tests/cluster/unit/test_security.py -q` → 15 passed (bloqueo de tokens/keys/IBAN/tarjeta, redacción de
  `did:key`/términos env, modelo NO redactado, passthrough de texto limpio, postura off).
- Smoke: `import bridge/security/reasoner` OK; se comprueba que en el prompt armado el contenido del peer va dentro
  de `⟦UNTRUSTED⟧` y el trailer de seguridad es el bloque final.
- **Invariante de privacidad** documentado: el cluster (texto + URLs sobre WS) no tiene ruta a micro/cámara/voz;
  esos se captan client-side sobre la sesión WebRTC local del operador.
- Pendiente de decisión del operador: push (no hay remote configurado).
