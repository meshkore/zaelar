#
# test_youtube.py — V2-057: the widget returns a VERIFIABLE result (sort by date + channel/date).
# Run: .venv/bin/pytest tests/browser/unit/youtube/test_youtube.py
#
import io
import urllib.request

from widgets.youtube import data as yt

# Realistic fragment of the videoRenderer from a YouTube search (the field order that we parse).
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
    assert r["published"] == "hace 2 días"      # ← the VERIFIABLE data (it is from 2 days ago, not a month ago)
    assert r["latest"] is True
    assert "sp=CAI%3D" in seen[0]               # «el último» → sort by upload date


def test_search_relevance_when_not_latest(monkeypatch):
    seen = []
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen(seen))
    r = yt._search_id("Despacito")
    assert r["latest"] is False
    assert "sp=CAI%3D" not in seen[0]           # without «último» → normal sort by relevance


def test_load_stores_verifiable_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen([]))
    from widgets import store
    # The global is called `DATA_DIR`; this used to say `_DATA_DIR` with `raising=False`, so monkeypatch CREATED a
    # new attribute and the isolation isolated nothing: this test had been writing to the operator's REAL store
    # (`widgets/_data/youtube/state.json`), overwriting the video loaded on each suite run. It was discovered on
    # 2026-08-13 because the global switch (V2-092) made the effect visible: the suite left the operator's widget
    # in «playing» with the agent stopped. Same approach as the rest of the suite (see test_rehydrate.py).
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    out = yt.apply_action("load", {"query": "el último de Cárpatos"})
    assert out["ok"] is True
    db = yt._load()
    assert db["channel"] == "José Luis Cárpatos"
    assert db["published"] == "hace 2 días"
    assert db["latest"] is True


# ── V2-590: captions are a DECLARED capability, not a narrated refusal ───────────────────────────────────
# Measured live (session 0e3a42d6, 2026-09-05): «Quita los subtítulos» → «solo puedes quitarlos tú desde el
# reproductor, botón CC». The widget had no captions action, and an undeclared capability is one the model
# narrates (V2-540). The server stores the choice; the player applies it via the IFrame API modules.

def test_captions_on_off_store_the_choice_and_bump_the_command(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    r = yt.apply_action("captions_on", {})
    assert r["ok"] and r["cmd"] == "captions_on"
    assert yt._load()["captions"] is True
    seq1 = yt._load()["cmd_seq"]
    r = yt.apply_action("captions_off", {})
    assert r["ok"] and yt._load()["captions"] is False
    assert yt._load()["cmd_seq"] == seq1 + 1, "cmd_seq must advance or the player never applies the toggle"


def test_captions_survive_a_new_load_and_never_make_it_play():
    """Source-level, both halves of the V2-590 design: the choice is re-asserted in applyState (or it
    silently drops on the next load), the live toggle goes through applyCmd, BOTH module names are sent,
    and captions are NOT in runtime.produce — subtitles never count as producing."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    src = (root / "widgets/youtube/widget.js").read_text(encoding="utf-8")
    assert "applyCaptions" in src and '"loadModule", ["captions"]' in src and '"loadModule", ["cc"]' in src
    body_state = src.split("function applyState", 1)[1][:700]
    assert "applyCaptions" in body_state, "captions must be re-asserted on every load (applyState)"
    body_cmd = src.split("function applyCmd", 1)[1][:1800]
    assert 'c === "captions_on"' in body_cmd
    assert "cc_load_policy" in src, "the load-time param covers a module sent before the player is ready"
    man = json.loads((root / "widgets/youtube/manifest.json").read_text(encoding="utf-8"))
    assert "captions_on" in man["actions"] and "captions_off" in man["actions"]
    assert "captions_on" not in (man.get("runtime") or {}).get("produce", []), \
        "subtitles do not produce: the global stop must not chase them"
