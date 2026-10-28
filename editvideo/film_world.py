"""Persistent film state and per-shot generation packets for an AI director; no model calls or identity guarantees."""
import copy
import math
import re
import uuid
from pathlib import Path
from typing import Literal
from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store
from .generation import GenerationRequest

ID = r"^[A-Za-z0-9_-]{1,60}$"


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(pattern=ID)
    kind: Literal["character", "prop", "location"]
    description: str = Field(min_length=1, max_length=1500)
    voice: str = Field(default="", max_length=500)
    references: list[str] = Field(default_factory=list, max_length=6)
    initial_state: dict[str, str] = Field(default_factory=dict, max_length=24)


class Shot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=ID)
    scene: str = Field(pattern=ID)
    purpose: str = Field(min_length=1, max_length=800)
    action: str = Field(min_length=1, max_length=1800)
    seconds: float = Field(ge=1, le=15, allow_inf_nan=False)
    entities: list[str] = Field(default_factory=list, max_length=16)
    framing: Literal["extreme_wide", "wide", "medium", "close_up", "extreme_close_up", "insert", "over_shoulder", "pov"] = "medium"
    camera: str = Field(default="static", max_length=500)
    sound: str = Field(default="", max_length=800)
    dialogue: str = Field(default="", max_length=1500)
    requires: dict[str, dict[str, str]] = Field(default_factory=dict)
    changes: dict[str, dict[str, str]] = Field(default_factory=dict)
    reset_state: dict[str, dict[str, str]] = Field(default_factory=dict)
    axis_id: str = Field(default="", max_length=60)
    axis_side: Literal["A", "B", "on_axis", "unknown"] = "unknown"
    motivated_axis_cross: bool = False
    screen_direction: Literal["left", "right", "neutral", "unknown"] = "unknown"
    continuous_action: bool = False
    layout: dict[str, list[float]] = Field(default_factory=dict)
    reference_image: str | None = None
    generation: dict = Field(default_factory=lambda: {"provider": "local_ltx", "preset": "standard"})

    @model_validator(mode="after")
    def shape(self):
        for box in self.layout.values():
            if len(box) != 4 or not all(math.isfinite(v) for v in box) or not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1:
                raise ValueError("layout uses normalized [left,top,right,bottom]")
        if set(self.generation).intersection({"prompt", "reference_image", "reference_frames", "reference_mask", "duration"}):
            raise ValueError("Prompt, duration and shot reference are compiled from the shot; generation holds backend options only")
        return self


class World(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    premise: str = Field(min_length=1, max_length=1500)
    look: str = Field(min_length=1, max_length=1500)
    entities: list[Entity] = Field(min_length=1, max_length=80)
    shots: list[Shot] = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def links(self):
        ids = {e.id for e in self.entities}
        if len(ids) != len(self.entities) or len({s.id for s in self.shots}) != len(self.shots):
            raise ValueError("Entity and shot ids must be unique")
        for s in self.shots:
            used = set(s.entities) | set(s.layout) | set(s.requires) | set(s.changes) | set(s.reset_state)
            if not used <= ids or not set(s.layout) <= set(s.entities):
                raise ValueError(f"{s.id}: unknown entity or layout not in shot entities")
            if len(str(s.requires)) + len(str(s.changes)) + len(str(s.reset_state)) > 12000:
                raise ValueError("Keep shot state compact")
        return self


def _path(world_id):
    if not re.fullmatch(r"world-[0-9a-f]{20}", world_id):
        raise ValueError("Invalid film world handle")
    return store.DATA / "film-worlds" / (world_id + ".json")


def evaluate(world):
    """Declared state, not inferred pixel truth. Resets allow intentional time jumps and transformations."""
    state = {e["id"]: copy.deepcopy(e["initial_state"]) for e in world["entities"]}
    rows, notes = [], []
    previous = None
    for shot in world["shots"]:
        for entity, changes in shot["reset_state"].items():
            state[entity].update(changes)
        before = copy.deepcopy(state)
        for entity, requires in shot["requires"].items():
            for key, expected in requires.items():
                actual = state[entity].get(key)
                if actual != expected:
                    notes.append({"shot_id": shot["id"], "kind": "state_mismatch", "entity": entity, "property": key,
                                  "expected": expected, "declared_before": actual, "next": "Add a motivated change/reset or revise this shot; inspect actual pixels separately."})
        if previous and previous["scene"] == shot["scene"]:
            if (shot["axis_id"] and shot["axis_id"] == previous["axis_id"] and
                {shot["axis_side"], previous["axis_side"]} == {"A", "B"} and not shot["motivated_axis_cross"]):
                notes.append({"shot_id": shot["id"], "kind": "axis_cross", "previous": previous["id"],
                              "next": "Consider an on-axis view, establishing move, or mark an intentional axis cross."})
            if shot["continuous_action"] and {shot["screen_direction"], previous["screen_direction"]} == {"left", "right"}:
                notes.append({"shot_id": shot["id"], "kind": "direction_reversal", "previous": previous["id"],
                              "next": "Check action direction across the cut; a motivated reversal may be intentional."})
        for entity, changes in shot["changes"].items():
            state[entity].update(changes)
        rows.append({"shot": shot, "before": before, "after": copy.deepcopy(state)})
        previous = shot
    return rows, notes


def packet(doc, shot_id):
    rows, notes = evaluate(doc["world"])
    row = next((r for r in rows if r["shot"]["id"] == shot_id), None)
    if not row:
        raise ValueError("Unknown shot id")
    s = row["shot"]
    index = rows.index(row)
    entities = [e for e in doc["world"]["entities"] if e["id"] in s["entities"]]
    parts = [doc["world"]["look"], f"{s['framing']}; camera: {s['camera']}", s["action"]]
    for e in entities:
        state = row["before"][e["id"]]
        parts.append(f"{e['id']}: {e['description']}; current state: {state}")
    if s["layout"]:
        parts.append(f"Intended layout [left,top,right,bottom] normalized: {s['layout']}")
    if s["changes"]:
        parts.append(f"By the end of this shot: {s['changes']}")
    prompt = ". ".join(parts)
    ref = str(Path(s["reference_image"]).resolve()) if s["reference_image"] else None
    missing = [p for e in entities for p in e["references"] if not Path(p).is_file()]
    reasons = []
    if ref and not Path(ref).is_file():
        reasons.append("Shot reference_image is missing; prepare a real scene keyframe first")
    generation = None
    try:
        options = dict(s["generation"])
        provider = options.get("provider", "local_ltx")
        options["provider"] = provider
        if provider == "local_ltx":
            fps = options.get("fps", 24)
            options.setdefault("frame_count", math.ceil(max(1, s["seconds"] * fps - 1) / 8) * 8 + 1)
        compiled = GenerationRequest.model_validate({**options, "prompt": prompt, "duration": max(2, math.ceil(s["seconds"])), "reference_image": ref})
        actual = compiled.frame_count / compiled.fps if compiled.frame_count else compiled.duration
        if actual + 1e-6 < s["seconds"]:
            raise ValueError("Configured frame_count is shorter than the shot; increase it or split the shot")
        if not reasons:
            generation = compiled.model_dump()
    except ValueError as error:
        reasons.append(str(error)[:1200])
    assets = []
    for e in entities:
        for raw in e["references"]:
            p = Path(raw)
            assets.append({"entity": e["id"], "path": raw, "available": p.is_file(), "use": "Identity/keyframe composition reference, not silently used as a whole-scene I2V frame"})
    history = []
    for e in entities:
        seen = [r["shot"]["id"] for r in rows[:index] if e["id"] in r["shot"]["entities"]]
        history.append({"entity": e["id"], "first_appearance": seen[0] if seen else shot_id,
                        "previous_appearance": seen[-1] if seen else None,
                        "use": "Inspect a clear prior appearance and compose a current scene keyframe; do not blindly carry the previous background."})
    return {"world_id": doc["id"], "revision": doc["revision"], "shot_id": shot_id, "shot": s,
            "cast": [{k: e[k] for k in ("id", "kind", "description", "voice")} for e in entities],
            "state_before": {e["id"]: row["before"][e["id"]] for e in entities},
            "state_after": {e["id"]: row["after"][e["id"]] for e in entities}, "prompt": prompt,
            "generation_call": {"tool": "editvideo_generate_footage", "arguments": {"request": generation}} if generation else None,
            "generation_notes": reasons, "conditioning_assets": assets, "missing_entity_references": missing,
            "reference_history": history,
            "previous_shot": rows[index - 1]["shot"]["id"] if index else None,
            "next_shot": rows[index + 1]["shot"]["id"] if index + 1 < len(rows) else None,
            "continuity_notes": [n for n in notes if n["shot_id"] == shot_id],
            "finishing": {"trim_to_frames_30fps": round(s["seconds"] * 30), "dialogue": s["dialogue"], "sound": s["sound"],
                          "note": "Dialogue/voice and sound are separate finishing intent; generation adapter does not synthesize them."},
            "limits": "Declared continuity and prompt conditioning only. No diffusion training, identity lock, layout guarantee, lip sync or model call. Inspect generated pixels, then attach results and sequence them."}


def summary(doc, offset=0, limit=12):
    _, notes = evaluate(doc["world"])
    return {"world_id": doc["id"], "revision": doc["revision"], "title": doc["world"]["title"],
            "entities": [{"id": e["id"], "kind": e["kind"]} for e in doc["world"]["entities"]],
            "shots": [{"id": s["id"], "scene": s["scene"], "seconds": s["seconds"], "purpose": s["purpose"][:240]}
                      for s in doc["world"]["shots"][offset:offset + limit]],
            "total_shots": len(doc["world"]["shots"]), "offset": offset,
            "next_offset": offset + limit if offset + limit < len(doc["world"]["shots"]) else None,
            "continuity_notes": notes[:12], "total_notes": len(notes), "path": str(_path(doc["id"])),
            "next": "Read shot_id for state and a provider-validated generation packet. Notes are continuity questions, not approval gates."}


def run(request=None, world_id=None, base_revision=None, shot_id=None, detail=False, offset=0, limit=12):
    if offset < 0 or not 1 <= limit <= 40:
        raise ValueError("offset>=0; limit=1..40")
    if request is None and world_id is None:
        return {"request_schema": World.model_json_schema(), "workflow": "AI writes story/world -> save -> shot_id packet -> generate_footage -> inspect -> attach -> sequence_plan/render"}
    if request is not None:
        if shot_id:
            raise ValueError("Save the world, then read a shot packet")
        world = World.model_validate(request).model_dump()
        if len(str(world)) > 400000:
            raise ValueError("Film world must fit 400KB")
        identity = world_id or "world-" + uuid.uuid4().hex[:20]
        path = _path(identity)
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path.with_suffix(".lock")), timeout=20):
            old = store.read_json(path) if path.exists() else None
            if old and old["revision"] != base_revision:
                raise ValueError("Film world revision conflict; reread before editing")
            if old is None and base_revision not in (None, 0):
                raise ValueError("Film world does not exist at base_revision")
            doc = {"id": identity, "revision": old["revision"] + 1 if old else 1, "world": world, "updated_at": store.now()}
            store.write_json(path, doc)
        return summary(doc, offset, limit)
    doc = store.read_json(_path(world_id))
    if shot_id:
        return packet(doc, shot_id)
    return doc if detail else summary(doc, offset, limit)
