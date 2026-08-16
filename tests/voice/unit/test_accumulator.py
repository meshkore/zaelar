"""Una frase en dos tiempos es una sola petición — V2-096, nodo 3.9.

Why this exists rather than a bigger `max_delay`, in one table (measured over 372 real mid-sentence pauses across
the 195 sessions of the local registry):

    p10 0.6s · p25 1.3s · p50 2.3s · p75 3.5s · p90 4.9s · max 19.5s
    fit inside max_delay=2.2s → 48.7%      fit inside 6s → 96.2%

Waiting covered less than half the cases *by construction*, and raising the ceiling delays every turn including the
ones that were already finished. Accumulating takes the clock out of the equation entirely: the pause can last 0.5s
or 19s, because what gets judged is the fragments TOGETHER.

The operator's own example is the specification:

    «oye, ¿qué tal? Ahora vamos a…»   → generates NOTHING, and must not
    «…buscar un libro del autor X»    → now the request is whole; act on the join

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


# ── LOS INVARIANTES DE SEGURIDAD ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("orden", [
    "para", "páralo", "páralo todo.", "Y que lo pares todo.", "Ciérralo todo y páralo todo.",
    "cancélalo", "Cancélalo.", "basta", "cierra todos los widgets", "ciérralo todo",
])
def test_una_orden_de_PARAR_nunca_se_acumula(orden):
    """V2-092 se llama «parar es parar». Un «para» retenido es el operador viendo cómo el agente ignora una orden.

    Aquí se comprueba en el ACUMULADOR además de en `attention.hard_interrupt`, que ya la atiende antes de llegar:
    defensa en profundidad, porque la lista de `hard_interrupt` y esta regla pueden divergir y el precio de que
    divergan lo paga el operador.
    """
    assert _offer(_a(), orden)[0] == "act", f"¡se retuvo una orden de parar!: {orden!r}"


@pytest.mark.parametrize("resp", ["sí", "no", "vale", "sí, te autorizo a borrar toda la agenda",
                                  "Sí, te autorizo a borrar toda la agenda.", "gracias", "ok"])
def test_una_confirmacion_nunca_se_acumula(resp):
    """Es como el operador autoriza algo IRREVERSIBLE. Retener la respuesta a una confirmación es retener la
    confirmación — y «sí»/«si» colapsan al normalizar tildes, que ya costó un fallo."""
    assert _offer(_a(), resp)[0] == "act", f"¡se retuvo una confirmación!: {resp!r}"


@pytest.mark.parametrize("orden", ["pon música", "abre la agenda", "sube el volumen", "cierra eso",
                                   "enséñame mi agenda", "siguiente canción", "vacía la agenda"])
def test_una_orden_corta_pasa_entera(orden):
    """Lo más frecuente que dice el operador. Un acumulador que las retiene es una regresión, no una mejora."""
    assert _offer(_a(), orden)[0] == "act", f"¡se retuvo una orden corta!: {orden!r}"


# ── EL COMPORTAMIENTO QUE PIDIÓ EL OPERADOR ─────────────────────────────────────────────────────────────────────
def test_el_ejemplo_literal_del_operador():
    """«oye, ¿qué tal? Ahora vamos a…» + [pausa] + «buscar un libro del autor X»."""
    a = _a()
    assert _offer(a, "Oye, ¿qué tal?", now=100.0)[0] == "act"          # saludo completo: se contesta
    action, text, why, dropped = _offer(a, "Ahora vamos a", now=101.0)
    assert action == "hold" and text == "" and why and not dropped, "«Ahora vamos a» tenía que quedarse callado"
    # La pausa dura CUATRO SEGUNDOS — más que `max_delay`, que es justo el caso que antes se perdía.
    action, text, _, _ = _offer(a, "buscar un libro del autor X.", now=105.0)
    assert action == "act"
    assert text == "Ahora vamos a buscar un libro del autor X."
    assert not a.pending()


def test_la_pausa_puede_durar_lo_que_quiera():
    """Lo que hace a esto distinto de esperar: NO hay reloj. 19 s fue el hueco real más largo del registro."""
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
    """El hueco que la capa léxica NO cubre, escrito como test para que se vea y se mida en vez de descubrirse otra
    vez en una sesión.

    «Quiero que busques» está sintácticamente cerrada —la última palabra no es función— pero pragmáticamente le falta
    lo esencial: buscar QUÉ. Igual que `'Mora, is there project'`, que sale de pegar dos trozos reales del registro.

    Distinguir esto es exactamente lo que pidió el operador originalmente («o no tienen una definición clara de
    acción, de pregunta o de request»), y AÚN documenta una carencia real tras V2-102: la capa 2 (`_judge`) solo
    se consulta cuando la capa 1 dice INCOMPLETA — aquí la capa 1 ya dice completa (ningún `_HARD`/`_SOFT` al
    final), así que el juez nunca llega a verla. Cerrar este hueco necesitaría consultar al juez TAMBIÉN en el
    veredicto "complete" de la capa 1, lo que convertiría cada turno corto y claro en una llamada de red — el
    mismo coste que V2-095 ya midió y descartó (2026-08-02). Sigue siendo la carencia conocida, ahora con motivo
    explícito de por qué no se cerró aquí.
    """
    a = _a()
    assert _offer(a, "Quiero que busques")[0] == "act", (
        "si esto ya devuelve «hold» o «ask», algo cambió en la capa 1 o en cuándo se llama al juez: revisa antes "
        "de tocar este test")


# ── QUE NO SE CUELGUE NI CONTAMINE ──────────────────────────────────────────────────────────────────────────────
def test_un_hueco_ENORME_no_se_pega_a_lo_de_antes():
    """Pegar un trozo de hace un minuto a una petición nueva daría una petición Frankenstein de dos intenciones.
    Se descarta lo viejo — y se DICE en el motivo, porque perder texto del operador en silencio es peor."""
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
    """El caso patológico: el STT pica una parrafada en trozos que nunca cierran. Se entrega el buffer COMPLETO,
    nunca a medio vaciar — si no, se perdería parte de lo que dijo el operador."""
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
    """Fail-open duro. Que se caiga el juez de completitud no puede convertir al agente en un mudo — retener de más
    es infinitamente peor que colar un turno."""
    acc.set_predicate(lambda t: (_ for _ in ()).throw(RuntimeError("boom")))
    assert _offer(_a(), "y ponerlo en la")[0] == "act"


def test_el_predicado_es_INYECTABLE():
    """La capa 1 (léxica, rápida) es inyectable — no confundir con la capa 2, PRAGMÁTICA/con modelo, cuyo punto de
    entrada es `set_judge` (ver la sección de abajo)."""
    acc.set_predicate(lambda t: (("autor" in t), "falta la petición"))
    a = _a()
    assert _offer(a, "Vamos a buscar un libro.")[0] == "hold", "el predicado inyectado no se usó"
    assert _offer(a, "del autor X")[0] == "act"


# ── LA CAPA 2, EL JUEZ (V2-102) ─────────────────────────────────────────────────────────────────────────────────
# El fallo real que la motivó: "dame los datos personales que conoces de mi" se retuvo TRES veces sin generar
# nunca una respuesta — la capa 1 la lee incompleta ("mi" = posesiva) y este módulo NO tiene válvula de tiempo,
# así que una petición real se perdía PARA SIEMPRE. Ahora, cuando la capa 1 dice incompleta, se consulta al juez.
def test_el_juez_sube_a_ACT_lo_que_el_lexico_marco_incompleto():
    """El caso exacto del fallo real: la capa 1 dice incompleta, el juez (real, cualquier idioma) dice que no."""
    acc.set_judge(_fake_judge("complete", ""))
    a = _a()
    assert _offer(a, "dame los datos personales que conoces de mi")[0] == "act", (
        "el juez dijo COMPLETE y la capa 1 solo debía tener la primera palabra, no la última")


def test_el_juez_puede_pedir_una_ACLARACION():
    """Nuevo veredicto (V2-102): ni actúa ni espera en silencio — pregunta, y la pregunta viaja en el campo
    `motivo` (mismo hueco que ya usaba «por qué se retuvo», reaprovechado). «Ahora vamos a» es lexicalmente
    incompleta (acaba en «a», capa 1 la manda al juez) — a diferencia de «Quiero que busques» (ver el test de
    la carencia conocida arriba), que la capa 1 YA da por completa y nunca llegaría al juez."""
    acc.set_judge(_fake_judge("ask", "¿A dónde vamos?"))
    a = _a()
    action, text, question, dropped = _offer(a, "Ahora vamos a")
    assert action == "ask"
    assert question == "¿A dónde vamos?"
    assert not a.pending(), "una vez preguntado, el buffer se vacía — no se sigue acumulando sobre una pregunta ya hecha"


def test_ASK_sin_pregunta_de_texto_hace_fail_open_a_incompleta():
    """Un juez que dice ASK pero no da pregunta no es accionable — mejor seguir esperando (capa 1 ya validado)
    que hablar con la boca vacía."""
    acc.set_judge(_fake_judge("ask", ""))
    assert _offer(_a(), "Ahora vamos a")[0] == "hold"


def test_el_juez_confirma_incompleta_y_sigue_el_comportamiento_de_siempre():
    """Cuando el juez está de acuerdo con la capa 1, nada cambia respecto a antes de V2-102: se acumula."""
    acc.set_judge(_fake_judge("incomplete", ""))
    assert _offer(_a(), "Ahora vamos a")[0] == "hold"


def test_un_juez_ROTO_no_deja_mudo_al_agente():
    """Fail-open duro, igual que la capa 1: un juez que revienta (red caída, respuesta rara) nunca puede convertir
    la ambigüedad en un cuelgue — cae a «incomplete», que es EXACTAMENTE el comportamiento de antes de V2-102, no
    uno peor."""
    async def _boom(text):
        raise RuntimeError("modelo caído")
    acc.set_judge(_boom)
    assert _offer(_a(), "Ahora vamos a")[0] == "hold"


def test_el_juez_NUNCA_se_consulta_si_la_capa_1_ya_dice_completa():
    """Coste: la capa 2 solo se paga cuando hace falta. Si la capa 1 ya dice completa, el juez ni se llama —
    verificado con un juez que revienta si se invoca."""
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
        # (b) ninguna cadena puede dejar el acumulador retenido más allá de sus válvulas
        assert len(a.fragments) < acc.MAX_FRAGMENTS, f"cadena atascada con {len(a.fragments)} trozos: {c[:3]}"

    assert recompuestas >= 50, (
        f"solo {recompuestas} frases recompuestas sobre {len(chains)} cadenas reales — medido: 141. "
        f"Si ha bajado tanto, el predicado de completitud cambió de comportamiento.")
