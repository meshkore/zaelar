# Root pytest conftest — test isolation for shared runtime state.
#
# Several unit tests exercise modules that, in production, write to the SINGLE live MeshKore log dir
# (.meshkore/logs/): voice/observer.py::emit() appends to timeline-latest.jsonl, and tests like
# tests/infrastructure/integration/test_sse_observer.py ("error"/"boom"/"oops") or
# tests/connectors/unit/architect/test_architect.py drive that path
# directly. Without isolation those synthetic events land in the very file the running server + the operator's
# audits read for REAL post-mortems — a test's "kind:error boom" is then indistinguishable from a live incident
# (exactly what happened 2026-07-25). Point ZAELAR_LOG_DIR at a throwaway dir for the whole test session BEFORE
# any module reads it at import time. Same knob shape as bus/log.py's ZAELAR_DB / nucleo/workspace.py's
# ZAELAR_WORKSPACE; unset in production → byte-identical to before.
#
# ZAELAR_RESEARCH=0 — el DIRECTOR DE INVESTIGACIÓN (nucleo/research.py) compone el brief de una selección con una
# llamada REAL a un proveedor, en el pre-vuelo de cada escalada. En producción es lo que se quiere; en un test es
# una llamada de red no declarada que cuelga el caso hasta el timeout (visto con
# `test_listener_consumes_escalate_requested`: «busca un piso» es una investigación, así que el despacho se ponía
# a llamar al modelo). Apagado para toda la sesión de test; quien PRUEBE el compositor lo enciende a mano
# (monkeypatch) — la misma forma de knob que ZAELAR_LOG_DIR de arriba, y sin efecto en producción.
#
# ZAELAR_LANGUAGE=en — EL IDIOMA NO LO PONE LA MÁQUINA DEL QUE CORRE LOS TESTS (2026-08-10). Aparecieron dos tests
# verdes por el ENTORNO y no por el código (`test_music_flow`, `test_prompt`): comprobaban frases que se le dicen al
# operador sin fijar el idioma, así que pasaban en una máquina configurada en castellano y habrían fallado en
# cualquier otra y en CI. Es la peor clase de test — no es que falle, es que MIENTE sobre estar cubriendo algo.
# Aquí se fija el idioma con el que ARRANCA el producto (`langs.DEFAULT_LANG`, inglés), que es el estado que vive
# cualquier instalación nueva; un test que pruebe otro idioma lo declara él (monkeypatch), y entonces lo que prueba
# es explícito. Con esto, `config/settings.json` del operador deja de poder cambiar el resultado de la suite.
import os
import tempfile

os.environ.setdefault("ZAELAR_LOG_DIR", tempfile.mkdtemp(prefix="zaelar-test-logs-"))
os.environ.setdefault("ZAELAR_RESEARCH", "0")
# FORZADO, no `setdefault`: con un default, un `ZAELAR_LANGUAGE=es` en el shell del que corre la suite volvería a
# cambiar qué significa «verde», que es justo el problema. El idioma de un test lo declara EL TEST (monkeypatch), y
# probar los dos idiomas se hace comprobando los dos DENTRO del caso —como en el guarda de las capas de memoria—,
# no corriendo la suite dos veces con el entorno cambiado.
os.environ["ZAELAR_LANGUAGE"] = "en"

# …Y LA CONFIG DEL OPERADOR NO DECIDE EL RESULTADO DE LA SUITE (2026-08-10).
#
# Fijar `ZAELAR_LANGUAGE` arriba NO basta, y descubrirlo es el hallazgo: `config/settings.load_into_env()` copia
# `config/settings.json` ENCIMA del entorno (`os.environ[env] = ...`, sin condición) porque en producción el store
# MANDA sobre el env — que es la regla correcta ahí. En un test significa que, en cuanto algo del grafo de imports
# llama a esa función, el idioma del operador (aquí `es`) pisa el de la suite… y con él el proveedor de STT/TTS, el
# modo de atención y el perfil del motor. O sea que un test puede estar verde por la máquina en la que corre.
# Apareció por el idioma (dos tests comprobaban frases en castellano sin fijarlo: verdes aquí, rojos en CI), pero
# la clase es más ancha que el idioma.
#
# Se apunta el fichero de ajustes a un temporal VACÍO para toda la sesión de test, al nivel del módulo y no en un
# fixture, porque los módulos de test se importan ANTES de que corra cualquier fixture. Misma lección de aislamiento
# que ZAELAR_LOG_DIR arriba, ZAELAR_DB en bus/log.py y `store.DATA_DIR` en los tests de widgets: **un test nunca
# lee ni escribe el estado real del operador**. Quien pruebe `load_into_env` de verdad se apunta el fichero él.
try:
    from pathlib import Path as _Path

    from config import settings as _settings

    _settings.SETTINGS_FILE = _Path(tempfile.mkdtemp(prefix="zaelar-test-settings-")) / "settings.json"
except Exception:                                  # sin `config` importable, la suite sigue como antes
    pass
