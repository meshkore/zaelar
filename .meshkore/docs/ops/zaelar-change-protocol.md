---
title: Zaelar Change Protocol
category: ops
updated: 2026-07-09
owner: ricart
status: current
---

# Protocolo de cambio de zaelar — "pasa el protocolo"

**Disparador:** cuando el operador dice **"pasa el protocolo"** (o "ejecuta el protocolo", "cierra el
cambio"), el agente ejecuta ESTA checklist de principio a fin para el cambio recién hecho. El objetivo es no
tener que recordar cada vez qué hay que hacer al cerrar un cambio mayor.

> Alcance: aplica a **cambios mayores** (feature nueva, fix sistémico, cambio de estructura/decisión).
> Para un typo o un ajuste trivial basta con commit; el operador dirá si quiere el protocolo completo.

---

## Checklist (en orden)

### 1. Reiniciar el sistema y verificar salud
- `make run` (= `BRAIN=nucleo`, el cerebro por defecto) tras matar la instancia previa en `:43917`.
- Verificar: `curl -sf localhost:43917/api/brain` responde, y el log muestra el arranque del cerebro sin errores.
- El cambio debe estar **cargado y corriendo** antes de darlo por bueno.

### 2. Verificar el cambio
- Correr la verificación que aplique: `make test`, `make smoke`, o un repro dirigido contra el binario real
  (p. ej. el harness de barge-in). **No** se cierra un cambio sin evidencia de que hace lo que dice.
- Si toca la voz: recordar que **la voz de entrada/salida es solo la interfaz** — la conversación del brain
  debe seguir siendo coherente y bidireccional. Ver [[bug-bargein-mute]] / decisiones clave en `CLAUDE.md`.

### 3. Subir la versión (semver)
- Versión de producto en `.meshkore/public/cluster.yaml` → campo `version:`.
- `fix` → PATCH · `feat` → MINOR · ruptura/estructura → MAJOR (mientras <1.0, MINOR para features).
- Etiquetar el commit: `git tag vX.Y.Z`.

### 4. Documentar en el estándar MeshKore
- **Diario de actuaciones** (obligatorio): una entrada por módulo tocado en
  `.meshkore/modules/<módulo>/logs/<YYYY-MM>/<ID>-<slug>.md` con frontmatter
  (`id, title, status, priority, owner, initiative, created, updated`) + cuerpo
  (Qué se hizo · Ficheros tocados · Verificación).
- **Iniciativa**: anclar la tarea a una iniciativa de `.meshkore/roadmap/initiatives/`. Si es trabajo nuevo,
  crear `INI-00N-<slug>.md`. Actualizar `status`/`updated` de la iniciativa afectada.
- **NO** editar `.meshkore/roadmap/state.json` a mano (artefacto generado por el daemon).
- **Contexto canónico** (`.meshkore/docs/<categoría>/`): actualizar SOLO si el cambio introdujo
  decisiones, criterios, settings o cambios de estructura. Categorías: architecture, product, deploy, ops,
  conventions, modules, security. Si es un módulo nuevo, declararlo en `cluster.yaml`.
- **`CLAUDE.md`**: añadir a "Decisiones clave" cualquier decisión o invariante nuevo que deba sobrevivir.
- **Memoria**: guardar como `feedback`/`project` lo no obvio (síntoma→causa→invariante) para no repetir el error.

### 5. Commit
- Mensaje descriptivo (`feat:`/`fix:`/`refactor:`/`docs:` …), cuerpo explicando el porqué.
- Incluir código **y** documentación en el mismo cierre de cambio (el diario y la iniciativa van commiteados).
- Cerrar con la línea `Co-Authored-By: Claude ...`.

### 6. Push (requiere confirmación del operador)
- Regla dura: `require_operator_approval_for_push` (cluster.yaml). No hay push sin OK explícito.
- Remote configurado: `origin` (github.com:meshkore/zaelar). Con OK del operador: `git push origin main --tags`.

### 7. Deploy (condicional — cuesta dinero)
- **Estado actual: sin prod.** Las apps de Fly.io fueron destruidas por ahorro de costes (2026-06-30, ver
  `zaelar-deploy.md`). Este paso se **omite por defecto**.
- Solo re-provisionar prod con go-ahead explícito del operador (implica coste). Manifiestos listos:
  `Dockerfile` + `fly.toml`. Comando: ver `.meshkore/docs/deploy/zaelar-deploy.md`.

---

## Resumen para el operador (al terminar)
Reportar en una línea por ítem: qué se hizo, qué se verificó, qué versión, qué se documentó, y qué quedó
**pendiente de tu decisión** (típicamente: push si no hay remote, deploy si no hay prod).
