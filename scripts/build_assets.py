# /// script
# requires-python = ">=3.11"
# dependencies = ["uharfbuzz>=0.39"]
# ///
"""Build the animated README graphics into assets/ (a light and a dark file each).

    uv run scripts/build_assets.py

GitHub shows README SVGs through <img>: no JavaScript and no web fonts. Motion
is therefore SMIL/CSS only, and all text is outlined to paths with the brand
fonts (fetched once into .cache/fonts) so every visitor sees the same type.
"""

import math
import urllib.request
from pathlib import Path

import uharfbuzz as hb

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / ".cache" / "fonts"
GOOGLE_FONTS = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONT_FILES = {
    "serif": "newsreader/Newsreader%5Bopsz%2Cwght%5D.ttf",
    "sans": "manrope/Manrope%5Bwght%5D.ttf",
    "mono": "jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}

# Dark mirrors mhbd.dev, light mirrors the CV.
THEMES = {
    "dark": dict(bg="#050505", border="#262626", rule="#1f1f1f", ink="#e8e8e8",
                 soft="#b8b8b8", muted="#8a8a8a", accent="#ff4500", glow=0.12),
    "light": dict(bg="#f0ede5", border="#d9d3c7", rule="#d9d3c7", ink="#111210",
                  soft="#3b3c38", muted="#66655f", accent="#4b5b78", glow=0.06),
}

EASE_OUT = "cubic-bezier(.23,1,.32,1)"
EASE_IN_OUT = ".77 0 .175 1"  # the same curves in SMIL keySplines form
EASE_OUT_SPLINE = ".23 1 .32 1"


def num(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def font_path(family):
    path = FONT_DIR / f"{family}.ttf"
    if not path.exists():
        FONT_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(GOOGLE_FONTS + FONT_FILES[family], path)
    return path


def join(*nums):
    """SVG number list: a minus sign already separates, so skip the space."""
    out = ""
    for s in nums:
        out += s if not out or s.startswith("-") else " " + s
    return out


def tenths(n):
    s = num(n / 10)
    return s.replace("0.", ".", 1) if s.startswith(("0.", "-0.")) else s


class Pen:
    """Writes glyph outlines as relative path commands on a 0.1 grid (no rounding drift)."""

    def __init__(self):
        self.d, self.cur, self.start = [], None, None

    def origin(self, x, y, scale):
        self.x, self.y, self.s = x, y, scale

    def _cmd(self, op, *pts):
        grid = [(round((self.x + px * self.s) * 10), round((self.y - py * self.s) * 10)) for px, py in pts]
        if self.cur is None:
            self.d.append(op.upper() + join(*(tenths(v) for p in grid for v in p)))
        else:
            cx, cy = self.cur
            self.d.append(op + join(*(tenths(v) for gx, gy in grid for v in (gx - cx, gy - cy))))
        self.cur = grid[-1]

    def moveTo(self, p):
        self._cmd("m", p)
        self.start = self.cur

    def lineTo(self, p):
        self._cmd("l", p)

    def qCurveTo(self, *p):
        self._cmd("q", *p)

    def curveTo(self, *p):
        self._cmd("c", *p)

    def closePath(self):
        self.d.append("z")
        self.cur = self.start


class Type:
    """One font at fixed variation axes; turns strings into SVG path data."""

    def __init__(self, family, **axes):
        face = hb.Face(hb.Blob.from_file_path(str(font_path(family))))
        self.font = hb.Font(face)
        self.font.set_variations(axes)
        self.upem = face.upem

    def _shape(self, text):
        for ch in set(text) - {" "}:
            if self.font.get_nominal_glyph(ord(ch)) is None:
                raise ValueError(f"glyph {ch!r} missing")
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.font, buf)
        return list(zip(buf.glyph_infos, buf.glyph_positions))

    def width(self, text, size, track=0.0):
        glyphs = self._shape(text)
        return (sum(p.x_advance for _, p in glyphs) / self.upem + track * (len(glyphs) - 1)) * size

    def path(self, text, size, x, y, track=0.0):
        pen, s = Pen(), size / self.upem
        for info, pos in self._shape(text):
            pen.origin(x + pos.x_offset * s, y - pos.y_offset * s, s)
            self.font.draw_glyph_with_pen(info.codepoint, pen)
            x += pos.x_advance * s + track * size
        return "".join(pen.d)

    def el(self, text, size, x, y, fill, track=0.0, anchor="start", cls=""):
        if anchor != "start":
            x -= self.width(text, size, track) / (2 if anchor == "middle" else 1)
        c = f' class="{cls}"' if cls else ""
        return f'<path{c} fill="{fill}" d="{self.path(text, size, x, y, track)}"/>'

    def wrap(self, text, size, width):
        lines, line = [], ""
        for word in text.split():
            trial = f"{line} {word}".strip()
            if line and self.width(trial, size) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        return lines + [line]


def svg(w, h, t, title, css, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-labelledby="t"><title id="t">{title}</title><style>{css}</style>'
        f'<defs><clipPath id="card"><rect width="{w}" height="{h}" rx="16"/></clipPath></defs>'
        f'<g clip-path="url(#card)"><rect width="{w}" height="{h}" fill="{t["bg"]}"/>{body}</g>'
        f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="15.5" fill="none" stroke="{t["border"]}"/>'
        "</svg>"
    )


# --- 3D ---------------------------------------------------------------------

def geodesic():
    """Icosahedron subdivided once: 42 vertices, 120 edges, on the unit sphere."""
    g = (1 + 5 ** 0.5) / 2

    def unit(p):
        n = math.sqrt(sum(c * c for c in p))
        return tuple(c / n for c in p)

    verts = [unit(p) for p in [(-1, g, 0), (1, g, 0), (-1, -g, 0), (1, -g, 0), (0, -1, g), (0, 1, g),
                               (0, -1, -g), (0, 1, -g), (g, 0, -1), (g, 0, 1), (-g, 0, -1), (-g, 0, 1)]]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5),
             (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    mids = {}

    def mid(a, b):
        key = (min(a, b), max(a, b))
        if key not in mids:
            verts.append(unit([(verts[a][i] + verts[b][i]) / 2 for i in range(3)]))
            mids[key] = len(verts) - 1
        return mids[key]

    edges = set()
    for a, b, c in faces:
        ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
        for tri in ((a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)):
            for i in range(3):
                edges.add(tuple(sorted((tri[i], tri[(i + 1) % 3]))))
    return verts, sorted(edges)


def project(p, spin, cx, cy, r, tilt=math.radians(-20), dist=4.5):
    """Spin around Y, tilt toward the camera, perspective-project. z: 1 front … -1 back."""
    x, y, z = p
    x, z = x * math.cos(spin) + z * math.sin(spin), -x * math.sin(spin) + z * math.cos(spin)
    y, z = y * math.cos(tilt) - z * math.sin(tilt), y * math.sin(tilt) + z * math.cos(tilt)
    k = dist / (dist - z)
    return cx + x * r * k, cy - y * r * k, z


def depth(z):
    return max(0.0, min(1.0, (z + 1) / 2))


def loop_attr(name, values, dur, kind="animate"):
    extra = ' type="translate"' if kind == "animateTransform" else ""
    return (f'<{kind} attributeName="{name}"{extra} values="{";".join(values)}" '
            f'dur="{dur}s" repeatCount="indefinite"/>')


def sphere(t, cx, cy, r):
    """Rotating geodesic sphere with an orbit. Drawn at 2x around its centre in
    whole numbers (0.5 px precision) to keep the ~40 animation frames small."""
    verts, edges = geodesic()
    frames_n, spin_s = 36, 48
    frames = [[project(v, 2 * math.pi * k / frames_n, 0, 0, 2 * r) for v in verts]
              for k in range(frames_n + 1)]
    accent = sorted({1, 4, 6, 10})

    def xy(p):
        return join(str(round(p[0])), str(round(p[1])))

    def op(v):
        return f"{v:.1f}".lstrip("0") or "0"

    moving, still = [], []
    for a, b in edges:
        ds = [f"M{xy(f[a])}l{join(str(round(f[b][0]) - round(f[a][0])), str(round(f[b][1]) - round(f[a][1])))}"
              for f in frames]
        ops = [op(0.07 + 0.6 * depth((f[a][2] + f[b][2]) / 2) ** 1.6) for f in frames]
        still.append(f'<path d="{ds[0]}" stroke-opacity="{ops[0]}"/>')
        moving.append(f'<path d="{ds[0]}" stroke-opacity="{ops[0]}">'
                      f'{loop_attr("d", ds, spin_s)}{loop_attr("stroke-opacity", ops, spin_s)}</path>')

    nodes_moving, nodes_still = [], []
    for i in range(len(verts)):
        hot = i in accent
        pos = [xy(f[i]) for f in frames]
        d = [depth(f[i][2]) for f in frames]
        rs = [str(round(2 * ((2.4 if hot else 1.2) + 1.6 * x))) for x in d]
        ops = [op(0.15 + 0.85 * x) for x in d]
        fill = t["accent"] if hot else t["ink"]
        nodes_still.append(f'<circle transform="translate({pos[0]})" r="{rs[0]}" fill="{fill}" opacity="{ops[0]}"/>')
        halo = ""
        if hot:
            pulse = (f'dur="2.8s" begin="{accent.index(i) * 0.7:.1f}s" repeatCount="indefinite" '
                     f'calcMode="spline" keyTimes="0;1" keySplines="{EASE_OUT_SPLINE}"')
            halo = (f'<circle r="6" fill="none" stroke="{t["accent"]}" stroke-width="2.4" stroke-opacity="0">'
                    f'<animate attributeName="r" values="6;28" {pulse}/>'
                    f'<animate attributeName="stroke-opacity" values=".7;0" {pulse}/></circle>')
        nodes_moving.append(
            f'<g transform="translate({pos[0]})" opacity="{ops[0]}">'
            f'{loop_attr("transform", pos, spin_s, "animateTransform")}{loop_attr("opacity", ops, spin_s)}'
            f'{halo}<circle r="{rs[0]}" fill="{fill}">{loop_attr("r", rs, spin_s)}</circle></g>')

    def orbit(angle):
        return project(rot_z((1.36 * math.cos(angle), 0, 1.36 * math.sin(angle)), math.radians(22)), 0, 0, 0, 2 * r)

    # Split the orbit so its back half can sit behind the sphere.
    back, front, run, side = [], [], [], None
    for x, y, z in (orbit(2 * math.pi * k / 120) for k in range(121)):
        if side is not None and (z >= 0) != side:
            (front if side else back).append(run)
            run = run[-1:]
        run.append((x, y))
        side = z >= 0
    (front if side else back).append(run)

    def poly(runs):
        return "".join("M" + "L".join(xy(p) for p in pts) for pts in runs)

    sat_n, sat_s = 72, 16
    sat = [orbit(-2 * math.pi * k / sat_n) for k in range(sat_n + 1)]
    sat_pos = [xy(p) for p in sat]
    sat_op = [op(0.25 + 0.75 * depth(p[2])) for p in sat]
    sat_r = [str(round(2 * (2.2 + 1.8 * depth(p[2])))) for p in sat]
    satellite = (f'<g transform="translate({sat_pos[0]})" opacity="{sat_op[0]}">'
                 f'{loop_attr("transform", sat_pos, sat_s, "animateTransform")}{loop_attr("opacity", sat_op, sat_s)}'
                 f'<circle r="{sat_r[0]}" fill="{t["accent"]}">{loop_attr("r", sat_r, sat_s)}</circle></g>')

    wire = f'fill="none" stroke="{t["ink"]}" stroke-width="2" stroke-linecap="round"'
    return (
        f'<g transform="translate({cx} {cy}) scale(.5)">'
        f'<path d="{poly(back)}" {wire} stroke-opacity=".18" stroke-dasharray="2 10"/>'
        f'<g class="motion"><g {wire}>{"".join(moving)}</g>{"".join(nodes_moving)}</g>'
        f'<g class="still"><g {wire}>{"".join(still)}</g>{"".join(nodes_still)}</g>'
        f'<path d="{poly(front)}" {wire} stroke-opacity=".4"/>'
        f'<g class="motion">{satellite}</g></g>'
    )


def rot_z(p, a):
    x, y, z = p
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a), z


# --- graphics -----------------------------------------------------------------

BASE_CSS = (
    ".still{display:none}"
    "@keyframes fade{from{opacity:0}}"
    "@media (prefers-reduced-motion:reduce){.motion{display:none}.still{display:inline}}"
)


def hero(t, f):
    w, h, x = 960, 392, 56
    cx, cy, r = 786, 168, 108

    name_size = min(80.0, 520 / f["display"].width("Muhammed Bodruk", 1))
    label = dict(size=12.5, track=0.16)
    status = "OPEN TO WEB PROJECTS"
    status_w = f["mono"].width(status, **label)

    css = (
        f".r{{animation:rise .8s {EASE_OUT} both}}"
        f".w{{transform-box:fill-box;transform-origin:left;animation:draw .8s {EASE_OUT} both}}"
        f".f{{animation:fade 1.6s {EASE_OUT} .3s both}}"
        f".p{{transform-box:fill-box;transform-origin:center;animation:pulse 2.4s {EASE_OUT} infinite}}"
        + "".join(f".d{i}{{animation-delay:{i * 0.07:.2f}s}}" for i in range(1, 7))
        + "@keyframes rise{from{opacity:0;transform:translateY(8px)}}"
        "@keyframes draw{from{transform:scaleX(0)}}"
        "@keyframes pulse{from{opacity:.55}to{opacity:0;transform:scale(3)}}"
        + BASE_CSS
        + "@media (prefers-reduced-motion:reduce){.r,.w{animation-name:fade}.p{animation:none;opacity:0}}"
    )

    body = "".join([
        f'<defs><radialGradient id="glow"><stop offset="0" stop-color="{t["accent"]}" stop-opacity="{t["glow"]}"/>'
        f'<stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/></radialGradient></defs>',
        f'<circle cx="{cx}" cy="{cy}" r="230" fill="url(#glow)"/>',
        f'<g class="f">{sphere(t, cx, cy, r)}</g>',
        f'<path class="w" d="M{x} 87.5H{x + 34}" stroke="{t["accent"]}" stroke-width="1.5"/>',
        f["mono"].el("FULLSTACK AI DEVELOPER", 13, x + 46, 92, t["accent"], track=0.24, cls="r d1"),
        f["display"].el("Muhammed Bodruk", name_size, x - 2, 178, t["ink"], cls="r d2"),
        f["sans"].el("Fast, secure, AI-assisted web products", 22, x, 222, t["soft"], cls="r d3"),
        f["mono"].el("Next.js · TypeScript · PostgreSQL · Drizzle ORM · AI Workflows", 14, x, 258,
                     t["muted"], cls="r d4"),
        f'<path class="w d5" d="M{x} 304.5H{w - x}" stroke="{t["rule"]}"/>',
        f["mono"].el("8+ YRS SHIPPING   ·   TÜRKİYE / REMOTE", label["size"], x, 346, t["muted"],
                     track=label["track"], cls="r d6"),
        f'<g class="r d6"><circle class="p" cx="{num(w - x - status_w - 16)}" cy="341.5" r="4" fill="{t["accent"]}"/>'
        f'<circle cx="{num(w - x - status_w - 16)}" cy="341.5" r="4" fill="{t["accent"]}"/></g>',
        f["mono"].el(status, label["size"], w - x, 346, t["ink"], track=label["track"], anchor="end",
                     cls="r d6"),
    ])
    return svg(w, h, t, "Muhammed Bodruk — Fullstack AI Developer", css, body)


STEPS = [
    ("01", "Discover", "Name the problem, the user and the evidence that proves success."),
    ("02", "Architect", "Shape data, UI and constraints so they hold up in real use."),
    ("03", "Harness", "Scoped prompt → agent run → human review → checks."),
    ("04", "Ship & evolve", "Release, observe, simplify. Findings feed the next brief."),
]


def loop(t, f):
    w, h = 960, 300
    left, right, top, bottom, rad = 32, 928, 84, 262, 22
    xs = [72 + i * 218 for i in range(len(STEPS))]

    # The signal travels the track clockwise, dwelling on each step.
    track = (f"M{left + rad} {top}H{right - rad}A{rad} {rad} 0 0 1 {right} {top + rad}V{bottom - rad}"
             f"A{rad} {rad} 0 0 1 {right - rad} {bottom}H{left + rad}A{rad} {rad} 0 0 1 {left} {bottom - rad}"
             f"V{top + rad}A{rad} {rad} 0 0 1 {left + rad} {top}Z")
    motion = (f"M{xs[0]} {top}H{right - rad}A{rad} {rad} 0 0 1 {right} {top + rad}V{bottom - rad}"
              f"A{rad} {rad} 0 0 1 {right - rad} {bottom}H{left + rad}A{rad} {rad} 0 0 1 {left} {bottom - rad}"
              f"V{top + rad}A{rad} {rad} 0 0 1 {left + rad} {top}H{xs[0]}")
    quarter = math.pi * rad / 2
    length = ((right - rad - xs[0]) + 2 * (bottom - top - 2 * rad) + (right - left - 2 * rad)
              + 4 * quarter + (xs[0] - left - rad))
    stops = [(x - xs[0]) / length for x in xs]

    dwell, move, back = 1.5, 0.7, 2.6
    total = len(xs) * dwell + (len(xs) - 1) * move + back
    times, points, splines = [0.0], [0.0], []
    clock = 0.0
    arrivals = []
    for i, p in enumerate(stops):
        if i:
            clock += move
            times.append(clock)
            points.append(p)
            splines.append(EASE_IN_OUT)
        arrivals.append(clock)
        clock += dwell
        times.append(clock)
        points.append(p)
        splines.append("0 0 1 1")
    times.append(total)
    points.append(1.0)
    splines.append(EASE_IN_OUT)

    def keys(values):
        return ";".join(f"{v:.4f}".rstrip("0").rstrip(".") or "0" for v in values)

    dot = (f'<g class="motion"><circle r="11" fill="{t["accent"]}" opacity=".18"/>'
           f'<circle r="5" fill="{t["accent"]}"/>'
           f'<animateMotion path="{motion}" dur="{total}s" repeatCount="indefinite" calcMode="spline" '
           f'keyTimes="{keys(v / total for v in times)}" keyPoints="{keys(points)}" '
           f'keySplines="{";".join(splines)}"/></g>')

    fade = 0.25
    titles = "".join(f'<path id="s{i}" d="{f["title"].path(title, 26, x - 7, 126)}"/>'
                     for i, ((_, title, _), x) in enumerate(zip(STEPS, xs)))
    parts = [f'<defs>{titles}</defs><path d="{track}" fill="none" stroke="{t["border"]}" stroke-width="1.5"/>']
    for i, ((n, title, desc), x) in enumerate(zip(STEPS, xs)):
        start, end = arrivals[i], arrivals[i] + dwell
        if i == 0:  # lit at the start of the loop, and again as the signal returns
            vals, kt = "1;1;0;0;1", [0, end, end + fade, total - fade, total]
        else:
            vals, kt = "0;0;1;1;0;0", [0, start - fade, start, end, end + fade, total]
        lines = f["sans"].wrap(desc, 15, 188)
        parts += [
            f["mono"].el(n, 12, x - 6, 60, t["accent"], track=0.16),
            f'<circle cx="{x}" cy="{top}" r="6" fill="{t["bg"]}" stroke="{t["muted"]}" stroke-width="1.5"/>',
            f'<use href="#s{i}" fill="{t["ink"]}"/>',
            *(f["sans"].el(line, 15, x - 6, 154 + 22 * j, t["soft"]) for j, line in enumerate(lines)),
            f'<g class="motion" opacity="{vals[0]}">'
            f'<animate attributeName="opacity" values="{vals}" keyTimes="{keys(v / total for v in kt)}" '
            f'dur="{total}s" repeatCount="indefinite"/>'
            f'<circle cx="{x}" cy="{top}" r="14" fill="{t["accent"]}" opacity=".16"/>'
            f'<circle cx="{x}" cy="{top}" r="6" fill="{t["accent"]}"/>'
            f'<use href="#s{i}" fill="{t["accent"]}"/></g>',
        ]

    label = "← OBSERVATIONS BECOME THE NEXT BRIEF"
    label_w = f["mono"].width(label, 12, 0.16)
    parts += [  # the signal passes under the label on its way back
        dot,
        f'<rect x="{num(w / 2 - label_w / 2 - 14)}" y="249" width="{num(label_w + 28)}" height="26" fill="{t["bg"]}"/>',
        f["mono"].el(label, 12, w / 2, 266, t["muted"], track=0.16, anchor="middle"),
    ]
    return svg(w, h, t, "How I build: Discover, Architect, Harness, Ship and evolve — a repeating loop",
               BASE_CSS, "".join(parts))


def main():
    faces = {
        "display": Type("serif", wght=560, opsz=72),
        "title": Type("serif", wght=500, opsz=28),
        "sans": Type("sans", wght=500),
        "mono": Type("mono", wght=500),
    }
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    for theme, t in THEMES.items():
        for name, build in (("hero", hero), ("loop", loop)):
            path = out / f"{name}-{theme}.svg"
            path.write_text(build(t, faces), encoding="utf-8")
            print(f"{path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
