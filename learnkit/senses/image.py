"""Still images (thumbnails, posters, banners, ad frames, screenshots): tone, colour, detail, empty space, text-like
regions, faces, where the eye is pulled (spectral-residual saliency) and how that sits on the thirds, symmetry.

Measurements on pixels only (numpy/OpenCV, no model). Text-like regions are an MSER heuristic, not OCR; faces are
OpenCV's frontal Haar cascade. The caller looks at crops (evidence) before calling anything good.
"""
import math
from pathlib import Path
import numpy as np
from PIL import Image
from . import feature, register

ANALYSIS = 768  # long side used for measuring


def _rgb(im):
    """RGB pixels of any mode, and the share that was transparent. Transparency is laid over mid-grey (its hidden colour
    is not what a viewer sees); 16/32-bit greyscale is scaled to 8 bits instead of clipped."""
    alpha = None
    if im.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        a = np.asarray(im, dtype=np.float64)
        top = float(np.nanmax(a)) if a.size else 0.0
        scale = 257.0 if im.mode.startswith("I;16") or top > 255 else (1 / 255 if im.mode == "F" and top <= 1 else 1.0)
        im = Image.fromarray(np.clip(a / scale, 0, 255).astype(np.uint8)).convert("RGB")
    elif im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        alpha = np.asarray(im.getchannel("A"), dtype=np.float32) / 255
        grey = Image.new("RGBA", im.size, (128, 128, 128, 255))
        im = Image.alpha_composite(grey, im).convert("RGB")
    else:
        im = im.convert("RGB")
    return im, (float((alpha < .5).mean()) if alpha is not None else None)


def load(path, box=None):
    with Image.open(path) as im:
        im, _ = _rgb(im)
        if box:
            x, y, w, h = box
            W, H = im.size
            im = im.crop((int(x * W), int(y * H), max(int(x * W) + 1, int((x + w) * W)), max(int(y * H) + 1, int((y + h) * H))))
        size = im.size
        scale = ANALYSIS / max(size)
        if scale < 1:
            im = im.resize((max(1, round(size[0] * scale)), max(1, round(size[1] * scale))), Image.BILINEAR)
        return np.asarray(im, dtype=np.uint8), size


def _saliency(gray):
    """Spectral residual saliency (Hou & Zhang 2007) on a 64x64 thumbnail, resized back; 0..1. On its own it leaves
    ghosts on flat backgrounds; _attention combines it with contrast to the background."""
    import cv2
    g = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
    spec = np.fft.fft2(g)
    log_amp = np.log(np.abs(spec) + 1e-9)
    residual = log_amp - cv2.blur(log_amp, (3, 3))
    sal = np.abs(np.fft.ifft2(np.exp(residual + 1j * np.angle(spec)))) ** 2
    sal = cv2.GaussianBlur(sal.astype(np.float32), (9, 9), 2.5)
    sal = (sal - sal.min()) / (np.ptp(sal) + 1e-9)
    return cv2.resize(sal, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)


def _attention(gray):
    """Saliency where the picture also differs from its background (|luminance - median|, blurred): on 90 synthetic
    squares, buttons and circles this put the focus within 0.15 of the shape every time (saliency alone: 5 misses)."""
    import cv2
    contrast = np.abs(gray.astype(np.float32) - float(np.median(gray)))
    k = max(3, int(.02 * max(gray.shape)) | 1)
    contrast = cv2.GaussianBlur(contrast, (k, k), 0)
    return _saliency(gray) * (contrast / (contrast.max() + 1e-9))


def _text_like(gray):
    """Share of the frame covered by MSER regions shaped like glyphs, and how many there are (a heuristic)."""
    import cv2
    H, W = gray.shape
    if min(H, W) < 8:  # too small to hold a glyph (OpenCV's MSER also refuses 1-pixel strips)
        return None, None
    regions, boxes = cv2.MSER_create(delta=5, min_area=12, max_area=int(.02 * H * W)).detectRegions(gray)
    mask = np.zeros_like(gray, dtype=np.uint8)
    n = 0
    for x, y, w, h in boxes:
        if 6 <= h <= .25 * H and .1 <= w / max(1, h) <= 6:
            mask[y:y + h, x:x + w] = 1
            n += 1
    return float(mask.mean()), n


def _faces(gray):
    import cv2
    if min(gray.shape) < 24:
        return []
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    found = cascade.detectMultiScale(gray, 1.1, 5, minSize=(max(20, gray.shape[0] // 25),) * 2)
    return [tuple(int(v) for v in f) for f in found] if len(found) else []


def _palette(rgb, k=5):
    import cv2
    px = rgb.reshape(-1, 3).astype(np.float32)
    if len(px) > 20000:
        px = px[np.random.default_rng(7).choice(len(px), 20000, replace=False)]
    k = min(k, len(np.unique(px, axis=0)))
    if k < 1:
        return []
    _, labels, centers = cv2.kmeans(px, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0), 3, cv2.KMEANS_PP_CENTERS)
    shares = np.bincount(labels.ravel(), minlength=k) / len(labels)
    order = np.argsort(-shares)
    return [{"hex": "#%02x%02x%02x" % tuple(int(c) for c in centers[i]), "share": round(float(shares[i]), 3)} for i in order]


def _measure(rgb, size, full=True):
    import cv2
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    lum = gray.astype(np.float32) / 255
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    rg, yb = r - g, .5 * (r + g) - b
    colorful = math.hypot(rg.std(), yb.std()) + .3 * math.hypot(rg.mean(), yb.mean())
    edges = cv2.Canny(gray, 80, 200) > 0
    rows, cols = gray.shape[0] // 16, gray.shape[1] // 16
    empty = float((gray[:rows * 16, :cols * 16].reshape(rows, 16, cols, 16).std(axis=(1, 3)) < 6).mean()) if rows and cols else None
    text_share, text_n = _text_like(gray)
    f = {"luminance_mean": feature(float(lum.mean()), "0..1"), "contrast": feature(float(lum.std()), "0..1 (std of luminance)"),
         "saturation_mean": feature(float(hsv[..., 1].mean() / 255), "0..1"), "colorfulness": feature(colorful, "Hasler-Süsstrunk M"),
         "edge_density": feature(float(edges.mean()), "share of edge pixels"),
         "empty_space_share": feature(empty, "share of flat 16 px blocks"),
         "text_like_share": feature(text_share, "share (MSER heuristic, not OCR)"), "text_like_regions": feature(text_n, "regions")}
    if not full:
        return f
    W, H = size
    faces = _faces(gray)
    sal = _attention(gray)
    ys, xs = np.mgrid[0:sal.shape[0], 0:sal.shape[1]]
    # Where the eye goes first: the strongest 5 % of saliency, squared, so faint texture does not drag the focus.
    weight = sal ** 2 * (sal >= np.quantile(sal, .95))
    total = float(weight.sum()) + 1e-9
    cx, cy = float((weight * xs).sum() / total / sal.shape[1]), float((weight * ys).sum() / total / sal.shape[0])
    thirds = min(math.hypot(cx - a, cy - b) for a in (1 / 3, 2 / 3) for b in (1 / 3, 2 / 3))
    left, right = lum[:, :lum.shape[1] // 2], np.fliplr(lum)[:, :lum.shape[1] // 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.corrcoef(left.ravel(), right.ravel())[0, 1] if left.size > 1 else np.nan
    sym = float(corr) if np.isfinite(corr) else None  # a flat half has no pattern to mirror
    palette = _palette(rgb)
    f.update(width_px=feature(W, "px"), height_px=feature(H, "px"), aspect=feature(W / H, "width/height"),
             faces=feature(len(faces), "faces (frontal)"),
             face_area_share=feature(sum(w * h for _, _, w, h in faces) / (gray.shape[0] * gray.shape[1]), "share"),
             focus_x=feature(cx, "0..1 (saliency centroid)"), focus_y=feature(cy, "0..1 (saliency centroid)"),
             focus_to_thirds=feature(thirds, "distance to nearest thirds point (frame=1)"),
             focus_to_center=feature(math.hypot(cx - .5, cy - .5), "distance (frame=1)"),
             symmetry_lr=feature(sym, "correlation -1..1"),
             palette_colors_over_5pct=feature(sum(1 for p in palette if p["share"] >= .05), "colours"),
             palette=feature(palette, "dominant colours (k-means)"))
    return f, sal, faces


def _regions(sal, n=4):
    """Boxes (fractions) of the most salient blobs, largest first."""
    import cv2
    mask = (sal >= np.quantile(sal, .9)).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    H, W = sal.shape
    boxes = sorted((s for s in stats[1:count] if s[4] >= .002 * H * W), key=lambda s: -s[4])[:n]
    return [[round(x / W, 3), round(y / H, 3), round(max(1, w) / W, 3), round(max(1, h) / H, 3)] for x, y, w, h, _ in boxes]


class ImageSense:
    kind = "image"
    version = "3"
    extensions = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")
    spans = ("box",)

    def measure(self, path, options=None):
        rgb, size = load(path)
        feats, sal, _ = _measure(rgb, size)
        with Image.open(path) as im:
            transparent = _rgb(im)[1]
        if transparent is not None:
            feats["transparent_share"] = feature(transparent, "share of pixels more than half transparent (shown over grey)")
        parts = [{"span": {"box": box}, "role_hint": "salient region", "features": self.measure_span(path, {"box": box})["features"]}
                 for box in _regions(sal)]
        return {"features": feats, "parts": parts, "notes": ["text_like_* is an MSER heuristic, not OCR; faces are frontal only"]}

    def measure_span(self, path, span, options=None):
        rgb, size = load(path, span["box"])
        f = _measure(rgb, size, full=False)
        f["area_share"] = feature(span["box"][2] * span["box"][3], "share of frame")
        return {"features": f}

    def fingerprint(self, path, options=None):
        from .. import fingerprint
        return fingerprint.image(load(path)[0])

    def geometry(self, path, span, features, options=None):
        x, y, w, h = span["box"]
        return {"share": round(w * h, 4), "start_share": round(y, 4)}

    def evidence(self, path, span, out_dir, options=None):
        with Image.open(path) as im:
            im, _ = _rgb(im)
            W, H = im.size
            x, y, w, h = span.get("box", [0, 0, 1, 1])
            crop = im.crop((int(x * W), int(y * H), max(int(x * W) + 1, int((x + w) * W)), max(int(y * H) + 1, int((y + h) * H))))
            crop.thumbnail((768, 768))
            out = Path(out_dir) / f"crop-{x:.3f}-{y:.3f}-{w:.3f}-{h:.3f}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            crop.save(out)
        return [{"type": "image", "path": str(out)}]


register(ImageSense())
