# Public comment-language migration

Status: **in progress**

## Goal

Translate every source-code comment, docstring, inline developer explanation, and developer-facing
maintenance note in this public repository into English. Runtime product text, localization bundles,
voice responses, examples that intentionally exercise Spanish, and user-facing keywords are excluded.

## Resume protocol

1. Read this file before editing.
2. Run `python tools/comment_language_audit.py <directory>` from `engine/`.
3. Work in lexical path order, one file at a time.
4. Translate only internal comments/docstrings/maintenance notes; preserve executable behavior.
5. Run the audit again for the file. Classify intentional runtime Spanish separately.
6. Mark the file complete in the ledger below and commit the ledger update with the edits.
7. Never revisit a file marked complete unless a later code change adds or modifies a comment in it.

The audit is deliberately conservative and reports likely matches; it is not proof that a line is an
internal comment. A completed file must therefore be reviewed, not blindly mass-rewritten.

## Ledger

| Scope | Status | Next action |
|---|---|---|
| `widgets/` | complete | Audited clean with `python3 tools/comment_language_audit.py widgets` |
| `server/` | complete | Audited clean with `python3 tools/comment_language_audit.py server`; py_compile passed |
| `config/` | complete | Audited clean with `python3 tools/comment_language_audit.py config`; py_compile passed |
| `bus/` | complete | Audited clean with `python3 tools/comment_language_audit.py bus`; py_compile passed |
| `connectors/` | complete | Audited clean with `python3 tools/comment_language_audit.py connectors`; py_compile passed by package |
| `memory/` | in progress | Continue after `memory/queue.py`; `__init__.py`, `concepts.py`, `db.py`, `graph.py`, `journal.py`, and `queue.py` are clean |
| `nucleo/` | pending | Process after memory |
| `frontend/` | pending | Process after nucleo; exclude vendored/minified assets |
| root engine files | pending | Process after directories |
| `.meshkore/` public developer docs | pending | Audit and translate internal documentation separately |

## Completed files

- `widgets/actions.py` — translated comments and docstrings; behavior unchanged.
- `widgets/agenda/data.py` — translated comments and docstrings; preserved spoken-language parsing literals and UI/runtime data.
- `widgets/agenda/notes.md` — translated developer maintenance notes; behavior unchanged.
- `widgets/agenda/widget.js` — translated maintenance comments; preserved UI/runtime text.
- `widgets/aliases.py` — translated comments and docstrings; preserved runtime messages.
- `widgets/background.py` — translated module documentation, comments, docstrings, and developer log messages; behavior unchanged.
- `widgets/brief.py` — translated comments and docstrings; preserved executable prompt text.
- `widgets/clock/data.py` — translated comments; behavior unchanged.
- `widgets/clock/widget.js` — translated comments; preserved UI date labels.
- `widgets/confirm.py` — translated comments and docstrings; preserved Spanish yes/no recognition patterns and runtime prompt text.
- `widgets/generator.py` — translated comments and docstrings; preserved executable generation contract strings and Spanish id filler/runtime examples.
- `widgets/inversiones/data.py` — translated comments; preserved UI/runtime Spanish text.
- `widgets/inversiones/notes.md` — translated developer design notes; behavior unchanged.
- `widgets/inversiones/widget.js` — translated comments; preserved UI/runtime Spanish text.
- `widgets/juego-serpiente-snake/data.py` — translated comments; preserved UI/runtime Spanish text.
- `widgets/juego-serpiente-snake/widget.js` — translated comments; preserved UI/runtime Spanish text.
- `widgets/lifecycle.py` — translated comments, docstrings, and lifecycle memory/log text; preserved behavior.
- `widgets/mensajeria/data.py` — translated comments and docstrings; preserved UI/runtime Spanish text and routing vocabulary.
- `widgets/mensajeria/notes.md` — translated developer architecture/design notes; behavior unchanged.
- `widgets/mensajeria/owner.py` — translated comments, docstrings, and developer logs; behavior unchanged.
- `widgets/mensajeria/triage_agent.py` — translated comments and docstring; behavior unchanged.
- `widgets/mensajeria/widget.js` — translated comments; preserved UI/runtime Spanish text and labels.
- `widgets/meteo-soria/data.py` — translated comments/docstring and background memory summary; preserved Spanish weather UI labels.
- `widgets/meteo-soria/widget.js` — translated comments; preserved UI/runtime Spanish text.
- `widgets/meteo-tarragona-grafico/data.py` — translated comments; preserved Spanish weather UI labels.
- `widgets/meteo-tarragona-grafico/widget.js` — translated comments; preserved UI/runtime Spanish text.
- `widgets/migrate_aliases.py` — translated comments and developer CLI messages; preserved Spanish aliases as functional identity data.
- `widgets/musica/data.py` — translated comments and docstrings; preserved UI/runtime Spanish text and action strings.
- `widgets/musica/widget.js` — translated comments; preserved UI/runtime Spanish text and labels.
- `widgets/navegador/act_api.py` — translated comments and docstrings; preserved endpoint/action strings.
- `widgets/navegador/agent.py` — translated comments and docstrings; preserved executable prompts/tool text.
- `widgets/navegador/auth_memory.py` — translated comments, docstrings, memory text, and developer logs; preserved state keys.
- `widgets/navegador/data.py` — translated comments, docstrings, and coach context; preserved runtime UI/error strings.
- `widgets/navegador/notes.md` — translated developer notes; behavior unchanged.
- `widgets/navegador/owner.py` — translated comments and docstrings; preserved runtime/user-facing Spanish behavior.
- `widgets/navegador/tasks.py` — translated comments and docstrings; preserved Spanish task routing vocabulary and user-facing feed text.
- `widgets/navegador/widget.js` — translated comments; preserved UI/runtime Spanish labels.
- `widgets/personalizado-reproduzca-video/data.py` — translated comments; preserved runtime Spanish title/messages.
- `widgets/personalizado-reproduzca-video/widget.js` — translated comments; preserved UI/runtime Spanish labels.
- `widgets/presentation.py` — translated comments and docstrings; preserved executable Spanish presentation directive text.
- `widgets/producers.py` — translated comments and docstrings; preserved runtime Spanish messages.
- `widgets/provenance.py` — translated comments and docstrings; behavior unchanged.
- `widgets/refs.py` — translated comments and docstrings; preserved Spanish reference-resolution vocabulary and runtime prompt text.
- `widgets/registry.py` — translated comments and docstrings; behavior unchanged.
- `widgets/reset.py` — translated comments and docstrings; preserved reset behavior and Spanish runtime messages.
- `widgets/results/data.py` — translated comments and docstrings; preserved runtime Spanish UI/action strings.
- `widgets/results/notes.md` — replaced historical developer notes with compact English notes.
- `widgets/results/widget.js` — translated comments; preserved UI/runtime Spanish labels.
- `widgets/runtime.py` — translated comments and docstrings; preserved Spanish resolver vocabulary.
- `widgets/selection.py` — translated comments and docstrings; behavior unchanged.
- `widgets/server_api.py` — translated comments and docstrings; preserved runtime Spanish API messages.
- `widgets/store.py` — translated comments and docstrings; behavior unchanged.
- `widgets/supervisor.py` — translated comments and docstrings; preserved runtime Spanish logs/messages.
- `widgets/system_surfaces.py` — translated comments; preserved Spanish system aliases.
- `widgets/temporizador-pomodoro-ayudar/data.py` — translated comments and docstrings; preserved Spanish UI labels.
- `widgets/timer/data.py` — translated module docstring; behavior unchanged.
- `widgets/timer/widget.js` — translated comments; preserved Spanish UI labels.
- `widgets/youtube/data.py` — translated comments and docstrings; preserved Spanish search/runtime behavior.
- `widgets/youtube/widget.js` — translated comments; preserved Spanish UI labels.
- `server/__init__.py` — translated startup/lifespan comments; preserved runtime Spanish logs and labels.
- `server/common.py` — translated credential-store comments; behavior unchanged.
- `server/config_api.py` — translated comments/docstrings; preserved configuration data and UI/runtime Spanish strings.
- `server/livekit_api.py` — translated comments/docstrings; preserved user-facing Spanish strings.
- `server/spotify_api.py` — translated comments/docstrings; preserved OAuth callback UI Spanish.
- `server/voice_api.py` — translated comments/docstrings; preserved runtime/UI Spanish status text.
- `server/wizard_api.py` — translated comments/docstrings; preserved wizard UI strings and Spanish error text.
- `config/balances.py` — translated comments/docstrings; preserved runtime Spanish status labels.
- `config/connectors.py` — translated comments/docstrings; preserved connector config keys and behavior.
- `config/credentials.py` — translated comments/docstrings; preserved credential-store behavior.
- `config/doctor.py` — translated comments/docstrings; preserved runtime Spanish report text.
- `config/model_benchmarks.py` — translated developer docstrings; preserved user-visible benchmark data.
- `config/profiles.py` — translated comments/docstrings; preserved profile labels and summaries.
- `config/settings.py` — translated comments/docstrings; behavior unchanged.
- `config/v2.py` — translated comments/docstrings; preserved config schema/defaults and runtime Spanish strings.
- `bus/__init__.py` — translated module docs, comments, and docstrings; behavior unchanged.
- `bus/log.py` — translated durable-log comments/docstrings; behavior unchanged.
- `bus/sse.py` — translated SSE bridge comments/docstrings; behavior unchanged.
- `connectors/__init__.py` — translated package comments; behavior unchanged.
- `connectors/architect/brief.py` — translated comments/docstrings; preserved protocol/runtime Spanish strings.
- `connectors/architect/client.py` — translated comments/docstrings; preserved runtime Spanish error strings.
- `connectors/architect/service.py` — translated comments/docstrings; preserved `[SISTEMA]` runtime notes.
- `connectors/email/__init__.py` — translated package comments; behavior unchanged.
- `connectors/email/config.py` — translated comments/docstrings; preserved UI/runtime Spanish strings.
- `connectors/email/mailbox.py` — translated comments/docstrings; preserved parser behavior and Spanish fallback strings.
- `connectors/email/oauth.py` — translated comments/docstrings; preserved OAuth runtime Spanish errors/logs.
- `connectors/email/providers.py` — translated comments/docstrings; preserved provider notes shown to UI.
- `connectors/email/service.py` — translated comments/docstrings; preserved user-facing Spanish guidance.
- `connectors/meshkore/brain.py` — translated comments/docstrings; preserved executable prompt behavior.
- `connectors/meshkore/bridge.py` — translated comments/docstrings; preserved runtime prompts, operator alerts, and protocol strings.
- `connectors/meshkore/capsule.py` — translated comments/docstrings; preserved Spanish runtime phase labels and prompt guidance strings.
- `connectors/meshkore/client.py` — translated comments/docstrings; preserved transport behavior.
- `connectors/meshkore/evaluator.py` — translated comments/docstrings; preserved Spanish evaluator prompt text.
- `connectors/meshkore/manager.py` — translated comments/docstrings; preserved runtime behavior.
- `connectors/meshkore/mem_ingest.py` — translated comments/docstrings; preserved Spanish memory synthesizer prompt/runtime text.
- `connectors/meshkore/perms.py` — translated comments/docstrings; behavior unchanged.
- `connectors/meshkore/security.py` — translated comments/docstrings; preserved security policy strings and detection regex behavior.
- `connectors/meshkore/server_api.py` — translated comments/docstrings; preserved API/runtime Spanish messages.
- `connectors/meshkore/store.py` — translated comments/docstrings; preserved credential persistence behavior.
- `connectors/messaging/__init__.py` — translated comments/docstrings; preserved msg tag behavior.
- `connectors/messaging/brief.py` — translated comments/docstrings; preserved executable Spanish messaging protocol text.
- `connectors/messaging/config.py` — translated comments; preserved triage config behavior.
- `connectors/messaging/control.py` — translated comments/docstrings; preserved UI/runtime Spanish logs and errors.
- `connectors/messaging/ingest.py` — translated comments/docstrings; behavior unchanged.
- `connectors/messaging/notify.py` — translated comments/docstrings; preserved Spanish brain-note text.
- `connectors/messaging/server_api.py` — translated comments/docstrings; behavior unchanged.
- `connectors/messaging/store.py` — translated comments/docstrings; preserved Spanish message-state schema keys.
- `connectors/messaging/supervisor.py` — translated comments/log text; behavior unchanged.
- `connectors/messaging/triage.py` — translated comments/docstrings; preserved Spanish classifier prompts/examples.
- `connectors/music/__init__.py` — translated comments/docstrings; preserved localized music messages.
- `connectors/music/base.py` — translated comments/docstrings; behavior unchanged.
- `connectors/music/registry.py` — translated comments/docstrings and developer logs; behavior unchanged.
- `connectors/music/youtube_audio.py` — translated comments/docstrings; preserved localized playback messages.
- `connectors/registry.py` — translated comments/docstrings; preserved connector descriptor schema values.
- `connectors/spotify/__init__.py` — translated comments/docstrings; behavior unchanged.
- `connectors/spotify/auth.py` — translated comments/docstrings; preserved OAuth behavior and Spanish runtime errors.
- `connectors/spotify/client.py` — translated comments/docstrings; preserved Spotify API behavior.
- `connectors/spotify/provider.py` — translated comments/docstrings; preserved localized playback messages.
- `connectors/telegram/__init__.py` — translated comments; behavior unchanged.
- `connectors/telegram/config.py` — translated comments; behavior unchanged.
- `connectors/telegram/service.py` — translated comments/docstrings; preserved Telegram runtime Spanish logs/messages.
- `connectors/whatsapp/__init__.py` — translated comments; behavior unchanged.
- `connectors/whatsapp/bridge_proc.py` — translated comments/docstrings; preserved runtime Spanish errors/logs.
- `connectors/whatsapp/client.py` — translated comments/docstrings; behavior unchanged.
- `connectors/whatsapp/config.py` — translated comments; behavior unchanged.
- `connectors/whatsapp/run.py` — translated comments; preserved standalone Spanish CLI text.
- `connectors/whatsapp/service.py` — translated comments/docstrings; preserved WhatsApp runtime Spanish logs/messages.
- `memory/__init__.py` — translated module documentation; behavior unchanged.
- `memory/concepts.py` — translated comments/docstrings; preserved Spanish concept taxonomy regexes.
- `memory/db.py` — translated comments/docstrings; preserved SQLite behavior.
- `memory/graph.py` — translated comments/docstrings; behavior unchanged.
- `memory/journal.py` — translated comments/docstrings; behavior unchanged.
- `memory/queue.py` — translated comments/docstrings and one developer error string; behavior unchanged.

## Rules for future agents

The language rule in `CLAUDE.md` is mandatory. New internal comments and developer documentation must be
written in English. A change is not complete if it introduces Spanish internal prose, even when the code
itself is correct.
