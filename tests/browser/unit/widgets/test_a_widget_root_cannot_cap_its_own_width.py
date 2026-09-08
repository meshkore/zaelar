"""V2-615 — the static gate rejects a widget root that caps its own width, the desktop half of what
`tests/browser/e2e/widgets/test_widget_roots_fill_a_wide_desktop_card.py` measures by actually rendering.

Direct unit tests of `widgets.validator._scan_widget_js`, same level as `test_generator_sync.py`'s coverage of
its sibling static checks — a synthetic snippet is the right size for a pure static-analysis function; a full
Playwright mount is not needed to prove a regex fires.
"""
from widgets import validator


def _js(style_body: str) -> str:
    return f"const s=document.createElement('style');s.textContent=`{style_body}`;document.head.appendChild(s);"


def test_the_old_clamp_idiom_is_rejected_regardless_of_its_size():
    err = validator._scan_widget_js(_js(".hb-test{width:min(480px,92vw)}"))
    assert err and "card-width CAP" in err, err


def test_a_bare_width_at_card_scale_is_rejected():
    err = validator._scan_widget_js(_js(".hb-test{width:760px}"))
    assert err and "card-width CAP" in err, err


def test_a_fluid_root_passes():
    assert validator._scan_widget_js(_js(".hb-test{width:100%;box-sizing:border-box}")) is None


def test_a_small_fixed_element_is_not_a_root_cap():
    """An icon, a QR code, a form field — legitimately small, never a card-width decision."""
    assert validator._scan_widget_js(_js(".hb-test .qr{width:220px}.hb-test input{width:120px}")) is None


def test_max_width_and_min_width_are_not_this_rule():
    """max-width alone never CAPS a root below its container (it only stops OVERgrowth); min-width above the
    phone floor is already a DIFFERENT, pre-existing rule with its own message — this one must not double-fire
    or hijack that message."""
    assert validator._scan_widget_js(_js(".hb-test{max-width:900px;width:100%}")) is None
    err = validator._scan_widget_js(_js(".hb-test{min-width:500px}"))
    assert err and "min-width" in err and "card-width CAP" not in err, err


def test_a_comment_describing_the_old_value_does_not_trip_the_gate():
    """The exact false positive found while building this rule: V2-615's own fix commits document the OLD
    width in a CSS comment right above the new one — the gate must read the comment's PROSE, not its example."""
    js = _js("/* the old width:min(480px,92vw) capped this forever */.hb-test{width:100%;box-sizing:border-box}")
    assert validator._scan_widget_js(js) is None
