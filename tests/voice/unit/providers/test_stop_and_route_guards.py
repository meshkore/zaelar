"""
Los dos guardas que costaron la sesión b70a45d0 (2026-08-14).

El operador pidió vaciar la agenda. Nunca se vació. La cadena completa del fallo, con sus dos eslabones evitables:

1. **Enrutado**: el backstop de «promesa sin acción» escaló la petición con `kind:"web"` FIJO. Una data-op
   puramente local («lees lo que hay en la agenda, lo borras y compruebas») se convirtió en una tarea de navegador:
   dos tarjetas de navegador que nadie pidió, rótulo «Buscando en la web…», y —el daño real— la tarea pasó a ser
   «la tarea del navegador».
2. **Hachazo**: el worker hizo lo correcto (leyó, borró tareas, se paró en el gate de confirmación de la acción
   irreversible y preguntó). El operador autorizó. Y el turno siguiente emitió, en el MISMO milisegundo,
   `answer_worker` con la autorización **y** `stop_worker` — que encontró la tarea porque se llamaba «del
   navegador», por el eslabón 1. Tarea cancelada `ok:False`, autorización entregada a un cadáver, y al operador se
   le dijo «Vale, se lo digo».

Aquí se fijan los dos guardas por separado, con las FRASES REALES de la sesión como casos.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

NUCLEO = Path(__file__).resolve().parents[4] / "voice/engine/llm/providers/nucleo.py"


# ── GUARD 2: matar exige que el operador lo haya pedido ────────────────────────────────────────────────────────
def _says_stop(t: str) -> bool:
    """Réplica del detector local del proveedor (`_says_stop`), extraído del fuente para poder probarlo sin montar
    media sesión de LiveKit. Si el fuente cambia, `test_el_detector_del_fuente_es_este` lo canta."""
    n = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c)).lower()
    return bool(re.search(
        r"\b(par[ae]r(?:me|te|lo|la|los|las)?|par[ae]l[oa]s?|paralo|parala|"
        r"det[ei]n(?:er|lo|la|los|las|ga|gan)?|cancel(?:a|ar|alo|ala|o|en)|"
        r"anul(?:a|ar|alo|ala)|abort(?:a|ar|)|deja de|dejalo|"
        r"stop|cancel|abort|kill|halt|call it off)\b", n))


# Las frases son LITERALES de la sesión (transcripción de voz incluida: «pararme», «Cancélalo»).
@pytest.mark.parametrize("frase,puede_matar", [
    # EL INCIDENTE: el turno que mató al worker no pedía parar nada — autorizaba un borrado.
    ("Sí, te autorizo a borrar toda la agenda. No el widget, los datos de la.", False),
    # El turno de DOS antes, del que el modelo arrastró la intención (y que un barge-in había cancelado).
    ("Seguramente, por error has abierto dos widgets más. Con dos navegadores que aquí no se tenían "
     "que haber abierto para nada.", False),
    # …y las paradas que SÍ son paradas, también literales de la sesión (esas dos eran correctas).
    ("No, esto no era para ti, puedes pararme.", True),
    ("Cancélalo, no tenía, el mensaje no era para ti.", True),
    ("Cancélalo.", True),
    # Las trampas del castellano: «para» es preposición muchísimo más a menudo que verbo.
    ("para nada me gusta eso", False),
    ("esto es para ti", False),
    ("es para mañana", False),
    # Formas inequívocas.
    ("detén la tarea del navegador", True),
    ("párala ya", True),
    ("deja de buscar", True),
    ("anula el proceso", True),
    ("stop the browser task", True),
    # Y lo que NUNCA debe autorizar un hachazo.
    ("enséñame la agenda", False),
    ("vacía la agenda por completo, hoy y siempre", False),
    ("borra los cuatro proyectos", False),
])
def test_matar_exige_orden_explicita_de_parar(frase, puede_matar):
    assert _says_stop(frase) is puede_matar, frase


def test_el_detector_del_fuente_es_este():
    """El detector vive en el proveedor (función local, no importable). Este test compara el REGEX del fuente con
    el de aquí: si alguien lo relaja allí y no aquí, los casos de arriba dejarían de significar nada."""
    body = NUCLEO.read_text(encoding="utf-8")
    i = body.index("def _says_stop(")
    block = body[i:i + 1200]
    assert "par[ae]r(?:me|te|lo|la|los|las)?" in block, "cambió el regex del fuente: revisa los casos de este test"
    assert r"\bpara\b" not in block, "«para» suelto NO puede autorizar un hachazo (es preposición: «para nada»)"


def test_el_guarda_no_mata_a_quien_acaba_de_contestar():
    """Guarda de CÓDIGO sobre el invariante: contestar a un worker y matarlo en el mismo turno es incoherente por
    definición, y en la sesión pasó en el mismo milisegundo. Gana la respuesta, que no es destructiva."""
    body = NUCLEO.read_text(encoding="utf-8")
    i = body.index('elif name == "stop_worker":')
    block = body[i:i + 5200]     # hasta pasado `cancel_soon`, que es lo que hay que preceder
    assert 'worker_acted["v"] == "answer"' in block, "falta el guarda: se puede volver a matar al que contestas"
    assert "_says_stop(text)" in block, "falta el guarda de orden explícita"
    # Los dos tienen que estar ANTES de resolver y matar.
    assert block.index('worker_acted["v"] == "answer"') < block.index("cancel_soon"), \
        "el guarda tiene que actuar ANTES de cancel_soon; después ya está muerto"
    assert block.index("_says_stop(text)") < block.index("cancel_soon")


# ── GUARD 1: el kind lo decide el clasificador, no el backstop ─────────────────────────────────────────────────
def test_la_peticion_de_la_agenda_NO_es_una_tarea_web():
    """El clasificador real siempre supo la verdad: para esta frase dice `generic`. El `kind:"web"` era un hardcode
    del backstop, y de ahí salieron los dos navegadores y el rótulo «Buscando en la web…»."""
    from nucleo import dispatch

    peticion = ("Vale, pues hazme un favor, lees lo que hay en la agenda. Lo borras y luego compruebas "
                "que lo hayas borrado.")
    assert dispatch._classify_kind(peticion) == "generic"
    assert dispatch._default_label(dispatch._classify_kind(peticion)) == "Pensando…"


def test_looks_like_web_task_casa_esa_frase_y_por_eso_no_puede_decidir_el_kind():
    """Documenta POR QUÉ no sirve como router: sus raíces (`borr|lee|compr|…`) no exigen destino web ninguno, así
    que casa tres veces con una petición que no toca internet. Vale como DISPARADOR, no como clasificador."""
    from nucleo.flash import router

    peticion = ("Vale, pues hazme un favor, lees lo que hay en la agenda. Lo borras y luego compruebas "
                "que lo hayas borrado.")
    assert router.looks_like_web_task(peticion) is True
    # Y sigue haciendo su trabajo original: una gestión web de verdad.
    assert router.looks_like_web_task("entra en mi Gmail y bórrame los correos de ayer") is True


def test_el_backstop_ya_no_fija_el_kind_a_web():
    body = NUCLEO.read_text(encoding="utf-8")
    i = body.index("promesa→escalada FORZADA")
    block = body[max(0, i - 2000):i + 400]
    assert '_classify_kind(text)' in block, "el backstop tiene que preguntar al clasificador"
    assert '"kind": "web"' not in block, "vuelve a estar el hardcode que abrió dos navegadores"
