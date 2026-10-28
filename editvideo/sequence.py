"""Caller-grounded short-form selects: bounded search under a frame budget, then executable multi-source edits."""
import math
import re
import uuid
from pathlib import Path
from typing import Literal
from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store
from .media import probe, sha256


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    path: str
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    relevance: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=800)
    keep_audio: bool = True
    focus_x: float = Field(default=.5, ge=0, le=1)
    focus_y: float = Field(default=.5, ge=0, le=1)
    fit: Literal["cover", "contain"] = "contain"
    role: Literal["evidence", "illustration", "metaphor", "reconstruction", "decoration"] = "illustration"

    @model_validator(mode="after")
    def span(self):
        if self.end - self.start < 1 / 30:
            raise ValueError("Candidate must contain at least one complete frame")
        return self


class Beat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    purpose: str = Field(min_length=1, max_length=800)
    candidates: list[Candidate] = Field(min_length=1, max_length=12)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    budget_seconds: float = Field(ge=1, le=180, allow_inf_nan=False)
    minimum_seconds: float = Field(default=0, ge=0, le=180, allow_inf_nan=False)
    beats: list[Beat] = Field(min_length=1, max_length=16)
    profile: Literal["vertical", "landscape", "square", "portrait45"] = "vertical"
    engine: Literal["remotion", "hyperframes"] = "remotion"
    prevent_source_overlap: bool = True
    chronological: bool = False
    beam_width: int = Field(default=256, ge=16, le=1024)


def _path(plan_id):
    if not re.fullmatch(r"sequence-[0-9a-f]{20}", plan_id):
        raise ValueError("Invalid sequence plan handle")
    return store.DATA / "sequence-plans" / (plan_id + ".json")


def plan(request):
    q = Request.model_validate(request)
    if q.minimum_seconds > q.budget_seconds or len({b.id for b in q.beats}) != len(q.beats):
        raise ValueError("Minimum must fit budget; beat ids must be unique")
    budget, minimum = math.floor(q.budget_seconds * 30 + 1e-6), math.ceil(q.minimum_seconds * 30 - 1e-6)
    files, choices = {}, []
    for beat in q.beats:
        if len({c.id for c in beat.candidates}) != len(beat.candidates):
            raise ValueError("Candidate ids must be unique within a beat")
        options = []
        for c in beat.candidates:
            source = Path(c.path).resolve(strict=True)
            if not source.is_file() or source.stat().st_size > 500 * 1024 * 1024:
                raise ValueError("Candidate source must be a local video <=500MB")
            if str(source) not in files:
                info = probe(source)
                if not any(s.get("codec_type") == "video" for s in info["streams"]):
                    raise ValueError("Select candidates must be video files")
                files[str(source)] = {"sha256": sha256(source), "duration": float(info["format"].get("duration", 0)),
                                      "audio": any(s.get("codec_type") == "audio" for s in info["streams"])}
            if c.end > files[str(source)]["duration"] + .001:
                raise ValueError(f"{c.id}: source window exceeds duration")
            frames = math.floor((c.end - c.start) * 30 + 1e-6)
            options.append({**c.model_dump(), "path": str(source), "frames": frames, "beat_id": beat.id, "purpose": beat.purpose})
        choices.append(options)
    # Every beat is mandatory. Whole caller-selected windows avoid arbitrary mid-word trims. Bounded beam search
    # retains different durations/paths; it does not claim a globally optimal edit or a predicted retention score.
    states = [(0.0, 0, [])]
    minimum_tail = [sum(min(c["frames"] for c in group) for group in choices[i + 1:]) for i in range(len(choices))]
    pruned = 0
    for i, options in enumerate(choices):
        next_states = []
        for score, length, selected in states:
            for c in options:
                n = length + c["frames"]
                if n + minimum_tail[i] > budget:
                    continue
                old = [s for s in selected if s["path"] == c["path"]]
                if q.prevent_source_overlap and any(c["start"] < s["end"] - 1e-6 and c["end"] > s["start"] + 1e-6 for s in old):
                    continue
                if q.chronological and any(c["start"] < s["end"] - 1e-6 for s in old):
                    continue
                next_states.append((score + c["relevance"], n, selected + [c]))
        next_states.sort(key=lambda s: (-s[0], -s[1], tuple(c["id"] for c in s[2])))
        pruned += max(0, len(next_states) - q.beam_width)
        states = next_states[:q.beam_width]
        if not states:
            raise ValueError(f"No feasible sequence at beat {q.beats[i].id}; adjust windows, overlap or duration budget")
    feasible = [s for s in states if s[1] >= minimum]
    if not feasible:
        raise ValueError("No retained sequence meets minimum_seconds; widen beam or provide different windows")
    score, frames, selected = feasible[0]
    cursor = 0
    for c in selected:
        c["start_frame"], c["end_frame"] = cursor, cursor + c["frames"]
        c["used_source_end"] = c["start"] + c["frames"] / 30
        cursor += c["frames"]
    identity = "sequence-" + uuid.uuid4().hex[:20]
    doc = {"id": identity, "request": q.model_dump(), "selected": selected, "sources": files,
           "total_frames": frames, "objective": score, "search_pruned": pruned, "created_at": store.now(),
           "method": "Bounded beam search; relevance supplied by caller after inspection, not a model/aesthetic/retention score."}
    store.write_json(_path(identity), doc)
    return summary(doc)


def summary(doc):
    return {"plan_id": doc["id"], "total_frames": doc["total_frames"], "seconds": doc["total_frames"] / 30,
            "unused_budget_s": round(doc["request"]["budget_seconds"] - doc["total_frames"] / 30, 4),
            "selected": [{k: c[k] for k in ("id", "beat_id", "purpose", "path", "start", "used_source_end", "start_frame", "end_frame", "reason")} for c in doc["selected"]],
            "search_pruned": doc["search_pruned"], "method": doc["method"], "path": str(_path(doc["id"])),
            "project_id": doc.get("project_id"), "next": "Inspect selected windows; build=true with plan_id creates a new editable project, retaining selected source audio. No narration is overwritten."}


def build(plan_id):
    from . import agent
    path = _path(plan_id)
    with FileLock(str(path.with_suffix(".lock")), timeout=30):
        doc = store.read_json(path)
        if doc.get("project_id") and doc.get("build_state") == "completed":
            store.get_project(doc["project_id"])
            return summary(doc)
        if doc.get("project_id"):
            raise ValueError(f"An incomplete build exists at project {doc['project_id']}; inspect it before rebuilding")
        for raw, info in doc["sources"].items():
            if sha256(Path(raw)) != info["sha256"]:
                raise ValueError("Candidate source changed; plan again")
        q = doc["request"]
        pid = agent.create_silent(q["profile"], doc["total_frames"], q["engine"], q["title"])["id"]
        doc.update(project_id=pid, build_state="assembling")
        store.write_json(path, doc)
        assets = {}
        for c in doc["selected"]:
            if c["path"] not in assets:
                r = agent.import_media(pid, c["path"], "sequence selects", "illustration", True, store.get_project(pid)["revision"])
                assets[c["path"]] = r["asset"]["id"]
        p = agent.read(pid)
        t = p["timeline"]
        t["shots"], t["audio_clips"] = [], []
        for i, c in enumerate(doc["selected"]):
            t["shots"].append({"id": f"select-{i:03}", "beat_id": c["beat_id"], "start_frame": c["start_frame"], "end_frame": c["end_frame"],
                               "asset_id": assets[c["path"]], "source_start": c["start"], "motion": "hold", "fit": c["fit"],
                               "focus_x": c["focus_x"], "focus_y": c["focus_y"], "role": c["role"], "reason": c["reason"]})
            if c["keep_audio"] and doc["sources"][c["path"]]["audio"]:
                t["audio_clips"].append({"id": f"source-{i:03}", "asset_id": assets[c["path"]], "start_frame": c["start_frame"],
                                         "end_frame": c["end_frame"], "source_start": c["start"], "volume": 1, "duck_under_voice": False,
                                         "fade_in": .01, "fade_out": .01})
        agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
        doc["build_state"] = "completed"
        store.write_json(path, doc)
    return summary(doc)


def run(request=None, plan_id=None, create=False):
    if request is not None and plan_id is not None:
        raise ValueError("Pass a request to plan OR an existing plan_id")
    if request is not None:
        result = plan(request)
        return build(result["plan_id"]) if create else result
    if plan_id:
        return build(plan_id) if create else summary(store.read_json(_path(plan_id)))
    if create:
        raise ValueError("build requires plan_id")
    return {"request_schema": Request.model_json_schema(), "method": "Supply complete semantically inspected windows; no ASR/meaning inferred, downloads or generation.",
            "workflow": "plan request -> inspect windows -> build plan_id -> captions/design -> export_code -> render"}
