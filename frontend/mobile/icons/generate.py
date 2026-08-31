"""Generate the PWA icons — no external asset, no design tool in the loop.

THE MARK IS THE EYE, and it is a SILHOUETTE (operator, 2026-08-18: “very clean icons on a uniform
background, ideally black, and silhouettes only — as close as possible to those already present in the
UI frontend”).

Why the eye and not a gradient orb: `engine/CLAUDE.md` already fixes it as zaelar's identity — the
seven controls are the upper lid, the ECG is the lower lid, and the ORB IS THE IRIS. So the eye is
not decoration invented for a launcher, it is the same thing the operator looks at on every screen,
reduced to the two strokes that survive being 48px wide in a browser tab. The previous version drew
the orb as a conic emerald->sky->violet ring: pretty at 512px, and at tab size an indistinct coloured
dot, which is the opposite of what a silhouette is for.

STROKES, ONE COLOUR, on FLAT BLACK — the same vocabulary as every icon in the UI
(`fill="none" stroke="currentColor"`, see `app/components/Orb.js`), so the home-screen icon and the
dock read as the same family. To move the mark to the brand emerald instead, change INK below to
(16, 185, 129) — it is one constant on purpose.

GEOMETRY comes from the real eye, not from taste: corners at +/-2.16 * R and the lid apex at
+/-1.24 * R, the ratios `styles.css` uses for the desktop eye (CLAUDE.md, orb v4 2026-07-22). Each
lid is the circular arc through those three points; solving for it gives a circle offset 1.2613 * R
from the eye centre with radius 2.5013 * R.

FOUR OUTPUTS, and the differences are not cosmetic:
  · icon-192 / icon-512 ("any")  -> squircle-masked, mark at 0.185 * S
  · maskable-512                 -> FULL BLEED, mark at 0.155 * S. Android crops a maskable icon to
    whatever shape the launcher uses, and only the inner 80% CIRCLE is safe. The mark is wide, so
    what has to fit is its bounding-box CORNER: sqrt(2.16^2 + 1.24^2) = 2.49 * R <= 0.4 * S. That is
    the usual reason a PWA icon looks decapitated on one phone and fine on another.
  · apple-touch-icon             -> 180px, NO transparency (iOS applies its own mask; a transparent
    corner renders black anyway, so it is painted black deliberately rather than by accident).

Run from engine/:  ./.venv/bin/python frontend/mobile/icons/generate.py
"""
import math

from PIL import Image, ImageDraw

BG = (0, 0, 0, 255)              # flat black, uniform — no gradient, no vignette
INK = (255, 255, 255, 255)       # the silhouette; swap for the emerald to brand it

# Eye ratios, expressed against the iris radius R (see module docstring).
CORNER_X = 2.16                  # half-width: where the two lids meet
APEX_Y = 1.24                    # half-height: how far each lid bulges from the centre line
_LID_OFF = 1.2613                # solved: circle centre offset from the eye centre
_LID_R = 2.5013                  # solved: that circle's radius

S = 8                            # supersample: PIL does not anti-alias arcs, so draw big and shrink


def _lids(d, cx, cy, r, w):
    """The two circular arcs that meet at the corners."""
    lr = _LID_R * r
    off = _LID_OFF * r
    # Endpoint angle on each lid circle. PIL measures from 3 o'clock and increases CLOCKWISE, and
    # because y grows downward that is also clockwise on screen.
    a = math.degrees(math.atan2(off, CORNER_X * r))
    # UPPER lid: its circle sits BELOW the eye, so the arc bulges up. 270 deg is 12 o'clock.
    box = [cx - lr, cy + off - lr, cx + lr, cy + off + lr]
    d.arc(box, start=180 + a, end=360 - a, fill=INK, width=w)
    # LOWER lid: mirrored.
    box = [cx - lr, cy - off - lr, cx + lr, cy - off + lr]
    d.arc(box, start=a, end=180 - a, fill=INK, width=w)


def icon(size, mark_scale, rounded):
    w_px = size * S
    img = Image.new("RGBA", (w_px, w_px), BG)
    d = ImageDraw.Draw(img)
    cx = cy = w_px / 2
    r = w_px * mark_scale                      # iris radius
    stroke = max(1, round(w_px * 0.030))       # generous: a hairline disappears at tab size

    _lids(d, cx, cy, r, stroke)
    # The IRIS: a stroked circle (same line weight as the lids) with a solid pupil, which is what
    # makes it read as an eye rather than as a lens shape at small sizes.
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=INK, width=stroke)
    p = r * 0.34
    d.ellipse([cx - p, cy - p, cx + p, cy + p], fill=INK)

    img = img.resize((size, size), Image.LANCZOS)
    if rounded:
        # Android's "any" purpose applies no mask of its own — without a squircle the icon looks like
        # a screenshot in the launcher grid.
        mask = Image.new("L", (w_px, w_px), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, w_px - 1, w_px - 1], radius=int(w_px * 0.22), fill=255)
        img.putalpha(mask.resize((size, size), Image.LANCZOS))
    return img


OUT = __file__.rsplit("/", 1)[0] + "/"
icon(192, 0.185, True).save(OUT + "icon-192.png")
icon(512, 0.185, True).save(OUT + "icon-512.png")
icon(512, 0.155, False).save(OUT + "maskable-512.png")     # full bleed, mark inside the 80% circle
icon(180, 0.185, False).save(OUT + "apple-touch-icon.png")  # iOS masks it itself
print("icons written")
