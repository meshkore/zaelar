---
title: Connector inventory — what the engine connects to, and where each piece is wired
category: modules
updated: 2026-09-14
owner: ricart
status: current
---

# The connectors — the list

This is the **roll call**: every connector the engine knows about, live or merely declared, with the family
it belongs to, the widget it serves and where its truth lives. It is the answer to «what do we connect to
today, and what is still a wish».

It exists because there was no such list. Per-connector module docs existed (`zaelar-cloud-files.md`,
`zaelar-fotos-connector-and-widget.md`, `zaelar-video-widget-and-account-connector.md`,
`zaelar-google-connector.md`) and the connector *workflow* existed, but nothing said what the shelf HOLDS —
so nobody could tell, at a glance, that YouTube had been parked as `planned` for eight days after the reason
for parking it disappeared.

> **Keep it honest by DERIVING it, never by reading this file.** Two commands print the truth:
> ```bash
> ./.venv/bin/python -c "from connectors import registry; [print(d['family'], d['id'], d['label'], d.get('connected')) for d in registry.descriptors()]"
> ./.venv/bin/python -c "from connectors import catalog; [print(m['state'], m['family'], m['id'], m['label']) for m in catalog.load_manifests()]"
> ```
> And a ratchet (`tests/connectors/unit/catalog/test_a_built_connector_is_never_on_the_wishlist.py`, node
> 5.7) keeps the two halves from contradicting each other, which is the failure this table cannot prevent
> on its own.

## The two halves

| | `connectors/registry.py::descriptors()` | `connectors/catalog/*.json` |
|---|---|---|
| what it is | the **LIVE inventory**: built connectors and their real connection state | the **SHELF**: what is declared, including what we do not have |
| costs | a read per call | zero — a manifest is data, no prompt bytes, no imports |
| renders in | ⚙ → Conectores, the chat wall's «Conectores» tab (live half) | the chat wall's wishlist (`planned` + `not-possible` only) |
| `built` there means | it is real and its state is reported | «exists — let `search()` find it by its words»; it never renders |

A `built` manifest whose id has no live row is **invisible everywhere but `search()`**. That is right for
exactly two things today, and both say so in their own `notes`.

## Live connectors

| family | id | label | auth | widget | doc |
|---|---|---|---|---|---|
| mensajeria | `whatsapp` | WhatsApp | QR (Baileys bridge) | mensajeria | — |
| mensajeria | `telegram` | Telegram | app password (Telethon) | mensajeria | — |
| mensajeria | `email` | Email (IMAP/SMTP) | app password / **Gmail OAuth** | mensajeria | — |
| musica | `spotify` | Spotify | OAuth | musica | — |
| musica | `youtube-audio` | YouTube (free audio) | none | musica | — |
| archivos | `gdrive` | Google Drive | **Google OAuth** | archivos | `zaelar-cloud-files.md` |
| archivos | `onedrive` | OneDrive | OAuth (Microsoft) | archivos | `zaelar-cloud-files.md` |
| fotos | `google-photos` | Google Photos | **Google OAuth** | fotos | `zaelar-fotos-connector-and-widget.md` |
| video | `youtube` | YouTube (account) | **Google OAuth** | youtube | `zaelar-video-widget-and-account-connector.md` |
| agenda | `google` | Google Calendar | **Google OAuth** | agenda | `zaelar-google-connector.md` |
| infra | `google-account` | Google (account) | **Google OAuth** | — (serves the five above) | `zaelar-google-connector.md` |
| infra | `architect` | Architect (code daemon) | token | — | — |
| infra | `meshkore` | MeshKore (cluster / team) | cluster identity | — | `zaelar-meshkore-network.md` |

**Five of those doors are ONE account.** Everything marked *Google OAuth* resolves its client through
`connectors/google/app.py`; the `google-account` row is that client, reported once, with no value in the
payload. A per-connector name (`EMAIL_GMAIL_CLIENT_ID`, `CALENDAR_GOOGLE_CLIENT_ID`, …) still wins where it
is set. See `zaelar-google-connector.md`.

**Google Meet is not a row.** A Meet link is `conferenceData` on a calendar event, minted with the calendar
scope: it is an ARGUMENT (`meet: true`) of `add_meeting`/`update_meeting`, not something the operator
connects. `connectors/catalog/google-meet.json` exists only so `search()` finds the capability by name.

## Declared and not built

`planned` = we could and have not. `not-possible` = the door is shut, and the manifest says by whom.

| state | family | id | why |
|---|---|---|---|
| planned | mensajeria | `slack` | — |
| planned | musica | `apple-music` | its real gate is in the manifest |
| planned | video | `vimeo`, `dailymotion`, `twitch` | — |
| not-possible | musica | `amazon-music`, `deezer`, `soundcloud`, `tidal`, `youtube-music` | each names its own reason |
| not-possible | fotos | `apple-photos`, `amazon-photos` | — |
| not-possible | archivos | `icloud-drive` | — |

⚠️ **`planned` is a promise with an expiry.** `youtube` sat in `planned` from 2026-09-06 to 2026-09-14 with a
note saying it would be reactivated «the day a Google OAuth client exists» — the client arrived on the 12th
and the manifest did not move, so for two days the chat wall offered the operator a **«Lo quiero»** button
for a connector he already had. When a manifest parks something behind a CONDITION, the condition goes in
the note, and lifting it is the last step of whatever satisfies it.

## Where a connector is wired

The workflow doc (`../ops/zaelar-new-widget-or-connector-workflow.md`) owns the full list and the traps.
The short version, for reading this table: `connectors/<family>/` (providers · oauth · client · service ·
server_api) · `connectors/registry.py` · `connectors/catalog/<id>.json` · `server/__init__.py` routers ·
the widget's `manifest.json` (**the actions AND the words that route to them**) · `ConfigPanel.js` card +
family · `ChatWall.js` family order · `i18n/bundles/{en,es}.json` · `nucleo/flash/connector_briefs.py` ·
`tests/run_testmap.py` · this file.
