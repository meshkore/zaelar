"""Connecting a video account (V2-603): one step, a redirect that follows the operator, and a failure that
is never silent.

Every case here comes from ONE measured session on the operator's own engine (2026-09-06, `e1acdcca`), where
he tried to connect YouTube for nine minutes and the agent said «Hecho.», «La autentificación quedó
completada» and «Te conecto YouTube ahora mismo» while the connector had no OAuth app registered at all and
`connect_account` was returning `ok: False`.

The three faults, each pinned below:
  · the brain never received the connection STATE, so it narrated an outcome instead of reading one;
  · a failed data-op's result was DISCARDED, so the false claim was never corrected;
  · the redirect was hardcoded to loopback, so the flow could not complete anywhere but a same-machine desktop.
"""
import asyncio

import pytest

from connectors.video import oauth, providers, service


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """Isolate the token store AND the credential store: `client_id` reads the real one, and a developer with
    their own YouTube app registered would otherwise flip every `builtin`/`configured` assertion here."""
    monkeypatch.setattr(oauth, "STORE", tmp_path / "video_oauth.json")
    monkeypatch.setattr(oauth, "_cred", lambda _name: "")
    return tmp_path


def _with_builtin(monkeypatch, client_id="zaelar-shipped.apps.googleusercontent.com"):
    """Give the registry a shipped client, the way a released engine will carry one."""
    p = providers.get("youtube")
    monkeypatch.setitem(providers.PROVIDERS, "youtube",
                        providers.VideoProvider(**{**p.__dict__, "builtin_client_id": client_id}))


# ── the shipped app: one step instead of a Google Cloud project ───────────────────────────────────────────
def test_a_shipped_client_makes_the_connector_configured_without_the_operator_registering_anything(
        sandbox, monkeypatch):
    """The whole point of the decision: with a client shipped, «create an OAuth app» stops being step one."""
    assert oauth.configured("youtube") is False          # nothing shipped, nothing registered → dormant
    _with_builtin(monkeypatch)
    assert oauth.configured("youtube") is True
    assert oauth.uses_builtin_app("youtube") is True


def test_the_operators_own_client_always_wins_over_the_shipped_one(sandbox, monkeypatch):
    """The fair-code half: a self-hoster who registers their own app keeps their own quota and consent screen,
    and must not be silently switched onto ours."""
    _with_builtin(monkeypatch)
    monkeypatch.setattr(oauth, "_cred",
                        lambda name: "mine.apps.googleusercontent.com" if name.endswith("CLIENT_ID") else "")
    assert oauth.client_id("youtube") == "mine.apps.googleusercontent.com"
    assert oauth.uses_builtin_app("youtube") is False     # → the card offers the bring-your-own-app road


def test_the_card_is_told_which_app_it_is_offering(sandbox, monkeypatch):
    """`builtin_app` is what decides the wizard's SHAPE (one consent step vs the whole BYO road), so it has to
    reach the frontend at all."""
    _with_builtin(monkeypatch)
    row = next(r for r in oauth.status() if r["id"] == "youtube")
    assert row["builtin_app"] is True and row["app_configured"] is True


# ── the redirect follows the operator ─────────────────────────────────────────────────────────────────────
def test_the_redirect_follows_the_origin_the_operator_is_actually_on(sandbox):
    """Hardcoded loopback is only right for a desktop opened on the same machine as the engine. On a managed
    deployment `127.0.0.1:43917` is the OPERATOR's own computer, which has never heard of the pending state,
    so the consent could not complete and the connector looked broken."""
    assert oauth.redirect_uri("https://my.zaelar.com") == "https://my.zaelar.com/api/video/callback"
    assert oauth.redirect_uri("https://my.zaelar.com/") == "https://my.zaelar.com/api/video/callback"


@pytest.mark.parametrize("hostile", [
    "https://evil.com/path?a=b",          # a path — not an origin
    "https://a.com\r\nX-Injected: y",     # header injection into a URL we hand to the provider
    "javascript:alert(1)",
    "not-a-url",
    "",
])
def test_a_hostile_origin_falls_back_to_loopback_instead_of_being_trusted(sandbox, hostile):
    """The origin arrives from a request header, so it is untrusted input that ends up inside a URL sent to
    Google. Anything that is not exactly scheme://host[:port] is refused."""
    assert oauth.redirect_uri(hostile) == oauth._DEFAULT_REDIRECT


def test_the_exchange_reuses_the_REDIRECT_THAT_WAS_AUTHORIZED(sandbox, monkeypatch):
    """OAuth requires the exchange to send back the exact redirect the authorization used. Now that it is
    derived per request, recomputing it at callback time could differ — and the provider would reject the
    exchange with a mismatch no one could read. So it rides under the state."""
    _with_builtin(monkeypatch)
    res = oauth.authorize_url("youtube", origin="https://my.zaelar.com")
    assert res["ok"]
    state = res["url"].split("state=")[1].split("&")[0]
    pend = oauth._load()["pending"][state]
    assert pend["redirect"] == "https://my.zaelar.com/api/video/callback"
    assert pend["verifier"]                                    # PKCE still stashed alongside it


# ── the brain is told the STATE, not just the verbs ───────────────────────────────────────────────────────
def test_the_brain_state_says_the_account_is_not_connected_and_why(sandbox):
    """The measured hallucination: the brain had `connect_account` in its action list and no fact to check it
    against, so «conéctame a YouTube» produced «Hecho.»."""
    txt = service.brain_state()
    assert "YouTube" in txt
    assert "SIN conectar" in txt and "SIN app OAuth" in txt


def test_the_brain_state_forbids_claiming_a_connection_and_names_the_google_login_trap(sandbox):
    """During the session a worker drove the browser to `accounts.google.com/signin` and the agent reported it
    as success — «la sesión se guardó en el perfil del navegador», true about that browser profile and
    useless for the connector. A statement that is true about the wrong mechanism is the worst failure shape,
    so the block names it explicitly."""
    txt = service.brain_state()
    assert "NUNCA digas que has conectado" in txt
    assert "entrar en" in txt.lower() and "google no conecta" in txt.lower()


def test_a_connected_account_reports_itself_as_connected(sandbox, monkeypatch):
    """The counterweight: this block must not just always say «not connected», or it would be a constant."""
    _with_builtin(monkeypatch)
    oauth._store_tokens("youtube", "readonly", {"access_token": "a", "refresh_token": "r", "expires_in": 3600})
    assert "CONECTADO" in service.brain_state()


# ── a failed data-op reaches the operator ─────────────────────────────────────────────────────────────────
@pytest.fixture
def rails(monkeypatch):
    """Capture the two rails a failure travels on, by patching the real modules' attributes.

    NOT by injecting into `sys.modules`: `report_failure` does `from voice import brain_notes`, which reads
    the PACKAGE attribute, so a fake registered under the module name is ignored the moment something else has
    already imported the real one — a first version of these tests passed alone and failed in the full run
    for exactly that reason."""
    import voice.brain_notes as bn
    import voice.proactive as pro
    from nucleo.flash import data_ops

    data_ops._RECENT_FAILURES.clear()
    pushed, spoken = [], []
    monkeypatch.setattr(bn, "push", lambda note: pushed.append(note))

    async def _notify(title, text, **kw):
        spoken.append(text)

    monkeypatch.setattr(pro, "notify", _notify)
    return pushed, spoken


def test_a_failed_data_op_is_announced_instead_of_vanishing(rails):
    """THE defect. `dispatch_tag` discarded `brain_action`'s result, so the widget's exact reason existed
    in-process and reached nobody — and twelve seconds later the agent claimed the opposite."""
    from nucleo.flash import data_ops

    pushed, spoken = rails
    told = asyncio.run(data_ops.report_failure(
        "youtube", "connect_account", {"ok": False, "error": "sin app OAuth registrada para YouTube"}))

    assert told is True
    assert pushed and "sin app OAuth registrada para YouTube" in pushed[0]
    # The note must FORBID the claim, not merely report the failure: the model had been saying «Hecho.»
    assert "NO se ejecutó" in pushed[0] and "NO digas que está" in pushed[0]
    assert spoken and "sin app OAuth" in spoken[0]


def test_a_SUCCESSFUL_data_op_says_nothing(rails):
    """The counterweight that keeps the above from being satisfied by announcing everything."""
    from nucleo.flash import data_ops

    pushed, _ = rails
    assert asyncio.run(data_ops.report_failure("youtube", "suggest", {"ok": True, "n": 12})) is False
    assert not pushed


def test_the_same_failure_is_not_announced_twice_in_a_row(rails):
    """A card that retries on a timer must not turn one broken connector into a monologue."""
    from nucleo.flash import data_ops

    res = {"ok": False, "error": "la sesión con YouTube caducó"}
    first = asyncio.run(data_ops.report_failure("youtube", "suggest", dict(res)))
    second = asyncio.run(data_ops.report_failure("youtube", "suggest", dict(res)))
    assert first is True and second is False


def test_dispatch_tag_returns_the_REAL_widgets_answer_not_just_its_own_guard_clauses(sandbox):
    """The seam itself: without a return value there is nothing for `report_failure` to look at.

    Driven through the REAL path — a genuine widget and a genuine action that genuinely fails — because a
    first version of this test only ever hit the `bad dispatch envelope` guard, and stayed GREEN with the fix
    reverted. `connect_account` with no client_id is read-only: it returns before anything is written."""
    import widgets

    out = asyncio.run(widgets.dispatch_tag(
        "widget.data", {"id": "youtube", "data": {"action": "connect_account", "payload": {}}}))
    assert isinstance(out, dict), out
    assert out.get("ok") is False
    # the WIDGET's own words must survive the trip, or the correction has nothing to say
    assert "OAuth" in str(out.get("error") or "")


# ── the mute backstop stops blaming the operator ──────────────────────────────────────────────────────────
def test_the_mute_backstop_rotates_instead_of_repeating_one_line():
    """Measured: «Perdona, ¿me lo repites?» four times in ninety seconds, answered with «Pero ¿por qué te lo
    tengo que repetir?». `holding_line` got this treatment in V2-189; this branch never did."""
    from nucleo.flash import reminder_guards
    from voice.engine.core import langs

    lines = langs.current_language().mute_lines
    assert len(lines) >= 3
    window, said = [], []
    for _ in range(3):
        s = reminder_guards.mute_line(window)
        said.append(s)
        window.append({"role": "assistant", "content": s})
    assert len(set(said)) == 3, f"repeated itself: {said}"


def test_after_every_variant_the_engine_admits_it_is_stuck_instead_of_apologising_again():
    from nucleo.flash import reminder_guards
    from voice.engine.core import langs

    lang = langs.current_language()
    window = [{"role": "assistant", "content": c} for c in lang.mute_lines]
    assert reminder_guards.mute_line(window) == lang.mute_stuck


def test_no_mute_line_asks_the_operator_to_repeat_himself_as_if_he_were_unclear():
    """The wording fault, separate from the repetition one: the model returned empty, which is our fault, and
    the old line put it on his speech."""
    from voice.engine.core import langs

    for code in ("es", "en"):
        lang = langs.LANGUAGES[code]
        assert lang.mute_lines, code
        # every variant must own the failure — it names US, not what he said
        assert any(m in " ".join(lang.mute_lines).lower()
                   for m in ("se me ha ido", "no te he seguido", "por dentro",
                             "i lost that", "didn't follow", "on my end")), code


# ── routing ───────────────────────────────────────────────────────────────────────────────────────────────
def test_connect_vocabulary_retrieves_the_media_family_not_only_the_cluster_one():
    """«conecta» was a seed of `cluster` (MeshKore peers) and of nothing else, so the most natural Spanish
    word for linking an account retrieved peer-to-peer tools. Measured on «Vamos, conecta.»:
    named=['cluster'], omitted=['media']."""
    from nucleo.flash import tool_selection

    for phrase in ("Vamos, conecta.", "conéctame la cuenta de YouTube", "connect my youtube account"):
        fams = {f for f, hints in tool_selection._HINTS.items()
                if tool_selection._words(phrase) & set(hints)}
        assert "media" in fams, f"{phrase!r} → {fams}"
    # and the cluster family keeps its own seed — families are not exclusive
    assert "conecta" in tool_selection._HINTS["cluster"]


def test_the_widgets_routing_line_still_mentions_connecting_after_the_brief_trims_it():
    """V2-547's budget: the routing line is cut at a sentence boundary, so a `whenToUse` that mentions
    connecting only in its LAST sentence loses exactly the half that routes this errand. Asserted through the
    real brief, not against the manifest."""
    from widgets import brief

    line = next(ln for ln in brief.for_prompt().splitlines() if ln.strip().startswith("- youtube"))
    routing = line.split(" · datos:")[0].lower()
    assert "conectar" in routing or "vincular" in routing, routing


# ── the canned show ack is not an answer either ───────────────────────────────────────────────────────────
def test_the_show_ack_counts_as_a_bare_ack_when_it_answers_a_QUESTION():
    """Found live, after the rest of this initiative was already committed and running (2026-09-06):

        OPERATOR  Acabo de iniciar sesión en Google, ¿ya has cogido los datos de mi cuenta de YouTube?
        ZAELAR    Aquí lo tienes.

    over a connector with no OAuth app at all. `show_ack` is OUR canned line for a `show_widget` turn the
    model left mute, and it is content-free in exactly the way `data_ack` is — but only `data_ack`'s wordings
    were seeded into this guard, so it sailed past. It is NON-DETERMINISTIC, which is why it survived: the
    same question answers correctly whenever the model happens to speak."""
    from nucleo.flash import answer_guards
    from voice.engine.core import langs

    q = "Acabo de iniciar sesión en Google, ¿ya has cogido los datos de mi cuenta de YouTube?"
    for code in ("es", "en"):
        ack = langs.LANGUAGES[code].show_ack
        assert answer_guards.a_bare_ack_answers_a_question(q, ack) is True, (code, ack)


def test_the_show_ack_stays_legitimate_when_the_operator_ASKED_for_the_card():
    """The counterweight: «ábreme YouTube» → «Aquí lo tienes.» is a correct, complete answer. The guard keys
    on an information QUESTION with no action verb, so this must stay out of its reach."""
    from nucleo.flash import answer_guards
    from voice.engine.core import langs

    ack = langs.LANGUAGES["es"].show_ack
    assert answer_guards.a_bare_ack_answers_a_question("Ábreme la tarjeta de YouTube", ack) is False
    # and an ack that actually carries the answer is not bare
    assert answer_guards.a_bare_ack_answers_a_question(
        "¿ya está conectada mi cuenta?", "Aquí lo tienes: sigue sin conectar.") is False
