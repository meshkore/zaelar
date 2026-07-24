#!/usr/bin/env bash
# zaelar · instala los git hooks versionados de scripts/hooks/ en .git/hooks/ (V2-038).
# .git/hooks/ NO se versiona; este script hace el enlace. Idempotente. Ejecútalo tras clonar.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
SRC="$ROOT/scripts/hooks"
DST="$ROOT/.git/hooks"
for hook in "$SRC"/*; do
  name="$(basename "$hook")"
  cp "$hook" "$DST/$name"
  chmod +x "$DST/$name"
  echo "✓ hook instalado: $name"
done
echo "Listo. Bypass puntual: git commit --no-verify"
