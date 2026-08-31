"""`payload JSON inválido` is anomaly no. 1 across the ENTIRE board, and it said nothing.

Counted on 2026-08-28 across the 44 rows of the scoreboard: **18 occurrences** of
`worker/task «↩ zaelar ⚠️ error»: Exit code N payload JSON inválido`, more than **twice** the next
signature. The message was literally that: neither what was invalid about it nor what had been read. A worker cannot
fix what it does not know it wrote incorrectly, so it retries the same way — the trace of those rounds shows three and
four identical attempts in a row.

Two different things, and both were needed:

  · **Tolerate the markdown fence.** When you ask a model to «write JSON», it produces ```json … ``` without
    thinking, because that is how it writes JSON everywhere. It is not ambiguous —a fence has only one reading—,
    so rejecting it protects against nothing: it only wastes an entire turn.
  · **Say WHAT failed.** The parser provides the line, column, and reason, and we were throwing them away.

What is NOT tolerated: single quotes, extra commas, or any other «almost JSON». That really is ambiguous, and a lenient parser
would end up executing what the worker did not say — which is worse than rejecting it.
"""
from __future__ import annotations

from nucleo import bridge_usage as BU

_VALLA = "```json\n{\"accion\": \"buscar\", \"q\": \"hoteles\"}\n```"


def test_un_json_normal_pasa_igual():
    d, err = BU.parse_payload('{"a": 1}')
    assert d == {"a": 1} and err == ""


def test_la_valla_de_markdown_se_tolera():
    d, err = BU.parse_payload(_VALLA)
    assert d == {"accion": "buscar", "q": "hoteles"} and err == ""


def test_tambien_la_valla_sin_idioma():
    d, err = BU.parse_payload("```\n{\"a\": 1}\n```")
    assert d == {"a": 1} and err == ""


def test_un_json_ROTO_dice_linea_columna_y_motivo():
    """«Invalid» by itself is what makes the worker retry the same thing three times."""
    _, err = BU.parse_payload('{"a": 1,}')
    assert "line 1" in err and "column" in err
    assert "empieza por" in err and '{"a": 1,}' in err


def test_el_casi_json_NO_se_arregla_solo():
    """Half the sensitivity, and the part that matters: a lenient parser executes what the worker did not say."""
    for casi in ("{'a': 1}", '{"a": 1,}', "{a: 1}"):
        d, err = BU.parse_payload(casi)
        assert d == {} and err, casi


def test_una_lista_no_es_un_payload():
    """`act` expects an object. Silently returning `{}` would send an empty action as if it were valid."""
    d, err = BU.parse_payload("[1, 2]")
    assert d == {} and "no un objeto" in err and "list" in err


def test_vacio_es_un_payload_vacio_y_no_un_error():
    """`act` without a payload is legitimate — not every command takes arguments."""
    assert BU.parse_payload("") == ({}, "")
    assert BU.parse_payload("   ") == ({}, "")


def test_el_puente_lo_USA_y_enseña_el_motivo():
    """The plumbing: without this, the classification exists and the worker keeps reading «invalid» by itself."""
    from pathlib import Path
    src = Path("nucleo/worker_bridge.py").read_text(encoding="utf-8")
    assert "_bu.parse_payload(_raw)" in src
    assert 'payload JSON inválido ({_src}): {_perr}' in src


# ── V2-469 · plain text for web_search IS the query ──────────────────────────────────────────────────
def test_una_query_pelada_para_web_search_es_la_query():
    """Measured in `cheapest-monitor__us` (00:14): the worker called `act web_search` with the payload being the
    bare query («LG 27US500-W 27 inch 4K monitor price») — the natural thing, in the V2-341 family — and lost
    the turn with «payload JSON inválido». For an action whose payload is exactly {"query": …}, plain
    text has no other reading. It lives in `bare_query_payload`, which decides ONCE for the CLI."""
    d = BU.bare_query_payload("web_search", "LG 27US500-W 27 inch 4K monitor price")
    assert d == {"query": "LG 27US500-W 27 inch 4K monitor price"}


def test_otra_accion_con_texto_plano_sigue_siendo_error():
    """Converting plain text for an action with a structure would invent the payload — that really is ambiguous."""
    assert BU.bare_query_payload("push_channel", "mándale esto a Marc") is None


def test_un_json_roto_no_se_convierte_en_query():
    """Text that STARTS like JSON and fails to parse is malformed JSON, not a query: converting it
    would execute a search with the braces inside."""
    assert BU.bare_query_payload("web_search", '{"query": "hoteles"') is None


def test_el_cli_cablea_la_conversion():
    """Wiring check: the three above pass intact with the CLI call removed."""
    from pathlib import Path
    src = Path("nucleo/worker_bridge.py").read_text(encoding="utf-8")
    assert "bare_query_payload" in src
