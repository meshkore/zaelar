---
title: Zaelar Alignment Review
category: ops
updated: 2026-07-09
owner: ricart
status: current
---

# Workflow de revisión de alineación — "pasa la revisión de alineación"

**Disparador:** se ejecuta **al cerrar cualquier cambio que toque arquitectura, un módulo, un flujo o una
decisión/invariante** (una tarea de roadmap, un fix estructural, una pieza nueva del cerebro/memoria/bus), y bajo
demanda cuando el operador dice *"pasa la revisión de alineación"* / *"revisa que todo está alineado"*.

**Objetivo:** garantizar que, después del cambio, **código ↔ contexto ↔ docs canónicas ↔ diagramas HTML ↔ roadmap
↔ tests** cuentan LA MISMA historia — el estado ACTUAL, sin dirty code y sin legacy. Codifica el checklist para no
repetir las instrucciones cada vez. Es la **puerta de calidad** que se pasa al final de un cambio.

> Relación con los otros workflows: [[zaelar-change-protocol]] cierra **un** cambio (reiniciar→versión→commit);
> [[zaelar-docs-sync]] es el paso de coherencia docs↔estructura; [[zaelar-audit-workflow]] audita **todo** el
> sistema periódicamente. **Esta revisión es más estrecha y más frecuente**: se pasa tras CADA cambio de
> arquitectura/módulo y verifica alineación total, incluidos los **diagramas** y el **roadmap**.

---

## 0. ¿Aplica a mi cambio?

Aplica si el cambio hace CUALQUIERA de estas cosas:
- toca una **pieza del sistema** (voz, FlashBrain, SlowBrain, memoria, bus, widgets, conectores, server, config);
- cambia un **flujo** dibujado en los diagramas públicos de `/technology` (camino del turno, escalado, retrieval de memoria, refresco de widgets);
- añade/quita/renombra un **módulo, ruta, tag, env var, comando o decisión/invariante**;
- cambia **cómo funciona** algo que un doc canónico describe (aunque el layout no cambie).

Un cambio trivial dentro de un solo fichero sin efecto en flujo/contrato NO lo dispara (basta el commit).

---

## 1. Checklist de alineación (marca CADA casilla)

### A · Código y arranque
- [ ] El cambio está **limpio**: sin código muerto, sin ramas legacy, sin `# TODO`/comentarios "antes X ahora Y",
      sin imports/ficheros huérfanos. `grep` de los símbolos retirados = 0 hits fuera de la historia.
- [ ] Arranque limpio verificado: `curl -s localhost:43917/api/brain` responde; sin traceback en el log.
- [ ] Si tocaste `.py`, **reiniciaste** zaelar y lo comprobaste en vivo (no solo tests).

### B · Tests
- [ ] `./.venv/bin/pytest` de lo tocado en verde; sin regresión en la suite adyacente.
- [ ] Si el cambio tiene superficie observable, se **ejercitó de verdad** (tester INI-013 o prueba manual), no solo unit.

### C · Contexto (`CLAUDE.md`)
- [ ] La descripción del/los módulo(s) afectado(s) refleja **cómo funciona hoy** (no cómo funcionaba antes).
- [ ] Las **decisiones clave** afectadas están actualizadas; ninguna decisión retirada sigue redactada como vigente.
- [ ] Las **hard rules** siguen correctas. La tabla de docs canónicas no apunta a ficheros borrados.

### D · Docs canónicas (`.meshkore/docs/<categoría>/`)
- [ ] El doc de la categoría tocada (architecture / modules / product / ops / security / conventions / deploy) está al día.
- [ ] **Sin legacy**: nada de "de dónde venimos"/historia de arquitecturas anteriores en la doc VIVA (los informes
      fechados de auditoría son la excepción — son registro, no se reescriben).

### E · Diagramas públicos (`web/src/pages/technology/*.astro` + `web/src/lib/diagrams/*.ts`)
> **Actualizado 2026-07-26** (auditoría): el panel interno `frontend/pages/architecture.html` (ruta `/architecture`
> del motor) se **retiró el 2026-07-24** — ya no tiene sentido servir un panel con editor de modelos en vivo desde
> el propio motor. Los diagramas viven ahora como contenido PÚBLICO, curado y en inglés bajo `/technology`
> (`web/src/pages/technology/{architecture,flashbrain,brainworkers,memory,widgets}.astro` +
> `web/src/lib/diagrams/*.ts`), con rutas de código internas y detalle de incidentes/costes RECORTADOS a propósito
> (audiencia externa). **Ya NO es un espejo automático del código** — es una foto seleccionada a mano, y NINGÚN
> workflow la actualiza sola: es un paso MANUAL cuando tocas topología/modelo/proveedor de forma significativa.
- [ ] **`architecture.ts`/`.astro`** (diagrama total): nodos/aristas reflejan el flujo actual.
- [ ] **`memory.ts`/`.astro`**: el flujo de escritura/lectura de memoria (retriever, caché, consolidador) está al día.
- [ ] **`flashbrain.ts`/`.astro`**: el camino del turno, el escalado y el routing de modelos actual.
- [ ] **`brainworkers.ts`/`.astro`**: brain workers interactivos, dev-worker/permisos si el cambio los toca.
- [ ] **`widgets.ts`/`.astro`** (si aplica).
- [ ] **Modelos-en-uso** (capa rápida, code-agent, STT, TTS) + nota de **coste** (local/gratis vs API) correctos.
- [ ] Si tocaste `web/`: `cd web && npm run build` (falla si hay error de tipos/sintaxis) + deploy
      (`npx wrangler pages deploy dist --project-name=zaelar`) y reporta la URL estable `https://zaelar.pages.dev`.

### F · Roadmap (el estado ES la cola, lo sirve el daemon al Architect)
- [ ] Las tareas del cambio están en **`status: done`** en su `.md` fuente (`.meshkore/modules/<m>/tasks/T*.md`),
      con `completed_at` + `commit_shas`. El daemon auto-archiva la iniciativa cuando TODAS sus tareas están done.
- [ ] Línea fechada en la **## Bitácora** de la iniciativa. **No** se edita `state.json` a mano.
- [ ] Si el cambio no estaba en el roadmap, se abrió su iniciativa/tarea ANTES (visible en el Architect en vivo).

### G · Regla de oro
- [ ] **Contexto + docs + arquitectura (diagrama) cuentan lo mismo que el código.** Si algo aparece en uno, aparece
      en los tres. Si el operador viera `/technology` (web) o CLAUDE.md, no encontraría nada obsoleto.

---

## 2. Sondas rápidas (copia-pega)

```bash
# Legacy/dirty en la doc viva (debe salir solo lo VIGENTE, p.ej. seed_from_hermes.py):
grep -rinE "pipecat|hermes|BRAIN=duo| duo |razonador" CLAUDE.md .meshkore/docs web/src/pages/technology web/src/lib/diagrams
# Símbolos retirados por este cambio (rellena) → 0 hits en código vivo:
grep -rn "<símbolo_retirado>" --include=*.py . | grep -v .venv
# Diagramas web: build limpio (falla si hay error de tipos/sintaxis en los .ts/.astro tocados):
cd web && npm run build
# render real: abrir https://zaelar.pages.dev/technology/architecture (o el que toques) tras deployar
# Roadmap: tareas del cambio done + iniciativa al día (lo sirve el daemon):
grep -h "^status:" .meshkore/modules/*/tasks/T*.md | sort | uniq -c
```

---

## 3. Template de informe (pégalo en la Bitácora / respuesta)

```
### Revisión de alineación — <cambio> (<fecha>)
- Código/arranque: <ok · qué se limpió · verificación en vivo>
- Tests: <n passed · qué se ejercitó>
- CLAUDE.md: <módulos/decisiones tocados>
- Docs canónicas: <ficheros actualizados · legacy purgado>
- Diagramas HTML: <pestañas tocadas · modelos/coste · sello Actualizado>
- Roadmap: <tareas done · iniciativa · bitácora>
- Regla de oro: <código↔contexto↔arquitectura alineados: sí/no>
- Abiertas: <ninguna | lista>
```

Si CUALQUIER casilla queda sin marcar, el cambio **no está cerrado** — se arregla la desalineación antes de dar el
cambio por terminado.
