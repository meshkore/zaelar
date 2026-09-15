#!/usr/bin/env bash
# One line, and the daemon is installed (V2-575 · P4).
#
#   curl -fsSL https://raw.githubusercontent.com/meshkore/zaelar/main/daemon/packaging/get.sh | bash
#
# WHY A TERMINAL COMMAND IS THE MAIN PATH, and not a download button. Quarantine on macOS is set by whatever
# WROTE the file — a browser marks it, `curl` does not — so a file that arrives this way is never held by
# Gatekeeper and the user is never shown a dialog they have to know how to dismiss. That is the whole
# difference between "it installs" and "it looks like a virus", and it costs nothing: no Apple account, no
# notarization queue, no approval that takes weeks to arrive and has to be renewed.
#
# ⚠️ IT DOES NOT TRUST THE DOWNLOAD BLINDLY. Piping a script into a shell is exactly as safe as the origin it
# came from and no safer, so: this script is fetched over https from the repository it belongs to, the binary
# is fetched from that repository's own release, and its SHA-256 is checked against the `SHA256SUMS-*` the
# build published beside it. Be clear about what that last part IS: two files agreeing. It catches a corrupt
# or truncated download and it catches a mirror that altered one of them — it is NOT provenance, because
# whoever can replace one can replace the other. Provenance needs a signature, and that is a separate,
# deliberate piece of work (see `.meshkore/docs/ops/zaelar-daemon-build.md`).
#
# NO SUDO. Anywhere. If this script ever needs an administrator password, something is wrong with it.
set -euo pipefail

REPO="${ZAELAR_DAEMON_REPO:-meshkore/zaelar}"
RAW_BASE="${ZAELAR_DAEMON_RAW_BASE:-https://raw.githubusercontent.com/$REPO/main/daemon/packaging}"

say()  { printf '  %s\n' "$*"; }
die()  { printf '✗ %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "this installer is for macOS. On Windows run the PowerShell one-liner instead."
command -v curl >/dev/null 2>&1 || die "curl is required and is not on PATH."

# ── which build is for this Mac ───────────────────────────────────────────────────────────────────────────
# ⚠️ APPLE SILICON AND INTEL ARE DIFFERENT BINARIES and there is no such thing as a build that runs on both:
# a PyInstaller bundle carries a real interpreter compiled for one architecture. Getting this wrong does not
# degrade, it fails with "bad CPU type in executable", which reads like a broken download.
case "$(uname -m)" in
  arm64)  ASSET="zaelar-daemon-macos" ;;
  x86_64) ASSET="zaelar-daemon-macos-x86_64" ;;
  *)      die "unsupported architecture: $(uname -m)" ;;
esac

# ── the newest DAEMON release, which is not the newest release ────────────────────────────────────────────
# The repository also tags the engine, so `releases/latest` regularly points at something with no daemon
# assets in it at all. Tags are filtered by prefix instead.
resolve_tag() {
  local tag
  tag="$(curl -fsSL "https://api.github.com/repos/$REPO/releases?per_page=30" 2>/dev/null \
        | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\(daemon-v[^"]*\)".*/\1/p' | head -n 1 || true)"
  printf '%s' "$tag"
}
TAG="${ZAELAR_DAEMON_TAG:-$(resolve_tag)}"
[[ -n "$TAG" ]] || die "could not find a published daemon release. Set ZAELAR_DAEMON_TAG to install a specific one."
BASE="https://github.com/$REPO/releases/download/$TAG"

printf '\nZaelar Local Daemon · %s · %s\n\n' "$TAG" "$(uname -m)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say "downloading ${ASSET}…"
curl -fsSL -o "$WORK/$ASSET" "$BASE/$ASSET" || die "could not download $ASSET from $TAG."
# Each architecture publishes its OWN checksum file: one `SHA256SUMS-macos` holding both would mean two
# jobs writing one name into a flattened release, and the second would win.
SUMS="SHA256SUMS-${ASSET#zaelar-daemon-}"
curl -fsSL -o "$WORK/SHA256SUMS" "$BASE/$SUMS" || die "could not download $SUMS."

# ── verify before anything is executed ────────────────────────────────────────────────────────────────────
# The order matters: the hash is checked while the file is still an inert blob in a temp directory, before it
# is made executable, moved anywhere, or handed to launchd.
say "checking the download…"
EXPECTED="$(sed -n "s/^\([0-9a-f]\{64\}\)[[:space:]]\{1,\}$ASSET$/\1/p" "$WORK/SHA256SUMS" | head -n 1)"
[[ -n "$EXPECTED" ]] || die "$ASSET is not listed in the published checksums for $TAG."
ACTUAL="$(shasum -a 256 "$WORK/$ASSET" | awk '{print $1}')"
[[ "$ACTUAL" == "$EXPECTED" ]] || die "checksum mismatch — the file that arrived is not the file that was built.
    expected $EXPECTED
    got      $ACTUAL"
say "checksum ok"

# ── install with the same script the repository ships ─────────────────────────────────────────────────────
# Fetched from `main` rather than from the release, deliberately: it then shares this script's origin exactly,
# so the trust decision the user already made by running this line is the only one being made.
say "installing…"
curl -fsSL -o "$WORK/install.sh" "$RAW_BASE/macos/install.sh" || die "could not download the installer."
chmod +x "$WORK/$ASSET"
bash "$WORK/install.sh" "$WORK/$ASSET"

printf '\n  To remove it later:\n'
printf '    curl -fsSL %s/macos/uninstall.sh | bash\n\n' "$RAW_BASE"
