#
# ClusterBridge — the seam between the MeshKore transport and the BRAIN.
#
# It does NOT think. It (1) turns every inbound cluster frame into a labelled brain input, (2) runs that through
# the injected `brain` (the FlashBrain engine in untrusted profile, off the voice pipeline), (3) parses the reply's
# [[cluster.*]] tags and routes them back to the manager, and (4) keeps a lightweight "engaged" flag per cluster so a
# heartbeat can nudge the brain to follow up / conclude. All the decisions (what to say, when to wait, when to
# conclude) live in the brain. The turn serializes with the voice turn via the shared turn_lock, so a cluster turn
# never cuts off the operator mid-sentence.
#
import asyncio
import os

from loguru import logger

from connectors.meshkore import brief, store, journal, security, mem_ingest, capsule, send_gate

IDLE_SECS = float(os.getenv("MESHKORE_IDLE_SECS", "90"))    # engaged + silent this long → one nudge
TICK_SECS = float(os.getenv("MESHKORE_TICK_SECS", "20"))    # heartbeat cadence
EVAL_SECS = float(os.getenv("MESHKORE_EVAL_SECS", "45"))    # how often conversation HEALTH is re-evaluated (V2-075)
MAX_INFLIGHT = int(os.getenv("MESHKORE_MAX_INFLIGHT", "8"))  # cap queued/in-flight brain turns → flood backpressure
# Anti-spam DEDUP (2026-07-25, live: zalo flooded 45 IDENTICAL "consultando con mi equipo… un momento" pings in
# ~90s — each spawned a brain turn until MAX_INFLIGHT dropped the rest, and zaelar burned tokens replying
# "Entendido, quedo a la espera" 40×). A peer re-sending the EXACT same text within this window is a loop/spam,
# not a new turn: reply ONCE, ignore verbatim repeats. Defensive hardening on the untrusted channel, same spirit
# as MAX_INFLIGHT — does NOT change conversational style, only suppresses reacting to duplicate spam.
DEDUP_SECS = float(os.getenv("MESHKORE_DEDUP_SECS", "60"))


def _close_cluster_flow(trace_id: str) -> None:
    """Every cluster turn opens a trace via `trace.begin()` but this whole path — unlike the voice provider's
    `_run` — never explicitly closed it (found live 2026-08-16: an idle heartbeat nudge sat "en curso" in the
    flow viewer with nothing happening, and the operator had asked for nothing in minutes). Nothing here chains
    fragments across turns the way voice does, so the close condition is simple: this turn is done, close its
    flow UNLESS `escalate_to_slowbrain` spawned a worker that is still running on it — that worker owns the
    close instead (same invariant as the voice path: a live worker's flow NEVER closes out from under it)."""
    if not trace_id:
        return
    try:
        from nucleo import dispatch as _dispatch
        if _dispatch.has_live_trace(trace_id):
            return
        from voice import observer as _observer
        _observer.emit("flow", "end", role="system", extra={"ok": True})
    except Exception:
        pass
# V2-086: the network no longer has a widget. Every cluster event notifies the NATIVE surface (ChatWall "Clusters"
# tab) through SSE, so it can refresh state/peers/counters without polling.


def _emit(*args, **kwargs):
    try:
        from voice.observer import emit
        emit(*args, **kwargs)
    except Exception:
        pass


import re as _re
import unicodedata as _ud

def _dedup_key(text: str) -> str:
    """Normalized key for anti-spam dedup: casefold + keep only alphanumerics and single spaces (drop emojis,
    punctuation, ellipsis variants, encoding differences). Two messages that reduce to the same key within
    DEDUP_SECS are the same status ping (a peer looping), not a distinct turn. '' for empty/no-alnum content
    (those bypass dedup — never suppress a real turn on a normalization artifact)."""
    n = _ud.normalize("NFKD", text or "").casefold()
    n = "".join(c for c in n if not _ud.combining(c))
    n = _re.sub(r"[^0-9a-z\s]+", " ", n)          # keep letters/digits/spaces only (Spanish enye -> n via NFKD above)
    return _re.sub(r"\s+", " ", n).strip()


from connectors.meshkore.bridge.events import _EventsMixin
from connectors.meshkore.bridge.turn import _TurnMixin
from connectors.meshkore.bridge.outbound import _OutboundMixin
from connectors.meshkore.bridge.heartbeat import _HeartbeatMixin


class ClusterBridge(_EventsMixin, _TurnMixin, _OutboundMixin, _HeartbeatMixin):
    def __init__(self, manager, brain):
        self._manager = manager
        self._brain = brain                  # async brain(text, on_chunk=None) -> str (FlashBrain engine, untrusted profile)
        self._engaged: dict[str, bool] = {}  # cluster -> has an open joint task
        self._last_activity: dict[str, float] = {}
        self._nudged: set[str] = set()
        self._last_peer_msg: dict[str, str] = {}  # cluster -> most recent inbound text (idle-nudge context)
        self._caught_up: set[tuple] = set()   # (cluster, peer, last_in_ts) already nudged for catch-up (dedup)
        self._recent_inbound: dict[tuple, tuple] = {}  # (cluster,peer) -> (text, ts) for anti-spam verbatim dedup
        # STALL GUARD (V2-069): consecutive repetitions of the SAME (normalized) message per peer + episode state
        # (did we already send the assertive message? did we already alert the operator?). Resets when new content
        # arrives. This is the 1st DETERMINISTIC line (cuts the loop at 2-3, not 1,333); Susurro is the 2nd line.
        self._repeat: dict[tuple, int] = {}          # (cluster,peer) -> number of consecutive repetitions
        self._stall: dict[tuple, dict] = {}          # (cluster,peer) -> {"assertive_sent":bool, "alerted":bool}
        self._resource_alerted: set = set()          # (cluster,peer) already alerted for resource exploitation (V2-071)
        self._window: dict[tuple, list] = {}          # (cluster,peer) -> [{"who","text"}] evaluator window (V2-075)
        self._paced: dict[tuple, dict] = {}           # (cluster,peer) -> {"paused":bool,"alerted":bool} (evaluator decides)
        self._last_eval: dict[tuple, float] = {}      # (cluster,peer) -> last evaluation timestamp (throttle, V2-075)
        self._tick_task = None
        self._turns: set = set()             # keep brain-turn tasks alive

    # ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────────
    def start_heartbeat(self):
        if self._tick_task is None:
            self._tick_task = asyncio.create_task(self._heartbeat(), name="meshkore:heartbeat")

    async def stop(self):
        if self._tick_task:
            self._tick_task.cancel()
            self._tick_task = None

    def _now(self) -> float:
        return asyncio.get_event_loop().time()

    def note_objective(self, name: str, active: bool = True):
        """Mark a cluster as having an active joint objective (so a peer arriving wakes the brain). Used by the
        startup autoreconnect path, which connects saved clusters directly (bypassing the [[cluster.connect]] tag).
        v1 caveat: a task concluded with [[cluster.done]] before a restart re-engages here (mission state isn't
        persisted yet) — the operator can just say 'stop'."""
        self._engaged[name] = active
        self._last_activity[name] = self._now()

    def _notify_registry(self):
        """Notify the NATIVE "Clusters" tab that something changed on the network (V2-086) — connection, peer
        presence, message. The frontend refreshes it from `/api/meshkore/status`. This used to touch the
        `cluster-registro` widget store to force a canvas re-render; that widget no longer exists."""
        try:
            from voice.observer import emit
            emit("cluster", "changed", role="system")
        except Exception:
            pass

    def _spawn(self, coro):
        # Flood backpressure: turns serialize on the shared turn_lock, so a peer spamming messages would otherwise
        # queue unbounded brain turns (memory + guaranteed LLM-cost DoS). Above the cap we DROP the new turn (a peer
        # cannot force unbounded work) and alert the operator once. Prefer dropping over unbounded acceptance.
        if len(self._turns) >= MAX_INFLIGHT:
            coro.close()
            _emit("error", f"cluster: dropped a brain turn — {MAX_INFLIGHT} already queued (flood backpressure).")
            return
        t = asyncio.create_task(coro)
        self._turns.add(t)
        t.add_done_callback(self._turns.discard)

    @staticmethod
    def _agent_stopped() -> bool:
        """The operator's ⏻, asked the same way every other loop in the engine asks it (V2-747).

        This bridge had NO reference to `runstate` at all, and it is the one connector that spends a model
        call on its own initiative. Measured in his own session: ⏻ off at 20:13:20 — `run stop`, the
        observability session closed, one worker frozen — and then a full brain turn at **20:14:15, 20:15:55,
        20:17:35, 20:19:15, 20:20:55, 20:22:35**, every 100 s, sessionless, still going when the database was
        read. His words: *«si he decidido pararlo para que no gaste tokens, para que no haga nada, el sistema
        se tiene que paralizar»*.

        Only the SELF-STARTED work is gated — the nudge and the conversation evaluator, the two things this
        loop decides to do on its own. An inbound peer message is not our initiative and keeps its existing
        path: dropping what a peer sent us would lose it, and losing a message is not hibernating.
        """
        try:
            from nucleo import runstate
            return runstate.stopped()
        except Exception:  # noqa: BLE001 — an unreadable switch never silences a live cluster
            return False

    # ── heartbeat: nudge on idle-with-peers-present (human-like follow-up), never spam ──────────────────────
    async def _heartbeat(self):
        while True:
            try:
                await asyncio.sleep(TICK_SECS)
                if self._agent_stopped():
                    continue            # hibernating: no nudges, no evaluations, no model calls
                now = self._now()
                for cluster, engaged in list(self._engaged.items()):
                    if not engaged:
                        continue
                    client = self._manager.get(cluster)
                    if not client or not client.online:          # no peers → wait silently (human-like)
                        continue
                    # V2-075: pass each active chat's HEALTH through the EVALUATOR (model), throttled. Independent
                    # from idle-nudge — this catches chat that IS active but going nowhere (bombardment/loop).
                    _active = (now - self._last_activity.get(cluster, 0)) < EVAL_SECS * 3   # do not re-judge dead chat
                    if _active:
                        for peer in list(client.online):
                            ph = security.neutralize_identity(peer)
                            dk = (cluster, ph)
                            if now - self._last_eval.get(dk, 0) >= EVAL_SECS and len(self._window.get(dk, [])) >= 4:
                                self._spawn(self._evaluate_and_apply(cluster, ph))
                    if cluster in self._nudged:
                        continue
                    if now - self._last_activity.get(cluster, 0) < IDLE_SECS:
                        continue
                    self._nudged.add(cluster)                     # suppress re-entry WHILE this turn is in flight
                    self._spawn(self._heartbeat_nudge(cluster))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"MeshKore heartbeat: {e}")
