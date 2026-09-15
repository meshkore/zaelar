---
title: The contacts connector — one address book, two copies, one rule
category: modules
updated: 2026-09-15
owner: ricart
status: current
---

# `connectors/contacts/` — one address book, two copies, one rule

**Related:** `zaelar-widget-header-standard.md` (the bars and the plug button this is reached through) ·
`zaelar-google-connector.md` (the shared OAuth app) · `widgets/directory.py` (who a name is, and how to
reach them).

```
connectors/contacts/
├─ providers.py      where a contact can come from, and what each tier costs in consent
├─ oauth.py          PKCE, tokens in .meshkore/credentials/contacts_oauth.json
├─ google_people.py  the People API, and the two shapes: person→contact, contact→person
├─ service.py        fetch() and push() — never touches the widget's store
└─ server_api.py     /api/contacts/{status,connect,callback,disconnect}

widgets/contactos/
├─ gcontacts.py      the GLUE (the agenda's gcal.py, one for one): providers(), sync(), sync_state()
└─ data.py           _merge_imported() — the MERGE, because this is the store's own judgement
```

## The boundary, and why it is where it is

**The connector FETCHES and PUSHES. The widget MERGES.** `connectors/contacts/service.py` never opens
`widgets/_data/contactos/state.json`; the widget is the only module that knows which fields the operator
typed himself, and a connector reaching into that store would be a second writer of a record with no
arbitration.

So «did it sync?» is always a COUNT the widget produced, never one claimed from the connector.

## Who wins — the one rule

The operator asked for a two-way link:

> «Si se modifica algo en nuestro agente, un nombre, un teléfono, también se modifica en Google. Eso sería
> lo más interesante, lo más simple a nivel gráfico y lo más fácil de comprender por parte de los usuarios.
> Además estaría unificado como por ejemplo en la agenda, Google Calendar.»

That makes «who wins» a question every pass has to answer, and the answer is **whoever touched the row
last** — which `updated` has recorded since V2-541.

```
  ┌── PUSH ──┐  rows whose local `updated` is newer than the last completed sync
  │          └→ update_person (read-modify-write) · create_person for rows Google has never seen
  │
  └── PULL ──┐  everything Google returns
             └→ _merge_imported: fills in ONLY what is empty here
```

⚠️ **PUSH runs before PULL, and the order is load-bearing.** Pulling first would fetch a stale Google row,
merge it in, and then push the result back — laundering a stale value into a fresh one.

⚠️ **The pull never overwrites a non-empty local field.** A pass that undid a correction he had made would
leave him unable to tell which of the two surfaces was lying. The ★ travels one way only: starring in
Google stars here; un-starring there never un-stars the favourite he set on this card.

## How a Google person is matched to a row here

Four keys, descending by how much they PROVE. Each one can be right while the ones below it are wrong:

1. **`googleId`** — the same resource as last time. Survives him renaming the person here.
2. **the email address**, wherever it lives (the stored field or an email channel). An address is an
   account, so two rows sharing one are one person — V2-693's Telegram rule.
3. **name + city** — `add_contact`'s own rule, so the two doors agree.
4. **the name ALONE, only when exactly one contact here carries it.** This is what makes a re-import
   idempotent: Google routinely knows a city he never typed, so name+city alone would import a second
   «Marta Ruiz» on every pass. When two contacts share the name it stops — adding a duplicate he can merge
   beats silently folding two people into one, which he cannot undo.

## Two traps in the People API, both already paid for elsewhere

⚠️ **An update needs the person's current `etag`**, and that is a feature: it is what stops us overwriting
an edit he made on his phone since we last read. Every update is a READ-MODIFY-WRITE — the shape V2-697's
calendar RSVP had to become when a PATCH carrying an array silently replaced it.

⚠️ **`updatePersonFields` is a whitelist and everything listed is REPLACED.** A field we name but do not
send is CLEARED on Google's side. So the body is built from the values present and the mask from the body,
never from a constant — a constant mask would delete, on Google, every field that happens to be empty here.

## Scopes, and the one thing still missing

| Tier | Scopes | Google's tier |
|---|---|---|
| `saved` (default) | `contacts.readonly` | sensitive |
| `saved+other` | `+ contacts.other.readonly` | sensitive |
| `sync` | `contacts` (read-write) | sensitive |

Read-only is the default on purpose: nobody gets write without choosing it. `service.can_write()` reads the
flag off the **granted** tier, never off a guess — the widget has to be able to say «solo puedo traer»
honestly.

⚠️ **The `sync` tier does not work yet.** As of 2026-09-15 the consent screen carries `contacts.readonly`
and `contacts.other.readonly` only; `https://www.googleapis.com/auth/contacts` must be added in the Google
Cloud console before anyone can consent to it. The card says so out loud rather than offering a promise
Google would refuse. Everything else is built and tested.

## What is NOT built

- **A live link.** He asked for it («cuando se crea un contacto en Google, automáticamente aparecerá en
  nuestro sistema»). The People API has no push for a personal account; the honest implementation is a
  periodic pass using `syncToken`, and it is not written. Today the sync is his click.
- **iCloud and CardDAV.** Visible in the strip, inert, and honest about it (see the header standard).
- **Live verification.** No real Google address book has travelled this path yet.
