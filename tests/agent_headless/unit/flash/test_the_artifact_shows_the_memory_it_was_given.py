"""The turn artifact must show the MEMORY that was shown to the model (V2-255).

It comes from a harness proposal for the problem V2-254 left open —nothing prevents a FOURTH copy of the
background-pill rule—: **do not watch the WRITERS; watch the ARTIFACT.** A list of surfaces has proved incomplete
three times because someone has to remember to expand it; but all of them, known and as-yet-unknown, end up in the
same place: a prompt sent to a model. And we already record that
(`observer.turn_detail`, which is **the single point closed by BOTH channels**, voice and probe).

The property, stated about the output: *no prompt sent to a model contains the text of a namespaced slot pill unless
the request names it.*

For that property to be verifiable, the artifact has to CONTAIN the part being checked. And it did not. Measured on
2026-08-21 with the empty session: the recall block lands at character **2,896** of a 16,585-character prompt, 104
characters from the 3,000-character head — and in a real turn the cached state and recent conversation come BEFORE
it, so it ALWAYS falls out.

A verifier reading that artifact would say “clean” about a dirty prompt. It is tonight’s rule applied to the record:
**a ceiling is dangerous only if the reader accepts prefixes**.
"""
import pytest

from nucleo.flash import prompt as fp
from voice import observer as ob

MARCA = "PILDORA_DE_FONDO_MARCADOR"
RECALL = f"Puede que venga a cuento (de tu memoria):\n· {MARCA}"


# The shared STATE is read from the DATABASE, so without control the prompt measures something different on each
# machine —and in the full-map run, another suite may leave it pointing at a database with real memory—. This case
# measures the TRUNCATION, not how much memory the runner has: with loose state it passed by itself and failed in the
# full map (2026-08-29), which is exactly what a test that measures its environment looks like.
_ESTADO = ("── QUIÉN ERES ──\nEres zaelar.\n\n── QUIÉN TIENES DELANTE ──\nEl operador se llama Marc.")


def _prompt(recent: str = "", estado: str = _ESTADO) -> str:
    import unittest.mock as _mock
    from nucleo.flash import memory_cache
    with _mock.patch.object(memory_cache, "get", lambda: (estado, "Marc")):
        s, _ = fp.build_flash_system(recall_block=RECALL, recent_block=recent)
    return s


# ── the measured case ───────────────────────────────────────────────────────────────────────────────────────────

def test_la_memoria_ENSEÑADA_sobrevive_al_recorte_en_un_turno_real():
    """A real turn puts cached state and recent conversation before the recall."""
    largo = "CONVERSACIÓN RECIENTE:\n" + ("· una línea de charla previa\n" * 60)
    assert MARCA in ob._prompt_excerpt(_prompt(largo)), \
        "el registro se comía justo la parte que decide conductas como la de V2-254"


def test_y_tambien_con_la_sesion_vacia():
    assert MARCA in ob._prompt_excerpt(_prompt())


# ── the other direction: it is still a TRUNCATION, and says how much was left out ──────────────────────────────

def test_un_prompt_largo_SIGUE_recortandose():
    """Sensitivity: “making room for memory” must not become storing the entire prompt — this record is persisted
    on every turn."""
    enorme = "x" * 40000
    out = ob._prompt_excerpt(enorme)
    assert len(out) < len(enorme)


def test_y_el_hueco_se_NOMBRA_para_que_nadie_lo_lea_como_ausencia():
    """This lets a verifier say “I cannot certify” instead of “clean” — the INFRA/FAIL distinction the harness
    already uses. Without it, the proposal to watch the artifact lies silently."""
    out = ob._prompt_excerpt("x" * 40000)
    assert "OMITIDOS" in out and "caracteres" in out


def test_lo_que_cabe_entero_no_se_toca():
    assert ob._prompt_excerpt("corto") == "corto"


# ── the artifact is where the two channels meet ───────────────────────────────────────────────────────────────

def test_turn_detail_es_el_UNICO_punto_que_cierran_los_dos_canales():
    """SOURCE GUARD: if someone gives a channel its own capture, the proposal to watch the artifact loses its single
    artifact and we return to a list of sites to update."""
    import inspect
    src = inspect.getsource(ob.turn_detail)
    assert "turn.completed" in src, "el bus es lo que permite consumirlo sin acoplarse a ningún canal"
    assert "system_prompt" in src and "_prompt_excerpt" in src


@pytest.mark.parametrize("cabeza,cola", [(ob._HEAD_CHARS, ob._TAIL_CHARS)])
def test_la_cola_sigue_cubriendo_el_estado_vivo(cabeza, cola):
    """Live state (“RIGHT NOW”) goes at the END and is what changes each turn — V2-195 put it there after a diagnosis
    that nearly went wrong. Widening the head must not have eaten into the tail."""
    s = _prompt()
    ex = ob._prompt_excerpt(s + "y" * 20000)
    assert cola >= 7000
    assert ex.endswith("y" * 100)


# ── the margin, stated as a NUMBER ────────────────────────────────────────────────────────────────────────────
# The case above passes or fails depending on how much space what comes BEFORE the recall occupies, and that grows
# on its own: each new state block (V2-490 added one) pushes memory toward the truncated center. A boolean does not
# warn that the margin is running out — it warns once it has run out, by which point the artifact has been lying for
# some time.

def test_el_MARGEN_hasta_el_recorte_se_mide_y_no_se_agota():
    """Sensitivity for the test above: fitting TODAY is not enough.

    REWRITTEN with V2-536 (2026-09-01), keeping what it protected. The stable-prefix reorder moved every
    per-turn block — the recall included — to the END of the prompt, so the capture window that holds the
    shown memory is now the TAIL, not the head. What eats this margin today is whatever sits AFTER the
    recall (the directive and the live state, which V2-479 already let grow to 12 sheet rows): when that
    region outgrows the tail, the shown memory falls into the omitted middle and a verifier says “clean”
    about a prompt it never saw — the exact failure V2-255 closed, from the other side."""
    s = _prompt("CONVERSACIÓN RECIENTE:\n" + ("· una línea de charla previa\n" * 60))
    pos = s.find(MARCA)
    assert pos >= 0
    inicio_cola = len(s) - ob._TAIL_CHARS
    margen = pos - inicio_cola
    assert margen > 400, (
        f"la memoria enseñada queda a {margen} caracteres de caerse del artefacto (cola de {ob._TAIL_CHARS}). "
        f"No ha fallado todavía, y por eso hay que mirarlo ahora: cuando falle, un verificador dirá «limpio» "
        f"sobre un prompt sucio.")


def test_un_ESTADO_grande_ya_NO_empuja_la_memoria_fuera_pero_un_estado_vivo_enorme_si():
    """Truncation is still by POSITION — this test states WHERE the risk lives after V2-536's reorder.

    Before, a long state block (an operator with lots of durable memory) pushed the recall past the head and
    out of the artifact. With the per-turn blocks at the END, a long state pushes the recall TOWARD the tail
    — INTO the capture — so that direction is closed and the first assertion says so. What can still push the
    shown memory into the omitted middle is a huge LIVE block after it. That has never been measured in
    production (live is bounded by its own budgets), but position-based truncation means the risk exists and
    does not depend on anything a higher ceiling can fix — stated here so nobody reads the capture as
    complete by construction."""
    import unittest.mock as _mock
    enorme = _ESTADO + "\n" + ("· un hecho durable más sobre la persona\n" * 300)
    s = _prompt(estado=enorme)
    assert MARCA in s, "el bloque de recall ya no viaja en el prompt: esto sería otro fallo"
    assert MARCA in ob._prompt_excerpt(s), (
        "un estado largo ya no puede costarle la memoria al artefacto: si esto se pone rojo, el orden de "
        "bloques ha vuelto a cambiar y hay que re-derivar dónde vive el riesgo")
    with _mock.patch.object(fp, "live_state", lambda: "· una línea de estado vivo\n" * 900):
        s2 = _prompt()
        assert MARCA in s2
        assert MARCA not in ob._prompt_excerpt(s2), (
            "si esto pasa a ser verde, el recorte ha dejado de ser por posición y este aviso sobra")
