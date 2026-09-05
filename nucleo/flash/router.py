"""nucleo/flash/router.py — FlashBrain input router (V2-004 · T61).

Decides, THROUGH FUNCTION-CALLING (no keyword lists — language-agnostic), what the layer does
with a turn: answer direct conversation, set a style preference, search for a fact on the web, or **escalate**
(delegate the task to a headless worker). This is the standard, proven mechanism for an LLM to trigger an action
reliably: it exposes an OpenAI-compatible `TOOLS` catalog; when the model calls one, `decide()`
translates it into a `Decision`. Canvas control (`[[show]]`/`[[close]]`/`[[move]]`) does NOT go through here: these are
text tags emitted by the model and processed by `frontend.py` + `voice.tag_protocol`.

⚠️ **TOOL CATALOG = canonical doc** in `.meshkore/docs/architecture/zaelar-architecture.md §8 (FlashBrain
tool catalog)`, with a public/curated version in `web/` under `/technology/flashbrain`. ANY change here
(adding/removing a tool, renaming it, changing its description or gating) MUST update that doc + the tests
(`test_router.py`) — see `zaelar-docs-sync.md §Tools`. Every tool must be JUSTIFIED and fit the
system flow (V2-036).

Historical naming note: the delegation tool is called `escalate_to_slowbrain` for LEGACY reasons (V2-004, when
SlowBrain was a separate reasoning brain). In **V2-036 that brain was DISSOLVED**: escalating today means
`nucleo/dispatch.py` LAUNCHES a **headless worker** (a Claude Code agent, or another configured agent) that
DRIVES the task with its own intelligence (memory/tools/browser). The name is retained as the stable identifier
in the model contract; its DESCRIPTION reflects current reality (it does not mention a "slow brain").

Why function-calling rather than a text tag: a small/terse model is unreliable at writing a pseudo-tag
inside prose (it confabulates "I'll look at the logs…" WITHOUT escalating). A tool call is the TRAINED,
model-agnostic, multilingual mechanism. See the key decision by the «Colmena» brain (V2-036) in CLAUDE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nucleo.flash import image_turn as _image_turn  # V2-457 (image_turn is a leaf)
from nucleo.flash.video_turn import normalize_action as _video_action  # V2-402 (video_turn is a leaf)
from typing import Any

# ── kind vocabulary ─────────────────────────────────────────────────────────────────────────────────────
CHAT = "chat"          # handled by the fast layer itself (conversation, state, canvas via tag)
STYLE = "style"        # the operator set a session interaction preference
SEARCH = "search"      # quick factual lookup on the web (web_search) — lightweight route, resolved in the turn
from nucleo.flash.listing_turn import request_from as _lt_request_from   # V2-556: una sola forma

LISTINGS = "listings"  # V2-556: marketplace/product LISTING hunt (search_listings) — the fast module serves the
                       # turn or escalates BY ITSELF (listing_turn.py); the model never picks fast-vs-deep
RECALL = "recall"      # V2-056: the MODEL decides to remember (the operator's durable memory) — lightweight route in the turn
REVEAL = "reveal"      # V2-060: the operator requests a stored SECRET (reveal_secret) — lightweight route; out-of-band value
MUSIC = "music"        # V2-041: plays/controls music through a connector (play_music) — lightweight route, in the turn
VIDEO = "video"        # V2-045: plays a VIDEO in the YouTube widget (play_video) — MUSIC's sibling, SEE≠HEAR
IMAGES = "images"      # V2-457: displays PHOTOS in the `imagenes` viewer (show_images) — MUSIC/VIDEO's third sibling
SHOW = "show"          # SHOW/OPEN a canvas widget (show_widget) — first-class tool, converges on [[show:id]]
PANEL = "panel"        # V2-079: opens the native side PANEL (chat/processes/crons) in a tab (show_panel)
ALIAS = "alias"        # V2-082: adds/removes a widget NAME/ALIAS (manage_widget_alias) — manifest write
ESCALATE = "escalate"  # the turn requests memory/tools/reasoning → a Brain Worker is LAUNCHED asynchronously
INJECT = "inject"      # V2-038: refines/expands an ACTIVE Brain Worker (send_to_worker) → injects, does not relaunch
STOP = "stop"          # V2-038: kills an ACTIVE Brain Worker (stop_worker)
ANSWER = "answer"      # V2-038: answers the question of a waiting Brain Worker (answer_worker)

# Priority when collapsing multiple tool calls from one turn into a decision (higher = wins). STOP overrides everything
# (if the operator asks to stop AND something else, stop first); ANSWER/INJECT outrank ESCALATE (refine/respond to a
# live worker before opening another). MUSIC follows the lightweight routes (SEARCH), below worker routes.
_PRIORITY = {CHAT: 0, STYLE: 1, SEARCH: 2, LISTINGS: 2, RECALL: 2, REVEAL: 2, MUSIC: 3, VIDEO: 3, IMAGES: 3, SHOW: 3,
             PANEL: 3, ALIAS: 3,
             ANSWER: 4, INJECT: 5, ESCALATE: 6, STOP: 7}


@dataclass
class Decision:
    """What the router decided for a turn."""
    kind: str                              # 'chat' | 'style' | 'escalate'
    payload: dict[str, Any] = field(default_factory=dict)
from nucleo.flash.router_catalog import TOOLS   # V2-556: el catálogo (dato puro) vive aparte



# ── tool FAMILIES + situational gating ─────────────────────────────────────────────────────────────────────
# Each tool belongs to a FAMILY (widgets, workers, cluster, messaging, media, web, memory, core). The
# family is living documentation and the unit used to reason about a turn's tool budget: it shows at a glance
# which block enters and which stays out, instead of 22 separate gates. It is NOT an intent classifier.
FAMILIES: dict[str, tuple[str, ...]] = {
    "core":      ("escalate_to_slowbrain", "set_style_directive"),
    "widgets":   ("show_widget", "widget_data", "delete_widget", "restore_widget", "confirm_widget_delete",
                  "fullscreen_widget", "manage_widget_alias", "show_panel", "arrange_canvas"),
    "workers":   ("send_to_worker", "stop_worker", "answer_worker"),
    "cluster":   ("connect_cluster", "set_cluster_objective", "cluster_send"),
    "messaging": ("reply_message",),
    "media":     ("play_music", "play_video", "show_images"),
    "web":       ("web_search", "search_listings", "authenticate_web", "login_done"),
    "memory":    ("recall", "reveal_secret"),
}


def family_of(name: str) -> str:
    """The family of a tool (or 'core' if unclassified — fail-safe: a new tool is never lost)."""
    for fam, names in FAMILIES.items():
        if name in names:
            return fam
    return "core"


# SITUATIONAL tools: meaningful only in a specific state → omitted from the prompt when inapplicable (V2-035).
# Offering them ALWAYS wasted ~1.2k chars/turn and added decision noise for the small model.
#
# ⚠️ INVARIANT (V2-085, `feedback_no_hardcoded_understand`): **a gate checks STATE, never the turn's words.**
# «does the vault exist?», «is a worker alive?», «is the messaging connector connected?» are system facts,
# verifiable and language-agnostic. «does the phrase contain "remind me"?» would be a keyword table deciding
# routing — exactly what this brain rejects: the model decides intent through function-calling.
# If a tool cannot be disabled by state, it is OFFERED; it is not guessed.
_SITUATIONAL = {
    "show_widget":           lambda ctx: ctx.get("has_widgets", True),   # only if there are widgets to show
    "widget_data":           lambda ctx: ctx.get("has_widgets", True),   # only if there are widgets with actions
    "delete_widget":         lambda ctx: ctx.get("has_widgets", True),   # only if there are widgets to delete
    "manage_widget_alias":   lambda ctx: ctx.get("has_widgets", True),   # V2-082: edit widget names/aliases
    "confirm_widget_delete": lambda ctx: ctx.get("confirm_pending", False),  # only with a pending deletion
    "login_done":            lambda ctx: ctx.get("auth_pending", False),     # only during an ongoing login
    "authenticate_web":      lambda ctx: ctx.get("allow_auth", True),        # operator-only; can be disabled
    # `cluster_send` IS situational, but based on REAL STATE: without a connected cluster there is nobody to write to.
    "cluster_send":          lambda ctx: ctx.get("cluster_connected", False),
    # V2-086: `connect_cluster`/`set_cluster_objective` are NO LONGER gated. The V2-064 gate (the
    # `cluster-registro` widget being open) made the capability UNDISCOVERABLE: connecting a new cluster required
    # knowing in advance that a widget had to be opened first — and that widget no longer exists (the network is a
    # NATIVE surface, Clusters tab). Protection against spurious activation was never the gate, but the deterministic
    # Yes/No confirmation with the cluster_id visible, which remains intact.
    # V2-038: worker tools only when there is something to direct (§v3·D: gated by has_workers / ask_pending).
    "send_to_worker":        lambda ctx: ctx.get("has_workers", False),
    "stop_worker":           lambda ctx: ctx.get("has_workers", False),
    "answer_worker":         lambda ctx: ctx.get("ask_pending", False),
    # V2-085 — three NEW gates, all based on REAL SYSTEM CAPABILITY (if it does not exist, the tool cannot work and
    # offering it only invites the model to promise something impossible):
    "reply_message":         lambda ctx: ctx.get("messaging_on", True),   # without a messaging connector, there is no recipient
    "reveal_secret":         lambda ctx: ctx.get("has_vault", True),      # V2-060: without a vault, there is no secret to read
    "play_video":            lambda ctx: ctx.get("has_video_widget", True),  # play_video LOADS the `youtube` widget
    "show_images":           lambda ctx: ctx.get("has_image_widget", True),  # show_images LOADS the `imagenes` viewer
}


def tools(context: dict | None = None) -> list[dict]:
    """The function catalog to offer the fast model THIS turn. CONTEXTUAL set (V2-035): tools
    situational (delete-confirmation, login-complete, and widget tools when there are no widgets) are OMITTED when
    their state does not apply → shorter prompt, less decision noise, same behavior. `context` (best-effort, all optional):
      · has_widgets (def True) · confirm_pending (def False) · auth_pending (def False) · allow_auth (def True)
      · messaging_on / has_vault / has_video_widget (def True — V2-085, capacidades reales).
    Without context, returns the COMPLETE set (compatibility with tests/prewarm).

    SCALING NOTE (V2-085): this catalog is **O(1)** — 22 fixed tools, ~29.7 KB complete / ~22.5 KB with typical
    gating. It does not grow with the widget catalog, so it is NOT the scalability bottleneck (that is the catalog,
    see `widgets/selection.py`); it is fixed cost and noise per turn, which is why it is pruned by state."""
    ctx = context or {}
    if not context:
        return TOOLS
    out = []
    for t in TOOLS:
        name = t.get("function", {}).get("name", "")
        gate = _SITUATIONAL.get(name)
        if gate is None or gate(ctx):
            out.append(t)
    return out


def tool_context(*, open_widgets=None, has_catalog: bool = True,
                 confirm_pending: bool = False, auth_pending: bool = False,
                 has_workers: bool = False, ask_pending: bool = False,
                 cluster_widget_open: bool = True, messaging_on: bool = True,
                 has_vault: bool = True, has_video_widget: bool = True, has_image_widget: bool = True,
                 cluster_connected: bool = False) -> dict:
    """Builds the `tools()` `context` from inexpensive state signals. `has_widgets` = a widget catalog exists
    (there is always one today) OR one is open. `has_workers` = live Brain Workers exist (→ send/stop_worker).
    `ask_pending` = a worker awaits a response (→ answer_worker). `messaging_on`/`has_vault`/`has_video_widget`
    (V2-085) = REAL system capabilities; the default is True (fail-OPEN) so a capability-probe failure never
    removes a tool the operator had.
    `cluster_widget_open` — OBSOLETE since V2-086: it gates nothing anymore (cluster tools are always offered;
    protection is Yes/No confirmation). Retained in the signature so callers passing it do not break."""
    return {"has_widgets": has_catalog or bool(open_widgets),
            "confirm_pending": confirm_pending, "auth_pending": auth_pending, "allow_auth": True,
            "has_workers": bool(has_workers), "ask_pending": bool(ask_pending),
            "cluster_widget_open": bool(cluster_widget_open), "messaging_on": bool(messaging_on),
            "has_vault": bool(has_vault), "has_video_widget": bool(has_video_widget),
            "has_image_widget": bool(has_image_widget),
            "cluster_connected": bool(cluster_connected)}


def tools_report(offered: list[dict]) -> dict:
    """OBSERVABLE breakdown of a turn's tool set: count, size, and which families entered/remained
    omitted. Feeds `llm_metrics` (same path as the prompt's `sz_*`) to attribute cost and detect when a family
    slips into turns where it does not belong."""
    import json as _json
    names = [t.get("function", {}).get("name", "") for t in offered]
    fams: dict[str, int] = {}
    for n in names:
        fams[family_of(n)] = fams.get(family_of(n), 0) + 1
    all_names = {t.get("function", {}).get("name", "") for t in TOOLS}
    return {"n_tools_offered": len(offered), "n_tools_total": len(TOOLS),
            "sz_tools": len(_json.dumps(offered, ensure_ascii=False)),
            "tool_families": fams, "tools_omitted": sorted(all_names - set(names))}


def _canon_panel_action(v) -> str:
    """'open' | 'close' for the `show_panel` action. Default OPEN: it is the majority case, and a model that is
    the argument cannot end up closing the operator's panel.

    Exists since 2026-08-10 because the tool only knew how to OPEN: the operator asked to close the chat five times in a row
    (“close the chat too”, “close the system chat”, “close the chat window”), zaelar replied “okay, closed” each time,
    and the chat remained open — he had to close it himself with the ✕. Saying yes is worse than being unable to:
    now the capability genuinely exists."""
    a = str(v or "").strip().lower()
    if any(k in a for k in ("clos", "cerr", "cierra", "quita", "oculta", "hide", "off")):
        return "close"
    return "open"


def _canon_panel(v) -> str:
    """Normalizes the `show_panel` `panel` to a canonical ChatWall tab (chat|procesos|crons|clusters).
    Accepts synonyms the model may produce in the argument (workers→procesos, cron→crons, text/wall→chat,
    network/mesh→clusters). This is only for the ARGUMENT already chosen by the model — the 'when' (synonyms in
    the request) lives in the tool description, not here. Default 'procesos' (the most requested case)."""
    p = str(v or "").strip().lower()
    if p in ("chat", "procesos", "crons", "clusters"):
        return p
    # 'clusters' BEFORE 'crons': "cluster" contains the substring "clus", not "cron", but the order makes
    # explicit that the network is evaluated first — and prevents a future ambiguous synonym from landing on the wrong side.
    if any(k in p for k in ("cluster", "meshkore", "mesh", "red", "malla", "peer", "network", "conexion", "conexión")):
        return "clusters"
    if any(k in p for k in ("cron", "programad", "recordatorio", "agendad")):
        return "crons"
    if any(k in p for k in ("chat", "texto", "muro", "escrib", "message", "mensaj")):
        return "chat"
    if any(k in p for k in ("proces", "worker", "tarea", "trabajo", "encarg", "activ")):
        return "procesos"
    return "procesos"


def decide(name: str, args: dict | None = None) -> Decision:
    """Translates ONE tool call (name + arguments) into a `Decision`. An unknown name = chat (fail-safe:
    the fast layer does not break because of an unrecognized function)."""
    args = args or {}
    name = (name or "").strip()
    if name == "escalate_to_slowbrain":
        # V2-227: the SURFACE travels with the request from here. It is deliberately passed RAW: `surfaces.resolve()`
        # needs the `kind`, which this point does not know, and normalizing twice erases the “said nothing” case.
        return Decision(ESCALATE, {"request": (args.get("request") or "").strip(),
                                   "surface": (args.get("surface") or "").strip()})
    if name == "web_search":
        return Decision(SEARCH, {"query": (args.get("query") or "").strip()})
    if name == "search_listings":
        return Decision(LISTINGS, _lt_request_from(args, ""))   # V2-556: la forma de la petición, una sola vez
    if name == "recall":
        return Decision(RECALL, {"query": (args.get("query") or "").strip()})
    if name == "reveal_secret":
        return Decision(REVEAL, {"label": (args.get("label") or "").strip()})
    if name == "play_music":
        return Decision(MUSIC, {"query": (args.get("query") or "").strip(),
                                "action": (args.get("action") or "play").strip().lower()})
    if name == "play_video":
        return Decision(VIDEO, {"query": (args.get("query") or "").strip(),
                                "action": _video_action(args.get("action"))})
    if name == "show_images":
        return Decision(IMAGES, _image_turn.request_from([{"name": "show_images", "args": args}]))
    if name == "show_widget":
        return Decision(SHOW, {"widget_id": (args.get("widget_id") or "").strip()})
    if name == "show_panel":
        return Decision(PANEL, {"panel": _canon_panel(args.get("panel")),
                                "action": _canon_panel_action(args.get("action"))})
    if name == "manage_widget_alias":
        _op = (args.get("op") or "add").strip().lower()
        return Decision(ALIAS, {"widget_id": (args.get("widget_id") or "").strip(),
                                "alias": (args.get("alias") or "").strip(),
                                "op": "remove" if _op.startswith("rem") or _op in ("quitar", "borrar") else "add"})
    if name == "set_style_directive":
        return Decision(STYLE, {"directive": (args.get("directive") or "").strip()})
    if name == "send_to_worker":
        return Decision(INJECT, {"which": (args.get("which") or "").strip(),
                                 "message": (args.get("message") or "").strip()})
    if name == "stop_worker":
        return Decision(STOP, {"which": (args.get("which") or "").strip()})
    if name == "answer_worker":
        return Decision(ANSWER, {"answer": (args.get("answer") or "").strip(),
                                 "which": (args.get("which") or "").strip()})
    return Decision(CHAT, {})


def classify(tool_calls: list[tuple[str, dict]] | None) -> Decision:
    """Collapses a turn's tool calls into ONE decision (the highest-priority one). No tool calls = chat."""
    best = Decision(CHAT, {})
    for name, args in (tool_calls or []):
        d = decide(name, args)
        if _PRIORITY[d.kind] > _PRIORITY[best.kind]:
            best = d
    return best


def is_escalation(name: str) -> bool:
    return (name or "").strip() == "escalate_to_slowbrain"



# ── deterministic backstop guards (moved to router_guards.py, 2026-08-17 modularization pass) ─────────────────
# Re-exported here so every existing call site (`router.looks_like_close(...)`, etc. — all of them import the
# whole module, none import individual names) keeps working unchanged. See router_guards.py's docstring for why.
from nucleo.flash.router_guards import (  # noqa: F401 — re-export, not a local use
    looks_like_web_task, looks_like_login_request, is_pure_show_request, show_request_blocks_data_action,
    is_music_service, looks_like_close, show_contradicts_the_order,
    looks_like_create_widget, promises_music, promises_action, asks_for_missing_detail,
    looks_like_show_strict, looks_like_escalate_task,
    escalate_goal_from_window, hands_public_lookup_back, promises_a_dated_reminder, dated_reminder_backstop,
    create_widget_request, dated_note_backstop, already_in_agenda,
    looks_like_marketplace_nav, looks_like_modify_widget, looks_like_rule_removal, looks_like_bare_ref,
    is_messaging_service, looks_like_stop_work, login_site, nothing_running_for,
)


def operator_words(operator_text: str, turn_text: str) -> str:
    """WHAT THE OPERATOR ACTUALLY ASKED, for the backstops that turn a promise into an errand.

    The turn's text is not it. `[SISTEMA]` notes (`voice/brain_notes.py` — a widget that finished building, a
    worker's result, a recall that arrived late) are glued to the front of the turn so the brain sees them as
    CONTEXT; the seam that does it says in its own comment that they are «NUNCA como parte de lo que el
    operador pidió», and keeps `operator_text` for precisely that. The backstops read the glued text anyway, so
    a note could BECOME the errand.

    Measured live, session c480413b (2026-08-31): a late recall arrived as a note carrying an old memory line,
    the promise-backstop fired on that turn, and a Brain Worker was born with the goal «· [tarea web] un
    fontanero que pueda venir hoy → …». The operator had asked for an appointment with a traumatologist. He got
    a PLUMBER — in the widget titles, on screen, and out loud («el proceso "· [tarea web] un fontanero que pueda
    ven" pregunta:») — plus a second browser tab, a second results card and a second worker racing the real one
    for nine minutes.

    The rule, which is not only about this one note: **a system note is context; it can never be the thing to go
    and do.** Falls back to the turn's text when there is no operator text, so a caller that never separated the
    two behaves exactly as before."""
    return (operator_text or "").strip() or (turn_text or "")
