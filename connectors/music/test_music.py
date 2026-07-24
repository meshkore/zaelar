"""Tests del seam agnóstico de música (V2-041): registro + fachada."""
from connectors import music
from connectors.music import registry
from connectors.music.base import MusicProvider, MusicResult, NowPlaying, Track


class _Fake(MusicProvider):
    name = "fake"

    def __init__(self, connected=True):
        self._c = connected
        self.calls = []

    def connected(self):
        return self._c

    def search(self, query, limit=5):
        return [Track(uri="fake:1", title=query, artist="X")]

    def play(self, query="", uri=""):
        self.calls.append(("play", query, uri))
        return MusicResult(ok=True, provider=self.name, action="play",
                           track=Track(uri="fake:1", title=query or "resume"), message="ok")

    def pause(self):
        self.calls.append(("pause",))
        return MusicResult(ok=True, provider=self.name, action="pause", message="pausado")

    def resume(self):
        return MusicResult(ok=True, provider=self.name, action="resume", message="sigo")

    def next(self):
        return MusicResult(ok=True, provider=self.name, action="next", message="siguiente")

    def previous(self):
        return MusicResult(ok=True, provider=self.name, action="previous", message="anterior")

    def set_volume(self, percent):
        self.calls.append(("volume", percent))
        return MusicResult(ok=True, provider=self.name, action="volume", message=f"vol {percent}")

    def now_playing(self):
        return NowPlaying(playing=True, volume=50, provider=self.name)


def _reset():
    registry._PROVIDERS.clear()
    registry._loaded = True          # evita cargar los built-in (aislamiento del test)


def test_no_provider_returns_hablable_message():
    _reset()
    r = music.control("play", "Frank Sinatra")
    assert r.ok is False and r.reason == "no_provider" and r.message


def test_active_picks_connected_provider():
    _reset()
    off = _Fake(connected=False)
    off.name = "off"
    on = _Fake(connected=True)
    on.name = "on"
    registry.register(off)
    registry.register(on)
    assert music.available() == ["on"]
    assert music.active_provider().name == "on"


def test_control_routes_play_and_volume():
    _reset()
    f = _Fake()
    registry.register(f)
    r = music.control("play", "jazz")
    assert r.ok and ("play", "jazz", "") in f.calls
    music.control("volume_up")               # 50 (now_playing) + 15
    music.control("volume_down")             # 50 - 15
    assert ("volume", 65) in f.calls and ("volume", 35) in f.calls
    music.control("stop")                    # stop = pausar
    assert ("pause",) in f.calls


def test_lazy_registry_loads_builtin_spotify():
    # El registro carga spotify de forma perezosa por su símbolo; sin credenciales queda no-conectado (no crashea).
    registry._PROVIDERS.clear()
    registry._loaded = False
    names = {p.name for p in registry.providers()}
    assert "spotify" in names
