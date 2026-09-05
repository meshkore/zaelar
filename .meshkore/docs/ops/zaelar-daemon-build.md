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

### Signing and notarizing

Not automated, and not a side effect of a green build: it needs the operator's Apple Developer ID and
(Windows) a code-signing certificate, which live with the operator and not in a workflow. Until then the
installers clear quarantine on a file the user explicitly chose, which is the same consent they already gave —
and the honest description is that the artifacts are **unsigned**.

⚠️ **There is no self-updater, deliberately.** An update channel that downloads and executes without a signed
artifact is remote code execution by design, and bolting one onto a daemon that reads somebody's documents
would be the worst possible place to have it. What exists instead: the engine can already read the daemon's
version over `/health` and tell the user it is out of date, `SHA256SUMS` lets a person check the file they got
matches the file that was built (two files agreeing — **not** provenance: whoever can replace one can replace
the other), and upgrading is re-running the installer. Building the signed channel is the work that makes an
updater safe, and it comes first.

---

## 4. Verified where

| Claim | How it is known |
|---|---|
| The archive assembles, carries every module, excludes the build tooling, and **runs** | Node **7.41**, on every CI run |
| The installed process does its whole job over real HTTP | Node **7.37** (boots a real `python -m daemon`) |
| The guards hold against a hostile local process | Node **7.40**, seven disarms |
| macOS install → launchd accepts, starts, defers to a running instance → uninstall leaves nothing | **By hand, 2026-09-06.** Built, installed into a temp `HOME`, `launchctl print` showed the job registered and correctly not restart-looping after it found the port taken; uninstalled and the job is gone |
| Windows install | **Not verified by hand — there was no Windows and no PowerShell on the machine this was written on.** That is what the Windows CI job is for, and until it has run green the Windows path is written and unmeasured |

The last row is the shape of this document: what is measured, and what is merely written.
