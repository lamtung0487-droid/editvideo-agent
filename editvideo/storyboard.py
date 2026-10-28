"""Storyboard: one plan for the whole film, validated, persisted and checked against the timeline.

Film level: message (one sentence the film must prove), arc, audience, mood. Direction block: ground/ink/accent
colours, reveal rule, hold rule, exactly one breather, negative list. Per frame: time range, type, persuasion
device, emotional beat, the one focal element, roles, reveal times and the technique carrying it. A callback motif
is planted early and returns changed. check() reports where the timeline drifts from the plan (missing reveals,
gaps, techniques with no matching layers, negative-list violations, a breather that is not the calmest frame).
"""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store, agent

FPS = 30


class Reveal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at_s: float = Field(ge=0)
    what: str = Field(min_length=1, max_length=200)
    layer_id: str | None = None


class Roles(BaseModel):
    model_config = ConfigDict(extra="forbid")
    foreground: str = Field(default="", max_length=200)
    supporting: str = Field(default="", max_length=300)
    background: str = Field(default="", max_length=200)


class Frame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    type: Literal["hook", "context", "evidence", "benefit", "turn", "climax", "payoff", "cta", "breather", "other"] = "other"
    persuasion: str = Field(default="", max_length=200)
    beat: str = Field(default="", max_length=200)
    focal: str = Field(min_length=1, max_length=200)
    roles: Roles = Field(default_factory=Roles)
    reveals: list[Reveal] = Field(default_factory=list, max_length=20)
    technique: str | None = None


class DirectionBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ground: str = Field(default="", pattern=r"^(#[0-9a-fA-F]{6})?$")
    ink: str = Field(default="", pattern=r"^(#[0-9a-fA-F]{6})?$")
    accent: str = Field(default="", pattern=r"^(#[0-9a-fA-F]{6})?$")
    reveal_rule: str = Field(default="elements arrive on narration cues (timestamps when silent)", max_length=300)
    hold_rule: Literal["still", "ambient"] = "ambient"
    breather_frame: str | None = None
    negative: list[str] = Field(default_factory=list, max_length=20)


class Callback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motif: str = Field(min_length=1, max_length=200)
    plant_frame: str
    return_frame: str
    layer_ids: list[str] = Field(default_factory=list, max_length=10)


class Storyboard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=3, max_length=300)
    arc: list[str] = Field(min_length=1, max_length=12)
    audience: str = Field(min_length=1, max_length=300)
    mood: str = Field(min_length=1, max_length=120)
    direction_id: str | None = None
    direction_block: DirectionBlock = Field(default_factory=DirectionBlock)
    frames: list[Frame] = Field(min_length=1, max_length=40)
    callback: Callback | None = None

    @model_validator(mode="after")
    def consistent(self):
        ids = [f.id for f in self.frames]
        if len(set(ids)) != len(ids):
            raise ValueError("frame ids must be unique")
        for a, b in zip(self.frames, self.frames[1:]):
            if b.start_s < a.end_s - 1e-6:
                raise ValueError(f"frames overlap: {a.id} and {b.id}")
        for f in self.frames:
            if f.end_s <= f.start_s:
                raise ValueError(f"frame {f.id} has an empty range")
            if any(not f.start_s - .01 <= r.at_s <= f.end_s + .01 for r in f.reveals):
                raise ValueError(f"frame {f.id} has a reveal outside its range")
        breathers = [f.id for f in self.frames if f.type == "breather"]
        b = self.direction_block.breather_frame
        if b and b not in ids:
            raise ValueError("breather_frame must name a frame")
        if len(breathers) > 1:
            raise ValueError("exactly one breather: several frames are typed breather")
        if self.callback:
            if self.callback.plant_frame not in ids or self.callback.return_frame not in ids:
                raise ValueError("callback frames must exist")
            if ids.index(self.callback.return_frame) <= ids.index(self.callback.plant_frame):
                raise ValueError("callback must return after it is planted")
        if self.direction_id:
            from .directions import DIRECTIONS
            if self.direction_id not in DIRECTIONS:
                raise ValueError("unknown direction_id")
        from .cinematic import ATLAS
        for f in self.frames:
            if f.technique and f.technique not in ATLAS:
                raise ValueError(f"frame {f.id}: technique must be a cinematic_catalog id")
        return self


def _path(pid):
    return store.folder(pid) / "plan" / "storyboard.json"


def save(pid, storyboard):
    sb = Storyboard.model_validate(storyboard)
    p = agent.read(pid)
    t = p.get("timeline")
    if t and sb.frames[-1].end_s > t["total_frames"] / FPS + .5:
        raise ValueError(f"storyboard runs past the timeline ({t['total_frames'] / FPS:.2f}s)")
    data = sb.model_dump()
    store.write_json(_path(pid), data)
    return {"saved": str(_path(pid)), "frames": len(sb.frames), "next": "Compose, then storyboard(check=true) to compare the timeline with this plan."}


def read(pid):
    p = _path(pid)
    if not p.exists():
        raise ValueError("No storyboard saved for this project")
    return store.read_json(p)


TECH_KINDS = {"globe_dive": ("scene3d",), "trajectory_3d": ("scene3d",), "photo_3d": ("scene3d",), "hero_object_3d": ("scene3d",),
              "map_journey": ("svg",), "film_finish": ("film",), "kinetic_title": ("text",), "text_behind_subject": ("text", "video"),
              "tracked_callout": ("callout",)}
NEGATIVE = [
    (r"glitch", lambda t: [l["id"] for l in t["layers"] if any(e["name"] == "glitch" for e in l.get("effects", []))]),
    (r"emoji", lambda t: [l["id"] for l in t["layers"] if re.search(r"[\U0001F300-\U0001FAFF☀-➿]", l.get("text", ""))]),
    (r"leak", lambda t: [l["id"] for l in t["layers"] if l["kind"] == "film" and (l.get("data") or {}).get("type") == "light_leak"]),
    (r"grain", lambda t: [l["id"] for l in t["layers"] if l["kind"] == "film" and (l.get("data") or {}).get("type") == "grain"]),
    (r"bounc|spring", lambda t: [l["id"] for l in t["layers"] if any(e.get("easing") in ("bouncy", "springy") or e["name"] in ("spring", "char_spring") for e in l.get("effects", []))]),
    (r"flash", lambda t: [s["id"] for s in t["shots"] if (s.get("transition") or {}).get("name") == "flash"]),
    (r"shake", lambda t: [l["id"] for l in t["layers"] + t["shots"] if any(e["name"] in ("shake", "handheld") for e in l.get("effects", []))]),
    (r"dissolve", lambda t: [s["id"] for s in t["shots"] if (s.get("transition") or {}).get("name") == "dissolve"]),
]


def check(pid, render_path=None):
    sb = read(pid)
    t = agent.read(pid)["timeline"]
    total = t["total_frames"] / FPS
    findings = []
    frames = sb["frames"]
    if frames[0]["start_s"] > .5:
        findings.append({"level": "check", "code": "unplanned_opening", "evidence": {"first_frame_starts_s": frames[0]["start_s"]}})
    for a, b in zip(frames, frames[1:]):
        if b["start_s"] - a["end_s"] > 1:
            findings.append({"level": "check", "code": "plan_gap", "evidence": {"between": [a["id"], b["id"]], "seconds": round(b["start_s"] - a["end_s"], 2)}})
    if total - frames[-1]["end_s"] > 1:
        findings.append({"level": "check", "code": "unplanned_ending", "evidence": {"seconds_after_plan": round(total - frames[-1]["end_s"], 2)}})
    energy = None
    if render_path:
        from .review import motion_audit
        energy = (1, motion_audit(render_path, full=True)["speed_full"])  # brightness-independent, every frame
    rows = []
    for f in frames:
        a, b = int(f["start_s"] * FPS), int(f["end_s"] * FPS)
        active = [l for l in t["layers"] if l["start_frame"] < b and l["end_frame"] > a]
        kinds = {l["kind"] for l in active}
        texts = [l for l in active if l["kind"] == "text"]
        row = {"frame": f["id"], "range_s": [f["start_s"], f["end_s"]], "layers": len(active), "text_layers": len(texts)}
        missing = []
        for r in f["reveals"]:
            fr = int(r["at_s"] * FPS)
            if r.get("layer_id"):
                hit = any(l["id"] == r["layer_id"] and abs(l["start_frame"] - fr) <= 10 for l in t["layers"])
            else:
                hit = any(abs(l["start_frame"] - fr) <= 10 for l in active)
            if not hit:
                missing.append(r["what"])
        if missing:
            findings.append({"level": "check", "code": "reveal_not_found", "where": f["id"], "evidence": {"missing": missing},
                             "suggestion": "No layer starts within ±0.33 s of these planned reveals; retime or update the plan."})
        tech = f.get("technique")
        if tech in TECH_KINDS and not set(TECH_KINDS[tech]) <= kinds:
            findings.append({"level": "check", "code": "technique_missing", "where": f["id"], "evidence": {"technique": tech, "layer_kinds_present": sorted(kinds)},
                             "suggestion": f"The plan relies on {tech} here but no matching layers are active in this range."})
        if energy:
            step, vals = energy
            seg = vals[a // step:max(a // step + 1, b // step)]
            row["motion_energy"] = round(sum(seg) / len(seg), 4) if seg else None
        rows.append(row)
    br = sb["direction_block"].get("breather_frame") or next((f["id"] for f in frames if f["type"] == "breather"), None)
    if br and energy:
        calm = min((r for r in rows if r.get("motion_energy") is not None), key=lambda r: r["motion_energy"], default=None)
        if calm and calm["frame"] != br:
            findings.append({"level": "check", "code": "breather_not_calmest", "where": br,
                             "evidence": {"calmest_frame": calm["frame"], "energies": {r["frame"]: r.get("motion_energy") for r in rows}},
                             "suggestion": "The planned breather is not the calmest stretch; quiet it (hold, fewer elements) or move the breather."})
    elif not br:
        findings.append({"level": "info", "code": "no_breather", "evidence": {}, "suggestion": "Plan exactly one calmer frame so hero beats register."})
    cb = sb.get("callback")
    if cb and cb.get("layer_ids"):
        rng = {f["id"]: (int(f["start_s"] * FPS), int(f["end_s"] * FPS)) for f in frames}
        for key in ("plant_frame", "return_frame"):
            a, b = rng[cb[key]]
            if not any(l["id"] in cb["layer_ids"] and l["start_frame"] < b and l["end_frame"] > a for l in t["layers"]):
                findings.append({"level": "check", "code": "callback_missing", "where": cb[key], "evidence": {"motif": cb["motif"], "layer_ids": cb["layer_ids"]}})
    for neg in sb["direction_block"].get("negative", []):
        for pattern, detect in NEGATIVE:
            if re.search(pattern, neg, re.I):
                hits = detect(t)
                if hits:
                    findings.append({"level": "likely_problem", "code": "negative_list_violation", "evidence": {"rule": neg, "found_in": hits[:10]},
                                     "suggestion": "The plan bans this; remove it or change the plan deliberately."})
    return {"message": sb["message"], "frames": rows, "findings": findings,
            "note": "Checks structure and timing against the plan; whether each frame's focal element reads first is for snapshot/review_frames and your eyes."}
