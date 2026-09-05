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

Then open **https://local.zaelar.com:44317** and follow the on-screen setup. Add your AI keys **in the app** —
no `.env` editing, no config files to touch.

> `local.zaelar.com` is a public DNS record that points at **127.0.0.1**, and its certificate ships in this repo,
> so it resolves to **your own machine** on every install and nothing ever leaves it. You get a real domain and
> HTTPS instead of `localhost` — which is also what browsers require before they will grant microphone access.
> Plain HTTP still works at `http://localhost:43917` if you prefer.

## Commands

Identical on macOS, Linux and Windows (use `.\zaelar.ps1` instead of `./zaelar` on Windows):

| Command | What it does |
|---|---|
| `./zaelar` | First run: check → setup → start. After that: just starts. |
| `./zaelar up` | Start it in the **background** and give you your prompt back. |
| `./zaelar stop` | Stop it, and unload any local models so they stop draining the battery. |
| `./zaelar restart` | Stop + start. This is how you pick up code you just changed. |
| `./zaelar status` | Is it running? On which ports? Which build? |
| `./zaelar start` | Run it in the **foreground** with the logs on screen (Ctrl-C quits). |
| `./zaelar doctor` | Check that your system meets the requirements. |
| `./zaelar setup` | Create the local environment and install dependencies. |
| `./zaelar update` | Pull the latest version and re-setup. |

Working on the code? `make start` / `make stop` / `make restart` / `make status` do the same thing.

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
inspect. No account, no cloud, no lock-in. Because the source is public, you can verify exactly what
runs on your data.

## Zaelar Cloud

Don't want to run it yourself? **Zaelar Cloud** runs the exact same Zaelar for you — ready in minutes,
automatic updates, managed backups, multi-device sync, no maintenance. → [Get early access](https://zaelar.com)

## Links

- Website — https://zaelar.com
- Docs — <!-- [[PENDING: docs-url]] -->
- Community & demos — <!-- [[PENDING: youtube-channel]] -->

## License

Zaelar is **[fair-code](https://faircode.io)**, distributed under the
[**Sustainable Use License**](LICENSE.md) (the license n8n pioneered):

- **Free to use for yourself** — self-host it for personal use or for your own internal business
  purposes, modify it, read every line.
- **Not free to commercialize** — you may not sell it, offer it as a hosted service, or build a
  commercial product on top of it. Commercial hosting is what [Zaelar Cloud](https://zaelar.com) is.
- Third-party components keep their own licenses — notably `connectors/whatsapp/bridge/` is
  MIT-licensed code vendored from [Hermes Agent](https://github.com/NousResearch/hermes-agent)
  (Nous Research); see the LICENSE file in that directory.

This is a source-available license, not an OSI-approved open-source license: the source is public and
yours to run, but the commercial rights stay with Zaelar.

<div align="center"><sub>Zaelar — an Asimovia company.</sub></div>
