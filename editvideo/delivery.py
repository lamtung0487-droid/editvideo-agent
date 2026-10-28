"""Durable incremental picture repair and verified delivery. Copy untouched H.264, render only changed frames.

An immutable base job is required for section reuse; declared timeline changes must fit the patch. Captions travel
as selectable English text and sidecars. Source media, original videos and custom code are never overwritten.
"""
import copy
import json
import math
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from filelock import FileLock
from . import store
from .media import FFMPEG, probe, sha256, command


class DeliveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    base_revision: int = Field(ge=1)
    base_job_id: str
    caption_path: str | None = None  # JSON [{start,end,text,raise?}], or UTF-8 SRT
    language: str = Field(default="eng", pattern=r"^[a-z]{3}$")
    patch_frames: list[int] | None = Field(default=None, min_length=2, max_length=2)
    captions_per_second: float = Field(default=17, ge=10, le=25)
    target_lufs: float = Field(default=-16, ge=-24, le=-12)
    true_peak_db: float = Field(default=-1.5, ge=-6, le=-1)
    threads: int = Field(default=2, ge=1, le=4)


def delta_ranges(old, current):
    """Finite, explicit reuse contract: layout/text-only layers, no altered media/timing/narration/canvas.

    For a start-only edit the changed picture ends at the old/new start (not at the end of a 100s held layer).
    Other effects may depend on local time: they require the full affected layer span.
    """
    changed = {k for k in set(old) | set(current) if old.get(k) != current.get(k)}
    if changed - {"layers"}:
        raise ValueError(f"Incremental delivery only supports layer edits; changed {sorted(changed)}. Render a new base job.")
    a, b = ({l["id"]: l for l in t.get("layers", [])} for t in (old, current))
    ranges = []
    for identity in a.keys() | b.keys():
        if a.get(identity) == b.get(identity): continue
        left, right = a.get(identity), b.get(identity)
        if (left or right).get("kind") in ("video", "image", "scene3d"):
            raise ValueError("Changed media/3D layers require a new base render (proxy and resource identity)")
        if left and right and {k for k in left.keys() | right.keys() if left.get(k) != right.get(k)} == {"start_frame"} and not left.get("keyframes") and not right.get("keyframes") and not left.get("effects") and not right.get("effects"):
            ranges.append([min(left["start_frame"], right["start_frame"]), max(left["start_frame"], right["start_frame"])])
        else:
            ranges.append([min(l["start_frame"] for l in (left, right) if l), max(l["end_frame"] for l in (left, right) if l)])
    return ranges


def prepare(request, out):
    """Snapshot inputs at submit so a later project edit cannot change this task's output."""
    from . import agent
    import uuid
    q = DeliveryRequest.model_validate(request)
    uuid.UUID(q.project_id); uuid.UUID(q.base_job_id)
    out = Path(out)
    with FileLock(str(store.folder(q.project_id) / "delivery.lock"), timeout=20):
        p = agent.read(q.project_id)
        if p["revision"] != q.base_revision: raise ValueError("Revision conflict; reread project")
        job = store.get_job(q.base_job_id)
        if job["project_id"] != q.project_id or job["kind"] != "final" or job["state"] != "completed":
            raise ValueError("A verified completed final job belonging to this project is required")
        base = store.folder(q.project_id) / "jobs" / q.base_job_id
        original, current = store.read_json(base / "timeline.json"), p["timeline"]
        delta = delta_ranges(original, current)
        if q.patch_frames and not 0 <= q.patch_frames[0] < q.patch_frames[1] <= current["total_frames"]:
            raise ValueError("patch_frames must be an in-range half-open frame window")
        if delta and (not q.patch_frames or any(a < q.patch_frames[0] or b > q.patch_frames[1] for a, b in delta)):
            raise ValueError(f"Patch window must contain every affected frame: {delta[:8]}")
        saved_config = store.read_json(base / "source/input.json")["config"]
        if saved_config != p["config"]: raise ValueError("Config changed since base render; render a new base job")
        technical = store.read_json(base / "technical.json")
        video = base / "final.mp4"
        if not technical.get("decoded") or sha256(video) != technical.get("sha256"):
            raise ValueError("Base video changed or lacks decoded evidence")
        captions = []
        if q.caption_path:
            from .study import parse_subtitles
            src = Path(q.caption_path).resolve(strict=True)
            captions = store.read_json(src) if src.suffix.lower() == ".json" else parse_subtitles(src)
        elif (store.folder(q.project_id) / "plan/subtitles" / (q.language + ".json")).exists():
            captions = store.read_json(store.folder(q.project_id) / "plan/subtitles" / (q.language + ".json"))
        from . import subtitles
        captions = subtitles.readable(captions, current["total_frames"] / 30, q.captions_per_second)
        out.mkdir(parents=True, exist_ok=True)
        store.write_json(out / "timeline.json", current)
        from . import narrative
        meaning, meaning_status=narrative.document(q.project_id,current)
        if meaning_status=='ready':store.write_json(out/'meaning.json',meaning)
        store.write_json(out / "captions.json", captions)
        payload = store.read_json(base / "source/input.json")
        # Keep render-time media remapping and fitted tracking from the original snapshot. Replace only actual deltas.
        old_by = {l["id"]: l for l in original["layers"]}; new_by = {l["id"]: l for l in current["layers"]}
        changed = {k for k in old_by.keys() | new_by.keys() if old_by.get(k) != new_by.get(k)}
        payload["timeline"]["layers"] = [new_by[l["id"]] if l["id"] in changed else l for l in payload["timeline"]["layers"] if l["id"] in new_by]
        payload["timeline"]["layers"] += [l for l in current["layers"] if l["id"] not in old_by]
        store.write_json(out / "payload.json", payload)
        store.write_json(out / "inputs.json", {"base_folder": str(base), "base_sha256": technical["sha256"],
                          "revision": p["revision"], "delta_ranges": delta, "caption_report": subtitles.report(captions)})
    return q.model_dump()


def keyframe_window(video, window, total):
    from .media import FFPROBE
    args = [FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_packets", "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", str(video)]
    r = subprocess.run(args, capture_output=True, text=True, check=True, timeout=120)
    keys = [0, total]
    for line in r.stdout.splitlines():
        parts = line.split(",")
        if len(parts) >= 2 and "K" in parts[-1]:
            try: keys.append(round(float(parts[0]) * 30))
            except ValueError: pass
    a = max(f for f in keys if f <= window[0])
    b = min(f for f in keys if f >= window[1])
    return a, b


def splice(video, patch, start, end, total, out, cancelled=lambda: False, threads=2):
    """Copy GOP-aligned unchanged H.264 segments, replace one exact frame range, then verify frame count/timestamps."""
    work = Path(out).parent
    parts = []
    if start:
        p = work / "prefix.mp4"
        command([FFMPEG, "-y", "-v", "error", "-i", video, "-frames:v", start, "-map", "0:v:0", "-c:v", "copy", "-an", p], cancelled=cancelled)
        parts.append(p)
    parts.append(Path(patch))
    if end < total:
        p = work / "suffix.mp4"
        command([FFMPEG, "-y", "-v", "error", "-ss", end / 30, "-i", video, "-frames:v", total - end, "-map", "0:v:0", "-c:v", "copy", "-an", p], cancelled=cancelled)
        parts.append(p)
    listing = work / "parts.txt"
    durations = ([start / 30] if start else []) + [(end - start) / 30] + ([(total - end) / 30] if end < total else [])
    listing.write_text("".join("file '" + str(p.resolve()).replace("\\", "/").replace("'", "'\\''") + f"'\nduration {d:.9f}\n" for p, d in zip(parts, durations)), encoding="utf-8")
    command([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", listing, "-map", "0:v:0", "-c", "copy", "-an", "-movflags", "+faststart", out], cancelled=cancelled)
    from .media import frame_grid
    grid = frame_grid(out, 30)
    if grid["frames"] != total or grid["irregular_count"]:
        raise ValueError(f"Incremental splice did not preserve frame grid: {grid}; original is unchanged")
    return grid


def loudness(path, cancelled=lambda: False):
    text = command([FFMPEG, "-nostdin", "-v", "info", "-i", path, "-vn", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], cancelled=cancelled, timeout=600)
    hits = re.findall(r'\{[^{}]*"input_i"[^{}]*\}', text, re.S)
    if not hits: raise ValueError("Audio loudness could not be measured")
    return json.loads(hits[-1])


def process(task_id, request):
    from . import media_tasks, subtitles
    from .code_engine import ENGINES, engine_env, link_media_copy
    q = DeliveryRequest.model_validate(request)
    out = media_tasks.folder(task_id)
    record = store.read_json(out / "inputs.json")
    base = Path(record["base_folder"])
    video = base / "final.mp4"
    timeline = store.read_json(out / "timeline.json")
    total = timeline["total_frames"]
    cancel = lambda: media_tasks.cancelled(task_id)
    media_tasks.update(task_id, progress=.05, message="Reading verified base render")
    if sha256(video) != record["base_sha256"]: raise ValueError("Base artifact changed since submit")
    picture = video
    render_frames = 0
    grid = None
    if q.patch_frames:
        payload = store.read_json(out / "payload.json")
        if payload["config"].get("renderer") != "remotion": raise ValueError("Incremental picture repair currently uses Remotion")
        a, b = keyframe_window(video, q.patch_frames, total)
        source = out / "source"
        shutil.copytree(base / "source", source, copy_function=link_media_copy)
        store.write_json(source / "input.json", payload)
        env = {**engine_env(q.project_id), "EDITVIDEO_FRAME_RANGE": f"{a}-{b-1}", "EDITVIDEO_RENDER_CONCURRENCY": "2", "EDITVIDEO_VIDEO_CACHE_MB": "256",
               "TEMP": str(out / "tmp"), "TMP": str(out / "tmp")}
        (out / "tmp").mkdir(exist_ok=True)
        media_tasks.update(task_id, progress=.15, message=f"Rendering only frames {a}..{b} of {total}")
        patch = out / "section.mp4"
        command(["node", ENGINES / "render-remotion.mjs", source, patch, "final"], cwd=ENGINES, env=env, cancelled=cancel, log=out / "section.log", timeout=1800)
        render_frames = b - a
        picture = out / "picture.mp4"
        grid = splice(video, patch, a, b, total, picture, cancel, q.threads)
    media_tasks.update(task_id, progress=.5, message="Audio headroom and caption packaging (picture copied)")
    cues = store.read_json(out / "captions.json")
    srt, ass = out / ("final." + q.language + ".srt"), out / ("final." + q.language + ".ass")
    srt.write_text(subtitles.to_srt(cues), encoding="utf-8")
    ass.write_text(subtitles.to_ass(cues, timeline["width"], timeline["height"]), encoding="utf-8")
    before = loudness(video, cancel)
    gain = min(0, q.target_lufs - float(before["input_i"]), q.true_peak_db - .7 - float(before["input_tp"]))  # never boost the existing mix
    final = out / "final.mp4"
    attempts = []
    for attempt in range(3):
        args = [FFMPEG, "-y", "-v", "error", "-i", picture, "-i", video]
        if cues: args += ["-i", srt]
        args += ["-map", "0:v:0", "-map", "1:a:0"]
        if cues: args += ["-map", "2:0", "-c:s", "mov_text", "-metadata:s:s:0", "language=" + q.language, "-disposition:s:0", "default"]
        args += ["-c:v", "copy", "-af", f"volume={gain:.4f}dB", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-threads", q.threads,
                 "-t", total / 30, "-movflags", "+faststart", final]
        command(args, cancelled=cancel, timeout=900, log=out / "finish.log")
        after = loudness(final, cancel)
        attempts.append({"gain_db": gain, "measured": after})
        if float(after["input_tp"]) <= q.true_peak_db + .05: break
        gain -= float(after["input_tp"]) - q.true_peak_db + .35
    else: raise ValueError("Encoded AAC could not meet the requested peak ceiling")
    command([FFMPEG, "-v", "error", "-xerror", "-threads", q.threads, "-i", final, "-f", "null", "-"], cancelled=cancel, timeout=900)
    info = probe(final)
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    if int(vs["nb_frames"]) != total: raise ValueError("Final frame count differs from project")
    report = {"project_id": q.project_id, "revision": q.base_revision, "base_job_id": q.base_job_id, "base_sha256": record["base_sha256"],
              "frames": total, "rendered_frames": render_frames, "reused_picture_frames": total - render_frames, "frame_grid": grid,
              "decoded": True, "caption_report": subtitles.report(cues), "caption_timing": "Reading reflow within nearby translation groups, not forced alignment",
              "audio_before": before, "audio_attempts": attempts, "target_lufs": q.target_lufs,
              "audio_note": "Existing mix preserved; attenuation for AAC headroom may lower integrated loudness", "sha256": sha256(final)}
    store.write_json(out / "delivery.json", report)
    media_tasks.update(task_id, progress=.9, message="Packaging exact captions and editable repair inputs")
    archive = out / "delivery.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        oldzip = base / "delivery.zip"
        if oldzip.exists():
            with zipfile.ZipFile(oldzip) as old:
                for name in old.namelist():
                    if name not in {"timeline.json", "source/input.json", "delivery.json", "captions.srt", "meaning.json"}:
                        z.writestr(name, old.read(name))
        z.write(out / "timeline.json", "timeline.json")
        z.write(out / "payload.json", "source/input.json")
        for p in (srt, ass, out / "captions.json", out / "delivery.json"): z.write(p, p.name)
        if (out/'meaning.json').exists():z.write(out/'meaning.json','meaning.json')
        z.writestr("REPAIR.txt", "Original authored source retained. Current timeline/input included. The encoded master uses the base job plus the declared incremental section and audio/caption finishing. See delivery.json.\n")
    # Only task intermediates; retain exact source snapshot/report for reproducibility.
    for name in ("prefix.mp4", "suffix.mp4", "picture.mp4", "section.mp4"): (out / name).unlink(missing_ok=True)
    shutil.rmtree(out / "tmp", ignore_errors=True)
    return {"video": str(final), "report": report, "artifacts": {"video": str(final), "subtitles": str(srt), "styled_subtitles": str(ass), "package": str(archive)}}
