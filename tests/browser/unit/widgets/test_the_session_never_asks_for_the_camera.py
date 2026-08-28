"""Camera capture is DISABLED — mic-only sessions (operator decision, 2026-08-28 · V2-456).

The CameraUnit surface was hidden on 2026-08-09, but both session engines kept a best-effort
`getUserMedia({ video: … })` in start(): every boot still triggered the browser's camera-permission
prompt (most jarring on the phone shell) for a preview nobody could see. The acquisition code is now
COMMENTED OUT, not deleted, in start() and toggleCam() of both engines — re-enabling is uncommenting.

Source tests (no browser in the deterministic battery), same pattern as test_chat_voice_independent.py:
what must be prevented is someone quietly re-activating the capture, and the commented block that
documents it would otherwise trip the check — hence comments are stripped first.
"""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[4] / "frontend"

_VIDEO_CAPTURE = re.compile(r"getUserMedia\(\s*\{[^)]*video", re.DOTALL)


def _code(path: Path) -> str:
    """The file WITHOUT line comments: the disabled block must stay visible to humans, invisible here."""
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in path.read_text(encoding="utf-8").split("\n"))


SESSION = _code(FRONTEND / "app" / "services" / "session.js")
SESSION_LK = _code(FRONTEND / "app" / "services" / "session-lk.js")


def test_neither_session_engine_captures_video():
    """The URL of session.js serves session-lk.js under the LiveKit engine (server/livekit_api.py),
    so BOTH files must be clean — fixing only the one you tested is the known trap here."""
    assert not _VIDEO_CAPTURE.search(SESSION), "session.js re-acquired the camera"
    assert not _VIDEO_CAPTURE.search(SESSION_LK), "session-lk.js re-acquired the camera"


def test_the_microphone_capture_survived_the_disable():
    """Disabling the camera must not have taken the mic with it: audio-only getUserMedia stays."""
    mic = re.compile(r"getUserMedia\(\s*\{\s*audio")
    assert mic.search(SESSION), "session.js lost its mic capture"
    assert mic.search(SESSION_LK), "session-lk.js lost its mic capture"


def test_no_other_frontend_code_asks_for_video():
    """Sweep app/ and mobile/ (vendor bundles excluded): the two engines were the only doors, and this
    keeps a third one from appearing under a different name."""
    for path in list((FRONTEND / "app").rglob("*.js")) + list((FRONTEND / "mobile").rglob("*.js")):
        assert not _VIDEO_CAPTURE.search(_code(path)), f"{path} asks for the camera"
