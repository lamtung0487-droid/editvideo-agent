"""Globe helper: geography (lat/lon markers, great-circle arcs, camera dives) compiled into a native Scene3D layer."""
import math
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .scene3d import Bloom, Point3, Scene3D


class GlobeMarker(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str = Field(default="", max_length=80)
    color: str = Field(default="#ffd166", pattern=r"^#[0-9a-fA-F]{6}$")
    size: float = Field(default=.008, ge=.002, le=.5)  # core dot diameter in globe radii
    appear: int = Field(default=0, ge=0)
    pulse: bool = True  # expanding ring lying on the surface, repeating every pulse_every frames
    pulse_every: int = Field(default=36, ge=12, le=300)


class GlobeOutline(BaseModel):
    """A glowing line drawn on the surface through [lon, lat] points (e.g. a country border); grown by frame."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    points: list[list[float]] = Field(min_length=2, max_length=5000)
    color: str = Field(default="#ffd166", pattern=r"^#[0-9a-fA-F]{6}$")
    radius: float = Field(default=.0025, ge=.0005, le=.05)
    grow: list[int] | None = None
    lift: float = Field(default=.002, ge=0, le=.2)
    emissive_intensity: float = Field(default=2.2, ge=0, le=20)

    @model_validator(mode="after")
    def check(self):
        if any(len(p) != 2 or not -360 <= p[0] <= 360 or not -90 <= p[1] <= 90 for p in self.points):
            raise ValueError(f"outline {self.id} points are [lon, lat]")
        if self.grow is not None and (len(self.grow) != 2 or not 0 <= self.grow[0] < self.grow[1]):
            raise ValueError(f"outline {self.id} grow needs [start, end] frames")
        return self


class GlobeArc(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    start: str
    end: str
    height: float = Field(default=.18, ge=0, le=2)
    grow: list[int]
    color: str = Field(default="#ffd166", pattern=r"^#[0-9a-fA-F]{6}$")
    radius: float = Field(default=.008, ge=.001, le=.2)
    traveler: bool = True


class GlobeCamera(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame: int = Field(ge=0)
    lat: float = Field(ge=-89, le=89)
    lon: float = Field(ge=-360, le=360)
    altitude: float = Field(ge=.02, le=40)  # distance above the surface, in globe radii
    look: float = Field(default=0, ge=0, le=1)  # 0 = look at the globe center, 1 = at the surface point below


class GlobeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default="globe", pattern=r"^[A-Za-z0-9_-]{1,60}$")
    start_frame: int = Field(default=0, ge=0)
    end_frame: int
    x: float = 0
    y: float = 0
    width: float = 1
    height: float = 1
    z: int = 20
    attach_shot: str | None = None
    earth_texture: str
    clouds_texture: str | None = None
    bump_texture: str | None = None
    radius: float = Field(default=1.5, ge=.1, le=20)
    markers: list[GlobeMarker] = Field(default_factory=list, max_length=20)
    arcs: list[GlobeArc] = Field(default_factory=list, max_length=12)
    outlines: list[GlobeOutline] = Field(default_factory=list, max_length=6)
    camera: list[GlobeCamera] = Field(min_length=1, max_length=40)
    stars: int = Field(default=40, ge=0, le=40)
    atmosphere: bool = True
    atmosphere_color: str = Field(default="#6fb8ff", pattern=r"^#[0-9a-fA-F]{6}$")  # Mars: thin butterscotch haze, e.g. #e8a070
    sun: Point3 = Field(default_factory=lambda: Point3(x=-4, y=1.5, z=3))
    # Sub-solar point; when set it overrides `sun` so the chosen region is lit (a few degrees west of the target = soft terminator).
    sun_lat: float | None = Field(default=None, ge=-90, le=90)
    sun_lon: float | None = Field(default=None, ge=-360, le=360)
    clouds_opacity: float = Field(default=.8, ge=.05, le=1)
    bloom: Bloom | None = Field(default_factory=lambda: Bloom(strength=.45, radius=.4, threshold=.82))
    background: str = Field(default="#03050a", pattern=r"^#[0-9a-fA-F]{6}$")
    fov: float = Field(default=38, ge=15, le=90)
    label_font_size: int = Field(default=30, ge=16, le=96)

    @model_validator(mode="after")
    def refs(self):
        ids = {m.id for m in self.markers}
        for a in self.arcs:
            if a.start not in ids or a.end not in ids:
                raise ValueError(f"arc {a.id} must connect marker ids")
            if len(a.grow) != 2 or not 0 <= a.grow[0] < a.grow[1]:
                raise ValueError(f"arc {a.id} grow needs [start, end] frames")
        if any(a.frame >= b.frame for a, b in zip(self.camera, self.camera[1:])):
            raise ValueError("camera keys must increase")
        if self.end_frame <= self.start_frame:
            raise ValueError("globe range invalid")
        return self


def latlon_dir(lat, lon):
    """Unit vector matching three.js SphereGeometry UVs with an equirectangular map (left edge = 180°W)."""
    phi = (lon + 180) / 360 * 2 * math.pi
    theta = (90 - lat) / 180 * math.pi
    return (-math.cos(phi) * math.sin(theta), math.cos(theta), math.sin(phi) * math.sin(theta))


def slerp(a, b, t):
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
    om = math.acos(dot)
    if om < 1e-6:
        return a
    s = math.sin(om)
    return tuple((math.sin((1 - t) * om) * x + math.sin(t * om) * y) / s for x, y in zip(a, b))


def simplify(points, limit=480):
    """Ramer-Douglas-Peucker on [lon, lat], loosening tolerance until at most `limit` points remain."""
    if len(points) <= limit:
        return points

    def rdp(pts, eps):
        keep, stack = {0, len(pts) - 1}, [(0, len(pts) - 1)]
        while stack:
            a, b = stack.pop()
            (x1, y1), (x2, y2) = pts[a], pts[b]
            dx, dy, best, idx = x2 - x1, y2 - y1, -1.0, -1
            n = math.hypot(dx, dy)
            for i in range(a + 1, b):
                # Closed rings start and end on the same point: fall back to distance from that point.
                d = abs(dy * (pts[i][0] - x1) - dx * (pts[i][1] - y1)) / n if n > 1e-9 else math.hypot(pts[i][0] - x1, pts[i][1] - y1)
                if d > best:
                    best, idx = d, i
            if idx > 0 and best > eps:
                keep.add(idx)
                stack += [(a, idx), (idx, b)]
        return [pts[i] for i in sorted(keep)]
    eps = .005
    out = rdp(points, eps)
    while len(out) > limit:
        eps *= 1.4
        out = rdp(points, eps)
    return out


def euler_facing(v):
    """XYZ Euler (three.js default order) rotating +Z onto unit vector v, so a torus lies flat on the surface."""
    x, y, z = v
    ax, ay = -y, x  # (0,0,1) x v
    s = math.hypot(ax, ay)
    c = z
    if s < 1e-9:
        return (0.0, 0.0, 0.0) if c > 0 else (math.pi, 0.0, 0.0)
    ax, ay = ax / s, ay / s
    t = 1 - c
    m11, m12, m13 = c + ax * ax * t, ax * ay * t, ay * s
    m22, m23, m32, m33 = c + ay * ay * t, -ax * s, ax * s, c
    ry = math.asin(max(-1.0, min(1.0, m13)))
    if abs(m13) < .9999999:
        return (math.atan2(-m23, m33), ry, math.atan2(-m12, m11))
    return (math.atan2(m32, m22), ry, 0.0)


def globe_scene(q: GlobeRequest):
    r, d = q.radius, q.end_frame - q.start_frame
    vec = lambda v: {"x": round(v[0], 4), "y": round(v[1], 4), "z": round(v[2], 4)}
    objs = [{"id": "earth", "geometry": "sphere", "size": [2 * r] * 3, "texture": q.earth_texture, "roughness": .88, "metalness": 0, "segments": 192,
             **({"bump_texture": q.bump_texture, "bump_scale": 2} if q.bump_texture else {})}]
    if q.clouds_texture:
        objs.append({"id": "clouds", "geometry": "sphere", "size": [2 * r * 1.012] * 3, "color": "#ffffff", "alpha_texture": q.clouds_texture,
                     "opacity": q.clouds_opacity, "roughness": 1, "metalness": 0, "segments": 128,
                     # Drift slowly; thin out as the camera descends so the ground stays readable on close dives.
                     "keyframes": [{"frame": f, "rotation": {"x": 0, "y": round(.12 * f / max(1, d - 1), 5), "z": 0},
                                    "opacity": round(q.clouds_opacity * min(1.0, .2 + alt / 4), 3)}
                                   for f, alt in sorted({0: q.camera[0].altitude, max(1, d - 1): q.camera[-1].altitude,
                                                         **{c.frame: c.altitude for c in q.camera if 0 < c.frame < d - 1}}.items())]})
    if q.atmosphere:
        objs.append({"id": "atmo", "geometry": "sphere", "size": [2 * r * 1.035] * 3, "color": q.atmosphere_color, "opacity": .07,
                     "emissive": q.atmosphere_color, "emissive_intensity": .35, "roughness": 1})
    pos = {}
    for m in q.markers:
        v = latlon_dir(m.lat, m.lon)
        pos[m.id] = v
        keys = [{"frame": 0, "scale": .01}, {"frame": max(1, m.appear), "scale": .01}, {"frame": m.appear + 10, "scale": 1}] if m.appear else []
        objs.append({"id": f"mk-{m.id}", "geometry": "sphere", "size": [m.size * r] * 3, "position": vec(tuple(x * r * 1.003 for x in v)),
                     "color": m.color, "emissive": m.color, "emissive_intensity": 1.6, "label": m.label, "label_facing": {"x": 0, "y": 0, "z": 0}, "keyframes": keys})
        if m.pulse:
            rot = dict(zip("xyz", (round(a, 5) for a in euler_facing(v))))
            ring, k = [{"frame": 0, "scale": .01, "opacity": 0}], 0
            while m.appear + (k + 1) * m.pulse_every - 2 < d and len(ring) < 96:
                a = m.appear + k * m.pulse_every
                ring += [{"frame": max(1, a), "scale": .3, "opacity": .95}, {"frame": a + m.pulse_every - 2, "scale": 3.2, "opacity": 0}]
                k += 1
            objs.append({"id": f"ring-{m.id}", "geometry": "torus", "size": [m.size * r * .9, m.size * r * .07, .01],
                         "position": vec(tuple(x * r * 1.002 for x in v)), "rotation": rot, "color": m.color, "emissive": m.color,
                         "emissive_intensity": 1.8, "roughness": 1, "metalness": 0, "keyframes": ring})
    for o in q.outlines:
        pts = simplify([[p[0], p[1]] for p in o.points])
        path = [[round(x * r * (1 + o.lift), 4) for x in latlon_dir(lat, lon)] for lon, lat in pts]
        objs.append({"id": f"ol-{o.id}", "geometry": "tube", "path": path, "tube_radius": o.radius * r, "grow": o.grow,
                     "color": o.color, "emissive": o.color, "emissive_intensity": o.emissive_intensity, "roughness": .5, "metalness": 0})
    for a in q.arcs:
        pts = []
        for i in range(65):
            t = i / 64
            v = slerp(pos[a.start], pos[a.end], t)
            h = 1.004 + a.height * math.sin(math.pi * t)
            pts.append([round(x * r * h, 4) for x in v])
        objs.append({"id": f"arc-{a.id}", "geometry": "tube", "path": pts, "tube_radius": a.radius * r, "grow": a.grow,
                     "color": a.color, "emissive": a.color, "emissive_intensity": 2.5, "roughness": .4})
        if a.traveler:
            g0, g1 = a.grow
            # Only exists while it travels: scaled in at departure, out on arrival.
            objs.append({"id": f"tr-{a.id}", "geometry": "sphere", "size": [a.radius * r * 3.2] * 3, "color": "#ffffff", "emissive": "#ffffff",
                         "emissive_intensity": 3.5, "follow": f"arc-{a.id}", "follow_range": a.grow, "follow_orient": False,
                         "keyframes": [{"frame": 0, "scale": .01}, *([{"frame": g0, "scale": .01}] if g0 > 0 else []), {"frame": g0 + 3, "scale": 1},
                                       {"frame": max(g0 + 4, g1 - 1), "scale": 1}, {"frame": max(g0 + 5, g1 + 5), "scale": .01}]})
    for i in range(q.stars):
        objs.append({"id": f"st{i}", "geometry": "sphere", "size": [.03 * r] * 3, "color": "#ffffff", "emissive": "#ffffff",
                     "emissive_intensity": 1.2 + (i * 7 % 10) / 6,
                     "position": {"x": round((-30 + (i * 13.37) % 60) * r / 1.5, 2), "y": round((-18 + (i * 7.91) % 36) * r / 1.5, 2),
                                  "z": round((-26 - (i * 3.13) % 12) * r / 1.5, 2)}})
    # Dense camera keys sampled from a C1 path: cubic Hermite through the user keys (Catmull-Rom tangents inside, zero
    # tangents at both ends) over lat, lon, log(altitude) and look. The camera eases out of the first key and into the last
    # one but glides through the middle keys instead of stopping at each; log altitude makes the dive zoom at an even rate.
    # Runtime plays these keys back linearly (camera_ease="linear"); the camera stays outside the sphere because altitude > 0.
    cams = q.camera
    chan = [(c.frame, (c.lat, c.lon, math.log(c.altitude), c.look)) for c in cams]
    def tangent(i, k):
        if i == 0 or i == len(chan) - 1:
            return 0.0
        (f0, a), (f1, b) = chan[i - 1], chan[i + 1]
        return (b[k] - a[k]) / (f1 - f0)
    def at(f):
        if f <= chan[0][0] or len(chan) == 1:
            return chan[0][1]
        if f >= chan[-1][0]:
            return chan[-1][1]
        j = next(i for i in range(1, len(chan)) if chan[i][0] >= f)
        (fa, a), (fb, b) = chan[j - 1], chan[j]
        h, t = fb - fa, (f - fa) / (fb - fa)
        h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
        return tuple(h00 * a[k] + h10 * h * tangent(j - 1, k) + h01 * b[k] + h11 * h * tangent(j, k) for k in range(4))
    def key(f):
        lat, lon, la, look = at(f)
        v = latlon_dir(max(-89.0, min(89.0, lat)), lon)
        alt = max(.02, math.exp(la))
        look = max(0.0, min(1.0, look))
        return {"frame": f, "position": vec(tuple(x * r * (1 + alt) for x in v)), "target": vec(tuple(x * r * look for x in v))}
    step = max(3, math.ceil(d / 95))
    keys = [key(f) for f in range(0, d, step)]
    if keys[-1]["frame"] != d - 1:
        keys.append(key(d - 1))
    sun = q.sun.model_dump()
    if q.sun_lat is not None or q.sun_lon is not None:
        sv = latlon_dir(q.sun_lat or 0, q.sun_lon or 0)
        sun = {"x": round(sv[0] * 10, 3), "y": round(sv[1] * 10, 3), "z": round(sv[2] * 10, 3)}
    return {"objects": objs, "lights": [{"kind": "ambient", "intensity": .05}, {"kind": "directional", "position": sun, "intensity": 3.4, "color": "#fff4e6"}],
            "camera_keyframes": keys, "camera_ease": "linear", "fov": q.fov, "background": q.background, "transparent": False, "ground": False, "shadows": False,
            "bloom": q.bloom.model_dump() if q.bloom else None, "label_font_size": q.label_font_size, "label_color": "#ffffff"}


def compose_globe(pid, base_revision, request):
    from . import agent
    from .models import Layer
    q = GlobeRequest.model_validate(request)
    scene = Scene3D.model_validate(globe_scene(q)).model_dump()
    layer = Layer.model_validate({"id": q.id, "kind": "scene3d", "start_frame": q.start_frame, "end_frame": q.end_frame, "x": q.x, "y": q.y,
                                  "width": q.width, "height": q.height, "z": q.z, "attach_shot": q.attach_shot, "data": scene}).model_dump()
    result = agent.patch(pid, base_revision, [{"op": "upsert_layer", "layer": layer}])
    d = q.end_frame - q.start_frame
    return {"revision": result["revision"], "layer_id": q.id, "objects": len(scene["objects"]),
            "inspect_frames": [q.start_frame, q.start_frame + d // 2, q.end_frame - 1],
            "scope": "Equirectangular texture on a sphere; lat/lon markers and great-circle arcs lifted above the surface, grown by frame; "
                     "camera slerps between lat/lon/altitude keys. Labels hide on the far side. Illustrative geography, not a GIS projection."}


def blender_globe(name, frames, camera, places, arcs, sun=None, stills=None, percent=100, texture=None, lens=35):
    """The globe shot rendered by Blender (editvideo.blender, blender_scripts/globe_shot.py): returns {"mp4" | "stills",
    "job", "per_frame_s"}. places: [{id, lat, lon, label, color, appear}]; arcs: [{start, end, grow: [f0, f1], height,
    color}] between place ids; camera: [{frame, lat, lon, altitude (globe radii), look 0..1}]; sun: {lat, lon} under the
    sun (day and night follow)."""
    from pathlib import Path
    from . import blender
    root = Path(__file__).resolve().parents[1]
    tex = texture or str(root / "data" / "sources" / "textures" / "earth_bluemarble_5400.jpg")
    font = str(root / "assets" / "fonts" / "bevietnampro" / "BeVietnamPro-SemiBold.ttf")
    params = {"texture": tex, "font": font, "frames": frames, "camera": list(camera), "places": list(places), "arcs": list(arcs),
              "sun": sun or {"lat": 12, "lon": 75, "strength": 4.0}, "percent": percent, "lens": lens}
    if stills:
        params["stills"] = list(stills)
    r = blender.run("globe_shot", params, files=[tex, font])
    out = {"job": r["job"], "per_frame_s": r.get("per_frame_s"), "cached": r.get("cached")}
    if stills:
        out["stills"] = [str(Path(r["job"]) / f"still_{f:04d}.png") for f in stills]
    else:
        out["mp4"] = blender.encode(r["job"])
    return out
