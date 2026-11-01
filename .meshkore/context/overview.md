---
title: Overview
status: stable
---

# Zaelar — overview

Zaelar is a **personal operating system you talk to**: one voice agent that runs your agenda, your messages and
your errands, opens what you ask for as **widgets** on a canvas, and **remembers** who you are. Public tagline
(zaelar.com): «A personal agent you talk to — for your agenda, your messages and your errands. The Personal
Operating System.» It runs on its **own brain** — `nucleo/` («Colmena»: FlashBrain for the sub-second voice turn,
Brain Workers for errands that do not fit in a turn) — with its **own memory** (`memory/`, one SQLite file). No
external agent in the loop.

**Two ways to run the same engine** — one codebase, no fork:
- **Self-hosted, free**: clone `github.com/asimovia/zaelar` (Sustainable Use License 1.0, fair-code — `LICENSE.md`;
  never call it «open source» or «MIT»), `make run`, open `http://localhost:43917`. Your memory is one file on your
  machine; only the questions sent to your AI provider leave it.
- **Hosted**: a hosted version exists — see zaelar.com.

**What it does today**: voice in English and Spanish with barge-in and corrections; agenda with spoken reminders
that fire; WhatsApp / Telegram / email / Google connectors; a canvas of built-in widgets (agenda, lists, video, music,
maps, markets, timers…) driven by voice; **generated widgets** — describe one and it is written and kept in your Apps;
its own **browser** for errands; and **external services**: the agents available on the MeshKore network, external
MCP servers and third-party APIs, which give it access to bookings and thousands of other external services. Those
are external services Zaelar orchestrates, not part of this repository. Network detail:
`docs/architecture/zaelar-meshkore-network.md`.

**Source of truth**: `docs/product/zaelar-product.md` (onboarding) + `docs/architecture/zaelar-architecture.md`
(mental model). The public, curated story (and the claims we stand behind) is zaelar.com; `docs/` is the detail.
