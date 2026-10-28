"""Time-grounded meaning shared by custom builds, native narration and AI scene tools.

Authored text is not ASR. Clip boundaries are not word alignment. A structural anchor rejects stale mappings
after media/timing changes, while allowing colour and layout edits to retain the same narrative context.
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store


class MeaningBeat(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    text: str = Field(max_length=4000)
    purpose: str = Field(min_length=1, max_length=800)
    chapter: str = Field(default="", max_length=200)
    role: Literal["context", "cause", "decision", "event", "consequence", "witness", "breath", "orientation", "payoff"] = "context"
    visual_goal: str = Field(default="", max_length=800)
    shot_ids: list[str] = Field(default_factory=list, max_length=100)
    audio_ids: list[str] = Field(default_factory=list, max_length=30)
    sources: list[str] = Field(default_factory=list, max_length=20)
    timing: Literal["clip_bounds", "authored_window", "subtitle_bounds", "asr_segments"] = "clip_bounds"

    @model_validator(mode="after")
    def ordered(self):
        if self.end_frame <= self.start_frame: raise ValueError("Narrative beat needs a nonempty frame window")
        if any(len(s) > 1200 for s in self.sources): raise ValueError("Source references <=1200 characters")
        return self


class BindNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    base_revision: int = Field(ge=1)
    expected_binding: int = Field(default=0, ge=0)
    message: str = Field(min_length=1, max_length=1200)
    audience: str = Field(default="", max_length=500)
    visual_language: str = Field(default="", max_length=1500)
    language: str = Field(default="vi", max_length=12)
    source: str = Field(min_length=1, max_length=1200)
    beats: list[MeaningBeat] = Field(min_length=1, max_length=1500)
    reference_render: str | None = None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def structural(t):
    fields = ("id", "asset_id", "start_frame", "end_frame", "source_start", "playback_rate", "freeze", "beat_id", "reverse")
    def row(r):
        values={k:r.get(k) for k in fields}
        # Pydantic defaults can serialize as 1/0 before a patch, then 1.0/0.0 after validation.
        # These are identical media mappings, not a reason to discard the narrative.
        for k in ('source_start','playback_rate'):
            if values[k] is not None:values[k]=float(values[k])
        return values
    return digest({"frames": t["total_frames"], "fps": t["fps"],
                   **{name: [row(r) for r in t.get(name, [])] for name in ("shots", "audio_clips")}})


def path(pid):
    return store.folder(pid) / "plan/meaning.json"


def authoring_state(pid,config=None):
    config=config or store.get_project(pid)['config']
    root=store.folder(pid)/'code'/config.get('renderer','remotion');files={}
    for directory,dirs,names in os.walk(root):
        dirs[:]=[d for d in dirs if d not in ('public','node_modules','.cache')]
        for name in names:
            f=Path(directory)/name
            if f.suffix in ('.tsx','.ts','.jsx','.js','.mjs','.cjs','.html','.css','.svg','.json') and name not in ('input.json','input.js','source-meta.json'):
                stat=f.stat();files[str(f.relative_to(root))]=[stat.st_size,stat.st_mtime_ns]
    return {'config_hash':digest(config),'code_file_state':files}


def bind(request):
    from . import agent
    from .media import probe, sha256
    q = BindNarrative.model_validate(request)
    p = agent.read(q.project_id); t = p.get("timeline")
    if not t or p["revision"] != q.base_revision: raise ValueError("Read the current locked project revision before binding narrative")
    if len({b.id for b in q.beats}) != len(q.beats): raise ValueError("Narrative beat IDs must be unique")
    rows = {"shot_ids": {x["id"]: x for x in t["shots"]}, "audio_ids": {x["id"]: x for x in t.get("audio_clips", [])}}
    for b in q.beats:
        if b.end_frame > t["total_frames"]: raise ValueError(f"{b.id}: beat exceeds timeline")
        for field, choices in rows.items():
            for identity in getattr(b, field):
                r = choices.get(identity)
                if not r or r["start_frame"] >= b.end_frame or r["end_frame"] <= b.start_frame:
                    raise ValueError(f"{b.id}: {field} {identity} is missing or outside this beat")
        if b.timing == "clip_bounds":
            if not b.audio_ids: raise ValueError("clip_bounds requires an actual audio clip")
            clips = [rows["audio_ids"][i] for i in b.audio_ids]
            if min(c["start_frame"] for c in clips) != b.start_frame or max(c["end_frame"] for c in clips) != b.end_frame:
                raise ValueError("clip_bounds must match referenced audio boundaries; use authored_window otherwise")
    reference = None
    if q.reference_render:
        source = Path(q.reference_render).resolve(strict=True)
        v = next(s for s in probe(source)["streams"] if s["codec_type"] == "video")
        if int(v.get("nb_frames", -1)) != t["total_frames"]: raise ValueError("Reference render frame count must match project")
        st = source.stat()
        reference = {"path": str(source), "sha256": sha256(source), "signature": [st.st_size, st.st_mtime_ns], "timeline_hash": digest(t),
                     'authoring_state':authoring_state(q.project_id,p['config'])}
    # Serialize with ordinary project mutations, with a separate binding revision for concurrent AI authors.
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT revision FROM projects WHERE id=?", (q.project_id,)).fetchone()
        if not current or current[0] != q.base_revision: raise ValueError("Project revision changed while binding")
        old = store.read_json(path(q.project_id)) if path(q.project_id).exists() else {}
        if old.get("binding_revision", 0) != q.expected_binding: raise ValueError("Narrative binding conflict: reread binding_revision")
        doc = {"schema": 1, "binding_revision": q.expected_binding + 1, "project_revision": q.base_revision,
               "structure_hash": structural(t), "created_at": store.now(), "reference_render": reference,
               **q.model_dump(exclude={"base_revision", "expected_binding", "reference_render"})}
        doc["beats"].sort(key=lambda b: (b["start_frame"], b["end_frame"], b["id"]))
        version = store.folder(q.project_id) / "meaning-versions" / (digest(doc) + ".json")
        store.write_json(version, doc)
        store.write_json(path(q.project_id), doc)
    return {"project_id": q.project_id, "binding_revision": doc["binding_revision"], "beats": len(doc["beats"]),
            "path": str(path(q.project_id)), "version": str(version), "timing": "Declared segment/clip bounds, no word alignment invented"}


def document(pid, t):
    f = path(pid)
    if not f.exists(): return None, "missing"
    try:
        d = store.read_json(f)
        if not isinstance(d,dict) or d.get('schema')!=1 or not isinstance(d.get('beats'),list) or not isinstance(d.get('structure_hash'),str):
            raise ValueError('Invalid narrative manifest')
    except (OSError,ValueError,TypeError):
        return None,'unreadable_binding'
    return d, "ready" if d["structure_hash"] == structural(t) else "stale_media_or_timing"


def context(pid, t, start=0, end=None, offset=0, limit=12):
    end = t["total_frames"] / 30 if end is None else end
    if not 0 <= start < end <= t["total_frames"] / 30 + .001 or offset < 0 or not 1 <= limit <= 200:
        raise ValueError("Narrative range/pagination outside timeline")
    d, status = document(pid, t)
    if status == "ready":
        all_beats = d["beats"]
        matches = [b for b in all_beats if b["start_frame"] < end * 30 and b["end_frame"] > start * 30]
        before = [b for b in all_beats if b["end_frame"] <= start * 30]
        after = [b for b in all_beats if b["start_frame"] >= end * 30]
        reference = d.get("reference_render")
        if reference:
            reference = dict(reference); f = Path(reference["path"])
            reference["file_unchanged"] = f.exists() and [f.stat().st_size, f.stat().st_mtime_ns] == reference["signature"]
            reference["matches_current_picture"] = reference["file_unchanged"] and reference["timeline_hash"] == digest(t) and reference.get('authoring_state')==authoring_state(pid)
        return {"status": status, "binding_revision": d["binding_revision"], "message": d["message"],
                "audience": d["audience"], "visual_language": d["visual_language"], "language": d["language"],
                "beats": matches[offset:offset + limit], "total": len(matches), "next_offset": offset + limit if offset + limit < len(matches) else None,
                "previous": [{k: b[k] for k in ("id", "text", "purpose")} for b in before[-1:]],
                "next": [{k: b[k] for k in ("id", "text", "purpose")} for b in after[:1]], "reference_render": reference,
                "timing_note": "Authored text linked to actual clips/windows; no per-word speech alignment. Inspect audio for exact delivery."}
    # Native projects remain useful without a separate manifest. Stale authored bindings are never reused silently.
    cues = [{"id": f"cue-{i}", "start_frame": round(c["start"] * 30), "end_frame": round(c["end"] * 30), "text": c["text"],
             "purpose": "", "timing": "subtitle_bounds"} for i, c in enumerate(t.get("cues", [])) if c["start"] < end and c["end"] > start]
    if not cues:
        f=store.folder(pid)/'plan/words.json'
        words=store.read_json(f).get('words',[]) if f.exists() else []
        if words:
            from .beatmap import _sentences
            cues=[{'id':f'words-{i}','start_frame':round(s['start']*30),'end_frame':round(s['end']*30),
                   'text':s['text'],'purpose':'','timing':'timed_words'} for i,s in enumerate(_sentences(words))
                  if s['start']<end and s['end']>start]
    return {"status": status, "binding_revision": d.get("binding_revision", 0) if d else 0, "beats": cues[offset:offset + limit],
            "total": len(cues), "next_offset": offset + limit if offset + limit < len(cues) else None,
            "warning": "Bind original narrative text to actual audio clip IDs. Native cues are fallback text; missing context is not silence."}


def narration(pid, t, offset=0, limit=200):
    c = context(pid, t, offset=offset, limit=limit)
    assets = {a["id"]: a for a in store.assets(pid)}
    audios = {a["id"]: a for a in t.get("audio_clips", [])}
    c["dialogue_sources"] = [{"beat_id": b["id"], "clip_id": identity,
            "path": assets[audios[identity]["asset_id"]]["path"],
            **{k: audios[identity].get(k) for k in ("start_frame", "end_frame", "source_start", "playback_rate")}}
        for b in c["beats"] for identity in b.get("audio_ids", []) if identity in audios and audios[identity]["asset_id"] in assets]
    return c
