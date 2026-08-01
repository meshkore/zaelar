#
# test_youtube.py — V2-057: el widget devuelve un resultado VERIFICABLE (orden por fecha + canal/fecha).
# Ejecutar: .venv/bin/pytest widgets/youtube/test_youtube.py
#
import io
import urllib.request

from widgets.youtube import data as yt

# Fragmento realista del videoRenderer de una búsqueda de YouTube (el orden de campos que parseamos).
_HTML = (
    '{"videoRenderer":{"videoId":"6V2lKeUE8YA",'
    '"title":{"runs":[{"text":"Las 4 claves de la semana"}]},'
    '"longBylineText":{"runs":[{"text":"Jos\\u00e9 Luis C\\u00e1rpatos"}]},'
    '"publishedTimeText":{"simpleText":"hace 2 d\\u00edas"}}}'
)


def _fake_urlopen(seen):
    def _u(req, timeout=6):
        seen.append(req.full_url)
        return io.BytesIO(_HTML.encode("utf-8"))
    return _u


def test_search_extracts_channel_and_published(monkeypatch):
    seen = []
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen(seen))
    r = yt._search_id("el último vídeo de José Luis Cárpatos")
    assert r["videoId"] == "6V2lKeUE8YA"
    assert r["channel"] == "José Luis Cárpatos"
    assert r["published"] == "hace 2 días"      # ← el dato VERIFICABLE (es de hace 2 días, no de hace un mes)
    assert r["latest"] is True
    assert "sp=CAI%3D" in seen[0]               # «el último» → orden por fecha de subida


def test_search_relevance_when_not_latest(monkeypatch):
    seen = []
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen(seen))
    r = yt._search_id("Despacito")
    assert r["latest"] is False
    assert "sp=CAI%3D" not in seen[0]           # sin «último» → orden normal por relevancia


def test_load_stores_verifiable_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen([]))
    from widgets import store
    monkeypatch.setattr(store, "_DATA_DIR", tmp_path, raising=False)
    out = yt.apply_action("load", {"query": "el último de Cárpatos"})
    assert out["ok"] is True
    db = yt._load()
    assert db["channel"] == "José Luis Cárpatos"
    assert db["published"] == "hace 2 días"
    assert db["latest"] is True
