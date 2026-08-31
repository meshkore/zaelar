#!/usr/bin/env bash
# zaelar · installs the versioned Git hooks from scripts/hooks/ into .git/hooks/ (V2-038).
# .git/hooks/ is NOT versioned; this script creates the link. Idempotent. Run it after cloning.
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
