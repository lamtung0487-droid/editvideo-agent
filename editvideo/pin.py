"""Pin graphics to tracked footage: a track_region result (source-normalised boxes over source seconds) becomes x/y
keyframes (canvas pixels) on chosen layers, mapped through the shot the footage plays in: source offset and playback
rate, cover/contain fit with its focus point, and the zoom the shot shows at each frame (held punches and pushes).

Before this the caller had to do that mapping by hand, and a label on handheld footage drifted off the thing it named.
"""
import copy
from pathlib import Path
from . import agent, store

FPS = 30
MAX_KEYS = 100  # per track (models.Layer keyframes limit)


def _zoom_at(shot, f_local):
    """(scale, origin share x, origin share y) the shot's zoom effects show at a shot-local frame."""
    from .ads import _on_screen_scale
    origin = (.5, .5)
    for e in shot.get("effects") or []:
        if e["name"] == "focus_zoom" and e.get("start_frame", 0) <= f_local:  # the runtime applies an effect from its start
            P = e.get("params") or {}
            origin = (P.get("focus_x", .5), P.get("focus_y", .5))  # ... and keeps the last applied one's origin
    return _on_screen_scale(shot.get("effects"), f_local), origin


def canvas_point(shot, asset, W, H, sx, sy, f_local):
    """Canvas pixel of a source-normalised point (sx, sy) at a shot-local frame."""
    aw, ah = asset["width"], asset["height"]
    k = (min if shot.get("fit") == "contain" else max)(W / aw, H / ah)
    dw, dh = aw * k, ah * k
    ox, oy = (W - dw) * shot.get("focus_x", .5), (H - dh) * shot.get("focus_y", .5)  # CSS object-position semantics
    x, y = ox + sx * dw, oy + sy * dh
    z, (fx, fy) = _zoom_at(shot, f_local)
    return fx * W + (x - fx * W) * z, fy * H + (y - fy * H) * z


def _thin(points, limit):
    """Keep at most `limit` keyframes: always the ends, then evenly spaced samples."""
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[round(i * step)] for i in range(limit)]


def pin_to_track(pid, base_revision, track, shot_id, layer_ids, dry_run=False):
    p = agent.read(pid)
    if p["revision"] != base_revision:
        raise ValueError("Read the current project revision before pinning")
    t = copy.deepcopy(p["timeline"])
    tr = store.read_json(Path(track)) if isinstance(track, str) else track
    samples = [s for s in tr.get("tracks") or [] if tr.get("lost_at") is None or s["timestamp"] < tr["lost_at"]]
    if len(samples) < 2:
        raise ValueError("The track has fewer than two usable samples (lost early?)")
    shot = next((s for s in t["shots"] if s["id"] == shot_id), None)
    if not shot or not shot.get("asset_id"):
        raise ValueError(f"Shot {shot_id} with footage not found")
    asset = store.find_asset(pid, shot["asset_id"])
    if not asset or not asset.get("width"):
        raise ValueError("Shot asset has no known size")
    W, H = t["width"], t["height"]
    rate = shot.get("playback_rate", 1) or 1
    pts = []
    for s in samples:
        f = shot["start_frame"] + (s["timestamp"] - shot.get("source_start", 0)) / rate * FPS
        if shot["start_frame"] <= f < shot["end_frame"]:
            l, tp, r, b = s["region"]
            pts.append((f, canvas_point(shot, asset, W, H, (l + r) / 2, (tp + b) / 2, f - shot["start_frame"])))
    if len(pts) < 2:
        raise ValueError("The track window does not overlap the shot's source range; track the seconds this shot plays")
    layers = {l["id"]: l for l in t.get("layers") or []}
    missing = [i for i in layer_ids if i not in layers]
    if missing:
        raise ValueError(f"Layers not found: {missing}")
    out = []
    for lid in layer_ids:
        l = layers[lid]
        inside = [(f, xy) for f, xy in pts if l["start_frame"] <= f < l["end_frame"]]
        if len(inside) < 2:
            out.append({"layer": lid, "skipped": "no tracked samples while the layer is on screen"})
            continue
        f0, (x0, y0) = inside[0]
        keys, seen = [], set()
        for f, (x, y) in inside:
            fr = min(int(round(f - l["start_frame"])), l["end_frame"] - l["start_frame"] - 1)  # keys live in [0, duration)
            if fr in seen:
                continue
            seen.add(fr)
            keys.append((fr, round(x - x0, 2), round(y - y0, 2)))
        keys = _thin(keys, MAX_KEYS)
        kf = dict(l.get("keyframes") or {})
        replaced = [k for k in ("x", "y") if k in kf]
        kf["x"] = [{"frame": fr, "value": x, "easing": "linear"} for fr, x, _ in keys]
        kf["y"] = [{"frame": fr, "value": y, "easing": "linear"} for fr, _, y in keys]
        l["keyframes"] = kf
        travel = max(abs(x) for _, x, _ in keys), max(abs(y) for _, _, y in keys)
        row = {"layer": lid, "keys": len(keys), "frames": [l["start_frame"] + keys[0][0], l["start_frame"] + keys[-1][0]],
               "max_offset_px": [round(travel[0], 1), round(travel[1], 1)], **({"replaced_tracks": replaced} if replaced else {})}
        if l["start_frame"] + keys[-1][0] < min(l["end_frame"], shot["end_frame"]) - 6:
            row["holds_from"] = l["start_frame"] + keys[-1][0]  # track ended (lost or window short): the label stops following
        out.append(row)
    unmodelled = sorted(set(k for k in ("x", "y", "scale", "rotate") if (shot.get("keyframes") or {}).get(k))
                        | {e["name"] for e in shot.get("effects") or [] if e["name"] in ("pan_x", "pan_y", "handheld", "shake", "float", "orbit", "spin")})
    if shot.get("motion") in ("push", "pull", "pan") and shot.get("fit") != "contain":
        unmodelled = sorted(set(unmodelled) | {f"motion:{shot['motion']}"})
    extra = {"unmodelled_shot_motion": unmodelled} if unmodelled else {}
    if dry_run:
        return {"dry_run": True, "pinned": out, **extra}
    rev = agent.patch(pid, base_revision, [{"op": "upsert_layer", "layer": layers[i]} for i in layer_ids if "keys" in next(o for o in out if o["layer"] == i)])["revision"]
    return {"revision": rev, "pinned": out, "lost_at": tr.get("lost_at"), **extra,
            "note": "Each layer keeps its placement at its first tracked frame and follows the region's centre from there "
                    "(translation only: no scale or rotation). Snapshot the start, middle and end of the span."}
