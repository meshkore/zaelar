"""V2-082 — CERTAINTY of the widget resolver (`runtime.identify`). Hard operator rules:
- only NAME/ALIAS open (the description no longer does); without a match → None (ask, do not open the closest match);
- the word "widget" scopes to USER widgets; a named SYSTEM object does not return a widget;
- voice tolerance applies only to alias tokens; open>recent tie-break (V2-078) retained.
Runs against the REAL migrated catalog (widgets/*/manifest.json with curated name+aliases)."""
from widgets import runtime


def _m(q, **kw):
    return runtime.identify(q, **kw)


# ── operator acceptance case: messaging vs chat ────────────────────────────────────────────────────────────
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
    assert _m("abre el chat")["match"] is None            # chat → system
    assert _m("abre los mensajes")["match"] == "mensajeria"  # messages → widget


# ── certainty: without a name/alias nothing opens (ask) ─────────────────────────────────────────────────────
def test_unknown_phrase_returns_none():
    for q in ("enséñame el conversor de divisas", "muéstrame no sé qué cosa rara", "ábreme el panel de la bolsa"):
        r = _m(q)
        assert r["match"] is None and r["system"] is None, f"{q!r} -> {r}"


def test_topical_overlap_does_not_open_a_widget():
    # Generic "clima"/"tiempo" are NO longer aliases for any widget → do not open based on topical similarity.
    r = _m("qué tiempo hace hoy")
    assert r["match"] is None


# ── system surfaces by name ──────────────────────────────────────────────────────────────────────────────────
def test_system_surfaces_resolve_by_name():
    assert _m("ábreme la configuración")["system"] == "config"
    assert _m("enséñame el debug")["system"] == "debug"
    assert _m("abre la bóveda")["system"] == "vault"


def test_widget_word_ignores_system_surfaces():
    # "el widget de configuración" must NOT fall through to the system surface (the user said widget).
    r = _m("abre el widget de configuración")
    assert r["system"] is None


# ── unique widget names/aliases ─────────────────────────────────────────────────────────────────────────────
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
    # A voice typo on a distinctive alias ('watsap'≈'whatsapp'/'wasap') still resolves.
    assert _m("abre el watsap")["match"] == "mensajeria"


def test_fuzzy_never_matches_an_inner_token_of_a_multiword_alias():
    # Measured 2026-09-03 (Soria reservation session): «…a través del restaurante o a través del tenedor…»
    # fuzzy-matched 'restante' — an INNER token of the timer's alias 'tiempo restante' — at 0.842, cleared the
    # certainty bar on that alone, and the close backstop then closed the timer and CANCELLED the reservation
    # escalation. An alias fragment is not a name: voice tolerance may only land on a complete alias.
    q = ("Yo solo quiero que hagas la reserva realmente. Termina, coge uno de esos restaurantes y ciérrame la "
         "reserva. Y si no puedes en uno, pues coge otro, pero hazlo ya, maldita sea, a través del restaurante "
         "o a través del tenedor o a través de donde quieras.")
    r = _m(q, open_ids=["results", "navegador"])
    assert r["match"] is None, f"an alias fragment resolved a widget: {r}"
    # …while NAMING the alias, whole and word-aligned, still resolves (the phrase path, untouched).
    assert _m("cuánto tiempo restante queda")["match"] == "timer"


# ── context fallback: operate on the only open widget (the one in front) ─────────────────────────────────────
def test_single_open_widget_is_context_fallback():
    r = _m("márcalo como hecho", open_ids=["agenda"])
    assert r["match"] == "agenda" and r["by_context"] is True


def test_multiple_open_no_context_fallback():
    r = _m("márcalo como hecho", open_ids=["agenda", "clock"])
    assert r["match"] is None and r["by_context"] is False
