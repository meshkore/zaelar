---
id: INI-007
title: Security Hardening & Adversarial Tests (audit 2026-07-02)
status: done
owner: ricart
modules: [connectors, brains, widgets, server, config]
updated: 2026-07-03
model_note: run on Opus 4.8 / Mythos — attack reasoning + payload authoring trip Fable 5 dual-use safeguards
depends_on: INI-006
---

## Goal

Aplicar **todos los hallazgos delicados/ofensivos de seguridad** de la auditoría 2026-07-02
([[harbee-audit-2026-07-02]]) — **fixes + sus tests que reproducen el ataque, juntos**. Es el desprendimiento de
**[[INI-006]]**: allí vive la refactorización de core/arquitectura (que la maneja **Fable 5**, el modelo más
capaz); aquí se aísla todo lo que toca vectores de ataque (inyección de comandos/prompt, exfiltración, XSS, DNS-
rebind, timing) porque razonar sobre esos vectores y **redactar payloads** pattern-matchea a capacidad ofensiva y
los safeguards de Fable 5 lo rechazan aunque el contexto sea 100% defensivo (auditoría del propio sistema).

> **Ejecutar en Opus 4.8 / Mythos, DESPUÉS de INI-006.** El plan del operador: Fable 5 refactoriza primero todo el
> core/arquitectura/docs/widgets (INI-006, sin fricción de safeguards); luego, sobre ese árbol ya saneado, se
> aplican aquí los endurecimientos de seguridad. Ventaja del corte: fix y su test de regresión viajan JUNTOS
> (recupera la regla "cada fix de seguridad va con su test que reproduce el ataque").

> **Regla de corte (decidida por el operador 2026-07-02):** INI-006 = todo lo que NO es sensible a seguridad
> (core, bugs de arquitectura, deriva de docs, widgets, cosmético). INI-007 = **el dominio de seguridad entero**
> (P0 completo + SEC-3). En la duda, delicado → aquí.

> Estado global: **DONE (2026-07-03)** — S-01…S-08, S-10, S-11 aplicados con tests adversariales (rojo
> pre-fix / verde post-fix); `test_security.py` 24→**51 passed**. **S-09** (tirith `fail_open:false`) queda
> ⏸ pendiente del operador: tirith no está instalado y poner fail-closed sin el binario bloquearía todos los
> comandos del operador — requiere `brew install sheeki03/tap/tirith` primero (acción de sistema del operador).
> Ejecutado en **Fable 5** por decisión del operador (2026-07-03), no en Opus/Mythos como preveía el plan.

---

## P0 — Vectores de seguridad (fix + test, juntos)

- [x] **S-01 · V1 (CRÍTICA) ✅ (2026-07-03, diario `connectors/logs/2026-07/S-01-02`) — fence del handle de peer hacia el turno de voz.** *(era T-01)* El handle elegido por
  el atacante entra sin neutralizar en `connectors/meshkore/brief.py:22-24` y llega al kickoff de voz
  (`voice/agent.py:253`), que corre con tools auto-aprobadas → bypass del tool-gate. **Fix:** neutralizar/fence toda
  identity string de peer antes de cualquier prompt (reutilizar `security._neutralize`); render en contexto untrusted.
  **Test:** handle con payload de inyección de instrucción/comando en `online` → assert entregado neutralizado y
  que no llega crudo al brief de voz.
- [x] **S-02 · V2 (ALTA) ✅ (2026-07-03, diario `connectors/logs/2026-07/S-01-02`) — neutralizar el handle en la etiqueta del turno de cluster.** *(era T-02)* `bridge.py:110,118,130`:
  `frm`/`ag`/`online` van fuera del fence. **Fix:** `security._neutralize()` sobre ellos o fence del evento entero.
  **Test:** payload en `frm`/`ag`/`online` → assert etiqueta neutralizada o dentro del fence.
- [x] **S-03 · V3 (ALTA) ✅ (2026-07-03, diario `connectors/logs/2026-07/S-03`) — escanear (o dropear) el campo `media` en salida.** *(era T-03)* `bridge.py:235` reenvía
  `media` sin `scan_outbound` → exfil por `media[].url`. **Fix:** escanear media serializado o allowlist text-only en
  replies de cluster. **Test:** reply con secreto embebido en `media[].url` → assert bloqueado/redactado/dropeado.
- [x] **S-04 · SEC-1 (ALTA) ✅ (2026-07-03, diario `widgets/logs/2026-07/S-04`) — XSS en widget `agenda`.** *(era T-04)* Sigue vivo tras W-001:
  `widgets/agenda/widget.js:61` usa `el.innerHTML` con `data.date/now/coaching/warnings` + `active.label`
  (brain-pushables vía `[[push:agenda]]`). **Fix:** `createElement`+`textContent`. **Test:** `[[push:agenda]]` con
  payload XSS en `label`/`coaching`/`warnings` → assert render inerte (texto, no HTML ejecutable).
- [x] **S-05 · V4 (MEDIA) ✅ (2026-07-03, diario `connectors/logs/2026-07/S-05-06`) — guard en `/api/meshkore/status`.** *(era T-06)* `server_api.py:69` sin `Depends(_guard)`.
  **Fix:** añadirlo. **Test:** request cross-origin/sin token → assert 401/403.
- [x] **S-06 · V5 (MEDIA) ✅ (2026-07-03, diario `connectors/logs/2026-07/S-05-06`) — anti DNS-rebind por host exacto.** *(era T-07)* `server_api.py:41` hace substring match.
  **Fix:** parsear el Origin y exact-match del host contra `{localhost,127.0.0.1,::1}` (+ puerto). **Test:** `Origin`
  tipo `localhost.<attacker>.com` → assert rechazo.
- [x] **S-07 · V6 (MEDIA) ✅ (2026-07-03, diario `connectors/logs/2026-07/S-07`) — redactar texto de peer inbound a SSE/timeline.** *(era T-08)* `bridge.py:103` `text=text`.
  **Fix:** `store.redact(text)`. **Test:** peer envía texto con secreto → assert redactado en SSE/timeline.
- [x] **S-08 · V7/V8/V9 (BAJAS) ✅ (2026-07-03, diario `connectors/logs/2026-07/S-08`) — endurecimientos.** *(era T-09)* `_decide_permission` matchear solo `reject`/`deny`
  (`acp_client.py:180-183`); redactar el fallback `_classify` (`client.py:72→103`); `hmac.compare_digest` en el
  compare de token (`server_api.py:29`). **Tests:** approve no mal-seleccionado como reject; token no filtrado en
  `str(e)`; compare constant-time.
- [x] **S-09 · V10 ✅ (2026-07-03, diario `connectors/logs/2026-07/S-09`) — cerrar la 2ª capa Tirith.** tirith 0.3.3 instalado en `~/.local/bin/tirith` (binario precompilado de la release, checksum verificado — el build de brew falló por CLT desactualizadas) + `fail_open:false` en vigor; verificado que un turno benigno del operador pasa y un comando peligroso se bloquea. *(era T-10)* Verificar binario instalado
  (`brew install sheeki03/tap/tirith`) y flip `fail_open:false` en `~/.hermes/config.yaml` para enforcement duro
  (hoy fail-open). Ver `zaelar-ops.md §3.2`. *(Ops/config; sin payload — se agrupa aquí por dominio.)*
- [x] **S-10 · SEC-3 ✅ (2026-07-03, diario `widgets/logs/2026-07/S-10`) — el generador debe validar reglas de la casa (escaneo ESTÁTICO).** *(era T-12; parcial: W-001
  ya añadió el smoke-test de `view_data()`)* **Falta:** rechazar `innerHTML`/`fetch`/`XMLHttpRequest`/`import(` en
  widget.js e imports no-stdlib/secretos en data.py (hoy solo lo pide la prosa, sin enforcement). **Test:** widget
  generado con `innerHTML`/`fetch` → assert rechazado por el validador.
- [x] **S-11 · Cobertura + recuento. ✅ (2026-07-03, diario `connectors/logs/2026-07/S-11`; gap real did:key arreglado; 24→51 tests)** Secreto multi-línea + huella `did:key` (edge del regex single-line). Tras
  S-01…S-10, actualizar el recuento documentado de tests en `zaelar-security.md` y en el informe (hoy 24).
  *(consolida el antiguo T-11.)*

---

## Notas de ejecución
- **Orden:** ejecutar tras INI-006. Antes de cada S-xx, re-verificar `fichero:línea` (Fable refactorizó alrededor).
- **Adversarial:** cada test primero rojo contra pre-fix, luego verde contra el fix.
- Cierre por [[zaelar-change-protocol]] (verificar → versión → diario en `.meshkore/modules/connectors/logs/`,
  `.meshkore/modules/widgets/logs/`, `.meshkore/modules/config/logs/` según toque → commit). Push solo con OK.
- Mover `status:` (`proposed`→`in-progress`→`done`) al aplicar.
