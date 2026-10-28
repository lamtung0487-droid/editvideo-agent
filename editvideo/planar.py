"""Planar tracking (Mocha-style) for screen replacement, signs, posters and any flat surface that moves in perspective.

Features inside the plane's quad are tracked frame to frame (pyramidal Lucas-Kanade with a forward-backward check),
a homography per frame comes from a robust fit (MAGSAC when OpenCV has it, else RANSAC), and the accumulated homography
is refined against the first frame by ECC on the plane's pixels so drift does not build up. Features are replenished
inside the projected quad; occluders can be excluded. The result is a per-frame corner track for a layer's
`corner_pin` (render-side homography, identical in Remotion and HyperFrames).
"""
import math
import uuid
from pathlib import Path
import numpy as np
from . import store
from .media import FFMPEG, command, probe, sha256

FPS = 30


def _decode(path, start, end, fps, width):
    info = probe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not v:
        raise ValueError("No video stream")
    sw, sh = int(v["width"]), int(v["height"])
    w = min(width, sw) // 2 * 2
    h = max(2, round(sh * w / sw / 2) * 2)
    out = store.DATA / "tracks" / str(uuid.uuid4())
    out.mkdir(parents=True)
    raw = out / "frames.gray"
    command([FFMPEG, "-y", "-v", "error", "-ss", start, "-i", path, "-t", end - start, "-vf", f"setpts=PTS-STARTPTS,fps={fps}:round=down,scale={w}:{h}",
             "-an", "-pix_fmt", "gray", "-f", "rawvideo", raw], timeout=600)
    frames = np.fromfile(raw, np.uint8)
    n = len(frames) // (w * h)
    raw.unlink()  # intermediate pixels only; the manifest keeps the result
    return frames[: n * w * h].reshape(n, h, w), (sw, sh), out


def _poly_mask(shape, quad, exclude=()):
    import cv2
    m = np.zeros(shape, np.uint8)
    cv2.fillConvexPoly(m, np.round(quad).astype(np.int32), 255)
    for r in exclude:
        x0, y0, x1, y1 = r
        m[int(y0 * shape[0]):int(math.ceil(y1 * shape[0])), int(x0 * shape[1]):int(math.ceil(x1 * shape[1]))] = 0
    return m


def _ncc(ref, cur, mask, Hs):
    """Normalised cross-correlation of the reference plane pixels with the current frame warped back by Hs (ref→cur)."""
    import cv2
    back = cv2.warpPerspective(cur, Hs, (ref.shape[1], ref.shape[0]), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=-1)
    m = (mask > 0) & (back >= 0)
    if m.sum() >= 50:  # robust: ignore pixels far off the plane's typical residual (occluders)
        r = np.abs(ref - back)
        m &= r <= max(25.0, 3 * float(np.median(r[m])))
    if m.sum() < 50:
        return -1.0
    a, b = ref[m] - ref[m].mean(), back[m] - back[m].mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))


def _convex(q):
    def cross(a, b):
        return a[0] * b[1] - a[1] * b[0]
    c = [cross(q[(i + 1) % 4] - q[i], q[(i + 2) % 4] - q[(i + 1) % 4]) for i in range(4)]
    return all(x > 0 for x in c) or all(x < 0 for x in c)


def _area(q):
    x, y = q[:, 0], q[:, 1]
    return .5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def track_plane(path, corners, start, end, fps=30, work_width=960, exclude=None, smooth=2, refine=True):
    """Track a planar quad. corners: TL, TR, BR, BL in source-normalised coordinates at `start` (seconds).
    exclude: [[l, t, r, b], ...] source-normalised boxes ignored for features at the start (static occluders, reflections).
    Returns per-frame corners (source-normalised), quality per frame, the lost frame if any."""
    import cv2
    source = Path(path).resolve(strict=True)
    if not (isinstance(corners, (list, tuple)) and len(corners) == 4 and all(len(c) == 2 for c in corners)):
        raise ValueError("corners are four [x, y] points TL, TR, BR, BL (source-normalised)")
    if not 0 <= start < end or end - start > 60:
        raise ValueError("window is start < end, at most 60 s")
    if not 6 <= fps <= 60 or not 320 <= work_width <= 1920 or not 0 <= smooth <= 6:
        raise ValueError("fps 6..60, work_width 320..1920, smooth 0..6")
    frames, (sw, sh), out = _decode(source, start, end, fps, work_width)
    if len(frames) < 2:
        raise ValueError("Window too short")
    h, w = frames.shape[1:]
    q0 = np.array(corners, np.float64) * [w, h]
    if not _convex(q0) or _area(q0) < 400:
        raise ValueError("corners must form a convex quad of reasonable size in order TL, TR, BR, BL")
    ex = [list(map(float, r)) for r in (exclude or [])]
    ref = frames[0]
    mask0 = _poly_mask((h, w), q0, ex)
    feat = dict(maxCorners=500, qualityLevel=.005, minDistance=6, blockSize=7)
    pts = cv2.goodFeaturesToTrack(ref, mask=mask0, **feat)
    if pts is None or len(pts) < 12:
        raise ValueError("The plane has too little texture to track (fewer than 12 features); enlarge the quad onto textured surface")
    n0 = len(pts)
    lk = dict(winSize=(21, 21), maxLevel=4, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, .01))
    method = getattr(cv2, "USAC_MAGSAC", cv2.RANSAC)
    H = np.eye(3)
    small = .5 if w > 700 else 1.0
    S = np.diag([small, small, 1.0])
    ref_s = cv2.resize(ref, None, fx=small, fy=small, interpolation=cv2.INTER_AREA).astype(np.float32)
    mask_s = cv2.resize(mask0, None, fx=small, fy=small, interpolation=cv2.INTER_NEAREST)
    quads, quality, lost = [q0.copy()], [{"frame": 0, "inliers": n0, "ecc": 1.0}], None
    prev = ref
    for i in range(1, len(frames)):
        cur = frames[i]
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, pts, None, **lk)
        back, st2, _ = cv2.calcOpticalFlowPyrLK(cur, prev, nxt, None, **lk)
        ok = (st.ravel() == 1) & (st2.ravel() == 1) & (np.linalg.norm((pts - back).reshape(-1, 2), axis=1) < 1.0)
        inl, ecc_c = int(ok.sum()), None
        Hn = None
        if inl >= 8:
            Hi, m = cv2.findHomography(pts[ok], nxt[ok], method, 2.0)
            if Hi is not None:
                inl = int(m.sum())
                Hn = Hi @ H
                keep = np.zeros(len(pts), bool)
                keep[np.where(ok)[0][m.ravel() == 1]] = True
                pts = nxt[keep]
        if Hn is not None and refine:
            # Drift-free refinement: align the first frame's plane pixels onto this frame (ECC, homography model).
            # OpenCV's ECC mask lives in the *current* frame, so the predicted quad is drawn there (shrunk 3% to stay on the
            # plane). The refined warp is kept only when it matches the reference better (NCC over the plane) and does not
            # jump; an occluder crossing the plane cannot pull it away.
            try:
                cur_s = cv2.resize(cur, None, fx=small, fy=small, interpolation=cv2.INTER_AREA).astype(np.float32)
                qa = cv2.perspectiveTransform(q0.reshape(-1, 1, 2), Hn).reshape(4, 2)
                c = qa.mean(0)
                m_cur = _poly_mask(cur_s.shape, (c + (qa - c) * .97) * small)
                Wm = (S @ Hn @ np.linalg.inv(S)).astype(np.float32)
                # Occluders: pixels whose residual against the predicted reference is far above the plane's typical
                # residual are left out (a hand or object crossing the plane, a reflection sweeping over it).
                fwd = cv2.warpPerspective(ref_s, Wm, (cur_s.shape[1], cur_s.shape[0]), flags=cv2.INTER_LINEAR)
                diff = np.abs(cur_s - fwd)
                inside = m_cur > 0
                if inside.any():
                    occl = (diff > max(25.0, 3 * float(np.median(diff[inside])))).astype(np.uint8)
                    m_cur[cv2.dilate(occl, np.ones((5, 5), np.uint8)) > 0] = 0
                ecc_c, Wm = cv2.findTransformECC(ref_s, cur_s, Wm, cv2.MOTION_HOMOGRAPHY,
                                                 (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 15, 1e-4), m_cur, 5)  # measured: same 0.36 px, 2.8x faster than 40/1e-5
                Hr = np.linalg.inv(S) @ Wm.astype(np.float64) @ S
                qb = cv2.perspectiveTransform(q0.reshape(-1, 1, 2), Hr).reshape(4, 2)
                if np.abs(qa - qb).max() < .05 * max(w, h) and _ncc(ref_s, cur_s, mask_s, S @ Hr @ np.linalg.inv(S)) > _ncc(ref_s, cur_s, mask_s, S @ Hn @ np.linalg.inv(S)):
                    Hn = Hr
            except cv2.error:
                ecc_c = None
        q = cv2.perspectiveTransform(q0.reshape(-1, 1, 2), Hn).reshape(4, 2) if Hn is not None else None
        bad = (Hn is None or inl < 10 or not _convex(q) or not .33 < _area(q) / max(1e-6, _area(quads[-1])) < 3
               or np.abs(q - quads[-1]).max() > .25 * max(w, h))
        if bad:
            lost = i
            break
        H = Hn
        quads.append(q)
        quality.append({"frame": i, "inliers": inl, "ecc": None if ecc_c is None else round(float(ecc_c), 3)})
        if len(pts) < max(20, .4 * n0):  # replenish inside the projected quad
            mk = _poly_mask((h, w), q)
            for r in ex:  # exclusions are in start-frame coordinates; carry them with the plane
                rq = np.array([[r[0] * w, r[1] * h], [r[2] * w, r[1] * h], [r[2] * w, r[3] * h], [r[0] * w, r[3] * h]], np.float64)
                cv2.fillConvexPoly(mk, np.round(cv2.perspectiveTransform(rq.reshape(-1, 1, 2), H).reshape(4, 2)).astype(np.int32), 0)
            fresh = cv2.goodFeaturesToTrack(cur, mask=mk, **feat)
            if fresh is not None:
                pts = np.concatenate([pts, fresh]).astype(np.float32)[:600]
        prev = cur
    Q = np.array(quads)
    if smooth and len(Q) > 2 * smooth + 1:
        k = 2 * smooth + 1
        pad = np.concatenate([Q[:1].repeat(smooth, 0), Q, Q[-1:].repeat(smooth, 0)])
        Qs = np.stack([pad[j:j + len(Q)] for j in range(k)]).mean(0)
        Qs[0] = Q[0]
        Q = Qs
    step = FPS / fps
    track = [{"frame": int(round(i * step)), "corners": [[round(float(x) / w, 5), round(float(y) / h, 5)] for x, y in q]} for i, q in enumerate(Q)]
    # Deduplicate frames when fps > 30 and keep strictly increasing frame numbers.
    dedup, last = [], -1
    for s in track:
        if s["frame"] > last:
            dedup.append(s)
            last = s["frame"]
    result = {"track_id": out.name, "source": str(source), "sha256": sha256(source), "window": [start, end], "fps": fps, "work_size": [w, h], "source_size": [sw, sh],
              "track": dedup, "frames_tracked": len(Q), "lost_at_frame": None if lost is None else int(round(lost * step)),
              "lost_at_s": None if lost is None else round(start + lost / fps, 3), "quality": quality[:: max(1, len(quality) // 60)],
              "manifest": str(out / "plane.json"),
              "notes": ["Corners are source-normalised; map them with to_frame() when the clip is scaled/cropped in the frame.",
                        "A hand or object crossing the plane is rejected by the robust fit, but the replacement will still draw over it: "
                        "matte the occluder (track_subject) above the pinned layer.", "Inspect the composite at the start, middle and end of the track."]}
    store.write_json(out / "plane.json", result)
    return result


def load_track(track_id):
    """A track_plane result by id (handles keep per-frame corner data out of the model's context)."""
    if not isinstance(track_id, str) or not track_id.replace("-", "").isalnum():
        raise ValueError("track_id from track_plane")
    p = store.DATA / "tracks" / track_id / "plane.json"
    if not p.exists():
        raise ValueError(f"No plane track {track_id}")
    import json
    return json.loads(p.read_text(encoding="utf-8"))


def summary(result):
    """Compact view of a plane track: first/last corners, coverage, quality range; full corners stay on disk."""
    q = result.get("quality") or []
    ecc = [x["ecc"] for x in q if x.get("ecc") is not None]
    tr = result["track"]
    return {"track_id": result["track_id"], "frames_tracked": result["frames_tracked"], "lost_at_frame": result["lost_at_frame"], "lost_at_s": result["lost_at_s"],
            "window": result["window"], "source_size": result["source_size"], "first": tr[0], "last": tr[-1],
            "inliers_min": min((x["inliers"] for x in q), default=None), "ecc_min": min(ecc) if ecc else None, "manifest": result["manifest"], "notes": result["notes"]}


def to_frame(track, source_size, frame_size=(1920, 1080), box=(0, 0, 1, 1), fit="cover", source_start_frame=0):
    """Map source-normalised corners to frame-normalised corners for a media layer at box (x, y, w, h, frame shares)
    with object-fit cover/contain, and shift frames so they are local to a layer starting at source_start_frame."""
    sw, sh = source_size
    W, H = frame_size
    bx, by, bw, bh = box
    s = (max if fit == "cover" else min)(bw * W / sw, bh * H / sh)
    dw, dh = sw * s, sh * s
    ox, oy = bx * W + (bw * W - dw) / 2, by * H + (bh * H - dh) / 2
    out = []
    for smp in track:
        f = smp["frame"] - source_start_frame
        if f < 0:
            continue
        out.append({"frame": f, "corners": [[round((ox + x * dw) / W, 5), round((oy + y * dh) / H, 5)] for x, y in smp["corners"]]})
    return out


def screen_replace(pid, base_revision, track_result, layer, timeline_start_frame, source_box=(0, 0, 1, 1), fit="cover", dry_run=False):
    """Place a replacement layer (image/video/text/svg...) pinned to a tracked plane. layer: the layer fields
    (id, kind, asset_id..., z, effects); its start/end and corner_pin track are set from the track and the timeline
    frame where the tracked window's first frame appears."""
    from . import agent
    if isinstance(track_result, str):
        track_result = load_track(track_result)
    p = agent.read(pid)
    if p["revision"] != base_revision:
        raise ValueError("Read the current project revision before placing the replacement")
    t = p["timeline"]
    pin = to_frame(track_result["track"], track_result["source_size"], (t["width"], t["height"]), source_box, fit)
    if len(pin) < 2:
        raise ValueError("Track too short")
    end = timeline_start_frame + pin[-1]["frame"] + 1
    first = pin[0]["corners"]
    xs, ys = [c[0] for c in first], [c[1] for c in first]
    L = {"x": round(min(xs), 4), "y": round(min(ys), 4), "width": round(max(.01, max(xs) - min(xs)), 4), "height": round(max(.01, max(ys) - min(ys)), 4),
         **layer, "start_frame": timeline_start_frame, "end_frame": end, "corner_pin": {"track": pin}}
    from .models import Layer
    Layer.model_validate(L)
    if dry_run:
        return {"layer": {**L, "corner_pin": {"track": pin[:3] + [{"...": len(pin) - 4}] + pin[-1:]}}, "frames": len(pin)}
    rev = agent.patch(pid, base_revision, [{"op": "upsert_layer", "layer": L}])["revision"]
    return {"revision": rev, "layer": L["id"], "frames": len(pin), "span": [timeline_start_frame, end],
            "note": "Add light_wrap/tint or a grade so the insert matches the plate; check the edges at several frames."}
