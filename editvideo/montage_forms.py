"""Two more archive montage forms beside the flood (montage.archive_montage), from the research
(docs/research/Montage tư liệu kiểu bom tấn.md, archetypes; docs/research/Nâng cấp thẩm mỹ toàn diện.md, design rules):

- map_matte (Dawn of the Planet of the Apes' opening; Capra's Why We Fight maps; Elastic's The Man in the High Castle
  titles): no cut at all, one continuous camera move over a map; archive plays INSIDE the land it was shot in, each
  side's colour declared before any footage, sourced events lighting up as a date clock walks forward, cold to red,
  then the map drains to dark with a few points left.
- dossier (Godzilla 2014's titles; Kyle Cooper's Se7en; the Narcos titles): the story's own documents and photographs,
  each 2-2.5 s through a dissolve and a push, shot like objects on a desk (raking light, a focal plane travelling over
  the page, a drop shadow, each sheet's own grain) rather than flat cards; the rhythm comes from the pencil marks and
  the withheld passages, not from cuts; a crescendo, a white-out, near silence, a small title.

Honesty is in the schema: footage inside a country's shape claims it was shot there, then, so each clip names a place
the region accepts and a date inside the clock; an event carries its source; a dossier item carries its own date and
archive reference, and only a document the release itself withholds gets its gaps marked (at most two: a redaction
device used more often reads as a gimmick).

`sound_plan` times everything; score_map_matte / score_dossier turn it into clips, form_arc measures the render.
"""
import math
import random
import numpy as np
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .montage import _when, _hold

FPS = 30
HEX = r"^#[0-9a-fA-F]{6}$"


def _rgb(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def _mix(a, b, u):
    return "#" + "".join(f"{round(x + (y - x) * u):02x}" for x, y in zip(_rgb(a), _rgb(b)))


def _year_frac(ymd):
    y, m, d = ymd
    return y + (m - 1) / 12 + (min(d, 31) - 1) / 365


def _ease(u):  # cubic in-out: the camera's one move
    u = min(1.0, max(0.0, u))
    return 4 * u ** 3 if u < .5 else 1 - (-2 * u + 2) ** 3 / 2


def _clip(ring, axis, value, above):
    """Sutherland-Hodgman: the part of a [lon, lat] ring on one side of a meridian (axis 0) or a parallel (axis 1)."""
    inside = (lambda p: p[axis] >= value) if above else (lambda p: p[axis] <= value)
    out = []
    for i in range(len(ring)):
        s, e = ring[i - 1], ring[i]
        if inside(e):
            if not inside(s):
                u = (value - s[axis]) / (e[axis] - s[axis])
                out.append([s[0] + u * (e[0] - s[0]), s[1] + u * (e[1] - s[1])])
            out.append(e)
        elif inside(s):
            u = (value - s[axis]) / (e[axis] - s[axis])
            out.append([s[0] + u * (e[0] - s[0]), s[1] + u * (e[1] - s[1])])
    return out


# ---------------------------------------------------------------- map_matte
class MatteFootage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str = Field(min_length=1, max_length=100)
    source_start: float = Field(default=0.0, ge=0)
    duration: float = Field(gt=1.0, le=600)             # usable seconds from source_start (no cut inside: review.clean_runs)
    date: str = Field(min_length=4, max_length=24)      # when it was SHOT ("3.1965"): it comes up as the clock reaches it
    place: str = Field(min_length=2, max_length=40)     # where it was shot: one of its region's places
    at: list[float] | None = Field(default=None, min_length=2, max_length=2)  # [lat, lon] of that place: checked inside the region
    focus: list[float] = Field(default_factory=lambda: [.5, .5], min_length=2, max_length=2)  # the part of the picture the region shows
    fps: float | None = Field(default=None, gt=0, le=120)
    sound: bool = False                                  # its own sound is usable: heard low, through a radio filter


class MatteRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=40)      # its label on the map ("Miền Nam")
    country: str = Field(min_length=2, max_length=60)   # Natural Earth outline the shape is cut from
    lat_range: list[float] | None = Field(default=None, min_length=2, max_length=2)  # keep these latitudes (south of the 17th parallel: [-90, 17.0])
    lon_range: list[float] | None = Field(default=None, min_length=2, max_length=2)
    side: str = Field(min_length=1, max_length=30)      # a key of `sides`: its colour
    places: list[str] = Field(default_factory=list, max_length=40)  # places footage may claim inside it (its name always counts)
    footage: list[MatteFootage] = Field(default_factory=list, max_length=24)
    label_at: list[float] | None = Field(default=None, min_length=2, max_length=2)  # [lat, lon]; default a clear spot near its centroid


class MapEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    date: str = Field(min_length=4, max_length=24)
    source: str = Field(min_length=3, max_length=120)   # who recorded it: an event without a source is not drawn
    label: str = Field(default="", max_length=32)       # a few events are named; the rest are points
    weight: float = Field(default=1.0, ge=.5, le=3)
    keep: bool = False                                   # stays lit when the map drains


class MapMatte(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["map_matte"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    start_frame: int = Field(ge=0)
    end_frame: int
    country: str = Field(min_length=2, max_length=60)   # the map's main country (its islands drawn; Vietnam's archipelagos too)
    neighbors: list[str] = Field(default_factory=list, max_length=8)
    view: list[float] | None = Field(default=None, min_length=4, max_length=4)  # [lon0, lat0, lon1, lat1]
    start: list[float] | None = Field(default=None, min_length=3, max_length=3)  # [lat, lon, zoom] the one move starts from; None: the whole view
    focus: list[float] | None = Field(default=None, min_length=3, max_length=3)  # [lat, lon, zoom] it ends on; None: a slow push in
    dates: list[str] = Field(min_length=2, max_length=2)  # the clock: first and last date
    clock: Literal["year", "month"] = "year"
    # 0: the clock walks the dates evenly; 1: by the moments (each clip and event an equal share of time); between, a
    # blend: empty years pass quickly instead of leaving the map with nothing to show (14 s of three dots in the first cut)
    clock_warp: float = Field(default=.5, ge=0, le=1)
    sides: dict[str, str] = Field(min_length=1, max_length=4)  # side -> colour, declared before any footage appears
    regions: list[MatteRegion] = Field(min_length=1, max_length=6)
    events: list[MapEvent] = Field(default_factory=list, max_length=240)
    drain_share: float = Field(default=.11, ge=.06, le=.25)  # the last share of the piece: the map darkens to a few points
    cold: str = Field(default="#8ea4bd", pattern=HEX)   # the first events' colour
    heat: str = Field(default="#d8442f", pattern=HEX)   # the last events' colour
    land: str = Field(default="#1d2127", pattern=HEX)
    border: str = Field(default="#b9a57a", pattern=HEX)
    accent: str = Field(default="#e8c46a", pattern=HEX)
    background: str = Field(default="#0a0b0d", pattern=HEX)
    title: str = Field(default="", max_length=60)
    grain: float = Field(default=.12, ge=0, le=1)
    seed: int = Field(default=7, ge=0, le=2 ** 31 - 1)
    z: int = Field(default=880, ge=0, le=960)

    @model_validator(mode="after")
    def check(self):
        N = self.end_frame - self.start_frame
        if N < 15 * FPS:
            raise ValueError("map_matte needs >= 15 s: a clock walking through the dates and the drain")
        for k in ("start", "focus"):
            v = getattr(self, k)
            if v and not (-90 <= v[0] <= 90 and -180 <= v[1] <= 180 and 1 <= v[2] <= 8):
                raise ValueError(f"{k} is [lat, lon, zoom] with zoom 1-8")
        w0, w1 = _when(self.dates[0]), _when(self.dates[1])
        if not w0 or not w1 or _year_frac(w1[1]) <= _year_frac(w0[0]):
            raise ValueError("dates: [first, last], each with a year, the last after the first (\"1.1965\", \"12.1968\")")
        lo, hi = _year_frac(w0[0]), _year_frac(w1[1])
        for c in self.sides.values():
            if not (isinstance(c, str) and len(c) == 7 and c.startswith("#")):
                raise ValueError("sides map a side to a #rrggbb colour")
        for r in self.regions:
            if r.side not in self.sides:
                raise ValueError(f"region {r.name}: side {r.side!r} is not among sides {sorted(self.sides)}")
            ok = {p.casefold() for p in [r.name, *r.places]}
            for f in r.footage:
                # footage inside a country's shape is a claim it was shot there, then (research: only matte footage
                # whose place and date match); `at` is checked against the shape itself when the map is drawn
                if f.place.casefold() not in ok:
                    raise ValueError(f"footage {f.asset_id} shot in {f.place!r} cannot play inside {r.name!r} (its places: {sorted(ok)})")
                w = _when(f.date)
                if not w or not lo <= _year_frac(w[0]) <= hi:
                    raise ValueError(f"footage {f.asset_id} dated {f.date!r} is outside the clock {self.dates[0]}-{self.dates[1]}")
                if not all(0 <= v <= 1 for v in f.focus):
                    raise ValueError(f"footage {f.asset_id}: focus is [x, y] in the picture (fractions)")
        for e in self.events:
            w = _when(e.date)
            if not w or not lo <= _year_frac(w[0]) <= hi:
                raise ValueError(f"event {e.label or (e.lat, e.lon)} dated {e.date!r} is outside the clock")
        if not any(r.footage for r in self.regions) and not self.events:
            raise ValueError("give footage inside a region or sourced events: an empty map is a slide")
        return self


def _frame_box(t, view):
    """The map's full-frame box: the view widened to the frame's aspect, its projection, the box in the frame."""
    from .cinematic import map_view
    from .resources import MapProjection
    W, H = t.get("width", 1920), t.get("height", 1080)
    q = SimpleNamespace(view=view[0], country=view[1], archipelagos="auto", fill_aspect=W / H)
    v = map_view(q)
    proj = MapProjection(v, 1000, pad=.04)
    VW, VH = proj.width, round(proj.height, 1)
    inner_w = min(1.0, VW / VH * H / W)
    inner_h = inner_w * W / H / (VW / VH)
    return proj, v, VW, VH, (1 - inner_w) / 2, (1 - inner_h) / 2, inner_w, inner_h


def _inside(rings, lat, lon):
    """Point in polygon (even-odd over all rings, [lon, lat])."""
    hit = False
    for g in rings:
        for (x0, y0), (x1, y1) in zip(g, g[1:] + g[:1]):
            if (y0 > lat) != (y1 > lat) and lon < x0 + (lat - y0) * (x1 - x0) / (y1 - y0):
                hit = not hit
    return hit


def map_matte(t, q: MapMatte, pid=None):
    from .cinematic import _archipelagos
    from .resources import geo_outline
    W, H = t.get("width", 1920), t.get("height", 1080)
    N = q.end_frame - q.start_frame
    A = lambda f: q.start_frame + f
    proj, view, VW, VH, ix, iy, iw, ih = _frame_box(t, (q.view, q.country))
    D = N - round(N * q.drain_share)                      # the drain starts
    lead = 30                                             # the map is up before the clock moves
    w0, w1 = _when(q.dates[0]), _when(q.dates[1])
    d0, d1 = _year_frac(w0[0]), _year_frac(w1[1])
    notes = []
    # the clock: dates to frames, blended between even time and an equal share for each moment (clip or event)
    moments = sorted({_year_frac(_when(f.date)[0]) for r in q.regions for f in r.footage} | {_year_frac(_when(e.date)[0]) for e in q.events})
    kx = [d0, *[m for m in moments if d0 < m < d1], d1]
    ky = [i / (len(kx) - 1) for i in range(len(kx))]
    warp = lambda d: (1 - q.clock_warp) * (d - d0) / (d1 - d0) + q.clock_warp * float(np.interp(d, kx, ky))
    at = lambda ymd: lead + round(warp(_year_frac(ymd)) * (D - lead - 20))

    # the one camera move: a null carries it, every map layer, matte and label rides it (one set of keys, not one a layer)
    def framing(la, lo, zoom):
        """(scale, tx, ty) putting (la, lo) mid-frame at this zoom, the map still covering its box."""
        x, y = proj(la, lo)
        tx, ty = .5 * W - ix * W - zoom * x / VW * iw * W, .5 * H - iy * H - zoom * y / VH * ih * H
        return (zoom, min(0.0, max(iw * W * (1 - zoom), tx)), min(0.0, max(ih * H * (1 - zoom), ty)))
    begin = framing(*q.start) if q.start else (1.0, 0.0, 0.0)
    if q.focus:
        end = framing(*q.focus)
    else:
        zoom = begin[0] * (1 + .05 * N / 300)            # a slow push about the frame's centre
        k_ = zoom / begin[0]
        cx, cy = W / 2 - ix * W, H / 2 - iy * H
        end = (zoom, min(0.0, max(iw * W * (1 - zoom), cx - k_ * (cx - begin[1]))), min(0.0, max(ih * H * (1 - zoom), cy - k_ * (cy - begin[2]))))

    def cam(f):
        u = _ease(f / max(1, N - 1))
        return tuple(a_ + (b_ - a_) * u for a_, b_ in zip(begin, end))
    upx = lambda f: iw * W / VW * cam(f)[0]               # screen pixels per map unit at frame f
    scr = lambda x, y, f: ((ix * W + cam(f)[1] + cam(f)[0] * x / VW * iw * W) / W, (iy * H + cam(f)[2] + cam(f)[0] * y / VH * ih * H) / H)

    def L(lid, kind, a, b, z, x=0.0, y=0.0, w=1.0, h=1.0, **kw):
        return {"op": "upsert_layer", "layer": {"id": f"{q.id}-{lid}", "kind": kind, "start_frame": A(a), "end_frame": A(b), "x": round(x, 4), "y": round(y, 4),
                                                "width": round(w, 4), "height": round(h, 4), "z": q.z + z, **kw}}
    camera = f"{q.id}-cam"
    fs = sorted({0, N - 1, *range(0, N, 30)})

    def maplayer(lid, a, b, z, els, **kw):
        return L(lid, "svg", a, b, z, ix, iy, iw, ih, parent=camera, data={"view_box": [VW, VH], "elements": els}, **kw)
    fade = lambda n, fi=10, fo=10: [{"name": "fade_in", "start_frame": 0, "end_frame": min(fi, n // 3)},
                                    {"name": "fade_out", "start_frame": max(0, n - fo), "end_frame": n - 1}]

    # shapes: the main country, its islands, each region cut from its country by latitude/longitude
    main = geo_outline(q.country, islands=True)
    shapes = []
    for r in q.regions:
        rings = geo_outline(r.country, islands=True)["rings"]
        for axis, rr in ((1, r.lat_range), (0, r.lon_range)):
            if rr:
                rings = [_clip(_clip(g, axis, min(rr), True), axis, max(rr), False) for g in rings]
                rings = [g for g in rings if len(g) >= 3]
        if not rings:
            raise ValueError(f"region {r.name}: nothing of {r.country} lies inside its ranges")
        for f in r.footage:  # a place given as a point must lie in the shape the footage is shown in
            if f.at and not _inside(rings, *f.at):
                raise ValueError(f"footage {f.asset_id} at {f.at} ({f.place}) lies outside {r.name}: it cannot play inside that shape")
            if not f.at:
                notes.append(f"footage {f.asset_id}: '{f.place}' is the caller's word; give `at` [lat, lon] to have it checked inside {r.name}")
        big = max(rings, key=len)
        cla, clo = sum(p[1] for p in big) / len(big), sum(p[0] for p in big) / len(big)
        shapes.append({"r": r, "rings": rings, "d": proj.path(rings), "pts": [proj(la, lo) for g in rings for lo, la in g], "centre": (cla, clo)})
    mid = N // 2
    px = lambda screen_px: round(screen_px / upx(mid), 2)  # a stroke that stays about this wide on screen through the move
    px0 = lambda screen_px: round(screen_px / upx(0), 2)   # type on from the start: this size at the first frame, larger as the camera closes in
    under = [{"id": f"n{i}", "type": "path", "d": proj.path(geo_outline(o, max_points=400)["rings"]), "stroke": "#3b4048", "stroke_width": px(1.0),
              "fill": "#121418", "appear": [0, 12]} for i, o in enumerate(q.neighbors)]
    under.append({"id": "land", "type": "path", "d": proj.path(main["rings"]), "stroke": "none", "stroke_width": 0, "fill": q.land, "appear": [0, 12]})
    # each side's colour is on the map from the first frame, before any footage (research: code the sides first)
    under += [{"id": f"tint{k}", "type": "path", "d": s["d"], "stroke": "none", "stroke_width": 0, "fill": q.sides[s["r"].side], "fill_opacity": .14,
               "appear": [0, 14]} for k, s in enumerate(shapes)]
    over = [{"id": "coast", "type": "path", "d": proj.path(main["rings"]), "stroke": q.border, "stroke_width": px(1.4), "fill": "none", "appear": [0, 12]}]
    over += [{"id": f"edge{k}", "type": "path", "d": s["d"], "stroke": q.sides[s["r"].side], "stroke_width": px(2.2), "fill": "none", "appear": [0, 14]}
             for k, s in enumerate(shapes)]
    ev = sorted(q.events, key=lambda e: _year_frac(_when(e.date)[0]))
    taken = []                                            # (screen box, first frame, last frame) of every word placed

    def tbox(x, y, f, size_px, text, anchor="middle"):
        sx, sy = scr(x, y, f)
        tw = .56 * size_px * len(text) / W
        x0 = sx - {"start": 0, "middle": tw / 2, "end": tw}[anchor]
        return (x0, sy - .8 * size_px / H, x0 + tw, sy + .25 * size_px / H)
    ovl = lambda b, c: max(0, min(b[2], c[2]) - max(b[0], c[0])) * max(0, min(b[3], c[3]) - max(b[1], c[1]))
    safe, clock_box = (.03, .05, .97, .95), (0.0, .8, .34, 1.0)  # inside the frame, clear of the clock low left
    out_of = lambda b: max(0, safe[0] - b[0]) + max(0, b[2] - safe[2]) + max(0, safe[1] - b[1]) + max(0, b[3] - safe[3]) + 10 * ovl(b, clock_box)
    for k, a in enumerate(_archipelagos(SimpleNamespace(country=q.country, archipelagos="auto"))):
        for j, (la, lo) in enumerate(a.points):
            x, y = proj(la, lo)
            over.append({"id": f"isl{k}_{j}", "type": "circle", "cx": x, "cy": y, "r": px(2.4), "fill": q.land, "stroke": q.border, "stroke_width": px(1.0), "appear": [0, 14]})
        lats, lons = [pt[0] for pt in a.points], [pt[1] for pt in a.points]
        # below the group, else above it, else beside it: whichever stays inside the frame at the first frame
        cands = [a.label_at] if a.label_at else []
        cands += [[min(lats) - .5, sum(lons) / len(lons)], [max(lats) + .7, sum(lons) / len(lons)], [sum(lats) / len(lats), max(lons) + 1.2]]
        best = min(cands, key=lambda c: out_of(tbox(*proj(*c), 0, 24, a.name)))
        x, y = proj(*best)
        over.append({"id": f"isl{k}_t", "type": "text", "x": x, "y": y, "text": a.name, "font_size": px0(24), "font_weight": 500, "anchor": "middle",
                     "fill": "#cfc6b4", "stroke": "none", "opacity": .85, "appear": [0, 14]})
        taken.append((tbox(x, y, 0, 24, a.name), 0, N))
    for k, s in enumerate(shapes):
        r = s["r"]
        first = min([at(_when(f.date)[0]) for f in r.footage] or [lead])
        # a clear spot near the centroid, inside the shape, away from the events (MIỀN BẮC had covered Hà Nội's dot)
        cla, clo = r.label_at or s["centre"]
        cands = [(cla + dy, clo + dx) for d in (0, .8, 1.6, 2.4) for dy, dx in ((0, 0), (d, 0), (-d, 0), (0, d), (0, -d)) if d or (dy, dx) == (0, 0)]
        cands = [c for c in cands if _inside(s["rings"], *c)] or [(cla, clo)]
        far = lambda c: min([math.hypot(c[0] - e.lat, (c[1] - e.lon) * math.cos(math.radians(c[0]))) for e in ev] or [9])
        spot = r.label_at or next((c for c in cands if far(c) >= .9), max(cands, key=far))
        x, y = proj(*spot)
        over.append({"id": f"rl{k}", "type": "text", "x": x, "y": y, "text": r.name.upper(), "font_size": px0(28), "font_weight": 600,
                     "anchor": "middle", "fill": _mix(q.sides[r.side], "#ffffff", .55), "stroke": "none", "opacity": .9, "glow": px(3),
                     "appear": [max(0, first - 20), max(1, first - 6)]})
        taken.append((tbox(x, y, mid, 28 * upx(mid) / upx(0), r.name.upper()), 0, N))
    ops = [L("cam", "null", 0, N, 0, ix, iy, iw, ih, anchor=[0, 0],
             keyframes={name: [{"frame": f, "value": round(cam(f)[j], 4 if j == 0 else 1), "easing": "linear"} for f in fs]
                        for name, j in (("scale", 0), ("x", 1), ("y", 2))}),
           L("bg", "shape", 0, N, 0, color=q.background, data={"shape": "rectangle", "corner_radius": 0}),
           maplayer("under", 0, N, 1, under, effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 12}]),
           maplayer("over", 0, N, 10, over, effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 12}])]
    sound = {"events": [], "footage": [], "reveals": [], "checks": []}

    # footage inside its region: it comes up when the clock reaches its date and dissolves into the next; one reveal
    # at a time (only one thing moves besides the camera's slow move)
    plays = []
    for k, s in enumerate(shapes):
        for f in sorted(s["r"].footage, key=lambda f: _year_frac(_when(f.date)[0])):
            plays.append({"k": k, "f": f, "a": at(_when(f.date)[0])})
    plays.sort(key=lambda p: p["a"])
    last_reveal = -10 ** 6
    for p in plays:
        if p["a"] < last_reveal + 24:
            moved = last_reveal + 24 - p["a"]
            p["a"] += moved
            if moved > 45:
                notes.append(f"footage {p['f'].asset_id} comes up {moved / FPS:.1f} s after its date: another reveal held the screen")
        last_reveal = p["a"]
    by_region = {}
    for p in plays:
        by_region.setdefault(p["k"], []).append(p)
    shown, small = [], []  # small: footage shown in a region too narrow to read it
    for k, ps in by_region.items():
        s, r = shapes[k], shapes[k]["r"]
        col = q.sides[r.side]
        spans = []
        for i, p in enumerate(ps):
            a = p["a"]
            nxt = ps[i + 1]["a"] + 15 if i + 1 < len(ps) else D
            b = min(D, nxt, a + int((p["f"].duration - .05) * FPS))
            if b - a < 2 * FPS:
                notes.append(f"footage {p['f'].asset_id} dropped: {max(0, b - a) / FPS:.1f} s before the next clip or the drain")
                continue
            spans.append((a, b, p["f"]))
        videos = []
        for i, (a, b, f) in enumerate(spans):
            # the region's screen extent over the clip's whole time (the camera moves under it)
            xs, ys = [], []
            for fr in (a, (a + b) // 2, b - 1):
                for x_, y_ in s["pts"][::max(1, len(s["pts"]) // 200)]:
                    sx, sy = scr(x_, y_, fr)
                    xs.append(sx)
                    ys.append(sy)
            rx0, ry0, rx1, ry1 = max(0.0, min(xs)), max(0.0, min(ys)), min(1.0, max(xs)), min(1.0, max(ys))
            if rx1 - rx0 < .06 or ry1 - ry0 < .06:
                notes.append(f"region {r.name} is {rx1 - rx0:.2f} x {ry1 - ry0:.2f} of the frame at {a / FPS:.1f} s: too small to hold footage; zoom in (focus)")
                continue
            if rx1 - rx0 < .2:
                notes.append(f"region {r.name} is {rx1 - rx0:.2f} of the frame wide: its footage reads as texture; frame it closer or pick the part to show (focus)")
                small.append({"region": r.name, "asset_id": f.asset_id, "width": round(rx1 - rx0, 3), "seconds": [round(a / FPS, 2), round(b / FPS, 2)]})
            # the clip at its own proportions, covering the region, its `focus` placed on the region's middle: the region
            # shows the part of the picture the caller chose, not whatever a centred crop leaves
            asset = None
            if pid:
                from . import store
                try:
                    asset = store.find_asset(pid, f.asset_id)
                except ValueError:
                    asset = None
            ar = (asset.get("width") or 16) / (asset.get("height") or 9) if asset else 16 / 9
            bh = max(ry1 - ry0, (rx1 - rx0) * W / H / ar) * 1.04
            bw = bh * H / W * ar
            if bw > 2 or bh > 2:
                bw, bh = bw / max(bw, bh) * 2, bh / max(bw, bh) * 2
            fx, fy = f.focus
            x0 = min(rx0, max(rx1 - bw, (rx0 + rx1) / 2 - fx * bw))
            y0 = min(ry0, max(ry1 - bh, (ry0 + ry1) / 2 - fy * bh))
            # toward the side's colour with the highlights held down: a bright sky inside the land read as a white blob,
            # and a lifted grade as fog; detail lives in the mids
            grade = [{"name": "tritone", "start_frame": 0, "end_frame": 1, "params": {"amount": .6, "shadow_color": "#050608",
                                                                                     "color": _mix(col, "#3c3c3c", .5), "highlight_color": "#a39d90"}},
                     {"name": "contrast", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.22}}]
            flow = {"frame_sampling": "flow"} if f.fps and abs(f.fps - FPS) > .5 else {}
            videos.append(L(f"v{k}-{i}", "video", a, b, 5 + i % 2, x0, y0, bw, bh, asset_id=f.asset_id, source_start=round(f.source_start, 3),
                            fit="cover", opacity=.96, matte={"source": f"{q.id}-m{k}", "mode": "alpha"}, **flow,
                            effects=[*grade, *fade(b - a, 18, 15)]))
            m_ = (a + b) // 2  # where form_arc reads the footage's contrast inside the shape
            ring = max(s["rings"], key=len)
            sound["checks"].append({"frame": A(m_), "asset_id": f.asset_id, "polygon": [[round(v, 4) for v in scr(*proj(la, lo), m_)] for lo, la in ring[::max(1, len(ring) // 80)]]})
            sound["footage"].append({"asset_id": f.asset_id, "source_start": f.source_start, "start": A(a), "end": A(b), "sound": f.sound})
            sound["reveals"].append(A(a))
            shown.append((a, b))
        if videos:  # a matte shape no clip uses would be drawn on screen: only emitted with its clips
            ma, mb = min(v["layer"]["start_frame"] for v in videos) - q.start_frame, max(v["layer"]["end_frame"] for v in videos) - q.start_frame
            ops.append(maplayer(f"m{k}", ma, mb, 4, [{"id": "shape", "type": "path", "d": s["d"], "stroke": "none", "stroke_width": 0, "fill": "#ffffff"}]))
            ops += videos

    # events: points lighting up as the clock passes their date, cold to red; the named ones say their name a while,
    # each on the side that covers no other word or point, inside the frame
    pts, kept, kept_n, labels = [], [], 0, 0
    dots = []
    for j, e in enumerate(ev):
        a = at(_when(e.date)[0])
        x, y = proj(e.lat, e.lon)
        col = _mix(q.cold, q.heat, min(1.0, a / max(1, D - 20)) ** 1.4)
        el = {"id": f"e{j}", "type": "circle", "cx": x, "cy": y, "r": round(4.5 * e.weight / upx(a), 2), "fill": col, "stroke": "#0b0d12",
              "stroke_width": round(1.2 / upx(a), 2), "glow": round(2.5 / upx(a), 2), "appear": [a, a + 6], "ripple": [a, a + 30], "ripple_scale": 3.0}
        (kept if e.keep else pts).append(el)
        dots.append((x, y, a))
        if e.keep:  # as the map drains, the kept points light again, larger: what is left when everything else goes dark
            kept_n += 1
            kept.append({**el, "id": f"k{j}", "r": round(7 * e.weight / upx(D), 2), "fill": q.heat, "glow": round(6 / upx(D), 2),
                         "stroke_width": round(1.5 / upx(D), 2), "appear": [D, D + 14], "ripple": [D, min(N - 1, D + 45)]})
        sound["events"].append(A(a))
    for j, e in enumerate(ev):
        if not e.label:
            continue
        labels += 1
        if labels > 12:
            notes.append(f"event label '{e.label}' not shown: twelve names are the most a moving map can carry")
            continue
        a = at(_when(e.date)[0])
        n = _hold(e.label) + 24
        b = min(D, a + 6 + n)
        if b - a < 30:
            continue
        x, y = proj(e.lat, e.lon)
        u = 1 / upx(a)
        best = None
        for side, (dx, dy, anc) in {"right": (10, 6, "start"), "left": (-10, 6, "end"), "above": (0, -12, "middle"), "below": (0, 26, "middle")}.items():
            tx_, ty_ = x + dx * u, y + dy * u
            bx = [tbox(tx_, ty_, f_, 27 * upx(f_) / upx(a), e.label, anc) for f_ in (a + 6, b - 1)]
            hit = sum(ovl(b_, tb) for tb, f0, f1 in taken if f0 < b and f1 > a for b_ in bx)
            hit += sum(ovl(b_, (sx - .006, sy - .006, sx + .006, sy + .006)) for b_ in bx for (dx_, dy_, fa) in dots if fa <= b
                       for sx, sy in [scr(dx_, dy_, max(fa, a))] if (dx_, dy_) != (x, y))
            score = (round(sum(out_of(b_) for b_ in bx), 3), hit)
            if best is None or score < best[0]:
                best = (score, tx_, ty_, anc, bx)
        _, tx_, ty_, anc, bx = best
        if best[0][0] > 0:
            notes.append(f"event label '{e.label}' leaves the frame's safe area at every side: frame the map closer to it")
        taken += [(b_, a, b) for b_ in bx]
        ops.append(maplayer(f"el{j}", a + 6, b, 12, [{"id": "t", "type": "text", "x": round(tx_, 1), "y": round(ty_, 1), "text": e.label, "anchor": anc,
                                                      "font_size": round(27 * u, 1), "font_weight": 600, "fill": "#efe6d6", "stroke": "none", "glow": round(3 * u, 2)}],
                            effects=fade(b - a - 6, 6, 10)))
    if pts:
        ops.append(maplayer("events", 0, N, 11, pts, effects=[{"name": "fade_out", "start_frame": D, "end_frame": min(N - 1, D + round((N - D) * .7))}]))
    if kept:
        ops.append(maplayer("kept", 0, N, 16, kept))
    # the longest stretch with nothing new on the map and no footage playing: the clock's warp should leave none over 8 s
    beats_ = sorted({p["a"] for p in plays} | {at(_when(e.date)[0]) for e in ev} | {lead, D})
    gap = 0
    for a_, b_ in zip(beats_, beats_[1:]):
        free, cur = 0, a_
        for s0, s1 in sorted(shown):
            if s1 <= cur or s0 >= b_:
                continue
            free, cur = free + max(0, s0 - cur), max(cur, s1)
        gap = max(gap, free + max(0, b_ - cur))
    if gap > 8 * FPS:
        notes.append(f"{gap / FPS:.1f} s with nothing new on the map: raise clock_warp, add events, or shorten the piece")

    # the clock: one date on screen, walking forward; it stops on the last date through the drain
    marks = []
    if q.clock == "month":
        y, m = w0[0][0], w0[0][1]
        while (y, m) <= (w1[1][0], w1[1][1]):
            marks.append(((y, m, 1), f"{m}.{y}"))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        if marks and (D - lead) / len(marks) < 18:
            notes.append("the month clock would change faster than it reads: shown by year")
            marks = []
    if not marks:
        marks = [((y, 1, 1), str(y)) for y in range(w0[0][0], w1[1][0] + 1)]
    starts = [max(0, at(m[0])) if i else 0 for i, m in enumerate(marks)]
    for i, (m, txt) in enumerate(marks):
        a, b = starts[i], (starts[i + 1] if i + 1 < len(marks) else N)
        if b - a < 4:
            continue
        flip = [{"name": "fade_out", "start_frame": b - a - 5, "end_frame": b - a - 1}] if i + 1 < len(marks) else []
        ops.append(L(f"clk{i}", "text", a, b, 18, .055, .855, .3, .07, text=txt, font_id="oswald", font_size=46, font_weight=500, color=q.accent,
                     data={"align": "left"}, effects=[{"name": "fade_in", "start_frame": 0, "end_frame": min(6, (b - a) // 3)},
                                                      {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 18}}, *flip]))
    ops.append(L("clksc", "shape", 0, N, 17, -.04, .80, .34, .2, color="#000000", opacity=.5, data={"shape": "rectangle", "corner_radius": 0},
                 effects=[{"name": "edge_feather", "start_frame": 0, "end_frame": 1, "params": {"amount": .3, "shape": "rect"}}]))

    # the drain: the map darkens, the kept points stay; a small title at the end
    ops.append(L("drain", "shape", D, N, 14, color="#000000", opacity=.8, data={"shape": "rectangle", "corner_radius": 0},
                 effects=[{"name": "fade_in", "start_frame": 0, "end_frame": max(2, round((N - D) * .6))}]))
    tt = None
    if q.title:
        tt = max(D + 20, N - round(3.2 * FPS))
        ops.append(L("title", "text", tt, N, 20, .1, .47, .8, .07, text=q.title.upper(), font_id="bevietnampro", font_size=38, font_weight=500, color="#efe6d6",
                     data={"align": "center"}, effects=[*fade(N - tt, 10, 12),
                                                        {"name": "tracking", "start_frame": 0, "end_frame": N - tt - 1, "easing": "linear",
                                                         "params": {"amount": .4, "from_em": .3, "center": True}}]))
    if q.grain:
        ops.append(L("grain", "film", 0, N, 19, blend="overlay", data={"type": "grain", "intensity": q.grain, "seed": q.seed, "gauge": 16}))
    ops.append(L("end-intent", "null", D, N, 0, data={"intent": "deliberate_still"}))
    sound.update({"body": [A(0), A(D)], "drain": [A(D), A(N)], "title": A(tt) if tt is not None else None, "end": A(N)})
    return {"ops": ops, "notes": notes,
            "inspect_frames": [A(min(N - 1, p["a"] + 30)) for p in plays[:4]] + [A(D - 10), A(N - 20)],
            "sound_plan": sound,
            "measurements": {"cuts": 0, "regions": len(shapes), "footage": len(sound["footage"]), "events": len(ev), "kept": kept_n,
                             "drain_s": round((N - D) / FPS, 2), "end_zoom": round(end[0], 3), "clock": [marks[0][1], marks[-1][1]],
                             "longest_empty_s": round(gap / FPS, 1), "footage_as_texture": small},
            "verify": "snapshot each reveal (footage only inside its region, its colour coded), the clock, the drain with its kept points; "
                      "play it: one camera move, no cut; run form_arc(video, plan, 'map_matte') (its footage contrast too)."}


# ---------------------------------------------------------------- dossier
class DossierItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str = Field(min_length=1, max_length=100)  # a scan or print of the story's own document or photograph
    kind: Literal["document", "photo", "map"] = "document"
    date: str = Field(min_length=4, max_length=24)      # its own date ("4.8.1964")
    source: str = Field(min_length=3, max_length=90)    # archive and reference, shown small under the date
    caption: str = Field(default="", max_length=40)     # what it is ("Điện CINCPAC"), beside the date
    hold: float | None = Field(default=None, ge=1.5, le=8)
    focus: list[float] = Field(default_factory=lambda: [.5, .42], min_length=2, max_length=2)  # where the push and the focal plane end (page fractions)
    travel: Literal["down", "across", "in"] = "down"    # the focal plane's path over the page
    underline: list[list[float]] = Field(default_factory=list, max_length=6)  # [x, y, w] page fractions under the words that matter, in order
    withheld: list[list[float]] = Field(default_factory=list, max_length=8)   # [x, y, w, h]: the release's own black bars
    climax: bool = False

    @model_validator(mode="after")
    def check(self):
        if not all(0 <= v <= 1 for v in self.focus):
            raise ValueError("focus is [x, y] in page fractions")
        for u in self.underline:
            if len(u) != 3 or not all(0 <= v <= 1 for v in u) or u[0] + u[2] > 1.001:
                raise ValueError("an underline is [x, y, w] inside the page (fractions)")
        for w in self.withheld:
            if len(w) != 4 or not all(0 <= v <= 1 for v in w) or w[0] + w[2] > 1.001 or w[1] + w[3] > 1.001:
                raise ValueError("a withheld passage is [x, y, w, h] inside the page (fractions)")
        if not _when(self.date):
            raise ValueError(f"item {self.asset_id}: its date needs a year ({self.date!r})")
        return self


class Dossier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["dossier"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    start_frame: int = Field(ge=0)
    end_frame: int
    items: list[DossierItem] = Field(min_length=2, max_length=40)
    dissolve_s: float = Field(default=.5, ge=.2, le=1.2)
    ending: Literal["whiteout", "black"] = "whiteout"
    silence_s: float = Field(default=2.0, ge=0, le=6)
    title: str = Field(default="", max_length=60)
    title_s: float = Field(default=3.2, ge=1.5, le=8)
    breaths: int = Field(default=2, ge=0, le=4)          # near-silent holes on item boundaries before the climax
    desk: str = Field(default="#16130f", pattern=HEX)
    mark: str = Field(default="#b8402c", pattern=HEX)    # red pencil
    accent: str = Field(default="#e8c46a", pattern=HEX)
    grain: float = Field(default=.12, ge=0, le=1)
    seed: int = Field(default=7, ge=0, le=2 ** 31 - 1)
    z: int = Field(default=880, ge=0, le=938)             # its layers reach z + 62

    @model_validator(mode="after")
    def check(self):
        if sum(1 for it in self.items if it.climax) > 1:
            raise ValueError("mark at most one item climax (default: the last)")
        if sum(1 for it in self.items if it.withheld) > 2:
            raise ValueError("mark the withheld passages of at most two documents: a redaction device used more often reads as a gimmick")
        if any(it.withheld and it.kind != "document" for it in self.items):
            raise ValueError("withheld passages belong to a released document")
        return self


def dossier(t, pid, q: Dossier):
    from . import store
    W, H = t.get("width", 1920), t.get("height", 1080)
    N = q.end_frame - q.start_frame
    A = lambda f: q.start_frame + f
    d = round(q.dissolve_s * FPS)
    sil, title_n = round(q.silence_s * FPS), (round(q.title_s * FPS) if q.title else 0)
    E = (12 if q.ending == "whiteout" else 6) + sil + title_n
    B = N - E                                             # the items end, the white-out begins
    want = [round((it.hold or 2.3 + .45 * (len(it.underline) + len(it.withheld)) + (.4 if it.caption else 0)) * FPS) for it in q.items]
    k = (B + d * (len(q.items) - 1)) / sum(want)
    if k < .8:
        need = (sum(want) * .8 - d * (len(q.items) - 1) + E) / FPS
        raise ValueError(f"{len(q.items)} items need >= {need:.1f} s (each at least 80 % of its reading hold); drop items or lengthen")
    notes = []
    if k > 1.6:
        notes.append(f"each item holds {k:.1f}x its pace: a dossier moves at 2-2.5 s an item; add items or shorten the piece")
    # an item stays up at least as long as its caption takes to read between the dissolves
    line_of = lambda it: it.date + (f" · {it.caption.upper()}" if it.caption else "")
    least = [max(_hold(line_of(it)) + 6, (24 + 12 * (len(it.underline) + len(it.withheld) - 1) + 30) if it.underline or it.withheld else 0)
             + (10 if i == 0 else d) + (d if i < len(q.items) - 1 else 6) for i, it in enumerate(q.items)]
    holds = [max(m_, round(w * k)) for w, m_ in zip(want, least)]
    over = sum(holds) - (B + d * (len(holds) - 1))
    slack = [h - m_ for h, m_ in zip(holds, least)]
    if over > sum(slack):
        raise ValueError(f"{len(q.items)} items need {(sum(least) - d * (len(q.items) - 1) + E) / FPS:.1f} s for their captions to be read; drop items or lengthen")
    if over > 0:
        holds = [h - round(over * sl / max(1, sum(slack))) for h, sl in zip(holds, slack)]
    holds[-1] += B + d * (len(holds) - 1) - sum(holds)
    climax_i = next((i for i, it in enumerate(q.items) if it.climax), len(q.items) - 1)

    def L(lid, kind, a, b, z, x=0.0, y=0.0, w=1.0, h=1.0, **kw):
        return {"op": "upsert_layer", "layer": {"id": f"{q.id}-{lid}", "kind": kind, "start_frame": A(a), "end_frame": A(b), "x": round(x, 4), "y": round(y, 4),
                                                "width": round(w, 4), "height": round(h, 4), "z": q.z + z, **kw}}
    ops = [L("desk", "shape", 0, N, 0, color=q.desk, data={"shape": "rectangle", "corner_radius": 0},
             effects=[{"name": "paper_grain", "start_frame": 0, "end_frame": 1, "params": {"amount": .07, "seed": q.seed}},
                      {"name": "vignette", "start_frame": 0, "end_frame": 1, "params": {"amount": .75}}])]
    sound = {"items": [], "marks": [], "breaths": []}
    a = 0
    spans = []
    for i, (it, n) in enumerate(zip(q.items, holds)):
        b = a + n
        spans.append((a, b))
        a = b - d
    for i, (it, (a, b)) in enumerate(zip(q.items, spans)):
        n = b - a
        asset = store.find_asset(pid, it.asset_id)
        if asset.get("kind") != "image":
            raise ValueError(f"item {it.asset_id} must be an image (a scan or a print)")
        ar = (asset.get("width") or 1) / (asset.get("height") or 1)
        underline, withheld = [list(u) for u in it.underline], [list(w) for w in it.withheld]
        if (underline or withheld) and asset.get("path") and Path(asset["path"]).is_file():
            underline, withheld = _check_marks(asset["path"], underline, withheld, it.asset_id)
        r_ = random.Random(q.seed * 1000 + i)            # each sheet its own grain, angle and place
        fx, fy = it.focus
        fi = 10 if i == 0 else d
        fo = d if i < len(q.items) - 1 else 6
        fades = [{"name": "fade_in", "start_frame": 0, "end_frame": fi}, {"name": "fade_out", "start_frame": n - fo, "end_frame": n - 1}]
        lin = lambda v0_, v1_: [{"frame": 0, "value": v0_, "easing": "linear"}, {"frame": n - 1, "value": v1_, "easing": "linear"}]
        travel = it.travel
        if travel != "in":  # a page with no room to travel along that axis (a wide scan going down) is pushed into instead
            room = (min(.9 if ar < 1 else min(1.6, .9 * ar), 1.95 * H / W * ar) * W / H / ar) if travel == "down" else min(1.5, 1.95 * W / H / ar) * H / W * ar
            if room <= 1.05:
                notes.append(f"item {i}: the page has no room to travel {travel} ({room:.2f} of the frame): pushed into its focus instead")
                travel = "in"
        marks = [(u[1] if travel != "across" else u[0], "u", j) for j, u in enumerate(underline)] + \
                [((w[1] + w[3] / 2) if travel != "across" else w[0], "w", j) for j, w in enumerate(withheld)]
        when = {}
        if travel == "in":
            # the whole picture in frame, the camera pushing into the focus; the focal plane opens around it
            ph = .84
            pw = ph * H / W * ar
            if pw > .84:
                pw = .84
                ph = pw * W / H / ar
            x0, y0 = (1 - pw) / 2 + r_.uniform(-.015, .015), (1 - ph) / 2 + r_.uniform(-.01, .01)
            push = 1.22 if it.kind == "photo" else 1.3
            motion = {"anchor": [round(fx, 4), round(fy, 4)], "rotation": round(r_.uniform(-1.2, 1.2), 2),
                      "keyframes": {"scale": lin(1.0, push), "x": lin(0, round((.5 - (x0 + fx * pw)) * W * .35, 1)),
                                    "y": lin(0, round((.5 - (y0 + fy * ph)) * H * .35, 1))}}
            g0, g1 = [fx, fy, .1, .1 * ar], [fx, fy, .34, .34 * ar]
            band = {"shape": "ellipse", "geom": [round(v, 4) for v in g0], "mode": "subtract", "feather_px": round(min(300, .2 * H)),
                    "keyframes": [{"frame": 0, "geom": [round(v, 4) for v in g0]}, {"frame": n - 1, "geom": [round(v, 4) for v in g1]}]}
            t0 = 16
            for _, kind_, j in marks:
                when[(kind_, j)] = t0
                t0 += 12
            t0 -= 4
        else:
            # the camera close over the sheet (its type large enough to read), travelling along it from above the first
            # mark to past the last one, the focal plane fixed in the middle of the frame as the page slides under it
            down = travel == "down"
            if down:
                pw = min(.9 if ar < 1 else min(1.6, .9 * ar), 1.95 * H / W * ar)  # a layer is at most twice the frame
                ph = pw * W / H / ar
                span = ph                                 # the page's length along the travel, in frames
            else:
                ph = min(1.5, 1.95 * W / H / ar)
                pw = ph * H / W * ar
                span = pw
            half = .5 / span                              # half the frame, in page units
            ys = sorted(m_[0] for m_ in marks) or [fy if down else fx]
            v0, v1 = min(ys) - .06, max(ys) + .03
            least = .14 / span                            # it always travels a little: a still sheet reads as a slide
            if v1 - v0 < least:
                v0, v1 = (v0 + v1) / 2 - least / 2, (v0 + v1) / 2 + least / 2
            reach = .2 / span if span > 1 else 0          # a mark is in focus once within a fifth of the frame of its middle
            # with marks the camera arrives a second before the dissolve and rests there, the last mark drawn and read
            te = max((n - 1) // 2, n - fo - 40) if marks else n - 1
            if marks:
                v1 = max(v1, max(ys) - reach)
            v0, v1 = (min(max(v, half), 1 - half) if span > 1 else .5 for v in (v0, v1))
            if (v1 - v0) * span / (n / FPS) > .3:
                notes.append(f"item {i}: the camera travels {(v1 - v0) * span / (n / FPS):.2f} frames a second over the page; hold it longer or mark less of it")
            other = fx if down else fy                    # the cross axis: centred on the focus, the page's edge kept out of frame when it can be
            cross = pw if down else ph
            c0 = .5 - other * cross
            c0 = min(0.0, max(1 - cross, c0)) if cross > 1 else (1 - cross) / 2
            arrive = lambda v_: [{"frame": 0, "value": 0, "easing": "linear"}, {"frame": te, "value": v_, "easing": "ease_out"},
                                 *([{"frame": n - 1, "value": v_, "easing": "linear"}] if te < n - 1 else [])]
            if down:
                x0, y0 = c0 + r_.uniform(-.01, .01), .5 - v0 * ph
                tr = {"x": lin(0, 0), "y": arrive(round(-(v1 - v0) * ph * H, 1))}
            else:
                x0, y0 = .5 - v0 * pw, c0 + r_.uniform(-.01, .01)
                tr = {"x": arrive(round(-(v1 - v0) * pw * W, 1)), "y": lin(0, 0)}
            motion = {"rotation": round(r_.uniform(-.7, .7), 2), "keyframes": {**tr, "scale": lin(1.0, 1.03)}}
            hb = .44 / span                               # the part of the frame in focus, in page units
            gs = (lambda v: [-.1, round(v - hb / 2, 4), 1.2, round(hb, 4)]) if down else (lambda v: [round(v - hb / 2, 4), -.1, round(hb, 4), 1.2])
            band = {"shape": "rect", "geom": gs(v0), "mode": "subtract", "feather_px": round(min(300, .2 * H)),
                    "keyframes": [{"frame": 0, "geom": gs(v0)}, {"frame": te, "geom": gs(v1), "easing": "ease_out"},
                                  *([{"frame": n - 1, "geom": gs(v1)}] if te < n - 1 else [])]}
            last, t0 = fi - 4, 0
            for v, kind_, j in sorted(marks):             # each mark is drawn as the camera reaches it
                f_ = max(round(min(1.0, max(0.0, (v - reach - v0) / max(1e-6, v1 - v0))) * te) - 4 if v1 > v0 else 16, fi, last + 10)
                t0 = max(t0, f_ + 8)                      # when it would finish drawing
                when[(kind_, j)] = last = min(f_, n - fo - 12)
        z0 = 10 + (i % 2) * 8
        paper = [{"name": "paper_grain", "start_frame": 0, "end_frame": 1, "params": {"amount": .14 if it.kind == "document" else .06, "seed": q.seed + 31 * i}},
                 {"name": "vignette", "start_frame": 0, "end_frame": 1, "params": {"amount": r_.uniform(.25, .4)}},
                 {"name": "contrast", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.04}}]
        frame = [{"name": "border", "start_frame": 0, "end_frame": 1, "params": {"amount": 10, "color": "#ece5d6"}}] if it.kind == "photo" else []
        ops.append(L(f"p{i}", "image", a, b, z0, x0, y0, pw, ph, asset_id=it.asset_id, fit="contain", **motion,
                     effects=[*paper, *frame, {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 34}}, *fades]))
        # the focal plane: a softened copy of the sheet over it, cut away where the lens is focused
        ops.append(L(f"p{i}soft", "image", a, b, z0 + 1, x0, y0, pw, ph, asset_id=it.asset_id, fit="contain", **motion,
                     masks=[{"shape": "rect", "geom": [0, 0, 1, 1], "mode": "add"}, band],
                     effects=[*paper, {"name": "blur", "start_frame": 0, "end_frame": 1, "params": {"amount": 3.5}}, *fades]))
        # raking light: a warm pool sliding across the frame from the window side
        side = -1 if r_.random() < .5 else 1
        ops.append(L(f"p{i}light", "shape", a, b, z0 + 3, .05, .05, .7, .9, color="#ffe9c4", opacity=.3, blend="soft_light", data={"shape": "ellipse"},
                     keyframes={"x": lin(round(-side * .1 * W, 1), round(side * .12 * W, 1))},
                     effects=[{"name": "blur", "start_frame": 0, "end_frame": 1, "params": {"amount": 80}}, *fades]))
        # pencil marks under the words that matter, and around the passages the release withholds
        els = []
        vb = [1000, round(1000 / ar, 1)]
        for j, (ux, uy, uw) in enumerate(underline):
            f_ = when[("u", j)]
            els.append({"id": f"u{j}", "type": "line", "x1": round(ux * 1000, 1), "y1": round(uy * vb[1], 1), "x2": round((ux + uw) * 1000, 1),
                        "y2": round(uy * vb[1] + r_.uniform(-2, 2), 1), "stroke": q.mark, "stroke_width": 4.5, "linecap": "round", "draw": [f_, f_ + 8]})
            sound["marks"].append(A(a + f_))
        for j, (wx, wy, ww, wh) in enumerate(withheld):
            f_, pad = when[("w", j)], 6
            els.append({"id": f"w{j}", "type": "rect", "x": round(wx * 1000 - pad, 1), "y": round(wy * vb[1] - pad, 1), "width": round(ww * 1000 + 2 * pad, 1),
                        "height": round(wh * vb[1] + 2 * pad, 1), "rx": 3, "stroke": q.mark, "stroke_width": 3.5, "fill": "none", "draw": [f_, f_ + 10]})
            sound["marks"].append(A(a + f_))
        if els and t0 > n - fo - 4:
            notes.append(f"item {i}: its marks are reached {(t0 - (n - fo - 4)) / FPS:.1f} s too late for the dissolve; give it a longer hold")
        if els:
            ops.append(L(f"p{i}marks", "svg", a, b, z0 + 2, x0, y0, pw, ph, **motion, data={"view_box": vb, "elements": els}, effects=fades))
        # its date (accent, tracked) and archive reference, low left, steady while the sheet moves; one caption at a
        # time: it leaves before the dissolve and the next comes up after it (two captions crossing read as clutter)
        line = line_of(it)
        ca, cb = a + (fi if i else 0), (b - fo if i < len(q.items) - 1 else b)
        cfx = [{"name": "fade_in", "start_frame": 0, "end_frame": 6}, {"name": "fade_out", "start_frame": cb - ca - 6, "end_frame": cb - ca - 1}]
        ops.append(L(f"c{i}sc", "shape", ca, cb, 40, -.04, .80, .62, .22, color="#000000", opacity=.55, data={"shape": "rectangle", "corner_radius": 0},
                     effects=[{"name": "edge_feather", "start_frame": 0, "end_frame": 1, "params": {"amount": .3, "shape": "rect"}}, *cfx]))
        # each line on its own dark plate sized to its words: over cream paper a soft field gave the gold date 1.9:1
        from .design_library import fit_width
        lw = min(.62, fit_width("bevietnampro", line, 30, W, 600, tracking=.14) + .01)
        sw = min(.62, fit_width("bevietnampro", it.source, 26, W, 500) + .01)
        ops.append(L(f"c{i}", "text", ca, cb, 41, .05, .835, lw, .055, text=line, font_id="bevietnampro", font_size=30, font_weight=600, color=q.accent,
                     background="#0c0b0aeb", data={"align": "left"},
                     effects=[{"name": "tracking", "start_frame": 0, "end_frame": 1, "params": {"amount": .14, "from_em": .14, "center": False}}, *cfx]))
        ops.append(L(f"c{i}src", "text", ca, cb, 41, .05, .892, sw, .048, text=it.source, font_id="bevietnampro", font_size=26, font_weight=500, color="#d6cdbb",
                     background="#0c0b0aeb", data={"align": "left"}, effects=cfx))
        if cb - ca - 6 < _hold(line):
            notes.append(f"item {i}: '{line}' holds {(cb - ca - 6) / FPS:.1f} s, under its reading time")
        sound["items"].append({"start": A(a), "end": A(b), "kind": it.kind, "climax": i == climax_i})
    # breaths: the bed drops out on item boundaries at about 40 % and 70 % of the way to the climax
    cl_a = spans[climax_i][0]
    for u in (.4, .7, .55, .85)[:q.breaths]:
        f = min(range(1, climax_i + 1), key=lambda j: abs(spans[j][0] - u * cl_a), default=None) if climax_i else None
        if f is not None and spans[f][0] > 30:
            br = (A(spans[f][0] - 9), A(spans[f][0] + 39))  # 1.6 s: under a second the bed's tails left no hole
            if br not in sound["breaths"]:
                sound["breaths"].append(br)
    # grain over the sheets; the white-out (or black), near silence, a small title
    if q.grain:
        ops.append(L("grain", "film", 0, B, 45, blend="overlay", data={"type": "grain", "intensity": q.grain, "seed": q.seed, "gauge": 16}))
        # overlay leaves the dark desk untouched and its vignette banded in the encode (CAMBI 21, 232 frames): a faint
        # normal grain dithers it, as in archive_montage
        ops.append(L("grain-dither", "film", 0, B, 44, opacity=.09, data={"type": "grain", "intensity": 1.0, "seed": q.seed + 1, "gauge": 16}))
    title_color = "#1d1b18" if q.ending == "whiteout" else "#efe6d6"
    if q.ending == "whiteout":
        ops.append(L("white", "shape", B - 10, N, 60, color="#ece6da", data={"shape": "rectangle", "corner_radius": 0},
                     effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 12}]))
    tt = None
    if q.title:
        tt = N - title_n
        ops.append(L("title", "text", tt, N, 62, .1, .47, .8, .07, text=q.title.upper(), font_id="bevietnampro", font_size=38, font_weight=500, color=title_color,
                     data={"align": "center"}, effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 10},
                                                        {"name": "tracking", "start_frame": 0, "end_frame": title_n - 1, "easing": "linear",
                                                         "params": {"amount": .4, "from_em": .3, "center": True}},
                                                        {"name": "fade_out", "start_frame": title_n - 10, "end_frame": title_n - 1}]))
    ops.append(L("end-intent", "null", B, N, 0, data={"intent": "deliberate_still"}))
    sound.update({"body": [A(0), A(B)], "climax": A(spans[climax_i][0]), "whiteout": A(B), "silence": [A(B), A(tt if tt is not None else N)],
                  "title": A(tt) if tt is not None else None, "end": A(N)})
    return {"ops": ops, "notes": notes,
            "inspect_frames": [A(spans[0][0] + 20), A(spans[len(spans) // 2][0] + holds[len(spans) // 2] // 2), A(spans[climax_i][0] + 30), A(B + 20)],
            "sound_plan": sound,
            "measurements": {"items": len(q.items), "hold_s": [round(h / FPS, 2) for h in holds], "dissolve_s": round(d / FPS, 2),
                             "marks": len(sound["marks"]), "withheld_items": sum(1 for it in q.items if it.withheld), "climax_s": round(spans[climax_i][0] / FPS, 2),
                             "breaths": len(sound["breaths"])},
            "verify": "snapshot a sheet mid-push (the band in focus moves, the light slides, the shadow lifts it off the desk), each mark, the white-out; "
                      "play it: dissolves and pushes, no cut; run form_arc(video, plan, 'dossier')."}


def _check_marks(path, underline, withheld, aid):
    """Marks measured on the scan itself. An underline goes in the clear gap under the line of type it points at (a
    line drawn through "take all necessary steps" reads as struck out); none fits, it is refused. A withheld passage
    must be the release's own black bar: mostly dark on the scan."""
    from PIL import Image
    im = Image.open(path).convert("L")
    if im.width > 1600:
        im = im.resize((1600, round(im.height * 1600 / im.width)))
    a = np.asarray(im, dtype=np.float32)
    h, w = a.shape
    thr = min(150.0, float(np.median(a)) - 60)            # ink: well darker than the paper
    out_u = []
    for x, y, uw in underline:
        c0, c1 = int(x * w), max(int(x * w) + 1, int((x + uw) * w))
        r0, r1 = max(0, int((y - .03) * h)), min(h, int((y + .03) * h))
        ink = (a[r0:r1, c0:c1] < thr).mean(1) > .06            # a row of type, not a descender crossing the gap
        lines, k = [], 0                                  # runs of inked rows: the lines of type near the mark
        while k < len(ink):
            if ink[k]:
                j = k
                while j + 1 < len(ink) and ink[j + 1]:
                    j += 1
                lines.append((r0 + k, r0 + j))
                k = j + 1
            else:
                k += 1
        target = int(y * h)
        above = [ln for ln in lines if ln[0] < target - .002 * h]  # the line the mark is under starts above it
        if not above:
            raise ValueError(f"item {aid}: no line of type above the underline at y={y:.3f} on the scan")
        top, bottom = max(above, key=lambda ln: ln[1])
        nxt = min([ln[0] for ln in lines if ln[0] > bottom] or [r1])
        gap = nxt - bottom - 1
        if gap < 2:
            raise ValueError(f"item {aid}: the underline at y={y:.3f} would cross the next line of type (no clear row under the words)")
        out_u.append([x, round((bottom + 1 + max(1.0, .3 * gap)) / h, 4), uw])
    for x, y, ww, wh in withheld:
        box = a[int(y * h):max(int(y * h) + 1, int((y + wh) * h)), int(x * w):max(int(x * w) + 1, int((x + ww) * w))]
        dark = float((box < thr).mean()) if box.size else 0.0
        if dark < .6:
            raise ValueError(f"item {aid}: the withheld passage at {[x, y, ww, wh]} is not a black bar on the scan ({dark:.0%} dark): "
                             "mark only what the release itself withholds")
    return out_u, withheld


# ---------------------------------------------------------------- sound
def _design(kind, d, seed, **kw):
    from . import sound as snd
    cap = 60 if kind in snd.BEDS else 12
    return snd.design(kind, round(max(.08, min(d, cap)), 3), seed, **kw)


def score_map_matte(plan, fps=FPS, seed=7, music=None):
    """Sparse sound for a map_matte: a low drone that breathes in phrases (holes between them), a soft tick for each
    event as it lights (merged when they crowd), the footage's own sound low through a radio filter, everything
    falling to the floor through the drain and silent for its last second and a half. music: {"path", "source_start"?,
    "volume"?} placed low under the body, out through the drain."""
    out, n_ = [], [0]
    rng = random.Random(seed)
    b0, b1 = plan["body"]
    d0, d1 = plan["drain"]

    def add(kind, a, b, vol, fi, fo, role="sfx", **kw):
        n_[0] += 1
        r = _design(kind, (b - a) / fps, seed + n_[0], **kw)
        out.append({"path": r["path"], "kind": kind, "start_frame": a, "end_frame": min(b, a + round(r["duration"] * fps)), "volume": vol, "role": role,
                    "fade_in": fi, "fade_out": fo})
    a = b0
    stop = d0 + round((d1 - d0) * .45)                    # the bed is gone before the drain's second half: the floor is silence
    while a < stop:
        n = round(rng.uniform(6, 10) * fps)
        b = min(stop, a + n)
        last = b >= d0
        add("drone", a, b, .5, 1.2, max(.8, (b - max(a, d0 - fps)) / fps * .9) if last else 1.0, role="ambience", gain_db=-24)
        a = b + round(rng.uniform(1.0, 1.6) * fps)       # a hole: the map's quiet is part of its sound
    prev = -10 ** 6
    for f in plan["events"][:200]:
        if f - prev >= 10 and f < d0:
            add("tick", f, f + 8, .4, .002, .05, gain_db=-24)
            prev = f
    for v in plan["footage"]:
        if v.get("sound"):
            out.append({"asset_id": v["asset_id"], "source_start": v["source_start"], "start_frame": v["start"], "end_frame": v["end"], "volume": .26,
                        "role": "sfx", "fade_in": .5, "fade_out": .5, "treatment": "radio"})
    if music:
        out.append({"path": music["path"], "kind": "music", "start_frame": b0, "end_frame": stop, "source_start": music.get("source_start", 0.0),
                    "volume": music.get("volume", .45), "role": "music", "fade_in": 1.5, "fade_out": max(1.0, (stop - d0) / fps)})
    return out


def score_dossier(plan, fps=FPS, seed=7, music=None):
    """Sound for a dossier: a bed that rises by thirds to the climax (+13 LU in Godzilla's titles), dropping out for
    each breath; a soft shutter under each pencil mark and on the climax sheet a low impact; then nothing through the
    white-out but a low swell under the title. music: {"path", "source_start"?, "volume"?}: rises the same way and is
    cut at the white-out."""
    out, n_ = [], [0]
    b0, wo = plan["body"][0], plan["whiteout"]

    def add(kind, a, b, vol, fi, fo, role="sfx", **kw):
        n_[0] += 1
        r = _design(kind, (b - a) / fps, seed + n_[0], **kw)
        out.append({"path": r["path"], "kind": kind, "start_frame": a, "end_frame": min(b, a + round(r["duration"] * fps)), "volume": vol, "role": role,
                    "fade_in": fi, "fade_out": fo})
    # the bed, in runs between the breaths, each run at the gain of the third it starts in
    edges = [b0] + [x for br in sorted(plan["breaths"]) for x in br] + [wo]
    runs = [(edges[i], edges[i + 1]) for i in range(0, len(edges) - 1, 2) if edges[i + 1] - edges[i] > 12]
    gains = (.3, .5, .9)                                 # about 10 dB over the thirds, the climax's hits on top (Godzilla: +13 LU)
    cl = plan["climax"]
    # ONE drone for the whole bed, its stretches cut from it: a drone designed per stretch (a seed each) came out at
    # levels of its own, and the thirds measured flat
    n_[0] += 1
    bed = _design("drone", min(60.0, (wo - b0) / fps + .5), seed + n_[0], gain_db=-16)
    blen = round(bed["duration"] * fps)
    for a, b in runs:
        f = a
        while f < b:
            third = min(2, int(3 * (f - b0) / max(1, cl - b0)))
            nxt = b0 + (cl - b0) * (third + 1) // 3 if third < 2 else b
            e = min(b, f + 58 * fps, max(f + 12, nxt))   # a new stretch at each third, so each sits at its own gain
            off = (f - b0) % max(1, blen - (e - f)) if blen > e - f else 0
            out.append({"path": bed["path"], "kind": "drone", "start_frame": f, "end_frame": min(e, f + blen), "source_start": round(off / fps, 3),
                        "volume": gains[third], "role": "ambience", "fade_in": .25 if f == a else .3, "fade_out": .12 if e == b else .3})
            if music:
                out.append({"path": music["path"], "kind": "music", "start_frame": f, "end_frame": e,
                            "source_start": round(music.get("source_start", 0.0) + (f - b0) / fps, 3),
                            "volume": round(music.get("volume", .8) * gains[third] / .8, 3), "role": "music", "fade_in": .25, "fade_out": .12})
            f = e
    for f in plan["marks"]:
        # the marks are the rhythm, under the bed's climb: as foley (the renderer levels sfx to a -12 dB peak, and the
        # shutters had flattened the thirds); a breath stays empty
        if not any(a - 6 <= f < b for a, b in plan["breaths"]):
            add("shutter", f, f + 6, .3, .001, .02, role="foley", gain_db=-18)
    add("impact", plan["climax"], plan["climax"] + 24, 1.0, .001, .2, gain_db=-9)
    add("braam", plan["climax"], plan["climax"] + 60, .9, .002, .6, gain_db=-11)
    add("sub_drop", plan["climax"], plan["climax"] + 45, .9, .001, .3, gain_db=-11)
    if plan.get("title"):
        add("drone", plan["title"], min(plan["end"], plan["title"] + 3 * fps), .3, 1.0, 1.0, role="ambience", gain_db=-28)
    return out


def _luma_spread(video, t, polygon):
    """95th minus 5th percentile of luma (0-255) inside a screen polygon (fractions) of the frame at t seconds."""
    import subprocess
    from PIL import Image, ImageDraw
    from .media import FFMPEG
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=640:360,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    if len(raw) < 640 * 360 or len(polygon) < 3:
        return None
    y = np.frombuffer(raw[:640 * 360], np.uint8).reshape(360, 640)
    m = Image.new("L", (640, 360), 0)
    ImageDraw.Draw(m).polygon([(x * 640, v * 360) for x, v in polygon], fill=255)
    v = y[np.asarray(m) > 0]
    return round(float(np.percentile(v, 95) - np.percentile(v, 5)), 1) if v.size > 200 else None


def form_arc(video, plan, form, fps=FPS):
    """The mix's shape for a form, measured on the render (RMS dB in 0.25 s windows).
    map_matte: sparse (at least three holes 12 dB under the body's 75th percentile), the drain's second half 12 dB
    under the body; dossier: the bed rises (thirds within 1 dB of each other's rise), the climax sheet 10 dB over the
    first third, and at least three near silences (below -45 dBFS for 0.8 s or more) totalling 4-9 s."""
    import subprocess
    import numpy as np
    from .media import FFMPEG
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    win = 4000
    lv = np.array([20 * np.log10(max(1e-9, float(np.sqrt(np.mean(x[i:i + win] ** 2))))) for i in range(0, max(0, len(x) - win), win)])
    at = lambda f: int(f / fps * 4)
    seg = lambda a, b: lv[at(a):max(at(a) + 1, at(b))]
    db = lambda a, b: round(float(10 * np.log10(np.mean(10 ** (seg(a, b) / 10)) + 1e-12)), 1)
    b0, b1 = plan["body"]
    if form == "map_matte":
        body = seg(b0, b1)
        p75 = float(np.percentile(body, 75))
        holes, run = 0, 0
        for v in body:
            run = run + 1 if v < p75 - 12 else 0
            holes += run == 3                             # 0.75 s under: a hole
        d0, d1 = plan["drain"]
        late = db((d0 + d1) // 2, d1)
        out = {"body_p75": round(p75, 1), "holes": holes, "drain_late": late, "drain_drop": round(p75 - late, 1)}
        # the footage must read inside the land: its luma spread (5th to 95th percentile) inside the shape at mid-clip
        # (the first cut's Huế river was a pale fog of 30 levels)
        spread = [{"asset_id": c["asset_id"], "frame": c["frame"], "luma_p5_p95": _luma_spread(video, c["frame"] / fps, c["polygon"])}
                  for c in plan.get("checks", [])]
        out["footage_spread"] = spread
        out["pass"] = bool(holes >= 3 and p75 - late >= 12 and all(x["luma_p5_p95"] is None or x["luma_p5_p95"] >= 60 for x in spread))
        return out
    cl = plan["climax"]
    held = np.ones(len(lv), bool)                         # the breaths are silence by design: the climb is measured on the bed
    for a_, b_ in plan.get("breaths", []):
        held[at(a_):at(b_)] = False

    def bed(a_, b_):
        v = lv[at(a_):max(at(a_) + 1, at(b_))][held[at(a_):max(at(a_) + 1, at(b_))]]
        return round(float(10 * np.log10(np.mean(10 ** (v / 10)) + 1e-12)), 1) if len(v) else -120.0
    th = [bed(b0 + (cl - b0) * i // 3, b0 + (cl - b0) * (i + 1) // 3) for i in range(3)]
    peak = db(cl, cl + round(1.5 * fps))
    quiet, run, runs = 0.0, 0, []
    for v in lv[at(b0):]:
        if v < -45:
            run += 1
        else:
            if run >= 4:
                runs.append(run / 4)
            run = 0
    if run >= 4:
        runs.append(run / 4)
    quiet = round(sum(runs), 2)
    rises = th[1] >= th[0] - 1 and th[2] >= th[1] - 1
    return {"thirds": th, "climax": peak, "rise": round(peak - th[0], 1), "near_silences": len(runs), "quiet_s": quiet, "rises": rises,
            "pass": bool(rises and 10 <= peak - th[0] <= 20 and len(runs) >= 3 and 4 <= quiet <= 9)}
