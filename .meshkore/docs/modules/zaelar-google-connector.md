---
title: The Google connector — one account, six doors
category: modules
updated: 2026-09-14
owner: ricart
status: current
---

# `connectors/google/` — one account, six doors

Five connectors in this engine authenticate against Google, and before V2-685 each one asked for the SAME
OAuth client under a different name: `EMAIL_GMAIL_*`, `CALENDAR_GOOGLE_*`, `VIDEO_YOUTUBE_*`,
`PHOTOS_GOOGLE_PHOTOS_*`, `FILES_GDRIVE_*`. Answer one and the other four stay dormant, in silence.

`connectors/google/` answers the question once. It is a **LEAF**: nothing in it imports another connector,
because everything else imports it.

```
connectors/google/
├─ app.py        the CLIENT — who we are to Google
├─ services.py   the six doors, and what each one needs
└─ brain.py      the sentences the two brains get
```

## `app.py` — resolving the client

Order, and it is deliberate:

1. `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in the credential store — the operator's own, wins.
2. `.meshkore/credentials/google-connector-client_secret_*.json` — the file the Google Cloud console hands
   you, read **verbatim**. Nothing is retyped into a source file, so no second copy can drift.

Cached on `(path, mtime_ns)`: a file dropped in while the engine runs is seen without a restart. A value
frozen at import would have meant restarting the engine to be believed.

`status(origin)` reports WHERE the client came from (`operator` | `shipped` | none) and **never what it is**.

**Each connector's own name still wins.** That is what keeps the self-host story honest, and it is also what
makes the change safe: Outlook authenticates against Microsoft and gets nothing from here — handing it a
Google client would turn a dormant connector into a broken one, which is the counterweight the tests care
about most.

## `services.py` — the six

`gmail` · `calendar` · `meet` · `drive` · `photos` · `youtube`.

It **does not own the scopes of a connector that has its own registry**. Each already declares them next to
the client that requests them, this package sits BELOW those connectors and cannot import them to check,
and two copies of a scope list drift. It fills in `scopes` only for a service with no connector at all,
which today means exactly one: Meet.

**Meet asks for nothing extra.** A Meet link is `conferenceData` on a calendar event, minted by the calendar
scope the connector already holds. There IS a standalone Meet REST API behind
`https://www.googleapis.com/auth/meetings.space.created`; it is named in `FUTURE_SCOPES` and **deliberately
not requested** — an unused sensitive scope buys nothing today and costs a harder Google verification for
every user of the app.

⚠️ **`conferenceDataVersion=1` is the half that fails silently.** Without that query parameter Google returns
200, creates the event, and DROPS the conference: no error, no link, and an agent that has just told the
operator it made them a meeting room.

## `brain.py` — what the model is told

Three states: no client / a client but no consent / connected. When Meet is live it emits the sentence that
NAMES THE ARGUMENT — «se pide en el MISMO `add_meeting`/`update_meeting` de la agenda con `meet: true`, no
hay ninguna tool aparte».

That sentence is load-bearing. Meet is a verb this engine has never had, so a model told only that the
capability exists has no prior behaviour to fall back on except inventing a `create_meet` tool or promising
a link before Google minted it. **Naming a capability without naming its mechanism is what makes a model
improvise one** — the third payment of V2-603's receipt.

Workers need no exception: they reach it through `act widget_data`, already allowed and gated on the
widget's own manifest.

## Registering the client

⚠️ It is a **web** client, not «installed»: Google refuses a redirect URI it has never seen — with
`invalid_client`, at the END of a flow that looks healthy all the way up. The engine prints the exact list:

```bash
./.venv/bin/python -c "from connectors.google import app; print(*app.redirect_uris(), sep='\n')"
```

Those go in *APIs y servicios → Credenciales → el cliente → URI de redirección autorizados*.

## Connecting, by hand or by voice

The consent itself is always the **operator's click**: the popup only survives inside the gesture that
opened it, which is why `widget.js` opens the window synchronously and fills its `location` afterwards.

So the voice does the half it can (V2-686): `agenda:connect` leaves the card ON its connect step, and the
manifest tells the model to say «press Conectar Google Calendar». The URL the action returns reaches nobody
by itself — the turn report keeps `{widget, act}` and discards the result — which is why the sentence has to
be declared rather than returned.

## Answering an invitation (V2-697)

An RSVP is one field of one row of the event's `attendees` array — and that is exactly what makes it
dangerous, because **in the Google API a PATCH carrying an array REPLACES it**. Sending only our own row
would delete every other guest from the organizer's meeting and return 200 while doing it.

So `service.rsvp(meeting, answer)` is a **read-modify-write**, and deliberately does NOT go through
`patch_event`: that door rebuilds the whole body from `meeting_to_event`, which would re-send title, times
and an attendee list rebuilt from bare names, on somebody else's event where we are a guest and not the
organizer. Instead it reads the live event back (`get_event`), edits OUR row alone — located by
`meeting["selfEmail"]`, captured at import — and sends the whole roster up again.

It needs no new scope: the connector already holds `https://www.googleapis.com/auth/calendar`.

**What the import captures, and why `attendees` did not change shape.** `event_to_meeting` writes a rich
`guests` list (`{name, email, rsvp, organizer}`) **alongside** the plain `attendees` list of names, from the
same roster in the same pass, so the two cannot drift. `attendees` stays `list[str]` because seven callers
already read it that way — the voice payloads (`widgets/agenda/details.py::_norm_attendees`), the errand
booker, the digest line, and the write direction that turns it back into Google bodies. A meeting the
operator dictated simply has no `guests`.

⚠️ **`status` changed meaning, and the change is the fix.** It used to be the OPERATOR's own
`responseStatus` while the card labelled it «sin confirmar por la otra parte» — so an invitation he had
accepted read as though THEY had agreed. Now `status` is about the other guests (`_others_status`) and his
own answer is `myRsvp`. A guest whose answer Google does not report leaves the meeting **pending** on
purpose: not knowing is not the same as being confirmed.

⚠️ **`meetLink` is attacker-controlled.** Anybody who can send the operator an invitation writes
`conferenceData`, and the card turns that string into an `href` — so only `http`/`https` survive the import,
and the widget refuses it again at the sink for rows stored before that guard existed. Only a **video**
entry point is ever stored: the phone bridge and its PIN never reach the card, by the operator's own
scoping.

## Limits worth knowing

- The YouTube Data API does **not** return watch history (empty for every account since 2016). The video
  widget owns its own history because we play the video — see `zaelar-video-widget-and-account-connector.md`.
- Google Photos is read through the **picker**, not a library scope — see
  `zaelar-fotos-connector-and-widget.md`.
