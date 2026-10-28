"""Short-form audit of a RENDERED video (TikTok / Reels / Shorts): what the viewer's phone shows and plays, measured on
the encoded file, plus the project's timeline when one is given (text boxes, captions, words, CTA).

Every finding carries its evidence grade and source (platforms.EVIDENCE): a spec or a study where one exists, otherwise
labelled a heuristic. Measurements and thresholds, not a retention forecast or a verdict.
"""
import math
import re
import subprocess
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from . import store, platforms
from .media import FFMPEG, probe

FPS = 30
MAX_SECONDS = 180


def _py(o):
    """numpy scalars/arrays out of a result, so it serialises as JSON."""
    if isinstance(o, dict):
        return {k: _py(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_py(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o


def _f(level, code, evidence, suggestion, where=None, rule=None):
    ev = dict(evidence)
    if rule:
        ev["evidence"] = "%s: %s" % platforms.EVIDENCE[rule]
    return {"level": level, "code": code, "where": where or {}, "evidence": ev, "suggestion": suggestion}


def _decode(path, width=96, seconds=MAX_SECONDS):
    """Small BGR frames at 30 fps (first `seconds`)."""
    info = next(s for s in probe(str(path))["streams"] if s["codec_type"] == "video")
    h = int(round(width * int(info["height"]) / int(info["width"]) / 2) * 2)
    raw = subprocess.run([FFMPEG, "-v", "error", "-t", str(seconds), "-i", str(path), "-vf", f"fps={FPS},scale={width}:{h}:flags=area",
                          "-pix_fmt", "bgr24", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, width, 3)


def cuts_of(frames):
    """Hard cuts: a colour-histogram jump that is also a spike of picture change (a dissolve or a fast pan is not)."""
    hists, diffs, out = [], [0.0], []
    for f in frames:
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        hst = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
        cv2.normalize(hst, hst)
        hists.append(hst)
    diffs += list(np.abs(np.diff(frames.astype(np.int16), axis=0)).mean(axis=(1, 2, 3)))  # colour, not brightness: red→blue is a cut
    d = np.array(diffs)
    for i in range(1, len(frames)):
        local = np.median(d[max(1, i - 6):i + 7]) if len(d) > 2 else 0
        if cv2.compareHist(hists[i - 1], hists[i], cv2.HISTCMP_BHATTACHARYYA) > .45 and d[i] > 12 and d[i] > 3 * local:
            out.append(i)
    return out, d


def visual_cuts(d, cuts):
    """Hard cuts plus framing cuts (a punch-in keeps the colours but every pixel moves): one-frame spikes of change."""
    out = set(cuts)
    for i in range(1, len(d)):
        local = np.median(d[max(1, i - 6):i + 7])
        if d[i] > 6 and d[i] > 4 * local and d[i] >= d[max(1, i - 1)] and d[i] >= d[min(len(d) - 1, i + 1)]:
            out.add(i)
    return sorted(out)


def _scenes(frames, cuts):
    """Distinct scenes: shots whose mean colour histograms differ (a cut back to the same angle is not a new scene)."""
    bounds = [0, *cuts, len(frames)]
    reps = []
    for a, b in zip(bounds, bounds[1:]):
        hsv = cv2.cvtColor(frames[(a + b) // 2], cv2.COLOR_BGR2HSV)
        h = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
        cv2.normalize(h, h)
        if not any(cv2.compareHist(h, r, cv2.HISTCMP_BHATTACHARYYA) < .35 for r in reps):
            reps.append(h)
    return len(reps)


def _wcag(rgb_a, rgb_b):
    def lum(c):
        v = [x / 255 for x in c]
        v = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in v]
        return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]
    a, b = sorted((lum(rgb_a), lum(rgb_b)))
    return (b + .05) / (a + .05)


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) else None


def _text_color(l, design):
    return _hex(l.get("color")) or _hex((design.get("color_roles") or {}).get(l.get("color_role") or "text")) or (255, 255, 255)


ACCENT_EFFECTS = {"white_flash", "flash", "impact_shake", "impact_zoom", "chroma_split", "rgb_split", "shake", "glitch"}  # not focus_zoom: a punch-in is a framing cut
ACCENT_TRANSITIONS = {"flash", "dip_white", "whip_left", "whip_right", "whip_up", "whip_down", "glitch_cut", "zoom_through"}


def _frame_at(path, t, width=540):
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={width}:-2",
                          "-pix_fmt", "rgb24", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=True).stdout
    return Image.open(__import__("io").BytesIO(raw)).convert("RGB")


def _contrast_on_render(path, l, design, W, H):
    """Approximate WCAG contrast of a text layer against what is really behind it in the render: pixels of its box far
    from the text colour (and from its outline/box colour) are the background; p10 of their contrast is reported.
    review_frames measures exact glyphs; this is a screen for the audit."""
    t = (l["start_frame"] + min(l["end_frame"] - 1, l["start_frame"] + 20)) / 2 / FPS
    img = np.asarray(_frame_at(path, t), np.float32)
    h, w = img.shape[:2]
    x0, y0 = int(max(0, l["x"]) * w), int(max(0, l["y"]) * h)
    x1, y1 = int(min(1, l["x"] + l["width"]) * w), int(min(1, l["y"] + l["height"]) * h)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    px = img[y0:y1, x0:x1].reshape(-1, 3)
    tc = np.array(_text_color(l, design), np.float32)
    fp = l.get("font_size") or 60
    behind = [c for c in (_hex(l.get("background")), *(_hex((e.get("params") or {}).get("color")) for e in l.get("effects") or []
                                                        if e.get("name") in ("text_outline", "shadow")
                                                        and float((e.get("params") or {}).get("amount", 2)) >= max(2.0, .02 * fp))) if c]
    ink = [c for c in behind if _wcag(tuple(tc), c) < 1.5]  # an outline in the text's own tone only thickens the glyph
    behind = [c for c in behind if c not in ink]
    if behind:  # a box or outline sits between the glyphs and the picture: that is the contrast that counts
        return round(min(_wcag(tuple(tc), c) for c in behind), 2)
    far = np.linalg.norm(px - tc, axis=1) > 60
    for c in ink:
        far &= np.linalg.norm(px - np.array(c, np.float32), axis=1) > 60
    bg = px[far]
    if len(bg) < 20:
        return None
    lum = bg @ np.array([.2126, .7152, .0722], np.float32)
    ref = bg[np.argsort(lum)[int(len(bg) * (.9 if tc.mean() > 128 else .1))]]  # the background pixels most like the text
    return round(_wcag(tuple(tc), tuple(ref)), 2)


def ink_box(img, l, design, H=1920):
    """Where a text layer's glyphs really are on a rendered RGB frame (pixels of its colour inside its column, from its
    top down through contiguous lines: wrapped text overflows its box). Normalised (x0, y0, x1, y1) or None."""
    h, w = img.shape[:2]
    x0, x1 = int(max(0, l["x"]) * w), int(min(1, l["x"] + l["width"]) * w)
    y0, y1 = int(max(0, l["y"]) * h), int(min(1, l["y"] + max(3 * l["height"], .25)) * h)  # room for wrapped lines
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    reg = img[y0:y1, x0:x1].astype(np.int16)
    mask = np.abs(reg - np.array(_text_color(l, design), np.int16)).max(axis=2) < 40
    rows = np.nonzero(mask.sum(axis=1) > 2)[0]
    if len(rows) < 3:
        return None
    gap = max(4, int((l.get("line_height") or 1.4) * (l.get("font_size") or 60) * h / H))  # a blank line pitch ends the block
    end = rows[0]
    for r in rows[1:]:
        if r - end > gap:
            break
        end = r
    cols = np.nonzero(mask[rows[0]:end + 1].sum(axis=0) > 0)[0]
    return ((x0 + cols.min()) / w, (y0 + rows[0]) / h, (x0 + cols.max() + 1) / w, (y0 + end + 1) / h)


def _faces_at(path, t):
    from .footage_pro import detect_faces
    for dt in (0, -.3, .3):
        g = np.asarray(_frame_at(path, max(0.0, t + dt), 640).convert("L"))
        found = detect_faces(g)
        if found:
            return found
    return []


def _plate_faces(t, assets, frame):
    """Faces of the clean source frame under the canvas at `frame` (no overlays hide them), mapped to canvas shares
    through the shot's fit, focus and held zoom. None when the picture is not footage (fall back to the render)."""
    from .footage_pro import detect_faces
    from .ads import _on_screen_scale
    W, H = t["width"], t["height"]
    for l in t.get("layers") or []:  # a full-frame video layer (B-roll) hides the shot's speaker
        if l["kind"] == "video" and l["start_frame"] <= frame < l["end_frame"] and l["width"] * l["height"] > .5:
            return []
    sh = next((x for x in t["shots"] if x["start_frame"] <= frame < x["end_frame"]), None)
    a = assets.get(sh.get("asset_id")) if sh else None
    if not a or a.get("kind") != "video" or not a.get("width"):
        return None
    st = sh.get("source_start", 0) + (0 if sh.get("freeze") else (frame - sh["start_frame"]) * sh.get("playback_rate", 1) / FPS)
    st = min(st, max(0.0, (a.get("duration") or 1e9) - .1))  # a freeze can hold a clip's last frame
    try:
        faces = detect_faces(np.asarray(_frame_at(a["path"], st, 640).convert("L")))
    except Exception:  # nothing decodable there: no plate to read, fall back to the render
        return None
    sw, shh = a["width"], a["height"]
    k = max(W / sw, H / shh) if sh.get("fit") == "cover" else min(W / sw, H / shh)
    ox, oy = (W - sw * k) * sh.get("focus_x", .5), (H - shh * k) * sh.get("focus_y", .5)
    z = _on_screen_scale(sh.get("effects"), frame - sh["start_frame"])
    zp = next(((e.get("params") or {}).get("focus_x", .5), (e.get("params") or {}).get("focus_y", .5)) for e in (sh.get("effects") or [])
              if e["name"] == "focus_zoom") if any(e["name"] == "focus_zoom" for e in sh.get("effects") or []) else (.5, .5)
    cx, cy = zp[0] * W, zp[1] * H
    out = []
    for fx, fy, fw, fh in faces:
        x0, y0 = ox + fx * sw * k, oy + fy * shh * k
        x1, y1 = x0 + fw * sw * k, y0 + fh * shh * k
        x0, x1 = cx + (x0 - cx) * z, cx + (x1 - cx) * z
        y0, y1 = cy + (y0 - cy) * z, cy + (y1 - cy) * z
        out.append((x0 / W, y0 / H, (x1 - x0) / W, (y1 - y0) / H))
    return out


def _speech_and_captions(pid, t):
    """(speech intervals from the narration's word timings, caption intervals on screen) in seconds."""
    words = (store.read_json(store.folder(pid) / "plan/words.json") or {}).get("words", []) if (store.folder(pid) / "plan/words.json").is_file() else []
    speech = [(w["start"], w["end"]) for w in words if isinstance(w, dict) and "start" in w]
    shown = []
    for l in t.get("layers", []):
        if l["kind"] == "caption":
            for pg in (l.get("data") or {}).get("pages") or []:
                shown.append(((l["start_frame"] + pg["start_frame"]) / FPS, (l["start_frame"] + pg["end_frame"]) / FPS))
    if (t.get("captions_visible", True) and t.get("cues")) and not shown:
        shown = [(c["start"], c["end"]) for c in t["cues"]]
    return speech, shown, words


def _union(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _overlap(intervals, others):
    """Seconds of `intervals` covered by any of `others` (both merged first: two caption lines are one coverage)."""
    tot = 0.0
    for a, b in _union(intervals):
        for c, d in _union(others):
            tot += max(0.0, min(b, d) - max(a, c))
    return tot


def audit(path=None, project_id=None, platform="tiktok", goal="organic", key_layer=None, cta_layer=None):
    """Audit a rendered short. path: an MP4 (any video); project_id adds timeline checks and, without path, uses the
    project's latest final render. Returns findings, measurements, cover candidates and a UI-overlay contact sheet."""
    if platform not in platforms.PLATFORMS:
        raise ValueError("platform is tiktok, reels or shorts")
    t, design = None, {}
    if project_id:
        from . import agent
        t = agent.read(project_id)["timeline"]
        design = t.get("design") or {}
        if not path:
            done = [j for j in store.jobs(project_id) if j["kind"] == "final" and j["state"] == "completed"]  # newest first
            mp4 = store.folder(project_id) / "jobs" / done[0]["id"] / "final.mp4" if done else None
            if not mp4 or not mp4.is_file():
                raise ValueError("No completed final render for this project: pass path")
            path = mp4
    if not path:
        raise ValueError("path or project_id required")
    path = Path(path).resolve(strict=True)
    meta = probe(str(path))
    v = next(s for s in meta["streams"] if s["codec_type"] == "video")
    a = next((s for s in meta["streams"] if s["codec_type"] == "audio"), None)
    dur = float(meta["format"].get("duration") or v.get("duration") or 0)
    vw, vh = int(v["width"]), int(v["height"])
    F, m = [], {"duration_s": round(dur, 2), "size": [vw, vh]}

    # --- delivery: native vertical, resolution, codec, length -------------------------------------------------------
    rate = v.get("avg_frame_rate", "0/1").split("/")
    fps = float(rate[0]) / max(1.0, float(rate[1] or 1))
    m["video"] = {"codec": v.get("codec_name"), "profile": v.get("profile"), "pix_fmt": v.get("pix_fmt"), "fps": round(fps, 3),
                  "color": v.get("color_primaries"), "kbps": round(int(meta["format"].get("bit_rate") or 0) / 1000)}
    if abs(vw / vh - 9 / 16) > .01 or vw < 720:
        F.append(_f("likely_problem", "not_native_vertical", {"size": [vw, vh]}, "Deliver 9:16 at 1080x1920 (at least 720 wide), "
                    "picture filling the frame.", rule="native"))
    lim = platforms.DELIVERY[platform]["max_seconds"]
    if dur > lim:
        F.append(_f("likely_problem", "too_long", {"seconds": round(dur, 1), "limit_s": lim}, f"{platform} accepts up to {lim} s."))
    if goal == "ad" and not 21 <= dur <= 34:
        F.append(_f("info", "ad_length", {"seconds": round(dur, 1), "band_s": [21, 34]}, "TikTok's model of ads found 21-34 s converted best "
                    "(correlational, ads only); length should follow the story.", rule="length"))
    spec = []
    if v.get("codec_name") != "h264":
        spec.append("video codec h264")
    if v.get("pix_fmt") not in ("yuv420p", "yuvj420p"):
        spec.append("yuv420p")
    if v.get("color_primaries") not in (None, "bt709", "unknown"):
        spec.append("BT.709")
    if a is None:
        F.append(_f("check", "silent_video", {}, "No audio track. TikTok reports sound-off ads ~15% more likely to be skipped; add "
                    "voice, music or sound design (or confirm silence is intended).", rule="loudness"))
    elif a.get("codec_name") != "aac" or int(a.get("sample_rate", 0)) < 44100:
        spec.append("AAC 44.1/48 kHz")
    if spec:
        F.append(_f("check", "delivery_spec", {"missing": spec, "video": m["video"]}, "Re-encode for upload (render with delivery preset).", rule="native"))

    # --- picture: first frame, first change, cuts, stills, scenes, letterbox, loop -------------------------------------
    fr = _decode(path)
    n = len(fr)
    if n < 15:
        raise ValueError("Too few frames decoded")
    g = fr.mean(axis=3).astype(np.float32)
    lum0 = float(g[0].mean())
    m["first_frame_luma"] = round(lum0, 1)
    if lum0 < 12 and float(g[0].std()) < 6:  # black, not a dark night shot (which still has structure)
        F.append(_f("likely_problem", "black_first_frame", {"luma": round(lum0, 1)}, "The first frame is black: the feed shows it as the "
                    "thumbnail and the first impression. Open on the picture itself.", where={"frames": [0, 1]}, rule="first_frame"))
    elif n > 12 and lum0 < .5 * float(g[12].mean()):
        F.append(_f("check", "fade_in_open", {"luma_0": round(lum0, 1), "luma_0_4s": round(float(g[12].mean()), 1)},
                    "The video fades in from dark; on a feed the first frame should already show the subject.", where={"frames": [0, 12]}, rule="first_frame"))
    cuts, d = cuts_of(fr)
    cutset = set(cuts)  # a cut, real motion (frame-to-frame change above encoder noise) or a new picture
    change = next((i for i in range(1, n) if i in cutset or d[i] > .6 or np.abs(g[i] - g[0]).mean() > 6), None)
    m["first_change_s"] = round(change / FPS, 2) if change else None
    if change is None or change > FPS:
        F.append(_f("check", "late_first_change", {"first_change_s": m["first_change_s"], "threshold_s": 1.0},
                    "Nothing changes on screen in the first second. Make the first cut, move or entering word happen by 1 s.",
                    where={"frames": [0, FPS]}, rule="first_change"))
    vis = visual_cuts(d, cuts)
    if t:  # with the timeline: an authored accent (a 2-frame white flash, a shake, a whip) changes the picture but is no cut
        starts = {sh["start_frame"] for sh in t["shots"]} | {l[k] for l in t.get("layers") or [] if l.get("kind") == "video" for k in ("start_frame", "end_frame")}
        acc = set()
        for it in [*t["shots"], *(t.get("layers") or [])]:
            for e in it.get("effects") or []:
                if e["name"] in ACCENT_EFFECTS:
                    acc.update(range(it["start_frame"] + e.get("start_frame", 0), it["start_frame"] + (e.get("end_frame") or 0) + 2))
        for sh in t["shots"]:
            tr = sh.get("transition") or {}
            if tr.get("name") in ACCENT_TRANSITIONS:
                acc.update(range(sh["start_frame"] - 1, sh["start_frame"] + tr.get("duration_frames", 0) + 2))
        span = {sh["start_frame"]: (sh.get("transition") or {}).get("duration_frames", 0) for sh in t["shots"]
                if (sh.get("transition") or {}).get("name") in ACCENT_TRANSITIONS}
        cut_of = {min((c for c in vis if s_ - 1 <= c <= s_ + max(1, span.get(s_, 0) + 1)), key=lambda c: abs(c - s_), default=None)
                  for s_ in starts}  # one detected change per authored cut, also when a whip moves it into the transition
        kept = [c for c in vis if c not in acc or c in cut_of]
        if len(kept) != len(vis):
            m["accent_changes_excluded"] = len(vis) - len(kept)
        vis = kept
    body = [c for c in vis if c >= 3 * FPS]
    body_s = max(1e-6, n / FPS - 3)
    m["scene_cuts"], m["visual_cuts"] = len(cuts), len(vis)
    m["cuts_per_s_after_3s"] = round(len(body) / body_s, 3)  # visual cuts: scene changes and punch-ins
    flashes = [(a_, b_) for a_, b_ in zip(vis, vis[1:]) if b_ - a_ < 9]
    if flashes:
        F.append(_f("check", "flash_cut", {"spans_frames": flashes[:6], "threshold_frames": 9},
                    "A picture shown for under 0.3 s between two cuts reads as a glitch: move a cut or merge the shots.",
                    where={"frames": list(flashes[0])}, rule="cut_rate"))
    if len(body) / body_s > .6:
        F.append(_f("check", "fast_pace", {"cuts_per_s": m["cuts_per_s_after_3s"], "band": [.19, .52]},
                    "Faster than top short-form talking heads; faster pacing lowered completion in an experiment. Cut on meaning.", rule="cut_rate"))
    still = np.abs(np.diff(g, axis=0)).mean(axis=(1, 2)) < .35
    run, best, best_at = 0, 0, 0
    for i, s_ in enumerate(still):
        run = run + 1 if s_ else 0
        if run > best:
            best, best_at = run, i + 1 - run
    m["longest_still_s"] = round(best / FPS, 2)
    if best / FPS > 5.3:
        F.append(_f("check", "long_still", {"seconds": m["longest_still_s"], "threshold_s": 5.3},
                    "The picture does not change for over 5 s; a reading hold is fine, otherwise move, cut or reveal.",
                    where={"frames": [best_at, best_at + best]}, rule="longest_still"))
    m["distinct_scenes"] = _scenes(fr, cuts)
    if goal == "ad" and m["distinct_scenes"] < 5 and dur > 15:
        F.append(_f("info", "few_scenes", {"distinct_scenes": m["distinct_scenes"]}, "TikTok's gaming-ads data favoured >= 5 distinct scenes "
                    "(correlational).", rule="scenes"))
    from .review import _letterbox
    bars = _letterbox(path, [{"id": "all", "start_frame": 0, "end_frame": n}])
    if bars:
        F.append(_f("likely_problem", "letterboxed", bars[0], "Black bars waste a phone screen: fill 9:16 (reframe or cover).", rule="native"))
    loop = float(np.abs(g[-1] - g[0]).mean())
    m["loop_seam_diff"] = round(loop, 1)
    if loop < 8:
        F.append(_f("info", "seamless_loop", {"last_vs_first_diff": round(loop, 1)}, "The last frame matches the first: the video loops "
                    "seamlessly (no evidence it lifts watch time; noted).", rule="loop"))

    # --- sound: loudness, peaks ---------------------------------------------------------------------------------------
    if a is not None:
        from .audiofx import _loudness
        ld = _loudness(path)
        m["loudness"] = {k: ld[k] for k in ("integrated_lufs", "range_lu", "true_peak_dbfs")}
        il, tp = ld["integrated_lufs"], ld["true_peak_dbfs"]
        if il is None or il < -50:
            F.append(_f("check", "silent_video", {"integrated_lufs": il}, "The audio track is silent. TikTok reports sound-off ads ~15% more "
                        "likely to be skipped; add voice, music or sound design (or confirm silence is intended).", rule="loudness"))
        elif abs(il - platforms.ENCODE["loudness_lufs"]) > 1.5:
            F.append(_f("check", "loudness", {"integrated_lufs": il, "target": platforms.ENCODE["loudness_lufs"]},
                        "Mobile feeds play loud; deliver about -14 LUFS (render with the delivery preset).", rule="loudness"))
        if tp is not None and tp > -1.0:
            F.append(_f("likely_problem", "true_peak", {"true_peak_dbfs": tp}, "Peaks above -1 dBTP distort after the platform's re-encode.", rule="true_peak"))

    # --- timeline: UI zones, first text, key message, captions, CTA ----------------------------------------------------
    if t:
        W, H = t["width"], t["height"]
        texts = sorted([l for l in t["layers"] if l["kind"] in ("text", "caption", "counter") and l.get("opacity", 1) > .05
                        and (l.get("text") or l["kind"] == "caption") and l.get("typography_role") != "source"], key=lambda l: l["start_frame"])
        first = texts[0]["start_frame"] / FPS if texts else None
        m["first_text_s"] = first
        if first is None or first > 2:
            F.append(_f("check", "late_first_text", {"first_text_s": first, "threshold_s": 2.0},
                        "Put the promise on screen within 2 s (many viewers watch muted).", rule="first_text"))
        key = next((l for l in texts if l["id"] == key_layer), None) if key_layer else (texts[0] if texts else None)
        if key and key["start_frame"] / FPS > 3:
            F.append(_f("check", "late_key_message", {"layer": key["id"], "starts_s": round(key["start_frame"] / FPS, 2), "threshold_s": 3.0},
                        "State the key message by 3 s.", rule="key_message"))
        strict = platforms.safe_area("all", "ads")
        for l in texts:
            box = (l["x"], l["y"], l["x"] + l["width"], l["y"] + l["height"])
            if l["kind"] == "text":  # where the glyphs really are (wide boxes around centred words are not covered)
                tt = (l["start_frame"] + min(l["end_frame"] - 1, l["start_frame"] + 20)) / 2 / FPS
                box = ink_box(np.asarray(_frame_at(path, tt, 540)), l, design, H) or box
            hit = {z: v for z, v in platforms.covered(box, platform).items() if v > .05}
            if hit:
                F.append(_f("check", "covered_by_ui", {"layer": l["id"], "box": [round(x, 3) for x in box], "zones": hit},
                            "The feed's action rail or caption block covers this text; move it inside platforms.safe_area.",
                            where={"layer": l["id"]}, rule="safe_area"))
            elif goal == "ad" and (box[0] < strict[0] - .01 or box[1] < strict[1] - .01 or box[2] > strict[2] + .01 or box[3] > strict[3] + .01):
                F.append(_f("info", "outside_ad_safe_area", {"layer": l["id"], "box": [round(x, 3) for x in box], "ad_safe": strict},
                            "Ads add a CTA button and longer caption: keep key text within the published ad safe area.", rule="safe_area"))
        for l in texts:  # caption geometry: lines and characters
            if l["kind"] != "text" or not l.get("text"):
                continue
            lines = [s_ for s_ in l["text"].split("\n") if s_.strip()]
            if len(lines) > 2 or max(len(s_) for s_ in lines) > 42:
                F.append(_f("info", "long_text_lines", {"layer": l["id"], "lines": len(lines), "longest_chars": max(len(s_) for s_ in lines)},
                            "On a phone, keep a text block to <= 2 lines of <= 42 characters.", rule="caption_lines"))
        contrasts = []
        for l in texts[:12]:
            c = _contrast_on_render(path, l, design, W, H) if l["kind"] == "text" else None
            if c is None:
                continue
            large = l.get("font_size", (design.get("typography") or {}).get(l.get("typography_role") or "", {}).get("size", 60)) >= 66
            contrasts.append(c)
            if c < (3 if large else 4.5):
                F.append(_f("check", "low_contrast", {"layer": l["id"], "contrast": c, "needed": 3 if large else 4.5},
                            "Text against what is really behind it is below WCAG contrast: add an outline, a box or a scrim "
                            "(review_frames measures the exact glyphs).", where={"layer": l["id"]}, rule="contrast"))
        m["text_contrast_min"] = min(contrasts) if contrasts else None
        over = []  # text on the speaker's eyes/mouth: measured glyphs against faces found on the render
        for l in texts[:12]:
            if l["kind"] != "text":
                continue
            tt = (l["start_frame"] + min(l["end_frame"] - 1, l["start_frame"] + 20)) / 2 / FPS
            ib = ink_box(np.asarray(_frame_at(path, tt, 540)), l, design, H)
            if not ib:
                continue
            plate = _plate_faces(t, {x["id"]: x for x in store.assets(project_id)}, int(tt * FPS))
            for fx, fy, fw, fh in (plate if plate is not None else _faces_at(path, tt))[:2]:
                ex0, ey0, ex1, ey1 = fx + .1 * fw, fy + .25 * fh, fx + .9 * fw, fy + .75 * fh  # eyes to mouth
                ov = max(0.0, min(ib[2], ex1) - max(ib[0], ex0)) * max(0.0, min(ib[3], ey1) - max(ib[1], ey0)) / max(1e-6, (ex1 - ex0) * (ey1 - ey0))
                if ov > .12:
                    over.append(l["id"])
                    F.append(_f("check", "text_over_face", {"layer": l["id"], "covers_face": round(ov, 2), "text_box": [round(v, 3) for v in ib],
                                                            "face_box": [round(v, 3) for v in (fx, fy, fx + fw, fy + fh)]},
                                "The text sits on the speaker's eyes or mouth: move it above the head, onto the chest, or shrink it "
                                "(the measured glyph box includes wrapped lines).", where={"layer": l["id"]}, rule="face_clear"))
                    break
        m["text_over_face"] = over
        speech, shown, words = _speech_and_captions(project_id, t)
        if speech:
            sp = sum(b - a for a, b in speech)
            cov = _overlap(speech, shown) / max(1e-6, sp)
            m["caption_coverage"] = round(cov, 3)
            if cov < .95:
                F.append(_f("check", "captions_missing", {"speech_covered": round(cov, 3), "target": .95},
                            "Caption all speech: many viewers watch muted (word_captions).", rule="caption_coverage"))
            offs = []
            for l in t["layers"]:
                if l["kind"] != "caption":
                    continue
                for pg in (l.get("data") or {}).get("pages") or []:
                    for wd in pg.get("words") or []:
                        on = (l["start_frame"] + wd["start_frame"]) / FPS
                        near = min(words, key=lambda w: abs(w["start"] - on)) if words else None
                        if near and abs(near["start"] - on) < .5:
                            offs.append(on - near["start"])
            if offs:
                late = float(np.percentile(offs, 95))
                m["caption_vs_words_offset_ms_p95"] = round(late * 1000)  # against the measured word times, not the audio itself
                if late > .06 + 1 / FPS:  # frame quantisation allowed on top of the sync tolerance
                    F.append(_f("check", "captions_late", {"p95_late_ms": round(late * 1000)}, "Highlighted words appear after they are "
                                "spoken; shift word timings earlier.", rule="av_sync"))
        elif not a and texts:
            for l in texts:
                words_n = len((l.get("text") or "").split())
                secs = (l["end_frame"] - l["start_frame"]) / FPS
                if words_n >= 4 and secs < .33 * words_n:
                    F.append(_f("check", "text_too_fast", {"layer": l["id"], "words": words_n, "seconds": round(secs, 2)},
                                "With no voice the text must be read: about 0.33 s per word.", rule="reading_time"))
        if goal == "ad":
            end = t["total_frames"]
            cta = next((l for l in texts if l["id"] == cta_layer), None) if cta_layer else next(
                (l for l in reversed(texts) if l["end_frame"] >= end - 3 * FPS), None)
            if not cta or (min(cta["end_frame"], end) - max(cta["start_frame"], end - 3 * FPS)) / FPS < 1.5:
                F.append(_f("check", "no_end_cta", {"cta_layer": cta["id"] if cta else None}, "End on a text call to action held >= 1.5 s.", rule="cta"))

    # --- cover candidates and the UI overlay sheet ---------------------------------------------------------------------
    sharp = [float(cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()) for f in fr[::15]]
    picks = sorted(range(len(sharp)), key=lambda i: -sharp[i])[:3]
    import hashlib
    out = store.DATA / "observations" / ("shortform-" + hashlib.sha256(f"{path}|{path.stat().st_mtime_ns}".encode()).hexdigest()[:16])
    out.mkdir(parents=True, exist_ok=True)
    covers = []
    for i in sorted(picks):
        tt = i * 15 / FPS
        p = out / f"cover-{int(tt * 1000):07d}.png"
        _frame_at(path, tt, 1080).save(p)
        covers.append({"t": round(tt, 2), "path": str(p)})
    sheet_t = [min(x_, max(0.0, dur - .1)) for x_ in (0, 1.0, 3.0, dur / 2, dur - .2)]
    tiles = [platforms.draw_ui(_frame_at(path, tt, 270), platform) for tt in sheet_t]
    sheet = Image.new("RGB", (sum(x.width for x in tiles) + 6 * (len(tiles) - 1), max(x.height for x in tiles)), (20, 20, 20))
    x = 0
    for tile in tiles:
        sheet.paste(tile, (x, 0))
        x += tile.width + 6
    sp = out / f"ui-{platform}.jpg"
    sheet.save(sp, quality=85)
    order = {"likely_problem": 0, "check": 1, "info": 2}
    F.sort(key=lambda f_: order[f_["level"]])
    return _py({"path": str(path), "platform": platform, "goal": goal, "measurements": m, "findings": F, "cover_candidates": covers,
            "ui_sheet": str(sp), "ui_sheet_times_s": [round(x_, 2) for x_ in sheet_t],
            "note": "Measured on the encoded file (and the timeline when given). Evidence grades: S spec, PR peer-reviewed, P platform "
                    "research (correlational), A academic preprint, H heuristic. No retention forecast."})
