"""Archive photo projection (reports/Nâng cấp 3D phim tài liệu.md, P1-5): a photograph's own pixels laid on the shape
MoGe-2 recovers from it, and a camera that moves a little through that space. The pixels stay the archive's; only the
camera is new, so the shot is an illustration of the photograph, not a reconstruction of the place.

1. estimate: MoGe-2 (Microsoft, MIT code and weights) in its own process gives points, depth, a validity mask and the
   field of view; cached by the image's bytes.
2. build: a mesh on a grid over the points, with the faces removed where the depth jumps (a person in front of a
   wall must not stretch into it like rubber), and a plate at the far depth: the photograph with the near side of
   every depth edge filled by OpenCV (Telea), so a camera that looks behind an edge sees plausible background, never
   the same object twice. The fill is algorithmic, not generative, and logged with its share of the frame.
3. move: the camera keys are scaled down until the largest reveal behind an edge stays under `reveal_limit` of the
   frame width (1.5 % by default); the shot then shows depth without showing what the photograph never saw.
4. shot: Blender (photo_projection template, emission under the Standard view, so the first frame is the photograph)
   and an encode.
Faces of people are better kept flat (a small move, or a crop without them): depth on a face is the weakest part.
"""
import json, math, os, subprocess, sys
from pathlib import Path
import numpy as np
from . import store
from .media import sha256

# installed beside the store (<drive>/EditVideo-data/models/moge for a store at <drive>/EditVideo-data/store) or in models/
MOGE = Path(os.environ.get("EDITVIDEO_MOGE") or next((c for c in (store.DATA.parent / "models" / "moge", store.models_root("moge") / "moge")
                                                      if c.is_dir()), store.DATA.parent / "models" / "moge"))
RUNNER = Path(__file__).with_name("archive3d_runner.py")


def available():
    return (MOGE / "code" / "moge" / "model" / "v2.py").is_file() and (MOGE / "moge-2-vitl-normal" / "model.pt").is_file()


def _cache(image):
    d = store.DATA / "cache" / "archive3d" / sha256(image)[:16]
    d.mkdir(parents=True, exist_ok=True)
    return d


def estimate(image, timeout=900):
    """MoGe-2 geometry of a photograph: {"npz", "fov_x", "fov_y", "depth": [p5, p50, p95], "valid"} (cached)."""
    if not available():
        raise RuntimeError(f"MoGe-2 is not installed under {MOGE} (code/moge and moge-2-vitl-normal/model.pt; set EDITVIDEO_MOGE)")
    d = _cache(image)
    out = d / "moge.npz"
    if not out.is_file():
        with store.gpu_admission(what="MoGe depth"):  # MoGe loads on the GPU: never beside a render or a Blender job
            r = subprocess.run([sys.executable, "-I", str(RUNNER), str(Path(image).resolve()), str(out), str(MOGE)], capture_output=True, text=True,
                               errors="replace", timeout=timeout)
        if r.returncode or not out.is_file():
            raise RuntimeError("MoGe-2 failed: " + (r.stderr or r.stdout)[-1500:])
    g = np.load(out)
    K, depth, mask = g["intrinsics"], g["depth"], g["mask"]
    fov_x, fov_y = 2 * math.atan(.5 / float(K[0, 0])), 2 * math.atan(.5 / float(K[1, 1]))  # MoGe's intrinsics are normalised
    v = depth[mask & np.isfinite(depth)]
    return {"npz": str(out), "fov_x": fov_x, "fov_y": fov_y, "depth": [round(float(np.percentile(v, q)), 4) for q in (5, 50, 95)],
            "valid": round(float(mask.mean()), 3), "size": [int(x) for x in g["size"]]}


def _edges(depth, valid, rtol):
    """Pixels where the depth jumps by more than rtol (relative) within their 3x3 neighbourhood."""
    from scipy.ndimage import maximum_filter, minimum_filter
    z = np.where(valid, depth, np.nan)
    hi = maximum_filter(np.nan_to_num(z, nan=0.0), 3)
    lo = minimum_filter(np.nan_to_num(z, nan=np.inf), 3)
    return (hi / np.maximum(lo, 1e-6) > 1 + rtol) & valid


def build(image, est, max_faces=1_600_000, rtol=.04, fill_px=None):
    """mesh.npz (verts in Blender space, uv, faces) and plate.png beside the estimate; returns their paths and the
    share of the frame the plate fill touched."""
    import cv2
    from PIL import Image
    d = Path(est["npz"]).parent
    g = np.load(est["npz"])
    pts, depth, mask = g["points"], g["depth"], g["mask"] & np.isfinite(g["depth"])
    H, W = depth.shape
    edge = _edges(depth, mask, rtol)
    # MoGe gives the sky no depth. The first build left it out of the mesh, so a bridge's hangers against the sky were
    # drawn once by the mesh and once more by the plate behind it as the camera moved. Now the sky is a far surface of
    # the mesh itself (just in front of the plate) and a hanger's edge stretches into it: a thin seam on a flat sky
    # instead of a doubled truss.
    K = g["intrinsics"]
    # behind everything measured: a river MoGe put at 30 units sat behind a plate at 1.6 x p95 and vanished under it
    zfar = float(np.percentile(depth[mask], 99.9))
    zs, zp = zfar * 1.15, zfar * 1.3
    uu, vv = np.meshgrid((np.arange(W) + .5) / W, (np.arange(H) + .5) / H)
    sky = np.stack([(uu - K[0, 2]) / K[0, 0] * zs, (vv - K[1, 2]) / K[1, 1] * zs, np.full_like(uu, zs)], -1).astype(np.float32)
    pts = np.where(mask[..., None], pts, sky)
    depth = np.where(mask, depth, zs)
    step = max(1, int(math.ceil(math.sqrt(H * W * 2 / max_faces))))
    ys, xs = np.arange(0, H, step), np.arange(0, W, step)
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    P = pts[gy, gx]
    ok = np.ones(gy.shape, bool)  # every cell is drawn but those straddling a jump between two measured depths
    vm = mask[gy, gx]
    # a grid cell is cut only when its own corners straddle a jump in depth: cutting every cell near an edge left a
    # rim around each hut and boat through which the filled plate showed on the very first frame
    Z = depth[gy, gx]
    h, w = P.shape[:2]
    idx = np.arange(h * w).reshape(h, w)
    a, b, c, e = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    corners = np.stack([Z[:-1, :-1], Z[:-1, 1:], Z[1:, :-1], Z[1:, 1:]], -1)
    jump = (corners.max(-1) / np.maximum(corners.min(-1), 1e-6) > 1 + max(rtol, .015 * step)) & vm[:-1, :-1] & vm[:-1, 1:] & vm[1:, :-1] & vm[1:, 1:]
    good = ok[:-1, :-1] & ok[:-1, 1:] & ok[1:, :-1] & ok[1:, 1:] & ~jump
    faces = np.concatenate([np.stack([a, c, b], -1)[good], np.stack([b, c, e], -1)[good]])
    used = np.unique(faces)
    remap = -np.ones(h * w, np.int64)
    remap[used] = np.arange(len(used))
    Pf = P.reshape(-1, 3)[used]
    verts = np.stack([Pf[:, 0], Pf[:, 2], -Pf[:, 1]], -1).astype(np.float32)  # OpenCV camera -> Blender
    uv = np.stack([(gx.ravel()[used] + .5) / W, 1 - (gy.ravel()[used] + .5) / H], -1).astype(np.float32)
    np.savez(d / "mesh.npz", verts=verts, faces=remap[faces].astype(np.int32), uv=uv)
    # the plate: what lies behind the rim of every near object is unknown, so near pixels within reach of an edge are
    # filled from the background around them. Two kinds of near: nearer than the ground around them, and anything
    # standing against the sky (MoGe gives the sky no depth: a bridge truss against it doubled when the plate kept its
    # pixels). The fill goes only UNDER the mesh, inside its border, so frame 0 is the photograph everywhere: where
    # the mesh draws, it hides the plate; where it does not (a thin truss, a gap at a depth jump), the plate shows the
    # photograph's own pixels. The reach is the widest reveal a planned move allows (1.5 % of the width).
    from scipy.ndimage import maximum_filter as mx
    fill_px = fill_px or max(6, int(W * .016))
    far = mx(np.where(mask, depth, 0), 2 * fill_px + 1)
    reach = cv2.dilate(edge.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=fill_px).astype(bool)
    near_obj = mask & (depth < far * (1 - rtol))
    cell = np.zeros((h - 1, w - 1), np.uint8)
    cell[good] = 1
    drawn = np.zeros((H, W), np.uint8)
    drawn[:(h - 1) * step, :(w - 1) * step] = np.kron(cell, np.ones((step, step), np.uint8))[:H, :W]
    core = cv2.erode(drawn, np.ones((3, 3), np.uint8), iterations=step + 1).astype(bool)
    hole = (near_obj & reach & core).astype(np.uint8)
    mk = np.zeros((H, W, 3), np.uint8)
    mk[drawn.astype(bool)] = (255, 0, 255)  # for the reveal check: magenta wherever the mesh hides the plate at frame 0
    Image.fromarray(mk).save(d / "drawn.png")
    img = np.asarray(Image.open(image).convert("RGB"))
    if img.shape[:2] != (H, W):
        img = np.asarray(Image.fromarray(img).resize((W, H), Image.LANCZOS))
    plate = cv2.inpaint(img[..., ::-1].copy(), hole, max(3, fill_px // 2), cv2.INPAINT_TELEA)[..., ::-1]
    Image.fromarray(plate).save(d / "plate.png")
    return {"mesh": str(d / "mesh.npz"), "plate": str(d / "plate.png"), "drawn": str(d / "drawn.png"), "plate_z": zp, "faces": int(len(faces)), "grid_step": step,
            "drawn_share": round(float(drawn.mean()), 4),
            "edge_share": round(float(edge.mean()), 4), "fill_share": round(float(hole.mean()), 4),
            "fill_method": "OpenCV Telea inpainting of the plate behind depth edges (algorithmic, not generative)"}


def _project(pts, cam, fx_px, cx, cy):
    """Pixel positions of Blender-space points seen from a camera key at (x, y, z) looking +Y (yaw/pitch ignored:
    keys keep them under a degree)."""
    rel = pts - np.array([cam.get("x", 0.0), cam.get("y", 0.0), cam.get("z", 0.0)])
    zf = np.maximum(rel[:, 1], 1e-4)
    return np.stack([cx + fx_px * rel[:, 0] / zf, cy - fx_px * rel[:, 2] / zf], -1)


def reveal_px(est, keys, width=1920, rtol=.04, samples=4000):
    """The widest gap (px at `width`) the camera keys open behind a depth edge: the near and far sides of edge
    pixels drift apart by this much between the first key and any other."""
    g = np.load(est["npz"])
    depth, mask, pts = g["depth"], g["mask"] & np.isfinite(g["depth"]), g["points"]
    edge = _edges(depth, mask, rtol)
    H, W = depth.shape
    yy, xx = np.nonzero(edge)
    if not len(yy):
        return 0.0
    sel = np.random.default_rng(0).choice(len(yy), min(samples, len(yy)), replace=False)
    yy, xx = yy[sel], xx[sel]
    from scipy.ndimage import maximum_filter, minimum_filter
    zmax = maximum_filter(np.where(mask, depth, 0), 9)[yy, xx]  # an estimate only: shot() measures the reveal on a render
    zmin = minimum_filter(np.where(mask, depth, np.inf), 9)[yy, xx]
    ray = pts[yy, xx] / np.maximum(depth[yy, xx], 1e-6)[:, None]  # unit-depth rays through the edge pixels
    near, far = ray * zmin[:, None], ray * zmax[:, None]
    to_b = lambda p: np.stack([p[:, 0], p[:, 2], -p[:, 1]], -1)
    fx = width / (2 * math.tan(est["fov_x"] / 2))
    base_n, base_f = _project(to_b(near), keys[0], fx, width / 2, 0), _project(to_b(far), keys[0], fx, width / 2, 0)
    worst = 0.0
    for k in keys[1:]:
        dn = _project(to_b(near), k, fx, width / 2, 0) - base_n
        df = _project(to_b(far), k, fx, width / 2, 0) - base_f
        worst = max(worst, float(np.percentile(np.linalg.norm(dn - df, axis=1), 99.5)))
    return round(worst, 1)


MOVES = {"push": {"y": .10}, "drift_left": {"x": -.05, "y": .03}, "drift_right": {"x": .05, "y": .03}, "rise": {"z": .04, "y": .04},
         "pull": {"y": -.08}}


def plan_move(est, move="push", frames=150, reveal_limit=.012, width=1920):
    """Camera keys for a named move, as shares of the median depth, scaled down until the reveal behind edges stays
    under reveal_limit of the frame width. Returns (keys, report)."""
    m = MOVES[move] if isinstance(move, str) else move
    zmed = est["depth"][1]
    scale, keys = 1.0, None
    for _ in range(12):
        end = {k: v * zmed * scale for k, v in m.items()}
        keys = [{"frame": 0}, {"frame": frames - 1, **end}]
        r = reveal_px(est, keys, width)
        if r <= reveal_limit * width:
            break
        scale *= .7
    return keys, {"move": move, "scale": round(scale, 3), "reveal_px": r, "limit_px": round(reveal_limit * width, 1)}


def frame0_check(image, frame_png, width=1920, height=1080):
    """How far the first rendered frame is from the photograph framed the same way (cover): mean absolute difference
    and the share of pixels off by more than 40 levels. The original camera must show the photograph."""
    from PIL import Image
    a = np.asarray(Image.open(frame_png).convert("RGB").resize((width, height)), np.float32)
    ph = Image.open(image).convert("RGB")
    k = max(width / ph.width, height / ph.height)
    ph = ph.resize((round(ph.width * k), round(ph.height * k)), Image.LANCZOS)
    x0, y0 = (ph.width - width) // 2, (ph.height - height) // 2
    b = np.asarray(ph.crop((x0, y0, x0 + width, y0 + height)), np.float32)
    dd = np.abs(a - b).max(-1)
    return {"mean_abs": round(float(np.abs(a - b).mean()), 2), "off_40": round(float((dd > 40).mean()), 4), "pass": bool((dd > 40).mean() < .005)}


def measure_reveal(image, est, geo, keys, frames, width=1920, height=1080):
    """The reveal a camera path really opens, measured on a render: the last key's frame with the mesh black and the
    plate magenta where the mesh covered it at frame 0. Returns {"share", "max_run_px" (the widest horizontal run of
    revealed plate, at `width`)}. The analytic estimate missed a boat's 50 px smear by half; this cannot."""
    from . import blender
    from PIL import Image
    params = {"mesh": geo["mesh"], "image": str(Path(image).resolve()), "plate": geo["plate"], "check_mask": geo["drawn"],
              "plate_z": geo["plate_z"], "near": est["depth"][0], "fov_x": est["fov_x"], "fov_y": est["fov_y"], "width": width, "height": height,
              "frames": frames, "camera": keys, "samples": 1, "percent": 50, "stills": [frames - 1]}
    r = blender.run("photo_projection", params, files=[geo["mesh"], geo["drawn"]])
    if r.get("error"):
        raise RuntimeError(r["error"][-800:])
    a = np.asarray(Image.open(Path(r["job"]) / f"still_{frames - 1:04d}.png").convert("RGB"), np.int16)
    mag = (a[..., 0] > 150) & (a[..., 1] < 90) & (a[..., 2] > 150)
    from scipy.ndimage import binary_opening
    mag = binary_opening(mag, np.ones((3, 3), bool))  # the one-pixel seams where the mesh and its mask rasterize apart
    e_ = max(1, round(mag.shape[1] * .01))  # picture entering or leaving at the frame's edge is the move itself, not a reveal
    mag[:, :e_] = mag[:, -e_:] = False
    mag[:e_, :] = mag[-e_:, :] = False
    from scipy.ndimage import distance_transform_edt
    k = width / a.shape[1]
    # the reveal is how THICK the revealed band gets (twice its deepest inside distance), not how long: a one-pixel
    # seam along a deck edge is 40 px long and nothing a viewer sees
    thick = 2 * float(distance_transform_edt(mag).max()) if mag.any() else 0.0
    # and the largest single patch: a 220 x 20 px streak of fill across the boats was thin but plainly visible
    from scipy.ndimage import label, binary_erosion
    thickp = binary_erosion(mag, np.ones((2 * max(1, round(3 / k)) + 1,) * 2, bool))  # only the parts thicker than ~6 px at 1920 read as a smear
    lab, n = label(thickp)
    biggest = float(np.bincount(lab.ravel())[1:].max()) / mag.size if n else 0.0  # the 220 x 20 px streak: ~.0011 of a frame after erosion
    return {"share": round(float(mag.mean()), 4), "max_run_px": round(thick * k, 1), "largest_patch": round(biggest, 5)}


def trim_border(image, max_share=.08, crop=None):
    """The photograph without its scan border: each side is trimmed while its line is much darker than the picture (a
    dark frame edge), at most max_share of the size. A flat line is not a border (it was a sky); a light label strip
    is not found here, so give `crop` = (left, top, right, bottom) shares for it. Returns the path of the trimmed copy
    (cached beside the estimates) or the image itself. A border left on broke into jagged blocks when the camera moved."""
    from PIL import Image
    im = Image.open(image).convert("RGB")
    a = np.asarray(im.convert("L"), np.float32)
    H, W = a.shape
    core = a[H // 8:-H // 8 or None, W // 8:-W // 8 or None]
    m0, s0 = float(np.median(core)), float(core.std())

    def edge(lines, n):
        k = 0
        for line in lines[:int(n * max_share)]:
            if line.mean() < .55 * m0:
                k += 1
            else:
                break
        return k
    if crop:
        left, top, right, bottom = (round(c_ * n) for c_, n in zip(crop, (W, H, W, H)))
    else:
        top, bottom = edge(a, H), edge(a[::-1], H)
        left, right = edge(a.T, W), edge(a.T[::-1], W)
    if not any((top, bottom, left, right)):
        return str(image)
    pad = lambda v: v + 2 if v else 0  # a couple of pixels past the line where the border fades into the picture
    out = _cache(image) / f"trimmed-{left}-{top}-{right}-{bottom}.jpg"
    if not out.is_file():
        im.crop((pad(left), pad(top), W - pad(right), H - pad(bottom))).save(out, quality=95)
    return str(out)


def shot(image, frames=150, move="push", width=1920, height=1080, reveal_limit=.015, patch_limit=.0008, stills=None, percent=100, samples=16,
         crf=16, trim=True, crop=None):
    """A projected archive shot: {"mp4" | "stills", "job", "report"}; the report lists the fill and the reveal."""
    from . import blender, ledger
    source = image
    if trim or crop:
        image = trim_border(image, crop=crop)
    est = estimate(image)
    geo = build(image, est)
    # the move: start from the analytic plan, then measure the real reveal on a render and scale until it fits
    keys, mv = plan_move(est, move, frames, reveal_limit * 2, width)
    m = MOVES[move] if isinstance(move, str) else move
    zmed, scale = est["depth"][1], 1.0  # the named move at full size first: the measurement only ever scales it down
    for _ in range(5):
        keys = [{"frame": 0}, {"frame": frames - 1, **{k: v * zmed * scale for k, v in m.items()}}]
        rv = measure_reveal(image, est, geo, keys, frames, width, height)
        if rv["max_run_px"] <= reveal_limit * width and rv["largest_patch"] <= patch_limit:
            break
        scale *= max(.35, min(.9 * reveal_limit * width / max(1.0, rv["max_run_px"]), (patch_limit / max(1e-9, rv["largest_patch"])) ** .5 * .9, .9))
    mv.update(scale=round(scale, 3), measured_reveal=rv, limit_px=round(reveal_limit * width, 1))
    params = {"mesh": geo["mesh"], "image": str(Path(image).resolve()), "plate": geo["plate"], "plate_z": geo["plate_z"],
              "near": est["depth"][0], "fov_x": est["fov_x"], "fov_y": est["fov_y"], "width": width, "height": height, "frames": frames,
              "camera": keys, "samples": samples, "percent": percent, "color_depth": 8,  # an 8-bit photograph: 8-bit frames (a third of the disk)
              **({"stills": list(stills)} if stills else {})}
    r = blender.run("photo_projection", params, files=[geo["mesh"], geo["plate"], image])
    if r.get("error"):
        raise RuntimeError(r["error"][-1500:])
    report = {**{k: est[k] for k in ("fov_x", "fov_y", "depth", "valid")}, **{k: geo[k] for k in ("faces", "grid_step", "edge_share", "fill_share", "fill_method")},
              **mv, "per_frame_s": r.get("per_frame_s"), "label": "3D illustration from an archive photograph (MoGe-2 depth, projected pixels)"}
    out = {"job": r["job"], "report": report, "cached": r.get("cached")}
    if stills:
        out["stills"] = [str(Path(r["job"]) / f"still_{f:04d}.png") for f in stills]
        if 0 in stills and percent == 100:
            report["frame0"] = frame0_check(image, out["stills"][0], width, height)
    else:
        report["frame0"] = frame0_check(image, str(Path(r["job"]) / "frame_0000.png"), width, height)
        out["mp4"] = blender.encode(r["job"], crf=crf, finish=False)
        # the clip carries its photograph's licence into every project that imports it
        e = ledger.find_entry(source)
        report["license"] = ledger.register_render(out["mp4"], f"3D illustration of {Path(source).name}",
                                                   [(e["license"], e["credit"]) if e else ("unknown (photograph not in the library)", Path(source).name)])["license"]
    (Path(r["job"]) / "archive3d.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
