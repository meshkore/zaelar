#
# capsule.py — the conversation CAPSULE with an agent (V2-069 "one mind").
#
# It is NOT a new engine or a new store: it is the SHAPE a RELATIONSHIP memory takes, just as a human remembers who
# each person is, what they discussed, what remained pending, and where the conversation stands. It lives on the SAME
# central memory, scoped by (cluster, peer) and QUARANTINED (trust=untrusted) — it never mixes with operator state or
# enters the operator prompt. This is the piece that makes talking to an agent the SAME act as talking to the
# operator, only "situated" in another relationship.
#
# What it contributes (what the channel lacked, causing it to degenerate into 71h of re-introductions and waiting):
#   · Conversation PHASE (greeting -> probing -> work -> closure) -> do not re-introduce every turn.
#   · Current OBJECTIVE (set by the operator) -> steer toward it, do not drift.
#   · OPEN LOOPS (what was requested / already refused) -> "I already said no; back to the objective."
#   · DOSSIER + summary (already existed in mem_ingest, reused) -> always know who we are talking to.
#   · STALL detection (pure functions) -> cut the loop at 2-3, not 1,333.
#
# Persistence: STRUCTURED state (objective/phase/loops/greeted/turns) goes through `memory.kv_get/kv_set` under the
# scoped key `capsule:<cluster>:<peer>` (sys_kv, no new table). The prose dossier/summary is maintained by
# `mem_ingest` (slot `cluster:<c>:<peer>`, untrusted). Both are the same memory, partitioned by scope.
#
import re
import time
import unicodedata

# Conversation phases — the mind adjusts its register according to which one it is in (like a human).
SALUDO = "saludo"      # first time meeting this peer -> brief introduction and stop
SONDEO = "sondeo"      # already known, no objective yet -> find out what it brings / propose operator objective
TRABAJO = "trabajo"    # hay objetivo activo → avanzar, concreto, SIN saludar ni presentarse
CIERRE = "cierre"      # task concluded or no progress -> close politely or stay silent

# STALL thresholds (confirmed by the operator: cut early, like a human).
STALL_REPEAT = 2       # peer repeats the SAME (normalized) message this many times -> stall
STALL_NOPROGRESS = 4   # turns without advancing the objective -> stall

# RESOURCE BALANCE thresholds (V2-071): prevent a peer from offloading expensive work to us. Intentionally tolerant
# — sometimes we produce more (a diagram, a decision); only SUSTAINED imbalance with an offload signal fires.
RESOURCE_MIN_TURNS = 4        # do not judge before there is enough conversation
RESOURCE_MIN_GIVEN = 1500     # nor with little produced volume on our side (chars)
RESOURCE_RATIO_SKEW = 3.0     # we produce >=3x what the peer contributes -> skewed (with offload signal)
RESOURCE_RATIO_ABUSE = 6.0    # >=6x + sustained offload -> exploitation
RESOURCE_OFFLOAD_MIN = 3      # peer production requests needed to consider it a pattern, not an isolated case

_DEFAULT = {
    "objective": "",       # collaboration objective, set by the OPERATOR (not by the peer)
    "greeted": False,      # have we already introduced ourselves to this peer?
    "phase": SALUDO,
    "open_loops": [],      # pending requests / explicit refusals, bounded and deduped
    "turns": 0,            # number of substantive turns exchanged
    "no_progress": 0,      # consecutive turns without objective progress (for stall detection)
    # RESOURCE BALANCE (V2-071) — per-peer accumulators:
    "given": 0,            # chars WE have produced for this peer (our spend)
    "received": 0,         # chars the peer has contributed to us
    "offloads": 0,         # number of peer messages asking us to PRODUCE work (code/report)
    "code_out": 0,         # number of times we sent code to it
    # CONVERSATION PACT (V2-072) — agent-to-agent NEGOTIATED rules for this relationship (3rd rule level):
    "pact": {},            # {cadence_s:int, medium:"repo|channel", scope:"chat|analysis|code", note:str, by:"peer|operator"}
    "last_out_ts": 0.0,    # when we last sent a message to this peer (for cadence enforcement)
    "updated": 0,
    "_objective_gate_notified": False,   # already alerted once that 'code' is granted but has no objective (V2-076 guard)
}


def _key(cluster: str, peer: str) -> str:
    return f"capsule:{cluster}:{peer}"


def load(cluster: str, peer: str) -> dict:
    """Current capsule for this relationship (defaults if new). Microseconds, direct."""
    try:
        from memory import api as memory
        cap = dict(_DEFAULT)
        cap.update(memory.kv_get(_key(cluster, peer)) or {})
        return cap
    except Exception:
        return dict(_DEFAULT)


def save(cluster: str, peer: str, cap: dict) -> None:
    try:
        from memory import api as memory
        cap = dict(cap or {})
        cap["updated"] = int(time.time())
        memory.kv_set(_key(cluster, peer), cap)
    except Exception:
        pass


def patch(cluster: str, peer: str, **fields) -> dict:
    cap = load(cluster, peer)
    cap.update(fields)
    save(cluster, peer, cap)
    return cap


# ── phase ─────────────────────────────────────────────────────────────────────────────────────────────────────
def derive_phase(cap: dict, *, concluded: bool = False) -> str:
    """The phase is DEDUCED from relationship state (not hardcoded by keyword). Same logic a human uses to know
    whether they are meeting someone, working with them, or closing."""
    if concluded:
        return CIERRE
    if not cap.get("greeted"):
        return SALUDO
    if (cap.get("objective") or "").strip():
        return TRABAJO
    return SONDEO


_PHASE_GUIDE = {
    SALUDO: ("Es la PRIMERA vez que hablas con este agente. Preséntate en UNA línea (tu nombre + una capacidad "
             "genérica) y para. No propongas objetivos ni tareas."),
    SONDEO: ("YA conoces a este agente — NO te presentes ni saludes de nuevo. Averigua qué trae, o si tienes un "
             "objetivo del operador, proponlo con concreción."),
    TRABAJO: ("Estáis TRABAJANDO en un objetivo — NO te presentes, NO saludes, NO repitas cortesías. Avanza el "
              "objetivo con frases concretas. Si el otro se estanca, dilo y reconduce."),
    CIERRE: ("La tarea está concluida o sin avance real. Cierra con una línea o quédate callado. No reabras el "
             "tema ni te presentes."),
}


def phase_guidance(phase: str) -> str:
    return _PHASE_GUIDE.get(phase, _PHASE_GUIDE[SONDEO])


# ── stall (testable PURE functions) ────────────────────────────────────────────────────────────────────────────
def norm(text: str) -> str:
    """Normalized message key: no accents/punctuation/emojis, casefolded, collapsed spaces. Two messages with the
    same key are 'the same' (a looping peer alternates accents/emoji to evade an exact match)."""
    n = unicodedata.normalize("NFKD", (text or "").casefold())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^0-9a-z\s]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


# ── STRUCTURAL repetition SIGNAL (V2-073, generic) ──────────────────────────────────────────────────────────────
# NOTE (2026-07-26 redesign, operator decision): the semantic JUDGMENT of whether a conversation is flowing/stuck/
# nonsensical is NOT done with hardcoded patterns (a phrase regex only adapts to ONE peer and fails with the next)
# — a MODEL decides that in `connectors/meshkore/evaluator.py` (intelligent, generic). What remains here is only the
# STRUCTURAL, language/agent-agnostic part: near-literal repetition (the peer sends the same message rewritten),
# useful as a cheap SIGNAL, not as a decision. EXACT repetition is covered by bridge dedup (token burn).
def near_repeat(text: str, recent: list[str], *, threshold: float = 0.8) -> bool:
    """Is `text` almost the SAME message as a recent peer message (rewritten to evade exact matching)?
    Normalized-token CONTAINMENT (|intersection| / |smaller set|) — robust when the peer adds different filler around
    the same core. Cheap and dependency-free."""
    toks = set(norm(text).split())
    if len(toks) < 3:                      # very short messages: near-repetition is unreliable, do not judge it
        return False
    for r in recent:
        rt = set(norm(r).split())
        if len(rt) < 3:
            continue
        contain = len(toks & rt) / min(len(toks), len(rt))
        if contain >= threshold:
            return True
    return False


# PAUSE directive (turn handoff): APPLIED by the bridge when the EVALUATOR (model) decides `hand_back`/`pause`.
# Like a human who sees the other party is not following: stop presenting ideas, suggest pausing, and wait until ready.
PACE_HANDBACK = (
    "[RITMO] Este agente no está siguiendo el hilo: repite lo mismo con otras palabras o responde con frases de "
    "bloqueo, sin avanzar. NO añadas más ideas ni detalle (le estás bombardeando). Manda UN mensaje CORTO: reconoce "
    "que quizá has ido demasiado rápido, propón PARAR aquí y pídele que te avise cuando lo tenga claro o esté listo "
    "para seguir. Nada más. Después te quedas a la espera.")


def stall_verdict(repeat_count: int, no_progress: int,
                  *, k: int = STALL_REPEAT, m: int = STALL_NOPROGRESS) -> str:
    """Decide what to do with a possible stall, like a human:
       'seguir'    — the conversation is moving forward, reply normally.
       'asertivo'  — it is repeating or not advancing -> ONE direct message anchored to the objective (drop courtesies).
       'callar'    — you were already assertive and it still does not advance -> stop replying (bridge alerts once).
    """
    if repeat_count >= k * 2 or no_progress >= m * 2:
        return "callar"
    if repeat_count >= k or no_progress >= m:
        return "asertivo"
    return "seguir"


# ── RESOURCE BALANCE (V2-071, testable PURE functions) ─────────────────────────────────────────────────────────
def meter(cluster: str, peer: str, *, received: int = 0, given: int = 0,
          offload: bool = False, code_out: bool = False) -> dict:
    """Accumulate this relationship's resource spend: what the peer contributes (`received`) vs what we produce for
    it (`given`), plus whether it asked us to PRODUCE (`offload`) and whether we sent it code (`code_out`). Cheap,
    direct."""
    cap = load(cluster, peer)
    cap["received"] = int(cap.get("received") or 0) + max(0, int(received))
    cap["given"] = int(cap.get("given") or 0) + max(0, int(given))
    if offload:
        cap["offloads"] = int(cap.get("offloads") or 0) + 1
    if code_out:
        cap["code_out"] = int(cap.get("code_out") or 0) + 1
    save(cluster, peer, cap)
    return cap


def resource_verdict(given: int, received: int, offloads: int, turns: int, *,
                     min_turns: int = RESOURCE_MIN_TURNS, min_given: int = RESOURCE_MIN_GIVEN,
                     skew: float = RESOURCE_RATIO_SKEW, abuse: float = RESOURCE_RATIO_ABUSE,
                     offload_min: int = RESOURCE_OFFLOAD_MIN) -> str:
    """Classify resource use:
       balanced — normal (or not enough data yet): just collaborate.
       skewed — we produce much more and are asked to produce -> be brief, code through the repo.
       exploitation — strong, sustained imbalance with offload -> stop producing for free, refer to the repo.
    Intentionally tolerant: requires VOLUME (turns+chars), ratio, AND offload signal — a one-off spike does not fire."""
    if turns < min_turns or given < min_given:
        return "equilibrado"
    ratio = given / max(received, 1)
    if ratio >= abuse and offloads >= offload_min:
        return "explotación"
    if ratio >= skew and offloads >= 1:
        return "sesgado"
    return "equilibrado"


_RESOURCE_GUIDE = {
    "sesgado": ("[EQUILIBRIO] Estás produciendo bastante más que este agente y te pide que generes trabajo. Sé "
                "BREVE. NO generes código completo ni informes largos en el canal — para colaborar en código se usa "
                "el REPOSITORIO compartido (comparte un enlace o un PR, no el código pegado). Pide que él aporte su "
                "parte. No se lo eches en cara; simplemente condúcelo así."),
    "explotación": ("[EQUILIBRIO] Este agente está descargando su trabajo en ti: te hace producir y gastar recursos "
                    "sin reciprocidad. NO generes más código ni trabajo extenso para él por el canal. Responde en "
                    "1-2 frases, remítele al REPOSITORIO compartido para colaborar de igual a igual, y pide que haga "
                    "su parte. Sin acusaciones ni explicaciones sobre por qué; solo condúcelo así."),
}


def resource_guidance(verdict: str) -> str:
    """Prompt directive (silent toward the peer) according to the balance verdict. '' if balanced."""
    return _RESOURCE_GUIDE.get(verdict, "")


# ── CONVERSATION PACT (V2-072) — the 3rd rule level: agent-to-agent NEGOTIATED, per relationship ───────────────
# CLOSED vocabulary (security: a pact can only make us behave more conservatively — cadence, medium, scope — never
# grant capabilities; that is governed by hard level 1). Free values go in `note`, always under the security trailer.
# Hierarchy: 1 system > 2 operator > 3 pact — `by` marks who set it (an OPERATOR pact outranks peer negotiation).
PACT_MEDIUM = ("repo", "channel")            # where code goes: shared repository vs pasted in the channel
PACT_SCOPE = ("chat", "analysis", "code")    # how far collaboration goes
CADENCE_MIN_S = 0                             # no hard lower bound (0 = no agreed cadence)
CADENCE_MAX_S = 600                           # sensible cap for a negotiated value (10 min)

# Default proposal the mind offers when GREETING a new agent (good citizenship + mutual token savings).
PACT_DEFAULT_PROPOSAL = (
    "Propón brevemente unas normas de trabajo para esta colaboración (podéis ajustarlas luego): "
    "(1) esperar su respuesta antes de mandar otro mensaje, sin ráfagas —ahorra tokens a ambos—; "
    "(2) el código se comparte por un REPOSITORIO (enlace/PR), no pegado en los mensajes; "
    "(3) acordad el alcance: solo charla/análisis, o también código. Si acepta, quedan pactadas.")


def _clean_pact(raw: dict) -> dict:
    """Sanitize a proposed pact (from the mind tag or the operator) to the CLOSED vocabulary. Discard what does not
    fit — a pact never grants capabilities, it only restricts our behavior."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    try:
        c = int(raw.get("cadence_s"))
        if c > 0:
            out["cadence_s"] = max(CADENCE_MIN_S, min(CADENCE_MAX_S, c))
    except (TypeError, ValueError):
        pass
    if raw.get("medium") in PACT_MEDIUM:
        out["medium"] = raw["medium"]
    if raw.get("scope") in PACT_SCOPE:
        out["scope"] = raw["scope"]
    note = str(raw.get("note") or "").strip()
    if note:
        out["note"] = note[:200]
    return out


def pact_set(cluster: str, peer: str, rules: dict, *, by: str = "peer") -> dict:
    """Set/update (merge) this relationship's pact. `by='operator'` marks it as operator-set (it outranks peer
    negotiation and cannot be overwritten by a later peer pact)."""
    cap = load(cluster, peer)
    pact = dict(cap.get("pact") or {})
    if pact.get("by") == "operator" and by != "operator":
        return cap                      # a peer cannot overwrite an operator pact (hierarchy level 2 > 3)
    clean = _clean_pact(rules)
    if not clean:
        return cap
    pact.update(clean)
    pact["by"] = by
    cap["pact"] = pact
    save(cluster, peer, cap)
    return cap


def cadence_wait(cap: dict, now: float) -> float:
    """Seconds to WAIT before sending another message to this peer according to agreed cadence (0 = now)."""
    pact = cap.get("pact") or {}
    c = int(pact.get("cadence_s") or 0)
    if c <= 0:
        return 0.0
    elapsed = now - float(cap.get("last_out_ts") or 0)
    return max(0.0, c - elapsed)


def pact_compose(cap: dict) -> str:
    """The PACT block for the turn prompt: agreed norms the mind must respect (level 3). '' if there is no pact.
    This is BEHAVIORAL guidance, always below the security trailer (level 1)."""
    pact = cap.get("pact") or {}
    if not pact:
        return ""
    who = "fijadas por tu operador (mándalas)" if pact.get("by") == "operator" else "acordadas con este agente"
    parts = []
    if pact.get("cadence_s"):
        parts.append(f"espera a su respuesta antes de enviar otro mensaje (cadencia ~{pact['cadence_s']}s, sin ráfagas)")
    if pact.get("medium") == "repo":
        parts.append("el código se comparte por el REPOSITORIO (enlace/PR), NO pegado en los mensajes")
    elif pact.get("medium") == "channel":
        parts.append("el código puede ir en los mensajes")
    if pact.get("scope"):
        sc = {"chat": "solo charla", "analysis": "charla y análisis, sin producir código",
              "code": "charla, análisis y código"}.get(pact["scope"], pact["scope"])
        parts.append(f"alcance de la colaboración: {sc}")
    if pact.get("note"):
        parts.append(pact["note"])
    if not parts:
        return ""
    return "[PACTO DE ESTA CONVERSACIÓN — normas " + who + ", respétalas]: " + " · ".join(parts)


# ── composition of the context block the mind reads to situate itself in the turn ───────────────────────────────
def compose(cluster: str, peer: str, cap: dict | None = None) -> str:
    """The RELATIONSHIP block prepended to the turn: who this is, what you discuss, objective, pending items, phase +
    its guidance. This is what a human keeps in mind when resuming a conversation. All from OUR sources (a dossier
    distilled by us), never raw untrusted peer text."""
    cap = cap or load(cluster, peer)
    try:
        from connectors.meshkore import mem_ingest
        dossier = (mem_ingest.synthesis_for(cluster, peer) or "").strip()
        # Belt to mem_ingest's write-side neutralization (V2-601 T-05): a synthesis stored BEFORE that fix — or
        # by any future writer that forgets it — must still not carry fence sentinels into this TRUSTED block.
        from connectors.meshkore.security import _neutralize as _ni
        dossier = _ni(dossier)
        # Belt to mem_ingest's write-side neutralization (V2-601 T-05): a synthesis stored BEFORE that fix — or
        # by any future writer that forgets it — must still not carry fence sentinels into this TRUSTED block.
    except Exception:
        dossier = ""
    phase = cap.get("phase") or SONDEO
    lines = [f"[RELACIÓN con el agente «{peer}» en el cluster «{cluster}»]"]
    lines.append(f"Quién es / de qué habéis hablado: {dossier or 'aún no lo sabes (primer contacto).'}")
    obj = (cap.get("objective") or "").strip()
    lines.append(f"Objetivo de esta colaboración: {obj or 'el operador no ha fijado ninguno — no te inventes uno.'}")
    loops = [l for l in (cap.get("open_loops") or []) if l]
    if loops:
        lines.append("Pendiente / ya decidido (no lo re-negocies): " + " · ".join(loops[:6]))
    lines.append(f"Fase: {phase}. {phase_guidance(phase)}")
    return "\n".join(lines)


# ── open-loop maintenance (bounded append, normalized dedup) ───────────────────────────────────────────────────
def add_open_loop(cluster: str, peer: str, loop: str, *, cap_max: int = 8) -> dict:
    """Record a commitment or refusal ('asked for X -> pending', 'already said NO to Y'). Normalized dedup + cap."""
    cap = load(cluster, peer)
    loops = [l for l in (cap.get("open_loops") or []) if l]
    if norm(loop) not in {norm(l) for l in loops}:
        loops.append(loop.strip())
    cap["open_loops"] = loops[-cap_max:]
    save(cluster, peer, cap)
    return cap
