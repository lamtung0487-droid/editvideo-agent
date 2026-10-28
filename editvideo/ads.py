"""Short-form and performance-ad grammar: a structure planner, an audit, and emphasis punch-ins from word timings.

Measured (round-4 study, local analysis only; n = 1 commercial for the ad timings, so treat as starting points):
a 28.7 s 1:1 product commercial showed the brand mascot at 0 s, the product at 0.9 s, the hero reveal at 2.4 s, eight
sections averaging 3.6 s, a first offer tag at 31 % and the main offer at 52 % of the runtime, a CTA end card from 88 %
held 3.4 s (12 %), ≤ 3-4 words per line and ≤ 7 on screen, a 0.6 s music dropout before the offer and the bed 15 dB
under the CTA. Retention edits measured 10.8-14.7 visual events/min (cuts + punch-ins + graphic pops), median gap
3.3-4.2 s, the first change by 2.6 s, the opening 30 s at ~2.3x the body rate; emphasis punch-ins were hard cuts to
x1.14 about the eye line (0.51, 0.31), on the first word after a pause ≥ 0.35 s, ~0.5/min, held to the next cut.
"""
import math
import re
import copy
import statistics
from .music import FPS
from .review import is_vietnamese

STRUCTURES = {
    # (section, share of runtime, required elements, purpose)
    "hook_demo_offer_cta": [("hook", .10, ["product or outcome on screen", "first change by 2.6 s"], "stop the scroll: outcome or problem in the first 3 s"),
                            ("problem", .15, ["the viewer's pain in their words"], "name the problem (skip for pure brand)"),
                            ("demo", .30, ["product in use", "benefit lines ≤ 4 words"], "show the outcome, not the features"),
                            ("proof", .15, ["social proof: review, number, face"], "make it believable"),
                            ("offer", .15, ["offer card", "music drop before it"], "what they get and why now"),
                            ("cta", .15, ["CTA card ≥ 2.5 s", "logo", "bed ducked ≥ 10 dB"], "one action")],
    "brand_promo": [("open", .09, ["brand at 0 s", "product by 0.9 s", "hero reveal by 2.4 s"], "brand and product immediately"),
                    ("showcase", .22, ["product swaps on beats"], "variety, one beat per swap"),
                    ("offer_1", .21, ["first offer tag by ~31 %"], "first offer"),
                    ("offer_main", .36, ["main offer by ~52 %", "music drop 0.6 s before it"], "main offer on a beat after a drop"),
                    ("cta_end_card", .12, ["CTA end card ≥ 3 s", "logo", "bed -15 dB"], "end card")],
}
from .platforms import ORGANIC as PROFILES_UI  # one table for every audit (platforms.py); top: tabs / title bar


def plan(duration_s, structure="hook_demo_offer_cta", music_path=None, bpm_range=None):
    if structure not in STRUCTURES:
        raise ValueError(f"structure is one of {sorted(STRUCTURES)}")
    if not 6 <= duration_s <= 180:
        raise ValueError("duration_s 6..180")
    rows, t = [], 0.0
    spec = STRUCTURES[structure]
    cta_share = max(spec[-1][1], 2.5 / duration_s if structure == "hook_demo_offer_cta" else 3.0 / duration_s)
    scale = (1 - cta_share) / sum(s[1] for s in spec[:-1])
    for i, (name, share, req, purpose) in enumerate(spec):
        length = duration_s * (cta_share if i == len(spec) - 1 else share * scale)
        rows.append({"section": name, "start": round(t, 2), "end": round(t + length, 2), "required": req, "purpose": purpose})
        t += length
    rows[-1]["end"] = round(duration_s, 2)
    music = None
    if music_path:
        from . import music as mu
        st = mu.structure(music_path, 0.0, None, bpm_range)
        beats = st["beats"]
        for r in rows[1:]:
            near = min(beats, key=lambda b: abs(b - r["start"])) if beats else None
            if near is not None and abs(near - r["start"]) < 1.0:
                r["music_anchor"] = round(near, 3)
        music = {k: st[k] for k in ("bpm", "pulse")}
        for i in range(1, len(rows)):
            if "music_anchor" in rows[i]:
                rows[i - 1]["end"] = rows[i]["start"] = rows[i]["music_anchor"]
    for r in rows:
        r["start_frame"], r["end_frame"] = round(r["start"] * FPS), round(r["end"] * FPS)
    return {"structure": structure, "sections": rows, "music": music,
            "rules": ["≤ 4 words per line, ≤ 7 on screen; captions 1-3 words per page", "10-15 visual events/min, opening ~2x the body rate; no hold over ~4 s without a change",
                      "product cuts land 2-3 frames before the beat, text pops 1-2 frames after", "drop the music 0.6 s before the offer, duck 15 dB under the CTA",
                      "aspect per placement: 9:16 TikTok/Reels/Shorts, 4:5 or 1:1 feed, 16:9 YouTube"],
            "evidence": "measured on one commercial and two retention edits (n small): starting points, not laws"}


def _visible(layer, a, b):
    return layer["start_frame"] < b and layer["end_frame"] > a


def audit(pid, sections=None, product_layers=None, cta_layer=None, logo_layer=None, offer_layer=None, platform=None):
    from . import agent
    p = agent.read(pid)
    t = p["timeline"]
    total = t["total_frames"]
    L = {l["id"]: l for l in t.get("layers") or []}
    findings = []
    F = lambda level, code, where, ev, sug: findings.append({"level": level, "code": code, "where": where, "evidence": ev, "suggestion": sug})
    if logo_layer:
        lg = L.get(logo_layer)
        if not lg or not _visible(lg, 0, 60):
            F("warning", "brand_late", logo_layer, "logo not visible in the first 2 s", "Show the brand at the open (measured: 0 s).")
        if not lg or not _visible(lg, total - 90, total):
            F("warning", "brand_missing_at_end", logo_layer, "logo not visible in the last 3 s", "Keep the logo on the end card.")
    if product_layers:
        firsts = [L[i]["start_frame"] for i in product_layers if i in L]
        if not firsts or min(firsts) > 90:
            F("warning", "product_late", ",".join(product_layers), f"product first visible at {min(firsts) / FPS if firsts else None} s", "Product on screen by 1-3 s.")
    if cta_layer:
        c = L.get(cta_layer)
        if not c:
            F("warning", "cta_missing", cta_layer, "layer not found", "Add a CTA end card.")
        else:
            hold = c["end_frame"] - c["start_frame"]
            if hold < max(75, .08 * total):
                F("warning", "cta_short", cta_layer, f"CTA held {hold / FPS:.1f} s", "Hold the CTA ≥ 2.5 s (≥ 8 % of runtime; measured 3.4 s / 12 %).")
            if c["end_frame"] < total - 3:
                F("info", "cta_not_last", cta_layer, "CTA ends before the video", "End on the CTA.")
            if offer_layer and offer_layer in L and L[offer_layer]["start_frame"] > c["start_frame"]:
                F("warning", "offer_after_cta", offer_layer, "offer starts after the CTA", "Offer, then CTA.")
    for l in t.get("layers") or []:
        if l["kind"] in ("text", "caption") and l.get("text"):
            txt = l["text"].replace("**", "").replace("==", "")
            lines = [ln.split() for ln in txt.split("\n")]
            # Vietnamese writes one syllable per space-separated token (mặt trăng = one word, two tokens): the same
            # reading load allows ~1.5x the tokens.
            vi = is_vietnamese(txt)
            per_line, total = (6, 10) if vi else (4, 7)
            if max(len(x) for x in lines) > per_line or sum(len(x) for x in lines) > total:
                F("info", "text_dense", l["id"], f"{max(len(x) for x in lines)} {'syllables' if vi else 'words'}/line, {sum(len(x) for x in lines)} on screen",
                  f"≤ {per_line} {'syllables' if vi else 'words'} per line, ≤ {total} on screen.")
    # Visual events: cuts + layer entrances (punch-ins on shots count as events too).
    ev = sorted({s["start_frame"] for s in t["shots"][1:]} | {l["start_frame"] for l in t.get("layers") or [] if l["start_frame"] > 0}
                | {s["start_frame"] for s in t["shots"] if any(e["name"] == "focus_zoom" for e in s.get("effects") or [])})
    rate = len(ev) / max(1e-6, total / FPS) * 60
    first = ev[0] / FPS if ev else None
    gaps = [(b - a) / FPS for a, b in zip([0] + ev, ev + [total])]
    if rate < 8:
        F("info", "slow_pace", "timeline", f"{rate:.1f} visual events/min", "Retention edits measured 10.8-14.7/min.")
    if first is None or first > 3:
        F("warning", "first_change_late", "timeline", f"first visual change at {first} s", "First change by ~2.6 s.")
    if gaps and max(gaps) > 8:
        F("info", "long_hold", "timeline", f"longest hold {max(gaps):.1f} s", "Add a cut, punch-in or graphic within ~4 s.")
    if platform in PROFILES_UI and t["height"] > t["width"]:
        for l in t.get("layers") or []:
            if l["kind"] not in ("text", "caption", "callout", "icon"):
                continue
            box = (l["x"], l["y"], l["x"] + l["width"], l["y"] + l["height"])
            for name, (x0, y0, x1, y1) in PROFILES_UI[platform].items():
                if box[0] < x1 and box[2] > x0 and box[1] < y1 and box[3] > y0 and not (name == "bottom" and l["kind"] == "caption" and box[1] < .8):
                    F("warning", "ui_zone", l["id"], f"overlaps the {platform} {name} UI", "Keep text out of the platform UI zones.")
                    break
    return {"findings": findings[:20], "events_per_min": round(rate, 1), "first_change_s": first, "median_gap_s": round(statistics.median(gaps), 2) if gaps else None,
            "note": "Thresholds measured on few references; deliberate departures are valid."}


ENTRANCES = {"fade_in", "rise", "drop", "slide_left", "slide_right", "pop", "spring", "blur_in", "rotate_in", "flip_x", "flip_y", "zoom_out",
             "wipe_left", "wipe_right", "wipe_up", "wipe_down", "iris", "diagonal_reveal", "diamond_reveal", "soft_edge_reveal", "slide_spring", "clock_wipe"}


def _eased(p, k):
    """Python mirror of engines/effects.js ease() for the curves used on camera moves."""
    p = min(1.0, max(0.0, p))
    return {"linear": p, "ease_in": p * p, "ease_out": 1 - (1 - p) ** 2, "snappy": 1 - (1 - p) ** 4,
            "dramatic": 1.0 if p >= 1 else 1 - 2 ** (-10 * p), "dreamy": .5 - .5 * math.cos(math.pi * p),
            "ease_in_out": 2 * p * p if p < .5 else 1 - (-2 * p + 2) ** 2 / 2}.get(k, p * p * (3 - 2 * p))


ZOOMS = ("focus_zoom", "zoom_in", "zoom_out")
PUSHES = ("focus_zoom", "zoom_in")  # scale runs 1 → 1+amount, so a truncated push is the same push with less amount


def _on_screen_scale(effects, f):
    """Plate scale an effect list shows at local frame f (zooms compose; geometric interpolation as in the runtime)."""
    k = 1.0
    for e in effects or []:
        if e["name"] not in ZOOMS:
            continue
        a = float((e.get("params") or {}).get("amount", .08 if e["name"] == "focus_zoom" else .1))
        if (e.get("params") or {}).get("cut"):
            k *= 1 + a
            continue
        q = _eased((f - e["start_frame"]) / max(1, e["end_frame"] - e["start_frame"]), e.get("easing") or "smooth")
        q = 1 - q if e["name"] == "zoom_out" else q  # zoom_out runs 1+amount → 1
        k *= (1 + a) ** q if 1 + a > 0 else 1 + a * q
    return k


def _truncate(e, d):
    """An effect cut at local frame d. A camera move crossing the cut keeps its speed: its amount becomes the value it
    had reached at d (a push truncated without this ran twice as fast and the punch then landed smaller)."""
    out = {**e, "end_frame": min(e["end_frame"], d)}
    if e["end_frame"] > d and e["name"] in PUSHES and not (e.get("params") or {}).get("cut"):
        P = dict(e.get("params") or {})
        a = float(P.get("amount", .08 if e["name"] == "focus_zoom" else .1))
        q = _eased((d - e["start_frame"]) / max(1, e["end_frame"] - e["start_frame"]), e.get("easing") or "smooth")
        P["amount"] = round((1 + a) ** q - 1 if 1 + a > 0 else a * q, 4)
        out.update(params=P, easing="linear" if (e.get("easing") or "smooth") == "linear" else e.get("easing") or "smooth")
    return out


def _same_picture(asset, t1, t2):
    """Whether a source shows the same picture at two times (a jump cut) rather than another scene: small grey frames,
    normalised correlation. Unknown counts as the same (the conservative choice for a talking head)."""
    import subprocess
    import numpy as np
    from .media import FFMPEG
    if not asset or not asset.get("path"):
        return True
    grab = lambda t: np.frombuffer(subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", asset["path"], "-frames:v", "1", "-vf", "scale=64:36,format=gray",
                                                   "-f", "rawvideo", "-"], capture_output=True).stdout, np.uint8).astype(float)
    a, b = grab(t1), grab(t2)
    if a.size != 64 * 36 or b.size != 64 * 36:
        return True
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9)) > .6


def punch_in(pid, base_revision, words=None, frames=None, scale=1.14, anchor=(.51, .31), min_pause_s=.35, min_gap_s=15.0, ladder=False, dry_run=False):
    """Emphasis punch-ins as hard cuts: at the first word after a pause ≥ min_pause_s (words [{word,start,end}] in
    timeline seconds) or at explicit frames; the shot is split there and the right part holds a ×scale zoom about the
    anchor until its end. ladder=True alternates in/out (×scale then ×1/scale-ish) for jump-cut-heavy talking edits."""
    from . import agent, store
    p = agent.read(pid)
    if p["revision"] != base_revision:
        raise ValueError("Read the current project revision before placing punch-ins")
    if not 1.03 <= scale <= 1.3:
        raise ValueError("scale 1.03..1.3 (measured 1.05-1.18)")
    t = copy.deepcopy(p["timeline"])
    assets = {x["id"]: x for x in store.assets(pid)}
    cand = []
    if frames:
        cand = sorted(int(f) for f in frames)
    elif words:
        ws = sorted(words, key=lambda w: w["start"])
        for a, b in zip(ws, ws[1:]):
            if b["start"] - a["end"] >= min_pause_s:
                cand.append(round(b["start"] * FPS))
    else:
        raise ValueError("Pass words (timeline seconds) or frames")
    placed, skipped, last = [], [], -10 ** 9
    covers = [(l["start_frame"], l["end_frame"]) for l in t.get("layers") or [] if l.get("kind") == "video" and l.get("width", 0) * l.get("height", 0) > .5]
    for f in cand:
        if f - last < min_gap_s * FPS:
            skipped.append({"frame": f, "reason": f"within {min_gap_s} s of the previous punch"})
            continue
        if any(a - 12 < f < b + 12 for a, b in covers):  # under a full-frame B-roll, or a flash shot just beside it
            skipped.append({"frame": f, "reason": "under or beside a full-frame video layer (B-roll)"})
            continue
        idx = next((i for i, s in enumerate(t["shots"]) if s["start_frame"] <= f < s["end_frame"]), None)
        if idx is None:
            skipped.append({"frame": f, "reason": "outside the shots"})
            continue
        sh = t["shots"][idx]
        if f - sh["start_frame"] < 6 or sh["end_frame"] - f < 12:
            skipped.append({"frame": f, "reason": "too close to an existing cut"})
            continue
        if not sh.get("asset_id"):
            skipped.append({"frame": f, "reason": "shot has no footage"})
            continue
        if any(l.get("attach_shot") == sh["id"] and l["start_frame"] < f < l["end_frame"] for l in t.get("layers") or []):
            skipped.append({"frame": f, "reason": "a layer attached to this shot spans the cut"})
            continue
        right = copy.deepcopy(sh)
        right["id"] = f"{sh['id']}-p{len(placed) + 1}"
        right["start_frame"] = f
        right["source_start"] = round(sh.get("source_start", 0) + (f - sh["start_frame"]) * sh.get("playback_rate", 1) / FPS, 4)
        # The punch must change the framing relative to what is already on screen: a held zoom on the left part (an
        # earlier punch or an alternating select) is the baseline. Ladder steps out when the left is already tight,
        # otherwise in, so a cut never lands on the same size (that is a jump cut).
        held = _on_screen_scale(sh.get("effects"), f - sh["start_frame"])  # what is on screen at the cut, moves included
        if ladder and held > 1.04:  # by what is on screen, not by count: two "in" steps would compound (x1.12 x1.12)
            k = 1.0
        else:
            k = min(1.6, held * scale)
        # A punch enlarges the source further: keep the total under ~3x source pixels (soft_upscale's 3.25 limit), so
        # a 720p take covering 9:16 (already 2.7x) gets a smaller punch instead of macroblocks.
        from .review import upscale_factor
        base = upscale_factor({**sh, "effects": []}, assets.get(sh.get("asset_id")), t["width"], t["height"])
        if base and k > 1 and base * k > 3.0:
            k = max(1.0, round(3.0 / base, 3))
            if k < 1.03:
                skipped.append({"frame": f, "reason": f"source already enlarged x{base:.2f}; a punch would turn soft"})
                continue
        d = f - sh["start_frame"]
        # Each half keeps only the effect spans inside it (re-based to its own frame 0); the punch half drops entrances
        # (a hard cut must not fade in again) and any previous focus_zoom.
        right["effects"] = [{**e, "start_frame": max(e["start_frame"], d) - d, "end_frame": e["end_frame"] - d} for e in right.get("effects") or []
                            if e["end_frame"] > d and e["name"] not in ENTRANCES and e["name"] != "focus_zoom"] + (
            [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": round(k - 1, 3), "focus_x": anchor[0], "focus_y": anchor[1], "cut": True}}] if k > 1 else [])
        right.pop("transition", None)
        right["keyframes"] = {}
        right["track_mods"] = {}
        sh["effects"] = [_truncate(e, d) for e in sh.get("effects") or [] if e["start_frame"] < d and min(e["end_frame"], d) > e["start_frame"]]
        sh["keyframes"] = {k: [q for q in v if q["frame"] < d] for k, v in (sh.get("keyframes") or {}).items()}
        sh["keyframes"] = {k: v for k, v in sh["keyframes"].items() if v}
        sh["track_mods"] = {k: v for k, v in (sh.get("track_mods") or {}).items() if k in sh["keyframes"]}
        sh["end_frame"] = f
        t["shots"].insert(idx + 1, right)
        placed.append({"frame": f, "scale": round(k, 3), "shot": right["id"]})
        last = f
    if ladder:  # every cut inside one take must change the framing: equal sizes on both sides read as a jump cut
        from .review import upscale_factor  # (a select boundary) or as no cut at all (a split of continuous source)
        byshot = {x["shot"]: x for x in placed}
        for a_, b_ in zip(t["shots"], t["shots"][1:]):
            if not a_.get("asset_id") or a_.get("asset_id") != b_.get("asset_id"):
                continue
            left = _on_screen_scale(a_.get("effects"), a_["end_frame"] - a_["start_frame"] - 1)
            if abs(left - _on_screen_scale(b_.get("effects"), 0)) >= .02:
                continue
            end_src = a_.get("source_start", 0) + (a_["end_frame"] - a_["start_frame"]) * a_.get("playback_rate", 1) / FPS
            if abs(end_src - b_.get("source_start", 0)) >= 1.5 / FPS and not _same_picture(assets.get(a_["asset_id"]), end_src - 1 / FPS, b_.get("source_start", 0)):
                continue  # two different scenes from one file are a cut, not a jump cut
            k = 1.0 if left > 1.04 else min(1.6, left * scale)
            base = upscale_factor({**b_, "effects": []}, assets.get(b_.get("asset_id")), t["width"], t["height"])
            if base and k > 1 and base * k > 3.0:
                k = max(1.0, round(3.0 / base, 3))
            if abs(k - left) < .03:
                skipped.append({"frame": b_["start_frame"], "reason": "same framing on both sides; no zoom available"})
                continue
            b_["effects"] = [e for e in b_.get("effects") or [] if not (e["name"] == "focus_zoom" and (e.get("params") or {}).get("cut"))] + (
                [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": round(k - 1, 3), "focus_x": anchor[0], "focus_y": anchor[1], "cut": True}}] if k > 1 else [])
            if b_["id"] in byshot:
                byshot[b_["id"]]["scale"] = round(k, 3)
            else:
                placed.append({"frame": b_["start_frame"], "scale": round(k, 3), "shot": b_["id"], "why": "select boundary (jump cut)"})
    placed.sort(key=lambda x: x["frame"])
    if dry_run or not placed:
        return {"dry_run": dry_run, "placed": placed, "skipped": skipped[:20]}
    rev = agent.patch(pid, base_revision, [{"op": "replace_timeline", "timeline": t}])["revision"]
    return {"revision": rev, "placed": placed, "skipped": skipped[:20],
            "note": "Hard cut to the punch, held until the next cut (no punch-out ramp). Check that eyes stay inside the frame at the zoom."}
