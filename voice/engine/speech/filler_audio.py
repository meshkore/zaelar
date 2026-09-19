"""Lead-in filler as the reply's FIRST SEGMENT — the only place it can sound before the reply.

History, because this mechanism has died three times and the reasons must survive (V2-529, 2026-08-31;
replaces `voice/engine/llm/providers/lead_in_filler.py`, V2-093/V2-114/V2-122):

  · v1 pushed the filler as a ChatChunk into the reply's text stream and let it ride. LiveKit's sentence
    tokenizer RETAINED it (no sentence-final punctuation, under 20 chars), so it came out GLUED to the
    reply — late.
  · v2 spoke it out of band with `session.say(...)`. That is STRUCTURALLY late: when the filler fires the
    reply is already the scheduler's CURRENT speech, and `AgentActivity._scheduling_task` serializes on
    GENERATION — which for a reply includes waiting for its playout. Measured live (session e081f343):
    the filler's synthesis fired at the exact millisecond the reply's playout ended, and the operator
    heard “Okay, I’ll start the task” … “Wait, wait”.
  · v2.5 (same day) tried pre-synthesized frames from a `tts_node` wrapper. It cannot work either, and the
    reason is worth keeping: in this livekit-agents the reply is SEGMENTED, and `perform_tts_inference` —
    hence `tts_node` — is only called from `_start_segment()`, which runs when the FIRST TEXT CHUNK
    arrives. A node that only exists once text exists can never measure "the text is late". Verified live:
    a turn with TTFT 2.5s and the timer at 1.1s produced no filler at all.

  · v3 (this module) uses the pipeline's OWN segmentation. The filler is emitted from `llm_node` as text
    followed by a `FlushSentinel`, so it becomes the reply's FIRST SEGMENT: synthesized and played
    immediately, while the model is still thinking, and the reply follows as segment two — in order, in
    the same speech, with no scheduler to fight. A barge-in cancels the whole speech, filler included.

    v1's failure does not come back because v1 had no flush: the sentence tokenizer retained the phrase
    precisely because nothing closed the segment. Here the `FlushSentinel` closes it.

    The filler must not pollute the transcript or the conversation history, so it is stripped in
    `transcription_node` — the seam whose output IS what LiveKit forwards to the frontend and writes into
    `chat_ctx` (`forwarded_text`, not the LLM's raw `generated_text`). Its chat-wall visibility is pushed
    by us explicitly, marked (`kind="filler"`), exactly as V2-122's addenda decided.

The other half of the operator's request — “if we are going to answer in one second or less, do not add a
filler” —
falls out of the same seam: the wrapper races the model's first chunk against the delay (default 1100 ms,
`ZAELAR_FILLER_MS`; 0 disables). A fast reply never gets one.

ARM/CONSUME: only a turn that ARMED the filler can sound one. The voice provider arms per eligible brain
turn (never the kickoff); `say()` speeches (greeting, proactive deliveries) don't go through `llm_node` at
all. The arm is consumed AT FIRE TIME, not at generation start, because the node can begin a hair before
the brain's `_run_inner` gets to arm.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
import unicodedata

_ARM_TTL_S = 20.0
_ARM_GRACE_S = 0.8       # past the deadline, how long we keep polling for this turn to ARM (see the race
                         # below). A spin guard, not a behavioural bound: the first-chunk future always
                         # resolves, so in practice the loop exits there — this only saves a model that hangs.
_ARM_POLL_S = 0.05
# The SECOND cover (V2-669). `_WORK_GRACE_S` is how long a work note waits before it is allowed to sound: a
# second pass that comes back inside it beats the cover and nothing is said. `_COVER_MIN_GAP_S` is measured
# from the LEAD-IN's fire, not its playout, because this node cannot know how long the TTS took — it is the
# guard against the one failure this mechanism can produce, which the codebase has already met once (V2-189,
# session 2bdc67ee): two of our own canned waits back to back.
_WORK_GRACE_S = 0.35
_COVER_MIN_GAP_S = 1.6
_arm: tuple[float, object, str] | None = None   # (monotonic ts, brain, filler kind)
_jev_pending: tuple[float, object] | None = None  # (monotonic ts, jev handle) — the async request-type
                                                  # verdict racing this turn's deadline; consumed at fire time
_work: tuple[float, object, str, str] | None = None   # (monotonic ts, brain, work kind, target title)
_last_phrase = ""
_pending_strip: list[str] = []             # phrases emitted as fillers, awaiting removal from the transcript
_last_fired_at = 0.0                       # monotonic; read by the turn onset (V2-535) to say whether
                                           # the first audio the operator heard was the COVER or the reply


def delay_ms() -> int:
    try:
        return int(os.getenv("ZAELAR_FILLER_MS", "1100"))
    except Exception:
        return 1100


def enabled() -> bool:
    return delay_ms() > 0


# ── The engine is answering fast right now: stop arming (V2-716) ──────────────────────────────────────────
# The operator's second rule, 2026-09-17: «si las latencias de las contestaciones se están reduciendo a menos
# de un segundo, y esa es la media de las últimas frases, quizás no haga falta meterlas de relleno; si las una,
# dos o tres últimas se van más lejos de un segundo, entonces sí hay que volver a activar ese flag».
#
# The per-turn race (`delay_ms`) already silences a fast turn, so this does NOT change what the operator hears
# on a turn that beats the deadline. What it removes is the other half of arming, which the race cannot: the
# `[SISTEMA]` note `arm()` appends to the last user message, promising the model a cover phrase to continue.
# On an engine that is answering in well under a second that note is pure prompt noise steering replies into
# «Got it — …» continuations of a phrase that will never sound.
#
# Re-arming is deliberately TWITCHY in the slow direction: one recent turn over the deadline brings the cover
# back. A missing cover on a slow turn is dead air, which is the failure this whole module exists to prevent;
# an extra cover on a fast turn is one short word. Asymmetric on purpose.
_RECENT_TTFT: list[int] = []
_FAST_WINDOW = 3          # how many recent turns must ALL be fast before arming stops
_stranded = False         # V2-716: the last generation sounded a cover and the model answered nothing


def note_latency(ttft_ms) -> None:
    """One turn's measured time-to-first-spoken-token. Called by the voice provider once the turn's own
    metrics exist. `None` — a turn that produced no speakable text at all — is NOT a fast turn and is not a
    slow one either: it is no evidence, and recording it either way would be a lie the next turn acts on."""
    global _RECENT_TTFT
    try:
        v = int(ttft_ms)
    except (TypeError, ValueError):
        return
    if v <= 0:
        return
    _RECENT_TTFT.append(v)
    del _RECENT_TTFT[:-8]


def _note_stranded(value: bool) -> None:
    global _stranded
    _stranded = bool(value)


def stranded() -> bool:
    """The previous generation's cover was the ONLY thing the operator heard on that turn."""
    return _stranded


def answering_fast() -> bool:
    """True when the last `_FAST_WINDOW` measured turns ALL beat the cover deadline — the engine is fast
    enough right now that the cover has nothing to cover. False until that much evidence exists, so a fresh
    process, a reconnect or a model swap arms normally rather than guessing."""
    d = delay_ms()
    if d <= 0 or len(_RECENT_TTFT) < _FAST_WINDOW:
        return False
    return all(v < d for v in _RECENT_TTFT[-_FAST_WINDOW:])


# ── What kind of turn is being covered (V2-572) ───────────────────────────────────────────────────────────
# The operator heard «Déjame ver…» answer «cierra los mensajes» and named it: a thinking sound before an ORDER
# TO ACT reads as incomprehension. The cover phrase is chosen BEFORE any model has spoken, so the class can
# only come from the utterance's own shape — deterministic and coarse on purpose: an imperative action verb up
# front (leading interjections skipped — «a ver, cierra los mensajes» is his literal sentence) means the
# action pool; a question mark vetoes it («¿puedes cerrarlo?» asks first); everything else keeps thinking.

# V2-716 — the RE-STATEMENT prefixes join the courtesy ones. Measured (sid 928c8761): «I said, hide the left
# chat. Column.» and «So what I did say is, please, open the messages.» both classified NEUTRAL and got a
# thinking cover, because the imperative underneath never reached `_ACTION_VERB_RE`. A re-statement is the one
# turn where getting the class wrong is most expensive: the operator is already repeating himself.
_LEADING_CHATTER_RE = re.compile(
    r"^(?:a ver|oye|mira|vale|venga|bueno|pues|por favor|ok|okay|hey|please|"
    r"(?:lo que )?(?:te )?(?:he |habia |acabo de )?dicho(?: es)?|te he dicho que|te digo que|"
    r"i said|i just said|what i (?:did )?say(?: is)?|so what i (?:did )?say is|"
    r"like i said|as i said|i told you(?: to)?|i'm telling you(?: to)?|again)[,\s]+")
_ACTION_VERB_RE = re.compile(
    r"^(?:me\s+|lo\s+|la\s+|los\s+|las\s+)?(?:cierra\w*|abre\w*|quita\w*|muestra\w*|muestrame|ensename?\w*|"
    r"pon\w*|apaga\w*|enciende\w*|sube\w*|baja\w*|borra\w*|guarda\w*|manda\w*|envia\w*|arranca\w*|activa\w*|"
    r"desactiva\w*|silencia\w*|limpia\w*|vacia\w*|despeja\w*|"
    # V2-633: the media verbs the class was missing — «reproduce el vídeo» read as "neutral" and got a
    # thinking cover. «siguiente/anterior» are bare-noun commands («siguiente canción») but commands still.
    r"reproduce\w*|reanuda\w*|pausa\w*|salta\w*|cambia\w*|repite\w*|reinicia\w*|deten\w*|continua\w*|"
    r"siguiente|anterior|"
    # V2-652: the DATA-WRITE verbs the class was missing — «Añade en la agenda mañana una cita» read as
    # "neutral" and got «Un momento, que lo busco…», a searching promise over a write (session 7f77e2cc).
    # «busca…» stays OUT on purpose: a search takes real time and the thinking pool fits it.
    r"anade\w*|apunta\w*|anota\w*|agendame\w*|crea\w*|programa\w*|recuerda\w*|mete\w*|coloca\w*|"
    r"cancela\w*|elimina\w*|mueve\w*|"
    r"close|open|show|hide|dismiss|play|pause|mute|unmute|clear|turn|put|start|launch|send|save|delete|"
    r"resume|skip|next|previous|stop|replay|add|create|schedule|remind|set|cancel|remove|move)\b")


# V2-716 — the INDIRECT imperative. `_ACTION_VERB_RE` anchors on a sentence that OPENS with the verb, which is
# how an order is phrased when it is short. Half of this session's orders were not: «I want you to ask him if we
# can arrange a meeting», «you need to tell him that you're Johnny», «you need to start over», «I wanna see my
# WhatsApp». Every one of them classified NEUTRAL and got a thinking cover. Stripping the frame leaves the very
# sentence the anchored regex was written for, so the class comes out right with no new verb list — and, in
# `smart` mode, an ACTION turn gets no cover at all, which is the honest answer to an order.
_INDIRECT_ORDER_RE = re.compile(
    r"^(?:and |so |ok |okay |now )?(?:i (?:want|need) (?:you )?to|i wanna|i want to|i'd like you to|"
    r"you (?:need|have) to|you must|"
    r"(?:necesito|quiero) que(?: me)?|tienes que|hazme el favor de|"
    r"lo que (?:quiero|necesito) es que)\s+(?:me\s+|le\s+|lo\s+|la\s+)?")

# The verbs an indirect order reaches that a bare imperative rarely does — «I wanna SEE my WhatsApp» is an
# order to show something, not a search. Kept separate from `_ACTION_VERB_RE` so the bare-imperative list
# (which the action map also leans on) is not widened by this change.
_INDIRECT_VERB_RE = re.compile(r"^(?:see|watch|view|listen to|tell|ask|arrange|start over|redo)\b")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


# V2-640 — the SOCIAL/META class the 19:27 session was missing: the operator asks about the CONVERSATION
# itself («¿de qué me estás hablando?», «¿qué quieres ver?», «¿a qué tengo que esperar?») or about us
# («¿sigues ahí?», «¿qué tal?»), and a thinking cover («Déjame ver…») reads as an ANSWER that promises
# looking at something — so the operator asks what we want to see, and every such question arms another
# thinking cover: a self-sustaining dialogue of besugos, measured live (sid 1674ee35). Coarse and
# deterministic like the action class: only phrasings we can match without understanding.
_SOCIAL_RE = re.compile(
    r"(?:^|\b)(?:"
    r"que tal\b|como (?:estas|vas|va)\b|"
    r"sigues? ahi\b|estas? ahi\b|me (?:oyes|escuchas|recibes)\b|"
    r"hay alguien\b|estas? (?:disponible|operativ|vivo)\w*|"
    r"de que (?:me )?(?:estas? )?habla\w*|"
    r"que (?:quieres|querias) (?:ver|decir|mirar)\b|"
    r"para que (?:quieres|necesitas)\b|"
    r"a que tengo que esperar|"
    r"no (?:me )?estas (?:haciendo|entendiendo|escuchando|siguiendo)|"
    r"no estas haciendo nada|que dices\b|"
    # V2-652 — COMPLAINT shapes about our own behaviour: a thinking cover here reads as not listening.
    # Measured (session 7f77e2cc): «¿Qué tienes que buscar? Te he dicho que hagas una acción sobre la
    # agenda.» got «Déjame que lo mire…», and «Te he hecho una pregunta.» the same. These open an
    # explanation, never another look.
    r"te he (?:dicho|pedido)\b|te acabo de (?:decir|pedir)\b|te estoy (?:diciendo|pidiendo)\b|"
    r"te he hecho una pregunta|respondeme\b|contestame\b|"
    r"por que (?:lo |me )?has\b|que chorrada\b|no tiene (?:ningun )?sentido\b|"
    r"aclarate\b|en que quedamos\b|"
    r"how are you\b|are you (?:there|okay|alive|listening)\b|can you hear me\b|"
    r"what are you (?:talking about|doing)\b|what do you (?:want|mean)\b|"
    r"i (?:just )?(?:told|asked) you\b|answer (?:me|the question|my question)\b|why did you\b|"
    # V2-674 — measured (sid fdd096a3): «You were saying?» got «One sec, checking…» and then an invented
    # errand. Asking what WE were saying is a question about the conversation, never a reason to look at
    # something; the same shape in Spanish was already covered by «de que me estas hablando».
    r"(?:you|we) (?:were|was) saying\b|what were you saying\b|go on\b|carry on\b|"
    r"that makes no sense\b|"
    # V2-716 — the English half was thin, and this session ran in English: 20 of 21 covers came out of the
    # NEUTRAL pool, including every complaint. Measured shapes (sid 928c8761), each one a turn where a
    # thinking sound reads as not having listened:
    r"i'?m talking to you\b|^hello\??$|^hey\??$|anyone there\b|"
    r"you did ?n'?t (?:get|understand|hear|answer|confirm|reply)\b|"
    r"you did ?n'?t get the point\b|missed the point\b|"
    r"i did ?n'?t (?:tell|ask) you\b|i never (?:told|asked) you\b|"
    r"without my (?:request|permission|asking)\b|i did ?n'?t say\b|"
    r"is it (?:done|correct|right|ok|okay|all correct)\b|are you (?:done|sure)\b|"
    r"that (?:was|is) (?:correct|right|wrong)\b|"
    r"there(?:'s| is) (?:another |a )?problem\b|it'?s not working\b|"
    r"is there (?:any|a) problem\b|what'?s (?:the problem|going on|wrong)\b"
    r")")


# V2-642 — a DANGLING fragment gets NO cover. Measured 20:51:26: the STT delivered «Ahora quiero» alone
# and the turn covered it with «A ver qué tenemos…» — promising an answer to half a sentence. The shape is
# coarse: very short, no question mark, or ending in a word that grammatically cannot end a Spanish/English
# sentence. The turn itself still runs (the accumulator owns fragment semantics); only the PROMISE is held.
_DANGLING_TAIL_RE = re.compile(
    r"(?:^|\s)(?:que|quiero|quieres|de|del|la|el|los|las|un|una|unos|unas|me|te|se|le|les|lo|a|al|y|o|u|"
    r"con|para|por|mi|tu|su|mis|tus|sus|es|en|si|the|to|of|and|or|my|your|i|that|want)$")


def _dangling_fragment(text: str) -> bool:
    if "?" in (text or ""):
        return False
    n = _norm(text)
    if not n:
        return False                      # no utterance handed in = no evidence — suppression needs a POSITIVE
    return len(n.split()) <= 2 or bool(_DANGLING_TAIL_RE.search(n))


def _strip_vocative(n: str) -> str:
    """A leading wake word is the ADDRESS, never part of the order (V2-635's lesson, applied to covers):
    «Johnny añade en la agenda…» must classify like «añade en la agenda…». Only the KNOWN wake words come
    off; best-effort because this module must not hard-depend on the attention gate."""
    try:
        from voice import attention as _att
        stripped = _att.strip_leading_wakeword(n)
        if stripped:
            return stripped
    except Exception:
        pass
    return n


def _answers_our_question(last_reply: str, text: str) -> bool:
    """The turn ANSWERS a question WE just asked (V2-716). Deterministic and deliberately narrow: our last
    reply with real content ended in a question mark, and what came back is SHORT and asks nothing itself.

    Measured (sid 928c8761): we asked «Which one would you like me to contact?» and «the one in Telegram»
    got «Good question…» — the operator's named absurdity. Nothing is being looked up on a turn like this
    and nothing is being explained; the only sound that can't be contradicted by the reply is receipt."""
    lr = (last_reply or "").strip()
    if not lr.endswith("?"):
        return False
    t = (text or "").strip()
    if not t or "?" in t:
        return False
    return len(_norm(t).split()) <= 8


def filler_kind(text: str, last_reply: str = "") -> str:
    """"action" when any sentence opens with an imperative action verb and the turn asks nothing — an
    explicit order to act outranks everything, so a complaint that ENDS in «Quítalo inmediatamente» still
    gets motion; "ack" when the turn is a short ANSWER to a question we just asked (`last_reply`, V2-716);
    "social" when the utterance is about the conversation/us (see `_SOCIAL_RE` — those turns must never get
    a thinking sound); "neutral" otherwise (questions and statements keep the thinking pool). Feeds
    `langs.pick_filler(kind=…)`.

    V2-652 — the imperative is judged per SENTENCE, with a leading vocative stripped: «…es lo que pedí.
    Johnny. Añade en la agenda mañana una cita» carries its order in the LAST sentence, and anchoring on
    the whole utterance hid it (measured 2026-09-10, session 7f77e2cc).

    ORDER OF THE CLASSES, since three of them can fire on one sentence: an explicit order still outranks
    everything (V2-652's rule, unchanged). `ack` comes next and before `social`, because a bare answer to
    our own question («the one in Telegram») carries none of the complaint shapes anyway, and when it does
    («I said, the Telegram one») the operator is answering us, not opening a conversation about us."""
    n = _norm(text)
    if "?" not in (text or ""):
        for part in re.split(r"[.!;]+", _strip_vocative(n)):
            p = _strip_vocative(part.strip())
            for _ in range(3):
                p2 = _LEADING_CHATTER_RE.sub("", p)
                if p2 == p:
                    break
                p = p2
            if p and _ACTION_VERB_RE.match(p):
                return "action"
            # V2-716: the same sentence with its indirect frame («I want you to…», «you need to…») removed.
            # Tried only after the bare form, so nothing that classified before changes class now.
            q = _INDIRECT_ORDER_RE.sub("", p, count=1)
            if q != p and q and (_ACTION_VERB_RE.match(q) or _INDIRECT_VERB_RE.match(q)):
                return "action"
    if _answers_our_question(last_reply, text):
        return "ack"
    if _SOCIAL_RE.search(n):
        return "social"
    return "neutral"


def arm(brain, text: str = "", messages: list | None = None) -> str:
    """Called by the voice provider once per eligible turn, right where the model is about to be paid.
    `text` is the operator's utterance — it picks which filler POOL covers this turn (V2-572). Since V2-640
    the PHRASE is chosen here too, so the model can be told which cover may sound before its reply («que las
    siguientes frases continúen a partir de esas frases de relleno», operator 2026-09-09): when the turn's
    `messages` are handed in, a [SISTEMA] note with the exact phrase is appended to the LAST USER message —
    the local list only, so the stable prompt prefix (V2-536 cache) and the durable window never see it, and
    conditional wording on purpose (a fast reply gets no filler and the model cannot know which case it is
    in). The phrase is only committed (anti-echo, last-said) at fire time, if it sounds."""
    global _arm
    if _dangling_fragment(text):
        _arm = None                       # half a sentence gets no promise — V2-642
        return ""
    if answering_fast():
        _arm = None                       # the engine is beating the deadline on its own — V2-716
        return ""
    if _stranded:
        _note_stranded(False)             # one turn of silence, then covers resume — V2-716
        _arm = None
        return ""
    kind = filler_kind(text, last_reply=getattr(brain, "_last_reply", "") or "")
    phrase = ""
    try:
        from voice.engine.core import langs
        last = getattr(brain, "_last_filler", "") or _last_phrase
        phrase = langs.pick_filler(last, kind=kind)
    except Exception:
        phrase = ""
    _arm = (time.monotonic(), brain, kind, phrase)
    # Jev races the filler deadline on its own thread: the regex class above is already promised to the
    # model, and the fire site below swaps the pool only when Jev lands confident (nucleo/jev.py).
    global _jev_pending
    try:
        from nucleo import jev as _jev
        _jev_pending = (time.monotonic(), _jev.request_async(
            text, last_reply=getattr(brain, "_last_reply", "") or ""))
    except Exception:
        _jev_pending = None
    if phrase and messages and isinstance(messages[-1], dict) and messages[-1].get("role") == "user":
        messages[-1] = {**messages[-1], "content": str(messages[-1].get("content") or "") + (
            f"\n\n[SISTEMA] Si tu respuesta tarda, sonará antes «{phrase}» en tu voz. Que tu primera "
            "frase continúe esa muletilla con naturalidad (sin repetirla ni contradecirla); y que "
            "también funcione sola por si no llega a sonar.")}
    return phrase


def _consume_arm():
    global _arm
    if _arm is None:
        return None
    ts, brain, kind, phrase = _arm
    _arm = None
    if time.monotonic() - ts > _ARM_TTL_S:
        return None
    return brain, kind, phrase


def _consume_jev_kind(fallback: str) -> tuple[str, dict | None]:
    """Fire-time Jev verdict, never blocking. Returns (pool kind, info): Jev's pool when its thread
    landed before the deadline AND confident, else the regex fallback. Consumed once per turn, so a
    late verdict cannot leak into the next turn — it still emits its observability event for review."""
    global _jev_pending
    pending, _jev_pending = _jev_pending, None
    if pending is None:
        return fallback, None
    _, handle = pending
    try:
        from nucleo import jev as _jev
        return _jev.resolve_kind(handle, fallback)
    except Exception:
        return fallback, None


def _pick_phrase(brain, kind: str = "neutral", phrase: str = "") -> str:
    """Same guards the say-path filler had: never over the operator's voice, varied, anti-echo updated.
    An armed `phrase` (chosen at arm time, already promised to the model) is used verbatim; picking here
    remains the fallback for callers that never armed one."""
    global _last_phrase
    try:
        from voice import proactive as _pro
        if _pro.user_speaking():
            return ""
    except Exception:
        pass
    if not phrase:
        try:
            from voice.engine.core import langs
            last = getattr(brain, "_last_filler", "") or _last_phrase
            phrase = langs.pick_filler(last, kind=kind)
        except Exception:
            return ""
    if not phrase:
        return ""
    _last_phrase = phrase
    try:
        brain._last_filler = phrase
        # anti-echo (the mic must not re-capture it) — never the reply-context field the directed-content
        # judge reads (V2-105/V2-109): a filler carries no topic and would misclassify the operator's next
        # turn. A source guard in test_nucleo_directed_context.py bans that field's name from this file.
        brain._last_spoken = phrase
        brain._last_spoke_at = time.time()
    except Exception:
        pass
    return phrase


def note_work(brain, kind: str, target: str = "") -> None:
    """The provider publishes, at the TOOL SEAM, what this turn is about to go and do — "widget" | "search" |
    "recall" — so the node that is still waiting for the first chunk can cover the far side of that seam.

    Why here and not in the lead-in: the lead-in is chosen ~1.1 s in, before any model has spoken, so it can
    only ever be a blind thinking sound. The hole it does NOT cover is the one measured on 7 real voice turns
    (2026-09-04..11, `deepseek-v4-pro`): the turn ends 3.4-5.9 s AFTER the tool event, with the lead-in's audio
    long finished and nothing in between. By this point the route is decided, so the cover can name the SOURCE
    — which is new information, and the reason two covers do not read as the same wait twice.

    Deliberately VOICE-ONLY: the text channel (`nucleo/flash/probe.py`) has no dead air to fill — its answer
    appears when it appears — so the parallel-implementation rule (V2-252) does not reach this one, and that is
    written down rather than left as drift."""
    global _work
    if kind:
        _work = (time.monotonic(), brain, str(kind), str(target or ""))


def _peek_work():
    if _work is None:
        return None
    ts, brain, kind, target = _work
    if time.monotonic() - ts > _ARM_TTL_S:
        return None
    return ts, brain, kind, target


def _consume_work() -> None:
    global _work
    _work = None


def _pick_cover(brain, kind: str, target: str) -> str:
    """Same guards as `_pick_phrase` — never over the operator's voice, anti-echo updated, never the reply
    context — plus the one that only covers need: the LEAD-IN that just sounded is what we must not restate."""
    try:
        from voice import proactive as _pro
        if _pro.user_speaking():
            return ""
    except Exception:
        pass
    try:
        from voice.engine.core import langs
        phrase = langs.pick_cover(kind, target=target, last=_last_phrase)
    except Exception:
        return ""
    if not phrase:
        return ""
    try:
        # anti-echo only (`_last_spoken`), NEVER `_last_reply` — a cover carries no topic either, and the
        # directed-content judge misclassifies the next turn if it is fed one (the 2026-08-17 bug).
        brain._last_spoken = phrase
        brain._last_spoke_at = time.time()
    except Exception:
        pass
    return phrase


def last_fired_at() -> float:
    """Monotonic timestamp of the last filler that actually sounded (0.0 if none this process)."""
    return _last_fired_at


def played_recently(within_s: float = 20.0) -> str:
    """The filler phrase that actually SOUNDED within the last `within_s` seconds — "" otherwise. For the
    canned-line choosers (holding line): a wait the operator JUST heard must not be restated with other words
    (measured 2026-09-09, session 2bdc67ee: «Déjame que mire…» + «Vale, dame un momento que lo miro.» back to
    back — two of our own canned waits in a row). Time-bounded so a filler from a previous exchange never
    counts as this turn's."""
    if _last_phrase and _last_fired_at and (time.monotonic() - _last_fired_at) <= within_s:
        return _last_phrase
    return ""


def _announce(phrase: str, *, cover: str = "") -> None:
    """The filler's visibility contract (V2-122 addenda): observability + an EXPLICIT chat-wall event with
    its own kind, pushed synchronously at the decision — always before any real reply text exists. `cover`
    names the work kind when this is the SECOND cover (V2-669), so the two are told apart in the timeline."""
    global _last_fired_at, _last_phrase
    _last_fired_at = time.monotonic()
    _last_phrase = phrase          # covers feed the same anti-repetition window as lead-ins
    try:
        from voice.observer import emit
        label = f"🛠 cobertura de trabajo ({cover})" if cover else "💬 relleno de espera (lead-in)"
        emit("brain", label, text=phrase, role="system",
             extra={"cat": "flash", "after_ms": delay_ms(), "path": "segment",
                    **({"work": cover} if cover else {})})
        emit("filler", "cobertura" if cover else "relleno", text=phrase, role="assistant",
             extra={"cat": "flash", **({"work": cover} if cover else {})})
    except Exception:
        pass


def mark_for_strip(phrase: str) -> None:
    _pending_strip.append(phrase)


def strip_if_filler(chunk) -> bool:
    """True when this transcript chunk IS a filler we just emitted — consumed once, so a reply that
    genuinely opens with the same interjection is only ever dropped for the filler that is pending."""
    try:
        text = str(chunk).strip()
    except Exception:
        return False
    if not text:
        return False
    for i, ph in enumerate(_pending_strip):
        if text == ph.strip():
            _pending_strip.pop(i)
            return True
    return False


async def llm_node_with_filler(agent, default_impl, chat_ctx, tools, model_settings):
    """Wrap the default llm_node: pass every chunk through unchanged, and — only when this turn ARMED a
    filler and the model's first chunk is later than `delay_ms` — emit the filler text plus a
    `FlushSentinel` first, so it becomes the reply's own first SEGMENT (see module docstring)."""
    from livekit.agents.types import FlushSentinel

    inner = default_impl(agent, chat_ctx, tools, model_settings)
    if asyncio.iscoroutine(inner):
        inner = await inner
    wait_ms = delay_ms()

    q: asyncio.Queue = asyncio.Queue()
    _END = object()

    async def _pump():
        try:
            async for chunk in inner:
                await q.put(("c", chunk))
        except asyncio.CancelledError:
            raise
        except BaseException as e:  # noqa: BLE001 — the model's errors must PROPAGATE, not vanish
            await q.put(("err", e))
            return
        await q.put(("end", _END))

    pump = asyncio.create_task(_pump(), name="filler-llm-pump")
    get_t = asyncio.ensure_future(q.get())
    fired_any = False       # V2-716: this generation sounded a cover (lead-in or work cover)
    model_spoke = False     # V2-716: the model yielded at least one chunk of its own
    try:
        if wait_ms > 0:
            # The ARM and the deadline RACE, and the arm can lose: this node is entered before the brain's
            # `_run_inner` reaches its arm call (prompt build + tool selection sit in between), and how far
            # before varies per turn. Measured live 2026-08-31: one turn armed 150 ms BEFORE the deadline
            # (filler fired) and the next armed ~400 ms AFTER it (no filler, with TTFT 3.26 s — a turn that
            # plainly deserved one). So the deadline is not a single sleep: past it we keep polling for the
            # arm, still racing the model's first chunk, for a bounded grace. A generation that never arms
            # (the kickoff) just waits out the grace producing nothing — it is not yielding meanwhile either.
            #
            # V2-669 — the loop no longer STOPS once the lead-in has settled. The turn that takes longest is
            # the one that calls a tool, and on that turn the lead-in is over long before the answer exists:
            # measured on 7 real voice turns (2026-09-04..11, `deepseek-v4-pro`), a web-search turn ends
            # 3.4-5.9 s AFTER the tool event while the lead-in sounded ~1 s in. So the node keeps racing the
            # first chunk and covers a SECOND time when the provider publishes a work note (`note_work`).
            deadline = time.monotonic() + wait_ms / 1000.0
            give_up = deadline + _ARM_GRACE_S
            lead_settled = False        # the lead-in phase is over: it fired, or its window closed
            lead_at = 0.0               # monotonic of the lead-in that actually SOUNDED (0 = none did)
            covered = False             # at most ONE work cover per turn
            while not get_t.done():
                now = time.monotonic()
                left = (deadline - now) if (not lead_settled and now < deadline - _ARM_POLL_S) else _ARM_POLL_S
                await asyncio.wait({get_t}, timeout=max(left, 0.01))
                if get_t.done():
                    break
                now = time.monotonic()
                if not lead_settled:
                    if now < deadline:
                        continue
                    armed = _consume_arm()
                    if armed is None:
                        if now >= give_up:
                            lead_settled = True     # nothing armed — the WORK cover may still speak
                        continue
                    lead_settled = True
                    brain, kind, armed_phrase = armed
                    # Jev re-class: a confident verdict for a different pool re-picks the phrase from
                    # THAT pool. The [SISTEMA] note promised the regex phrase conditionally ("si tarda"),
                    # and all covers are equally short continuations — a wrong-class cover is the worse
                    # failure (the operator's "Good question" for an order).
                    try:
                        _jev_kind, _ = _consume_jev_kind(kind)
                        if _jev_kind != kind:
                            kind, armed_phrase = _jev_kind, ""
                    except Exception:
                        pass
                    # V2-633: the style policy rules the fire. Genesis "smart" drops the cover on ACTION
                    # turns («reproduce el vídeo» + «Un segundo…» measured as pure annoyance, session
                    # 6c715232); "off" (operator rule) drops it everywhere. Checked at fire time, so a
                    # rule given one turn ago already governs this one.
                    try:
                        from nucleo import style_policy as _style
                        if not _style.filler_allowed(kind):
                            continue
                    except Exception:
                        pass
                    phrase = _pick_phrase(brain, kind, armed_phrase)
                    if phrase:
                        _announce(phrase)
                        mark_for_strip(phrase)
                        fired_any = True
                        lead_at = now
                        yield phrase + " "
                        yield FlushSentinel()   # closes the segment → played on its own, right now
                    continue
                if covered:
                    break                       # nothing left to say — stop spinning, just await the chunk
                work = _peek_work()
                if work is None:
                    continue
                w_ts, w_brain, w_kind, w_target = work
                if now - w_ts < _WORK_GRACE_S:
                    continue                    # a fast second pass still beats the cover
                if lead_at and now - lead_at < _COVER_MIN_GAP_S:
                    continue                    # never two of our own waits back to back (V2-189)
                _consume_work()
                covered = True
                # The work cover asks the policy as a THINKING cover ("neutral"), so only an explicit
                # «no fillers» silences it. The operator's action-turn rule (V2-633) is about an order that
                # executes instantly — «reproduce esta canción» + «un segundo» — and a turn that is genuinely
                # six seconds deep in a tool is the case he asked to have covered (2026-09-11).
                try:
                    from nucleo import style_policy as _style2
                    if not _style2.filler_allowed("neutral"):
                        continue
                except Exception:
                    pass
                cover = _pick_cover(w_brain, w_kind, w_target)
                if cover:
                    _announce(cover, cover=w_kind)
                    mark_for_strip(cover)
                    fired_any = True
                    yield cover + " "
                    yield FlushSentinel()
        kind, val = await get_t
        while True:
            if kind == "err":
                raise val
            if kind == "end":
                break
            model_spoke = True
            yield val
            kind, val = await q.get()
    finally:
        # V2-716 — did this generation STRAND its cover? A cover that sounded on a turn the model then never
        # answered is the whole of what the operator heard, and the measure that named this is blunt: of the
        # 21 covers in session 928c8761, FIFTEEN had no reply behind them (17 barge-in cancellations, 4 turns
        # discarded with no text). His words: «yo le decía algo y él no me contestaba; sin embargo, sí me
        # soltaba la puñetera palabra de relleno». One stranded cover is a stumble; the run of six in 32 s
        # (740-772 s) is the conversation falling apart, so the NEXT turn is the one that must stay quiet.
        _note_stranded(bool(fired_any) and not model_spoke)
        if not pump.done():
            pump.cancel()


async def transcription_node_without_filler(agent, default_impl, text, model_settings):
    """Drop the filler from what LiveKit FORWARDS: this node's output is the subtitle stream and the text
    that becomes the assistant's `chat_ctx` message. The filler is real speech and IS shown in the chat
    wall — but by our own marked event, never inside the reply's own bubble or the model's history."""
    async def _filtered():
        async for chunk in text:
            if strip_if_filler(chunk):
                continue
            yield chunk

    out = default_impl(agent, _filtered(), model_settings)
    if asyncio.iscoroutine(out):
        out = await out
    if out is None:
        return
    async for chunk in out:
        yield chunk


def _reset_for_tests() -> None:
    global _arm, _last_phrase, _work, _last_fired_at, _jev_pending
    _arm = None
    _jev_pending = None
    _work = None
    _last_phrase = ""
    _last_fired_at = 0.0
    _pending_strip.clear()
    _RECENT_TTFT.clear()      # V2-716 — a stale fast window would silence the NEXT test's cover
    _note_stranded(False)
