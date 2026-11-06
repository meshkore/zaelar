"""A sign-in the model forgot to call is opened by the brief's verdict, never by his words (V2-857 phase 8, 2.1620).

Before: the close's login fallback (V2-022) read his sentence through `_LOGIN_INTENT_RE` («conéctame», «inicia sesión»,
«sign in»…) and, when the model had called nothing, opened the browser login. Whether a turn asks to sign in is a
reading of the request, which the brief's model reads in any language: it is now one declared question of the brief
(`login_only`, `nucleo/request/login.py`), paid every turn (K9). The SITE still comes from his words.

Disarm: `login.asked` returning False — the paid verdict opens nothing.
"""
from __future__ import annotations

import inspect
import threading

import pytest

from nucleo.flash import router_guards as rg
from nucleo.request import login
from nucleo.turn import brief as tb
from nucleo.turn import pipeline_close as PC

ORDERS = {"es": ("Conéctame a mi cuenta de Wallapop", "wallapop.com"),
          "en": ("Sign me in to my LinkedIn account", "linkedin.com")}
#: His words name a site and a sign-in verb but ask no sign-in: a question about capability.
QUESTIONS = {"es": "¿Puedes iniciar sesión en Wallapop si te lo pido?",
             "en": "Can you sign in to LinkedIn if I ask you to?"}


def _brief(choice=None, conf=0.0):
    ev = threading.Event()
    ev.set()
    res = {"_call_id": "t"}
    if choice:
        res[login.KEY] = {"choice": choice, "confidence": conf, "probs": {}}
    return {"event": ev, "turn_id": "t", "result": res}


class _Log:
    def warning(self, *_a, **_k):
        pass


def _close(text, brief):
    """The close's fallback with the turn's state; returns (sites a login was started for, events)."""
    started, events = [], []
    ok = PC.login_fallback(brief, text, lambda *a, **k: events.append((a, k)),
                           lambda site: started.append(site) or True, _Log())
    assert ok == bool(started)
    return started, events


def test_the_question_is_declared_and_asked_every_turn():
    assert login.KEY in tb.keys()
    qs = tb.build("hola")
    assert login.KEY in qs and set(qs[login.KEY]["criteria"]) == {login.LOGIN, login.OTHER}


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_sure_login_verdict_opens_his_site(lang):
    text, site = ORDERS[lang]
    started, events = _close(text, _brief(login.LOGIN, 0.9))
    assert started == [site], "the site comes from his words"
    (_a, kw), = [e for e in events if "login fallback" in e[0][1]]
    assert kw["extra"]["verdict"] == "login" and kw["extra"]["confidence"] == 0.9 and kw["extra"]["source"] == "verdict"


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("brief", [None, _brief(login.OTHER, 0.9), _brief(login.LOGIN, 0.3)],
                         ids=["no-brief", "other", "unsure"])
def test_his_words_alone_open_no_login(lang, brief):
    text, _site = ORDERS[lang]
    assert _close(text, brief) == ([], []), "the words opened a login the brief did not read"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_question_about_signing_in_opens_nothing(lang):
    assert _close(QUESTIONS[lang], _brief(login.OTHER, 0.95)) == ([], [])


@pytest.mark.parametrize("lang", ["es", "en"])
def test_disarmed_the_paid_verdict_opens_nothing(lang, monkeypatch):
    monkeypatch.setattr(login, "asked", lambda _b: False)
    text, _site = ORDERS[lang]
    assert _close(text, _brief(login.LOGIN, 0.9)) == ([], [])


def test_no_word_reader_decides_a_login():
    assert not hasattr(rg, "_LOGIN_INTENT_RE") and not hasattr(rg, "looks_like_login_request")
    src = inspect.getsource(PC)
    assert "looks_like_login_request" not in src and "login.asked(" in src
