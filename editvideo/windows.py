"""Tracked power windows: an adjust layer whose mask follows a track (region box track or planar corner track).

Modes: color (grade inside the window: exposure, saturation, temperature), blur (anonymise a face, plate or screen),
spotlight (darken and desaturate everything outside the window). A colourist's windows are used subtly (a measured
subject-to-surround lift of only ~0.05 stop), so defaults are gentle; anonymising blur is strong (≥ 18 px).
"""
from . import store

MODES = {"color": {"exposure": .25, "saturation": 1.1}, "blur": {"blur": 22}, "spotlight": {"exposure": -.8, "saturation": .6}}


def _boxes(track):
    """[(frame, x0, y0, x1, y1)] normalised to the tracked source, from a track_region result or a plane track."""
    if isinstance(track, str):
        from .planar import load_track
        track = load_track(track)
    if "tracks" in track:  # track_region
        return [(t["local_frame"], *t["region"]) for t in track["tracks"]]
    if "track" in track:  # plane track (corners)
        out = []
        for s in track["track"]:
            xs, ys = [c[0] for c in s["corners"]], [c[1] for c in s["corners"]]
            out.append((s["frame"], min(xs), min(ys), max(xs), max(ys)))
        return out
    raise ValueError("track must be a track_region result, a plane track result or a plane track_id")


def tracked_window(pid, base_revision, track, start_frame, mode="color", shape="ellipse", pad=.15, feather_px=40, adjust=None, layer_id="window",
                   source_box=(0, 0, 1, 1), dry_run=False):
    from . import agent
    from .models import Layer
    if mode not in MODES:
        raise ValueError(f"mode is one of {sorted(MODES)}")
    p = agent.read(pid)
    if p["revision"] != base_revision:
        raise ValueError("Read the current project revision before adding the window")
    boxes = _boxes(track)
    if len(boxes) < 1:
        raise ValueError("empty track")
    bx, by, bw, bh = source_box
    step = max(1, len(boxes) // 59 + 1)  # mask keyframes ≤ 60: sample the track evenly, keep the last sample
    pick = boxes[::step]
    if pick[-1] != boxes[-1]:
        pick.append(boxes[-1])

    def geom(b):
        _, x0, y0, x1, y1 = b
        x0, x1 = bx + x0 * bw, bx + x1 * bw
        y0, y1 = by + y0 * bh, by + y1 * bh
        w, h = (x1 - x0) * (1 + pad), (y1 - y0) * (1 + pad)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return [round(cx, 4), round(cy, 4), round(w / 2, 4), round(h / 2, 4)] if shape == "ellipse" else [round(cx - w / 2, 4), round(cy - h / 2, 4), round(w, 4), round(h, 4)]
    first = pick[0][0]
    keys = [{"frame": int(b[0] - first), "geom": geom(b), "easing": "linear"} for b in pick]
    dur = keys[-1]["frame"] + 1
    data = {**MODES[mode], **(adjust or {})}
    layer = {"id": layer_id, "kind": "adjust", "start_frame": start_frame, "end_frame": start_frame + max(2, dur), "x": 0, "y": 0, "width": 1, "height": 1, "z": 500,
             "data": data, "masks": [{"shape": "ellipse" if shape == "ellipse" else "rect", "geom": keys[0]["geom"], "feather_px": feather_px, "keyframes": keys}],
             "mask_invert": mode == "spotlight"}
    Layer.model_validate(layer)
    if dry_run:
        return {"dry_run": True, "keys": len(keys), "frames": dur, "first_geom": keys[0]["geom"]}
    warn = _bright_subject_warning(track, boxes[0], mode)
    rev = agent.patch(pid, base_revision, [{"op": "upsert_layer", "layer": layer}])["revision"]
    return {"revision": rev, "layer": layer_id, "keys": len(keys), "span": [start_frame, start_frame + dur], **({"warning": warn} if warn else {}),
            "note": "Snapshot a frame mid-track: the window should sit on the subject with a soft edge; anonymising blur must cover the whole face."}


def _bright_subject_warning(track, box, mode):
    """Mean luma inside the first tracked box (track_region results carry their source); a colour lift on a subject that
    is already a highlight cannot be seen (Y > 150), so suggest darkening the surround instead."""
    if mode != "color" or not isinstance(track, dict) or not track.get("source"):
        return None
    try:
        import cv2
        cap = cv2.VideoCapture(track["source"])
        cap.set(cv2.CAP_PROP_POS_MSEC, float((track.get("window") or [0])[0]) * 1000)
        ok, img = cap.read()
        cap.release()
        if not ok:
            return None
        h, w = img.shape[:2]
        _, x0, y0, x1, y1 = box
        roi = img[int(y0 * h):max(int(y0 * h) + 1, int(y1 * h)), int(x0 * w):max(int(x0 * w) + 1, int(x1 * w))]
        y = float(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).mean())
    except Exception:
        return None
    if y > 150:
        return {"subject_luma": round(y, 1), "suggestion": "The subject is already bright: a lift inside will not read. Use mode='spotlight' "
                "(darken/desaturate the surround) or punch in so the subject is larger."}
    return None
