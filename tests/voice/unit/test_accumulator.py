"""One sentence in two stages is one request — V2-096, node 3.9.

Why this exists rather than a bigger `max_delay`, in one table (measured over 372 real mid-sentence pauses across
the 195 sessions of the local registry):

    p10 0.6s · p25 1.3s · p50 2.3s · p75 3.5s · p90 4.9s · max 19.5s
    fit inside max_delay=2.2s → 48.7%      fit inside 6s → 96.2%

Waiting covered less than half the cases *by construction*, and raising the ceiling delays every turn including the
ones that were already finished. Accumulating takes the clock out of the equation entirely: the pause can last 0.5s
or 19s, because what gets judged is the fragments TOGETHER.

The operator's own example is the specification:

    “oye, ¿qué tal? Ahora vamos a…”   → generates NOTHING, and must not
    “…buscar un libro del autor X”    → now the request is whole; act on the join

The first three tests are the safety invariants. They matter more than the feature: a stop order or an
authorisation that gets swallowed is a worse bug than the one this fixes.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import accumulator as acc


async def _stub_incomplete(text: str) -> tuple[str, str]:
    """Default layer-2 stub for every test below: always agrees with a lexical "incomplete" verdict, fast and
    with zero network. Without this, every pre-V2-102 test whose fragments are lexically incomplete would fire a
    REAL `judge()` call (network, `nucleo.memllm`) on each `offer()` — slow, flaky, and needs a live credential
    the test sandbox doesn't have. Tests that actually exercise the judge (§ layer 2 below) inject their own
    `acc.set_judge(...)` fake instead."""
    return "incomplete", ""


@pytest.fixture(autouse=True)
def _lexico():
    """Every test runs on the default lexical predicate and a fast, network-free judge stub, whatever a previous
    test injected."""
    acc.set_predicate(None)
    acc.set_judge(_stub_incomplete)
    yield
    acc.set_predicate(None)
    acc.set_judge(None)


def _fake_judge(verdict: str, extra: str = ""):
    """Factory for a one-shot layer-2 fake: `set_judge` wants an ASYNC `(text) -> (verdict, extra)` callable."""
    async def _fn(text: str) -> tuple[str, str]:
        return verdict, extra
    return _fn


def _a():
    return acc.Accumulator()


def _offer(a: acc.Accumulator, *args, **kwargs) -> tuple[str, str, str, str]:
    """`offer()` is async since V2-102 (it may `await` the layer-2 judge) — this is the SAME
    `asyncio.run(...)`-per-call convention already used elsewhere in this test suite for a sync test function
    that needs one async result (see `tests/voice/unit/test_language_bootstrap.py`), not pytest-asyncio."""
    return asyncio.run(a.offer(*args, **kwargs))


# ── THE SAFETY INVARIANTS ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("orden", [
    "para", "páralo", "páralo todo.", "Y que lo pares todo.", "Ciérralo todo y páralo todo.",
    "cancélalo", "Cancélalo.", "basta", "cierra todos los widgets", "ciérralo todo",
])
def test_una_orden_de_PARAR_nunca_se_acumula(orden):
    """V2-092 is called “stop means stop.” A held “stop” is the operator watching the agent ignore an order.

    This is checked in the ACCUMULATOR as well as in `attention.hard_interrupt`, which already handles it before it
    gets here: defense in depth, because the `hard_interrupt` list and this rule can diverge, and the operator pays
    the price when they do.
    """
    assert _offer(_a(), orden)[0] == "act", f"¡se retuvo una orden de parar!: {orden!r}"


@pytest.mark.parametrize("resp", ["sí", "no", "vale", "sí, te autorizo a borrar toda la agenda",
                                  "Sí, te autorizo a borrar toda la agenda.", "gracias", "ok"])
def test_una_confirmacion_nunca_se_acumula(resp):
    """This is how the operator authorizes something IRREVERSIBLE. Holding the response to a confirmation means
    holding the confirmation — and “sí”/“si” collapse when accents are normalized, which has already caused a bug."""
    assert _offer(_a(), resp)[0] == "act", f"¡se retuvo una confirmación!: {resp!r}"


@pytest.mark.parametrize("orden", ["pon música", "abre la agenda", "sube el volumen", "cierra eso",
                                   "enséñame mi agenda", "siguiente canción", "vacía la agenda"])
def test_una_orden_corta_pasa_entera(orden):
    """The most frequent thing the operator says. An accumulator that holds them is a regression, not an improvement."""
    assert _offer(_a(), orden)[0] == "act", f"¡se retuvo una orden corta!: {orden!r}"


# ── THE BEHAVIOR THE OPERATOR REQUESTED ─────────────────────────────────────────────────────────────────────────
def test_el_ejemplo_literal_del_operador():
    """“oye, ¿qué tal? Ahora vamos a…” + [pause] + “buscar un libro del autor X”."""
    a = _a()
    assert _offer(a, "Oye, ¿qué tal?", now=100.0)[0] == "act"          # complete greeting: it gets answered
    action, text, why, dropped = _offer(a, "Ahora vamos a", now=101.0)
    assert action == "hold" and text == "" and why and not dropped, "«Ahora vamos a» tenía que quedarse callado"
    # The pause lasts FOUR SECONDS — longer than `max_delay`, which is exactly the case previously lost.
    action, text, _, _ = _offer(a, "buscar un libro del autor X.", now=105.0)
    assert action == "act"
    assert text == "Ahora vamos a buscar un libro del autor X."
    assert not a.pending()


def test_la_pausa_puede_durar_lo_que_quiera():
    """What makes this different from waiting: there is NO timer. 19 s was the longest real gap in the registry."""
    for gap in (0.3, 2.2, 4.9, 12.0, 19.5):
        a = _a()
        assert _offer(a, "Busca también en todas las", now=0.0)[0] == "hold"
        action, text, _, _ = _offer(a, "páginas que puedas, ¿vale?", now=gap)
        assert action == "act", f"con un hueco de {gap}s no se recompuso la frase"
        assert text == "Busca también en todas las páginas que puedas, ¿vale?"


def test_tres_trozos_seguidos_se_juntan():
    a = _a()
    assert _offer(a, "Quiero que me busques un", now=0.0)[0] == "hold"
    assert _offer(a, "velero de", now=2.0)[0] == "hold"
    action, text, _, _ = _offer(a, "unos cuarenta pies.", now=5.0)
    assert action == "act" and text == "Quiero que me busques un velero de unos cuarenta pies."


def test_LIMITE_CONOCIDO_el_lexico_no_ve_que_falta_el_OBJETO():
    """The gap the lexical layer does NOT cover, written as a test so it can be seen and measured instead of being
    discovered again in a session.

    “Quiero que busques” is syntactically closed —the last word is not a function word— but pragmatically lacks
    the essential thing: what to search for. Like `'Mora, is there project'`, formed by joining two real registry fragments.

    Distinguishing this is exactly what the operator originally requested (“or do not have a clear definition of an
    action, question, or request”), and it STILL documents a real limitation after V2-102: layer 2 (`_judge`) is
    consulted only when layer 1 says INCOMPLETE — here layer 1 already says complete (no `_HARD`/`_SOFT` at the
    end), so the judge never sees it. Closing this gap would require consulting the judge ALSO for layer 1's
    “complete” verdict, turning every short, clear turn into a network call — the same cost V2-095 measured and
    rejected (2026-08-02). It remains a known limitation, now with an explicit reason why it was not closed here.
    """
    a = _a()
    assert _offer(a, "Quiero que busques")[0] == "act", (
        "si esto ya devuelve «hold» o «ask», algo cambió en la capa 1 o en cuándo se llama al juez: revisa antes "
        "de tocar este test")


# ── MUST NOT HANG OR CONTAMINATE ──────────────────────────────────────────────────────────────────────────────
def test_un_hueco_ENORME_no_se_pega_a_lo_de_antes():
    """Appending a fragment from a minute ago to a new request would produce a Frankenstein request with two
    intentions. The old content is discarded — and this is STATED in the reason, because silently losing the
    operator's words is worse."""
    a = _a()
    _offer(a, "y ponerlo en la", now=0.0)
    action, text, why, dropped = _offer(a, "Abre la agenda.", now=acc.MAX_GAP_S + 5)
    assert action == "act"
    assert text == "Abre la agenda.", "se contaminó la petición nueva con el fragmento viejo"
    # 2026-08-15: the drop reason moved to its own field (see the test right below — a "hold" outcome needs it
    # just as much, and used to lose it entirely).
    assert dropped == "y ponerlo en la"
    assert not why, "a clean act needs no hold-reason — the discard lives in its own field now"


def test_a_drop_that_lands_on_HOLD_still_reports_the_discard():
    """THE ACTUAL BUG (session d4b2bc35, 2026-08-15): the fragment that TRIGGERS a drop is, more often than not,
    itself incomplete — it falls to the "hold" branch a few lines further down, which used to carry NO discard
    info at all. The operator's words vanished with no trace anywhere, not even the timeline: reproduced verbatim
    from the real session, where a 3-fragment question got lost entirely after a 64s gap, and the next turn
    ("qué edad tengo," and friends) got answered as if it had never been said, with zero "descartado"/"hueco"
    event anywhere in the whole log."""
    a = _a()
    _offer(a, "Me refería a mi información,", now=0.0)
    action, text, why, dropped = _offer(a, "del software,", now=acc.MAX_GAP_S + 10)
    assert action == "hold", "«del software,» alone is still mid-sentence — this is how the real bug reproduced"
    assert dropped == "Me refería a mi información,", (
        "the discard must be visible EVEN WHEN this call ends in hold, not only when it ends in act")
    assert why, "there is still a hold reason of its own, independent from the discard"


# ── THE GROWING CHAIN (LiveKit hands back the whole turn, not just what's new) ──────────────────────────────────
# Second cause, found while reading the REAL session (d4b2bc35) to reproduce the bug above: when the semantic
# detector vetoes closing an ACOUSTIC turn (the same lexical predicate this module uses), LiveKit does not close
# the sentence between fragments — its `ChatContext` keeps growing it, so what reaches `offer()` on the NEXT call
# is the WHOLE utterance so far, not a fresh delta. Without this fix the accumulator appended on top of what was
# already appended, and that session's `acumulado` field literally read
# "Me refería a mi información, Me refería a mi información, personal, dónde vivo, en qué trabajo," — duplicated.
def test_a_GROWING_fragment_does_not_get_duplicated():
    a = _a()
    action, _, _, _ = _offer(a, "Me refería a mi información,", now=0.0)
    assert action == "hold"
    action, _, _, _ = _offer(a, "Me refería a mi información, personal, dónde vivo, en qué trabajo,", now=2.3)
    assert action == "hold"
    assert a.text() == "Me refería a mi información, personal, dónde vivo, en qué trabajo,", (
        f"duplicated: {a.text()!r}")
    action, _, _, _ = _offer(a, 
        "Me refería a mi información, personal, dónde vivo, en qué trabajo, qué edad tengo,", now=4.6)
    assert action == "hold"
    assert a.text() == "Me refería a mi información, personal, dónde vivo, en qué trabajo, qué edad tengo,", (
        f"duplicated again: {a.text()!r}")
    assert len(a.fragments) == 1, "a turn that only GROWS is one chain, not several fragments stacked up"


def test_the_full_real_session_discards_CLEAN_not_tripled():
    """The end-to-end reproduction of the incident: the 3 real growing fragments, the 64s gap, then a 4th
    fragment on a new topic. Before this fix, the discarded content arrived tripled (see the test above); now
    it's exactly what the operator said, once — which is in turn what `acc_fragment_dropped`
    (voice/engine/llm/providers/nucleo.py) ends up saying out loud."""
    a = _a()
    _offer(a, "Me refería a mi información,", now=0.0)
    _offer(a, "Me refería a mi información, personal, dónde vivo, en qué trabajo,", now=2.3)
    _offer(a, "Me refería a mi información, personal, dónde vivo, en qué trabajo, qué edad tengo,", now=4.6)
    _, _, _, dropped = _offer(a, "Está tontado de ríos.", now=4.6 + acc.MAX_GAP_S + 39)
    assert dropped == "Me refería a mi información, personal, dónde vivo, en qué trabajo, qué edad tengo,", (
        f"the discarded content arrived corrupted: {dropped!r}")


def test_a_NEW_fragment_that_does_not_extend_still_concatenates():
    """`_grows` is purely structural (prefix match): two genuinely distinct fragments — neither a prefix of the
    other — still have to CONCATENATE like before, never replace each other."""
    a = _a()
    _offer(a, "Quiero que me busques un", now=0.0)
    action, _, _, _ = _offer(a, "velero de", now=1.0)
    assert action == "hold"
    assert a.text() == "Quiero que me busques un velero de", "a fragment that does NOT grow must keep appending"


def test_la_valvula_de_TROZOS_entrega_todo_lo_que_hay():
    """The pathological case: the STT chops a long utterance into fragments that never close. The COMPLETE buffer
    is delivered, never partially emptied — otherwise part of what the operator said would be lost."""
    a = _a()
    trozos = ["y luego", "y además", "y también", "y encima", "y aparte", "y para acabar"]
    outs = [_offer(a, t, now=float(i)) for i, t in enumerate(trozos)]
    assert outs[-1][0] == "act", "la válvula no disparó"
    assert "válvula" in outs[-1][2]
    assert not outs[-1][3], "no gap happened here — no discard should be reported"
    for t in trozos:
        assert t in outs[-1][1], f"la válvula se comió {t!r}"
    assert not a.pending()


def test_la_valvula_de_TAMANO_tambien_corta(monkeypatch):
    monkeypatch.setattr(acc, "MAX_CHARS", 80)
    a = _a()
    action = "hold"
    for i in range(20):
        action, text, why, _ = _offer(a, "y otra cosa más de las que", now=float(i))
        if action == "act":
            assert "chars" in why and len(text) >= 80
            break
    assert action == "act", "la válvula de tamaño no disparó"


def test_un_predicado_ROTO_no_deja_mudo_al_agente():
    """Hard fail-open. If the completeness judge goes down, it must not turn the agent mute — holding too much is
    infinitely worse than letting a turn through."""
    acc.set_predicate(lambda t: (_ for _ in ()).throw(RuntimeError("boom")))
    assert _offer(_a(), "y ponerlo en la")[0] == "act"


def test_el_predicado_es_INYECTABLE():
    """Layer 1 (lexical, fast) is injectable — do not confuse it with layer 2, PRAGMATIC/model-based, whose entry
    point is `set_judge` (see the section below)."""
    acc.set_predicate(lambda t: (("autor" in t), "falta la petición"))
    a = _a()
    assert _offer(a, "Vamos a buscar un libro.")[0] == "hold", "el predicado inyectado no se usó"
    assert _offer(a, "del autor X")[0] == "act"


# ── LAYER 2, THE JUDGE (V2-102) ─────────────────────────────────────────────────────────────────────────────────
# The real bug that prompted it: "dame los datos personales que conoces de mi" was held THREE times without ever
# generating a response — layer 1 reads it as incomplete ("mi" = possessive), and this module has NO time valve,
# so a real request was lost FOREVER. Now, when layer 1 says incomplete, the judge is consulted.
def test_el_juez_sube_a_ACT_lo_que_el_lexico_marco_incompleto():
    """The exact case from the real bug: layer 1 says incomplete, while the judge (real, any language) says it is not."""
    acc.set_judge(_fake_judge("complete", ""))
    a = _a()
    assert _offer(a, "dame los datos personales que conoces de mi")[0] == "act", (
        "el juez dijo COMPLETE y la capa 1 solo debía tener la primera palabra, no la última")


def test_el_juez_puede_pedir_una_ACLARACION():
    """New verdict (V2-102): it neither acts nor waits silently — it asks, and the question travels in the `motivo`
    (the same slot previously used for “why it was held,” repurposed). “Ahora vamos a” is lexically incomplete
    (it ends in “a,” so layer 1 sends it to the judge) — unlike “Quiero que busques” (see the known-gap test above),
    which layer 1 ALREADY considers complete and would never send to the judge."""
    acc.set_judge(_fake_judge("ask", "¿A dónde vamos?"))
    a = _a()
    action, text, question, dropped = _offer(a, "Ahora vamos a")
    assert action == "ask"
    assert question == "¿A dónde vamos?"
    assert not a.pending(), "una vez preguntado, el buffer se vacía — no se sigue acumulando sobre una pregunta ya hecha"


def test_ASK_sin_pregunta_de_texto_hace_fail_open_a_incompleta():
    """A judge that says ASK but provides no question is not actionable — better to keep waiting (layer 1 already
    validated it) than to speak with an empty mouth."""
    acc.set_judge(_fake_judge("ask", ""))
    assert _offer(_a(), "Ahora vamos a")[0] == "hold"


def test_el_juez_confirma_incompleta_y_sigue_el_comportamiento_de_siempre():
    """When the judge agrees with layer 1, nothing changes from before V2-102: the content is accumulated."""
    acc.set_judge(_fake_judge("incomplete", ""))
    assert _offer(_a(), "Ahora vamos a")[0] == "hold"


def test_un_juez_ROTO_no_deja_mudo_al_agente():
    """Hard fail-open, just like layer 1: a judge that crashes (network down, malformed response) can never turn
    ambiguity into a hang — it falls back to “incomplete,” which is EXACTLY the behavior from before V2-102, not
    a worse one."""
    async def _boom(text):
        raise RuntimeError("modelo caído")
    acc.set_judge(_boom)
    assert _offer(_a(), "Ahora vamos a")[0] == "hold"


def test_el_juez_NUNCA_se_consulta_si_la_capa_1_ya_dice_completa():
    """Cost: layer 2 is paid for only when needed. If layer 1 already says complete, the judge is not called —
    verified with a judge that raises if invoked."""
    async def _must_not_be_called(text):
        raise AssertionError("el juez no debía llamarse: la capa 1 ya había dicho completa")
    acc.set_judge(_must_not_be_called)
    assert _offer(_a(), "para")[0] == "act"          # orden corta, capa 1 la deja pasar por _ALSO_A_VERB


def test_texto_vacio_no_toca_el_buffer():
    a = _a()
    _offer(a, "y ponerlo en la", now=0.0)
    assert _offer(a, "   ", now=1.0)[0] == "act"
    assert a.pending(), "un turno vacío tiró el buffer"


# ── CONTRA EL REGISTRO REAL ─────────────────────────────────────────────────────────────────────────────────────
SESSIONS = __import__("pathlib").Path(__file__).resolve().parents[3] / ".meshkore/logs/sessions"


@pytest.mark.skipif(not SESSIONS.is_dir() or not list(SESSIONS.glob("*.jsonl")),
                    reason="the session registry is local to the operator's machine (gitignored)")
def test_sobre_las_sesiones_REALES_recompone_frases_y_no_se_atasca():
    """The end-to-end claim, on production data: replaying every chain of consecutive operator transcripts (a
    sentence said in several goes), the accumulator has to (a) recompose a good number of them and (b) never end up
    holding a chain forever.

    Numbers are asserted as a FLOOR, not an exact figure — the registry grows every session and a test that pins an
    exact count would go red for the wrong reason.
    """
    import json
    chains, cur = [], []
    for p in sorted(SESSIONS.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("kind") != "transcript":
                continue
            txt = (e.get("text") or "").strip()
            if e.get("role") == "user" and txt:
                cur.append(txt)
            elif e.get("role") == "assistant" and txt:
                if len(cur) > 1:
                    chains.append(cur)
                cur = []
    if len(chains) < 10:
        pytest.skip(f"too few multi-fragment chains to measure ({len(chains)})")

    recompuestas = 0
    for c in chains:
        a = _a()
        for i, txt in enumerate(c):
            action, merged, _, _ = _offer(a, txt, now=float(i) * 2.0)
            if action == "act" and " " in merged and merged != txt:
                recompuestas += 1
        # (b) no chain may leave the accumulator held beyond its valves
        assert len(a.fragments) < acc.MAX_FRAGMENTS, f"cadena atascada con {len(a.fragments)} trozos: {c[:3]}"

    # The floor is a PROPORTION, not a count. It was written as `>= 50` against the 141 measurements on the day it
    # was calibrated, based on the premise stated in the docstring: “the registry grows every session.” The premise
    # is false — the registry was emptied on 2026-08-15 when the operator's diary was removed from the public repo—
    # so the test went DORMANT under the “fewer than 10 chains” `skip`, and on 2026-08-21, after restarting the engine
    # and generating new sessions, woke up red with 16 out of 17 chains: a 94% success rate reported as a failure.
    # An absolute count on live data measures CORPUS SIZE; the proportion measures the predicate, which is the only
    # thing this file can assert. Without this, the next log cleanup will blame the product again.
    assert recompuestas >= max(5, len(chains) // 2), (
        f"solo {recompuestas} frases recompuestas sobre {len(chains)} cadenas reales (menos de la mitad). "
        f"El predicado de completitud cambió de comportamiento.")
