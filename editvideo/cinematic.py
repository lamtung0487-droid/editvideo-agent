"""Cinematic technique atlas and executable recipes.

The atlas is thinking material for the calling AI: what each technique does for the viewer, when it fits, what it needs,
parameters that have held up in real renders, how it fails and how to verify it. Recipes compute the geometry the AI
would otherwise guess (where free space is above a subject, how far a camera may travel before a photo plane's border
shows, when a traveller reaches each milestone) and compile it to ordinary timeline layers. No aesthetic score.
"""
import math
import subprocess
from typing import Literal
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store, agent

FPS = 30
HEX = r"^#[0-9a-fA-F]{6}$"

ATLAS = {
    "globe_dive": {
        "purpose": "Place the story on Earth and travel continuously from global to local; the dive motivates the cut into ground footage.",
        "use_when": "Geography is part of the meaning: journeys, several locations, where something happened, scale.",
        "avoid_when": "Place is incidental; a globe would only decorate. Very short videos where 4–7 s of intro is too costly.",
        "needs": ["library texture tagged earth (Blue Marble)", "optional clouds texture", "geo_outline for a glowing border"],
        "tool": "compose_globe",
        "params": "sun_lat/sun_lon a few degrees west of the destination; final altitude ≥1 radius with a 5400 px texture; "
                  "outline grows first, markers appear after it, arcs grow after markers; bloom strength≈.4 threshold≈.86.",
        "failure_modes": ["destination on the night side (no sun_lat/lon)", "blob markers / white haze from strong bloom",
                          "soft ground when diving too low (audit: texture_magnified)", "judder from eased dense keys (audit: camera_oscillation)"],
        "verify": "audit_timeline → snapshot first/middle/last frame and one frame inside each arc's growth → motion_audit on the render."},
    "map_journey": {
        "purpose": "Keep the viewer oriented between locations: a small map draws the leg being travelled in every shot.",
        "use_when": "Two or more places in sequence; travel, logistics, history across regions.",
        "avoid_when": "One location; or the map would cover the subject of the shot.",
        "needs": ["geo_map(country) from Natural Earth", "city coordinates"],
        "recipe": "map_journey",
        "params": "Card in a corner the footage does not need (check the shot); previous legs stay drawn, the current leg draws over ~40 frames with a follower.",
        "failure_modes": ["card covers the subject/action", "labels too small to read on phones", "leg drawn faster than the eye can follow"],
        "verify": "snapshot at the start and end of each leg; review_frames if it shares space with text."},
    "trajectory_3d": {
        "purpose": "Explain a path through space or a process as a journey: the camera chases the traveller, milestones appear on arrival, then the whole route is revealed.",
        "use_when": "Missions, routes, supply chains, any sequence whose shape matters.",
        "avoid_when": "The order of steps matters but their geometry does not (use a flow diagram).",
        "needs": ["path points (3D or projected 2D)", "optional textured bodies (Earth, Moon)"],
        "recipe": "trajectory_3d",
        "params": "Tube radius ≈.0075 and emissive ≈1.5 with bloom .35/.88 stay crisp near the camera; chase offset fixed in world space; "
                  "label carriers hold ~2.5 s then hide so the final overview is not crowded.",
        "failure_modes": ["thick glowing band when the camera is close", "camera whips at sharp turns (path-relative offset)", "labels collide with titles"],
        "verify": "audit_timeline (label_collision, camera_stops) → snapshot chase, turn, overview."},
    "photo_3d": {
        "purpose": "Give a still photograph time and depth: a slow move reveals foreground/background separation.",
        "use_when": "Strong still images (archive, landscapes) where footage is missing; quiet, contemplative beats.",
        "avoid_when": "Thin structures in front of far background (railings, hair, wires) dominate — relative depth smears them.",
        "needs": ["image asset", "estimate_depth result (near = white) imported as image"],
        "recipe": "photo_3d",
        "params": "Camera faces the plane (truck/crane/push, not orbit); travel ≤ ~30% of the visible width; relief ≈ .12–.16 of the plane height.",
        "failure_modes": ["plane border visible (audit: plane_edge_visible)", "stretched edges when viewed obliquely (audit: displacement_angle)", "move too fast for a still"],
        "verify": "audit_timeline → snapshot first/last frame and the corners."},
    "text_behind_subject": {
        "purpose": "Make a title part of the scene: the subject passes in front of a large word naming the place or person.",
        "use_when": "A clear subject in the lower/middle frame with free background above it; openers, place names.",
        "avoid_when": "The subject fills the frame top to bottom, moves a lot vertically, or the camera moves (the foreground must match the plate).",
        "needs": ["track_subject (SAM2)", "edit_subject foreground with alpha for the same source window", "shot with motion hold"],
        "recipe": "text_behind_subject",
        "params": "Text bottom overlaps the subject's top by ~25–35% of the text height; 60–90% of the glyphs stay visible.",
        "failure_modes": ["text centred on the subject is mostly hidden", "foreground crop differs from the plate (shot push/focus)", "low contrast against bright sky/walls"],
        "verify": "review_frames on 2–3 frames: visible_fraction and contrast_p10; watch mask edges at full speed."},
    "doc_chapter": {
        "purpose": "Tell the viewer where they are in a long story: part, title, years, one line of context and a timeline strip that grows chapter by chapter.",
        "use_when": "Historical or multi-part documentaries; any film that moves through years or phases.",
        "avoid_when": "Short films with one moment; every few seconds (a chapter needs material behind it).",
        "needs": ["design typography roles label, headline, caption"],
        "recipe": "doc_chapter",
        "params": "hold 3-5 s (about 1 s plus 0.3 s per word); context <= 20 words; same position and look for every chapter; done = earlier spans.",
        "failure_modes": ["context too long to read", "a chapter card with no new material after it", "years that contradict the footage"],
        "verify": "snapshot when the context has revealed; check the strip's span against the chapter's years."},
    "data_story": {
        "purpose": "Put a figure on screen with what it counts and who counted it, so the narration can say one number and leave the rest to the picture.",
        "use_when": "A statistic matters (a budget share, a death toll, a poll); two sources disagree (compare=True shows both, tagged 'two sources').",
        "avoid_when": "The narration already says the number; more than three figures (split them over two cards).",
        "needs": ["design typography roles label, display, data, caption, source", "a named source for every figure"],
        "recipe": "data_story",
        "params": "1-3 figures; each counts up over 36 frames, 14 frames apart; the hold covers the count plus one reading of every text (3.5 words/s).",
        "failure_modes": ["a figure without its source", "a contested number shown as fact", "a unit too long for its column"],
        "verify": "snapshot once every figure has counted up; read each label and source at phone size."},
    "document_highlight": {
        "purpose": "Let a primary document speak: its own words on a paper panel, the sentence that matters underlined as the narration reaches it.",
        "use_when": "A memo, letter, treaty or speech text is the evidence (Roosevelt 1944, Nixon to Thiệu 1972, Geneva 1954).",
        "avoid_when": "The passage is paraphrase rather than the document's words; more than about 60 words.",
        "needs": ["design typography roles label, quote, source", "the passage and its archive or publication"],
        "recipe": "document_highlight",
        "params": "highlight = exact words of the passage; the underline draws from highlight_at over ~1 s; the panel holds the reading time + 1 s.",
        "failure_modes": ["underline under the wrong words (layout differs from the measure)", "a translation not credited", "passage too long for the panel"],
        "verify": "snapshot after the underline; it must sit under the highlighted words only."},
    "night_log": {
        "purpose": "Count a campaign night by night in a corner while its pictures play: the night on screen, its number, the nights before.",
        "use_when": "A sequence covers several days or nights of one operation with a sourced count per night (sorties, shells, kilometres).",
        "avoid_when": "No per-night source; the pictures already carry captions in that corner; nights pass faster than about 1.3 s each.",
        "needs": ["typography roles label, caption, source", "a count per night and its source", "the local frame each night starts"],
        "recipe": "night_log",
        "params": "one bar a night, gap nights as a dash with a note; the last night writes the sum when total is set.",
        "failure_modes": ["nights flicking past unread", "a contested count shown without its source"],
        "verify": "snapshot two nights; the line must read at phone size and clear the shot's own captions."},
    "credibility_gap": {
        "purpose": "Set what was announced beside what the record later showed, without the edit drawing the conclusion.",
        "use_when": "An official claim is contradicted by a declassified or later document (Tonkin 1964 against the NSA history of 2005).",
        "avoid_when": "The record is disputed or the claim is paraphrased loosely; one side has no source.",
        "needs": ["footage of the claim (its date and place)", "the record's words and source", "typography roles label, caption, quote, source"],
        "recipe": "credibility_gap",
        "params": "the claim alone until split_at (read once), then the record wipes in on the right half and is read beside it.",
        "failure_modes": ["the record arriving before the claim is read", "a conclusion written into the record text"],
        "verify": "snapshot before and after the split."},
    "history_map": {
        "purpose": "Make a geographic change understood: a partition line, offensives, a supply trail, cities taken, drawn step by step on a full-frame map.",
        "use_when": "History or news where where-and-when is the point (wars, borders, migrations, campaigns).",
        "avoid_when": "Geography is incidental; more than 4-5 steps in under 10 s (the eye cannot follow).",
        "needs": ["Natural Earth country and neighbours (geo)", "city coordinates", "a date card before or on the map"],
        "recipe": "history_map",
        "params": "one change per step, 20-40 frames to draw, 1-2 s between steps; labels <= 4 words; the map holds >= 2 s after the last step.",
        "failure_modes": ["labels colliding near the coast", "too many steps at once", "arrows without a date (the viewer cannot place them in time)"],
        "verify": "snapshot after each step; read every label at full size."},
    "kinetic_title": {
        "purpose": "Give a short statement rhythm and weight on entry.",
        "use_when": "Titles, place names, one key phrase per beat.",
        "avoid_when": "Long sentences (reading load) or every line of the video (fatigue).",
        "needs": ["design typography roles"],
        "recipe": "kinetic_title",
        "params": "mask_reveal for statements, char_spring for short punchy words, tracking_in for calm openers; measured with layout_text.",
        "failure_modes": ["unexpected wrap / overflow", "too many words for the time on screen (audit: reading_load)"],
        "verify": "snapshot mid-entrance and settled; review_frames for contrast."},
    "film_finish": {
        "purpose": "Unify footage from different sources with grain; mark big transitions with light.",
        "use_when": "Mixed sources, documentary/travel tone.",
        "avoid_when": "Clean product/UI/data explainers where texture reads as dirt.",
        "needs": [],
        "recipe": "film_finish",
        "params": "grain intensity .15–.25 overlay; light leaks 1.5–2.5 s centred on flash/burn/zoom transitions, ≤30% of runtime.",
        "failure_modes": ["washed colours from leaks everywhere (audit: light_leak_coverage)"],
        "verify": "snapshot one frame inside each leak; compare with the clean frame."},
    "live_transitions": {
        "purpose": "Move between shots along a direction the content motivates; graphics travel with their shot (attach_shot).",
        "use_when": "Changing place/time along a journey; a whip on fast action; zoom_through into detail; flash for space→ground; burn to close.",
        "avoid_when": "Every cut — a straight cut is the default; identical transitions in a row (audit: transition_repeat).",
        "needs": ["source handles for mode live (validated)"],
        "tool": "patch_timeline update_shot transition + attach_shot on layers",
        "params": "10–18 frames; live keeps the outgoing shot moving.",
        "failure_modes": ["full-frame layers hide the transition unless attached to the shot", "transition longer than 40% of a shot"],
        "verify": "snapshot 3 frames inside the transition."},
    "speed_ramp": {
        "purpose": "Compress waiting and stretch the decisive moment (liftoff, a jump, a pour).",
        "use_when": "Footage with one peak action.",
        "avoid_when": "Evidence where real timing matters, unless labelled.",
        "needs": ["source footage"],
        "tool": "retime_footage (flow interpolation, speed_keys, motion blur)",
        "params": "Find the action frame by dense inspection first; ramp over 8–15 frames.",
        "failure_modes": ["ramp misses the action", "flow warping on thin/fast objects", "25/24 fps sources stutter in 30p (motion_audit: duplicate_frames)"],
        "verify": "inspect_window around the peak; motion_audit for duplicates."},
    "tracked_callout": {
        "purpose": "Point at a moving detail and name it.",
        "use_when": "Explaining a part of an object/scene in motion.",
        "avoid_when": "Static scenes (use a plain label).",
        "needs": ["track_region or track_subject"],
        "tool": "compose_edit recipe tracked_callout",
        "params": "Label away from the subject's direction of travel.",
        "failure_modes": ["track drift", "label crossing the subject"],
        "verify": "snapshot start/middle/end of the track."},
    "hero_object_3d": {
        "purpose": "Show an object the footage cannot (a spacecraft, a product) with real light and perspective.",
        "use_when": "A glTF model exists in the library or the object is simple geometry.",
        "avoid_when": "The model would be mistaken for evidence; label it as a model.",
        "needs": ["model asset (.glb)"],
        "tool": "compose_scene3d / patch scene3d layer",
        "params": "environment studio for metals, slow turn, one key light.",
        "failure_modes": ["model fits poorly (check size[0])", "animation clip names"],
        "verify": "snapshot two angles."},
    "match_cut": {
        "purpose": "Join two shots through a shared shape, motion or position so the change feels inevitable.",
        "use_when": "Two sources share a circle/horizon/direction of movement.",
        "avoid_when": "The match would be accidental or confusing.",
        "needs": ["inspect_window on both shots"],
        "tool": "move_boundary / split_shot; layer positions aligned to the matched shape",
        "params": "Align the shared element to the same canvas position on both sides of the cut.",
        "failure_modes": ["shape positions differ by more than ~5% of the frame"],
        "verify": "snapshot last frame of A and first frame of B side by side."},
}

PRINCIPLES = [
    "Pick ONE hero technique that carries the core idea of the film; add at most two or three supporting techniques.",
    "Every technique must orient, explain or bind information to the picture; if it only decorates, cut it.",
    "Prefer continuous space (dives, chases, attached graphics) over hard visual resets when the story is a journey.",
    "Let the footage interact with graphics (text behind subject, tracked labels, depth) instead of stacking graphics on top.",
    "Vary energy: measure shot motion with motion_audit; a calm stretch longer than ~3 s needs a reason.",
    "Decide the verification frames while designing: transition middles, arrival moments, closest camera approach.",
    "Credits come from records (project_credits), never from memory.",
]


def catalog(query="", project_id=None):
    """Technique atlas filtered by query, with readiness checks against the library and the project."""
    from . import resources
    words = [w for w in query.casefold().split() if w]
    lib = resources._load()  # every record with tags (library() returns compact rows for the model)
    have = lambda *tags: any(any(t in (e.get("tags", "") + " " + e["title"]).casefold() for t in tags) for e in lib)
    assets = store.assets(project_id) if project_id else []
    ready = {
        "globe_dive": have("earth"), "map_journey": any(e["kind"] == "geo" for e in lib), "trajectory_3d": True,
        "photo_3d": any(a.get("kind") == "image" for a in assets) if project_id else None,
        "text_behind_subject": any((a.get("provenance") or {}).get("operation") == "mask_edit" for a in assets) if project_id else None,
        "hero_object_3d": any(e["kind"] == "model" for e in lib) or any(a.get("kind") == "model" for a in assets),
    }
    out = []
    for key, v in ATLAS.items():
        hay = (key + " " + " ".join(str(x) for x in v.values())).casefold()
        if words and not any(w in hay for w in words):
            continue
        out.append({"id": key, **v, "ready": ready.get(key, True)})
    if not (len(out) == 1 or any(w == o["id"] for w in words for o in out)):
        # Listing: what each technique is for, when to use it, which tool, readiness; the full card (params, failure
        # modes, avoid_when, needs) comes back for an exact id query.
        out = [{k: o[k] for k in ("id", "purpose", "use_when", "tool", "ready") if k in o} for o in out]
    elif len(out) > 1:
        out = [o for o in out if o["id"] in words] or out
    return {"principles": PRINCIPLES, "techniques": out,
            "ready_meaning": "true: required resources exist; false: missing (see needs); null: depends on project assets not checked.",
            "next": "Write a treatment: for each beat, what the viewer must understand → technique → verification frames. "
                    "Then compose_cinematic(recipe) or the named tool, audit_timeline, snapshot/review_frames, render, motion_audit."}


# ---------------------------------------------------------------- shared helpers
def _timeline(pid, base_revision):
    p = agent.read(pid)
    t = p.get("timeline")
    if not t or p["revision"] != base_revision:
        raise ValueError("Read the current project revision (locked plan) before composing")
    return t


def _shot(t, sid):
    s = next((s for s in t["shots"] if s["id"] == sid), None)
    if not s:
        raise ValueError(f"Shot {sid} not found")
    return s


def _typo(t, role):
    ty = ((t.get("design") or {}).get("typography") or {}).get(role)
    if not ty:
        raise ValueError(f"Design has no typography role {role}; apply_design first")
    return ty


def _measure(t, role, text, width_px):
    from .design_library import layout_text
    ty = _typo(t, role)
    px = ty["size"] * min(t["width"], t["height"]) / 1080
    m = layout_text(ty["font_id"], text, max(12, min(300, px)), max(100, min(4000, width_px)), ty.get("weight", 400))
    line_px = px * ty.get("line_height", 1.2)
    widths = m.get("line_widths") or [0]
    glyph = m.get("glyph_bounds") or [[0, 0, widths[0], line_px]]
    longest = m["lines"][widths.index(max(widths))] if m.get("lines") else text
    width = max(widths) + ty.get("tracking", 0) * px * max(0, len(longest) - 1)  # CSS letter-spacing in em
    return {"px": px, "lines": m["lines"], "width": width, "line_px": line_px,
            "height": line_px * len(m["lines"]), "glyph_top": glyph[0][1], "glyph_bottom": (len(m["lines"]) - 1) * line_px + glyph[-1][3],
            "overlong": m.get("overlong_tokens"), "missing": m.get("missing_glyphs")}


def _apply(pid, base_revision, ops, dry_run):
    if dry_run:
        return None
    if len(ops) <= 90:
        return agent.patch(pid, base_revision, ops)["revision"]
    # a patch takes at most 100 operations and a long montage writes several hundred layers: apply them to a copy and
    # replace the timeline in ONE validated patch, so a bad layer leaves nothing half-built
    t = agent.read(pid)
    if t["revision"] != base_revision:
        raise ValueError(f"revision moved ({t['revision']} != {base_revision}): reread and compose again")
    if any(op["op"] not in ("upsert_layer", "delete_layer", "set_design", "update_shot") for op in ops):
        raise ValueError("a recipe of more than 90 operations may only upsert/delete layers, set the design or update shots")
    shot_fields = {"asset_id", "source_start", "text", "role", "motion", "fit", "focus_x", "focus_y", "reason", "effects", "keyframes", "playback_rate", "transition"}
    if any(op["op"] == "update_shot" and set(op["changes"]) - shot_fields for op in ops):  # the same fields agent.patch allows
        raise ValueError("update_shot supports visual fields; use move_boundary/split_shot for timing")
    return agent.patch(pid, base_revision, [{"op": "replace_timeline", "timeline": preview_ops(t["timeline"], ops)}])["revision"]


# ---------------------------------------------------------------- kinetic title
class KineticTitle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["kinetic_title"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    text: str = Field(min_length=1, max_length=300)
    start_frame: int = Field(ge=0)
    end_frame: int
    attach_shot: str | None = None
    role: Literal["display", "headline", "title", "body", "label", "data", "quote"] = "headline"
    x: float = Field(default=.08, ge=0, le=1)
    y: float = Field(default=.12, ge=0, le=1)
    width: float = Field(default=.84, gt=0, le=1)
    style: Literal["reveal", "spring", "tracking", "type", "word"] = "reveal"
    color: str = Field(default="#ffffff", pattern=HEX)
    shadow: bool = True
    exit_fade: bool = False
    max_lines: int = Field(default=3, ge=1, le=6)
    z: int = Field(default=60, ge=0, le=1000)


def kinetic_title(t, q: KineticTitle):
    W, H = t["width"], t["height"]
    m = _measure(t, q.role, q.text, q.width * W)
    notes = []
    if len(m["lines"]) > q.max_lines:
        notes.append(f"Text wraps to {len(m['lines'])} lines at the {q.role} size (max {q.max_lines}); shorten it or use a smaller role.")
    if m["overlong"]:
        notes.append(f"Words wider than the box: {m['overlong']}")
    d = q.end_frame - q.start_frame
    entry = max(1, min(26, d - 1))
    fx = {"reveal": [{"name": "mask_reveal", "end_frame": entry}],
          "spring": [{"name": "char_spring", "end_frame": entry, "params": {"amount": .6}}],
          "tracking": [{"name": "fade_in", "end_frame": entry}, {"name": "tracking_in", "end_frame": entry + 10, "params": {"amount": 40}}],
          "type": [{"name": "typewriter", "end_frame": max(entry, min(d - 1, len(q.text) * 2))}],
          "word": [{"name": "word_reveal", "end_frame": max(entry, min(d - 1, len(q.text.split()) * 5))}]}[q.style]
    if q.shadow:
        fx.append({"name": "shadow", "end_frame": 1, "params": {"amount": 28}})
    if q.exit_fade and d > 30:
        fx.append({"name": "fade_out", "start_frame": d - 12, "end_frame": d - 1})
    h = min(.9, m["height"] / H + .01)
    if q.y + h > .95:
        notes.append("Box runs past the bottom of the frame.")
    words = len(q.text.split())
    if words >= 4 and words / max(.3, d / FPS - .5) > 3.2:
        notes.append(f"{words} words in {d / FPS:.1f}s exceeds ~3 words/s reading pace.")
    layer = {"id": q.id, "kind": "text", "text": "\n".join(m["lines"]) if len(m["lines"]) > 1 else q.text, "start_frame": q.start_frame,
             "end_frame": q.end_frame, "x": q.x, "y": q.y, "width": q.width, "height": round(h, 4), "z": q.z, "attach_shot": q.attach_shot,
             "typography_role": q.role, "color": q.color, "effects": fx}
    return {"ops": [{"op": "upsert_layer", "layer": layer}], "notes": notes, "inspect_frames": [q.start_frame + entry // 2, q.start_frame + entry + 4],
            "measurements": {"font_px": round(m["px"], 1), "lines": m["lines"], "text_width_px": round(m["width"]), "box_height": round(h, 4)}}


# ---------------------------------------------------------------- text behind subject
class TextBehindSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["text_behind_subject"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    shot_id: str
    text: str = Field(min_length=1, max_length=40)
    foreground_asset: str
    role: Literal["display", "headline", "title", "data"] = "data"
    color: str = Field(default="#ffffff", pattern=HEX)
    target_covered: float = Field(default=.25, ge=0, le=.6)  # median share of glyph pixels the subject should cover
    margin_top: float = Field(default=.05, ge=0, le=.4)
    align: Literal["center", "left"] = "center"
    samples: int = Field(default=8, ge=2, le=24)
    effect: Literal["reveal", "spring", "none"] = "reveal"
    z_text: int = Field(default=30, ge=0, le=999)


def _alpha_frames(path, times, width):
    rows = []
    for ts in times:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-ss", f"{ts:.3f}", "-i", str(path), "-frames:v", "1",
                              "-vf", f"alphaextract,scale={width}:-2,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        if not raw:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{ts:.3f}", "-i", str(path), "-frames:v", "1",
                                  "-vf", f"alphaextract,scale={width}:-2,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        if raw:
            rows.append(np.frombuffer(raw, np.uint8))
    if not rows:
        raise ValueError("Could not read an alpha channel from the foreground asset (expected VP9/WebM with alpha from edit_subject)")
    return rows


def text_behind_subject(t, pid, q: TextBehindSubject):
    W, H = t["width"], t["height"]
    s = _shot(t, q.shot_id)
    if abs(s.get("focus_x", .5) - .5) > 1e-3 or abs(s.get("focus_y", .5) - .5) > 1e-3:
        raise ValueError("Shot focus must be 0.5/0.5: the foreground layer is drawn with a centred cover crop")
    if s.get("fit", "cover") != "cover":
        raise ValueError("Shot fit must be cover so plate and foreground share the crop")
    fg = store.find_asset(pid, q.foreground_asset)
    if fg.get("kind") != "video":
        raise ValueError("foreground_asset must be the alpha video from edit_subject (operation foreground)")
    sw, sh = fg["width"], fg["height"]
    shot_len = (s["end_frame"] - s["start_frame"]) / FPS
    span = min(shot_len, fg.get("duration") or shot_len)
    times = [span * (i + .5) / q.samples for i in range(q.samples)]
    aw = 240
    ah = int(round(aw * sh / sw / 2) * 2)
    frames = [f.reshape(-1, aw)[:ah] > 128 for f in _alpha_frames(fg["path"], times, aw)]
    scale = max(W / sw, H / sh)
    dw, dh = sw * scale, sh * scale
    ox, oy = (W - dw) / 2, (H - dh) / 2
    from .design_library import glyph_mask
    ty = _typo(t, q.role)
    m = _measure(t, q.role, q.text, W * .94)
    tw = m["width"]
    x0 = (W - tw) / 2 if q.align == "center" else W * .06
    # Real glyph mask at canvas scale (downsampled by k) against each sampled alpha frame mapped into canvas space.
    k = 4
    gm, _ = glyph_mask(ty["font_id"], m["lines"], m["px"], ty.get("weight", 400), ty.get("tracking", 0), ty.get("line_height", 1.2))
    gm = gm[::k, ::k]
    gh, gw = gm.shape
    cw, chh = W // k, H // k
    xs = (np.arange(cw) * k - ox) / dw * aw
    ys = (np.arange(chh) * k - oy) / dh * ah
    xi, yi = np.clip(xs.astype(int), 0, aw - 1), np.clip(ys.astype(int), 0, ah - 1)
    inside = ((xs >= 0) & (xs < aw))[None, :] & ((ys >= 0) & (ys < ah))[:, None]
    canvas_frames = [f[yi][:, xi] & inside for f in frames]
    gx = int(x0 / k)
    def coverage(y_px):
        gy = int(y_px / k)
        if gy < 0 or gy + gh > chh:
            return None
        sub = [cf[gy:gy + gh, gx:gx + gw][: gm.shape[0], : gm.shape[1]] for cf in canvas_frames]
        vals = [float(sc[gm[: sc.shape[0], : sc.shape[1]]].mean()) for sc in sub]
        return float(np.median(vals)), vals
    notes = []
    lo_y, hi_y = int(q.margin_top * H), int(H * .8 - m["height"])
    best = None
    for y in range(lo_y, max(lo_y + 1, hi_y), 4):
        c = coverage(y)
        if c is None:
            continue
        if best is None or abs(c[0] - q.target_covered) < abs(best[1] - q.target_covered):
            best = (y, c[0], c[1])
        if c[0] > q.target_covered + .15:
            break
    if best is None:
        raise ValueError("Title does not fit in the frame at this role size")
    y_px, occl, per = best
    if abs(occl - q.target_covered) > .08:
        notes.append(f"Closest achievable coverage is {occl:.0%} (target {q.target_covered:.0%}); the subject's outline limits placement.")
    if occl < .05:
        notes.append("The subject barely reaches the title anywhere; the behind effect will not read. Try align='left' or a larger role.")
    if max(per) - min(per) > .25:
        notes.append(f"The subject moves: coverage ranges {min(per):.0%}–{max(per):.0%} across the shot. Check the extremes with review_frames; "
                     "a shorter shot window or a smaller word keeps it readable.")
    gy0, gy1 = y_px + m["glyph_top"], y_px + m["glyph_bottom"]
    d = s["end_frame"] - s["start_frame"]
    fg_frames = min(d, int((fg.get("duration") or shot_len) * FPS))
    effects = {"reveal": [{"name": "mask_reveal", "end_frame": min(26, d - 1), "params": {"amount": 120}}],
               "spring": [{"name": "char_spring", "end_frame": min(26, d - 1), "params": {"amount": .6}}], "none": []}[q.effect]
    pad = .03
    text_layer = {"id": q.id, "kind": "text", "text": q.text, "start_frame": s["start_frame"] + 6, "end_frame": s["end_frame"],
                  "x": round(float(max(0, x0 / W - pad / 2)), 4), "y": round(float(y_px / H), 4), "width": round(min(1, tw / W + pad), 4),
                  "height": round(m["height"] / H + .01, 4), "z": q.z_text, "attach_shot": s["id"], "typography_role": q.role,
                  "color": q.color, "effects": effects}
    fg_layer = {"id": q.id + "-fg", "kind": "video", "asset_id": q.foreground_asset, "start_frame": s["start_frame"],
                "end_frame": s["start_frame"] + fg_frames, "x": 0, "y": 0, "width": 1, "height": 1, "fit": "cover", "source_start": 0,
                "attach_shot": s["id"], "z": q.z_text + 5}
    ops = []
    if s.get("motion") != "hold":
        ops.append({"op": "update_shot", "shot_id": s["id"], "changes": {"motion": "hold"}})
        notes.append("Shot motion set to hold: a push/pull would scale the plate but not the foreground.")
    if fg_frames < d:
        notes.append(f"Foreground covers {fg_frames} of {d} frames; after it ends the text sits in front of the subject.")
    ops += [{"op": "upsert_layer", "layer": text_layer}, {"op": "upsert_layer", "layer": fg_layer}]
    mid = s["start_frame"] + d // 2
    return {"ops": ops, "notes": notes, "inspect_frames": [s["start_frame"] + 30, mid, s["start_frame"] + fg_frames - 10],
            "measurements": {"title_glyph_px": [round(gy0), round(gy1)], "font_px": round(m["px"]), "estimated_glyphs_covered": round(occl, 3),
                             "covered_range_over_samples": [round(min(per), 3), round(max(per), 3)], "samples": len(frames)},
            "verify": "review_frames on inspect_frames: covered_fraction should land near the target; check contrast_p10 and same_as_background_fraction."}


# ---------------------------------------------------------------- photo 3D
class Photo3D(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["photo_3d"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    image: str
    depth: str
    shot_id: str | None = None
    start_frame: int | None = None
    end_frame: int | None = None
    move: Literal["truck_right", "truck_left", "push_in", "pull_out", "crane_up", "crane_down"] = "truck_right"
    amount: Literal["minimal", "subtle", "medium", "strong"] = "medium"
    relief: float = Field(default=.14, ge=0, le=.4)
    fov: float = Field(default=40, ge=20, le=70)
    z: int = Field(default=10, ge=0, le=999)
    focus: list[float] | None = None  # [x, y] of the point of interest in image coordinates 0..1

    @model_validator(mode="after")
    def where(self):
        if not self.shot_id and (self.start_frame is None or self.end_frame is None):
            raise ValueError("photo_3d needs shot_id or start_frame/end_frame")
        return self


def photo_3d_geometry(iw, ih, canvas_aspect, move, amount, relief, fov):
    """Camera distance/travel that keep the photo plane filling the frame at every frame, including relief pushed back."""
    PW = 8.0
    PH = PW * ih / iw
    scale = relief * PH
    bias = -.4 * scale
    back = -bias  # deepest point sits this far behind the plane
    tn = math.tan(math.radians(fov) / 2)
    m = .94
    k = {"minimal": .06, "subtle": .12, "medium": .22, "strong": .32}[amount]
    A = canvas_aspect
    if move in ("truck_right", "truck_left"):
        D = min(PH / 2 * m / tn - back, PW / 2 * m / (tn * A * (1 + 2 * k)) - back)
        travel = 2 * k * D * tn * A
        start, end = (-travel / 2, 0, D), (travel / 2, 0, D)
        if move == "truck_left":
            start, end = end, start
    elif move in ("crane_up", "crane_down"):
        D = min(PW / 2 * m / (tn * A) - back, PH / 2 * m / (tn * (1 + 2 * k)) - back)
        travel = 2 * k * D * tn
        start, end = (0, -travel / 2, D), (0, travel / 2, D)
        if move == "crane_down":
            start, end = end, start
    else:
        D = min(PH / 2 * m / tn - back, PW / 2 * m / (tn * A) - back)
        start, end = (0, 0, D), (0, 0, D * (1 - 1.2 * k))
        travel = D * 1.2 * k
        if move == "pull_out":
            start, end = end, start
    near = scale + bias
    if D - near < .6:
        raise ValueError("Relief too strong for the framing: lower relief")
    # How far the whole move may be shifted toward a point of interest before the frustum leaves the plane.
    hx, hy = (D + back) * tn * A, (D + back) * tn
    span_x = max(abs(start[0]), abs(end[0])) + hx * (max(start[2], end[2]) / D)
    span_y = max(abs(start[1]), abs(end[1])) + hy * (max(start[2], end[2]) / D)
    slack = (max(0.0, PW / 2 * m - span_x), max(0.0, PH / 2 * m - span_y))
    return {"plane": [PW, PH], "displacement_scale": scale, "displacement_bias": bias, "distance": D, "travel": travel, "start": start, "end": end, "slack": slack}


def photo_3d(t, pid, q: Photo3D):
    W, H = t["width"], t["height"]
    if q.shot_id:
        s = _shot(t, q.shot_id)
        a, b, attach = s["start_frame"], s["end_frame"], s["id"]
    else:
        a, b, attach = q.start_frame, q.end_frame, None
    img, dep = store.find_asset(pid, q.image), store.find_asset(pid, q.depth)
    if img.get("kind") != "image" or dep.get("kind") != "image":
        raise ValueError("image and depth must be image assets (import the estimate_depth PNG)")
    g = photo_3d_geometry(img["width"], img["height"], W / H, q.move, q.amount, q.relief, q.fov)
    fx, fy = (q.focus or [.5, .5])
    PW, PH = g["plane"]
    sx, sy = g["slack"]  # shift toward the point of interest as far as the frame stays inside the photo
    off = (max(-sx, min(sx, (fx - .5) * PW)), max(-sy, min(sy, (.5 - fy) * PH)))
    d = b - a
    cam = lambda p: {"x": round(p[0] + off[0], 4), "y": round(p[1] + off[1], 4), "z": round(p[2], 4)}
    tgt = lambda p: {"x": round(p[0] + off[0], 4), "y": round(p[1] + off[1], 4), "z": 0}
    from PIL import Image
    with Image.open(img["path"]) as im:
        mean = im.convert("RGB").resize((1, 1)).getpixel((0, 0))
    data = {"objects": [{"id": "photo", "geometry": "plane", "size": [PW, PH, 1], "segments": 320, "color": "#000000", "emissive": "#ffffff",
                         "emissive_intensity": 1, "emissive_texture": q.image, "displacement_texture": q.depth,
                         "displacement_scale": round(g["displacement_scale"], 4), "displacement_bias": round(g["displacement_bias"], 4),
                         "roughness": 1, "metalness": 0}],
            "lights": [{"kind": "ambient", "intensity": .2}],
            "camera_keyframes": [{"frame": 0, "position": cam(g["start"]), "target": tgt(g["start"])},
                                 {"frame": max(1, d - 1), "position": cam(g["end"]), "target": tgt(g["end"])}],
            "fov": q.fov, "background": "#%02x%02x%02x" % mean[:3], "transparent": False, "ground": False, "shadows": False}
    layer = {"id": q.id, "kind": "scene3d", "start_frame": a, "end_frame": b, "x": 0, "y": 0, "width": 1, "height": 1, "z": q.z,
             "attach_shot": attach, "data": data}
    f_px = (H / 2) / math.tan(math.radians(q.fov) / 2)
    near, far = g["displacement_scale"] + g["displacement_bias"], g["displacement_bias"]
    D = g["distance"]
    parallax = g["travel"] * (1 / (D - near) - 1 / (D - far)) * f_px if q.move not in ("push_in", "pull_out") else None
    from .review import audit_timeline  # noqa: F401  (geometry check below mirrors audit's plane_edge test)
    return {"ops": [{"op": "upsert_layer", "layer": layer}], "notes": [],
            "inspect_frames": [a, a + d // 2, b - 1],
            "measurements": {"camera_distance": round(D, 3), "travel": round(g["travel"], 3), "plane": [PW, round(PH, 3)],
                             "near_far_parallax_px": round(parallax, 1) if parallax else None,
                             "relief_scale": round(g["displacement_scale"], 3)},
            "verify": "audit_timeline should report no plane_edge_visible/displacement_angle for this layer; snapshot first/last frame corners."}


# ---------------------------------------------------------------- trajectory 3D
class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    position: list[float] = Field(min_length=3, max_length=3)
    diameter: float = Field(gt=0, le=10)
    texture: str | None = None
    bump_texture: str | None = None
    clouds_texture: str | None = None
    color: str = Field(default="#9aa3b2", pattern=HEX)
    label: str = ""
    atmosphere: bool = False
    atmosphere_color: str = Field(default="#6fb8ff", pattern=HEX)
    emissive: bool = False  # self-lit body (a star); with light=true it also lights the scene from its position
    light: bool = False


class Milestone(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    index: int | None = None
    fraction: float | None = Field(default=None, ge=0, le=1)
    keep: bool = False


class Trajectory3D(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["trajectory_3d"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    start_frame: int = Field(ge=0)
    end_frame: int
    attach_shot: str | None = None
    path: list[list[float]] = Field(min_length=2, max_length=500)
    bodies: list[Body] = Field(default_factory=list, max_length=6)
    milestones: list[Milestone] = Field(default_factory=list, max_length=12)
    travel: list[int] | None = None
    establish_on: str | None = None
    focus_body: str | None = None
    focus_window: list[int] | None = None
    overview_from: float = Field(default=.74, ge=.3, le=.95)
    chase_offset: list[float] = Field(default_factory=lambda: [-.75, .7, 1.3], min_length=3, max_length=3)
    route_color: str = Field(default="#e4b866", pattern=HEX)
    label_hold: int = Field(default=75, ge=20, le=300)
    stars: int = Field(default=40, ge=0, le=60)
    fov: float = Field(default=42, ge=20, le=80)
    background: str = Field(default="#04060b", pattern=HEX)
    # Orbit rings in the XZ plane (orbital diagrams): [{radius, center [x,y,z], color}]
    orbits: list[dict] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def check_orbits(self):
        for o in self.orbits:
            if not isinstance(o.get("radius"), (int, float)) or not .05 <= o["radius"] <= 50:
                raise ValueError("orbit radius .05..50")
        return self


def trajectory_3d(t, q: Trajectory3D):
    d = q.end_frame - q.start_frame
    if d < 60:
        raise ValueError("trajectory_3d needs at least 2 s")
    P = [[round(v, 4) for v in p] for p in q.path]
    seg = [0.0]
    for a, b in zip(P, P[1:]):
        seg.append(seg[-1] + math.dist(a, b))
    travel = q.travel or [int(d * .08), int(d * .9)]
    smooth = lambda u: u * u * (3 - 2 * u)
    def at(f):
        u = min(1.0, max(0.0, (f - travel[0]) / (travel[1] - travel[0])))
        s = smooth(u) * seg[-1]
        i = max(0, min(len(seg) - 2, next((k for k in range(1, len(seg)) if seg[k] >= s), len(seg) - 1) - 1))
        r = (s - seg[i]) / max(1e-9, seg[i + 1] - seg[i])
        return [P[i][k] + (P[i + 1][k] - P[i][k]) * r for k in range(3)]
    def arrive(frac):
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if smooth(mid) < frac else (lo, mid)
        return round(travel[0] + lo * (travel[1] - travel[0]))
    bodies = {b.id: b for b in q.bodies}
    objs = []
    for b in q.bodies:
        pos = dict(zip("xyz", b.position))
        base = {"id": b.id, "geometry": "sphere", "size": [b.diameter] * 3, "position": pos, "roughness": .9, "metalness": 0,
                "keyframes": [{"frame": 0, "rotation": {"x": 0, "y": 0, "z": 0}}, {"frame": d - 1, "rotation": {"x": 0, "y": .8, "z": 0}}]}
        if b.texture:
            base["texture"] = b.texture
        else:
            base["color"] = b.color
        if b.emissive:
            base.update(emissive=b.color, emissive_intensity=2.2, **({"emissive_texture": b.texture} if b.texture else {}))
        if b.bump_texture:
            base.update(bump_texture=b.bump_texture, bump_scale=3)
        objs.append(base)
        if b.clouds_texture:
            objs.append({"id": b.id + "-clouds", "geometry": "sphere", "size": [b.diameter * 1.015] * 3, "position": pos, "color": "#ffffff",
                         "alpha_texture": b.clouds_texture, "opacity": .85, "roughness": 1, "metalness": 0,
                         "keyframes": [{"frame": 0, "rotation": {"x": 0, "y": 0, "z": 0}}, {"frame": d - 1, "rotation": {"x": 0, "y": .95, "z": 0}}]})
        if b.atmosphere:
            objs.append({"id": b.id + "-atmo", "geometry": "sphere", "size": [b.diameter * 1.06] * 3, "position": pos, "color": b.atmosphere_color,
                         "opacity": .12, "emissive": b.atmosphere_color, "emissive_intensity": .6, "roughness": 1})
        if b.label:
            objs.append({"id": b.id + "-l", "geometry": "sphere", "size": [.001] * 3,
                         "position": {"x": b.position[0], "y": b.position[1] + b.diameter * .65, "z": b.position[2]}, "label": b.label,
                         "keyframes": [{"frame": 0, "scale": .01}, {"frame": 6, "scale": 1}, {"frame": 80, "scale": 1}, {"frame": 90, "scale": .01},
                                       {"frame": int(d * q.overview_from), "scale": .01}, {"frame": int(d * q.overview_from) + 12, "scale": 1}]})
    for k, o in enumerate(q.orbits):
        c = o.get("center", [0, 0, 0])
        ring = [[round(c[0] + o["radius"] * math.cos(a), 4), c[1], round(c[2] + o["radius"] * math.sin(a), 4)] for a in (i / 96 * 2 * math.pi for i in range(97))]
        objs.append({"id": f"orbit{k}", "geometry": "tube", "path": ring, "tube_radius": .004, "color": o.get("color", "#4a5a74"), "emissive": o.get("color", "#4a5a74"),
                     "emissive_intensity": .6, "roughness": .8, "metalness": 0})
    objs += [{"id": "ghost", "geometry": "tube", "path": P, "tube_radius": .004, "grow": [0, 30], "color": "#3a4a60", "emissive": "#3a4a60",
              "emissive_intensity": .7, "roughness": .8, "metalness": 0},
             {"id": "route", "geometry": "tube", "path": P, "tube_radius": .0075, "grow": list(travel), "color": q.route_color,
              "emissive": q.route_color, "emissive_intensity": 1.5, "roughness": .4, "metalness": 0},
             {"id": "traveller", "geometry": "sphere", "size": [.032] * 3, "color": "#ffffff", "emissive": "#ffffff", "emissive_intensity": 3,
              "follow": "route", "follow_range": list(travel), "follow_orient": False}]
    arrivals = []
    for n, ms in enumerate(q.milestones):
        frac = ms.fraction if ms.fraction is not None else seg[min(len(P) - 1, ms.index or 0)] / seg[-1]
        idx = ms.index if ms.index is not None else min(range(len(seg)), key=lambda i: abs(seg[i] / seg[-1] - frac))
        f0 = arrive(frac)
        arrivals.append(f0)
        p = P[idx]
        objs.append({"id": f"ms{n}", "geometry": "sphere", "size": [.034] * 3, "position": dict(zip("xyz", p)), "color": q.route_color,
                     "emissive": q.route_color, "emissive_intensity": 1.8,
                     "keyframes": [{"frame": 0, "scale": .01}, {"frame": max(1, f0), "scale": .01}, {"frame": f0 + 8, "scale": 1.4}, {"frame": f0 + 14, "scale": 1}]})
        last = ms.keep or n == len(q.milestones) - 1
        hold = [] if last else [{"frame": f0 + q.label_hold, "scale": 1}, {"frame": f0 + q.label_hold + 10, "scale": .01}]
        objs.append({"id": f"ml{n}", "geometry": "sphere", "size": [.001] * 3, "position": {"x": p[0], "y": p[1] + .05, "z": p[2]}, "label": ms.label,
                     "keyframes": [{"frame": 0, "scale": .01}, {"frame": max(1, f0 + 2), "scale": .01}, {"frame": f0 + 10, "scale": 1}, *hold]})
    for i in range(q.stars):
        objs.append({"id": f"st{i}", "geometry": "sphere", "size": [.035] * 3, "color": "#ffffff", "emissive": "#ffffff", "emissive_intensity": 1 + (i * 7 % 10) / 8,
                     "position": {"x": round(-16 + (i * 13.37) % 32, 2), "y": round(-6 - (i * 3.7) % 6, 2), "z": round(-14 + (i * 7.91) % 28, 2)}})
    xs, zs = [p[0] for p in P], [p[2] for p in P]
    cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    extent = max(max(xs) - min(xs), max(zs) - min(zs), 1)
    over_p, over_t = [cx - .04 * extent, .95 * extent, cz + .9 * extent], [cx, -.04 * extent, cz + .03 * extent]
    mix = lambda a, b, w: [a[k] + (b[k] - a[k]) * w for k in range(3)]
    band = lambda f, a, b: smooth(min(1.0, max(0.0, (f - a) / max(1, b - a))))
    est = bodies.get(q.establish_on)
    focus = bodies.get(q.focus_body)
    fw = q.focus_window or ([int(d * .38), int(d * .52)] if focus else None)
    ov = int(d * q.overview_from)
    def rig(f):
        o = at(f)
        ahead = at(min(d - 1, f + 24))
        chase_p = [o[0] + q.chase_offset[0], o[1] + q.chase_offset[1], o[2] + q.chase_offset[2]]
        chase_t = mix(o, ahead, .5)
        if est:
            p0 = [est.position[0] - 1.6 * est.diameter, est.position[1] + .55 * est.diameter, est.position[2] + 2 * est.diameter]
            t0 = [est.position[0] + .9 * est.diameter, est.position[1], est.position[2] - .3 * est.diameter]
        else:
            p0, t0 = chase_p, chase_t
        p, tg = p0, t0
        w = band(f, travel[0] - 14, travel[0] + 36)
        p, tg = mix(p, chase_p, w), mix(tg, chase_t, w)
        if focus and fw:
            fp = [focus.position[0] - 1.7 * focus.diameter, focus.position[1] + 3.2 * focus.diameter, focus.position[2] + 5.5 * focus.diameter]
            w = band(f, fw[0], fw[1])
            p, tg = mix(p, fp, w), mix(tg, mix(focus.position, o, .45), w)
        w = band(f, ov, min(d - 1, ov + int(d * .17)))
        return mix(p, over_p, w), mix(tg, over_t, w)
    cams = []
    step = max(3, math.ceil(d / 95))
    for f in list(range(0, d, step)) + [d - 1]:
        p, tg = rig(f)
        cams.append({"frame": f, "position": dict(zip("xyz", (round(v, 4) for v in p))), "target": dict(zip("xyz", (round(v, 4) for v in tg)))})
    lamps = [b for b in q.bodies if b.light]
    lights = [{"kind": "ambient", "intensity": .07}] + ([{"kind": "point", "position": dict(zip("xyz", b.position)), "intensity": 12, "color": "#fff1d6"} for b in lamps[:3]]
                                                        or [{"kind": "directional", "position": {"x": -3, "y": 2.2, "z": 4}, "intensity": 3.3, "color": "#fff4e6"}])
    data = {"objects": objs, "lights": lights,
            "camera_keyframes": cams, "camera_ease": "linear", "fov": q.fov, "background": q.background, "transparent": False, "ground": False,
            "shadows": False, "bloom": {"strength": .35, "radius": .3, "threshold": .88}, "label_font_size": 30, "label_color": "#ffffff"}
    layer = {"id": q.id, "kind": "scene3d", "start_frame": q.start_frame, "end_frame": q.end_frame, "x": 0, "y": 0, "width": 1, "height": 1, "z": 10,
             "attach_shot": q.attach_shot, "data": data}
    inspect = sorted({q.start_frame + travel[0] + 20, *(q.start_frame + f + 12 for f in arrivals[:3]), q.end_frame - 1})
    return {"ops": [{"op": "upsert_layer", "layer": layer}], "notes": [] if len(objs) <= 160 else ["Too many objects; reduce stars"],
            "inspect_frames": inspect[:8], "measurements": {"path_length": round(seg[-1], 3), "milestone_frames": [q.start_frame + f for f in arrivals],
                                                            "camera_keys": len(cams), "objects": len(objs)},
            "verify": "audit_timeline: label_collision/camera_stops for this layer; snapshot inspect_frames."}


# ---------------------------------------------------------------- map journey
class City(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Leg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: str
    start_frame: int = Field(ge=0)
    end_frame: int
    attach_shot: str | None = None
    origin: str | None = None
    curve: float = Field(default=.25, ge=-1, le=1)


class MapJourney(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["map_journey"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    country: str
    neighbors: list[str] = Field(default_factory=list, max_length=6)
    cities: list[City] = Field(min_length=1, max_length=30)
    legs: list[Leg] = Field(min_length=1, max_length=20)
    box: list[float] = Field(default_factory=lambda: [.68, .06, .28, .27], min_length=4, max_length=4)
    land: str = Field(default="#1c2636", pattern=HEX)
    border: str = Field(default="#ffd166", pattern=HEX)
    route: str = Field(default="#ffffff", pattern=HEX)
    card: bool = True
    draw_frames: int = Field(default=40, ge=8, le=200)


def map_journey(t, q: MapJourney):
    from .resources import geo_map
    gm = geo_map(q.country, [c.model_dump() for c in q.cities], width=1000, islands=True, extra_countries=q.neighbors)
    C = gm["cities"]
    VW, VH = gm["view_box"]
    def bez(p0, p1, curve, n=36):
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        c = (mx - dy * curve, my + dx * curve)
        return [[round((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * c[0] + u * u * p1[0], 1),
                 round((1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * c[1] + u * u * p1[1], 1)] for u in (i / n for i in range(n + 1))]
    ops, drawn, prev = [], [], q.legs[0].origin or q.cities[0].name
    bx, by, bw, bh = q.box
    aspect = VW / VH
    # Fit the map inside the card keeping its aspect (normalized canvas units).
    W, H = t["width"], t["height"]
    inner_w = min(bw * .9, bh * .9 * aspect * H / W)
    inner_h = inner_w * W / H / aspect
    ix, iy = bx + (bw - inner_w) / 2, by + (bh - inner_h) / 2
    for n, leg in enumerate(q.legs):
        origin = leg.origin or prev
        if origin not in C or leg.to not in C:
            raise ValueError(f"Leg {n}: unknown city {origin!r} or {leg.to!r}")
        pts = bez(C[origin], C[leg.to], leg.curve)
        # Neighbours first (muted), the main country last so its glowing border sits on top.
        paths = [{"id": f"land{i}", "type": "path", "d": d, "stroke": q.border if i == 0 else "#55617a", "stroke_width": 6 if i == 0 else 3,
                  "glow": 8 if i == 0 else 0, "fill": q.land if i == 0 else "#141b27", "fill_opacity": .95}
                 for i, d in enumerate(gm["paths"].values())]
        els = paths[1:] + paths[:1]
        for k, done in enumerate(drawn):
            els.append({"id": f"done{k}", "type": "polyline", "points": done, "stroke": q.route, "stroke_width": 6, "glow": 8})
        dr = min(q.draw_frames, max(8, leg.end_frame - leg.start_frame - 20))
        els += [{"id": "leg", "type": "polyline", "points": pts, "stroke": q.route, "stroke_width": 6, "glow": 8, "draw": [6, 6 + dr]},
                {"id": "mk", "type": "follower", "route": "leg", "progress": [6, 6 + dr], "r": 18, "fill": q.route, "stroke": "none", "glow": 18}]
        for k, c in enumerate(q.cities):
            hero = c.name == leg.to
            x, y = C[c.name]
            els.append({"id": f"c{k}", "type": "circle", "cx": x, "cy": y, "r": 17 if hero else 11, "fill": q.border if hero else "#ffffff",
                        "stroke": "#0b0d12", "stroke_width": 3, "glow": 14 if hero else 4})
        lid = f"{q.id}-{n}"
        if q.card:
            ops.append({"op": "upsert_layer", "layer": {"id": lid + "-card", "kind": "shape", "start_frame": leg.start_frame, "end_frame": leg.end_frame,
                                                        "x": bx, "y": by, "width": bw, "height": bh, "attach_shot": leg.attach_shot, "z": 44, "color": "#0b0d12",
                                                        "opacity": .72, "data": {"shape": "rectangle", "corner_radius": 0},
                                                        "effects": [{"name": "fade_in", "end_frame": 10}, {"name": "rounded", "end_frame": 1, "params": {"amount": 22}}]}})
        ops.append({"op": "upsert_layer", "layer": {"id": lid, "kind": "svg", "start_frame": leg.start_frame, "end_frame": leg.end_frame,
                                                    "x": round(ix, 4), "y": round(iy, 4), "width": round(inner_w, 4), "height": round(inner_h, 4),
                                                    "attach_shot": leg.attach_shot, "z": 45, "data": {"view_box": [VW, VH], "elements": els},
                                                    "effects": [{"name": "fade_in", "end_frame": 10}]}})
        drawn.append(pts)
        prev = leg.to
    return {"ops": ops, "notes": [] if len(q.cities) < 12 else ["Many cities: consider showing only the legs' endpoints."],
            "inspect_frames": [leg.start_frame + 8 + q.draw_frames for leg in q.legs][:8],
            "measurements": {"view_box": [VW, VH], "card": q.box, "map_box": [round(ix, 4), round(iy, 4), round(inner_w, 4), round(inner_h, 4)]},
            "verify": "snapshot each leg after it draws; make sure the card does not cover the shot's subject."}


# ---------------------------------------------------------------- film finish
class FilmFinish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["film_finish"]
    id: str = Field(default="fx", pattern=r"^[A-Za-z0-9_-]{1,40}$")
    grain: float | None = Field(default=.2, ge=0, le=1)
    leaks: Literal["auto"] | list[int] = "auto"
    leak_seconds: float = Field(default=2.2, ge=.5, le=6)
    colors: list[str] = Field(default_factory=lambda: ["#ffb347", "#ff5a3c"], min_length=2, max_length=2)
    max_coverage: float = Field(default=.3, ge=0, le=1)


def film_finish(t, q: FilmFinish):
    N = t["total_frames"]
    ops, notes = [], []
    if q.grain:
        ops.append({"op": "upsert_layer", "layer": {"id": q.id + "-grain", "kind": "film", "start_frame": 0, "end_frame": N, "x": 0, "y": 0, "width": 1,
                                                    "height": 1, "z": 900, "blend": "overlay", "data": {"type": "grain", "intensity": q.grain, "scale": .9}}})
    if q.leaks == "auto":
        at = [s["start_frame"] for s in t["shots"] if (s.get("transition") or {}).get("name") in ("flash", "burn", "zoom_through")]
    else:
        at = list(q.leaks)
    L = int(q.leak_seconds * FPS)
    budget = int(q.max_coverage * N)
    used = 0
    for i, f in enumerate(sorted(at)):
        a, b = max(0, f - int(L * .4)), min(N, f + int(L * .6))
        if used + (b - a) > budget:
            notes.append(f"Skipped leak at {f}: coverage budget {q.max_coverage:.0%} reached")
            continue
        used += b - a
        ops.append({"op": "upsert_layer", "layer": {"id": f"{q.id}-leak{i}", "kind": "film", "start_frame": a, "end_frame": b, "x": 0, "y": 0, "width": 1,
                                                    "height": 1, "z": 890, "blend": "screen",
                                                    "data": {"type": "light_leak", "intensity": .7, "color": q.colors[0], "secondary_color": q.colors[1], "speed": 2, "seed": 3 + 4 * i},
                                                    "effects": [{"name": "fade_in", "end_frame": min(14, (b - a) // 3)},
                                                                {"name": "fade_out", "start_frame": int((b - a) * .6), "end_frame": b - a - 1}]}})
    if not at:
        notes.append("No flash/burn/zoom_through transitions found; pass leaks as frame numbers if wanted.")
    return {"ops": ops, "notes": notes, "inspect_frames": [min(N - 1, f + 6) for f in sorted(at)][:6],
            "measurements": {"leak_coverage": round(used / max(1, N), 3), "leaks": len(ops) - bool(q.grain)}}


# ---------------------------------------------------------------- history map
class MapCity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class MapStep(BaseModel):
    """One timed event on a history map (frames local to the map layer). parallel: a dashed line along a latitude that
    draws west to east (a partition, a front); arrow: an offensive or movement from one city to another; route: a path
    through [lat, lon] points (a supply trail, a march); marker: a city that appears with rings; label: text at a point;
    region: a large faint name over an area (MIỀN BẮC); camera: the map flies to a city or point (zoom, eased over
    `frames`) and holds it at `focus` on screen; footage: located footage, a framed video of that place growing out of its
    pin with a leader line and a caption, the map dimmed under it, then closing back to the pin or (expand) filling the
    frame so the next shot continues the same footage full screen."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["parallel", "arrow", "route", "marker", "label", "region", "camera", "footage"]
    at: int = Field(ge=0)
    frames: int = Field(default=24, ge=1, le=600)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    city: str | None = None
    origin: str | None = None
    to: str | None = None
    points: list[list[float]] = Field(default_factory=list, max_length=200)
    text: str = Field(default="", max_length=60)
    color: str | None = Field(default=None, pattern=HEX)
    dashed: bool = False
    side: Literal["left", "right", "above", "below"] = "right"
    size: float = Field(default=1.0, ge=.4, le=4)
    lon_range: list[float] | None = Field(default=None, min_length=2, max_length=2)  # parallel: [west, east]; default the whole view
    zoom: float = Field(default=1.6, ge=1, le=3)  # camera: map scale after the move
    focus: list[float] | None = Field(default=None, min_length=2, max_length=2)  # camera: where the point lands on screen [x, y]
    asset_id: str | None = Field(default=None, max_length=100)  # footage: the video asset
    source_start: float = Field(default=0, ge=0)
    playback_rate: float = Field(default=1, ge=.25, le=4)
    caption: str = Field(default="", max_length=80)  # footage: place · year under the frame
    expand: bool = False  # footage: grow to full frame at its end (the map's last step) instead of closing to the pin
    width: float = Field(default=.42, ge=.2, le=.6)  # footage: frame width as a share of the screen


class MapArchipelago(BaseModel):
    """Islands drawn as small land dots with one label (Natural Earth's country outlines leave most of them out)."""
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    points: list[list[float]] = Field(min_length=1, max_length=80)  # [lat, lon] of each island or reef
    label_at: list[float] | None = Field(default=None, min_length=2, max_length=2)  # [lat, lon]; default below the group


# Vietnam's maps show its two archipelagos (Vietnamese mapping rules require them); island positions are approximate.
VIETNAM_ARCHIPELAGOS = [
    {"name": "Quần đảo Hoàng Sa", "label_at": [17.55, 112.1],
     "points": [[16.834, 112.335], [16.667, 112.725], [16.983, 112.267], [17.08, 111.50], [16.534, 111.608], [16.45, 111.508],
                [16.467, 111.733], [15.783, 111.20], [16.033, 112.533], [16.95, 112.55]]},
    {"name": "Quần đảo Trường Sa", "label_at": [7.35, 113.6],
     "points": [[11.43, 114.33], [11.054, 114.284], [10.68, 114.42], [10.377, 114.365], [10.181, 114.36], [10.377, 114.478],
                [9.883, 114.329], [9.912, 114.568], [8.645, 111.92], [8.85, 112.2], [7.89, 112.917], [8.18, 113.30], [8.97, 113.70],
                [8.82, 113.98], [8.67, 111.67], [11.083, 115.022], [10.733, 115.80], [9.5, 112.9]]},
]


class HistoryMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["history_map"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    start_frame: int = Field(ge=0)
    end_frame: int
    country: str
    neighbors: list[str] = Field(default_factory=list, max_length=8)
    view: list[float] | None = Field(default=None, min_length=4, max_length=4)  # [lon0, lat0, lon1, lat1]; default the country's bbox
    # "auto": Vietnam's map carries Hoàng Sa and Trường Sa (and its default view reaches them); [] draws none
    archipelagos: Literal["auto"] | list[MapArchipelago] = "auto"
    cities: list[MapCity] = Field(default_factory=list, max_length=40)
    steps: list[MapStep] = Field(min_length=1, max_length=60)
    box: list[float] = Field(default_factory=lambda: [.05, .04, .9, .92], min_length=4, max_length=4)
    land: str = Field(default="#20242a", pattern=HEX)
    border: str = Field(default="#e8b04a", pattern=HEX)
    accent: str = Field(default="#d8442f", pattern=HEX)
    ink: str = Field(default="#f4ead8", pattern=HEX)
    background: str | None = Field(default="#0b0c0e", pattern=HEX)  # full-frame card under the map; None keeps the shot
    attach_shot: str | None = None
    z: int = Field(default=46, ge=0, le=999)
    # a relief image cropped to map_extent(view) (resources.relief_crop), drawn under the outlines and moved by the camera
    relief_asset: str | None = Field(default=None, max_length=100)
    relief_brightness: float = Field(default=.78, ge=.2, le=1.2)
    # widen the view (in longitude or latitude) until its projected box has this width/height, so a full-frame box is
    # filled edge to edge by land, sea and relief (box [0, 0, 1, 1] on 16:9: 16/9)
    fill_aspect: float | None = Field(default=None, gt=.3, lt=4)
    # between camera moves the map keeps creeping in about the middle of the screen: this much scale per 10 s (0: hold)
    drift: float = Field(default=.06, ge=0, le=.3)

    @model_validator(mode="after")
    def check(self):
        if self.end_frame <= self.start_frame:
            raise ValueError("history_map needs end_frame > start_frame")
        names = {c.name for c in self.cities}
        span = self.end_frame - self.start_frame
        for k, st in enumerate(self.steps):
            if st.at >= span:
                raise ValueError(f"step {k} starts after the map ends")
            if st.kind == "parallel" and st.lat is None:
                raise ValueError(f"step {k}: parallel needs lat")
            if st.kind == "arrow" and (st.origin not in names or st.to not in names):
                raise ValueError(f"step {k}: arrow needs origin and to among cities")
            if st.kind == "marker" and st.city not in names:
                raise ValueError(f"step {k}: marker needs a city")
            if st.kind == "route" and (len(st.points) < 2 or any(len(pt) != 2 for pt in st.points)):
                raise ValueError(f"step {k}: route needs >= 2 [lat, lon] points")
            if st.kind in ("label", "region") and (not st.text or (st.city not in names and (st.lat is None or st.lon is None))):
                raise ValueError(f"step {k}: {st.kind} needs text and a city or lat/lon")
            if st.kind in ("camera", "footage") and st.city not in names and (st.lat is None or st.lon is None):
                raise ValueError(f"step {k}: {st.kind} needs a city or lat/lon")
            if st.kind == "footage":
                if not st.asset_id:
                    raise ValueError(f"step {k}: footage needs asset_id")
                if st.frames < 75:
                    raise ValueError(f"step {k}: footage needs >= 75 frames (it grows, plays >= 2 s and closes)")
                if st.expand and st.at + st.frames != span:
                    raise ValueError(f"step {k}: an expanding footage step ends the map (at + frames == end_frame - start_frame)")
        shown = [(st.at, st.at + st.frames) for st in self.steps if st.kind == "footage"]
        if any(sum(1 for a2, b2 in shown if a2 < b and b2 > a) > 2 for a, b in shown):
            raise ValueError("at most two footage frames on the map at once")
        return self


def _archipelagos(q):
    vietnam = q.country.strip().lower() in ("vietnam", "viet nam", "vnm")
    return [MapArchipelago.model_validate(a) for a in VIETNAM_ARCHIPELAGOS] if q.archipelagos == "auto" and vietnam else \
        ([] if q.archipelagos == "auto" else q.archipelagos)


def map_view(q):
    """The [lon0, lat0, lon1, lat1] a history_map draws: its view, else the country's bbox reaching its archipelagos."""
    from .resources import geo_outline
    arch = _archipelagos(q)
    view = q.view or geo_outline(q.country, islands=True)["bbox"]
    if arch and not q.view:  # reach the islands: the country's bbox stops at its mainland coast
        lats = [pt[0] for a in arch for pt in a.points] + [a.label_at[0] for a in arch if a.label_at]
        lons = [pt[1] for a in arch for pt in a.points]
        view = [min(view[0], min(lons) - .6), min(view[1], min(lats) - .6), max(view[2], max(lons) + .6), max(view[3], max(lats) + .6)]
    if q.fill_aspect:  # MapProjection(width 1000, pad .04): box height = h * 920 / w + 80
        lon0, lat0, lon1, lat1 = view
        k = math.cos(math.radians((lat0 + lat1) / 2))
        w, h = (lon1 - lon0) * k, lat1 - lat0
        need_w = 920 * h / (1000 / q.fill_aspect - 80)
        if need_w > w:
            d = (need_w - w) / k / 2
            view = [lon0 - d, lat0, lon1 + d, lat1]
        else:
            d = (w * (1000 / q.fill_aspect - 80) / 920 - h) / 2
            view = [lon0, lat0 - d, lon1, lat1 + d]
    return view


def map_extent(q):
    """The lon/lat rectangle the map's whole view box covers, padding included: [west, north, east, south] and the view
    box size. An equirectangular image cropped to it lines up with the outlines (the projection is linear in lon and lat)."""
    from .resources import MapProjection
    proj = MapProjection(map_view(q), 1000, pad=.04)
    w = proj.lon0 - proj.pad / (proj.k * proj.scale)
    n = proj.lat1 + proj.pad / proj.scale
    return {"extent": [w, n, w + proj.width / (proj.k * proj.scale), n - proj.height / proj.scale], "view_box": [proj.width, round(proj.height, 1)]}


def history_map(t, q: HistoryMap):
    """Full-frame documentary map that tells a geographic change step by step (partition, offensives, trails), as one
    vector layer drawn identically by both engines; text uses the design's label face."""
    from .resources import geo_outline, MapProjection
    from .explainer import _font
    main = geo_outline(q.country, islands=True)
    arch = _archipelagos(q)
    view = map_view(q)
    proj = MapProjection(view, 1000, pad=.04)
    VW, VH = proj.width, round(proj.height, 1)
    span = q.end_frame - q.start_frame
    C = {c.name: proj(c.lat, c.lon) for c in q.cities}
    font = _font(t, "label")
    end = lambda a, n: min(span - 1, a + n)
    els = []
    for i, other in enumerate(q.neighbors):
        o = geo_outline(other, max_points=400, islands=False)
        els.append({"id": f"n{i}", "type": "path", "d": proj.path(o["rings"]), "stroke": "#4a505a", "stroke_width": 2.5, "fill": "#14171b" if not q.relief_asset else "#000000",
                    "fill_opacity": 1 if not q.relief_asset else .42, "appear": [0, 12]})  # on relief: neighbours dimmed, terrain still read
    # the outline scales with the country on the map: at world scale a 4-unit stroke and its glow covered Vietnam whole
    # (round 13 showcase, the owner: "đường màu vàng che hết cả việt nam")
    mx0, my0 = proj(main["bbox"][3], main["bbox"][0])
    mx1, my1 = proj(main["bbox"][1], main["bbox"][2])
    diag = math.hypot(mx1 - mx0, my1 - my0)
    sw = round(min(4.0, max(.8, diag * .012)), 2)
    els.append({"id": "land", "type": "path", "d": proj.path(main["rings"]), "stroke": q.border, "stroke_width": sw, "glow": round(min(6.0, sw * 1.5), 2),
                "fill": q.land, "fill_opacity": 1 if not q.relief_asset else 0, "appear": [0, 14]})
    W, H = t["width"], t["height"]
    bx, by, bw, bh = q.box
    aspect = VW / VH
    inner_w = min(bw, bh * aspect * H / W)
    inner_h = inner_w * W / H / aspect
    ix, iy = bx + (bw - inner_w) / 2, by + (bh - inner_h) / 2
    fs0 = 30 * (H / 1080) / (inner_w * W / VW)  # labels ~30 px on a 1080p frame, whatever the map's size
    cams = sorted((st for st in q.steps if st.kind == "camera"), key=lambda st: st.at)

    def text_scale(f):
        """Labels drawn under a camera zoom grow with it: 36 px on the whole map, ~51 px at 2x, ~62 px at 3x (round 13:
        30 px on a country map could not be read, 90 px at 3x crowded the frame), by the zoom set when they appear."""
        z = next((st.zoom for st in reversed(cams) if st.at <= f), 1.0)
        return 1.2 / z ** .5

    def line_scale(f):
        """Strokes under the camera zoom keep (nearly) their on-screen width from the zoom set when they appear: the
        border was 23-26 px wide at 3.5x (ep2 735 s)."""
        z = next((st.zoom for st in reversed(cams) if st.at <= f), 1.0)
        return 1 / z ** .85
    zmax = max([st.zoom for st in cams] or [1.0])
    for e_ in els:  # the country outline lives through every zoom: sized for the closest one, its glow a hairline
        if e_.get("id") == "land":
            e_["stroke_width"] = round(max(.6, e_["stroke_width"] / zmax ** .6), 2)
            e_["glow"] = round(min(3.0, e_["stroke_width"]), 2)

    def readable(col, bg="#14171b", need=4.5):
        """A coloured label lightened toward white until it reads on the dark map (a red sublabel measured 2.0:1)."""
        def lum(h):
            h = h.lstrip("#")
            c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            c = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in c]
            return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
        try:
            rgb = [int(col.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
        except (ValueError, AttributeError):
            return col
        for k_ in range(11):
            mix = "#" + "".join(f"{round(v + (255 - v) * k_ / 10):02x}" for v in rgb)
            if (lum(mix) + .05) / (lum(bg) + .05) >= need:
                return mix
        return "#ffffff"
    for k, a in enumerate(arch):  # islands: land dots ringed by the border colour, one label for the group
        for j, (la, lo) in enumerate(a.points):
            x, y = proj(la, lo)
            els.append({"id": f"isl{k}_{j}", "type": "circle", "cx": x, "cy": y, "r": round(fs0 * .16, 2), "fill": q.land, "stroke": q.border,
                        "stroke_width": round(fs0 * .07, 2), "appear": [0, 14]})
        la, lo = a.label_at or [min(pt[0] for pt in a.points) - .5, sum(pt[1] for pt in a.points) / len(a.points)]
        x, y = proj(la, lo)
        els.append({"id": f"isl{k}_t", "type": "text", "x": x, "y": y, "text": a.name, "font_size": round(fs0 * .78 * text_scale(0), 1), "font_weight": 500,
                    "anchor": "middle", "fill": q.ink, "stroke": "none", "opacity": .85, "appear": [0, 14]})

    def label(eid, x, y, text, side, a, color, size=1.0, weight=600, clear=0.0):
        fs = fs0 * text_scale(a)
        u = fs / 26  # offsets were tuned for 26-unit text
        dx, dy, anchor = {"right": (18, 9, "start"), "left": (-18, 9, "end"), "above": (0, -16, "middle"), "below": (0, 34, "middle")}[side]
        # clear: a marker's radius (map units) the words keep off, whatever the zoom has done to the type (round 13
        # showcase: at zoom 3 the Việt Bắc dot covered the label's last letter)
        cx, cy = {"right": (clear, 0), "left": (-clear, 0), "above": (0, -clear), "below": (0, clear)}[side]
        return {"id": eid, "type": "text", "x": round(x + dx * u + cx, 1), "y": round(y + dy * size * u + cy, 1), "text": text, "font_size": round(fs * size, 1),
                "font_weight": weight, "anchor": anchor, "fill": color, "stroke": "none", "appear": [a, max(a + 1, end(a, 10))], "glow": 3}

    def away_from_lines(city, side):
        """The side for a city's label that no arrow or route leaving the city runs through (round 13 showcase: the
        Moskva arc crossed "Moskva · 30.1.1950" for twelve seconds). Keeps the asked side when it is clear."""
        x0, y0 = C[city]
        dirs = []
        for st_ in q.steps:
            if st_.kind == "arrow" and city in (st_.origin, st_.to):
                ox, oy = C[st_.to if st_.origin == city else st_.origin]
                dirs.append((ox - x0, oy - y0))
            elif st_.kind == "route" and len(st_.points) > 1:
                pts = [proj(la, lo) for la, lo in st_.points]
                for end_, nxt in ((pts[0], pts[min(3, len(pts) - 1)]), (pts[-1], pts[max(0, len(pts) - 4)])):
                    if math.hypot(end_[0] - x0, end_[1] - y0) < 12:
                        dirs.append((nxt[0] - end_[0], nxt[1] - end_[1]))
        vec = {"right": (1, 0), "left": (-1, 0), "above": (0, -1), "below": (0, 1)}
        unit = [(dx / (math.hypot(dx, dy) or 1), dy / (math.hypot(dx, dy) or 1)) for dx, dy in dirs]
        worst = lambda sd: max([vec[sd][0] * ux + vec[sd][1] * uy for ux, uy in unit] or [-1])
        if worst(side) < .5:
            return side
        return min([side] + [x for x in ("right", "left", "above", "below") if x != side], key=worst)

    def boxes(e):
        """Map-unit boxes of a drawn arrow, route or line: small boxes along it, so a label never sits on a stroke
        ("Buôn Ma Thuột" and "Phnôm Pênh" were under arrowheads)."""
        if e.get("type") == "arrow":
            pts = [(e["x1"], e["y1"]), (e["x2"], e["y2"])]
        elif e.get("type") == "line":
            pts = [(e["x1"], e["y1"]), (e["x2"], e["y2"])]
        elif e.get("type") == "polyline":
            pts = [tuple(p_) for p_ in e["points"]]
        else:
            return []
        r = e.get("stroke_width", 4) / 2 + e.get("head_size", 0) * .5 + 2
        out = []
        for (ax, ay), (bx_, by_) in zip(pts, pts[1:]):
            n_ = max(1, int(math.hypot(bx_ - ax, by_ - ay) / max(4.0, 2 * r)))
            out += [(ax + (bx_ - ax) * i / n_ - r, ay + (by_ - ay) * i / n_ - r, ax + (bx_ - ax) * i / n_ + r, ay + (by_ - ay) * i / n_ + r) for i in range(n_ + 1)]
        return out

    def box(e):
        """Map-unit box of a drawn text or circle (text width estimated at .55 em a character)."""
        if e.get("type") == "circle":
            r = e["r"] + e.get("stroke_width", 0)
            return (e["cx"] - r, e["cy"] - r, e["cx"] + r, e["cy"] + r)
        fs_ = e["font_size"]
        tw = .55 * fs_ * len(e["text"])
        x = e["x"] - {"start": 0, "middle": tw / 2, "end": tw}[e.get("anchor", "start")]
        return (x, e["y"] - .8 * fs_, x + tw, e["y"] + .25 * fs_)

    def clear_side(sid, x, y, st, a):
        """The marker's label on the side that covers the fewest other words and rings, never on a line leaving the city;
        the asked side wins a tie."""
        line_ok = away_from_lines(st.city, st.side)
        others = [box(e) for e in els if e.get("type") in ("text", "circle") and e.get("opacity", 1) >= .5 and not e["id"].startswith(sid)]
        others += [b_ for e in els if e.get("type") in ("arrow", "polyline", "line") for b_ in boxes(e)]
        best = None
        for k_, side in enumerate([st.side] + [x_ for x_ in ("right", "left", "above", "below") if x_ != st.side]):
            el = label(sid + "t", x, y, st.text or st.city, side, min(a + 4, span - 2), q.ink, st.size, clear=9 * st.size)
            x0, y0, x1, y1 = box(el)
            hit = sum(max(0, min(x1, u1) - max(x0, u0)) * max(0, min(y1, v1) - max(y0, v0)) for u0, v0, u1, v1 in others)
            score = (side != line_ok and away_from_lines(st.city, side) != side, hit, k_)
            if best is None or score < best[0]:
                best = (score, el)
        return best[1]

    for k, st in enumerate(q.steps):
        if st.kind in ("camera", "footage"):  # layer motion and video, after the drawing
            continue
        a = st.at
        b = max(a + 1, end(a, st.frames))
        col = st.color or q.accent
        sid = f"s{k}"
        if st.kind == "parallel":  # a demarcation follows its land span (the 17th parallel ran along the Bến Hải river, not across the sea)
            w0, w1 = st.lon_range or (view[0], view[2])
            x0, y = proj(st.lat, w0)
            x1, _ = proj(st.lat, w1)
            ls = line_scale(a)
            els.append({"id": sid, "type": "line", "x1": x0, "y1": y, "x2": x1, "y2": y, "stroke": col, "stroke_width": round(4 * ls, 2), "dashed": round(14 * ls, 1),
                        "draw": [a, b], "glow": round(2 * ls, 2)})
            if st.text:
                els.append(label(sid + "t", x1, y, st.text, "right", min(b, span - 2), readable(col), st.size))  # beyond the line's east end
        elif st.kind == "arrow":
            (x0, y0), (x1, y1) = C[st.origin], C[st.to]
            ls = line_scale(a)
            els.append({"id": sid, "type": "arrow", "x1": x0, "y1": y0, "x2": x1, "y2": y1, "stroke": col, "stroke_width": round(9 * ls, 2), "head_size": round(34 * ls, 1),
                        "glow": round(3 * ls, 2), "draw": [a, b], "dashed": round(18 * ls, 1) if st.dashed else 0})
            if st.text:
                els.append(label(sid + "t", (x0 + x1) / 2, (y0 + y1) / 2, st.text, st.side, min(b, span - 2), readable(col), st.size))
        elif st.kind == "route":
            pts = [list(proj(la, lo)) for la, lo in st.points]
            ls = line_scale(a)
            els.append({"id": sid, "type": "polyline", "points": pts, "stroke": col, "stroke_width": round(6 * ls, 2), "glow": round(3 * ls, 2),
                        "dashed": round(12 * ls, 1) if st.dashed else 0, "draw": [a, b]})
            if st.text:
                mx, my = pts[len(pts) // 2]
                els.append(label(sid + "t", mx, my, st.text, st.side, min(b, span - 2), readable(col), st.size))
        elif st.kind == "marker":
            x, y = C[st.city]
            ls = line_scale(a)
            els.append({"id": sid, "type": "circle", "cx": x, "cy": y, "r": round(9 * st.size * ls, 2), "fill": col, "stroke": "#0b0d12", "stroke_width": round(3 * ls, 2),
                        "glow": round(4 * ls, 2), "appear": [a, max(a + 1, end(a, 8))], "ripple": [a, max(a + 1, end(a, max(20, st.frames)))]})
            els.append(clear_side(sid, x, y, st, a))
        else:
            x, y = C[st.city] if st.city in C else proj(st.lat, st.lon)
            if st.kind == "region":
                els.append({**label(sid, x, y, st.text, "above", a, q.ink, 1.9 * st.size, 700), "opacity": .55, "glow": 0,
                            "appear": [a, max(a + 1, end(a, 18))]})
            else:
                els.append(label(sid, x, y, st.text, st.side, a, st.color or q.ink, st.size))
    # Camera: the map layer scales about its top-left corner and translates so each target lands at its focus point on
    # screen; one eased move per camera step. Between moves the camera creeps in (drift) instead of holding: a map that
    # stands still for ten seconds reads as a slide.
    pt = lambda st: C[st.city] if st.city in C else proj(st.lat, st.lon)

    def crept(state, f):
        """The camera `state` (frame, (scale, x, y)) left to creep until frame f: scale grows about the screen centre."""
        f0, (s0, tx0, ty0) = state
        if not q.drift or f <= f0:
            return (s0, tx0, ty0)
        k = 1 + q.drift * (f - f0) / 300
        s1 = s0 * k
        cx, cy = W / 2 - ix * W, H / 2 - iy * H  # the screen centre, in the map box's pixels
        tx1, ty1 = cx - k * (cx - tx0), cy - k * (cy - ty0)
        return (s1, min(0.0, max(inner_w * W * (1 - s1), tx1)), min(0.0, max(inner_h * H * (1 - s1), ty1)))
    scr = lambda x, y, c: (ix * W + c[1] + c[0] * x / VW * inner_w * W, iy * H + c[2] + c[0] * y / VH * inner_h * H)  # viewBox -> px
    held = sorted((st.at, min(span, st.at + st.frames)) for st in q.steps if st.kind == "footage")  # located footage: the map holds

    def creep_to(state, f1):
        """Keys from state (frame, cam) to frame f1: creeping, but holding while located footage is open."""
        f0, c = state
        out = []
        for a, b in held:
            if b <= f0 or a >= f1:
                continue
            if a > f0:
                c = crept((f0, c), a)
                out.append((a, c, "linear"))
            f0 = min(b, f1)
            out.append((f0, c, "linear"))
        if f1 > f0:
            out.append((f1, crept((f0, c), f1), "linear"))
        return out
    states = [(0, (1.0, 0.0, 0.0), "ease_in_out")]
    for st in sorted((st for st in q.steps if st.kind == "camera"), key=lambda st: st.at):
        x, y = pt(st)
        fx, fy = st.focus or (.5, .5)
        tx, ty = fx * W - ix * W - st.zoom * x / VW * inner_w * W, fy * H - iy * H - st.zoom * y / VH * inner_h * H
        # the scaled map keeps covering its own box (a point near the map's edge stops short of its focus instead of
        # pulling the edge, and the black beyond it, into the frame)
        cam = (st.zoom, min(0.0, max(inner_w * W * (1 - st.zoom), tx)), min(0.0, max(inner_h * H * (1 - st.zoom), ty)))
        if st.at > states[-1][0]:  # a step that starts before the previous move ends takes over from where that one lands
            states += creep_to(states[-1][:2], st.at) or [(st.at, states[-1][1], "linear")]
        states.append((max(st.at + 1, end(st.at, st.frames)), cam, "ease_in_out"))
    if q.drift and span - 1 > states[-1][0]:
        states += creep_to(states[-1][:2], span - 1)
    uniq, ease = {}, {}
    for f, c, e_ in states:
        uniq[f], ease[f] = c, e_
    keys = {name: [{"frame": f, "value": round(c[j], 4 if j == 0 else 1), "easing": ease[f]} for f, c in sorted(uniq.items())]
            for name, j in (("scale", 0), ("x", 1), ("y", 2))} if len(uniq) > 1 else {}

    def cam_at(f):  # the camera at a local frame (linear between keys: located footage starts on a settled camera)
        pts = sorted(uniq.items())
        if f <= pts[0][0]:
            return pts[0][1]
        for (g0, c0), (g1, c1_) in zip(pts, pts[1:]):
            if g0 <= f <= g1:
                u = (f - g0) / max(1, g1 - g0)
                return tuple(v0 + (v1 - v0) * u for v0, v1 in zip(c0, c1_))
        return pts[-1][1]
    ops = []
    if q.background:
        ops.append({"op": "upsert_layer", "layer": {"id": q.id + "-bg", "kind": "shape", "start_frame": q.start_frame, "end_frame": q.end_frame,
                                                    "x": 0, "y": 0, "width": 1, "height": 1, "z": q.z - 1, "color": q.background, "attach_shot": q.attach_shot,
                                                    "data": {"shape": "rectangle", "corner_radius": 0}, "effects": [{"name": "fade_in", "end_frame": 8}]}})
    if q.relief_asset:  # the terrain under the outlines, same box and camera
        ops.append({"op": "upsert_layer", "layer": {"id": q.id + "-relief", "kind": "image", "asset_id": q.relief_asset, "start_frame": q.start_frame,
                                                    "end_frame": q.end_frame, "x": round(ix, 4), "y": round(iy, 4), "width": round(inner_w, 4),
                                                    "height": round(inner_h, 4), "z": q.z - 1 if q.z > 0 else 0, "fit": "cover", "attach_shot": q.attach_shot,
                                                    "effects": [{"name": "fade_in", "end_frame": 10},
                                                                {"name": "brightness", "start_frame": 0, "end_frame": 1, "params": {"amount": q.relief_brightness}}],
                                                    **({"anchor": [0, 0], "keyframes": keys} if keys else {})}})
    ops.append({"op": "upsert_layer", "layer": {"id": q.id, "kind": "svg", "start_frame": q.start_frame, "end_frame": q.end_frame,
                                                "x": round(ix, 4), "y": round(iy, 4), "width": round(inner_w, 4), "height": round(inner_h, 4), "z": q.z,
                                                "attach_shot": q.attach_shot, "data": {"view_box": [VW, VH], "elements": els, "font_family": font},
                                                "effects": [{"name": "fade_in", "end_frame": 10}],
                                                **({"anchor": [0, 0], "keyframes": keys} if keys else {})}})
    # Located footage: the leader line draws from the pin (10 frames), the frame grows out of its end (18), the map dims,
    # the caption lands; at the end the frame closes back to the pin (16), or expands to fill the screen (26).
    def words_on_map(a, b, c):  # boxes (screen fractions) of the map's text on screen during [a, b): what a frame must not cover
        boxes = []
        for e in els:
            if e.get("type") != "text" or e.get("opacity", 1) < 1 or e["appear"][0] >= b:
                continue
            x, y = scr(e["x"], e["y"], c)
            fs_ = e["font_size"] * c[0] * inner_w * W / VW
            tw = .55 * fs_ * len(e["text"])
            x = x - {"start": 0, "middle": tw / 2, "end": tw}[e.get("anchor", "start")]
            boxes.append((x / W, (y - .8 * fs_) / H, (x + tw) / W, (y + .25 * fs_) / H))
        return boxes

    def covered(box, boxes):
        x0, y0, x1, y1 = box
        return sum(max(0, min(x1, u1) - max(x0, u0)) * max(0, min(y1, v1) - max(y0, v0)) for u0, v0, u1, v1 in boxes)

    shown = []
    for k, st in enumerate([x for x in q.steps if x.kind == "footage"]):
        a, b = st.at, min(span, st.at + st.frames)
        px, py = scr(*pt(st), cam_at(a))
        fw = st.width
        fh = fw * W / H * 9 / 16
        # the frame opens on the side with more room, level with the pin, unless that covers the map's words (the
        # pin's own label, a neighbour's): then above or below it, then on the other side (round 13: Huế's label cut
        # in half by its own footage)
        boxes, best = words_on_map(a, b, cam_at(a)), None
        near = [bx for bx in boxes if abs((bx[1] + bx[3]) / 2 - py / H) < .12]  # words beside the pin: clear them, not just the pin
        levels = [py / H - fh / 2, py / H - .04 - fh, py / H + .04] + [v for bx in near for v in (bx[1] - .02 - fh - .07, bx[3] + .02)]
        for right in ((px / W < .5), not (px / W < .5)):
            for y0 in levels:
                x0 = min(.97 - fw, px / W + .07) if right else max(.03, px / W - .07 - fw)
                y0 = min(max(.06, y0), .9 - fh)
                score = covered((x0, y0, x0 + fw, y0 + fh + .07), boxes)  # with the caption under it
                if best is None or score < best[0] - 1e-4:
                    best = (score, right, x0, y0)
        _, right, x0, y0 = best
        ax, ay = (0.0 if right else 1.0), min(1.0, max(0.0, (py / H - y0) / fh))
        P = ((x0 + ax * fw) * W, (y0 + ay * fh) * H)  # where the line meets the frame: the pivot it grows from
        fid, A0, A = f"{q.id}-f{k}", q.start_frame + a, q.start_frame + b
        L = b - a - 8 - 1  # the video layer's last local frame (it starts as the line reaches the frame)
        grow = [{"frame": 0, "value": .06, "easing": "linear"}, {"frame": 18, "value": 1, "easing": "ease_out"}]
        if st.expand:
            s_ = 1 / fw
            T = (-(P[0] + s_ * (x0 * W - P[0])), -(P[1] + s_ * (y0 * H - P[1])))
            e0 = L - 26
            fkeys = {"scale": grow + [{"frame": e0, "value": 1, "easing": "linear"}, {"frame": L, "value": round(s_, 4), "easing": "ease_in_out"}],
                     "x": [{"frame": e0, "value": 0, "easing": "linear"}, {"frame": L, "value": round(T[0], 1), "easing": "ease_in_out"}],
                     "y": [{"frame": e0, "value": 0, "easing": "linear"}, {"frame": L, "value": round(T[1], 1), "easing": "ease_in_out"}]}
            leave = b - a - 26  # the line, caption, frame edge and dimming leave as the frame opens
        else:
            c0 = L - 16
            fkeys = {"scale": grow + [{"frame": c0, "value": 1, "easing": "linear"}, {"frame": L, "value": .06, "easing": "ease_in"}],
                     "opacity": [{"frame": 0, "value": 0, "easing": "linear"}, {"frame": 5, "value": 1, "easing": "linear"},
                                 {"frame": c0 + 8, "value": 1, "easing": "linear"}, {"frame": L, "value": 0, "easing": "linear"}]}
            leave = c0 + 8
        ops.append({"op": "upsert_layer", "layer": {"id": fid, "kind": "video", "asset_id": st.asset_id, "source_start": st.source_start,
                                                    "playback_rate": st.playback_rate, "start_frame": A0 + 8, "end_frame": A, "x": round(x0, 4), "y": round(y0, 4),
                                                    "width": round(fw, 4), "height": round(fh, 4), "z": q.z + 8, "fit": "cover", "attach_shot": q.attach_shot,
                                                    "anchor": [ax, round(ay, 4)], "keyframes": fkeys, "frame_sampling": "flow"}})
        # the frame's edge: a light plate 4 px larger behind the video, moving with it about the same pivot; it fades as an
        # expanding frame opens (an effect border would stay on the full picture)
        m_ = 4 / W, 4 / H
        bx, by, bw, bh = x0 - m_[0], y0 - m_[1], fw + 2 * m_[0], fh + 2 * m_[1]
        e_end = leave - 8 + 1  # in the edge's own frames (it starts with the video, 8 frames after the line)
        ops.append({"op": "upsert_layer", "layer": {"id": fid + "-edge", "kind": "shape", "start_frame": A0 + 8, "end_frame": min(A, A0 + 8 + e_end + 1) if st.expand else A,
                                                    "x": round(bx, 5), "y": round(by, 5), "width": round(bw, 5), "height": round(bh, 5), "z": q.z + 7,
                                                    "color": q.ink, "attach_shot": q.attach_shot, "data": {"shape": "rectangle", "corner_radius": 0},
                                                    "anchor": [round((P[0] / W - bx) / bw, 5), round((P[1] / H - by) / bh, 5)],
                                                    "keyframes": {"scale": grow} if st.expand else fkeys,
                                                    "effects": [{"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 28}},
                                                                *([{"name": "fade_out", "start_frame": max(19, e_end - 9), "end_frame": e_end}] if st.expand else [])]}})
        line = [{"id": "pin", "type": "circle", "cx": round(px, 1), "cy": round(py, 1), "r": 9, "fill": q.accent, "stroke": "#0b0d12", "stroke_width": 3,
                 "glow": 10, "appear": [0, 6], "ripple": [0, 30]},
                {"id": "lead", "type": "line", "x1": round(px, 1), "y1": round(py, 1), "x2": round(P[0], 1), "y2": round(P[1], 1), "stroke": q.ink,
                 "stroke_width": 3, "draw": [2, 12]}]
        out_fx = lambda n: [{"name": "fade_in", "start_frame": 0, "end_frame": 6}, {"name": "fade_out", "start_frame": n, "end_frame": n + 10}]
        gone = min(A, A0 + leave + 11)
        ops.append({"op": "upsert_layer", "layer": {"id": fid + "-line", "kind": "svg", "start_frame": A0, "end_frame": gone,
                                                    "x": 0, "y": 0, "width": 1, "height": 1, "z": q.z + 7, "attach_shot": q.attach_shot,
                                                    "data": {"view_box": [W, H], "elements": line}, "effects": out_fx(leave)}})
        ops.append({"op": "upsert_layer", "layer": {"id": fid + "-dim", "kind": "shape", "start_frame": A0, "end_frame": gone,
                                                    "x": 0, "y": 0, "width": 1, "height": 1, "z": q.z + 5, "color": "#000000", "opacity": .38,
                                                    "attach_shot": q.attach_shot, "data": {"shape": "rectangle", "corner_radius": 0},
                                                    "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 12}, {"name": "fade_out", "start_frame": leave, "end_frame": leave + 10}]}})
        if st.caption:
            cy = y0 + fh + .015 if y0 + fh + .07 < .97 else y0 - .065
            ops.append({"op": "upsert_layer", "layer": {"id": fid + "-cap", "kind": "text", "text": st.caption, "start_frame": A0 + 24, "end_frame": gone,
                                                        "x": round(x0, 4), "y": round(cy, 4), "width": round(fw, 4), "height": .05, "z": q.z + 9,
                                                        "typography_role": "label", "color": q.ink, "attach_shot": q.attach_shot, "data": {"align": "left"},
                                                        "effects": out_fx(leave - 24)}})
        shown.append({"step": k, "box": [round(x0, 4), round(y0, 4), round(fw, 4), round(fh, 4)], "pin": [round(px / W, 4), round(py / H, 4)],
                      "plays": [A0 + 8, A], **({"handoff": {"asset_id": st.asset_id, "source_start": round(st.source_start + (L + 1) / FPS * st.playback_rate, 3)}}
                                               if st.expand else {})})
    ends = sorted({min(span - 1, st.at + st.frames + 6) for st in q.steps if st.kind != "footage"} |
                  {min(span - 1, st.at + 40) for st in q.steps if st.kind == "footage"})
    return {"ops": ops, "notes": [], "inspect_frames": [q.start_frame + f for f in ends][:8],
            "measurements": {"view_box": [VW, VH], "map_box": [round(ix, 4), round(iy, 4), round(inner_w, 4), round(inner_h, 4)],
                             "steps": len(q.steps), "footage": shown},
            "verify": "snapshot after each step draws; labels must not cross the coast or each other."}


# ---------------------------------------------------------------- documentary chapter card
class DocChapter(BaseModel):
    """A chapter of a historical documentary: part number, title, years and one line of context, over a dark card or a
    dimmed shot, with a timeline strip that shows where this chapter sits in the whole story (the viewer always knows
    when they are). Each chapter's strip keeps the earlier chapters drawn and grows the current span."""
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["doc_chapter"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    start_frame: int = Field(ge=0)
    end_frame: int
    part: str = Field(default="", max_length=24)          # "PHẦN 3"
    title: str = Field(min_length=1, max_length=48)
    years: str = Field(default="", max_length=24)         # "1965 — 1968"
    context: str = Field(default="", max_length=140)      # one or two short lines; <= ~20 words
    timeline: list[int] = Field(default_factory=list, max_length=2)   # [first year, last year] of the whole film
    span: list[int] = Field(default_factory=list, max_length=2)       # this chapter's [from, to]
    marks: list[int] = Field(default_factory=list, max_length=12)     # labelled years on the strip
    done: list[list[int]] = Field(default_factory=list, max_length=12)  # earlier chapters' spans, already drawn
    card: bool = True            # dark card; False dims the shot under it instead
    accent: str = Field(default="#e8b04a", pattern=HEX)
    ink: str = Field(default="#f4ead8", pattern=HEX)
    attach_shot: str | None = None
    z: int = Field(default=940, ge=0, le=999)

    @model_validator(mode="after")
    def check(self):
        if self.end_frame - self.start_frame < 45:
            raise ValueError("doc_chapter needs at least 45 frames (a title and a line of context must be read)")
        if self.timeline and (len(self.timeline) != 2 or self.timeline[0] >= self.timeline[1]):
            raise ValueError("timeline is [first year, last year]")
        if self.span and (len(self.span) != 2 or not self.timeline or not self.timeline[0] <= self.span[0] <= self.span[1] <= self.timeline[1]):
            raise ValueError("span [from, to] must sit inside timeline")
        if len(self.context.split()) > 24:
            raise ValueError("context over 24 words cannot be read while the card holds")
        need = question_frames(self.context)
        if self.end_frame - self.start_frame < need:
            raise ValueError(f"doc_chapter with this question needs >= {need} frames ({need / FPS:.1f} s): part, years and title for 3 s, "
                             "then the question alone for max(6 s, 1.5 x its reading time + 1 s)")
        return self


def question_frames(context):
    """A chapter card's length for its question (round 13, the owner: text gone before it was read): 3 s for the part,
    years and title, then the question alone for max(6 s, 1.5 x its reading time + 1 s), and the 10-frame exit. Reading
    runs ~2.5 words/s in English and ~3.5 syllable-words/s in Vietnamese (Netflix's 17 characters/s)."""
    w = len(context.split())
    vi = any(ch in "ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ" for ch in context.lower())
    return 75 if not w else QUESTION_AT + int(round(FPS * max(6.0, 1.5 * w / (3.5 if vi else 2.5) + 1))) + 10


QUESTION_AT = 90  # frames: the question enters once the title has settled


def doc_chapter(t, q: DocChapter):
    N = q.end_frame - q.start_frame
    font = _typo(t, "label")["font_id"] if "label" in ((t.get("design") or {}).get("typography") or {}) else None
    base = {"start_frame": q.start_frame, "end_frame": q.end_frame, "attach_shot": q.attach_shot}
    out = lambda n=10: {"name": "fade_out", "start_frame": N - n, "end_frame": N - 1}
    ops = [{"op": "upsert_layer", "layer": {**base, "id": q.id + "-card", "kind": "shape", "x": 0, "y": 0, "width": 1, "height": 1, "z": q.z,
                                            "color": "#0a0b0d", "opacity": 1 if q.card else .62, "data": {"shape": "rectangle", "corner_radius": 0},
                                            "effects": [{"name": "fade_in", "end_frame": 8}, out(12)]}}]

    def text(lid, txt, y, h, role, color, a, fx, track=None):
        e = [{"name": "fade_in", "start_frame": a, "end_frame": a + 8}, out(10), *fx]
        if track is not None:
            e.append({"name": "tracking", "start_frame": a, "end_frame": N - 1, "easing": "linear", "params": {"amount": track, "from_em": track * .5}})
        return {"op": "upsert_layer", "layer": {**base, "id": f"{q.id}-{lid}", "kind": "text", "text": txt, "x": .1, "y": y, "width": .8, "height": h,
                                                "z": q.z + 2, "typography_role": role, "color": color, "data": {"align": "center"}, "effects": e}}
    # beats, one change at a time: part and years (0), the title (15), the question alone once the title has settled
    if q.part:
        ops.append(text("part", q.part, .25, .05, "label", q.accent, 0, [], .3))
    ops.append(text("title", q.title, .31, .14, "headline", q.ink, 15, [{"name": "mask_reveal", "start_frame": 15, "end_frame": 40, "params": {"amount": 110}}]))
    if q.years:
        ops.append(text("years", q.years, .46, .06, "label", q.accent, 4, [], .15))
    if q.context:
        ops.append(text("context", q.context, .55, .12, "caption", "#e6dccb", QUESTION_AT,
                        [{"name": "word_reveal", "start_frame": QUESTION_AT, "end_frame": QUESTION_AT + 30, "params": {"amount": 18}}]))
    if q.timeline and q.span:
        y0, y1 = q.timeline
        VW, VH = 1600.0, 120.0
        X = lambda y: 40 + (y - y0) / (y1 - y0) * (VW - 80)
        els = [{"id": "base", "type": "line", "x1": 40, "y1": 60, "x2": VW - 40, "y2": 60, "stroke": "#5a5f68", "stroke_width": 3, "appear": [0, 8]}]
        for k, (a, b) in enumerate(q.done):
            els.append({"id": f"d{k}", "type": "line", "x1": X(a), "y1": 60, "x2": X(b) if b > a else X(a) + 3, "y2": 60, "stroke": "#b9a27a",
                        "stroke_width": 6, "linecap": "butt", "appear": [0, 8]})
        for k, yr in enumerate(sorted(set(q.marks) | set(q.timeline))):
            els += [{"id": f"m{k}", "type": "line", "x1": X(yr), "y1": 50, "x2": X(yr), "y2": 70, "stroke": "#8a8f98", "stroke_width": 2, "appear": [0, 8]},
                    {"id": f"t{k}", "type": "text", "x": X(yr), "y": 104, "text": str(yr), "font_size": 26, "font_weight": 500, "anchor": "middle",
                     "fill": "#9aa0a8", "stroke": "none", "appear": [0, 8]}]
        a, b = q.span
        els += [{"id": "now", "type": "line", "x1": X(a), "y1": 60, "x2": max(X(b), X(a) + 4), "y2": 60, "stroke": q.accent, "stroke_width": 10,
                 "linecap": "butt", "glow": 8, "draw": [12, 40]},
                {"id": "dot", "type": "circle", "cx": max(X(b), X(a) + 4), "cy": 60, "r": 11, "fill": q.accent, "stroke": "none", "glow": 10,
                 "appear": [38, 44], "ripple": [40, min(N - 2, 90)]}]
        ops.append({"op": "upsert_layer", "layer": {**base, "id": q.id + "-timeline", "kind": "svg", "x": .08, "y": .8, "width": .84, "height": .84 * 1920 / 1080 * VH / VW,
                                                    "z": q.z + 1, "data": {"view_box": [VW, VH], "elements": els, **({"font_family": font} if font else {})},
                                                    "effects": [{"name": "fade_in", "end_frame": 8}, out(10)]}})
    return {"ops": ops, "notes": [], "inspect_frames": [q.start_frame + min(N - 1, 70)],
            "measurements": {"words": len(q.context.split()), "hold_s": round(N / FPS, 2)},
            "verify": "snapshot when the context has revealed; the title, years and strip must read at phone size."}


def _reading_frames(*texts):
    """Frames a viewer needs to read these texts once (3.5 syllable-words/s in Vietnamese, 2.5 words/s in English), and
    never fewer than the review's checks accept (review.reading_frames): the recipes had passed their own rule and
    failed the audit."""
    from .review import reading_frames
    text = " ".join(x for x in texts if x)
    vi = any(ch in "ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ" for ch in text.lower())
    return max(int(round(FPS * len(text.split()) / (3.5 if vi else 2.5))), reading_frames(text, FPS) if text.strip() else 0)


class Figure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float
    decimals: int = Field(default=0, ge=0, le=2)
    prefix: str = Field(default="", max_length=6)
    suffix: str = Field(default="", max_length=14)        # " %", " chiếc", " tỷ USD"
    label: str = Field(min_length=1, max_length=56)       # what it counts
    source: str = Field(min_length=3, max_length=90)      # who counted it: a figure on screen always names its source
    # the picture above the number: ring (a share of 100), icons (one pictogram per `per_icon` units, `highlight` of them
    # in the accent colour), area (circles sized by value, for magnitudes far apart), none; auto picks from the figure
    visual: Literal["auto", "none", "ring", "icons", "area"] = "auto"
    icon: str = Field(default="", max_length=20)          # editvideo.icons name: plane, truck, user, bottle, coin, ...
    per_icon: float = Field(default=1.0, gt=0)
    highlight: float | None = Field(default=None, ge=0)   # units of the count drawn in the accent colour (34 of 81 planes were B-52s)
    scale: float = Field(default=1.0, gt=0)                # the real quantity is value x scale ("3 triệu": value 3, scale 1e6), for area


class DataStory(BaseModel):
    """A sourced figure the narration leaves to the screen (round 13, the owner's team: two numbers a sentence, the rest on
    screen with their source). One to three numbers count up, each with what it counts and who counted it. compare=True
    sets two sources' figures for the same thing side by side under a 'two sources' tag: a contested number is shown as
    contested, never averaged or silently picked."""
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["data_story"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    start_frame: int = Field(ge=0)
    end_frame: int
    title: str = Field(min_length=1, max_length=64)
    figures: list[Figure] = Field(min_length=1, max_length=3)
    # figures: 1-3 counting numbers; grid: figures[0] as a share of 100 squares (a unit chart); bars: a series by year or
    # place (series), figures[0] naming the bar to read and its source
    kind: Literal["figures", "grid", "bars"] = "figures"
    series: list[dict] = Field(default_factory=list, max_length=14)    # bars: [{"label": "1965", "value": 184300}]
    compare: bool = False
    compare_tag: str = Field(default="HAI NGUỒN", max_length=24)
    note: str = Field(default="", max_length=120)          # why the sources differ, or what a figure leaves out
    group: str = Field(default=".", max_length=1)          # thousands separator ("." in Vietnamese, "," in English)
    card: bool = True            # dark card; False dims the shot under it instead
    # footage under the card, darkened and softened, pushing in slowly: {"asset_id", "source_start", "kind": video|image}
    backdrop: dict | None = None
    grid_icon: str = Field(default="", max_length=20)      # grid: person icons (or another pictogram) instead of squares
    accent: str = Field(default="#e8b04a", pattern=HEX)
    ink: str = Field(default="#f4ead8", pattern=HEX)
    attach_shot: str | None = None
    z: int = Field(default=945, ge=0, le=999)

    def need(self):
        last = 15 + 14 * (len(self.figures) - 1) + 36   # the last number has counted up
        if self.kind in ("grid", "bars"):
            last = 15 + 50
        words = _reading_frames(self.title, self.note, *[f.label for f in self.figures], *[f.source for f in self.figures])
        return max(5 * FPS, last + words + 15)

    @model_validator(mode="after")
    def check(self):
        if self.kind == "grid" and not (0 <= self.figures[0].value <= 100 and len(self.figures) == 1):
            raise ValueError("a grid shows one share of 100: one figure between 0 and 100")
        if self.kind == "bars" and (len(self.series) < 2 or any(not isinstance(x.get("value"), (int, float)) or not str(x.get("label", "")).strip()
                                                               for x in self.series)):
            raise ValueError("bars need a series of at least two {label, value}")
        for f in self.figures:
            if f.visual == "icons" and not f.icon:
                raise ValueError("icons need an icon name (editvideo.icons)")
            if f.visual == "icons" and f.value / f.per_icon > 120:
                raise ValueError(f"{f.value:g} at {f.per_icon:g} a pictogram is more than 120 pictograms; raise per_icon")
            if f.visual == "ring" and not 0 <= f.value <= 100:
                raise ValueError("a ring shows a share of 100")
        if self.backdrop is not None and not self.backdrop.get("asset_id"):
            raise ValueError("backdrop needs an asset_id")
        if self.compare and (len(self.figures) != 2 or self.figures[0].source.strip().lower() == self.figures[1].source.strip().lower()):
            raise ValueError("compare sets two figures from two different sources side by side")
        if self.end_frame - self.start_frame < self.need():
            raise ValueError(f"data_story needs >= {self.need()} frames ({self.need() / FPS:.1f} s): every number counted up, then its "
                             "label and source read once")
        return self


def _visual_kind(q, f):
    """The picture a figure gets: what the author asked, or the one its numbers suit."""
    if f.visual != "auto":
        return f.visual
    if "%" in f.suffix and 0 <= f.value <= 100:  # a share is a ring (its icon, if any, inside); 78 coins read as a count
        return "ring"
    if f.icon and f.value / f.per_icon <= 120:
        return "icons"
    vals = [x.value * x.scale for x in q.figures if x.value > 0]
    if len(vals) >= 2 and max(vals) / min(vals) >= 8:
        return "area"
    return "none"


def _illustrated(q):
    return q.kind == "figures" and any(_visual_kind(q, f) != "none" for f in q.figures)


def _arc(cx, cy, r, share):
    """A ring's arc from twelve o'clock, clockwise, over `share` of the circle (an SVG path a `draw` animates)."""
    share = max(0.0, min(.9999, share))
    a = 2 * math.pi * share - math.pi / 2
    x, y = cx + r * math.cos(a), cy + r * math.sin(a)
    return f"M{cx:.1f} {cy - r:.1f}A{r:.1f} {r:.1f} 0 {1 if share > .5 else 0} 1 {x:.1f} {y:.1f}"


def data_story(t, q: DataStory):
    N, n = q.end_frame - q.start_frame, len(q.figures)
    base = {"start_frame": q.start_frame, "end_frame": q.end_frame, "attach_shot": q.attach_shot}
    out = {"name": "fade_out", "start_frame": N - 10, "end_frame": N - 1}

    def layer(lid, kind, x, y, w, h, z, **kw):
        return {"op": "upsert_layer", "layer": {**base, "id": f"{q.id}-{lid}", "kind": kind, "x": round(x, 4), "y": round(y, 4), "width": round(w, 4),
                                                "height": round(h, 4), "z": q.z + z, **kw}}

    def text(lid, txt, x, y, w, h, role, color, a, align="center"):
        return layer(lid, "text", x, y, w, h, 2, text=txt, typography_role=role, color=color, data={"align": align},
                     effects=[{"name": "fade_in", "start_frame": a, "end_frame": a + 8}, out])

    ops = []
    if q.backdrop:  # the picture the figure belongs to stays behind it, dark and soft, still moving
        b = q.backdrop
        ops.append(layer("plate", b.get("kind", "video"), 0, 0, 1, 1, -1, asset_id=b["asset_id"], source_start=float(b.get("source_start", 0.0)), fit="cover",
                         **({"playback_rate": float(b["playback_rate"])} if b.get("playback_rate") else {}),
                         effects=[{"name": "blur", "start_frame": 0, "end_frame": 1, "params": {"amount": 10}},
                                  {"name": "grayscale", "start_frame": 0, "end_frame": 1, "params": {"amount": .6}},
                                  {"name": "zoom_in", "start_frame": 0, "end_frame": N - 1, "params": {"amount": .06}, "easing": "linear"},
                                  {"name": "fade_in", "end_frame": 10}, out]))
    ops += [layer("card", "shape", 0, 0, 1, 1, 0, color="#0a0b0d", opacity=(.8 if q.backdrop else 1) if q.card else .7,
                  data={"shape": "rectangle", "corner_radius": 0}, effects=[{"name": "fade_in", "end_frame": 8}, out]),
            text("title", q.title, .08, .1 if _illustrated(q) else .17, .84, .07, "label", q.accent, 0)]
    if q.kind in ("grid", "bars"):
        f = q.figures[0]
        els = []
        if q.kind == "grid":  # a hundred squares (or pictograms), the share filled one row at a time
            k_on = int(round(f.value))
            from . import icons as _ic
            for i in range(100):
                r_, c_ = divmod(i, 10)
                if q.grid_icon:
                    els += _ic.pictogram(q.grid_icon, 40 + c_ * 62, 40 + r_ * 62, 54, q.accent if i < k_on else "#3a3e46", f"g{i}",
                                         appear=[15 + i // 2, 17 + i // 2])
                else:
                    els.append({"id": f"g{i}", "type": "rect", "x": 40 + c_ * 62, "y": 40 + r_ * 62, "width": 52, "height": 52, "rx": 4,
                                "fill": q.accent if i < k_on else "#2a2d33", "stroke": "none", "appear": [15 + i // 2, 17 + i // 2]})
            ops.append(layer("grid", "svg", .1, .28, .34, .34 * 1920 / 1080, 1, data={"view_box": [700, 700], "elements": els},
                             effects=[{"name": "fade_in", "end_frame": 8}, out]))
            shown = f"{f.prefix}{f.value:,.{f.decimals}f}{f.suffix}".replace(",", q.group)
            big = "display" if _measure(t, "display", shown, 4000)["width"] <= .42 * t["width"] - 48 else "data"  # "hơn 90 %" overflowed
            ops.append(layer("n0", "counter", .5, .34, .42, .16, 2, typography_role=big, color=q.ink,
                             data={"from": 0, "to": f.value, "decimals": f.decimals, "group": q.group, "prefix": f.prefix, "suffix": f.suffix, "align": "left"},
                             effects=[{"name": "progress", "start_frame": 15, "end_frame": 65, "easing": "smooth"},
                                      {"name": "fade_in", "start_frame": 15, "end_frame": 23}, out]))
            ops.append(text("l0", f.label, .5, .52, .42, .12, "caption", q.ink, 40, "left"))
            ops.append(text("s0", f.source, .5, .66, .42, .07, "source", "#b8ad98", 50, "left"))
        else:  # bars: each grows from the base, the named one in the accent colour, its value written over it
            vals = [float(x["value"]) for x in q.series]
            top = max(vals) or 1.0
            W_, H_ = 1600.0, 560.0
            bw = W_ / len(vals)
            for i, (x, v) in enumerate(zip(q.series, vals)):
                h_ = (H_ - 120) * v / top
                hot = str(x["label"]) == f.label or abs(v - f.value) < 1e-9
                a_ = 15 + 3 * i
                els += [{"id": f"b{i}", "type": "rect", "x": i * bw + bw * .18, "y": H_ - 50 - h_, "width": bw * .64, "height": max(1.0, h_),
                         "fill": q.accent if hot else "#6b7480", "stroke": "none", "appear": [a_, a_ + 12]},
                        {"id": f"t{i}", "type": "text", "x": i * bw + bw / 2, "y": H_ - 12, "text": str(x["label"])[:12], "font_size": 30, "font_weight": 500,
                         "anchor": "middle", "fill": "#c9c2b4", "stroke": "none", "appear": [a_, a_ + 10]}]
                if hot:
                    vt = f"{v:,.0f}".replace(",", q.group)
                    els.append({"id": f"v{i}", "type": "text", "x": i * bw + bw / 2, "y": H_ - 64 - h_, "text": vt, "font_size": 40, "font_weight": 600,
                                "anchor": "middle", "fill": q.ink, "stroke": "none", "appear": [a_ + 14, a_ + 24]})
            ops.append(layer("bars", "svg", .08, .3, .84, .84 * 1920 / 1080 * H_ / W_, 1, data={"view_box": [W_, H_], "elements": els},
                             effects=[{"name": "fade_in", "end_frame": 8}, out]))
            ops.append(text("l0", f.label + ((" · " + q.note) if q.note else ""), .08, .76, .84, .06, "caption", q.ink, 40))
            ops.append(text("s0", f.source, .08, .84, .84, .05, "source", "#b8ad98", 50))
        return {"ops": ops, "notes": [], "inspect_frames": [q.start_frame + min(N - 1, 80)],
                "measurements": {"kind": q.kind, "hold_s": round(N / FPS, 2), "need_s": round(q.need() / FPS, 2)},
                "verify": "snapshot after the build: the highlighted share or bar, its label and source must read at phone size."}
    col = .84 / n
    notes, widest = [], 0.0
    pics = _illustrated(q)
    y_num = .45 if pics else .31
    vis_els, vmax = [], max(f_.value * f_.scale for f_ in q.figures) or 1.0

    def icon_fit(f, cw, box_h):
        """(size, cols) of the largest pictogram that lays out f's units in a column."""
        units, best = max(1, int(round(f.value / f.per_icon))), (0, 1)
        for cols in range(1, units + 1):
            rows = -(-units // cols)
            size_ = min((cw - 40) / cols, box_h / rows) * .86
            if size_ > best[0]:
                best = (size_, cols)
        return best
    # one pictogram size across a comparison: sized per column, "26" drew its icons 1.8x larger than "81" beside it
    icon_figs = [f_ for f_ in q.figures if _visual_kind(q, f_) == "icons"]
    shared_icon = min((icon_fit(f_, col * 1920, .25 * 1080 - (34 if f_.per_icon != 1 else 0))[0] for f_ in icon_figs), default=None)
    for k, f in enumerate(q.figures):  # the pictures, in one SVG over the whole frame (1920 x 1080 units)
        kind = _visual_kind(q, f)
        x0p, a = (.08 + k * col) * 1920, 15 + 14 * k
        cw, top, hh = col * 1920, .19 * 1080, .25 * 1080
        cx = x0p + cw / 2
        if kind == "ring":
            r, w_ = hh * .42, hh * .085
            cy = top + hh / 2
            vis_els += [{"id": f"rt{k}", "type": "circle", "cx": cx, "cy": cy, "r": r, "fill": "none", "stroke": "#2c3038", "stroke_width": w_,
                         "appear": [a - 6, a]},
                        {"id": f"ra{k}", "type": "path", "d": _arc(cx, cy, r, f.value / 100), "fill": "none", "stroke": q.accent, "stroke_width": w_,
                         "linecap": "butt", "draw": [a, a + 36]}]
            if f.icon:
                from . import icons as _ic
                vis_els += _ic.pictogram(f.icon, cx - r * .45, cy - r * .45, r * .9, q.ink, f"ri{k}", appear=[a + 30, a + 40])
        elif kind == "icons":
            from . import icons as _ic
            units = max(1, int(round(f.value / f.per_icon)))
            hot = units if f.highlight is None else int(round(f.highlight / f.per_icon))
            box_h = hh - (34 if f.per_icon != 1 else 0)  # the key line sits inside the box, under the pictograms
            size_, cols = icon_fit(f, cw, box_h)
            if shared_icon and size_ > shared_icon:  # the comparison's common size: fewest columns that still fit it
                size_ = shared_icon
                cols = next((c for c in range(1, units + 1) if -(-units // c) * size_ <= box_h * .86 + 1e-6 and c * size_ <= (cw - 40) * .86 + 1e-6), cols)
            gx = cx - cols * size_ / .86 / 2
            for u in range(units):
                r_, c_ = divmod(u, cols)
                at_ = a + int(36 * u / max(1, units))
                vis_els += _ic.pictogram(f.icon, gx + c_ * size_ / .86, top + r_ * size_ / .86, size_, q.accent if u < hot else "#7d8590",
                                         f"u{k}_{u}", appear=[at_, at_ + 4])
            if f.per_icon != 1:
                num = f"{f.per_icon:,.2f}".rstrip("0").rstrip(".").replace(",", "\x00").replace(".", "," if q.group == "." else ".").replace("\x00", q.group)
                key = f"1 biểu tượng = {num} {f.suffix.strip()}".strip()
                vis_els.append({"id": f"key{k}", "type": "text", "x": cx, "y": top + hh + 4, "text": key[:40], "font_size": 26, "font_weight": 400,
                                "anchor": "middle", "fill": "#9aa0a8", "stroke": "none", "appear": [a + 30, a + 40]})
        elif kind == "area":
            rmax = hh * .5
            r = max(3.0, rmax * (f.value * f.scale / vmax) ** .5)
            cy = top + hh - r  # circles stand on one baseline
            el = {"id": f"ar{k}", "type": "circle", "cx": cx, "cy": cy, "r": r, "fill": q.accent, "fill_opacity": .85, "stroke": q.accent,
                  "stroke_width": 2, "appear": [a, a + 24]}
            if r < 12:  # a dot this small needs to be pointed at
                el["ripple"] = [a + 20, a + 80]
            vis_els.append(el)
    if vis_els:
        ops.append(layer("pictures", "svg", 0, 0, 1, 1, 1, data={"view_box": [1920, 1080], "elements": vis_els},
                         effects=[{"name": "fade_in", "end_frame": 8}, out]))
    # a label breaks as the renderer breaks it (its width over the column less 24 px padding each side); the sources sit
    # under the tallest label, so a three-line label no longer runs into its source (audit text_wraps)
    lab = [_measure(t, "caption", f.label, 4000) for f in q.figures]
    lab_h = max(m_["line_px"] * max(1, math.ceil(m_["width"] / ((col - .02) * t["width"] - 48))) for m_ in lab) / t["height"] + .01
    for k, f in enumerate(q.figures):
        x, a = .08 + k * col, 15 + 14 * k
        final = f"{f.prefix}{f.value:,.{f.decimals}f}{f.suffix}".replace(",", "\x00").replace(".", "," if q.group == "." else ".").replace("\x00", q.group)
        role = "display"  # the number as the picture; the lighter data face when the display size would not fit its column
        m = _measure(t, role, final, t["width"])
        if m["width"] / t["width"] > col * .9:
            role, m = "data", _measure(t, "data", final, t["width"])
        widest = max(widest, m["width"] / t["width"])
        if m["width"] / t["width"] > col * .96:
            notes.append(f"figure {k + 1} ({final}) is wider than its column; put the unit in the label or show fewer figures")
        ops.append(layer(f"n{k}", "counter", x, y_num, col, .16, 2, typography_role=role, color=q.ink,
                         data={"from": 0, "to": f.value, "decimals": f.decimals, "group": q.group, "prefix": f.prefix, "suffix": f.suffix, "align": "center"},
                         effects=[{"name": "progress", "start_frame": a, "end_frame": a + 36, "easing": "smooth"},
                                  {"name": "fade_in", "start_frame": a, "end_frame": a + 8}, out]))
        y_lab = y_num + .17
        ops.append(text(f"l{k}", f.label, x + .01, y_lab, col - .02, round(max(.1, lab_h), 4), "caption", q.ink, a + 20))
        ops.append(text(f"s{k}", f.source, x + .01, round(max(y_lab + .12, y_lab + lab_h + .02), 4), col - .02, .07, "source", "#b8ad98", a + 30))
    if q.compare:
        ops.append(text("tag", q.compare_tag, .3, .16 if pics else .27, .4, .05, "label", "#9aa0a8", 10))
        els = [{"id": "div", "type": "line", "x1": 960, "y1": 220 if pics else 340, "x2": 960, "y2": 860 if pics else 700, "stroke": "#5a5f68",
                "stroke_width": 2, "draw": [10, 30]}]
        ops.append(layer("divider", "svg", 0, 0, 1, 1, 1, data={"view_box": [1920, 1080], "elements": els},
                         effects=[{"name": "fade_in", "end_frame": 8}, out]))
    if q.note:
        ops.append(text("note", q.note, .14, .86 if pics else .76, .72, .08, "source", "#9aa0a8", 15 + 14 * n + 30))
    return {"ops": ops, "notes": notes, "inspect_frames": [q.start_frame + min(N - 1, 15 + 14 * n + 50)],
            "measurements": {"figures": n, "hold_s": round(N / FPS, 2), "need_s": round(q.need() / FPS, 2), "widest_figure": round(widest, 3)},
            "verify": "snapshot once every figure has counted up: each number, its label and its source must read at phone size."}


class DocumentHighlight(BaseModel):
    """A passage of a primary document on a paper panel, the sentence that matters underlined as the narration reaches it
    (Roosevelt's 1944 memo, Nixon's letter to Thiệu, the Geneva declaration). The passage is the document's own words,
    in the original or translated with the translation credited; the underline is the edit's only emphasis."""
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["document_highlight"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    start_frame: int = Field(ge=0)
    end_frame: int
    heading: str = Field(min_length=1, max_length=80)      # who wrote to whom, and when
    passage: str = Field(min_length=10, max_length=360)
    highlight: str = Field(min_length=3, max_length=200)   # words of the passage to underline
    source: str = Field(min_length=3, max_length=110)      # archive, collection or publication; translator if translated
    highlight_at: int = Field(default=45, ge=0)            # local frame the underline starts drawing
    # earlier documents of the same correspondence ("16.2.1946 · ĐIỆN"), oldest first: each lands on the pile before
    # this one comes to the top (Hồ Chí Minh wrote to Truman again and again; none was answered)
    stack: list[str] = Field(default_factory=list, max_length=8)
    paper: str = Field(default="#ece3cf", pattern=HEX)
    ink: str = Field(default="#2a2620", pattern=HEX)
    mark: str = Field(default="#c8962e", pattern=HEX)
    attach_shot: str | None = None
    z: int = Field(default=945, ge=0, le=999)

    @model_validator(mode="after")
    def check(self):
        if self.highlight not in self.passage:
            raise ValueError("highlight must be words of the passage, exactly as written")
        if any(not 1 <= len(x) <= 40 for x in self.stack):
            raise ValueError("each earlier document is named in 1-40 characters (date and kind)")
        s0 = self.stack_frames()
        if self.highlight_at < s0 + 20:
            raise ValueError(f"with {len(self.stack)} earlier letters the underline starts at frame {s0 + 20} or later, once the passage is up")
        need = max(self.highlight_at + 30, s0 + _reading_frames(self.heading, self.passage)) + 30  # a citation is glanced at, not read
        if self.end_frame - self.start_frame < need:
            raise ValueError(f"document_highlight needs >= {need} frames ({need / FPS:.1f} s) to read the passage once")
        if self.highlight_at + 30 > self.end_frame - self.start_frame - 15:
            raise ValueError("the underline must finish drawing at least half a second before the panel leaves")
        return self

    def stack_frames(self):
        """Frames the pile takes to land before the passage comes up (8 a letter, a breath after the last)."""
        return 8 * len(self.stack) + 10 if self.stack else 0


def document_highlight(t, q: DocumentHighlight):
    """The passage is laid out line by line here (measured glyphs, so each line is its own text layer and the underline
    sits under the exact words); a line the layout cannot fit is reported, never silently clipped."""
    N, W, H = q.end_frame - q.start_frame, t["width"], t["height"]
    ROLE = "quote"  # the document's words in the light quotation face, large enough to read on a phone
    base = {"start_frame": q.start_frame, "end_frame": q.end_frame, "attach_shot": q.attach_shot}
    out = {"name": "fade_out", "start_frame": N - 10, "end_frame": N - 1}
    px0, pw = .14, .72                                  # the paper panel, centred on the frame once its height is known
    tx, tw = px0 + .045, pw - .09                       # text box inside it
    # lines are broken here, a little narrower than the box (the face's tracking and rounding), and each line's layer is
    # wider than its text, so the renderer never wraps a line a second time over the next one
    m = _measure(t, ROLE, q.passage, tw * W * .95 / (1 + _typo(t, ROLE).get("tracking", 0)))
    lines, line_h = m["lines"], m["line_px"] / H
    ty_label = _typo(t, "label")
    # the label face is letter-spaced and a text box keeps 24 px of padding each side: the heading's lines are its tracked
    # width over the box's inner width, as the renderer (and audit text_wraps) breaks it
    head = _measure(t, "label", q.heading, 4000)
    head_h = head["line_px"] * max(1, math.ceil(head["width"] / (tw * W - 48))) / H
    inner = .05 + head_h + .045 + len(lines) * line_h + .06
    n_st, step = len(q.stack), .034                     # each earlier letter shows a strip above the one on top of it
    room = .8 - n_st * step
    ph = min(room, inner)
    py0 = max(.06 + n_st * step, (1 - ph + n_st * step) / 2 - .03)
    ty0 = py0 + .05 + head_h + .045
    s0 = q.stack_frames()
    notes = []
    if inner > room:
        notes.append(f"passage needs {len(lines)} lines and overflows the panel; shorten it" + (" or the pile" if n_st else ""))
    ops = [{"op": "upsert_layer", "layer": {**base, "id": f"{q.id}-dim", "kind": "shape", "x": 0, "y": 0, "width": 1, "height": 1, "z": q.z,
                                            "color": "#0a0b0d", "opacity": .78, "data": {"shape": "rectangle", "corner_radius": 0},
                                            "effects": [{"name": "fade_in", "end_frame": 10}, out]}},
           {"op": "upsert_layer", "layer": {**base, "id": f"{q.id}-paper", "kind": "shape", "x": px0, "y": py0, "width": pw, "height": round(ph, 4),
                                            "z": q.z + 2, "color": q.paper, "data": {"shape": "rectangle", "corner_radius": 6},
                                            "effects": [{"name": "fade_in", "start_frame": s0, "end_frame": s0 + 12} if s0 else {"name": "fade_in", "end_frame": 12},
                                                        {"name": "shadow", "end_frame": 1, "params": {"amount": 30}}, out]}},
           {"op": "upsert_layer", "layer": {**base, "id": f"{q.id}-head", "kind": "text", "text": q.heading, "x": tx, "y": py0 + .05, "width": tw,
                                            "height": round(head_h + .005, 4), "z": q.z + 4, "typography_role": "label", "color": "#7a6a4e",
                                            "data": {"align": "left"}, "effects": [{"name": "fade_in", "start_frame": s0 + 6, "end_frame": s0 + 14}, out]}}]
    for k, name in enumerate(q.stack):  # the pile: oldest at the back, highest strip; each lands 8 frames after the last
        y = py0 - (n_st - k) * step
        a = 4 + 8 * k
        ops += [{"op": "upsert_layer", "layer": {**base, "id": f"{q.id}-st{k}", "kind": "shape", "x": round(px0 + (n_st - k) * .006, 4), "y": round(y, 4),
                                                 "width": pw, "height": round(ph, 4), "z": q.z + 1, "color": ("#d6ccb5", "#e0d6c0")[k % 2],
                                                 "data": {"shape": "rectangle", "corner_radius": 6},
                                                 "effects": [{"name": "drop", "start_frame": a, "end_frame": a + 7, "params": {"amount": 40}},
                                                             {"name": "fade_in", "start_frame": a, "end_frame": a + 5},
                                                             {"name": "shadow", "end_frame": 1, "params": {"amount": 14}}, out]}},
                {"op": "upsert_layer", "layer": {**base, "id": f"{q.id}-stl{k}", "kind": "text", "text": name, "x": round(px0 + (n_st - k) * .006 + .02, 4),
                                                 "y": round(y + .004, 4), "width": pw - .04, "height": round(step - .006, 4), "z": q.z + 1,
                                                 "typography_role": "source", "color": "#5e5240", "data": {"align": "left"},
                                                 "effects": [{"name": "fade_in", "start_frame": a + 3, "end_frame": a + 8}, out]}}]
    # where the highlighted words fall: character offsets of each laid-out line inside the passage
    space = _measure(t, ROLE, "a a", 4000)["width"] - _measure(t, ROLE, "aa", 4000)["width"]  # a layout trims trailing spaces
    start, spans, pos = q.passage.index(q.highlight), [], 0
    end = start + len(q.highlight)
    for k, ln in enumerate(lines):
        i = q.passage.find(ln, pos)
        i = pos if i < 0 else i
        pos = i + len(ln)
        y = ty0 + k * line_h
        ops.append({"op": "upsert_layer", "layer": {**base, "id": f"{q.id}-line{k}", "kind": "text", "text": ln, "x": tx, "y": round(y, 4), "width": tw + .04,
                                                    "height": round(line_h, 4), "z": q.z + 4, "typography_role": ROLE, "color": q.ink,
                                                    "data": {"align": "left"},
                                                    "effects": [{"name": "fade_in", "start_frame": s0 + 10 + 3 * k, "end_frame": s0 + 20 + 3 * k}, out]}})
        a, b = max(start, i), min(end, i + len(ln))
        if a < b:
            lead = q.passage[i:a]
            pre = (_measure(t, ROLE, lead.rstrip(), 4000)["width"] if lead.strip() else 0.0) + (space if lead.endswith(" ") else 0.0)
            seg = _measure(t, ROLE, q.passage[a:b].strip(), 4000)["width"]
            spans.append((tx * W + pre, y * H + m["line_px"] * .92, seg))
    els = []
    per = max(8, 30 // max(1, len(spans)))
    for k, (x, y, w) in enumerate(spans):
        a = q.highlight_at + k * per
        els.append({"id": f"u{k}", "type": "line", "x1": round(x, 1), "y1": round(y, 1), "x2": round(x + w, 1), "y2": round(y, 1), "stroke": q.mark,
                    "stroke_width": round(m["px"] * .12, 1), "linecap": "round", "draw": [a, a + per]})
    if els:
        ops.append({"op": "upsert_layer", "layer": {**base, "id": f"{q.id}-mark", "kind": "svg", "x": 0, "y": 0, "width": 1, "height": 1, "z": q.z + 3,
                                                    "data": {"view_box": [W, H], "elements": els}, "effects": [out]}})
    ops.append({"op": "upsert_layer", "layer": {**base, "id": f"{q.id}-source", "kind": "text", "text": q.source, "x": px0, "y": round(py0 + ph + .02, 4),
                                                "width": pw, "height": .05, "z": q.z + 4, "typography_role": "source", "color": "#b8ad98",
                                                "data": {"align": "left"}, "effects": [{"name": "fade_in", "start_frame": s0 + 20, "end_frame": s0 + 28}, out]}})
    return {"ops": ops, "notes": notes, "inspect_frames": [q.start_frame + min(N - 1, q.highlight_at + 34)],
            "measurements": {"lines": len(lines), "underlined_lines": len(spans), "stack": n_st, "hold_s": round(N / FPS, 2)},
            "verify": "snapshot after the underline: it must sit under the highlighted words only, and the passage must read at phone size."}


class Bulletin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str = Field(min_length=1, max_length=100)
    source_start: float = Field(default=0.0, ge=0)
    duration: float = Field(gt=.5, le=600)               # seconds of usable picture from source_start
    caption: str = Field(default="", max_length=48)      # place · date, never a network's name or logo


class Night(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=12)       # the date, "18.12"
    value: float | None = Field(default=None, ge=0)       # None: no raid that night, drawn as a gap
    note: str = Field(default="", max_length=32)          # said for a gap night ("ngừng ném bom")


class NightLog(BaseModel):
    """A campaign counted night by night in a corner of the picture (round 13: the twelve days and nights of December
    1972, B-52 sorties per night as the US Air Force counted them): one bar a night, the night on screen in the accent
    colour with its date and number written out, the nights before it grey, the nights to come as outlines. The caller
    says when each night begins (local frames), so the ledger follows the edit, not a clock; the source is always on."""
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["night_log"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    start_frame: int = Field(ge=0)
    end_frame: int
    title: str = Field(min_length=1, max_length=40)
    unit: str = Field(min_length=1, max_length=20)        # "lượt B-52"
    nights: list[Night] = Field(min_length=2, max_length=31)
    at: list[int]                                         # local frame each night becomes the one on screen
    source: str = Field(min_length=3, max_length=60)
    total: bool = True                                    # the last night also writes the campaign's sum
    corner: Literal["top_right", "top_left"] = "top_right"
    top: float = Field(default=.055, ge=0, le=.7)         # below a letterbox bar (.128) when the sequence has one
    accent: str = Field(default="#e8b04a", pattern=HEX)
    ink: str = Field(default="#f2ece0", pattern=HEX)
    z: int = Field(default=900, ge=0, le=990)
    attach_shot: str | None = None

    @model_validator(mode="after")
    def check(self):
        N = self.end_frame - self.start_frame
        if len(self.at) != len(self.nights):
            raise ValueError("at: one start frame for every night")
        if any(b <= a for a, b in zip(self.at, self.at[1:])) or self.at[0] < 0 or self.at[-1] > N - 45:
            raise ValueError("at must rise, start inside the span and leave the last night at least 1.5 s on screen")
        if all(n.value is None for n in self.nights):
            raise ValueError("a night log needs at least one counted night")
        return self


def night_log(t, q: NightLog):
    N, W = q.end_frame - q.start_frame, t["width"]
    base = {"attach_shot": q.attach_shot}
    H = t["height"]
    x0, y0, w = (.66 if q.corner == "top_right" else .04), q.top, .30
    # stacked without overlap: title, bars, the night's line (two lines kept for the sum), the source (audit text_boxes_overlap)
    lh = _measure(t, "caption", "ĐÊM 12 · 29.12", 4000)["line_px"] / H
    y_b, hb = y0 + .056, .085
    y_l = y_b + hb + .012
    y_s = y_l + 2 * lh + .016
    h = y_s + .03 + .012 - y0
    top = max(n.value or 0 for n in q.nights)
    n = len(q.nights)
    VW = 600.0
    VH = round(VW * hb * H / ((w - .03) * W), 2)
    bw = VW / n
    out = lambda d: {"name": "fade_out", "start_frame": d - 8, "end_frame": d - 1}
    span = lambda a, b: {**base, "start_frame": q.start_frame + a, "end_frame": q.start_frame + b}
    ops = [{"op": "upsert_layer", "layer": {**span(0, N), "id": f"{q.id}-bg", "kind": "shape", "x": x0, "y": y0, "width": w, "height": h, "z": q.z,
                                            "color": "#0a0b0d", "opacity": .66, "data": {"shape": "rectangle", "corner_radius": 6},
                                            "effects": [{"name": "fade_in", "end_frame": 10}, out(N)]}},
           {"op": "upsert_layer", "layer": {**span(0, N), "id": f"{q.id}-title", "kind": "text", "text": q.title, "x": x0 + .015, "y": y0 + .012,
                                            "width": w - .03, "height": .036, "z": q.z + 2, "typography_role": "label", "color": q.accent,
                                            "data": {"align": "left"}, "effects": [{"name": "fade_in", "start_frame": 4, "end_frame": 12}, out(N)]}},
           {"op": "upsert_layer", "layer": {**span(0, N), "id": f"{q.id}-src", "kind": "text", "text": q.source, "x": x0 + .015, "y": round(y_s, 4),
                                            "width": w - .03, "height": .03, "z": q.z + 2, "typography_role": "source", "color": "#b8ad98",
                                            "data": {"align": "left"}, "effects": [{"name": "fade_in", "start_frame": 8, "end_frame": 16}, out(N)]}}]
    if _measure(t, "source", q.source, 4000)["width"] > (w - .03) * W - 48:  # one line under the bars, or it runs into them
        raise ValueError("night_log source does not fit one line of the panel; shorten it")
    counted, notes = 0.0, []
    for i, night in enumerate(q.nights):
        a, b = q.at[i], (q.at[i + 1] if i + 1 < n else N)
        d = b - a
        if d < 40:
            notes.append(f"night {i + 1} is on screen {d / FPS:.1f} s: its line may not be read")
        counted += night.value or 0
        els = []
        for j, other in enumerate(q.nights):
            x = j * bw + bw * .18
            if other.value is None:
                els.append({"id": f"p{j}", "type": "line", "x1": x, "y1": VH - 6, "x2": x + bw * .64, "y2": VH - 6, "stroke": "#6b7480", "stroke_width": 4})
                continue
            bh = max(3.0, (VH - 20) * other.value / top)
            if j < i:
                els.append({"id": f"b{j}", "type": "rect", "x": x, "y": VH - bh, "width": bw * .64, "height": bh, "fill": "#7d8590", "stroke": "none"})
            elif j == i:
                els.append({"id": f"b{j}", "type": "rect", "x": x, "y": VH - bh, "width": bw * .64, "height": bh, "fill": q.accent, "stroke": "none",
                            "appear": [0, 8]})
            else:
                els.append({"id": f"b{j}", "type": "rect", "x": x, "y": VH - bh, "width": bw * .64, "height": bh, "fill": "none",
                            "stroke": "#59606a", "stroke_width": 2})
        last = i == n - 1
        line = (f"{night.label} · {night.note}" if night.value is None else
                f"ĐÊM {i + 1} · {night.label} · {night.value:,.0f} {q.unit}".replace(",", "."))
        if last and q.total:
            line += f"\nTỔNG · {counted:,.0f} {q.unit}".replace(",", ".")
        ops += [{"op": "upsert_layer", "layer": {**span(a, b), "id": f"{q.id}-bars{i}", "kind": "svg", "x": x0 + .015, "y": round(y_b, 4), "width": w - .03,
                                                 "height": hb, "z": q.z + 1, "data": {"view_box": [VW, VH], "elements": els},
                                                 "effects": [out(N - a)] if last else []}},
                {"op": "upsert_layer", "layer": {**span(a, b), "id": f"{q.id}-line{i}", "kind": "text", "text": line, "x": x0 + .015, "y": round(y_l, 4),
                                                 "width": w - .03, "height": round(lh * (2 if last and q.total else 1) + .008, 4), "z": q.z + 2, "typography_role": "caption",
                                                 "color": q.ink, "data": {"align": "left"},
                                                 "effects": [{"name": "fade_in", "end_frame": 5}] + ([out(N - a)] if last else [])}}]
    return {"ops": ops, "notes": notes, "inspect_frames": [q.start_frame + q.at[min(2, n - 1)] + 12, q.start_frame + N - 20],
            "measurements": {"nights": n, "counted": counted, "hold_s": round(N / FPS, 2)},
            "verify": "snapshot two nights: the current bar in the accent colour, its line readable at phone size, clear of the picture's own captions."}


class CredibilityGap(BaseModel):
    """What was said, against what the record shows (round 13: Washington's 4 August 1964 announcement of a second attack
    in the Gulf of Tonkin, against the NSA history declassified in 2005). The claim's own footage fills the frame under its
    date and words; then it keeps playing on the left half while the record wipes in on the right with its source. Both
    sides are quoted or closely paraphrased and credited; the recipe draws no conclusion of its own. Archive of the claim
    often comes in short shots (a 1964 newsreel cut every 2-5 s), so the claim is a list of clips played in turn, each no
    longer than it holds."""
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["credibility_gap"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    start_frame: int = Field(ge=0)
    end_frame: int
    claim_clips: list[Bulletin] = Field(min_length=1, max_length=6)   # the claim's footage, played one after another
    claim_label: str = Field(min_length=1, max_length=40)     # "LỜI CÔNG BỐ · 4.8.1964"
    claim: str = Field(min_length=3, max_length=120)
    record_label: str = Field(min_length=1, max_length=40)    # "HỒ SƠ GIẢI MẬT · 2005"
    record: str = Field(min_length=3, max_length=170)
    source: str = Field(min_length=3, max_length=110)
    split_at: int = Field(default=75, ge=30)                  # local frame the record comes in
    accent: str = Field(default="#e8b04a", pattern=HEX)
    z: int = Field(default=930, ge=0, le=990)
    attach_shot: str | None = None

    @model_validator(mode="after")
    def check(self):
        N = self.end_frame - self.start_frame
        if self.split_at < _reading_frames(self.claim_label, self.claim) * .7:
            raise ValueError("the claim must be on screen long enough to be read before the record comes in")
        if N - self.split_at < _reading_frames(self.record_label, self.record) + 30:
            raise ValueError(f"credibility_gap needs {_reading_frames(self.record_label, self.record) + 30} frames after split_at: "
                             "the record read once, beside the claim")
        return self


def credibility_gap(t, q: CredibilityGap):
    N, S = q.end_frame - q.start_frame, q.split_at
    base = {"attach_shot": q.attach_shot}
    span = lambda a, b: {**base, "start_frame": q.start_frame + a, "end_frame": q.start_frame + b}
    out = lambda d: {"name": "fade_out", "start_frame": d - 10, "end_frame": d - 1}

    def text(lid, a, b, txt, x, y, w, h, role, color, fx=None):
        return {"op": "upsert_layer", "layer": {**span(a, b), "id": f"{q.id}-{lid}", "kind": "text", "text": txt, "x": x, "y": y, "width": w, "height": h,
                                                "z": q.z + 3, "typography_role": role, "color": color, "data": {"align": "left"},
                                                "effects": fx or [{"name": "fade_in", "end_frame": 8}, out(b - a)]}}
    shade = {"shape": "rectangle", "corner_radius": 0}
    ops, f, k = [], 0, 0
    while f < N:  # the claim's clips in turn, full frame until the split, then on the left half
        c = q.claim_clips[k % len(q.claim_clips)]
        seg = min(N - f, max(12, int((c.duration - .1) * FPS)))
        for a, b in ((f, min(f + seg, S)), (max(f, S), f + seg)):
            if b - a < 1:
                continue
            half = a >= S
            ops.append({"op": "upsert_layer", "layer": {**span(a, b), "id": f"{q.id}-claim{k}" + ("h" if half else ""), "kind": "video", "asset_id": c.asset_id,
                                                        "source_start": round(c.source_start + (a - f) / FPS, 3), "x": 0, "y": 0, "width": .5 if half else 1,
                                                        "height": 1, "z": q.z, "fit": "cover"}})
        f += seg
        k += 1
    ops += [{"op": "upsert_layer", "layer": {**span(0, N), "id": f"{q.id}-scrim", "kind": "shape", "x": 0, "y": .5, "width": .5, "height": .5, "z": q.z + 1,
                                            "color": "#000000", "opacity": .55, "data": shade, "effects": [{"name": "fade_in", "end_frame": 8}, out(N)]}},
           text("claim-label", 6, N, q.claim_label, .04, .6, .42, .045, "label", q.accent),
           text("claim-text", 10, N, q.claim, .04, .66, .42, .2, "caption", "#f4efe6"),
           {"op": "upsert_layer", "layer": {**span(S, N), "id": f"{q.id}-panel", "kind": "shape", "x": .5, "y": 0, "width": .5, "height": 1, "z": q.z + 1,
                                            "color": "#0d0e10", "data": shade,
                                            "effects": [{"name": "wipe_right", "start_frame": 0, "end_frame": 12, "easing": "ease_out"}, out(N - S)]}},
           {"op": "upsert_layer", "layer": {**span(S + 8, N), "id": f"{q.id}-seam", "kind": "shape", "x": .4985, "y": 0, "width": .003, "height": 1, "z": q.z + 2,
                                            "color": q.accent, "data": shade, "effects": [{"name": "fade_in", "end_frame": 4}, out(N - S - 8)]}},
           text("record-label", S + 12, N, q.record_label, .54, .3, .42, .045, "label", q.accent),
           text("record-text", S + 16, N, q.record, .54, .37, .42, .3, "quote", "#f4efe6"),
           text("source", S + 24, N, q.source, .54, .8, .42, .08, "source", "#b8ad98")]
    return {"ops": ops, "notes": [], "inspect_frames": [q.start_frame + S - 10, q.start_frame + min(N - 1, S + 60)],
            "measurements": {"claim_s": round(S / FPS, 2), "record_s": round((N - S) / FPS, 2)},
            "verify": "snapshot before and after the split: the claim legible over its footage, the record and its source legible on the panel."}


class NewsMontage(BaseModel):
    """Archival news as the chorus of a documentary (round 13, rebuilt after the owner found the first version "broken,
    ugly, not like the films"; measured on five reference sequences). Three movements:
    1. the TV set: one period television fills the frame (cabinet, cream bezel, rounded glass), the camera pushing in
       5 %; two or three bulletins play in the glass with a burst of static between them and a place · date line;
    2. the flood: the bulletins leave the set and fill the frame, each cut shorter (1.8 s x 0.86^k, never under 0.4 s),
       a black slanted wedge carrying the place on every other cut;
    3. the stop: the last picture held, all sound cut at the hold, then black.
    No ticker, no title, no network logo or style is imitated; real footage only. Returns the movements' frames so
    the caller stacks the sound (the bulletins' own voices, static, a pulse that quickens, silence at the hold)."""
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["news_montage"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    start_frame: int = Field(ge=0)
    end_frame: int
    bulletins: list[Bulletin] = Field(min_length=3, max_length=16)
    tv_share: float = Field(default=.35, ge=.2, le=.6)      # of the time before the stop
    tv_clips: int = Field(default=3, ge=1, le=4)
    hold_s: float = Field(default=2.2, ge=.8, le=4)
    black_s: float = Field(default=1.4, ge=0, le=3)
    static_asset: str | None = None                          # a noise clip for the bursts between bulletins on the set
    wedge: bool = True
    ink: str = Field(default="#ede6d6", pattern=HEX)
    z: int = Field(default=930, ge=0, le=999)

    @model_validator(mode="after")
    def check(self):
        N = self.end_frame - self.start_frame
        need = int((5.0 + 3.5 + self.hold_s + self.black_s) * FPS)
        if N < need:
            raise ValueError(f"news_montage needs >= {need} frames: the set, the flood, the held stop and the black")
        return self


def news_montage(t, q: NewsMontage):
    N = q.end_frame - q.start_frame
    hold, black = int(q.hold_s * FPS), int(q.black_s * FPS)
    body = N - hold - black
    tvN = int(body * q.tv_share)
    A = lambda f: q.start_frame + f

    def L(lid, kind, a, b, x, y, w, h, z, **kw):
        return {"op": "upsert_layer", "layer": {"id": f"{q.id}-{lid}", "kind": kind, "start_frame": A(a), "end_frame": A(b), "x": round(x, 4),
                                                "y": round(y, 4), "width": round(w, 4), "height": round(h, 4), "z": q.z + z, **kw}}
    grade = [{"name": "saturate", "start_frame": 0, "end_frame": 1, "params": {"amount": .7}},
             {"name": "warm", "start_frame": 0, "end_frame": 1, "params": {"amount": .12}},
             {"name": "contrast", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.08}}]
    ops = [L("bg", "shape", 0, N, 0, 0, 1, 1, 0, color="#050403", data={"shape": "rectangle", "corner_radius": 0})]
    screens, nxt = [], 0
    # 1. the set: a null carries the push-in; cabinet, bezel, glass, controls and the footage are its children
    rig = f"{q.id}-rig"
    ops.append(L("rig", "null", 0, tvN, 0, 0, 1, 1, 1, effects=[{"name": "zoom_in", "start_frame": 0, "end_frame": max(1, tvN - 1), "easing": "linear",
                                                                     "params": {"amount": .05}}]))
    kid = {"parent": rig}
    gx, gy, gw, gh = .15, .11, .6, .78
    ops += [L("cabinet", "shape", 0, tvN, .08, .03, .84, .94, 2, color="#2a1d14", data={"shape": "rectangle", "corner_radius": 36},
              effects=[{"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 40}}], **kid),
            L("bezel", "shape", 0, tvN, .12, .07, .66, .86, 3, color="#d6cbb2", data={"shape": "rectangle", "corner_radius": 48}, **kid),
            L("glassbg", "shape", 0, tvN, gx, gy, gw, gh, 4, color="#0e1012", data={"shape": "rectangle", "corner_radius": 60}, **kid),
            L("panel", "shape", 0, tvN, .80, .12, .09, .76, 3, color="#3a2a1e", data={"shape": "rectangle", "corner_radius": 14}, **kid),
            L("knobs", "svg", 0, tvN, .80, .12, .09, .76, 4, data={"view_box": [173, 821], "elements": [  # the box's own pixel size
                {"id": "k1", "type": "circle", "cx": 86, "cy": 160, "r": 40, "fill": "#c9bfa6", "stroke": "#1a120c", "stroke_width": 5},
                {"id": "k2", "type": "circle", "cx": 86, "cy": 280, "r": 32, "fill": "#c9bfa6", "stroke": "#1a120c", "stroke_width": 5},
                {"id": "grille", "type": "rect", "x": 30, "y": 420, "width": 113, "height": 330, "rx": 8, "fill": "#24190f", "stroke": "none"}]}, **kid)]
    burst = 15 if q.static_asset else 0
    f, k = 0, 0
    lengths = [3.5, 2.5] + [2.5] * 4
    while f < tvN - 12 and k < q.tv_clips:
        bl = q.bulletins[nxt % len(q.bulletins)]
        nxt += 1
        last = k == q.tv_clips - 1
        seg = min(tvN - f if last else int(lengths[k] * FPS), int((bl.duration - .1) * FPS))
        seg = max(12, seg)
        ops.append(L(f"tv{k}", "video", f, f + seg, gx, gy, gw, gh, 5, asset_id=bl.asset_id, source_start=round(bl.source_start, 3), fit="cover",
                     effects=[*grade, {"name": "blur", "start_frame": 0, "end_frame": 1, "params": {"amount": .7}},
                              {"name": "rounded", "start_frame": 0, "end_frame": 1, "params": {"amount": 60}},
                              {"name": "vignette", "start_frame": 0, "end_frame": 1, "params": {"amount": .5}}], **kid))
        screens.append({"id": f"{q.id}-tv{k}", "asset_id": bl.asset_id, "source_start": bl.source_start, "start": A(f), "end": A(f + seg), "mode": "tv"})
        if bl.caption:
            ops.append(L(f"tvcap{k}", "text", f + 6, f + seg, gx + .02, gy + gh - .1, gw - .04, .05, 7, text=bl.caption.upper(), typography_role="label",
                         color=q.ink, data={"align": "center", "same_subject": True},
                         effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 6},
                                  {"name": "text_outline", "start_frame": 0, "end_frame": 1, "params": {"amount": 2, "color": "#0b0b0b"}}], **kid))
        f += seg
        if burst and f < tvN - 12 and k < q.tv_clips - 1:  # a burst of static between two bulletins
            ops.append(L(f"static{k}", "video", f, f + burst, gx, gy, gw, gh, 6, asset_id=q.static_asset, source_start=0.0, fit="cover",
                         effects=[{"name": "rounded", "start_frame": 0, "end_frame": 1, "params": {"amount": 60}}], **kid))
            f += burst
        k += 1
    tv_end = min(tvN, max(f, 1))
    ops.append(L("glare", "svg", 0, tvN, gx, gy, gw, gh, 8, blend="screen", data={"view_box": [1152, 842], "elements": [
        {"id": "g1", "type": "path", "d": "M77 43 C 384 11 806 22 1075 65 L 1075 216 C 730 162 346 173 77 248 Z", "fill": "#ffffff", "fill_opacity": .06,
         "stroke": "none"}]}, **kid))
    # 2. the flood: full frame, each cut shorter, a black wedge carrying the place on every other cut
    f, k = tv_end, 0
    flood_end = body
    while f < flood_end - 6:
        bl = q.bulletins[nxt % len(q.bulletins)]
        nxt += 1
        want = max(12, int(max(.4, 1.8 * .86 ** k) * FPS))
        seg = min(want, flood_end - f, int((bl.duration - .1) * FPS))
        if seg < 8:
            break
        ops.append(L(f"fl{k}", "video", f, f + seg, 0, 0, 1, 1, 10, asset_id=bl.asset_id, source_start=round(bl.source_start, 3), fit="cover",
                     effects=list(grade)))
        screens.append({"id": f"{q.id}-fl{k}", "asset_id": bl.asset_id, "source_start": bl.source_start, "start": A(f), "end": A(f + seg), "mode": "flood"})
        if q.wedge and k % 2 == 0 and seg >= 18:
            left = k % 4 == 0
            pts = [[0, 0], [768, 0], [614, 1080], [0, 1080]] if left else [[1920, 0], [1152, 0], [1306, 1080], [1920, 1080]]
            ops.append(L(f"wedge{k}", "svg", f, f + seg, 0, 0, 1, 1, 11, data={"view_box": [1920, 1080], "elements": [
                {"id": "w", "type": "path", "d": "M" + " L".join(f"{x} {y}" for x, y in pts) + " Z", "fill": "#050403", "stroke": "none"}]}))
            if bl.caption and seg >= 45:  # a place on the wedge is read: 1.5 s at least, as the references hold theirs
                ops.append(L(f"wcap{k}", "text", f + 2, f + seg, .03 if left else .67, .44, .29, .11, 12, text=bl.caption.upper(), typography_role="label",
                             color=q.ink, data={"align": "left" if left else "right", "same_subject": True}))
        f += seg
        k += 1
    # 3. the stop: the last picture held (its own frames, not a freeze), then black under the bg
    hb = max(q.bulletins, key=lambda b_: b_.duration)
    seg = min(hold, int((hb.duration - .1) * FPS))
    ops.append(L("hold", "video", body, body + seg, 0, 0, 1, 1, 10, asset_id=hb.asset_id, source_start=round(hb.source_start, 3), fit="cover",
                 effects=[*grade, {"name": "fade_out", "start_frame": max(0, seg - 8), "end_frame": seg - 1}]))
    phases = {"tv": [A(0), A(tv_end)], "flood": [A(tv_end), A(body)], "hold": [A(body), A(body + seg)], "black": [A(body + seg), A(N)]}
    return {"ops": ops, "notes": [], "inspect_frames": [A(tv_end // 2), A((tv_end + body) // 2), A(body + 10)], "phases": phases, "screens": screens,
            "measurements": {"tv_s": round(tv_end / FPS, 2), "flood_s": round((body - tv_end) / FPS, 2), "flood_cuts": k,
                             "hold_s": round(seg / FPS, 2), "black_s": round((N - body - seg) / FPS, 2)},
            "verify": "snapshot each movement: the set's glass and its caption, the flood's wedge label, the held stop; no ticker, no logo."}


from .montage import ArchiveMontage, archive_montage  # noqa: E402  (the blockbuster archive montage, its own module)
from .montage_forms import MapMatte, map_matte, Dossier, dossier  # noqa: E402  (its map and dossier forms)

RECIPES = {"kinetic_title": KineticTitle, "text_behind_subject": TextBehindSubject, "photo_3d": Photo3D, "trajectory_3d": Trajectory3D,
           "map_journey": MapJourney, "film_finish": FilmFinish, "history_map": HistoryMap, "doc_chapter": DocChapter,
           "data_story": DataStory, "document_highlight": DocumentHighlight, "news_montage": NewsMontage, "night_log": NightLog,
           "credibility_gap": CredibilityGap, "archive_montage": ArchiveMontage, "map_matte": MapMatte, "dossier": Dossier}


def compose(pid, base_revision, request, dry_run=False):
    name = (request or {}).get("recipe")
    if name not in RECIPES:
        raise ValueError(f"recipe must be one of {sorted(RECIPES)}")
    q = RECIPES[name].model_validate(request)
    t = _timeline(pid, base_revision)
    if name == "kinetic_title":
        r = kinetic_title(t, q)
    elif name == "text_behind_subject":
        r = text_behind_subject(t, pid, q)
    elif name == "photo_3d":
        r = photo_3d(t, pid, q)
    elif name == "trajectory_3d":
        r = trajectory_3d(t, q)
    elif name == "map_journey":
        r = map_journey(t, q)
    elif name == "history_map":
        r = history_map(t, q)
    elif name == "doc_chapter":
        r = doc_chapter(t, q)
    elif name == "data_story":
        r = data_story(t, q)
    elif name == "document_highlight":
        r = document_highlight(t, q)
    elif name == "news_montage":
        r = news_montage(t, q)
    elif name == "night_log":
        r = night_log(t, q)
    elif name == "credibility_gap":
        r = credibility_gap(t, q)
    elif name == "archive_montage":
        r = archive_montage(t, q)
    elif name == "map_matte":
        r = map_matte(t, q, pid)
    elif name == "dossier":
        r = dossier(t, pid, q)
    else:
        r = film_finish(t, q)
    r["revision"] = _apply(pid, base_revision, r["ops"], dry_run)
    r["recipe"] = name
    r["dry_run"] = dry_run
    if dry_run:
        # Audit the would-be timeline so geometry/label/camera risks show up before anything is written.
        from .review import audit_timeline
        future = preview_ops(t, r["ops"])
        touched = {op["layer"]["id"] for op in r["ops"] if op["op"] == "upsert_layer"} | {op.get("shot_id") for op in r["ops"] if op["op"] == "update_shot"}
        found = audit_timeline(pid, future)["findings"]
        r["audit"] = [f for f in found if touched & set(_ids(f["where"]))]
    else:
        r.pop("ops")
    return r


def _ids(where):
    out = []
    for k in ("layer", "shot", "object"):
        if isinstance(where.get(k), str):
            out.append(where[k])
    for k in ("layers", "shots"):
        out += [x for x in where.get(k, []) if isinstance(x, str)]
    return out


def preview_ops(t, ops):
    """Apply recipe operations to a copy of the timeline (no validation, nothing persisted)."""
    import copy
    data = copy.deepcopy(t)
    for op in ops:
        if op["op"] == "upsert_layer":
            data["layers"] = [l for l in data["layers"] if l["id"] != op["layer"]["id"]] + [copy.deepcopy(op["layer"])]
        elif op["op"] == "delete_layer":
            data["layers"] = [l for l in data["layers"] if l["id"] != op["id"]]
        elif op["op"] == "set_design":
            data["design"] = {**(data.get("design") or {}), **copy.deepcopy(op["design"])}
        elif op["op"] == "update_shot":
            for sh in data["shots"]:
                if sh["id"] == op["shot_id"]:
                    sh.update(copy.deepcopy(op["changes"]))
    return data
