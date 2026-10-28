"""Then and now, matched (round 13: the owner's list of techniques, B1): an archival shot of a place and a present-day
shot of the same place, aligned on the features they share, so the picture of today appears exactly over the
picture of then and only afterwards settles into its own framing.

The alignment is ORB features with a ratio test and a RANSAC homography between one frame of each, both seen as
the canvas shows them (cover fit). It is reported, never forced: a 1968 black-and-white frame and a 2024 colour frame
may share too little (rebuilt façades, new trees, another lens), and then the caller dissolves without the warp. The
result is a corner-pin track for the present-day layer: from the aligned quad to the full frame, eased.
"""
import subprocess
import numpy as np
from .media import FFMPEG

W, H = 960, 540


def _frame(path, t, w=W, h=H):
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(path), "-frames:v", "1",
                          "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    if len(raw) != w * h:
        raise ValueError(f"no frame at {t:.2f} s in {path}")
    return np.frombuffer(raw, np.uint8).reshape(h, w)


def align(old_path, old_t, new_path, new_t, min_inliers=24):
    """Where the present-day frame lands on the archival one: {"ok", "inliers", "matches", "quad"} with quad the
    present-day frame's corners in the archival canvas (shares, clockwise from top left)."""
    import cv2
    a, b = _frame(old_path, old_t), _frame(new_path, new_t)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    a, b = clahe.apply(a), clahe.apply(b)
    orb = cv2.ORB_create(nfeatures=5000, scaleFactor=1.2, nlevels=8)
    ka, da = orb.detectAndCompute(a, None)
    kb, db = orb.detectAndCompute(b, None)
    if da is None or db is None or len(ka) < 20 or len(kb) < 20:
        return {"ok": False, "inliers": 0, "matches": 0, "quad": None, "why": "too few features"}
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(db, da, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < .78 * n.distance]
    if len(good) < 12:
        return {"ok": False, "inliers": 0, "matches": len(good), "quad": None, "why": "too few matches"}
    src = np.float32([kb[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([ka[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    Hm, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    inl = int(mask.sum()) if mask is not None else 0
    if Hm is None:
        return {"ok": False, "inliers": 0, "matches": len(good), "quad": None, "why": "no homography"}
    corners = np.float32([[0, 0], [W, 0], [W, H], [0, H]]).reshape(-1, 1, 2)
    q = cv2.perspectiveTransform(corners, Hm).reshape(-1, 2) / np.array([W, H])
    area = .5 * abs(np.dot(q[:, 0], np.roll(q[:, 1], 1)) - np.dot(q[:, 1], np.roll(q[:, 0], 1)))
    turn = lambda a, b: float(a[0] * b[1] - a[1] * b[0])
    convex = all(turn(q[(i + 1) % 4] - q[i], q[(i + 2) % 4] - q[(i + 1) % 4]) > 0 for i in range(4))
    sane = convex and .25 <= area <= 4.0 and np.all(np.abs(q) < 3)
    ok = inl >= min_inliers and sane
    return {"ok": bool(ok), "inliers": inl, "matches": len(good), "quad": [[round(float(x), 4), round(float(y), 4)] for x, y in q],
            "why": "" if ok else ("too few inliers" if inl < min_inliers else "implausible warp")}


def relax_track(quad, frames, hold=.25):
    """A corner-pin track (layer-local frames) that holds the aligned quad for `hold` of the span, then eases it to the
    full frame: the present day first sits exactly on the past, then becomes itself."""
    full = [[0, 0], [1, 0], [1, 1], [0, 1]]
    track = []
    h0 = int(frames * hold)
    for f in range(0, frames, 2):
        u = 0.0 if f <= h0 else (f - h0) / max(1, frames - 1 - h0)
        e = u * u * (3 - 2 * u)
        track.append({"frame": f, "corners": [[round(a[0] + (b[0] - a[0]) * e, 4), round(a[1] + (b[1] - a[1]) * e, 4)] for a, b in zip(quad, full)]})
    if track[-1]["frame"] != frames - 1:
        track.append({"frame": frames - 1, "corners": full})
    return track
