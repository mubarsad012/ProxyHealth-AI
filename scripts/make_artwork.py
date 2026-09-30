"""Draw the ProxyHealth AI app artwork (WP8). Run from the repo root:

    apps/api/.venv/bin/python scripts/make_artwork.py

The mark: a sheet of paper with a folded corner and lines of text, and a speech bubble with a
check — "your paper, explained". Brand colours come from ``src/design/tokens.ts`` (primary
``#0B4F8A``, secondary ``#E3ECF5``, dark-palette success ``#8FD3A8``). Everything is drawn at 4×
and downsampled with Lanczos, so edges stay clean at 48 px.

Writes into ``apps/mobile/assets/images/`` (same names as the Expo template, so ``app.json``
never breaks):
  icon.png                      1024×1024, opaque (iOS rejects transparency), full-bleed blue
  android-icon-foreground.png   1024×1024, transparent, mark inside the central 66 % circle
  android-icon-background.png   1024×1024, solid primary blue
  android-icon-monochrome.png   1024×1024, one colour on transparent (Android 13 themed icons)
  splash-icon.png               1024×1024, transparent, rounded blue tile with the mark
  favicon.png                   48×48, rounded blue tile, simplified mark (fewer, bolder lines)
  notification-icon.png         96×96, white glyph on transparent (Android status bar)
  ../expo.icon/Assets/proxyhealth-mark.png   the mark on transparent, the iOS 26 icon layer

The script lives in ``scripts/`` so it never ships inside the app bundle's asset folder.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]  # repo root (this file is scripts/make_artwork.py)
IMAGES = ROOT / "apps" / "mobile" / "assets" / "images"
EXPO_ICON_ASSETS = ROOT / "apps" / "mobile" / "assets" / "expo.icon" / "Assets"
SS = 4  # supersampling factor

BLUE = (11, 79, 138, 255)  # tokens.light.primary #0B4F8A
PAPER = (255, 255, 255, 255)
FOLD = (207, 224, 241, 255)  # a shade of tokens.light.secondary #E3ECF5
LINE = (183, 202, 223, 255)
BUBBLE = (143, 211, 168, 255)  # tokens.dark.success #8FD3A8
WHITE = (255, 255, 255, 255)
CLEAR = (0, 0, 0, 0)

# The mark in a 1000-unit box, recentred so its farthest point is ~505 units from (500, 500).
PAPER_BOX = (160, 110, 660, 770)  # x0, y0, x1, y1
PAPER_R = 40
FOLD_SIZE = 150
BUBBLE_C = (640, 650)
BUBBLE_R = 200
TAIL = [(510, 770), (590, 830), (445, 890)]
GAP = 34  # background-coloured ring that separates the bubble from the paper
CHECK = [(555, 655), (620, 720), (735, 585)]
CHECK_W = 58


def lines(simple: bool) -> list[tuple[int, int, int, int, bool]]:
    """(x0, x1, y, thickness, is_title) text lines on the paper."""
    if simple:  # favicon / tiny sizes: three bold lines read better than five thin ones
        return [(235, 470, 330, 70, True), (235, 540, 460, 62, False), (235, 400, 590, 62, False)]
    return [
        (235, 450, 310, 46, True),
        (235, 560, 400, 40, False),
        (235, 590, 480, 40, False),
        (235, 470, 560, 40, False),
        (235, 360, 640, 40, False),
    ]


class Pen:
    """Maps mark units to pixels: ``px = offset + unit * k`` (already supersampled)."""

    def __init__(self, img: Image.Image, cx: float, cy: float, k: float) -> None:
        self.d = ImageDraw.Draw(img)
        self.cx, self.cy, self.k = cx, cy, k

    def p(self, x: float, y: float) -> tuple[float, float]:
        return (self.cx + (x - 500) * self.k, self.cy + (y - 500) * self.k)

    def s(self, v: float) -> float:
        return v * self.k

    def box(self, x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        a, b = self.p(x0, y0), self.p(x1, y1)
        return (a[0], a[1], b[0], b[1])

    def rounded(self, box: tuple[int, int, int, int], r: float, fill: tuple[int, ...]) -> None:
        self.d.rounded_rectangle(self.box(*box), radius=self.s(r), fill=fill)

    def poly(self, pts: list[tuple[float, float]], fill: tuple[int, ...]) -> None:
        self.d.polygon([self.p(x, y) for x, y in pts], fill=fill)

    def circle(self, c: tuple[float, float], r: float, fill: tuple[int, ...]) -> None:
        x, y = self.p(*c)
        rr = self.s(r)
        self.d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=fill)

    def bar(self, x0: float, x1: float, y: float, w: float, fill: tuple[int, ...]) -> None:
        """A horizontal line with round ends (a pill), crisper than a stroked line."""
        self.d.rounded_rectangle(self.box(x0 - w / 2, y - w / 2, x1 + w / 2, y + w / 2),
                                 radius=self.s(w / 2), fill=fill)  # fmt: skip

    def stroke(self, pts: list[tuple[float, float]], w: float, fill: tuple[int, ...]) -> None:
        px = [self.p(x, y) for x, y in pts]
        width = max(1, round(self.s(w)))
        self.d.line(px, fill=fill, width=width, joint="curve")
        for x, y in px:  # round caps
            r = width / 2
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def draw_mark(pen: Pen, bg: tuple[int, ...], *, mono: tuple[int, ...] | None = None,
              simple: bool = False) -> None:  # fmt: skip
    """Paper + fold + lines, then the bubble with its separating ring and check.

    ``bg`` is what the cut-outs show (the tile colour, or transparent). ``mono`` draws every
    filled part in one colour, with the details as cut-outs (themed / notification icons).
    """
    x0, y0, x1, y1 = PAPER_BOX
    paper, fold, line_c, title_c = PAPER, FOLD, LINE, BLUE
    bubble, check = BUBBLE, BLUE
    if mono is not None:
        paper = fold = bubble = mono
        line_c = title_c = check = bg
    pen.rounded(PAPER_BOX, PAPER_R, paper)
    # Cut the top-right corner, then draw the folded flap.
    a = (x1 - FOLD_SIZE, y0)
    b = (x1, y0 + FOLD_SIZE)
    pen.poly([(a[0], y0 - 2), (x1 + 2, y0 - 2), (x1 + 2, b[1])], bg)
    flap = [a, (a[0], b[1] - 18), (a[0] + 18, b[1]), b]
    pen.poly(flap, fold)
    if mono is not None:  # in one colour, a gap along the flap's two creases keeps it readable
        pen.stroke([a, (a[0], b[1]), b], 24, bg)
    for lx0, lx1, ly, th, is_title in lines(simple):
        pen.bar(lx0, lx1, ly, th, title_c if is_title else line_c)
    # Separating ring (bubble + tail grown by GAP), then the bubble itself.
    pen.circle(BUBBLE_C, BUBBLE_R + GAP, bg)
    pen.stroke(TAIL + [TAIL[0]], GAP * 2, bg)
    pen.poly(TAIL, bg)
    pen.circle(BUBBLE_C, BUBBLE_R, bubble)
    pen.poly(TAIL, bubble)
    pen.stroke(CHECK, CHECK_W * (1.15 if simple else 1.0), check)


def canvas(size: int, fill: tuple[int, ...]) -> Image.Image:
    return Image.new("RGBA", (size * SS, size * SS), fill)


def finish(img: Image.Image, size: int, path: Path, *, opaque: bool = False) -> None:
    out = img.resize((size, size), Image.Resampling.LANCZOS)
    if opaque:
        out = out.convert("RGB")
    out.save(path, optimize=True)
    print(f"wrote {path.relative_to(ROOT)} {out.size} {out.mode}")


def tile(size: int, radius_frac: float, k_frac: float, simple: bool) -> Image.Image:
    """A rounded blue tile with the mark, on transparent (splash, favicon)."""
    n = size * SS
    img = canvas(size, CLEAR)
    ImageDraw.Draw(img).rounded_rectangle((0, 0, n - 1, n - 1), radius=n * radius_frac, fill=BLUE)
    draw_mark(Pen(img, n / 2, n / 2, n * k_frac / 1000), BLUE, simple=simple)
    return img


def main() -> None:
    n = 1024 * SS
    # iOS / generic icon: opaque, full bleed (the OS applies its own corner mask).
    img = canvas(1024, BLUE)
    draw_mark(Pen(img, n / 2, n / 2, n * 0.96 / 1000), BLUE)
    finish(img, 1024, IMAGES / "icon.png", opaque=True)

    # Android adaptive: foreground inside the central 66 % circle (radius 0.33 × 1024 = 338 px);
    # the mark's farthest point is ~505 units from its centre, so k = 0.33 / 0.505 per unit.
    img = canvas(1024, CLEAR)
    draw_mark(Pen(img, n / 2, n / 2, n * (0.33 / 0.505) / 1000), CLEAR)
    finish(img, 1024, IMAGES / "android-icon-foreground.png")
    finish(canvas(1024, BLUE), 1024, IMAGES / "android-icon-background.png")
    img = canvas(1024, CLEAR)
    draw_mark(Pen(img, n / 2, n / 2, n * (0.33 / 0.505) / 1000), CLEAR, mono=WHITE)
    finish(img, 1024, IMAGES / "android-icon-monochrome.png")

    # Splash: a rounded tile so the white paper stays visible on the white light-mode splash.
    finish(tile(1024, 0.225, 0.78, simple=False), 1024, IMAGES / "splash-icon.png")
    # Favicon: simplified lines; legible at 48 px.
    finish(tile(48, 0.2, 0.84, simple=True), 48, IMAGES / "favicon.png")

    # Notification icon: white on transparent, filling the 96 px box (Android tints it).
    img = canvas(96, CLEAR)
    draw_mark(Pen(img, 96 * SS / 2, 96 * SS / 2, 96 * SS * 0.94 / 1000), CLEAR, mono=WHITE,
              simple=True)  # fmt: skip
    finish(img, 96, IMAGES / "notification-icon.png")

    # iOS 26 Icon Composer layer: the mark on transparent at icon scale; icon.json supplies the
    # blue fill, so the separating ring is a real gap (no painted blue that could mismatch).
    img = canvas(1024, CLEAR)
    draw_mark(Pen(img, n / 2, n / 2, n * 0.96 / 1000), CLEAR)
    finish(img, 1024, EXPO_ICON_ASSETS / "proxyhealth-mark.png")


if __name__ == "__main__":
    main()
