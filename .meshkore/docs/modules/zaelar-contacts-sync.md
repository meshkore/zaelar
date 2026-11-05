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
reach them — the ranking, groups and contacts in memory: `zaelar-architecture.md` §5h-ter).

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

The link is two-way: a name or a phone changed in the agent is changed in Google too, the same way the
agenda mirrors Google Calendar.

That makes «who wins» a question every pass has to answer, and the answer is **whoever touched the row
last** — which each row's `updated` records.

```
  ┌── PUSH ──┐  rows whose `touchedAt` is newer than their `pushedAt` — he changed it, Google has not
  │          │  been told · plus `sync.pendingDeletes`, the rows he removed HERE
  │          └→ update_person (read-modify-write) · create_person · delete_person
  │
  └── PULL ──┐  what the SYNC TOKEN says changed (or everything, on the first pass and after an expiry)
             └→ _merge_imported · _drop_deleted
```

## It stays on

Sync is not a one-off import: once switched on it stays connected, both ways, so the agent and Google
Contacts mirror each other — including changes made on a phone that syncs to the same Google account.

The control is a **switch**, not a button: a button is a one-off by its grammar, whatever its label says.
`sync.auto` is the state, `set_auto` writes it (declared, so it is reachable by voice), and
`widgets/background.py` calls `data.tick` on the manifest's cycle. The period lives in `gcontacts.PERIOD`,
not in the manifest — the scheduler wakes the module far more often than it should talk to Google, so a
card reopening never triggers a pass and the interval can change in one place. The card reads it from
`sync_state().every` rather than carrying a number nobody keeps in step.

⚠️ **It is a POLL because the People API has no push for a personal account.** «Permanently connected» is,
physically, a cheap question asked on a timer — and the SYNC TOKEN is what makes it cheap. A large address
book spans several pages; a full re-read every minute is a request budget spent to learn that nothing
happened. With a token a quiet minute is ONE round-trip that returns no people. A change lands within one
period rather than instantly.

Two rules of Google's govern the token, and both are load-bearing:

- **`sortOrder` may not be combined with a sync request** — it is «only used if sync is not requested». The
  sort was the half worth losing; the merge matches on identity, not on arrival order.
- **«When the syncToken is specified, all other request parameters must match the first call.»** So there
  is exactly ONE parameter set in `list_people`, not a full one and an incremental one that can drift.

An expired token (429 `EXPIRED_SYNC_TOKEN`, or 410 on older deployments) is retried once as a full read —
Google's own documented remedy — and the operator never sees it. A **truncated** read throws its token
away: a pass that stopped at `max_pages` never saw the last pages, and a token stamped there would make
everything it skipped invisible forever, with the card honestly reporting «sin cambios» about a question it
never asked.

### The clock that stops the storm

⚠️ **`updated` is a DATE, and a date cannot say «he changed it after we last sent it».** It says «today»
for the rest of the day. On a timer, a date rule would mean a PATCH per edited contact per minute — each one
succeeding and writing the same values. So a local write stamps `touchedAt` and a successful push stamps
`pushedAt`, and «ours» is one comparison of two clocks. Rows written before either existed fall back to the
date rule ONCE, and the push that follows moves them onto the precise path.

⚠️ **An import filling in a blank must NOT stamp `touchedAt`.** It is Google's doing, not his — stamping it
there sends Google its own value straight back, every minute, forever.

### A change made on his phone

The phone writes to Google, Google hands it to us through the token, and the merge takes it: a row that
arrived through a sync token is one Google CHANGED, and if we have nothing pending on it then Google
touched it last. That is the one case where the pull may REPLACE a value instead of only filling a blank,
and it is exactly what makes this a sync rather than a repeated import. A **full** re-read is never
authoritative — there «changed» is unknown, and treating every row as fresh would undo his corrections
wholesale on the first pass after an expiry.

### Deletions, in both directions, with a breaker

A mirror that reflects every change except a deletion is not a mirror: the row comes back on the next full
re-read and he has no way to tell why.

- **Google → here**: the token returns deleted people as a person carrying `metadata.deleted` and nothing
  else — no name, no email — so `list_people` separates them out. Handing one to the shaper returns None
  and the deletion vanishes silently.
- **Here → Google**: a pull can never carry this half. Once the row is gone from the store there is nothing
  left to compare, so `remove_contact` writes the intention into `sync.pendingDeletes` and the next push
  spends it. The queue is cleared only on a pass that actually reached Google.
- **A row he edited since we last sent it is not Google's to delete.** He touched it last — the same rule
  as every other conflict, applied to the direction that cannot be undone.

⚠️ **`_DELETE_CAP_SHARE` / `_DELETE_CAP_ROWS` are a circuit breaker around OUR OWN code, not a theory about
how many contacts a person deletes in a minute.** The failure mode of a sync token gone wrong is
«everything looks deleted», and the difference between a bug and a catastrophe is whether anything acted on
it. When it trips, nothing is removed and the card SAYS SO — a guard that protects silently is one he
cannot trust and cannot act on.

⚠️ **PUSH runs before PULL, and the order is load-bearing.** Pulling first would fetch a stale Google row,
merge it in, and then push the result back — laundering a stale value into a fresh one.

⚠️ **The pull never overwrites a non-empty local field.** A pass that undid a correction he had made would
leave him unable to tell which of the two surfaces was lying. The ★ travels one way only: starring in
Google stars here; un-starring there never un-stars the favourite he set on this card.

## How a Google person is matched to a row here

Four keys, descending by how much they PROVE. Each one can be right while the ones below it are wrong:

1. **`googleId`** — the same resource as last time. Survives him renaming the person here.
2. **the email address**, wherever it lives (the stored field or an email channel). An address is an
   account, so two rows sharing one are one person — the same rule the Telegram import follows.
3. **name + city** — `add_contact`'s own rule, so the two doors agree.
4. **the name ALONE, only when exactly one contact here carries it.** This is what makes a re-import
   idempotent: Google routinely knows a city he never typed, so name+city alone would import a second
   «Marta Ruiz» on every pass. When two contacts share the name it stops — adding a duplicate he can merge
   beats silently folding two people into one, which he cannot undo.

## Two People API rules the code is built around

⚠️ **An update needs the person's current `etag`**, and that is a feature: it is what stops us overwriting
an edit he made on his phone since we last read. Every update is a READ-MODIFY-WRITE — the same shape the
calendar RSVP uses, because a PATCH carrying an array silently replaces it.

⚠️ **`updatePersonFields` is a whitelist and everything listed is REPLACED.** A field we name but do not
send is CLEARED on Google's side. So the body is built from the values present and the mask from the body,
never from a constant — a constant mask would delete, on Google, every field that happens to be empty here.

## Scopes

| Tier | Scopes | Google's tier |
|---|---|---|
| `saved` (default) | `contacts.readonly` | sensitive |
| `saved+other` | `+ contacts.other.readonly` | sensitive |
| `sync` | `contacts` (read-write) | sensitive |

Read-only is the default on purpose: nobody gets write without choosing it. `service.can_write()` reads the
flag off the **granted** tier, never off a guess — the widget has to be able to say «solo puedo traer»
honestly.

⚠️ **The `sync` tier needs the `contacts` scope on the consent screen.** The Google OAuth client in use must
list `https://www.googleapis.com/auth/contacts` (Google Cloud console) before anyone can consent to it; when
it is absent the card says so rather than offering a write Google would refuse.

## Extension point

The provider strip already reserves places for **iCloud and CardDAV** (see the header standard); a new source
plugs in as a provider in `connectors/contacts/providers.py` behind the same fetch/push boundary.
