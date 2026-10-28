"""Study a reference or tutorial video in one call: editorial rhythm, transcript, technique mentions, where text/UI is on
screen, music/cut alignment, and token-lean visual evidence (one timestamped sheet, optional dense strips).

Built from the manual procedure that worked when learning from professional videos: detect cuts, sample an overview
sheet, read the narration, then look densely only where a technique is demonstrated. The full breakdown is written to
disk; the call returns a compact summary so the model reads details on demand.
"""
import html
import json
import math
import re
import subprocess
import uuid
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from . import store
from .media import FFMPEG, command, probe, sha256

# Vocabulary of professional editing, motion design, VFX, colour and sound. Category → terms (regex-safe, lower case).
GLOSSARY = {
    "editing": ["j cut", "j-cut", "l cut", "l-cut", "match cut", "jump cut", "cutaway", "cross cut", "crosscut", "cross-cutting", "montage", "smash cut",
                "cut on action", "b-roll", "a-roll", "pacing", "rhythm", "ripple edit", "roll edit", "slip edit", "slide edit", "nest", "adjustment layer",
                "speed ramp", "time remapping", "time remap", "freeze frame", "reverse", "whip pan", "zoom transition", "wipe", "dissolve", "dip to black",
                "fade", "transition", "pattern interrupt", "retention", "hook", "storytelling", "beat", "on the beat", "jump zoom", "punch in", "punch-in"],
    "motion": ["ease", "easy ease", "graph editor", "speed graph", "value graph", "bezier", "overshoot", "anticipation", "follow through", "squash",
               "stretch", "motion blur", "offset", "stagger", "parent", "null object", "expression", "wiggle", "loopout", "trim paths", "repeater",
               "shape layer", "precomp", "pre-compose", "text animator", "range selector", "tracking", "kerning", "kinetic", "typography", "displacement",
               "turbulent displace", "echo", "glow", "lens flare", "chromatic aberration", "rgb split", "glitch", "grain", "vignette", "light leak", "parallax",
               "3d layer", "camera", "depth of field", "keyframe", "mask", "track matte", "alpha matte", "luma matte", "blend mode", "opacity", "slit scan"],
    "vfx": ["rotoscope", "rotoscoping", "roto brush", "refine edge", "keying", "green screen", "chroma key", "keylight", "camera tracker", "3d camera tracker",
            "planar track", "mocha", "point track", "motion track", "stabilize", "warp stabilizer", "content-aware fill", "compositing", "clean plate",
            "matte", "spill", "object matte", "solve camera", "track point"],
    "color": ["color grading", "colour grading", "color correction", "colour correction", "lut", "log", "rec 709", "rec.709", "white balance", "exposure",
              "contrast", "saturation", "curves", "hsl", "qualifier", "color wheels", "lift", "gamma", "gain", "scopes", "waveform", "vectorscope", "parade",
              "skin tone", "node", "serial node", "parallel node", "power window", "film look", "halation", "teal and orange", "split toning", "film grain"],
    "sound": ["sound design", "sound effect", "sfx", "foley", "ambience", "ambient", "room tone", "riser", "whoosh", "swoosh", "impact", "hit", "eq",
              "equalizer", "compression", "compressor", "reverb", "ducking", "sidechain", "lufs", "loudness", "music bed", "audio levels", "decibel",
              "crossfade", "low pass", "high pass", "build up", "drop"],
}


def _clock(s):
    return f"{int(s // 60):02d}:{int(s % 60):02d}"


def parse_subtitles(path):
    """VTT/SRT → [{start, end, text}]. YouTube auto captions repeat the previous line in each rolling cue and carry inline
    word timings; keep each new line once."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    cues, seen_last = [], ""
    t = lambda s: sum(float(x) * 60 ** i for i, x in enumerate(reversed(s.replace(",", ".").split(":"))))
    for block in re.split(r"\n\s*\n", raw):
        m = re.search(r"(\d{1,2}:?\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{1,2}:?\d{2}:\d{2}[.,]\d{3})", block)
        if not m:
            continue
        body = block[m.end():]
        body = body.split("\n", 1)[1] if "\n" in body else ""  # cue settings (align:start position:0%) share the timing line
        lines = [re.sub(r"<[^>]+>", "", ln).strip() for ln in body.splitlines()]
        lines = [html.unescape(ln) for ln in lines if ln]
        if not lines:
            continue
        a, b = t(m.group(1)), t(m.group(2))
        if b - a < .05:  # zero-length transition cues in auto captions
            continue
        new = [ln for ln in lines if ln != seen_last]
        if not new:
            continue
        text = " ".join(new)
        if cues and text == cues[-1]["text"]:
            cues[-1]["end"] = b
            continue
        cues.append({"start": round(a, 2), "end": round(b, 2), "text": text})
        seen_last = lines[-1]
    return cues


# Words whose everyday sense dominates tutorial narration ("hit enter", "drag and drop", "log in"): measured on 46
# studies, at least 44 % of "hit" and 67 % of "drop" lines were UI instructions. "hit"/"drop" count only as part of a
# sound phrase ("hit sound", "bass drop"); "log", "impact" and "reverse" need a craft phrase or a context word in the
# caption line or a neighbouring one (captions split sentences). Bracketed caption tags ("[Music]") are not context.
CRAFT_PHRASE = {
    "hit": re.compile(r"\bhits? (?:sounds?|sfx|effects?|points?|markers?|on the (?:beat|cut|downbeat)s?|the (?:beat|downbeat)s?)\b|"
                      r"\b(?:sound|sfx|impact|bass|drum|audio|cinematic|braam|sub) hits?\b|\bon the hits?\b"),
    "drop": re.compile(r"\b(?:bass|beat|music|song|sub|track|energy) drops?\b|\bdrops? (?:of|in) the (?:beat|music|song|track)\b|"
                       r"\bthe drop (?:hits|lands|comes)\b"),
    "log": re.compile(r"\b[sfvc]-?log\b|\blog[- ]?[c3]\b|\b(?:pre|post)[- ]?log\b|\blog (?:footage|profiles?|images?|wheels?|nodes?|"
                      r"space|curves?|gamma|encoded|conversion|to rec)\b"),
}
CONTEXT = {
    "impact": {"sound", "sounds", "sfx", "audio", "effect", "effects", "hit", "hits", "cut", "cuts", "frame", "frames", "moment",
               "emotional", "title", "titles"},
    "log": {"footage", "lut", "luts", "gamma", "color", "colour", "colors", "camera", "cameras", "profile", "profiles", "rec",
            "slog", "clog", "flat", "grade", "grading", "convert", "converted", "conversion", "space", "node", "nodes", "transform",
            "cst", "wheel", "wheels"},
    "reverse": {"clip", "clips", "speed", "playback", "cymbal", "cymbals", "symbol", "footage", "play", "time", "transition",
                "transitions", "effect", "effects", "motion", "shot", "shots", "angle", "angles", "impact", "sound", "sfx", "riser"},
}
PHRASE_ONLY = {"hit", "drop"}
UI_INSTRUCTION = {
    "hit": re.compile(r"\bhit (?:the |a )?(?:ctrl|control|cmd|command|alt|shift|enter|return|space\w*|tab|delete|backspace|play|apply|"
                      r"ok|okay|save|render|export|subscribe|like|record|create|done|f\d+|[a-z])\b"),
    "drop": re.compile(r"\bdrag\b|\bdrop (?:it|this|them|these|those|down|in|into|onto|on)\b"),
    "log": re.compile(r"\blog ?(?:in|out)\b|\blogin\b"),
}


def _clean(text):
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", " ", text.lower())).strip()


def _phrase_here(phrase, low, near):
    """The craft phrase is in this line, or runs across its boundary with a neighbouring caption line."""
    if phrase.search(low):
        return True
    i = near.find(low.strip())
    return i >= 0 and any(m.start() < i + len(low.strip()) and m.end() > i for m in phrase.finditer(near))


def craft_sense(term, line, around=None):
    """False when an ambiguous term is used in its everyday sense here ('hit enter', 'drag and drop', 'log in')."""
    if term not in CRAFT_PHRASE and term not in CONTEXT:
        return True
    low, near = _clean(line), _clean(around or line)
    phrase = CRAFT_PHRASE.get(term)
    if phrase and _phrase_here(phrase, low, near):
        return True
    if term in PHRASE_ONLY or (term in UI_INSTRUCTION and UI_INSTRUCTION[term].search(low)):
        return False
    if phrase and phrase.search(near):  # e.g. a node named "log" right after a "pre-log" line
        return True
    return bool(CONTEXT.get(term, set()) & (set(re.findall(r"[a-z0-9]+", near)) - {term}))


def glossary_hits(cues, limit_per_term=6):
    found = {}
    for i, c in enumerate(cues):
        low = " " + c["text"].lower() + " "
        # Auto captions split sentences into short cues: judge an ambiguous term with its neighbours' words too.
        around = " ".join(x["text"] for x in cues[max(0, i - 1):i + 2])
        for cat, terms in GLOSSARY.items():
            for term in terms:
                if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", low) and craft_sense(term, low, around):
                    found.setdefault(cat, {}).setdefault(term, []).append(c["start"])
    out = {}
    for cat, terms in found.items():
        ranked = sorted(terms.items(), key=lambda kv: -len(kv[1]))
        out[cat] = {term: {"count": len(ts), "at": [_clock(x) for x in ts[:limit_per_term]]} for term, ts in ranked[:25]}
    return out


def _grab(path, t, width):
    """One frame at time t as RGB (fast seek; cheap for the <=60 frames a sheet needs)."""
    import subprocess
    p = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={width}:-2",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=60)
    if p.returncode or not p.stdout:
        return None
    w = width
    h = len(p.stdout) // (w * 3)
    return np.frombuffer(p.stdout[: w * h * 3], np.uint8).reshape(h, w, 3)


def sheet(path, times, out, width=320, cols=6):
    frames = [(t, _grab(path, t, width)) for t in times]
    frames = [(t, f) for t, f in frames if f is not None]
    if not frames:
        return None, []
    h = frames[0][1].shape[0]
    rows = math.ceil(len(frames) / cols)
    canvas = Image.new("RGB", (cols * (width + 4), rows * (h + 4)), (60, 60, 60))
    d = ImageDraw.Draw(canvas)
    for i, (t, f) in enumerate(frames):
        x, y = (i % cols) * (width + 4), (i // cols) * (h + 4)
        canvas.paste(Image.fromarray(f), (x, y))
        d.rectangle([x, y, x + 62, y + 16], fill=(0, 0, 0))
        d.text((x + 4, y + 3), _clock(t), fill=(255, 230, 0))
    canvas.save(out, quality=82)
    return str(out), frames


def text_density(frame):
    """Share of small high-contrast edges: flat UI panels and on-screen text score high, natural footage low."""
    import cv2
    g = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    e = cv2.Canny(g, 80, 200)
    return float((e > 0).mean())


def _ghosts_both(s0, e0, mid):
    """In a real dissolve the middle frame carries edges of BOTH ends (double exposure). A camera move or a turning
    object makes edges that match neither end. Flat ends (few edges) cannot be judged and pass."""
    import cv2
    edge = lambda f: cv2.Canny((np.clip(f, 0, 1) * 255).astype(np.uint8), 30, 90) > 0
    es, ee, em = edge(s0), edge(e0), edge(mid)
    if es.sum() < 25 or ee.sum() < 25:
        return True
    k = np.ones((3, 3), np.uint8)
    grow = lambda e: cv2.dilate(e.astype(np.uint8), k) > 0
    only_s, only_e = es & ~grow(ee), ee & ~grow(es)  # edges unique to each end
    if only_s.sum() < 10 or only_e.sum() < 10:
        return True
    gm = grow(em)
    return (gm & only_s).sum() / only_s.sum() > .3 and (gm & only_e).sum() / only_e.sum() > .3


def _motion_explains(s0, e0, mid):
    """True when the middle frame is better explained by moving one end (zoom 0.85-1.18x, shift up to 4 px at 80 px
    width) than by blending the two ends: a zoom or pan inside one shot, not a dissolve."""
    import cv2
    h, w = mid.shape
    span = e0 - s0
    a = float(((mid - s0) * span).sum() / max(1e-9, (span * span).sum()))
    blend = float(np.abs(mid - (s0 + np.clip(a, 0, 1) * span)).mean())
    best = 1e9
    for src in (s0, e0):
        for sc in (.85, .9, .95, 1.05, 1.1, 1.18):
            for dx in (-4, 0, 4):
                for dy in (-2, 0, 2):
                    M = np.float32([[sc, 0, (1 - sc) * w / 2 + dx], [0, sc, (1 - sc) * h / 2 + dy]])
                    warped = cv2.warpAffine(src, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
                    best = min(best, float(np.abs(mid - warped).mean()))
    return best < .7 * blend


def transitions(path, duration, fps=8, size=(80, 45)):
    """Find gradual transitions that pixel-change cut detection misses: dips/fades through black or white (luminance
    runs), dissolves (middle frames fit a linear blend of the two ends), and whip/blur transitions (sharpness collapses
    while the picture changes fast). Times are in seconds; durations are accurate to one sample (1/fps)."""
    import subprocess
    import cv2
    w, h = size
    p = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, timeout=1800)
    if p.returncode or not p.stdout:
        return {"events": [], "counts": {}, "error": "decode failed"}
    fr = np.frombuffer(p.stdout, np.uint8)[: len(p.stdout) // (w * h) * w * h].reshape(-1, h, w).astype(np.float32) / 255
    n = len(fr)
    if n < 6:
        return {"events": [], "counts": {}}
    L = fr.mean((1, 2))
    D = np.r_[0, np.abs(np.diff(fr, axis=0)).mean((1, 2))]
    S = np.array([cv2.Laplacian(f, cv2.CV_32F).var() for f in fr])
    t = lambda i: round(i / fps, 2)
    events = []
    # Dips and fades: runs of near-black or near-white frames.
    sd = fr.std((1, 2))
    # A dip frame is dark (or bright) AND nearly uniform: a dark graphic with content is not a dip.
    for kind, mask in (("black", (L < .035) & (sd < .03)), ("white", (L > .93) & (sd < .04))):
        i = 0
        while i < n:
            if not mask[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            a, b = max(0, i - 6), min(n - 1, j + 6)
            ramp_in = i > 0 and L[a:i].size and (abs(L[a] - L[i]) > .08)
            ramp_out = j < n - 1 and (abs(L[b] - L[j]) > .08)
            hold = (j - i + 1) / fps
            if i == 0 and ramp_out:
                typ = f"fade_in_from_{kind}"
            elif j == n - 1 and ramp_in:
                typ = f"fade_out_to_{kind}"
            elif ramp_in and ramp_out and hold <= 3:
                typ = f"dip_to_{kind}"
            else:
                typ = f"{kind}_hold" if hold >= 1 else None
            if typ:
                events.append({"type": typ, "start": t(a if ramp_in else i), "end": t(b if ramp_out else j), "hold_s": round(hold, 2)})
            i = j + 1
    # Dissolves: elevated change for 0.4-3 s whose middle frames are blends of the two ends.
    busy = D > .012
    i = 1
    while i < n - 1:
        if not busy[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and busy[j + 1]:
            j += 1
        length = (j - i + 1) / fps
        s0, e0 = fr[max(0, i - 1)], fr[min(n - 1, j + 1)]
        span = e0 - s0
        denom = float((span * span).sum())
        if .4 <= length <= 3 and denom > (w * h) * .004 and np.mean(L[i:j + 1]) > .05:
            alphas, res = [], []
            for k in range(i, j + 1):
                a = float(((fr[k] - s0) * span).sum() / denom)
                alphas.append(a)
                res.append(float(np.abs(fr[k] - (s0 + a * span)).mean() / (np.abs(span).mean() + 1e-6)))
            mono = all(b >= a - .08 for a, b in zip(alphas, alphas[1:]))
            if mono and np.mean(res) < .35 and alphas[0] < .45 and alphas[-1] > .55 and S[i:j + 1].min() > .25 * np.median(S) \
                    and _ghosts_both(s0, e0, fr[(i + j) // 2]) and not _motion_explains(s0, e0, fr[(i + j) // 2]):
                events.append({"type": "dissolve", "start": t(i - 1), "end": t(j + 1), "duration_s": round(length + 1 / fps, 2)})
        i = j + 1
    # Whips / blur transitions: sharpness collapses (<35% of its local level) while the picture changes fast.
    local = np.array([np.median(S[max(0, k - 12):k + 13]) for k in range(n)])
    blur = (S < .35 * local) & (D > .03)
    i = 0
    while i < n:
        if not blur[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and blur[j + 1]:
            j += 1
        before, after = fr[max(0, i - 2)], fr[min(n - 1, j + 2)]
        # A whip joins two different shots; blur inside one continuing shot (action, smoke, defocus) is not a transition.
        # Fades also lose sharpness, but one end of a fade is a flat frame; a whip has picture content on both sides.
        if 1 <= j - i + 1 <= 10 and float(np.abs(after - before).mean()) > .07 and min(before.std(), after.std()) > .05 and L[i:j + 1].mean() > .05:
            events.append({"type": "whip_or_blur", "start": t(i), "end": t(j + 1), "duration_s": round((j - i + 2) / fps, 2)})
        i = j + 1
    events.sort(key=lambda e: e["start"])
    counts = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    return {"events": events, "counts": counts, "sample_fps": fps}


def subtitle_path(source, explicit=None):
    """Match subtitles to THIS video; an unrelated sibling must never become its narration."""
    if explicit:
        return Path(explicit).resolve(strict=True)
    rank = lambda p: (0 if re.search(r"\.en\.(vtt|srt)$", p.name) else 1 if ".en-" in p.name and "orig" not in p.name else 2, p.name)
    return next(iter(sorted((p for p in source.parent.glob("*") if p.suffix.lower() in (".vtt", ".srt")
                            and (p.stem == source.stem or p.name.startswith(source.stem + "."))), key=rank)), None)


def study_video(path, subtitles=None, sheet_frames=30, strips=None, beats=True):
    from .perception import index_video
    source = Path(path).resolve(strict=True)
    info = probe(source)
    duration = float(info["format"].get("duration", 0))
    if not 0 < duration <= 3600:
        raise ValueError("Video up to 1 hour")
    if not 6 <= sheet_frames <= 60:
        raise ValueError("sheet_frames 6..60")
    if any(not 0 <= a < b <= duration or b - a > 60 for a, b in strips or []):  # checked before minutes of analysis
        raise ValueError("strip windows must be inside the video and at most 60 s")
    source_hash = sha256(source)
    study_id = "study-" + source_hash[:16]
    out = store.DATA / "observations" / study_id
    out.mkdir(parents=True, exist_ok=True)
    idx = index_video(str(source), 10, 0, 100)
    data = store.read_json(Path(idx["index_path"]))
    segs = data["segments"]
    lengths = np.array([s["duration"] for s in segs]) if segs else np.array([duration])
    cuts = [s["start"] for s in segs[1:]]
    bucket = 30.0
    pace = [sum(1 for c in cuts if k * bucket <= c < (k + 1) * bucket) * 60 / bucket for k in range(int(math.ceil(duration / bucket)))]
    holds = sorted(segs, key=lambda s: -s["duration"])[:5]
    samples = data["visual_samples"]
    activity = [round(float(np.mean([s["sampled_pixel_change"] or 0 for s in samples[int(k * bucket):int((k + 1) * bucket)]] or [0])), 4)
                for k in range(len(pace))]
    lum = [s["mean_luminance"] for s in samples]
    palette = {}
    for s in samples:
        for c in s["palette"][:3]:
            rgb = [int(c[i:i + 2], 16) for i in (1, 3, 5)]
            if max(rgb) < 24:  # letterbox/black limbo says little about the grade; reported as dark_frames_share
                continue
            key = "#%02x%02x%02x" % tuple(v // 24 * 24 for v in rgb)  # merge near-identical colours
            palette[key] = palette.get(key, 0) + 1
    summary = {"study_id": study_id, "source_sha256": source_hash, "source": str(source), "duration_s": round(duration, 2), "size": data["source_size"],
               "fps": next((s.get("r_frame_rate") for s in info["streams"] if s["codec_type"] == "video"), None),
               "rhythm": {"shots": len(segs), "cuts_per_min": round(len(cuts) * 60 / duration, 2), "median_shot_s": round(float(np.median(lengths)), 2),
                          "mean_shot_s": round(float(lengths.mean()), 2), "shot_length_cv": round(float(lengths.std() / max(1e-6, lengths.mean())), 3),
                          "pace_cuts_per_min_by_30s": [round(p, 1) for p in pace], "activity_by_30s": activity,
                          "longest_holds": [{"at": _clock(h["start"]), "s": round(h["duration"], 1)} for h in holds]},
               "look": {"mean_luminance": round(float(np.mean(lum)), 3) if lum else None, "dark_frames_share": round(float(np.mean([s["dark_pixel_fraction"] > .6 for s in samples])), 3) if samples else None,
                        "dominant_colors": [c for c, _ in sorted(palette.items(), key=lambda kv: -kv[1])[:8]]}}
    from .learning import reference_meta
    meta = reference_meta(source, duration, study_id)  # publisher title/channel/tags: what a reference is about, for recall
    if meta:
        summary["reference"] = meta
    # Transcript: provided subtitle file, or a sibling .vtt/.srt next to the video.
    # Prefer human captions (.en) over regional/auto originals (.en-orig) when yt-dlp wrote several.
    sub = subtitle_path(source, subtitles)
    cues = parse_subtitles(sub) if sub and sub.exists() else []
    if cues:
        (out / "transcript.txt").write_text("\n".join(f"[{_clock(c['start'])}] {c['text']}" for c in cues), encoding="utf-8")
        words = sum(len(c["text"].split()) for c in cues)
        summary["transcript"] = {"path": str(out / "transcript.txt"), "cues": len(cues), "words": words, "words_per_min": round(words * 60 / duration, 1),
                                 "source": str(sub), "sha256": sha256(sub)}
        summary["techniques_mentioned"] = glossary_hits(cues)
    else:
        summary["transcript"] = None
        summary["note"] = "No subtitles found; run editvideo_transcribe for narration."
    # Music/cut alignment (only meaningful when there is a music bed).
    if beats and any(s["codec_type"] == "audio" for s in info["streams"]) and len(cuts) >= 4:
        try:
            from .music import cut_alignment
            al = cut_alignment(str(source), cuts, 0.0, min(duration, 900.0))
            summary["music"] = {k: al.get(k) for k in ("reading", "lead_frames", "fps", "cuts_on_beat", "chance_p95", "p_value", "downbeat_share_of_on_beat", "cuts_counted")}
            summary["music"]["windows"] = [{k: w[k] for k in ("start", "end", "bpm", "periodicity", "cuts")} for w in al["windows"]][:30]
        except Exception as e:  # beat tracking is optional evidence
            summary["music"] = {"error": str(e)[:120]}
    # Every abrupt edit event (cuts, punch-ins/outs, graphic pops): what retention editors actually pace by.
    try:
        ev = event_profile(source, 0.0, min(duration, 900.0))
        summary["events"] = {k: ev[k] for k in ("events_per_min", "per_min", "gap_s", "first_event_s", "punch_scales")}
        summary["events"]["measured_until_s"] = round(min(duration, 900.0), 2)
        # Keep the timestamped event list with its study (learning windows read it); it used to be left as an
        # unreferenced observations/events-*.json file. If the move fails (file open elsewhere), point at where it is.
        try:
            Path(ev["manifest"]).replace(out / "events.json")
            summary["events"]["list"] = str(out / "events.json")
        except OSError:
            summary["events"]["list"] = ev["manifest"]
    except Exception as e:  # optional evidence
        summary["events"] = {"error": str(e)[:120]}
    # Gradual transitions the cut detector cannot see (dissolves, dips/fades, whips).
    tr = transitions(source, duration)
    summary["transitions"] = {"counts": tr["counts"], "events": tr["events"][:40], "sample_fps": tr.get("sample_fps")}
    all_transitions = tr["events"]  # the reply lists 40; the stored report keeps all (learning windows look them up)
    # Overview sheet + where text/UI dominates the frame.
    times = list(np.linspace(min(1.0, duration * .01), duration - .5, sheet_frames))
    sheet_path, frames = sheet(source, times, out / "overview.jpg")
    dens = [(t, text_density(f)) for t, f in frames]
    summary["on_screen_text_or_ui"] = [_clock(t) for t, d in dens if d > .06][:30]
    summary["sheet"] = sheet_path
    # Every sampled time and its text/UI flag (the reply above lists 30): learning windows say "unknown" between them.
    sheet_samples = [[round(float(t), 2), d > .06] for t, d in dens]
    strip_paths = []
    for k, (a, b) in enumerate(strips or []):
        p, _ = sheet(source, list(np.linspace(a, b - .04, 8)), out / f"strip-{k}-{int(a)}-{int(b)}.jpg", width=480, cols=4)
        strip_paths.append(p)
    summary["strips"] = strip_paths
    store.write_json(out / "study.json", {**summary, "transitions": {**summary["transitions"], "events": all_transitions},
                                          "sheet_samples": sheet_samples, "segments": segs})
    summary["full"] = str(out / "study.json")
    summary["learning_next"] = "Inspect technique windows, then remember_lesson with study_id and source seconds; learning_library retrieves related references and craft cards."
    summary["method"] = ("Cuts are pixel-change candidates (scdet); activity is 1 Hz pixel change, not optical flow; text/UI flags are edge-density "
                         "heuristics; technique mentions are vocabulary matches in the narration — open the strip at those times to see the "
                         "demonstration before turning it into a system feature.")
    return summary


def _gray_frames(source, fps, width, start=0.0, end=None):
    info = probe(source)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    w = width
    h = max(2, round(int(v["height"]) * w / int(v["width"]) / 2) * 2)
    cmd = [FFMPEG, "-v", "error", "-ss", str(start), *(["-t", str(end - start)] if end else []), "-i", str(source), "-vf", f"fps={fps},scale={w}:{h}",
           "-an", "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True, timeout=1800).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[: n * w * h], np.uint8).reshape(n, h, w)


def _gray_iter(source, fps, width, start=0.0, end=None):
    """Decoded grey frames streamed from ffmpeg one at a time (constant memory for hour-long references)."""
    info = probe(source)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    w = width
    h = max(2, round(int(v["height"]) * w / int(v["width"]) / 2) * 2)
    cmd = [FFMPEG, "-v", "error", "-ss", str(start), *(["-t", str(end - start)] if end else []), "-i", str(source), "-vf", f"fps={fps},scale={w}:{h}",
           "-an", "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        while True:
            buf = proc.stdout.read(w * h)
            if len(buf) < w * h:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w)
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()


def event_profile(path, start=0.0, end=None, sample_fps=10, width=480):
    """Classify every abrupt visual event: cut, punch_in / punch_out (same picture rescaled, with scale and fixed point),
    or overlay_pop (a local change: text/graphic appearing). Retention editors count all of these; cut detection alone
    misses 35-46 % of them. Returns rates per minute, gap statistics and A-roll-style holds; the event list goes to disk.
    Two streamed passes (difference signals, then a 4-frame window around each candidate): memory does not grow with
    duration."""
    import cv2
    from collections import deque
    source = Path(path).resolve(strict=True)
    mad, blk, lum, prev = [], [], [], None
    for f in _gray_iter(source, sample_fps, width, start, end):
        if prev is not None:
            d = np.abs(f.astype(np.int16) - prev)
            hh, ww = f.shape[0] // 6, f.shape[1] // 8  # 8 x 6 blocks: a graphic pop changes a few blocks a lot
            mad.append(float(d.mean()))
            blk.append(float(d[: hh * 6, : ww * 8].reshape(6, hh, 8, ww).mean((1, 3)).max()))
            lum.append(float(max(f.mean(), prev.mean())))
        prev = f
    n_fr = len(mad) + 1 if prev is not None else 0
    if n_fr < 3:
        raise ValueError("Video too short")
    mad, blk, lum = np.array(mad), np.array(blk), np.array(lum)
    th = max(10.0, 3 * float(np.median(mad)))
    # Dark-to-dark cuts (night, space) change few grey levels in absolute terms: also accept a change that is large
    # relative to the frames' brightness.
    rel = mad / (lum + 8)
    bth = max(25.0, 3 * float(np.median(blk)))
    peak = lambda arr, k: (k < 2 or arr[k - 1] >= arr[k - 2]) and (k >= len(arr) or arr[k - 1] >= arr[k])
    cand = []
    for i in range(1, n_fr):
        if not (((mad[i - 1] > th or (mad[i - 1] > max(4.0, 3 * float(np.median(mad))) and rel[i - 1] > .2)) and peak(mad, i))
                or (blk[i - 1] > bth and peak(blk, i))):
            continue
        # Edit events are abrupt: the next frame settles (motion inside a shot keeps changing frame after frame).
        nxt = mad[i] if i < len(mad) else 0.0
        nblk = blk[i] if i < len(blk) else 0.0
        if nxt < .5 * mad[i - 1] or nblk < .5 * blk[i - 1]:
            cand.append(i)
    # Soft frames (480 px, defocus, a punch's upscale) give ORB ~20 corners at its default threshold of 20: too few for a
    # stable inlier share (FFmpeg 6.1, 7.1 and 8.1 encodes of one test clip fell on both sides of the cut-off). 10 gives
    # ~130; the extra corners also let RANSAC fit a "rescale" between two unrelated shots, so the pixels confirm it.
    orb = cv2.ORB_create(1500, fastThreshold=10)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    events = []

    def moves_onto(a, b, M):
        """Does a, moved by M, reproduce b? A rescale leaves little difference; a cut leaves most of it."""
        h, w = a.shape
        valid = cv2.warpAffine(np.full_like(a, 255), M, (w, h), flags=cv2.INTER_NEAREST) > 0
        if valid.mean() < .3:  # a punch out to 0.7 covers 49 % of the frame
            return False
        before = np.abs(b.astype(np.int16) - a)[valid].mean()
        return np.abs(b.astype(np.int16) - cv2.warpAffine(a, M, (w, h)))[valid].mean() < .5 * before

    def scale_match(a, b):
        """Same picture rescaled between a and b? → (scale, fixed point) or None (ORB + partial affine, RANSAC)."""
        ka, da = orb.detectAndCompute(a, None)
        kb, db = orb.detectAndCompute(b, None)
        if da is None or db is None or len(ka) < 8 or len(kb) < 8:
            return None, False
        m = [x for x, y in (p_ for p_ in bf.knnMatch(da, db, k=2) if len(p_) == 2) if x.distance < .8 * y.distance]
        if len(m) < 8:
            return None, False
        pa = np.float32([ka[x.queryIdx].pt for x in m])
        pb = np.float32([kb[x.trainIdx].pt for x in m])
        M, inl = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC, ransacReprojThreshold=2.5)
        if M is None or inl is None or inl.sum() < 8:
            return None, False
        sc = float(np.hypot(M[0, 0], M[1, 0]))
        out = ~inl.ravel().astype(bool)
        if abs(sc - 1) <= .03 and inl.mean() > .5 and out.sum() >= 20:
            # Held overlays (titles, labels) match as an identity; the picture behind them may still be rescaled.
            M2, inl2 = cv2.estimateAffinePartial2D(pa[out], pb[out], method=cv2.RANSAC, ransacReprojThreshold=2.5)
            if M2 is not None and inl2 is not None and inl2.sum() >= 12 and inl2.mean() > .3:
                sc2 = float(np.hypot(M2[0, 0], M2[1, 0]))
                if .7 < sc2 < 1.5 and abs(sc2 - 1) > .03:
                    M, sc = M2, sc2
        if not (.7 < sc < 1.5 and abs(sc - 1) > .03):
            return None, bool(inl.mean() > .5)  # same picture, not rescaled (or no shared structure)
        if not moves_onto(a, b, M):  # the corners propose a rescale; the pixels confirm it
            return None, False
        try:
            fx, fy = np.linalg.solve(np.eye(2) - M[:, :2], M[:, 2])
        except np.linalg.LinAlgError:
            fx, fy = a.shape[1] / 2, a.shape[0] / 2
        return {"scale": round(sc, 3), "fixed_point": [round(float(fx) / a.shape[1], 2), round(float(fy) / a.shape[0], 2)]}, True

    def motion_before(i):
        """Continuous motion keeps changing frame after frame; an edit is a single spike (mad before it is small)."""
        before = mad[i - 2] if i >= 2 else 0.0
        return before > .5 * mad[i - 1]

    def judge(i, a, b, after2):
        t = round(start + i / sample_fps, 2)
        d = np.abs(b.astype(np.int16) - a)
        changed = d > 25
        static_after = after2 is not None and changed.any() and np.abs(after2.astype(np.int16) - b)[changed].mean() < 8
        # A punch over a mostly dark frame (space, night) changes only the lit part, which looks like a local change:
        # test for a rescale first whenever a sizeable share of pixels changes.
        punch, same = scale_match(a, b) if changed.mean() > .1 else (None, False)
        if punch:
            events.append({"t": t, "kind": "punch_in" if punch["scale"] > 1 else "punch_out", **punch})
            return
        if a.mean() < 4 and a.std() < 3 and changed.any() and changed.mean() < .35 and static_after:
            ys, xs = np.nonzero(changed)
            if (np.ptp(ys) + 1) * (np.ptp(xs) + 1) < .6 * changed.size:  # a compact graphic onto black: a title, not a shot
                events.append({"t": t, "kind": "overlay_pop", "area": round(float(changed.mean()), 3)})
                return
        if changed.mean() > .1 and not same and not motion_before(i):
            # A sizeable change with no shared structure between the frames is a cut, even when the rest is black.
            events.append({"t": t, "kind": "cut"})
            return
        if .003 < changed.mean() < .35 and (d[~changed].mean() if (~changed).any() else 99) < 3:
            if static_after:  # a local change over an otherwise identical frame: text or a graphic appearing (or leaving)
                events.append({"t": t, "kind": "overlay_pop", "area": round(float(changed.mean()), 3)})
            elif changed.mean() > .02 and not motion_before(i) and not (same or scale_match(a, b)[1]):
                events.append({"t": t, "kind": "cut"})  # dark-to-dark cut: little changes, but nothing is shared
            return  # otherwise a gesture or object moving, not an edit
        if changed.mean() <= .1:
            punch, same = scale_match(a, b)
            if punch:
                events.append({"t": t, "kind": "punch_in" if punch["scale"] > 1 else "punch_out", **punch})
                return
        kind = "overlay_pop" if same and changed.mean() < .35 else "cut"
        events.append({"t": t, "kind": kind})

    pending = deque(cand)
    win = deque(maxlen=4)  # frames j-3 .. j
    j = -1
    for f in _gray_iter(source, sample_fps, width, start, end):
        j += 1
        win.append(f)
        while pending and pending[0] + 2 == j:  # frames i-1, i, i+1, i+2 are in the window
            i = pending.popleft()
            judge(i, win[0], win[1], win[3])
    while pending:  # candidates in the last two frames: no frame two ahead
        i = pending.popleft()
        k = i - (j - len(win) + 1)
        if 1 <= k < len(win):
            judge(i, win[k - 1], win[k], None)
    fr_len = n_fr
    dur = fr_len / sample_fps
    times = [e["t"] for e in events]
    gaps = np.diff([start] + times + [start + dur]) if events else np.array([dur])
    counts = {k: sum(1 for e in events if e["kind"] == k) for k in ("cut", "punch_in", "punch_out", "overlay_pop")}
    out_dir = store.DATA / "observations" / f"events-{uuid.uuid4().hex[:10]}.json"
    store.write_json(out_dir, {"source": str(source), "events": events, "sample_fps": sample_fps})
    return {"events_per_min": round(len(events) / dur * 60, 1), "per_min": {k: round(v / dur * 60, 2) for k, v in counts.items()}, "counts": counts,
            "gap_s": {"median": round(float(np.median(gaps)), 2), "p90": round(float(np.percentile(gaps, 90)), 2), "max": round(float(gaps.max()), 2)},
            "first_event_s": times[0] if times else None,
            "punch_scales": sorted({e["scale"] for e in events if "scale" in e})[:12], "manifest": str(out_dir),
            "reference": "retention edits measured 10.8-14.7 events/min, median gap 3.3-4.2 s; emphasis punches x1.05-1.18"}
