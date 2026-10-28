"""Deepgram nova-3 STT — remote streaming (alternative to Voxtral)."""
from __future__ import annotations

from livekit.plugins import deepgram as _deepgram

from ...core import langs
from ...core.config import SETTINGS
from . import gazetteer, registry


@registry.register("deepgram")
def build(vad=None):
    first_run = langs.first_run_auto()
    model = SETTINGS.stt_model_deepgram
    opts = {}

    # TERM BOOSTING — only the places EXPECTED in his speech (`gazetteer.expected_terms`): a national list sent
    # on every session turned ordinary words into towns (V2-812 T-07, measured there). Empty by default.
    # Three conditions, and each one is a way to go deaf rather than mishear a town:
    #   · nova-3 only. The plugin RAISES on `keyterm` with any other model, and that exception happens while the
    #     session is being built, so a `ZAELAR_STT_MODEL_DG=nova-2` would take the whole STT down with it.
    #   · not while the language is still auto-detecting. Seeding Spanish toponyms into the first sentence would
    #     bias the very classification that picks the operator's language (`i18n.init.detect`).
    #   · non-empty. An unknown language has no list, and sending an empty one is noise on every request.
    if str(model).startswith("nova-3") and not first_run:
        boost = gazetteer.boost_terms(langs.current_code())
        if boost:
            opts["keyterm"] = boost

    # EGRESS: a mediated deployment opens the socket through egress with its own credential (`nucleo.energy.egress`).
    from nucleo.energy import egress as llm_egress
    base_url, api_key = llm_egress.route_url(llm_egress.base_of("deepgram") + "/listen", SETTINGS.deepgram_api_key or "")
    return _deepgram.STT(
        model=model,
        api_key=api_key or None,
        base_url=base_url,
        # FIRST RUN → `"multi"` (multilingual nova-3, with code-switching): with no language chosen yet, we cannot
        # pin one down, or `i18n.init.detect`'s auto-detection would receive the operator's sentence transcribed
        # through the wrong model and there would be nothing left to classify. NOTE: omitting the parameter does not
        # work here —the Deepgram server falls back to en-US, which is not auto—; we must explicitly request "multi".
        # Once a language has been chosen, use the usual one: LIVE, and the change applies on reconnection.
        language="multi" if first_run else langs.current_code(),
        interim_results=True,
        **opts,
    )
