---
id: INI-014
title: WhatsApp Triage Connector — leer, triar y marcar leído
status: done
owner: ricart
modules: [connectors, brains, voice]
updated: 2026-07-06
---

## Goal

Que zaelar **lea el WhatsApp personal del operador**, clasifique el flujo entrante y solo interrumpa con
**lo que merece atención** (por voz + UI), marcando como leídas las conversaciones ya resumidas. El brain
sigue siendo dueño de la decisión ("¿esto importa?"); el conector es el transporte + el motor de triaje.

Decisiones del operador (2026-07-06):
- **WhatsApp primero** (Telegram queda para una iniciativa aparte — ver §Fuera de alcance).
- **Leer + marcar leído** — SIN autorespondedor en esta iniciativa (diferido, §Fase 4).
- **Integración como `connectors/whatsapp/`** (patrón `connectors/architect/`), no como gateway nativo suelto:
  el triaje corre en el **agente Hermes compartido** (`brains/hermes/runtime.py`, serializado por `turn_lock`),
  y la entrega usa el circuito existente `voice/proactive` + notas `[SISTEMA]` (`voice/brain_notes`).

## Contexto: qué reutilizamos de Hermes (verificado en v0.17.0)

- **Bridge Baileys** de Hermes (`~/.hermes/hermes-agent/scripts/whatsapp-bridge/bridge.js`): proceso Node que se
  vincula por **QR** como dispositivo enlazado y recibe **todos** los mensajes entrantes (`messages.upsert`:
  DMs, grupos, media). Expone HTTP: `GET /messages` (long-poll), `POST /send`, `/send-media`, `/typing`,
  `/health`. Sesión persistente en `~/.hermes/whatsapp/session` (multiFileAuthState) → un solo QR, luego auto.
- Primitiva de silencio del gateway (`gateway/response_filters.py`, tokens `NO_REPLY`/`[SILENT]`) — referencia
  de diseño para "si no importa, calla".

**Frontera de propiedad y seguridad ante `hermes update`**: `hermes update` = `git pull` sobre
`~/.hermes/hermes-agent` + auto-stash de cambios locales → **jamás editamos ese árbol**. El bridge es un paquete
Node autónomo (`package.json` propio) → lo **vendorizamos** en `connectors/whatsapp/bridge/` con `VENDORED_FROM.md`
(commit upstream `190e1ffa`, Baileys pin `01047deb…`) y parches marcados `// ZAELAR-PATCH:`. Contrato completo,
patrón de re-vendoring y regla black-box/vendoring para futuros conectores en la doc canónica
**`.meshkore/docs/architecture/zaelar-hermes-federation.md`**.

Lo que Hermes **NO** trae y esta iniciativa aporta (candidato a upstream a la comunidad Hermes):
1. **Marcar como leído** — el bridge no llama a `sock.readMessages()` en ningún sitio. Hay que añadirlo.
2. **Modo triaje/observación** — el gateway es reactivo (mensaje→turno→respuesta). No existe un modo
   "observa el buzón, clasifica, entrega un digest y no respondas". Lo construimos.

## Arquitectura propuesta

```
WhatsApp ⇄ bridge.js (Baileys, modo "observe")   ← proceso Node, dueño de la sesión/QR
             │  GET /messages (long-poll)  POST /mark-read (NUEVO)
             ▼
connectors/whatsapp/client.py   ← HTTP al bridge (loopback), sin auto-send en esta INI
             │
connectors/whatsapp/triage.py   ← batching + clasificación vía runtime.ask (agente compartido)
             │        relevancia por chat → digest
             ├─▶ voice/proactive  (voz + UI: "3 cosas en WhatsApp que quizá quieras ver…")
             ├─▶ voice/brain_notes [SISTEMA]  (el brain sabe el desenlace real, no inventa)
             └─▶ POST /mark-read  (solo lo ya resumido)
```

- **`connectors/whatsapp/` (módulo nuevo — declarar en `cluster.yaml` antes de crear)**:
  - `bridge_proc.py` — lifecycle del bridge Node (arranque/paro/health, hash-check anti-bridge-obsoleto que ya
    trae el propio bridge), superficie del **QR** de emparejamiento en la UI de zaelar o terminal.
  - `client.py` — cliente HTTP loopback del bridge: poll de `/messages`, `POST /mark-read` (nuevo endpoint).
    **No llama a `/send`** en esta iniciativa (read-only + mark-read).
  - `triage.py` — ciclo: batch de mensajes → **clasificación con llamada DIRECTA al modelo local** (NO por
    `runtime.ask`; ver §Modelo del clasificador) → salida JSON `{relevante, dirigido_a_mí, urgencia, motivo}`
    con few-shot → score de relevancia por conversación → digest. Marca leído SOLO lo entregado en el digest.
  - `brief.py` — protocolo + estado vivo (nº de chats no leídos, último digest) inyectable al kickoff de voz.
  - `store.py` — cursor de "hasta dónde hemos triado" + dedupe (no re-resumir lo mismo), atómico, gitignored.
- **Parche al bridge** (`scripts/whatsapp-bridge/bridge.js`, upstreamable):
  - Nuevo `POST /mark-read` → `sock.readMessages([key])`.
  - Nuevo `--mode observe` (o `WHATSAPP_MODE=observe`): reenvía TODO lo entrante (no-`fromMe`) a `/messages`
    **sin** disparar respuesta ni prefijo, sin depender de allowlist. Mantiene `self-chat`/`bot` intactos.
- **Entrega**: mismo circuito que widgets/architect — proactive (voz recortada si es largo) + nota `[SISTEMA]`.
  El operador puede además preguntar por voz ("¿algo importante en WhatsApp?") → tag `[[wa.digest]]` (operator-only).
- **Cadencia**: digest bajo demanda + programado (reutiliza el cron nativo de Hermes, INI/`project_native_cron`):
  p.ej. resumen a las 9:00 y 18:00. Configurable.

## Fases

- **✅ Fase 0 — Parche bridge (HECHA 2026-07-06)**: bridge vendorizado en `connectors/whatsapp/bridge/`
  (`VENDORED_FROM.md`, commit `190e1ffa`), parches `// ZAELAR-PATCH:` para `POST /mark-read` y modo `observe`.
  `node --check` OK; boot verificado (escucha `:3111` mode observe, sirve `/health`, imprime QR). `npm install` OK.
- **🟡 Fase 1 — Transporte (CÓDIGO HECHO, falta pairing)**: `connectors/whatsapp/` = `config.py`, `client.py`
  (GET /messages, POST /mark-read), `bridge_proc.py` (lifecycle+QR), `triage.py` (clasificador), `run.py`
  (runnable standalone `python -m connectors.whatsapp`). **Clasificador VALIDADO** contra `qwen2.5:3b` local
  (6.6s/6 msgs, generaliza más allá del few-shot). **Pendiente**: escanear el QR una vez (paso del operador) para
  verlo sobre mensajes reales.
- **Fase 2 — Triaje + digest + mark-read**: ya implementado en `run.py` a nivel consola (score de relevancia,
  digest, mark-read de lo resumido). Falta afinar el umbral "merece atención" sobre tráfico real.
- **🟡 Fase 3 — Widget en el canvas + voz (CÓDIGO HECHO 2026-07-06, falta run+QR)**: WhatsApp es un **widget de
  primera clase** (`widgets/whatsapp/`, hand-built como agenda) respaldado por `connectors/whatsapp/service.py`
  (motor en el lifespan del server, gated `WA_ENABLED`, siempre-on) que ESCRIBE el store aislado
  `widgets/_data/whatsapp.json`; el widget solo lo LEE (`data.py`, stdlib, nunca lanza). El **QR se pinta EN EL
  CANVAS** (ZAELAR-PATCH #3: el bridge lo emite como data-URI; el widget lo muestra `<img>`). El desktop
  auto-refresca (`GET /widgets/whatsapp/data`) → QR y mensajes en vivo sin código extra. Lista **plana por
  urgencia**, lo dirigido a ti en **amarillo**; cuerpos = `textContent` (anti-XSS). Control por **voz**:
  `[[show:whatsapp]]` abre; `[[wa.read:N]]`/`[[wa.dismiss:N]]`/`[[wa.clear]]` (parseadas en `tag_protocol.py`,
  despachadas en los providers `hermes`/`duo` → `whatsapp.dispatch_tag` → `apply_action` → el motor drena
  `pending_read` al bridge). Botones ✓/✕/Limpiar en el widget hacen lo mismo. **Brief numerado** (`brief.py`)
  inyectado al kickoff de voz (`voice/engine/pipeline/agent.py`) y al system por-turno del duo
  (`brains/duo/prompt.py`) → el brain ve la lista numerada viva, así "descarta el 1 / lo de mi madre" mapea al
  `[[wa.read:N]]` correcto. **Aviso proactivo** (`service._announce`): al entrar algo urgente/dirigido a ti,
  voz por `voice/proactive` (throttle 45s) + nota `[SISTEMA]` (`voice/brain_notes`) siempre. **Verificado**:
  round-trip store↔widget (+fix del match por `n`), tags emitidas sin hablarse, architect+wa parsean juntos,
  imports sin ciclos, brief numerado, dispatch robusto. **Único pendiente**: `make run` con `WA_ENABLED=1`,
  decir "muéstrame WhatsApp", escanear el QR en el canvas y validar sobre mensajes reales (paso del operador).
- **Fase 4 — Autorespondedor (DIFERIDO, requiere go-ahead explícito)**: modo borrador → allowlist estricta →
  envío. Persona del operador (`~/.hermes/memories/USER.md`). NO en esta iniciativa.

## Arranque (unificado — sin piezas sueltas)

Todo arranca con **`make run`**. El motor WhatsApp está cableado en el **lifespan del server** (`server/__init__.py`,
gated `WA_ENABLED=1` en `.env`); ese motor **lanza el bridge Node como proceso hijo automáticamente** — no hay
comando aparte ni demonio suelto. Setup de una-vez: `make install-whatsapp` (deps del bridge; además el propio
`bridge_proc` **auto-instala** si faltan). El flag `WA_ENABLED` es config de `.env` (como `GEMINI_API_KEY`/
`ARCHITECT_TOKEN`), no un paso de arranque. Los widgets (estáticos) siempre se sirven; el widget `whatsapp`
aparece en el catálogo sin arrancar nada.

## Seguridad y privacidad (bloqueante — decidir antes de Fase 2)

- **Read-only + mark-read**: el conector NUNCA llama a `/send` en esta iniciativa. Sin ruta de escritura, sin
  injection que dispare un envío. Auto-respuesta = Fase 4 con su propio go-ahead.
- **Operator-only**: como architect, las tags (`[[wa.*]]`) quedan fuera de la allow-list del bridge de cluster
  → un peer no confiable jamás dispara un digest ni ve mensajes.
- **✅ Privacidad del clasificador (DECIDIDO 2026-07-06 — modelo local)**: el triaje NO mezcla nada personal
  con el modelo remoto. Ver §Modelo del clasificador. Solo si el operador pide profundizar/actuar (Fase 4) entra
  el brain remoto, con consentimiento explícito por acción.
- No commitear la sesión de WhatsApp ni el store (gitignored). Sección nueva en `zaelar-security.md`.

## Modelo del clasificador (decisión de arquitectura)

El brain de voz (agente Hermes compartido, `runtime.ask`) está **clavado a un solo modelo remoto** que cierra el
turno ACP (invariante: un razonador lo rompe → voz muda) y arrastra memoria/tools/persona. Meter el triaje ahí
usaría ese modelo remoto → tus mensajes saldrían fuera. Por eso:

- **El clasificador NO pasa por el agente Hermes.** Es una tarea *stateless* y estrecha ("¿importa? ¿va dirigido
  a mí?"), así que `triage.py` hace una **llamada directa al modelo local** vía el cliente OpenAI-compatible que
  zaelar ya tiene contra Ollama (`voice/engine/llm/providers/local.py`, `:11434/v1`).
- **Default local**: `qwen2.5:3b` (ya instalado; alternativa `gemma2:2b`). Nada personal sale de la máquina.
- **Fallback configurable** (`WA_TRIAGE_MODEL` / `WA_TRIAGE_PROVIDER` en `.env`): si el modelo local no da la
  talla en pruebas reales → cae a remoto (DeepSeek V4 Flash vía AIMLAPI). Es un knob del conector, no de Hermes.
- **Afinable**: prompt con few-shot sobre mensajes reales del operador; salida estructurada JSON. Iteramos.
- `deepseek-v3:latest` (404 GB) listado en Ollama es inviable de ejecutar aquí — no es candidato.

## Fuera de alcance (otras iniciativas)

- **Telegram personal**: Hermes solo trae **Bot API** (no userbot/MTProto/Telethon) → un bot no puede leer tus
  chats personales. Leer tu Telegram exige una capa **userbot (Telethon)** de cero, con matiz ToS. Iniciativa
  separada si el operador la quiere (INI-015 candidata).
- **WhatsApp Business Cloud** (`hermes whatsapp-cloud`): solo ve conversaciones contra un número business, no tu
  cuenta personal → no sirve para este objetivo.

## Decisiones a confirmar antes de arrancar

1. ~~Privacidad del clasificador~~ **RESUELTO**: modelo local (`qwen2.5:3b`), directo, con fallback remoto
   configurable. Ver §Modelo del clasificador.
2. **Coordinación con el gateway nativo**: si algún día corres `hermes gateway`, comparten `~/.hermes/whatsapp/`
   → una sola sesión Baileys. Definir quién es dueño (zaelar es el dueño en esta iniciativa).
3. **Alcance de "importa"**: ¿solo DMs, o también grupos? ¿allowlist de contactos VIP?
4. **¿Upstream?** El parche del bridge (`mark-read` + modo `observe`) es contribución limpia a la comunidad
   Hermes — decidir si se abre PR o se mantiene como fork local en zaelar.
