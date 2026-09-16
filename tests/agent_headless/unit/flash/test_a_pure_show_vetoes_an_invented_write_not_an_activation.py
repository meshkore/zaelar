"""V2-713 R1 · Un «abre X» puede vetar una ESCRITURA inventada, nunca una activación.

## El incidente que creó el guarda, y el que lo delató

`show_request_blocks_data_action` nació de un caso real: «abre la agenda» y el modelo colaba un `add_meeting`
con título y fecha que el operador no había dicho. Eso hay que pararlo y se sigue parando.

Lo que no funcionaba era CÓMO lo reconocía: preguntando «¿es una acción de vista?». Medido el 2026-09-16 —
«abre música y sigue con la pista» se lee como show puro (no lleva verbo de cambio, y «sigue» está
deliberadamente FUERA de `_ACTIVATE_VERB_RE` porque el stem choca con «el siguiente»), así que un `resume`
bien elegido se descartaba y el operador se quedaba con una tarjeta que no hacía nada.

Ampliar la lista de verbos es justo el movimiento que V2-712 acaba de retirar del consentimiento: crece un
incidente cada vez y la frase siguiente se escribe de otra forma. El propio auditor lo dice: «no seguir
ampliando sinónimos».

## Lo que se afirma aquí

Que la pregunta se ha movido del VERBO a la LLAMADA — ¿trae esta acción contenido que la frase no menciona? —,
que una acción sin datos pero CON consecuencia (`clear_all`) sigue bloqueada, que los dos canales pasan el
payload, y que cada veto queda contado en sombra para poder retirar el guarda con un número en vez de con una
opinión.
"""
from __future__ import annotations

import pathlib

import pytest

from nucleo.flash import show_guard as G

ENGINE = pathlib.Path(__file__).resolve().parents[4]


# ── 1 · una activación pasa; una escritura inventada no ─────────────────────────────────────────────────

@pytest.mark.parametrize("frase,wid,act,payload", [
    ("abre musica y sigue con la pista", "musica", "resume", {}),
    ("abre musica y reanuda la pista", "musica", "resume", {}),
    ("abre el youtube", "youtube", "play", {}),
    ("muestrame la musica", "musica", "next", {}),
    ("abre musica y continua donde lo dejaste", "musica", "resume", {}),
])
def test_una_activacion_sin_datos_pasa_diga_lo_que_diga_la_frase(frase, wid, act, payload):
    """El caso del auditor y sus vecinos. Ninguno depende de qué verbo se usó: dependen de que la acción no
    lleva nada que inventar."""
    assert G.show_request_blocks_data_action(frase, wid, act, payload) is False


def test_la_alucinacion_original_sigue_bloqueada():
    """«abre la agenda» con una cita que el operador no nombró. Es el motivo del guarda y no se ha movido."""
    assert G.show_request_blocks_data_action(
        "abre la agenda", "agenda", "add_meeting", {"title": "Dentista", "date": "2026-10-02"}) is True


def test_una_orden_que_SI_lleva_verbo_de_cambio_ni_siquiera_llega_aqui():
    """«abre la agenda y apunta dentista» no es un show puro — `_CHANGE_VERB_RE` lo ve —, así que el guarda
    no opina. Merece un caso propio para que nadie lo confunda con una excepción de este mecanismo."""
    assert G.is_pure_show_request("abre la agenda y apunta dentista") is False
    assert G.show_request_blocks_data_action(
        "abre la agenda y apunta dentista", "agenda", "add_meeting", {"title": "Dentista"}) is False


def test_abrir_un_elemento_de_dentro_sigue_funcionando():
    """V2-545: «ábreme el mensaje de Francisco» es una acción de vista y además nombra su objeto."""
    assert G.show_request_blocks_data_action(
        "abreme el mensaje de Francisco", "mensajeria", "open", {"name": "Francisco"}) is False


# ── 2 · «sin datos» NO es «sin consecuencia» ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("wid,act,payload", [
    ("agenda", "clear_all", {}),                      # vacía la agenda entera, y no lleva payload
    ("musica", "disconnect", {}),
    ("youtube", "clear_history", {}),
    ("contactos", "remove_contact", {"contactId": "c1"}),
    ("navegador", "open", {}),                        # carga una URL: no «quita» nada y actúa igual
    ("imagenes", "clear", {}),                        # vacía el visor
    ("agenda", "add_meeting", {}),                    # la alucinación original, sin datos que delaten
])
def test_todo_lo_que_no_declara_activacion_sigue_bloqueado(wid, act, payload):
    """El contrapeso, y la mitad que no se negocia: el defecto por defecto es BLOQUEAR. Un widget que no
    declara nada se comporta hoy exactamente como ayer — la mejora solo alcanza a lo que dice lo que es."""
    assert G.show_request_blocks_data_action("muestrame la agenda", wid, act, payload) is True


def test_lo_que_puede_correr_un_show_puro_esta_DECLARADO_no_adivinado():
    """⚠️ Dos intentos que NO sobrevivieron al contacto, los dos cazados por tests antes de commitear:
    «sin payload = inofensivo» (`agenda:clear_all` tampoco lleva payload y vacía la agenda) y «sin payload y
    no destructiva = inofensivo» (`navegador:open` carga una URL, `imagenes:clear` vacía el visor, y
    `contract.is_destructive` dice que no a los dos porque responde «¿quita algo?», otra pregunta).

    Una heurística en la frontera de un raíl sigue encontrando el caso que no pensó. Una declaración no."""
    src = pathlib.Path(G.__file__).read_text(encoding="utf-8")
    assert 'spec.get("activation") is True' in src
    # ⚠️ Solo el CÓDIGO EJECUTABLE, por AST. El módulo nombra a propósito los dos intentos retirados (el
    # método de este repo es que el patrón lleve su incidente), y un assert sobre el texto entero leería esa
    # prosa como si el intento siguiera vivo — primero en un comentario y después, cuando filtré los
    # comentarios, en el docstring. Es el defecto que el trinquete de espejos ya documentó: la prosa SOBRE el
    # patrón cuenta como el patrón. Quitar docstrings y comentarios de verdad es lo que no tiene escapatoria.
    import ast
    arbol = ast.parse(src)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and ast.get_docstring(nodo):
            nodo.body = nodo.body[1:]
    codigo = ast.unparse(arbol)
    assert "is_destructive" not in codigo, "la heurística de destructividad respondía otra pregunta"
    assert "_payload_is_invented" not in codigo, "la heurística del payload también se retiró"


# ── 3 · ningún verbo nuevo ──────────────────────────────────────────────────────────────────────────────

def test_la_lista_de_verbos_de_activacion_NO_ha_crecido():
    """El arreglo que NO se hizo, afirmado: “sigue”/“continúa” no entran en la tabla. Si alguien los añade,
    este test lo dice — y la razón es que la tabla vuelve a crecer un incidente cada vez."""
    src = pathlib.Path(G.__file__).read_text(encoding="utf-8")
    fila = src[src.index("_ACTIVATE_VERB_RE = "):].split("\n")[0]
    for verbo in ("sigu", "continu", "sigue", "retoma", "resume\\b"):
        assert verbo not in fila, f"«{verbo}» entró en la tabla de verbos: el arreglo era no tocarla"


def test_un_widget_que_nadie_ha_escrito_hereda_el_comportamiento():
    """La tercera pregunta de la doctrina. Una acción de un widget desconocido no revienta y no inventa."""
    assert G.show_request_blocks_data_action("abre el chisme", "no_existe", "play", {}) is False


# ── 4 · los dos canales, y la cuenta para poder retirarlo ───────────────────────────────────────────────

def test_los_dos_canales_pasan_el_payload():
    """Si solo lo pasa uno, el canal de texto vuelve a reportar una decisión que el producto no toma — que es
    exactamente el falso verde que este guarda ya provocó una vez (V2-545)."""
    voz = (ENGINE / "voice" / "engine" / "llm" / "providers" / "nucleo.py").read_text(encoding="utf-8")
    txt = (ENGINE / "nucleo" / "flash" / "probe.py").read_text(encoding="utf-8")
    assert "show_request_blocks_data_action(text, wid, action_name, payload)" in voz
    assert "show_request_blocks_data_action(text, _wid, _act, _pl)" in txt


def test_cada_veto_queda_contado_en_sombra_con_su_regla():
    """Un guarda que veta la elección del modelo no se puede juzgar leyendo el código: hace falta saber
    cuántas veces tiró algo que estaba bien. V2-711 dejó el lector; esto le da las filas."""
    visto = []

    import voice.observer as obs
    real = obs.emit
    obs.emit = lambda cat, kind, **kw: visto.append((kind, kw.get("extra", {}).get("rule")))
    try:
        G.show_request_blocks_data_action("muestrame la agenda", "agenda", "clear_all", {})
        G.show_request_blocks_data_action("abre la agenda", "agenda", "add_meeting", {"title": "Dentista"})
        G.show_request_blocks_data_action("abre musica y sigue", "musica", "resume", {})
    finally:
        obs.emit = real
    assert [k for k, _ in visto] == ["gate_shadow", "gate_shadow"], "un veto sin fila es un coste invisible"
    assert {r for _, r in visto} == {"not-declared-activation"}


def test_contar_un_veto_nunca_puede_tumbar_un_turno():
    import voice.observer as obs
    real = obs.emit
    obs.emit = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bus caído"))
    try:
        assert G.show_request_blocks_data_action("muestrame la agenda", "agenda", "clear_all", {}) is True
    finally:
        obs.emit = real


# ── 5 · el nivel de las acciones de activación está DECLARADO (V2-712) ──────────────────────────────────

@pytest.mark.parametrize("wid,act", [("musica", "resume"), ("musica", "play"), ("musica", "next"),
                                     ("youtube", "play"), ("youtube", "play_item")])
def test_una_activacion_se_DECLARA_y_declara_tambien_su_nivel(wid, act):
    import json
    spec = json.loads((ENGINE / "widgets" / wid / "manifest.json").read_text(encoding="utf-8"))["actions"][act]
    assert spec.get("activation") is True, "«cambia lo que el widget HACE» lo dice el manifiesto, no un verbo"
    assert spec.get("sensitivity") == "routine", "y el nivel también se declara (V2-712)"
