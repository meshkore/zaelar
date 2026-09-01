"""The three NODE OVERRIDES of zaelar's LiveKit agent, in one place (extracted V2-538, 2026-09-01).

WHY IT IS ITS OWN MODULE, and it was the architecture ratchet that asked: `agent.py` sat at 890 lines against
a 900 ceiling, so a legitimate ten-line change tipped it — and the rule in this house is EXTRACT, never a
taller ceiling. This class is the clean seam: three methods, each one delegating to a speech module, needing
nothing from the entrypoint's enclosing scope. It is also a coherent subject on its own — *what zaelar does to
the pipeline's text as it flows through*, which is exactly what someone chasing «why did the voice say that»
comes looking for.

The three, and they are NOT interchangeable — each sits where it does for a reason that was measured:

  · `llm_node` — the LEAD-IN FILLER (V2-529). A `say()`-based filler is structurally LATE (the reply is
    already the scheduler's current speech, so the say is only authorised once the reply finishes playing —
    measured live: «Vale, empiezo» … «Espera, espera»), and a `tts_node` wrapper cannot work either: this
    pipeline only calls tts_node from `_start_segment()`, i.e. once the first text chunk exists, so it can
    never observe that the text is LATE. Emitting the filler from here with a FlushSentinel closes a segment
    of its own → synthesised and played while the model still thinks, with the reply as segment two.
  · `transcription_node` — what LiveKit FORWARDS: subtitles and the `chat_ctx` message. The filler is stripped
    here; its chat-wall visibility is our own marked event, never the reply's bubble.
  · `tts_node` — what is SPOKEN, and the one place every spoken path converges on (generated reply, `say()`,
    the filler, a proactive notice). Figures are made speakable here and nowhere else, so «151.008 €» cannot
    slip through by taking another road (V2-538). Deliberately NOT in `transcription_node`: on screen the
    operator wants to READ «151.008 €».

Full contracts: `voice/engine/speech/filler_audio.py` and `voice/engine/speech/say_numbers.py`.
"""
from __future__ import annotations

from livekit.agents import Agent

from ..core import langs


class ZaelarAgent(Agent):
    def llm_node(self, chat_ctx, tools, model_settings):
        from voice.engine.speech import filler_audio as _fa
        return _fa.llm_node_with_filler(self, Agent.default.llm_node, chat_ctx, tools, model_settings)

    def transcription_node(self, text, model_settings):
        from voice.engine.speech import filler_audio as _fa
        return _fa.transcription_node_without_filler(self, Agent.default.transcription_node,
                                                     text, model_settings)

    def tts_node(self, text, model_settings):
        from voice.engine.speech import say_numbers as _sn
        return _sn.tts_node_speaking_figures(self, Agent.default.tts_node, text, model_settings,
                                             langs.current_code())
