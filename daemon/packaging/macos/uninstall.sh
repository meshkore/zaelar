#!/usr/bin/env bash
# Remove the Zaelar Local Daemon from this user's account.
#
# THE STATE IS KEPT BY DEFAULT, and that is a deliberate asymmetry. Uninstalling is often a step in
# troubleshooting, and throwing away the token and the folder allowlist turns "let me reinstall this" into "let
# me set it all up again". `--purge` is there for somebody who really means it, and it says what it deleted.
set -euo pipefail

LABEL="com.zaelar.daemon"
PREFIX="$HOME/Library/Application Support/Zaelar"
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"

say() { printf '  %s\n' "$*"; }

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || launchctl unload "$AGENT" >/dev/null 2>&1 || true
rm -f "$AGENT"
rm -f "$PREFIX/bin/zaelar-daemon" "$PREFIX/bin/zaelar-daemon.pyz"

printf '\n✓ zaelar-daemon stopped and removed\n'
if [[ "${1:-}" == "--purge" ]]; then
  rm -rf "$PREFIX"
  say "purged: the token, the folder allowlist and the audit log are gone as well"
else
  say "kept:   $PREFIX  (your token, the folders you allowed, and the audit log)"
  say "        run with --purge to delete those too"
fi
