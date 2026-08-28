# The lab — two agents you can watch

Two real zaelar installations that stay up, on ports that never change, each with its own database,
its own identity and its own country. They exist because the rest of this suite boots a throwaway
engine per run and tears it down at the end: right for an unattended measurement, useless for
watching — by the time you open the URL, the port is gone.

| | port | language | who they are |
|---|---|---|---|
| `es` | **http://127.0.0.1:43921** | `es` | Marc, lives in Madrid, Spain |
| `us` | **http://127.0.0.1:43922** | `en` | Alex, lives in San Francisco, California |

Those two numbers are not written here or in `profiles.py` — they come from `tests/platform/ports.py`,
the one table of the **three** agents this machine runs (the operator's own engine holds `43917`). The
unattended batch reads the same table, so a Spanish round answers on `43921` whether it was started with
`--lab es` or with `--sandbox`. Until 2026-08-28 it did not: `--sandbox` booted on `preferred_port(43918)`
— one number for both languages, sliding to an ephemeral one when taken — and the operator opened the port
they remembered to find nothing listening.

```
python -m tests.use_cases.lab up            # both, with voice, on their own LiveKit rooms
python -m tests.use_cases.lab status
python -m tests.use_cases.lab say es "Necesito un fontanero hoy mismo en mi ciudad."
python -m tests.use_cases.lab clean es      # blank session (canvas + background work); memory KEPT
python -m tests.use_cases.lab reset es      # wipe its memory, reseed the profile, SAME port
python -m tests.use_cases.lab logs es -n 80
python -m tests.use_cases.lab down
```

Open the port in a browser and you get the whole product: the orb, the canvas, widgets opening as the
agent opens them, the process list, the results sheet with its live progress tab, the observability
viewer (◷) and the memory map (🧠). Nothing about that screen is special to the lab — it is the same
frontend the operator's own engine serves, pointed at a different database.

## A boot is a BLANK session

`up` leaves the agent on a blank session — background work stopped, canvas cleared, a new observability
window — and keeps its memory and its profile. It has to: what persists here is not the process but the
**workspace on disk**, so without it a freshly booted agent opens showing the errand of a week ago, and the
◷ visor cannot tell "this test" from whatever was there before (operator, 2026-08-28, looking at exactly
that). The runner does the same before EVERY case; `clean` does it to a running agent without a reboot.

It is `/reset/hard` and never `/api/reset/full` with a wipe flag — that one relaunches the engine with
`make run` in the real engine directory, which would take the lab and the operator's engine down together.
And it is reported both ways: asking for the clean-up is not having got it.

## Why two and not one

Almost everything this suite measures is an errand aimed at the real world, and every one of those
resolves against **where the person lives**. `operator.location` is a supersede slot: one shared agent
means the last case to run decides the country for every case after it, and a US scenario would leave
a Spanish one searching California. Two agents, two databases, two identities that never meet.

## Why voice is ON by default

Not for the microphone — for the **screen**. Measured by rendering the shell in a real Chromium:
with `ZAELAR_ENGINE=off` the boot veil never lifts, at 5 s or at 70 s. `server/livekit_api.py` is what
swaps `services/session.js` for `services/session-lk.js`, and that router only mounts on
`ZAELAR_ENGINE=livekit`; without it the browser loads the legacy Pipecat client, 404s on
`/api/ice-servers`, `/api/offer` and `/api/hangup`, and that path has none of the boot-unblock safety
the LiveKit client grew. The operator opens their bookmark and gets a permanent splash.

So `--quiet` is a genuinely headless mode for batches nobody watches, and it says so when you use it.

Each agent joins its own room prefix (`lab-es`, `lab-us`), deliberately **not** derived from `zaelar`:
the voice worker admits any room whose name starts with its own prefix, so `zaelar-lab-es` would still
be accepted by the operator's real engine and their worker would race ours for our own room. `lab-es`
shares no prefix with `zaelar` in either direction.

## What the profile seeds, and what it must never seed

Written straight into the database before the engine boots — the fixed `state` row plus one pinned
pill per identity slot — and `config/settings.json` so the agent opens ready instead of on the
first-run wizard, with its language written down rather than guessed (the same code that guesses it
resolves the locale of `nucleo/flash/site_catalog.py`, so a wrong guess sends a Spanish errand to
`opentable.com`).

**Nothing about the errands goes in a profile.** No favourite sites, no "in Madrid people look for a
plumber at X", no preference a scenario is about to ask for. That is the operator's standing rule for
this tree — harden the RESOURCES, leave the REASONING open — and a profile that pre-loads the answer
measures the seed, not the agent.

Two things the lab copies from the operator's real install, both infrastructure and both for the same
reason (measuring the product against plumbing the product does not use measures something else):
`fast.providers`, the model ladder, and the STT/TTS provider pair, because an agent booted on the
engine's stock profile would call a provider nobody has credentials for and come up mute.

## Traps

- **`make run` kills the lab.** `scripts/run-livekit.sh` reaps every `python -m server` process by
  NAME, not by port. Starting a lab agent never touches a running engine; the reverse is not true.
- **The port is fixed and a busy port is an error**, not a reason to slide to another one. An agent
  that quietly moves is an agent you cannot find. If something else answers there, the CLI says so
  and stops.
- **`meteo-soria` writes into every fresh agent within seconds of boot** — it ships tracked in this
  repo and ticks hourly. Its pill is namespaced (`meteo-soria:weather:soria`) so the readers filter it,
  but it is visible in the memory map and it is the reason a plumber search once went to Soria.
- **Reset does not touch the credential store.** An isolated database is the point; a crippled engine
  that cannot call a model is not.
