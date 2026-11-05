---
title: Connector inventory — what the engine connects to, and where each piece is wired
category: modules
updated: 2026-09-14
owner: ricart
status: current
---

# The connectors — the list

This is the **roll call**: every connector the engine knows about, with the family it belongs to, the widget
it serves and where its truth lives. Per-connector detail lives in the module docs (`zaelar-cloud-files.md`,
`zaelar-fotos-connector-and-widget.md`, `zaelar-video-widget-and-account-connector.md`,
`zaelar-google-connector.md`); the connector *workflow* lives in ops. This page says what the shelf HOLDS.

Connectors are the operator's own accounts. Beyond them, Zaelar orchestrates EXTERNAL services — the agents of
the MeshKore network, external MCP servers and third-party APIs — which give it access to bookings and
thousands of external services without a connector of its own for each (`zaelar-meshkore-network.md`).

> **Keep it honest by DERIVING it, never by reading this file.** Two commands print the truth:
> ```bash
> ./.venv/bin/python -c "from connectors import registry; [print(d['family'], d['id'], d['label'], d.get('connected')) for d in registry.descriptors()]"
> ./.venv/bin/python -c "from connectors import catalog; [print(m['state'], m['family'], m['id'], m['label']) for m in catalog.load_manifests()]"
> ```
> And a ratchet (`tests/connectors/unit/catalog/test_a_built_connector_is_never_on_the_wishlist.py`, node
> 5.7) keeps the two halves from contradicting each other, which this table cannot guarantee on its own.

## The two halves

| | `connectors/registry.py::descriptors()` | `connectors/catalog/*.json` |
|---|---|---|
| what it is | the **LIVE inventory**: built connectors and their real connection state | the **SHELF**: what is declared, including what we do not have |
| costs | a read per call | zero — a manifest is data, no prompt bytes, no imports |
| renders in | ⚙ → Conectores, the chat wall's «Conectores» tab (live half) | the chat wall's wishlist (`planned` + `not-possible` only) |
| `built` there means | it is real and its state is reported | «exists — let `search()` find it by its words»; it never renders |

A `built` manifest whose id has no live row is **invisible everywhere but `search()`**. That is right for a
capability that is reached through another connector, and such a manifest says so in its own `notes`.

## A source can serve MORE THAN ONE family

`family` is still a single string and every view in the engine reads it unchanged; `families` is the full
list and **`registry.serves(descriptor, family)` is the only reader**. Telegram and WhatsApp, for example, are
contact sources as well as message channels, and they deliberately appear in BOTH cards: a connector shown in
every widget it serves is clearer than one the operator has to look for.

What a contact source owes the Contactos card: a normalised `{contacts, groups}` payload published on
`connector.contacts` when asked on `msg.contacts`, and NOTHING written to the store (`widgets/contactos/
imports.py` folds it in). The contract is IMPORT-ONLY — no platform here has an address-book write API, so
an edit or a deletion in zaelar never travels back, and the card says so.

## Live connectors

| family | id | label | auth | widget | doc |
|---|---|---|---|---|---|
| mensajeria **+ contactos** | `whatsapp` | WhatsApp | QR (Baileys bridge) | mensajeria, contactos | — |
| mensajeria **+ contactos** | `telegram` | Telegram | QR (Telethon) with the install's own app (`TG_API_ID`/`TG_API_HASH` env); own api_id/api_hash optional | mensajeria, contactos | — |
| mensajeria | `email` | Email (IMAP/SMTP) | app password / **Gmail OAuth** | mensajeria | — |
| musica | `spotify` | Spotify | OAuth | musica | — |
| musica | `youtube-audio` | YouTube (free audio) | none | musica | — |
| archivos | `gdrive` | Google Drive | **Google OAuth** | archivos | `zaelar-cloud-files.md` |
| archivos | `onedrive` | OneDrive | OAuth (Microsoft) | archivos | `zaelar-cloud-files.md` |
| fotos | `google-photos` | Google Photos | **Google OAuth** | fotos | `zaelar-fotos-connector-and-widget.md` |
| video | `youtube` | YouTube (account) | **Google OAuth** | youtube | `zaelar-video-widget-and-account-connector.md` |
| agenda | `google` | Google Calendar | **Google OAuth** | agenda | `zaelar-google-connector.md` |
| infra | `google-account` | Google (account) | **Google OAuth** | — (serves the Google rows above) | `zaelar-google-connector.md` |
| infra | `architect` | Architect (code daemon) | token | — | — |
| infra | `meshkore` | MeshKore (cluster / team) | cluster identity | — | `zaelar-meshkore-network.md` |

**All the Google doors are ONE account.** Everything marked *Google OAuth* resolves its client through
`connectors/google/app.py`; the `google-account` row is that client, reported once, with no value in the
payload. A per-connector name (`EMAIL_GMAIL_CLIENT_ID`, `CALENDAR_GOOGLE_CLIENT_ID`, …) still wins where it
is set. See `zaelar-google-connector.md`.

**Google Meet is not a row.** A Meet link is `conferenceData` on a calendar event, minted with the calendar
scope: it is an ARGUMENT (`meet: true`) of `add_meeting`/`update_meeting`, not something the operator
connects. `connectors/catalog/google-meet.json` exists only so `search()` finds the capability by name.

## Catalogue states

Besides `built`, a manifest can be `planned` (a connector the catalogue offers for the wishlist) or
`not-possible` (the provider exposes no third-party door, and the manifest names why). Both render only in
the chat wall's wishlist; the second command above prints the current shelf.

⚠️ **When a manifest parks something behind a CONDITION, the condition goes in the note, and lifting it is
the last step of whatever satisfies it** — otherwise the wishlist keeps offering a connector the operator
already has.

## Where a connector is wired

The workflow doc (`../ops/zaelar-new-widget-or-connector-workflow.md`) owns the full list and the traps.
The short version, for reading this table: `connectors/<family>/` (providers · oauth · client · service ·
server_api) · `connectors/registry.py` · `connectors/catalog/<id>.json` · `server/__init__.py` routers ·
the widget's `manifest.json` (**the actions AND the words that route to them**) · `ConfigPanel.js` card +
family · `ChatWall.js` family order · `i18n/bundles/{en,es}.json` · `nucleo/turn/prompt/catalogs.py` ·
`tests/run_testmap.py` · this file.
