"""LangSpec — the per-language table of everything the agent says and reads (V2-778 F1, 2026-10-01).

Moved out of `i18n/langs.py` (994 lines, over the 900 a new file may reach): the dataclass that declares every
field a language provides (its spoken lines, its fillers, its detectors' vocabulary), unchanged. `i18n.langs`
imports it back and keeps the instances (`LANGUAGES`) and the accessors, so `from i18n.langs import LangSpec`
still works.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LangSpec:
    code: str                      # our language code (es, en, …) — Whisper/Voxtral/Deepgram/Cartesia language
    name: str                      # English name (logs/UI)
    native: str                    # native name (UI)
    kokoro_lang: str               # Kokoro lang_code (a/e/…)
    whisper_prompt: str            # Whisper initial_prompt in this language (anti-hallucination + accents)
    reply_directive: str           # instruction appended to the brain so it replies in this language
    warm: str                      # short warm phrase for the Metal TTS model
    filler_holding: str            # neutral "I'm on it" line — used when the fast brain escalates to Hermes
                                    # with no spoken content of its own (see duo.py's escalate_to_hermes tool)
    mission: str = ""              # Zaelar's MISSION/identity (3-4 sentences) IN THE OPERATOR'S LANGUAGE — section A
                                    # of the composite STATE (memory.compose_state). It lives here (the single language source)
                                    # and is SEEDED into memory (state.mission) at startup; the prompt NEVER
                                    # hardcodes it in English. BOTH brains use it as part of the shared state.
    show_ack: str = ""  # short "here you go" when opening a widget with no spoken content of its own
    # V2-209: the SAME act over a surface with nothing in it. «Aquí lo tienes» asserts a delivery, and
    # opening a card is not one — measured on `book-hotel-night-known__es` (2026-08-20 13:49), where the
    # judge called it «alucinación de éxito» over a browser task that had brought nothing back.
    # ⚠️ DOES NOT CLAIM ONGOING WORK. The first version ended with “I'm still on it,” and that was a measured
    # REGRESSION (V2-209 addendum): in `cancel-subscription-before-charge__es` —the board's only 5/5 case,
    # which succeeded precisely by asserting NOTHING— it dropped to 2/5 with the verdict “said it was still
    # canceling on the user's account without the mechanism supporting it.” I changed one false claim (“here you go”)
    # to another, smaller one and therefore one easier to sneak through. This ack only says what HAPPENED: it opened,
    # and it is empty.
    show_ack_empty: str = ""
    # V2-210: when the turn had to consult a source and could not. Worse response, better information.
    unverified_fact: str = ""
    #: What the AGENDA says when it refuses to write (V2-689). These were hardcoded Spanish inside
    #: `widgets/agenda/data.py`, which is the exact shape V2-676 ruled against — the operator running his
    #: agent in English was answered by our own canned lines in Castilian. A widget's refusal is a text the
    #: operator HEARS, so it belongs in the table that gets translated when a language is initialised, not
    #: in an `_en` ternary that can only ever know the two languages this repo happens to ship.
    agenda_no_data: str = ("")
    agenda_no_title: str = ""
    agenda_series_scope: str = ""
    agenda_series_left: str = ""
    #: A DESTRUCTIVE widget action that arrived with no selector (V2-705, `widgets/contract.py`). The
    #: operator hears this instead of «done» — and instead of losing everything, which is what an empty
    #: `cancel_meeting` did to his Google Calendar on 2026-09-15. `{options}` is the widget's own menu.
    widget_selector_missing: str = ("")
    widget_selector_missing_bare: str = ""
    #: The same guard when IT ITSELF failed (V2-710 T0.3). `contract.guard` used to answer «proceed» on any
    #: internal error, so a destructive action whose contract could not be read ran with an empty selector —
    #: the exact pre-V2-705 state, in silence. It now fails CLOSED for anything destructive, and this is what
    #: the operator hears: the action did not run, and it is worth saying again rather than doing it blind.
    widget_guard_error: str = ("")
    #: The TITLE an errand writes on the meeting it just agreed with a third party (V2-692). It lands in
    #: the operator's agenda and, through the connector, in his real Google Calendar — a row only HE can
    #: delete — so it is a text he reads and belongs here rather than in an f-string inside the errand.
    #: `{name}` is the other person, as the directory or the conversation names them.
    errand_meeting_title: str = ""
    # V2-676 — THE SEARCH RAN AND THEY BLOCKED IT. Measured 2026-09-11 (session af4429e0): five searches for
    # the New York weather, every one `n:0` with `failure.kind = captcha`, and the reply the operator got was
    # «I actually don't have live internet access… my training data has a cutoff date». The agent denied, to
    # its owner, a capability it ships with. This line is what it says instead — and it says the TRUE thing:
    # the search happened, somebody refused it, and there is another way in.
    search_blocked: str = ("")
    # V2-677 — the SAME shape one surface over: the agent denying, to its owner, something it ships with.
    # Measured in session e896f596 (2026-09-11, English), three times in eighty seconds: «I can't display
    # images or graphs» nineteen seconds after painting six of them on his canvas; «I don't have a way to
    # actually select or display images from my side»; «I can't resize or maximize windows or widgets on
    # your screen — I don't have control over your device's interface», with `fullscreen_widget` and
    # `arrange_canvas` both in that turn's tool list. He read all three as the product lacking the feature.
    # This line is what it says instead, and it ends by asking for the one thing that was actually missing.
    screen_denied_repair: str = ("")
    # V2-676 — the whole model chain is dry. SHORT on purpose: the detail (which model, how to top it up, the
    # way into the settings) belongs on the screen, in the operator's own language and with a button, not in a
    # spoken sentence full of config keys — which is exactly what he heard, in Spanish, in an English session.
    no_model_provider: str = ("")
    # V2-676 — THE SENTENCES THAT USED TO BYPASS THIS TABLE. Every one below was a Spanish string literal at
    # its own delivery point, spoken or written to the operator verbatim whatever language he had chosen.
    # Measured on his English session (`af4429e0`, 2026-09-11): he heard «Esa tarea no ha podido completarse
    # por un fallo del proveedor» and «Me he quedado sin proveedor de modelo… ponlo en `fast.providers`» in the
    # middle of a conversation held entirely in English. The table was never wrong — English overrides all 56
    # of its fields — these sentences simply never asked it.
    #
    # The chain is dry (`{names}` = credentialed rungs the self-host rule is silencing, V2-244).
    no_model_provider_suppressed: str = (
        "")
    # The model's own health, as the operator reads it (banner) and hears it (spoken) — `voice/llm_health.py`.
    model_credit_banner: str = ""
    model_credit_line: str = ""
    model_auth_banner: str = ""
    model_auth_line: str = ""
    model_outage_banner: str = ""
    model_outage_line: str = ""
    # A background worker that did not finish — `nucleo/workers/handoff.py`. THE one he heard.
    worker_context_full: str = ("")
    worker_provider_problem: str = ("")
    worker_failed: str = ("")
    # V2-682 — THE CONFIRM GATE AND THE SPEND GATE. Both were hardcoded Spanish in `nucleo/danger.py` and in
    # the voice provider, and the operator heard them verbatim in the middle of an English session
    # (2026-09-12, 20:07 and 20:45): «¿Vacío la agenda entera? Es permanente.» → «Vale, no toco nada.», and
    # «Esto mueve dinero («Yeah. Can you pay, uh, can you pause?») y no hago ningún cargo sin tu OK… ¿Sigo?»
    # — the money gate, in Spanish, fired by the STT mishearing «pause» as «pay».
    spend_confirm: str = ("")
    irreversible_confirm: str = ("")
    confirm_cancelled: str = ""
    # three-tasks-at-once (2026-10-10) — an errand the turn could NOT start (the worker pool takes three per turn)
    # is named back to him; dropping it silently left him waiting on work nothing was doing.
    errands_not_started: str = ("")
    # …and a status question over live errands is answered with each one's phase, never an empty wait.
    errands_status: str = ""
    errand_under_way: str = ""
    errand_step_of: str = ""
    errand_running_for: str = ""
    errand_waiting_on_you: str = ""
    # …and a WAIT reply while an errand runs names its real current step (photo round, 2026-10-11: «Will do»,
    # «Sounds good» with «entrando en media.ferrari.com» in the turn's own state).
    errand_step_now: str = ""
    errand_step_bare: str = ""
    # …and what he asked for while a widget was being built is applied to it afterwards (three-tasks, 2026-10-11).
    widget_changes_applied: str = ""
    widget_changes_not_applied: str = ("")
    # …and a refinement passed to a running errand is confirmed NAMING that errand: the report's refinement got
    # the holding line, and he had to ask three more times whether it had landed (ES round 20:00).
    errand_refined: str = ""
    # his words on a live errand's progress note go to its worker: say what happens next (search-buy-watch, 2026-10-14)
    errand_relayed_next: str = ("")
    # …and ONE sentence about several errands is answered errand by errand (three-tasks-at-once EN, 2026-10-14:
    # «…ping me when the game's ready… for the monitor make sure it's got hdmi» got a bare «Done.»; split_by_errand.py).
    errands_each: str = ""
    errand_part_passed: str = ""
    errand_part_done: str = ""
    # V2-757 — TOUCHING A CARD OF HIS IS ASKED FIRST. Measured live (session f84f91ef, 2026-09-23): with
    # the mic open the operator dictated a design brief to ANOTHER conversation, and the turn read it as
    # his to us — «lo mando hacer», a Brain Worker started rewriting the video card, and his «Olvídate de
    # eso, no va por ti» arrived when the task had already been running for a minute. His rule, from that
    # same day: «recuerda que hay que pedir confirmación siempre que pidamos crear un widget o modificar
    # un widget… que sea algo de sistema, porque así nos evitaremos que se empiecen a generar widgets por
    # ahí fuera de cualquier manera». The question is phrased the way HE put it — «si no me equivoco me
    # estás pidiendo que modifique esto» — because its whole job is to let him say NO.
    widget_build_confirm: str = ("")
    widget_change_confirm: str = ("")
    # V2-812 T-03 — an errand that would start from a line that was not clearly his request to the agent (talk
    # between passengers, an «eso es» after a statement) is asked first, naming what would start.
    errand_unaddressed_confirm: str = ""
    # ── V2-707 F6 — THE CONFIRM GATE'S OWN SENTENCES ────────────────────────────────────────────────────
    # V2-682 moved `danger.py`'s two gates here and left the OTHER gate — the one that asks about a widget's
    # own data — composing its prose inside `voice/engine/llm/providers/confirm_gate.py`. Measured on
    # 2026-09-16 (session 080b96a7): thirty seconds after «Do not speak Spanish», the operator heard «Voy a
    # borrar 5 citas del 2026-09-17. Es permanente. ¿Las borro?» (i=10765) and, before that, «No hay ninguna
    # cita que borrar en ese tramo» (i=10600). Neither is a `notify`/`say` call nor an assignment to a spoken
    # field — they are RETURN values, which is the one shape V2-682's ratchet still cannot see, so the leak
    # was invisible until he heard it.
    #
    # The sentences arrive in PIECES on purpose: the span («del 17» vs «del 17 al 20»), what is kept and the
    # plural are all decided by the DATA, and a language that words them differently has to be able to say
    # so. Composing them from fragments of this table is the only way that stays true in a language nobody
    # in this repo speaks.
    sweep_confirm_one: str = ""
    sweep_confirm_many: str = ""
    sweep_span_one: str = ""
    sweep_span_range: str = ""
    sweep_keeping: str = ""
    sweep_keeping_more: str = ""
    sweep_nothing: str = ""
    sweep_nothing_keeping: str = ("")
    sweep_confirm_bare: str = ""
    #: THE CONTRADICTION (V2-707 F6). The order named a number and the radius resolved to a different one, so
    #: there is nothing to say yes to — see `confirm_gate.scope_mismatch`.
    scope_mismatch: str = ("")
    #: The generic tail of any confirmation, when the manifest resolved which item it is about.
    data_confirm_item: str = ""
    #: A `confirm_q` from a manifest that is not phrased as a question already.
    data_confirm_needs_q: str = ""
    #: No `confirm_q`: the action's own one-line description is quoted instead.
    data_confirm_from_desc: str = ""
    #: Not even a description — the last-resort sentence, which names the raw action.
    data_confirm_generic: str = ""
    #: ANSWERING a message (V2-051) and WRITING to a person (V2-683): the confirmation reads the draft.
    reply_confirm: str = ""
    reply_confirm_dest: str = ""
    send_to_confirm: str = ""
    forward_confirm: str = ""
    forward_confirm_what: str = ""
    forward_confirm_note: str = ""
    send_to_confirm_mandate: str = ("")
    send_to_who: str = ""
    send_to_via: str = ""
    #: The three confirmations the voice provider asks in its own words: delete a widget, restore it to the
    #: shipped version, connect a MeshKore cluster. Same fault, same table.
    widget_delete_confirm: str = ""
    widget_delete_confirm_named: str = ""
    widget_restore_confirm: str = ""
    # Demo pass 62, S1: «Tienes 2 abiertas: ¿cuál te enseño…?» was spoken in Spanish to an English operator — the
    # two «which card?» questions of `widgets/instances.py` were literals.
    instances_which_show: str = ""
    instances_which_close: str = ""
    instances_or: str = ""
    #: V2-812 T-06 — two cards of one piece that say the same thing are told apart by their place, never by id.
    instances_nth: str = ""
    widget_restore_nothing: str = ""
    cluster_connect_confirm: str = ("")

    # ── V2-709 — WHAT THE PROVIDER ASKS BACK, AND THE ANSWERS IT GIVES ──────────────────────────────────
    # The sibling leak of the V2-707 F6 one, found the same way — by him hearing it. Session `234457a3`,
    # 2026-09-16: an English session, and eight turns of «¿Cuál exactamente? Tengo Cita Agencia
    # Tributaria…», ending in «Why are you speaking Spanish?» twice.
    # These are not `notify`/`say` calls and not RETURN values either: they are ASSIGNMENTS to
    # `clarify["msg"]` inside `providers/nucleo.py`, a third shape the prose ratchet could not see — so it
    # now watches that field by name, and this is the table it reads from.
    #: The item reference did not resolve: the candidate list, or the bare question when there is none.
    ask_which_item: str = ""
    ask_which_item_bare: str = ""
    #: The turn's RECEIPT (V2-781, `card_receipt`): the cards a turn changed that its reply did not account for.
    receipt_closed: str = ""
    receipt_left: str = ""
    receipt_left_none: str = ""
    receipt_opened: str = ""
    receipt_on_card: str = ""
    receipt_and: str = ""
    #: The TRANSPORT receipt (`reply_receipts.player`, 2026-10-11): a reply that ignored the next/play/pause/add he
    #: asked for names what happened and what is playing now.
    receipt_now_playing: str = ""
    receipt_paused: str = ""
    receipt_queue_total: str = ""
    #: …naming the rows when they are few (2026-10-14: «Hecho.» over three videos he could not see were there).
    receipt_queue_titles: str = ""
    receipt_queue_empty: str = ""
    #: V2-807 T-16 — he asked one of our cards for a capability none of them declares: «not yet», and where the
    #: request went (kept as a suggestion, or the button to send one).
    capability_not_yet: str = ""
    capability_not_yet_noted: str = ""
    #: …and when the player REFUSED it (`player_outcome`): what could not play and why, never «Suena ahora».
    receipt_cannot_play: str = ""
    receipt_swapped: str = ""
    #: A pasted link from a channel he BLOCKED, let through because he asked (`reply_receipts.blocked_channel`, V2-604).
    receipt_blocked_channel_played: str = ""
    receipt_blocked_channel_queued: str = ""
    #: «Exit full screen» with no card at full screen (`fullscreen_nothing`): said, never «Hecho.».
    fullscreen_nothing: str = ""
    #: A row zaelar NAMED and he quotes back (V2-782, `own_words`): never denied — named, and where it is now.
    own_row_named: str = ""
    own_row_still: str = ""
    own_row_facts: str = ""
    own_row_no_facts: str = ""
    own_row_discarded: str = ""
    own_row_discarded_off: str = ""
    own_row_gone: str = ""
    #: The site he asked for blocked us, and the rows came from elsewhere (V2-782, `asked_site`).
    asked_site_blocked: str = ""
    asked_site_elsewhere: str = ""
    #: A delivery that names fewer rows than he asked for (or than a comparison needs) — the rest, by name.
    top_rows_line: str = ""
    #: OPENING a piece nobody can find (V2-609).
    open_no_such_piece: str = ""
    open_system_piece: str = ""
    #: RENAMING a widget — the two questions and the four answers.
    alias_which_widget: str = ""
    alias_which_name: str = ""
    alias_removed: str = ""
    alias_added: str = ""
    alias_unchanged_had: str = ""
    alias_unchanged_had_not: str = ""
    alias_failed: str = ""
    #: REPLYING without knowing to what, an OBJECTIVE without a peer, and STOPPING one of several workers.
    reply_which_message: str = ""
    objective_which_peer: str = ""
    stop_which_worker: str = ""
    #: refactor2710-07 — the model stopped the errand and the brief, unsure, read otherwise: asked, never refused silently.
    stop_doubt: str = ""
    #: refactor2710-99 — the stop backstop stopped an errand the model did not: said alone, or after the model's words.
    stopped_now: str = ""
    stopped_also: str = ""
    #: The mute backstop's LAST resort — what he hears when even the backstop that composes «never mute»
    #: raised. Found by the same ratchet pass, in the same file, in an English session.
    still_on_it: str = ""
    say_again: str = ""
    # The FIRST TURN, spoken in the operator's own voice into the model's window. It is not an internal note
    # like the system prompt: it impersonates HIM, so a Spanish one primes a Spanish reply on turn one.
    kickoff_prompt: str = ("")
    #: What the FIRST TURN says when the model behind it failed. The greeting answers nothing the operator
    #: said, so the reply-shaped fallback («say that again?») asks him to repeat words he never spoke.
    kickoff_fallback: str = ""
    # What a worker session says when it ENDS badly — `nucleo/workers/session.py`, four Spanish literals.
    worker_context_lost: str = ("")
    worker_relay_failed: str = ("")
    worker_no_relay: str = ("")
    # The worker chain ASLEEP (every tier in cooldown): what a turn says instead of «still on it», and what an
    # errand refused for it says once it is parked to resume at the reset time (`nucleo/workers/quota_wait.py`).
    worker_chain_asleep: str = ("")
    worker_chain_asleep_again: str = ""
    worker_chain_parked: str = ""
    worker_chain_parked_short: str = ""
    worker_chain_resumed: str = ""
    worker_chain_job_name: str = ""
    # A price said after an errand that FAILED, with nothing behind it (`nucleo/flash/amount_gate.py`).
    amounts_unbacked: str = ""
    worker_gave_up_context: str = ("")
    worker_command_denied: str = ("")
    worker_reach_gap: str = ("")
    worker_stalled: str = ("")
    worker_spinning: str = ("")
    worker_gave_up_provider: str = ("")
    # An errand that DIED while the reply promising it was being written — `nucleo/flash/death_line.py`.
    death_line: str = ""
    death_what_widget: str = ""
    death_what_task: str = ""
    death_why_rate: str = ""
    death_why_credit: str = ""
    death_why_auth: str = ""
    death_why_network: str = ""
    death_why_stalled: str = ""
    death_offer_retry: str = ""
    death_offer_fix: str = ""
    # A widget refused a data operation — `nucleo/flash/widget_data_turn.py`.
    widget_data_failed: str = ""
    widget_refused: str = ""
    widget_partial_failed: str = ""
    # The browser's own login ceremony — `widgets/navegador/owner.py`.
    login_opened: str = ("")
    login_not_saved: str = ""
    # V2-822 — no browser window can reach him (no display here, no connected daemon that can open one).
    login_needs_daemon: str = ""
    # V2-682 — THE INTRODUCTION MUST NOT ASK A QUESTION THIS LANGUAGE DOES NOT HAVE. The phase's goal list
    # was hardcoded «cómo prefiere que le hables (tú/usted)», so an ENGLISH conversation was asked «"tú" or
    # "usted", which do you prefer?» — three times in one session (2026-09-12, 20:08). English has no T–V
    # distinction, so there is no answer to give. Empty = the goal is not pursued, which is also what every
    # language with no spec of its own inherits: never ask about a distinction we cannot confirm exists.
    treatment_question: str = ""
    # The browser owner's own three sentences (V2-682) — all f-strings at a `notify` call, which is the
    # shape the prose ratchet could not see until it learned to join an f-string back together.
    login_left_halfway: str = ("")
    login_already_in: str = ""
    click_needs_ok: str = ""
    # …and with the gate's reason apart and whole: «Reload — el destino es una página de com» was read to an
    # English session, in Spanish and cut mid-word (find-direct-flight-budget EN, 2026-10-14; click_reason.py).
    click_needs_ok_why: str = ""
    nav_click_card_question: str = ""
    nav_click_this_action: str = ""
    nav_click_why_unreadable: str = ""
    nav_click_why_button: str = ""
    nav_click_why_secret: str = ""
    nav_click_why_payment: str = ""
    nav_click_why_checkout: str = ""
    # A form that wants HIS data is a question for the DATUM, never a yes/no to click (widgets/navegador/form_facts.py).
    form_needs_facts: str = ""
    form_fact_names: tuple = ()
    # What a row says about one of his HARD requirements (nucleo/flash/row_check.py): yes / no / not verified.
    row_check_yes: str = ""
    row_check_no: str = ""
    row_check_unknown: str = ""
    row_check_row_unknown: str = ""   # a row asked about something it does not carry
    claim_correction: str = ""
    # A restart caught a widget half-built — `widgets/server_api.py`.
    widget_build_resumed: str = ""
    # The two that already had an inline `if english:` ternary. They were CORRECT for an English operator and
    # wrong for everybody else — a second vocabulary that stops at two languages, which is the whole reason
    # this table exists. `delivery.py` and `reminder_guards.py` read them from here now.
    not_on_screen_yet: str = ""
    # A reply CLAIMED a reminder is set and no scheduled job exists — `nucleo/flash/reminder_promise.py`.
    reminder_not_set_yet: str = ""
    reminder_date_passed: str = ""
    # An asked notice whose hour had already gone today rings soon today instead — `nucleo/flash/notice_readback.py`.
    reminder_moved_soon: str = ""
    done_not_on_card: str = ""   # «Hecho.» over an unmet end state
    done_just_started: str = ""              # «Hecho.» over an errand that just started
    data_ack: str = ""       # short "done" when a widget data-op ran with no spoken content of its own (V2-026)
    # Demo pass 50: the words ASKED («…want me to write that?») and the order was carried out anyway — «?Done.» read
    # as the answer to its own question. After a question the line says it went ahead.
    data_ack_went_ahead: str = ""
    # Demo passes 108-109: after «¿cuál…?» the verdict PICKED one — said as a choice he can correct, not a go-ahead.
    data_ack_went_with: str = ""
    # V2-790 — a reply committed to an act and nothing ran: the plain «I have not done it» (`nucleo/turn/promise_kept.py`).
    promise_not_kept: str = ""
    # A correction of a results sheet ran as a data-op the model did not speak over (`nucleo/flash/correction_ack.py`):
    # «esos no son de Rosalía» got a bare «Hecho.» twice (find-concert-tickets ES, 2026-10-14). The line says what
    # changed: how many rows left the list, and that what does not fit no longer comes in.
    correction_dropped: str = ""
    correction_dropped_one: str = ""
    correction_noted: str = ""
    # V2-743 — the three beats of a CONFIRMED irreversible op. `work_started` replaces `data_ack` at the
    # moment the operator says yes: until today the gate answered «Hecho.» 0.86 s after DISPATCHING the
    # deletion and 7 s before any outcome existed. His own words for the beat he wanted: «me pongo a hacerlo
    # ahora mismo y te aviso». The other two are what the receipt says when it settles — and `op_unknown` is
    # the one that did not exist at all, which is why a pool timeout could only be reported as nothing.
    work_started: str = ""
    op_failed: str = ""
    op_unknown: str = ""
    # refactor2710-03 — the mouth speaks the verdict: ONE line per verdict of `nucleo/turn/reply.py`. `{object}` is
    # what the act named (a title, a queue), `{reason}` the act's own sentence for why not. A promise is a START.
    reply_started: str = ""
    reply_met: str = ""
    reply_unmet: str = ""
    reply_unverifiable: str = ""
    reply_undeclared: str = ""
    reply_cannot: str = ""
    reply_asked: str = ""
    reply_skipped: str = ""
    # V2-771 — a message that hands over SEVERAL tasks is a list (`nucleo/batch`). On receipt he hears that it
    # is a list and that work started — never the list read back to him, and no count: the count needs the
    # split (~5 s) and the receipt must not wait for it. The report comes ONCE, at
    # the end: counts, then only what failed, what needs him, and what is still running.
    list_started: str = ""
    # three-tasks-at-once (2026-10-10 20:00): a canned line is said ONCE per conversation — the receipt above
    # answered four distinct questions word for word. A second list gets this one; a third is an ordinary turn.
    list_started_again: str = ""
    list_done: str = ""
    list_failed: str = ""
    list_needs_you: str = ""
    list_still_running: str = ""
    # data-op ack variants (V2-038, post-P1/P2 test): two consecutive data-ops with the SAME "Done." triggered
    # the loop detector (LOOP×2) → consecutive functional responses are phrased differently. The provider chooses one
    # that does NOT repeat the previous one. Localized copy (lives in the language catalog, not test data).
    data_acks: tuple = ()
    # Demo pass 39: a NEW errand whose turn said nothing, after a lead-in filler — the opener is burned (it would restate
    # the filler) and the next variant said «Still on it» about work that had just started. This one claims no «still».
    filler_errand_taken: str = ""
    # Demo pass 47: the agenda's digest labelled tomorrow «(mañana, miércoles)» in an English session, and the reply
    # opened «mañana miércoles 30 you've got…». How far a date is travels in the language the agent speaks.
    day_today: str = ""
    day_tomorrow: str = ""
    day_after_tomorrow: str = ""
    day_in_days: str = ""
    weekdays: tuple = ()
    filler_still_working: str = ""  # V2-029: variation when a background task was ALREADY
                                    # a background task was already in progress when the turn began — do NOT repeat the same
                                    # filler_holding from turn to turn (the operator keeps insisting while the SlowBrain works)
    # V2-189: the same treatment as `data_acks`, which has existed since V2-038 because two consecutive «Done.» lines
    # triggered the loop detector — a treatment never applied to the waiting filler. Measured in
    # `cheapest-monitor` (2026-08-20 01:21): «Alright, give me a moment to look into that.» FOUR times word for
    # word, with the operator replying «okay, I'll wait» each time. The judge marked it serious in two different
    # cases. None of these asserts a STEP — that is the line V2-133 established and does not cross.
    holding_lines: tuple = ()
    # V2-603: the SAME treatment for the OTHER half of the mute backstop — the one with no background task
    # running, which had exactly one line, «Perdona, ¿me lo repites?», and said it every single time. Measured
    # on the operator's engine (2026-09-06, session e1acdcca): four times in ninety seconds, ending in «Pero
    # ¿por qué te lo tengo que repetir?». Two faults in one string. It repeats, which `holding_lines` exists to
    # prevent on the sibling branch; and it blames the operator's SPEECH for a turn the model returned empty —
    # he had been perfectly clear, four times. These say the honest thing instead: the fault was ours.
    #: Said when every `mute_lines` variant is already in the last three turns — the operator has repeated
    #: himself three times into an engine that keeps coming back empty. Cycling a fourth apology pretends this
    #: is a hiccup; it is not, and saying so is the only useful thing left.
    mute_stuck: str = ("")
    mute_lines: tuple = ()
    #: A turn with no words at all («👋», «👍») asks for nothing: answering it with an apology for a lost line
    #: blamed a turn nobody lost (dictate-a-reply-honestly EN, 2026-10-15, after the goodbyes).
    mute_wordless: str = ""
    # And from the third consecutive wait onward, the only honest fact available: how long it has been running. Without
    # inventing what point it has reached, and with a way out — something the operator can do with that information.
    filler_waited: str = ("")
    # PROACTIVE DELIVERY (finding 2026-07-23: nucleo/pulse/loop.py, nucleo/pulse/sparks.py, and connectors/messaging/notify.py
    # spoke with fixed Spanish f-strings without going through this catalog — deaf to a language change). These are
    # SPOKEN phrases initiated by zaelar itself (the operator did not request them in this turn): worker questions,
    # budget timeouts, spontaneous sparks, and messaging notices. Placeholders use `.format(...)`.
    worker_ask_named: str = ""
    worker_ask_generic: str = ""
    # A worker's action that needs his yes (`nucleo/cli/worker_policy.py`) — they were Spanish literals and reached
    # an English session as «El worker quiere hacer «delete_file»… ¿Lo autorizas?» (demo pass 2026-09-28).
    worker_confirm_channel: str = ""
    worker_confirm_widget: str = ""
    worker_confirm_generic: str = ""
    # An act in HIS name toward somebody he never named in this errand (`nucleo/on_his_behalf.py`).
    worker_confirm_on_behalf: str = ("")
    nav_form_on_behalf: str = ""
    worker_budget_killed: str = ("")
    # V2-776 L3 — said beside a forced ending: the END STATE the circuit read, not only the clock.
    worker_end_state_met: str = ""
    worker_end_state_unmet: str = ""
    worker_end_state_unverifiable: str = ""
    worker_timeout_running: str = ""
    # V2-776 D2 — said by the pulse when a worker goes SILENT (no event at all for STUCK_SECS). The stall
    # watchdog stops it a couple of minutes later and it is restarted ONCE (`workers/relay.restart_stalled`).
    worker_stuck: str = ("")
    # CONFIRMATION TIMEOUT (2026-08-16): a pending irreversible-action confirmation the operator never answered
    # (`widgets/confirm.py`'s 90s TTL) must not just vanish — the task stays undone and the operator has no way
    # to know unless told. Spoken/chatted once by `nucleo/pulse/loop.py::_supervise_confirms`, same proactive rails as
    # a stuck/timed-out worker above.
    confirm_expired: str = ("")
    spark_pending: str = ""
    generic_task: str = ""        # fallback for {goal} when the worker has no title of its own
    someone: str = ""              # fallback for {sender} when the connector provides no sender
    msg_notice_single: str = ""
    msg_notice_single_urgent: str = ""
    msg_notice_multi: str = ""
    # LEAD-IN FILLERS (2026-07-19): neutral, varied THINKING sounds to fill TTFT silence (~1.1s measured) ONLY when
    # the turn genuinely takes time (timer, `pick_filler`). They NEVER commit to or contradict the real response
    # (they are neutral, not "done/okay"): the actual utterance continues them. Naturalness, not filler everywhere.
    # V2-642 — the pool follows OpenAI's realtime prompting doctrine, which the operator pointed at
    # («OpenAI tiene un agente de voz que es brillante gestionando esos huecos»): a cover DESCRIBES THE
    # ACTION («I'll check that now»), never a bare thinking sound — their explicit avoid-list («Hmm…»,
    # «Let me think…», «One moment while I process…») was literally our old pool, and the 19:27 session
    # showed why: a sound that promises nothing invites «¿a ver qué?» back.
    #
    # V2-716 (2026-09-17) — that doctrine overshot, and the operator measured it: a cover that DESCRIBES an
    # action states something, and a stated thing can be WRONG («Good question…» answered «the one in
    # Telegram»; «I'll check that now…» answered «close everything»). His rule: «palabras más cortas, en plan
    # one second, yes, checking, ok — en español vale, sí, ajá». No conflict once named precisely: V2-642
    # banned MACHINE NOISE («Mmm…», «A ver…»); what survives is the ACKNOWLEDGEMENT («Vale…», «One sec…»),
    # true of every turn and never contradicted by the reply. Length is latency (a cover cannot be cut).
    fillers: tuple = ()
    # Lead-ins for a turn that is an ORDER to act (V2-572). «Déjame ver…» before closing a widget reads as
    # incomprehension — the operator's own words. These commit to nothing either: they promise motion, not a
    # result, so a turn that ends up declining («no puedo cerrar eso, hay un encargo en marcha») still
    # continues them naturally.
    fillers_action: tuple = ()
    # Lead-ins for a SOCIAL/META turn (V2-640) — the operator asks about the CONVERSATION itself or about us
    # («¿qué tal?», «¿de qué me estás hablando?», «¿qué quieres ver?»). A thinking sound here is what produced
    # the 19:27 besugos session: «Déjame ver…» answered «¿qué quieres ver?» and the operator asked what we
    # wanted to see, forever. These open an EXPLANATION or a presence, promise no looking, and the reply
    # continues them («Pues…» → «Pues te decía que…»).
    fillers_social: tuple = ()
    # ACK (V2-716): the turn ANSWERS a question WE just asked («¿cuál de los dos?» → «el de Telegram»).
    # Nothing is being looked up and nothing is being explained — the only honest sound is receipt. Measured
    # 2026-09-17 (sid 928c8761): «The one in Telegram.» got «Good question…», which the operator named as the
    # absurdity that made the whole dialogue read wrong.
    fillers_ack: tuple = ()
    # WORK COVERS (V2-669) — the SECOND cover, spoken at the TOOL SEAM, not before the model. A lead-in is a
    # blind guess made ~1.1 s in; by the time the router hands back a light route we KNOW what we are about to
    # do, and the measured hole is on the far side of that seam: with `deepseek-v4-pro` a web-search turn ends
    # 3.4-5.9 s AFTER the tool fires (7 real voice turns, 2026-09-04..11), and the lead-in's audio is long over.
    # These name the SOURCE, which is information the lead-in could not carry — that is what keeps them from
    # being a second stall («Voy a mirarlo…» then «Miro en agenda…» says something new). Short on purpose: a
    # cover cannot be cut mid-sentence, so its own length is latency (the operator's rule, 2026-09-11).
    covers_widget: tuple = ()
    covers_search: tuple = ()
    covers_recall: tuple = ()
    # V2-640 — the PRESENCE fast lane's spoken answers («¿sigues ahí?» must never wait 4 s for a model).
    # Two pools because the honest answer differs: idle = "I'm here, talk to me"; busy = "here, and still
    # on your task" — which is what that question really asks mid-task.
    presence_idle: tuple = ()
    presence_busy: tuple = ()
    # V2-674 — the PHRASEBOOK: the set phrases of a relationship (a greeting, «¿qué tal?», «gracias»,
    # «adiós»), with the replies to answer them with. Same reason as `presence_*` widened to the rest of the
    # connective tissue of a conversation, and DATA rather than a regex because Zaelar is language agnostic
    # and a regex is not: a new language is a translation of this table, never a code change. Matching lives
    # in `nucleo/flash/smalltalk.py`; the shape is
    #   {"vocatives": (…), "intents": {name: {"cues": (…), "replies": (…), "bounces"?, "after_bounce"?}}}
    smalltalk: dict = field(default_factory=dict)
    # V2-642 — the HONEST closer for a turn that produced no answer after a sounded cover. The operator's
    # rule: «igual no tenía respuesta, pero igualmente hay que cerrar las conversaciones» — a conversation
    # may end without an answer, never without an ending.
    # V2-717 — spoken when the reply PROMISED to look and the turn looked at nothing we can read: honest, and
    # it names the state (nothing running) so the operator is not left waiting on a look that never started.
    promise_retracted: str = ("")
    #: …and while a worker IS running (2026-10-22: «…and nothing is running» was said over two live workers). It
    #: retracts the look only and says nothing about the state — the live list is the panel's to show.
    promise_retracted_busy: str = ("")
    #: Said when a document was written in one request and is on screen (`compose_rung`). `{title}`.
    composed_on_screen: str = ("")
    #: The FIRST backed rows of an errand he asked to be told about, said once (`nucleo/turn/first_rows_notice`).
    #: Measured 2026-10-14: boats landed 34 s and kid-friendly activities 18 s after his last turn, and nothing
    #: reached him. The cues are DATA (accent-free, lowercase, matched as substrings): his «tell me» and our «I'll
    #: tell you» — a new language is a translation of these, never a code change.
    first_rows_notice: str = ""
    tell_me_cues: tuple = ()
    tell_you_cues: tuple = ()
    closers_no_answer: tuple = ()
    # The spoken confirmation of an already-EXECUTED direct action (the action-map fast lane). Unlike fillers
    # these DO commit — they are only ever spoken after the mutation happened, never as a lead-in.
    acks: tuple = ()
    # SECRETS VAULT (V2-060) — deterministic SPOKEN lines. The secret's value is inserted OUT-OF-BAND
    # (it never passes through the model): `secret_reveal.format(label=…, value=…)`. The others do not contain the value.
    secret_reveal: str = ""           # (F2: voice reading with log redaction)
    secret_shown: str = ""   # F1b: value through the UI, not by voice
    secret_locked: str = ("")
    secret_no_vault: str = ("")
    secret_not_found: str = ""
    secret_screen_only: str = ""
    secret_saved: str = ""   # after encrypting a new secret
    secret_need_vault: str = ("")                        # attempting to save without a vault yet
    energy_exhausted: str = ("")                                             # 2026-08-09, real accounts only
    energy_unconfirmed: str = ("")      # V2-801: stopped because the lease could not be renewed — NOT an empty account
    # SPLIT-FRAGMENT ACCUMULATOR (V2-096, fix 2026-08-15): two SPOKEN lines, delivered out of band
    # (`voice/proactive.speaker()`, same channel as V2-093's lead-in filler), that only exist because staying
    # completely silent left the operator with no way to tell "still listening" from "hung".
    acc_fragment_dropped: str = ("")
    #   spoken ONCE when a mid-chain fragment gets discarded by the gap valve (> MAX_GAP_S, 25s) — the reply that
    #   follows never proceeds as if those words never existed.
    acc_still_listening: str = ""
    #   spoken ONCE if a hold drags on longer than usual (ZAELAR_ACC_NUDGE_S, def 8s — above the real-world p90
    #   pause, 4.9s) — a reassurance, not an action: it never touches the buffer or forces the turn.
    kokoro_voices: list = field(default_factory=list)  # [{label, voice, gender}] native to this language
    kokoro_default: str = ""       # the reliable default voice for this language
