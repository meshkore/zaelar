"""V2-082 — CERTEZA del resolver de widgets (`runtime.identify`). Reglas duras del operador:
- solo NOMBRE/ALIAS abren (la descripción ya no); sin match → None (se pregunta, no se abre el más parecido);
- la palabra "widget" acota a widgets de USUARIO; un objeto de SISTEMA nombrado no devuelve un widget;
- tolerancia de voz solo sobre tokens de alias; desempate open>recent (V2-078) conservado.
Corre contra el catálogo REAL migrado (widgets/*/manifest.json con name+aliases curados)."""
from widgets import runtime


def _m(q, **kw):
    return runtime.identify(q, **kw)


# ── caso de aceptación del operador: mensajería vs chat ──────────────────────────────────────────────────────
def test_widget_word_scopes_to_user_space():
    r = _m("abre el widget de mensajería")
    assert r["match"] == "mensajeria" and r["system"] is None


def test_messaging_aliases_resolve_to_mensajeria():
    for q in ("abre los mensajes", "enséñame el whatsapp", "abre twitter", "pon la x", "mira el telegram"):
        r = _m(q)
        assert r["match"] == "mensajeria", f"{q!r} -> {r['match']!r}"


def test_chat_is_a_system_surface_not_a_widget():
    r = _m("abre el chat")
    assert r["match"] is None and r["system"] == "chat"


def test_chat_and_mensajeria_never_collide():
    assert _m("abre el chat")["match"] is None            # chat → sistema
    assert _m("abre los mensajes")["match"] == "mensajeria"  # mensajes → widget


# ── certeza: sin nombre/alias no se abre nada (se pregunta) ───────────────────────────────────────────────────
def test_unknown_phrase_returns_none():
    for q in ("enséñame el conversor de divisas", "muéstrame no sé qué cosa rara", "ábreme el panel de la bolsa"):
        r = _m(q)
        assert r["match"] is None and r["system"] is None, f"{q!r} -> {r}"


def test_topical_overlap_does_not_open_a_widget():
    # "clima"/"tiempo" genéricos ya NO son alias de ningún widget → no abren por parecido temático.
    r = _m("qué tiempo hace hoy")
    assert r["match"] is None


# ── superficies de sistema por nombre ────────────────────────────────────────────────────────────────────────
def test_system_surfaces_resolve_by_name():
    assert _m("ábreme la configuración")["system"] == "config"
    assert _m("enséñame el debug")["system"] == "debug"
    assert _m("abre la bóveda")["system"] == "vault"


def test_widget_word_ignores_system_surfaces():
    # "el widget de configuración" NO debe caer en la superficie de sistema (el usuario dijo widget).
    r = _m("abre el widget de configuración")
    assert r["system"] is None


# ── nombres/alias de widgets, únicos ─────────────────────────────────────────────────────────────────────────
def test_distinct_widgets_by_alias():
    # 2026-08-31: the operator's personal widgets (pomodoro, meteo-*) left the shipped catalog — the
    # distinct-alias property is now exercised on shipped widgets only.
    assert _m("ponme el temporizador")["match"] == "timer"
    assert _m("cuenta atrás de cinco minutos")["match"] == "timer"
    assert _m("abre el navegador")["match"] == "navegador"
    assert _m("pon un vídeo")["match"] == "youtube"
    assert _m("abre la agenda")["match"] == "agenda"
    assert _m("pon música")["match"] == "musica"


def test_voice_typo_tolerance_on_alias():
    # errata de voz sobre un alias distintivo ('watsap'≈'whatsapp'/'wasap') sigue resolviendo.
    assert _m("abre el watsap")["match"] == "mensajeria"


# ── fallback de contexto: operar sobre el único widget abierto (lo que tiene delante) ────────────────────────
def test_single_open_widget_is_context_fallback():
    r = _m("márcalo como hecho", open_ids=["agenda"])
    assert r["match"] == "agenda" and r["by_context"] is True


def test_multiple_open_no_context_fallback():
    r = _m("márcalo como hecho", open_ids=["agenda", "clock"])
    assert r["match"] is None and r["by_context"] is False
