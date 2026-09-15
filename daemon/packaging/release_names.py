"""Give a build's files the names the RELEASE publishes them under (V2-575 · P4).

WHY THIS IS A SCRIPT AND NOT THREE LINES OF SHELL. Three build jobs — Apple Silicon, Intel, Windows — upload
into one flattened release, and every one of them produces `zaelar-daemon`, `zaelar-daemon.pyz`,
`manifest.json` and `SHA256SUMS` under those exact names. Whoever uploaded last used to win. So each job
renames its own output with its architecture's suffix before uploading, and that rename has to happen
identically on bash and on PowerShell, which is exactly the kind of thing that drifts between two copies.

⚠️ AND THE RENAME IS NOT JUST A RENAME. `build.py` writes `SHA256SUMS` listing the files by their BUILD names,
so renaming the files alone leaves a checksum file that names things the release does not contain — published,
correct-looking, and useless for the one job it has. Measured 2026-09-15: the first release shipped exactly
that, and the one-line installer refused to install because it could not find its own artifact in the sums.
The digests are recomputed here from the files as they will actually be published.

    python daemon/packaging/release_names.py macos
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent.parent / "dist" / "daemon"

# Build name → the template its published name follows. `.exe` keeps its extension because Windows needs it to
# run the file at all, so the suffix goes before it rather than after.
_RENAMES = (
    ("zaelar-daemon", "zaelar-daemon-{suffix}"),
    ("zaelar-daemon.exe", "zaelar-daemon-{suffix}.exe"),
    ("zaelar-daemon.pyz", "zaelar-daemon-{suffix}.pyz"),
    ("manifest.json", "manifest-{suffix}.json"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rename_for(suffix: str, dist: Path | None = None) -> list[Path]:
    """Rename everything in `dist` for `suffix`, then rewrite the checksums and the manifest to match.

    Returns the artifacts (binary and archive) under their published names."""
    dist = dist or DIST
    # Windows names its binary `zaelar-daemon.exe`; a suffix that already carries `.exe` would double it.
    published: list[Path] = []
    for build_name, template in _RENAMES:
        source = dist / build_name
        if not source.exists():
            continue
        target = dist / template.format(suffix=suffix)
        source.replace(target)
        if not target.name.startswith("manifest"):
            published.append(target)

    # The checksums are RECOMPUTED, not rewritten by text substitution: a sums file whose names were patched
    # but whose digests came from somewhere else would be the same lie in a more convincing format.
    sums = dist / f"SHA256SUMS-{suffix}"
    sums.write_text("".join(f"{_sha256(a)}  {a.name}\n" for a in sorted(published)), encoding="utf-8")
    old_sums = dist / "SHA256SUMS"
    if old_sums.exists():
        old_sums.unlink()

    manifest_path = dist / f"manifest-{suffix}.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["platform_suffix"] = suffix
            manifest["artifacts"] = [
                {"name": a.name, "bytes": a.stat().st_size, "sha256": _sha256(a)} for a in sorted(published)
            ]
            manifest_path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
        except Exception:       # noqa: BLE001 — the manifest is informational; the sums are the control
            pass
    return published


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].strip():
        print("usage: release_names.py <suffix>", file=sys.stderr)
        return 2
    published = rename_for(argv[1].strip())
    if not published:
        print(f"nothing to rename in {DIST}", file=sys.stderr)
        return 1
    for artifact in published:
        print(f"  {artifact.name}  {artifact.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
