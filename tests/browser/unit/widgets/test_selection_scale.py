"""Tests de la SELECCIÓN PROGRESIVA de widgets (V2-084) — la garantía de que el prompt es **O(K), no O(N)**.

El contrato que se defiende aquí, y que hay que romper a propósito para que estos tests fallen:

  1. Ampliar el catálogo NO engorda el turno. Un "¿qué hora es?" con 10.000 widgets cuesta lo mismo que con 100.
  2. Recortar el catálogo NO es amnesia: el widget que el operador NOMBRA se promociona al prompt aunque esté en
     la posición 9.999 (capa `named`, vía `runtime.rank` — nombre/alias, V2-082).
  3. Lo ABIERTO nunca se recorta (es la pantalla del operador) y manda sobre todo lo demás (V2-078).
  4. Cuando queda catálogo fuera, el prompt lo DICE — para que el modelo no niegue capacidades que sí existen ni
     se invente ids, y sepa que `show_widget`/`widget_data` resuelven el nombre contra el catálogo completo.
  5. `GET /widgets` devuelve un ÍNDICE compacto, no los manifests enteros.
"""
import json

import pytest

from widgets import brief, runtime, selection


def _fake_catalog(n: int) -> list[dict]:
    """N widgets sintéticos con nombre/alias distintivos (`contador <i>`) y una acción declarada."""
    return [{"id": f"w{i:05d}", "title": f"Widget número {i}", "name": f"contador {i}",
             "aliases": [f"contador {i}"],
             "whenToUse": f"Cuenta y muestra la métrica número {i} del operador en tiempo real.",
             "actions": {"add": {"desc": "añade", "payload": {"v": 1}}}}
            for i in range(n)]


@pytest.fixture
def catalog(monkeypatch):
    """Instala un catálogo sintético de tamaño N, saltándose el escaneo de disco y sus cachés por mtime."""
    def _install(n: int):
        cat = _fake_catalog(n)
        monkeypatch.setattr(runtime, "_signature", lambda: ("synthetic", n))
        monkeypatch.setitem(runtime._cache, "sig", ("synthetic", n))
        monkeypatch.setitem(runtime._cache, "list", cat)
        monkeypatch.setitem(runtime._index, "sig", None)     # el índice de alias se reconstruye con este catálogo
        return cat
    return _install


# ── 1. O(K), no O(N) ────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("n", [100, 1000, 10000])
def test_prompt_block_is_bounded_regardless_of_catalog_size(catalog, n):
    catalog(n)
    stats: dict = {}
    txt = brief.for_prompt(open_ids=[], recent_ids=[], query="qué hora es", stats=stats)
    assert stats["n_total"] == n
    assert stats["n_selected"] <= selection.MAX_WIDGETS
    assert stats["hidden"] == n - stats["n_selected"]
    # El techo real: el bloque de widgets de un turno que NO va de widgets cabe holgado en 4 KB con CUALQUIER N.
    assert len(txt) < 4000, f"bloque de widgets desbordado con {n} widgets: {len(txt)} chars"


def test_growing_the_catalog_does_not_grow_an_unrelated_turn(catalog):
    """La prueba directa del contrato: el MISMO turno irrelevante con 100 y con 10.000 widgets pesa casi igual."""
    catalog(100)
    small = brief.for_prompt(open_ids=[], recent_ids=[], query="qué hora es")
    catalog(10000)
    big = brief.for_prompt(open_ids=[], recent_ids=[], query="qué hora es")
    assert abs(len(big) - len(small)) < 200, "el catálogo se está colando en un turno que no va de widgets"


# ── 2. Nombrar un widget lo saca de la cola del catálogo ────────────────────────────────────────────────────
@pytest.mark.parametrize("n", [100, 1000, 10000])
def test_named_widget_surfaces_from_the_tail(catalog, n):
    catalog(n)
    last = n - 1
    stats: dict = {}
    txt = brief.for_prompt(open_ids=[], recent_ids=[], query=f"abre el contador {last}", stats=stats)
    assert f"w{last:05d}" in stats["selected_ids"], "el widget NOMBRADO no llegó al prompt"
    assert f"w{last:05d}" in txt
    assert stats["n_named"] >= 1


def test_named_widget_is_ranked_above_filler(catalog):
    catalog(500)
    picked = selection.candidates("abre el contador 499", [], [])
    reasons = {p["w"]["id"]: p["reason"] for p in picked}
    assert reasons.get("w00499") == selection.NAMED
    # …y va por delante del relleno en la lista que ve el modelo.
    ids = [p["w"]["id"] for p in picked]
    assert ids.index("w00499") < ids.index([i for i in ids if reasons[i] == selection.FILL][0])


# ── 3. Lo abierto manda y no se recorta ─────────────────────────────────────────────────────────────────────
def test_open_widgets_always_present_and_first(catalog):
    catalog(5000)
    opened = ["w04000", "w04001"]
    stats: dict = {}
    brief.for_prompt(open_ids=opened, recent_ids=[], query="qué tal", stats=stats)
    assert stats["selected_ids"][:2] == opened
    assert stats["n_open"] == 2


def test_recent_widgets_ride_along_bounded(catalog):
    catalog(5000)
    recent = [f"w0{i:04d}" for i in range(3000, 3010)]      # 10 recientes, más que MAX_RECENT
    stats: dict = {}
    brief.for_prompt(open_ids=[], recent_ids=recent, query="qué tal", stats=stats)
    assert stats["n_recent"] == selection.MAX_RECENT
    assert set(stats["selected_ids"]) & set(recent) == set(recent[:selection.MAX_RECENT])


def test_open_beats_recent_and_neither_is_duplicated(catalog):
    catalog(200)
    stats: dict = {}
    brief.for_prompt(open_ids=["w00100"], recent_ids=["w00100", "w00101"], query="", stats=stats)
    ids = stats["selected_ids"]
    assert ids[0] == "w00100" and ids.count("w00100") == 1
    assert stats["n_open"] == 1


# ── 4. El recorte se DECLARA (ni negar capacidades ni inventar ids) ─────────────────────────────────────────
def test_truncation_is_announced_with_the_escape_hatch(catalog):
    catalog(1000)
    txt = brief.for_prompt(open_ids=[], recent_ids=[], query="hola")
    assert "EXTRACTO" in txt and "show_widget" in txt
    assert "PREGÚNTALE" in txt


def test_no_truncation_notice_when_everything_fits(catalog):
    catalog(5)
    stats: dict = {}
    txt = brief.for_prompt(open_ids=[], recent_ids=[], query="hola", stats=stats)
    assert stats["truncated"] is False and stats["hidden"] == 0
    assert "EXTRACTO" not in txt


def test_real_catalog_is_not_truncated_today(monkeypatch):
    """Cero regresión para el operador: su catálogo real cabe entero bajo el techo (si algún día deja de caber,
    este test avisa antes de que lo note en una conversación)."""
    stats: dict = {}
    brief.for_prompt(open_ids=[], recent_ids=[], query="hola", stats=stats)
    assert stats["truncated"] is False, (
        f"el catálogo real ({stats['n_total']}) ya no cabe en MAX_WIDGETS={selection.MAX_WIDGETS}; "
        "revisa el techo antes de asumir que el recorte es inocuo")


# ── 5. El endpoint devuelve índice, no manifests ────────────────────────────────────────────────────────────
def test_widgets_index_is_much_smaller_than_full_manifests():
    from widgets import server_api
    cat = runtime.catalog()
    if not cat:
        pytest.skip("sin catálogo real en este entorno")
    full = len(json.dumps(cat, ensure_ascii=False))
    idx = len(json.dumps([server_api._index_row(w) for w in cat], ensure_ascii=False))
    assert idx * 3 < full, f"el índice no está comprimiendo nada (índice {idx} vs manifests {full})"


def test_index_row_keeps_identity_and_drops_payload_schemas():
    from widgets import server_api
    row = server_api._index_row({"id": "x", "title": "X", "name": "equis", "aliases": ["equis", "ex"],
                                 "whenToUse": "P" * 500, "actions": {"a": {"payload": {"k": 1}}},
                                 "usage": "prosa larga"})
    assert row["id"] == "x" and row["name"] == "equis" and "ex" in row["aliases"]
    assert "actions" not in row and "usage" not in row          # carga bajo demanda: /widgets/{id}/manifest
    assert len(row["whenToUse"]) <= server_api._INDEX_PURPOSE_MAX


# ── El estado nunca se traga el catálogo entero ─────────────────────────────────────────────────────────────
def test_state_widget_registry_is_capped(tmp_path, monkeypatch):
    from memory import state
    monkeypatch.setattr(state, "read", lambda: {})
    written: dict = {}
    monkeypatch.setattr(state, "write", lambda cur: written.update(cur))
    rows = state.set_widget_registry([{"id": f"w{i}", "name": f"n{i}", "aliases": []} for i in range(5000)])
    assert len(rows) == state._REGISTRY_CAP + 1                 # prefijo + marcador
    assert rows[-1]["_truncated"] is True and rows[-1]["total"] == 5000
