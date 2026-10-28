"""Intent-level animation: the AI names the action (hop, drop, slide_to, turn, rock, pop, hit, enter, exit) and a
material; this compiles the classic principles into keyframes and track modifiers on one layer.

Numbers come from frame-by-frame measurement of animation-principle demonstrations (round-4 study, local analysis
only), converted to 30 fps: stretch builds only in the last ~5 frames of a fall; contact squash lasts 1 frame with
width/height ≈ 1 + 1.5·v (v = impact speed in body heights per frame); 2 frames of rebound stretch; bounce heights
shrink ×0.33 then ×0.26 and air time ×0.64/×0.7 (≈ √height); a jump crouches 5 frames, holds 4, launches in 2-3
(anticipation ≈ 3× the action); x moves linearly through an arc while y eases (decelerate up, accelerate down, no ease
into a collision); follow-through overshoots ≈ 0.65× the drag with a 5-frame period and halves each cycle; a product
pop measured 0 → 1.08 → 0.955 → 1.0 over 9/4/3 frames; a rock 5° → -2° → 0.6° → 0 in 5-frame steps.
"""
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .models import TRACK_LIMITS

RISE = [.3, .6, .5, 1]       # decelerating toward the apex
FALL = [.5, 0, .7, .4]       # accelerating into contact (no ease into a collision)
ARRIVE = [.45, 0, .75, .9]   # arrives with speed so inertia can overshoot and settle
LEAVE = [.55, 0, 1, .45]     # accelerates away
SOFT_OUT = [.22, 1, .36, 1]  # quint-out

MATERIALS = {
    # max contact squash (w/h), fall/launch stretch (h/w), rebound height ratio, extra bounces, settle inertia
    "stiff": dict(squash=1.06, stretch=1.04, rebound=.37, bounces=1, inertia=dict(amount=.3, period_frames=5, decay=.35)),
    "rubber": dict(squash=2.4, stretch=1.6, rebound=.33, bounces=2, inertia=dict(amount=.6, period_frames=5, decay=.5)),
    "soft": dict(squash=3.0, stretch=1.8, rebound=.15, bounces=1, inertia=dict(amount=1.0, period_frames=8, decay=.55)),
    "ui": dict(squash=1.12, stretch=1.08, rebound=.2, bounces=1, inertia=dict(amount=.45, period_frames=6, decay=.45)),
}


class Beat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verb: Literal["hop", "drop", "slide_to", "turn", "rock", "pop", "hit", "enter", "exit"]
    at: int = Field(ge=0)  # layer-local frame where the beat (including anticipation) starts
    height: float = Field(default=120, gt=0, le=4000)  # hop/drop px
    to: list[float] | None = Field(default=None, min_length=2, max_length=2)  # px offset [dx, dy] relative to the rest pose
    deg: float = Field(default=20, ge=-720, le=720)  # turn/rock degrees
    frames: int | None = Field(default=None, ge=2, le=240)  # main action length (auto per verb)
    side: Literal["left", "right", "top", "bottom"] = "left"  # enter from / exit to
    distance: float | None = Field(default=None, gt=0, le=8000)  # enter/exit travel px (default: 1.2 frame widths)
    anticipation: Literal["auto", "none"] | int = "auto"


class AnimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layer_id: str
    beats: list[Beat] = Field(min_length=1, max_length=20)
    material: Literal["stiff", "rubber", "soft", "ui"] = "ui"
    exaggerate: float = Field(default=.6, ge=0, le=1.5)  # 1 = measured cartoon amounts; .4-.7 suits graphics and UI
    motion_blur: bool = True


class Keys:
    def __init__(self):
        self.t = {}

    def add(self, track, frame, value, bezier=None, easing=None):
        lo, hi = TRACK_LIMITS[track]
        k = {"frame": int(frame), "value": round(min(hi, max(lo, value)), 4)}
        if bezier:
            k["bezier"] = bezier
        elif easing:
            k["easing"] = easing
        pts = self.t.setdefault(track, [])
        pts[:] = [p for p in pts if p["frame"] != k["frame"]] + [k]
        pts.sort(key=lambda p: p["frame"])

    def last(self, track, default):
        pts = self.t.get(track)
        return pts[-1]["value"] if pts else default


def _air(h, ref_h=120):
    return max(4, round(6 + .8 * math.sqrt(h)))


def _contact(K, M, ex, f, v_norm):
    """1-frame squash on contact, 2 frames of rebound stretch, round on the third."""
    s = min(M["squash"], 1 + 1.5 * v_norm)
    s = 1 + (s - 1) * ex
    K.add("squash", f - 1, 1 / (1 + (M["stretch"] - 1) * ex), FALL)
    K.add("squash", f, s, easing="linear")
    K.add("squash", f + 1, 1 / (1 + (M["stretch"] - 1) * ex * .9), easing="linear")
    K.add("squash", f + 2, 1 / (1 + (M["stretch"] - 1) * ex * .45), easing="linear")
    K.add("squash", f + 3, 1, easing="ease_out")


def _fall_and_bounce(K, M, ex, f_apex, y0, h, box_h, bounces=None):
    """From an apex at height h above rest: fall, contact, smaller bounces. Returns (contact frames, end frame)."""
    T = _air(h)
    contacts = []
    f = f_apex
    K.add("squash", f, 1, easing="ease_out")
    K.add("squash", f + max(1, T - 5), 1, easing="linear")  # stays round until the last ~5 frames
    land = f + T
    K.add("y", land, y0, FALL)
    contacts.append(land)
    _contact(K, M, ex, land, (2 * h / T) / max(1, box_h))
    hh, TT = h, T
    ratios = [M["rebound"], .79]
    for i in range(M["bounces"] if bounces is None else bounces):
        hh *= ratios[min(i, 1)]
        if hh < 2:
            break
        TT = max(3, round(T * math.sqrt(hh / h)))
        up = land + TT
        K.add("y", up, y0 - hh, RISE)
        land = up + TT
        K.add("y", land, y0, FALL)
        K.add("squash", up, 1, easing="ease_out")
        contacts.append(land)
        _contact(K, M, ex, land, (2 * hh / TT) / max(1, box_h))
    return contacts, land + 3


def compile_beats(req: AnimateRequest, layer, W=1920, H=1080):
    M = MATERIALS[req.material]
    ex = req.exaggerate
    box_h = max(1.0, layer.get("height", .3) * H)
    K, out = Keys(), []
    x0, y0 = 0.0, 0.0
    ordered = sorted(req.beats, key=lambda b: b.at)
    first = ordered[0]
    for b in ordered:
        f = b.at
        ant = 0 if b.anticipation == "none" else (b.anticipation if isinstance(b.anticipation, int) else None)
        if b.verb == "hop":
            A = 5 if ant is None else ant
            hold = 4 if ant is None else (0 if ant == 0 else max(1, ant // 2))
            crouch = 1 + min(.8, (M["squash"] - 1) * .6) * ex
            K.add("y", f, y0, easing="linear")
            K.add("squash", f, 1, easing="linear")
            if A:
                K.add("squash", f + A, crouch, easing="ease_out")
            if hold:
                K.add("squash", f + A + hold, crouch, easing="linear")
            take = f + A + hold + 2
            K.add("squash", take, 1 / (1 + (M["stretch"] - 1) * ex * .6), easing="ease_in")
            K.add("y", take, y0, easing="linear")
            T = _air(b.height)
            apex = take + T
            K.add("squash", take + round(.55 * T), 1, easing="ease_out")
            K.add("y", apex, y0 - b.height, RISE)
            if b.to:
                K.add("x", take, x0, easing="linear")
            contacts, end = _fall_and_bounce(K, M, ex, apex, y0 + (b.to[1] if b.to else 0), b.height, box_h)
            if b.to:
                x0 += b.to[0]
                K.add("x", contacts[0], x0, easing="linear")  # linear x through the arc
                y0 += b.to[1]
            out.append({"verb": "hop", "frames": [f, end], "takeoff": take, "apex": apex, "contacts": contacts})
        elif b.verb == "drop":
            K.add("y", f, y0 - b.height, easing="linear")
            contacts, end = _fall_and_bounce(K, M, ex, f, y0, b.height, box_h)
            out.append({"verb": "drop", "frames": [f, end], "contacts": contacts})
        elif b.verb in ("slide_to", "enter", "exit"):
            n = b.frames or {"slide_to": 18, "enter": 14, "exit": 10}[b.verb]
            if b.verb == "slide_to":
                dx, dy = b.to or (200, 0)
                start = (x0, y0)
                end_pos = (x0 + dx, y0 + dy)
            else:
                d = b.distance or 1.2 * W
                v = {"left": (-d, 0), "right": (d, 0), "top": (0, -d), "bottom": (0, d)}[b.side]
                start, end_pos = ((x0 + v[0], y0 + v[1]), (x0, y0)) if b.verb == "enter" else ((x0, y0), (x0 + v[0], y0 + v[1]))
            A = (min(10, max(3, round(.35 * n))) if ant is None else ant) if b.verb != "enter" else 0
            g = f
            for tr, s0 in (("x", start[0]), ("y", start[1])):
                K.add(tr, g, s0, easing="linear")
            if A:
                back = (.06 if b.verb == "slide_to" else .04)
                for tr, s0, e0 in (("x", start[0], end_pos[0]), ("y", start[1], end_pos[1])):
                    K.add(tr, g + A, s0 - (e0 - s0) * back, SOFT_OUT)
                g += A
            curve = LEAVE if b.verb == "exit" else ARRIVE
            for tr, e0 in (("x", end_pos[0]), ("y", end_pos[1])):
                K.add(tr, g + n, e0, curve)
            x0, y0 = end_pos
            out.append({"verb": b.verb, "frames": [f, g + n], "anticipation": A})
        elif b.verb == "turn":
            n = b.frames or 15
            r0 = K.last("rotate", 0.0)
            A = (min(8, max(3, round(.35 * n))) if ant is None else ant)
            K.add("rotate", f, r0, easing="linear")
            if A:
                K.add("rotate", f + A, r0 - .08 * b.deg, SOFT_OUT)
            K.add("rotate", f + A + n, r0 + b.deg, ARRIVE)
            out.append({"verb": "turn", "frames": [f, f + A + n], "anticipation": A})
        elif b.verb == "rock":
            r0 = K.last("rotate", 0.0)
            step = b.frames or 5
            seq = [b.deg, -.4 * b.deg, .12 * b.deg, 0]
            K.add("rotate", f, r0, easing="linear")
            for i, v in enumerate(seq, 1):
                K.add("rotate", f + i * step, r0 + v, easing="ease_in_out")
            out.append({"verb": "rock", "frames": [f, f + 4 * step]})
        elif b.verb == "pop":
            # First beat: an entrance from nothing (measured product pop). Later: an emphasis pulse from rest.
            entrance = b is first
            s9, s13, s16 = 1 + .08 * ex / .6, 1 - .045 * ex / .6, 1.0
            if not entrance:
                K.add("scale", 0, 1, easing="linear")
            K.add("scale", f, .01 if entrance else 1, easing="linear")
            K.add("scale", f + 9, s9, SOFT_OUT)
            K.add("scale", f + 13, s13, easing="ease_in_out")
            K.add("scale", f + 16, s16, easing="ease_in_out")
            out.append({"verb": "pop", "frames": [f, f + 16], "peak_scale": round(s9, 3)})
        elif b.verb == "hit":
            s = 1 + (M["squash"] - 1) * .5 * ex
            K.add("squash", f, 1, easing="linear")
            K.add("squash", f + 1, s, easing="linear")
            K.add("squash", f + 3, 1, easing="ease_out")
            out.append({"verb": "hit", "frames": [f, f + 3]})
    mods = {}
    for tr in ("x", "y", "rotate"):
        if tr in K.t and any(o["verb"] in ("slide_to", "enter", "turn") for o in out):
            mods[tr] = {"inertia": dict(M["inertia"])}
    if "squash" in K.t and req.material in ("soft", "rubber"):
        mods["squash"] = {"inertia": dict(M["inertia"])}
    for tr, pts in K.t.items():
        if len(pts) > 100:
            raise ValueError(f"{tr} needs {len(pts)} keys (>100): fewer or shorter beats")
    return K.t, mods, out


def apply(pid, base_revision, request, dry_run=False):
    """Compile beats onto an existing layer: keyframe tracks the beats use are replaced, other tracks/effects stay."""
    from . import agent
    q = AnimateRequest.model_validate(request)
    p = agent.read(pid)
    if p["revision"] != base_revision:
        raise ValueError("Read the current project revision before animating")
    t = p["timeline"]
    layer = next((l for l in t.get("layers") or [] if l["id"] == q.layer_id), None)
    if not layer:
        raise ValueError(f"Layer {q.layer_id} not found")
    keys, mods, beats = compile_beats(q, layer, t["width"], t["height"])
    dur = layer["end_frame"] - layer["start_frame"]
    last = max(p_["frame"] for pts in keys.values() for p_ in pts)
    notes = []
    if last >= dur:
        notes.append(f"Beats run to local frame {last} but the layer lasts {dur} frames; extend end_frame or start earlier.")
    new = dict(layer)
    new["keyframes"] = {**(layer.get("keyframes") or {}), **keys}
    new["track_mods"] = {**{k: v for k, v in (layer.get("track_mods") or {}).items() if k in new["keyframes"]}, **mods}
    fx = [e for e in layer.get("effects") or [] if e["name"] != "motion_blur"]
    if q.motion_blur:
        fx.append({"name": "motion_blur", "start_frame": 0, "end_frame": 1, "params": {"amount": 180}})
    new["effects"] = fx[:16]
    from .models import Layer
    Layer.model_validate(new)
    summary = {"tracks": {k: len(v) for k, v in keys.items()}, "modifiers": sorted(mods), "beats": beats, "notes": notes,
               "inspect_frames": [layer["start_frame"] + f for f in sorted({b["frames"][0] + 1 for b in beats} | {c for b in beats for c in b.get("contacts", [])[:1]} | {b["frames"][1] for b in beats})[:6]]}
    if dry_run:
        return {"dry_run": True, **summary, "keyframes": keys, "track_mods": mods}
    rev = agent.patch(pid, base_revision, [{"op": "upsert_layer", "layer": new}])["revision"]
    return {"revision": rev, **summary}
