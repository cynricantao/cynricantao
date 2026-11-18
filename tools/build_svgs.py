"""Build the animated terminal-style SVGs for the profile README.

Text is converted to JetBrains Mono glyph outlines (<path> defs + <use>), because
GitHub serves repo SVGs with CSP default-src 'none', which blocks embedded fonts.
Animations are CSS keyframes (style-src 'unsafe-inline' is allowed) and SMIL.

usage: python tools/build_svgs.py <dir containing JetBrainsMono-*.ttf>
needs: fonttools, pyfiglet
"""
import math
import os
import sys

import pyfiglet
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")
FONT_DIR = os.environ.get("JBM_DIR") or (sys.argv[1] if len(sys.argv) > 1 else "fonts")

P = dict(bg="#1a1b26", bg2="#16161e", surf="#1f2335", surf2="#24283b", line="#292e42",
         line2="#3b4261", fg="#c0caf5", fg2="#a9b1d6", mute="#565f89", blue="#7aa2f7",
         cyan="#7dcfff", purple="#bb9af7", green="#9ece6a", orange="#ff9e64", red="#f7768e",
         yellow="#e0af68", teal="#73daca", dim="#737aa2", black="#414868")


class Font:
    def __init__(self, fname, key):
        self.f = TTFont(os.path.join(FONT_DIR, fname))
        self.gs = self.f.getGlyphSet()
        self.cmap = self.f.getBestCmap()
        self.key = key
        self.upm = self.f["head"].unitsPerEm
        self.adv = self.f["hmtx"][self.cmap[ord("M")]][0]

    def cw(self, size):
        return size * self.adv / self.upm

    def bbox(self, ch):
        g = self.f["glyf"][self.cmap[ord(ch)]]
        return g.yMin, g.yMax


R = Font("JetBrainsMono-Regular.ttf", "r")
B = Font("JetBrainsMono-Bold.ttf", "b")
X = Font("JetBrainsMono-ExtraBold.ttf", "x")


class Doc:
    def __init__(self, w, h, title):
        self.w, self.h, self.title = w, h, title
        self.glyphs, self.defs, self.css, self.body = {}, [], [], []
        self._n = 0

    def uid(self, p="u"):
        self._n += 1
        return f"{p}{self._n}"

    def ref(self, font, ch):
        gid = f"{font.key}{ord(ch):x}"
        if gid not in self.glyphs:
            pen = SVGPathPen(font.gs)
            font.gs[font.cmap[ord(ch)]].draw(pen)
            self.glyphs[gid] = pen.getCommands()
        return gid

    def text(self, s, x, y, size, color, font=R, attrs=""):
        """Glyph-outline text, baseline at y. color: hex or f(i)->hex."""
        k = size / font.upm
        uses = []
        for i, ch in enumerate(s):
            if ch == " ":
                continue
            gid = self.ref(font, ch)
            if not self.glyphs[gid]:
                continue
            fill = f' fill="{color(i)}"' if callable(color) else ""
            uses.append(f'<use href="#{gid}" x="{i * font.adv}"{fill}/>')
        base = "" if callable(color) else f' fill="{color}"'
        return (f'<g transform="translate({x:.1f} {y:.1f}) scale({k:.5f} {-k:.5f})"{base}{attrs}>'
                + "".join(uses) + "</g>")

    def spans(self, parts, x, y, size, font=R):
        out, cx = [], x
        for s, c, *f in parts:
            fnt = f[0] if f else font
            out.append(self.text(s, cx, y, size, c, fnt))
            cx += fnt.cw(size) * len(s)
        return "".join(out), cx

    def typing(self, inner, x, y, size, n, begin, per=0.045, font=R):
        """Reveal `inner` char by char (discrete SMIL clip)."""
        cid = self.uid("t")
        cw = font.cw(size)
        vals = ";".join(f"{i * cw:.1f}" for i in range(n + 1))
        kts = ";".join(f"{i / n:.4f}" for i in range(n + 1))
        self.defs.append(
            f'<clipPath id="{cid}"><rect x="{x - 2:.1f}" y="{y - size * 1.15:.1f}" width="0" height="{size * 1.6:.1f}">'
            f'<animate attributeName="width" values="{vals}" keyTimes="{kts}" calcMode="discrete" '
            f'dur="{n * per:.2f}s" begin="{begin:.2f}s" fill="freeze"/></rect></clipPath>')
        return f'<g clip-path="url(#{cid})">{inner}</g>'

    def render(self):
        css = "\n".join(self.css) + "\n@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
        glyph_defs = "".join(f'<path id="{k}" d="{d}"/>' for k, d in self.glyphs.items() if d)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{self.title}">'
                f"<title>{self.title}</title><style>{css}</style>"
                f"<defs>{glyph_defs}{''.join(self.defs)}</defs>{''.join(self.body)}</svg>")

    def save(self, name, out=None):
        out = out or OUT
        os.makedirs(out, exist_ok=True)
        path = os.path.join(out, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.render())
        print(f"{name}: {os.path.getsize(path) / 1024:.0f} KB")


def lerp_hex(stops, t):
    t = min(max(t, 0), 1)
    seg = t * (len(stops) - 1)
    i = min(int(seg), len(stops) - 2)
    f = seg - i
    a = [int(stops[i][j:j + 2], 16) for j in (1, 3, 5)]
    b = [int(stops[i + 1][j:j + 2], 16) for j in (1, 3, 5)]
    return "#" + "".join(f"{round(a[k] + (b[k] - a[k]) * f):02x}" for k in range(3))


COMMON_CSS = """
.blink{animation:blink 1.05s steps(1) infinite}
@keyframes blink{0%,50%{opacity:1}50.01%,100%{opacity:0}}
.drift{animation:drift 14s ease-in-out infinite alternate}
.drift2{animation:drift2 17s ease-in-out infinite alternate}
@keyframes drift{from{transform:translate(0,0)}to{transform:translate(90px,30px)}}
@keyframes drift2{from{transform:translate(0,0)}to{transform:translate(-110px,-25px)}}
.scan{animation:scan 7s linear infinite}
@keyframes scan{from{transform:translateY(-140px)}to{transform:translateY(760px)}}
.pulse{animation:pulse 2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
.rise{animation:rise .55s cubic-bezier(.2,.7,.2,1) both}
@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.flow{animation:flow 1.1s linear infinite}
@keyframes flow{to{stroke-dashoffset:-32}}
"""


def window(d, title, glow=True):
    """Reserve a slot for terminal chrome; close() fills it once the final height is known."""
    d._win = (len(d.body), title, glow)
    d.body.append("")


def close(d):
    idx, title, glow = d._win
    w, h = d.w, d.h
    clip = d.uid("c")
    d.defs.append(f'<clipPath id="{clip}"><rect width="{w}" height="{h}" rx="14"/></clipPath>')
    d.defs.append(f'<radialGradient id="gA"><stop offset="0" stop-color="{P["blue"]}" stop-opacity=".22"/>'
                  f'<stop offset="1" stop-color="{P["blue"]}" stop-opacity="0"/></radialGradient>')
    d.defs.append(f'<radialGradient id="gB"><stop offset="0" stop-color="{P["purple"]}" stop-opacity=".18"/>'
                  f'<stop offset="1" stop-color="{P["purple"]}" stop-opacity="0"/></radialGradient>')
    d.defs.append(f'<pattern id="dots" width="26" height="26" patternUnits="userSpaceOnUse">'
                  f'<circle cx="1.5" cy="1.5" r="1.1" fill="{P["line2"]}"/></pattern>')
    d.defs.append('<pattern id="scanl" width="4" height="3" patternUnits="userSpaceOnUse">'
                  '<rect width="4" height="1" fill="#000" opacity=".22"/></pattern>')
    d.defs.append(f'<linearGradient id="scanb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{P["cyan"]}" stop-opacity="0"/>'
                  f'<stop offset=".5" stop-color="{P["cyan"]}" stop-opacity=".05"/><stop offset="1" stop-color="{P["cyan"]}" stop-opacity="0"/></linearGradient>')
    d.defs.append('<radialGradient id="fade" cx=".5" cy=".45" r=".65"><stop offset="0" stop-color="#fff" stop-opacity=".55"/>'
                  '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
                  f'<mask id="dmask"><rect width="{w}" height="{h}" fill="url(#fade)"/></mask>')
    pre = [f'<g clip-path="url(#{clip})"><rect width="{w}" height="{h}" fill="{P["bg"]}"/>']
    if glow:
        pre.append(f'<g class="drift"><ellipse cx="{w * .18:.0f}" cy="{h * .3:.0f}" rx="{w * .38:.0f}" ry="{h * .7:.0f}" fill="url(#gA)"/></g>'
                   f'<g class="drift2"><ellipse cx="{w * .85:.0f}" cy="{h * .85:.0f}" rx="{w * .36:.0f}" ry="{h * .7:.0f}" fill="url(#gB)"/></g>')
    pre.append(f'<rect width="{w}" height="{h}" fill="url(#dots)" mask="url(#dmask)"/>')
    pre.append(f'<rect width="{w}" height="44" fill="{P["bg2"]}"/><rect y="44" width="{w}" height="1" fill="{P["line"]}"/>')
    for i, c in enumerate((P["red"], P["yellow"], P["green"])):
        pre.append(f'<circle cx="{26 + i * 22}" cy="22" r="6.5" fill="{c}"/>')
    pre.append(d.text(title, (w - R.cw(13) * len(title)) / 2, 27, 13, P["dim"]))
    d.body[idx] = "".join(pre)
    d.body.append(f'<rect width="{w}" height="{h}" fill="url(#scanl)" opacity=".5"/>'
                  f'<g class="scan"><rect y="0" width="{w}" height="140" fill="url(#scanb)"/></g></g>'
                  f'<rect x=".75" y=".75" width="{w - 1.5}" height="{h - 1.5}" rx="13.5" fill="none" stroke="{P["line2"]}" stroke-width="1.5"/>')


def prompt(d, cmd, x, y, size, begin, path="~"):
    head, cx = d.spans([("cynric", P["cyan"], B), ("@", P["mute"]), ("github", P["blue"], B),
                        (" " + path + " ", P["purple"]), ("❯ ", P["green"], B)], x, y, size)
    d.body.append(head)
    d.body.append(d.typing(d.text(cmd, cx, y, size, P["fg"]), cx, y, size, len(cmd), begin))
    return cx + R.cw(size) * len(cmd), begin + len(cmd) * 0.045


# ───────────────────────── hero ─────────────────────────
def hero():
    d = Doc(1200, 440, "Cynric Antao: AI agents, open source, shipping apps")
    d.css.append(COMMON_CSS + """
.gr{animation:gr 7s steps(1) infinite}.gc{animation:gc 7s steps(1) infinite}
@keyframes gr{0%,90%,100%{opacity:0;transform:none}91%{opacity:.7;transform:translate(-5px,1px)}92%{opacity:0}94%{opacity:.5;transform:translate(4px,-2px)}95%{opacity:0}}
@keyframes gc{0%,90%,100%{opacity:0;transform:none}91%{opacity:.7;transform:translate(5px,-1px)}92%{opacity:0}94%{opacity:.5;transform:translate(-3px,2px)}95%{opacity:0}}
""")
    window(d, "cynric@hermes: ~")
    _, t = prompt(d, "whoami", 48, 88, 16, 0.4)

    art = [l.rstrip() for l in pyfiglet.figlet_format("CYNRIC ANTAO", font="ansi_shadow", width=300).split("\n")]
    art = [l for l in art if l.strip()]
    cols = max(len(l) for l in art)
    size = min(17.0, 1100 / (cols * 0.6))
    k = size / X.upm
    y0, y1 = X.bbox("█")
    pitch = (y1 - y0) * k
    top = 112
    grad = (P["blue"], P["purple"], P["cyan"])
    rows_main, rows_r, rows_c = [], [], []
    for r, line in enumerate(art):
        base = top + r * pitch + y1 * k
        delay = t + 0.25 + r * 0.09
        rows_main.append(f'<g class="rise" style="animation-delay:{delay:.2f}s">'
                         + d.text(line, 48, base, size, lambda i: lerp_hex(grad, i / cols), X) + "</g>")
        rows_r.append(d.text(line, 48, base, size, P["red"], X))
        rows_c.append(d.text(line, 48, base, size, P["cyan"], X))
    d.body.append(f'<g class="gr">{"".join(rows_r)}</g><g class="gc">{"".join(rows_c)}</g>')
    d.body.append("".join(rows_main))
    art_bottom = top + len(art) * pitch

    y = art_bottom + 48
    t2 = t + 0.25 + len(art) * 0.09 + 0.4
    _, t3 = prompt(d, "cat focus.txt", 48, y, 16, t2)

    # looping type/erase tagline
    phrases = ["building tools for AI agents",
               "shipping Android & iOS apps",
               "open-source plugins for Hermes Agent",
               "editing YouTube in DaVinci Resolve Studio"]
    ty, size2 = y + 40, 21
    cw = R.cw(size2)
    x0 = 48 + R.cw(size2) * 2
    d.body.append(d.text("→", 48, ty, size2, P["green"]))
    per_t, per_e, hold, gap = 0.055, 0.025, 1.8, 0.35
    spans_t = []
    T = sum(len(p) * (per_t + per_e) + hold + gap for p in phrases)
    start = t3 + 0.3
    cur_points = []  # (time, x)
    acc = 0.0
    for p in phrases:
        n = len(p)
        pts = [(0.0, 0.0)]
        for i in range(1, n + 1):
            pts.append((acc + i * per_t, i * cw))
        te = acc + n * per_t + hold
        for i in range(1, n + 1):
            pts.append((te + i * per_e, (n - i) * cw))
        pts.append((T, 0.0))
        cur_points += pts[1:-1]
        cid = d.uid("lp")
        ktimes = ";".join(f"{a / T:.5f}" for a, _ in pts)
        vals = ";".join(f"{v:.1f}" for _, v in pts)
        d.defs.append(f'<clipPath id="{cid}"><rect x="{x0 - 1:.1f}" y="{ty - 26}" width="0" height="36">'
                      f'<animate attributeName="width" values="{vals}" keyTimes="{ktimes}" calcMode="discrete" '
                      f'dur="{T:.2f}s" begin="{start:.2f}s" repeatCount="indefinite"/></rect></clipPath>')
        spans_t.append(f'<g clip-path="url(#{cid})">' + d.text(p, x0, ty, size2, P["fg"]) + "</g>")
        acc += n * (per_t + per_e) + hold + gap
    d.body.append("".join(spans_t))
    cur_points = [(0.0, 0.0)] + sorted(cur_points) + [(T, 0.0)]
    kt = ";".join(f"{a / T:.5f}" for a, _ in cur_points)
    vx = ";".join(f"{x0 + v + 2:.1f}" for _, v in cur_points)
    d.body.append(f'<g class="blink"><rect x="{x0 + 2}" y="{ty - 19}" width="{cw * .9:.1f}" height="24" fill="{P["blue"]}" opacity=".9">'
                  f'<animate attributeName="x" values="{vx}" keyTimes="{kt}" calcMode="discrete" dur="{T:.2f}s" '
                  f'begin="{start:.2f}s" repeatCount="indefinite"/></rect></g>')

    # status chips
    cy = ty + 34
    chips = [("●", "hermes agent: online", P["green"], True),
             ("◆", "BSc CS · University of London", P["blue"], False),
             ("◆", "open to collaborate", P["purple"], False)]
    cx = 48
    for i, (icon, label, col, pulse) in enumerate(chips):
        wch = R.cw(13) * (len(label) + 3) + 24
        delay = 0.6 + i * 0.15
        dot = d.text(icon, cx + 14, cy + 22, 13, col)
        if pulse:
            dot = f'<g class="pulse">{dot}</g>'
        d.body.append(f'<g class="rise" style="animation-delay:{delay:.2f}s">'
                      f'<rect x="{cx}" y="{cy}" width="{wch:.0f}" height="32" rx="16" fill="{P["surf"]}" stroke="{P["line2"]}"/>'
                      + dot + d.text(label, cx + 14 + R.cw(13) * 2, cy + 21, 13, P["fg2"]) + "</g>")
        cx += wch + 12
    d.h = int(cy + 32 + 34)
    close(d)
    d.save("hero.svg")


# ───────────────────────── about (neofetch) ─────────────────────────
def about():
    d = Doc(1200, 560, "About Cynric, neofetch style")
    d.css.append(COMMON_CSS + """
.wave{animation:wave 3.2s ease-in-out infinite}
@keyframes wave{0%,100%{opacity:.45}50%{opacity:1}}
""")
    window(d, "neofetch")
    # isometric cube logo
    cols, rows, size = 55, 27, 11.5
    cw, pitch = R.cw(size), 14.4
    ox, oy = 46, 80
    Rr = 172
    cx, cy = ox + cols * cw / 2, oy + rows * pitch / 2 + 6
    c30 = math.cos(math.pi / 6)
    V = dict(t=(cx, cy - Rr), ur=(cx + Rr * c30, cy - Rr / 2), lr=(cx + Rr * c30, cy + Rr / 2),
             b=(cx, cy + Rr), ll=(cx - Rr * c30, cy + Rr / 2), ul=(cx - Rr * c30, cy - Rr / 2), c=(cx, cy))

    def inside(pt, poly):
        x, y = pt
        sign = None
        for i in range(len(poly)):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % len(poly)]
            cr = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
            s = cr >= 0
            if sign is None:
                sign = s
            elif s != sign:
                return False
        return True

    faces = [([V["t"], V["ur"], V["c"], V["ul"]], "▓", (P["cyan"], P["teal"])),
             ([V["ul"], V["c"], V["b"], V["ll"]], "▒", (P["blue"], P["blue"])),
             ([V["c"], V["ur"], V["lr"], V["b"]], "░", (P["purple"], P["purple"]))]
    hexp = " ".join(f"{V[k][0]:.1f},{V[k][1]:.1f}" for k in ("t", "ur", "lr", "b", "ll", "ul"))
    for fi, (poly, ch, (c1, c2)) in enumerate(faces):
        cid = f"face{fi}"
        d.defs.append(f'<clipPath id="{cid}"><polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in poly)}"/></clipPath>')
        colgroups = {}
        for r in range(rows):
            for c in range(cols):
                x0_, y0_ = ox + c * cw, oy + r * pitch
                probe = [(x0_ + a * cw, y0_ + b * pitch) for a in (0, .5, 1) for b in (0, .5, 1)]
                if any(inside(pt, poly) for pt in probe):
                    colgroups.setdefault(c, []).append((r, lerp_hex((c1, c2), r / rows)))
        d.body.append(f'<g clip-path="url(#{cid})">')
        for c, cells in sorted(colgroups.items()):
            parts = [d.text(ch, ox + c * cw, oy + (r + 1) * pitch - 3, size, col) for r, col in cells]
            d.body.append(f'<g class="wave" style="animation-delay:{c * 0.07:.2f}s">{"".join(parts)}</g>')
        d.body.append("</g>")
    d.defs.append('<filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3"/></filter>')
    inner = (f'M{V["ul"][0]:.1f} {V["ul"][1]:.1f}L{cx:.1f} {cy:.1f}L{V["ur"][0]:.1f} {V["ur"][1]:.1f}'
             f'M{cx:.1f} {cy:.1f}L{V["b"][0]:.1f} {V["b"][1]:.1f}')
    d.body.append(f'<g class="pulse" style="animation-duration:4s"><polygon points="{hexp}" fill="none" stroke="{P["cyan"]}" stroke-width="5" opacity=".35" filter="url(#glow)"/></g>'
                  f'<polygon points="{hexp}" fill="none" stroke="{P["cyan"]}" stroke-width="1.6" stroke-linejoin="round" opacity=".9"/>'
                  f'<path d="{inner}" fill="none" stroke="{P["fg"]}" stroke-width="1.2" opacity=".55"/>')

    # info column
    x = 500
    y = 96
    head, _ = d.spans([("cynric", P["cyan"], B), ("@", P["fg"]), ("github", P["blue"], B)], x, y, 20)
    d.body.append(f'<g class="rise" style="animation-delay:.2s">{head}'
                  + d.text("─" * 13, x, y + 22, 20, P["line2"]) + "</g>")
    info = [("User", "Cynric Antao"),
            ("Study", "BSc Computer Science · University of London"),
            ("Role", "Mobile developer · Video editor"),
            ("Shell", "Hermes Agent (my daily driver)"),
            ("Building", "Vanoa · fitness app for Android & iOS"),
            ("Languages", "Kotlin · Swift · TypeScript · Python · Rust"),
            ("Open source", "Hermes plugins · Omarchy desktop widgets"),
            ("Learning", "Rust · SwiftUI · agent harnesses"),
            ("Editing", "DaVinci Resolve Studio · Arabic YouTube"),
            ("Also", "Roblox experiences with my group"),
            ("Motto", "Ship it, measure it, cut what doesn't work.")]
    y += 62
    keyw = 13
    for i, (k_, v) in enumerate(info):
        line, _ = d.spans([(k_, P["blue"], B), (":", P["mute"]), (" " * (keyw - len(k_)), P["fg"]),
                           (v, P["fg"] if k_ != "Motto" else P["green"])], x, y, 16)
        d.body.append(f'<g class="rise" style="animation-delay:{.35 + i * .09:.2f}s">{line}</g>')
        y += 29
    y += 6
    pal = [P["black"], P["red"], P["green"], P["yellow"], P["blue"], P["purple"], P["cyan"], P["fg"]]
    for i, c in enumerate(pal):
        d.body.append(f'<rect class="rise" style="animation-delay:{1.45 + i * .05:.2f}s" x="{x + i * 38}" y="{y}" width="34" height="18" rx="3" fill="{c}" stroke="{P["line2"]}"/>')
    d.h = int(max(y + 18, oy + rows * pitch) + 36)
    close(d)
    d.save("about.svg")


# ───────────────────────── agents pipeline ─────────────────────────
def agents():
    d = Doc(1200, 640, "How Cynric works with AI agents")
    d.css.append(COMMON_CSS)
    window(d, "hermes status --graph")

    def box(x, y, w, h, title, tcol, lines, delay, lsize=13, badge=None):
        g = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{P["surf"]}" fill-opacity=".92" stroke="{P["line2"]}"/>',
             f'<rect x="{x}" y="{y}" width="3" height="{h}" rx="1.5" fill="{tcol}"/>',
             d.text(title, x + 18, y + 27, 15, tcol, B)]
        if badge:
            bx = x + w - 18 - R.cw(12) * len(badge[0]) - 16
            g.append(f'<g class="pulse">{d.text("●", bx, y + 26, 12, P["green"])}</g>' + d.text(badge[0], bx + 16, y + 26, 12, P["green"]))
        ly = y + 52
        for ln in lines:
            if isinstance(ln, tuple):
                s, _ = d.spans([(ln[0].ljust(8), P["cyan"]), (ln[1], P["fg2"])], x + 18, ly, lsize)
                g.append(s)
            else:
                g.append(d.text(ln, x + 18, ly, lsize, P["fg2"]))
            ly += lsize + 9
        return f'<g class="rise" style="animation-delay:{delay:.2f}s">{"".join(g)}</g>'

    paths = []

    def link(dpath, col, begin):
        pid = d.uid("p")
        d.defs.append(f'<path id="{pid}" d="{dpath}"/>')
        paths.append(f'<path d="{dpath}" fill="none" stroke="{P["line2"]}" stroke-width="2"/>'
                     f'<path class="flow" d="{dpath}" fill="none" stroke="{col}" stroke-opacity=".75" stroke-width="2" stroke-dasharray="6 10"/>'
                     f'<circle r="4" fill="{col}"><animateMotion dur="2.6s" begin="{begin:.2f}s" repeatCount="indefinite" rotate="auto">'
                     f'<mpath href="#{pid}"/></animateMotion></circle>')

    # geometry
    A = (40, 122, 250, 150)
    C = (360, 100, 450, 194)
    Wk = [(880, 100 + i * 66, 280, 62) for i in range(3)]
    outs_y, outs_h, outs_w = 372, 132, 260
    outs_x = [40 + i * (outs_w + 30) for i in range(4)]

    link(f"M{A[0] + A[2]} {A[1] + 75} C{A[0] + A[2] + 40} {A[1] + 75},{C[0] - 40} {C[1] + 97},{C[0]} {C[1] + 97}", P["green"], 0)
    for i, (x, y, w, h) in enumerate(Wk):
        sy = C[1] + 55 + i * 44
        link(f"M{C[0] + C[2]} {sy} C{C[0] + C[2] + 40} {sy},{x - 40} {y + h / 2},{x} {y + h / 2}", P["purple"], .3 + i * .4)
    for i, x in enumerate(outs_x):
        sx = C[0] + 75 + i * 100
        link(f"M{sx} {C[1] + C[3]} C{sx} {C[1] + C[3] + 40},{x + outs_w / 2} {outs_y - 40},{x + outs_w / 2} {outs_y}", P["blue"], .5 + i * .35)
    d.body.append("".join(paths))

    d.body.append(box(*A, "YOU", P["green"], ["one-line spec", "Hermes desktop app", "TUI · Telegram", "approve risky steps"], .2))
    d.body.append(box(*C, "HERMES AGENT", P["blue"], [("memory", "Hindsight, long-term recall"),
                                                      ("skills", "workflows that improve"),
                                                      ("cron", "scheduled jobs and digests"),
                                                      ("search", "self-hosted SearXNG"),
                                                      ("guard", "asks before post/spend/ship")], .35, 14, badge=("online",)))
    workers = [("CLAUDE CODE", "Kotlin, Swift, big refactors"), ("DEEPSEEK V4.1 FLASH", "bulk + background work"),
               ("SUBAGENTS", "parallel research, translation")]
    for i, ((x, y, w, h), (t, s)) in enumerate(zip(Wk, workers)):
        d.body.append(box(x, y, w, h, t, P["purple"], [s], .5 + i * .1, lsize=13))
    outs = [("APPS", P["cyan"], ["review PRs", "build + emulator test", "merge what passes"]),
            ("VIDEO", P["orange"], ["Resolve via Python API", "VO, music, SFX, titles", "Arabic audio, English subs"]),
            ("RESEARCH", P["yellow"], ["web + GitHub digests", "cited, dated sources", "daily ecosystem cron"]),
            ("DESKTOP", P["teal"], ["Windows 11 tuning", "GPU, display, storage", "backups that get checked"])]
    for i, (x, (t, col, lines)) in enumerate(zip(outs_x, outs)):
        d.body.append(box(x, outs_y, outs_w, outs_h, t, col, lines, .9 + i * .12))
    note, _ = d.spans([("rule: ", P["dim"]), ("anything that posts, spends, deletes or ships waits for my yes.", P["fg2"])], 40, outs_y + outs_h + 44, 14)
    d.body.append(f'<g class="rise" style="animation-delay:1.5s">{note}</g>')
    d.h = outs_y + outs_h + 70
    close(d)
    d.save("agents.svg")


# ───────────────────────── section headers ─────────────────────────
def header(name, path, cmd):
    d = Doc(1200, 64, f"{path} {cmd}")
    d.css.append(COMMON_CSS + """
.sweep{animation:sweep 4.5s ease-in-out infinite}
@keyframes sweep{from{transform:translateX(-300px)}to{transform:translateX(1250px)}}
""")
    d.defs.append(f'<linearGradient id="hl" x1="0" x2="1"><stop offset="0" stop-color="{P["blue"]}"/><stop offset=".55" stop-color="{P["purple"]}" stop-opacity=".6"/>'
                  f'<stop offset="1" stop-color="{P["purple"]}" stop-opacity="0"/></linearGradient>'
                  f'<linearGradient id="sw" x1="0" x2="1"><stop offset="0" stop-color="{P["cyan"]}" stop-opacity="0"/><stop offset=".5" stop-color="{P["cyan"]}"/>'
                  f'<stop offset="1" stop-color="{P["cyan"]}" stop-opacity="0"/></linearGradient>')
    end, t = prompt(d, cmd, 4, 34, 21, 0.3, path)
    d.body.append(f'<g class="blink"><rect x="{end + 4:.1f}" y="17" width="11" height="22" fill="{P["blue"]}"/></g>')
    d.body.append(f'<rect x="4" y="54" width="1192" height="1.5" fill="url(#hl)"/>'
                  f'<g class="sweep"><rect x="0" y="53.5" width="240" height="2.5" fill="url(#sw)"/></g>')
    d.save(f"h-{name}.svg")


def footer():
    d = Doc(1200, 150, "exit")
    d.css.append(COMMON_CSS)
    window(d, "logout")
    end, t = prompt(d, "exit", 48, 86, 16, 0.4)
    msg = "connection to github.com/cynricantao closed. thanks for stopping by."
    d.body.append(f'<g class="rise" style="animation-delay:{t + .3:.2f}s">' + d.text(msg, 48, 118, 14, P["dim"]) + "</g>")
    d.body.append(f'<g class="blink"><rect x="{48 + R.cw(14) * len(msg) + 6:.1f}" y="104" width="9" height="17" fill="{P["blue"]}"/></g>')
    close(d)
    d.save("footer.svg")


if __name__ == "__main__":
    hero()
    about()
    agents()
    for args in [("about", "~", "neofetch"), ("agents", "~/agents", "cat how-i-work.md"),
                 ("stack", "~/stack", "ls --group"), ("stats", "~/github", "gh stats --live"),
                 ("activity", "~/github", "git log --graph"), ("connect", "~", "open links.txt")]:
        header(*args)
    footer()
