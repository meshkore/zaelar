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
    agenda_series_scope: str = "Esa cita se repite: ¿quito solo un día (cuál) o toda la serie?"
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
    # three-tasks-at-once (2026-10-10) — an errand the turn could NOT start (the worker pool takes three per turn)
    # is named back to him; dropping it silently left him waiting on work nothing was doing.
    errands_not_started: str = ("Eso sí, con esto no he empezado todavía: {what}. Cuando acabe alguna de las "
                                "otras, dímelo y me pongo.")
    # V2-757 — TOUCHING A CARD OF HIS IS ASKED FIRST. Measured live (session f84f91ef, 2026-09-23): with
    # the mic open the operator dictated a design brief to ANOTHER conversation, and the turn read it as
    # his to us — «lo mando hacer», a Brain Worker started rewriting the video card, and his «Olvídate de
    # eso, no va por ti» arrived when the task had already been running for a minute. His rule, from that
    # same day: «recuerda que hay que pedir confirmación siempre que pidamos crear un widget o modificar
    # un widget… que sea algo de sistema, porque así nos evitaremos que se empiecen a generar widgets por
    # ahí fuera de cualquier manera». The question is phrased the way HE put it — «si no me equivoco me
    # estás pidiendo que modifique esto» — because its whole job is to let him say NO.
    widget_build_confirm: str = ("Si no te he entendido mal, me pides que te CONSTRUYA una tarjeta nueva "
                                 "(«{what}»). Tarda unos minutos y se queda en tu catálogo. ¿La hago?")
    widget_change_confirm: str = ("Si no te he entendido mal, me pides que MODIFIQUE una tarjeta tuya y "
                                  "deje una versión nueva («{what}»). ¿Lo hago?")
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
    forward_confirm: str = "Voy a reenviar{what} a {who}{note}. ¿Lo envío?"
    forward_confirm_what: str = " el correo de {what}"
    forward_confirm_note: str = " con la nota: «{note}»"
    send_to_confirm_mandate: str = ("Voy a escribir{who}{via}: «{draft}». Es para {objective}: si contesta, "
                                     "sigo yo la conversación por ahí y te aviso. ¿Le escribo?")
    send_to_who: str = " a {who}"
    send_to_via: str = " por {via}"
    #: The three confirmations the voice provider asks in its own words: delete a widget, restore it to the
    #: shipped version, connect a MeshKore cluster. Same fault, same table.
    widget_delete_confirm: str = "¿Seguro que quieres que borre este widget?"
    widget_delete_confirm_named: str = "¿Seguro que quieres que borre el widget «{wid}»?"
    widget_restore_confirm: str = "¿Vuelvo el widget «{wid}» a la versión de sistema? Tu versión se descarta."
    # Demo pass 62, S1: «Tienes 2 abiertas: ¿cuál te enseño…?» was spoken in Spanish to an English operator — the
    # two «which card?» questions of `widgets/instances.py` were literals.
    instances_which_show: str = "Tienes {n} abiertas: ¿cuál te enseño, {which}?"
    instances_which_close: str = "Tienes {n} abiertas: ¿cuál cierro, {which}?"
    instances_or: str = "o"
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
    worker_spinning: str = ("Mi proceso de fondo se quedó dando vueltas sobre el mismo paso sin avanzar y lo he "
                            "parado. Se puede relanzar.")
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
    # Demo pass 50: the words ASKED («…want me to write that?») and the order was carried out anyway — «?Done.» read
    # as the answer to its own question. After a question the line says it went ahead.
    data_ack_went_ahead: str = "Ya lo he hecho, tal como lo pediste."
    # Demo passes 108-109: after «¿cuál…?» the verdict PICKED one — said as a choice he can correct, not a go-ahead.
    data_ack_went_with: str = "He ido con lo más probable; si era otra cosa, dímelo."
    # V2-743 — the three beats of a CONFIRMED irreversible op. `work_started` replaces `data_ack` at the
    # moment the operator says yes: until today the gate answered «Hecho.» 0.86 s after DISPATCHING the
    # deletion and 7 s before any outcome existed. His own words for the beat he wanted: «me pongo a hacerlo
    # ahora mismo y te aviso». The other two are what the receipt says when it settles — and `op_unknown` is
    # the one that did not exist at all, which is why a pool timeout could only be reported as nothing.
    work_started: str = "Me pongo a ello y te aviso."
    op_failed: str = "No he podido completarlo."
    op_unknown: str = "Lo he lanzado, pero no he podido confirmar que quedara hecho."
    # V2-771 — a message that hands over SEVERAL tasks is a list (`nucleo/batch`). On receipt he hears that it
    # is a list and that work started — never the list read back to him, and no count: the count needs the
    # split (~5 s) and the receipt must not wait for it. The report comes ONCE, at
    # the end: counts, then only what failed, what needs him, and what is still running.
    list_started: str = "Entendido, me pides varias cosas. Me pongo con ellas y te aviso cuando termine."
    list_done: str = "He terminado tu lista: {ok} de {n} hechas."
    list_failed: str = "No he podido con: {items}."
    list_needs_you: str = "Necesito que me aclares: {items}"
    list_still_running: str = "Aún siguen {n} en marcha; te aviso al acabar."
    # data-op ack variants (V2-038, post-P1/P2 test): two consecutive data-ops with the SAME "Done." triggered
    # the loop detector (LOOP×2) → consecutive functional responses are phrased differently. The provider chooses one
    # that does NOT repeat the previous one. Localized copy (lives in the language catalog, not test data).
    data_acks: tuple = ("Hecho.", "Listo.", "Ya está.", "Vale, hecho.", "Apuntado.")
    # Demo pass 39: a NEW errand whose turn said nothing, after a lead-in filler — the opener is burned (it would restate
    # the filler) and the next variant said «Still on it» about work that had just started. This one claims no «still».
    filler_errand_taken: str = "Te aviso en cuanto lo tenga."
    # Demo pass 47: the agenda's digest labelled tomorrow «(mañana, miércoles)» in an English session, and the reply
    # opened «mañana miércoles 30 you've got…». How far a date is travels in the language the agent speaks.
    day_today: str = "hoy"
    day_tomorrow: str = "mañana"
    day_after_tomorrow: str = "pasado mañana"
    day_in_days: str = "en {n} días"
    weekdays: tuple = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
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
    # A worker's action that needs his yes (`nucleo/worker_policy.py`) — they were Spanish literals and reached
    # an English session as «El worker quiere hacer «delete_file»… ¿Lo autorizas?» (demo pass 2026-09-28).
    worker_confirm_channel: str = "El worker quiere enviar algo al canal «{channel}». ¿Lo hago?"
    worker_confirm_widget: str = "El worker quiere hacer «{action}» en «{widget}», y no se puede deshacer. ¿Lo autorizas?"
    worker_confirm_generic: str = "El worker quiere ejecutar «{action}». ¿Lo autorizas?"
    worker_budget_killed: str = ("He parado «{goal}»: agotó su tiempo. Te dejo en la tarjeta lo que ha "
                                 "encontrado hasta ahora.")
    # V2-776 L3 — said beside a forced ending: the END STATE the circuit read, not only the clock.
    worker_end_state_met: str = "Aun así, lo que pediste sí quedó hecho: lo he comprobado."
    worker_end_state_unmet: str = "Lo que pediste no quedó hecho: queda {missing}."
    worker_end_state_unverifiable: str = "No he podido comprobar si lo que pediste quedó hecho."
    worker_timeout_running: str = "El proceso «{goal}» lleva ya {minutes} minutos. ¿Quieres que lo pare o que siga?"
    # V2-776 D2 — said by the pulse when a worker goes SILENT (no event at all for STUCK_SECS). The stall
    # watchdog stops it a couple of minutes later and it is restarted ONCE (`workers/relay.restart_stalled`).
    worker_stuck: str = ("El proceso «{goal}» lleva {minutes} minutos sin dar señales. Si no reacciona en un "
                         "par de minutos lo reinicio una vez.")
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
