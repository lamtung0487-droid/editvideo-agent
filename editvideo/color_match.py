"""Shot balancing, shot matching and timeline colour consistency — measured, returned as a `grade` for process_color.

A colourist balances every shot (neutral midtones, sensible black and white points) and then matches shots of a scene
to a hero shot. Here both are solved from frame statistics on the active picture (letterbox bars excluded):
per-channel gain/offset from channel percentiles, a 5-point luma curve for the remaining tone difference, saturation
from the chroma ratio, and an optional skin secondary when both shots show skin on different hues. The solved grade is
applied to the same frames to report residuals, so the AI sees how well it matched without looking at images.
"""
import math
import numpy as np
from . import store
from .color_grade import Grade, apply, SKIN, key, _ycc, SKIN_DEG
from .scopes import _frame, active_area

Q = (1, 10, 25, 50, 75, 90, 99)


def stats(rgb):
    """Compact colour statistics of a frame (H, W, 3) or pooled pixels (N, 3) in 0..1 display RGB."""
    px = (active_area(rgb)[0] if rgb.ndim == 3 else rgb).reshape(-1, 3)
    if len(px) > 60000:
        px = px[:: len(px) // 60000 + 1]
    y, cb, cr = _ycc(px)
    mids = (y > .25) & (y < .75)
    out = {"ch": np.percentile(px, Q, axis=0), "y": np.percentile(y, Q), "black": float(np.percentile(y, .5)), "white": float(np.percentile(y, 99)),
           "mid": float(np.percentile(y, 50)), "chroma": float(np.hypot(cb, cr).mean()),
           "cast": (float(cb[mids].mean()) if mids.any() else 0.0, float(cr[mids].mean()) if mids.any() else 0.0)}
    k = key(SKIN, np.clip(px, 0, 1))
    sk = k > .5
    out["skin_cover"] = float(sk.mean())
    if sk.sum() > 50:
        h = np.degrees(np.arctan2(cr[sk], cb[sk])) % 360
        out["skin_hue"] = float(np.median(h))
        out["skin_chroma"] = float(np.hypot(cb[sk], cr[sk]).mean())
    return out


def _pooled(frames):
    return np.concatenate([active_area(f)[0].reshape(-1, 3) for f in frames])


def _frames(src, times, width=480):
    return [_frame(src, t, width) for t in times]


def report(st):
    r = {"black_pct": round(st["black"] * 100, 1), "mid_pct": round(st["mid"] * 100, 1), "white_pct": round(st["white"] * 100, 1),
         "chroma_pct": round(st["chroma"] * 100, 2), "cast_pct": round(math.hypot(*st["cast"]) * 100, 2)}
    if "skin_hue" in st:
        r["skin_hue_deg"] = round(st["skin_hue"], 1)
    return r


def _fit_channels(s, t):
    """Per-channel gain/offset mapping source channel percentiles onto target percentiles (least squares)."""
    gain, off = [], []
    for c in range(3):
        A = np.stack([s["ch"][:, c], np.ones(len(Q))], 1)
        g, o = np.linalg.lstsq(A, t["ch"][:, c], rcond=None)[0]
        gain.append(float(np.clip(g, .5, 2)))
        off.append(float(np.clip(o, -.2, .2)))
    return gain, off


def solve(src_frames, ref_frames=None, strength=1.0, targets=None):
    """Return (grade dict, before stats, after stats, target stats). Without reference: balance (neutral mids, black
    ~2 %, white ~90 % unless the shot already sits inside 1-4 % / 85-93 %)."""
    S = stats(_pooled(src_frames))
    if ref_frames:
        T = stats(_pooled(ref_frames))
    else:
        tg = {"black": .02, "white": .90, **(targets or {})}
        T = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in S.items()}
        b = S["black"] if .01 <= S["black"] <= .04 else tg["black"]
        w = S["white"] if .85 <= S["white"] <= .93 else tg["white"]
        # Neutral target: each channel's percentiles move to the luma percentiles, then levels map black/white.
        lev = lambda x: b + (x - S["black"]) * (w - b) / max(1e-3, S["white"] - S["black"])
        T["ch"] = np.stack([lev(S["y"])] * 3, 1)
        T["chroma"] = S["chroma"]
    gain, off = _fit_channels(S, T)
    g = Grade(gain=gain, offset=off)
    mid = apply(g, _pooled(src_frames))
    M = stats(mid)
    ys, yt = M["y"][[0, 1, 3, 5, 6]], T["y"][[0, 1, 3, 5, 6]] if ref_frames else None
    curve = None
    if ref_frames is not None:
        pts = sorted({(round(float(a), 4), round(float(c), 4)) for a, c in zip(np.clip(ys, 0, 1), np.clip(yt, 0, 1))})
        pts = [list(p) for i, p in enumerate(pts) if i == 0 or p[0] > pts[i - 1][0] + .01]
        for i in range(1, len(pts)):
            pts[i][1] = max(pts[i][1], pts[i - 1][1])
        if len(pts) >= 2 and max(abs(a - c) for a, c in pts) > .01:
            curve = pts
    sat = float(np.clip(T["chroma"] / max(1e-4, M["chroma"]), .5, 1.6)) if ref_frames is not None else 1.0
    grade = {"gain": [round(v, 4) for v in gain], "offset": [round(v, 4) for v in off], "saturation": round(sat, 3)}
    if curve:
        grade["curve"] = curve
    if ref_frames is not None and "skin_hue" in S and "skin_hue" in T:
        g2 = Grade(**grade)
        after = stats(apply(g2, _pooled(src_frames)))
        if "skin_hue" in after and abs(after["skin_hue"] - T["skin_hue"]) > 4:
            grade["secondaries"] = [{"hue_deg": round(after["skin_hue"] % 360, 1), "width_deg": 30, "soft_deg": 20, "sat": [3, 35], "luma": [.12, .9],
                                     "hue_shift_deg": round(float(np.clip(T["skin_hue"] - after["skin_hue"], -30, 30)), 1)}]
    if strength < 1:
        grade = _blend(grade, strength)
    A = stats(apply(Grade(**grade), _pooled(src_frames)))
    return grade, S, A, T


def _blend(grade, s):
    out = dict(grade)
    out["gain"] = [1 + (v - 1) * s for v in grade["gain"]]
    out["offset"] = [v * s for v in grade["offset"]]
    out["saturation"] = 1 + (grade["saturation"] - 1) * s
    if "curve" in grade:
        out["curve"] = [[a, a + (c - a) * s] for a, c in grade["curve"]]
    for sec in out.get("secondaries", []):
        sec["mix"] = s
    return out


def residuals(A, T):
    r = {"d_black": round((A["black"] - T["black"]) * 100, 2), "d_mid": round((A["mid"] - T["mid"]) * 100, 2), "d_white": round((A["white"] - T["white"]) * 100, 2),
         "d_cast": round(math.hypot(A["cast"][0] - T["cast"][0], A["cast"][1] - T["cast"][1]) * 100, 2),
         "chroma_ratio": round(A["chroma"] / max(1e-4, T["chroma"]), 3)}
    if "skin_hue" in A and "skin_hue" in T:
        r["d_skin_hue"] = round(((A["skin_hue"] - T["skin_hue"] + 180) % 360) - 180, 1)
    return r


def match(src, src_times, reference=None, ref_times=None, strength=1.0, width=480):
    """Balance one shot (no reference) or match it to a reference shot. Returns the grade for process_color and the
    measured residuals after applying it to the same frames."""
    if not 0 <= strength <= 1:
        raise ValueError("strength 0..1")
    if not 1 <= len(src_times) <= 6 or (reference and not 1 <= len(ref_times or []) <= 6):
        raise ValueError("1..6 sample times per shot")
    sf = _frames(src, src_times, width)
    rf = _frames(reference, ref_times, width) if reference else None
    grade, S, A, T = solve(sf, rf, strength)
    if rf is None:
        T = {**A, "cast": (0.0, 0.0)}
    return {"mode": "match" if reference else "balance", "grade": grade, "before": report(S), "after": report(A),
            "target": report(T), "residual": residuals(A, T),
            "use": "process_color(request={path, grade}) applies it; pair with protect_skin when a look follows.",
            "tolerance": "match is good when |d_mid| < 2, |d_black|,|d_white| < 2 (points of 100), d_cast < 1 %, chroma_ratio .95-1.05, |d_skin_hue| < 4°"}


def consistency(pid, samples=3, width=320, groups=None):
    """Exposure / white balance / saturation / skin drift between the shots of a timeline (or within given groups of
    shot ids). Only flagged shots are returned, with the group medians they were compared against."""
    from . import agent
    p = agent.read(pid)
    t = p.get("timeline") or {}
    assets = {a["id"]: a for a in store.assets(pid)}
    from .media import safe_asset_path
    rows, skipped = [], []
    for sh in t.get("shots", []):
        a = assets.get(sh.get("asset_id"))
        if not a or a.get("kind") not in ("video", "image"):
            continue
        dur = (sh["end_frame"] - sh["start_frame"]) / 30 * sh.get("playback_rate", 1)
        times = [sh.get("source_start", 0) + dur * (i + .5) / samples for i in range(samples)] if a["kind"] == "video" else [0]
        try:
            px = _pooled(_frames(safe_asset_path(pid, a["id"]), times, width))
            if float(np.asarray(px, np.float32).std()) < (4 if np.asarray(px).max() > 1.5 else 4 / 255):
                skipped.append(sh["id"])  # a flat carrier/solid plate has no colour to compare (graphics sit on top)
                continue
            st = stats(px)
        except ValueError:
            continue
        rows.append({"shot": sh["id"], "frames": [sh["start_frame"], sh["end_frame"]], **report(st), "_cast": st["cast"]})
    if len(rows) < 2:
        return {"shots": len(rows), "flagged": [], "note": "Need at least two picture shots to compare."}
    by = groups or [[r["shot"] for r in rows]]
    flagged, medians = [], []
    for grp in by:
        G = [r for r in rows if r["shot"] in grp]
        if len(G) < 2:
            continue
        med = {k: float(np.median([r[k] for r in G if k in r])) for k in ("black_pct", "mid_pct", "white_pct", "chroma_pct") }
        cb, cr = float(np.median([r["_cast"][0] for r in G])), float(np.median([r["_cast"][1] for r in G]))
        skin = [r["skin_hue_deg"] for r in G if "skin_hue_deg" in r]
        sk = float(np.median(skin)) if skin else None
        medians.append({"shots": len(G), **{k: round(v, 1) for k, v in med.items()}, **({"skin_hue_deg": round(sk, 1)} if sk is not None else {})})
        for r in G:
            why = []
            if abs(r["mid_pct"] - med["mid_pct"]) > 6:
                why.append(f"exposure {r['mid_pct'] - med['mid_pct']:+.1f} pts mid")
            if abs(r["black_pct"] - med["black_pct"]) > 2:
                why.append(f"black {r['black_pct'] - med['black_pct']:+.1f} pts")
            d_cast = math.hypot(r["_cast"][0] - cb, r["_cast"][1] - cr) * 100
            if d_cast > 2:
                why.append(f"white balance off by {d_cast:.1f} % chroma")
            ratio = r["chroma_pct"] / max(.01, med["chroma_pct"])
            if not .85 <= ratio <= 1.15:
                why.append(f"saturation x{ratio:.2f}")
            if sk is not None and "skin_hue_deg" in r and abs(r["skin_hue_deg"] - sk) > 8:
                why.append(f"skin hue {r['skin_hue_deg'] - sk:+.0f}°")
            if why:
                flagged.append({k: v for k, v in r.items() if k != "_cast"} | {"issues": why})
    return {"shots": len(rows), "skipped_flat": skipped, "groups": medians, "flagged": flagged,
            "next": "color_match(src=flagged shot, reference=a typical shot of its group) → process_color grade; re-run to confirm.",
            "thresholds": "mid ±6 pts (~1/3 stop), black ±2 pts, cast 2 % chroma, saturation ratio .85-1.15, skin hue ±8°"}
