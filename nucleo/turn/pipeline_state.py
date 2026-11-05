"""The turn's MOUTH and its tag buffer — what the stream, the tool rounds and the close all speak through (V2-851 F5).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner` (where they were closures over its locals) into one
factory, `open_the_mouth`, with no change of behaviour: `send` is the turn's one in-turn mouth (the anti-echo marks,
the attention window, the chunk on the channel's stream through `self._out`); `take` runs the inline tags out of the
buffer; `speak` is a tool round (the model asked for data with a tool, and this round says its answer — never a re-run
of a reply already given); `_buf_reset`/`_buf_add` feed the same buffer. The tag emitter is the executor's, built
after the mouth: it is bound late (`late["tag_emit"]`).
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from nucleo.flash import follow_up_pass as _fup
from nucleo.input import stt as _acc_mod   # V2-776 D0: a turn that died unanswered is un-consumed


def open_the_mouth(self, motor, *, brain, attention, first_turn: bool, emit, FastClient, spec, t0: float,
                   speech, strip_tags, typed: bool = False) -> SimpleNamespace:
    """The mouth of ONE turn. `self` is the channel's stream (`_out` puts a chunk on it). `typed`: the turn's line was
    typed — its reply keeps no voice window alive, because text never opens the voice (V2-852 T01, R1)."""
    from nucleo.turn import pipeline_failure as _turn_failure
    buf, spoken, first_ms = "", [], None
    late: dict = {"tag_emit": None}

    def _tag_emit(*a, **k):
        return late["tag_emit"](*a, **k)

    def send(txt: str):
        nonlocal first_ms
        if not txt:
            return
        if first_ms is None:
            first_ms = round((time.time() - t0) * 1000)
            _acc_mod.answered_by(brain)   # its words are answered now, not when the turn began
        spoken.append(txt)
        # ANTI-ECO (FASE 2): recuerda lo ÚLTIMO que zaelar dice + cuándo, para descartar el eco que el mic
        # recaptura como turno del operador. Se actualiza en CADA salida de voz (respuesta, filler, degradado).
        brain._last_spoken = "".join(spoken)
        brain._last_spoke_at = time.time()
        # `_last_reply`: the same text, but never a filler (`filler_audio.py`) — the context `evaluate_content()`
        # judges the NEXT turn's address with (2026-08-17: four follow-ups after a filler read as ambient). It is
        # THIS reply while it streams: «what we said before his turn» is `prior_line`, never this field.
        brain._last_reply = "".join(spoken)
        # A real reply KEEPS THE CONVERSATION ALIVE (2026-09-01): the attention window opens on the
        # operator's handled turn, but a long narration can outlast `window_s()` — and then his answer to
        # what Zaelar just said lands on the cold-turn judge. Refreshed here, per chunk, because this path
        # only runs for real model output on a turn that already passed the gate; the kickoff (`first_turn`)
        # deliberately does NOT open the window (a session starting mid-meeting must not let ambient speech
        # in through an initial gap — the same rule written at the gate call site).
        if not first_turn and not typed:
            attention.note_directed()
        self._out(txt)

    def take(final: bool) -> str:
        nonlocal buf
        out, buf = strip_tags(buf, _tag_emit, final)
        return out

    def _buf_reset() -> None:
        nonlocal buf
        buf = ""

    def _buf_add(d: str) -> None:
        nonlocal buf
        buf += d

    def _cover_work(kind: str, target: str = "") -> None:
        """Tell the filler node what this turn is about to GO AND DO, so it can cover the far side of the
        tool seam while the work and the tool round run (V2-669). Voice only: the text channel has no dead
        air to fill. Never breaks a turn."""
        try:
            motor._filler_audio_mod().note_work(brain, kind, target)
        except Exception:                       # noqa: BLE001
            pass

    async def speak(sys2: str, user_text: str, max_tokens: int = 240, what: str = "2º pase") -> None:
        """ONE (system, user) TOOL ROUND streamed straight into the mouth — the shape every light route
        (recall, read_widget) had written out in full. Owns this turn's tag accumulator (`buf`/`take`), so
        it lives beside them; the routes themselves live in their modules and inject it."""
        nonlocal buf
        buf = ""                        # discard any tag leftovers from the first pass
        # What this turn ALREADY said, so the round continues it instead of contradicting it (demo pass
        # 2026-09-28, C3: «which slot do you want, the 1:00 or the 4:00?» followed by a read answer saying «I
        # don't have any free-afternoon slot details») — and its first words are never glued to it
        # («…your day.Tomorrow, Tuesday»).
        _said = "".join(spoken).strip()
        if _said:
            # Demo pass 84, Z1: «tomorrow's … calendar's clear — nothing booked» was said BEFORE the agenda was
            # read; the read brought four meetings, and «don't contradict it» made this pass answer SKIP. What was
            # just READ is the truth; words said before it are not — they are corrected, never protected.
            user_text = (f"{user_text}\n\n(En este turno ya le has dicho: «{_said[:400]}». Continúa desde ahí, "
                         f"en SU idioma, sin repetirlo. Si lo dicho choca con los DATOS de arriba, corrígelo en "
                         f"una frase — los datos mandan, lo dicho antes de leerlos no. Si YA contesta lo que "
                         f"preguntó y coincide con los datos, responde exactamente SKIP y nada más. "
                         f"Anunciar que vas a mirar o que lo estás mirando NO es contestar: entonces da la "
                         f"respuesta.)")
        _lead = [" " if _said else ""]
        # SKIP is held back until it can be told apart from an answer — a model asked for an EMPTY reply
        # says «you're all set» instead, so the silence is a word we recognise and never speak.
        _held = [""] if _said else None

        def _out(piece: str) -> None:
            if _held is not None:
                if _held[0] is None:
                    return                                   # decided: SKIP — nothing of this pass is spoken
                if _held[0] is not False:
                    _held[0] += piece or ""
                    head = _held[0].strip().upper()
                    if head.startswith("SKIP"):
                        _held[0] = None
                        # visible on the timeline (full53 R3 went silent after «let me look…» and nothing said why)
                        emit("brain", "🤐 segundo pase: SKIP — lo ya dicho contestaba", role="system",
                             text=f"{what}: {_said[:120]}", extra={"cat": "flash"})
                        return
                    if __import__("nucleo.flash.tool_round", fromlist=["x"]).still_held(_held[0].strip(), _said):
                        return                               # still could be SKIP, or only repeats what was said: hold
                    piece, _held[0] = _held[0], False
            if piece and _lead[0]:
                piece, _lead[0] = _lead[0] + piece, ""
            send(piece)
        try:
            async for delta in _fup.measured(FastClient(), sys2, user_text, spec, max_tokens, what):
                buf += delta
                _out(speech.inline(take(False)))
            _out(speech.sanitize(take(True), drop_metadata=False))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            _turn_failure.log_named(f"{what} failed (the voice goes on)", e)

    return SimpleNamespace(send=send, take=take, speak=speak, _cover_work=_cover_work, _buf_reset=_buf_reset,
                           _buf_add=_buf_add, spoken=spoken, late=late, first_ms=lambda: first_ms)


def the_turn_requests(had_pending_confirm: bool) -> dict:
    """The turn's request holders: what its tools asked for, read after the stream by the chain and the close."""
    # `v` = the turn's MAIN escalation; `more` = the extra ones when he commissions several DIFFERENT tasks at once
    # (V2-118: only one used to start and the rest were dropped while the turn said all were under way). The rest of
    # the turn reasons over ONE decision; the extra ones are added at the end, once the turn really escalated.
    return dict(
        escalate_req={"v": None, "more": [], "surface": {}},   # V2-227: superficie declarada POR petición
        search_req={"v": None},
        listing_req={"v": None},         # V2-556: la pasada rápida de anuncios (nucleo/acts/search_listing.py)
        recall_req={"v": None},          # V2-056: el modelo pidió RECORDAR (tool recall) — se resuelve tras el stream
        read_req={"v": None},            # V2-668: el modelo pidió LEER un widget (read_widget) — hermana de recall
        reopen_req={"v": None},          # V2-728: el modelo pidió RECUPERAR el resultado de un encargo terminado
        reveal_req={"v": None},          # V2-060: el operador pidió un SECRETO (reveal_secret) — valor OUT-OF-BAND
        music_req={"v": None, "followup": None},  # V2-041: {'query','action'}; 'followup' = 2ª acción de CONTROL
        # (volumen/pausa) pedida EN EL MISMO turno que un play/queue (bug real 2026-07-23: "pon música de Queen y
        # súbele el volumen" decía las DOS cosas pero solo ejecutaba la 1ª — la 2ª se tiraba en silencio)
        images_req={"v": None},          # V2-457: {'query','n'} de `show_images`, ejecutado tras el stream
        style_fired={"v": False},        # V2-046 A1: se fijó/retiró una user rule → ack si el modelo no habló
        acted={"widget": False},
        confirm_state={"handled": False},
        clarify={"msg": None},           # V2-026: pregunta a decir si una referencia a un item no se resolvió
        _closed_by_tool=set(),           # the cards `close_widget` closed this turn — each one once
        _repeat_repair={"v": None},      # (card, repeated view, verdict action) — see `call_for_repeated_view`
        data_done={"v": False},          # V2-026: se despachó una data-op FAST → ack hablado si el modelo no habló
        deduped={"v": False},            # V2-634: el guarda anti context-bleed descartó un duplicado — el turno
                                         # fue ATENDIDO (dedupe deliberado), no un vacío que disculpar
        aside={"v": False},              # V2-657: el modelo emitió [[aparte]] — el turno iba dirigido a OTRA
                                         # persona presente; silencio sancionado, y el refresco de ventana se
                                         # RETRACTA para que la conversación pueda morir durante charla de sala
        worker_acted={"v": None},        # V2-038: 'inject'|'stop'|'answer' si se dirigió a un Brain Worker vivo
        _shown_ids=set(),                # ids ya mostrados ESTE turno → dedup de [[show]] duplicado
        _tool_fired=set(),
        _data_ops_hechas=[],             # V2-391: las data-ops YA ejecutadas de este turno, en orden
        _turn_op_tasks=[],               # the dispatches of THIS turn's data-ops — a read of their card waits for them
        had_pending_confirm=had_pending_confirm,
    )
