"""Burned-in overlays: channel logos and watermarks that stay still while the picture under them moves.

Archive re-uploads often carry a second broadcaster's logo inside the picture (round 13: the army film studio's mark in
the corner of footage that QPVN re-broadcast), which a fixed per-source crop cannot reach. `find` samples frames across a
window and keeps the corner regions whose pixels barely change over time but carry strong edges in every frame: static
texture is an overlay, moving content is picture. `clean` removes the boxes with FFmpeg's `delogo` (interpolation from the
surrounding pixels), which suits small marks over moving archive; stabilize after cleaning, never before (a steadied
picture makes the logo move).
"""
import subprocess
import numpy as np
from .media import FFMPEG, FFPROBE


def _info(path):
    """Displayed width and height (rotation applied) and duration in seconds."""
    from .media import probe, display_size
    info = probe(str(path))
    v = next(st for st in info["streams"] if st.get("codec_type") == "video")
    W, H = display_size(path)  # FFmpeg filters see the rotated, square-pixel picture
    dur = info["format"].get("duration") or v.get("duration")
    return int(W), int(H), float(dur) if dur not in (None, "N/A") else 0.0


def find(path, start=0.0, end=None, samples=24, width=480, max_area=.06, min_motion=8.0):
    """Static textured regions near the frame's corners. Returns {"boxes": [[x0, y0, x1, y1] normalised], "motion": median
    temporal std of the frame, "note"}; a window whose whole picture is still cannot tell an overlay from the scene."""
    import cv2
    W, H, dur = _info(path)
    end = min(end or dur, dur)
    h = int(round(width * H / W / 2) * 2)
    times = np.linspace(start + .05, max(start + .1, end - .1), samples)
    frames = []
    for t in times:
        raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={width}:{h},format=gray",
                              "-f", "rawvideo", "-"], capture_output=True).stdout
        if len(raw) == width * h:
            frames.append(np.frombuffer(raw, np.uint8).reshape(h, width).astype(np.float32))
    if len(frames) < 6:
        return {"boxes": [], "motion": None, "note": "too few frames decoded"}
    F = np.stack(frames)
    std = F.std(axis=0)
    motion = float(np.median(std))
    if motion < min_motion:
        return {"boxes": [], "motion": round(motion, 2), "note": "the picture is nearly still: overlays cannot be told from the scene"}
    edges = np.mean([np.hypot(cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)) for f in F], axis=0)
    cand = (std < max(3.0, .3 * motion)) & (edges > max(20.0, 2.5 * float(np.median(edges))))
    cand = cv2.dilate(cand.astype(np.uint8), np.ones((5, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
    boxes = []
    for i in range(1, n):
        x, y, w, hh, area = stats[i]
        x0, y0, x1, y1 = x / width, y / h, (x + w) / width, (y + hh) / h
        corner = (x0 > .7 or x1 < .3) and (y0 > .7 or y1 < .3)  # broadcasters' marks sit in a corner
        # a mark is compact (not a thin strip along a crop edge or the gate) and big enough to read; static props deeper
        # in the frame are picture, not overlays
        if corner and min(w / width, hh / h) >= .02 and .002 <= w * hh / (width * h) < max_area and area > 40:
            pad = .012
            boxes.append([round(float(max(0.0, x0 - pad)), 4), round(float(max(0.0, y0 - pad)), 4), round(float(min(1.0, x1 + pad)), 4),
                          round(float(min(1.0, y1 + pad)), 4)])
    return {"boxes": boxes, "motion": round(motion, 2), "note": ""}


def delogo_filter(boxes, W, H):
    """FFmpeg delogo filters for normalised boxes (kept one pixel inside the frame, as delogo requires)."""
    out = []
    for x0, y0, x1, y1 in boxes:
        x, y = max(1, int(x0 * W)), max(1, int(y0 * H))
        w, h = min(W - 2 - x, int((x1 - x0) * W) + 1), min(H - 2 - y, int((y1 - y0) * H) + 1)
        if w > 2 and h > 2:
            out.append(f"delogo=x={x}:y={y}:w={w}:h={h}")
    return ",".join(out)


def clean(path, out, boxes, crf=17):
    """Re-encode `path` to `out` with the boxes removed (the picture is filtered; the sound is re-encoded to AAC for MP4)."""
    W, H, _ = _info(path)
    vf = delogo_filter(boxes, W, H)
    if not vf:
        raise ValueError("no box inside the frame")
    p = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(path), "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-300:])
    return {"path": str(out), "filter": vf}


def _frames(path, start, end, samples, width):
    import cv2  # noqa: F401  (kept with find's imports)
    W, H, dur = _info(path)
    end = min(end or dur, dur)
    h = int(round(width * H / W / 2) * 2)
    out = []
    for t in np.linspace(start + .05, max(start + .1, end - .1), samples):
        raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={width}:{h},format=gray",
                              "-f", "rawvideo", "-"], capture_output=True).stdout
        if len(raw) == width * h:
            out.append(np.frombuffer(raw, np.uint8).reshape(h, width).astype(np.float32))
    return out, h


def find_family(paths, samples_per_clip=6, width=480, max_area=.12):
    """A broadcaster's mark across one source's clips. A single still clip cannot tell a logo from the scene, but frames
    pooled from many clips of the same source (same crop) differ everywhere except where the mark is burned in. Returns
    {"boxes": [[x0, y0, x1, y1] normalised], "clips": n, "template": edge map of the mark region (internal)}; pass raw
    clips (a steadied clip moves its logo with the correction)."""
    import cv2
    frames, h = [], None
    for p in paths:
        f, h = _frames(p, 0.0, None, samples_per_clip, width)
        frames += f
    if len(frames) < 12:
        return {"boxes": [], "clips": len(paths), "note": "too few frames"}
    F = np.stack(frames)
    std = F.std(axis=0)
    edges = np.mean([np.hypot(cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)) for f in F], axis=0)
    motion = float(np.median(std))
    cand = (std < max(4.0, .3 * motion)) & (edges > max(20.0, 2.5 * float(np.median(edges))))
    cand = cv2.dilate(cand.astype(np.uint8), np.ones((5, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
    boxes = []
    for i in range(1, n):
        x, y, w, hh, area = stats[i]
        x0, y0, x1, y1 = x / width, y / h, (x + w) / width, (y + hh) / h
        corner = (x0 > .6 or x1 < .4) and (y0 > .6 or y1 < .4)
        if corner and min(w / width, hh / h) >= .02 and .002 <= w * hh / (width * h) < max_area and area > 40:
            pad = .012
            boxes.append([round(float(max(0.0, x0 - pad)), 4), round(float(max(0.0, y0 - pad)), 4), round(float(min(1.0, x1 + pad)), 4),
                          round(float(min(1.0, y1 + pad)), 4)])
    return {"boxes": boxes, "clips": len(paths), "motion": round(motion, 2), "edges": edges, "note": ""}


def present(path, box, family, width=480, samples=8, threshold=.35):
    """Whether a clip carries the family's mark: the clip's persistent edges inside the box correlate with the family's."""
    import cv2
    frames, h = _frames(path, 0.0, None, samples, width)
    if not frames:
        return False
    e = np.mean([np.hypot(cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)) for f in frames], axis=0)
    x0, y0, x1, y1 = int(box[0] * width), int(box[1] * h), int(box[2] * width), int(box[3] * h)
    a, b = e[y0:y1, x0:x1].ravel(), family["edges"][y0:y1, x0:x1].ravel()
    if a.size < 20 or a.std() < 1e-3 or b.std() < 1e-3:
        return False
    return float(np.corrcoef(a, b)[0, 1]) > threshold


def zoom_past(boxes, margin=.03):
    """The smallest held punch-in (focus_zoom params, cut) that keeps every box out of frame: the picture scales about the
    corner opposite the marks, and only one axis has to clear each box. Margin covers a steadied clip's moving mark."""
    sx = lambda b, ox: 1 / max(.05, b[0] - margin) if ox == 0 else 1 / max(.05, 1 - b[2] - margin)
    sy = lambda b, oy: 1 / max(.05, b[1] - margin) if oy == 0 else 1 / max(.05, 1 - b[3] - margin)
    best = None
    for ox in (0, 1):
        for oy in (0, 1):
            need = max([1.0] + [min(sx(b, ox), sy(b, oy)) for b in boxes])
            if best is None or need < best[0]:
                best = (need, ox, oy)
    s, ox, oy = best
    fx, fy = float(ox), float(oy)
    # an axis no mark needs stays centred, so the punch-in keeps the picture's middle (a logo top right cleared sideways
    # does not also push the frame to the top)
    if all(sx(b, ox) <= s + 1e-9 for b in boxes):
        fy = .5
    elif all(sy(b, oy) <= s + 1e-9 for b in boxes):
        fx = .5
    return {"amount": round(s - 1, 3), "focus_x": fx, "focus_y": fy, "cut": True}
