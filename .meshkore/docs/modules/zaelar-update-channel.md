---
title: Update channel (version number + «there is a new version»)
category: modules
updated: 2026-09-02
owner: ricart
status: current
---

# The update channel — one number a person can compare, one honest «do I have to reload?»

`update/` (engine) + `frontend/app/update/` (both shells). Delivered by **V2-553**.

It answers two questions and keeps them apart on purpose:

1. **«Which version am I on?»** — a plain incrementing integer, shown at the foot of the desktop's left column
   and updated live, so a browser left open for days watches the number climb.
2. **«Does this tab have to reload?»** — a bar across the top offering to reload, which appears **only** when
   the engine is serving frontend bytes this tab is not running.

## Why the payload has two fields and not one

A version number cannot answer question 2. It moves on **every** release, including the ones that change
nothing a browser executes — so using it to drive the bar means offering a reload after every backend fix.
So `GET /api/update` publishes both:

| field | what it is | who reads it |
|---|---|---|
| `build` | the user-facing integer, from `update/BUILD` | the badge |
| `ui_rev` | digest of the bytes the browser runs (`frontend/**`, browser-fetchable extensions) | the bar |
| `version`, `sha`, `short` | the existing seal from `version.py` | the badge's tooltip |
| `started_ms`, `deploy` | which process, and which deployment answered | diagnosis |

Everything is constant after the first call, which is what makes the endpoint cheap enough for every open tab
to poll: **8.1 ms once** to hash 74 files / ~2 MB, then **25 µs** per call.

## Three decisions that are not obvious, with the reason

**The number lives in a FILE, not in git.** There is no repository inside a deployed Machine — the
`Dockerfile` does not `COPY .git`, so `version.sha()` returns `"nogit"` in production and always has. A plain
text file is the only source of truth that survives into the image intact. The consequence is a release step:
`python -m update bump`, committed, before the tag. The tag gate in `.github/workflows/release.yml` refuses a
release whose build number did not move, because forgetting it is silent — every browser reloads and the
badge still reads yesterday's number.

**The digest is of CONTENT, never of timestamps.** A Docker `COPY` and a fresh `git clone` both invent
mtimes. An mtime digest would announce a phantom update on every deployment, and would stay silent about a
real one whose file was written with an older timestamp. Content costs the same and cannot be wrong about
this. Any failure returns the sentinel `"unknown"`, and the client refuses to act on it: an empty digest is a
perfectly stable value that every client would compare against happily, leaving the channel mute forever with
nobody noticing.

**A tab learns its own revision from the FIRST answer it gets.** The page was served by that same process
moments earlier, so that answer describes the code running in the tab — no revision has to be stamped into
`index.html` at build time, which would put a build step in front of a file that is edited by hand. The
residual race is ~0 s wide (a restart between the page being served and the first check) and is why the first
check fires the instant the module loads rather than on the first interval.

## Poll, not SSE — and the SSE argument is the interesting one

A version can only change when the process changes, and a new process breaks every open SSE connection: «the
stream reconnected» would already be the news. It is still a poll because the *other* half has to keep
working — the number must keep climbing in a browser open for three days and in a PWA whose tab has been
backgrounded for hours. One request of ~200 bytes against a fully cached dict, less than the `/api/status`
poll already running, and **zero requests while the tab is hidden**. Returning to a tab checks immediately.

## Where the two surfaces live, and why one of them is not where it looks

`UpdateSurface.js` is one entry in the canonical `core/system-surfaces.js` list and renders two fixed
elements:

- **The bar** (`#hb-upd-bar`, z-index 100200 — above everything else in the app, whose maximum is 100020).
  Clicking anywhere on it reloads; ✕ dismisses **that revision only**, in memory, never persisted: the fix
  for staleness is a reload, which clears the dismissal by definition, while a dismissal remembered across
  reloads could hide a real update forever.
- **The badge** (`#hb-upd-ver`) at the foot of the widget rail's column — but **not inside `WidgetRail.js`**,
  because the rail hides itself whenever the canvas is empty, and a version number you can only read while a
  widget happens to be open is not a version number you can read. It steps aside when the rail is folded
  through `body:has(#wrail.folded)`, which is why this file holds no reference to the rail at all.

The bar writes `--banner-h`, a custom property that already existed in `core/palette.css` documented as
*«height of the update banner when visible (0 when hidden) — top controls shift down by this»*, with `.tr` and
`.me` already consuming it through a `calc()` and a 0.2 s transition. The seam was built for this banner and
had never had a writer, so no layout CSS changed. Widget cards deliberately do not move: placement already
reserves the top 70 px (`Desktop.tile.top`), more than the bar occupies, so V2-551's guarantee that a card is
always whole and reachable still holds with the bar up.

The **mobile shell gets the bar and not the badge** (`UpdateSurface({badge:false})`): its bottom edge belongs
to the dock. An installed PWA is the surface most likely to be running code from days ago, which is why it
gets the bar first. Where the number belongs on a phone is still open.

## The constraint this module was built under

The operator's words: *«que no ensucie el código actual del agente… que sea como una especie de componente de
librería o módulo»*. Two touch points, and a test that counts them — `git grep` for `import update` across
`nucleo/ voice/ memory/ widgets/ connectors/ bus/ observability/` must come back empty:

- `server/__init__.py` mounts the router;
- the `Dockerfile` ships the package (and its guard, `test_docker_boot_copy.py`, already refuses a top-level
  package with no `COPY`).

## Operating it

```bash
python -m update            # what this tree would report — the endpoint's payload, verbatim
python -m update bump       # raise the build number by one, print it (a release step, never runtime)
curl -s localhost:43917/api/update
```

Tests: node **7.29** (engine) and node **4.103** (rendered — the bar, the badge, and the rule that a
backend-only release moves the number and shows no bar).
