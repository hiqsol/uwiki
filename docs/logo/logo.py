# /// script
# requires-python = ">=3.11"
# dependencies = ["fonttools", "skia-pathops", "shapely"]
# ///
"""uWiki logo: one letter that starts as μ and goes on as w, cut from DejaVu Sans Bold.

The bowl of DejaVu's u, made symmetric so the last stem has no foot, is used twice: the bowls share
the middle stem and meet under it in a round valley, the μ's descender goes under the first stem.
The wordmark adds DejaVu's own `iki`.

    uv run docs/logo/logo.py [path/to/DejaVuSans-Bold.ttf]

writes `mark.svg`, `uwiki.svg` and `favicon.svg` next to this script, and to `src/uwiki/assets/` the favicon
of built pages and the uncolored mark of their `--up` link. Shapes only, no font needed to show them.
"""
import sys
from pathlib import Path

import pathops
from fontTools.pens.basePen import BasePen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).parent
ASSETS = HERE.parent.parent / 'src' / 'uwiki' / 'assets'
FONT = sys.argv[1] if len(sys.argv) > 1 else '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

BOWL_DEPTH = 0.45  # height where the bowl's outside meets the stem, in bowl widths
BOWL_ROUND = 0.6   # roundness of the bowl's outside: 0.55 is a circle, higher is squarer
FILLET = 0.45      # radius of the valley between the bowls, in stem widths

ACCENT = ('#4f64ee', '#7c93ff')  # on light, on dark: the accent of the HTML build
INK = ('#1b1f2b', '#e3e5ea')
TILE = '#6176f5'


def rect(x0, y0, x1, y1):
    p = pathops.Path()
    pen = p.getPen()
    pen.moveTo((x0, y0)); pen.lineTo((x1, y0)); pen.lineTo((x1, y1)); pen.lineTo((x0, y1)); pen.closePath()
    return p


def op(a, b, kind):
    return pathops.op(a, b, kind)


def union(*paths):
    out = paths[0]
    for p in paths[1:]:
        out = op(out, p, pathops.PathOp.UNION)
    return out


def moved(path, matrix):
    out = pathops.Path()
    path.draw(TransformPen(out.getPen(), matrix))
    return out


class Font:
    def __init__(self, path):
        self.tt = TTFont(path)
        self.glyphs = self.tt.getGlyphSet()
        self.cmap = self.tt.getBestCmap()
        self.upm = self.tt['head'].unitsPerEm
        self.xh = self.glyph('x')[0].bounds[3]

    def glyph(self, ch, dx=0):
        p = pathops.Path()
        g = self.glyphs[self.cmap[ord(ch)]]
        g.draw(TransformPen(p.getPen(glyphSet=self.glyphs), (1, 0, 0, 1, dx, 0)))
        return p, g.width

    def stems(self, path):
        """Left and right edges of the vertical stems crossing 60% of x-height, left to right."""
        cut = op(path, rect(-5000, self.xh * .58, 20000, self.xh * .62), pathops.PathOp.INTERSECTION)
        return sorted((c.bounds[0], c.bounds[2]) for c in cut.contours)


class Flatten(BasePen):
    """Contours of a path as point rings, curves sampled."""
    def __init__(self):
        super().__init__(None)
        self.rings, self.cur = [], []

    def _moveTo(self, p):
        self.cur = [p]

    def _lineTo(self, p):
        self.cur.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur[-1]
        for i in range(1, 33):
            t = i / 32
            self.cur.append(tuple((1-t)**3 * a + 3 * (1-t)**2 * t * b + 3 * (1-t) * t * t * c + t**3 * d
                                  for a, b, c, d in zip(p0, p1, p2, p3)))

    def _qCurveToOne(self, p1, p2):
        p0 = self.cur[-1]
        for i in range(1, 33):
            t = i / 32
            self.cur.append(tuple((1-t)**2 * a + 2 * (1-t) * t * b + t * t * d for a, b, d in zip(p0, p1, p2)))

    def _closePath(self):
        self.rings.append(self.cur)
        self.cur = []


def fillet(path, r, area):
    """Round the concave crotches inside area with radius r: a morphological closing there only."""
    fp = Flatten()
    path.draw(fp)
    shape = unary_union([Polygon(ring).buffer(0) for ring in fp.rings if len(ring) > 2])
    closed = shape.buffer(r, resolution=64).buffer(-r, resolution=64)
    shape = unary_union([shape, closed.intersection(area)]).simplify(0.6)
    out = pathops.Path()
    pen = out.getPen()
    for poly in getattr(shape, 'geoms', [shape]):
        for ring in [poly.exterior, *poly.interiors]:
            pts = list(ring.coords)[:-1]
            pen.moveTo(pts[0])
            for p in pts[1:]:
                pen.lineTo(p)
            pen.closePath()
    return out


def letter(f):
    """The μw letter and its advance width."""
    u, advance = f.glyph('u')
    (a0, a1), (_, b1) = f.stems(u)[0], f.stems(u)[-1]
    c = (a0 + b1) / 2
    left = op(u, rect(-5000, -5000, c + 1, 5000), pathops.PathOp.INTERSECTION)
    bowl = union(left, moved(left, (-1, 0, 0, 1, 2 * c, 0)))  # u without its foot, symmetric about c
    cols = []
    for x in range(int(a1) + 4, int(c) + 1, 2):
        _, lo, _, hi = op(bowl, rect(x - .5, -5000, x + .5, f.xh * .7), pathops.PathOp.INTERSECTION).bounds
        cols.append((x, lo, hi))
    _, yo, _ = min(cols, key=lambda r: (r[1], -r[0]))  # lowest outside
    xi, _, yi = min(cols, key=lambda r: (r[2], -r[0]))  # lowest inside
    bowl = op(bowl, rect(xi, yi, 2 * c - xi, f.xh * 2), pathops.PathOp.DIFFERENCE)  # no ridge in the counter
    # DejaVu's u is nearly flat underneath: a round U outside, the font's stems and counter kept
    width = 2 * (c - a0)
    ytop = min(yo + width * BOWL_DEPTH, f.xh * .75)
    k = BOWL_ROUND
    outside = pathops.Path()
    pen = outside.getPen()
    pen.moveTo((a0, ytop))
    pen.curveTo((a0, ytop - k * (ytop - yo)), (c - k * width / 2, yo), (c, yo))
    pen.curveTo((c + k * width / 2, yo), (2 * c - a0, ytop - k * (ytop - yo)), (2 * c - a0, ytop))
    pen.closePath()
    counter = op(rect(a1 - 1, yo - 1, 2 * c - a1 + 1, f.xh * 2), bowl, pathops.PathOp.DIFFERENCE)
    counter = next(cc for cc in pathops.Path(counter).contours if cc.bounds[3] >= f.xh * 1.5)
    bowl = union(op(bowl, rect(-5000, ytop, 10000, 5000), pathops.PathOp.INTERSECTION),
                 op(outside, counter, pathops.PathOp.DIFFERENCE))
    shift = (2 * c - a1) - a0  # second bowl's left stem on the first bowl's right stem
    mu, _ = f.glyph('μ')
    descender = rect(a0, mu.bounds[1], a1, ytop)
    res = union(bowl, moved(bowl, (1, 0, 0, 1, shift, 0)), descender)
    # round valley between the two bowl bottoms; the descender meets the first bowl in a plain corner
    return fillet(res, (a1 - a0) * FILLET, box(c, -5000, c + shift, yi - 2)), advance + shift


def svg_d(path):
    pen = SVGPathPen(None, ntos=lambda v: f'{v:.0f}')
    path.draw(TransformPen(pen, (1, 0, 0, -1, 0, 0)))
    return pen.getCommands()


def svg(view, body, label='uWiki'):
    """SVG of body, labeled image, or hidden from screen readers without label, as decoration."""
    a11y = f'role="img" aria-label="{label}"' if label else 'aria-hidden="true"'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{" ".join(f"{v:.0f}" for v in view)}" '
            f'{a11y}>{body}</svg>\n')


def themed(*rules):
    """Colors for light, and for dark when the viewer prefers it."""
    light = ''.join(f'.{cls}{{fill:{pair[0]}}}' for cls, pair in rules)
    dark = ''.join(f'.{cls}{{fill:{pair[1]}}}' for cls, pair in rules)
    return f'<style>{light}@media (prefers-color-scheme:dark){{{dark}}}</style>'


def main():
    f = Font(FONT)
    mark, advance = letter(f)
    rest, x = [], advance
    for ch in 'iki':
        p, w = f.glyph(ch, x)
        rest.append(p)
        x += w
    rest = union(*rest)

    x0, y0, x1, y1 = mark.bounds
    side = max(x1 - x0, y1 - y0) * 1.1
    cx, cy = (x0 + x1) / 2, -(y0 + y1) / 2
    view = (cx - side / 2, cy - side / 2, side, side)
    (HERE / 'mark.svg').write_text(svg(view, themed(('a', ACCENT)) + f'<path class="a" d="{svg_d(mark)}"/>'))
    # the --up link of built pages: no colors of its own, the page fills it, nor label, the link has one
    (ASSETS / 'mark.svg').write_text(svg(view, f'<path d="{svg_d(mark)}"/>', label=None))

    wx0, wy0, wx1, wy1 = union(mark, rest).bounds
    pad = f.upm * .04
    (HERE / 'uwiki.svg').write_text(svg(
        (wx0 - pad, -wy1 - pad, wx1 - wx0 + 2 * pad, wy1 - wy0 + 2 * pad),
        themed(('a', ACCENT), ('i', INK)) + f'<path class="a" d="{svg_d(mark)}"/><path class="i" d="{svg_d(rest)}"/>'))

    # favicon: white letter on an accent tile, the same on light and dark tabs
    tile = side * 1.12
    scale = .82
    icon = svg((cx - tile / 2, cy - tile / 2, tile, tile),
               f'<rect x="{cx - tile / 2:.0f}" y="{cy - tile / 2:.0f}" width="{tile:.0f}" height="{tile:.0f}" '
               f'rx="{tile * .22:.0f}" fill="{TILE}"/>'
               f'<path transform="translate({cx:.0f} {cy:.0f}) scale({scale}) translate({-cx:.0f} {-cy:.0f})" '
               f'd="{svg_d(mark)}" fill="#fff"/>')
    (HERE / 'favicon.svg').write_text(icon)
    (ASSETS / 'favicon.svg').write_text(icon)


if __name__ == '__main__':
    main()
