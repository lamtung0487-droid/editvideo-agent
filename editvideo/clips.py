"""Choosing material for a multi-source edit: windows across many clips ranked by what an edit needs (movement,
sharpness, colour, one continuous take), each with its action peak (where a ramp or an accent lands) and its dominant
direction (so a whip follows the motion), plus match-cut suggestions (the same shape or the same motion on both
sides of a cut). A selection aid with measurements; the story and taste stay with the caller."""
import math
import os
import subprocess
import numpy as np
import cv2
from pathlib import Path
from PIL import Image, ImageDraw
from . import store
from .media import FFMPEG, probe

SR = 6  # analysis frames per second


def _decode(path, seconds=180, width=192):
    v = next(s for s in probe(str(path))["streams"] if s["codec_type"] == "video")
    h = int(round(width * int(v["height"]) / int(v["width"]) / 2) * 2)
    raw = subprocess.run([FFMPEG, "-v", "error", "-t", str(seconds), "-i", str(path), "-vf", f"fps={SR},scale={width}:{h}:flags=area",
                          "-pix_fmt", "bgr24", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, width, 3)


def _signals(fr):
    """Per analysis frame: flow magnitude (px/frame at a 1920-wide reference), flow direction, sharpness, colourfulness,
    and hard cuts (a colour-histogram jump)."""
    g = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in fr]
    k = 1920 / fr.shape[2] / (30 / SR)  # flow measured between frames SR apart, reported per 30 fps output frame
    mag, ang, hd, act = [0.0], [0.0], [0.0], [0.0]
    hist = lambda f: cv2.normalize(cv2.calcHist([cv2.cvtColor(f, cv2.COLOR_BGR2HSV)], [0, 1], None, [16, 8], [0, 180, 0, 256]), None)
    hs = [hist(f) for f in fr]
    for i in range(1, len(g)):
        fl = cv2.calcOpticalFlowFarneback(g[i - 1], g[i], None, .5, 3, 13, 3, 5, 1.1, 0)
        mx, my = float(np.median(fl[..., 0])), float(np.median(fl[..., 1]))
        mag.append(float(np.mean(np.hypot(fl[..., 0], fl[..., 1]))) * k)
        # local action: the picture change left after following the camera (median flow), at its 99.5th percentile, so a
        # small fast subject (a bird taking off) counts and handheld shake does not
        prev = cv2.warpAffine(g[i - 1], np.float32([[1, 0, mx], [0, 1, my]]), (g[i].shape[1], g[i].shape[0]), borderMode=cv2.BORDER_REPLICATE)
        act.append(float(np.percentile(np.abs(g[i].astype(np.int16) - prev), 99.5)))
        ang.append(float(np.degrees(np.arctan2(my, mx))) if abs(mx) + abs(my) > .05 else 0.0)
        hd.append(cv2.compareHist(hs[i - 1], hs[i], cv2.HISTCMP_BHATTACHARYYA))
    # a hard cut: a large histogram jump, or a moderate one far above the clip's own frame-to-frame change (two shots of
    # one scene share colours: a kingfisher wide then close measured .40 against .05 between its own frames)
    base = float(np.median(hd[1:])) if len(hd) > 1 else 0.0
    cut = [d > .5 or (d > .25 and d > 5 * base) for d in hd]
    sharp = [float(cv2.Laplacian(x, cv2.CV_64F).var()) for x in g]
    colour = []
    for f in fr:
        b, gg, r = [f[..., c].astype(np.float32) for c in range(3)]
        rg, yb = r - gg, .5 * (r + gg) - b
        colour.append(float(np.hypot(rg.std(), yb.std()) + .3 * np.hypot(rg.mean(), yb.mean())))
    lum = [float(x.mean()) for x in g]
    return np.array(mag), np.array(ang), np.array(cut), np.array(sharp), np.array(colour), np.array(lum), np.array(act)


def audio_presence(path):
    """What the clip's own sound offers an edit: none (no stream), silent (a mute track, common on stock and Commons
    footage) or its peak level, so the caller plans ambience before counting on source sound."""
    if not any(s["codec_type"] == "audio" for s in probe(str(path))["streams"]):
        return "none"
    err = subprocess.run([FFMPEG, "-v", "info", "-t", "60", "-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True, errors="replace").stderr
    peak = next((float(x.split("max_volume:")[1].split()[0]) for x in err.splitlines() if "max_volume:" in x), -91.0)
    return "silent" if peak < -60 else f"peak {peak:.0f} dBFS"


def rank(paths, window_s=3.0, top=12, match_cuts=True, subject=None, min_look=None):
    """Windows of window_s across the clips, best first; per clip at most one window per window_s span (no overlaps).
    subject ("rally car", "bird"): open-vocabulary detection at 2 fps; windows without it rank last, and each window
    reports how much of it shows the subject, its largest share of the frame and subject_at (its clearest view).
    min_look "A"/"B": each chosen window's picture is graded (editvideo.look: resolution, detail, noise, handheld
    shake, clipping) and windows below the grade are passed over (motion alone had ranked shaky phone clips first)."""
    if not 1 <= len(paths) <= 40 or not 1 <= window_s <= 15 or not 1 <= top <= 40:
        raise ValueError("1..40 paths, window_s 1..15, top 1..40")
    if min_look and min_look not in ("A", "B"):
        raise ValueError("min_look is A or B")
    rows, frames, sound, skipped = [], {}, {}, []
    for path in paths:
        src = Path(path).resolve(strict=True)
        try:
            fr = _decode(src)
        except (StopIteration, subprocess.CalledProcessError, ValueError):  # no video stream (audio-only) or undecodable
            skipped.append({"path": str(src), "reason": "no decodable video"})
            continue
        if len(fr) < SR:
            skipped.append({"path": str(src), "reason": "shorter than 1 s"})
            continue
        if len(fr) >= 180 * SR:
            skipped.append({"path": str(src), "reason": "analysed the first 180 s only"})
        sound[str(src)] = audio_presence(src)
        keep = {}  # only the frames the sheet and match cuts read (a 40-clip call had held every decoded frame)
        frames[str(src)] = keep
        mag, ang, cut, sharp, colour, lum, diff = _signals(fr)
        n = int(window_s * SR)
        for a in range(0, max(1, len(fr) - n + 1), max(1, n // 2)):
            b = min(len(fr), a + n)
            m = mag[a + 1:b]
            if not len(m):
                continue
            peak = a + 1 + int(np.argmax(np.where(cut[a + 1:b], -1, diff[a + 1:b])))
            for i in (a, b - 1, peak):
                keep[i] = fr[i]
            rows.append({"path": str(src), "_f": (a, b - 1, peak), "start": round(a / SR, 2), "end": round(b / SR, 2), "motion": round(float(np.median(m)), 2),
                         "sharpness": round(float(np.median(sharp[a:b])), 1), "colour": round(float(np.median(colour[a:b])), 1),
                         "action": round(float(np.max(np.where(cut[a + 1:b], 0, diff[a + 1:b]))), 1),
                         "cuts_inside": int(cut[a + 1:b].sum()), "dark": float(np.median(lum[a:b])) < 40,
                         "peak_at": round(peak / SR, 2), "direction_deg": round(float(np.median(ang[a + 1:b])), 0)})
    if not rows:
        raise ValueError("No decodable video in paths: " + "; ".join(f"{Path(x['path']).name}: {x['reason']}" for x in skipped))
    z = lambda key: (lambda v: (v - v.mean()) / (v.std() + 1e-6))(np.array([r[key] for r in rows], np.float64))
    if subject:  # what is in the window, not only how much moves (a spectator's hand had out-scored the car)
        from .semantic import detect
        det = detect(list(frames), [subject], fps=2.0)
        for r in rows:
            seen = det["clips"][r["path"]][subject.strip().lower()].get("track") or []
            inside = [(t, b) for t, b in seen if r["start"] <= t <= r["end"]]
            area = [(b[2] - b[0]) * (b[3] - b[1]) for _, b in inside]
            r["subject"] = {"share": round(len(inside) / max(1, (r["end"] - r["start"]) * 2), 2), "area": round(max(area, default=0), 3),
                            **({"at": inside[int(np.argmax(area))][0]} if inside else {})}
    zm, za, zs, zc = z("motion"), z("action"), z("sharpness"), z("colour")
    for r, a_, x_, b_, c_ in zip(rows, zm, za, zs, zc):  # movement and a moment of action first, then a sharp, colourful picture
        r["score"] = round(float(.35 * a_ + .2 * x_ + .27 * b_ + .18 * c_ - 1.2 * r["cuts_inside"] - .8 * r["dark"]), 3)
    if subject:  # presence times size: a large, steady view of the subject first; none: last
        for r in rows:
            r["_p"] = r["subject"]["share"] * math.sqrt(r["subject"]["area"])
        for r, p_ in zip(rows, z("_p")):
            r["score"] = round(r["score"] + .8 * float(p_) - (2.0 if not r["subject"]["share"] else 0), 3)
            r.pop("_p")
    best, cap = [], max(3, -(-2 * top // max(1, len(frames))))
    rejected, tried, whole = 0, {}, {}
    for r in sorted(rows, key=lambda r: -r["score"]):
        if any(o["path"] == r["path"] and o["start"] < r["end"] and r["start"] < o["end"] for o in best):
            continue
        if sum(o["path"] == r["path"] for o in best) >= cap:  # several clips' windows, not one clip's
            continue
        if min_look:
            from .look import UPSCALE_MAX, measure
            from .media import display_size
            if r["path"] not in whole:  # resolution is the whole file's: one check, not a decode per window
                w0, h0 = display_size(r["path"])
                whole[r["path"]] = max(1920 / max(w0, h0), 1080 / min(w0, h0)) <= UPSCALE_MAX
            if not whole[r["path"]] or tried.get(r["path"], 0) >= cap + 2:  # a clip that keeps failing is not measured on
                rejected += 1
                continue
            tried[r["path"]] = tried.get(r["path"], 0) + 1
            lk = measure(r["path"], r["start"], r["end"])
            r["look"] = {"grade": lk["grade"], **({"flags": lk["flags"]} if lk["flags"] else {})}
            if lk["grade"] > min_look:  # "A" < "B" < "C"
                rejected += 1
                continue
        best.append(r)
        if len(best) >= top:
            break
    pairs = _match(best, frames) if match_cuts and len(best) > 1 else []
    sheet = _sheet(best, frames)
    labels = _labels(list(frames))
    for r in best:
        r["label"] = labels[r["path"]]
        r.pop("_f", None)
    return {"windows": best, "match_cuts": pairs, "sheet": str(sheet), "clips": len(frames), "audio": {labels[k]: v for k, v in sound.items()},
            **({"skipped": skipped} if skipped else {}), **({"look_rejected": rejected} if min_look else {}),
            "method": f"{SR} fps analysis: Farneback flow (motion px/frame at 1920 wide, median direction), Laplacian sharpness, opponent-colour "
                      "colourfulness, histogram cuts; score = .35 motion + .2 action + .27 sharpness + .18 colour (z-scores across all windows) - cuts - darkness. "
                      "peak_at = the strongest local action (picture change after following the camera; a ramp or accent lands there). Not an aesthetic judgement."}


def _mask(f):
    from .footage_pro import spectral_saliency
    s = spectral_saliency(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
    return s >= np.percentile(s, 80)


def _match(best, frames):
    """Out/in pairs whose subject shape (saliency mask overlap) or motion direction continues across the cut."""
    ends = []
    for r in best:
        fr = frames[r["path"]]
        a, b, _ = r["_f"]
        ends.append((_mask(fr[b]), _mask(fr[a])))
    out = []
    for i, ri in enumerate(best):
        for j, rj in enumerate(best):
            if i == j or ri["path"] == rj["path"]:  # two moments of one take read as a jump cut, not a match cut
                continue
            mo, mi = ends[i][0], ends[j][1]
            iou = float((mo & mi).sum() / max(1, (mo | mi).sum()))
            moving = ri["motion"] > 2 and rj["motion"] > 2
            dirs = float(np.cos(np.radians(ri["direction_deg"] - rj["direction_deg"]))) if moving else 0.0
            score = .7 * iou + .3 * max(0.0, dirs)
            out.append({"out": {"path": ri["path"], "at": ri["end"]}, "in": {"path": rj["path"], "at": rj["start"]}, "score": round(score, 3),
                        "shape_overlap": round(iou, 3), "same_direction": round(dirs, 2) if moving else None})
    return sorted(out, key=lambda x: -x["score"])[:6]


def _labels(paths):
    """Short names that tell clips apart: the part of each file name the others do not share (series of files often
    share a long prefix and suffix, e.g. a photographer's credit)."""
    stems = [Path(x).stem for x in paths]
    short = lambda s: s if len(s) <= 28 else s[:14] + "~" + s[-13:]  # head and tail: series differ at either end
    if len(stems) < 2:
        return {x: short(s) for x, s in zip(paths, stems)}
    cp = os.path.commonprefix(stems)
    cs = os.path.commonprefix([s[::-1] for s in stems])[::-1]
    pre = max((cp.rfind(c) + 1 for c in "_- ."), default=0)  # back to the last separator: "00" + "6_Gorilla" keeps "006"
    suf = len(cs) - min((i for i, c in enumerate(cs) if c in "_- ."), default=len(cs))
    out = {}
    for x, s in zip(paths, stems):
        mid = s[pre:len(s) - suf] if len(s) - suf > pre else s
        out[x] = short(mid.strip("_- ") or s)
    for x in paths:  # same name in different folders: prefix the folder
        if sum(v == out[x] for v in out.values()) > 1:
            out[x] = short(Path(x).parent.name + "/" + out[x])
    return out


def _sheet(best, frames):
    labels = _labels(list(frames))
    tiles = []
    for k, r in enumerate(best):
        f = frames[r["path"]][r["_f"][2]]
        im = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)).resize((240, int(240 * f.shape[0] / f.shape[1])))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 240, 16], fill=(0, 0, 0))
        d.text((4, 2), f"{k + 1}. {labels[r['path']]} {r['start']}-{r['end']}s", fill=(255, 220, 0))
        tiles.append(im)
    cols = 4
    h = max(t.height for t in tiles)
    sheet = Image.new("RGB", (cols * 244, ((len(tiles) + cols - 1) // cols) * (h + 4)), (16, 16, 16))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * 244, (k // cols) * (h + 4)))
    import hashlib
    out = store.DATA / "observations" / ("clips-" + hashlib.sha256("|".join(r["path"] + str(r["start"]) for r in best).encode()).hexdigest()[:16] + ".jpg")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=85)
    return out
