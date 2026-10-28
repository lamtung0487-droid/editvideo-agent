"""Semantic sight for edits: what is in the frame, not only how it moves.

- detect(): open-vocabulary boxes for text queries ("rally car", "bird", "plate of food") on sampled frames, with
  OWLv2 base/16 ensemble (google/owlv2-base-patch16-ensemble, Apache-2.0; LVIS rare-class AP 40.5 zero-shot).
  Each query is scored on its own, so "is X here and how big" is a direct reading; a hit needs two neighbouring
  sampled frames, boxes are merged by non-maximum suppression, and the clip's spans of presence come back.
- search(): rank windows across clips by a text query or a reference image with SigLIP base/16-224
  (google/siglip-base-patch16-224, Apache-2.0), on three square crops per frame (SigLIP squashes a 16:9 frame).

Both run offline after install(allow_download=True) (pinned revisions, file hashes checked, ~1.44 GB together).
Measured presence and similarity, not understanding: a spectator's hand is still a "person"; actions ("drifting"),
relations ("in the hairpin"), identity and counting are beyond them; text visible in a frame pulls similarity; scores
compare only within one query. Look at the returned sheet.
"""
import hashlib
import json
import math
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from . import store
from .media import FFMPEG, display_size, probe, sha256

MODELS = {
    "owlv2": {"repo": "google/owlv2-base-patch16-ensemble", "revision": "cfd3195ba4ea9592eec887ded089f4c08eff231d", "license": "Apache-2.0",
              "files": ["config.json", "preprocessor_config.json", "tokenizer_config.json", "special_tokens_map.json", "added_tokens.json",
                        "vocab.json", "merges.txt", "model.safetensors"]},
    "siglip": {"repo": "google/siglip-base-patch16-224", "revision": "7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed", "license": "Apache-2.0",
               "files": ["config.json", "preprocessor_config.json", "tokenizer_config.json", "special_tokens_map.json", "spiece.model",
                         "tokenizer.json", "model.safetensors"]},
}
MAX_SECONDS = 180


def model_root(name):
    """The model's folder: under the data root, else the repository's data/models. Models belong to the installation, not
    to a project store: with EDITVIDEO_DATA on another drive (round 13 keeps projects on G:) SigLIP stayed installed in
    the repository's data/models and was reported missing."""
    return store.models_root(f"{name}/install.json") / name


def install(allow_download=False, names=("owlv2", "siglip")):
    """Verify (or, with allow_download, fetch) the pinned models: every file's SHA-256 against the hub's record."""
    import httpx
    out = {}
    for name in names:
        spec, root = MODELS[name], model_root(name)
        manifest = root / "install.json"
        if manifest.exists():
            rec = store.read_json(manifest)
            # hashed once per file state (size, mtime): 1.4 GB is not re-read at every load
            seen, fresh = rec.get("verified") or {}, {}
            for f, d in rec["files"].items():
                fp = root / f
                key = [fp.stat().st_size, fp.stat().st_mtime_ns] if fp.is_file() else None
                if rec.get("revision") != spec["revision"] or key is None or (seen.get(f) != key and sha256(fp) != d):
                    raise ValueError(f"{name}: installed files changed; reinstall the pinned revision")
                fresh[f] = key
            if fresh != seen:
                store.write_json(manifest, {**rec, "verified": fresh})
            out[name] = {k: rec[k] for k in ("repo", "revision", "license")}
            continue
        if not allow_download:
            raise ValueError(f"{name} not installed: {spec['repo']} ({spec['license']}); ask the user, then install with allow_download=true")
        root.mkdir(parents=True, exist_ok=True)
        files = {}
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            meta = client.get(f"https://huggingface.co/api/models/{spec['repo']}/revision/{spec['revision']}", params={"blobs": "true"})
            meta.raise_for_status()
            sib = {s["rfilename"]: s for s in meta.json()["siblings"]}
            for f in spec["files"]:
                part = root / (f + ".part")
                with client.stream("GET", f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{f}") as r:
                    r.raise_for_status()
                    with open(part, "wb") as h:
                        for chunk in r.iter_bytes(1 << 20):
                            h.write(chunk)
                digest, want = sha256(part), (sib.get(f, {}).get("lfs") or {}).get("sha256")
                if want and digest != want:
                    part.unlink()
                    raise ValueError(f"{name}/{f}: SHA-256 differs from the hub record")
                if sib.get(f, {}).get("size") and part.stat().st_size != sib[f]["size"]:
                    part.unlink()
                    raise ValueError(f"{name}/{f}: size differs from the hub record")
                part.replace(root / f)
                files[f] = digest
        rec = {"repo": spec["repo"], "revision": spec["revision"], "license": spec["license"], "files": files}
        store.write_json(manifest, rec)
        out[name] = {k: rec[k] for k in ("repo", "revision", "license")}
    return out


_LOADED = {}


def _device():
    import torch
    return ("cuda", torch.float16) if torch.cuda.is_available() else ("cpu", torch.float32)


def _owl():
    if "owlv2" not in _LOADED:
        install(False, ("owlv2",))
        from transformers import Owlv2ForObjectDetection, Owlv2Processor
        dev, dt = _device()
        _LOADED["owlv2"] = (Owlv2Processor.from_pretrained(model_root("owlv2"), use_fast=True),  # the fast processor: ~2x the frames per second
                            Owlv2ForObjectDetection.from_pretrained(model_root("owlv2"), dtype=dt).to(dev).eval())
    return _LOADED["owlv2"]


def _siglip():
    if "siglip" not in _LOADED:
        install(False, ("siglip",))
        from transformers import AutoModel, AutoProcessor
        dev, dt = _device()
        _LOADED["siglip"] = (AutoProcessor.from_pretrained(model_root("siglip"), use_fast=True),
                             AutoModel.from_pretrained(model_root("siglip"), dtype=dt).to(dev).eval())
    return _LOADED["siglip"]


def _key(path, *extra):
    p = Path(path).resolve(strict=True)
    st = p.stat()
    return hashlib.sha256("|".join(map(str, (p, st.st_size, st.st_mtime_ns, *extra))).encode()).hexdigest()[:24]


def frames(path, fps=1.0, width=960, start=0.0, end=None):
    """RGB frames sampled at fps (times in source seconds), at most MAX_SECONDS; a still image is one frame at 0."""
    from PIL import ImageOps
    p = Path(path)
    w0, h0 = display_size(p)  # as shown: FFmpeg rotates phone video while decoding, browsers apply EXIF orientation
    h = int(round(width * h0 / w0 / 2) * 2)
    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"):
        with Image.open(p) as im:
            return [0.0], [np.asarray(ImageOps.exif_transpose(im).convert("RGB").resize((width, h)))]
    dur = float(probe(str(p))["format"].get("duration") or 0)
    end = min(dur, end if end is not None else dur, start + MAX_SECONDS)
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{max(0.0, end - start):.3f}", "-i", str(p), "-vf",
                          f"fps={fps},scale={width}:{h}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    arr = np.frombuffer(raw, np.uint8).reshape(-1, h, width, 3)
    return [round(start + (i + .5) / fps, 2) for i in range(len(arr))], list(arr)


def _square(img):
    """Pad to a square with black at the right/bottom, as OWLv2 expects (4.57's own pad is grey), boxes stay in place."""
    h, w = img.shape[:2]
    s = max(h, w)
    out = np.zeros((s, s, 3), np.uint8)
    out[:h, :w] = img
    return Image.fromarray(out), s


def _detect_frames(imgs, queries, threshold):
    import torch
    from torchvision.ops import nms
    proc, model = _owl()
    dev, dt = _device()
    found = []
    for i in range(0, len(imgs), 4):
        batch = [_square(x) for x in imgs[i:i + 4]]
        inp = proc(text=[queries] * len(batch), images=[b[0] for b in batch], return_tensors="pt")
        inp = {k: (v.to(dev, dt) if v.is_floating_point() else v.to(dev)) for k, v in inp.items()}
        with torch.no_grad():
            out = model(**inp)
        post = getattr(proc, "post_process_object_detection", None) or proc.image_processor.post_process_object_detection  # transformers 5 moved it
        res = post(outputs=out, threshold=threshold, target_sizes=torch.tensor([[s, s] for _, s in batch]))
        for (img, s), r, src in zip(batch, res, imgs[i:i + 4]):
            h, w = src.shape[:2]
            hits = []
            for q in range(len(queries)):
                m = r["labels"] == q
                if not m.any():
                    continue
                boxes, scores = r["boxes"][m].float(), r["scores"][m].float()
                for k in nms(boxes, scores, .5)[:5].tolist():
                    x0, y0, x1, y1 = boxes[k].tolist()
                    b = [max(0, x0 / w), max(0, y0 / h), min(1, x1 / w), min(1, y1 / h)]
                    if b[2] > b[0] and b[3] > b[1]:
                        hits.append({"q": q, "score": round(float(scores[k]), 3), "box": [round(x, 3) for x in b]})
            found.append(hits)
    return found


def detect(paths, queries, fps=1.0, threshold=.12, min_hits=2):
    """Where each query appears in each clip: spans (seconds), the best view (time, score, box, area share) and the
    share of sampled frames that show it. Cached per file, queries, rate and threshold."""
    if not 1 <= len(paths) <= 40 or not 1 <= len(queries) <= 8 or not .2 <= fps <= 4:
        raise ValueError("1..40 paths, 1..8 queries, fps .2..4")
    queries = [q.strip().lower() for q in queries if q.strip()]
    cache = store.DATA / "cache" / "semantic"
    cache.mkdir(parents=True, exist_ok=True)
    clips, sheet_rows = {}, []
    for path in paths:
        f = cache / f"det-{_key(path, fps, threshold, '|'.join(queries), 'shown')}.json"  # 'shown': frames as displayed (rotation, pixel aspect)
        if f.is_file():
            rec = store.read_json(f)
        else:
            times, imgs = frames(path, fps)
            rec = {"times": times, "hits": _detect_frames(imgs, queries, threshold)}
            store.write_json(f, rec)
        per = {}
        for qi, q in enumerate(queries):
            seen = [max((h for h in hits if h["q"] == qi), key=lambda h: h["score"] * math.sqrt((h["box"][2] - h["box"][0]) * (h["box"][3] - h["box"][1])), default=None)
                    for hits in rec["hits"]]
            on = [s is not None for s in seen]
            if min_hits > 1 and len(on) > 1:  # one lone frame is more often a false hit than a real one (a still has one frame)
                on = [o and ((i > 0 and on[i - 1]) or (i + 1 < len(on) and on[i + 1])) for i, o in enumerate(on)]
            spans, a = [], None
            for i, o in enumerate(on + [False]):
                if o and a is None:
                    a = i
                elif not o and a is not None:
                    s0, s1 = round(max(0, rec["times"][a] - .5 / fps), 2), round(rec["times"][i - 1] + .5 / fps, 2)
                    if spans and s0 - spans[-1][1] <= 1 / fps + 1e-6:  # one missed sample inside a presence: flicker, not an exit
                        spans[-1][1] = s1
                    else:
                        spans.append([s0, s1])
                    a = None
            best_i = max((i for i in range(len(seen)) if on[i]), default=None,
                         key=lambda i: seen[i]["score"] * math.sqrt((seen[i]["box"][2] - seen[i]["box"][0]) * (seen[i]["box"][3] - seen[i]["box"][1])))
            if best_i is not None:
                b = seen[best_i]
                per[q] = {"spans": spans, "share": round(sum(on) / max(1, len(on)), 2),
                          "best": {"at": rec["times"][best_i], "score": b["score"], "box": b["box"],
                                   "area": round((b["box"][2] - b["box"][0]) * (b["box"][3] - b["box"][1]), 3)},
                          "track": [[rec["times"][i], seen[i]["box"]] for i in range(len(seen)) if on[i]]}  # whole: callers rank windows anywhere in the clip
                sheet_rows.append((path, q, rec["times"][best_i], b["box"], b["score"]))
            else:
                per[q] = {"spans": [], "share": 0.0}
        clips[str(Path(path).resolve())] = per
    return {"clips": clips, "queries": queries, "sheet": str(_sheet(sheet_rows, "det")),
            "method": f"OWLv2 base/16 ensemble at {fps} fps, threshold {threshold}, NMS .5, a hit needs a neighbouring sampled frame; boxes are frame shares [x0,y0,x1,y1]."}


def to_canvas(box, source_w, source_h, canvas_w, canvas_h, fit="cover", focus_x=.5, focus_y=.5):
    """A box in source-frame shares [x0,y0,x1,y1] -> canvas shares, through a shot's fit and focus (before any zoom
    effect). A detected subject on a 4:3 photo framed 16:9 sits elsewhere on the canvas than in the photo."""
    k = max(canvas_w / source_w, canvas_h / source_h) if fit == "cover" else min(canvas_w / source_w, canvas_h / source_h)
    ox, oy = (canvas_w - source_w * k) * focus_x, (canvas_h - source_h * k) * focus_y
    return [(box[0] * source_w * k + ox) / canvas_w, (box[1] * source_h * k + oy) / canvas_h,
            (box[2] * source_w * k + ox) / canvas_w, (box[3] * source_h * k + oy) / canvas_h]


def frame_subject(box, source_w, source_h, canvas_w, canvas_h, fill=.86, region=(0, 0, 1, 1)):
    """Shot framing that keeps a subject box (source shares) whole, inside `region` (canvas shares, the area titles leave
    free; default the whole canvas) and as large as `fill` of it allows, centred in it: cover when that holds there;
    else contain with the subject centred, enlarged by a held focus_zoom cut (up to 2x, about the point that centres
    it). Scaling a shot never reveals more of its source, so a subject too wide for cover is framed up from contain;
    the uncovered bands show the timeline's design background (set it to the footage's own black or colour).
    A subject that runs off its source frame (box within 1 % of an edge) would end in a straight cut floating in the
    canvas where a contained picture leaves bands: those picture edges fade into the background (edge_feather box).
    Returns {fit, focus_x, focus_y, effects, subject, inside_region, cut_edges} (subject = its canvas box; cut_edges =
    the source edges it touches); inside_region is false when no framing fits it there."""
    x0, y0, x1, y1 = (min(1.0, max(0.0, float(v))) for v in box)
    if x1 - x0 <= 1e-4 or y1 - y0 <= 1e-4 or min(region[2] - region[0], region[3] - region[1]) <= 0:
        raise ValueError("box and region are [x0, y0, x1, y1] shares with x0 < x1 and y0 < y1")
    kc, kn = max(canvas_w / source_w, canvas_h / source_h), min(canvas_w / source_w, canvas_h / source_h)
    cl = lambda v: round(min(1.0, max(0.0, v)), 4)
    at = ((region[0] + region[2]) / 2, (region[1] + region[3]) / 2)
    fw, fh = fill * (region[2] - region[0]), fill * (region[3] - region[1])
    inside = lambda b: b[0] >= region[0] - 2e-3 and b[1] >= region[1] - 2e-3 and b[2] <= region[2] + 2e-3 and b[3] <= region[3] + 2e-3
    cut = [n for n, hit in (("left", x0 <= .01), ("top", y0 <= .01), ("right", x1 >= .99), ("bottom", y1 >= .99)) if hit]

    def out(fit, fx, fy, b, effects=()):
        effects = list(effects)
        if fit == "contain":  # the picture's own edges, before any zoom (the mask moves with the element)
            band = to_canvas([0, 0, 1, 1], source_w, source_h, canvas_w, canvas_h, "contain", fx, fy)
            floating = ({"top", "bottom"} & set(cut) and (band[1] > .005 or band[3] < .995)) or ({"left", "right"} & set(cut) and (band[0] > .005 or band[2] < .995))
            if floating:
                effects.append({"name": "edge_feather", "start_frame": 0, "end_frame": 1, "params": {"amount": .12, "box": [round(v, 4) for v in band]}})
        return {"fit": fit, "focus_x": fx, "focus_y": fy, "effects": effects, "subject": [round(v, 3) for v in b], "inside_region": inside(b), "cut_edges": cut}
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    # the focus that brings the subject's centre to `at` on the axis where the scaled source is longer (cover) or
    # shorter (contain) than the canvas: (n - s k) f + c s k = a n
    centre = lambda c, s, n, k, a: cl((a * n - c * s * k) / (n - s * k)) if abs(n - s * k) > 1e-6 else .5
    fx, fy = centre(cx, source_w, canvas_w, kc, at[0]), centre(cy, source_h, canvas_h, kc, at[1])
    cb = to_canvas([x0, y0, x1, y1], source_w, source_h, canvas_w, canvas_h, "cover", fx, fy)
    if cb[2] - cb[0] <= fw + 1e-6 and cb[3] - cb[1] <= fh + 1e-6 and inside(cb):
        return out("cover", fx, fy, cb)
    fx, fy = centre(cx, source_w, canvas_w, kn, at[0]), centre(cy, source_h, canvas_h, kn, at[1])
    nb = to_canvas([x0, y0, x1, y1], source_w, source_h, canvas_w, canvas_h, "contain", fx, fy)
    s = min(2.0, fw / (nb[2] - nb[0]), fh / (nb[3] - nb[1]))
    px, py = (nb[0] + nb[2]) / 2, (nb[1] + nb[3]) / 2
    if s <= 1.001:  # as large as it can be at contain already (inside_region says whether it fits there)
        return out("contain", fx, fy, nb)
    # scale s about the origin o that lands the subject's centre p on `at`: o + (p - o) s = a
    ox, oy = cl((s * px - at[0]) / (s - 1)), cl((s * py - at[1]) / (s - 1))
    sub = [ox + (nb[0] - ox) * s, oy + (nb[1] - oy) * s, ox + (nb[2] - ox) * s, oy + (nb[3] - oy) * s]
    return out("contain", fx, fy, sub, [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1,
                                          "params": {"amount": round(s - 1, 4), "focus_x": ox, "focus_y": oy, "cut": True}}])


def _crops(img):
    """Three squares along the long side (SigLIP squashes the frame to a square; subjects at the edges survive)."""
    h, w = img.shape[:2]
    s = min(h, w)
    if w >= h:
        xs = [0, (w - s) // 2, w - s]
        return [img[:, x:x + s] for x in xs]
    ys = [0, (h - s) // 2, h - s]
    return [img[y:y + s] for y in ys]


def _image_vectors(imgs):
    import torch
    proc, model = _siglip()
    dev, dt = _device()
    out = []
    for i in range(0, len(imgs), 16):
        crops = [Image.fromarray(c) for x in imgs[i:i + 16] for c in _crops(x)]
        px = proc(images=crops, return_tensors="pt")["pixel_values"].to(dev, dt)
        with torch.no_grad():
            v = model.get_image_features(pixel_values=px).float()
        v = torch.nn.functional.normalize(v, dim=-1).cpu().numpy().reshape(-1, 3, v.shape[-1])
        out.append(v)
    return np.concatenate(out).astype(np.float16)


def _text_vector(text):
    import torch
    proc, model = _siglip()
    dev, _ = _device()
    tok = proc(text=[text], padding="max_length", return_tensors="pt")  # SigLIP was trained on max-length padding
    with torch.no_grad():
        v = model.get_text_features(input_ids=tok["input_ids"].to(dev)).float()
    return torch.nn.functional.normalize(v, dim=-1).cpu().numpy()[0]


def embeddings(path, fps=1.0, whole=False):
    """SigLIP vectors of frames sampled at fps: the first MAX_SECONDS (search), or with whole=True the entire video, read
    in MAX_SECONDS chunks so a feature-length film never sits in memory at once (round 13: a 96-minute reference read as
    its first three minutes)."""
    cache = store.DATA / "cache" / "semantic"
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"emb-{_key(path, fps, 'shown', *(('whole',) if whole else ()))}.npz"  # search's cached keys stay valid
    if f.is_file():
        d = np.load(f)
        return list(d["times"]), d["vecs"]
    if not whole:
        times, imgs = frames(path, fps, width=448)
        vecs = _image_vectors(imgs)
    else:
        dur = float(probe(str(path))["format"].get("duration") or 0)
        times, parts = [], []
        for a in np.arange(0.0, max(dur, 1e-3), MAX_SECONDS):
            t, imgs = frames(path, fps, width=448, start=float(a), end=float(min(dur, a + MAX_SECONDS)))
            if imgs:
                times += t
                parts.append(_image_vectors(imgs))
        vecs = np.concatenate(parts) if parts else np.zeros((0, 3, 768), np.float16)
    np.savez(f, times=np.array(times), vecs=vecs)
    return times, vecs


def search(paths, text=None, image=None, window_s=2.0, top=10, fps=1.0):
    """Windows ranked by similarity to a text query or a reference image ({"path", "at"} seconds into a clip or a
    still): the best crop per frame, the window's best frame. Scores are relative to the best window (1.0)."""
    if bool(text) == bool(image):
        raise ValueError("pass text or image")
    if text:
        q = _text_vector(text)
    else:
        ip = Path(image["path"])
        _, imgs = frames(ip, fps=1, width=448, start=float(image.get("at", 0)), end=float(image.get("at", 0)) + 1)
        q = _image_vectors(imgs[:1])[0].astype(np.float32).mean(axis=0)
        q /= np.linalg.norm(q) + 1e-9
    rows = []
    for path in paths:
        times, vecs = embeddings(path, fps)
        sim = (vecs.astype(np.float32) @ q).max(axis=1)  # the best of three crops
        n = max(1, int(round(window_s * fps)))
        for a in range(0, max(1, len(sim) - n + 1), max(1, n // 2)):
            w = sim[a:a + n]
            i = a + int(np.argmax(w))
            rows.append({"path": str(Path(path).resolve()), "start": round(max(0, times[a] - .5 / fps), 2), "end": round(times[min(len(times) - 1, a + n - 1)] + .5 / fps, 2),
                         "at": times[i], "score": float(w.max())})
    best, top_score = [], max((r["score"] for r in rows), default=1.0)
    for r in sorted(rows, key=lambda r: -r["score"]):
        if any(o["path"] == r["path"] and o["start"] < r["end"] and r["start"] < o["end"] for o in best):
            continue
        best.append({**r, "score": round(r["score"] / (top_score or 1), 3)})
        if len(best) >= top:
            break
    sheet = _sheet([(r["path"], text or "image", r["at"], None, r["score"]) for r in best], "search")
    return {"windows": best, "sheet": str(sheet), "method": f"SigLIP base/16-224 at {fps} fps, best of three square crops; scores relative "
            "to the best window (compare within this query only)."}


def _sheet(rows, kind):
    """A contact sheet of the hits: frame, box (detect), label and score."""
    tiles = []
    for path, label, at, box, score in rows[:24]:
        try:
            _, imgs = frames(path, fps=1, width=320, start=max(0.0, at - .5), end=at + .5)
        except Exception:
            continue
        if not imgs:
            continue
        im = Image.fromarray(imgs[0])
        d = ImageDraw.Draw(im)
        w, h = im.size
        if box:
            d.rectangle([box[0] * w, box[1] * h, box[2] * w, box[3] * h], outline=(255, 220, 0), width=2)
        d.rectangle([0, 0, w, 14], fill=(0, 0, 0))
        d.text((3, 1), f"{Path(path).stem[:18]} {at:.1f}s {label[:14]} {score:.2f}", fill=(255, 220, 0))
        tiles.append(im)
    out = store.DATA / "observations" / f"{kind}-{hashlib.sha256(json.dumps([r[:3] for r in rows], default=str).encode()).hexdigest()[:16]}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    if tiles:
        cols, h = 4, max(t.size[1] for t in tiles)
        sheet = Image.new("RGB", (cols * 324, ((len(tiles) + cols - 1) // cols) * (h + 4)), (16, 16, 16))
        for k, t in enumerate(tiles):
            sheet.paste(t, ((k % cols) * 324, (k // cols) * (h + 4)))
        sheet.save(out, quality=85)
    else:
        Image.new("RGB", (320, 40), (16, 16, 16)).save(out)
    return out


def focus_for_faces(boxes, source_w, source_h, canvas_w, canvas_h, band_top=0.0, band_bottom=0.0, third=1 / 3):
    """focus_y for a cover-fitted shot so the people in it keep their heads (round 13, the fifth cut: 4:3 archive filled
    to 16:9 shows 75 % of its height, and a centred crop cut foreheads off; letterbox bars covered more). boxes: face (or
    head) boxes as source shares [x0, y0, x1, y1] seen over the shot. The faces' centre goes `third` of the way down the
    picture left visible between the bars, then the window moves the least needed for every face to sit whole between
    them. Returns {"focus_y", "visible", "kept": all faces whole} — focus_y .5 when the shot is not cropped vertically."""
    kc = max(canvas_w / source_w, canvas_h / source_h)
    v = min(1.0, canvas_h / kc / source_h)  # share of the source height on the canvas
    if v >= .999 or not boxes:
        return {"focus_y": .5, "visible": round(v, 4), "kept": True}
    top_free, bot_free = v * band_top, v * (1 - band_bottom)  # the part of the visible window the bars leave clear
    y0 = min(b[1] for b in boxes)
    y1 = max(b[3] for b in boxes)
    cy = sum((b[1] + b[3]) / 2 for b in boxes) / len(boxes)
    top = cy - (top_free + third * (bot_free - top_free))  # source share at the window's top edge
    top = min(top, y0 - top_free - .01)                    # every face below the top bar
    top = max(top, y1 - bot_free + .01)                    # and above the bottom one
    top = min(max(top, 0.0), 1.0 - v)
    kept = top + top_free <= y0 + 1e-6 and y1 <= top + bot_free + 1e-6
    return {"focus_y": round(top / (1.0 - v), 4), "visible": round(v, 4), "kept": bool(kept)}
