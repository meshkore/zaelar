---
title: Zaelar Docs & Structure Sync
category: ops
updated: 2026-07-02
owner: ricart
status: current
---

# Workflow de sincronización de docs y estructura — "sincroniza la documentación"

**Disparador:** se ejecuta **automáticamente** siempre que un cambio toca la **estructura** del proyecto o la
**documentación/contexto** — y bajo demanda cuando el operador dice *"sincroniza la documentación"* / *"pasa la
sync de docs"*. El objetivo: que la documentación, el contexto (CLAUDE.md), la arquitectura (incluido su diagrama)
y lo que lee quien clona el repo (README) **nunca se queden atrás** del código. Codifica las instrucciones que el
operador repite una y otra vez, para no tener que darlas cada vez.

> Complementa a [[zaelar-change-protocol]] (que cierra **un** cambio) y a [[zaelar-audit-workflow]] (que audita
> **todo** el sistema). Este es el paso de **coherencia docs↔estructura** que va DENTRO del change protocol
> (su paso 4) y también puede correrse suelto.

---

## 0. Cuándo aplica (¿mi cambio toca estructura o docs?)

Aplica si el cambio hace CUALQUIERA de estas cosas:
- añade/renombra/mueve un **módulo o carpeta**, o cambia el layout de la raíz;
- añade una **dependencia o paso de instalación** (algo que alguien tendría que instalar/configurar);
- introduce una **decisión, invariante, política de seguridad o setting** nuevo;
- cambia un **flujo** que ya está dibujado en un diagrama o descrito en un doc canónico;
- añade/quita una **ruta, endpoint, env var o comando** relevante.

Si NO toca nada de esto (p. ej. un fix interno sin efecto observable), este workflow no es necesario.

## 1. Principio rector: multi-plataforma, sin casarse con nadie

zaelar debe poder correr en **macOS, Windows y Linux**. Al documentar instalación o comandos:
- da el comando **por-OS** cuando difiere (p. ej. `make install-stt` en mac vs `scripts/*.ps1` en Windows);
- no asumas `brew`/`apt`/`bash` como universales — indícalo como específico de OS y ofrece la alternativa;
- providers (STT/TTS/brain) son **intercambiables** por env/config: nunca hardcodear un vendedor en la doc.

## 2. Checklist de sincronización (marca todo lo que aplique)

| Si el cambio… | Actualiza |
|---|---|
| añade/quita/mueve un módulo o carpeta | `.meshkore/public/cluster.yaml` (módulos) · `CLAUDE.md` (§Módulos/layout) · `.meshkore/docs/modules/zaelar-modules.md` · el **diagrama** en `.meshkore/docs/architecture/zaelar-architecture.md` |
| añade una dependencia o paso de instalación | **`README.md`** (raíz, por-OS) · `.meshkore/docs/ops/zaelar-ops.md` (§Prerequisites + la sección relevante) |
| introduce una decisión/invariante | `CLAUDE.md` §"Decisiones clave" · el doc de categoría que corresponda (architecture/product/security/…) |
| toca seguridad (canal cluster, permisos, secretos) | `.meshkore/docs/security/zaelar-security.md` · la subsección de fronteras de confianza del `zaelar-architecture.md` · `CLAUDE.md` |
| cambia un flujo ya dibujado | el **diagrama ASCII** correspondiente en `zaelar-architecture.md` (no dejar el dibujo obsoleto) |
| añade ruta/endpoint/env/comando | el doc que lo describa (ops/architecture) · `config/.env.example` si es una env var |
| cambia estructura, comandos, suites, catálogo o protocolo de testing | `tests/README.md` · `.meshkore/docs/ops/zaelar-testing.md` · `tests/TESTMAP.md`/`tests/platform/SCHEMA.md` según corresponda · `CLAUDE.md` y `AGENTS.md` si cambia lo que deben hacer los agentes |
| **toca el catálogo de TOOLS del FlashBrain** (`nucleo/flash/router.py::TOOLS`: añade/quita/renombra una tool, cambia su descripción o su gating) | la **doc canónica `zaelar-architecture.md §8`** (única fuente) · el diagrama público `web/src/pages/technology/flashbrain.astro` + `web/src/lib/diagrams/flashbrain.ts` (solo si el cambio es significativo de cara a fuera — paso MANUAL, ningún workflow lo hace solo desde 2026-07-24) · `tests/agent_headless/unit/flash/test_router.py` · re-comprobar el gating contextual en `providers/nucleo.py` + `nucleo/flash/probe.py` · `CLAUDE.md` si cambia una decisión. Toda tool debe estar JUSTIFICADA y encajar en el flujo V2-036 (nada de entradas muertas/stale). |
| es visible para quien clona el repo | **`README.md`** (siempre que cambie qué instalar/cómo arrancar) |

## 3. Regla de oro: "que aparezca en los tres sitios"

Todo concepto que importe debe ser hallable en: **(a) el contexto** (`CLAUDE.md`), **(b) la documentación canónica**
(`.meshkore/docs/<categoría>/`), y **(c) la arquitectura** (`zaelar-architecture.md`, incluido su diagrama si el
concepto es estructural o de flujo). Si algo solo está en el código, no está documentado.

Para testing, la misma regla se concreta en cuatro capas sin duplicar instrucciones: `CLAUDE.md`/`AGENTS.md`
enrutan al agente, `tests/README.md` da el contrato operativo, `zaelar-testing.md` explica el diagnóstico profundo y
`tests/platform/SCHEMA.md` fija el contrato máquina. Un cambio de plataforma de tests debe mantener las cuatro
coherentes.

## 4. Verificación

- **Enlaces**: los `[texto](ruta)` nuevos resuelven (rutas relativas correctas). Sin referencias colgando en la
  tabla de docs canónicos de `CLAUDE.md`.
- **Coherencia código↔doc**: lo que dice la doc coincide con el código (nombres de fichero/env/comando reales).
- **Multi-plataforma**: cada instrucción de instalación tiene su variante por-OS o dice explícitamente que es
  específica de una.
- Luego continúa con [[zaelar-change-protocol]] (versión → diario/iniciativa → commit → push si procede).

## 5. Resumen para el operador
Una línea: qué se sincronizó (README/CLAUDE/architecture/diagrama/docs de categoría), y qué quedó pendiente.
