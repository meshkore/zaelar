# Building, installing and releasing the Zaelar Local Daemon

**Trigger:** *"build the daemon installers"*, *"release a new daemon version"*, *"how does someone install
this?"*

The daemon runs on the user's own computer, so unlike the engine it is not deployed — it is **handed over**.
Everything below is about producing a file somebody else can run, and about the one property that matters more
than any of it: that re-running the installer is the whole upgrade procedure.

---

## 1. What gets built

| Artifact | Needs | For |
|---|---|---|
| `zaelar-daemon.pyz` | a Python ≥ 3.11 on the target | developers, self-hosters, and the guarantee that there is always a way to ship |
| `zaelar-daemon` / `.exe` | nothing on the target | an ordinary user |
| `manifest.json`, `SHA256SUMS` | — | telling whether the file you have is the file that was built |

The portable archive is built by the **standard library** (`zipapp`) with no build dependency at all, which is
why it exists alongside the onefile: a build that only works when a third-party tool is working is a build that
stops existing the first time that tool breaks on a new Python.

```bash
python daemon/packaging/build.py             # everything this machine can build
python daemon/packaging/build.py --zipapp    # portable only, needs nothing installed

pip install -r daemon/packaging/requirements-build.txt   # PyInstaller, pinned
python daemon/packaging/build.py --onefile
```

Output lands in `dist/daemon/` (gitignored — the artifacts are reproducible from source, so a binary in a git
repo would only ever be a stale one).

⚠️ **PyInstaller is a BUILD dependency and must never reach `daemon/requirements.txt`**, which is empty and
checked by a test. "Runs on a bare Python with nothing installed" is the property that makes a single-file
installer possible at all.

---

## 2. Installing (and upgrading — the same command)

### How an ordinary person installs it: one line

```bash
curl -fsSL https://raw.githubusercontent.com/asimovia/zaelar/main/daemon/packaging/get.sh | bash    # macOS
```
```powershell
irm https://raw.githubusercontent.com/asimovia/zaelar/main/daemon/packaging/get.ps1 | iex           # Windows
```

⚠️ **This is the main path, and not because terminals are nice.** macOS quarantine and the Windows Mark of the
Web are written by whatever **saved** the file — a browser stamps them, `curl` and `Invoke-WebRequest` do not.
So an **unsigned** build that arrives this way is never held by Gatekeeper and never raises "Windows protected
your PC". That buys, for free and immediately, most of what a code-signing certificate would buy: no Apple
Developer account, no Microsoft account, no notarization queue, nothing that expires, and no approval between
a fix and the person who needs it.

What the bootstrap does, in order: resolve the newest **`daemon-v*`** tag (never `releases/latest` — this repo
also tags the engine), pick the build for `uname -m`, download it, **verify its SHA-256 against the published
sums while it is still an inert file in a temp directory**, and only then run the installer, fetched from
`main` so it shares the origin the user already trusted by running the line.

Be exact about what that verification is: **two files from one release agreeing.** It catches a corrupt
download and an altered mirror. It is **not provenance** — whoever can replace one can replace the other; that
is what a signature adds (see «Signing and notarizing» below).

The direct download still works and the interface still offers it, in a `<details>` that says what it costs: a
browser saved the file, so macOS asks the user to allow it in System Settings and Windows shows SmartScreen.

### Where it lands, and how to put it somewhere else

| | Default |
|---|---|
| macOS | `~/Library/Application Support/Zaelar` |
| Windows | `%LOCALAPPDATA%\Zaelar` |

`ZAELAR_DAEMON_PREFIX` (or `-Prefix` on Windows) moves it, and the **uninstallers take the same override** —
one that only knew the default would remove the launch agent, report success, and leave the program and the
folder allowlist exactly where the user put them.

⚠️ **The state follows the program, and it is derived rather than configured.** The daemon takes its root from
where its own binary sits: `<prefix>/bin/<program>` → `<prefix>`, so the token, the allowlist and the audit log
land in `<prefix>/config/daemon`. That is why a custom prefix needs no environment variable in the launch
agent and no wrapper around the Windows task — which matters on Windows, where a scheduled task cannot carry an
environment variable and setting a user-level `ZAELAR_WORKSPACE` would repoint the **engine's** workspace as a
side effect.

The `bin` directory is the guard, not decoration. Without it a file somebody ran straight out of `~/Downloads`
would claim `~` as its root, and an in-repo `python -m daemon` would resolve `sys.executable` to
`.venv/bin/python` and take the **virtualenv** for its prefix.

⚠️ **"Installed" is not the same as "frozen".** A zipapp is not frozen, so the root resolution must recognise
an installed `.pyz` too; testing `_frozen()` alone would resolve its state to a directory *inside the archive
file* — impossible to create. Since this module never raises, every write would fail quietly: a fresh random
token on every start and a folder allowlist that does not survive a restart, behind a `/health` that answers
perfectly.

### Installing from a checkout

**macOS**

```bash
daemon/packaging/macos/install.sh              # picks the artifact next to it, or the newest in dist/daemon/
daemon/packaging/macos/uninstall.sh [--purge]
```

Per-user LaunchAgent, `~/Library/Application Support/Zaelar`, **no sudo**.

**Windows**

```powershell
powershell -ExecutionPolicy Bypass -File daemon\packaging\windows\install.ps1
powershell -ExecutionPolicy Bypass -File daemon\packaging\windows\uninstall.ps1 [-Purge]
```

Per-user scheduled task at logon, `%LOCALAPPDATA%\Zaelar`, **no administrator**. If local policy refuses the
task, it falls back to a minimized Startup shortcut and says so rather than telling somebody to find an admin.

**No elevation on either platform, and that is a security property before it is a convenience one:** a per-user
daemon that needed elevation could then reach every account on the machine, which is exactly the blast radius
the permission circuit exists to keep small.

**Re-running the installer is the upgrade path** — stop, replace, start. The state directory (the token and the
folders the user chose) is never touched, so an upgrade keeps their choices. Uninstalling keeps them too unless
asked to `--purge`, because uninstalling is usually a step in troubleshooting and throwing away the allowlist
turns "let me reinstall this" into "let me set it all up again".

### The two install-time surprises, both real

- **macOS TCC.** The first time the daemon reads `~/Documents`, `~/Desktop` or `~/Downloads`, macOS asks the
  user to allow it — its own permission layer, on top of ours. If the prompt is missed: System Settings →
  Privacy & Security → Files and Folders. The installer prints this.
- **Quarantine / Mark of the Web.** A file that arrived through a browser is blocked, and the failure is a
  dialog the user cannot dismiss into a working state. Both installers clear it on the file the user just chose
  to install. That is **not** a substitute for signing.

---

## 3. Releasing

`.github/workflows/daemon-artifacts.yml` builds on **macos-latest** and **windows-latest** — the platforms
people install on, not the one the tests run on — and on a tag attaches the artifacts to the release.

It does more than build. On each runner it:

1. imports the daemon on a **bare Python with nothing installed** (stronger than proving it in a checkout where
   the engine's venv is next door and an accidental import would resolve);
2. **parse-checks the installer scripts** — a syntax error in a PowerShell file is a thing you find at install
   time, on somebody else's computer;
3. starts the **real binary** and checks `/health` answers **and that a request naming `Host: evil.example` is
   still refused with a 401** — the one regression that would ship a daemon which starts and defends nothing.

```bash
git tag daemon-v0.2.0 && git push origin daemon-v0.2.0
```

### ⚠️ Release assets are named per platform, and the interface depends on it

Both runners produce `zaelar-daemon.pyz`, `manifest.json` and `SHA256SUMS` under those exact names, and the
release job flattens every downloaded artifact into a single upload — so without a rename one platform's files
would overwrite the other's. Each runner renames its own before uploading:

| Published asset | Platform |
|---|---|
| `zaelar-daemon-macos`, `zaelar-daemon-macos.pyz` | macOS, Apple Silicon |
| `zaelar-daemon-macos-x86_64`, `zaelar-daemon-macos-x86_64.pyz` | macOS, Intel |
| `zaelar-daemon-windows.exe`, `zaelar-daemon-windows.pyz` | Windows |
| `SHA256SUMS-<suffix>`, `manifest-<suffix>.json` | one per build job |
| `get.sh`, `get.ps1`, `zaelar-daemon-(un)install-*` | published once, architecture-independent |

⚠️ **Two Mac builds, not one.** A PyInstaller bundle carries a real interpreter compiled for one architecture
and `macos-latest` has been arm64 since macos-14, so a single build would hand an Intel Mac a binary that fails
with "bad CPU type in executable" — which every user reads as a corrupt download. `get.sh` picks by `uname -m`,
which is precisely what a download button cannot do: a user-agent does not say which Mac this is.

⚠️ **`release_names.py` owns the rename, and it RECOMPUTES the digests.** `build.py` writes `SHA256SUMS` under
the build names while the release publishes the architecture names, so the published sums must be computed
over the published names — otherwise the one-line installer would refuse a binary it fetched perfectly.
Patching the names inside the build's file is not enough: the digests are recomputed from the renamed files.

**These names are a contract.** `server/daemon_api.py` builds the download links from them, and both installers
look for them (including in `~/Downloads`, which is where a browser actually puts them). Renaming an asset
without the other two is how the download screen starts offering a 404, so node **7.44** joins all three.

### Where a user gets the file

`GET /api/daemon/status` carries a `downloads` block pinned to **the daemon's own version tag** — not
`releases/latest`, which follows whatever was released last, including an engine release with no daemon assets
in it. The 🖥 icon in the interface renders it; when the engine runs on a remote host that is the icon's whole job,
since a remote engine cannot reach a daemon on somebody's desk.

`ZAELAR_DAEMON_DOWNLOAD_BASE` overrides the base URL for a mirror or a private build.

### Signing and notarizing

Not a side effect of a green build: it needs an Apple Developer ID and (Windows) a code-signing certificate,
which live with whoever publishes the build, not in a workflow. Builds published without them are **unsigned**;
the installers clear quarantine on a file the user explicitly chose, which is the same consent they already
gave.

⚠️ **There is no self-updater, deliberately.** An update channel that downloads and executes without a signed
artifact is remote code execution by design, and bolting one onto a daemon that reads somebody's documents
would be the worst possible place to have it. What exists instead: the engine can already read the daemon's
version over `/health` and tell the user it is out of date, `SHA256SUMS` lets a person check the file they got
matches the file that was built (two files agreeing — **not** provenance: whoever can replace one can replace
the other), and upgrading is re-running the installer. A signed channel is the prerequisite for any updater.

---

## 4. Tests

| Claim | Where it is checked |
|---|---|
| The archive assembles, carries every module, excludes the build tooling, and **runs** | Node **7.41**, on every CI run |
| The installed process does its whole job over real HTTP | Node **7.37** (boots a real `python -m daemon`) |
| The guards hold against a hostile local process | Node **7.40**, with disarms |
| The release asset names, the download links and the installers agree | Node **7.44** |
| The Windows and macOS builds, the installer syntax, and the guards surviving the build | `.github/workflows/daemon-artifacts.yml` on `windows-latest` / `macos-latest` |

The macOS install path (launchd accepts the job, starts it, defers to an already-running instance, and uninstall
leaves nothing) can be exercised by hand by installing into a temporary `HOME` and checking `launchctl print`.
