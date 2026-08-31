"""The worker bridge did not speak the widget vocabulary that the rest of the system already has.

Each widget carries its identity—ID, name, and aliases—and `widgets/registry.py` builds it in normalized form for
the 26. What did not exist was anything USING IT from the worker side: `paths.dir_for` matches the folder and
nothing more, so the bridge replied “the widget «music» does not exist” to a name that the rest of the system
resolves without hesitation.

Measured on 2026-08-28 in `build-a-video-playlist-from-links` (24/7 studio). The worker requested `music`; the
folder is `musica`. **And it is not just an English issue**: the same lookup rejected `reloj`, which is the
Spanish name of the widget whose folder is called `clock`.

It matters twice over right now: the US studio runs all its rounds in English, and English is how the product is
currently being sold.
"""
from __future__ import annotations

from widgets import naming


def test_el_caso_MEDIDO_resuelve():
    assert naming.resolve("music")[0] == "musica"


def test_y_no_era_solo_el_ingles():
    """`reloj` is Spanish and also failed: the bridge did not speak the vocabulary in ANY language."""
    assert naming.resolve("reloj")[0] == "clock"


def test_un_ALIAS_cualquiera_vale():
    assert naming.resolve("playlist")[0] == "musica"


def test_el_id_exacto_gana_sobre_cualquier_alias():
    """If someone enters the ID, that is what they want: an alias of another widget cannot hijack it."""
    assert naming.resolve("agenda") == ("agenda", [])


def test_lo_que_NO_existe_sigue_sin_existir():
    """The half of the sensitivity: a resolver that always finds something is worse than finding nothing, because
    the caller is about to WRITE to whatever it returns."""
    ident, varios = naming.resolve("no-existe-esto-xyz")
    assert ident == "" and varios == []


def test_una_COLISIÓN_es_una_negativa_y_no_una_apuesta():
    """`widgets/aliases.py` guarantees that an alias belongs to only one widget, but a manually edited manifest
    can break that—and choosing one of two widgets to write to is worse than saying no."""
    import widgets.registry as R
    orig = R.registry
    try:
        R.registry = lambda: [{"id": "uno", "name": "Uno", "aliases": ["compartido"]},
                              {"id": "dos", "name": "Dos", "aliases": ["compartido"]}]
        ident, varios = naming.resolve("compartido")
        assert ident == "" and varios == ["dos", "uno"]
        assert "vale para varios" in naming.not_found("compartido", varios)
    finally:
        R.registry = orig


def test_el_no_existe_DICE_los_que_hay():
    """A name rejected without further information leaves the worker guessing, and what it then does is retry the
    same one—measured that very night at three other entry points in the system."""
    msg = naming.not_found("calendar")
    assert "no existe" in msg and "los que hay" in msg and "agenda" in msg


def test_un_registro_ILEGIBLE_no_tumba_al_llamante():
    import widgets.registry as R
    orig = R.registry
    try:
        R.registry = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        assert naming.resolve("music") == ("", [])
        assert "no existe" in naming.not_found("music")
    finally:
        R.registry = orig


def test_las_DOS_puertas_del_worker_lo_usan():
    """The plumbing: `read_widget` and the data path are two different places, and fixing only one leaves the
    worker resolving a name for reading and failing with the same name when writing."""
    from pathlib import Path
    src = Path("nucleo/worker_api.py").read_text(encoding="utf-8")
    assert src.count("from widgets import naming as _nm") == 2
    assert "el widget «{wid}» no existe" not in src, "queda una puerta con el mensaje viejo"
