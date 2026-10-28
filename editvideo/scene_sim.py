"""Whether two frames show the same scene: the measure behind repeated_picture and repeated_source (audit_timeline)
and repeat_share (the video sense).

Round 12 counted repeats by 64x36 grey thumbnails (correlation > .85), which miss the same scene shown again from a
slightly different moment: a camera that has panned a little, a subject that has walked a step. An independent
review found 49 % of the shots of one travel film repeated by ORB+RANSAC where thumbnails said 5 % (the studied
exemplar: 6 %). A pair is the same scene when either the thumbnails correlate above .85 or an ORB feature match at
480 px wide (1000 features, Hamming matcher, Lowe ratio .75, RANSAC homography) keeps at least 30 inliers. Features
are cached per (file state, time); ORB runs only on the pairs the thumbnails did not settle, most alike first, capped.
"""
import functools
import os
import subprocess
from pathlib import Path
import numpy as np
from .media import FFMPEG, display_size

THUMB_MATCH, MIN_INLIERS, WIDTH, MAX_PAIRS, RATIO, REPROJ_PX = .85, 30, 480, 3160, .75, 5.0  # 3160 pairs: every pair of 80 shots
IMAGES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")
METHOD = ("same scene: 64x36 grey thumbnails inside any letterbox correlate > .85, or ORB (1000 features at 480 px wide, Hamming, "
          "Lowe ratio .75) with a RANSAC homography keeping >= 30 inliers; ORB only on pairs the thumbnails did not settle")


def frame(path, t, width=WIDTH):
    """One frame of a video at t (an image: its picture) as grey uint8, width px wide; None when unreadable."""
    try:
        if Path(path).suffix.lower() in IMAGES:
            from PIL import Image, ImageOps
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("L")
                return np.asarray(im.resize((width, max(2, round(width * im.height / im.width))), Image.BILINEAR))
        w0, h0 = display_size(path)  # as decoded: rotation and pixel aspect applied
        h = int(round(width * h0 / w0 / 2) * 2)
        raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(path), "-frames:v", "1", "-vf",
                              f"scale={width}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(h, width).copy() if len(raw) == h * width else None
    except Exception:
        return None


def thumbnail(g):
    """64x36 grey thumbnail of a frame inside any letterbox bars (bars would match any two), zero-mean and unit-norm."""
    import cv2
    from .look import _content
    r0, r1, c0, c1 = _content(g.astype(np.float32))
    v = cv2.resize(g[r0:r1, c0:c1], (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    v -= v.mean()
    return v / (np.linalg.norm(v) + 1e-6)


@functools.lru_cache(maxsize=4096)
def _features(path, t, size, mtime):
    import cv2
    g = frame(path, t)
    if g is None:
        return None
    kp, des = cv2.ORB_create(1000).detectAndCompute(g, None)
    return thumbnail(g), np.array([k.pt for k in kp], np.float32).reshape(-1, 2), des


def features(path, t=0.0):
    """(thumbnail, keypoints Nx2 at 480 px wide, ORB descriptors) of the frame at t (an image: 0), rounded to 0.1 s and
    cached per file state; None when the frame cannot be read."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return _features(str(path), round(float(t), 1), st.st_size, st.st_mtime_ns)


def inliers(fa, fb):
    """RANSAC-consistent ORB matches between two frames' features; 0 when either side has too few, or when the fitted
    homography folds or collapses the picture (random matches on a different scene can fit one of those)."""
    import cv2
    _, pa, da = fa
    _, pb, db = fb
    if da is None or db is None or len(pa) < 8 or len(pb) < 8:
        return 0
    good = [m for m, n in (x for x in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2) if len(x) == 2) if m.distance < RATIO * n.distance]
    if len(good) < 8:
        return 0
    H, mask = cv2.findHomography(pa[[m.queryIdx for m in good]], pb[[m.trainIdx for m in good]], cv2.RANSAC, REPROJ_PX)
    if H is None or mask is None:
        return 0
    det = float(H[0, 0] * H[1, 1] - H[0, 1] * H[1, 0])
    return int(mask.sum()) if .2 < det < 5 else 0


def same_scene(fa, fb):
    """True when the thumbnails correlate above .85 or an ORB match keeps 30 inliers (the thumbnails first: cheap)."""
    return bool(float(fa[0] @ fb[0]) > THUMB_MATCH) or inliers(fa, fb) >= MIN_INLIERS


def repeats(feats, max_pairs=MAX_PAIRS):
    """Which frames of a list repeat another: a bool per frame and the matched pairs (i, j, "thumb" | "orb"). Thumbnail
    correlation on every pair; ORB on the pairs the thumbnails did not settle, most alike first, at most max_pairs, and
    never on a pair whose both sides already repeat something (the share is what counts)."""
    n = len(feats)
    dup, pairs = np.zeros(n, bool), []
    if n < 2:
        return dup, pairs
    x = np.stack([f[0] for f in feats])
    c = x @ x.T
    np.fill_diagonal(c, -1)
    for i in range(n):
        j = int(np.argmax(c[i]))
        if c[i, j] > THUMB_MATCH:
            dup[i] = True
            if i < j or not dup[j]:
                pairs.append((min(i, j), max(i, j), "thumb"))
    iu = np.triu_indices(n, 1)
    order = np.argsort(-c[iu])
    for k in order[:max_pairs]:
        i, j = int(iu[0][k]), int(iu[1][k])
        if c[i, j] > THUMB_MATCH or (dup[i] and dup[j]):
            continue
        if inliers(feats[i], feats[j]) >= MIN_INLIERS:
            dup[i] = dup[j] = True
            pairs.append((i, j, "orb"))
    return dup, sorted(set(pairs))
