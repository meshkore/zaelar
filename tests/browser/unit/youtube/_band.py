"""The six-row band of `find-videos-on-a-topic-no-ai-slop` (2026-10-14), seeded straight into the card's store."""
from __future__ import annotations

import urllib.request

import pytest

from widgets import store
from widgets.youtube import data as yt

ES = [("🪓🌳 Así PODA un profesional del OLIVO en JAÉN (sin guión).", "🫒 Olivares de Andalucía"),
      ("La Poda del Olivo Herencia C  Real 2021", "Evgeniy Vorobyov"),
      ("Podar los olivos con José Manuel", "El campo es nuestro Aragón TV"),
      ("Poda olivo 6 - 2026", "Olivos de la manchuela"),
      ("Curso Completo para PODAR CORRECTAMENTE un OLIVO!! Fácil y Paso a Paso | La Huerta de Ivan", "La Huerta de Iván"),
      ("Introducción a la poda el olivo", "Agro canal")]
EN = [("Tutorial how to prune an Olive Tree 🌿💚 #garden #pruning #trees", "The Frenchie Gardener"),
      ("Cómo podar un olivo #jardín #jardinería", "Michael Griffiths"),
      ("Poda profesional de olivos | Ejemplo práctico de gestión de olivares", "Escuela Superior del Aceite"),
      ("Cómo podar un olivo: la guía profesional completa", "ColtivoBio"),
      ("How to Prune an Olive Tree", "The Palm Centre"),
      ("Olive Tree Pruning (HOW TO GROW OLIVES), Olive tree Care UK", "Mark's House and Garden UK")]


def vid(i: int) -> str:
    return f"VIDEO{i:06d}"


def seed(rows, queue=()) -> None:
    db = yt._load()
    db["search_results"] = [{"videoId": vid(i), "title": t, "channel": c, "published": "", "source": "youtube",
                             "url": "https://www.youtube.com/watch?v=" + vid(i)} for i, (t, c) in enumerate(rows, 1)]
    db["search_query"] = "poda de olivo"
    db["list"] = [{**db["search_results"][i - 1], "added_at": 0, "added_seq": n} for n, i in enumerate(queue, 1)]
    store.save(yt.WID, db)


@pytest.fixture
def card(monkeypatch, tmp_path):
    """An isolated store; any network call is a failure — a row he can SEE is never searched for again."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    def _no_network(*a, **k):
        raise AssertionError("the card went to the network for a row already on screen")
    monkeypatch.setattr(urllib.request, "urlopen", _no_network)
    return yt
