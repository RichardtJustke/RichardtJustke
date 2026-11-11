#!/usr/bin/env python3
"""Render the animated SVG cards of the profile README (purple edition).

Each block of the README is one SVG in cards/. GitHub shows them through <img>,
so there is no JavaScript and no external request: fonts and images are
embedded as base64 and animation is CSS @keyframes + SMIL.

    python scripts/render_cards.py            # live data (GITHUB_TOKEN / GH_TOKEN)
    STATIC=1 python scripts/render_cards.py   # final frame only, for screenshots

Live data: contribution calendar (heatmap, streak, monthly bars) and the
languages of repos pushed in the last 12 months. With the default Actions
token only public repos count; a personal token (CARDS_TOKEN secret) adds
private ones. Without any token the last saved data/github.json is used.
Requires Pillow (text measuring).
"""
from __future__ import annotations

import base64
import datetime as dt
import html
import json
import os
import sys
import urllib.request
from pathlib import Path

from PIL import ImageFont

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("OUT_DIR", ROOT / "cards"))
DATA = ROOT / "data" / "github.json"
USER = "RichardtJustke"
STATIC = os.environ.get("STATIC") == "1"

W = 880          # full-width card; README scales to the column
THIRD = W / 3    # three cards per row
P = 4            # inset, so neighbouring cards get an 8px gap

ACCENT = "#a78bfa"
TEXT, MUTED, DIM, FAINT = "#f4f4f5", "#a1a1aa", "#71717a", "#52525b"
CARD, LINE, LINE2 = "#000000", "rgba(255,255,255,.11)", "rgba(255,255,255,.08)"
GREEN, BLUE = "#00c758", "#60a5fa"

# ------------------------------------------------------------------ content
PILLS = ["Open to freelance projects", "Brasília, BR · UTC-3"]
FIRST, LAST = "Richardt", "Justke"
SUBTITLE = ("Software Engineer · Founder at ", "Ketsu")
LEAD = [("I build products end to end — from ", MUTED, False), ("pixel to server", TEXT, True), (".", MUTED, False)]
PROMPT = [("richardt@arch", GREEN), (":", MUTED), ("~/projects", BLUE), ("$", MUTED)]
COMMAND = "cd .."

ABOUT = [
    [("I'm a Computer Science student driven by ", 0), ("continuous learning and evolution", 1),
     (", transforming ideas into real solutions.", 0)],
    [("I work across the full stack with focus on ", 0), ("clean architecture, performance and visual consistency", 1), (".", 0)],
    [("I like building things that feel simple to use and solid under the hood. My workflow is shaped by a mix "
      "of design thinking, Linux, terminal tools and low-level curiosity.", 0)],
]
FACTS = [("studying", "JavaScript, TypeScript, React and Go"),
         ("goal", "Build scalable and well-designed systems"),
         ("beyond code", "Linux, terminal tooling & low-level concepts")]

TILES = [  # file, label, title, foot, style, foot arrow
    ("tile-build", "BUILD", "Ketsu studio", "ketsu.dev", "accent", "up"),
    ("tile-ship", "SHIP", "Folio", "Qt 6 · QML · C++", "light", "right"),
    ("tile-write", "WRITE", "The blog", "Oct 2026 · latest post", "outline", "right"),
]
REPOS = [
    ("repo-folio", "Folio", "2026", "folio.jpg", "Finder-style file manager for Linux and Wayland.", "Qt 6 · QML · C++"),
    ("repo-nexo", "Nexo", "2026", "nexo.jpg", "A personal operating system: tasks, habits, money and AI.", "React · TypeScript · Vite"),
    ("repo-cli", "Justke-cli", "2026", "justke-cli.jpg", "My portfolio doesn't have a homepage. It has a prompt.", "JavaScript · Bash"),
]
CONTACT = [
    ("link-email", "EMAIL", "rj.justke@gmail.com", True),
    ("link-portfolio", "PORTFOLIO", "richardtjustke.tech", False),
    ("link-linkedin", "LINKEDIN", "/in/rjustke", False),
    ("link-instagram", "INSTAGRAM", "@heyy.justke", False),
    ("link-github", "GITHUB", "@RichardtJustke", False),
    ("link-ketsu", "STUDIO", "ketsu.dev", False),
]
LANG_FALLBACK_COLOR = "#52525b"

# ------------------------------------------------------------------ fonts
FONT_FILES = {"sans": "inter-latin-400-normal", "sans600": "inter-latin-600-normal", "mono": "geist-mono-latin-400-normal"}
_M = {k: ImageFont.truetype(str(HERE / "fonts" / f"{v}.woff"), 100) for k, v in FONT_FILES.items()}


def tw(s: str, size: float, font: str = "sans", ls: float = 0) -> float:
    return _M[font].getlength(s) * size / 100 + ls * len(s)


def _font_css() -> str:
    out = []
    for fam, weight, key in [("Inter", 400, "sans"), ("Inter", 600, "sans600"), ("Geist Mono", 400, "mono")]:
        b64 = base64.b64encode((HERE / "fonts" / f"{FONT_FILES[key]}.woff2").read_bytes()).decode()
        out.append(f"@font-face{{font-family:'{fam}';font-weight:{weight};src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "".join(out)


FONT_CSS = _font_css()


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def wrap(text: str, max_w: float, size: float, font="sans") -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}" if cur else word
        if cur and tw(trial, size, font) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def rich_wrap(segments, max_w: float, size: float) -> list[list[tuple[str, int]]]:
    """Wrap [(text, bold)] by measured width; returns lines of (piece, bold)."""
    words, trailing = [], False
    for text, bold in segments:
        for k, word in enumerate(text.split(" ")):
            if word:
                words.append((word, bold, bool(words) and (k > 0 or trailing)))
        trailing = text.endswith(" ")
    lines, cur, cur_w = [], [], 0.0
    for word, bold, space in words:
        font = "sans600" if bold else "sans"
        piece = (" " if space and cur else "") + word
        w = tw(piece, size, font)
        if cur and space and cur_w + w > max_w:
            lines.append(cur)
            cur, cur_w, piece = [], 0.0, word
            w = tw(piece, size, font)
        cur.append((piece, bold))
        cur_w += w
    return lines + [cur]


# ------------------------------------------------------------------ svg helpers
BASE_CSS = """
text{font-family:'Inter',ui-sans-serif,system-ui,sans-serif}
.m{font-family:'Geist Mono',ui-monospace,SFMono-Regular,Menlo,monospace}
.b{font-weight:600}
.rise{animation:rise .7s cubic-bezier(.2,.8,.2,1) both}
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.fade{animation:fade .6s ease both}
@keyframes fade{from{opacity:0}to{opacity:1}}
.pop{transform-box:fill-box;transform-origin:center;animation:pop .45s cubic-bezier(.2,.8,.2,1) both}
@keyframes pop{from{opacity:0;transform:translateY(6px) scale(.7)}to{opacity:1;transform:none}}
.grow{transform-box:fill-box;transform-origin:bottom;animation:grow .8s cubic-bezier(.2,.8,.2,1) both}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
.growx{transform-box:fill-box;transform-origin:left;animation:growx .6s cubic-bezier(.2,.8,.2,1) both}
@keyframes growx{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.ring{transform-box:fill-box;transform-origin:center;animation:ring 2s ease-out infinite}
@keyframes ring{0%{transform:scale(1);opacity:.7}70%,100%{transform:scale(2.6);opacity:0}}
.nudge{animation:nudge 3s ease-in-out 2s infinite}
@keyframes nudge{0%,70%,100%{transform:none}80%{transform:translate(2px,-2px)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def svg(width: float, height: float, body: str) -> str:
    css = FONT_CSS + BASE_CSS + ("*{animation:none!important}" if STATIC else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{width:g}" height="{height:g}" viewBox="0 0 {width:g} {height:g}" role="img">'
            f"<style>{css}</style>{body}</svg>")


def d(sec: float) -> str:
    return f'style="animation-delay:{sec:.2f}s"'


def card(w: float, h: float, fill: str = CARD, stroke: str = LINE, r: int = 14) -> str:
    st = f'stroke="{stroke}"' if stroke else ""
    return f'<rect x="{P + .5:g}" y="{P + .5:g}" width="{w - 2 * P - 1:g}" height="{h - 2 * P - 1:g}" rx="{r}" fill="{fill}" {st}/>'


def hline(x1, x2, y, color=LINE2) -> str:
    return f'<line x1="{x1:g}" x2="{x2:g}" y1="{y + .5:g}" y2="{y + .5:g}" stroke="{color}"/>'


def label(x, y, text, color=MUTED, size=11, extra="") -> str:
    return f'<text x="{x:g}" y="{y:g}" class="m" font-size="{size}" letter-spacing="1.2" fill="{color}" {extra}>{esc(text)}</text>'


def section_head(x, y, num, title) -> str:
    return (f'<text x="{x:g}" y="{y:g}" class="m" font-size="13" fill="{ACCENT}">{num}</text>'
            f'<text x="{x + 26:g}" y="{y:g}" class="b" font-size="17" fill="{TEXT}">{esc(title)}</text>')


def arrow(x, y, color, kind="right") -> str:
    path = f"M{x:g} {y:g}h8m-3-3 3 3-3 3" if kind == "right" else f"M{x:g} {y + 7:g}l7-7m-5 0h5v5"
    return (f'<g class="nudge"><path d="{path}" fill="none" stroke="{color}" stroke-width="1.4" '
            f'stroke-linecap="round" stroke-linejoin="round"/></g>')


def status_dot(cx, cy) -> str:
    return (f'<circle cx="{cx:g}" cy="{cy:g}" r="3.5" fill="{GREEN}"/>'
            f'<circle class="ring" cx="{cx:g}" cy="{cy:g}" r="3.5" fill="none" stroke="{GREEN}"/>')


def embed(name: str, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode((HERE / "assets" / name).read_bytes()).decode()


def typing(uid, x, y_top, h, text, size, font, ls, begin, dur, final_hold=False) -> tuple[str, str, float]:
    """clipPath that reveals `text` one character at a time (SMIL), plus the x values for a caret."""
    widths = [0.0] + [tw(text[:i], size, font, ls) for i in range(1, len(text) + 1)]
    full = widths[-1] + 6
    if STATIC:
        clip = f'<clipPath id="{uid}"><rect x="{x:g}" y="{y_top:g}" width="{full:.1f}" height="{h}"/></clipPath>'
    else:
        vals = ";".join(f"{w + (2 if w else 0):.1f}" for w in widths[:-1]) + f";{full:.1f}"
        clip = (f'<clipPath id="{uid}"><rect x="{x:g}" y="{y_top:g}" width="0" height="{h}">'
                f'<animate attributeName="width" values="{vals}" calcMode="discrete" begin="{begin}s" '
                f'dur="{dur}s" fill="freeze"/></rect></clipPath>')
    caret_x = ";".join(f"{x + w + 4:.1f}" for w in widths)
    return clip, caret_x, x + widths[-1] + 4


# ------------------------------------------------------------------ data
QUERY = """query($login:String!){user(login:$login){
  contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}
  repositories(first:100, ownerAffiliations:OWNER, isFork:false, orderBy:{field:PUSHED_AT,direction:DESC}){
    nodes{pushedAt languages(first:10, orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}}}"""


def fetch_data() -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        try:
            req = urllib.request.Request(
                "https://api.github.com/graphql",
                data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
                headers={"Authorization": f"bearer {token}", "User-Agent": "readme-cards"})
            with urllib.request.urlopen(req, timeout=30) as r:
                user = json.load(r)["data"]["user"]
            cal = user["contributionsCollection"]["contributionCalendar"]
            since = (dt.date.today() - dt.timedelta(days=365)).isoformat()
            sizes, colors = {}, {}
            for repo in user["repositories"]["nodes"]:  # only aggregated sizes are stored, never repo names
                if repo["pushedAt"][:10] < since:
                    continue
                for e in repo["languages"]["edges"]:
                    n = e["node"]["name"]
                    sizes[n] = sizes.get(n, 0) + e["size"]
                    colors[n] = e["node"]["color"] or LANG_FALLBACK_COLOR
            data = {"total": cal["totalContributions"],
                    "days": [x for w in cal["weeks"] for x in w["contributionDays"]],
                    "languages": [{"name": n, "size": s, "color": colors[n]} for n, s in
                                  sorted(sizes.items(), key=lambda kv: -kv[1])]}
            DATA.parent.mkdir(exist_ok=True)
            DATA.write_text(json.dumps(data))
            return data
        except Exception as e:
            print(f"warning: GitHub API failed ({e}); using cached data", file=sys.stderr)
    return json.loads(DATA.read_text()) if DATA.exists() else {"total": 0, "days": [], "languages": []}


def stats(data: dict) -> dict:
    days = sorted(data["days"], key=lambda x: x["date"])
    counts = [x["contributionCount"] for x in days]
    streak, i = 0, len(counts) - 1
    if i >= 0 and counts[i] == 0:  # no commit yet today doesn't break the streak
        i -= 1
    while i >= 0 and counts[i]:
        streak, i = streak + 1, i - 1
    nonzero = sorted(c for c in counts if c)
    q = [nonzero[int(len(nonzero) * f)] if nonzero else 1 for f in (.25, .5, .75)]
    levels = [0 if c == 0 else 1 if c <= q[0] else 2 if c <= q[1] else 3 if c <= q[2] else 4 for c in counts]
    months: dict[str, int] = {}
    for x in days:
        months[x["date"][:7]] = months.get(x["date"][:7], 0) + x["contributionCount"]
    busiest = max(days, key=lambda x: x["contributionCount"]) if days else {"date": "2026-01-01", "contributionCount": 0}
    last_active = next((x["date"] for x in reversed(days) if x["contributionCount"]), None)
    gap = (dt.date.today() - dt.date.fromisoformat(last_active)).days if last_active else None
    last = "last commit today" if gap == 0 else "last commit yesterday" if gap == 1 else \
        f"last commit {gap} days ago" if gap is not None else "no commits yet"
    langs = data.get("languages", [])
    total_size = sum(l["size"] for l in langs) or 1
    top = langs[:9]
    shares = [(l["name"], l["size"] / total_size * 100, l["color"]) for l in top]
    rest = 100 - sum(s for _, s, _ in shares)
    if rest > .05:
        shares.append(("Other", rest, LANG_FALLBACK_COLOR))
    return dict(total=data["total"], streak=streak, active=sum(1 for c in counts if c), levels=levels,
                months=sorted(months.items())[-12:], busiest=busiest, last=last, langs=shares)


# ------------------------------------------------------------------ cards
def hero(s: dict) -> str:
    h, x = 300, 44
    b = [card(W, h)]
    px = x
    for i, text in enumerate(PILLS):
        live = i == 0
        pw = tw(text, 12, "mono") + (40 if live else 24)
        b.append(f'<g class="fade" {d(.05 + i * .08)}><rect x="{px + .5:g}" y="40.5" width="{pw - 1:.1f}" height="27" rx="13.5" '
                 f'fill="none" stroke="rgba(255,255,255,.18)"/>'
                 + (status_dot(px + 16, 54) if live else "")
                 + f'<text x="{px + (28 if live else 12):.1f}" y="58" class="m" font-size="12" fill="{TEXT}">{esc(text)}</text></g>')
        px += pw + 8

    # name typed line by line, with a caret that follows the letters
    c1, cx1, end1 = typing("n1", x, 88, 60, FIRST, 56, "sans600", -2, .3, .9)
    c2, cx2, end2 = typing("n2", x, 144, 60, LAST, 56, "sans600", -2, 1.35, .75)
    b.append(f"<defs>{c1}{c2}</defs>")
    b.append(f'<g clip-path="url(#n1)"><text x="{x}" y="134" class="b" font-size="56" letter-spacing="-2" fill="{TEXT}">{FIRST}</text></g>')
    b.append(f'<g clip-path="url(#n2)"><text x="{x}" y="190" class="b" font-size="56" letter-spacing="-2" fill="{TEXT}">{LAST}</text></g>')
    if STATIC:
        b.append(f'<rect x="{end2:.1f}" y="148" width="4" height="46" fill="{ACCENT}"/>')
    else:
        b.append(f'<rect y="92" width="4" height="46" fill="{ACCENT}" x="{x + 4}">'
                 f'<animate attributeName="x" values="{cx1}" calcMode="discrete" begin=".3s" dur=".9s" fill="freeze"/>'
                 f'<set attributeName="opacity" to="0" begin="1.25s" fill="freeze"/></rect>')
        b.append(f'<rect y="148" width="4" height="46" fill="{ACCENT}" x="{x + 4}" opacity="0">'
                 f'<set attributeName="opacity" to="1" begin="1.25s"/>'
                 f'<animate attributeName="x" values="{cx2}" calcMode="discrete" begin="1.35s" dur=".75s" fill="freeze"/>'
                 f'<animate attributeName="opacity" values="1;0" calcMode="discrete" dur="1s" begin="2.2s" repeatCount="indefinite"/></rect>')

    sub_a, sub_b = SUBTITLE
    b.append(f'<text x="{x}" y="232" font-size="16" fill="{MUTED}" class="rise" {d(2.1)}>{esc(sub_a)}<tspan fill="{ACCENT}">{esc(sub_b)}</tspan></text>')
    spans = "".join(f'<tspan fill="{c}"{" font-weight=\"600\"" if bold else ""}>{esc(t)}</tspan>' for t, c, bold in LEAD)
    b.append(f'<text x="{x}" y="270" font-size="17" class="rise" {d(2.25)}>{spans}</text>')

    # terminal: prompt + "cd .." typed + block cursor
    cmd_w = tw(COMMAND, 92, "mono", -2)
    rx = W - 44 - (cmd_w + 8 + 30)
    prompt = "".join(f'<tspan fill="{c}">{esc(t)}</tspan>' for t, c in PROMPT)
    b.append(f'<text x="{rx:.1f}" y="118" class="m fade" font-size="13" {d(2.3)}>{prompt}</text>')
    c3, cx3, end3 = typing("cmd", rx, 130, 90, COMMAND, 92, "mono", -2, 2.6, .9)
    b.append(f"<defs>{c3}</defs>")
    b.append(f'<g clip-path="url(#cmd)"><text x="{rx:.1f}" y="202" class="m" font-size="92" letter-spacing="-2" fill="{ACCENT}">{COMMAND}</text></g>')
    if STATIC:
        b.append(f'<rect x="{end3 + 4:.1f}" y="134" width="30" height="76" fill="{ACCENT}" opacity=".9"/>')
    else:
        cx3_shift = ";".join(f"{float(v) + 4:.1f}" for v in cx3.split(";"))
        b.append(f'<rect y="134" width="30" height="76" fill="{ACCENT}" opacity=".9" x="{rx + 4:.1f}">'
                 f'<animate attributeName="x" values="{cx3_shift}" calcMode="discrete" begin="2.6s" dur=".9s" fill="freeze"/>'
                 f'<animate attributeName="opacity" values=".9;0" calcMode="discrete" dur="1s" begin="0s" repeatCount="indefinite"/></rect>')
    b.append(f'<text x="{W - 24}" y="{h - 18}" class="m fade" font-size="11" fill="{FAINT}" text-anchor="end" {d(3.6)}>'
             f'zsh · {s["streak"]}-day streak · {esc(s["last"])}</text>')
    return svg(W, h, "".join(b))


def about() -> str:
    x, text_w, img_w, img_h = 36, W - 2 * P - 64 - 210 - 32, 210, 315
    y = 50
    b = [section_head(x, y, "01", "About me")]
    y += 34
    for pi, para in enumerate(ABOUT):
        for line in rich_wrap(para, text_w, 15):
            spans = "".join(f'<tspan fill="{TEXT if bold else MUTED}"{" font-weight=\"600\"" if bold else ""}>{esc(t)}</tspan>'
                            for t, bold in line)
            b.append(f'<text x="{x}" y="{y}" font-size="15" class="rise" {d(.15 + pi * .12)} xml:space="preserve">{spans}</text>')
            y += 24
        y += 12
    y += 4
    b.append(hline(x, x + text_w, y - 18))
    for i, (k, v) in enumerate(FACTS):
        b.append(f'<g class="rise" {d(.6 + i * .1)}><path d="M{x} {y + 2}h8m-3-3 3 3-3 3" fill="none" stroke="{ACCENT}" stroke-width="1.4" '
                 f'stroke-linecap="round" stroke-linejoin="round"/>'
                 f'<text x="{x + 16}" y="{y + 6}" class="m" font-size="12" fill="{ACCENT}">{esc(k)}</text>'
                 f'<text x="{x + 150}" y="{y + 6}" font-size="14" fill="{TEXT}">{esc(v)}</text></g>')
        b.append(hline(x, x + text_w, y + 22))
        y += 40
    h = max(y + 10, img_h + 64)
    ix, iy = W - P - 32 - img_w, (h - img_h) / 2
    b.append(f'<defs><clipPath id="rb"><rect x="{ix}" y="{iy:g}" width="{img_w}" height="{img_h}" rx="10"/></clipPath></defs>'
             f'<g class="fade" {d(.3)}><image href="{embed("robot.gif", "image/gif")}" x="{ix}" y="{iy:g}" width="{img_w}" height="{img_h}" '
             f'preserveAspectRatio="xMidYMid slice" clip-path="url(#rb)"/>'
             f'<rect x="{ix + .5}" y="{iy + .5:g}" width="{img_w - 1}" height="{img_h - 1}" rx="10" fill="none" stroke="{LINE}"/></g>')
    return svg(W, h, card(W, h) + "".join(b))


def heatmap(s: dict) -> str:
    h, x0, top = 188, 36, 58
    ramp = ["rgba(255,255,255,.06)", ACCENT + "40", ACCENT + "73", ACCENT + "b3", ACCENT]
    b = [card(W, h), label(x0, 38, f'LAST 12 MONTHS · {s["total"]:,} CONTRIBUTIONS · {s["active"]} ACTIVE DAYS')]
    lx = W - 36 - tw("more", 10.5, "mono")
    b.append(f'<text x="{lx:.1f}" y="38" class="m" font-size="10.5" fill="{DIM}">more</text>')
    for i, c in enumerate(reversed(ramp)):
        b.append(f'<rect x="{lx - 18 - i * 14:.1f}" y="29" width="10" height="10" rx="2" fill="{c}"/>')
    b.append(f'<text x="{lx - 22 - 5 * 14:.1f}" y="38" class="m" font-size="10.5" fill="{DIM}" text-anchor="end">less</text>')
    levels = s["levels"]
    for w in range((len(levels) + 6) // 7):
        cells = "".join(f'<rect x="{x0 + w * 15}" y="{top + r * 15}" width="12" height="12" rx="3" fill="{ramp[levels[w * 7 + r]]}"/>'
                        for r in range(7) if w * 7 + r < len(levels))
        b.append(f'<g class="pop" {d(.2 + w * .03)}>{cells}</g>')
    return svg(W, h, "".join(b))


def activity(s: dict) -> str:
    h, x0 = 260, 36
    busy = s["busiest"]
    busy_day = dt.date.fromisoformat(busy["date"]).strftime("%b %-d")
    rows = [("CURRENT STREAK", f'{s["streak"]} days', 30, ACCENT),
            ("ACTIVE DAYS", f'{s["active"]}', 30, TEXT),
            ("BUSIEST DAY", f'{busy_day} · {busy["contributionCount"]} commits', 16, TEXT)]
    b = [card(W, h)]
    y = 48
    for i, (k, v, size, color) in enumerate(rows):
        b.append(f'<g class="rise" {d(2.0 + i * .15)}>{label(x0, y, k, size=10)}'
                 f'<text x="{x0}" y="{y + (34 if size == 30 else 24)}" class="b" font-size="{size}" fill="{color}">{esc(v)}</text></g>')
        y += 70 if size == 30 else 0
    divider = x0 + 200 + 32
    b.append(f'<line x1="{divider + .5}" x2="{divider + .5}" y1="30" y2="{h - 30}" stroke="{LINE2}"/>')
    months = s["months"]
    area_x, area_w, base, max_h = divider + 24, W - 36 - (divider + 24), 216, 150
    n = max(len(months), 1)
    gap = 10
    bw = (area_w - gap * (n - 1)) / n
    top_v = max((v for _, v in months), default=1) or 1
    best = max(range(n), key=lambda i: months[i][1]) if months else 0
    for i, (ym, v) in enumerate(months):
        bh = max(3, v / top_v * max_h)
        bx = area_x + i * (bw + gap)
        fill = ACCENT if i == best else "rgba(255,255,255,.12)"
        b.append(f'<rect class="grow" {d(2.2 + i * .09)} x="{bx:.1f}" y="{base - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="4" fill="{fill}"/>')
        lbl = dt.date(int(ym[:4]), int(ym[5:]), 1).strftime("%b")
        b.append(f'<text x="{bx + bw / 2:.1f}" y="{base + 18}" class="m" font-size="10" fill="{DIM}" text-anchor="middle">{lbl}</text>')
        if i == best:
            b.append(f'<text x="{bx + bw / 2:.1f}" y="{base - bh - 8:.1f}" class="m fade" font-size="10" fill="{ACCENT}" '
                     f'text-anchor="middle" {d(3.4)}>{v}</text>')
    return svg(W, h, "".join(b))


def tile(lbl, title, foot, style, kind, delay) -> str:
    w, h = THIRD, 150
    fill, fg, sub = {"accent": (ACCENT, "#000", "#000"), "light": (TEXT, "#000", "#000"),
                     "outline": (CARD, TEXT, MUTED)}[style]
    stroke = "rgba(255,255,255,.18)" if style == "outline" else ""
    fw = tw(foot, 11, "mono")
    body = (f'<g class="rise" {d(delay)}>{card(w, h, fill, stroke)}'
            f'{label(28, 38, lbl, sub)}'
            f'<text x="28" y="92" class="b" font-size="30" letter-spacing="-1" fill="{fg}">{esc(title)}</text>'
            f'<text x="28" y="126" class="m" font-size="11" fill="{sub}">{esc(foot)}</text>'
            f'{arrow(28 + fw + 8, 122 if kind == "right" else 118, sub, kind)}</g>')
    return svg(w, h, body)


def title_building() -> str:
    h = 60
    tx = 4 + 26 + tw("What I'm building", 17, "sans600") + 14
    return svg(W, h, f'<g class="fade">{section_head(8, 40, "02", "What I&#39;m building".replace("&#39;", "’"))}</g>'
                     f'<line class="growx" {d(.2)} x1="{tx:.0f}" x2="{W - 4}" y1="35.5" y2="35.5" stroke="rgba(255,255,255,.1)"/>')


def repo(title, year, img, desc, tech, delay) -> str:
    w, h = THIRD, 290
    ix, iy, iw, ih = P + 10, P + 10, w - 2 * P - 20, 150
    b = [card(w, h),
         f'<defs><clipPath id="ri"><rect x="{ix}" y="{iy}" width="{iw:.1f}" height="{ih}" rx="8"/></clipPath></defs>',
         f'<g class="fade" {d(delay)}><image href="{embed(img, "image/jpeg")}" x="{ix}" y="{iy}" width="{iw:.1f}" height="{ih}" '
         f'preserveAspectRatio="xMidYMin slice" clip-path="url(#ri)"/></g>',
         f'<g class="rise" {d(delay + .15)}><text x="{ix + 8}" y="{iy + ih + 32}" class="b" font-size="16" fill="{TEXT}">{esc(title)}</text>'
         f'<text x="{ix + iw - 8:.1f}" y="{iy + ih + 31}" class="m" font-size="11" fill="{MUTED}" text-anchor="end">{year}</text>']
    for i, line in enumerate(wrap(desc, iw - 16, 13)[:2]):
        b.append(f'<text x="{ix + 8}" y="{iy + ih + 54 + i * 19}" font-size="13" fill="{MUTED}">{esc(line)}</text>')
    b.append(f'<text x="{ix + 8}" y="{h - 22}" class="m" font-size="11" fill="{DIM}">{esc(tech)}</text></g>')
    return svg(w, h, "".join(b))


def languages(s: dict) -> str:
    h, x0 = 172, 36
    inner = W - 2 * x0
    b = [card(W, h), section_head(x0, 48, "03", "Languages I'm using".replace("'", "’")),
         f'<text x="{W - x0}" y="48" class="m" font-size="11" fill="{DIM}" text-anchor="end">by code pushed · last 12 months</text>',
         f'<defs><clipPath id="bar"><rect x="{x0}" y="68" width="{inner}" height="10" rx="5"/></clipPath></defs>']
    segs, bx = [], x0
    for i, (name, pct, color) in enumerate(s["langs"]):
        sw = inner * pct / 100
        segs.append(f'<rect class="growx" {d(.2 + i * .08)} x="{bx:.1f}" y="68" width="{max(sw - 2, 1):.1f}" height="10" fill="{color}"/>')
        bx += sw
    b.append(f'<g clip-path="url(#bar)">{"".join(segs)}</g>')
    col_w = (inner + 16) / 5
    for i, (name, pct, color) in enumerate(s["langs"]):
        cx, cy = x0 + (i % 5) * col_w, 112 + (i // 5) * 30
        b.append(f'<g class="rise" {d(.5 + i * .06)}><circle cx="{cx + 4:.1f}" cy="{cy - 4}" r="4" fill="{color}"/>'
                 f'<text x="{cx + 16:.1f}" y="{cy}" font-size="13.5" fill="{TEXT}">{esc(name)}'
                 f'<tspan class="m" font-size="11.5" fill="{DIM}" dx="8">{pct:.1f}%</tspan></text></g>')
    return svg(W, h, "".join(b))


def contact_head() -> str:
    h, x0 = 170, 36
    status = "Open to freelance projects"
    sw = tw(status, 12, "mono")
    return svg(W, h, card(W, h) + section_head(x0, 48, "04", "Let’s talk")
               + f'<g class="fade">{status_dot(W - x0 - sw - 14, 44)}'
                 f'<text x="{W - x0}" y="48" class="m" font-size="12" fill="{MUTED}" text-anchor="end">{status}</text></g>'
               + f'<text x="{x0}" y="102" class="b rise" font-size="28" letter-spacing="-.8" fill="{TEXT}" {d(.1)}>Have something hard to build?</text>'
               + f'<text x="{x0}" y="134" class="rise" font-size="16" fill="{MUTED}" {d(.2)}>That’s exactly where I want to be. Tell me about it.</text>')


def link_tile(lbl, value, filled, delay) -> str:
    w, h = THIRD, 92
    fill, fg = (ACCENT, "#000") if filled else (CARD, TEXT)
    stroke = ACCENT if filled else "rgba(255,255,255,.14)"
    return svg(w, h, f'<g class="rise" {d(delay)}>{card(w, h, fill, stroke, 12)}'
                     f'<text x="22" y="32" class="m" font-size="10.5" letter-spacing="1.2" fill="{fg}" opacity=".75">{lbl}</text>'
                     f'<text x="22" y="70" class="b" font-size="14" fill="{fg}">{esc(value)}</text>'
                     f'{arrow(w - 30, 22, fg, "up")}</g>')


def contact_foot() -> str:
    year = dt.date.today().year
    return svg(W, 44, hline(P, W - P, 4, LINE)
               + f'<text x="{P + 4}" y="32" class="m" font-size="11.5" fill="{DIM}">© {year} Richardt Justke · Brasília, BR</text>'
               + f'<text x="{W - P - 4}" y="32" class="m" font-size="11.5" fill="{DIM}" text-anchor="end">~/richardt $ exit</text>')


# ------------------------------------------------------------------ main
def main() -> None:
    s = stats(fetch_data())
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    files = {
        "hero": hero(s),
        "about": about(),
        "heatmap": heatmap(s),
        "activity": activity(s),
        "title-building": title_building(),
        "languages": languages(s),
        "contact": contact_head(),
        "footer": contact_foot(),
    }
    for i, (name, lbl, title, foot, style, kind) in enumerate(TILES):
        files[name] = tile(lbl, title, foot, style, kind, .1 + i * .12)
    for i, (name, title, year, img, desc, tech) in enumerate(REPOS):
        files[name] = repo(title, year, img, desc, tech, .1 + i * .15)
    for i, (name, lbl, value, filled) in enumerate(CONTACT):
        files[name] = link_tile(lbl, value, filled, .1 + i * .06)
    for name, content in files.items():
        (OUT / f"{name}.svg").write_text(content, encoding="utf-8")
    print(f"rendered {len(files)} cards in {OUT} (total={s['total']}, streak={s['streak']}, "
          f"active={s['active']}, langs={[n for n, _, _ in s['langs']][:4]})")


if __name__ == "__main__":
    main()
