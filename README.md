<div align="center">

# Zaelar

### The Personal Operating System — self-hosted.

One place where your AI agents live, remember, and act for your digital life.
Open source. You own your data. Runs on your machine.

</div>

---

Zaelar is not a chatbot or "another assistant." It's the operating system that **hosts your personal
AI agents** — with voice, persistent memory, widgets, a real browser, messaging and proactivity.
This repository is the **agent** you run yourself. Prefer zero setup? See **Zaelar Cloud** ↓.

## Quick start

You need **[Python 3.11+](https://python.org/downloads)** and about **3 GB** of free disk. That's it —
Zaelar installs everything else **into its own folder** (nothing is installed system-wide, **no Docker**).

**macOS / Linux**
```bash
git clone https://github.com/<org>/zaelar
cd zaelar
./zaelar          # checks your system, sets up, and starts
```

**Windows (PowerShell)**
```powershell
git clone https://github.com/<org>/zaelar
cd zaelar
.\zaelar.ps1      # checks your system, sets up, and starts
```

Then open **http://localhost:43917** and follow the on-screen setup. Add your AI keys **in the app** —
no `.env` editing, no config files to touch.

## Commands

| Command | What it does |
|---|---|
| `./zaelar` (or `.\zaelar.ps1`) | First run: check → setup → start. After that: just starts. |
| `./zaelar doctor` | Check that your system meets the requirements. |
| `./zaelar setup` | Create the local environment and install dependencies. |
| `./zaelar start` | Run Zaelar. |
| `./zaelar update` | Pull the latest version and re-setup. |

## Requirements

- **macOS, Windows or Linux.**
- **Python 3.11+** — the only thing you install yourself.
- ~3 GB free disk, 8 GB RAM recommended.
- An internet connection for the first setup.
- Your own AI provider key(s) — added later, in the app.

Run `./zaelar doctor` anytime to check. Everything else (voice server, models, dependencies) Zaelar
fetches automatically into `.venv/` and `bin/` **inside this folder** — delete the folder and it's gone.

## Your data is yours

Everything Zaelar knows lives under this folder, on your machine — encrypted, portable, and open to
inspect. No account, no cloud, no lock-in. Because the code is open source, you can verify exactly what
runs on your data.

## Zaelar Cloud

Don't want to run it yourself? **Zaelar Cloud** runs the exact same Zaelar for you — ready in minutes,
automatic updates, managed backups, multi-device sync, no maintenance. → [Get early access](https://zaelar.com)

## Links

- Website — https://zaelar.com
- Docs — <!-- [[PENDING: docs-url]] -->
- Community & demos — <!-- [[PENDING: youtube-channel]] -->

## License

<!-- [[PENDING: license]] — recommended: AGPL-3.0 -->

<div align="center"><sub>Zaelar — an Asimovia company.</sub></div>
