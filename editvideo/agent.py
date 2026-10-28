"""Headless project and edit API shared by MCP and CLI."""
import subprocess
import math
import copy
import shutil
import uuid
from pathlib import Path
from . import store
from .media import register, sha256
from .models import ProjectInput, Timeline
from .planner import validate_sources


def create(config: dict):
    return store.create_project(ProjectInput.model_validate({"renderer":"remotion",**config}).model_dump())


def read(pid):
    project = store.get_project(pid)
    plan = store.folder(pid)/"plan"
    return {**project, "assets": store.assets(pid), "jobs": store.jobs(pid),
            "timeline": store.read_json(plan/"timeline.json") if (plan/"timeline.json").exists() else None,
            "plan_meta": store.read_json(plan/"plan-meta.json") if (plan/"plan-meta.json").exists() else None,
            "code_directory": str(store.folder(pid)/"code")}


def summary(pid, page=0, rows=60):
    """Token-lean project view: everything needed to plan a patch except heavy layer data (3D scenes, SVG paths,
    caption words, keyframes). Fetch exact JSON for the layers you will change with read_layers. Shots, layers and the
    assets the timeline uses come `rows` at a time (page 0, 1, ...): a 29-min film's summary was 160k characters."""
    p = read(pid)
    t = p.get("timeline") or {}
    win = lambda xs: xs[page * rows:(page + 1) * rows]
    used = {x.get("asset_id") for k in ("shots", "layers", "audio_clips") for x in t.get(k) or []}
    used |= {(p.get("config") or {}).get(k) for k in ("narration_id", "music_id")}
    for l in t.get("layers") or []:  # 3D textures and models live in layer data
        d = l.get("data") or {}
        used |= {o.get(k) for o in d.get("objects", []) for k in ("texture", "bump_texture", "emissive_texture", "alpha_texture", "displacement_texture", "model")}
        used |= {d.get("background_texture"), d.get("environment_texture")}
    used.discard(None)
    assets = [a for a in p.get("assets", []) if a["id"] in used]
    clip = lambda s, n=48: (s[:n] + "…") if isinstance(s, str) and len(s) > n else s
    design = t.get("design") or {}
    from . import narrative
    meaning, meaning_status = narrative.document(pid,t) if t else (None,'missing')
    return {"id": p["id"], "revision": p["revision"], "title": (p.get("config") or {}).get("title"),
            "narrative": {"status":meaning_status,"beats":len(meaning['beats']) if meaning else 0,"binding_revision":meaning.get('binding_revision',0) if meaning else 0,
                          "message":meaning.get('message','') if meaning else '',"read":"direct_scene or read_narration for timed meaning"},
            "canvas": [t.get("width"), t.get("height"), t.get("total_frames")] if t else None,
            "design": {"style_id": design.get("style_id"), "direction": (design.get("direction") or {}).get("id")},
            "counts": {"shots": len(t.get("shots") or []), "layers": len(t.get("layers") or []), "audio_clips": len(t.get("audio_clips") or []),
                       "assets": len(p.get("assets", [])), "assets_used": len(assets)},
            "shots": win([{"id": s["id"], "f": [s["start_frame"], s["end_frame"]], "asset": s.get("asset_id"), "src": s.get("source_start"),
                           "motion": s.get("motion"), "tr": (s.get("transition") or {}).get("name"), "fx": [e["name"] for e in s.get("effects", [])]}
                          for s in t.get("shots", [])]),
            "layers": win([{"id": l["id"], "kind": l["kind"], "f": [l["start_frame"], l["end_frame"]], "z": l.get("z"), "attach": l.get("attach_shot"),
                            **({"text": clip(l["text"])} if l.get("text") else {}), **({"asset": l["asset_id"]} if l.get("asset_id") else {}),
                            "fx": [e["name"] for e in l.get("effects", [])]} for l in t.get("layers", [])]),
            "assets": win([{"id": a["id"], "kind": a["kind"], "name": clip(a.get("name"), 40), "dur": a.get("duration"), "size": [a.get("width"), a.get("height")]}
                           for a in assets]),
            "page": page, "next_page": page + 1 if any(len(t.get(k) or []) > (page + 1) * rows for k in ("shots", "layers")) or len(assets) > (page + 1) * rows else None,
            "jobs": [{"id": j["id"], "kind": j["kind"], "state": j["state"]} for j in (p.get("jobs") or [])[-3:]],
            "note": f"Summary view, {rows} rows a page; assets are those the timeline uses. read_layers(ids) returns exact layer JSON to edit; read_project(detail='full') returns everything."}


def read_layers(pid, ids):
    t = read(pid).get("timeline") or {}
    want = set(ids)
    found = [l for l in t.get("layers", []) if l["id"] in want] + [{"shot": s} for s in t.get("shots", []) if s["id"] in want]
    return {"revision": store.get_project(pid)["revision"], "items": found, "missing": sorted(want - {l.get("id") or l["shot"]["id"] for l in found})}


def import_media(pid, path, tags="", role="illustration",preserve_plan=False,base_revision=None,provenance=None):
    if preserve_plan:
        if base_revision is None:raise ValueError("preserve_plan requires base_revision")
        from .media_tasks import attach_file
        return attach_file(path,pid,base_revision,tags,role)
    store.get_project(pid)
    if role not in ("illustration", "evidence", "metaphor", "reconstruction", "decoration"):
        raise ValueError("Role không hợp lệ")
    source = Path(path).resolve(strict=True)
    if not source.is_file() or source.stat().st_size > 500*1024*1024:
        raise ValueError("File phải nhỏ hơn 500 MB")
    from .media import working_copy
    name = source.name  # the asset keeps the original's name, not the cache file's
    source, origin = working_copy(source)  # archival TIFF / oversized scans, rotated or anamorphic pictures: a working copy
    target = store.folder(pid)/"assets"/(str(uuid.uuid4())+source.suffix.lower())
    target.parent.mkdir(exist_ok=True)
    if store.DATA.resolve() in source.parents:
        # System-managed files (downloads, task results, other projects) are never edited in place: share bytes.
        from .code_engine import place_file
        place_file(source, target)
    else:
        shutil.copyfile(source, target)  # user files outside data/ stay independent of later edits
    try:
        if origin or provenance:  # a working copy or a derived file carries its source's sha, so credits trace to its licence
            meta = register(pid, target, name, tags, role, persist=False)
            meta["provenance"] = provenance or {"operation": "import working copy", "source_sha256": origin}
            store.add_asset(pid, meta)
            return meta
        return register(pid, target, name, tags, role)
    except Exception:
        target.unlink(missing_ok=True)
        target.with_suffix(".thumb.jpg").unlink(missing_ok=True)
        raise


def patch(pid: str, base_revision: int, operations: list[dict]):
    """One atomic edit batch. Invalid/conflicting batches make no changes."""
    if not operations or len(operations) > 100:
        raise ValueError("Cần 1..100 thao tác")
    plan = store.folder(pid)/"plan"
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if store.busy(db, pid):
            raise ValueError("Tác vụ đang chạy; hủy hoặc đợi trước khi sửa")
        project = db.execute("SELECT revision FROM projects WHERE id=?", (pid,)).fetchone()
        if not project or project["revision"] != base_revision:
            raise ValueError("Revision conflict: read project again and reapply intent")
        meta = store.read_json(plan/"plan-meta.json")
        if meta["revision"] != base_revision:
            raise ValueError("Plan stale: plan again after changing narration/media")
        original = store.read_json(plan/"timeline.json")
        data = copy.deepcopy(original)
        for op in operations:
            kind = op.get("op")
            if kind == "replace_timeline":
                data = copy.deepcopy(op["timeline"])
            elif kind == "replace_cues":
                data["cues"] = copy.deepcopy(op["cues"])
            elif kind == "freeze_frame":
                # Hold the picture at frame `at` for `frames`, then carry on where it paused: the shot becomes before /
                # still / after (same total length). The still lands with a punch and a 2-frame white flash.
                at, hold = int(op["at"]), int(op.get("frames", 30))
                idx = next((i for i, x in enumerate(data["shots"]) if x["start_frame"] < at < x["end_frame"] - 1), None)
                if idx is None or hold < 4:
                    raise ValueError("freeze_frame at must fall inside a shot (not on its first or last frame); frames >= 4")
                sh = data["shots"][idx]
                if at + hold >= sh["end_frame"]:
                    raise ValueError("freeze_frame: the shot ends before the hold does; shorten frames")
                d = at - sh["start_frame"]
                if any(l.get("attach_shot") == sh["id"] and l["end_frame"] > at for l in data.get("layers") or []):
                    raise ValueError("freeze_frame: layers attached to this shot run past the freeze; detach them (attach_shot) first")
                src = sh.get("source_start", 0) + d * sh.get("playback_rate", 1) / 30
                # the shot's look (vignette, grade...) carries over to every part at the same timeline frames; accents stay
                # where they were placed, and the still gets its own punch
                look = [e for e in sh.get("effects") or [] if not (e.get("params") or {}).get("accent")]
                n = sh["end_frame"] - sh["start_frame"]
                part = lambda a_, b_, skip=(): [{**e, "start_frame": max(0, e.get("start_frame", 0) - a_), "end_frame": min(b_ - a_ - 1, e["end_frame"] - a_)}
                                                for e in look if e["name"] not in skip and e.get("start_frame", 0) < b_ - 1 and e["end_frame"] > a_
                                                and min(b_ - a_ - 1, e["end_frame"] - a_) > max(0, e.get("start_frame", 0) - a_)]
                still = {**copy.deepcopy(sh), "id": f"{sh['id']}-freeze", "start_frame": at, "end_frame": at + hold, "source_start": round(src, 4), "freeze": True,
                         "motion": "hold",  # a still does not restart the shot's push (its punch is the focus_zoom below)
                         "transition": None, "keyframes": {}, "track_mods": {},
                         "effects": part(d, d + hold, ("focus_zoom",)) + ([{"name": "white_flash", "start_frame": 0, "end_frame": 2, "params": {"amount": 1}}] if op.get("flash", True) else []) + (
                             [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": float(op.get("zoom", .08)), "cut": True,
                                                                                                 "focus_x": float(op.get("focus_x", .5)), "focus_y": float(op.get("focus_y", .45))}}]
                             if float(op.get("zoom", .08)) > 0 else [])}
                after = {**copy.deepcopy(sh), "id": f"{sh['id']}-after", "start_frame": at + hold, "source_start": round(src, 4), "transition": None,
                         "keyframes": {}, "track_mods": {}, "effects": part(d + hold, n)}
                sh["effects"] = [{**e, "end_frame": min(e["end_frame"], d - 1)} for e in sh.get("effects") or [] if e["start_frame"] < d - 1]
                sh["keyframes"], sh["track_mods"], sh["end_frame"] = {}, {}, at
                data["shots"][idx + 1:idx + 1] = [still, after]
            elif kind == "apply_combo":
                # One call for a curated effect stack (effect_catalog combos): every effect spans [start_frame, end_frame)
                # local to the target; previous effects of the same names on it are replaced.
                from .effect_guide import COMBOS
                if op.get("combo") not in COMBOS:
                    raise ValueError(f"combo must be one of {sorted(COMBOS)}")
                item = next((x for x in [*data["shots"], *data.get("layers", [])] if x["id"] == op.get("target")), None)
                if not item:
                    raise ValueError("apply_combo target is a shot or layer id")
                a, b = int(op.get("start_frame", 0)), int(op.get("end_frame", item["end_frame"] - item["start_frame"] - 1))
                stack = COMBOS[op["combo"]]["stack"]
                names = {e["name"] for e in stack}
                item["effects"] = [e for e in item.get("effects") or [] if e["name"] not in names] + [
                    {"name": e["name"], "start_frame": a, "end_frame": max(a + 1, b), "params": dict(e.get("params") or {})} for e in stack]
            elif kind == "upsert_overlay":
                overlay = copy.deepcopy(op["overlay"])
                data["overlays"] = [o for o in data.get("overlays", []) if o["id"] != overlay["id"]]+[overlay]
            elif kind == "delete_overlay":
                data["overlays"] = [o for o in data.get("overlays", []) if o["id"] != op["id"]]
            elif kind in ("upsert_layer","upsert_audio"):
                key="layers" if kind=="upsert_layer" else "audio_clips"
                item=copy.deepcopy(op["layer" if kind=="upsert_layer" else "audio"])
                data[key]=[o for o in data.get(key,[]) if o["id"]!=item["id"]]+[item]
            elif kind in ("delete_layer","delete_audio"):
                key="layers" if kind=="delete_layer" else "audio_clips"
                data[key]=[o for o in data.get(key,[]) if o["id"]!=op["id"]]
            elif kind == "set_design":
                data["design"]={**data.get("design",{}),**copy.deepcopy(op["design"])}
            elif kind == "set_audio_mix":
                data["audio_mix"]={**data.get("audio_mix",{}),**copy.deepcopy(op["audio_mix"])}
            else:
                idx = next((i for i, s in enumerate(data["shots"]) if s["id"] == op.get("shot_id")), None)
                if idx is None:
                    raise ValueError(f"Shot missing: {op.get('shot_id')}")
                shot = data["shots"][idx]
                if kind == "update_shot":
                    if set(op["changes"])-{"asset_id", "source_start", "text", "role", "motion", "fit", "focus_x", "focus_y", "reason", "effects", "keyframes", "playback_rate", "transition"}:
                        raise ValueError("update_shot supports visual fields; use move_boundary/split_shot for timing")
                    shot.update(op["changes"])
                elif kind == "split_shot":
                    frame = op["frame"]
                    if not isinstance(frame, int) or not shot["start_frame"] < frame < shot["end_frame"]:
                        raise ValueError("Split frame phải nằm trong shot")
                    right = copy.deepcopy(shot)
                    right.update(id=op["new_id"], start_frame=frame,
                                 source_start=shot.get("source_start", 0)+(frame-shot["start_frame"])*shot.get("playback_rate",1)/data["fps"])
                    if shot.get("effects") or shot.get("keyframes") or shot.get("transition"):
                        raise ValueError("Split animated shot explicitly with replace_timeline to preserve animation intent")
                    shot["end_frame"] = frame
                    data["shots"].insert(idx+1, right)
                elif kind == "move_boundary":
                    if idx+1 >= len(data["shots"]):
                        raise ValueError("Shot cuối không có boundary phía sau")
                    following = data["shots"][idx+1]
                    frame = op["frame"]
                    if not isinstance(frame, int) or not shot["start_frame"] < frame < following["end_frame"]:
                        raise ValueError("Boundary nằm ngoài hai shot")
                    shot["end_frame"] = frame
                    following["start_frame"] = frame
                else:
                    raise ValueError(f"Unknown edit operation: {kind}")
        timeline = Timeline.model_validate(data)
        if any(data.get(k, original[k]) != original[k] for k in ("audio_samples", "sample_rate", "fps", "width", "height", "total_frames")):
            raise ValueError("Voice/dimensions/timebase locked; create new plan to change them")
        validate_sources(pid, timeline, store.assets(pid))
        history = store.folder(pid)/"history"/f"revision-{base_revision:06}.json"
        store.write_json(history, {"timeline": original, "operations": operations, "applied_at": store.now()})
        store.write_json(plan/"timeline.json", timeline.model_dump())
        meta.update(revision=base_revision+1, timeline_hash=sha256(plan/"timeline.json"))
        store.write_json(plan/"plan-meta.json", meta)
        db.execute("UPDATE projects SET revision=revision+1, updated_at=? WHERE id=?", (store.now(), pid))
    return {"revision": base_revision+1, "timeline": timeline.model_dump(), "history": str(history)}


def result(jid):
    job = store.get_job(jid)
    work = store.folder(job["project_id"])/"jobs"/jid
    files = [{"name": p.name, "path": str(p.resolve()), "bytes": p.stat().st_size}
             for p in work.iterdir() if p.is_file()] if work.exists() else []
    return {**job, "artifacts": files,
            "output": store.read_json(work/"output.json") if (work/"output.json").exists() else None}


def from_segments(path,segments,profile="landscape",engine="remotion",title=None,audio_path=None,fade_ms=8,shot_effects=None):
    """Editable project from kept ranges of one source (dialogue condensing, selects): one shot per range, the source
    audio of exactly those ranges concatenated (micro fades at every join, no clicks), and a time map old → new.
    audio_path replaces the source audio (e.g. a cleaned dialogue file of the same length as the source)."""
    import math,subprocess
    import numpy as np
    from .media import probe,FFMPEG,command
    from .models import PROFILES
    source=Path(path).resolve(strict=True)
    if not source.is_file() or source.stat().st_size>500*1024*1024:
        raise ValueError("Source video <=500MB required")
    info=probe(source);duration=float(info["format"].get("duration",0))
    if not next((s for s in info["streams"] if s["codec_type"]=="video"),None):
        raise ValueError("Video source required")
    segs=[(max(0.0,round(float(a)*30)/30),min(duration,float(b))) for a,b in segments]  # whole-frame starts: engines agree
    segs=[(a,b) for a,b in segs if b-a>=1/30]
    # Any order: selects are rearranged freely (an interview answer can open the film); each range is cut on its own.
    if not segs or len(segs)!=len(segments) or sum(b-a for a,b in segs)>3600:
        raise ValueError("segments are [start, end] seconds inside the source, each at least one frame, total <= 1 h")
    p=create({"title":title or source.stem,"profile":profile,"renderer":engine,"captions":False})
    pid=p["id"];asset=import_media(pid,str(source),"source footage","evidence")
    SR=48000
    raw=subprocess.run([FFMPEG,"-v","error","-i",str(audio_path or source),"-vn","-ac","1","-ar",str(SR),"-f","f32le","-"],capture_output=True,timeout=900).stdout
    audio=np.frombuffer(raw,np.float32) if raw else np.zeros(int(duration*SR),np.float32)
    shots,pieces,tmap,f0=[],[],[],0
    fade=max(1,int(fade_ms*SR/1000))
    ramp=np.linspace(0,1,fade,dtype=np.float32)
    for i,(a,b) in enumerate(segs):
        n=max(1,math.floor((b-a)*30+1e-6));s0=int(round(a*SR));piece=np.zeros(n*1600,np.float32)  # floor: a rounded-up frame reads past the source
        chunk=audio[s0:s0+n*1600];piece[:len(chunk)]=chunk
        if len(segs)>1:
            if i>0:piece[:fade]*=ramp
            if i<len(segs)-1:piece[-fade:]*=ramp[::-1]
        pieces.append(piece)
        shots.append({"id":f"seg-{i+1:03d}","beat_id":"source","start_frame":f0,"end_frame":f0+n,"asset_id":asset["id"],"source_start":round(a,4),
                      "motion":"hold","fit":"contain","role":"evidence",**({"effects":shot_effects[i]} if shot_effects and shot_effects[i] else {})})
        tmap.append({"src":[round(a,4),round(a+n/30,4)],"frames":[f0,f0+n]})
        f0+=n
    voice=store.folder(pid)/"source-audio.wav"
    subprocess.run([FFMPEG,"-v","error","-y","-f","f32le","-ar",str(SR),"-ac","1","-i","-","-c:a","pcm_s16le",str(voice)],input=np.concatenate(pieces).tobytes(),check=True)
    narration=import_media(pid,str(voice),"source audio (assembled)",provenance={"operation":"extract audio","source_sha256":asset["sha256"]})
    p=store.get_project(pid);store.update_project(pid,{**p["config"],"narration_id":narration["id"]})
    p=store.get_project(pid);w,h=PROFILES[profile]
    timeline=Timeline(width=w,height=h,total_frames=f0,audio_samples=f0*1600,timing_method="source_video_audio",beats=[],cues=[],shots=shots)
    validate_sources(pid,timeline,store.assets(pid))
    plan=store.folder(pid)/"plan";plan.mkdir(exist_ok=True);shutil.copyfile(voice,plan/"voice.wav")
    store.write_json(plan/"words.json",{"method":timeline.timing_method,"words":[]})
    store.write_json(plan/"timeline.json",timeline.model_dump())
    store.write_json(plan/"time-map.json",{"source":str(source),"map":tmap})
    store.write_json(plan/"plan-meta.json",{"revision":p["revision"],"audio_hash":sha256(plan/"voice.wav"),"timeline_hash":sha256(plan/"timeline.json")})
    gaps=segment_gaps(source,segs,audio,SR,tmap)
    return {"project_id":pid,"frames":f0,"shots":len(shots),"time_map":str(plan/"time-map.json"),
            **({"gaps":gaps[:20],"note":"Dead air or black inside a select (a reel's slug between soundbites): split the select at the gap or "
                "trim it, then rebuild. Times are source seconds; frames are in the new timeline."} if gaps else {})}


def segment_gaps(source,segs,audio,sr,tmap,silence_db=-50.0,min_silence=1.0,min_black=.25):
    """Dead air (RMS below max(silence_db, the select's speech level - 30 dB) for >= min_silence s) and black picture
    (>= min_black s) inside each kept range."""
    import re,numpy as np
    from .media import FFMPEG
    out=[]
    win=int(sr*.05)
    for i,(a,b) in enumerate(segs):
        x=audio[int(a*sr):int(b*sr)]
        if len(x)>=win:
            n=len(x)//win
            db=20*np.log10(np.sqrt(np.mean(x[:n*win].reshape(n,win)**2,axis=1))+1e-9)
            # Relative to the select's own speech level: a slug with room tone sits well above -50 dBFS but ~30 dB
            # under the voice.
            floor=max(silence_db,float(np.percentile(db,90))-30)
            quiet=np.r_[False,db<floor,False].astype(int)
            for s0,s1 in zip(np.flatnonzero(np.diff(quiet)==1),np.flatnonzero(np.diff(quiet)==-1)):
                if (s1-s0)*.05>=min_silence:
                    out.append({"segment":i,"kind":"silence","source":[round(float(a+s0*.05),2),round(float(a+s1*.05),2)]})
        log=subprocess.run([FFMPEG,"-v","info","-ss",str(a),"-t",str(b-a),"-i",str(source),"-an","-vf","scale=160:-2,blackdetect=d=%s:pix_th=0.10"%min_black,
                            "-f","null","-"],capture_output=True,text=True,timeout=300).stderr
        for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+)",log):
            out.append({"segment":i,"kind":"black","source":[round(a+float(m.group(1)),2),round(a+float(m.group(2)),2)]})
    for g in out:
        f0=tmap[g["segment"]]["frames"][0];a=tmap[g["segment"]]["src"][0]
        g["frames"]=[f0+int((g["source"][0]-a)*30),f0+int((g["source"][1]-a)*30)]
    return out


def from_multicam(master,angle_paths,shots,profile="landscape",engine="remotion",title=None):
    """Project whose picture switches between synced angles over the continuous master audio. shots: [{angle,
    start_frame, end_frame, source_start}] (source_start in that angle's own time)."""
    import subprocess
    from .media import probe,FFMPEG
    from .models import PROFILES
    master=Path(master).resolve(strict=True)
    total=shots[-1]["end_frame"]
    p=create({"title":title or master.stem,"profile":profile,"renderer":engine,"captions":False})
    pid=p["id"];ids=[import_media(pid,str(Path(a).resolve(strict=True)),f"angle {i+1}","evidence")["id"] for i,a in enumerate(angle_paths)]
    voice=store.folder(pid)/"source-audio.wav"
    subprocess.run([FFMPEG,"-v","error","-y","-i",str(master),"-vn","-af",f"apad,atrim=duration={total/30}","-ar","48000","-ac","1","-c:a","pcm_s16le",str(voice)],check=True,timeout=900)
    narration=import_media(pid,str(voice),"master audio",provenance={"operation":"extract audio","source_sha256":sha256(master)})
    p=store.get_project(pid);store.update_project(pid,{**p["config"],"narration_id":narration["id"]})
    p=store.get_project(pid);w,h=PROFILES[profile]
    tl=[{"id":f"cam-{k+1:03d}","beat_id":"source","start_frame":s["start_frame"],"end_frame":s["end_frame"],"asset_id":ids[s["angle"]],
         "source_start":s["source_start"],"motion":"hold","fit":"cover","role":"evidence"} for k,s in enumerate(shots)]
    if any(s["source_start"]<0 for s in tl):raise ValueError("a multicam shot starts before its angle was recording; plan with multicam.build (it falls back to a covering angle)")
    timeline=Timeline(width=w,height=h,total_frames=total,audio_samples=total*1600,timing_method="source_video_audio",beats=[],cues=[],shots=tl)
    validate_sources(pid,timeline,store.assets(pid))
    plan=store.folder(pid)/"plan";plan.mkdir(exist_ok=True);shutil.copyfile(voice,plan/"voice.wav")
    store.write_json(plan/"words.json",{"method":timeline.timing_method,"words":[]})
    store.write_json(plan/"timeline.json",timeline.model_dump())
    store.write_json(plan/"plan-meta.json",{"revision":p["revision"],"audio_hash":sha256(plan/"voice.wav"),"timeline_hash":sha256(plan/"timeline.json")})
    return {"project_id":pid,"frames":total}


def create_silent(profile="vertical",frames=900,engine="remotion",title=None,color="#0b0d0c"):
    """A silent, locked timeline of exactly `frames` frames (30 fps) on a plain carrier shot, for edits driven by
    picture and on-screen text (reels, ads, travel cuts). Replace the shot list with real footage; the length stays."""
    import tempfile
    from .media import FFMPEG,command
    from .models import PROFILES
    if profile not in PROFILES or not 30<=int(frames)<=30*1800:  # 30 min: documentaries run past the 10 min of a reel
        raise ValueError(f"profile one of {sorted(PROFILES)}; frames 30..54000 (1 s..30 min)")
    w,h=PROFILES[profile]
    with tempfile.TemporaryDirectory(dir=store.DATA) as tmp:
        carrier=Path(tmp)/"silent-carrier.mp4"
        command([FFMPEG,"-y","-v","error","-f","lavfi","-i",f"color=c={color.lstrip('#')}:s={w}x{h}:r=30:d={(int(frames)+2)/30}","-frames:v",str(int(frames)),
                 "-c:v","libx264","-pix_fmt","yuv420p",carrier])
        r=from_video(carrier,profile,engine,title or "Silent edit")
    # The carrier colour is the canvas colour too: a contained or letterboxed shot shows it, not the default teal.
    p=patch(r["id"],r["revision"],[{"op":"set_design","design":{"background":color}}])
    return {**r,"revision":p["revision"],"timeline":p["timeline"]}


def from_video(path,profile="landscape",engine="remotion",title=None):
    """Start an editable project from actual footage, retaining its audio."""
    import math
    from .media import probe,command,FFMPEG,safe_asset_path
    from .models import PROFILES
    source=Path(path).resolve(strict=True)
    if not source.is_file() or source.stat().st_size>500*1024*1024:
        raise ValueError("Source video <=500MB required")
    info=probe(source)
    duration=float(info["format"].get("duration",0));video=next((s for s in info["streams"] if s["codec_type"]=="video"),None)
    if not video or not 1/30<=duration<=3600:
        raise ValueError("Video source required; 1 frame..1 hour")
    p=create({"title":title or source.stem,"profile":profile,"renderer":engine,"captions":False})
    pid=p["id"];asset=import_media(pid,str(source),"source footage","evidence")
    frames=math.floor(duration*30+.02);seconds=frames/30  # containers round duration to ms: 856 frames read 28.533 s
    voice=store.folder(pid)/"source-audio.wav"
    audio=any(s["codec_type"]=="audio" for s in info["streams"])
    if audio:
        command([FFMPEG,"-y","-v","error","-i",safe_asset_path(pid,asset["id"]),"-vn","-af",f"apad,atrim=duration={seconds}","-ar","48000","-ac","1","-c:a","pcm_s16le",voice])
    else:
        command([FFMPEG,"-y","-v","error","-f","lavfi","-i","anullsrc=r=48000:cl=mono","-t",seconds,"-c:a","pcm_s16le",voice])
    # the extracted sound keeps its source's provenance: a reel's picture may be free while its sound is not
    narration=import_media(pid,str(voice),"source audio",provenance={"operation":"extract audio","source_sha256":asset["sha256"]} if audio
                           else {"operation":"generated silence"})  # a silent source gets EditVideo's own silence: nothing to license
    p=store.get_project(pid);store.update_project(pid,{**p["config"],"narration_id":narration["id"]})
    p=store.get_project(pid);w,h=PROFILES[profile]
    timeline=Timeline(width=w,height=h,total_frames=frames,audio_samples=frames*1600,timing_method="source_video_audio" if audio else "source_video_silent",
        beats=[],cues=[],shots=[{"id":"source-001","beat_id":"source","start_frame":0,"end_frame":frames,"asset_id":asset["id"],"motion":"hold","fit":"contain","role":"evidence"}])
    plan=store.folder(pid)/"plan";plan.mkdir(exist_ok=True);shutil.copyfile(voice,plan/"voice.wav")
    store.write_json(plan/"words.json",{"method":timeline.timing_method,"words":[]})
    store.write_json(plan/"timeline.json",timeline.model_dump())
    store.write_json(plan/"plan-meta.json",{"revision":p["revision"],"audio_hash":sha256(plan/"voice.wav"),"timeline_hash":sha256(plan/"timeline.json")})
    return {**read(pid),"import_notes":"Source audio retained; last fractional frame dropped to keep exact 30fps duration. Original footage copied, output profile contains it. Transcribe then apply cues if captions are wanted."}
