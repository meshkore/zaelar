---
title: Zaelar Widgets Change Workflow
category: ops
updated: 2026-07-09
owner: ricart
status: current
---

# Workflow de cambios en el sistema de widgets — "pasa el workflow de widgets"

**Disparador:** cuando el operador dice **"pasa el workflow de widgets"** (o "revisa el cambio de widgets", "cierra
el cambio de widgets"), o cuando TÚ mismo acabas de tocar algo estructural del sistema de widgets y vas a darlo por
cerrado — ejecuta esta checklist antes de decir que has terminado.

> **No todo cambio en `widgets/` la dispara.** Un comentario, un renombrado interno, un ajuste de estilo dentro de
> un widget concreto que no toca el contrato ni la arquitectura → **no hace falta este workflow**, sigue como
> siempre. Esto es para cambios **estructurales**: nuevo tag, nuevo campo de `manifest.json`, cambio de storage,
> cambio de quién puede mutar qué (SlowBrain/FlashBrain), cambio del mecanismo de refresco, cambio del gate de
> validación, o un nuevo "kind" de widget. Ver [[zaelar-modules]] §Widgets para el estado actual del sistema, y
> [[zaelar-change-protocol]] / [[zaelar-docs-sync]] para los protocolos generales de los que este es la
> especialización para `widgets/`.

---

## 0. ¿Aplica este workflow? (filtro de alcance)

Pregúntate: ¿este cambio altera algo que **cualquier widget, presente o futuro, tiene que respetar o puede usar**?
Si la respuesta es sí a cualquiera de estas, aplica el workflow completo:

- El contrato de `manifest.json` / `data.py` / `widget.js` (nuevo campo, nueva convención, `actions`, `usage`,
  `confirm`/`irreversible` — modo de ejecución de una acción, `widgets/actions.py`; `background`+`tick(ctx)` —
  ejecución off-screen con ciclo, `widgets/background.py`; `ref_index` — refs a items, `widgets/refs.py`; `kind`).
- El protocolo de tags (`voice/tag_protocol.py`) — tag nuevo, cambio de sintaxis, cambio de qué se escapa/retiene.
- El despacho cerebro↔widget (`voice/engine/llm/providers/nucleo.py`, `nucleo/flash/router.py`,
  `nucleo/dispatch.py`, `widgets/__init__.py`, `widgets/server_api.py`) — quién puede crear/modificar/borrar/
  entregar/mutar datos, y con qué condiciones.
- El modelo de almacenamiento (`widgets/store.py`) — formato en disco, ubicación, migración.
- El mecanismo de refresco (`frontend/app/widgets/desktop.js`, `frontend/app/services/sse.js`).
- El gate de validación del generador (`widgets/generator.py`).
- La casa de la documentación pública del sistema (diagrama `web/src/pages/technology/widgets.astro` +
  `web/src/lib/diagrams/widgets.ts` — retirado el panel interno `frontend/pages/architecture.html` el 2026-07-24,
  ver la nota de `CLAUDE.md` sobre el traslado; paso MANUAL, ningún workflow lo sincroniza solo — actualízalo solo
  si el cambio es significativo de cara a fuera, no para cada detalle interno — `widgets/AGENTS.md`,
  `zaelar-modules.md §Widgets`).

Si el cambio es solo dentro de UN widget concreto (su `data.py`/`widget.js`/`notes.md`) y no toca nada de lo
anterior, actualiza el `notes.md` de ESE widget (memoria por-widget, ver `widgets/AGENTS.md`) y para ahí — no hace
falta nada más de este documento.

## 1. Mapa de impacto — "si tocaste esto, actualiza aquello"

| Tocaste | Actualiza también |
|---|---|
| Tag nuevo o cambio de sintaxis (`tag_protocol.py`) | `widgets/brief.py` (`TAG_PROTOCOL`) · `nucleo/flash/prompt.py` si el FlashBrain debe conocerlo o quedar bloqueado de él · `zaelar-modules.md §Widgets` · diagrama público (`web/src/pages/technology/widgets.astro` + `.ts`, solo si es un cambio significativo de cara a fuera) |
| Campo nuevo en `manifest.json` (p.ej. `actions`, `safe`, `kind`) | `widgets/AGENTS.md` (contrato para quien edita a mano) · `widgets/generator.py` → `_CONTRACT`/`_CREATE_PROMPT`/`_MODIFY_PROMPT` (contrato para el agente de código) · `widgets/brief.py` si el cerebro debe leerlo |
| Modelo de storage (`widgets/store.py`) | migración **perezosa y automática**, nunca script manual ni pérdida de datos (mismo patrón que la migración `_v` de esquema) · `widgets/AGENTS.md` · `_CONTRACT` del generador · doc + diagrama |
| Gobernanza cerebro↔widget (quién muta qué) | `voice/engine/llm/providers/nucleo.py` + `nucleo/flash/router.py` (despacho + declaración de tools `escalate_to_slowbrain`/`set_style_directive`) · `nucleo/dispatch.py` (SlowBrain) · `nucleo/flash/prompt.py` · `widgets/brief.py` · doc + diagrama |
| Mecanismo de refresco (SSE/poll) | `desktop.js` · `sse.js` · `widgets/AGENTS.md` (regla "sin polling") · doc + diagrama |
| Gate de validación (`generator.py`) | correr `make test-widgets` contra TODOS los widgets existentes antes de dar el cambio por bueno |
| Nuevo "kind" o capacidad estructural (p.ej. widgets "backed") | diseño completo por escrito en `zaelar-modules.md` ANTES de tocar código real · entrada en `CLAUDE.md` · no construir el mecanismo genérico sin un consumidor real que lo valide (ver la discusión de widgets "backed" del 2026-07-07) |

## 2. Repasa el impacto en los widgets que YA existen

- Si tocaste algo que usan TODOS los widgets (contrato, store, gate de validación): corre `make test-widgets` y
  confirma 0 fallos antes de continuar. Si algo falla, arréglalo — un cambio estructural nunca puede dejar un
  widget existente roto.
- Decide, widget por widget, si le corresponde adoptar la nueva capacidad (p.ej. ¿debería `mensajeria` declarar
  `"safe"` en alguna acción ahora que existe el nivel?). No hace falta migrar todos a la vez — pero si decides NO
  migrar uno todavía, anótalo en su `notes.md` para que quede trazado y no se re-discuta desde cero la próxima vez.
- Si cambiaste el formato en disco (`widgets/store.py`), verifica la migración contra datos REALES de al menos un
  widget existente (no solo un widget de prueba vacío) antes de darlo por bueno.

## 3. Documenta — la regla de oro es SIEMPRE tres sitios, nunca dos de tres

Mismo principio que `zaelar-docs-sync.md`: que aparezca en **contexto (CLAUDE.md) + doc canónica
(`zaelar-modules.md`) + el diagrama público** (si el cambio es significativo de cara a fuera). Para widgets, en
concreto:

- **`.meshkore/docs/modules/zaelar-modules.md` §Widgets** — la fuente canónica, el detalle completo. Si el cambio
  es grande, puede merecer su propia sub-sección (como "Widget-apps ('backed' widgets)").
- **`CLAUDE.md`** — un bullet CONCISO en "Decisiones clave" que apunte al detalle de arriba. Nunca dupliques el
  detalle aquí, solo la decisión + una frase de por qué + dónde está el resto.
- **`web/src/pages/technology/widgets.astro` + `web/src/lib/diagrams/widgets.ts` — EL DIAGRAMA Y LA TEORÍA, LOS
  DOS.** (Antes `frontend/pages/architecture.html` → pestaña Widgets, retirado el 2026-07-24 — el mismo riesgo de
  "actualicé la teoría y olvidé el SVG" aplica igual aquí, ahora en TypeScript en vez de HTML embebido). Es fácil
  actualizar solo la prosa del `.astro` y olvidar los nodos del `build()` en el `.ts` (pasó de verdad el
  2026-07-07 con el archivo viejo). Repasa `build()` **nodo por nodo** — títulos, sub-líneas, y las rutas/etiquetas
  de las flechas que referencien lo que cambiaste — no solo la prosa de arriba. Si el cambio añade una pieza nueva
  al circuito (una carpeta, un tag, un nivel de gobernanza), esa pieza necesita SU PROPIO grupo/caja en el SVG, no
  solo una mención en prosa. Esto es de cara a EXTERNOS (recortado a propósito, sin rutas de fichero internas) —
  no lo dispares por cada detalle interno, solo cambios de topología/flujo que un self-hoster/visitante vería.
- Si cambia el vocabulario de tags o el contrato que ve el cerebro: **`widgets/brief.py`** + el prompt del
  FlashBrain (**`nucleo/flash/prompt.py`**). La persona/instrucciones vivas ya no son un fichero externo: se
  inyectan en cada conexión desde `memory/` + `nucleo/flash/prompt.py`, así que no hay copia personal del operador
  que tocar aquí.
- Si cambia el contrato que ve el agente de código (Claude Code): **`widgets/AGENTS.md`** +
  **`widgets/generator.py`** (`_CONTRACT`/`_CREATE_PROMPT`/`_MODIFY_PROMPT`).

## 4. Prueba — no solo revisión de código

- `make test` (imports/salud) y `make test-widgets` (contrato + golden + parseo ES module de CADA widget) — los
  dos en verde antes de continuar.
- Si el cambio toca despacho/gobernanza cerebro↔widget: pruébalo **en vivo** contra el sistema real (no solo
  lectura de código) — p.ej. invocando `nucleo.flash.fast_client.FastClient()` (FlashBrain) y `nucleo.dispatch`
  (SlowBrain) directamente para confirmar que ambas velocidades se comportan como se espera con el prompt/brief
  nuevos, y que `escalate_to_slowbrain` escala lo que debe. Limpia cualquier dato de prueba que quede en los stores
  reales al terminar (no dejes "Reunión de prueba" en la agenda del operador).
- Si tocaste `web/src/lib/diagrams/widgets.ts` o `web/src/pages/technology/widgets.astro`: `cd web && npm run
  build` (falla en error de tipos/sintaxis) y, si tocaste la geometría del SVG, valida a ojo en el navegador
  (ninguna caja se sale de su grupo, el texto cabe en la altura de la caja según su número de líneas, ninguna
  etiqueta de flecha se sale del canvas) antes de deployar.

## 5. Reinicia (si hace falta)

- ¿Tocaste algún `.py`? → **sí** hace falta reiniciar el servidor (no hay hot-reload; `make run` = `BRAIN=nucleo`,
  el cerebro por defecto — compruébalo con `GET /api/brain` ANTES de matar el proceso, para relanzar exactamente
  igual).
- ¿Tocaste solo un widget (`.js`/`.css` de frontend, o el diagrama en `web/`)? → **no** hace falta reiniciar el
  motor — el frontend se sirve con `Cache-Control: no-store` (recargar la página basta) y `web/` es un sitio
  aparte que se deploya independientemente (`cd web && npm run build && npx wrangler pages deploy dist
  --project-name=zaelar`).
- Para reiniciar: identifica el árbol de procesos (`livekit-server` + `python -m server`, ambos hijos del
  `bash scripts/run-livekit.sh`), `SIGTERM` primero; si no responde en unos segundos (ha pasado), `SIGKILL`. Tras
  un `SIGKILL`, revisa procesos huérfanos que puedan haber quedado colgados de un hijo (p.ej. el bridge de
  WhatsApp en el puerto 3111) — si no se limpian, el siguiente arranque choca con el puerto ocupado.
- Verifica después: `GET /`, `GET /api/brain`, `GET /widgets` (catálogo correcto, campos nuevos presentes si
  tocaste el manifest), y cualquier endpoint específico del cambio.

## 6. Commit / push — regla dura, se repite aquí porque es fácil olvidarla en medio de un cambio grande

- **NUNCA** commitear sin que el operador lo pida explícitamente, aunque el workflow esté "cerrado" en todo lo demás.
- **NUNCA** hacer push sin confirmación explícita, ni aunque haya remote configurado.
- Cuando el operador SÍ pida commitear: agrupa los ficheros tocados por categoría en el mensaje (código ·
  contrato del generador · docs canónicas · arquitectura pública) para que el commit quede trazable como el
  cambio estructural que es, no como un totum revolutum.

## Resumen para el operador (al terminar)

Cuando termines de pasar este workflow, responde SIEMPRE con:
- Qué cambió, en 2-3 frases (arquitectura/contrato/gobernanza — no una lista de ficheros).
- Qué actualizaste (lista corta: contrato del generador, brief, docs canónicas, diagrama+teoría de arquitectura).
- Qué probaste (`make test`/`test-widgets`, y si hubo prueba en vivo, contra qué).
- Si reiniciaste o no, y por qué.
- Qué queda pendiente (diseño sin construir, migración de un widget concreto no hecha todavía, algo que el
  operador tiene que re-hacer a mano como re-escanear un QR).
- Recuerda que el commit/push sigue pendiente de que el operador lo pida — no lo des por hecho.
