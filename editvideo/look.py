"""How a shot looks as a picture, apart from what it shows: the cinematography a viewer reads as beautiful or cheap.

A learning test (round 12) rebuilt a studied travel film's structure and rhythm to within a few per cent and still
looked worse, because the selection read only content (SigLIP) and motion: a 720p phone clip of buffaloes at noon, a
handheld market walk and a dark, noisy night shot all passed. This sense measures what that selection could not see,
per window of a clip: real resolution against the canvas, fine detail, sensor noise, handheld shake, subject isolation
(a sharp subject on a soft background), exposure clipping, contrast, saturation and the warmth of the light.

Numbers carry units and fixed thresholds (calibrated on 4K drone and cinema-camera footage against phone clips); the
grade is a gate (A keep, B usable, C reject), not a taste judgement - composition, story and timing stay the caller's.
"""
import hashlib
import json
import math
import subprocess
from pathlib import Path
import numpy as np
from . import store
from .media import FFMPEG, display_size, probe

CANVAS = (1920, 1080)
# thresholds (a C needs one hard flag; an A needs none and good detail): measured on round-12 material
UPSCALE_MAX, SHAKE_SLIGHT, SHAKE_SHAKY, NOISE_NOISY, DETAIL_SOFT, CLIP_HARSH, CONTRAST_FLAT, DARK = 1.35, 2.0, 4.0, 3.2, .045, .06, .35, .08
# a frame with over half its pixels under luma 16 is read for noise temporally (the spatial measure cannot look there);
# temporal flatness: block contrast in 8-bit levels, never above this; alignment: a shift over 1/16 of the frame is a cut
DARK_SHARE, TEMPORAL_FLAT, TEMPORAL_SHIFT = .5, 8.0, 16


def _frames(path, start, end, fps, width, size):
    w0, h0 = size
    h = int(round(width * h0 / w0 / 2) * 2)
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{max(.05, end - start):.3f}", "-i", str(path), "-vf",
                          f"fps={fps},scale={width}:{h}:flags=area", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, width, 3)


def _luma(rgb):
    return rgb[..., 0] * .2126 + rgb[..., 1] * .7152 + rgb[..., 2] * .0722


def _content(y):
    """Rows and columns of the picture inside letterbox or pillarbox bars (near-black, flat edge bands): bars would
    read as the flattest, noiseless part of the frame and as contrast."""
    rows, cols = (y.mean(axis=1) < 10) & (y.std(axis=1) < 4), (y.mean(axis=0) < 10) & (y.std(axis=0) < 4)
    edge = lambda m: (int(np.argmin(m)) if not m.all() else 0, len(m) - int(np.argmin(m[::-1])) if not m.all() else len(m))
    (r0, r1), (c0, c1) = edge(rows), edge(cols)
    return (r0, r1, c0, c1) if r1 - r0 > .3 * len(rows) and c1 - c0 > .3 * len(cols) else (0, len(rows), 0, len(cols))


def _coarse(yf):
    """Local contrast at a coarse scale (8-bit levels): the standard deviation over 16 px blocks of the picture blurred
    by sigma 2, so grain (fine) does not count and texture or a gradient (coarse) does."""
    import cv2
    b = cv2.GaussianBlur(yf, (0, 0), 2)
    m1, m2 = cv2.boxFilter(b, -1, (16, 16)), cv2.boxFilter(b * b, -1, (16, 16))
    return np.sqrt(np.maximum(m2 - m1 * m1, 0))


def _noise(y):
    """Immerkaer's fast noise sigma (8-bit levels) from the Laplacian-of-differences kernel, on a native-resolution crop
    and only where the picture is flat at a coarser scale (blurred, 16 px blocks) and neither clipped nor crushed:
    texture is not flat there, grain is. The flattest tenth alone had read clean rice terraces as sigma 4.3 and bars
    or clipped sky as noiseless. None when under 3 % of the crop qualifies (a frame of foliage cannot say)."""
    import cv2
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    yf = y.astype(np.float32)
    r = np.abs(cv2.filter2D(yf, -1, k)) * math.sqrt(math.pi / 2) / 6
    coarse = _coarse(yf)
    usable = (yf > 16) & (yf < 239)
    usable[:2], usable[-2:], usable[:, :2], usable[:, -2:] = False, False, False, False
    if usable.mean() < .03:
        return None
    first = float(np.mean(r[usable & (coarse <= np.percentile(coarse[usable], 10))]))  # strong grain survives the blur a little
    flat = usable & (coarse < max(1.5, .2 * first))
    return float(np.mean(r[flat])) if flat.mean() >= .03 else None


def _temporal_noise(y0, y1):
    """Noise sigma (8-bit levels) from the difference of two consecutive frames at native resolution: a still scene
    differs frame to frame by sqrt(2) x sigma. Motion goes first: the global shift (phase correlation at quarter
    scale), then what parallax or a subject leaves (Farneback flow at half scale), both applied as whole-pixel moves
    by nearest-neighbour lookup so the grain itself is never resampled (a drone over rice terraces had read sigma 5.4
    after the global shift alone). Only pixels count that are flat in both frames at a coarse scale (the flattest
    quarter of the picture, never above 8 levels of block contrast, so a frame of foliage still says None) and within
    luma 8..239 in both (the spatial measure wants > 16, which leaves a night frame's grain out: round 12 graded
    grainy night clips A). Median absolute deviation, so what the flow still misses (a minority of the flat pixels)
    does not read as grain. None under 3 % of qualifying pixels, across a cut (a weak peak, or a shift over a
    sixteenth of the frame) or when the second frame repeats the first (a duplicated frame would read as noiseless)."""
    import cv2
    a, b = np.ascontiguousarray(y0, dtype=np.float32), np.ascontiguousarray(y1, dtype=np.float32)
    H, W = a.shape
    if a.shape != b.shape or H < 64 or W < 64:
        return None
    s = 4
    sa, sb = (cv2.resize(x, (W // s, H // s), interpolation=cv2.INTER_AREA) for x in (a, b))
    (dx, dy), resp = cv2.phaseCorrelate(sa, sb, cv2.createHanningWindow(sa.shape[::-1], cv2.CV_32F))
    dx, dy = int(round(dx * s)), int(round(dy * s))  # a(x, y) ~ b(x + dx, y + dy)
    if resp < .03 or abs(dx) > W // TEMPORAL_SHIFT or abs(dy) > H // TEMPORAL_SHIFT:
        return None
    x0, x1, r0, r1 = max(0, -dx), min(W, W - dx), max(0, -dy), min(H, H - dy)
    ya, yb = a[r0:r1, x0:x1], b[r0 + dy:r1 + dy, x0 + dx:x1 + dx]
    h, w = ya.shape
    u8 = lambda y: cv2.resize(np.clip(y, 0, 255).astype(np.uint8), (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    flow = cv2.resize(cv2.calcOpticalFlowFarneback(u8(ya), u8(yb), None, .5, 3, 21, 3, 5, 1.2, 0), (w, h), interpolation=cv2.INTER_LINEAR) * 2
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    yb = cv2.remap(yb, gx + np.round(flow[..., 0]), gy + np.round(flow[..., 1]), cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=-1)
    d = yb - ya
    if np.mean(d == 0) > .98:
        return None
    usable = (ya > 8) & (ya < 239) & (yb > 8) & (yb < 239)  # a lookup off the frame reads -1: out
    usable[:2], usable[-2:], usable[:, :2], usable[:, -2:] = False, False, False, False
    if usable.mean() < .03:
        return None
    c = np.maximum(_coarse(ya), _coarse(yb))
    flat = usable & (c < min(TEMPORAL_FLAT, max(1.5, float(np.percentile(c[usable], 25)))))
    if flat.mean() < .03:
        return None
    dd = d[flat]
    return 1.4826 * float(np.median(np.abs(dd - np.median(dd)))) / math.sqrt(2)


def _detail_and_isolation(y):
    """Fine detail (high-frequency energy at full analysis width relative to the picture's contrast) and isolation
    (the sharpest tile against the median tile, log2: a subject in focus over a soft background reads 2-4)."""
    import cv2
    lap = cv2.Laplacian(y.astype(np.float32), cv2.CV_32F)
    detail = float(np.sqrt(np.mean(lap ** 2)) / (np.std(y) + 8))
    th, tw = y.shape[0] // 4, y.shape[1] // 4
    tiles = [float(np.var(lap[i * th:(i + 1) * th, j * tw:(j + 1) * tw])) for i in range(4) for j in range(4)]
    iso = math.log2((max(tiles) + 1) / (float(np.median(tiles)) + 1))
    return detail, iso


def _shake(path, start, end, size, fps):
    """Handheld shake: global motion over ~1/15 s steps at the source's own frame rate (phase correlation at 320 px),
    minus its 1/3 s average, so a drone's smooth pan, orbit or parallax drops out and a hand's 3-8 Hz jitter stays;
    median of the residual in pixels per 1/15 s at 1920 wide. Resampling a 24/25 fps clip to 15 fps had alternated
    1- and 2-frame steps (a smooth pan read 5 px). Pairs across a cut or over moving water (weak peak) are left out."""
    import cv2
    rate = min(fps or 30.0, 60.0)
    fr = _frames(path, start, min(end, start + 4), rate, 320, size)
    m = max(1, int(round(rate / 15)))  # frames per step
    if len(fr) < 4 * m + 4:
        return 0.0
    g = [np.float32(_luma(f)) for f in fr]
    win = cv2.createHanningWindow(g[0].shape[::-1], cv2.CV_32F)
    pairs = [cv2.phaseCorrelate(a, b, win) for a, b in zip(g, g[m:])]
    d = np.array([s for s, _ in pairs]) * (rate / m) / 15  # px per 1/15 s
    ok = np.array([r >= .08 and math.hypot(*s) < 24 for s, r in pairs])
    if ok.sum() < 6:
        return 0.0
    d = np.where(ok[:, None], d, 0.0)
    k = max(3, int(round(rate / 3)) // 2 * 2 + 1)
    pad = np.pad(d, ((k // 2, k // 2), (0, 0)), mode="edge")
    smooth = np.stack([np.convolve(pad[:, i], np.ones(k) / k, mode="valid") for i in range(2)], axis=1)[:len(d)]
    jitter = np.hypot(*(d - smooth).T)[ok]
    return float(np.median(jitter) * 1920 / 320)


def measure(path, start=0.0, end=None, samples=4, canvas=None):
    """Look of one window [start, end) of a clip (a still image: the whole picture). canvas: the frame it will fill
    (default 1080p in the source's own orientation). Cached per file state, window and canvas."""
    import os
    p = Path(path)
    st = os.stat(p)
    info = probe(str(p)) if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp") else None
    dur = float(info["format"].get("duration") or 0) if info else 0.0
    v = next((x for x in (info or {}).get("streams", []) if x.get("codec_type") == "video"), {})
    rate = str(v.get("avg_frame_rate") or "0/1")
    num, _, den = rate.partition("/")
    fps = float(num) / float(den) if float(den or 0) and float(num or 0) else 30.0
    if dur and start >= dur - max(.05, 1 / fps):
        raise ValueError(f"window starts at {start:.2f} s, the clip ends at {dur:.2f} s")
    end = min(end if end is not None else dur, dur) if dur else 0.0
    w0, h0 = display_size(p)
    canvas = tuple(canvas or (CANVAS if w0 >= h0 else CANVAS[::-1]))
    key = hashlib.sha256(f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}|{start:.2f}|{end:.2f}|{samples}|{canvas}|look-v7".encode()).hexdigest()[:24]
    cache = store.DATA / "cache" / "look" / f"{key}.json"
    if cache.is_file():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:  # a torn write: measure again
            pass
    upscale = max(canvas[0] / w0, canvas[1] / h0)
    if dur:
        times = [start + (end - start) * (i + .5) / samples for i in range(samples)]
        singles = [_frames(p, t, t + .07, 15, 960, (w0, h0))[:1] for t in times]
        if not all(len(f) for f in singles):  # a window shorter than a frame at the tail decodes nothing (was an IndexError)
            raise ValueError(f"no frame decodes at {times[[len(f) for f in singles].index(0)]:.2f} s: the window [{start:.2f}, {end:.2f}) "
                             f"reaches past the last frame of a {dur:.2f} s clip")
        rgb = np.concatenate(singles)
        # two consecutive source frames at native resolution (the rate as the stream's fraction: 23.976 as a float
        # would duplicate or drop one, and a duplicate reads as noiseless)
        native = [_frames(p, t, t + 2.5 / fps, rate if fps != 30.0 or float(num or 0) else fps, min(w0, 3840) // 2 * 2, (w0, h0))[:2]
                  for t in times[1::2]]
    else:
        from PIL import Image, ImageOps
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            native = [np.asarray(im)[None]]
            rgb = np.asarray(im.resize((960, max(2, round(960 * im.height / im.width)))))[None]
    r0, r1, c0, c1 = _content(_luma(np.median(rgb, axis=0)))  # bars in every sample
    rows = []
    for f in rgb[:, r0:r1, c0:c1]:
        y = _luma(f.astype(np.float32))
        detail, iso = _detail_and_isolation(y)
        hi = y >= np.percentile(y, 75)
        mx, mn = f.max(axis=2).astype(np.float32), f.min(axis=2).astype(np.float32)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
        rows.append({"detail": detail, "isolation": iso, "contrast": float(np.percentile(y, 95) - np.percentile(y, 5)) / 255,
                     "clipped": float(np.mean(y >= 250)), "crushed": float(np.mean(y <= 3)), "mean": float(np.mean(y)) / 255,
                     "saturation": float(np.median(sat)),
                     "warmth": float(np.mean(f[..., 0][hi].astype(np.float32) - f[..., 2][hi].astype(np.float32))) / 255})
    med = {k: round(float(np.median([r[k] for r in rows])), 4) for k in rows[0]}
    spatial, temporal, dark = [], [], []
    for pair in native:  # the content box at native resolution, its central 1280x720 at most; the same box on both frames
        if not len(pair):
            continue
        k = pair[0].shape[1] / rgb.shape[2]
        ys = [_luma(f[int(r0 * k):int(r1 * k), int(c0 * k):int(c1 * k)].astype(np.float32)) for f in pair]
        ch, cw = min(720, ys[0].shape[0]), min(1280, ys[0].shape[1])
        ys = [y[(y.shape[0] - ch) // 2:(y.shape[0] + ch) // 2, (y.shape[1] - cw) // 2:(y.shape[1] + cw) // 2] for y in ys]
        n = _noise(ys[0])
        if n is not None:
            spatial.append(n)
        dark.append(float(np.mean(ys[0] < 16)))
        tn = _temporal_noise(ys[0], ys[1]) if len(ys) > 1 else None
        if tn is not None:
            temporal.append(tn)
    sp = round(float(np.median(spatial)), 4) if spatial else None
    tp = round(float(np.median(temporal)), 4) if temporal else None
    # the spatial measure says None on most windows of textured or night footage (round 12: grainy night clips graded A);
    # the temporal one stands in there, and leads on a mostly dark frame, where the spatial one sees a few bright pixels
    mostly_dark = bool(dark) and float(np.median(dark)) > DARK_SHARE
    med.update(noise=tp if tp is not None and (sp is None or mostly_dark) else sp, noise_spatial=sp, noise_temporal=tp)
    shake = round(_shake(p, start, end, (w0, h0), fps), 2) if dur and end - start >= 1 else 0.0
    flags, hard = [], []
    if upscale > UPSCALE_MAX:
        hard.append(f"upscaled x{upscale:.2f} ({w0}x{h0} source)")
    if shake > SHAKE_SHAKY:
        hard.append(f"handheld shake {shake:.1f} px")
    elif shake > SHAKE_SLIGHT:
        flags.append(f"slight shake {shake:.1f} px")
    if med["noise"] is not None and med["noise"] > NOISE_NOISY:
        hard.append(f"noisy (sigma {med['noise']:.1f})")
    if med["detail"] < DETAIL_SOFT:
        flags.append(f"soft (detail {med['detail']:.3f})")
    if med["clipped"] > CLIP_HARSH:
        flags.append(f"highlights clipped {med['clipped'] * 100:.0f} %")
    if med["contrast"] < CONTRAST_FLAT and med["mean"] > .2:  # a night frame is mostly dark by nature, not flat
        flags.append(f"flat (contrast {med['contrast']:.2f})")
    if med["mean"] < DARK:
        flags.append(f"dark (mean {med['mean']:.2f})")
    notes = ["noise unmeasured"] if med["noise"] is None else []  # neither measure could look: never an A on trust (a still, a cut)
    grade = "C" if hard or len(flags) >= 2 else ("B" if flags or notes or med["detail"] < 2 * DETAIL_SOFT else "A")
    out = {"window": [round(start, 2), round(end, 2)], "resolution": [w0, h0], "canvas": list(canvas), "upscale": round(upscale, 2),
           "shake_px": shake, **med, "grade": grade, "flags": hard + flags + notes,
           **({"letterbox": [r0, r1, c0, c1]} if (r0, c0) != (0, 0) or r1 < rgb.shape[1] or c1 < rgb.shape[2] else {}),
           "method": "960-px frames inside any letterbox: Laplacian RMS / luma std (detail), tile sharpness max/median log2 (isolation), "
                     "p95-p5 luma (contrast), clipped share, median saturation, highlight R-B (warmth); noise (sigma, 8-bit levels): "
                     "Immerkaer on the flattest tenth of a native-resolution crop (noise_spatial), and the globally aligned difference of "
                     "two consecutive native frames on pixels flat in both within luma 8..239, MAD / sqrt 2 (noise_temporal), which "
                     "stands in where the spatial one is None and leads on a mostly dark frame; 'noise unmeasured' when neither could "
                     "look. 320-px phase correlation over ~1/15 s steps at the source rate minus a 1/3 s average (shake, px per 1/15 s "
                     "at 1920 wide). Grade: C on upscale > 1.35, shake > 4 px, noise > 3.2 or two soft/clipped/flat/dark flags; A needs "
                     "none, measured noise and detail > 0.09."}
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(out), encoding="utf-8")
    tmp.replace(cache)
    return out
