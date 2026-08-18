"""Generate the PWA icons from the MeshKore palette — no external asset, no design tool in the loop.

The mark: zaelar's ORB, which is what the operator already looks at on every screen — a conic ring
(emerald -> sky -> violet, the MeshKore gradient) around a dark core, on the app's own canvas colour.
Two sizes plus a MASKABLE variant: Android crops a maskable icon to whatever shape the launcher uses
(circle, squircle, rounded square), and anything outside the inner 80% safe zone can be cut. So the
maskable one draws the same mark at 62% scale on a full-bleed background instead of at 78% with
transparent margins -- the usual reason a PWA icon looks decapitated on one phone and fine on another.
"""
import math
from PIL import Image, ImageDraw

BG = (10, 15, 22, 255)          # --canvas
CORE = (13, 22, 34, 255)        # --hb-console-bg
STOPS = [(0.00, (16, 185, 129)),   # emerald-500
         (0.33, (122, 208, 255)),  # sky
         (0.66, (139, 123, 255)),  # violet
         (1.00, (16, 185, 129))]


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def ring_color(frac):
    for i in range(len(STOPS) - 1):
        p0, c0 = STOPS[i]
        p1, c1 = STOPS[i + 1]
        if p0 <= frac <= p1:
            return lerp(c0, c1, (frac - p0) / (p1 - p0))
    return STOPS[-1][1]


def icon(size, mark_scale, rounded):
    S = 8  # supersample: PIL has no anti-aliasing on arcs, so draw big and downscale
    W = size * S
    img = Image.new("RGBA", (W, W), BG)
    d = ImageDraw.Draw(img)
    cx = cy = W / 2
    outer = W * mark_scale / 2
    width = outer * 0.30
    # The conic gradient, one degree at a time.
    for deg in range(360):
        d.arc([cx - outer, cy - outer, cx + outer, cy + outer],
              start=deg - 91, end=deg + 1, fill=ring_color(deg / 360.0), width=round(width))
    inner = outer - width
    d.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill=CORE)
    # A soft highlight on the core, so it reads as a sphere and not as a hole.
    hi = inner * 0.52
    hx, hy = cx - inner * 0.28, cy - inner * 0.30
    for k in range(24):
        t = k / 24
        r = hi * (1 - t)
        a = round(26 * (1 - t))
        d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=(122, 208, 255, a))
    img = img.resize((size, size), Image.LANCZOS)
    if rounded:
        # iOS applies its own mask, but Android's "any" purpose does not — a squircle keeps it from looking
        # like a screenshot in the launcher grid.
        mask = Image.new("L", (size * S, size * S), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, size * S - 1, size * S - 1],
                                              radius=int(size * S * 0.22), fill=255)
        img.putalpha(mask.resize((size, size), Image.LANCZOS))
    return img


# Run from engine/: ./.venv/bin/python frontend/mobile/icons/generate.py
OUT = __file__.rsplit("/", 1)[0] + "/"
icon(192, 0.78, True).save(OUT + "icon-192.png")
icon(512, 0.78, True).save(OUT + "icon-512.png")
icon(512, 0.62, False).save(OUT + "maskable-512.png")   # full bleed, mark inside the 80% safe zone
icon(180, 0.78, False).save(OUT + "apple-touch-icon.png")  # iOS masks it itself; a transparent corner turns black
print("icons written")
