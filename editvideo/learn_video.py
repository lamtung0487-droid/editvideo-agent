"""EditVideo's video sense for learnkit: a video is measured through study_video (rhythm, edit events, transitions,
look, narration, music/cut alignment, text/UI samples) and looked at through inspect_window.

A study is reused when its report for the same content exists; otherwise the video is studied once (about 15-20 s per
10 min). Older reports lack some signals; those features are simply absent, never zero.
"""
import subprocess
from pathlib import Path
from learnkit import senses
from learnkit.senses import feature
from . import store
from .media import sha256


def _study(path):
    from . import study
    src = Path(path).resolve(strict=True)
    folder = store.DATA / "observations" / ("study-" + sha256(src)[:16])
    if not (folder / "study.json").is_file():
        study.study_video(str(src))
    return store.read_json(folder / "study.json"), folder


def _transcript(folder, duration):
    from .learning import _transcript as read
    return read({"transcript": True, "duration_s": duration}, folder)


def _events(folder):
    p = folder / "events.json"
    try:
        rows = store.read_json(p).get("events") if p.is_file() else None
    except (OSError, ValueError, AttributeError):
        rows = None
    return [e for e in rows or [] if isinstance(e, dict) and isinstance(e.get("t"), (int, float))]


def _ui_samples(doc):
    rows = doc.get("sheet_samples")
    if isinstance(rows, list) and rows:
        return [(float(r[0]), bool(r[1])) for r in rows if isinstance(r, list) and len(r) == 2]
    return []


LOOK_KEYS = (("detail", "fine detail (Laplacian RMS / luma std)"), ("isolation", "subject isolation, log2 sharpest/median tile"),
             ("noise", "noise sigma, 8-bit levels"), ("shake_px", "handheld jitter, px at 1920 wide"), ("contrast", "p95-p5 luma, 0..1"),
             ("mean", "exposure level, mean luma 0..1"),  # per part, so a blueprint carries a day-dusk-night arc
             ("saturation", "median saturation, 0..1"), ("warmth", "highlight R-B, -1..1"), ("upscale", "x to fill 1920x1080"))


def _look(path, windows):
    """Cinematography of the picture (editvideo.look) over a few short windows: medians, and the share graded A/C."""
    from .look import measure
    rows = []
    for a, b in windows:
        try:
            rows.append(measure(str(path), a, b))
        except (ValueError, OSError, subprocess.CalledProcessError) as e:  # a window past the end or an undecodable stretch
            import logging
            logging.getLogger(__name__).warning("look not measured at %.1f-%.1f s of %s: %s", a, b, path, e)
    if not rows:
        return {}
    import statistics
    out = {f"look_{k}": feature(round(statistics.median(vals), 4), unit) for k, unit in LOOK_KEYS
           if (vals := [r[k] for r in rows if r.get(k) is not None])}  # noise is None where a frame cannot show it
    out["look_a_share"] = feature(round(sum(r["grade"] == "A" for r in rows) / len(rows), 3), "share of sampled windows graded A")
    out["look_c_share"] = feature(round(sum(r["grade"] == "C" for r in rows) / len(rows), 3), "share graded C (shaky, upscaled, noisy)")
    return out


def _span_features(doc, folder, a, b, path=None):
    dur = max(1e-6, b - a)
    segs = doc.get("segments") or []
    cuts = sum(1 for s in segs[1:] if isinstance(s, dict) and a <= s.get("start", -1) < b)
    tr = [e for e in (doc.get("transitions") or {}).get("events") or [] if isinstance(e, dict) and e.get("start", -1) < b and e.get("end", -1) > a]
    out = {"cuts_per_min": feature(60 * cuts / dur, "cuts/min"), "transitions": feature(len(tr), "gradual transitions")}
    ev = _events(folder)
    if ev:
        inside = [e for e in ev if a <= e["t"] < b]
        out["events_per_min"] = feature(60 * len(inside) / dur, "edit events/min")
        out["punch_ins"] = feature(sum(e.get("kind") == "punch_in" for e in inside), "punch-ins")
        out["overlay_pops"] = feature(sum(e.get("kind") == "overlay_pop" for e in inside), "graphic/text pops")
    cues = _transcript(folder, doc.get("duration_s", 0))
    if cues:
        words = sum(len(t.split()) for s, t in cues if a <= s < b)
        out["words_per_min"] = feature(60 * words / dur, "narration words/min")
    ui = [f for t, f in _ui_samples(doc) if a <= t < b]
    if ui:
        out["text_ui_share"] = feature(sum(ui) / len(ui), "share of sampled frames with text/UI")
    if path is not None and dur >= 1.5:  # one 2 s window in the middle of the part (or the whole of a short one)
        m = (a + b) / 2
        out.update(_look(path, [(max(a, m - 1.0), min(b, m + 1.0))]))
    return out


def repeat_share(path, segs, duration):
    """Share of shots whose middle frame shows the same scene as another shot's (scene_sim: 64x36 grey thumbnails
    inside any letterbox correlating > .85, or an ORB match keeping 30 RANSAC inliers at 480 px, which sees a scene
    shown again from a slightly different moment): how much of a film is the same picture shown again. Thumbnails
    alone had read round 12's fourth remake at 6 % where a third of its shots repeated by features; the exemplar
    reads 6 % either way. None with under 4 shots."""
    from . import scene_sim
    if len(segs) < 4 or not duration:
        return None
    feats = [f for f in (scene_sim.features(str(path), min(max(0.0, duration - .05), (s["start"] + s.get("end", s["start"])) / 2))
                         for s in segs if isinstance(s, dict) and "start" in s) if f is not None]
    if len(feats) < 4:
        return None
    dup, _ = scene_sim.repeats(feats)
    return round(float(dup.mean()), 3)


class VideoSense:
    kind = "video"
    version = "7"  # 3: the look of the picture (editvideo.look); 4: repeated pictures; 5: inside the letterbox; 6: repeats by scene (ORB), exposure level; 7: the kind of picture per shot (source_mix), hard cuts to black, frozen time
    extensions = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi")
    spans = ("t",)

    def measure(self, path, options=None):
        doc, folder = _study(path)
        d = float(doc.get("duration_s") or 0)
        r = doc.get("rhythm") or {}
        segs = doc.get("segments") or []
        f = {"duration_s": feature(d, "s"), "cuts_per_min": feature(r.get("cuts_per_min"), "cuts/min"),
             "median_shot_s": feature(r.get("median_shot_s"), "s"), "shot_length_cv": feature(r.get("shot_length_cv"), "cv"),
             "first_cut_s": feature(segs[1]["start"] if len(segs) > 1 else None, "s"),
             "mean_luminance": feature((doc.get("look") or {}).get("mean_luminance"), "0..1"),
             "dark_frames_share": feature((doc.get("look") or {}).get("dark_frames_share"), "share")}
        ev = doc.get("events") or {}
        if "events_per_min" in ev:
            f.update(events_per_min=feature(ev["events_per_min"], "edit events/min"), first_event_s=feature(ev.get("first_event_s"), "s"),
                     punch_ins_per_min=feature((ev.get("per_min") or {}).get("punch_in"), "/min"),
                     overlay_pops_per_min=feature((ev.get("per_min") or {}).get("overlay_pop"), "/min"))
        tr = doc.get("transitions")
        if isinstance(tr, dict) and d:
            f["transitions_per_min"] = feature(60 * sum((tr.get("counts") or {}).values()) / d, "gradual transitions/min")
            f["dissolves"] = feature((tr.get("counts") or {}).get("dissolve", 0), "dissolves")
        t = doc.get("transcript") or {}
        if t:
            f["words_per_min"] = feature(t.get("words_per_min"), "narration words/min")
        m = doc.get("music") or {}
        if "cuts_on_beat" in m:
            f["cuts_on_beat_share"] = feature(m.get("cuts_on_beat"), "share of cuts on a beat")
        ui = _ui_samples(doc)
        if ui:
            f["text_ui_share"] = feature(sum(x for _, x in ui) / len(ui), "share of sampled frames with text/UI")
        segs_end = [{**x, "end": (segs[i + 1]["start"] if i + 1 < len(segs) else d)} for i, x in enumerate(segs) if isinstance(x, dict) and "start" in x]
        rs = repeat_share(path, segs_end, d)
        if rs is not None:
            f["repeat_share"] = feature(rs, "share of shots that nearly repeat another shot's picture")
        # the look: 2 s windows every ~8 s (at most 24), so a 2-minute film is read in about half a minute
        n = max(1, min(24, int(d // 8)))
        f.update(_look(path, [(d * (i + .5) / n - 1.0, d * (i + .5) / n + 1.0) for i in range(n) if d * (i + .5) / n >= 1.0]))
        # the kind of picture each shot is and how the film mixes them (archive, stage, painterly/AI, CGI, graphics...): an
        # estimate from SigLIP zero-shot, with the strongest shots per kind kept as evidence (round 13, the owner's CCTV gala)
        mix = None
        notes_extra = []
        try:
            from . import source_mix
            mix = source_mix.measure(path, [(x["start"], x["end"]) for x in segs_end if x["end"] > x["start"]])
            for k in source_mix.CATEGORIES:
                f[f"mix_{k}_share"] = feature(mix["share"].get(k, 0.0), f"share of runtime that looks like {k.replace('_', ' ')} (estimate)")
            f["mix_switch_share"] = feature(mix["switch_share"], "share of cuts that change the kind of picture")
            f["mix_median_run_shots"] = feature(mix["median_run_shots"], "shots in a row of one kind, median")
            notes_extra.append("source mix: " + mix["method"] + "; evidence per kind: " +
                               "; ".join(f"{k} {v}" for k, v in list(mix["evidence"].items())[:9]))
        except Exception as e:  # SigLIP not installed, or a study without segments
            notes_extra.append(f"source mix not measured: {e}")
        # what the viewer of the round 13 cuts objected to, measured on any film: cuts straight to black, frozen pictures
        from .review import black_cuts, frozen_share, still_runs
        if d:
            bc = black_cuts(path)
            f["hard_black_cuts_per_10min"] = feature(round(600 * sum(1 for x in bc if x["hard"]) / d, 2), "cuts straight to black per 10 min")
            fz = frozen_share(path)
            f["frozen_share"] = feature(fz["share"], "share of runtime on a frozen (not black) picture")
            f["still_share"] = feature(still_runs(path)["share"], "share of runtime where >= 92 % of the picture stays put for 3 s or more")
        bucket = 5.0 if d <= 90 else 30.0
        parts = []
        for k in range(min(40, int(d // bucket) + (d % bucket > 1))):
            a, b = k * bucket, min(d, (k + 1) * bucket)
            pf = _span_features(doc, folder, a, b, path)
            if mix:  # the kinds of picture inside this part, by time
                inside = {}
                for sh in mix["shots"]:
                    o = max(0.0, min(b, sh["t"][1]) - max(a, sh["t"][0]))
                    if o > 0:
                        inside[sh["category"]] = inside.get(sh["category"], 0.0) + o
                for k, v in inside.items():
                    pf[f"mix_{k}_share"] = feature(round(v / max(b - a, 1e-6), 3), f"share of the part that looks like {k.replace('_', ' ')}")
            parts.append({"span": {"t": [round(a, 2), round(b, 2)]}, "features": pf})
        notes = ["measured through study_video; see its method note", f"study: {folder.name}", *notes_extra]
        if not ev or "events_per_min" not in ev:
            notes.append("edit events not measured in this (older) report")
        return {"features": f, "parts": parts, "notes": notes}

    def fingerprint(self, path, options=None):
        from learnkit import fingerprint
        from learnkit.senses.audio import ffmpeg
        return fingerprint.video_file(Path(path).resolve(strict=True), ffmpeg())

    def measure_span(self, path, span, options=None):
        doc, folder = _study(path)
        a, b = span["t"]
        if b > float(doc.get("duration_s") or 0) + .01:
            raise ValueError("span ends after the video")
        return {"features": _span_features(doc, folder, a, b, path)}

    def evidence(self, path, span, out_dir, options=None):
        from .perception import inspect_window
        a, b = span["t"]
        r = inspect_window(str(path), a, min(b, a + 30), frames=8, width=640, listen=False)
        return [{"type": "image", "path": f["path"], "t": round(f["timestamp"], 2)} for f in r["frames"]]


def install():
    """Point learnkit at EditVideo's data folder and add the video sense (idempotent)."""
    import learnkit.store
    learnkit.store.configure(store.DATA / "learnkit")
    if "video" not in senses.REGISTRY:
        senses.register(VideoSense())
