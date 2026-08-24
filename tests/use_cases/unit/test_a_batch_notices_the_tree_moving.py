"""Las guardas de árbol corren UNA vez, y una tanda dura horas (V2-282).

Medido el 2026-08-24: arranqué cuatro casos con el árbol limpio y el motor recién levantado —las dos guardas
dijeron que sí, con razón— y edité `nucleo/` mientras corrían. Del segundo caso en adelante se midió código
que ya no existía en disco. Y como el marcador se escribe POR ESCENARIO desde V2-... (nodo 10.8), esa basura
entra en el tablero compartido caso a caso, con su fecha de hoy y su aire de medida buena.

Es literalmente el daño que `dirty_tree_refusal` existe para impedir — su propia docstring dice «una ronda
medida a mitad de una edición no se puede comparar con ninguna otra» — y la guarda no podía verlo, porque
solo mira ANTES del primer caso. Misma forma que `stale_engine_refusal`, que se escribió al descubrir que un
árbol limpio no implica un proceso al día: aquí el que no implica nada es el árbol al ARRANCAR.

Se PARA la tanda en vez de saltar el caso: lo que cambió es el sujeto de la medida, así que los que quedan
tampoco valen. Y se dice con qué `--start-at` se retoman, como ya hace el tope de `--stop-after-failures`.
"""
import inspect

from tests.use_cases.e2e.agent import run as runmod


def test_la_comprobacion_esta_DENTRO_del_bucle_de_casos():
    """El hecho estructural: si vuelve a estar solo antes del bucle, no ve nada de lo que pasa durante."""
    src = inspect.getsource(runmod._run_batch)
    assert "for scenario in chosen:" in src
    i_bucle = src.find("for scenario in chosen:")
    i_check = src.find("_tree_at_start")
    assert 0 <= i_check < i_bucle, "el sello del árbol se toma antes del bucle, que es donde tiene sentido"
    assert src.find("config.code_stamp()", i_bucle) > i_bucle, (
        "nadie vuelve a mirar el árbol una vez arrancada la tanda")


def test_para_la_tanda_y_dice_como_retomarla():
    src = inspect.getsource(runmod._run_batch)
    assert "--start-at {scenario.id}" in src, (
        "sin decir por dónde se retoma, parar la tanda cuesta volver a correr lo ya medido")
    assert "el MOTOR se ha movido" in src


def test_NO_dispara_en_el_primer_caso():
    """El primer caso ya lo cubren las guardas de arranque; volver a preguntarle sería pararse antes de medir."""
    src = inspect.getsource(runmod._run_batch)
    assert "if results and not allow_dirty:" in src, (
        "la comprobación tiene que exigir que YA haya un caso corrido, o la tanda no arranca nunca")


def test_y_se_puede_apagar_con_allow_dirty():
    """`--allow-dirty` es «mido mi propio cambio a posta»: si no lo respetara, el agente que arregla no puede
    medir su trabajo en curso — que es justo para lo que existe ese flag."""
    assert "allow_dirty" in inspect.signature(runmod._run_batch).parameters
    src = inspect.getsource(runmod)
    # y los TRES caminos se lo pasan: uno que se lo olvide mide sucio en silencio, que es el fallo de partida
    assert src.count('allow_dirty=getattr(args, "allow_dirty", False),\n') >= 3


def test_un_arbol_SUCIO_a_mitad_tambien_cuenta_no_solo_otro_commit():
    """Editar sin commitear es el caso MEDIDO: los ficheros cambiaron y el sha seguía siendo el mismo."""
    src = inspect.getsource(runmod._run_batch)
    assert 'bool(_now.get("dirty"))' in src, (
        "solo comparar el sha deja pasar exactamente la forma que costó la tanda del 2026-08-24")
