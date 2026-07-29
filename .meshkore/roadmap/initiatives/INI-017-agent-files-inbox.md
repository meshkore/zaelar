---
id: INI-017
title: Agent Files Inbox — paste-image & drag-drop file upload
status: done
owner: ricart
modules: [files, frontend, server, voice, brains]
updated: 2026-07-08
---

## Goal

Let the operator hand zaelar a file — a screenshot, a PDF, a text export — using **native browser gestures**
(paste an image, drag & drop any file), with **no UI to open first**, so Hermes can read/summarize/analyze it on
request, and (future, out of scope here) act on it — e.g. "mándale este archivo a X por mail".

## Operator decisions (2026-07-07, taken up front)

Asked and confirmed via `AskUserQuestion` before implementation:

1. **How does Hermes "see" images/files**, given the ACP client only sends plain text and that's unverified to
   carry attachments? → **Save + let Hermes read the file itself** with its own filesystem tools (already
   auto-approved on operator voice/chat turns). Rejected alternative: probing whether the `hermes` CLI binary
   accepts ACP image content blocks — too speculative/risky for the payoff.
2. **A browse/manage widget for uploaded files?** → **Not now.** Files just need to land somewhere Hermes and
   the frontend can reach; a widget to navigate/present them is a **future**, dynamically-generated addition
   once there's an actual need.
3. **Scope of this delivery** → **All together**: both paste-image and drag-drop, in one pass (not phased).

A follow-up clarification (same day) tightened the storage model further: **one flat folder inside the repo**
(`files/`), **no organization, no metadata** for now — simplicity over a per-entity store like `widgets/_data/`.

## Why NOT multimodal (the load-bearing design call)

Investigated before writing code (see conversation research, and `.meshkore/docs/modules/zaelar-modules.md
§Files` for the permanent record): `livekit-agents`' `ChatContext` supports `ImageContent`, but neither
`voice/engine/llm/providers/hermes.py` nor `duo.py` reads it (`_last_user_text()` silently drops non-string
content). The Hermes ACP client (`brains/hermes/acp_client.py`) only ever builds a single
`{"type":"text",...}` prompt block — no verified attachment support in this codebase. Threading a real image
through `ChatContext`→ACP or through duo's OpenAI-compatible fast layer was judged unverified/risky versus the
much simpler and already-available mechanism: **save the file to disk, tell the brain via a `[SISTEMA]` note,
let Hermes read it with its own tools on the next relevant turn.** This satisfies the operator's actual asks
("resume this PDF", "look at this screenshot") without adding any new surface to the LLM plumbing.

## Architecture

```
Browser (frontend/app/main.js)
  paste (image)  ──┐
  drop (any file) ──┼──► uploadFile(file, source) ──► POST /api/files/upload (multipart)
                    │                                          │
                    │                                          ▼
                    │                              files/server_api.py
                    │                                          │
                    │                                          ▼
                    │                              files/store.py :: save_upload()
                    │                                 · sanitize name (basename, alnum/-_.)
                    │                                 · collision → numeric suffix, never overwrite
                    │                                 · atomic write (tmp + os.replace)
                    │                                 · files/uploads/  (gitignored, flat, no metadata)
                    │                                          │
                    │                                          ▼
                    │                          voice/brain_notes.push("[SISTEMA] … → ruta: <abs path>")
                    │                                          │
                    ▼                                          ▼
      store.pushChat({role:"sys", …})          hermes.py / duo.py drain() on next turn
      (confirmation line in ChatWall)           → Hermes reads the file with its OWN fs tools
                                                 → duo escalates via escalate_to_hermes if asked to read content
```

## Files touched

New module `files/`:
- `files/__init__.py` (empty, marks the package)
- `files/store.py` — `UPLOAD_DIR`, `_safe_name()`, `save_upload()`, `list_files()`
- `files/server_api.py` — `POST /api/files/upload`, `GET /api/files`

Edited:
- `server/__init__.py` — import + register `files_router` unconditionally (alongside `widgets_router` etc.)
- `.gitignore` — `files/uploads/`
- `frontend/app/main.js` — extended the existing global `paste` listener (image branch), added global
  `dragover`/`drop` listeners, added `uploadFile(file, source)` helper
- `frontend/app/components/ChatWall.js` — render a third `sys` role class (was `agent`/`you` only)
- `frontend/app/styles.css` — `.cw-msg.sys` (dashed border, `--hb-muted-2`, centered, italic)
- `.meshkore/public/cluster.yaml` — declared the `files` module
- `CLAUDE.md` — added `files/` to "Módulos declarados" + a "Decisiones clave" bullet
- `.meshkore/docs/modules/zaelar-modules.md` — full `§Files` section (design record, kept in sync with this doc)

## Verification (2026-07-07/08)

- `./.venv/bin/python -c "from server import create_app; create_app()"` → imports clean, no errors from the new
  module or its registration.
- `app.openapi()["paths"]` confirms `/api/files/upload` (POST) and `/api/files` (GET) are mounted.
- `fastapi.testclient.TestClient` round-trip: uploaded `captura.png` (`source=paste`) → 200 with
  `{name, path, size}`; uploaded a SECOND file with the same name (`source=drop`) → resolved to
  `captura_1.png`, original NOT overwritten; `voice.brain_notes` confirmed to have queued both
  `[SISTEMA]` notes (visible in the test run's log output); `GET /api/files` listed both files with correct
  size/mtime. Test files cleaned up after the check.
- Live stack restart verified: the app was already running (`make run-duo`, BRAIN=duo) from a previous session;
  killed cleanly (`SIGTERM` → `SIGKILL` on the lingering web process) and relaunched with the SAME command
  (`make run-duo`, preserving the operator's existing brain config) — `GET /api/files` responded `{"files":[]}`
  from the freshly-restarted process, confirming the new code is what's actually running at `:8473`.
- NOT yet verified by the operator: an actual paste/drop from the browser UI, and a live voice/chat turn asking
  Hermes to read an uploaded file's content. Flagged as the remaining acceptance step.

## Out of scope / deferred

- **Browse/manage widget** — deferred per operator decision; `files/store.py::list_files()` exists so this is a
  pure future addition (frontend/widget-generator only, no backend change needed).
- **Delete endpoint** — nothing needed it yet; add later mirroring `widgets/store.py::delete`'s pattern.
- **Real multimodal vision in the same turn** (`ImageContent`/ACP attachments) — deliberately not built; see
  "Why NOT multimodal" above. Revisit only if a concrete need for same-turn image analysis outweighs the risk of
  extending the ACP client / fast-layer message builder on unverified ground.
- **Sending a file by email / other actions on stored files** — the operator named this as a future use case
  the inbox enables, not something this change implements.
