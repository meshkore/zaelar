"""
LA SUITE NO DEPENDE DE LA MÁQUINA EN LA QUE CORRE — un guarda sobre los guardas.

Esto nace de un test verde que MENTÍA (2026-08-10). Dos casos (`test_music_flow`, `test_prompt`) comprobaban frases
que se le dicen al operador sin fijar el idioma: pasaban en una máquina con el castellano configurado y habrían
fallado en cualquier otra y en CI. Al arreglarlo apareció que la causa era más ancha que el idioma —
`config/settings.load_into_env()` copia `config/settings.json` ENCIMA del entorno, sin condición, porque en
producción el store MANDA sobre el env (regla correcta allí). En un test eso significa que la configuración
personal del operador —idioma, proveedor de STT/TTS, modo de atención, perfil del motor— decide el resultado de la
suite en cuanto algo del grafo de imports llama a esa función.

No es que fallara: es que **no se podía confiar en el verde**, que es peor. La misma familia que un fixture sin
aislar que borraba los datos reales de los widgets, o dos nodos del mapa de tests con el mismo número.

Este fichero fija las invariantes de aislamiento de la sesión de test. Si alguna se rompe, la suite vuelve a poder
mentir — y no se enteraría nadie hasta que un test pasara aquí y fallara en otro sitio.
"""
from __future__ import annotations

import os
from pathlib import Path


def test_the_language_is_the_products_own_default_not_the_operators():
    """Se corre en el idioma con el que ARRANCA el producto, que es el estado de cualquier instalación nueva. Un
    test que quiera otro idioma lo declara él — y entonces lo que prueba es explícito."""
    from voice.engine.core import langs

    assert langs.current_code() == langs.DEFAULT_LANG == "en"


def test_the_operators_settings_file_is_not_the_one_the_suite_reads():
    from config import settings

    p = str(settings.SETTINGS_FILE)
    assert "zaelar-test-settings-" in p, (
        "la suite está leyendo el `settings.json` REAL: la configuración del operador puede cambiar el resultado "
        f"de los tests (y en producción el store pisa el entorno a propósito). Apunta a: {p}")
    assert not Path(settings.SETTINGS_FILE).exists(), "y el fichero de la suite arranca VACÍO, no copiado"


def test_loading_the_settings_cannot_flip_the_suite():
    """La prueba del algodón: llamar a lo que hace el arranque real no puede cambiar el idioma bajo los pies."""
    from config import settings
    from voice.engine.core import langs

    settings.load_into_env()
    assert langs.current_code() == "en"


def test_the_logs_of_a_test_never_land_in_the_operators_timeline():
    """Ya existía (2026-07-25: un «kind:error boom» de un test se leyó como incidente real) y se comprueba aquí
    para que las invariantes de aislamiento vivan juntas y se lean de una."""
    d = os.getenv("ZAELAR_LOG_DIR") or ""
    assert "zaelar-test-logs-" in d, f"los eventos de la suite irían al timeline real: {d!r}"
