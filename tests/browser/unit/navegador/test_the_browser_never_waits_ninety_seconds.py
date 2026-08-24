"""El navegador es conexión DIRECTA: lo que funciona, funciona en segundos (2026-08-24).

Norma del operador, con la traza delante: *«los navegadores no tienen que tener ningún tipo de espera… todo
es inmediato, y si falla algo, falla en los siguientes segundos… no tiene tiempos de espera de noventa
segundos bajo ningún concepto»*.

Lo que había, medido contra el plató vivo sobre un sitio real: `navigate` 4,2 s · `look` 4,2 s · `extract`
0,05 s — y un tope de **90 s**, veinte veces el coste. Eso no es margen de sobra: es que un cuelgue se lleva
un tercio de la ronda antes de que nadie se entere.

Y el cuelgue existía, con su causa exacta. `page.evaluate` **no tiene timeout en Playwright**: espera a un
contexto de ejecución, y una página NAVEGANDO —el Enter después de escribir en un buscador— no lo tiene
hasta que el documento nuevo está listo. Reproducido en `search-buy-guitar__es`:

    18:03:45  type «guitarra acustica»      ← se escribe
    18:03:48  screenshot                     ← la captura SALE, o sea que la acción funcionó
    18:05:15  ERROR: no ha contestado en 90s ← 90 s de una ronda de 250

Lo caro no es la espera: es lo que la espera CONVIERTE. La acción había funcionado y el worker recibía un
FALLO, así que la repetía. Ahora una lectura lenta devuelve lo que haya DICIENDO que la vista está a medias,
y la acción sigue contando como lo que fue.
"""
import inspect

from nucleo import nav_cli
from widgets.navegador import owner


def test_ninguna_espera_llega_a_noventa_segundos():
    """El número que la norma prohíbe, en los tres sitios que lo podían imponer."""
    assert nav_cli._ACT_TIMEOUT_S < 90, "el tope del puente era 90 s y es el que se lleva la ronda"
    assert owner._DOM_TIMEOUT_S < 90
    assert owner._NAV_TIMEOUT / 1000.0 < 90


def test_los_topes_son_de_SEGUNDOS_no_de_minutos():
    """Medido: una acción real cuesta ~4 s. Un tope se pone contra el coste real, no contra el miedo."""
    assert nav_cli._ACT_TIMEOUT_S <= 30
    assert owner._DOM_TIMEOUT_S <= 15
    assert owner._NAV_TIMEOUT / 1000.0 <= 20


def test_el_tope_del_PUENTE_es_mayor_que_el_de_dentro():
    """Si el puente cortara antes que las lecturas, el worker vería «no contestó» sobre acciones que estaban
    a punto de contestar — el mismo fallo con otro número."""
    assert nav_cli._ACT_TIMEOUT_S > owner._DOM_TIMEOUT_S
    assert nav_cli._ACT_TIMEOUT_S > owner._NAV_TIMEOUT / 1000.0


def test_las_TRES_lecturas_del_DOM_estan_acotadas():
    """Ninguna lo estaba: dos caían en el timeout por defecto del contexto y `evaluate` no tiene ninguno.
    Acotar dos de tres deja el cuelgue exactamente donde estaba."""
    # Se miran las LÍNEAS DE CÓDIGO. La primera versión de este caso casó con el comentario que NOMBRA las
    # tres lecturas y dio por acotada la que no lo estaba — un guarda de presencia certificando el fallo que
    # existe para evitar. Segunda vez hoy que la misma trampa pasa por delante.
    src = "\n".join(l for l in inspect.getsource(owner.TaskBrowser.snapshot_for_agent).splitlines()
                    if not l.strip().startswith("#"))
    for lectura in ("query_selector_all", "_bulk_metas", "page.title()"):
        i = src.find(lectura)
        assert i > 0, f"{lectura} ya no está en la mirada"
        assert "asyncio.wait_for" in src[max(0, i - 120):i], f"{lectura} sin acotar"
    assert src.count("_DOM_TIMEOUT_S") >= 3


def test_una_lectura_lenta_NO_convierte_una_accion_BUENA_en_un_fallo():
    """El corazón del defecto. El texto estaba escrito y el worker recibía «no ha contestado a type», así que
    lo repetía. La mirada devuelve lo que tenga y lo DICE; no lanza."""
    src = "\n".join(l for l in inspect.getsource(owner.TaskBrowser.snapshot_for_agent).splitlines()
                    if not l.strip().startswith("#"))
    assert '"partial"' in src and '"note"' in src
    assert "La acción SÍ se hizo" in src, (
        "el worker tiene que enterarse de que su acción funcionó, o la repite")
    assert "raise" not in src, "una mirada lenta no puede tumbar la acción que ya salió bien"


def test_la_vista_a_medias_se_NOMBRA_y_dice_como_salir():
    """Una vista incompleta entregada como si fuera la página entera es cómo un worker concluye «aquí no hay
    nada» sobre un listado lleno. Mismo contrato que el nodo 4.20."""
    src = inspect.getsource(owner.TaskBrowser.snapshot_for_agent)
    assert "seguía cargando" in src and "look" in src


def test_el_barrido_de_BANNERS_es_por_navegacion_no_por_mirada():
    """El peaje fijo que hacía imposible «abrir pestañas y valorar fichas una a una».

    `_dismiss_overlays` espera 2,5 s a que aparezca un CMP conocido y, si no, barre TODOS los frames × TODOS
    los selectores — y una web con iframes de anuncios tiene muchos frames. Se pagaba ENTERO en cada `look`.
    Medido contra el plató vivo sobre es.wallapop.com, misma página y sin banner:

        antes:  look 11,17 s · 11,23 s · 11,45 s   (tres miradas seguidas)
        ahora:  look  0,42 s ·  0,42 s ·  0,41 s   con los MISMOS 60 elementos

    No era el coste de aceptar cookies una vez: era un peaje por acción. Se barre al CAMBIAR de página, que
    es cuando puede haber banner nuevo; si aparece tarde en la misma URL sale en la captura y el worker
    puede clicarlo — se pierde un automatismo, no la salida.
    """
    src = "\n".join(l for l in inspect.getsource(owner.TaskBrowser.snapshot_for_agent).splitlines()
                    if not l.strip().startswith("#"))
    i = src.find("_dismiss_overlays")
    assert i > 0, "el barrido sigue haciendo falta al cambiar de página"
    assert "_overlays_url" in src[:i], (
        "el barrido tiene que ir detrás de una comprobación de URL, no correr en cada mirada")
    assert "self._overlays_url = " in src[i:], "y hay que recordar para qué página se hizo"


def test_el_barrido_NO_se_paga_DOS_VECES_por_navegacion():
    """`_goto` barre y, acto seguido, la mirada que viene detrás volvía a barrer — porque la URL acababa de
    cambiar, que es justo la condición que dispara el barrido. El mismo peaje, cobrado por la otra puerta.

    Medido contra el plató vivo (es.wallapop.com), antes y después de apuntar la URL barrida en `_goto`:

        navigate #1  36,6 s → 7,2 s
        navigate #2  24,7 s → 11,4 s
        look          15,5 s → 0,35 s
    """
    src = "\n".join(l for l in inspect.getsource(owner.TaskBrowser._goto).splitlines()
                    if not l.strip().startswith("#"))
    i = src.find("_dismiss_overlays")
    assert i > 0, "una navegación sí tiene que barrer: es cuando puede haber banner nuevo"
    assert "self._overlays_url" in src[i:], (
        "hay que apuntar para qué página se barrió, o la mirada siguiente lo repite entero")
