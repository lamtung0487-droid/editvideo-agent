"""Evidence for the calling AI's own judgement: a timeline audit before rendering, isolated-layer measurements on
rendered frames, and motion signals read from an encoded video.

Every result is a measurement with the threshold that produced it and a concrete next step. Nothing here scores
beauty, predicts retention or approves a cut; heuristics are labelled as heuristics and can be overruled by intent.
"""
import functools
import math
import re
import subprocess
from pathlib import Path
import numpy as np
from . import store, agent, platforms, effects

FPS = 30
SAFE = {"vertical": platforms.ORGANIC_SAFE, "landscape": (.06, .07, .94, .92)}  # editable platform-UI heuristics (platforms.py)
smooth = lambda u: u * u * (3 - 2 * u)


def _finding(level, code, where, evidence, suggestion):
    return {"level": level, "code": code, "where": where, "evidence": evidence, "suggestion": suggestion}


# ---------------------------------------------------------------- 3D camera / labels (mirrors engines/scene3d.js)
def _vec(p):
    return (p.get("x", 0) or 0, p.get("y", 0) or 0, p.get("z", 0) or 0) if p else (0, 0, 0)


def sample_camera(keys, f, linear=False):
    """Same interpolation as the runtime: smoothstep per key pair unless camera_ease is linear."""
    if not keys:
        return None
    if f <= keys[0]["frame"]:
        k = keys[0]
        return _vec(k["position"]), _vec(k["target"])
    for a, b in zip(keys, keys[1:]):
        if f <= b["frame"]:
            u = (f - a["frame"]) / max(1, b["frame"] - a["frame"])
            p = u if linear else smooth(u)
            mix = lambda s, e: tuple(x + (y - x) * p for x, y in zip(_vec(s), _vec(e)))
            return mix(a["position"], b["position"]), mix(a["target"], b["target"])
    k = keys[-1]
    return _vec(k["position"]), _vec(k["target"])


def camera_profile(data, frames):
    """Per-frame camera speed and the two motion defects the runtime can produce from key placement:
    stops (speed collapses at keys under smooth easing) and oscillation (alternating step sizes from dense eased keys)."""
    keys = data.get("camera_keyframes") or []
    if len(keys) < 2:
        return {"keys": len(keys), "moving": False}
    linear = data.get("camera_ease") == "linear"
    pos = [sample_camera(keys, f, linear)[0] for f in range(frames)]
    speed = [math.dist(a, b) for a, b in zip(pos, pos[1:])]
    top = max(speed) if speed else 0
    if top < 1e-6:
        return {"keys": len(keys), "moving": False}
    moving = [i for i, s in enumerate(speed) if s > .05 * top]
    lo, hi = moving[0], moving[-1]
    inner = speed[lo:hi + 1]
    mean = sum(inner) / len(inner)
    osc = sum(abs(inner[i] - (inner[i - 1] + inner[i + 1]) / 2) for i in range(1, len(inner) - 1)) / max(1, len(inner) - 2) / mean if len(inner) > 2 else 0
    stops = []
    for i in range(max(lo + 3, 1), min(hi - 3, len(speed) - 1)):
        around = speed[max(lo, i - 6):i - 1] + speed[i + 2:min(hi + 1, i + 7)]
        ref = sum(around) / len(around) if around else 0
        if ref > .2 * top and speed[i] < .3 * ref and speed[i] <= speed[i - 1] and speed[i] <= speed[i + 1]:
            stops.append(i)
    gaps = [b["frame"] - a["frame"] for a, b in zip(keys, keys[1:])]
    return {"keys": len(keys), "moving": True, "ease": "linear" if linear else "smooth", "min_key_gap": min(gaps),
            "median_key_gap": sorted(gaps)[len(gaps) // 2], "speed_max": round(top, 5), "speed_mean": round(mean, 5),
            "oscillation": round(osc, 3), "stop_frames": stops[:40], "positions": pos}


def _sample_object(o, f):
    """Object pose at local frame f: partial keys inherit the object's base values, smoothstep between keys."""
    base = {"position": _vec(o.get("position")), "scale": o.get("scale", 1) or 1}
    keys = [{"frame": k["frame"], "position": _vec(k["position"]) if k.get("position") else base["position"],
             "scale": k["scale"] if k.get("scale") is not None else base["scale"]} for k in o.get("keyframes") or []]
    if not keys:
        return base
    if f <= keys[0]["frame"]:
        return keys[0]
    for a, b in zip(keys, keys[1:]):
        if f <= b["frame"]:
            p = smooth((f - a["frame"]) / max(1, b["frame"] - a["frame"]))
            return {"position": tuple(x + (y - x) * p for x, y in zip(a["position"], b["position"])), "scale": a["scale"] + (b["scale"] - a["scale"]) * p}
    return keys[-1]


def _basis(P, T):
    f = np.array(T, float) - np.array(P, float)
    f /= np.linalg.norm(f) or 1
    r = np.cross(f, (0, 1, 0))
    r /= np.linalg.norm(r) or 1
    return f, r, np.cross(r, f)


def project(point, P, T, fov, aspect):
    """World point -> normalized device coords (x,y in [-1,1] when on screen) and view depth."""
    f, r, u = _basis(P, T)
    v = np.array(point, float) - np.array(P, float)
    z = float(v @ f)
    if z <= .05:
        return None
    t = math.tan(math.radians(fov) / 2)
    return float(v @ r) / (z * t * aspect), float(v @ u) / (z * t), z


def label_tracks(layer, canvas_w, canvas_h, step=3):
    """Approximate on-canvas boxes of a scene3d layer's HTML labels over time (same visibility rules as the runtime)."""
    data = layer["data"]
    d = layer["end_frame"] - layer["start_frame"]
    W, H = layer["width"] * canvas_w, layer["height"] * canvas_h
    fs = data.get("label_font_size", 32)
    keys = data.get("camera_keyframes") or []
    linear = data.get("camera_ease") == "linear"
    out = []
    for f in range(0, d, step):
        cam = sample_camera(keys, f, linear) if keys else (_vec(data.get("camera_position") or {"x": 4, "y": 2.5, "z": 7}), _vec(data.get("camera_target")))
        boxes = []
        for o in data.get("objects", []):
            if not o.get("label") or o.get("follow"):
                continue
            pose = _sample_object(o, f)
            alpha = min(1, max(0, (pose["scale"] / (o.get("scale") or 1) - .3) / .6))
            if alpha <= .01:
                continue
            if o.get("label_facing"):
                c = np.array(_vec(o["label_facing"]))
                wp = np.array(pose["position"])
                if float((wp - c) @ (np.array(cam[0]) - wp)) <= 0:
                    continue
            pr = project(pose["position"], cam[0], cam[1], data.get("fov", 40), W / H)
            if not pr or abs(pr[0]) >= 1 or abs(pr[1]) >= 1:
                continue
            cx = (pr[0] + 1) / 2 * W
            top = min(H - fs * 1.5, (1 - pr[1]) / 2 * H + 8)
            bw, bh = len(o["label"]) * fs * .56 + 20, fs * 1.45
            boxes.append({"id": o["id"], "text": o["label"],
                          "box": [(layer["x"] * canvas_w + cx - bw / 2) / canvas_w, (layer["y"] * canvas_h + top) / canvas_h, bw / canvas_w, bh / canvas_h]})
        out.append({"frame": layer["start_frame"] + f, "labels": boxes})
    return out


def _overlap(a, b):
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ix * iy / max(1e-9, min(a[2] * a[3], b[2] * b[3]))


def _ranges(frames, gap=6):
    out = []
    for f in sorted(frames):
        if out and f - out[-1][1] <= gap:
            out[-1][1] = f
        else:
            out.append([f, f])
    return out


# ---------------------------------------------------------------- timeline audit
def _text_px(layer, design, w, h):
    t = (design.get("typography") or {}).get(layer.get("typography_role") or "")
    return (t["size"] if t else layer.get("font_size", 60)) * min(w, h) / 1080


def _type_of(layer, design):
    """(font_id, weight, line_height, tracking_em) the engines resolve for a text layer (layer overrides its role)."""
    t = (design.get("typography") or {}).get(layer.get("typography_role") or "") or {}
    return (layer.get("font_id") or t.get("font_id"), layer.get("font_weight") or t.get("weight") or 400,
            layer.get("line_height") or t.get("line_height") or 1.2, t.get("tracking") or 0)


def _axes(layer, design):
    """The role's variable-font axes (a condensed wdth draws far narrower than the default width), unless the layer
    names another font."""
    t = (design.get("typography") or {}).get(layer.get("typography_role") or "") or {}
    return (t.get("variation_axes") or None) if not layer.get("font_id") or layer.get("font_id") == t.get("font_id") else None


def _ink_box(layer, design, W, H):
    """Estimated glyph block (frame shares x, y, w, h): measured line widths aligned in the layer box, lines from the top.
    Falls back to the layer box when the font is not a bundled one."""
    font_id, weight, lh, _ = _type_of(layer, design)
    box = [layer["x"], layer["y"], layer["width"], layer["height"]]
    if not font_id:
        return box
    try:
        from .design_library import layout_text
        px = _text_px(layer, design, W, H)
        probe = min(300, max(12, px))
        m = layout_text(font_id, layer["text"], round(probe), 4000, int(weight), variation_axes=_axes(layer, design))
    except Exception:
        return box
    k = px / probe
    widths = [w * k for w in m["line_widths"]]
    bw = min(layer["width"] * W, max(widths or [0]))
    al = (layer.get("data") or {}).get("align", "left")
    plated = str(layer.get("background") or "").strip().lower() not in ("", "transparent", "none")  # inset + centred in both engines
    inset = min(.35 * px, 24) if plated else 0
    bw = min(layer["width"] * W - 2 * inset, bw)
    x0 = layer["x"] * W + inset + {"center": (layer["width"] * W - 2 * inset - bw) / 2, "right": layer["width"] * W - 2 * inset - bw}.get(al, 0)
    # Ink rows: each CSS line box centres the font's content area; PIL bounds are measured from the ascender line.
    L, lead = lh * px, (lh * px - (m["ascent"] + m["descent"]) * k) / 2
    tops, bots = [b[1] for b in m["glyph_bounds"]], [b[3] for b in m["glyph_bounds"]]
    top = layer["y"] * H + (max(0.0, (layer["height"] * H - len(widths) * L) / 2) if plated else 0)
    y0 = top + lead + min(tops or [0]) * k
    y1 = top + (len(widths) - 1) * L + lead + max(bots or [0]) * k
    return [x0 / W, y0 / H, bw / W, max(1.0, y1 - y0) / H]


def _hex_rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) else None


def _wcag_ratio(a, b):
    def lum(c):
        v = [x / 255 for x in c]
        v = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in v]
        return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]
    lo, hi = sorted((lum(a), lum(b)))
    return (hi + .05) / (lo + .05)


@functools.lru_cache(maxsize=64)
def _source_frame(path, t, width=480):
    """One source frame as RGB (cached: audits run again after every patch)."""
    from .media import FFMPEG
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", path, "-frames:v", "1", "-vf", f"scale={width}:-2",
                          "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True).stdout
    from .media import display_size
    w0, h0 = display_size(path)  # as decoded: rotation and pixel aspect applied (a portrait phone clip had read as None)
    h = int(round(width * h0 / w0 / 2) * 2)
    return np.frombuffer(raw, np.uint8).reshape(h, width, 3) if len(raw) == h * width * 3 else None


@functools.lru_cache(maxsize=256)
def _faces(path, t):
    """Face boxes (normalized x, y, w, h) on one source frame, [] when it cannot be read. Cached on disk per file state
    and detector: decoding is most of the cost, and audits run again after every patch."""
    import hashlib, json, os
    from .footage_pro import cv2, detect_faces
    try:
        st = os.stat(path)
    except OSError:  # a missing source: nothing to read
        return []
    backend = "haar" if hasattr(cv2, "CascadeClassifier") else "owl"
    key = hashlib.sha256(f"{Path(path).resolve()}|{st.st_size}|{st.st_mtime_ns}|{t:.1f}|{backend}".encode()).hexdigest()[:24]
    cache = store.DATA / "cache" / "faces" / f"{key}.json"
    if cache.is_file():
        return [tuple(b) for b in json.loads(cache.read_text(encoding="utf-8"))]
    img = _source_frame(path, t, 640)
    if img is None:  # unreadable here: not cached as "no faces"
        return []
    out = [tuple(round(float(v), 4) for v in b) for b in detect_faces((img @ np.array([.299, .587, .114])).clip(0, 255).astype(np.uint8))]
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(out), encoding="utf-8")
    tmp.replace(cache)
    return out


def _plate_contrast(l, t, asset, design, W, H):
    """WCAG contrast of a text layer with nothing of its own behind it (no plate, no outline or shadow in another tone)
    against the picture under it, read from the source frame through the shot's fit and focus. The render can differ
    (grades, zooms, other layers): a screen, as shortform_audit's render check is for shorts."""
    tc = _hex_rgb(l.get("color")) or (255, 255, 255)
    px = _text_px(l, design, W, H)
    if str(l.get("background") or "").strip().lower() not in ("", "transparent", "none"):
        return None
    for e in l.get("effects") or []:
        # the engines draw shadow black (rgba(0,0,0,.55)) whatever its params say; a soft half-black shadow separates only
        # when its blur is wide for the size (a 2 px blur is no separation), an outline at any width over 2 % of the size
        shadow = e.get("name") == "shadow"
        c = _hex_rgb("#000000" if shadow else (e.get("params") or {}).get("color")) if e.get("name") in ("text_outline", "shadow") else None
        amount = float((e.get("params") or {}).get("amount", 20 if shadow else 2))  # the engine defaults
        if c and amount >= (max(8.0, .15 * px) if shadow else max(2.0, .02 * px)) and _wcag_ratio(tc, c) >= 1.5:
            return None
    f = l["start_frame"] + min(l["end_frame"] - l["start_frame"] - 1, 15)
    # an opaque flat shape between the text and the footage (a paper card, a black slate) is what the text is read
    # against: measure its colour (the redacted document's dark type on paper had read as 1.2:1 against the reel below)
    lx, ly = l.get("x", 0) + l.get("width", 0) / 2, l.get("y", 0) + l.get("height", 0) / 2
    card = [x for x in t.get("layers") or [] if x.get("kind") == "shape" and x["start_frame"] <= f < x["end_frame"] and x.get("z", 0) < l.get("z", 0)
            and (x.get("opacity", 1) or 0) >= .95 and str(x.get("blend") or "normal") == "normal"
            and x.get("x", 0) <= lx <= x.get("x", 0) + x.get("width", 0) and x.get("y", 0) <= ly <= x.get("y", 0) + x.get("height", 0)
            and _hex_rgb(x.get("color"))]
    pics = [x for x in t.get("layers") or [] if x.get("kind") in ("video", "image") and x["start_frame"] <= f < x["end_frame"] and x.get("z", 0) < l.get("z", 0)]
    if card and all(c.get("z", 0) > max([p.get("z", 0) for p in pics] or [-1]) for c in card[-1:]):
        return round(_wcag_ratio(tc, _hex_rgb(max(card, key=lambda x: x.get("z", 0))["color"])), 2)
    under = [x for x in t.get("layers") or [] if x.get("kind") in ("video", "image") and x["start_frame"] <= f < x["end_frame"]
             and x.get("width", 0) * x.get("height", 0) > .5 and x.get("z", 0) < l.get("z", 0)]
    item = under[-1] if under else next((x for x in t["shots"] if x["start_frame"] <= f < x["end_frame"]), None)
    a = asset(item.get("asset_id")) if item else None
    if not a or a.get("kind") not in ("video", "image") or not a.get("width") or not a.get("path"):
        return None
    try:
        if a["kind"] == "video":
            st = item.get("source_start", 0) + (0 if item.get("freeze") else (f - item["start_frame"]) * item.get("playback_rate", 1) / FPS)
            img = _source_frame(str(a["path"]), round(min(st, max(0.0, (a.get("duration") or 1e9) - .1)), 1))
        else:
            from PIL import Image
            img = np.asarray(Image.open(a["path"]).convert("RGB").resize((480, max(1, round(480 * a["height"] / a["width"])))))
    except Exception:
        return None
    if img is None:
        return None
    sw, sh = a["width"], a["height"]
    bw_, bh_ = (W, H) if item in t["shots"] else (item["width"] * W, item["height"] * H)
    k = max(bw_ / sw, bh_ / sh) if item.get("fit", "cover") == "cover" else min(bw_ / sw, bh_ / sh)
    ox = (0 if item in t["shots"] else item["x"] * W) + (bw_ - sw * k) * item.get("focus_x", .5)
    oy = (0 if item in t["shots"] else item["y"] * H) + (bh_ - sh * k) * item.get("focus_y", .5)
    g = img.shape[1] / sw  # grabbed pixels per source pixel
    # held punch-ins (focus_zoom cut) scale the element about their origin: canvas X shows element point o + (X - o) / z
    ex, ey = (0, 0) if item in t["shots"] else (item["x"] * W, item["y"] * H)
    zs = [((e.get("params") or {}).get("amount", .08), (e.get("params") or {}).get("focus_x", .5), (e.get("params") or {}).get("focus_y", .5))
          for e in item.get("effects") or [] if e.get("name") == "focus_zoom" and (e.get("params") or {}).get("cut")
          and e.get("start_frame", 0) <= f - item["start_frame"]]
    unzoom = lambda v, o, n: v if not zs else o * n + (v - o * n) / (1 + float(zs[-1][0]))
    x0, x1 = [int((ex + unzoom(v - ex, zs[-1][1] if zs else .5, bw_) - ox) / k * g) for v in (l["x"] * W, (l["x"] + l["width"]) * W)]
    y0, y1 = [int((ey + unzoom(v - ey, zs[-1][2] if zs else .5, bh_) - oy) / k * g) for v in (l["y"] * H, (l["y"] + l["height"]) * H)]
    crop = img[max(0, y0):max(0, y1), max(0, x0):max(0, x1)].reshape(-1, 3).astype(np.float32)
    # the part of the box beyond the picture (a contained or scaled-down frame) shows the canvas background
    outside = max(1, (x1 - x0) * (y1 - y0)) - len(crop)
    bg = _hex_rgb((design or {}).get("background") or "#102322") if item in t["shots"] else None
    if bg and outside > .25 * max(1, (x1 - x0) * (y1 - y0)):
        crop = np.concatenate([crop, np.tile(np.array(bg, np.float32), (min(outside, 4000), 1))])
    if len(crop) < 20:
        return None
    lum = crop @ np.array([.2126, .7152, .0722], np.float32)
    ref = crop[np.argsort(lum)[int(len(crop) * (.9 if np.mean(tc) > 128 else .1))]]  # the picture most like the text
    return round(_wcag_ratio(tc, tuple(int(v) for v in ref)), 2)


def tracking_fit(layer, design, W, H):
    """Widest letter-spacing (px per glyph, CSS letter-spacing trails every glyph incl. spaces) the layer's resting lines
    take without reflowing in their box, from bundled glyph advances. None when the font is not bundled."""
    font_id, weight, _, _ = _type_of(layer, design)
    if not font_id or not layer.get("text"):
        return None
    t = (design.get("typography") or {}).get(layer.get("typography_role") or "")
    px = t["size"] * min(W, H) / 1080 if t else layer.get("font_size", 60)  # the size the engines resolve (design.js)
    box = layer["width"] * W * .97  # browser shaping differs slightly from FreeType advances
    try:
        from .design_library import layout_text
        probe = min(300, max(12, px))
        k = px / probe
        m = layout_text(font_id, layer["text"], round(probe), max(100, min(4000, round(box / k))), int(weight), variation_axes=_axes(layer, design))
    except Exception:
        return None
    room = [(box - w * k) / len(line) for line, w in zip(m["lines"], m["line_widths"]) if line]
    return round(max(0.0, min(room)), 2) if room else None


_VI = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]")


def is_vietnamese(text: str) -> bool:
    """Vietnamese text: space-separated tokens are syllables, not words (reading/density limits scale ~1.4-1.5x)."""
    return bool(_VI.search((text or "").lower()))


# Looks whose runtime output does not depend on time (engines/effects.js computes them without the phase), besides the
# grade/mask/texture/frame families; tests/test_round7.py checks this list against the runtime source.
STATIC_EFFECTS = ("bloom", "glow", "halation", "highlight", "highlight_glow", "light_wrap", "motion_blur", "rgb_split", "shadow",
                  "text_outline", "text_gradient", "radial_glow", "paper_grain")


def _moves(e):
    """An effect whose rendered value changes over its span (entrances, reveals, camera moves, loops, data), not a static
    look and not a held zoom."""
    from .effects import CATALOG
    fam = (CATALOG.get(e.get("name")) or {}).get("family")
    P = e.get("params") or {}
    looks = fam in (None, "grade", "mask", "texture", "frame") or e.get("name") in STATIC_EFFECTS
    return ((not looks or bool(P.get("ramp"))) and not P.get("cut")  # a look with a ramp (halation, light_wrap) animates
            and e.get("end_frame", 1) - e.get("start_frame", 0) > 1)


def _changing_keys(l):
    """Frames spanned by keyframe tracks whose value actually changes (a constant track moves nothing)."""
    frames = [q["frame"] for pts in (l.get("keyframes") or {}).values() if len({round(float(q["value"]), 4) for q in pts}) > 1 for q in pts]
    return (min(frames), max(frames)) if len(frames) > 1 else None


def reading_words(text):
    """Reading weight of on-screen text: words with letters count 1, bare numbers 0.5, symbols ("/", "·") nothing."""
    import re as _re
    toks = str(text or "").replace("**", "").replace("==", "").split()
    return sum(1 if _re.search(r"[^\W\d_]", t) else .5 if _re.search(r"\d", t) else 0 for t in toks)


def motion_spans(shot, cover):
    """Absolute frame spans [a, b) during which something on screen moves in this shot: the shot's own move and
    animated effects, footage/3D/particle layers, layer keyframes, animated effects, and SVG draw/appear/progress.
    Captions are left out (words changing under a still picture do not make it move)."""
    s0, s1 = shot["start_frame"], shot["end_frame"]
    spans = []
    if shot.get("motion") in ("push", "pull", "pan") and shot.get("fit") != "contain" and shot.get("asset_id"):  # the runtime moves media only
        spans.append((s0, s1))
    spans += [(s0 + e.get("start_frame", 0), s0 + e["end_frame"]) for e in shot.get("effects") or [] if _moves(e)]
    for l in cover:
        a = l["start_frame"]
        if l["kind"] in ("scene3d", "video", "particles"):
            spans.append((l["start_frame"], l["end_frame"]))
            continue
        if l["kind"] == "caption":
            continue
        keys = _changing_keys(l)
        if keys:
            spans.append((a + keys[0], a + keys[1]))
        spans += [(a + e.get("start_frame", 0), a + e["end_frame"]) for e in l.get("effects") or [] if _moves(e)]
        for el in (l.get("data") or {}).get("elements") or []:
            for k in ("draw", "appear", "progress", "fill_in"):
                r = el.get(k)
                if isinstance(r, (list, tuple)) and len(r) == 2:
                    spans.append((a + r[0], a + r[1]))
    return sorted((max(s0, x), min(s1, y)) for x, y in spans if y > s0 and x < s1 and y > x)


def longest_still(shot, spans):
    """(first frame, frames) of the longest interval of the shot with no motion span."""
    best, cur = (shot["start_frame"], 0), shot["start_frame"]
    for a, b in spans + [(shot["end_frame"], shot["end_frame"])]:
        if a - cur > best[1]:
            best = (cur, a - cur)
        cur = max(cur, b)
    return best


def edge_scale(s, at_end):
    """Picture scale at a shot's first (at_end=False) or last frame: held (cut) zooms plus animated zooms at that end."""
    k = 1.0
    for e in s.get("effects", []):
        if e["name"] in ("focus_zoom", "zoom_in", "zoom_out"):
            amt = float((e.get("params") or {}).get("amount", .1))
            cut = (e.get("params") or {}).get("cut")
            k *= 1 + amt if cut or (at_end if e["name"] != "zoom_out" else not at_end) else 1
    return k


def scale_step(a, b):
    """Size change between two picture scales, the same in both directions (x1.08 in = x1.08 out): max(a/b, b/a)."""
    return max(a / b, b / a)


def footage_speed(asset):
    """(speed baked into a footage asset by retime_footage, stabilize report of its source or None), from provenance:
    a clip retimed x8 counts x8 before any playback_rate; a retime of a stabilized clip carries that stabilization."""
    from . import media_tasks
    pv = (asset or {}).get("provenance") or {}
    baked, stab = 1.0, None

    def task_of(path):  # data/media-tasks/<task id>/<artifact>
        try:
            t = media_tasks.get(Path(path).parent.name)
            return t if t.get("state") == "completed" else None
        except Exception:
            return None
    if pv.get("operation") == "retime":
        req = pv.get("request") or {}
        baked = max([float(k.get("speed", 1)) for k in req.get("speed_keys") or []] or [float(req.get("speed", 1))])
        src = task_of(req.get("path", ""))
        if src and src.get("kind") == "stabilize":
            stab = (src.get("result") or {}).get("report") or {}
    elif pv.get("operation") == "stabilize":
        try:
            t = media_tasks.get(pv.get("media_task_id")) if pv.get("media_task_id") else None
        except Exception:  # task record gone: the clip still plays, its measurement is unknown
            t = None
        stab = ((t or {}).get("result") or {}).get("report") or {}
    return baked, stab


def max_magnification(sh):
    """Largest scale a shot's plate reaches on screen over the fit: held (cut) zooms, the end of pushes, the start of
    zoom_outs, scale keys above 1 and the default push motion."""
    k = 1.0
    for e in sh.get("effects") or []:
        if e["name"] in ("focus_zoom", "zoom_in", "zoom_out"):
            k *= max(1.0, 1 + float((e.get("params") or {}).get("amount", .08 if e["name"] == "focus_zoom" else .1)))
    sc = [q["value"] for q in (sh.get("keyframes") or {}).get("scale", [])]
    if sc:
        k *= max(1.0, max(sc))
    if sh.get("motion") in ("push", "pull") and sh.get("fit") != "contain":
        k *= 1.075
    return k


def upscale_factor(sh, asset, W, H):
    """Source pixels → screen pixels at the tightest moment of the shot (cover/contain fit × magnification)."""
    sw, shh = (asset or {}).get("width"), (asset or {}).get("height")
    if not sw or not shh or (asset or {}).get("kind") not in ("video", "image"):
        return None
    fit = min(W / sw, H / shh) if sh.get("fit") == "contain" else max(W / sw, H / shh)
    return fit * max_magnification(sh)


def _plate_scale(sh):
    """How much a shot's picture scales over its span (animated focus_zoom / zoom_in and scale keys; held zooms excluded)."""
    k = 1.0
    for e in sh.get("effects") or []:
        if e["name"] in ("focus_zoom", "zoom_in") and not (e.get("params") or {}).get("cut"):
            k *= 1 + float((e.get("params") or {}).get("amount", .1))
    sc = [q["value"] for q in (sh.get("keyframes") or {}).get("scale", [])]
    if len(sc) > 1:
        k *= max(sc) / max(.01, min(sc))
    return k


def audit_timeline(pid, timeline=None):
    """Static evidence from the locked plan (or a would-be timeline, e.g. after a dry-run recipe): inventory of techniques,
    shot pacing, text reading load and size, text collisions and platform safe regions, transitions, and 3D
    camera/texture/label/plane risks."""
    p = agent.read(pid)
    t = timeline or p.get("timeline")
    if not t:
        raise ValueError("Project has no locked plan yet")
    W, H, N = t["width"], t["height"], t["total_frames"]
    vertical = H > W
    design = t.get("design") or {}
    shots, layers = t["shots"], t["layers"]
    # A chosen direction's pacing scales the attention checks: a calm documentary (6-8 s per idea) holds a map or a face for
    # 15-40 s where a feed edit would cut; the 6 s / 8 s defaults suit explainers and short-form.
    pace = ((design.get("direction") or {}).get("pacing") or {})
    pace_hi = float((pace.get("seconds_per_idea") or [3, 6])[1])
    assets = {a["id"]: a for a in store.assets(pid)}
    def asset(aid):
        if not aid:
            return None
        if aid not in assets:
            try:
                assets[aid] = store.find_asset(pid, aid)
            except Exception:
                assets[aid] = None
        return assets[aid]
    findings = []
    inv = {"shots": len(shots), "seconds": round(N / FPS, 2), "layers_by_kind": {}, "effects": {}, "transitions": {}, "attached_layers": 0}
    for l in layers:
        inv["layers_by_kind"][l["kind"]] = inv["layers_by_kind"].get(l["kind"], 0) + 1
        inv["attached_layers"] += bool(l.get("attach_shot"))
        for e in l.get("effects", []):
            inv["effects"][e["name"]] = inv["effects"].get(e["name"], 0) + 1
    for s in shots:
        tr = (s.get("transition") or {}).get("name")
        if tr:
            key = tr + ("/live" if (s.get("transition") or {}).get("mode") == "live" else "")
            inv["transitions"][key] = inv["transitions"].get(key, 0) + 1
    # Added camera shake on footage. Viewers accept picture unsteadiness below ~0.2 % of the picture height peak to peak
    # (SMPTE 1973; RP 105 allows 0.2-0.3 % weave) and feel it most at 3-6 Hz; archival restoration removes motion rather than
    # adding it, so shake effects on real footage read as a shaking camera, not as energy.
    SHAKE_PP = {"impact_shake": 1.4, "handheld": 1.4, "gate_weave": 2.0, "shake": 2.0, "jitter": 2.0}  # vertical peak-to-peak / amount
    shaken = {}
    for s in shots:
        if (asset(s.get("asset_id")) or {}).get("kind") != "video":
            continue
        for e in s.get("effects") or []:
            k = SHAKE_PP.get(e["name"])
            amount = float((e.get("params") or {}).get("amount", effects.CATALOG.get(e["name"], {}).get("amount", {}).get("default", 0)) or 0)
            if k and amount * k / H * 100 > .2:
                row = shaken.setdefault(e["name"], {"shots": [], "max_pp_percent": 0.0})
                row["shots"].append(s["id"])
                row["max_pp_percent"] = max(row["max_pp_percent"], round(amount * k / H * 100, 2))
    for name, row in shaken.items():
        findings.append(_finding("check", "added_shake", {"effect": name, "shots": row["shots"][:12]}, {"shots": len(row["shots"]), **row},
                                 f"{name} moves real footage by up to {row['max_pp_percent']} % of the picture height peak to peak (viewers notice "
                                 "> 0.2 %). Drop it on archive and live action, or keep gate weave <= 0.1 % (about 1 px at 1080); stabilize "
                                 "shaky sources (stabilize_footage) instead of adding motion."))

    # Lip sync: a shot and a sound that play the same recording must show the same moment. A talking head whose words run
    # ahead of the lips by more than ~45 ms, or behind by more than ~125 ms, is noticed (ITU-R BT.1359 detectability), and
    # two rates drift apart. Shot fitting that slows a picture to fill its span breaks a talking head this way.
    path_of = lambda aid: (asset(aid) or {}).get("path") or aid
    for s in shots:
        if not s.get("asset_id") or s.get("freeze"):
            continue
        for c in t.get("audio_clips") or []:
            if c.get("asset_id") != s["asset_id"] and path_of(c.get("asset_id")) != path_of(s["asset_id"]):
                continue
            a, b = max(s["start_frame"], c["start_frame"]), min(s["end_frame"], c["end_frame"])
            if b - a < 6:
                continue
            rs, rc = float(s.get("playback_rate") or 1), float(c.get("playback_rate") or 1)
            lead = [round(c.get("source_start", 0) + (f - c["start_frame"]) / FPS * rc - s.get("source_start", 0) - (f - s["start_frame"]) / FPS * rs, 3)
                    for f in (a, b)]
            if max(lead) > .045 or min(lead) < -.125 or abs(rs - rc) > .005:
                findings.append(_finding("likely_problem", "av_sync", {"shot": s["id"], "audio": c["id"], "frames": [a, b]},
                                         {"sound_lead_s": lead, "picture_rate": rs, "sound_rate": rc},
                                         "The picture and its own sound show different moments (positive: the sound runs ahead). Set the shot's "
                                         "source_start to the sound's source time at the cut and play both at the same rate; do not stretch a "
                                         "synced shot to fill a span, trim or extend around it instead."))

    # Shots: pacing and stillness that the picture alone cannot carry.
    shot_rows = []
    for i, s in enumerate(shots):
        a = asset(s.get("asset_id"))
        dur = (s["end_frame"] - s["start_frame"]) / FPS
        cover = [l for l in layers if l["start_frame"] < s["end_frame"] and l["end_frame"] > s["start_frame"] and l.get("opacity", 1) > 0]
        animated = [l["id"] for l in cover if l["kind"] in ("scene3d", "video", "particles") or l.get("keyframes")]
        text_ids = [l["id"] for l in cover if l["kind"] in ("text", "caption")]
        spans = motion_spans(s, cover)
        still_at, still = longest_still(s, spans)
        shot_rows.append({"id": s["id"], "start": s["start_frame"], "end": s["end_frame"], "seconds": round(dur, 2),
                          "picture": (a or {}).get("kind", "none"), "motion": s.get("motion"), "transition": s.get("transition"),
                          "moving_layers": animated, "text_layers": text_ids, "longest_still_s": round(still / FPS, 2)})
        if (a or {}).get("kind") in (None, "image") and still / FPS >= 4:
            # What is on screen during the still stretch decides whether it is a reading hold or a dead frame.
            during = [l for l in cover if l["start_frame"] < still_at + still and l["end_frame"] > still_at and l["kind"] != "caption"]
            readable = [l for l in during if l["kind"] in ("text", "counter", "svg", "bar_chart", "line_chart", "pie", "callout", "flow")
                        and l.get("typography_role") != "source"]  # a credit line is not content to hold a frame for
            words = round(sum(reading_words(l.get("text")) for l in readable) + sum(
                reading_words(el.get("text")) for l in readable for el in (l.get("data") or {}).get("elements") or []), 1)
            graphic = any(l["kind"] not in ("text", "callout") for l in readable)
            need = words / 3 + (2.0 if graphic else 1.0)  # ~3 words/s plus time to take in a chart or a card
            where = {"shot": s["id"], "frames": [still_at, still_at + still]}
            ev = {"still_seconds": round(still / FPS, 2), "shot_seconds": round(dur, 2), "readable_layers": [l["id"] for l in readable][:6],
                  "words_on_screen": words, "reading_need_s": round(need, 1)}
            if not readable and still >= dur * FPS - 1:
                findings.append(_finding("likely_problem", "static_hold", where, {**ev, "picture": (a or {}).get("kind", "none")},
                                         "Nothing moves for this whole hold and there is nothing to read. Give the frame one motivated motion "
                                         "(push/pull, photo_3d parallax, a drawn diagram) or shorten it; confirm with motion_audit."))
            elif not readable or still / FPS > need + 3:
                findings.append(_finding("check", "static_hold", where, ev,
                                         "The picture stops moving for longer than its content needs to be read. Shorten the hold, spread the "
                                         "reveal over it (draw/appear later elements, a follower along the plot), or add a slow push."))
            else:
                findings.append(_finding("info", "reading_hold", where, ev,
                                         "A still stretch the reader needs (estimated from the words and graphics on screen)."))
        elif dur >= max(6, 2 * pace_hi) and (a or {}).get("kind") == "video" and not any(
                l["width"] * l["height"] > .6 for l in cover if l["kind"] in ("scene3d", "video")):
            findings.append(_finding("check", "long_shot", {"shot": s["id"], "frames": [s["start_frame"], s["end_frame"]]}, {"seconds": round(dur, 2)},
                                     "Long footage shot: measure its real motion energy with motion_audit; if the clip is calm, cut earlier, "
                                     "add a progression (route drawing, counter) or a second angle."))
    # Letterbox mattes (opaque full-width bars on the top or bottom edge) over footage: a bar across a face, or in a
    # medium shot across the head above it, reads as a framing error the plan cannot show (round 12: a conical hat
    # under a 2.35 matte). Faces on source frames at a third and two thirds of the shot (a detector misses some frames),
    # through fit and focus; zooms not modelled.
    mattes = [l for l in layers if l["kind"] == "shape" and l.get("opacity", 1) >= .9 and l["width"] >= .98 and l["height"] <= .3
              and (l["y"] <= .005 or l["y"] + l["height"] >= .995)]
    for s in shots if mattes else []:
        a, mid = asset(s.get("asset_id")), (s["start_frame"] + s["end_frame"]) // 2
        on = [l for l in mattes if l["start_frame"] <= mid < l["end_frame"]]
        if not on or (a or {}).get("kind") != "video" or not a.get("width") or s["end_frame"] - s["start_frame"] < 15:
            continue
        sw, sh_ = a["width"], a["height"]
        k = max(W / sw, H / sh_) if s.get("fit", "cover") == "cover" else min(W / sw, H / sh_)
        ox, oy = (W - sw * k) * s.get("focus_x", .5), (H - sh_ * k) * s.get("focus_y", .5)
        span = (s["end_frame"] - s["start_frame"]) * (0 if s.get("freeze") else s.get("playback_rate", 1)) / FPS
        times = {round(min(s.get("source_start", 0) + span * q, max(0.0, (a.get("duration") or 1e9) - .1)), 1) for q in (1 / 3, 2 / 3)}
        faces = [b for tt in sorted(times) for b in _faces(str(a["path"]), tt)[:2]]
        for fx, fy, fw, fh in faces:
            if not 0 <= (ox + (fx + fw / 2) * sw * k) / W <= 1:  # cropped off the canvas sideways (a 9:16 cover of 16:9)
                continue
            top, bot = (oy + fy * sh_ * k) / H, (oy + (fy + fh) * sh_ * k) / H
            head = top - (.35 * (bot - top) if bot - top < .25 else 0)  # hair or a hat above the box; a close-up may crop it
            for l in on:
                face_cut = (l["y"] + l["height"] - top) if l["y"] <= .005 else (bot - l["y"])
                head_cut = (l["y"] + l["height"] - head) if l["y"] <= .005 else 0
                if face_cut > .15 * (bot - top) or head_cut > .02:
                    findings.append(_finding("likely_problem" if face_cut > .15 * (bot - top) else "check", "matte_cuts_subject",
                                             {"shot": s["id"], "layer": l["id"], "frames": [s["start_frame"], s["end_frame"]]},
                                             {"face_box_y": [round(top, 3), round(bot, 3)], "head_top_y": round(head, 3),
                                              "bar_y": [round(l["y"], 3), round(l["y"] + l["height"], 3)]},
                                             "The letterbox bar cuts the face or the head above it. Pick a window or a clip with more "
                                             "headroom, move focus_y, or end the matte for this shot."))
                    break
            else:
                continue
            break
    names = [((s.get("transition") or {}).get("name")) for s in shots[1:]]
    run = 1
    for i in range(1, len(names)):
        run = run + 1 if names[i] and names[i] == names[i - 1] else 1
        if run == 3:
            findings.append(_finding("check", "transition_repeat", {"shots": [s["id"] for s in shots[i - 1:i + 2]]}, {"transition": names[i]},
                                     "Three identical transitions in a row read as a template. Keep the default cut where nothing is "
                                     "motivated and reserve the transition for the change it explains."))
    for i, s in enumerate(shots[1:], 1):
        tr = s.get("transition") or {}
        if tr.get("duration_frames"):
            shortest = min(s["end_frame"] - s["start_frame"], shots[i - 1]["end_frame"] - shots[i - 1]["start_frame"])
            if tr["duration_frames"] > .4 * shortest:
                findings.append(_finding("check", "transition_long", {"shot": s["id"]}, {"duration_frames": tr["duration_frames"], "shortest_neighbor": shortest},
                                         "Transition occupies over 40% of a neighbouring shot; shorten it or lengthen the shot."))

    for i, s in enumerate(shots[1:], 1):
        a, tr = shots[i - 1], s.get("transition") or {}
        if tr.get("name") == "dissolve" and a.get("asset_id") and a.get("asset_id") == s.get("asset_id"):
            a_end = a.get("source_start", 0) + (a["end_frame"] - a["start_frame"]) * a.get("playback_rate", 1) / FPS
            same_frames = (tr.get("mode") == "live" and abs(a_end - s.get("source_start", 0)) <= 1.5 / FPS
                           and a.get("playback_rate", 1) == s.get("playback_rate", 1) and a.get("freeze") == s.get("freeze")
                           and (a.get("fit"), a.get("focus_x"), a.get("focus_y")) == (s.get("fit"), s.get("focus_x"), s.get("focus_y"))
                           and scale_step(edge_scale(a, True), edge_scale(s, False)) < 1.03
                           # the shot's own push/pull/pan (default push) ends at 1.075x / an offset: the seam would double
                           and all(x.get("motion") == "hold" or x.get("fit") == "contain" for x in (a, s)))
            if same_frames:  # both sides play the same frames: only the look changes (grey dissolving into colour)
                findings.append(_finding("info", "grade_dissolve", {"shots": [a["id"], s["id"]]}, {"source_gap_s": round(s.get("source_start", 0) - a_end, 3)},
                                         "A live dissolve between contiguous moments of one clip shows the same frames on both sides: "
                                         "it changes only the grade. Keep the framing identical on both shots."))
            elif abs(a_end - s.get("source_start", 0)) < .5:
                findings.append(_finding("likely_problem", "same_clip_dissolve", {"shots": [a["id"], s["id"]]}, {"source_gap_s": round(s.get("source_start", 0) - a_end, 2)},
                                         "A dissolve between contiguous moments of the same clip superimposes two copies of one picture "
                                         "(a doubled subject). Cut instead, or change the framing with an animated push on one shot."))
            elif scale_step(edge_scale(a, True), edge_scale(s, False)) >= 1.03:
                findings.append(_finding("check", "same_clip_dissolve", {"shots": [a["id"], s["id"]]},
                                         {"scale_out": round(edge_scale(a, True), 3), "scale_in": round(edge_scale(s, False), 3)},
                                         "A time-passing dissolve on one camera at two different scales doubles every fixed structure (a tower, "
                                         "a horizon). Match the incoming scale to the outgoing one, or cut."))

    # Rhythm and continuity: nearly equal shot lengths read as a template; a sprawl of fonts or accent colours breaks the
    # film's motif (the design tokens should carry one voice).
    lens = [(s["end_frame"] - s["start_frame"]) / FPS for s in shots]
    if len(lens) >= 5:
        mean = sum(lens) / len(lens)
        cv = (sum((x - mean) ** 2 for x in lens) / len(lens)) ** .5 / mean if mean else 0
        if cv < .25:
            findings.append(_finding("check", "uniform_rhythm", {}, {"shot_length_cv": round(cv, 2), "mean_s": round(mean, 2)},
                                     "Shot lengths are nearly equal; let content set them (short beats around a long held one). beat_map shows where."))
    fonts = {l.get("font_id") for l in layers if l["kind"] == "text" and l.get("font_id")}
    if len(fonts) > 3:
        findings.append(_finding("check", "font_sprawl", {}, {"fonts": sorted(fonts)}, "More than three typefaces; keep one display and one text face (+ mono for data)."))
    def _grey(c):
        try:
            r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
        except (TypeError, ValueError):
            return True
        return max(r, g, b) - min(r, g, b) < 24
    accents = {l.get("color").lower() for l in layers if l["kind"] in ("text", "shape", "svg", "icon") and isinstance(l.get("color"), str)
               and l["color"].startswith("#") and not _grey(l["color"])}
    if len(accents) > 6:
        findings.append(_finding("check", "palette_sprawl", {}, {"accent_colours": sorted(accents)[:12]},
                                 "Many different accent colours; a motif palette (1-2 accents used consistently) reads as one film."))

    # Text: reading load, size on the target screen, collisions, platform UI regions.
    safe = SAFE["vertical" if vertical else "landscape"]
    texts = [l for l in layers if l["kind"] == "text" and l.get("text", "").strip() and l.get("opacity", 1) > .05]
    first_texts = {l["id"] for l in sorted(texts, key=lambda l: l["start_frame"])[:20]}  # source frames are cached per audit run
    for l in texts:
        words = len(l["text"].split())
        secs = (l["end_frame"] - l["start_frame"]) / FPS
        px = _text_px(l, design, W, H)
        role = l.get("typography_role")
        rate = words / max(.3, secs - .5)
        limit = WORDS_PER_S * (1.4 if is_vietnamese(l["text"]) else 1)
        chars = len(" ".join(l["text"].split()))
        cps = chars / max(.3, secs - .3)
        if (words >= 4 and rate > limit) or (chars >= 12 and cps > CHARS_PER_S):
            findings.append(_finding("info" if role == "source" else "likely_problem", "reading_load", {"layer": l["id"], "frames": [l["start_frame"], l["end_frame"]]},
                                     {"words": words, "seconds_on_screen": round(secs, 2), "words_per_second": round(rate, 2), "threshold": round(limit, 2),
                                      "chars_per_second": round(cps, 1), "cps_limit": 17},
                                     "More text than a viewer reads in the time shown (Netflix's Vietnamese subtitles: <= 17 characters/s; ~3 words/s "
                                     "after the entrance). Cut words, split into two cues or hold longer."))
        # Labels, titles and dates compete with narration and a moving picture: read twice at a slow pace (round 13: 35 of
        # 185 layers in the fourth film left before they could be read).
        if role in LABEL_ROLES and chars >= 6 and secs < label_hold_s(chars) - .05:
            findings.append(_finding("check", "text_too_brief", {"layer": l["id"], "frames": [l["start_frame"], l["end_frame"]]},
                                     {"seconds_on_screen": round(secs, 2), "needed_s": round(label_hold_s(chars), 1), "chars": chars},
                                     "A label or title leaves before it can be read twice: hold it at least max(3.5 s, 2 x characters / 15 + 0.5 s), "
                                     "inside one held shot, entering >= 0.5 s after a cut."))
        if px < 26 and role != "source":
            findings.append(_finding("check", "small_text", {"layer": l["id"]}, {"rendered_px": round(px, 1), "threshold_px": 26},
                                     "Small on a phone screen; raise the role size or move detail into narration."))
        if l["id"] in first_texts:  # contrast against the footage under it (every aspect ratio; shortform_audit reads the render)
            c = _plate_contrast(l, t, asset, design, W, H)
            if c is not None and c < (3 if px >= 66 else 4.5):
                findings.append(_finding("check", "low_contrast_plate", {"layer": l["id"], "frames": [l["start_frame"], l["end_frame"]]},
                                         {"contrast": c, "needed": 3 if px >= 66 else 4.5, "measured_on": "source frame under the layer"},
                                         "The text is close in tone to the footage behind it (WCAG): add a box, an outline in another tone "
                                         "or a scrim, or move it over a darker/lighter area."))
        if "\n" in l["text"].strip():
            font_id, weight, lh, tr = _type_of(l, design)
            if font_id:
                try:
                    from .design_library import stack_line_height
                    need = stack_line_height(font_id, l["text"].strip().split("\n"), int(weight), tr)["line_height"]
                except Exception:
                    need = 0
                if need > lh + .005:
                    findings.append(_finding("likely_problem", "diacritic_collision", {"layer": l["id"]}, {"line_height": lh, "needed": need},
                                             "Marks of adjacent lines touch or sit as close to the other line as to their own letter (a dot below between Ạ and the breve of Ă reads TRẮNG). Raise line_height to the measured value or re-break the lines."))
        # Wrapping: the engines pad a text layer 24 px each side; a line that does not fit breaks, and the block grows
        # down over whatever is below (a 4-line title on a speaker's eyes). Predict it with the bundled font.
        font_id, weight, lh, tr = _type_of(l, design)
        if font_id and l.get("text", "").strip():
            try:
                from .design_library import layout_text
                inner = l["width"] * W - 48
                lay = layout_text(font_id, l["text"].strip(), max(12, min(300, round(px))), int(max(100, min(4000, inner))), int(weight),
                                  variation_axes=_axes(l, design)) if inner >= 100 else None
            except Exception:
                lay = None
            authored = len([x for x in l["text"].strip().split("\n")])
            # letter spacing widens every line: the design's tracking plus the widest a `tracking` effect reaches
            spread = tr + max([float((e.get("params") or {}).get("amount", .2)) for e in l.get("effects") or [] if e.get("name") == "tracking"] or [0])
            if lay and spread > 0:
                lines = [x for x in l["text"].strip().split("\n") if x.strip()]
                wide = [layout_text(font_id, x, max(12, min(300, round(px))), 4000, int(weight), variation_axes=_axes(l, design))["line_widths"] for x in lines]
                lay = {**lay, "line_count": sum(max(1, math.ceil((max(w or [0]) + spread * px * len(x)) / inner)) for w, x in zip(wide, lines))}
            need = lay["line_count"] * lh * px / H if lay else 0
            if lay and lay["line_count"] > authored and need > l["height"] + .005:  # wrapping that stays inside its box is fine
                findings.append(_finding("check", "text_wraps", {"layer": l["id"]},
                                         {"authored_lines": authored, "predicted_lines": lay["line_count"], "font_px": round(px, 1),
                                          "predicted_height": round(need, 3), "box_height": round(l["height"], 3)},
                                         "At this size the text breaks into more lines than written (24 px padding each side) and "
                                         "grows down the frame: shrink it (design_library.fit_width), widen the box or break the lines yourself."
                                         + (f" Its typography_role '{role}' sets the size ({round(px)} px) and overrides font_size: pick a smaller "
                                            "role or drop the role and set font_id/font_weight/font_size." if role else "")))
        x0, y0, x1, y1 = l["x"], l["y"], l["x"] + l["width"], l["y"] + l["height"]
        if vertical and (x0 < safe[0] - .02 or y0 < safe[1] - .06 or x1 > safe[2] + .1 or y1 > safe[3] + .1):
            findings.append(_finding("info", "outside_safe_region", {"layer": l["id"]}, {"box": [round(v, 3) for v in (x0, y0, x1, y1)], "safe_region": safe},
                                     "Platform buttons/captions may cover this box on vertical feeds (editable heuristic). Verify the "
                                     "rendered glyph box with review_frames before moving it."))
    # Upscaling: a 720p source covering a 9:16 canvas is already ~2.7x; a push on top turns grain into macroblocks.
    # One finding per source (the fit alone is the source's limit), plus each shot whose zoom takes it past 3.25x.
    soft = {}
    for sh in shots:
        up = upscale_factor(sh, assets.get(sh.get("asset_id")), W, H)
        if up and up > 2.0:
            soft.setdefault(sh["asset_id"], []).append((up, sh))
    for aid, rows in soft.items():
        a, worst = assets[aid], max(rows, key=lambda r: r[0])
        over = [sh["id"] for up, sh in rows if up > 3.25]
        findings.append(_finding("likely_problem" if over else "check", "soft_upscale", {"asset": a.get("name", aid), "shots": over or [sh["id"] for _, sh in rows][:8]},
                                 {"source_px": [a["width"], a["height"]], "worst_upscale": round(worst[0], 2), "worst_shot": worst[1]["id"],
                                  "magnification": round(max_magnification(worst[1]), 2), "limits": [2.0, 3.25]},
                                 "Source pixels are enlarged this much at the tightest moment (fit x zoom); above ~3x grain turns to blocks. "
                                 "Soften the push/zoom on the listed shots, use a higher-resolution source or reframe wider; check at full size."))
    # Text over a strong push: what lies under the text changes as the plate scales (a dark sky becomes a bright solar
    # array), so contrast checked at the entrance can fail at the end. Point at the frame to re-check.
    for l in texts:
        for sh in shots:
            a, b = max(l["start_frame"], sh["start_frame"]), min(l["end_frame"], sh["end_frame"])
            if b - a > 30 and sh.get("asset_id") and _plate_scale(sh) >= 1.3:
                findings.append(_finding("check", "text_over_push", {"layer": l["id"], "shot": sh["id"], "frames": [a, b]}, {"plate_scale": round(_plate_scale(sh), 2)},
                                         f"The plate under this text scales x{_plate_scale(sh):.2f} while it is on screen; check contrast under the glyphs "
                                         f"at frame {b - 1} (review_frames / crop), or give the text a backing plate or a quieter area."))
                break
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            both = (max(a["start_frame"], b["start_frame"]), min(a["end_frame"], b["end_frame"]))
            if both[0] >= both[1]:
                continue
            if _overlap([a["x"], a["y"], a["width"], a["height"]], [b["x"], b["y"], b["width"], b["height"]]) <= .15:
                continue
            ov = _overlap(_ink_box(a, design, W, H), _ink_box(b, design, W, H))  # measured glyph blocks, not layout boxes
            if ov > .1:
                findings.append(_finding("check", "text_boxes_overlap", {"layers": [a["id"], b["id"]], "frames": list(both)}, {"ink_overlap_of_smaller": round(ov, 2)},
                                         "Estimated glyph blocks overlap; confirm with review_frames at a frame in this range."))

    # 3D layers: camera motion defects, magnified textures, plane edges, label collisions, bloom haze.
    scene_rows = []
    for l in layers:
        if l["kind"] != "scene3d":
            continue
        data, d = l["data"], l["end_frame"] - l["start_frame"]
        prof = camera_profile(data, d)
        row = {"layer": l["id"], "camera": {k: v for k, v in prof.items() if k != "positions"}}
        scene_rows.append(row)
        if prof.get("moving"):
            if prof["oscillation"] > .12:
                findings.append(_finding("likely_problem", "camera_oscillation", {"layer": l["id"]},
                                         {"oscillation": prof["oscillation"], "ease": prof["ease"], "min_key_gap": prof["min_key_gap"], "threshold": .12},
                                         "Step size alternates frame to frame: visible judder. Dense keys must use camera_ease='linear' "
                                         "(or keep few keys with smooth easing)."))
            if prof["stop_frames"]:
                findings.append(_finding("likely_problem", "camera_stops", {"layer": l["id"], "frames": [l["start_frame"] + f for f in prof["stop_frames"][:12]]},
                                         {"stops": len(prof["stop_frames"]), "ease": prof["ease"], "median_key_gap": prof["median_key_gap"]},
                                         "Camera nearly halts at intermediate keys (smooth easing per key pair). Use camera_ease='linear' with a "
                                         "pre-eased path, or remove intermediate keys."))
        H_px = l["height"] * H
        aspect = (l["width"] * W) / H_px
        fov = data.get("fov", 40)
        if prof.get("positions"):
            positions = prof["positions"]
        elif data.get("camera_keyframes"):
            positions = [sample_camera(data["camera_keyframes"], 0)[0]]
        else:
            positions = [_vec(data.get("camera_position") or {"x": 4, "y": 2.5, "z": 7})]
        for o in data.get("objects", []):
            tex = o.get("texture") or o.get("emissive_texture")
            if o.get("geometry") == "sphere" and tex and positions:
                img = asset(tex)
                if img and img.get("width"):
                    r = o["size"][0] / 2 * (o.get("scale") or 1)
                    c = _vec(o.get("position"))
                    dmin = min(math.dist(pp, c) for pp in positions)
                    s = dmin - r
                    if s <= 0:
                        findings.append(_finding("likely_problem", "camera_inside_sphere", {"layer": l["id"], "object": o["id"]}, {"closest_distance": round(dmin, 3), "radius": r},
                                                 "Camera reaches the sphere surface; raise altitude."))
                        continue
                    px_per_unit = H_px / (2 * s * math.tan(math.radians(fov) / 2))
                    texel_per_unit = img["width"] / (2 * math.pi * r)
                    mag = px_per_unit / texel_per_unit
                    if mag > 1.6:
                        findings.append(_finding("check", "texture_magnified", {"layer": l["id"], "object": o["id"]},
                                                 {"screen_px_per_texel": round(mag, 2), "texture_width": img["width"], "closest_surface_distance": round(s, 3)},
                                                 "At the closest camera approach each texel covers several pixels: the surface looks soft. Keep the "
                                                 "camera higher, use a larger texture, or cut to real footage before the closest point."))
            if o.get("geometry") == "plane" and o.get("displacement_texture") and positions and not any(abs(v) > 1e-6 for v in _vec(o.get("rotation"))):
                c = np.array(_vec(o.get("position")))
                sx, sy = o["size"][0] * (o.get("scale") or 1), o["size"][1] * (o.get("scale") or 1)
                angles, edges = [], []
                keys = data.get("camera_keyframes")
                linear = data.get("camera_ease") == "linear"
                for f in range(0, d, 3):
                    P, T = sample_camera(keys, f, linear) if keys else (positions[0], _vec(data.get("camera_target")))
                    v = np.array(P) - c
                    angles.append(math.degrees(math.acos(max(-1, min(1, v[2] / (np.linalg.norm(v) or 1))))))
                    fw, rt, up = _basis(P, T)
                    tn = math.tan(math.radians(fov) / 2)
                    for ex in (-1, 1):
                        for ey in (-1, 1):
                            ray = fw + ex * tn * aspect * rt + ey * tn * up
                            if ray[2] >= -1e-6:
                                edges.append(f); break
                            k = (c[2] - P[2]) / ray[2]
                            hit = np.array(P) + k * ray
                            if abs(hit[0] - c[0]) > sx / 2 or abs(hit[1] - c[1]) > sy / 2:
                                edges.append(f); break
                        else:
                            continue
                        break
                if max(angles) > 22:
                    findings.append(_finding("check", "displacement_angle", {"layer": l["id"], "object": o["id"]}, {"max_view_angle_deg": round(max(angles), 1), "threshold_deg": 22},
                                             "Relative-depth relief stretches at depth edges when viewed this obliquely; keep the camera nearer "
                                             "the plane normal or lower displacement_scale."))
                if edges:
                    findings.append(_finding("likely_problem", "plane_edge_visible", {"layer": l["id"], "object": o["id"],
                                             "frames": [[l["start_frame"] + a, l["start_frame"] + b] for a, b in _ranges(edges)]},
                                             {"plane_size": [sx, sy]}, "The view frustum leaves the photo plane: its border shows. Enlarge the plane, "
                                             "move the camera closer, or reduce lateral travel."))
        bloom = data.get("bloom")
        if bloom and (bloom.get("strength", .8) > .6 or bloom.get("threshold", .75) < .78):
            findings.append(_finding("check", "bloom_haze", {"layer": l["id"]}, {"bloom": bloom},
                                     "Strong bloom turns thin emissive lines into wide haze near the camera (strength ≈.3–.5, threshold ≈.85 "
                                     "keeps lines crisp); inspect the closest frame."))
        if any(o.get("label") for o in data.get("objects", [])):
            tracks = label_tracks(l, W, H)
            hits, edge = {}, []
            others = [x for x in texts if x["start_frame"] < l["end_frame"] and x["end_frame"] > l["start_frame"]]
            for fr in tracks:
                labs = fr["labels"]
                for i, a in enumerate(labs):
                    bx = a["box"]
                    if bx[0] < .01 or bx[0] + bx[2] > .99:
                        edge.append(fr["frame"])
                    for b in labs[i + 1:]:
                        if _overlap(bx, b["box"]) > .05:
                            hits.setdefault((a["text"], b["text"]), []).append(fr["frame"])
                    for x in others:
                        if x["start_frame"] <= fr["frame"] < x["end_frame"] and _overlap(bx, [x["x"], x["y"], x["width"], x["height"]]) > .05:
                            hits.setdefault((a["text"], "text:" + x["id"]), []).append(fr["frame"])
            for (a, b), frs in list(hits.items())[:12]:
                findings.append(_finding("check", "label_collision", {"layer": l["id"], "frames": _ranges(frs)}, {"labels": [a, b]},
                                         "Projected 3D labels overlap each other or a text layer here (box estimate). Stagger their appear/hide "
                                         "keys, move a carrier, or change the camera at these frames; confirm with a snapshot."))
            if edge:
                findings.append(_finding("info", "label_at_edge", {"layer": l["id"], "frames": _ranges(edge)}, {}, "A label box touches the frame edge."))
    # Motion-design tells that read as template/cheap (simultaneous identical entrances, missing entrances, compound
    # moves making unrelated claims, overshooting numbers, fade-out/fade-in dips, a different transition at every seam).
    ENTR = {"fade_in", "rise", "drop", "slide_left", "slide_right", "pop", "blur_in", "rotate_in", "flip_x", "flip_y", "wipe_left", "wipe_right",
            "wipe_up", "wipe_down", "iris", "tracking_in", "mask_reveal", "char_spring", "word_reveal", "line_reveal", "character_reveal",
            "typewriter", "decode", "slide_spring", "spring", "soft_edge_reveal", "diagonal_reveal", "diamond_reveal", "marker_reveal"}
    MOVE = {"rise", "drop", "slide_left", "slide_right", "rotate_in", "flip_x", "flip_y", "zoom_in", "zoom_out", "pop", "spring", "blur_in", "skew", "spin"}
    groups = {}
    for l in layers:
        if l["kind"] in ("text", "shape", "icon", "svg", "counter", "image"):
            first = next((e for e in l.get("effects", []) if e["name"] in ENTR), None)
            if first:  # the entrance happens when its effect starts (entrances hold their start state until then)
                groups.setdefault((l.get("attach_shot"), l["start_frame"] + first.get("start_frame", 0), first["name"]), []).append(l["id"])
    for (shot, start, name), ids in groups.items():
        if len(ids) >= 3:
            findings.append(_finding("check", "simultaneous_entrances", {"layers": ids, "frames": [start, start]}, {"effect": name, "count": len(ids)},
                                     "Several elements enter on the same frame with the same move. Bring the focal element first and stagger "
                                     "supporting ones by irregular offsets shorter than the animation (apply_direction restyle does this)."))
    # A hard cut-in on a full-frame plate that starts with the text (impact titles, word cards) is a deliberate cut,
    # not a pop: the plate itself is the picture change.
    plates = [(l["start_frame"], l["end_frame"]) for l in layers if l["kind"] == "shape" and l.get("width", 0) >= .99 and l.get("height", 0) >= .99 and l.get("opacity", 1) > .9]
    for l in texts:
        shot = next((sh for sh in shots if sh["start_frame"] <= l["start_frame"] < sh["end_frame"]), None)
        cut_in = any(a - 1 <= l["start_frame"] < b for a, b in plates) or any(e["name"] == "typewriter" for e in l.get("effects", []))
        if shot and not cut_in and l["start_frame"] > shot["start_frame"] + 2 and not any(e["name"] in ENTR for e in l.get("effects", [])):
            findings.append(_finding("check", "missing_entrance", {"layer": l["id"], "frames": [l["start_frame"], l["start_frame"]]}, {},
                                     "Text pops on mid-shot with no entrance; in motion graphics an unanimated appearance reads as a glitch."))
    # The mirror image: a graphic that vanishes mid-shot at full opacity (no fade/wipe/exit animation, not at a cut or
    # the film's end) reads as a glitch just like an unanimated pop-on.
    bounds = {sh["start_frame"] for sh in shots} | {sh["end_frame"] for sh in shots}
    total = t.get("total_frames") or max((sh["end_frame"] for sh in shots), default=0)
    hidden = {l["matte"]["source"] for l in layers if l.get("matte") and l["matte"].get("hide_source", True)}  # a track matte's shape is never seen
    for l in layers:
        if l["kind"] not in ("text", "svg", "shape", "icon", "counter", "callout") or l.get("opacity", 1) <= .05 or l["end_frame"] - l["start_frame"] < 30 or l["id"] in hidden:
            continue
        if any(abs(l["end_frame"] - b) <= 1 for b in bounds) or l["end_frame"] >= total - 1:
            continue
        exits = any(e["name"] == "fade_out" or e["name"].endswith("_out") or (e["name"] == "text_animate" and (e.get("params") or {}).get("mode") == "out")
                    for e in l.get("effects", []))  # an exit holds its end state (fade_out stays at zero)
        op = (l.get("keyframes") or {}).get("opacity") or []
        if not exits and not (op and op[-1]["value"] <= .05):
            findings.append(_finding("check", "abrupt_exit", {"layer": l["id"], "frames": [l["end_frame"], l["end_frame"]]}, {},
                                     "Disappears mid-shot at full opacity with no exit; end it on a cut/punch or give it a short fade/erase."))
    for l in layers:
        moving = {e["name"] for e in l.get("effects", []) if e["name"] in MOVE and e.get("start_frame", 0) <= 2}
        if len(moving) >= 3:
            findings.append(_finding("check", "compound_motion", {"layer": l["id"]}, {"simultaneous_moves": sorted(moving)},
                                     "Several unrelated moves at once (e.g. slide + rotate + scale + blur) make competing claims; keep the one "
                                     "that carries the idea."))
        if l["kind"] == "counter" and any(e.get("easing") in ("bouncy", "springy") or e["name"] in ("spring", "pop") for e in l.get("effects", [])):
            findings.append(_finding("likely_problem", "number_overshoot", {"layer": l["id"]}, {},
                                     "A counter overshoots its value; transforms may overshoot, numbers may not."))
    for a_, b_ in zip(shots, shots[1:]):
        out_fade = any(e["name"] == "fade_out" for e in a_.get("effects", []))
        in_fade = any(e["name"] == "fade_in" and e.get("start_frame", 0) <= 1 for e in b_.get("effects", []))
        if out_fade and in_fade:
            findings.append(_finding("check", "dip_transition", {"shots": [a_["id"], b_["id"]], "frames": [b_["start_frame"], b_["start_frame"]]}, {},
                                     "Outgoing fades out and incoming fades in: that renders as a dip, not a transition. Use one transition."))
    # Transition grammar measured from film examples: dissolves mean time passing (1.3-2.5 s), dips are 10-12 frames,
    # and most seams are plain cuts; anything else needs a stated job.
    for s in shots[1:]:
        tr = s.get("transition") or {}
        if tr.get("name") == "dissolve" and tr.get("duration_frames", 12) < 8:
            findings.append(_finding("check", "short_dissolve", {"shot": s["id"], "frames": [s["start_frame"], s["start_frame"] + tr["duration_frames"]]},
                                     {"duration_frames": tr["duration_frames"]},
                                     "A dissolve under ~8 frames reads as a stutter. Cut, or give it 1.3-2.5 s when it means time passing."))
    decorative = [s for s in shots[1:] if (s.get("transition") or {}).get("name") not in (None, "dissolve")]
    minutes = N / FPS / 60
    if len(decorative) >= 4 and len(decorative) / max(minutes, 1e-6) > 4:
        findings.append(_finding("check", "decorative_transitions", {"shots": [s["id"] for s in decorative][:12]},
                                 {"per_minute": round(len(decorative) / minutes, 1)},
                                 "Most seams in professional edits are plain cuts; whips, spins and glitches need a job (momentum, a change of place, "
                                 "a deliberate style). Keep them for real scene changes where the motion matches."))
    # Accidental jump cut: same source, nearly continuous source time, same framing, plain cut.
    for a_, b_ in zip(shots, shots[1:]):
        if not a_.get("asset_id") or a_.get("asset_id") != b_.get("asset_id") or b_.get("transition"):
            continue
        a_end = a_.get("source_start", 0) + (a_["end_frame"] - a_["start_frame"]) / FPS * a_.get("playback_rate", 1)
        gap = b_.get("source_start", 0) - a_end
        framing = lambda s: (s.get("fit", "contain"), s.get("motion", "hold"), round(s.get("focus_x", .5), 2), round(s.get("focus_y", .5), 2))

        same_size = scale_step(edge_scale(a_, True), edge_scale(b_, False)) < 1.08  # a punch of x1.08+ (in or out) is a new framing
        # A small skip forward reads as a jump on any source; on a selects edit (picture and sound cut from one
        # recording) any discontinuity does, including selects taken out of order. A long skip on narrated footage is
        # usually new content (a tracking camera that has moved on), so it is not flagged there.
        selects = t.get("timing_method") == "source_video_audio"
        if (1.5 / FPS < gap < 3 or (selects and abs(gap) > 1.5 / FPS)) and framing(a_) == framing(b_) and same_size:  # < 1.5 frames: continuous
            findings.append(_finding("check", "jump_cut", {"shots": [a_["id"], b_["id"]], "frames": [b_["start_frame"], b_["start_frame"]]},
                                     {"source_gap_s": round(gap, 2)},
                                     "Same source and framing across a cut with a time skip (or out-of-order selects): if it is the same set-up, "
                                     "punch in about 15-30% on alternate fragments (focus_zoom), or cover the seam with a cutaway."))
        ra, rb = a_.get("playback_rate", 1) or 1, b_.get("playback_rate", 1) or 1
        if abs(gap) <= 1.5 / FPS and max(ra, rb) / min(ra, rb) >= 1.5:
            findings.append(_finding("check", "speed_step", {"shots": [a_["id"], b_["id"]], "frames": [b_["start_frame"], b_["start_frame"]]},
                                     {"rates": [ra, rb]},
                                     "An instant speed change on one continuous take reads as a jolt (the motion doubles from one frame to "
                                     "the next). Ramp it: retime_footage with speed_keys over the take, then play the result at 1x."))
    # Synthetic narration a listener may not understand (listen-back share above the threshold).
    from .voices import narration_finding
    nf = narration_finding(pid)
    if nf:
        findings.append(_finding(nf[0], nf[1], {}, nf[2], nf[3]))
    # Off-cadence sources at 1x: a 24/25/50 fps clip on the 30 fps timeline repeats (or drops) a frame every few frames,
    # a judder on slow glides (round 12: 13 of 23 clips, 264 repeated frames in a 90 s film, no finding).
    from .code_engine import _fps, off_cadence
    judder = {}
    for sh in shots:
        a = asset(sh.get("asset_id"))
        if ((a or {}).get("kind") == "video" and (sh.get("playback_rate", 1) or 1) == 1 and not sh.get("freeze")
                and sh.get("frame_sampling", "nearest") != "flow" and sh["end_frame"] - sh["start_frame"] >= FPS and a.get("path")):
            try:
                fps_ = _fps(str(a["path"]))
            except Exception:
                continue
            if off_cadence(fps_):
                judder.setdefault(round(fps_, 2), []).append(sh["id"])
    if judder:
        findings.append(_finding("check", "off_cadence_footage", {"shots": [x for v in judder.values() for x in v][:24]},
                                 {"source_fps": {str(k): len(v) for k, v in judder.items()}, "timeline_fps": FPS},
                                 "These 1x shots come from 24/25/50 fps sources: the 30 fps timeline repeats or drops a frame every "
                                 "few frames (judder on slow moves). Set frame_sampling \"flow\" on the shots with camera motion "
                                 "(motion-interpolated at render; can smear thin detail; where fast foreground motion or occlusion "
                                 "would ghost, the render measures it and falls back to the nearest source frame by itself, logging "
                                 "the shot), or keep it on static ones."))
    # Slow motion from nearest frames repeats them unevenly (1-2-1-2 at 0.7x), and a clip conformed to 30 fps by
    # duplication (fps=30 on a 25 fps source repeats every sixth frame) carries the judder inside a file that reads 30 fps
    # (round 13: 171 of 361 archive moments, 64 slowed shots; the owner: "giật").
    slowed, baked = [], {}
    for sh in shots:
        a = asset(sh.get("asset_id"))
        if (a or {}).get("kind") != "video" or sh.get("freeze") or sh.get("frame_sampling", "nearest") == "flow" or not a.get("path"):
            continue
        rate = sh.get("playback_rate", 1) or 1
        if rate < .97 and sh["end_frame"] - sh["start_frame"] >= FPS // 2:
            slowed.append(sh["id"])
        elif rate == 1 and sh["end_frame"] - sh["start_frame"] >= FPS:
            try:
                share = repeated_frames(str(a["path"]), float(sh.get("source_start") or 0), 2.0)
            except Exception:
                continue
            if share >= .1:
                baked[sh["id"]] = round(share, 3)
    if slowed:
        findings.append(_finding("check", "slow_motion_repeats", {"shots": slowed[:24]}, {"shots": len(slowed)},
                                 "Slowed shots repeat source frames unevenly (a stutter on any movement). Set frame_sampling \"flow\": "
                                 "the render interpolates the slow motion (falling back to nearest frames where it would ghost)."))
    if baked:
        findings.append(_finding("check", "baked_cadence", {"shots": list(baked)[:24]}, {"repeated_share": dict(list(baked.items())[:12])},
                                 "These files repeat about one frame in five or six while the picture moves: they were conformed to 30 fps "
                                 "by duplication. Re-cut them from the source at its own rate and set frame_sampling \"flow\"."))
    # Re-use: the same source shown again and again within a stretch reads as a loop of a few clips (round 12: five
    # people four times each in 25 s, the flashes re-showing shots of the previous 10 s). The middle source frame of
    # each footage shot is read once (scene_sim: thumbnail and ORB features, cached) for the two checks below.
    from . import scene_sim
    feats = {}
    for sh in shots:
        a = asset(sh.get("asset_id"))
        if (a or {}).get("kind") in ("video", "image") and a.get("path"):
            mid = (sh["end_frame"] - sh["start_frame"]) / 2 * (0 if sh.get("freeze") else (sh.get("playback_rate", 1) or 1)) / FPS
            f = scene_sim.features(str(a["path"]), sh.get("source_start", 0) + mid if a["kind"] == "video" else 0.0)
            if f is not None:
                feats[sh["id"]] = f
    uses = {}
    for sh in shots:
        if (asset(sh.get("asset_id")) or {}).get("kind") in ("video", "image"):
            uses.setdefault(sh["asset_id"], []).append(sh)
    for aid, ss in uses.items():
        # visits: a run of consecutive shots is one; the spine of an edit (an interview over 40 % of the film) returns by design
        visits = [s for i, s in enumerate(ss) if not i or shots.index(s) != shots.index(ss[i - 1]) + 1]
        starts = [s["start_frame"] for s in visits]
        spine = sum(s["end_frame"] - s["start_frame"] for s in ss) > .4 * N
        dense = 0 if spine else max((sum(1 for y in starts if x <= y < x + 20 * FPS) for x in starts), default=0)
        win = lambda s: (s.get("source_start", 0), s.get("source_start", 0) + (s["end_frame"] - s["start_frame"]) * (s.get("playback_rate", 1) or 1) / FPS)
        again = [(p["id"], q["id"]) for i, p in enumerate(ss) for q in ss[i + 1:]
                 if win(p)[0] < win(q)[1] and win(q)[0] < win(p)[1] and not p.get("freeze") and not q.get("freeze")]
        # two visits inside 20 s whose windows show the same scene from other moments (the camera moved a little, the
        # subject a step: round 12's thumbnails had not seen it); not for the spine
        scene = [] if spine else [(p["id"], q["id"]) for i, p in enumerate(visits) for q in visits[i + 1:]
                                  if q["start_frame"] - p["start_frame"] < 20 * FPS and (p["id"], q["id"]) not in again
                                  and p["id"] in feats and q["id"] in feats and scene_sim.same_scene(feats[p["id"]], feats[q["id"]])]
        if dense >= 3 or again or scene:
            findings.append(_finding("check", "repeated_source", {"shots": [s["id"] for s in ss][:12]},
                                     {"asset": aid, "uses": len(ss), "most_in_20s": dense, "same_moment_twice": again[:4], "same_scene_in_20s": scene[:4]},
                                     "One source carries several shots close together (or shows the same moment, or the same scene within "
                                     "20 s, twice): viewers read it as a loop. Spread its uses, take distant windows with a different "
                                     "framing, or find more material."))
    # Near-identical pictures: shots whose middle source frames show the same scene (scene_sim: grey 64x36 thumbnails
    # correlating > .85, or an ORB match keeping 30 RANSAC inliers, which sees a scene shown again from a slightly
    # different moment; thumbnails alone had read 6 % of a film whose shots repeated by 34 %), the measure
    # learn_video's repeat_share takes of a finished film (exemplar 6 %).
    pics = list(feats.items())
    if len(pics) >= 8:
        dup, pairs = scene_sim.repeats([f for _, f in pics])
        if dup.mean() > .15:
            findings.append(_finding("check", "repeated_picture", {"shots": [pics[i][0] for i in np.nonzero(dup)[0]][:24]},
                                     {"share": round(float(dup.mean()), 3), "pairs": [(pics[i][0], pics[j][0], how) for i, j, how in pairs][:10],
                                      "threshold": .15, "method": scene_sim.METHOD},
                                     "Over 15 % of the shots show another shot's scene again: the film reads as a few clips on a "
                                     "loop. Take other windows (a moving camera changes the picture within seconds), other clips, or "
                                     "fewer shots."))
    # Playback speed on footage: fractional rates repeat/skip source frames unevenly (judder); fast-forwards multiply
    # any camera motion left in the picture by the EFFECTIVE speed (a clip retimed x8 and played at 3x runs at x24).
    for sh in shots:
        a = asset(sh.get("asset_id"))
        r = sh.get("playback_rate", 1) or 1
        if (a or {}).get("kind") != "video":
            continue
        baked, stab = footage_speed(a)
        eff = r * baked
        if r > 1 and abs(r - round(r)) > 1e-6:
            findings.append(_finding("check", "fractional_speed", {"shot": sh["id"], "frames": [sh["start_frame"], sh["end_frame"]]}, {"playback_rate": r},
                                     "A non-integer speed-up shows source frames in an uneven 1-2-1-2 cadence (judder on pans and drone "
                                     "moves). Use an integer rate, or retime_footage (flow interpolation) and play the result at 1x."))
        if eff >= 4:
            # On-screen motion per output frame: the stabilized clip's displacement over `eff` source frames
            # (interpolated between measured windows, scaled linearly past the longest; older reports only have the
            # 1-frame step), times how much the shot enlarges the clip on the canvas (a 9:16 cover of 16:9 is 1.78x).
            # A report that could not measure (nothing trackable) is unmeasured, not still.
            over = {int(k): v for k, v in ((stab or {}).get("residual_px_over_frames") or {}).items()}
            if (stab or {}).get("residual_coverage", 1) < .5:
                moves = None
            elif over:
                ks = sorted(over)
                moves = float(np.interp(eff, ks, [over[k] for k in ks])) if eff <= ks[-1] else over[ks[-1]] * eff / ks[-1]
            else:
                p95 = ((stab or {}).get("residual_step_px") or {}).get("p95")
                moves = p95 * eff if p95 is not None else None
            dims = (stab or {}).get("dimensions") or [None]
            if moves is not None:
                moves *= (upscale_factor(sh, a, W, H) or 1.0) * ((a.get("width") or dims[0] or 1) / (dims[0] or a.get("width") or 1))
            ev = {"playback_rate": r, "retimed_speed": baked, "effective_speed": round(eff, 2), "stabilized": stab is not None}
            if stab is None:
                findings.append(_finding("check", "fast_forward", {"shot": sh["id"], "frames": [sh["start_frame"], sh["end_frame"]]}, ev,
                                         "A fast-forward multiplies camera shake by its effective speed. On handheld footage stabilize first "
                                         "(stabilize_footage mode lock), then retime with motion blur."))
            elif moves is None or moves > 2:
                findings.append(_finding("check", "fast_forward", {"shot": sh["id"], "frames": [sh["start_frame"], sh["end_frame"]]},
                                         {**ev, "on_screen_px_per_frame": round(moves, 1) if moves is not None else None},
                                         "The stabilized clip still moves more than ~2 px per output frame at this speed on screen (or it could "
                                         "not be measured): lock on a rigid, textured region, lower the speed, raise max_zoom, or choose a calmer "
                                         "window; check the shot at full size."))
    # Attention: a visual event (cut, transition or a graphic entering) every 3-8 s keeps explainers alive; >8 s of nothing
    # on a held shot sags, more than ~4 events in 3 s turns to mush.
    events = sorted({s["start_frame"] for s in shots[1:]} | {l["start_frame"] for l in layers if l["start_frame"] > 0 and l["kind"] not in ("film", "adjust", "pattern", "caption")}
                    | {l["end_frame"] for l in layers if l["kind"] == "video" and l.get("width", 0) * l.get("height", 0) > .5 and l["end_frame"] < N})  # a B-roll leaving is a cut
    bounds = [0, *events, N]
    vertical = H > W  # short-form profile: faster attention economy, platform UI over the frame
    gap_s = 4 if vertical else max(8, 2 * pace_hi)
    for a, b in zip(bounds, bounds[1:]):
        if b - a > gap_s * FPS:
            held = [s for s in shots if s["start_frame"] < b and s["end_frame"] > a and s.get("motion", "hold") == "hold" and not s.get("effects") and not s.get("keyframes")]
            if held:
                findings.append(_finding("check", "attention_gap", {"frames": [a, b]}, {"seconds": round((b - a) / FPS, 1), "threshold_s": gap_s},
                                         f"More than {gap_s} s with no cut, transition or entering graphic on a held shot. Fine for a deliberate breather; "
                                         "otherwise add a punch-in, a B-roll cut or a graphic beat."))
    # Hook (first 3 s): something to read or hear by 0.5 s, several visual events, a short hook line clear of platform UI.
    if N > 6 * FPS:
        texty = [l for l in layers if l["kind"] in ("text", "caption", "counter") and l["start_frame"] < 3 * FPS]
        cues = t.get("cues") or []
        if not any(l["start_frame"] <= 15 for l in texty) and not any(c.get("start", 9) <= .5 for c in cues):
            findings.append(_finding("check", "late_hook", {"frames": [0, 15]}, {},
                                     "Nothing to read or hear in the first 0.5 s. Open with the hook line (text or voice) on the first beat."))
        # A first change by 1 s (feed items get ~1.7 s of attention), not a quota of events: in an experiment faster
        # pacing LOWERED completion, and engagement peaks at a moderate shot count (platforms.EVIDENCE).
        opening = 1 + sum(1 for e in events if e < 3 * FPS)  # the first frame counts as one event
        # a change the viewer sees: an event, a full-frame B-roll leaving, or an animated caption page landing
        seen = list(events) + [l["end_frame"] for l in layers if l["kind"] == "video" and l.get("width", 0) * l.get("height", 0) > .5 and l["end_frame"] < N] + [
            l["start_frame"] + pg["start_frame"] for l in layers if l["kind"] == "caption" and (l.get("data") or {}).get("animation", "none") != "none"
            for pg in (l.get("data") or {}).get("pages") or []]
        first_change = min((e for e in seen if e > 0), default=None)
        body_rate = sum(1 for e in events if e >= 3 * FPS) / max(1e-6, (N - 3 * FPS) / FPS)
        if first_change is None or first_change > FPS:
            findings.append(_finding("check", "sparse_open", {"frames": [0, FPS]},
                                     {"first_change_s": round(first_change / FPS, 2) if first_change else None, "threshold_s": 1.0,
                                      "events_0_3s": opening, "evidence": platforms.EVIDENCE["first_change"]},
                                     "Nothing changes on screen in the first second (no cut, punch-in or entering graphic); make the first "
                                     "change by 1 s. More changes than that is not better."))
        elif body_rate > 0 and opening / 3 < 1.5 * body_rate:
            findings.append(_finding("info", "flat_hook_pace", {"frames": [0, 3 * FPS]}, {"open_events_per_s": round(opening / 3, 2), "body_events_per_s": round(body_rate, 2)},
                                     "The opening is no denser than the body; hooks often run ~1.5x the body's event rate (practice, not evidence)."))
        cuts = [s_["start_frame"] for s_ in shots[1:] if s_["start_frame"] >= 3 * FPS]
        rate = len(cuts) / max(1e-6, (N - 3 * FPS) / FPS)
        if vertical and rate > .6:
            findings.append(_finding("check", "fast_pace", {"frames": [3 * FPS, N]}, {"cuts_per_s": round(rate, 2), "band": [.19, .52], "evidence": platforms.EVIDENCE["cut_rate"]},
                                     "Faster than top short-form talking heads (0.19-0.52 cuts/s), and in an experiment faster pacing lowered "
                                     "completion. Let shots carry a point each; cut on meaning, not on a quota."))
        for l in texty:
            words = len(re.sub(r"[*=]", "", l.get("text") or "").split())
            if l["kind"] == "text" and words > 8 and l.get("typography_role") != "source":  # a source/credit line is not hook copy
                findings.append(_finding("check", "hook_text_long", {"layer": l["id"]}, {"words": words},
                                         "A hook line over 8 words is read, not glanced at; cut it to the question the viewer should have."))
            if vertical and l["kind"] == "text":
                ib = _ink_box(l, design, W, H)  # the glyph block, not a wide layer box around centred words
                box = (ib[0], ib[1], ib[0] + ib[2], ib[1] + ib[3])
                hit = {f"{p}:{z}": v for p in platforms.PLATFORMS for z, v in platforms.covered(box, p).items() if v > .05}
                if hit:
                    findings.append(_finding("check", "hook_text_in_ui_zone", {"layer": l["id"]}, {"box": [round(v, 3) for v in box], "covered_by": hit},
                                             "Short-form platforms cover the right action rail and the bottom caption block; place hook text "
                                             "around y .15-.30 (platforms.safe_area)."))
    # A label held across a cut lands on whatever the next shot shows (round 13: «B-52 RƠI» over a B-52 still bombing,
    # «MỸ DI TẢN» over a tank): keep a label inside its shot unless the shots share the subject (data.same_subject).
    cuts = sorted({s_["start_frame"] for s_ in shots[1:]})
    for l in layers:
        if l["kind"] != "text" or l.get("typography_role") != "label" or (l.get("data") or {}).get("same_subject"):
            continue
        inside = [c for c in cuts if l["start_frame"] + 6 < c < l["end_frame"] - 6]
        if inside:
            findings.append(_finding("check", "label_crosses_cut", {"layer": l["id"], "frames": [l["start_frame"], l["end_frame"]]},
                                     {"cuts": inside[:4], "text": (l.get("text") or "")[:60]},
                                     "This label stays on screen across a cut, so it captions the next picture too. End it with its shot, "
                                     "or mark data.same_subject when both shots show the same place or thing."))
    # A picture cut straight to black reads as a dropout, not a pause (round 13, the fifth cut: 16 hard cuts into black,
    # before chapter cards and inside set pieces; the owner: "đang xem thì giật thành đen"). Black is reached by a fade
    # (a dip_black transition with hold_frames), and a card or map that replaces footage comes in by a dissolve.
    def drawn(a, b):  # anything visible over [a, b) besides grain, bars and plates
        return any(l["start_frame"] < b and l["end_frame"] > a and l["kind"] in ("text", "image", "video", "svg", "graphic", "globe", "scene3d")
                   for l in layers)
    soft_in = ("dissolve", "dip_black", "blur_in")
    for i_, s_ in enumerate(shots[1:], 1):
        prev = shots[i_ - 1]
        if s_.get("asset_id") or not prev.get("asset_id") or (s_.get("transition") or {}).get("name") in soft_in:
            continue
        span = s_["end_frame"] - s_["start_frame"]
        faded_out = any(e.get("name") in ("fade_out", "fade_to_black") and e.get("end_frame", 0) >= prev["end_frame"] - prev["start_frame"] - 2
                        for e in prev.get("effects") or [])
        if faded_out:
            continue
        if not drawn(s_["start_frame"], s_["end_frame"]) and span >= 6:
            findings.append(_finding("check", "hard_black_cut", {"shot": s_["id"], "frames": [s_["start_frame"], s_["end_frame"]]},
                                     {"after": prev["id"], "seconds": round(span / FPS, 2)},
                                     "The picture cuts straight to black, which reads as a dropout. Fade into it: a dip_black transition "
                                     "on the next picture (hold_frames for the pause), or a fade_out on this shot."))
        elif drawn(s_["start_frame"], s_["end_frame"]) and span >= 2 * FPS:
            findings.append(_finding("check", "card_entry", {"shot": s_["id"], "frames": [s_["start_frame"], s_["end_frame"]]},
                                     {"after": prev["id"]},
                                     "A card or map replaces the footage on a hard cut, which feels abrupt. Bring it in with a dissolve "
                                     "of 18-30 frames and carry the sound across."))
    # Generated pictures say so: a documentary may mix AI or 3D imagery with archive (round 13: the owner's CCTV reference
    # does it well), but a generated shot shown without a label reads as evidence (the second cut's CGI B-52 battle did).
    # A shot whose asset came from a generation task, or is marked reconstruction, needs a visible label naming it.
    marker = re.compile(r"(?i)\b(ai|minh họa|minh hoạ|illustration|reconstruction|dựng lại|tái hiện|mô phỏng|generated|cgi)\b")
    for s_ in shots:
        a_ = asset(s_.get("asset_id")) or {}
        made = bool((a_.get("provenance") or {}).get("media_task_id")) or a_.get("role") == "reconstruction" or "generated" in str(a_.get("tags") or "").lower()
        if not made or s_["end_frame"] - s_["start_frame"] < 12:
            continue
        labelled = any(l["kind"] == "text" and l["start_frame"] < s_["end_frame"] - 6 and l["end_frame"] > s_["start_frame"] + 6
                       and marker.search(l.get("text") or "") for l in layers)
        if not labelled:
            findings.append(_finding("check", "generated_unlabeled", {"shot": s_["id"], "frames": [s_["start_frame"], s_["end_frame"]]},
                                     {"asset": a_.get("id"), "role": a_.get("role"), "operation": (a_.get("provenance") or {}).get("operation")},
                                     "A generated or reconstructed picture is shown without saying so. Put a small label on it "
                                     "(\"Minh họa AI\", \"AI illustration\", \"Dựng lại\") for as long as it is on screen."))
    # Frozen pictures: a held frame is a deliberate accent (round 13, the fifth cut: 39 freezes, 74.5 s, stretched short
    # clips the owner read as "lạm dụng hiệu ứng đứng hình"). A short clip makes a shorter shot, or another window.
    frozen = [s_ for s_ in shots if s_.get("freeze") and (asset(s_.get("asset_id")) or {}).get("kind") == "video"]
    if frozen:
        secs = sum(s_["end_frame"] - s_["start_frame"] for s_ in frozen) / FPS
        allowed = max(2, round(N / FPS / 300))  # about one per five minutes
        if len(frozen) > allowed or secs > max(4.0, .015 * N / FPS):
            findings.append(_finding("check", "freeze_overuse", {"shots": [s_["id"] for s_ in frozen][:24]},
                                     {"freezes": len(frozen), "seconds": round(secs, 1), "allowed": allowed},
                                     "Too many frozen video frames: viewers read them as the film stalling. Keep a freeze for one "
                                     "chosen moment; give short clips shorter shots or find a longer window."))
    # Flash shots: what the viewer sees between two visible cuts (shot changes and full-frame video layers coming in
    # or out) for under 0.3 s reads as a glitch, not a cut (a punch 6 frames after a B-roll ended).
    vis = sorted({s_["start_frame"] for s_ in shots[1:]} | {v for l in layers if l["kind"] == "video" and l.get("width", 0) * l.get("height", 0) > .5
                                                            for v in (l["start_frame"], l["end_frame"]) if 0 < v < N})
    for a_, b_ in zip(vis, vis[1:]):
        if b_ - a_ < 9:
            findings.append(_finding("check", "flash_shot", {"frames": [a_, b_]}, {"frames_visible": b_ - a_, "threshold_frames": 9},
                                     "A picture on screen for under 0.3 s between two cuts reads as a glitch: move one cut or merge."))
    # Short shots outside set pieces: a documentary alternates dense bursts (a battle, cut on the music) with long holds;
    # an even 4 s rhythm everywhere reads as relentless. A burst is a run of short shots touching a hit, <= 45 s.
    if pace.get("min_shot_s"):
        lo = float(pace["min_shot_s"])
        foot = [s_ for s_ in shots if (asset(s_.get("asset_id")) or {}).get("kind") == "video"]
        hit_ids = {s_["id"] for s_ in shots if any(e.get("name") == "white_flash" for e in s_.get("effects") or [])}
        short = [s_ for s_ in foot if (s_["end_frame"] - s_["start_frame"]) / FPS < lo]
        runs, run = [], []
        for s_ in shots:
            if s_ in short or s_["id"] in hit_ids:
                run.append(s_)
            elif run:
                runs.append(run); run = []
        runs += [run] if run else []
        burst = {x["id"] for r_ in runs if any(x["id"] in hit_ids for x in r_) and (r_[-1]["end_frame"] - r_[0]["start_frame"]) <= 45 * FPS for x in r_}
        rest = [s_ for s_ in short if s_["id"] not in burst]
        share = len(rest) / max(1, len(foot))
        if share > float(pace.get("short_share_max", .1)):
            findings.append(_finding("check", "short_shots", {"shots": [s_["id"] for s_ in rest][:24]},
                                     {"share": round(share, 3), "limit": pace.get("short_share_max", .1), "min_shot_s": lo, "shots": len(rest), "footage_shots": len(foot)},
                                     f"More than {int(100 * float(pace.get('short_share_max', .1)))} % of footage shots outside set pieces are shorter than {lo} s: "
                                     "fewer, longer shots carry the narration (one held image per idea); keep fast cutting for bursts of <= 45 s "
                                     "around an event, bracketed by a map before and a held aftermath after."))
    dense = [f for f in events if sum(1 for g in events if f <= g < f + 3 * FPS) > 4]
    if dense:
        findings.append(_finding("check", "event_overload", {"frames": [dense[0], dense[0] + 3 * FPS]}, {"events_in_3s": max(sum(1 for g in events if f <= g < f + 3 * FPS) for f in dense)},
                                 "More than four visual events inside 3 s: the eye cannot settle. Stagger or drop some entrances."))
    used = [n for n in names if n]
    if len(set(used)) > 3:
        findings.append(_finding("check", "transition_variety", {}, {"distinct": sorted(set(used)), "count": len(set(used))},
                                 "Pick one primary transition for most seams with one or two accents for pivots; a different transition at every "
                                 "seam reads as a showreel of presets."))
    direction = design.get("direction") or {}
    if direction:
        vocab = {direction["transitions"]["primary"], *direction["transitions"]["accents"]} - {"cut"}
        off = sorted({n for n in used if n not in vocab})
        if off:
            findings.append(_finding("info", "off_direction_transitions", {}, {"direction": direction["id"], "used": off, "vocabulary": sorted(vocab)},
                                     "Transitions outside the chosen direction's vocabulary; keep them only where they are motivated."))
        lo_s, hi_s = direction["pacing"]["seconds_per_idea"]
        lens = sorted((sh["end_frame"] - sh["start_frame"]) / FPS for sh in shots)
        med = lens[len(lens) // 2]
        if med < lo_s * .75 or med > hi_s * 1.25:
            findings.append(_finding("check", "pacing_vs_direction", {}, {"median_shot_s": round(med, 2), "direction_range_s": [lo_s, hi_s], "direction": direction["id"]},
                                     "Median shot length is outside the direction's pacing; correct animation at the wrong tempo still reads wrong."))
        curve = direction["motion"]["ease"]
        mixed = sum(1 for l in layers for e in l.get("effects", []) if e["name"] in ENTR and e.get("easing", "smooth") != curve and not e.get("bezier"))
        if mixed:
            findings.append(_finding("info", "mixed_motion_language", {}, {"entrances_off_curve": mixed, "direction_curve": curve},
                                     "Entrances use other curves than the direction's motion language; apply_direction(restyle=true) unifies them."))
    films = [l for l in layers if l["kind"] == "film" and (l.get("data") or {}).get("type") == "light_leak"]
    leak = sum(l["end_frame"] - l["start_frame"] for l in films) / max(1, N)
    if leak > .35:
        findings.append(_finding("check", "light_leak_coverage", {"layers": [l["id"] for l in films]}, {"fraction_of_runtime": round(leak, 2)},
                                 "Light leaks over a third of the runtime wash out source colour; keep them on motivated transitions."))
    order = {"likely_problem": 0, "check": 1, "info": 2}
    findings.sort(key=lambda f: order[f["level"]])
    return {"project_id": pid, "revision": p["revision"], "canvas": [W, H, N], "inventory": inv, "shots": shot_rows, "scenes3d": scene_rows,
            "findings": findings,
            "how_to_use": "Findings are measurements with thresholds, not a verdict. Decide from intent; fix with patch_timeline/recipes, then "
                          "verify the exact frames named here with review_frames/snapshot_code and the render with motion_audit."}


# ---------------------------------------------------------------- isolated-layer frame review
def _load(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def _lin(c):
    c = c / 255.0
    return np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


def luminance(rgb):
    l = _lin(rgb)
    return .2126 * l[..., 0] + .7152 * l[..., 1] + .0722 * l[..., 2]


def measure_text(full, plate, solo, diff_threshold=18, glyph_threshold=60):
    """Glyph-level measurements for one text layer from three renders of the same frame:
    full (everything), plate (all text layers removed) and solo (only this text, white on black)."""
    glyph = solo.max(axis=2) > glyph_threshold
    area = int(glyph.sum())
    if area == 0:
        return {"glyph_pixels": 0}
    visible = glyph & (np.abs(full - plate).max(axis=2) > diff_threshold)
    ys, xs = np.nonzero(glyph)
    h, w = glyph.shape
    bg = luminance(plate[glyph])
    core = visible
    text_rgb = np.median(full[core], axis=0) if core.any() else np.median(full[glyph], axis=0)
    # A glyph pixel that did not change the image is either covered by something above it, or the text colour equals
    # the plate there (white on a white wall). Separate the two: only pixels where the text colour differs from the plate
    # could have been seen, so only those count as covered.
    distinct = np.abs(plate - text_rgb).max(axis=2) > 2 * diff_threshold
    covered = glyph & ~visible & distinct
    indistinct = glyph & ~visible & ~distinct
    lt = float(luminance(text_rgb[None])[0])
    hi, lo = np.maximum(lt, bg), np.minimum(lt, bg)
    ratio = (hi + .05) / (lo + .05)
    return {"glyph_pixels": area, "visible_fraction": round(float(visible.sum()) / area, 3),
            "covered_fraction": round(float(covered.sum()) / area, 3), "same_as_background_fraction": round(float(indistinct.sum()) / area, 3),
            "bbox": [round(float(xs.min()) / w, 4), round(float(ys.min()) / h, 4), round(float(xs.max() + 1) / w, 4), round(float(ys.max() + 1) / h, 4)],
            "text_rgb": [int(v) for v in text_rgb], "background_luminance_p10_p50_p90": [round(float(np.percentile(bg, q)), 3) for q in (10, 50, 90)],
            "contrast_median": round(float(np.median(ratio)), 2), "contrast_p10": round(float(np.percentile(ratio, 10)), 2),
            "low_contrast_fraction": round(float((ratio < 3).mean()), 3), "_glyph": glyph, "_visible": visible, "_covered": covered, "_ratio": ratio}


def _overlay(full, results, out):
    from PIL import Image
    img = full * .45
    for r in results:
        g, v = r.pop("_glyph", None), r.pop("_visible", None)
        ratio, occluded = r.pop("_ratio", None), r.pop("_covered", None)
        if g is None:
            continue
        img[v] = img[v] * .3 + np.array([90, 220, 255]) * .7
        img[occluded] = np.array([255, 60, 60])
        low = np.zeros_like(g)
        low[g] = ratio < 3
        img[low & v] = np.array([255, 210, 0])
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    im.thumbnail((960, 960))
    im.save(out)
    return str(out)


def review_frames(pid, frames, layer_ids=None):
    """Render each frame three ways (full / without text / one text layer alone) and measure, per text layer:
    rendered glyph box, how much of it is visible (occlusion by subjects, shapes, other layers), and contrast
    against what is actually behind the glyphs. Returns an overlay per frame: cyan = visible glyphs, red =
    covered glyphs, yellow = glyph pixels under 3:1 contrast. Glyph pixels that match the background colour are neither
    visible nor covered (same_as_background_fraction)."""
    from .snapshot import snapshot
    import copy
    if not frames or len(frames) > 4:
        raise ValueError("review_frames takes 1..4 frames")
    p = agent.read(pid)
    t = p["timeline"]
    W, H = t["width"], t["height"]
    vertical = H > W
    texts = [l for l in t["layers"] if l["kind"] == "text" and l.get("text", "").strip()]
    active = {f: [l for l in texts if l["start_frame"] <= f < l["end_frame"] and (not layer_ids or l["id"] in layer_ids)] for f in frames}
    ids = sorted({l["id"] for ls in active.values() for l in ls})
    if len(ids) > 6:
        raise ValueError(f"{len(ids)} text layers active; pass layer_ids (max 6) to choose what to measure")
    full = {r["frame"]: r["path"] for r in snapshot(pid, "remotion", frames)["frames"]}
    plate_t = copy.deepcopy(t)
    plate_t["layers"] = [l for l in plate_t["layers"] if l["kind"] != "text"]
    plate = {r["frame"]: r["path"] for r in snapshot(pid, "remotion", frames, plate_t)["frames"]}
    solo = {}
    for lid in ids:
        fs = [f for f in frames if any(l["id"] == lid for l in active[f])]
        v = copy.deepcopy(t)
        v["design"] = {**(v.get("design") or {}), "background": "#000000"}
        v["layers"] = [{**l, "color": "#ffffff", "color_role": None, "background": "transparent", "background_role": None,
                        "effects": [e for e in l.get("effects", []) if e["name"] not in ("shadow", "glow", "text_outline")]}
                       for l in v["layers"] if l["id"] == lid]
        for s in v["shots"]:
            s.update(asset_id=None, effects=[])
        for r in snapshot(pid, "remotion", fs, v)["frames"]:
            solo[(lid, r["frame"])] = r["path"]
    safe = SAFE["vertical" if vertical else "landscape"]
    out, work = [], store.DATA / "observations"
    for f in frames:
        F, Pl = _load(full[f]), _load(plate[f])
        rows = []
        for l in active[f]:
            m = measure_text(F, Pl, _load(solo[(l["id"], f)]))
            m["layer"] = l["id"]
            m["text"] = l["text"][:60]
            notes = []
            if m.get("glyph_pixels"):
                if m["same_as_background_fraction"] > .1:
                    notes.append(f"{round(m['same_as_background_fraction'] * 100)}% of the glyphs have the same colour as what is behind them (invisible without outline/shadow)")
                if m["covered_fraction"] > .15:
                    notes.append(f"{round(m['covered_fraction'] * 100)}% of the glyphs are covered by something drawn above them"
                                 + (" (intended for text-behind-subject; keep the word readable: aim ≥60% visible)" if l.get("z", 10) < max((x.get("z", 10) for x in t["layers"] if x["kind"] == "video" and x.get("attach_shot") == l.get("attach_shot")), default=-1) else ""))
                if m["contrast_p10"] < 3:
                    notes.append(f"10% of glyph pixels sit on backgrounds under {m['contrast_p10']}:1 contrast; add shadow/scrim, change colour or move")
                b = m["bbox"]
                if b[0] < safe[0] or b[1] < safe[1] or b[2] > safe[2] or b[3] > safe[3]:
                    notes.append(f"rendered glyph box {b} leaves the platform safe region {safe} (heuristic)")
            m["notes"] = notes
            rows.append(m)
        path = _overlay(F, rows, Path(full[f]).with_name(f"review-{f:06}.png"))
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if a.get("bbox") and b.get("bbox"):
                    A = [a["bbox"][0], a["bbox"][1], a["bbox"][2] - a["bbox"][0], a["bbox"][3] - a["bbox"][1]]
                    B = [b["bbox"][0], b["bbox"][1], b["bbox"][2] - b["bbox"][0], b["bbox"][3] - b["bbox"][1]]
                    if _overlap(A, B) > .02:
                        a["notes"].append(f"glyph box overlaps {b['layer']}")
        out.append({"frame": f, "timestamp": f / FPS, "overlay": path, "full": full[f], "texts": rows})
    return {"project_id": pid, "revision": p["revision"], "frames": out,
            "method": "Three remotion renders per frame: full, text layers removed, and each text alone (white on black, no shadow). "
                      "visible_fraction = glyph pixels that change the final image; contrast = WCAG ratio of the rendered text colour "
                      "against the plate under each glyph pixel. Shadows/outlines raise real legibility beyond the plate contrast."}


# ---------------------------------------------------------------- motion signals from an encoded video
def flow_speed(frames, reference_width=1920):
    """Physical motion per frame: Farneback optical flow magnitude averaged over textured pixels (gradient > 6), scaled to a
    1920-px-wide reference. Unlike luminance change it ignores grain/noise and is not biased by dark or flat frames."""
    import cv2
    f8 = np.clip(np.asarray(frames, np.float32), 0, 255).astype(np.uint8)
    w = f8.shape[2]
    out = [0.0]
    for a, b in zip(f8[:-1], f8[1:]):
        fl = cv2.calcOpticalFlowFarneback(a, b, None, .5, 2, 13, 2, 5, 1.1, 0)
        gx, gy = cv2.Sobel(a, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(a, cv2.CV_32F, 0, 1, ksize=3)
        tex = np.hypot(gx, gy) > 6 * 4  # Sobel scale ~4x
        mag = np.hypot(fl[..., 0], fl[..., 1])
        out.append(float(mag[tex].mean()) if tex.sum() > 20 else 0.0)
    return np.array(out[1:]) * reference_width / w


def analyze_signal(frames):
    """frames: (N, h, w) grayscale float array at 30 fps. Returns per-frame difference/luminance and defects."""
    frames = np.asarray(frames, np.float32)
    diff = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    lum = frames.mean(axis=(1, 2))
    speed = flow_speed(frames)  # px/frame at 1920-px reference, robust to grain and darkness
    n = len(diff)
    still = (diff < .25) & (speed < .3)  # a slow push over a dark frame barely changes brightness but still moves
    static = []
    i = 0
    while i < n:
        if still[i]:
            j = i
            while j + 1 < n and still[j + 1]:
                j += 1
            if j - i + 1 >= 15:
                static.append([i + 1, j + 1])
            i = j + 1
        else:
            i += 1
    # Holds separated by under 10 frames of change (a blink of motion, a flicker, a small pop) are one held picture:
    # merge them so a 13 s still does not report as four short-looking fragments. Only runs >= 15 frames merge, so
    # animation on twos (alternate still frames) never reads as a hold.
    merged_static = []
    for a, b in static:
        if merged_static and a - merged_static[-1][1] <= 10:
            merged_static[-1][1] = b
        else:
            merged_static.append([a, b])
    static = merged_static
    dup = [i + 1 for i in range(1, n - 1) if diff[i] < .12 * min(diff[i - 1], diff[i + 1]) and min(diff[i - 1], diff[i + 1]) > 1.0]
    # Periodicity is judged on the high-passed signal: a smooth acceleration (rising diff) must not read as a cycle. It
    # runs on brightness change and on flow speed: a dark animation on black barely changes brightness (a 2.5x retime of
    # a render on black juddered 4.3/6.2 px a frame unseen by the brightness series alone).
    k = 9
    periodic = []
    for series, floor in ((diff, .6), (np.asarray(speed, float), .8)):
        pad = np.pad(series, (k // 2, k // 2), mode="edge")
        hp = series - np.convolve(pad, np.ones(k) / k, mode="valid")
        for a in range(0, max(1, n - 45), 15):
            w, x = series[a:a + 45], hp[a:a + 45]
            if len(w) < 30 or w.mean() < floor:
                continue
            x = x - x.mean()
            den = float((x * x).sum())
            if den <= 1e-9 or x.std() / w.mean() < .08:
                continue
            ac = {lag: float((x[:-lag] * x[lag:]).sum()) / den for lag in range(2, 7)}
            lag, val = max(ac.items(), key=lambda kv: kv[1])
            if val > .5 and not any(p["frames"][0] == a + 1 and p["period_frames"] == lag for p in periodic):
                periodic.append({"frames": [a + 1, a + len(w)], "period_frames": lag, "autocorrelation": round(val, 2),
                                 "relative_amplitude": round(float(x.std() / w.mean()), 3)})
    periodic.sort(key=lambda p: (p["period_frames"], p["frames"][0]))
    merged = []
    for p in periodic:  # overlapping windows with the same period become one span
        if merged and p["period_frames"] == merged[-1]["period_frames"] and p["frames"][0] <= merged[-1]["frames"][1]:
            merged[-1]["frames"][1] = p["frames"][1]
            merged[-1]["autocorrelation"] = max(merged[-1]["autocorrelation"], p["autocorrelation"])
        else:
            merged.append(p)
    periodic = merged
    flashes = [i + 1 for i in range(n) if lum[i + 1] - lum[i] > 35]
    return {"diff": diff, "speed": speed, "lum": lum, "static_spans": static, "duplicate_frames": dup, "periodic": periodic, "flash_frames": flashes}


def _letterbox(path, shots, start=0.0, end=None, width=320, fps=2):
    """Bars baked into a source, per shot: leading/trailing rows that stay digital black (max <= 6 of 255) in every sampled
    frame, 0.8-15 % of the height, with picture in the rows right inside them. Unblurred 320-px frames: the bars of a
    letterboxed 16:9 plate are ~2 % of the height, below what the blurred motion frames can resolve. A title on black
    (black far beyond 15 %) or dark sky with noise is not a bar."""
    probe_ = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
                            capture_output=True, text=True, check=True).stdout.strip().split(",")
    h = int(round(width * int(probe_[1]) / int(probe_[0]) / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), *(["-t", str(end - start)] if end else []), "-i", str(path),
                          "-vf", f"fps={fps},scale={width}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    g = np.frombuffer(raw, np.uint8).reshape(-1, h, width)
    out = []
    for sh in shots:
        a = int(np.ceil((sh["start_frame"] / FPS - start) * fps))
        b = int((sh["end_frame"] / FPS - start) * fps)
        seg = g[max(0, a):min(len(g), b)]
        if len(seg) < 2:
            continue
        row_max = seg.max(axis=(0, 2))
        row_mean = seg.mean(axis=(0, 2))

        def bar(rows_max, rows_mean):
            n = 0
            while n < len(rows_max) and rows_max[n] <= 6:
                n += 1
            ok = .008 * h <= n <= .15 * h and n + 2 < len(rows_mean) and rows_mean[n + 1:n + 3].mean() > 8
            return n if ok else 0
        top, bot = bar(row_max, row_mean), bar(row_max[::-1], row_mean[::-1])
        if top or bot:
            k = int(probe_[1]) / h
            out.append({"shot": sh["id"], "frames": [sh["start_frame"], sh["end_frame"]], "top_px": round(top * k), "bottom_px": round(bot * k)})
    return out


def shake_profile(path, shots, start=0.0, end=None, width=320):
    """Camera unsteadiness per shot, read from the pixels: the global translation between frames (robust sparse LK with a
    RANSAC similarity that must cover most of the frame, so a moving subject is not taken for the camera), high-passed (minus its 0.4 s moving average, so pans and pushes do not count) and reported as the 2.5-97.5 percentile
    peak-to-peak in % of the picture height. Viewers notice > 0.2 % on still scenes and > 0.3 % on moving ones (SMPTE 1973)."""
    from .motion import _camera
    path = str(path)
    vw, vh = (int(v) for v in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                              "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.strip().split(",")[:2])
    h = int(round(width * vh / vw / 2) * 2)
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), *(["-t", str(end - start)] if end else []), "-i", path,
           "-vf", f"fps={FPS},scale={width}:{h},format=gray", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    prev, dx, dy, ok = None, [], [], []
    try:
        while True:
            buf = proc.stdout.read(width * h)
            if len(buf) < width * h:
                break
            cur = np.frombuffer(buf, np.uint8).reshape(h, width)
            if prev is not None:
                # a cut inside the shot (archive clips often hold one) is not camera motion
                cut = float(np.abs(cur[::4, ::4].astype(np.int16) - prev[::4, ::4]).mean()) > 28
                m = None if cut else _camera(prev, cur)[0]
                dx.append(float(m[0, 2]) if m is not None else 0.0); dy.append(float(m[1, 2]) if m is not None else 0.0); ok.append(m is not None)
            prev = cur
    finally:
        proc.stdout.close(); proc.wait()
    dx, dy, ok = np.array(dx), np.array(dy), np.array(ok, bool)
    off = int(round(start * FPS))
    rows = []
    for s in shots:
        tr = (s.get("transition") or {}).get("duration_frames", 0) if s.get("transition") else 0
        a, b = s["start_frame"] - off + 3 + tr, s["end_frame"] - off - 4  # skip cuts and transitions
        if b - a < 20 or a < 0 or b > len(dx):
            continue
        sel = ok[a:b]
        if sel.mean() < .6:  # the camera cannot be told apart from the subject (or no texture): no reading
            continue
        px, py = np.cumsum(np.where(sel, dx[a:b], 0)), np.cumsum(np.where(sel, dy[a:b], 0))
        k = np.ones(12) / 12
        hp = lambda v: (v - np.convolve(np.pad(v, 6, mode="edge"), k, mode="same")[6:-6])[6:-6]
        pp = lambda v: float(np.percentile(v, 97.5) - np.percentile(v, 2.5)) if len(v) > 8 else 0.0
        rows.append({"shot": s["id"], "frames": [s["start_frame"], s["end_frame"]],
                     "shake_pp_percent": round(max(pp(hp(px)) / width, pp(hp(py)) / h) * 100, 3)})  # x in % of the width, y of the height
    return rows


def motion_audit(path, start=0.0, end=None, project_id=None, width=96, full=False):
    """Read the encoded video (not the plan) and report what a viewer feels as motion: static spans, duplicated
    frames, periodic step patterns (judder, 24→30 cadence), sudden brightness jumps and per-shot motion energy."""
    path = str(path)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                            "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.strip().split(",")
    vw, vh = int(probe[0]), int(probe[1])
    h = int(round(width * vh / vw / 2) * 2)
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), *(["-t", str(end - start)] if end else []), "-i", path,
           "-vf", f"fps={FPS},scale={width}:{h},gblur=sigma=1.5,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h, width)
    if len(frames) < 3:
        raise ValueError("Too few frames decoded")
    sig = analyze_signal(frames)
    off = int(round(start * FPS))
    sec = lambda f: round((f + off) / FPS, 2)
    findings = []
    for a, b in sig["static_spans"]:
        findings.append(_finding("check", "static_span", {"frames": [a + off, b + off], "seconds": [sec(a), sec(b)]}, {"frames_still": b - a + 1},
                                 "Picture does not change here. Fine for a deliberate read/hold; otherwise add a motivated motion or cut."))
    n_all = len(sig["diff"])
    if sig["static_spans"] and sig["static_spans"][-1][1] >= n_all - 15 and sig["static_spans"][-1][1] - sig["static_spans"][-1][0] >= 90:
        a, b = sig["static_spans"][-1]
        lum = sig["lum"]
        if lum[-1] > .25 * float(np.mean(lum[a:b])) and lum[-1] > 8:  # not resolved to black
            findings.append(_finding("likely_problem", "static_ending", {"frames": [a + off, b + off]}, {"held_s": round((b - a + 1) / FPS, 2), "final_luma": round(float(lum[-1]), 1)},
                                     "The film ends on a frozen picture that never resolves (no fade, no move). Cap the end card at its reading "
                                     "time (~3-4 s), add a slow push, and fade picture and layers to black over >= 15 frames."))
    if sig["duplicate_frames"]:
        findings.append(_finding("likely_problem", "duplicate_frames", {"frames": [f + off for f in sig["duplicate_frames"][:30]]}, {"count": len(sig["duplicate_frames"])},
                                 "A frame repeats inside continuous motion (stutter). Common causes: 24/25p source in a 30p timeline, "
                                 "retime without interpolation, or a renderer frame miss. Retime with interpolation='flow' or conform the source."))
    for p in sig["periodic"]:
        findings.append(_finding("likely_problem", "periodic_judder", {"frames": [p["frames"][0] + off, p["frames"][1] + off]},
                                 {"period_frames": p["period_frames"], "autocorrelation": p["autocorrelation"]},
                                 "Motion steps repeat every few frames instead of flowing (eased dense keys, cadence conversion). "
                                 "For 3D cameras use camera_ease='linear' with pre-eased keys; for footage conform frame rate."))
    for f in sig["flash_frames"][:20]:
        findings.append(_finding("info", "brightness_jump", {"frame": f + off, "second": sec(f)}, {}, "Large one-frame brightness rise (flash transition or cut to a bright shot)."))
    shots = []
    if project_id:
        t = agent.read(project_id)["timeline"]
        d = sig["diff"]
        for s in picture_shots(t):
            a, b = max(s["start_frame"] - off, 1), min(s["end_frame"] - off, len(d))
            if b - a < 3:
                continue
            seg = d[a - 1:b - 1]
            spd = sig["speed"][a - 1:b - 1]
            shots.append({"shot": s["id"], "frames": [s["start_frame"], s["end_frame"]], "motion_energy": round(float(seg.mean()), 2),
                          "speed": round(float(spd.mean()), 3), "still_fraction": round(float(((seg < .25) & (spd < .3)).mean()), 2)})
        kinds = {a["id"]: a.get("kind") for a in store.assets(project_id)}
        try:  # footage only: an impact_shake on a title card is a graphic choice, not a shaking camera
            shake = shake_profile(path, [s for s in picture_shots(t) if kinds.get(s.get("asset_id")) == "video"], start, end)
        except (ImportError, OSError, ValueError, subprocess.SubprocessError):
            shake = []
        by_shot = {r["shot"]: r for r in shots}
        for r in shake:
            if r["shot"] in by_shot:
                by_shot[r["shot"]]["shake_pp_percent"] = r["shake_pp_percent"]
            if r["shake_pp_percent"] > .3:
                findings.append(_finding("check", "shaky_shot", {"shot": r["shot"], "frames": r["frames"]}, {"shake_pp_percent": r["shake_pp_percent"]},
                                         "The picture shakes more than viewers accept (> 0.3 % of the height peak to peak, SMPTE). Remove "
                                         "added shake effects (impact_shake, handheld, gate_weave) or stabilize the source (stabilize_footage)."))
        for row in _letterbox(path, picture_shots(t), start, end):
            findings.append(_finding("check", "black_bands", {"shot": row["shot"], "frames": row["frames"]}, {k: row[k] for k in ("top_px", "bottom_px")},
                                     "Digital-black bars at the frame edge through the whole shot while picture reaches the rows "
                                     "next to them: letterboxing baked into the source. Crop it (focus_zoom cut / cover the active "
                                     "picture) unless the letterbox is intended."))
        for r in shots:
            if r["still_fraction"] > .8 and r["frames"][1] - r["frames"][0] > 90:
                findings.append(_finding("likely_problem", "still_shot", {"shot": r["shot"], "frames": r["frames"]}, {"still_fraction": r["still_fraction"]},
                                         "Over 80% of this shot is a still picture for more than 3 s: a slideshow beat. Add a motivated move "
                                         "(push, drift, parallax, a tracked element) or cut it shorter."))
        # A hold while text is being read is a reading hold, not missing motion: re-label static spans and still shots
        # that last no longer than the reading time of the words on screen (0.6 s + 3 words/s, x1.6 headroom).
        def reading(a, b):
            words = 0
            for l in t.get("layers") or []:
                if l["kind"] in ("text", "caption", "counter", "callout") and l["start_frame"] < b and l["end_frame"] > a and l.get("opacity", 1) > .1:
                    words += len(str(l.get("text", "")).replace("**", "").replace("==", "").split()) or (2 if l["kind"] == "counter" else 0)
            return words, .6 + words / 3.0
        for fd in findings:
            if fd["code"] in ("static_span", "still_shot"):
                a, b = fd["where"]["frames"]
                lum_span = sig["lum"][max(0, a - off):max(1, b - off)]
                if len(lum_span) and float(np.mean(lum_span)) < 6:  # black: a dip, pause or the end, not a frozen picture
                    fd.update(level="info", code="black_hold", suggestion="Black hold (a dip, beat of silence or the end).")
                    continue
                words, need = reading(a, b)
                if words >= 2 and (b - a) / FPS <= max(2.5, need * 1.6):
                    fd.update(level="info", code="reading_hold")
                    fd["evidence"] = {**fd.get("evidence", {}), "words_on_screen": words, "reading_s": round(need, 1), "held_s": round((b - a) / FPS, 1)}
                    fd["suggestion"] = "A hold while the viewer reads the text on screen; fine at this length. Longer holds want a slow move."
        speeds = [r["speed"] for r in shots]
        if speeds:
            med = sorted(speeds)[len(speeds) // 2]
            for r in shots:
                if r["speed"] < .35 * med and (r["frames"][1] - r["frames"][0]) > 90:
                    findings.append(_finding("check", "calm_shot", {"shot": r["shot"], "frames": r["frames"]}, {"speed": r["speed"], "median_speed": med},
                                             "Much calmer than the rest of the film for over 3 s; intended pause, or trim/enrich it."))
            if len(speeds) >= 5 and float(np.std(speeds)) < .2 * float(np.mean(speeds)):
                findings.append(_finding("check", "uniform_energy", {}, {"speed_cv": round(float(np.std(speeds) / (np.mean(speeds) + 1e-9)), 3)},
                                         "Every shot moves at about the same rate: the film reads as a slideshow. Give hero beats more motion and one breather less."))
    d = sig["diff"]
    step = max(1, len(d) // 120)
    still_total = sum(b - a + 1 for a, b in sig["static_spans"])
    return {"path": path, "start": start, "frames": int(len(frames)), "static_total_s": round(still_total / FPS, 2),
            "static_share": round(still_total / max(1, len(sig["diff"])), 3), "findings": findings, "shots": shots,
            "diff_series": {"every_frames": step, "values": [round(float(v), 2) for v in d[::step]]},
            "speed_series": {"every_frames": step, "values": [round(float(v), 4) for v in sig["speed"][::step]]},
            **({"speed_full": [round(float(v), 4) for v in sig["speed"]]} if full else {}),
            "method": f"Mean absolute luminance difference between consecutive frames, plus speed = optical-flow magnitude over textured "
                      f"pixels in px/frame at a 1920-px reference; frames downscaled to {width}px and blurred (sigma 1.5) so film "
                      "grain/encoder noise do not count as motion; periodicity is measured after removing a 9-frame moving average. "
                      "Thresholds are stated per finding."}


# ---------------------------------------------------------------- editing craft: eye trace, cutting on action, rhythm
def picture_shots(t):
    """The cut structure of a timeline: its shots, or, when a recipe builds the picture from full-frame video layers on one
    carrier shot (archive_montage), those layers in time order with their asset. cut_audit read only shots and reported a
    48-cut montage as one 70 s shot with no findings."""
    shots = t.get("shots") or []
    if len(shots) > 1:
        return shots
    full = sorted((l for l in t.get("layers") or [] if l.get("kind") == "video" and l.get("asset_id") and float(l.get("x", .1)) <= .02
                   and float(l.get("y", .1)) <= .02 and float(l.get("width", .8)) >= .96 and float(l.get("height", .3)) >= .96),
                  key=lambda l: (l["start_frame"], -l["end_frame"]))
    out = []
    for l in full:
        if out and l["start_frame"] < out[-1]["start_frame"] + 2:
            continue  # a copy stacked on the same cut (a projected-frame double, a grade layer)
        out.append({"id": l["id"], "start_frame": l["start_frame"], "end_frame": l["end_frame"], "asset_id": l["asset_id"], "transition": None})
    return out if len(out) > 1 else shots


def cut_audit(path, project_id, start=0.0, width=160):
    """Evidence for the editing criteria editors use to judge a cut (Murch's eye trace and rhythm; cutting on action):
    per cut, the focal point of the last outgoing and first settled incoming frame (saliency + motion), the jump between
    them, motion around the cut, and shot-length rhythm. Returns a contact sheet of cut pairs with focal markers."""
    from .footage_pro import focus_of
    from PIL import Image, ImageDraw
    t = agent.read(project_id)["timeline"]
    W, H = t["width"], t["height"]
    probe_ = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
                            capture_output=True, text=True, check=True).stdout.strip().split(",")
    vw, vh = int(probe_[0]), int(probe_[1])
    h = int(round(width * vh / vw / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-i", str(path), "-vf", f"fps={FPS},scale={width}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    rgb = np.frombuffer(raw, np.uint8).reshape(-1, h, width, 3)
    gray = (rgb.astype(np.float32) @ np.array([.299, .587, .114], np.float32)).astype(np.uint8)
    n = len(gray)
    off = int(round(start * FPS))
    import cv2
    low = np.stack([cv2.GaussianBlur(cv2.resize(g, (96, max(2, int(96 * h / width)))), (0, 0), 1.5) for g in gray]).astype(np.float32)
    diff = np.abs(np.diff(low, axis=0)).mean(axis=(1, 2))  # low-passed: grain and encoder noise are not motion
    mot = lambda a, b: float(diff[max(0, a):max(0, min(n - 1, b))].mean()) if b > a and a < n - 1 else 0.0

    def flow(a, b):
        """Mean optical-flow vector (px/frame at the 96 px analysis width) over textured pixels between frames a..b."""
        vs = []
        for k in range(max(1, a), min(n - 1, b)):
            f = cv2.calcOpticalFlowFarneback(low[k - 1].astype(np.uint8), low[k].astype(np.uint8), None, .5, 2, 9, 3, 5, 1.1, 0)
            mag = np.hypot(cv2.Sobel(low[k], cv2.CV_32F, 1, 0), cv2.Sobel(low[k], cv2.CV_32F, 0, 1))
            m = mag > np.percentile(mag, 60)
            if m.sum() > 20:
                vs.append([float(f[..., 0][m].mean()), float(f[..., 1][m].mean())])
        return np.mean(vs, 0) if vs else np.zeros(2)
    diag = math.hypot(W, H)
    rows = []
    shots = picture_shots(t)
    for i, s in enumerate(shots[1:], 1):
        tr = s.get("transition") or {}
        c = s["start_frame"] - off
        a = c - 1
        b = c + (tr.get("duration_frames", 0) if tr.get("name") else 0)
        if a < 2 or b >= n - 1:
            continue
        xa, ya, ca = focus_of(gray[a], gray[a - 1])
        xb, yb, cb = focus_of(gray[b], gray[b - 1])
        jump = math.hypot((xa - xb) * W, (ya - yb) * H) / diag
        before, after = mot(a - 4, a), mot(b, b + 4)
        kind = "on_action" if before > .8 and after > .8 else "static_to_motion" if before <= .3 and after > .8 else \
            "motion_to_static" if before > .8 and after <= .3 else "static"
        fb, fa = flow(a - 4, a + 1), flow(b, b + 5)
        prev_len = (shots[i - 1]["end_frame"] - shots[i - 1]["start_frame"]) / FPS
        next_len = (s["end_frame"] - s["start_frame"]) / FPS
        rows.append({"cut_frame": s["start_frame"], "into_shot": s["id"], "transition": tr.get("name") or "cut", "focus_out": [round(xa, 3), round(ya, 3)],
                     "focus_in": [round(xb, 3), round(yb, 3)], "eye_jump": round(jump, 3), "motion_before": round(before, 2), "motion_after": round(after, 2),
                     "cut_type": kind, "shorter_neighbor_s": round(min(prev_len, next_len), 2), "_a": a, "_b": b,
                     "flow_before": [round(float(v), 2) for v in fb], "flow_after": [round(float(v), 2) for v in fa]})
    lens = [(s["end_frame"] - s["start_frame"]) / FPS for s in shots]
    asl = sum(lens) / len(lens)
    cv = float(np.std(lens) / (asl + 1e-9))
    slope = float(np.polyfit(np.arange(len(lens)), lens, 1)[0]) if len(lens) >= 3 else 0.0
    findings = []
    for r in rows:
        if r["eye_jump"] > .35 and r["shorter_neighbor_s"] < 2.0:
            findings.append(_finding("check", "eye_trace_jump", {"cut_frame": r["cut_frame"], "into_shot": r["into_shot"]},
                                     {"eye_jump": r["eye_jump"], "focus_out": r["focus_out"], "focus_in": r["focus_in"], "threshold": .35},
                                     "The viewer's eye must travel across the frame at a fast cut. Reframe the incoming shot (focus_x/y, crop) so its "
                                     "subject lands near the outgoing focus, or hold the shot longer."))
    # Motion direction across the seam (the first rule of seamless transitions): a directional transition should travel
    # the way the footage already moves, and a plain cut between two moving shots should not reverse screen direction.
    WANT = {"whip_left": (-1, 0), "push_left": (-1, 0), "pass_left": (-1, 0), "whip_right": (1, 0), "push_right": (1, 0), "pass_right": (1, 0),
            "whip_up": (0, -1), "push_up": (0, -1), "whip_down": (0, 1), "push_down": (0, 1)}
    ang = lambda v, w: math.degrees(math.acos(max(-1, min(1, (v[0] * w[0] + v[1] * w[1]) / (math.hypot(*v) * math.hypot(*w) + 1e-9)))))
    for r in rows:
        fb, fa = r["flow_before"], r["flow_after"]
        moving = lambda v: math.hypot(*v) > .6
        if r["transition"] in WANT:
            want = WANT[r["transition"]]
            against = [side for side, v in (("outgoing", fb), ("incoming", fa)) if moving(v) and ang(v, want) > 100]
            if against:
                findings.append(_finding("check", "transition_against_motion", {"cut_frame": r["cut_frame"], "into_shot": r["into_shot"]},
                                         {"transition": r["transition"], "against": against, "flow_before": fb, "flow_after": fa},
                                         "The transition travels against the motion already in the footage; the seam reads as a bump. Use the "
                                         "transition that matches the camera/subject direction or cut on the move."))
        elif r["transition"] == "cut" and moving(fb) and moving(fa) and ang(fb, fa) > 135:
            findings.append(_finding("info", "screen_direction_reversal", {"cut_frame": r["cut_frame"], "into_shot": r["into_shot"]},
                                     {"flow_before": fb, "flow_after": fa},
                                     "Both sides move but in opposite screen directions. Fine for a deliberate confrontation; in continuous action it breaks direction."))
    jumps = [r["eye_jump"] for r in rows]
    if rows and asl < 2.0 and sum(jumps) / len(jumps) > .25:
        findings.append(_finding("likely_problem", "fast_cutting_without_eye_trace", {}, {"average_shot_s": round(asl, 2), "mean_eye_jump": round(sum(jumps) / len(jumps), 3)},
                                 "Fast cutting reads as chaos unless each shot's subject sits where the eye already is (centre-framed or "
                                 "matched). Align focal points across cuts or slow the cutting."))
    if len(lens) >= 5 and cv < .12:
        findings.append(_finding("info", "metric_rhythm", {}, {"shot_length_cv": round(cv, 3)},
                                 "Shot lengths are nearly identical (metric montage). Fine on a beat grid; otherwise vary length with the content."))
    static = [r for r in rows if r["cut_type"] == "static"]
    if rows and len(static) / len(rows) > .7:
        findings.append(_finding("info", "few_cuts_on_action", {}, {"static_cuts": len(static), "cuts": len(rows)},
                                 "Most cuts happen between still moments. Cutting during a movement hides the cut; ending a scene on stillness and "
                                 "cutting into motion changes the rhythm on purpose."))
    # Contact sheet: up to 8 cuts, outgoing | incoming with focal markers.
    sheet = None
    if rows:
        tw, th = 240, int(240 * h / width)
        im = Image.new("RGB", (tw * 2 + 30, (th + 26) * min(8, len(rows))), (16, 16, 16))
        d = ImageDraw.Draw(im)
        for k, r in enumerate(rows[:8]):
            y0 = k * (th + 26)
            for j, (fi, fp) in enumerate(((r["_a"], r["focus_out"]), (r["_b"], r["focus_in"]))):
                tile = Image.fromarray(rgb[fi]).resize((tw, th))
                im.paste(tile, (j * (tw + 30), y0))
                cx, cy = j * (tw + 30) + fp[0] * tw, y0 + fp[1] * th
                d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], outline=(255, 210, 0), width=3)
            d.text((4, y0 + th + 4), f"cut {r['cut_frame']} {r['transition']} jump {r['eye_jump']} {r['cut_type']}", fill=(230, 230, 230))
        out = store.DATA / "observations"
        out.mkdir(parents=True, exist_ok=True)
        sheet = str(out / f"cut-audit-{project_id[:8]}-{int(rows[0]['cut_frame'])}.png")
        im.save(sheet)
    for r in rows:
        r.pop("_a"), r.pop("_b")
    return {"project_id": project_id, "cuts": rows, "rhythm": {"shots": len(lens), "average_shot_s": round(asl, 2), "median_shot_s": round(float(np.median(lens)), 2),
                                                               "length_cv": round(cv, 3), "trend_s_per_shot": round(slope, 3)},
            "findings": findings, "contact_sheet": sheet,
            "method": "Focus = spectral-residual saliency mixed with motion and a mild centre prior on 160 px frames; eye_jump is the focus "
                      "distance across the cut as a fraction of the frame diagonal; motion is mean luminance change. Heuristic evidence for "
                      "eye trace and cutting on action, not a judgement of emotion or story (which rank higher)."}


def contact_sheet(paths, labels=None, max_width=1600):
    """Tile images into one labelled sheet (one image costs far fewer tokens than many)."""
    from PIL import Image, ImageDraw
    ims = [Image.open(p).convert("RGB") for p in paths]
    cols = min(4, len(ims))
    rows = (len(ims) + cols - 1) // cols
    tw = max_width // cols
    th = round(tw * ims[0].height / ims[0].width)
    sheet = Image.new("RGB", (tw * cols, (th + 18) * rows), (12, 12, 12))
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(ims):
        x, y = (i % cols) * tw, (i // cols) * (th + 18)
        sheet.paste(im.resize((tw, th)), (x, y))
        if labels:
            d.text((x + 4, y + th + 2), str(labels[i]), fill=(235, 235, 235))
    out = Path(paths[0]).with_name("sheet-" + Path(paths[0]).stem + ".jpg")
    sheet.save(out, quality=85)
    return str(out)



def black_in_shots(pid, timeline=None, min_s=.12, pix_th=.10):
    """Black runs inside each video shot's source window (a source that cuts through black, a tape dropout): the frames a
    shot will actually show, read with FFmpeg blackdetect at low resolution. Returns [{"shot", "black": [[start, end] in the
    shot's seconds]}]."""
    from .media import FFMPEG
    t = timeline or agent.read(pid)["timeline"]
    assets = {a["id"]: a for a in store.assets(pid)}
    out = []
    for s in t["shots"]:
        a = assets.get(s.get("asset_id") or "")
        if not a or a.get("kind") != "video" or s.get("freeze"):
            continue
        rate = float(s.get("playback_rate") or 1)
        dur = (s["end_frame"] - s["start_frame"]) / FPS * rate
        r = subprocess.run([FFMPEG, "-v", "info", "-ss", f"{float(s.get('source_start') or 0):.3f}", "-t", f"{dur:.3f}", "-i", a["path"], "-an",
                            "-vf", f"scale=160:-2,blackdetect=d={min_s}:pix_th={pix_th}", "-f", "null", "-"], capture_output=True)
        log = (r.stderr or b"").decode("utf-8", "replace")
        spans = [[round(float(x) / rate, 2), round(float(y) / rate, 2)] for x, y in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", log)]
        if spans:
            out.append({"shot": s["id"], "black": spans})
    return out


@functools.lru_cache(maxsize=512)
def black_runs(path, min_s=.12, pix_th=.10):
    """Black runs in a whole file, [(start, end)] in seconds (FFmpeg blackdetect at low resolution); cached per path, so a
    build can test every shot's window against the file once."""
    from .media import FFMPEG
    r = subprocess.run([FFMPEG, "-v", "info", "-i", str(path), "-an", "-vf", f"scale=160:-2,blackdetect=d={min_s}:pix_th={pix_th}", "-f", "null", "-"],
                       capture_output=True)
    log = (r.stderr or b"").decode("utf-8", "replace")
    return tuple((float(x), float(y)) for x, y in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", log))


def avoid_black(start, need, runs, length, gap=.04):
    """The source in-point nearest `start` whose next `need` seconds of the file hold no black run (from black_runs). Returns
    `start` when it is already clear, or when no clear window of that length exists (black_in_shots will still report it)."""
    hit = lambda s: any(a < s + need and b > s for a, b in runs)
    if not hit(start):
        return start
    cands = [0.0, max(0.0, length - need)] + [b + gap for a, b in runs] + [a - need - gap for a, b in runs]
    ok = [c for c in cands if 0 <= c <= length - need + 1e-6 and not hit(c)]
    return round(min(ok, key=lambda c: abs(c - start)), 3) if ok else start


@functools.lru_cache(maxsize=1024)
def repeated_frames(path, start=0.0, seconds=2.0):
    """Share of frames that repeat the previous one while the picture moves: a frame whose change from the last (the
    mean of its 5 % most-changed pixels, so a small moving subject counts) is under 8 % of the window's typical change
    (75th percentile).
    A 25 fps clip conformed to 30 fps by duplication reads about .17, 24 fps about .2, true 30 fps footage about 0; a
    still picture reads 0 (nothing to judder)."""
    from .media import FFMPEG
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-t", f"{seconds:.3f}", "-i", str(path), "-an",
                          "-vf", "scale=160:90,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    f = np.frombuffer(raw[:len(raw) // 14400 * 14400], np.uint8).reshape(-1, 90, 160).astype(np.int16)
    if len(f) < 12:
        return 0.0
    diff = np.abs(np.diff(f, axis=0)).reshape(len(f) - 1, -1)
    k = max(1, diff.shape[1] // 20)
    d = np.partition(diff, -k, axis=1)[:, -k:].mean(axis=1)
    moving = float(np.percentile(d, 75))  # a picture repeated every other frame has a median change of ~0
    if moving < 1.0:
        return 0.0
    return float((d < moving * .08).mean())


def render_repeats(video, timeline, min_frames=20, start=0.0):
    """Per footage shot, the share of frames in the RENDER that repeat the one before while the picture moves (the rule
    of repeated_frames, frame by frame over the whole film at 160x90). Proxies may fall back from interpolation; this
    reads what the viewer gets. Returns [{"shot", "seconds", "repeated_share"}] for shots of >= min_frames frames."""
    from .media import FFMPEG
    proc = subprocess.Popen([FFMPEG, "-v", "error", "-ss", f"{start:.3f}", "-i", str(video), "-an", "-vf", "scale=160:90,format=gray", "-f", "rawvideo", "-"],
                            stdout=subprocess.PIPE)
    diffs, prev = [], None
    while True:
        buf = proc.stdout.read(14400)
        if len(buf) < 14400:
            break
        f = np.frombuffer(buf, np.uint8).astype(np.int16)
        if prev is not None:
            d = np.abs(f - prev)
            k = len(d) // 20
            diffs.append(float(np.partition(d, -k)[-k:].mean()))
        prev = f
    proc.wait()
    diffs = np.array(diffs)
    out = []
    for sh in timeline["shots"]:
        a, b = sh["start_frame"] - round(start * FPS), sh["end_frame"] - round(start * FPS)
        if not sh.get("asset_id") or sh.get("freeze") or b - a < min_frames or a < 0 or b - 1 > len(diffs):
            continue
        d = diffs[a:b - 1]  # pairs (j, j+1) inside the shot: not the cut into it
        moving = float(np.percentile(d, 75))  # a picture repeated every other frame has a median change of ~0
        if moving < 1.0:
            continue
        out.append({"shot": sh["id"], "seconds": round((b - a) / FPS, 2), "repeated_share": round(float((d < moving * .08).mean()), 3)})
    return out


def black_cuts(video, min_seconds=.15):
    """Runs of black in the RENDER and how each was entered: [{"start_s", "seconds", "hard"}]. hard: the picture one to
    frame before was still bright, so the film cut to black instead of fading (round 13, the fifth cut: 16 of 37
    black runs; the owner saw them as the film breaking down). FFmpeg blackdetect at 320 px."""
    from .media import FFMPEG
    run = subprocess.run([FFMPEG, "-v", "info", "-i", str(video), "-an", "-vf", f"scale=320:-2,blackdetect=d={min_seconds}:pix_th=0.08", "-f", "null", "-"],
                         capture_output=True, text=True, errors="replace")
    if run.returncode != 0:  # an unreadable render is an error, not a film without black runs
        raise RuntimeError(f"black_cuts could not read {video}: {run.stderr.strip()[-300:]}")
    log = run.stderr

    def luma(sec):
        raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, sec):.3f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=160:90,format=gray",
                              "-f", "rawvideo", "-"], capture_output=True).stdout
        return float(np.frombuffer(raw, np.uint8).mean()) if raw else 0.0
    out = []
    for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log):
        a, b = float(a), float(b)
        l1 = luma(a - 1.5 / FPS)  # the last frame before the run (a seek at a - 1/30 can land on the first black one)
        out.append({"start_s": round(a, 2), "seconds": round(b - a, 2), "hard": a > .1 and l1 > 25})  # a fade arrives near black
    return out


def intensity_curve(video, window=5.0, flat_lu=3.0, flat_s=90.0, drop_lu=10.0):
    """How loud the RENDER is window by window, and whether a long film breathes (round 13, the owner's list C4: high and
    low alternating, silences on purpose). RMS level of the mixed track in dBFS per `window` seconds (8 kHz mono; a
    level, not integrated LUFS). flat: stretches of at least `flat_s` seconds whose windows all stay within `flat_lu`
    of each other (no rise, no rest); drops: windows at least `drop_lu` under the minute around them, the quiet moments
    the edit chose (or a gap it did not). Returns {"window_s", "levels", "flat", "drops", "range_db"}."""
    from .media import FFMPEG
    run = subprocess.run([FFMPEG, "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"], capture_output=True)
    if run.returncode != 0:
        raise RuntimeError(f"intensity_curve could not read {video}: {run.stderr.decode(errors='replace').strip()[-300:]}")
    x = np.frombuffer(run.stdout, np.float32)
    n = int(window * 8000)
    if len(x) < n:
        raise ValueError("the render is shorter than one window")
    k = len(x) // n
    rms = np.sqrt(np.mean(x[:k * n].reshape(k, n).astype(np.float64) ** 2, axis=1))
    lev = 20 * np.log10(np.maximum(rms, 1e-6))
    flat, i = [], 0
    while i < k:
        j = i
        while j + 1 < k and lev[i:j + 2].max() - lev[i:j + 2].min() <= flat_lu:
            j += 1
        if (j - i + 1) * window >= flat_s:
            flat.append({"start_s": round(i * window, 1), "end_s": round((j + 1) * window, 1)})
        i = j + 1
    around = max(1, int(round(60 / window / 2)))
    drops = [{"at_s": round(i * window, 1), "under_db": round(float(np.median(lev[max(0, i - around):i + around + 1]) - lev[i]), 1)}
             for i in range(k) if np.median(lev[max(0, i - around):i + around + 1]) - lev[i] >= drop_lu]
    return {"window_s": window, "levels": [round(float(v), 1) for v in lev], "flat": flat, "drops": drops,
            "range_db": round(float(np.percentile(lev, 95) - np.percentile(lev, 5)), 1)}


def render_sharpness(video, timeline, sources, min_frames=30):
    """Per footage shot, how sharp the RENDER is at the shot's middle frame against its own source at the same moment,
    both at 960x540 (variance of the Laplacian; letterbox bars left out). sources: asset id -> file path. ratio < .6 is
    softness the edit added (a blend, a heavy scale or blur); a low "source" alone is a soft original (upscaled 360p).
    Round 13: blended proxies kept 60 % of the sharpness the shots had elsewhere. Returns [{"shot", "render", "source",
    "ratio"}]."""
    import cv2
    from .media import FFMPEG
    bars = [(l["start_frame"], l["end_frame"]) for l in timeline.get("layers", []) if l["id"].startswith("lbx-top-")]

    def frame(path, sec):
        raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, sec):.3f}", "-i", str(path), "-frames:v", "1", "-vf",
                              "scale=960:540:force_original_aspect_ratio=increase,crop=960:540,format=gray", "-f", "rawvideo", "-"],
                             capture_output=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(540, 960) if len(raw) >= 960 * 540 else None

    def sharp(g, top):
        return float(cv2.Laplacian(g[top + 4:540 - top - 4, 4:-4], cv2.CV_64F).var())
    out = []
    for sh in timeline["shots"]:
        a, b = sh["start_frame"], sh["end_frame"]
        src = sources.get(sh.get("asset_id"))
        if not src or sh.get("freeze") or b - a < min_frames:
            continue
        mid = (a + b) // 2
        top = int(.128 * 540) if any(x <= mid < y for x, y in bars) else 0
        r = frame(video, mid / FPS)
        s = frame(src, float(sh.get("source_start") or 0) + (mid - a) / FPS * float(sh.get("playback_rate") or 1))
        if r is None or s is None:
            continue
        rv, sv = sharp(r, top), sharp(s, top)
        out.append({"shot": sh["id"], "render": round(rv, 1), "source": round(sv, 1), "ratio": round(rv / max(sv, 1e-6), 2)})
    return out


def frozen_share(video, min_s=.5):
    """Share of a video's running time spent on a frozen picture: runs of at least min_s where frames stop changing
    (top-5 % pixel change under 0.6 at 160x90) and the picture is not black. Round 13: the fifth cut froze 39 shots
    (74.5 s), which the owner read as overuse. Returns {"share", "seconds", "runs"}."""
    from .media import FFMPEG, probe
    v = next((x for x in probe(str(video))["streams"] if x["codec_type"] == "video"), {})
    num, _, den = str(v.get("avg_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    proc = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(video), "-an", "-vf", "scale=160:90,format=gray", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    prev, run, runs, n = None, 0, [], 0
    while True:
        buf = proc.stdout.read(14400)
        if len(buf) < 14400:
            break
        f = np.frombuffer(buf, np.uint8).astype(np.int16)
        n += 1
        if prev is not None:
            d = np.abs(f - prev)
            k = len(d) // 20
            still = float(np.partition(d, -k)[-k:].mean()) < .6 and f.mean() > 20
            if still:
                run += 1
            else:
                if run + 1 >= min_s * fps:
                    runs.append(run + 1)
                run = 0
        prev = f
    proc.wait()
    if run + 1 >= min_s * fps:
        runs.append(run + 1)
    secs = sum(runs) / fps
    return {"share": round(secs / max(n / fps, 1e-6), 4), "seconds": round(secs, 1), "runs": len(runs)}


def still_runs(video, window=3.0, delta=6, static=.92, step=.5):
    """Stretches where almost the whole picture stays put: over every `window` seconds, the share of pixels (320x180
    grey) that never change by more than `delta` levels; a run is where that share stays >= `static` on a picture that
    is not black. frozen_share counts only frames that stop changing altogether; a card with one growing line or a
    drifting thumbnail is not frozen, yet reads as a slide (round 13, ninth cut: 16 cards per episode, 9-12 s each,
    0-4.5 % of the picture moving; frozen_share found 77 s of episode 1, this 124 s). A held wide shot
    can land here too: the runs are evidence for whoever directs, not a verdict. Returns {"runs": [{"start_s",
    "seconds", "static_share"}], "seconds", "share"}."""
    from .media import FFMPEG
    proc = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(video), "-an", "-vf", f"fps={1 / step:g},scale=320:180,format=gray",
                             "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    frames = []
    while True:
        buf = proc.stdout.read(57600)
        if len(buf) < 57600:
            break
        frames.append(np.frombuffer(buf, np.uint8))
    proc.wait()
    k = max(1, int(round(window / step)))
    flags = []  # (window start index, static share) for windows that read as a still picture
    for i in range(0, max(0, len(frames) - k)):
        stack = np.stack(frames[i:i + k + 1]).astype(np.int16)
        if stack.mean() <= 20:  # black: black_cuts covers it
            flags.append((i, None))
            continue
        flags.append((i, float(((stack.max(0) - stack.min(0)) <= delta).mean())))
    runs, cur = [], None
    for i, s in flags + [(len(flags), None)]:
        if s is not None and s >= static:
            cur = cur or {"i": i, "shares": []}
            cur["shares"].append(s)
        elif cur:
            n = len(cur["shares"])
            runs.append({"start_s": round(cur["i"] * step, 2), "seconds": round((n - 1) * step + window, 2),
                         "static_share": round(float(np.median(cur["shares"])), 3)})
            cur = None
    secs = sum(r["seconds"] for r in runs)
    return {"runs": runs, "seconds": round(secs, 1), "share": round(secs / max(len(frames) * step, 1e-6), 4)}


def cuts_inside(video, threshold=12.0):
    """Seconds at which a source file cuts to another picture (ffmpeg scdet, scene score >= threshold of 100). Archive
    reels hide cuts and title cards inside what looks like one shot: the round 13 showcase's triptych showed a Pathé
    title card that sat 4.16 s into a "single" portrait clip."""
    import re
    from .media import FFMPEG
    r = subprocess.run([FFMPEG, "-v", "info", "-i", str(video), "-an", "-vf", f"scdet=threshold={threshold:g}", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace").stderr
    return [round(float(t), 3) for t in re.findall(r"lavfi\.scd\.time: ([\d.]+)", r)]


def clean_runs(video, start=0.0, seconds=None, fps=10, jump=.35):
    """Stretches of a source window fit to show. Every sampled frame (fps a second, 160x90 luma) is judged against the
    window's own level, because archive often peaks near 200 rather than 255:
    - dark: mean under 30 with nothing bright in it (98th percentile under 110): a fogged or black head of a reel
      (night footage with tracers or fires keeps its bright points and passes);
    - flash: the 95th percentile 25+ above the window's median and a few pixels above its usual peak (white punch holes,
      burns, splices: the first montage showed punch holes for 0.3 s);
    - jump: a luma-histogram change between neighbours over `jump` (Bhattacharyya distance), a cut the scene detector
      missed (a crowd inside a "Chinook" clip).
    Returns {"runs": [[start_s, end_s], ...] clean, longest first, "flags": [{"t", "why"}]}."""
    from .media import FFMPEG, probe
    d = float(probe(video)["format"]["duration"])
    seconds = d - start if seconds is None else min(seconds, d - start)
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{seconds:.3f}", "-vf",
                          f"fps={fps},scale=160:90,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 90, 160) if raw else np.zeros((0, 90, 160), np.uint8)
    if not len(fr):
        return {"runs": [], "flags": [{"t": start, "why": ["unreadable"]}]}
    # judge the picture, not its frame: NARA's scans put 4:3 film between black bars, and the bars alone made a cut from
    # a teletype to its operator correlate at 0.86 (and diluted the histograms)
    lit = fr.max(axis=0) > 24
    cols, rows = np.flatnonzero(lit.any(axis=0)), np.flatnonzero(lit.any(axis=1))
    if len(cols) > 40 and len(rows) > 24:
        fr = np.ascontiguousarray(fr[:, rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1])
    p95 = np.percentile(fr.reshape(len(fr), -1), 95, axis=1)
    p98 = np.percentile(fr.reshape(len(fr), -1), 98, axis=1)
    p99 = np.percentile(fr.reshape(len(fr), -1), 99, axis=1)
    hist = [np.histogram(f_, 32, (0, 256))[0].astype(np.float64) for f_ in fr]
    hist = [h / max(1, h.sum()) for h in hist]
    # a cut: the luma histogram jumps, or the picture's structure stops matching its neighbour's (correlation of the
    # mean-removed frames under 0.5). Grey sky with aircraft cut to grey water with gunboats kept its histogram (0.41);
    # a catapult launch in steam, the fastest action in the reel, stays above 0.75.
    def corr(x, y):
        x, y = x.astype(np.float32) - x.mean(), y.astype(np.float32) - y.mean()
        return float((x * y).sum() / np.sqrt((x * x).sum() * (y * y).sum() + 1e-6))
    cut = [i for i in range(1, len(fr)) if 1 - np.sum(np.sqrt(hist[i] * hist[i - 1])) > jump or corr(fr[i], fr[i - 1]) < .5]
    # a dissolve changes the picture too slowly for any neighbour test (an edited Navy documentary dissolved from a
    # teletype to its operator to a destroyer and read as one 200 s shot): a frame inside one is the mix of the frames
    # either side of it while those two have little in common. A pan is not: its middle is no blend of its ends.
    k = max(2, round(.7 * fps))
    dissolve = set()
    for i in range(k, len(fr) - k):
        fa, fb, fm = fr[i - k].astype(np.float32), fr[i + k].astype(np.float32), fr[i]
        if corr(fa, fb) < .4:
            mix = corr(fm, (fa + fb) / 2)
            if mix > .9 and mix > max(corr(fm, fa), corr(fm, fb)) + .08:
                dissolve.update(range(i - k // 2, i + k // 2 + 1))
    # each shot between two cuts is judged against its own level (a dark gunsight shot followed by a bright jungle shot
    # made the whole jungle shot read as one long flash)
    seg = np.zeros(len(fr), int)
    for c_ in cut:
        seg[c_:] += 1
    m95 = {k: float(np.median(p95[seg == k])) for k in set(seg.tolist())}
    m99 = {k: float(np.median(p99[seg == k])) for k in set(seg.tolist())}
    bad, flags = np.zeros(len(fr), bool), []
    for i, f_ in enumerate(fr):
        why = []
        if (f_.mean() < 30 and p98[i] < 110) or (f_.mean() < 45 and np.percentile(f_, 90) < 75 and f_.std() < 22):
            why.append("dark")  # a dark smear with one bright strip (a B-52 at dawn) is still unreadable
        if p95[i] - m95[seg[i]] > 25 and (f_ > min(250, m99[seg[i]] + 15)).mean() > .002:
            why.append("flash")  # kept only when short (below): a long bright stretch is another shot, not a flash
        if i in cut:
            why.append("jump")
            bad[i - 1] = True  # a cut spoils both sides of it
        if i in dissolve:
            why.append("dissolve")
        if why:
            bad[i] = True
            flags.append({"t": round(start + i / fps, 2), "why": why})
    # a "flash" longer than 0.8 s is a change of shot that the cut tests missed: the frame where it starts is the cut
    fl = {round((f_["t"] - start) * fps) for f_ in flags if f_["why"] == ["flash"]}
    i = 0
    while i < len(fr):
        if i in fl:
            j = i
            while j + 1 in fl:
                j += 1
            if j - i + 1 > .8 * fps:
                bad[i + 1:j + 1] = False
                flags = [f_ for f_ in flags if not (f_["why"] == ["flash"] and i < round((f_["t"] - start) * fps) <= j)]
                for f_ in flags:
                    if round((f_["t"] - start) * fps) == i:
                        f_["why"] = ["jump"]
            i = j + 1
        else:
            i += 1
    runs, a = [], None
    for i, b_ in enumerate(list(bad) + [True]):
        if not b_ and a is None:
            a = i
        elif b_ and a is not None:
            runs.append([round(start + a / fps, 2), round(start + i / fps, 2)])
            a = None
    runs.sort(key=lambda r: r[0] - r[1])
    # how readable each frame is: contrast (luma spread) times detail (gradient energy)
    gy, gx = np.gradient(fr.astype(np.float32), axis=(1, 2))
    read = fr.reshape(len(fr), -1).std(1) * np.sqrt((gx * gx + gy * gy).reshape(len(fr), -1).mean(1))
    return {"runs": runs, "flags": flags[:60], "readability": [round(float(v), 1) for v in read], "fps": fps, "start": start}


def best_window(video, seconds, start=0.0, end=None, fps=10):
    """(source_start, seconds) of the most readable clean stretch of at least `seconds` between start and end
    (review.clean_runs ranks frames by contrast x detail): the dark head of a take-off reel lost to its clear lift-off
    3 s later. Raises when no clean stretch is long enough."""
    r = clean_runs(video, start, None if end is None else end - start, fps)
    rd, best = r["readability"], None
    k = max(1, round(seconds * fps))
    for a, b in r["runs"]:
        i0, i1 = round((a - start) * fps), round((b - start) * fps)
        for i in range(i0, max(i0, i1 - k) + 1):
            seg = rd[i:i + k]
            if len(seg) == k and (best is None or np.mean(seg) > best[0]):
                best = (float(np.mean(seg)), start + i / fps)
    if best is None:
        raise ValueError(f"{Path(video).name}: no clean stretch of {seconds} s")
    a = round(best[1], 2)
    run_end = next(b for a_, b in r["runs"] if a_ <= a + .01 < b)
    return a, round(run_end - a - .05, 2)


def source_cuts(timeline, assets, threshold=12.0):
    """Shots and video layers whose source window crosses a cut inside their file: the picture changes to something
    the edit did not choose (another shot, a title card, a slate). Returns [{"kind", "id", "asset_id", "cut_s", "window"}]."""
    by = {a["id"]: a for a in assets}
    seen, out = {}, []
    items = [("shot", s_) for s_ in timeline.get("shots") or []] + [("layer", l_) for l_ in timeline.get("layers") or [] if l_.get("kind") == "video"]
    for kind, it in items:
        a = by.get(it.get("asset_id"))
        if not a or a.get("kind") != "video" or not a.get("path"):
            continue
        if a["id"] not in seen:
            seen[a["id"]] = cuts_inside(a["path"], threshold)
        s0 = float(it.get("source_start") or 0)
        s1 = s0 + (it["end_frame"] - it["start_frame"]) / 30 * float(it.get("playback_rate") or 1)
        for c in seen[a["id"]]:
            if s0 + .05 < c < s1 - .05:
                out.append({"kind": kind, "id": it["id"], "asset_id": a["id"], "cut_s": c, "window": [round(s0, 3), round(s1, 3)]})
    return out


# ---------------------------------------------------------------- delivery gates (reports/Nâng cấp 3D phim tài liệu.md, P0-4)
def banding(video, start=None, seconds=None, threshold=5.0):
    """Netflix CAMBI banding score per frame (libvmaf, no reference: the video against itself); around 5 banding starts
    to annoy. Sky, mist and dark seas are where an 8-bit render bands. Returns {"max", "mean", "over"}."""
    import json, tempfile
    from .media import FFMPEG
    cut = (["-ss", str(start)] if start is not None else []) + (["-t", str(seconds)] if seconds else [])
    with tempfile.TemporaryDirectory(dir=str(Path(video).parent)) as td:
        subprocess.run([FFMPEG, "-v", "error", *cut, "-i", str(video), *cut, "-i", str(video), "-lavfi",
                        "[0:v][1:v]libvmaf=feature=name=cambi:log_fmt=json:log_path=cambi.json:n_threads=4", "-f", "null", "-"],
                       cwd=td, check=True, capture_output=True)
        fr = json.loads((Path(td) / "cambi.json").read_text())["frames"]
    v = [f["metrics"].get("cambi", 0.0) for f in fr]
    run = longest = 0
    for x in v:  # a fade through black bands for a few frames; banding that stays is what a viewer sees
        run = run + 1 if x > threshold else 0
        longest = max(longest, run)
    return {"max": round(max(v or [0]), 3), "mean": round(sum(v) / max(1, len(v)), 3), "longest_run": longest,
            "over": [round(i / 30 + (start or 0), 2) for i, x in enumerate(v) if x > threshold][:20]}


def flashes(video, area=.25, delta_cd=20.0, dark_cd=160.0, peak_cd=200.0):
    """Photosensitive-epilepsy screening (Ofcom/ITU-R BT.1702 and WCAG 2.3.1 general flash rule): a flash is a pair of
    opposite luminance changes of >= 20 cd/m2, the darker state under 160 cd/m2, over more than a quarter of the screen;
    more than three flashes in any second fails. Luminance assumes a 200 cd/m2 display; saturated-red flashes are not
    screened here. Returns {"max_per_s", "fails": [seconds]} (a screening, not a certificate)."""
    from .media import FFMPEG, probe
    v = next((x for x in probe(str(video))["streams"] if x["codec_type"] == "video"), {})
    num, _, den = str(v.get("avg_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    proc = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(video), "-an", "-vf", "scale=160:90,format=gray", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    prev, events, n = None, [], 0
    while True:
        buf = proc.stdout.read(14400)
        if len(buf) < 14400:
            break
        cd = peak_cd * (np.frombuffer(buf, np.uint8).astype(np.float32) / 255) ** 2.2
        if prev is not None:
            d = cd - prev
            lo = np.minimum(cd, prev) < dark_cd
            up = ((d >= delta_cd) & lo).mean() > area
            dn = ((d <= -delta_cd) & lo).mean() > area
            if up or dn:
                events.append((n, 1 if up else -1))
        prev, n = cd, n + 1
    proc.wait()
    per_s, fails = 0, []
    for i, (f, sgn) in enumerate(events):
        win = [s_ for g, s_ in events[i:] if g < f + fps]
        flips = sum(1 for a, b in zip(win, win[1:]) if a != b)
        k = (flips + 1) // 2
        per_s = max(per_s, k)
        if k > 3:
            fails.append(round(f / fps, 2))
    return {"max_per_s": per_s, "fails": sorted(set(fails))[:20]}


def legal_levels(video, limit=.01):
    """Broadcast-range screening (EBU R103: luma -1..103 %, RGB -5..105 %, about 1 % of the picture may stray): frames
    whose share of out-of-range pixels (ffmpeg signalstats BRNG) passes `limit`. Returns {"frames", "worst", "at"}."""
    import re
    from .media import FFMPEG
    r = subprocess.run([FFMPEG, "-v", "info", "-i", str(video), "-an", "-vf", "scale=480:-2,signalstats=stat=brng,metadata=print:key=lavfi.signalstats.BRNG",
                        "-f", "null", "-"], capture_output=True, text=True, errors="replace")
    vals = [float(x) for x in re.findall(r"lavfi\.signalstats\.BRNG=([-+\d.eE]+)", r.stdout + r.stderr)]  # a fraction, often 7.7e-05
    if not vals:
        raise RuntimeError("signalstats printed nothing: cannot screen legal levels")
    bad = [i for i, x in enumerate(vals) if x > limit]
    return {"frames": len(bad), "worst": round(max(vals or [0]), 4), "at": [round(i / 30, 2) for i in bad[:20]]}


WORDS_PER_S = 3.2   # the audit's reading_load: about 3 words a second (x1.4 for Vietnamese's short syllables)
CHARS_PER_S = 17    # Netflix's Vietnamese subtitles


LABEL_ROLES = ("label", "headline", "title", "display")


def label_hold_s(chars):
    """A label, title or date competing with narration and a moving picture is read twice at a slow pace (round 13: 35
    of 185 layers in the fourth film left before they could be read)."""
    return max(3.5, 2 * chars / 15 + .5)


def reading_frames(text, fps=30, role=None):
    """The fewest frames a line needs on screen to pass the audit's reading_load (words and characters a second, 0.5 s
    and 0.3 s of fades not counted), its text_too_brief for labels and titles (role), and the delivery gate's
    text_holds (the bible's hold, half of 6 + 6 frame fades not counted). Recipes that place type use it, so what they
    place is what the checks accept."""
    from . import style
    words, chars = len(text.split()), len(" ".join(text.split()))
    limit = WORDS_PER_S * (1.4 if is_vietnamese(text) else 1)
    need = [style.hold_frames(text) + 6]
    if words >= 4:
        need.append(math.ceil((words / limit + .5) * fps))
    if chars >= 12:
        need.append(math.ceil((chars / CHARS_PER_S + .3) * fps))
    if role in LABEL_ROLES and chars >= 6:
        need.append(math.ceil(label_hold_s(chars) * fps) + 2)
    return max(need)


def text_holds(timeline, lang="vi"):
    """Text layers on screen too briefly to be read at the language's reading speed (the bible's label rules: Vietnamese
    17 characters a second, a 1.5 s floor; fades do not count). Returns [{"id", "text", "frames", "needs"}]."""
    from . import style
    out = []
    for l in timeline.get("layers") or []:
        if l.get("kind") != "text" or not (l.get("text") or "").strip():
            continue
        fades = sum(e["end_frame"] - e.get("start_frame", 0) for e in l.get("effects") or [] if e["name"] in ("fade_in", "fade_out"))
        shown = l["end_frame"] - l["start_frame"] - fades // 2
        need = style.hold_frames(l["text"], lang)
        if shown < need:
            out.append({"id": l["id"], "text": l["text"][:60], "frames": shown, "needs": need})
    return out


def text_contrast(video, timeline, large_px=24):
    """WCAG contrast of each text layer against the picture under its box, at its middle frame in the render (the
    median of the box: thin type covers little of it). Large type (>= large_px, labels) needs 3:1, the rest 4.5:1.
    Returns [{"id", "ratio", "needs", "at_s"}] for those below."""
    from PIL import Image
    from .media import FFMPEG
    from . import style
    W, H = timeline.get("width", 1920), timeline.get("height", 1080)
    lum = lambda rgb: sum(w * ((c / 255) / 12.92 if c / 255 <= .04045 else ((c / 255 + .055) / 1.055) ** 2.4) for w, c in zip((.2126, .7152, .0722), rgb))
    out = []
    for l in timeline.get("layers") or []:
        if l.get("kind") != "text" or not (l.get("text") or "").strip():
            continue
        t = (l["start_frame"] + l["end_frame"]) / 2 / 30
        x0, y0 = int(max(0, l["x"]) * W), int(max(0, l["y"]) * H)
        x1, y1 = int(min(1, l["x"] + l["width"]) * W), int(min(1, l["y"] + l["height"]) * H)
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        r = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0}",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
        if not r.stdout:
            continue
        px = np.frombuffer(r.stdout, np.uint8).reshape(-1, 3)
        bg = np.median(px, 0)
        fg = tuple(int((l.get("color") or "#ffffff").lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        a, b = lum(fg), lum(bg)
        ratio = (max(a, b) + .05) / (min(a, b) + .05)
        size = style.typography(l.get("typography_role") or "label")["size"] if l.get("typography_role") else (l.get("font_size") or 32)
        need = style.get("label.contrast_min_large") if size >= large_px else style.get("label.contrast_min")
        if ratio < need:
            out.append({"id": l["id"], "ratio": round(ratio, 2), "needs": need, "at_s": round(t, 2)})
    return out


MEANT_MAX_S = {"deliberate_black": 3.0, "deliberate_still": 8.0}  # an editor's black or held card, never a scene's worth


def _mean_luma(video, start, seconds):
    """Mean 8-bit luma of a stretch (mid 60 %, 6 frames a second)."""
    from .media import FFMPEG
    a, n = start + seconds * .2, max(.1, seconds * .6)
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{a:.3f}", "-i", str(video), "-t", f"{n:.3f}", "-vf", "fps=6,scale=160:90,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    return round(float(np.frombuffer(raw, np.uint8).mean()), 1) if raw else None


def delivery_gates(video, timeline=None, lang="vi"):
    """The cheap delivery gates in one report, cheapest first: legal levels, flashes, still pictures, cuts to black,
    banding, then (with the timeline) text holds and text contrast. Returns {"pass", "gates": {...}}. A gate that cannot
    run (a decoder out of memory) is reported as an error and fails the report; it never stops the other gates."""
    g, errors = {}, {}
    for name, fn in (("legal_levels", lambda: legal_levels(video)), ("flashes", lambda: flashes(video)), ("still", lambda: still_runs(video)),
                     ("black", lambda: black_cuts(video)), ("banding", lambda: banding(video))):
        try:
            g[name] = fn()
        except Exception as e:  # noqa: BLE001 - reported, and the report fails
            errors[name] = f"{type(e).__name__}: {str(e)[:300]}"
    if timeline:
        for name, fn in (("text_holds", lambda: text_holds(timeline, lang)), ("text_contrast", lambda: text_contrast(video, timeline))):
            try:
                g[name] = fn()
            except Exception as e:  # noqa: BLE001
                errors[name] = f"{type(e).__name__}: {str(e)[:300]}"
        # an editor's black (the silence before a hit) or held card is declared on the timeline by a null layer with
        # data.intent; a black or still inside one is reported as intended. A declared black must BE black (grain
        # over it lifted the first montage's gap to RGB 42) and no marker excuses more than MEANT_MAX_S.
        fps = timeline.get("fps", 30)
        meant = {k: [(l["start_frame"] / fps, l["end_frame"] / fps) for l in timeline.get("layers", [])
                     if l.get("kind") == "null" and (l.get("data") or {}).get("intent") == k] for k in MEANT_MAX_S}
        g["intent"] = []
        for k, spans in meant.items():
            for lo, hi in spans:
                row = {"intent": k, "start_s": round(lo, 2), "seconds": round(hi - lo, 2)}
                if hi - lo > MEANT_MAX_S[k]:
                    row["too_long"] = True
                if k == "deliberate_black":
                    row["luma"] = _mean_luma(video, lo, hi - lo)
                    row["not_black"] = row["luma"] is None or row["luma"] > 16
                g["intent"].append(row)
        ok_spans = {k: [(lo - .1, hi + .1) for lo, hi in v if hi - lo <= MEANT_MAX_S[k]] for k, v in meant.items()}
        inside = lambda a, n, spans: any(lo <= a and a + n <= hi for lo, hi in spans)
        for b in g.get("black", []):
            if inside(b["start_s"], b["seconds"], ok_spans["deliberate_black"]):
                b["intended"] = True
        for r in (g.get("still") or {}).get("runs", []):
            if inside(r["start_s"], r["seconds"], ok_spans["deliberate_black"] + ok_spans["deliberate_still"]):
                r["intended"] = True
    if errors:
        g["errors"] = errors
    ok = (not errors and g["legal_levels"]["frames"] <= 15 and not g["flashes"]["fails"] and g["banding"]["longest_run"] < 12
          and not any(b.get("hard") and not b.get("intended") for b in g["black"]) and not g.get("text_holds") and not g.get("text_contrast")
          and not any(r.get("too_long") or r.get("not_black") for r in g.get("intent", [])))
    return {"pass": ok, "gates": g}
