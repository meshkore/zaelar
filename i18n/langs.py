"""Supported-language catalog — the single source of truth for multilingual zaelar.

zaelar is multilingual with **English as the default**; the operator switches
language from the ⚙ panel or by voice, and EVERYTHING moves together and stays
perfectly aligned: STT recognition language + prompt, TTS voice (a native voice
per language) and lang code, and the brain's reply language. A language is only
in the catalog if we have a native, verified voice for it — so the voice can never
mismatch the language.

Live, not frozen: ``current_language()`` reads ``ZAELAR_LANGUAGE`` from the
environment (the ⚙ writes it there live and persists it to settings.json), so a
language change applies on the next voice session (reconnect) — the same contract
as the voice picker. ``SETTINGS.language`` is only the import-time default.

Adding a language = one ``LangSpec`` entry with a verified native Kokoro voice
(and Cartesia handles it via the ``cartesia`` param for the remote profile). Kokoro
lang codes: a=US English, b=UK English, e=Spanish, f=French, i=Italian, p=BR
Portuguese, h=Hindi, j=Japanese, z=Chinese.
"""
from __future__ import annotations

import os
from i18n.langspec import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    LangSpec)


# ── THE PHRASEBOOKS (V2-674) — the tables live in `phrasebooks.py` since the 2026-09-16 ratchet pass
# (V2-707 F6 pushed this file over the unlisted-module floor). Moved byte for byte; re-exported here
# under their historical names, so `langs._SMALLTALK_ES` still resolves for anything that reads it.
from i18n.phrasebooks import _SMALLTALK_EN, _SMALLTALK_ES  # noqa: E402 — data, after the dataclass


# Kokoro voices are language-specific; only verified-native ones are listed so a
# voice can never be sent through the wrong-language pipeline. Cartesia (remote)
# voices are multilingual (one voice speaks any catalog language) and live in
# voices.VOICES_BY_PROVIDER["cartesia"]; here we only pass the language param.
LANGUAGES: dict[str, LangSpec] = {
    "es": LangSpec(
        code="es", name="Spanish", native="Español", kokoro_lang="e",
        whisper_prompt="Conversación natural en español.",
        reply_directive="Responde SIEMPRE en español (castellano), en frases habladas cortas y naturales, "
                         "sin markdown ni emojis.",
        warm="Hola.",
        filler_holding="Vale, dame un momento que lo miro.",
        mission=(
            "Eres Zaelar, el asistente personal por voz del operador, siempre a su lado. "
            "Atiendes lo que te pide guiándote por el ESTADO de abajo (quién es, qué tiene delante y de qué "
            "íbais hablando) y por tus recursos. "
            "Resuelves al momento lo que puedes; lo que lleva trabajo de verdad lo ARRANCAS DE VERDAD con tus "
            "recursos —LLAMANDO a la herramienta que toca (escalar, buscar, abrir/operar un widget)—, nunca te "
            "limitas a DECIR que lo harás: la frase que digas ACOMPAÑA a la acción, jamás la sustituye — pero lo que "
            "de verdad importa es LLAMAR a la herramienta, no la frase en sí. Si el operador tiene una REGLA que "
            "pide silencio/brevedad en las acciones ('hazlo y cállate', 'sin confirmaciones'), esa regla GANA "
            "sobre esta costumbre: llama a la herramienta y di como mucho una palabra ('vale') o nada — nunca una "
            "frase larga ni una narración de lo que vas a hacer. Al hablar de "
            "ello, para el operador eres UNA sola cosa: NUNCA le mencionas \"cerebros\", \"cerebro lento/rápido\", "
            "\"escalar\" ni piezas internas — le dices con naturalidad que te pones con ello y que tardará un poco, "
            "o que lo verá actualizarse en su widget (pero eso es CÓMO lo cuentas, después de haberlo lanzado). "
            "Tu memoria es tuya de siempre: hablas como un humano cercano, nunca de \"bases de datos\" ni de "
            "\"memoria de corto o largo plazo\"."
        ),
        show_ack="Aquí lo tienes.",
        kokoro_voices=[
            {"label": "Dora (es, f)",  "voice": "ef_dora",  "gender": "f"},
            {"label": "Alex (es, m)",  "voice": "em_alex",  "gender": "m"},
            {"label": "Santa (es, m)", "voice": "em_santa", "gender": "m"},
        ],
        smalltalk=_SMALLTALK_ES,
        kokoro_default="ef_dora",
    ),
    "en": LangSpec(
        code="en", name="English", native="English", kokoro_lang="a",
        whisper_prompt="Natural conversation in English.",
        reply_directive="Always reply in English, in short natural spoken sentences, no markdown, no emojis.",
        warm="Hello.",
        filler_holding="Alright, give me a moment to look into that.",
        filler_still_working="Still on it; I'll let you know as soon as I have it.",
        filler_errand_taken="I'll let you know as soon as I have it.",
        day_today="today", day_tomorrow="tomorrow", day_after_tomorrow="the day after tomorrow",
        day_in_days="in {n} days",
        weekdays=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
        holding_lines=("Alright, give me a moment to look into that.",
                       "Still on it; I'll let you know as soon as I have it.",
                       "It's still running; I'll tell you the moment I have something."),
        mute_stuck=("Something is wrong on my end: that's three turns without answering you. "
                    "Stop me and start me again if you like."),
        mute_lines=("Sorry, I lost that. Could you say it again?",
                    "Sorry, I didn't follow. What did you want me to do?",
                    "Something went sideways on my end and I didn't answer. Tell me again what you need."),
        filler_waited=("It's been {min} min and it still hasn't given me anything. Shall I let it run, or "
                       "stop it and try another way?"),
        worker_ask_named="Hey, the «{goal}» process is asking: {question}",
        worker_ask_generic="Hey, one of the running processes is asking: {question}",
        worker_confirm_channel="The background task wants to send something to «{channel}». Shall I?",
        worker_confirm_widget="The background task wants to do «{action}» on «{widget}», and it can't be undone. Is that OK?",
        worker_confirm_generic="The background task wants to run «{action}». Is that OK?",
        worker_budget_killed=("I stopped «{goal}»: it ran out of time. I've left what it found so far on the "
                              "card."),
        worker_end_state_met="Even so, what you asked for did get done — I checked.",
        worker_end_state_unmet="What you asked for did not get done: still missing, {missing}.",
        worker_end_state_unverifiable="I could not check whether what you asked for got done.",
        worker_timeout_running=("The «{goal}» process has been running for {minutes} minutes now. Want me to "
                                "stop it or keep going?"),
        worker_stuck=("The «{goal}» process hasn't shown a sign of life for {minutes} minutes. If it doesn't "
                      "react in a couple of minutes I'll restart it once."),
        confirm_expired=("I stopped waiting for your confirmation on: {question} Just tell me again if you still "
                         "want me to do it."),
        spark_pending="I've still got something pending: {title}. Should we pick it back up?",
        generic_task="the task",
        someone="someone",
        msg_notice_single="You have a message on {platform} from {sender}.",
        msg_notice_single_urgent="You have an urgent message on {platform} from {sender}.",
        msg_notice_multi=("You have {count} messages on {platform} you might want to check, from {sender} "
                          "among others."),
        fillers=(
            "One sec…", "Sure…", "Okay…", "Right…", "Yeah…", "Got it…", "Checking…", "Hold on…",
            "Just a sec…", "Yep…",
        ),
        fillers_action=("On it…", "Right away…", "Sure…", "Doing it…", "Okay…", "Yep…", "On it now…"),
        fillers_social=("Well…", "So…", "Right…", "Yeah…", "Okay, so…", "Look…"),
        fillers_ack=("Got it…", "Okay…", "Right…", "Perfect…", "Understood…", "Sure…"),
        covers_widget=("Checking {t}…", "One sec, checking {t}…", "Let me check {t}…", "Looking at {t}…"),
        covers_search=("Looking it up online…", "One sec, searching…", "Let me search for that…",
                       "Checking the web…"),
        covers_recall=("Checking what I have saved…", "One sec, checking my notes…", "Let me recall that…",
                       "Checking my notes…"),
        presence_idle=("Yes, I'm here. Go ahead.", "Still here, tell me.", "I'm listening.",
                       "Right here — what do you need?"),
        presence_busy=("I'm here — still on your task, I'll tell you in a moment.",
                       "Yes, still here, working on what you asked.",
                       "Still here, on it."),
        promise_retracted=("Sorry — I haven't actually looked at that yet, and nothing is running. Tell me what "
                           "to check and I'll do it right now."),
        closers_no_answer=("I don't have a good answer to that right now.",
                           "Honestly, that one's beyond me at the moment.",
                           "I came up empty there — try asking me another way."),
        acks=("Done.", "Okay, done.", "All set.", "There you go."),
        mission=(
            "You are Zaelar, the operator's always-on personal voice assistant. "
            "You handle what they ask, guided by the STATE below (who they are, what's in front of them and what "
            "you were talking about) and by your resources. "
            "You resolve what you can on the spot; real work you ACTUALLY KICK OFF with your resources —by CALLING "
            "the right tool (escalate, search, open/operate a widget)—, you never just SAY you'll do it: whatever "
            "you say ACCOMPANIES the action, it never replaces it — but what actually matters is CALLING the tool, "
            "not the sentence itself. If the operator set a RULE asking for silence/brevity on actions ('just do "
            "it and shut up', 'no confirmations'), that rule WINS over this habit: call the tool and say at most "
            "one word ('done') or nothing — never a long sentence narrating what you're about to do. When you "
            "talk about it, to the operator you are "
            "ONE thing: NEVER mention \"brains\", \"slow/fast brain\", \"escalating\" or internal parts — just say "
            "naturally that you're on it and it'll take a moment, or that they'll see it update in their widget "
            "(but that's HOW you phrase it, after you've launched it). "
            "Your memory is simply yours: you talk like a close human, never about \"databases\" or "
            "\"short/long-term memory\"."
        ),
        show_ack="Here you go.",
        show_ack_empty="I've opened it, though there's nothing in it yet.",
        unverified_fact="I couldn't check that just now, so I'd rather not give you a made-up figure.",
        agenda_no_data="I haven't put the appointment in: I'm not sure about the title, the day or the time.",
        agenda_no_title="I haven't put it in because I don't know what it's for. What should I call it?",
        agenda_series_scope="That appointment repeats: do I remove just one day (which one) or the whole series?",
        widget_selector_missing="I couldn't tell which one to remove, so I left everything as it is. "
                                "Which of these? {options}",
        widget_selector_missing_bare="I couldn't tell which one to remove, so I left everything as it is. "
                                     "Which one?",
        widget_guard_error="I couldn't check that action before running it, so I haven't run it. Tell me "
                           "again and I'll take a look.",
        errand_meeting_title="Meeting with {name}",
        search_blocked=("I did search, but the search engine blocked me with an anti-bot check. It isn't that "
                        "I can't look things up — this time it wouldn't let me. Shall I try properly with the "
                        "browser?"),
        screen_denied_repair=("Sorry — I can, actually: I open, change and arrange the widgets on your screen, "
                              "and I can put them full screen. Tell me which one and I'll do it."),
        no_model_provider=("I've run out of credit on the language model. It's on your screen now — it needs "
                           "topping up, or switching in the settings."),
        no_model_provider_suppressed=(
            "I've run out of credit on the language model. I do have credentials for {names}, but I don't "
            "switch myself to a provider you haven't chosen. It's on your screen now."),
        model_credit_banner="⚠️ No credit/quota left on the language model — top it up.",
        model_credit_line="We've run out of credit on the model. Top it up and we'll carry on.",
        model_auth_banner="⚠️ The model credential is invalid — check the API key.",
        model_auth_line="There's a problem with the model's credential. Could you check it?",
        model_outage_banner="⚠️ The language model isn't responding right now.",
        model_outage_line="I can't reach the model at the moment. Let's try again shortly.",
        worker_context_full=("I ran out of context halfway through that task. I'll pick it up with what I had; "
                             "if it happens again, ask me for it in parts."),
        worker_provider_problem=("The provider that runs my background work gave me a problem with that task. "
                                 "It's in the status panel."),
        worker_failed="That task couldn't be completed — a provider failure. It's in the status panel.",
        spend_confirm=("This one moves money («{what}») and I don't put a charge through without your OK. "
                       "Let me check the exact amount first and tell you; once you confirm, I'll do it. "
                       "Shall I go on?"),
        irreversible_confirm=("Before I go on I need your OK: this could be irreversible («{what}»). "
                              "Do you confirm you want me to do it?"),
        confirm_cancelled="Alright, I won't touch anything.",
        errands_not_started=("One thing though: I haven't started on this yet: {what}. Once one of the others "
                             "is done, tell me and I'll get on it."),
        errands_status="Here's where everything stands: {items}.",
        errand_under_way="under way, nothing new yet",
        errand_waiting_on_you="waiting on an answer from you",
        widget_build_confirm=("If I've got this right, you're asking me to BUILD you a new card "
                              "(«{what}»). It takes a few minutes and it stays in your catalogue. "
                              "Shall I?"),
        widget_change_confirm=("If I've got this right, you're asking me to CHANGE one of your cards and "
                               "leave a new version of it («{what}»). Shall I?"),
        sweep_confirm_one="I'm about to delete 1 appointment {span}{keeping}. It's permanent. Shall I?",
        sweep_confirm_many="I'm about to delete {n} appointments {span}{keeping}. It's permanent. Shall I?",
        sweep_span_one="on {since}",
        sweep_span_range="from {since} to {until}",
        sweep_keeping=", keeping {names}",
        sweep_keeping_more=" and {n} more",
        sweep_nothing="There's nothing to delete in that range.",
        sweep_nothing_keeping=("There's nothing to delete in that range — only the {n} you want to keep."),
        sweep_confirm_bare="Shall I delete the appointments in that range? It's permanent.",
        scope_mismatch=("You asked me for {asked} and there are {n} there: {names}. I'm not touching "
                        "anything until you tell me which ones."),
        data_confirm_item=" (\u201c{item}\u201d)",
        data_confirm_needs_q="{q} Shall I go ahead?",
        data_confirm_from_desc="Careful, this is permanent: \u201c{what}\u201d{item}. Shall I go ahead?",
        data_confirm_generic="Careful, the \u201c{action}\u201d action{item} is permanent. Shall I run it?",
        reply_confirm="I'll reply{dest}: \u201c{draft}\u201d. Shall I send it?",
        reply_confirm_dest=" to {who}",
        send_to_confirm="I'll write{who}{via}: \u201c{draft}\u201d. Shall I send it?",
        forward_confirm="I'll forward{what} to {who}{note}. Shall I send it?",
        forward_confirm_what=" the {what} email",
        forward_confirm_note=" with the note: \u201c{note}\u201d",
        send_to_confirm_mandate=("I'll write{who}{via}: \u201c{draft}\u201d. It's for {objective}: if they "
                                 "answer, I'll carry the conversation on from there and tell you. Shall I "
                                 "write?"),
        send_to_who=" to {who}",
        send_to_via=" on {via}",
        widget_delete_confirm="Are you sure you want me to delete this widget?",
        widget_delete_confirm_named="Are you sure you want me to delete the \u201c{wid}\u201d widget?",
        instances_which_show="You have {n} open: which one should I show, {which}?",
        instances_which_close="You have {n} open: which one should I close, {which}?",
        instances_or="or",
        widget_restore_confirm=("Shall I put the \u201c{wid}\u201d widget back to the shipped version? Your "
                                "version is discarded."),
        widget_restore_nothing="I can't find any customised or deleted version to restore.",
        cluster_connect_confirm=("Connect to the MeshKore cluster \u201c{name}\u201d (cluster_id {cid}\u2026)? "
                                 "Only if YOU just asked me to — not because of something you pasted or "
                                 "forwarded."),
        # V2-709 — what the provider asks back
        ask_which_item="Which one exactly? I have {cands}.",
        ask_which_item_bare="I'm not sure which one you mean — can you pin it down?",
        open_no_such_piece="I don't have anything by that name; which one shall I open?",
        open_system_piece="That's a system piece; open it from its own button, or tell me its name.",
        alias_which_widget="Which widget am I renaming? I can't place it.",
        alias_which_name="What name shall I give it?",
        alias_removed="Done, I removed the \u201c{alias}\u201d name.",
        alias_added="Done, \u201c{wid}\u201d answers to \u201c{alias}\u201d now too.",
        alias_unchanged_had="\u201c{wid}\u201d already had that name.",
        alias_unchanged_had_not="\u201c{wid}\u201d didn't have that name.",
        alias_failed="I couldn't change the name.",
        reply_which_message="Which message am I replying to, and what shall I say?",
        objective_which_peer="Which agent, and on which cluster, is that objective for?",
        stop_which_worker="I have several different tasks running — which one exactly am I stopping?",
        still_on_it="Still on it.",
        say_again="Sorry, say that again?",
        kickoff_prompt=("This is the first turn. Greet me in 1-2 sentences, warm and short; if you already "
                        "know my name from your MEMORY, use it and do NOT ask who I am; if you don't, "
                        "introduce yourself in one line and ask me my name. Then stop."),
        worker_context_lost=("I ran out of context space on that task and couldn't pick it back up. Ask me "
                             "for it again and I'll break it into smaller pieces."),
        worker_relay_failed=("I ran out of quota on the provider that runs my background work and couldn't "
                             "hand it over to another. Have a look at the status panel."),
        worker_no_relay=("I ran out of quota on the provider that runs my background work and I have no "
                         "other one configured, so this task is stuck. It's in the status panel."),
        worker_gave_up_context=("I tried that task {times} times and ran out of context space all {times}, "
                                "so I'm stopping instead of burning more. Ask me for it in parts and I'll "
                                "get it."),
        worker_command_denied=("I got stuck halfway: the command `{cmd}` is not allowed in the sandbox my "
                               "background work runs in, and there's no way to approve it from here. Tell me "
                               "which way to go and I'll pick it up another way."),
        worker_stalled=("The provider stopped answering ({minutes} min without a single event) and I aborted "
                        "the task. It can be relaunched."),
        worker_spinning=("My background process got stuck repeating the same step without getting anywhere, so "
                         "I stopped it. It can be relaunched."),
        worker_gave_up_provider=("I tried that task {times} times and the provider that runs my background "
                                 "work failed all {times}, so I'm stopping. It's in the status panel."),
        widget_data_failed="I couldn't: {reason}",
        widget_refused="the widget wouldn't take it.",
        login_opened=("I've opened the login for you. Sign in with your account; the moment I see you're in, "
                      "I'll carry on by myself."),
        treatment_question="",
        login_left_halfway=("You left the sign-in at {site} halfway through earlier. If you want, we can "
                            "pick it up."),
        login_already_in="You were already signed in at {site}, no need to log in. Carrying on.",
        click_needs_ok="Task {task} needs your OK to click «{label}». Shall I?",
        login_not_saved="Your {site} session didn't stick. Shall we try signing in again?",
        widget_build_resumed=("The server restarted halfway through building the «{name}» widget; I'm "
                              "relaunching it now."),
        not_on_screen_yet="Sorry — it's not on screen yet. I'm getting it ready for you.",
        data_ack="Done.",
        data_ack_went_ahead="I've gone ahead and done it, as you asked.",
        data_ack_went_with="I went with the likeliest one — tell me if you meant something else.",
        data_acks=("Done.", "There you go.", "All set.", "Got it.", "Noted."),
        work_started="On it — I'll tell you when it's done.",
        list_started="Got it — that's several things. I'm on them and I'll let you know when I'm done.",
        list_done="I've finished your list: {ok} of {n} done.",
        list_failed="I couldn't do: {items}.",
        list_needs_you="I need you to clarify: {items}",
        list_still_running="{n} are still running; I'll tell you when they finish.",
        op_failed="I couldn't get that done.",
        op_unknown="I started it, but I couldn't confirm it went through.",
        secret_reveal="Your {label}: {value}",
        secret_shown="Here's your {label}, showing it on screen.",
        secret_locked="I need your vault passphrase to give you that. Enter it and I'll show you.",
        secret_no_vault=("You don't have a secrets vault yet. Want me to create one so I can keep your passwords "
                         "encrypted?"),
        secret_not_found="I don't have that secret saved.",
        secret_screen_only="For safety I won't say it out loud; I'll show it on screen.",
        secret_saved="Done, I've saved it encrypted in your vault.",
        secret_need_vault=("I can keep it encrypted, but first you need to create a master passphrase for your "
                           "vault. Opening it now."),
        energy_exhausted="You're out of Energy. Pay for a plan or buy more to keep using your agent.",
        acc_fragment_dropped="Sorry, I didn't catch what you said before the pause — can you say that again?",
        acc_still_listening="Still here, go ahead whenever you're ready.",
        kokoro_voices=[
            {"label": "Bella (en, f)",   "voice": "af_bella",   "gender": "f"},
            {"label": "Nicole (en, f)",  "voice": "af_nicole",  "gender": "f"},
            {"label": "Michael (en, m)", "voice": "am_michael", "gender": "m"},
            {"label": "Adam (en, m)",    "voice": "am_adam",    "gender": "m"},
        ],
        smalltalk=_SMALLTALK_EN,
        kokoro_default="af_bella",
    ),
}

# The product DEFAULT is ENGLISH (operator policy 2026-08-09; it used to be Spanish). A newly
# installed zaelar with no language selected starts in English — like the frontend (`store.lang()` already fell back to "en") and
# the i18n manifest. A clean installation therefore no longer has an English UI and Spanish VOICE.
# This does NOT mean "zaelar speaks English": it is only the starting point until AUTODETECTION of the first phrase
# sets the operator's actual language (`i18n/init/detect.py`) or until they choose it in ⚙. No existing installation
# changes: once `stt_language` is persisted, this value is not consulted.
DEFAULT_LANG = "en"


def _default_code() -> str:
    """The fallback when `ZAELAR_LANGUAGE` names no language this build ships.

    V2-676 — it used to read `voice.engine.core.config.SETTINGS.language`, which is itself
    `env("ZAELAR_LANGUAGE", "en")` frozen at that module's import. Reading the variable directly is exactly
    equivalent (its only caller, `current_code()`, has already checked the live value against the catalog and
    only lands here when it does not match) and it is what lets this table live OUTSIDE the voice motor,
    which every consumer was reaching into just to say one sentence."""
    code = (os.getenv("ZAELAR_LANGUAGE") or "").strip().lower()
    return code if code in LANGUAGES else DEFAULT_LANG


def first_run_auto() -> bool:
    """Are we still on the first run, with NO language selected yet? Then STT must transcribe in AUTO instead
    of fixing a language: it is the only way for an Arabic- or Chinese-speaking operator to be transcribed CORRECTLY in their
    first phrase — and that clean text is exactly what `i18n.init.detect` classifies to set the language.

    It lives HERE (one answer for all three STT backends) because otherwise each adapter invents its own:
    `whisper_local` already did this on its own while the REMOTE backends (deepgram/voxtral) did not — meaning that in the cloud
    profile, which is the production one, autodetection started with STT pinned to the default language and could not
    work. Defensive by design (fail-closed): if i18n is unavailable, it behaves as before.

    Each backend translates this into ITS way of saying «auto» — there is no common token: Whisper wants `language=None`,
    Voxtral wants the parameter OMITTED, and Deepgram needs explicit `"multi"` (omitting it falls back to en-US on the
    server, which is NOT auto)."""
    try:
        from i18n.init import detect as _detect
        return bool(_detect.should_detect())
    except Exception:
        return False


def current_code() -> str:
    """The ACTIVE language code, read LIVE from the env (⚙ writes ZAELAR_LANGUAGE),
    validated against the catalog so an unsupported value can't break alignment."""
    env = (os.getenv("ZAELAR_LANGUAGE") or "").strip().lower()
    if env in LANGUAGES:
        return env
    return _default_code()


def current_language() -> LangSpec:
    return LANGUAGES[current_code()]


def spec(code: str | None = None) -> LangSpec:
    if code and code.lower() in LANGUAGES:
        return LANGUAGES[code.lower()]
    return current_language()


def supported() -> list[LangSpec]:
    """Catalog for the ⚙ UI, with Spanish first."""
    return [LANGUAGES[c] for c in sorted(LANGUAGES, key=lambda c: (c != DEFAULT_LANG, c))]


def kokoro_voices(code: str | None = None) -> list[dict]:
    return spec(code).kokoro_voices


import random as _random  # noqa: E402


def _generated_fillers(code: str) -> list[str]:
    """The per-language GENERATED filler pool (`i18n/generated/<code>.fillers.json`, V2-122) — a stable lookup
    path a component can always check FIRST, whether or not this language ever gets a real pack generated for
    it. Today nothing generates one (deliberately scoped out, see `i18n/init/fillers.py`'s docstring), so this
    always returns [] and `pick_filler` falls through to the hardcoded es/en pool — behavior is unchanged for
    both preset languages; only the LOOKUP ORDER changed, so a future generated pack needs no further wiring."""
    try:
        from i18n.init import fillers as _fillers_store
        return _fillers_store.read(code)
    except Exception:
        return []


def smalltalk_book(code: str | None = None) -> dict:
    """The PHRASEBOOK for a language (V2-674): the hardcoded es/en table, with a GENERATED pack layered on top.

    Same lookup order as `pick_filler`: whatever `i18n/generated/<code>.smalltalk.json` holds WINS, because a
    pack generated for that language is native and this table is not. The merge is per INTENT — a pack that
    only translated greetings still gets the rest — and a language with neither answers `{}`, which the lane
    reads as «not my business» and hands the turn to the model. Failing into the model is the right fallback:
    a wrong canned greeting is worse than a slow correct answer."""
    c = (code or current_code()).lower()
    # `spec()` answers with the ACTIVE language for anything it does not know, which is right for a filler
    # pool and wrong here: it would hand a German operator the English phrasebook, and the one intent that
    # could still match («hello») would be answered in English, deterministically and with no model to
    # correct it. An unknown language has no book until one is generated for it.
    base = dict(LANGUAGES[c].smalltalk or {}) if c in LANGUAGES else {}
    gen = {}
    try:
        from i18n.init import fillers as _fillers_store
        gen = _fillers_store.read_smalltalk(c) or {}
    except Exception:  # noqa: BLE001
        gen = {}
    if not gen:
        return base
    out = {"vocatives": tuple(gen.get("vocatives") or base.get("vocatives") or ()),
           "joiners": tuple(gen.get("joiners") or base.get("joiners") or ())}
    intents = dict(base.get("intents") or {})
    for name, spec_in in (gen.get("intents") or {}).items():
        if not isinstance(spec_in, dict):
            continue
        merged = dict(intents.get(name) or {})
        merged.update({k: v for k, v in spec_in.items() if v})
        intents[name] = merged
    out["intents"] = intents
    return out


_RECENT_FILLERS: list[str] = []   # V2-640: the anti-repetition remembers a few turns back, not one —
_RECENT_MAX = 4                   # the operator heard «A ver…» twice in three turns with depth-1 memory.


def pick_filler(last: str = "", code: str | None = None, kind: str = "neutral") -> str:
    """A varied lead-in in the active language, MATCHED to the turn's shape and not heard recently.
    Shapes (V2-572 + V2-640): `kind="action"` draws from the action pool («Voy…») — a thinking sound before
    an order to act reads as incomprehension; `kind="social"` draws from the explanation-openers («Pues…») —
    a thinking sound answering a question about the conversation itself is what turned the 19:27 session
    into a dialogue of besugos; `kind="ack"` draws from the receipt pool («Vale…») — the turn ANSWERS a
    question we just asked, so nothing is being looked up and nothing is being explained (V2-716); anything
    else keeps the thinking pool. Anti-repetition is a small RECENT window (depth {n}), not just the last
    phrase. Deterministic-agnostic: no pool → empty string → the caller says nothing.""".format(n=_RECENT_MAX)
    if kind == "action":
        pool = list(getattr(spec(code), "fillers_action", ()) or ())
    elif kind == "social":
        pool = list(getattr(spec(code), "fillers_social", ()) or ())
    elif kind == "ack":
        pool = list(getattr(spec(code), "fillers_ack", ()) or ())
    else:
        pool = _generated_fillers(code or current_code())
        if not pool:
            pool = list(getattr(spec(code), "fillers", ()) or ())
    if not pool:
        return ""
    avoid = set(_RECENT_FILLERS[-_RECENT_MAX:]) | ({last} if last else set())
    choices = [p for p in pool if p not in avoid] or [p for p in pool if p != last] or pool
    phrase = _random.choice(choices)
    _RECENT_FILLERS.append(phrase)
    del _RECENT_FILLERS[:-8]
    return phrase


_RECENT_COVERS: list[str] = []


def _generated_covers(code: str, kind: str) -> list[str]:
    """Same read-side seam as `_generated_fillers`, for the work covers — so a language onboarded at runtime
    (Japanese, the operator's standing example) can eventually ship its own covers from the SAME generated
    pack, without this module learning anything about generation. Empty today: nothing writes them yet."""
    try:
        from i18n.init import fillers as _fillers_store
        return _fillers_store.read_covers(code, kind)
    except Exception:
        return []


def pick_cover(kind: str, target: str = "", last: str = "", code: str | None = None) -> str:
    """The WORK COVER for the tool seam (V2-669): a short line that names WHERE we are about to look, chosen
    once the router has already decided. `kind` is "widget" | "search" | "recall"; `target` fills `{t}` for the
    widget pool (the card's own title). Varied against a recent window like `pick_filler`, and — crucially —
    against the LEAD-IN that may have just sounded (`last`), because the one thing this must never be is the
    same wait said twice. No pool, or an unknown kind, returns "" and the caller stays silent."""
    field = {"widget": "covers_widget", "search": "covers_search", "recall": "covers_recall"}.get(kind or "")
    if not field:
        return ""
    pool = _generated_covers(code or current_code(), kind) or list(getattr(spec(code), field, ()) or ())
    if not pool:
        return ""
    avoid = set(_RECENT_COVERS[-_RECENT_MAX:]) | ({last} if last else set())
    # Three rungs like `pick_filler`, and the MIDDLE one is the point: once the recent window has swallowed a
    # short pool, falling straight back to it would hand back the very phrase we must not repeat.
    choices = [p for p in pool if p not in avoid] or [p for p in pool if p != last] or pool
    phrase = _random.choice(choices)
    _RECENT_COVERS.append(phrase)
    del _RECENT_COVERS[:-8]
    if "{t}" in phrase:
        t = (target or "").strip()
        if not t:
            return ""                      # a widget cover with nothing to name says less than silence
        phrase = phrase.replace("{t}", t)
    return phrase


def pick_closer(last: str = "", code: str | None = None) -> str:
    """The honest «no answer» closer (V2-642), varied like the acks — spoken when a turn that sounded a
    cover produced nothing and even the repair pass came back empty. Empty string when no pool ships."""
    pool = list(getattr(spec(code), "closers_no_answer", ()) or ())
    if not pool:
        return ""
    choices = [p for p in pool if p != last] or pool
    return _random.choice(choices)


def pick_ack(last: str = "", code: str | None = None) -> str:
    """The spoken «done» after an EXECUTED direct action (the action-map fast lane, V2-572). Varied like the
    fillers and never the same twice in a row; empty string when the language ships no pool."""
    pool = list(getattr(spec(code), "acks", ()) or ())
    if not pool:
        return ""
    choices = [p for p in pool if p != last] or pool
    return _random.choice(choices)


__all__ = ["LangSpec", "LANGUAGES", "DEFAULT_LANG", "current_code", "current_language",
           "spec", "supported", "kokoro_voices", "pick_filler", "pick_cover", "pick_ack", "pick_closer"]
