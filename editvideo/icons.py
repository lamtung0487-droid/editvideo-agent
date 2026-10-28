"""Pictogram icons for charts (round 13, the owner on the sixth cut's figure cards: "only text, no animated picture").
A small bundled set from Tabler Icons (MIT, assets/icons/tabler) is read as SVG path data and placed into a chart's own
coordinate space: `place(d, x, y, size)` rewrites a 24-unit icon path for a given spot and size, so the SVG layer needs
no transform support and both engines draw it the same way."""
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "assets" / "icons" / "tabler"
NAMES = {"plane": "outline-plane", "truck": "outline-truck", "user": "filled-user", "person": "filled-user", "bottle": "filled-bottle",
         "coin": "filled-coin", "book": "filled-book", "bomb": "filled-bomb", "ship": "outline-ship", "flame": "outline-flame",
         "cash": "outline-cash", "school": "outline-school", "bank": "outline-building-bank"}
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_TOK = re.compile(rf"[MmLlHhVvCcSsQqTtAaZz]|{_NUM}")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


@lru_cache(maxsize=None)
def icon(name):
    """{"paths": [d, ...], "filled": bool} of a bundled icon (24 x 24 units), the empty frame path left out."""
    file = NAMES.get(name)
    if not file:
        raise ValueError(f"icon must be one of {sorted(NAMES)}")
    svg = (ROOT / f"{file}.svg").read_text(encoding="utf-8")
    paths = [d for d in re.findall(r'<path[^>]*\sd="([^"]+)"', svg) if d.strip() != "M0 0h24v24H0z"]
    return {"paths": paths, "filled": file.startswith("filled-")}


def place(d, x, y, size, unit=24.0):
    """Path data `d` drawn in a `unit`-wide box, moved so the box's top left sits at (x, y) and scaled to `size` wide.
    Absolute coordinates are scaled and moved, relative ones scaled; arc radii scale, their angle and flags do not."""
    s = size / unit
    out, cmd, args = [], None, []
    toks = _TOK.findall(d)
    i = 0

    def fmt(v):
        return f"{v:.2f}".rstrip("0").rstrip(".") if abs(v) >= .005 else "0"
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                out.append("Z")
                continue
        n = _ARGS[cmd.upper()]
        args = [float(v) for v in toks[i:i + n]]
        i += n
        rel = cmd.islower()
        C = cmd.upper()
        if C == "H":
            v = [args[0] * s + (0 if rel else x)]
        elif C == "V":
            v = [args[0] * s + (0 if rel else y)]
        elif C == "A":
            rx, ry, rot, large, sweep, ex, ey = args
            v = [rx * s, ry * s, rot, large, sweep, ex * s + (0 if rel else x), ey * s + (0 if rel else y)]
        else:
            v = [a * s + (0 if rel else (x if k % 2 == 0 else y)) for k, a in enumerate(args)]
        out.append(cmd + " ".join(fmt(a) if C != "A" or k not in (3, 4) else str(int(a)) for k, a in enumerate(v)))
        if cmd in "Mm":  # a moveto's extra pairs are linetos
            cmd = "l" if rel else "L"
    return "".join(out)


def pictogram(name, x, y, size, color, eid, appear=None, muted=False):
    """SVG elements for one icon at (x, y), `size` wide: filled icons as shapes, outline icons as strokes."""
    ic = icon(name)
    els = []
    for k, d in enumerate(ic["paths"]):
        e = {"id": f"{eid}p{k}", "type": "path", "d": place(d, x, y, size), "opacity": .55 if muted else 1}
        if ic["filled"]:
            e.update(fill=color, stroke="none", stroke_width=0)
        else:
            e.update(fill="none", stroke=color, stroke_width=round(max(1.0, size / 12), 2))
        if appear:
            e["appear"] = appear
        els.append(e)
    return els
