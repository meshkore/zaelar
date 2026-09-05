#!/usr/bin/env bash
# Install (or upgrade) the Zaelar Local Daemon on macOS, for the CURRENT USER ONLY.
#
# NO SUDO, ON PURPOSE. A daemon whose whole job is to read one person's documents has no business running as
# root, and asking for an administrator password is the single biggest reason an install gets abandoned. It
# goes in this user's own Application Support and runs as a per-user LaunchAgent, which means it can never
# reach another account's files even if every check inside it failed at once.
#
# RE-RUNNING IT IS THE UPGRADE PATH. Stop, replace, start — so "deploy a new version" is the same command as
# "install", and there is no second procedure to get wrong. The allowlist and the token live in the state
# directory, which is never touched, so an upgrade keeps the folders the user chose.
#
#   ./install.sh                     use the artifact next to this script, or the newest in dist/daemon/
#   ./install.sh /path/to/artifact   use a specific one (a onefile binary or a .pyz)
set -euo pipefail

LABEL="com.zaelar.daemon"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HOME/Library/Application Support/Zaelar"
BIN_DIR="$PREFIX/bin"
LOG_DIR="$PREFIX/logs"
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
TARGET="$BIN_DIR/zaelar-daemon"

say() { printf '  %s\n' "$*"; }
die() { printf '✗ %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "this installer is for macOS; use windows/install.ps1 on Windows."

# ── find something to install ─────────────────────────────────────────────────────────────────────────────
# The onefile binary is preferred because it carries its own interpreter: nothing else has to be present on the
# machine. The .pyz is the fallback and needs a python3, which is why the check below is a check and not an
# assumption — a launchd job that cannot find its interpreter fails at LOGIN, hours later, with the user
# nowhere near a terminal.
SOURCE="${1:-}"
if [[ -z "$SOURCE" ]]; then
  for candidate in "$HERE/zaelar-daemon" "$HERE/zaelar-daemon.pyz" \
                   "$HERE/../../../dist/daemon/zaelar-daemon" "$HERE/../../../dist/daemon/zaelar-daemon.pyz"; do
    [[ -f "$candidate" ]] && { SOURCE="$candidate"; break; }
  done
fi
[[ -n "$SOURCE" && -f "$SOURCE" ]] || die "no artifact found. Build one: python daemon/packaging/build.py"

PYTHON=""
if [[ "$SOURCE" == *.pyz ]]; then
  PYTHON="$(command -v python3 || true)"
  [[ -n "$PYTHON" ]] || die "$SOURCE needs a python3 and there is none on PATH. Install the onefile build instead."
  "$PYTHON" - <<'PY' || die "the python3 on PATH is older than 3.11, which the daemon requires."
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
fi

mkdir -p "$BIN_DIR" "$LOG_DIR" "$(dirname "$AGENT")"

# ── stop whatever is running, so the file can be replaced ─────────────────────────────────────────────────
# `bootout` is the modern verb and `unload` the one that works on older macOS; the daemon may also be running
# from a terminal, which launchd knows nothing about. Every one of these is allowed to fail: "it was not
# running" is a fine outcome for a stop.
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
else
  launchctl unload "$AGENT" >/dev/null 2>&1 || true
fi
sleep 0.5

# ── install the artifact ──────────────────────────────────────────────────────────────────────────────────
if [[ "$SOURCE" == *.pyz ]]; then
  install -m 0644 "$SOURCE" "$BIN_DIR/zaelar-daemon.pyz"
  # A two-line launcher rather than a shebang: the plist names ONE program, and this keeps the plist identical
  # whichever artifact is installed — so an upgrade from .pyz to onefile does not need a different plist.
  cat > "$TARGET" <<EOF
#!/bin/sh
exec "$PYTHON" "$BIN_DIR/zaelar-daemon.pyz" "\$@"
EOF
  chmod 0755 "$TARGET"
  say "installed the portable build (needs $PYTHON)"
else
  install -m 0755 "$SOURCE" "$TARGET"
  # Gatekeeper quarantines anything that arrived from a browser, and the failure is a dialog the user cannot
  # dismiss into a working state. Clearing the attribute on a file THEY just chose to install is the same
  # consent they already gave; it is not a substitute for signing, which is a release step.
  xattr -d com.apple.quarantine "$TARGET" 2>/dev/null || true
  say "installed the standalone build (carries its own Python)"
fi

# ── register it to start at login ─────────────────────────────────────────────────────────────────────────
# KeepAlive with SuccessfulExit=false: restart it if it dies, but let a deliberate `zaelar-daemon stop` stay
# stopped instead of fighting the user. ProcessType Background asks the scheduler to treat it as what it is.
cat > "$AGENT" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$TARGET</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key>
  <dict><key>SuccessfulExit</key><false/></dict>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG_DIR/daemon.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/daemon.log</string>
</dict>
</plist>
EOF
chmod 0644 "$AGENT"

if ! launchctl bootstrap "gui/$(id -u)" "$AGENT" 2>/dev/null; then
  launchctl load "$AGENT" 2>/dev/null || die "launchd refused the agent; see $AGENT"
fi

# ── say what happened, and check it rather than assume ────────────────────────────────────────────────────
sleep 1
VERSION="$("$TARGET" version 2>/dev/null || echo "?")"
printf '\n✓ zaelar-daemon %s installed for %s\n' "$VERSION" "$USER"
say "program:  $TARGET"
say "state:    $PREFIX  (the token and the folders you allow)"
say "log:      $LOG_DIR/daemon.log"
say "starts:   at login, and now"
printf '\n'
say "It can read NOTHING until you choose folders — that is the point of the wizard in Zaelar."
say "From a terminal: $TARGET status | allow ~/Documents | deny ~/Documents"
printf '\n'
say "⚠️ The first time it reads ~/Documents, ~/Desktop or ~/Downloads, macOS will ask you to allow it."
say "   That prompt is the operating system's own permission layer, on top of ours. If you miss it,"
say "   grant it under System Settings → Privacy & Security → Files and Folders."
