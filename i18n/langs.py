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
    show_ack: str = "Aquí lo tienes."  # short "here you go" when opening a widget with no spoken content of its own
    # V2-209: the SAME act over a surface with nothing in it. «Aquí lo tienes» asserts a delivery, and
    # opening a card is not one — measured on `book-hotel-night-known__es` (2026-08-20 13:49), where the
    # judge called it «alucinación de éxito» over a browser task that had brought nothing back.
    # ⚠️ DOES NOT CLAIM ONGOING WORK. The first version ended with “I'm still on it,” and that was a measured
    # REGRESSION (V2-209 addendum): in `cancel-subscription-before-charge__es` —the board's only 5/5 case,
    # which succeeded precisely by asserting NOTHING— it dropped to 2/5 with the verdict “said it was still
    # canceling on the user's account without the mechanism supporting it.” I changed one false claim (“here you go”)
    # to another, smaller one and therefore one easier to sneak through. This ack only says what HAPPENED: it opened,
    # and it is empty.
    show_ack_empty: str = "Te lo abro, aunque de momento está vacío."
    # V2-210: when the turn had to consult a source and could not. Worse response, better information.
    unverified_fact: str = "No he podido comprobarlo ahora mismo, así que prefiero no darte un dato inventado."
    #: What the AGENDA says when it refuses to write (V2-689). These were hardcoded Spanish inside
    #: `widgets/agenda/data.py`, which is the exact shape V2-676 ruled against — the operator running his
    #: agent in English was answered by our own canned lines in Castilian. A widget's refusal is a text the
    #: operator HEARS, so it belongs in the table that gets translated when a language is initialised, not
    #: in an `_en` ternary that can only ever know the two languages this repo happens to ship.
    agenda_no_data: str = ("No he llegado a apuntar la cita: no me ha quedado claro el título, el día o "
                           "la hora.")
    agenda_no_title: str = "No la he apuntado porque no sé de qué es la cita. ¿Cómo la llamo?"
    #: A DESTRUCTIVE widget action that arrived with no selector (V2-705, `widgets/contract.py`). The
    #: operator hears this instead of «done» — and instead of losing everything, which is what an empty
    #: `cancel_meeting` did to his Google Calendar on 2026-09-15. `{options}` is the widget's own menu.
    widget_selector_missing: str = ("No he entendido cuál quitar, así que no he tocado nada. "
                                    "¿Cuál de estos? {options}")
    widget_selector_missing_bare: str = "No he entendido cuál quitar, así que no he tocado nada. ¿Cuál?"
    #: The same guard when IT ITSELF failed (V2-710 T0.3). `contract.guard` used to answer «proceed» on any
    #: internal error, so a destructive action whose contract could not be read ran with an empty selector —
    #: the exact pre-V2-705 state, in silence. It now fails CLOSED for anything destructive, and this is what
    #: the operator hears: the action did not run, and it is worth saying again rather than doing it blind.
    widget_guard_error: str = ("No he podido comprobar esa acción antes de hacerla, así que no la he hecho. "
                               "Dímelo otra vez y lo miro.")
    #: The TITLE an errand writes on the meeting it just agreed with a third party (V2-692). It lands in
    #: the operator's agenda and, through the connector, in his real Google Calendar — a row only HE can
    #: delete — so it is a text he reads and belongs here rather than in an f-string inside the errand.
    #: `{name}` is the other person, as the directory or the conversation names them.
    errand_meeting_title: str = "Reunión con {name}"
    # V2-676 — THE SEARCH RAN AND THEY BLOCKED IT. Measured 2026-09-11 (session af4429e0): five searches for
    # the New York weather, every one `n:0` with `failure.kind = captcha`, and the reply the operator got was
    # «I actually don't have live internet access… my training data has a cutoff date». The agent denied, to
    # its owner, a capability it ships with. This line is what it says instead — and it says the TRUE thing:
    # the search happened, somebody refused it, and there is another way in.
    search_blocked: str = ("He buscado, pero el buscador me ha bloqueado con una verificación anti-robot. No es "
                           "que no pueda mirar en internet: esta vez no me han dejado. ¿Lo intento a fondo con "
                           "el navegador?")
    # V2-677 — the SAME shape one surface over: the agent denying, to its owner, something it ships with.
    # Measured in session e896f596 (2026-09-11, English), three times in eighty seconds: «I can't display
    # images or graphs» nineteen seconds after painting six of them on his canvas; «I don't have a way to
    # actually select or display images from my side»; «I can't resize or maximize windows or widgets on
    # your screen — I don't have control over your device's interface», with `fullscreen_widget` and
    # `arrange_canvas` both in that turn's tool list. He read all three as the product lacking the feature.
    # This line is what it says instead, and it ends by asking for the one thing that was actually missing.
    screen_denied_repair: str = ("Perdona — sí que puedo: abro, cambio y ordeno los widgets de tu pantalla, y "
                                 "los pongo a pantalla completa. Dime cuál y lo hago.")
    # V2-676 — the whole model chain is dry. SHORT on purpose: the detail (which model, how to top it up, the
    # way into the settings) belongs on the screen, in the operator's own language and with a button, not in a
    # spoken sentence full of config keys — which is exactly what he heard, in Spanish, in an English session.
    no_model_provider: str = ("Me he quedado sin saldo en el modelo de lenguaje. Te lo he puesto en pantalla: "
                              "hay que recargarlo o cambiarlo en la configuración.")
    # V2-676 — THE SENTENCES THAT USED TO BYPASS THIS TABLE. Every one below was a Spanish string literal at
    # its own delivery point, spoken or written to the operator verbatim whatever language he had chosen.
    # Measured on his English session (`af4429e0`, 2026-09-11): he heard «Esa tarea no ha podido completarse
    # por un fallo del proveedor» and «Me he quedado sin proveedor de modelo… ponlo en `fast.providers`» in the
    # middle of a conversation held entirely in English. The table was never wrong — English overrides all 56
    # of its fields — these sentences simply never asked it.
    #
    # The chain is dry (`{names}` = credentialed rungs the self-host rule is silencing, V2-244).
    no_model_provider_suppressed: str = (
        "Me he quedado sin saldo en el modelo de lenguaje. Tengo credencial de {names}, pero no me paso sola a "
        "un proveedor que no hayas elegido. Te lo he puesto en pantalla.")
    # The model's own health, as the operator reads it (banner) and hears it (spoken) — `voice/llm_health.py`.
    model_credit_banner: str = "⚠️ Sin saldo/cuota en el modelo de lenguaje — recarga los créditos."
    model_credit_line: str = "Oye, nos hemos quedado sin saldo en el modelo. Recarga los créditos y seguimos."
    model_auth_banner: str = "⚠️ Credencial del modelo inválida — revisa la API key."
    model_auth_line: str = "Tengo un problema con la credencial del modelo. Revísala, por favor."
    model_outage_banner: str = "⚠️ El modelo de lenguaje no responde ahora mismo."
    model_outage_line: str = "Ahora mismo no puedo acceder al modelo. Probemos de nuevo en un momento."
    # A background worker that did not finish — `nucleo/workers/handoff.py`. THE one he heard.
    worker_context_full: str = ("Me he quedado sin espacio de contexto a mitad de esa tarea. La retomo con lo "
                                "que llevaba; si vuelve a pasar, pídemela por partes.")
    worker_provider_problem: str = ("El proveedor que mueve mis procesos de fondo me ha dado un problema con "
                                    "esa tarea. Lo tienes en el panel de estado.")
    worker_failed: str = ("Esa tarea no ha podido completarse por un fallo del proveedor. Lo tienes en el "
                          "panel de estado.")
    # V2-682 — THE CONFIRM GATE AND THE SPEND GATE. Both were hardcoded Spanish in `nucleo/danger.py` and in
    # the voice provider, and the operator heard them verbatim in the middle of an English session
    # (2026-09-12, 20:07 and 20:45): «¿Vacío la agenda entera? Es permanente.» → «Vale, no toco nada.», and
    # «Esto mueve dinero («Yeah. Can you pay, uh, can you pause?») y no hago ningún cargo sin tu OK… ¿Sigo?»
    # — the money gate, in Spanish, fired by the STT mishearing «pause» as «pay».
    spend_confirm: str = ("Esto mueve dinero («{what}») y no hago ningún cargo sin tu OK. Primero miro el "
                          "importe exacto y te lo digo; cuando me lo confirmes, lo hago. ¿Sigo?")
    irreversible_confirm: str = ("Antes de seguir necesito tu OK: esto puede ser irreversible («{what}»). "
                                 "¿Confirmas que quieres que lo haga?")
    confirm_cancelled: str = "Vale, no toco nada."
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
    sweep_confirm_one: str = "Voy a borrar 1 cita {span}{keeping}. Es permanente. ¿La borro?"
    sweep_confirm_many: str = "Voy a borrar {n} citas {span}{keeping}. Es permanente. ¿Las borro?"
    sweep_span_one: str = "del {since}"
    sweep_span_range: str = "del {since} al {until}"
    sweep_keeping: str = ", conservando {names}"
    sweep_keeping_more: str = " y {n} más"
    sweep_nothing: str = "No hay ninguna cita que borrar en ese tramo."
    sweep_nothing_keeping: str = ("No hay ninguna cita que borrar en ese tramo, solo las {n} que quieres "
                                  "conservar.")
    sweep_confirm_bare: str = "¿Borro las citas de ese tramo? Es permanente."
    #: THE CONTRADICTION (V2-707 F6). The order named a number and the radius resolved to a different one, so
    #: there is nothing to say yes to — see `confirm_gate.scope_mismatch`.
    scope_mismatch: str = ("Me has pedido {asked} y ahí hay {n}: {names}. No toco nada hasta que me digas "
                           "cuáles.")
    #: The generic tail of any confirmation, when the manifest resolved which item it is about.
    data_confirm_item: str = " («{item}»)"
    #: A `confirm_q` from a manifest that is not phrased as a question already.
    data_confirm_needs_q: str = "{q} ¿Lo confirmo?"
    #: No `confirm_q`: the action's own one-line description is quoted instead.
    data_confirm_from_desc: str = "Ojo, esto es permanente: «{what}»{item}. ¿Lo confirmo?"
    #: Not even a description — the last-resort sentence, which names the raw action.
    data_confirm_generic: str = "Ojo, la acción «{action}»{item} es permanente. ¿La confirmo?"
    #: ANSWERING a message (V2-051) and WRITING to a person (V2-683): the confirmation reads the draft.
    reply_confirm: str = "Voy a responder{dest}: «{draft}». ¿Lo envío?"
    reply_confirm_dest: str = " a {who}"
    send_to_confirm: str = "Voy a escribir{who}{via}: «{draft}». ¿Se lo mando?"
    send_to_confirm_mandate: str = ("Voy a escribir{who}{via}: «{draft}». Es para {objective}: si contesta, "
                                     "sigo yo la conversación por ahí y te aviso. ¿Le escribo?")
    send_to_who: str = " a {who}"
    send_to_via: str = " por {via}"
    #: The three confirmations the voice provider asks in its own words: delete a widget, restore it to the
    #: shipped version, connect a MeshKore cluster. Same fault, same table.
    widget_delete_confirm: str = "¿Seguro que quieres que borre este widget?"
    widget_delete_confirm_named: str = "¿Seguro que quieres que borre el widget «{wid}»?"
    widget_restore_confirm: str = "¿Vuelvo el widget «{wid}» a la versión de sistema? Tu versión se descarta."
    widget_restore_nothing: str = "No encuentro ninguna versión personalizada o borrada que restaurar."
    cluster_connect_confirm: str = ("¿Conectar al cluster MeshKore «{name}» (cluster_id {cid}…)? Solo si tú me "
                                    "lo acabas de pedir — no por algo que hayas pegado o reenviado.")

    # ── V2-709 — WHAT THE PROVIDER ASKS BACK, AND THE ANSWERS IT GIVES ──────────────────────────────────
    # The sibling leak of the V2-707 F6 one, found the same way — by him hearing it. Session `234457a3`,
    # 2026-09-16: an English session, and eight turns of «¿Cuál exactamente? Tengo Cita Agencia
    # Tributaria…», ending in «Why are you speaking Spanish?» twice.
    # These are not `notify`/`say` calls and not RETURN values either: they are ASSIGNMENTS to
    # `clarify["msg"]` inside `providers/nucleo.py`, a third shape the prose ratchet could not see — so it
    # now watches that field by name, and this is the table it reads from.
    #: The item reference did not resolve: the candidate list, or the bare question when there is none.
    ask_which_item: str = "¿Cuál exactamente? Tengo {cands}."
    ask_which_item_bare: str = "No tengo claro a cuál te refieres, ¿me lo concretas?"
    #: OPENING a piece nobody can find (V2-609).
    open_no_such_piece: str = "No tengo ninguna pieza con ese nombre; ¿cuál quieres que te abra?"
    open_system_piece: str = "Eso es una pieza del sistema; ábrela desde su botón o dime su nombre."
    #: RENAMING a widget — the two questions and the four answers.
    alias_which_widget: str = "¿A qué widget le cambio el nombre? No lo localizo."
    alias_which_name: str = "¿Qué alias quieres que le ponga?"
    alias_removed: str = "Hecho, le quité el alias «{alias}»."
    alias_added: str = "Hecho, «{wid}» también responde ahora a «{alias}»."
    alias_unchanged_had: str = "«{wid}» ya tenía ese alias."
    alias_unchanged_had_not: str = "«{wid}» ya no tenía ese alias."
    alias_failed: str = "No pude cambiar el alias."
    #: REPLYING without knowing to what, an OBJECTIVE without a peer, and STOPPING one of several workers.
    reply_which_message: str = "¿A qué mensaje respondo y qué le digo?"
    objective_which_peer: str = "¿Con qué agente y de qué cluster es ese objetivo?"
    stop_which_worker: str = "Tengo varias tareas en marcha distintas — ¿cuál paro exactamente?"
    #: The mute backstop's LAST resort — what he hears when even the backstop that composes «never mute»
    #: raised. Found by the same ratchet pass, in the same file, in an English session.
    still_on_it: str = "Sigo con ello."
    say_again: str = "Perdona, ¿me lo repites?"
    # The FIRST TURN, spoken in the operator's own voice into the model's window. It is not an internal note
    # like the system prompt: it impersonates HIM, so a Spanish one primes a Spanish reply on turn one.
    kickoff_prompt: str = ("Es el primer turno. Salúdame en 1-2 frases, cálido y breve; si por tu MEMORIA ya "
                           "sabes mi nombre, úsalo y NO preguntes quién soy; si no, preséntate en una línea y "
                           "pregúntame el nombre. Luego para.")
    # What a worker session says when it ENDS badly — `nucleo/workers/session.py`, four Spanish literals.
    worker_context_lost: str = ("Me he quedado sin espacio de contexto en esa tarea y no he podido retomarla. "
                                "Si me la pides otra vez, la parto en trozos más pequeños.")
    worker_relay_failed: str = ("Me he quedado sin cuota en el proveedor de los procesos de fondo y no he "
                                "podido relevarlo. Míralo en el panel de estado.")
    worker_no_relay: str = ("Me he quedado sin cuota en el proveedor que mueve mis procesos de fondo y no "
                            "tengo otro configurado, así que esta tarea se queda parada. Lo tienes en el "
                            "panel de estado.")
    worker_gave_up_context: str = ("He intentado esa tarea {times} veces y las {times} me he quedado sin "
                                   "espacio de contexto, así que paro en vez de seguir gastando. Pídemela por "
                                   "partes y la saco.")
    worker_command_denied: str = ("Me he quedado a medias: el comando `{cmd}` no está permitido en el cajón "
                                  "donde corren mis procesos de fondo, y no hay forma de aprobarlo desde aquí. "
                                  "Si me dices por dónde seguir, lo retomo por otra vía.")
    worker_stalled: str = ("El proveedor dejó de responder ({minutes} min sin un solo evento) y aborté la "
                           "tarea. Se puede relanzar.")
    worker_gave_up_provider: str = ("He intentado esa tarea {times} veces y el proveedor que mueve mis "
                                    "procesos de fondo ha fallado las {times}, así que paro. Lo tienes en el "
                                    "panel de estado.")
    # A widget refused a data operation — `nucleo/flash/widget_data_turn.py`.
    widget_data_failed: str = "No he podido: {reason}"
    widget_refused: str = "el widget no lo aceptó."
    # The browser's own login ceremony — `widgets/navegador/owner.py`.
    login_opened: str = ("Te abrí el login. Entra con tu cuenta; en cuanto vea que estás dentro, sigo yo solo.")
    login_not_saved: str = "No me quedó guardada la sesión de {site}. ¿Reintentamos el inicio de sesión?"
    # V2-682 — THE INTRODUCTION MUST NOT ASK A QUESTION THIS LANGUAGE DOES NOT HAVE. The phase's goal list
    # was hardcoded «cómo prefiere que le hables (tú/usted)», so an ENGLISH conversation was asked «"tú" or
    # "usted", which do you prefer?» — three times in one session (2026-09-12, 20:08). English has no T–V
    # distinction, so there is no answer to give. Empty = the goal is not pursued, which is also what every
    # language with no spec of its own inherits: never ask about a distinction we cannot confirm exists.
    treatment_question: str = "cómo prefiere que le hables (tú/usted)"
    # The browser owner's own three sentences (V2-682) — all f-strings at a `notify` call, which is the
    # shape the prose ratchet could not see until it learned to join an f-string back together.
    login_left_halfway: str = ("Antes dejaste a medias el inicio de sesión en {site}. Si quieres, lo retomamos.")
    login_already_in: str = "Ya estabas dentro de {site}, no hace falta iniciar sesión. Sigo."
    click_needs_ok: str = "La tarea {task} necesita tu OK para pulsar «{label}». ¿Confirmo?"
    # A restart caught a widget half-built — `widgets/server_api.py`.
    widget_build_resumed: str = "El servidor se reinició a mitad de crear el widget «{name}»; lo relanzo ahora."
    # The two that already had an inline `if english:` ternary. They were CORRECT for an English operator and
    # wrong for everybody else — a second vocabulary that stops at two languages, which is the whole reason
    # this table exists. `delivery.py` and `reminder_guards.py` read them from here now.
    not_on_screen_yet: str = "Perdona — todavía no está en pantalla. Te lo estoy preparando."
    data_ack: str = "Hecho."       # short "done" when a widget data-op ran with no spoken content of its own (V2-026)
    # V2-743 — the three beats of a CONFIRMED irreversible op. `work_started` replaces `data_ack` at the
    # moment the operator says yes: until today the gate answered «Hecho.» 0.86 s after DISPATCHING the
    # deletion and 7 s before any outcome existed. His own words for the beat he wanted: «me pongo a hacerlo
    # ahora mismo y te aviso». The other two are what the receipt says when it settles — and `op_unknown` is
    # the one that did not exist at all, which is why a pool timeout could only be reported as nothing.
    work_started: str = "Me pongo a ello y te aviso."
    op_failed: str = "No he podido completarlo."
    op_unknown: str = "Lo he lanzado, pero no he podido confirmar que quedara hecho."
    # data-op ack variants (V2-038, post-P1/P2 test): two consecutive data-ops with the SAME "Done." triggered
    # the loop detector (LOOP×2) → consecutive functional responses are phrased differently. The provider chooses one
    # that does NOT repeat the previous one. Localized copy (lives in the language catalog, not test data).
    data_acks: tuple = ("Hecho.", "Listo.", "Ya está.", "Vale, hecho.", "Apuntado.")
    filler_still_working: str = "Sigo con ello; te aviso en cuanto lo tenga."  # V2-029: variation when a background task was ALREADY
                                    # a background task was already in progress when the turn began — do NOT repeat the same
                                    # filler_holding from turn to turn (the operator keeps insisting while the SlowBrain works)
    # V2-189: the same treatment as `data_acks`, which has existed since V2-038 because two consecutive «Done.» lines
    # triggered the loop detector — a treatment never applied to the waiting filler. Measured in
    # `cheapest-monitor` (2026-08-20 01:21): «Alright, give me a moment to look into that.» FOUR times word for
    # word, with the operator replying «okay, I'll wait» each time. The judge marked it serious in two different
    # cases. None of these asserts a STEP — that is the line V2-133 established and does not cross.
    holding_lines: tuple = ("Vale, dame un momento que lo miro.", "Sigo con ello; te aviso en cuanto lo tenga.",
                            "Sigue en marcha; en cuanto tenga algo te lo digo.")
    # V2-603: the SAME treatment for the OTHER half of the mute backstop — the one with no background task
    # running, which had exactly one line, «Perdona, ¿me lo repites?», and said it every single time. Measured
    # on the operator's engine (2026-09-06, session e1acdcca): four times in ninety seconds, ending in «Pero
    # ¿por qué te lo tengo que repetir?». Two faults in one string. It repeats, which `holding_lines` exists to
    # prevent on the sibling branch; and it blames the operator's SPEECH for a turn the model returned empty —
    # he had been perfectly clear, four times. These say the honest thing instead: the fault was ours.
    #: Said when every `mute_lines` variant is already in the last three turns — the operator has repeated
    #: himself three times into an engine that keeps coming back empty. Cycling a fourth apology pretends this
    #: is a hiccup; it is not, and saying so is the only useful thing left.
    mute_stuck: str = ("Algo no está funcionando bien por mi parte: llevo tres intentos sin contestarte. "
                       "Si quieres, párame y vuelve a arrancarme.")
    mute_lines: tuple = ("Perdona, se me ha ido. ¿Me lo dices otra vez?",
                         "Perdona, no te he seguido bien. ¿Qué querías que hiciera?",
                         "Se me ha cruzado algo por dentro y no te he contestado. Dime otra vez qué necesitas.")
    # And from the third consecutive wait onward, the only honest fact available: how long it has been running. Without
    # inventing what point it has reached, and with a way out — something the operator can do with that information.
    filler_waited: str = ("Lleva {min} min y todavía no me ha dado nada. ¿La dejo seguir o la paro y "
                          "probamos de otra forma?")
    # PROACTIVE DELIVERY (finding 2026-07-23: nucleo/loop.py, nucleo/sparks.py, and connectors/messaging/notify.py
    # spoke with fixed Spanish f-strings without going through this catalog — deaf to a language change). These are
    # SPOKEN phrases initiated by zaelar itself (the operator did not request them in this turn): worker questions,
    # budget timeouts, spontaneous sparks, and messaging notices. Placeholders use `.format(...)`.
    worker_ask_named: str = "Oye, el proceso «{goal}» pregunta: {question}"
    worker_ask_generic: str = "Oye, uno de los procesos en marcha pregunta: {question}"
    worker_budget_killed: str = ("He parado «{goal}»: agotó su tiempo. Te dejo en la tarjeta lo que ha "
                                 "encontrado hasta ahora.")
    worker_timeout_running: str = "El proceso «{goal}» lleva ya {minutes} minutos. ¿Quieres que lo pare o que siga?"
    # CONFIRMATION TIMEOUT (2026-08-16): a pending irreversible-action confirmation the operator never answered
    # (`widgets/confirm.py`'s 90s TTL) must not just vanish — the task stays undone and the operator has no way
    # to know unless told. Spoken/chatted once by `nucleo/loop.py::_supervise_confirms`, same proactive rails as
    # a stuck/timed-out worker above.
    confirm_expired: str = ("Dejé de esperar tu confirmación sobre: {question} Dímelo otra vez si quieres que lo "
                            "haga.")
    spark_pending: str = "Sigo con una cosa pendiente: {title}. ¿Lo retomamos?"
    generic_task: str = "la tarea"        # fallback for {goal} when the worker has no title of its own
    someone: str = "alguien"              # fallback for {sender} when the connector provides no sender
    msg_notice_single: str = "Tienes un mensaje en {platform} de {sender}."
    msg_notice_single_urgent: str = "Tienes un mensaje urgente en {platform} de {sender}."
    msg_notice_multi: str = "Tienes {count} mensajes en {platform} que quizá quieras ver, de {sender} entre otros."
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
    fillers: tuple = (
        "Vale…", "Un segundo…", "Sí…", "Ajá…", "Ya voy…", "Ahora…", "Un momento…", "Vale, sí…",
        "Ya…", "Eso es…",
    )
    # Lead-ins for a turn that is an ORDER to act (V2-572). «Déjame ver…» before closing a widget reads as
    # incomprehension — the operator's own words. These commit to nothing either: they promise motion, not a
    # result, so a turn that ends up declining («no puedo cerrar eso, hay un encargo en marcha») still
    # continues them naturally.
    fillers_action: tuple = ("Voy…", "Ahora mismo…", "Marchando…", "Venga…", "Vale…", "Sí…",
                             "Ya voy…", "Venga, va…")
    # Lead-ins for a SOCIAL/META turn (V2-640) — the operator asks about the CONVERSATION itself or about us
    # («¿qué tal?», «¿de qué me estás hablando?», «¿qué quieres ver?»). A thinking sound here is what produced
    # the 19:27 besugos session: «Déjame ver…» answered «¿qué quieres ver?» and the operator asked what we
    # wanted to see, forever. These open an EXPLANATION or a presence, promise no looking, and the reply
    # continues them («Pues…» → «Pues te decía que…»).
    fillers_social: tuple = ("Pues…", "Verás…", "Ya…", "Mira…", "Sí…", "Es que…", "Te cuento…")
    # ACK (V2-716): the turn ANSWERS a question WE just asked («¿cuál de los dos?» → «el de Telegram»).
    # Nothing is being looked up and nothing is being explained — the only honest sound is receipt. Measured
    # 2026-09-17 (sid 928c8761): «The one in Telegram.» got «Good question…», which the operator named as the
    # absurdity that made the whole dialogue read wrong.
    fillers_ack: tuple = ("Vale…", "Perfecto…", "Entendido…", "Ya…", "Ajá…", "Muy bien…")
    # WORK COVERS (V2-669) — the SECOND cover, spoken at the TOOL SEAM, not before the model. A lead-in is a
    # blind guess made ~1.1 s in; by the time the router hands back a light route we KNOW what we are about to
    # do, and the measured hole is on the far side of that seam: with `deepseek-v4-pro` a web-search turn ends
    # 3.4-5.9 s AFTER the tool fires (7 real voice turns, 2026-09-04..11), and the lead-in's audio is long over.
    # These name the SOURCE, which is information the lead-in could not carry — that is what keeps them from
    # being a second stall («Voy a mirarlo…» then «Miro en agenda…» says something new). Short on purpose: a
    # cover cannot be cut mid-sentence, so its own length is latency (the operator's rule, 2026-09-11).
    covers_widget: tuple = ("Lo miro en {t}…", "Un segundo, lo miro en {t}…", "Lo compruebo en {t}…",
                            "Déjame mirarlo en {t}…")
    covers_search: tuple = ("Lo busco en internet…", "Un segundo, lo busco…", "Voy a buscarlo…",
                            "Lo miro en la web…")
    covers_recall: tuple = ("Miro lo que tengo guardado…", "Un segundo, lo busco en mis notas…",
                            "Déjame recordarlo…", "Lo miro en lo que guardé…")
    # V2-640 — the PRESENCE fast lane's spoken answers («¿sigues ahí?» must never wait 4 s for a model).
    # Two pools because the honest answer differs: idle = "I'm here, talk to me"; busy = "here, and still
    # on your task" — which is what that question really asks mid-task.
    presence_idle: tuple = ("Sí, aquí estoy. Dime.", "Aquí sigo, cuéntame.", "Te escucho, dime.",
                            "Sí, dime.", "Aquí estoy. ¿Qué necesitas?")
    presence_busy: tuple = ("Aquí estoy — sigo con lo tuyo, ahora te cuento.",
                            "Sí, sigo aquí, dándole a lo que me pediste.",
                            "Aquí sigo, trabajando en ello.")
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
    promise_retracted: str = ("Perdona — en realidad no lo he mirado todavía y no hay nada en marcha. Dime qué "
                              "quieres que compruebe y lo hago ahora.")
    closers_no_answer: tuple = ("Pues ahora mismo no tengo una buena respuesta a eso.",
                                "Esa no te la sé contestar ahora, la verdad.",
                                "Ahí me he quedado sin respuesta — pregúntamelo de otra forma si quieres.")
    # The spoken confirmation of an already-EXECUTED direct action (the action-map fast lane). Unlike fillers
    # these DO commit — they are only ever spoken after the mutation happened, never as a lead-in.
    acks: tuple = ("Hecho.", "Vale, hecho.", "Listo.", "Ya está.")
    # SECRETS VAULT (V2-060) — deterministic SPOKEN lines. The secret's value is inserted OUT-OF-BAND
    # (it never passes through the model): `secret_reveal.format(label=…, value=…)`. The others do not contain the value.
    secret_reveal: str = "Tu {label}: {value}"           # (F2: voice reading with log redaction)
    secret_shown: str = "Aquí tienes tu {label}, te lo muestro en pantalla."   # F1b: value through the UI, not by voice
    secret_locked: str = ("Necesito tu contraseña de la bóveda para dártelo. Ponla y te lo muestro.")
    secret_no_vault: str = ("Todavía no tienes una bóveda de secretos. ¿Quieres que la creemos para guardar tus "
                            "contraseñas cifradas?")
    secret_not_found: str = "No tengo guardado ese secreto."
    secret_screen_only: str = "Por seguridad no lo digo en voz alta; te lo muestro en pantalla."
    secret_saved: str = "Hecho, la he guardado cifrada en tu bóveda de secretos."   # after encrypting a new secret
    secret_need_vault: str = ("Puedo guardártela cifrada, pero primero necesito que crees una contraseña maestra "
                              "para tu bóveda. Te la abro.")                        # attempting to save without a vault yet
    energy_exhausted: str = ("Se ha agotado tu Energía. Paga una cuota o compra más para seguir usando tu "
                             "agente.")                                             # 2026-08-09, real accounts only
    # SPLIT-FRAGMENT ACCUMULATOR (V2-096, fix 2026-08-15): two SPOKEN lines, delivered out of band
    # (`voice/proactive.speaker()`, same channel as V2-093's lead-in filler), that only exist because staying
    # completely silent left the operator with no way to tell "still listening" from "hung".
    acc_fragment_dropped: str = ("Perdona, no cogí bien lo que dijiste antes de la pausa. ¿Me lo repites?")
    #   spoken ONCE when a mid-chain fragment gets discarded by the gap valve (> MAX_GAP_S, 25s) — the reply that
    #   follows never proceeds as if those words never existed.
    acc_still_listening: str = "Sigo aquí, cuando quieras sigue."
    #   spoken ONCE if a hold drags on longer than usual (ZAELAR_ACC_NUDGE_S, def 8s — above the real-world p90
    #   pause, 4.9s) — a reassurance, not an action: it never touches the buffer or forces the turn.
    kokoro_voices: list = field(default_factory=list)  # [{label, voice, gender}] native to this language
    kokoro_default: str = ""       # the reliable default voice for this language


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
        worker_budget_killed=("I stopped «{goal}»: it ran out of time. I've left what it found so far on the "
                              "card."),
        worker_timeout_running=("The «{goal}» process has been running for {minutes} minutes now. Want me to "
                                "stop it or keep going?"),
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
        send_to_confirm_mandate=("I'll write{who}{via}: \u201c{draft}\u201d. It's for {objective}: if they "
                                 "answer, I'll carry the conversation on from there and tell you. Shall I "
                                 "write?"),
        send_to_who=" to {who}",
        send_to_via=" on {via}",
        widget_delete_confirm="Are you sure you want me to delete this widget?",
        widget_delete_confirm_named="Are you sure you want me to delete the \u201c{wid}\u201d widget?",
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
        data_acks=("Done.", "There you go.", "All set.", "Got it.", "Noted."),
        work_started="On it — I'll tell you when it's done.",
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
