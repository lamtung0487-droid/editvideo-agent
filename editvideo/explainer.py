"""Science-explainer toolkit: recipes that compile to ordinary timeline layers (svg, text, counter, particles, shape).

Techniques studied in professional science explainers (presenter + motion graphics). Each recipe solves geometry or
synchronisation the calling AI would otherwise hand-place:
- measure:     dimension arrow growing from its middle while the number counts in sync with the arrow length.
- diagram:     nodes and connectors (straight, wavy "photon", dashed, arrow), drawn in order, with labels and ripples.
- unit_grid:   dot grid / unit chart: one dot among many, a scanning selection band, bracketed counts.
- plot:        scientific plot: axes, ticks, scatter with error bars, fitted line drawn on, a hand-drawn highlight.
- annotate:    a hand-drawn ellipse, underline, box or arrow on footage or stills.
- chips:       concept labels in boxed chips that enter, move/shrink into a header and stack over a divider.
- number_wall: a hero number, then the same number repeated into rows that drift in alternate directions (scale).
- hud_card:    small info card with caption and a live counter.
- stat_line:   bottom-centre stat caption with inline **strong** / ==accent== emphasis.
- particles:   bunch (accelerator bunch), stream, starfield (drift) and collision (curved tracks) presets.
- camera_stage: a camera travelling over one big canvas of laid-out children (maps, cut-outs, charts): stops with eased
               moves (land/dive/glide), log-space zoom for deep dives (up to 40x), drift after landing, velocity motion
               blur, optional animation on twos; baked into child keyframes.
- pie:         a pie/donut swept clockwise from 12 o'clock as strokes, one slice sliding out along its bisector, % labels.
- columns:     column chart drawn as strokes: baseline grows from the centre, bars rise staggered, values land on top.
- text_window_zoom: footage seen through a word, then a fly-through of the thickest stroke of one letter to full frame.
- doc_timecard: documentary time jump: tracked label (PAST/PRESENT/place), mono year that rolls from the previous one, rule.
- evidence_3d: an archival photo/document as a physical card: tilt, slow push to the region that matters, exact projected mark, caption + source.
- motif_progress: recurring chapter motif: ticks on a line, chapters done filled, the current one lit, ripple, named.
All timing is in frames. Positions are normalized to the canvas unless a recipe says box-relative. Rendered identically
by Remotion and HyperFrames through engines/effects.js. Measurements are returned so the AI can verify placement.
"""
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store
from .cinematic import FPS, HEX, _timeline, _measure, _typo, _apply, preview_ops, _ids

Role = Literal["display", "headline", "title", "body", "label", "data", "quote", "caption"]
LayerId = Field(pattern=r"^[A-Za-z0-9_-]{1,70}$")


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = LayerId
    start_frame: int = Field(ge=0)
    end_frame: int
    attach_shot: str | None = None
    z: int = Field(default=60, ge=0, le=1000)

    @model_validator(mode="after")
    def span(self):
        if self.end_frame <= self.start_frame + 6:
            raise ValueError("end_frame must be at least 7 frames after start_frame")
        return self


def _layer(q, suffix, kind, **kw):
    return {"id": f"{q.id}-{suffix}" if suffix else q.id, "kind": kind, "start_frame": q.start_frame, "end_frame": q.end_frame,
            "attach_shot": q.attach_shot, "z": q.z, **kw}


def _font(t, role):
    return _typo(t, role)["font_id"]


def _px(t, size_1080):
    return size_1080 * min(t["width"], t["height"]) / 1080


def _r(v):
    return round(v, 2)


# ---------------------------------------------------------------- measure
class Measure(Base):
    recipe: Literal["measure"]
    start: list[float] = Field(min_length=2, max_length=2)  # normalized canvas point
    end: list[float] = Field(min_length=2, max_length=2)
    value_to: float = Field(allow_inf_nan=False)
    value_from: float = Field(default=0, allow_inf_nan=False)
    decimals: int = Field(default=0, ge=0, le=4)
    group: str = Field(default=" ", max_length=3)
    prefix: str = Field(default="", max_length=20)
    suffix: str = Field(default="", max_length=40)
    delay: int = Field(default=6, ge=0)
    grow_frames: int = Field(default=45, ge=6, le=600)
    style: Literal["count", "roll", "scramble"] = "count"
    heads: Literal["both", "end", "start"] = "both"
    grow: Literal["center", "start"] = "center"
    label: Literal["below", "above"] = "below"
    role: Role = "title"
    color: str = Field(default="#ffffff", pattern=HEX)
    stroke: float = Field(default=5, gt=0, le=40)  # px at 1080p


def measure(t, q: Measure):
    W, H = t["width"], t["height"]
    (x1, y1), (x2, y2) = q.start, q.end
    sw = _px(t, q.stroke)
    end = q.delay + q.grow_frames
    line = _layer(q, "line", "svg", x=0, y=0, width=1, height=1, data={"view_box": [W, H], "elements": [
        {"id": "dim", "type": "arrow", "x1": _r(x1 * W), "y1": _r(y1 * H), "x2": _r(x2 * W), "y2": _r(y2 * H), "heads": q.heads,
         "grow": q.grow, "head_size": _r(sw * 4.2), "stroke": q.color, "stroke_width": _r(sw), "draw": [q.delay, end]}]},
        effects=[{"name": "shadow", "end_frame": 1, "params": {"amount": 14}}])
    ty = _typo(t, q.role)
    label_h = ty["size"] * min(W, H) / 1080 * ty.get("line_height", 1.2) / H
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    gap = (sw * 5) / H
    y = my + gap if q.label == "below" else my - gap - label_h
    final = f"{q.prefix}{q.value_to:,.{q.decimals}f}{q.suffix}".replace(",", q.group)
    m = _measure(t, q.role, final, W)
    box_w = min(.9, max(.2, m["width"] / W + .06))
    value = _layer(q, "value", "counter", x=_r(min(1 - box_w, max(0, mx - box_w / 2)) * 1e4) / 1e4, y=round(y, 4), width=round(box_w, 4),
                   height=round(label_h + .01, 4), typography_role=q.role, color=q.color,
                   data={"from": q.value_from, "to": q.value_to, "decimals": q.decimals, "group": q.group, "prefix": q.prefix,
                         "suffix": q.suffix, "style": q.style, "align": "center"},
                   effects=[{"name": "progress", "start_frame": q.delay, "end_frame": end, "easing": "smooth"},
                            {"name": "fade_in", "start_frame": q.delay, "end_frame": q.delay + 8},
                            {"name": "shadow", "end_frame": 1, "params": {"amount": 18}}])
    notes = []
    if not (0 <= y <= 1 - label_h):
        notes.append("Label falls outside the frame; use label='above' or move the line.")
    length = math.hypot((x2 - x1) * W, (y2 - y1) * H)
    if length < m["width"] * .6:
        notes.append("Line is shorter than its label; the number will read as the subject, not the distance.")
    return {"ops": [{"op": "upsert_layer", "layer": line}, {"op": "upsert_layer", "layer": value}], "notes": notes,
            "inspect_frames": [q.start_frame + q.delay + q.grow_frames // 2, q.start_frame + end + 4],
            "measurements": {"line_px": round(length), "label_width_px": round(m["width"]), "label_y": round(y, 4)}}


# ---------------------------------------------------------------- diagram
class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    x: float = Field(ge=0, le=1)  # box-relative
    y: float = Field(ge=0, le=1)
    r: float = Field(default=.05, gt=0, le=.5)  # fraction of box height
    color: str = Field(default="#3cd2ff", pattern=HEX)
    outline: str | None = Field(default=None, pattern=HEX)
    label: str = Field(default="", max_length=60)
    label_side: Literal["right", "left", "top", "bottom"] = "right"
    label_color: str = Field(default="#ffffff", pattern=HEX)
    at: int = Field(default=0, ge=0)
    ripple: list[int] | None = None  # recipe-local [start, end]
    ripple_count: int = Field(default=3, ge=1, le=6)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    target: str
    style: Literal["line", "wave", "dashed", "arrow"] = "line"
    at: int = Field(default=0, ge=0)
    frames: int = Field(default=12, ge=1, le=300)
    color: str = Field(default="#ffffff", pattern=HEX)
    width: float = Field(default=3, gt=0, le=30)  # px at 1080p
    amplitude: float = Field(default=.012, ge=0, le=.2)  # wave, fraction of box height
    wavelength: float = Field(default=.03, gt=.002, le=.5)  # wave, fraction of box height


class Diagram(Base):
    recipe: Literal["diagram"]
    box: list[float] = Field(default=[0, 0, 1, 1], min_length=4, max_length=4)
    nodes: list[Node] = Field(min_length=1, max_length=60)
    edges: list[Edge] = Field(default_factory=list, max_length=120)
    label_size: float = Field(default=30, gt=6, le=200)  # px at 1080p
    label_role: Role = "label"

    @model_validator(mode="after")
    def refs(self):
        ids = {n.id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("node ids must be unique")
        for e in self.edges:
            if e.source not in ids or e.target not in ids:
                raise ValueError(f"edge {e.source}->{e.target} references an unknown node")
        return self


def _wave(ax, ay, bx, by, amp, lam):
    L = math.hypot(bx - ax, by - ay)
    if L < 1:
        return f"M{_r(ax)} {_r(ay)}L{_r(bx)} {_r(by)}"
    ux, uy = (bx - ax) / L, (by - ay) / L
    n = max(8, int(L / lam * 16))
    pts = []
    for i in range(n + 1):
        s = L * i / n
        env = min(1, s / (lam * .5), (L - s) / (lam * .5))  # start and end on the axis
        o = amp * env * math.sin(2 * math.pi * s / lam)
        pts.append(f"{_r(ax + ux * s - uy * o)} {_r(ay + uy * s + ux * o)}")
    return "M" + "L".join(pts)


def diagram(t, q: Diagram):
    W, H = t["width"], t["height"]
    bw, bh = q.box[2] * W, q.box[3] * H
    nodes = {n.id: n for n in q.nodes}
    els, fs = [], _px(t, q.label_size)
    for e in q.edges:
        a, b = nodes[e.source], nodes[e.target]
        ax, ay, bx, by = a.x * bw, a.y * bh, b.x * bw, b.y * bh
        L = math.hypot(bx - ax, by - ay) or 1
        ux, uy = (bx - ax) / L, (by - ay) / L
        ra, rb = a.r * bh, b.r * bh
        ax, ay, bx, by = ax + ux * ra, ay + uy * ra, bx - ux * rb, by - uy * rb  # connect circle edges, not centres
        sw, draw = _r(_px(t, e.width)), [e.at, e.at + e.frames]
        eid = f"e{len(els)}"
        if e.style == "wave":
            els.append({"id": eid, "type": "path", "d": _wave(ax, ay, bx, by, e.amplitude * bh, e.wavelength * bh), "stroke": e.color,
                        "stroke_width": sw, "draw": draw})
        elif e.style == "arrow":
            els.append({"id": eid, "type": "arrow", "x1": _r(ax), "y1": _r(ay), "x2": _r(bx), "y2": _r(by), "stroke": e.color,
                        "stroke_width": sw, "draw": draw, "heads": "end"})
        else:
            els.append({"id": eid, "type": "line", "x1": _r(ax), "y1": _r(ay), "x2": _r(bx), "y2": _r(by), "stroke": e.color,
                        "stroke_width": sw, "draw": draw, **({"dashed": _r(sw * 3)} if e.style == "dashed" else {})})
    for n in q.nodes:
        cx, cy, r = n.x * bw, n.y * bh, n.r * bh
        el = {"id": f"n-{n.id}", "type": "circle", "cx": _r(cx), "cy": _r(cy), "r": _r(r), "fill": n.color,
              "stroke": n.outline or n.color, "stroke_width": _r(max(2, r * .08)), "appear": [n.at, n.at + 10]}
        if n.ripple:
            el.update(ripple=n.ripple, ripple_count=n.ripple_count)
        els.append(el)
        if n.label:
            off = r + fs * .6
            lx, ly, anchor = {"right": (cx + off, cy + fs * .35, "start"), "left": (cx - off, cy + fs * .35, "end"),
                              "top": (cx, cy - off, "middle"), "bottom": (cx, cy + off + fs * .7, "middle")}[n.label_side]
            els.append({"id": f"l-{n.id}", "type": "text", "x": _r(lx), "y": _r(ly), "text": n.label, "anchor": anchor,
                        "font_size": _r(fs), "font_weight": 500, "fill": n.label_color, "stroke": n.label_color, "appear": [n.at + 4, n.at + 14]})
    layer = _layer(q, "", "svg", x=q.box[0], y=q.box[1], width=q.box[2], height=q.box[3],
                   data={"view_box": [_r(bw), _r(bh)], "elements": els, "font_family": _font(t, q.label_role)})
    last = max([n.at + 14 for n in q.nodes] + [e.at + e.frames for e in q.edges])
    notes = []
    if last >= q.end_frame - q.start_frame:
        notes.append("The last element finishes after the layer ends; extend end_frame or start earlier.")
    return {"ops": [{"op": "upsert_layer", "layer": layer}], "notes": notes,
            "inspect_frames": [q.start_frame + min(last, q.end_frame - q.start_frame - 1)], "measurements": {"elements": len(els)}}


# ---------------------------------------------------------------- unit grid
class Band(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row: int = Field(ge=0)
    at: int = Field(ge=0)
    frames: int = Field(default=12, ge=1, le=300)
    color: str = Field(default="#ffffff", pattern=HEX)


class Bracket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cols: list[int] = Field(min_length=2, max_length=2)
    label: str = Field(default="", max_length=40)
    at: int = Field(ge=0)
    color: str = Field(default="#ffffff", pattern=HEX)


class UnitGrid(Base):
    recipe: Literal["unit_grid"]
    box: list[float] = Field(default=[.04, .06, .92, .78], min_length=4, max_length=4)
    rows: int = Field(ge=1, le=60)
    cols: int = Field(ge=1, le=80)
    dot: float = Field(default=.3, gt=0, le=.5)  # radius as a fraction of the cell
    color: str = Field(default="#3cd2ff", pattern=HEX)
    highlight: list[list[int]] = Field(default_factory=list, max_length=200)  # [row, col]
    highlight_count: int = Field(default=0, ge=0, le=200)  # seeded picks when highlight is empty
    highlight_color: str = Field(default="#ffffff", pattern=HEX)
    highlight_at: int = Field(default=0, ge=0)
    appear: Literal["wave", "rows", "all", "none"] = "wave"
    appear_frames: int = Field(default=24, ge=1, le=300)
    bands: list[Band] = Field(default_factory=list, max_length=10)
    brackets: list[Bracket] = Field(default_factory=list, max_length=6)
    label_size: float = Field(default=34, gt=6, le=200)
    seed: int = Field(default=7, ge=0)

    @model_validator(mode="after")
    def size(self):
        if self.rows * self.cols > 1600:
            raise ValueError("rows*cols must be at most 1600 dots")
        for r, c in self.highlight:
            if not (0 <= r < self.rows and 0 <= c < self.cols):
                raise ValueError("highlight [row, col] outside the grid")
        for b in self.bands:
            if b.row >= self.rows:
                raise ValueError("band row outside the grid")
        for b in self.brackets:
            if not 0 <= b.cols[0] <= b.cols[1] < self.cols:
                raise ValueError("bracket cols outside the grid")
        return self


def unit_grid(t, q: UnitGrid):
    import random
    W, H = t["width"], t["height"]
    bw, bh = q.box[2] * W, q.box[3] * H
    label_room = _px(t, q.label_size) * 1.8 if q.brackets else 0
    cell = min(bw / q.cols, (bh - label_room) / q.rows)
    ox, oy = (bw - cell * q.cols) / 2, (bh - label_room - cell * q.rows) / 2
    r = cell * q.dot
    pos = lambda i, j: (ox + (j + .5) * cell, oy + (i + .5) * cell)
    marks = {tuple(h) for h in q.highlight}
    if not marks and q.highlight_count:
        rng = random.Random(q.seed)
        marks = set(rng.sample([(i, j) for i in range(q.rows) for j in range(q.cols)], min(q.highlight_count, q.rows * q.cols)))
    els, cr, cc = [], (q.rows - 1) / 2, (q.cols - 1) / 2
    far = math.hypot(cr, cc) or 1
    for i in range(q.rows):
        for j in range(q.cols):
            x, y = pos(i, j)
            el = {"id": f"d{i}_{j}", "type": "circle", "cx": _r(x), "cy": _r(y), "r": _r(r), "fill": q.color, "stroke": "none", "stroke_width": 0}
            if q.appear != "none":
                d = 0 if q.appear == "all" else (math.hypot(i - cr, j - cc) / far if q.appear == "wave" else i / max(1, q.rows - 1))
                a = int(d * q.appear_frames)
                el["appear"] = [a, a + 8]
            els.append(el)
    for i, j in sorted(marks):
        x, y = pos(i, j)
        els.append({"id": f"h{i}_{j}", "type": "circle", "cx": _r(x), "cy": _r(y), "r": _r(r * 1.05), "fill": q.highlight_color,
                    "stroke": q.highlight_color, "stroke_width": _r(max(1, r * .2)), "glow": _r(r * 1.6),
                    "appear": [q.highlight_at, q.highlight_at + 8], "ripple": [q.highlight_at, q.highlight_at + 40], "ripple_count": 2})
    for k, b in enumerate(q.bands):
        _, y = pos(b.row, 0)
        els.append({"id": f"band{k}", "type": "rect", "x": _r(ox - cell * .1), "y": _r(y - cell * .5), "width": _r(cell * q.cols + cell * .2),
                    "height": _r(cell), "rx": _r(cell * .08), "stroke": b.color, "stroke_width": _r(max(2, cell * .06)),
                    "fill": b.color, "fill_opacity": .08, "draw": [b.at, b.at + b.frames]})
    fs = _px(t, q.label_size)
    for k, b in enumerate(q.brackets):
        xa, xb = pos(0, b.cols[0])[0] - cell * .4, pos(0, b.cols[1])[0] + cell * .4
        y = oy + cell * q.rows + cell * .35
        els.append({"id": f"br{k}", "type": "path", "d": f"M{_r(xa)} {_r(y)}V{_r(y + cell * .35)}H{_r(xb)}V{_r(y)}", "stroke": b.color,
                    "stroke_width": _r(max(2, cell * .07)), "draw": [b.at, b.at + 12]})
        if b.label:
            els.append({"id": f"brl{k}", "type": "text", "x": _r((xa + xb) / 2), "y": _r(y + cell * .35 + fs * 1.05), "text": b.label,
                        "anchor": "middle", "font_size": _r(fs), "font_weight": 700, "fill": b.color, "stroke": b.color, "appear": [b.at + 6, b.at + 16]})
    layer = _layer(q, "", "svg", x=q.box[0], y=q.box[1], width=q.box[2], height=q.box[3],
                   data={"view_box": [_r(bw), _r(bh)], "elements": els, "font_family": _font(t, "label")})
    notes = []
    if r * 2 < _px(t, 6):
        notes.append(f"Dots are {r * 2:.1f}px wide; under ~6px they shimmer when the frame scales. Use fewer cells or a larger box.")
    return {"ops": [{"op": "upsert_layer", "layer": layer}], "notes": notes,
            "inspect_frames": [q.start_frame + q.appear_frames + 8, q.start_frame + max([q.highlight_at + 12] + [b.at + 14 for b in q.bands])],
            "measurements": {"dots": q.rows * q.cols, "dot_px": round(r * 2, 1), "highlighted": len(marks), "elements": len(els)}}


# ---------------------------------------------------------------- plot
class Series(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["scatter", "line", "errorbar"] = "scatter"
    points: list[list[float]] = Field(min_length=1, max_length=300)
    errors: list[float] | None = None
    color: str = Field(default="#ffffff", pattern=HEX)
    at: int = Field(default=0, ge=0)
    frames: int = Field(default=30, ge=1, le=600)
    size: float = Field(default=6, gt=0, le=60)  # px at 1080p
    width: float = Field(default=4, gt=0, le=30)

    @model_validator(mode="after")
    def shape(self):
        if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in self.points):
            raise ValueError("points are [x, y] pairs")
        if self.errors is not None and len(self.errors) != len(self.points):
            raise ValueError("errors must match points")
        return self


class Highlight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cx: float
    cy: float
    rx: float = Field(gt=0)  # data units
    ry: float = Field(gt=0)
    color: str = Field(default="#e0413a", pattern=HEX)
    at: int = Field(default=0, ge=0)
    frames: int = Field(default=18, ge=1, le=300)
    width: float = Field(default=6, gt=0, le=30)


class Plot(Base):
    recipe: Literal["plot"]
    box: list[float] = Field(default=[.1, .1, .8, .78], min_length=4, max_length=4)
    x_range: list[float] = Field(min_length=2, max_length=2)
    y_range: list[float] = Field(min_length=2, max_length=2)
    x_ticks: list[float] = Field(default_factory=list, max_length=20)
    y_ticks: list[float] = Field(default_factory=list, max_length=20)
    x_label: str = Field(default="", max_length=60)
    y_label: str = Field(default="", max_length=60)
    axis_color: str = Field(default="#ffffff", pattern=HEX)
    grid: bool = False
    axes_at: int = Field(default=0, ge=0)
    series: list[Series] = Field(min_length=1, max_length=8)
    highlight: Highlight | None = None
    font_size: float = Field(default=26, gt=6, le=120)

    @model_validator(mode="after")
    def ranges(self):
        if self.x_range[1] <= self.x_range[0] or self.y_range[1] <= self.y_range[0]:
            raise ValueError("x_range/y_range need [low, high] with low < high")
        return self


def _hand_ellipse(cx, cy, rx, ry, seed=3):
    """Two slightly offset loops with a small tilt: reads as a marker circle drawn by hand."""
    import random
    rng = random.Random(seed)
    tilt = math.radians(-6)
    pts = []
    for i in range(0, 64):
        a = -math.pi * .6 + 2.15 * math.pi * i / 63  # a little more than one loop, overshooting the start
        k = 1 + .06 * math.sin(a * 3 + rng.random()) + .03 * i / 63
        x, y = rx * k * math.cos(a), ry * k * math.sin(a)
        pts.append(f"{_r(cx + x * math.cos(tilt) - y * math.sin(tilt))} {_r(cy + x * math.sin(tilt) + y * math.cos(tilt))}")
    return "M" + "L".join(pts)


def plot(t, q: Plot):
    W, H = t["width"], t["height"]
    bw, bh = q.box[2] * W, q.box[3] * H
    fs = _px(t, q.font_size)
    left, bottom, top, right = fs * 3.4, fs * (3.2 if q.x_label else 1.9), fs * .6, fs * .6
    pw, ph = bw - left - right, bh - top - bottom
    X = lambda v: left + (v - q.x_range[0]) / (q.x_range[1] - q.x_range[0]) * pw
    Y = lambda v: top + ph - (v - q.y_range[0]) / (q.y_range[1] - q.y_range[0]) * ph
    a0, sw = q.axes_at, _r(_px(t, 3))
    els = [{"id": "ax", "type": "polyline", "points": [[_r(left), _r(top)], [_r(left), _r(top + ph)], [_r(left + pw), _r(top + ph)]],
            "stroke": q.axis_color, "stroke_width": sw, "draw": [a0, a0 + 18]}]
    for k, v in enumerate(q.x_ticks):
        x = X(v)
        els.append({"id": f"xt{k}", "type": "line", "x1": _r(x), "y1": _r(top + ph), "x2": _r(x), "y2": _r(top + ph + fs * .35), "stroke": q.axis_color,
                    "stroke_width": sw, "appear": [a0 + 10, a0 + 18]})
        els.append({"id": f"xl{k}", "type": "text", "x": _r(x), "y": _r(top + ph + fs * 1.45), "text": f"{v:g}", "anchor": "middle", "font_size": _r(fs),
                    "font_weight": 400, "fill": q.axis_color, "stroke": q.axis_color, "appear": [a0 + 12, a0 + 20]})
        if q.grid:
            els.append({"id": f"xg{k}", "type": "line", "x1": _r(x), "y1": _r(top), "x2": _r(x), "y2": _r(top + ph), "stroke": q.axis_color,
                        "stroke_width": 1, "opacity": .18, "appear": [a0 + 10, a0 + 18]})
    for k, v in enumerate(q.y_ticks):
        y = Y(v)
        els.append({"id": f"yt{k}", "type": "line", "x1": _r(left - fs * .35), "y1": _r(y), "x2": _r(left), "y2": _r(y), "stroke": q.axis_color,
                    "stroke_width": sw, "appear": [a0 + 10, a0 + 18]})
        els.append({"id": f"yl{k}", "type": "text", "x": _r(left - fs * .55), "y": _r(y + fs * .35), "text": f"{v:g}", "anchor": "end", "font_size": _r(fs),
                    "font_weight": 400, "fill": q.axis_color, "stroke": q.axis_color, "appear": [a0 + 12, a0 + 20]})
        if q.grid:
            els.append({"id": f"yg{k}", "type": "line", "x1": _r(left), "y1": _r(y), "x2": _r(left + pw), "y2": _r(y), "stroke": q.axis_color,
                        "stroke_width": 1, "opacity": .18, "appear": [a0 + 10, a0 + 18]})
    if q.x_label:
        els.append({"id": "xlab", "type": "text", "x": _r(left + pw), "y": _r(bh - fs * .3), "text": q.x_label, "anchor": "end", "font_size": _r(fs * 1.05),
                    "font_weight": 600, "fill": q.axis_color, "stroke": q.axis_color, "appear": [a0 + 14, a0 + 24]})
    if q.y_label:
        els.append({"id": "ylab", "type": "text", "x": _r(left - fs * .55), "y": _r(top - fs * .1), "text": q.y_label, "anchor": "start",
                    "font_size": _r(fs * 1.05), "font_weight": 600, "fill": q.axis_color, "stroke": q.axis_color, "appear": [a0 + 14, a0 + 24]})
    outside = 0
    for s_i, s in enumerate(q.series):
        pts = sorted(range(len(s.points)), key=lambda i: s.points[i][0])
        for i in pts:
            x, y = s.points[i]
            outside += not (q.x_range[0] <= x <= q.x_range[1] and q.y_range[0] <= y <= q.y_range[1])
        if s.type == "line":
            els.append({"id": f"s{s_i}", "type": "polyline", "points": [[_r(X(s.points[i][0])), _r(Y(s.points[i][1]))] for i in pts],
                        "stroke": s.color, "stroke_width": _r(_px(t, s.width)), "draw": [s.at, s.at + s.frames]})
            continue
        for rank, i in enumerate(pts):
            x, y = s.points[i]
            a = s.at + int(rank / max(1, len(pts) - 1) * s.frames)
            if s.errors and s.errors[i] > 0:
                els.append({"id": f"s{s_i}e{i}", "type": "line", "x1": _r(X(x)), "y1": _r(Y(y - s.errors[i])), "x2": _r(X(x)), "y2": _r(Y(y + s.errors[i])),
                            "stroke": s.color, "stroke_width": _r(_px(t, 2)), "appear": [a, a + 6]})
            els.append({"id": f"s{s_i}p{i}", "type": "circle", "cx": _r(X(x)), "cy": _r(Y(y)), "r": _r(_px(t, s.size)), "fill": s.color,
                        "stroke": s.color, "stroke_width": 0, "appear": [a, a + 6]})
    if q.highlight:
        h = q.highlight
        rx = h.rx / (q.x_range[1] - q.x_range[0]) * pw
        ry = h.ry / (q.y_range[1] - q.y_range[0]) * ph
        els.append({"id": "hl", "type": "path", "d": _hand_ellipse(X(h.cx), Y(h.cy), rx, ry), "stroke": h.color,
                    "stroke_width": _r(_px(t, h.width)), "draw": [h.at, h.at + h.frames]})
    layer = _layer(q, "", "svg", x=q.box[0], y=q.box[1], width=q.box[2], height=q.box[3],
                   data={"view_box": [_r(bw), _r(bh)], "elements": els, "font_family": _font(t, "data") if "data" in (t.get("design") or {}).get("typography", {}) else _font(t, "label")})
    notes = [f"{outside} points fall outside the axis ranges and will be drawn off the plot."] if outside else []
    if len(els) > 2000:
        raise ValueError(f"Plot needs {len(els)} elements (max 2000); thin the data or drop error bars")
    last = max([s.at + s.frames for s in q.series] + ([q.highlight.at + q.highlight.frames] if q.highlight else []))
    return {"ops": [{"op": "upsert_layer", "layer": layer}], "notes": notes, "inspect_frames": [q.start_frame + a0 + 24, q.start_frame + last + 2],
            "measurements": {"plot_px": [round(pw), round(ph)], "elements": len(els)}}


# ---------------------------------------------------------------- annotate
class Annotate(Base):
    recipe: Literal["annotate"]
    shape: Literal["ellipse", "underline", "box", "arrow"] = "ellipse"
    region: list[float] = Field(min_length=4, max_length=4)  # normalized canvas x, y, w, h of the thing to mark
    from_point: list[float] | None = Field(default=None, min_length=2, max_length=2)  # arrow tail
    color: str = Field(default="#e0413a", pattern=HEX)
    width: float = Field(default=7, gt=0, le=40)
    at: int = Field(default=0, ge=0)
    frames: int = Field(default=16, ge=1, le=300)
    seed: int = Field(default=3, ge=0)


def annotate(t, q: Annotate):
    W, H = t["width"], t["height"]
    x, y, w, h = q.region[0] * W, q.region[1] * H, q.region[2] * W, q.region[3] * H
    sw, draw = _r(_px(t, q.width)), [q.at, q.at + q.frames]
    if q.shape == "ellipse":
        el = {"id": "mark", "type": "path", "d": _hand_ellipse(x + w / 2, y + h / 2, w * .62, h * .7, q.seed)}
    elif q.shape == "underline":
        yy = y + h * 1.18
        el = {"id": "mark", "type": "path", "d": f"M{_r(x - w * .03)} {_r(yy + h * .04)}Q{_r(x + w * .5)} {_r(yy - h * .06)} {_r(x + w * 1.03)} {_r(yy + h * .02)}"}
    elif q.shape == "box":
        p = min(w, h) * .12
        el = {"id": "mark", "type": "path", "d": f"M{_r(x - p)} {_r(y - p * 1.2)}L{_r(x + w + p)} {_r(y - p * .8)}L{_r(x + w + p * 1.2)} {_r(y + h + p)}L{_r(x - p * .9)} {_r(y + h + p * 1.1)}Z"}
    else:
        fx, fy = (q.from_point or [max(.02, q.region[0] - .18), min(.98, q.region[1] + q.region[3] + .15)])
        fx, fy = fx * W, fy * H
        tx, ty = min(max(fx, x), x + w), min(max(fy, y), y + h)
        el = {"id": "mark", "type": "arrow", "x1": _r(fx), "y1": _r(fy), "x2": _r(tx), "y2": _r(ty), "heads": "end", "head_size": _r(_px(t, q.width) * 4)}
    el.update(stroke=q.color, stroke_width=sw, draw=draw)
    layer = _layer(q, "", "svg", x=0, y=0, width=1, height=1, data={"view_box": [W, H], "elements": [el]},
                   effects=[{"name": "shadow", "end_frame": 1, "params": {"amount": 10}}])
    return {"ops": [{"op": "upsert_layer", "layer": layer}], "notes": [], "inspect_frames": [q.start_frame + q.at + q.frames + 2]}


# ---------------------------------------------------------------- chips
class Move(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at: int = Field(ge=0)  # recipe-local frame
    frames: int = Field(default=14, ge=1, le=120)
    x: float = Field(ge=0, le=1)  # new centre
    y: float = Field(ge=0, le=1)
    scale: float = Field(default=1, gt=.1, le=4)


class Chip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,30}$")
    text: str = Field(min_length=1, max_length=60)
    x: float = Field(ge=0, le=1)  # centre
    y: float = Field(ge=0, le=1)
    at: int = Field(default=0, ge=0)
    exit_at: int | None = Field(default=None, ge=1)
    style: Literal["outline", "filled", "plain"] = "outline"
    size: float = Field(default=44, gt=8, le=200)  # font px at 1080p
    weight: int = Field(default=700, ge=100, le=900)
    ink: str | None = Field(default=None, pattern=HEX)  # text colour (outline/plain); filled uses paper. Default from theme
    paper: str | None = Field(default=None, pattern=HEX)  # chip fill (outline: translucent). Default from theme
    tilt: float = Field(default=0, ge=-20, le=20)  # degrees on entry, settles to 0
    moves: list[Move] = Field(default_factory=list, max_length=6)


class Divider(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(default=.08, gt=0, le=1)
    at: int = Field(default=0, ge=0)
    color: str | None = Field(default=None, pattern=HEX)  # default: theme ink


class Chips(Base):
    recipe: Literal["chips"]
    theme: Literal["light", "dark"] = "light"  # light: dark ink on pale chips (bright backgrounds); dark: light ink on deep chips
    chips: list[Chip] = Field(min_length=1, max_length=14)
    dividers: list[Divider] = Field(default_factory=list, max_length=6)
    role: Role = "title"


def chips(t, q: Chips):
    from .design_library import layout_text
    W, H = t["width"], t["height"]
    font = _font(t, q.role)
    ops, measurements = [], {}
    span = q.end_frame - q.start_frame
    ink0, paper0 = ("#141414", "#ffffff") if q.theme == "light" else ("#ffffff", "#0b0f16")
    for c in q.chips:
        c = c.model_copy(update={"ink": c.ink or ink0, "paper": c.paper or paper0})
        fs = _px(t, c.size)
        m = layout_text(font, c.text, max(12, min(300, fs)), 4000, c.weight)
        tw = max(m.get("line_widths") or [fs * len(c.text) * .55])
        pad = fs * .42
        w, h = tw + pad * 2, fs * 1.5
        els = []
        if c.style != "plain":
            els.append({"id": "box", "type": "rect", "x": 1.5, "y": 1.5, "width": _r(w - 3), "height": _r(h - 3), "rx": _r(fs * .08),
                        "stroke": c.ink if c.style == "outline" else c.paper, "stroke_width": _r(max(1.5, fs * .045)),
                        "fill": c.paper if c.style == "outline" else c.ink, "fill_opacity": .55 if c.style == "outline" else 1})
        els.append({"id": "t", "type": "text", "x": _r(w / 2), "y": _r(h / 2 + fs * .35), "text": c.text, "anchor": "middle", "font_size": _r(fs),
                    "font_weight": c.weight, "fill": c.paper if c.style == "filled" else c.ink, "stroke": "none"})
        start = q.start_frame + c.at
        end = q.start_frame + c.exit_at if c.exit_at else q.end_frame
        if end <= start + 1:
            raise ValueError(f"chip {c.id}: exit_at must follow at")
        kf, cx, cy, sc = {}, c.x, c.y, 1.0
        for mv in sorted(c.moves, key=lambda m: m.at):
            a, b = mv.at - c.at, mv.at - c.at + mv.frames
            if a < 0:
                raise ValueError(f"chip {c.id}: move at {mv.at} precedes the chip's entry")
            for key, old, new in (("x", (cx - c.x) * W, (mv.x - c.x) * W), ("y", (cy - c.y) * H, (mv.y - c.y) * H), ("scale", sc, mv.scale)):
                track = kf.setdefault(key, [{"frame": 0, "value": round(old, 2) if key != "scale" else old}])
                if track[-1]["frame"] < a:
                    track.append({"frame": a, "value": track[-1]["value"]})
                track.append({"frame": b, "value": round(new, 2) if key != "scale" else round(new, 4), "easing": "snappy"})
            cx, cy, sc = mv.x, mv.y, mv.scale
        fx = [{"name": "fade_in", "end_frame": 6}, {"name": "pop", "end_frame": 10, "easing": "snappy", "params": {"amount": .25}}]
        if c.tilt:
            fx.append({"name": "rotate_in", "end_frame": 12, "easing": "snappy", "params": {"amount": c.tilt}})
        if c.exit_at:
            fx.append({"name": "fade_out", "start_frame": max(0, end - start - 6), "end_frame": end - start})
        layer = {"id": f"{q.id}-{c.id}", "kind": "svg", "start_frame": start, "end_frame": end, "attach_shot": q.attach_shot, "z": q.z,
                 "x": round(c.x - w / W / 2, 4), "y": round(c.y - h / H / 2, 4), "width": round(w / W, 4), "height": round(h / H, 4),
                 "data": {"view_box": [_r(w), _r(h)], "elements": els, "font_family": font}, "effects": fx, "keyframes": kf}
        ops.append({"op": "upsert_layer", "layer": layer})
        measurements[c.id] = {"width_px": round(w), "height_px": round(h)}
        if c.at >= span:
            raise ValueError(f"chip {c.id} enters after the recipe ends")
    if q.dividers:
        els = [{"id": f"dv{k}", "type": "line", "x1": _r((d.x - d.width / 2) * W), "y1": _r(d.y * H), "x2": _r((d.x + d.width / 2) * W),
                "y2": _r(d.y * H), "stroke": d.color or ink0, "stroke_width": _r(_px(t, 3)), "draw": [d.at, d.at + 10]} for k, d in enumerate(q.dividers)]
        ops.append({"op": "upsert_layer", "layer": _layer(q, "dividers", "svg", x=0, y=0, width=1, height=1, data={"view_box": [W, H], "elements": els})})
    frames = sorted({q.start_frame + c.at + 12 for c in q.chips} | {q.start_frame + m.at + m.frames + 2 for c in q.chips for m in c.moves})
    return {"ops": ops, "notes": [], "inspect_frames": frames[:6], "measurements": measurements}


# ---------------------------------------------------------------- number wall
class NumberWall(Base):
    recipe: Literal["number_wall"]
    text: str = Field(min_length=1, max_length=40)
    color: str = Field(default="#ffffff", pattern=HEX)
    accent: str = Field(default="#ff6b3d", pattern=HEX)
    hero_role: Role = "display"
    wall_role: Role = "headline"
    wall_at: int = Field(default=45, ge=8)
    rows: int = Field(default=5, ge=2, le=9)
    speed: float = Field(default=90, ge=0, le=600)  # px per second at 1080p
    wall_opacity: float = Field(default=.85, gt=0, le=1)


def number_wall(t, q: NumberWall):
    W, H = t["width"], t["height"]
    hero = _measure(t, q.hero_role, q.text, W * .95)
    hw = min(.98, hero["width"] / W + .02)
    hh = hero["height"] / H + .01
    hero_end = q.start_frame + q.wall_at + 10
    if hero_end >= q.end_frame:
        raise ValueError("wall_at must leave at least 10 frames before end_frame")
    ops = [{"op": "upsert_layer", "layer": {"id": f"{q.id}-hero", "kind": "text", "text": q.text, "start_frame": q.start_frame, "end_frame": hero_end,
            "attach_shot": q.attach_shot, "z": q.z + 1, "x": round((1 - hw) / 2, 4), "y": round(.5 - hh / 2, 4), "width": round(hw, 4), "height": round(hh, 4),
            "typography_role": q.hero_role, "color": q.color, "data": {"align": "center"},
            "effects": [{"name": "char_spring", "end_frame": 22, "params": {"amount": .6}}, {"name": "shadow", "end_frame": 1, "params": {"amount": 30}},
                        {"name": "zoom_in", "start_frame": q.wall_at - 4, "end_frame": q.wall_at + 10, "easing": "snappy", "params": {"amount": -.55}},
                        {"name": "fade_out", "start_frame": q.wall_at + 2, "end_frame": q.wall_at + 10}]}}]
    unit = _measure(t, q.wall_role, q.text + " ", W * 4)
    uw = max(1, unit["width"])
    reps = max(2, int(W * 2 / uw))
    row_h = unit["line_px"] / H
    dur = (q.end_frame - q.start_frame - q.wall_at) / FPS
    travel = min(W * .7, _px(t, q.speed) * dur)
    gap = (1 - q.rows * row_h) / (q.rows + 1)
    for i in range(q.rows):
        left = i % 2 == 0
        y = gap + i * (row_h + gap)
        ops.append({"op": "upsert_layer", "layer": {
            "id": f"{q.id}-row{i}", "kind": "text", "text": (" ".join([q.text] * reps)), "start_frame": q.start_frame + q.wall_at,
            "end_frame": q.end_frame, "attach_shot": q.attach_shot, "z": q.z, "x": -.25 if left else -.75, "y": round(y, 4), "width": 2,
            "height": round(row_h + .01, 4), "typography_role": q.wall_role, "color": q.accent if i % 2 else q.color, "opacity": q.wall_opacity,
            "effects": [{"name": "fade_in", "end_frame": 10 + i * 2}],
            "keyframes": {"x": [{"frame": 0, "value": 0}, {"frame": max(1, int(dur * FPS) - 1), "value": round(-travel if left else travel, 1)}]}}})
    notes = []
    if hero["width"] > W * .95:
        notes.append("Hero number is wider than the frame at this role size; use a smaller hero_role.")
    return {"ops": ops, "notes": notes, "inspect_frames": [q.start_frame + 20, q.start_frame + q.wall_at + 20],
            "measurements": {"hero_px": round(hero["width"]), "repeat_px": round(uw), "repeats_per_row": reps}}


# ---------------------------------------------------------------- hud card
class HudCard(Base):
    recipe: Literal["hud_card"]
    caption: str = Field(min_length=1, max_length=80)
    value_to: float = Field(allow_inf_nan=False)
    value_from: float = Field(default=0, allow_inf_nan=False)
    decimals: int = Field(default=0, ge=0, le=4)
    suffix: str = Field(default="", max_length=20)
    group: str = Field(default=" ", max_length=3)
    style: Literal["count", "roll", "scramble"] = "count"
    count_frames: int = Field(default=40, ge=1, le=900)
    x: float = Field(default=.74, ge=0, le=1)
    y: float = Field(default=.08, ge=0, le=1)
    width: float = Field(default=.2, gt=.05, le=.6)
    panel: str | None = Field(default=None, pattern=HEX)  # default: the design's surface colour
    color: str | None = Field(default=None, pattern=HEX)  # default: design text (caption) and accent (value)


def hud_card(t, q: HudCard):
    W, H = t["width"], t["height"]
    # Colours follow the film's palette unless given (a hard-coded royal blue sat in an amber monochrome film).
    roles = (t.get("design") or {}).get("color_roles") or {}
    panel = q.panel or roles.get("surface") or "#1f3c96"
    cap_color = q.color or roles.get("text") or "#ffffff"
    val_color = q.color or roles.get("accent") or roles.get("text") or "#ffffff"
    cap = _typo(t, "label")
    cap_h = cap["size"] * min(W, H) / 1080 * cap.get("line_height", 1.2) / H
    val = _typo(t, "title")
    val_h = val["size"] * min(W, H) / 1080 * val.get("line_height", 1.2) / H
    pad = .012
    # Reserve the caption lines it actually takes (a one-line caption left an empty band above the value).
    try:
        n_cap = min(2, max(1, len(_measure(t, "label", q.caption, (q.width - pad * 1.6) * W)["lines"])))
    except Exception:
        n_cap = 2
    h = cap_h * n_cap + val_h + pad * 3
    enter = [{"name": "fade_in", "end_frame": 8}, {"name": "slide_left", "end_frame": 12, "easing": "snappy", "params": {"amount": -60}}]
    ops = [{"op": "upsert_layer", "layer": _layer(q, "panel", "shape", x=q.x, y=q.y, width=q.width, height=round(h, 4), color=panel, opacity=.88,
                                                   data={"shape": "rectangle", "corner_radius": 10}, effects=enter)},
           {"op": "upsert_layer", "layer": _layer(q, "caption", "text", text=q.caption, x=round(q.x + pad * .8, 4), y=round(q.y + pad, 4),
                                                   width=round(q.width - pad * 1.6, 4), height=round(cap_h * n_cap, 4), typography_role="label", color=cap_color,
                                                   opacity=.85, effects=enter)},
           {"op": "upsert_layer", "layer": _layer(q, "value", "counter", x=round(q.x + pad * .8, 4), y=round(q.y + pad * 2 + cap_h * n_cap, 4),
                                                   width=round(q.width - pad * 1.6, 4), height=round(val_h, 4), typography_role="title", color=val_color,
                                                   data={"from": q.value_from, "to": q.value_to, "decimals": q.decimals, "suffix": q.suffix, "group": q.group, "style": q.style},
                                                   effects=[*enter, {"name": "progress", "start_frame": 6, "end_frame": 6 + q.count_frames, "easing": "ease_out"}])}]
    for k, op in enumerate(ops):
        if k:
            op["layer"]["z"] = q.z + 1
        op["layer"]["effects"] = [dict(e) for e in op["layer"]["effects"]]  # the layers share one entrance list
        for e in op["layer"]["effects"]:  # panel, caption, value arrive in turn (not one simultaneous pop)
            if e["name"] in ("fade_in", "rise", "slide_left", "slide_right", "wipe_right", "wipe_left", "progress"):
                e["start_frame"] = e.get("start_frame", 0) + 4 * k
                e["end_frame"] = e["end_frame"] + 4 * k
    d = q.end_frame - q.start_frame
    if d > 40:  # the card leaves with a short fade instead of vanishing (abrupt_exit)
        for op in ops:
            op["layer"]["effects"].append({"name": "fade_out", "start_frame": d - 10, "end_frame": d - 1})
    return {"ops": ops, "notes": [], "inspect_frames": [q.start_frame + 14, q.start_frame + 8 + q.count_frames]}


# ---------------------------------------------------------------- stat line
class StatLine(Base):
    recipe: Literal["stat_line"]
    text: str = Field(min_length=1, max_length=160)  # **strong** and ==accent== allowed
    y: float = Field(default=.8, ge=0, le=1)
    role: Role = "title"
    color: str = Field(default="#ffffff", pattern=HEX)
    accent: str = Field(default="#ffd166", pattern=HEX)
    entrance: Literal["word", "mask", "fade"] = "word"


def stat_line(t, q: StatLine):
    W, H = t["width"], t["height"]
    plain = q.text.replace("**", "").replace("==", "")
    m = _measure(t, q.role, plain, W * .86)
    w = min(.9, m["width"] / W + .04)
    h = m["height"] / H + .01
    d = q.end_frame - q.start_frame
    entry = {"word": [{"name": "word_reveal", "end_frame": min(d - 1, max(10, len(plain.split()) * 4))}],
             "mask": [{"name": "mask_reveal", "end_frame": min(d - 1, 18)}],
             "fade": [{"name": "fade_in", "end_frame": 10}, {"name": "rise", "end_frame": 12, "params": {"amount": 20}}]}[q.entrance]
    fx = [*entry, {"name": "shadow", "end_frame": 1, "params": {"amount": 22}}]
    if d > 30:
        fx.append({"name": "fade_out", "start_frame": d - 10, "end_frame": d - 1})
    text = q.text if len(m["lines"]) == 1 else q.text  # wrapping is left to the browser; measurement flags long lines
    layer = _layer(q, "", "text", text=text, x=round((1 - w) / 2, 4), y=round(min(q.y, .97 - h), 4), width=round(w, 4), height=round(h, 4),
                   typography_role=q.role, color=q.color, data={"align": "center", "accent": q.accent}, effects=fx)
    notes = [f"Wraps to {len(m['lines'])} lines; stat lines read best on one."] if len(m["lines"]) > 1 else []
    words = len(plain.split())
    if words / max(.5, d / FPS - .4) > 3.2:
        notes.append(f"{words} words in {d / FPS:.1f}s exceeds ~3 words/s.")
    return {"ops": [{"op": "upsert_layer", "layer": layer}], "notes": notes, "inspect_frames": [q.start_frame + 16],
            "measurements": {"lines": len(m["lines"]), "text_width_px": round(m["width"])}}


# ---------------------------------------------------------------- particles
class ParticleFx(Base):
    recipe: Literal["particles"]
    preset: Literal["bunch", "stream", "starfield", "collision"]
    box: list[float] = Field(default=[0, 0, 1, 1], min_length=4, max_length=4)
    color: str = Field(default="#ff9a3c", pattern=HEX)
    secondary_color: str = Field(default="#7fd8ff", pattern=HEX)
    count: int | None = Field(default=None, ge=1, le=1500)
    angle: float = Field(default=-8, ge=-360, le=360)
    origin: list[float] = Field(default=[.5, .5], min_length=2, max_length=2)  # collision, box-relative
    travel_frames: int | None = Field(default=None, ge=6)  # bunch: frames to cross the box; collision: frames to draw tracks
    seed: int = Field(default=7, ge=0)


def particles(t, q: ParticleFx):
    d = q.end_frame - q.start_frame
    presets = {"bunch": {"mode": "bunch", "count": 500, "length": .3, "spread": .035, "radius": 2.4, "glow": 3},
               "stream": {"mode": "stream", "count": 700, "spread": .03, "radius": 2, "speed": .35, "glow": 3},
               "starfield": {"mode": "drift", "count": 420, "radius": 1.8, "speed": .015, "twinkle": .6, "glow": 2, "mix": .25},
               "collision": {"mode": "tracks", "count": 90, "radius": 3, "curvature": 1.4, "stroke_width": 2, "mix": .4, "origin": q.origin}}
    data = {**presets[q.preset], "seed": q.seed, "angle": q.angle, "secondary_color": q.secondary_color}
    if q.count:
        data["count"] = min(q.count, 300) if q.preset == "collision" else q.count
    fx = []
    if q.preset in ("bunch", "collision"):
        span = min(d, q.travel_frames or (d if q.preset == "bunch" else 45))
        fx.append({"name": "progress", "end_frame": span, "easing": "linear" if q.preset == "bunch" else "smooth"})
    layer = _layer(q, "", "particles", x=q.box[0], y=q.box[1], width=q.box[2], height=q.box[3], color=q.color, blend="screen", data=data, effects=fx)
    return {"ops": [{"op": "upsert_layer", "layer": layer}], "notes": [], "inspect_frames": [q.start_frame + d // 3, q.start_frame + 2 * d // 3]}


# ---------------------------------------------------------------- camera stage (big-canvas explainer camera)
class CamStop(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at: int = Field(ge=0)  # recipe-local frame when the camera has arrived
    cx: float = Field(ge=0, le=1)  # focus point on the canvas (normalized)
    cy: float = Field(ge=0, le=1)
    zoom: float = Field(default=1, gt=.1, le=40)  # 1 = canvas pixels at frame scale; map dives go far deeper (vector children stay sharp)
    frames: int = Field(default=18, ge=1, le=240)  # duration of the move that ends at `at`
    bezier: list[float] = Field(default=[.7, 0, .2, 1], min_length=4, max_length=4)
    # land: long deceleration onto the target (map arrival); dive: accelerate into it; glide: even in-out. Overrides bezier.
    move: Literal["custom", "land", "dive", "glide"] = "custom"
    drift: list[float] = Field(default=[.015, 0], min_length=2, max_length=2)  # frame widths/heights per second after landing


class StageChild(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float  # canvas-normalized box
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    layer: dict  # an ordinary layer (kind, text/asset/data, effects, z...) without x/y/width/height


class CameraStage(Base):
    recipe: Literal["camera_stage"]
    canvas: list[float] = Field(default=[3, 2], min_length=2, max_length=2)  # canvas size in frame widths/heights
    children: list[StageChild] = Field(min_length=1, max_length=40)
    stops: list[CamStop] = Field(min_length=1, max_length=40)
    motion_blur: bool = True
    step_frames: int = Field(default=1, ge=1, le=4)  # 2 = the infographic house style "on twos"
    # log: zoom changes by equal ratios per frame and the centre moves with 1/zoom, so a deep zoom approaches its target
    # steadily instead of crawling and then swooping (moves with a zoom ratio > 1.3 are sampled every 2 frames).
    zoom_space: Literal["log", "linear"] = "log"

    @model_validator(mode="after")
    def order(self):
        ats = [s.at for s in self.stops]
        if ats != sorted(ats) or len(set(ats)) != len(ats):
            raise ValueError("stops must have increasing `at` frames")
        if self.stops[0].at != 0:
            raise ValueError("the first stop is the opening framing: at = 0")
        for a, b in zip(self.stops, self.stops[1:]):
            if b.at - b.frames <= a.at:
                raise ValueError(f"the move into the stop at {b.at} starts before the camera arrives at the stop at {a.at}")
        if self.stops[-1].at >= self.end_frame - self.start_frame:
            raise ValueError("last stop must arrive before end_frame")
        if any(v < 1 or v > 6 for v in self.canvas):
            raise ValueError("canvas is 1..6 frames wide/high")
        for c in self.children:
            if {"x", "y", "width", "height", "start_frame", "end_frame"} & set(c.layer):
                raise ValueError("child layers take position from the stage (x/y/width/height) and timing from the recipe")
            if {"x", "y", "scale"} & set(c.layer.get("keyframes") or {}):
                raise ValueError("child x/y/scale keyframes are driven by the camera; animate with effects instead")
        return self


MOVES = {"land": [.16, 1, .3, 1], "dive": [.7, 0, .84, 0], "glide": [.45, 0, .55, 1]}


def _bezier_ease(x, b):
    """CSS cubic-bezier(x1, y1, x2, y2) evaluated at progress x (Newton on x(t), bisection fallback)."""
    x1, y1, x2, y2 = b
    bx = lambda t: 3 * x1 * t * (1 - t) ** 2 + 3 * x2 * t * t * (1 - t) + t ** 3
    by = lambda t: 3 * y1 * t * (1 - t) ** 2 + 3 * y2 * t * t * (1 - t) + t ** 3
    lo, hi, t = 0.0, 1.0, x
    for _ in range(40):
        v = bx(t) - x
        if abs(v) < 1e-7:
            break
        lo, hi = (t, hi) if v < 0 else (lo, t)
        t = (lo + hi) / 2
    return by(t)


def camera_stage(t, q: CameraStage):
    W, H = t["width"], t["height"]
    CW, CH = q.canvas[0] * W, q.canvas[1] * H
    span = q.end_frame - q.start_frame
    # Camera keys (local frame, centre px on canvas, zoom, bezier into this key).
    keys = [(0, q.stops[0].cx * CW, q.stops[0].cy * CH, q.stops[0].zoom, None)]
    def drifted(stop, frames):
        cx, cy = stop.cx * CW, stop.cy * CH
        return cx + stop.drift[0] * W * frames / FPS / stop.zoom, cy + stop.drift[1] * H * frames / FPS / stop.zoom
    for a, b in zip(q.stops, q.stops[1:]):
        leave = b.at - b.frames
        x, y = drifted(a, leave - a.at)
        keys.append((leave, x, y, a.zoom, "linear"))
        bez = MOVES.get(b.move, b.bezier)
        z0, z1 = a.zoom, b.zoom
        if q.zoom_space == "log" and max(z0, z1) / min(z0, z1) > 1.3:
            for f in range(leave + 2, b.at, 2):
                u = _bezier_ease((f - leave) / b.frames, bez)
                z = z0 * (z1 / z0) ** u
                k = (1 / z0 - 1 / z) / (1 / z0 - 1 / z1)  # centre follows 1/zoom: screen offsets shrink in proportion
                keys.append((f, x + (b.cx * CW - x) * k, y + (b.cy * CH - y) * k, z, "linear"))
            keys.append((b.at, b.cx * CW, b.cy * CH, b.zoom, "linear"))
        else:
            keys.append((b.at, b.cx * CW, b.cy * CH, b.zoom, bez))
    last = q.stops[-1]
    x, y = drifted(last, span - 1 - last.at)
    keys.append((span - 1, x, y, last.zoom, "linear"))
    keys = [k for i, k in enumerate(keys) if i == 0 or k[0] > keys[i - 1][0]]
    ops, notes = [], []
    for i, c in enumerate(q.children):
        pcx, pcy = (c.x + c.width / 2) * CW, (c.y + c.height / 2) * CH
        screen = [((pcx - kx) * kz + W / 2, (pcy - ky) * kz + H / 2, kz) for _, kx, ky, kz, _ in keys]
        # Base the layer where it is closest to frame centre so pixel offsets stay inside keyframe limits.
        bx, by, _ = min(screen, key=lambda s: abs(s[0] - W / 2) + abs(s[1] - H / 2))
        w_n, h_n = c.width * CW / W, c.height * CH / H
        if w_n > 2 or h_n > 2:
            raise ValueError(f"child {i} is larger than 2 frames at zoom 1; split it or use a smaller canvas")
        lay = dict(c.layer)
        lid = lay.get("id") or f"{q.id}-c{i}"
        x0, y0 = bx / W - w_n / 2, by / H - h_n / 2
        x0c, y0c = min(2, max(-1, x0)), min(2, max(-1, y0))
        kf = dict(lay.get("keyframes") or {})
        ease = lambda b: ({"bezier": b} if isinstance(b, list) else {"easing": b or "linear"})
        offx = [round(sx - (x0c + w_n / 2) * W, 1) for sx, _, _ in screen]
        offy = [round(sy - (y0c + h_n / 2) * H, 1) for _, sy, _ in screen]
        if max(map(abs, offx + offy)) > 40000:
            raise ValueError(f"child {i} travels more than 40000 px; reduce the canvas or the zoom")
        kf["x"] = [{"frame": k[0], "value": ox, **ease(k[4])} for k, ox in zip(keys, offx)]
        kf["y"] = [{"frame": k[0], "value": oy, **ease(k[4])} for k, oy in zip(keys, offy)]
        kf["scale"] = [{"frame": k[0], "value": round(k[3], 4), **ease(k[4])} for k in keys]
        fx = list(lay.get("effects") or [])
        if q.motion_blur and not any(e["name"] == "motion_blur" for e in fx):
            fx.append({"name": "motion_blur", "end_frame": 1, "params": {"amount": 180}})
        lay.update(id=lid, start_frame=q.start_frame, end_frame=q.end_frame, attach_shot=q.attach_shot, x=round(x0c, 4), y=round(y0c, 4),
                   width=round(w_n, 4), height=round(h_n, 4), keyframes=kf, effects=fx[:16])
        lay.setdefault("z", q.z)
        if q.step_frames > 1:
            lay["step_frames"] = q.step_frames
        ops.append({"op": "upsert_layer", "layer": lay})
    moves = [(a.at - a.frames, a.at) for a in q.stops[1:]]
    return {"ops": ops, "notes": notes, "inspect_frames": [q.start_frame + s.at + 2 for s in q.stops][:6] + [q.start_frame + (m0 + m1) // 2 for m0, m1 in moves][:2],
            "measurements": {"camera_keys": len(keys), "children": len(ops), "moves": moves}}


# ---------------------------------------------------------------- pie and column charts (stroke builds)
class Pie(Base):
    recipe: Literal["pie"]
    box: list[float] = Field(default=[.3, .15, .4, .7], min_length=4, max_length=4)
    values: list[float] = Field(min_length=2, max_length=8)
    labels: list[str] = Field(default_factory=list, max_length=8)
    colors: list[str] = Field(default_factory=lambda: ["#c6f06a", "#3cd2ff", "#ff6b3d", "#ffffff", "#9b7bff", "#ffd166", "#5ce1a6", "#ff8fb1"], min_length=2, max_length=8)
    donut: float = Field(default=0, ge=0, le=.8)  # inner radius as a fraction of the outer radius
    build_frames: int = Field(default=24, ge=6, le=240)
    pop: int | None = Field(default=None, ge=0)  # slice to slide out after the build
    pop_frames: int = Field(default=9, ge=2, le=60)
    label_size: float = Field(default=30, gt=6, le=120)

    @model_validator(mode="after")
    def vals(self):
        if any(v <= 0 for v in self.values):
            raise ValueError("pie values must be positive")
        if self.labels and len(self.labels) != len(self.values):
            raise ValueError("labels must match values")
        if self.pop is not None and self.pop >= len(self.values):
            raise ValueError("pop names a slice index")
        return self


def pie(t, q: Pie):
    W, H = t["width"], t["height"]
    bw, bh = q.box[2] * W, q.box[3] * H
    cx, cy, R = bw / 2, bh / 2, min(bw, bh) * .42
    total = sum(q.values)
    rm, sw = R * (1 + q.donut) / 2, R * (1 - q.donut)
    circle = f"M{_r(cx)} {_r(cy - rm)}A{_r(rm)} {_r(rm)} 0 1 1 {_r(cx - .01)} {_r(cy - rm)}"  # clockwise from 12 o'clock
    fs = _px(t, q.label_size)
    base, popped, cum = [], [], 0.0
    for i, v in enumerate(q.values):
        share = v / total
        a, b = int(q.build_frames * cum), max(int(q.build_frames * cum) + 1, int(q.build_frames * (cum + share)))
        el = {"id": f"s{i}", "type": "path", "d": circle, "stroke": q.colors[i % len(q.colors)], "stroke_width": _r(sw),
              "trim": {"frames": [a, b], "start": [cum, cum], "end": [cum, cum + share]}, "trim_bezier": [0, 0, 1, 1]}
        (popped if i == q.pop else base).append(el)
        th = 2 * math.pi * (cum + share / 2)
        if q.labels:
            lx, ly = cx + math.sin(th) * R * 1.18, cy - math.cos(th) * R * 1.18
            base.append({"id": f"l{i}", "type": "text", "x": _r(lx), "y": _r(ly + fs * .35), "text": f"{q.labels[i]} {share * 100:.0f}%",
                         "anchor": "start" if math.sin(th) > .2 else "end" if math.sin(th) < -.2 else "middle", "font_size": _r(fs), "font_weight": 600,
                         "fill": "#ffffff", "stroke": "#ffffff", "appear": [q.build_frames + 2, q.build_frames + 12]})
        if i == q.pop:
            pop_dir = (math.sin(th), -math.cos(th))
        cum += share
    data = lambda els: {"view_box": [_r(bw), _r(bh)], "elements": els, "font_family": _font(t, "label")}
    ops = [{"op": "upsert_layer", "layer": _layer(q, "", "svg", x=q.box[0], y=q.box[1], width=q.box[2], height=q.box[3], data=data(base))}]
    if popped:
        d = R * .06
        p0, p1 = q.build_frames + 4, q.build_frames + 4 + q.pop_frames
        kf = {"x": [{"frame": 0, "value": 0}, {"frame": p0, "value": 0}, {"frame": p1, "value": _r(pop_dir[0] * d), "easing": "snappy"}],
              "y": [{"frame": 0, "value": 0}, {"frame": p0, "value": 0}, {"frame": p1, "value": _r(pop_dir[1] * d), "easing": "snappy"}]}
        ops.append({"op": "upsert_layer", "layer": _layer(q, "pop", "svg", x=q.box[0], y=q.box[1], width=q.box[2], height=q.box[3], data=data(popped),
                                                          keyframes=kf, z=q.z + 1)})
    return {"ops": ops, "notes": [], "inspect_frames": [q.start_frame + q.build_frames // 2, q.start_frame + q.build_frames + q.pop_frames + 8]}


class Columns(Base):
    recipe: Literal["columns"]
    box: list[float] = Field(default=[.12, .15, .76, .7], min_length=4, max_length=4)
    values: list[float] = Field(min_length=1, max_length=24)
    labels: list[str] = Field(default_factory=list, max_length=24)
    max_value: float | None = Field(default=None, gt=0)
    color: str = Field(default="#c6f06a", pattern=HEX)
    axis_color: str = Field(default="#ffffff", pattern=HEX)
    stagger: int = Field(default=10, ge=0, le=60)
    grow: int = Field(default=12, ge=2, le=120)
    value_labels: bool = True
    label_size: float = Field(default=28, gt=6, le=120)

    @model_validator(mode="after")
    def vals(self):
        if any(v < 0 for v in self.values):
            raise ValueError("column values are non-negative")
        if self.labels and len(self.labels) != len(self.values):
            raise ValueError("labels must match values")
        return self


def columns(t, q: Columns):
    W, H = t["width"], t["height"]
    bw, bh = q.box[2] * W, q.box[3] * H
    fs = _px(t, q.label_size)
    top, bottom = fs * 1.6, bh - fs * 1.8
    n, hi = len(q.values), q.max_value or max(q.values) or 1
    slot = bw / n
    barw = slot * .58
    els = [{"id": "base", "type": "path", "d": f"M0 {_r(bottom)}L{_r(bw)} {_r(bottom)}", "stroke": q.axis_color, "stroke_width": _r(_px(t, 3)),
            "trim": {"frames": [0, 12], "start": [.5, 0], "end": [.5, 1]}}]  # baseline grows out from the centre
    for i, v in enumerate(q.values):
        x = slot * (i + .5)
        yt = bottom - (bottom - top) * min(1, v / hi)
        a = 12 + i * q.stagger
        els.append({"id": f"b{i}", "type": "path", "d": f"M{_r(x)} {_r(bottom)}L{_r(x)} {_r(yt)}", "stroke": q.color, "stroke_width": _r(barw),
                    "linecap": "butt", "trim": {"frames": [a, a + q.grow], "start": [0, 0], "end": [0, 1]}})
        if q.labels:
            els.append({"id": f"l{i}", "type": "text", "x": _r(x), "y": _r(bottom + fs * 1.3), "text": q.labels[i], "anchor": "middle", "font_size": _r(fs),
                        "font_weight": 500, "fill": q.axis_color, "stroke": q.axis_color, "appear": [a, a + 8]})
        if q.value_labels:
            els.append({"id": f"v{i}", "type": "text", "x": _r(x), "y": _r(yt - fs * .4), "text": f"{v:g}", "anchor": "middle", "font_size": _r(fs),
                        "font_weight": 700, "fill": q.axis_color, "stroke": q.axis_color, "appear": [a + q.grow - 2, a + q.grow + 6]})
    layer = _layer(q, "", "svg", x=q.box[0], y=q.box[1], width=q.box[2], height=q.box[3],
                   data={"view_box": [_r(bw), _r(bh)], "elements": els, "font_family": _font(t, "label")})
    end = 12 + (n - 1) * q.stagger + q.grow
    notes = [] if end < q.end_frame - q.start_frame else ["The last column finishes after the layer ends; shorten stagger or extend end_frame."]
    return {"ops": [{"op": "upsert_layer", "layer": layer}], "notes": notes, "inspect_frames": [q.start_frame + end + 4]}


# ---------------------------------------------------------------- text window zoom
class TextWindowZoom(Base):
    recipe: Literal["text_window_zoom"]
    text: str = Field(min_length=1, max_length=24)
    asset_id: str = Field(min_length=1, max_length=100)  # footage or still seen through the letters
    media_kind: Literal["video", "image"] = "video"
    source_start: float = Field(default=0, ge=0)
    role: Role = "display"
    y: float = Field(default=.35, ge=0, le=1)
    hold: int = Field(default=40, ge=0)  # frames the word holds before the zoom
    zoom_frames: int = Field(default=30, ge=6, le=240)
    zoom_to: float | None = Field(default=None, ge=4, le=100)  # default: enough for the stroke to cover the frame width (max 100)
    letter: int | None = Field(default=None, ge=0)  # which character to fly through (default: the thickest stroke in the word)


def text_window_zoom(t, q: TextWindowZoom):
    """Footage seen through a word, then the camera flies through the thickest stroke of one letter until the footage
    fills the frame. The anchor is placed on a solid part of the glyph (distance transform), never in a counter, so the
    zoom ends on picture rather than on black."""
    import cv2
    import numpy as np
    from .design_library import glyph_mask
    W, H = t["width"], t["height"]
    ty = _typo(t, q.role)
    m = _measure(t, q.role, q.text, W * .95)
    if len(m["lines"]) > 1:
        raise ValueError("text_window_zoom needs one line; shorten the word or use a smaller role")
    mask, _ = glyph_mask(ty["font_id"], [q.text], m["px"], ty.get("weight", 400), ty.get("tracking", 0), ty.get("line_height", 1.2))
    mh, mw = mask.shape
    dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    if q.letter is not None:  # restrict to one character's advance
        k = q.letter
        if k >= len(q.text):
            raise ValueError("letter index outside the text")
        from .design_library import layout_text
        x_a = layout_text(ty["font_id"], q.text[:k], m["px"], 4000, ty.get("weight", 400))["line_widths"][0] if k else 0
        x_b = layout_text(ty["font_id"], q.text[:k + 1], m["px"], 4000, ty.get("weight", 400))["line_widths"][0]
        band = np.zeros_like(dist)
        band[:, int(max(0, x_a)):int(min(mw, x_b + 4))] = 1
        dist = dist * band
    if dist.max() <= 0:
        raise ValueError("the chosen character has no solid stroke to fly through (a space?)")
    py, px = np.unravel_index(int(np.argmax(dist)), dist.shape)
    bw, bh = mw / W, mh / H
    x0 = (1 - bw) / 2
    zoom_to = q.zoom_to or min(100.0, round(1.15 * W / (2 * float(dist.max())), 1))
    end_zoom = q.start_frame + q.hold + q.zoom_frames
    if end_zoom >= q.end_frame:
        raise ValueError("end_frame must leave time after the zoom for the footage to continue full-frame")
    word = _layer(q, "word", "text", text=q.text, x=round(x0, 4), y=q.y, width=round(bw, 4), height=round(bh, 4), typography_role=q.role,
                  color="#ffffff", anchor=[round(px / mw, 4), round(py / mh, 4)], end_frame=end_zoom,
                  keyframes={"scale": [{"frame": 0, "value": 1}, {"frame": q.hold, "value": 1}, {"frame": q.hold + q.zoom_frames - 1, "value": zoom_to, "easing": "ease_in"}]})
    # Bring the anchor to frame centre while zooming so the stroke grows around the middle of the picture.
    ax_px, ay_px = (x0 * W + px), (q.y * H + py)
    for key, delta in (("x", W / 2 - ax_px), ("y", H / 2 - ay_px)):
        word["keyframes"][key] = [{"frame": 0, "value": 0}, {"frame": q.hold, "value": 0},
                                  {"frame": q.hold + q.zoom_frames - 1, "value": round(delta, 1), "easing": "ease_in_out"}]
    if q.hold == 0:
        for key in ("scale", "x", "y"):
            word["keyframes"][key] = [word["keyframes"][key][0], word["keyframes"][key][2]]
    # The matted plate carries the zoom; the same footage continues unmatted from the frame the stroke fills the view.
    plate = _layer(q, "plate", q.media_kind, asset_id=q.asset_id, source_start=q.source_start, x=0, y=0, end_frame=end_zoom,
                   width=1, height=1, fit="cover", matte={"source": word["id"], "mode": "alpha"})
    full = _layer(q, "full", q.media_kind, asset_id=q.asset_id, source_start=round(q.source_start + (end_zoom - q.start_frame) / FPS, 4), x=0, y=0,
                  start_frame=end_zoom, width=1, height=1, fit="cover")
    notes = [] if zoom_to * 2 * float(dist.max()) >= W else [f"At x{zoom_to} the stroke covers {zoom_to * 2 * float(dist.max()):.0f} px of {W}; the cut to full frame finishes the move."]
    return {"ops": [{"op": "upsert_layer", "layer": word}, {"op": "upsert_layer", "layer": plate}, {"op": "upsert_layer", "layer": full}], "notes": notes,
            "inspect_frames": [q.start_frame + max(0, q.hold - 2), q.start_frame + q.hold + q.zoom_frames // 2, q.start_frame + q.hold + q.zoom_frames + 2],
            "measurements": {"anchor_px_in_word": [int(px), int(py)], "word_px": [mw, mh], "stroke_half_width_px": round(float(dist.max()), 1), "zoom_to": zoom_to}}


# ---------------------------------------------------------------- dispatcher
# ---------------------------------------------------------------- documentary time card and chapter motif
class DocTimecard(Base):
    """Investigative/map documentaries mark every jump in time: a small tracked label (PAST / PRESENT / a place), the
    year in a mono face, and when the story jumps, the year rolls from the previous one. Bottom-left by default, away
    from captions; one consistent position for the whole film."""
    recipe: Literal["doc_timecard"]
    year: int = Field(ge=-9999, le=9999)
    roll_from: int | None = Field(default=None, ge=-9999, le=9999)  # previous year: the digits roll to the new one
    label: str = Field(default="", max_length=40)  # e.g. QUÁ KHỨ / HIỆN TẠI / a place
    detail: str = Field(default="", max_length=60)  # optional third line (date, place)
    corner: Literal["bottom_left", "top_left", "bottom_right", "top_right"] = "bottom_left"
    roll_frames: int = Field(default=30, ge=6, le=180)
    color: str = Field(default="#ffffff", pattern=HEX)
    accent: str = Field(default="#e8b04a", pattern=HEX)
    font_id: str = "ibmplexmono"


def doc_timecard(t, q: DocTimecard):
    W, H = t["width"], t["height"]
    k = min(W, H) / 1080
    label_px, year_px, det_px = round(30 * k), round(64 * k), round(30 * k)  # ≥ 30 px at 1080: readable on a phone over footage
    m = .06
    right = q.corner.endswith("right")
    top = q.corner.startswith("top")
    lh = 1.25
    blocks = [("label", q.label.upper(), label_px)] if q.label else []
    blocks.append(("year", str(q.year), year_px))
    if q.detail:
        blocks.append(("detail", q.detail, det_px))
    heights = [px * lh / H for _, _, px in blocks]
    total = sum(heights) + .004 * (len(blocks) - 1) + .012
    y = m if top else 1 - m - total
    width = .26
    x = 1 - m - width if right else m
    align = "right" if right else "left"
    d = q.end_frame - q.start_frame
    enter = lambda k_: [{"name": "fade_in", "start_frame": k_ * 4, "end_frame": k_ * 4 + 10, "easing": "ease_out"},
                        {"name": "slide_right" if not right else "slide_left", "start_frame": k_ * 4, "end_frame": k_ * 4 + 14,
                         "params": {"amount": -24 if not right else 24}, "bezier": [.22, 1, .36, 1]}]
    leave = [{"name": "fade_out", "start_frame": d - 10, "end_frame": d - 1}] if d > 40 else []
    ops, yy = [], y
    rule_y = None
    for i, ((name, text, px), hgt) in enumerate(zip(blocks, heights)):
        fx = enter(i) + leave + [{"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 10}}]
        common = dict(x=round(x, 4), y=round(yy, 4), width=width, height=round(hgt + .004, 4), color=q.accent if name == "label" else q.color,
                      font_id=q.font_id, font_size=px, line_height=lh)
        if name == "year":
            frm = q.roll_from if q.roll_from is not None else q.year
            lay = _layer(q, "year", "counter", **common, font_weight=600,
                         data={"from": frm, "to": q.year, "decimals": 0, "group": "", "style": "roll" if q.roll_from is not None else "count", "align": align},
                         effects=fx + [{"name": "progress", "start_frame": 8, "end_frame": 8 + q.roll_frames, "easing": "ease_in_out"}])
            rule_y = yy + hgt + .003
        else:
            lay = _layer(q, name, "text", text=text, **common, font_weight=500 if name == "label" else 400, data={"align": align},
                         effects=fx + ([{"name": "tracking", "start_frame": 0, "end_frame": 1, "params": {"amount": .25, "from_em": .25, "center": False}}] if name == "label" else []))
        ops.append({"op": "upsert_layer", "layer": lay})
        yy += hgt + .004
    # A thin accent rule under the year that draws out from the anchored side.
    if rule_y is not None:
        ops.append({"op": "upsert_layer", "layer": _layer(q, "rule", "shape", x=round(x, 4), y=round(rule_y, 4), width=.08, height=round(2 * k / H + .0005, 4),
                                                          color=q.accent, data={"shape": "rectangle", "corner_radius": 0},
                                                          effects=[{"name": "wipe_right" if not right else "wipe_left", "start_frame": 6, "end_frame": 20, "easing": "ease_out"}] + leave)})
        if right:
            ops[-1]["layer"]["x"] = round(x + width - .08, 4)
    notes = []
    if q.roll_from is not None and abs(q.year - q.roll_from) > 400 and q.roll_frames < 45:
        notes.append("A long jump in time reads better with roll_frames ≥ 45.")
    return {"ops": ops, "notes": notes, "inspect_frames": [q.start_frame + 4, q.start_frame + 10 + q.roll_frames]}


class MotifProgress(Base):
    """A recurring chapter motif: N ticks on a thin line with the current chapter lit and named. Re-used at every
    chapter break so viewers feel progress through a long documentary."""
    recipe: Literal["motif_progress"]
    chapters: list[str] = Field(min_length=2, max_length=12)
    current: int = Field(ge=0)
    y: float = Field(default=.9, ge=.05, le=.95)
    width: float = Field(default=.5, gt=.1, le=.9)
    color: str = Field(default="#ffffff", pattern=HEX)
    accent: str = Field(default="#e8b04a", pattern=HEX)
    font_id: str = "inter"

    @model_validator(mode="after")
    def cur(self):
        if self.current >= len(self.chapters):
            raise ValueError("current is a chapter index")
        return self


def motif_progress(t, q: MotifProgress):
    W, H = t["width"], t["height"]
    n = len(q.chapters)
    x0 = (1 - q.width) / 2
    step = q.width / (n - 1)
    k = min(W, H) / 1080
    d = q.end_frame - q.start_frame
    leave = [{"name": "fade_out", "start_frame": d - 12, "end_frame": d - 1}] if d > 40 else []
    Y = round(q.y * H, 2)
    els = [{"id": "base", "type": "line", "x1": round(x0 * W, 2), "y1": Y, "x2": round((x0 + q.width) * W, 2), "y2": Y, "stroke": q.color,
            "stroke_width": round(2 * k, 2), "opacity": .45, "draw": [0, 18]}]
    if q.current > 0:
        els.append({"id": "done", "type": "line", "x1": round(x0 * W, 2), "y1": Y, "x2": round((x0 + q.current * step) * W, 2), "y2": Y,
                    "stroke": q.color, "stroke_width": round(3 * k, 2), "draw": [10, 30]})
    for i in range(n):
        on, done = i == q.current, i < q.current
        els.append({"id": f"t{i}", "type": "circle", "cx": round((x0 + i * step) * W, 2), "cy": Y, "r": round((9 if on else 5) * k, 2),
                    "fill": q.accent if on else (q.color if done else "#000000"), "stroke": q.accent if on else q.color,
                    "stroke_width": round(2 * k, 2), "appear": [6 + 3 * i, 12 + 3 * i], **({"ripple": [20, 50], "ripple_count": 2} if on else {})})
    svg = _layer(q, "line", "svg", x=0, y=0, width=1, height=1, data={"view_box": [W, H], "elements": els}, effects=[*leave])
    lab_px = round(26 * k)
    label = _layer(q, "label", "text", text=q.chapters[q.current].upper(), x=round(x0 + q.current * step - .2, 4), y=round(q.y - .055, 4), width=.4,
                   height=round(lab_px * 1.3 / H, 4), font_id=q.font_id, font_size=lab_px, font_weight=600, line_height=1.3, color=q.accent,
                   data={"align": "center"}, effects=[{"name": "fade_in", "start_frame": 14, "end_frame": 26},
                                                       {"name": "tracking", "start_frame": 14, "end_frame": 40, "easing": "ease_out", "params": {"amount": .22, "from_em": .4, "center": True}}, *leave])
    label["z"] = q.z + 1
    return {"ops": [{"op": "upsert_layer", "layer": svg}, {"op": "upsert_layer", "layer": label}], "notes": [],
            "inspect_frames": [q.start_frame + 30]}


class Evidence3D(Base):
    """An archival photo or document presented as the physical object it is: a thin card on a dark table with a soft
    shadow and a slight tilt, a slow push toward the region that matters, then that region marked (projected exactly from
    the final camera) with a caption and the source line. The image stays the evidence: the move only directs attention."""
    recipe: Literal["evidence_3d"]
    asset_id: str = Field(min_length=1, max_length=100)  # the image (scan, photo, document page)
    aspect: float | None = Field(default=None, gt=.2, le=5)  # image width / height (read from the asset when omitted)
    focus: list[float] | None = Field(default=None, min_length=4, max_length=4)  # [x0, y0, x1, y1] on the image, normalised
    caption: str = Field(default="", max_length=90)
    source: str = Field(min_length=1, max_length=140)  # provenance shown on screen (evidence needs its source)
    tilt_deg: float = Field(default=10, ge=0, le=35)
    push: float = Field(default=.6, ge=0, le=.9)  # how far the camera travels toward the focus (0 = hold wide)
    arrive: float = Field(default=.62, ge=.3, le=.9)  # share of the span the push takes; the rest holds for reading
    mark: Literal["box", "underline", "none"] = "box"
    background: str = Field(default="#0b0c0e", pattern=HEX)
    accent: str = Field(default="#e8b04a", pattern=HEX)
    color: str = Field(default="#f2f2ee", pattern=HEX)
    font_id: str = "inter"

    @model_validator(mode="after")
    def region(self):
        if self.focus and not (0 <= self.focus[0] < self.focus[2] <= 1 and 0 <= self.focus[1] < self.focus[3] <= 1):
            raise ValueError("focus is [x0, y0, x1, y1] inside the image (0..1)")
        if self.end_frame - self.start_frame < 75:
            raise ValueError("evidence_3d needs at least 75 frames (push, then a readable hold)")
        return self


def _project(p, eye, target, fov_deg, aspect):
    """World point → normalised screen [x, y] (y down) for a look-at perspective camera (three.js convention)."""
    import numpy as np
    f = np.array(target, float) - np.array(eye, float)
    f /= np.linalg.norm(f)
    r = np.cross(f, [0, 1, 0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    v = np.array(p, float) - np.array(eye, float)
    x, y, z = v @ r, v @ u, v @ f
    k = 1 / np.tan(np.radians(fov_deg) / 2)
    return [float(.5 + .5 * (x * k / aspect) / z), float(.5 - .5 * (y * k) / z)]


def evidence_3d(t, q: Evidence3D):
    import math
    W, H = t["width"], t["height"]
    A = q.aspect or 1.5
    d = q.end_frame - q.start_frame
    h = 2.0  # card height in world units; width follows the image
    w = h * A
    tilt = math.radians(q.tilt_deg)
    cy = -1.15 + .02 + h / 2 * math.cos(tilt) + .05  # resting just above the table (ground plane at y = -1.15)

    def world(u, v):  # image point (0..1, y down) → world, card tilted back about its centre
        x, y = (u - .5) * w, (.5 - v) * h
        return [x, cy + y * math.cos(tilt), -y * math.sin(tilt)]
    fov, aspect = 30, W / H
    tan = math.tan(math.radians(fov / 2))
    D0 = max(h / 2 / tan, w / 2 / (tan * aspect)) * 1.18
    fx = [(q.focus[0] + q.focus[2]) / 2, (q.focus[1] + q.focus[3]) / 2] if q.focus else [.5, .5]
    ft = world(*fx)
    centre = world(.5, .5)
    # Close enough that the focus region fills about half the frame height, never past the requested push share.
    if q.focus:
        fh = max((q.focus[3] - q.focus[1]) * h, (q.focus[2] - q.focus[0]) * w / aspect)
        D_focus = max(.9, fh / .5 / 2 / tan)
    else:
        D_focus = D0
    D1 = D0 + (min(D0, D_focus) - D0) * q.push / .9
    tgt1 = [centre[i] + (ft[i] - centre[i]) * min(1, q.push / .6) for i in range(3)]
    eye0 = [0, centre[1] + .35, centre[2] + D0]
    eye1 = [tgt1[0] * .85, tgt1[1] + .25, tgt1[2] + D1]
    arrive = max(30, round(d * q.arrive))
    scene = {"objects": [{"id": "card", "geometry": "box", "size": [round(w, 4), h, .025], "texture": q.asset_id, "color": "#ffffff",
                          "roughness": .8, "metalness": 0, "position": {"x": 0, "y": round(cy, 4), "z": 0},
                          "rotation": {"x": round(-tilt, 4), "y": 0, "z": 0},
                          "keyframes": [{"frame": 0, "rotation": {"x": round(-tilt, 4), "y": -.035, "z": .01}},
                                        {"frame": d - 1, "rotation": {"x": round(-tilt, 4), "y": .02, "z": 0}}], "ease": "linear"}],
             "lights": [{"kind": "directional", "position": {"x": -2.5, "y": 5, "z": 3.5}, "intensity": 1.6},
                        {"kind": "ambient", "intensity": .55}],
             "background": q.background, "ground": True, "shadows": True, "environment": "none", "fov": fov,
             "camera_keyframes": [{"frame": 0, "position": dict(zip("xyz", map(lambda v: round(v, 4), eye0))), "target": dict(zip("xyz", map(lambda v: round(v, 4), centre)))},
                                  {"frame": arrive, "position": dict(zip("xyz", map(lambda v: round(v, 4), eye1))), "target": dict(zip("xyz", map(lambda v: round(v, 4), tgt1)))},
                                  {"frame": d - 1, "position": dict(zip("xyz", map(lambda v: round(v, 4), eye1))), "target": dict(zip("xyz", map(lambda v: round(v, 4), tgt1)))}],
             "camera_ease": "smooth"}
    from .scene3d import Scene3D
    scene = Scene3D.model_validate(scene).model_dump()
    leave = [{"name": "fade_out", "start_frame": d - 12, "end_frame": d - 1}] if d > 60 else []
    ops = [{"op": "upsert_layer", "layer": _layer(q, "scene", "scene3d", x=0, y=0, width=1, height=1, data=scene,
                                                  effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 12}, *leave])}]
    k = min(W, H) / 1080
    mark_box = None
    if q.focus and q.mark != "none":
        corners = [_project(world(u, v), eye1, tgt1, fov, aspect) for u, v in ((q.focus[0], q.focus[1]), (q.focus[2], q.focus[1]), (q.focus[2], q.focus[3]), (q.focus[0], q.focus[3]))]
        xs, ys = [c[0] for c in corners], [c[1] for c in corners]
        pad = .012
        mark_box = [max(0, min(xs) - pad), max(0, min(ys) - pad), min(1, max(xs) + pad), min(1, max(ys) + pad)]
        X0, Y0, X1, Y1 = (mark_box[0] * W, mark_box[1] * H, mark_box[2] * W, mark_box[3] * H)
        sw = round(4 * k, 2)
        el = ({"id": "m", "type": "rect", "x": round(X0, 1), "y": round(Y0, 1), "width": round(X1 - X0, 1), "height": round(Y1 - Y0, 1), "stroke": q.accent,
               "stroke_width": sw, "fill": "none", "draw": [arrive + 4, arrive + 22]} if q.mark == "box" else
              {"id": "m", "type": "line", "x1": round(X0, 1), "y1": round(Y1, 1), "x2": round(X1, 1), "y2": round(Y1, 1), "stroke": q.accent,
               "stroke_width": round(5 * k, 2), "draw": [arrive + 4, arrive + 18]})
        ops.append({"op": "upsert_layer", "layer": {**_layer(q, "mark", "svg", x=0, y=0, width=1, height=1, data={"view_box": [W, H], "elements": [el]},
                                                             effects=[*leave]), "z": q.z + 2}})
    cap_px, src_px = round(40 * k), round(26 * k)
    texts = []
    if q.caption:
        texts.append(("caption", q.caption, cap_px, .06, .8, q.color, 600))
    texts.append(("source", q.source, src_px, .06, .9, "#b9b9b2", 400))
    for name, txt, px, x, y, col, wt in texts:
        a = arrive + (10 if name == "caption" else 18)
        ops.append({"op": "upsert_layer", "layer": {**_layer(q, name, "text", text=txt, x=x, y=round(y - px * 1.3 / H / 2, 4), width=.7, height=round(px * 1.3 / H, 4),
                                                             font_id=q.font_id, font_size=px, font_weight=wt, line_height=1.3, color=col, data={"align": "left"},
                                                             typography_role=None,
                                                             effects=[{"name": "fade_in", "start_frame": a, "end_frame": a + 12, "easing": "ease_out"},
                                                                      {"name": "rise", "start_frame": a, "end_frame": a + 14, "params": {"amount": 10}, "bezier": [.22, 1, .36, 1]},
                                                                      {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 10}}, *leave]), "z": q.z + 3}})
    notes = ["The image is the evidence: keep its colours unaltered (no LUT on the card) and its source line on screen."]
    if not q.focus:
        notes.append("Without focus the push goes to the centre; give focus = the words or detail the narration points at.")
    return {"ops": ops, "notes": notes, "mark_box": [round(v, 4) for v in mark_box] if mark_box else None, "camera": {"arrive_frame": q.start_frame + arrive},
            "inspect_frames": [q.start_frame + 6, q.start_frame + arrive + 24]}


RECIPES = {"measure": (Measure, measure), "diagram": (Diagram, diagram), "unit_grid": (UnitGrid, unit_grid), "plot": (Plot, plot),
           "annotate": (Annotate, annotate), "chips": (Chips, chips), "number_wall": (NumberWall, number_wall), "hud_card": (HudCard, hud_card),
           "stat_line": (StatLine, stat_line), "particles": (ParticleFx, particles), "camera_stage": (CameraStage, camera_stage),
           "pie": (Pie, pie), "columns": (Columns, columns), "text_window_zoom": (TextWindowZoom, text_window_zoom),
           "doc_timecard": (DocTimecard, doc_timecard), "motif_progress": (MotifProgress, motif_progress), "evidence_3d": (Evidence3D, evidence_3d)}


def catalog():
    """Compact recipe list: purpose and fields (defaults omitted) so the caller can author requests without a schema dump."""
    out = []
    for name, (model, fn) in RECIPES.items():
        fields = [k for k in model.model_fields if k not in ("recipe", "z", "attach_shot")]
        doc = next((ln.split(":", 1)[1].strip() for ln in __doc__.splitlines() if ln.strip().startswith(f"- {name}:")), "")
        out.append({"recipe": name, "purpose": doc, "fields": fields})
    return {"recipes": out, "guide": "docs/EXPLAINER_KIT.md", "markup": "text layers accept **strong** and ==accent== inline emphasis",
            "runtime": {"counter": "group separator, style count|roll|scramble, align", "particles": "mode burst|bunch|stream|drift|tracks",
                        "svg": "arrow element (heads, grow center), circle ripple", "film": "speed_lines, flare (center)"}}


def compose(pid, base_revision, request, dry_run=False):
    name = (request or {}).get("recipe")
    if name not in RECIPES:
        raise ValueError(f"recipe must be one of {sorted(RECIPES)}")
    model, fn = RECIPES[name]
    q = model.model_validate(request)
    if name == "evidence_3d":
        a = store.find_asset(pid, q.asset_id)
        if not a or a.get("kind") != "image":
            raise ValueError("evidence_3d asset_id must be an imported image")
        if q.aspect is None and a.get("width") and a.get("height"):
            q = q.model_copy(update={"aspect": a["width"] / a["height"]})
    t = _timeline(pid, base_revision)
    r = fn(t, q)
    if name == "doc_timecard":
        # A time card asserts when/where the footage under it was shot. Evidence whose date is not recorded on the
        # asset (tags such as "recorded 2022-11-16") gets a note: record it, or describe the event, not the footage.
        import re
        under = [s for s in t["shots"] if s.get("asset_id") and s["start_frame"] < q.end_frame and s["end_frame"] > q.start_frame]
        undated = sorted({(store.find_asset(pid, s["asset_id"]) or {}).get("name", s["asset_id"]) for s in under
                          if not re.search(r"(19|20)\d\d-\d\d-\d\d", (store.find_asset(pid, s["asset_id"]) or {}).get("tags") or "")})
        if undated:
            r.setdefault("notes", []).append(f"Time card over footage without a recorded date ({', '.join(undated)[:120]}): confirm the date at the source and "
                                             "put it in the asset tags ('recorded YYYY-MM-DD'), or word the card as the event, not the footage.")
    r["revision"] = _apply(pid, base_revision, r["ops"], dry_run)
    r["recipe"] = name
    r["dry_run"] = dry_run
    if dry_run:
        from .review import audit_timeline
        future = preview_ops(t, r["ops"])
        touched = {op["layer"]["id"] for op in r["ops"] if op["op"] == "upsert_layer"}
        r["audit"] = [f for f in audit_timeline(pid, future)["findings"] if touched & set(_ids(f["where"]))]
    else:
        r["layers"] = [op["layer"]["id"] for op in r.pop("ops")]
    return r
