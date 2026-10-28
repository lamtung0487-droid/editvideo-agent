"""Title design: film title cards, poster/credit lockups, trailer word cards and sound-first reveals.

Numbers come from frame-by-frame measurement of title-design tutorials and the film titles they show (round-3 study,
kept locally for analysis only): cap heights as a share of frame height, tracking in em, holds and black-before
durations at 30 fps. Every recipe compiles to ordinary layers (text, shape) and effects that render identically in
Remotion and HyperFrames.
"""
from functools import lru_cache
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .cinematic import FPS, HEX, _timeline, _apply, preview_ops, _ids

LayerId = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
QUINT_OUT = [.22, 1, .36, 1]

# Preset → look (font, weight, cap height share of H, max width share of W, tracking em) and timing (frames at 30 fps).
PRESETS = {
    # Hard cut on the hit, frame-filling condensed caps, white on black; 1-2 s of black before builds anticipation.
    "impact": dict(font="oswald", weight=700, cap=.45, max_w=.94, track=0.0, color="#ffffff", plate=True, black_before=36,
                   entry="cut", entry_frames=0, hold=72, exit="cut", exit_frames=0, line_height=1.0),
    # Light sans, widely spaced (+.6 → +.45 em while it fades in), long linear fade, hold ≥ 3 s.
    "minimal_wide": dict(font="inter", weight=300, cap=.075, max_w=.8, track=.45, track_from=.6, color="#ffffff", plate=True, black_before=0,
                         entry="fade", entry_frames=54, hold=90, exit="fade", exit_frames=24, line_height=1.25),
    # Small spaced serif caps at deliberately low contrast (grey on black), slow fade both ways.
    "atmospheric": dict(font="lora", weight=400, cap=.03, max_w=.5, track=.2, color="#8a8a8a", plate=True, black_before=0,
                        entry="fade", entry_frames=54, hold=90, exit="fade", exit_frames=36, line_height=1.3),
    # Condensed caps, first word in the accent colour (period drama, comedy).
    "two_tone": dict(font="oswald", weight=600, cap=.14, max_w=.8, track=.05, color="#ffffff", plate=True, black_before=12,
                     entry="cut", entry_frames=0, hold=66, exit="cut", exit_frames=0, line_height=1.1),
    # Over the picture: whip in with motion blur (15 frames, quint-out), leave by scattering characters.
    "integrated": dict(font="archivo", weight=700, cap=.085, max_w=.6, track=.08, color="#ffffff", plate=False, black_before=0,
                       entry="whip", entry_frames=15, hold=45, exit="scatter", exit_frames=15, line_height=1.15),
}


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = LayerId
    start_frame: int = Field(ge=0)
    end_frame: int
    attach_shot: str | None = None
    z: int = Field(default=900, ge=0, le=1000)

    @model_validator(mode="after")
    def span(self):
        if self.end_frame <= self.start_frame + 6:
            raise ValueError("end_frame must be at least 7 frames after start_frame")
        return self


@lru_cache(maxsize=256)
def _probe(font_id, text, weight):
    """Width and vertical metrics at 100 px (FreeType, bundled font): line widths, ascent/descent and the cap band."""
    from .design_library import layout_text
    m = layout_text(font_id, text, 100, 4000, weight)
    h = layout_text(font_id, "H", 100, 4000, weight)
    top, bottom = h["glyph_bounds"][0][1], h["glyph_bounds"][0][3]
    return {"widths": m["line_widths"], "lines": m["lines"], "ascent": m["ascent"], "descent": m["descent"], "cap_top": top, "cap_bottom": bottom,
            "cap_ratio": (bottom - top) / 100}


def _size(t, font_id, weight, text, cap, max_w, track, line_height):
    """Font px for a cap height (share of H), shrunk to fit max_w (share of W) with tracking; box and cap-centre offset."""
    W, H = t["width"], t["height"]
    pr = _probe(font_id, text, weight)
    px = cap * H / pr["cap_ratio"]
    longest = max(range(len(pr["lines"])), key=lambda i: pr["widths"][i])
    chars = max(1, len(pr["lines"][longest]))
    width_at = lambda p: pr["widths"][longest] * p / 100 + track * p * chars  # CSS letter-spacing trails the last glyph too
    if width_at(px) > max_w * W:
        px = max_w * W / (pr["widths"][longest] / 100 + track * chars)
    px = max(12.0, min(900.0, px))
    L = line_height * px
    k = px / 100
    # Within a CSS line box the font's content area (ascent+descent) is centred; the cap band sits inside it.
    cap_mid = (L - (pr["ascent"] + pr["descent"]) * k) / 2 + (pr["cap_top"] + pr["cap_bottom"]) / 2 * k
    n = len(pr["lines"])
    return {"px": round(px), "width": width_at(px), "height": L * n, "cap_mid_first": cap_mid, "line_px": L, "lines": n,
            "cap_px": pr["cap_ratio"] * px}


def _box(t, m, cx, cy, extra_w=0.0):
    """Layer box (frame shares) centring the cap band of the text block on (cx, cy)."""
    W, H = t["width"], t["height"]
    w = min(1.0, (m["width"] + extra_w) / W + .02)
    block_mid = m["cap_mid_first"] + (m["lines"] - 1) * m["line_px"] / 2
    y = cy - block_mid / H
    return {"x": round(cx - w / 2, 4), "y": round(y, 4), "width": round(w, 4), "height": round(m["height"] / H + .01, 4)}


def _plate(lid, attach, z, start, end, color="#000000"):
    """Full-frame solid (black before an impact title, behind word cards, sound-first black)."""
    return {"id": lid, "kind": "shape", "start_frame": start, "end_frame": end, "attach_shot": attach, "z": z,
            "x": 0, "y": 0, "width": 1, "height": 1, "color": color, "data": {"shape": "rectangle", "corner_radius": 0}}


def _words(text):
    return len(text.replace("==", "").replace("**", "").split())


# ---------------------------------------------------------------- title card
class TitleCard(Base):
    recipe: Literal["title_card"]
    text: str = Field(min_length=1, max_length=120)  # explicit \n for stacked titles; ==word== uses the accent colour
    preset: Literal["impact", "minimal_wide", "atmospheric", "two_tone", "integrated"] = "impact"
    hit_frame: int | None = Field(default=None, ge=0)  # the sound hit the title lands on (read_audio_events / music_structure hits)
    black_before: int | None = Field(default=None, ge=0, le=120)
    placement: Literal["center", "left_third", "right_third"] = "center"
    y: float = Field(default=.5, ge=.05, le=.95)  # cap-band centre
    uppercase: bool = True
    font_id: str | None = None
    weight: int | None = Field(default=None, ge=100, le=900)
    color: str | None = Field(default=None, pattern=HEX)
    accent: str = Field(default="#d7263d", pattern=HEX)
    exit: Literal["preset", "cut", "fade", "scatter"] = "preset"
    exit_frames: int | None = Field(default=None, ge=2, le=120)
    cap: float | None = Field(default=None, ge=.01, le=.6)  # override cap height share of H


def title_card(t, q: TitleCard):
    P = dict(PRESETS[q.preset])
    if q.font_id:
        P["font"] = q.font_id
    weight = q.weight or P["weight"]
    text = q.text.upper() if q.uppercase else q.text
    if q.preset == "two_tone" and "==" not in text:
        first, _, rest = text.partition(" ")
        text = f"=={first}== {rest}".strip()
    track_max = max(P["track"], P.get("track_from", P["track"]))
    # Stacked titles need room between lines for Vietnamese marks (dot below on one line, hat/breve/hook above on the
    # next): the line height comes from the glyph ink itself (box metrics missed a fused dot + breve in "MẶT TRĂNG").
    if "\n" in text:
        from .design_library import stack_line_height
        P["line_height"] = round(max(P["line_height"], stack_line_height(P["font"], text.split("\n"), weight, track_max)["line_height"]), 3)
    m = _size(t, P["font"], weight, text, q.cap or P["cap"], P["max_w"], track_max, P["line_height"])
    cx = {"center": .5, "left_third": 1 / 3 - .06, "right_third": 2 / 3 + .06}[q.placement]
    if q.placement != "center" and P["max_w"] > .45:
        m = _size(t, P["font"], weight, text, q.cap or P["cap"], .45, track_max, P["line_height"])
    box = _box(t, m, cx, q.y)
    hit = q.hit_frame if q.hit_frame is not None else q.start_frame
    if not q.start_frame <= hit < q.end_frame - 6:
        raise ValueError("hit_frame must fall inside the title span")
    d = q.end_frame - hit
    black = P["black_before"] if q.black_before is None else q.black_before
    exit_kind = P["exit"] if q.exit == "preset" else q.exit
    exit_frames = q.exit_frames or (P["exit_frames"] or (90 if exit_kind == "fade" and q.preset == "impact" else 15))
    fx, keys = [], {}
    if P["entry"] == "fade":
        fx.append({"name": "fade_in", "start_frame": 0, "end_frame": min(d - 2, P["entry_frames"]), "easing": "linear"})
    elif P["entry"] == "whip":
        keys["x"] = [{"frame": 0, "value": round(.32 * t["width"]), "easing": "linear"},
                     {"frame": min(d - 2, P["entry_frames"]), "value": 0, "easing": "linear", "bezier": QUINT_OUT}]
        fx += [{"name": "fade_in", "start_frame": 0, "end_frame": 4, "easing": "linear"}, {"name": "motion_blur", "start_frame": 0, "end_frame": 1, "params": {"amount": 270}}]
    if "track_from" in P:
        fx.append({"name": "tracking", "start_frame": 0, "end_frame": min(d - 2, 36), "easing": "ease_out",
                   "params": {"amount": P["track"], "from_em": P["track_from"], "center": True}})
    elif P["track"]:
        fx.append({"name": "tracking", "start_frame": 0, "end_frame": 1, "params": {"amount": P["track"], "from_em": P["track"], "center": True}})
    if exit_kind == "fade":
        fx.append({"name": "fade_out", "start_frame": max(1, d - exit_frames), "end_frame": d - 1, "easing": "linear"})
    elif exit_kind == "scatter":
        fx.append({"name": "text_animate", "start_frame": max(1, d - exit_frames), "end_frame": d - 1, "easing": "ease_in",
                   "params": {"unit": "char", "mode": "out", "order": "random", "amount": -40, "x": 90, "rotate": 25, "blur": 6, "opacity": 0,
                              "window": .5, "shutter": 180, "seed": 11}})
    layer = {"id": q.id, "kind": "text", "start_frame": hit, "end_frame": q.end_frame, "attach_shot": q.attach_shot, "z": q.z, **box,
             "text": text, "font_id": P["font"], "font_weight": weight, "line_height": P["line_height"], "font_size": m["px"],
             "color": q.color or P["color"], "data": {"align": "center", "accent": q.accent}, "effects": fx, **({"keyframes": keys} if keys else {})}
    ops = []
    if P["plate"]:
        ops.append({"op": "upsert_layer", "layer": _plate(f"{q.id}-plate", q.attach_shot, q.z - 1, max(q.start_frame, hit - black), q.end_frame)})
    ops.append({"op": "upsert_layer", "layer": layer})
    words = _words(text)
    need = max(45, round((.6 + .3 * words) * FPS))
    hold = d - (exit_frames if exit_kind != "cut" else 0) - (P["entry_frames"] if P["entry"] != "cut" else 0)
    notes = []
    if hold < need:
        notes.append(f"Readable hold is {hold} frames; {words} words need ≥{need} (0.6 s + 0.3 s/word, never under 1.5 s).")
    if q.preset == "impact":
        if hit - q.start_frame < 12 and black >= 12:
            notes.append("Impact titles read after ≥12 frames of black or a hard cut; start the span earlier or set black_before.")
        notes.append("Land the title on a harsh hit: music_structure hits or design_sound braam starting exactly on hit_frame.")
    if q.preset in ("minimal_wide", "atmospheric"):
        notes.append("Let scene sound or the first notes of the score carry this title; no hit.")
    if exit_kind == "fade" and P["entry"] == "fade" and exit_frames > P["entry_frames"] / 2 and q.preset != "impact":
        notes.append("Exits read best at most half the entry length.")
    if m["cap_px"] < .025 * t["height"] and q.preset != "atmospheric":
        notes.append("Cap height under 2.5% of frame height reads as texture, not a title.")
    return {"ops": ops, "notes": notes, "inspect_frames": [hit, hit + min(d - 1, max(P["entry_frames"], 6) + 6)],
            "measurements": {"font_px": m["px"], "cap_px": round(m["cap_px"]), "cap_share_H": round(m["cap_px"] / t["height"], 3),
                             "width_share_W": round(m["width"] / t["width"], 3), "tracking_em": P["track"], "hold_frames": hold, "black_before": black if P["plate"] else 0}}


# ---------------------------------------------------------------- lockups and credits
class Lockup(Base):
    recipe: Literal["type_lockup"]
    mode: Literal["poster", "credit"] = "poster"
    top: str | None = Field(default=None, max_length=80)
    main: str | None = Field(default=None, max_length=60)
    sub: str | None = Field(default=None, max_length=80)
    footer: list[str] = Field(default_factory=list, max_length=4)
    role: str | None = Field(default=None, max_length=60)  # credit: "directed by"
    name: str | None = Field(default=None, max_length=60)  # credit: the surname (last word) is set heavier
    align: Literal["center", "left"] = "center"
    x: float = Field(default=.1, ge=0, le=.9)  # left edge when align=left
    y: float = Field(default=.45, ge=.1, le=.9)  # main line cap centre
    main_font: str = "oswald"
    small_font: str = "inter"
    color: str = Field(default="#ffffff", pattern=HEX)
    accent: str = Field(default="#d7263d", pattern=HEX)
    stagger: int = Field(default=6, ge=0, le=30)
    entry_frames: int = Field(default=18, ge=1, le=60)

    @model_validator(mode="after")
    def need(self):
        if self.mode == "poster" and not self.main:
            raise ValueError("poster lockup needs main")
        if self.mode == "credit" and not (self.role and self.name):
            raise ValueError("credit lockup needs role and name")
        return self


def type_lockup(t, q: Lockup):
    W, H = t["width"], t["height"]
    lines = []  # (suffix, text, font, weight, cap, track, max_w, gap_after, extra)
    if q.mode == "poster":
        if q.top:
            lines.append(("top", q.top.upper(), q.small_font, 700, .023, .15, .8, .06))
        lines.append(("main", q.main.upper(), q.main_font, 700, .18, .02, .64, .045))
        if q.sub:
            lines.append(("sub", q.sub.upper(), q.small_font, 700, .023, .15, .8, 0))
    else:
        nm = q.name.upper().split()
        if not nm:
            raise ValueError("credit name is empty")
        name = " ".join(nm[:-1] + [f"**{nm[-1]}**"]) if len(nm) > 1 else f"**{nm[0]}**"
        lines.append(("role", q.role.upper(), q.small_font, 500, .025, .15, .7, .03))
        lines.append(("name", name, q.main_font, 400, .062, .04, .8, 0))
    ops, meas, y = [], [], None
    sized = [(s, txt, f, wgt, _size(t, f, wgt, txt, cap, mw, tr, 1.25), tr, gap) for s, txt, f, wgt, cap, tr, mw, gap in lines]
    main_i = next(i for i, l in enumerate(sized) if l[0] in ("main", "name"))
    # Stack around the main line: caps of neighbours sit gap*H apart from its cap band.
    mids = [0.0] * len(sized)
    mids[main_i] = q.y
    for i in range(main_i - 1, -1, -1):
        mids[i] = mids[i + 1] - (sized[i + 1][4]["cap_px"] / 2 + sized[i][4]["cap_px"] / 2) / H - sized[i][6]
    for i in range(main_i + 1, len(sized)):
        mids[i] = mids[i - 1] + (sized[i - 1][4]["cap_px"] / 2 + sized[i][4]["cap_px"] / 2) / H + sized[i - 1][6]
    for k, ((suffix, txt, font, wgt, m, tr, _), cy) in enumerate(zip(sized, mids)):
        if q.align == "center":
            box = _box(t, m, .5, cy)
        else:
            b = _box(t, m, .5, cy)
            box = {**b, "x": round(q.x, 4)}
        fx = [{"name": "fade_in", "start_frame": k * q.stagger, "end_frame": k * q.stagger + q.entry_frames, "easing": "ease_out"},
              {"name": "rise", "start_frame": k * q.stagger, "end_frame": k * q.stagger + q.entry_frames, "params": {"amount": 12}, "bezier": QUINT_OUT}]
        if tr:
            fx.append({"name": "tracking", "start_frame": 0, "end_frame": 1, "params": {"amount": tr, "from_em": tr, "center": q.align == "center"}})
        d = q.end_frame - q.start_frame
        if d > 60:
            fx.append({"name": "fade_out", "start_frame": d - 10, "end_frame": d - 1, "easing": "ease_in"})
        ops.append({"op": "upsert_layer", "layer": {"id": f"{q.id}-{suffix}", "kind": "text", "start_frame": q.start_frame, "end_frame": q.end_frame,
                                                    "attach_shot": q.attach_shot, "z": q.z, **box, "text": txt, "font_id": font, "font_weight": wgt,
                                                    "line_height": 1.25, "font_size": m["px"], "color": q.color,
                                                    "data": {"align": q.align, "accent": q.accent, "strong_weight": 800}, "effects": fx}})
        meas.append({"line": suffix, "font_px": m["px"], "cap_share_H": round(m["cap_px"] / H, 4), "width_share_W": round(m["width"] / W, 3)})
    cy, prev_cap = .885, None
    for j, txt in enumerate(q.footer):
        cap = .02 if j == 0 else .0125
        m = _size(t, q.small_font, 500, txt.upper(), cap, .8, .1, 1.25)
        if prev_cap is not None:  # stack by cap heights with a gap of ~1.1 caps (accents above Vietnamese capitals need room)
            cy += (prev_cap + m["cap_px"]) / 2 / H + 1.1 * m["cap_px"] / H
        prev_cap = m["cap_px"]
        box = _box(t, m, .5, cy) if q.align == "center" else {**_box(t, m, .5, cy), "x": round(q.x, 4)}
        ops.append({"op": "upsert_layer", "layer": {"id": f"{q.id}-footer{j}", "kind": "text", "start_frame": q.start_frame, "end_frame": q.end_frame,
                                                    "attach_shot": q.attach_shot, "z": q.z, **box, "text": txt.upper(), "font_id": q.small_font, "font_weight": 500,
                                                    "line_height": 1.25, "font_size": m["px"], "color": q.color, "data": {"align": q.align},
                                                    "effects": [{"name": "fade_in", "start_frame": len(sized) * q.stagger, "end_frame": len(sized) * q.stagger + q.entry_frames},
                                                                {"name": "tracking", "start_frame": 0, "end_frame": 1, "params": {"amount": .1, "from_em": .1, "center": q.align == "center"}}]}})
    main_cap = sized[main_i][4]["cap_px"]
    others = [l[4]["cap_px"] for i, l in enumerate(sized) if i != main_i]
    notes = []
    if q.mode == "poster" and others and main_cap / max(others) < 2.5:
        notes.append("Main-to-secondary size ratio under 2.5 weakens the hierarchy.")
    if any(m_["cap_share_H"] < .012 for m_ in meas):
        notes.append("Lines under 1.2% of frame height read as texture only.")
    return {"ops": ops, "notes": notes, "inspect_frames": [q.start_frame + q.entry_frames + len(sized) * q.stagger + 4], "measurements": {"lines": meas}}


# ---------------------------------------------------------------- trailer word cards
class WordCards(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["word_cards"]
    id: str = LayerId
    words: list[str] = Field(min_length=1, max_length=16)
    hit_frames: list[int] = Field(min_length=1, max_length=16)  # one hit per word (music_structure hits / snap targets)
    card_frames: int = Field(default=12, ge=6, le=24)  # measured 9-18 frames (0.3-0.6 s)
    lead_frames: int = Field(default=1, ge=0, le=3)  # cards cut in ~1 frame before the hit
    flash_frames: int = Field(default=0, ge=0, le=3)  # picture flashes through the middle of each card
    font_id: str = "oswald"
    weight: int = Field(default=700, ge=100, le=900)
    cap: float = Field(default=.16, ge=.03, le=.5)
    color: str = Field(default="#ffffff", pattern=HEX)
    background: str = Field(default="#000000", pattern=HEX)
    attach_shot: str | None = None
    z: int = Field(default=900, ge=1, le=1000)

    @model_validator(mode="after")
    def pair(self):
        if len(self.words) != len(self.hit_frames):
            raise ValueError("one hit frame per word")
        if any(b <= a for a, b in zip(self.hit_frames, self.hit_frames[1:])):
            raise ValueError("hit_frames must increase")
        return self


def word_cards(t, q: WordCards):
    ops, notes = [], []
    for i, (w, h) in enumerate(zip(q.words, q.hit_frames)):
        s = max(0, h - q.lead_frames)
        nxt = q.hit_frames[i + 1] - q.lead_frames if i + 1 < len(q.hit_frames) else None
        e = s + q.card_frames if nxt is None else min(s + q.card_frames, nxt)
        if e - s < 6:
            notes.append(f"Card {i} ({w}) is {e - s} frames; hits closer than 6 frames read as flicker.")
            e = s + 6
        txt = w.upper()
        m = _size(t, q.font_id, q.weight, txt, q.cap, .9, .02, 1.05)
        keys = {}
        if q.flash_frames and e - s >= q.flash_frames + 6:
            mid = (e - s) // 2
            keys["opacity"] = [{"frame": 0, "value": 1}, {"frame": mid - 1, "value": 1, "easing": "stepped"},
                               {"frame": mid, "value": 0, "easing": "stepped"},
                               *([{"frame": mid + q.flash_frames - 1, "value": 0, "easing": "stepped"}] if q.flash_frames > 1 else []),
                               {"frame": mid + q.flash_frames, "value": 1, "easing": "stepped"}]
        card = {"id": f"{q.id}-{i}", "start_frame": s, "end_frame": e, "attach_shot": q.attach_shot}
        plate = {**_plate(f"{q.id}-{i}-plate", q.attach_shot, q.z - 1, s, e, q.background), **({"keyframes": keys} if keys else {})}
        ops.append({"op": "upsert_layer", "layer": plate})
        ops.append({"op": "upsert_layer", "layer": {**card, "kind": "text", "z": q.z, **_box(t, m, .5, .5), "text": txt, "font_id": q.font_id,
                                                    "font_weight": q.weight, "line_height": 1.05, "font_size": m["px"], "color": q.color,
                                                    "data": {"align": "center"}, "effects": [{"name": "tracking", "start_frame": 0, "end_frame": 1, "params": {"amount": .02, "from_em": .02, "center": True}}],
                                                    **({"keyframes": keys} if keys else {})}})
    return {"ops": ops, "notes": notes, "inspect_frames": [max(0, q.hit_frames[0] - q.lead_frames) + 2],
            "measurements": {"cards": len(q.words), "card_frames": q.card_frames, "lead_frames": q.lead_frames}}


# ---------------------------------------------------------------- sound-first reveal
class SoundFirst(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["sound_first"]
    id: str = LayerId
    black_from: int = Field(ge=0)  # picture goes to black here (the sound carries the scene)
    hit_frame: int = Field(ge=0)  # the hit lands on black
    picture_delay: int = Field(default=51, ge=0, le=180)  # picture returns this many frames after the hit (measured ~1.7 s)
    fade_up: int = Field(default=0, ge=0, le=60)  # 0 = hard cut back to picture; 1 is treated as 2 (a fade needs two frames)
    attach_shot: str | None = None
    z: int = Field(default=890, ge=1, le=1000)

    @model_validator(mode="after")
    def order(self):
        if not self.black_from < self.hit_frame:
            raise ValueError("black_from must precede hit_frame")
        return self


def sound_first(t, q: SoundFirst):
    if q.fade_up == 1:
        q = q.model_copy(update={"fade_up": 2})
    end = q.hit_frame + q.picture_delay + max(1, q.fade_up)
    layer = _plate(q.id, q.attach_shot, q.z, q.black_from, end)
    if q.fade_up:
        layer["effects"] = [{"name": "fade_out", "start_frame": end - q.black_from - q.fade_up, "end_frame": end - q.black_from - 1, "easing": "ease_in"}]
    notes = ["Before the hit, let the level fall to near silence (-40..-50 dB) for ~1.7 s, or end a suck_out exactly on hit_frame; "
             "the hit should rise ≥30 dB over that silence. Check with read_audio_events / music_structure quiet gaps."]
    return {"ops": [{"op": "upsert_layer", "layer": layer}], "notes": notes, "inspect_frames": [q.hit_frame, q.hit_frame + q.picture_delay + 2],
            "measurements": {"black_frames": end - q.black_from, "picture_after_hit": q.picture_delay}}


RECIPES = {"title_card": (TitleCard, title_card), "type_lockup": (Lockup, type_lockup), "word_cards": (WordCards, word_cards), "sound_first": (SoundFirst, sound_first)}


def catalog():
    return {"recipes": {k: {"fields": sorted(m.model_fields), "doc": (f.__doc__ or m.__doc__ or "").strip()} for k, (m, f) in RECIPES.items()},
            "presets": {k: {kk: v for kk, v in p.items()} for k, p in PRESETS.items()},
            "rules": ["Pick impact or integration first: impact = hard cut on a harsh hit after black; integration = linear fade with the picture or scene sound.",
                      "Readable hold ≥ 0.6 s + 0.3 s per word (never under 1.5 s); exits at most half the entry.",
                      "Titles are capitals; wide-spaced caps +0.35..+0.7 em, frame-filling titles ~0 em; centre corrected for trailing letter-spacing.",
                      "Hierarchy: poster main word ≈ 7.5× the top line; credit role line 0.4× the name, surname heavier.",
                      "Do not overpower strong footage: shrink and quieten the type; integrated type sits in the empty space opposite the subject."]}


def compose(pid, base_revision, request, dry_run=False):
    name = (request or {}).get("recipe")
    if name not in RECIPES:
        raise ValueError(f"recipe must be one of {sorted(RECIPES)}")
    model, fn = RECIPES[name]
    q = model.model_validate(request)
    t = _timeline(pid, base_revision)
    r = fn(t, q)
    r["revision"] = _apply(pid, base_revision, r["ops"], dry_run)
    r["recipe"], r["dry_run"] = name, dry_run
    if dry_run:
        from .review import audit_timeline
        future = preview_ops(t, r["ops"])
        touched = {op["layer"]["id"] for op in r["ops"] if op["op"] == "upsert_layer"}
        r["audit"] = [f for f in audit_timeline(pid, future)["findings"] if touched & set(_ids(f["where"]))]
    else:
        r["layers"] = [op["layer"]["id"] for op in r.pop("ops")]
    return r
