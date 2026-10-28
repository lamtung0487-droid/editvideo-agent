"""Footage finishing tools professional editors expect: stabilization and subject-aware reframing.

Stabilize: KLT feature tracking + partial-affine RANSAC per frame → camera trajectory → smoothed (or locked) path →
warp with the smallest zoom that hides moving borders (capped). Reframe: crop a new aspect ratio that follows the
subject (tracked points or an automatic motion+saliency focus) with a dead zone so the virtual camera only moves when
the subject leaves the comfortable centre, then eases. Both are classical CV, deterministic, silent outputs.
"""
import math
import subprocess
from collections import deque
from typing import Literal
from pathlib import Path
import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store
from .media import FFMPEG, FFPROBE, probe


def _video_info(path):
    info = probe(path)
    s = next(x for x in info["streams"] if x["codec_type"] == "video")
    num, den = (s.get("r_frame_rate") or "30/1").split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den or 1), float(info["format"]["duration"])


def _frames(path, start, dur, w, h, fps=None):
    vf = f"scale={w}:{h}" + (f",fps={fps}" if fps else "")
    p = subprocess.Popen([FFMPEG, "-v", "error", "-ss", str(start), "-t", str(dur), "-i", str(path), "-vf", vf, "-f", "rawvideo",
                          "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    size = w * h * 3
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.wait()


def _encoder(target, w, h, fps, crf):
    return subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{fps:.6f}", "-i", "-",
                             "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-g", str(max(1, round(fps))),  # a keyframe a second: engines seek cleanly
                             "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
                             "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", str(target)], stdin=subprocess.PIPE)


def _with_source_audio(target, src, start, dur):
    """Mux the source's sound for the same window into a picture-only result (a steadied statement keeps its voice).
    The sound is padded or cut to the picture's length, never the reverse; the muxed file replaces the picture-only one
    only when its video stream still has the same frame count. Returns True when the sound was added."""
    has = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(src)],
                         capture_output=True, text=True).stdout.strip()
    if not has:
        return False
    frames = lambda f: subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets",
                                       "-of", "csv=p=0", str(f)], capture_output=True, text=True).stdout.strip()
    n0 = frames(target)
    vdur = float(probe(str(target))["format"]["duration"])
    tmp = target.with_name(target.stem + ".av.mp4")
    p = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(target), "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
                        "-map", "0:v", "-map", "1:a:0", "-c:v", "copy", "-af", "apad", "-c:a", "aac", "-b:a", "192k", "-t", f"{vdur:.3f}",
                        "-movflags", "+faststart", str(tmp)], capture_output=True, text=True)
    if p.returncode or not tmp.is_file() or not n0 or frames(tmp) != n0:
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(target)
    return True


def _smooth(x, radius):
    if radius < 1:
        return x.copy()
    k = np.exp(-.5 * (np.arange(-radius, radius + 1) / (radius / 2.5)) ** 2)
    k /= k.sum()
    pad = np.pad(x, (radius, radius), mode="edge")
    return np.convolve(pad, k, mode="valid")


class StabilizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    end: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    mode: str = Field(default="smooth", pattern="^(smooth|lock)$")  # lock = tripod: remove all camera motion
    smoothing_seconds: float = Field(default=1.0, ge=.1, le=10)
    max_zoom: float = Field(default=1.12, ge=1.0, le=1.5)
    max_width: int = Field(default=1920, ge=320, le=3840)
    crf: int = Field(default=17, ge=12, le=28)
    # Source-normalised [left, top, right, bottom] of the subject to hold still (at the window start). A handheld camera
    # that moves sees near and far things shift differently (parallax): a whole-frame lock holds neither; lock the subject.
    region: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def window(self):
        if self.end is not None and not self.start < self.end <= self.start + 60:
            raise ValueError("Stabilize window must be within 60 source seconds")
        if self.region and not (0 <= self.region[0] < self.region[2] <= 1 and 0 <= self.region[1] < self.region[3] <= 1):
            raise ValueError("region is normalised [left, top, right, bottom]")
        return self


def leashed_path(traj, target, leash, smooth_radius):
    """A camera path as close to `target` (constant for lock, smoothed for smooth) as the crop allows: it rides the real
    path's slow drift (a heavy low-pass) and moves toward the target only within the slack the shake leaves on the
    leash, so it never has to follow a shake to stay inside the crop. Where the real camera wanders further, the
    virtual one drifts slowly with it instead of jumping. traj, target: (n, k) arrays; leash: per-axis limits (k,)."""
    sm = lambda a, r: np.stack([_smooth(a[:, j], r) for j in range(a.shape[1])], axis=1)
    low = sm(traj, smooth_radius)
    shake = np.percentile(np.abs(traj - low), 99, axis=0)
    slack = np.maximum(0.0, leash - 1.1 * shake)
    path = sm(low + np.clip(target - low, -slack, slack), max(1, smooth_radius // 2))
    return traj + np.clip(path - traj, -leash, leash)


def to_center(M, c):
    """Origin-based 2x3 similarity → (dx, dy, angle, log-scale) about centre c: p' = sR(p - c) + c + t. The warp
    rotates/scales about the frame centre; mixing the two conventions cost tens of pixels whenever the camera dollied."""
    sR = np.asarray(M, float)[:, :2]
    t = np.asarray(M, float)[:, 2] + sR @ np.asarray(c, float) - np.asarray(c, float)
    return float(t[0]), float(t[1]), math.atan2(sR[1, 0], sR[0, 0]), math.log(max(1e-6, math.hypot(sR[0, 0], sR[1, 0])))


def from_center(params, c, f=1.0):
    """3x3 matrix of centre-based params in a space scaled by f (translation scaled, centre c given in that space)."""
    dx, dy, a, ls = params
    sR = math.exp(ls) * np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    c = np.asarray(c, float)
    m = np.eye(3)
    m[:2, :2] = sR
    m[:2, 2] = np.array([dx * f, dy * f]) + c - sR @ c
    return m


def _similarity(a_pts, b_pts):
    M, inl = cv2.estimateAffinePartial2D(a_pts, b_pts, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    return (M, int(inl.sum())) if M is not None and inl is not None else (None, 0)


def _klt(a, b, pts):
    """KLT a → b with a forward-backward check: (from, to) of the points that track back to where they started (a lost
    track on a big jump or a repetitive texture does not), or None when fewer than 8 survive."""
    if pts is None or len(pts) < 8:
        return None
    nxt, st, _ = cv2.calcOpticalFlowPyrLK(a, b, pts, None, winSize=(21, 21), maxLevel=3)
    back, st2, _ = cv2.calcOpticalFlowPyrLK(b, a, nxt, None, winSize=(21, 21), maxLevel=3)
    good = (st.reshape(-1) == 1) & (st2.reshape(-1) == 1) & (np.hypot(*(back - pts).reshape(-1, 2).T) < 1.0)
    return (pts[good], nxt[good]) if good.sum() >= 8 else None


def pair_motion(prev, g, mask=None):
    """(dx, dy, angle, log-scale) about the frame centre from prev to g: KLT features (inside mask) + RANSAC
    similarity; zeros if unsure."""
    tr = _klt(prev, g, cv2.goodFeaturesToTrack(prev, maxCorners=400, qualityLevel=.01, minDistance=12, blockSize=7, mask=mask))
    if tr is not None:
        M, _ = _similarity(*tr)
        if M is not None:
            return to_center(M, (g.shape[1] / 2, g.shape[0] / 2))
    return 0.0, 0.0, 0.0, 0.0


class Registrar:
    """Registers frames to one reference image with ORB matches inside a (moving) subject box."""

    def __init__(self, ref, box=None):
        self.orb = cv2.ORB_create(nfeatures=1500, fastThreshold=10)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self.box, self.c = box, (ref.shape[1] / 2, ref.shape[0] / 2)
        self.kp, self.des = self.orb.detectAndCompute(ref, _region_mask(ref.shape, box))

    def __call__(self, g, shift=(0.0, 0.0)):
        """Centre-based params of the reference content in g, or None when it cannot be matched."""
        if self.des is None:
            return None
        kp, des = self.orb.detectAndCompute(g, _region_mask(g.shape, self.box, *shift))
        if des is None or len(kp) < 12:
            return None
        ms = sorted(self.bf.match(self.des, des), key=lambda m: m.distance)[:300]
        if len(ms) < 12:
            return None
        M, n = _similarity(np.float32([self.kp[m.queryIdx].pt for m in ms]), np.float32([kp[m.trainIdx].pt for m in ms]))
        return to_center(M, self.c) if M is not None and n >= 10 else None


def _region_mask(shape, box, dx=0.0, dy=0.0):
    """uint8 mask of box (analysis px, x0 y0 x1 y1) shifted by (dx, dy), clipped to the frame; None for whole frame."""
    if box is None:
        return None
    h, w = shape
    x0, y0, x1, y1 = (int(round(v)) for v in (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy))
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None
    m = np.zeros((h, w), np.uint8)
    m[y0:y1, x0:x1] = 255
    return m


def corner_shift(a, pts, b, corners):
    """How far the box corners move from frame a to b (analysis px): KLT of a's features (pts) into b + RANSAC
    similarity evaluated at the corners. Small, local and subpixel, unlike registration to a distant reference whose
    rotation/scale noise reads as several pixels at the corners. None when unsure."""
    tr = _klt(a, b, pts)
    if tr is None:
        return None
    M, n = _similarity(*tr)
    if M is None or n < 6:
        return None
    return float(np.hypot(*(corners @ M[:, :2].T + M[:, 2] - corners).T).max())


def fuse_paths(chained, registered, radius=30):
    """Complementary filter: frame-to-frame KLT (chained) is precise but drifts over a long take; registration to the
    first frame (ORB) never drifts but each estimate is ~0.5 px / 0.5% scale noisy, which a lock would bake into the
    picture as breathing. Keep the chain's high frequencies and the registration's slow ones: chained plus the
    median-then-Gaussian-smoothed difference. registered may hold NaN rows (no match): interpolated.
    Where one step of the two disagrees by more than the registration noise: a one-frame registration spike (off and
    back) is dropped; otherwise the chain lost track on that step (a big jump) and takes the registration's step."""
    chained, registered = np.array(chained, float), np.array(registered, float)
    if len(chained) > 2:
        steps, rsteps = np.diff(chained, axis=0), np.diff(registered, axis=0)
        d = np.nan_to_num(rsteps[:, :2] - steps[:, :2])
        tol = max(4.0, 8 * float(np.median(np.abs(d))))  # analysis px
        off = np.abs(d).max(axis=1) > tol
        i = 0
        while i < len(off):
            if off[i]:
                if i + 1 < len(off) and off[i + 1] and np.abs(d[i] + d[i + 1]).max() < tol:
                    registered[i + 1] = np.nan
                    i += 2
                    continue
                steps[i] = rsteps[i]
            i += 1
        chained = np.vstack([chained[:1], chained[:1] + np.cumsum(steps, axis=0)])
    diff = registered - chained
    ok = ~np.isnan(diff).any(axis=1)
    if not ok.any():
        return chained.copy()
    idx = np.arange(len(diff))
    out = np.empty_like(diff)
    for j in range(diff.shape[1]):
        col = np.interp(idx, idx[ok], diff[ok, j])
        if len(col) >= 5:  # a single wrong match must not bend the path
            col = np.median(np.lib.stride_tricks.sliding_window_view(np.pad(col, 2, mode="edge"), 5), axis=1)
        out[:, j] = _smooth(col, radius)
    return chained + out


def registered_path(frames_gray, region=None, radius=30):
    """Lock-mode trajectory with no drift: every frame registered to the FIRST one (ORB matches inside the subject
    region + RANSAC similarity; a 60 s frame-to-frame chain alone drifted 100+ px), fused with the frame-to-frame
    KLT chain for precision (fuse_paths). Returns (n, 4) centre-based (dx, dy, angle, log-scale) of the reference
    content in each frame."""
    reg_out, chain, reg, prev, cur = [], [], None, None, np.zeros(4)
    for g in frames_gray:
        if reg is None:
            reg, prev = Registrar(g, region), g
            reg_out.append(np.zeros(4))
            chain.append(np.zeros(4))
            continue
        step = np.array(pair_motion(prev, g, _region_mask(prev.shape, region, cur[0], cur[1])))
        chain.append(chain[-1] + step)
        est = reg(g, (cur[0], cur[1]))
        reg_out.append(np.array(est) if est is not None else np.full(4, np.nan))
        cur = reg_out[-1] if est is not None else cur + step
        prev = g
    if len(chain) < 3:
        return np.array(chain, float).reshape(-1, 4)
    return fuse_paths(chain, reg_out, radius)


def camera_path(frames_gray, region=None):
    """Per-frame inter-frame motion (dx, dy, angle, log-scale). With region (analysis px box at the first frame) only
    features on the subject count; the box follows the subject's accumulated translation."""
    out, prev, cx, cy = [], None, 0.0, 0.0
    for g in frames_gray:
        if prev is None:
            out.append((0.0, 0.0, 0.0, 0.0))
            prev = g
            continue
        mo = pair_motion(prev, g, _region_mask(prev.shape, region, cx, cy))
        cx, cy = cx + mo[0], cy + mo[1]
        out.append(mo)
        prev = g
    return np.array(out)


def stabilize(task_id, request):
    from .media_tasks import folder, check, update
    q = StabilizeRequest.model_validate(request)
    src = Path(q.path).resolve(strict=True)
    sw, sh, fps, duration = _video_info(src)
    end = min(q.end or duration, duration, q.start + 60)
    dur = end - q.start
    aw = 640
    ah = int(round(aw * sh / sw / 2) * 2)
    update(task_id, progress=.05, message="Tracking camera motion")
    gray = (cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in _frames(src, q.start, dur, aw, ah))
    box = [q.region[0] * aw, q.region[1] * ah, q.region[2] * aw, q.region[3] * ah] if q.region else None
    if q.mode == "lock":  # absolute registration to the first frame: no accumulated drift
        traj = registered_path(gray, box, max(8, int(round(fps))))  # ~1 s (lowest residual at x8-x32 on a 60 s take)
    else:
        traj = np.cumsum(camera_path(gray, box), axis=0)
    check(task_id)
    n = len(traj)
    if n < 3:
        raise ValueError("Too few frames to stabilize")
    radius = max(1, int(q.smoothing_seconds * fps))
    smooth = np.zeros_like(traj) if q.mode == "lock" else np.stack([_smooth(traj[:, k], radius) for k in range(4)], axis=1)
    corr = smooth - traj  # what to apply to each frame (analysis-resolution pixels / radians / log-scale)
    k = sw / aw
    # Zoom needed so the warped frame still covers the canvas (translation + rotation, and a scale correction that
    # shrinks the frame when the camera moved closer than the reference), capped by max_zoom.
    need = (1 + 2 * np.maximum(np.abs(corr[:, 0]) * k / sw, np.abs(corr[:, 1]) * k / sh) + np.abs(corr[:, 2]) * (sw + sh) / max(sw, sh)) \
        * np.exp(np.maximum(0.0, -corr[:, 3]))
    zoom = float(min(q.max_zoom, max(1.0, np.percentile(need, 98))))
    capped = float(np.percentile(need, 98)) > q.max_zoom
    if capped:
        # The ideal path needs more crop than allowed. Scaling the whole correction down (as before) left part of the
        # shake in every frame — a locked time-lapse still jumped 20-30 px between frames. Instead the virtual camera
        # is put on a leash: as still/smooth as possible, never further from the real path than the crop hides
        # (translation gets 75% of the margin, rotation 15%, scale 10%), following slowly where it must.
        margin = (q.max_zoom - 1) / 2
        leash = np.array([.75 * margin * aw, .75 * margin * ah, .15 * margin * max(sw, sh) / (sw + sh), .1 * margin])
        path = leashed_path(traj, smooth, leash, max(radius, int(2 * fps)))
        corr = path - traj
    scale = min(1, q.max_width / sw)
    w, h = int(round(sw * scale / 2) * 2), int(round(sh * scale / 2) * 2)
    out = folder(task_id)
    target = out / "stabilized.mp4"
    enc = _encoder(target, w, h, fps, q.crf)
    f = k * scale  # analysis px → output px
    co = (w / 2, h / 2)
    Z = from_center((0, 0, 0, math.log(zoom)), co)
    target_path = traj + corr  # where the virtual camera should be (lock: zero; leashed or smoothed otherwise)
    # The subject box as it lands on the output (zoomed about the centre), for measuring what the viewer sees.
    zb = lambda v, c, lim: min(lim, max(0.0, c + (v - c) * zoom))
    obox = [zb(box[0], aw / 2, aw), zb(box[1], ah / 2, ah), zb(box[2], aw / 2, aw), zb(box[3], ah / 2, ah)] if box else None
    x0, y0, x1, y1 = obox or (0, 0, aw, ah)
    corners = np.array([[x0, y0], [x1, y0], [x0, y1], [x1, y1]], float)
    strides = (1, 4, 8, 16, 32)
    recent, moved = deque(maxlen=max(strides)), {s_: [] for s_ in strides}  # last output frames (gray, features)
    measured, meas_reg, matched = [], None, 0  # subject position on the output vs its first frame (static after a lock)
    try:
        for i, frame in enumerate(_frames(src, q.start, dur, w, h)):
            if i >= n:
                break
            if i % 30 == 0:
                check(task_id)
                update(task_id, progress=.3 + .65 * i / n, message=f"Warping {i}/{n}")
            W = Z @ from_center(target_path[i], co, f) @ np.linalg.inv(from_center(traj[i], co, f))
            warped = cv2.warpAffine(frame, W[:2], (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            enc.stdin.write(warped.tobytes())
            g = cv2.cvtColor(cv2.resize(warped, (aw, ah), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            for s_ in strides:  # what a fast-forward at speed s_ shows between two output frames
                if len(recent) >= s_:
                    d = corner_shift(*recent[-s_], g, corners)
                    if d is not None:
                        moved[s_].append(d)
            recent.append((g, cv2.goodFeaturesToTrack(g, maxCorners=300, qualityLevel=.01, minDistance=8, blockSize=7,
                                                      mask=_region_mask(g.shape, obox))))
            if meas_reg is None:
                meas_reg = Registrar(g, obox)
                measured.append(np.zeros(4))
            else:
                est = meas_reg(g)
                matched += est is not None
                measured.append(np.array(est) if est is not None else measured[-1])
    finally:
        enc.stdin.close()
        enc.wait()
    if enc.returncode:
        raise ValueError("Stabilize encoder failed")
    audio = _with_source_audio(target, src, q.start, dur)
    hf = lambda a: float(np.std(a - np.stack([_smooth(a[:, j], 5) for j in range(a.shape[1])], axis=1)[:, :2]))
    # Measured on the stabilized output (subject region if given), in its pixels. Drift: the subject's position vs the
    # first output frame by registration (translation, lightly smoothed: per-frame registration noise is ~0.5 px).
    # Steps: how far the subject box's corners move between output frames s apart, tracked directly (corner_shift).
    # Nothing trackable (a flat region) is reported as unmeasured, never as 0 px.
    mv = np.array(measured)
    pairs = max(1, len(mv) - 1)
    seen = (np.stack([_smooth(mv[:, j], 2) for j in range(2)], axis=1) if len(mv) > 4 else mv[:, :2]) * f
    step = np.array(moved[1]) * f
    pct = lambda q_: {str(s_): round(float(np.percentile(moved[s_], q_)) * f, 2) for s_ in strides if len(moved[s_]) >= max(3, .5 * (len(mv) - s_))}
    report = {"source": str(src), "window": [q.start, end], "mode": q.mode, "frames": n, "fps": fps, "dimensions": [w, h], "zoom": round(zoom, 4),
              "source_audio": audio,
              "correction_capped": capped, "jitter_px_before": round(hf(traj[:, :2]) * k, 3),
              # Residual motion, not only high-frequency jitter: a slow drift is invisible at 1x and a slide at x24.
              "residual_coverage": round(len(moved[1]) / pairs, 3),
              "residual_drift_px": [round(float(np.ptp(seen[:, 0])), 1), round(float(np.ptp(seen[:, 1])), 1)] if matched >= .5 * pairs else None,
              "residual_step_px": {"p95": round(float(np.percentile(step, 95)), 2), "max": round(float(step.max()), 2)} if len(step) >= max(3, .5 * pairs) else None,
              # What a fast-forward shows: at speed s each output frame jumps over s source frames.
              "residual_px_over_frames": pct(95),
              "residual_px_over_frames_p99": pct(99),
              "residual_measured_on": "stabilized output pixels" + (" (subject region)" if box else " (whole frame)"),
              "residual_note": "At speed s, the picture moves about residual_px_over_frames[s] px per output frame (p95); "
                               "missing or None = not measurable (nothing trackable in the region): inspect by eye.",
              "max_correction_px": round(float(np.abs(corr[:, :2]).max()) * k, 2),
              "method": "KLT features + RANSAC similarity per frame, Gaussian-smoothed trajectory; lock registers every frame to the first (ORB, subject region) fused with the KLT chain; when the crop cap is "
                        "reached the path is leashed to the real one (smooth, within the crop), replicate-border warp with the smallest zoom covering 98% of frames (capped). "
                        "Residuals are tracked on the output (subject box corners between frames 1-32 apart). Rolling shutter and parallax are not modelled; inspect edges and wobble."}
    store.write_json(out / "stabilize.json", report)
    return {"video": str(target), "artifacts": {"video": str(target), "manifest": str(out / "stabilize.json")}, "report": report}


class FocusPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t: float = Field(ge=0)  # seconds from window start
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class ReframeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    end: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    aspect: str = Field(default="9:16", pattern=r"^\d{1,2}:\d{1,2}$")
    focus: list[FocusPoint] = Field(default_factory=list, max_length=4000)  # tracked subject points; empty → automatic
    # Automatic focus: "saliency" (salient + moving regions) or "faces" (the main face, OpenCV's bundled Haar detectors;
    # frames without a face hold the last one, then fall back to saliency). For talking heads and interviews.
    auto_focus: Literal["saliency", "faces"] = "saliency"
    dead_zone: float = Field(default=.15, ge=0, le=.4)  # fraction of crop width the subject may wander before the camera moves
    smoothing_seconds: float = Field(default=.8, ge=.1, le=5)
    output_height: int = Field(default=1920, ge=320, le=3840)
    crf: int = Field(default=17, ge=12, le=28)

    @model_validator(mode="after")
    def window(self):
        if self.end is not None and not self.start < self.end <= self.start + 120:
            raise ValueError("Reframe window must be within 120 source seconds")
        a, b = (int(v) for v in self.aspect.split(":"))
        if not a or not b:
            raise ValueError("aspect like 9:16")
        return self


def spectral_saliency(gray):
    """Spectral-residual saliency (Hou & Zhang 2007) on a small grayscale frame; returns a [0,1] map."""
    from scipy.ndimage import gaussian_filter, uniform_filter
    g = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
    g = cv2.copyMakeBorder(g, 16, 16, 16, 16, cv2.BORDER_REFLECT)  # mirror padding: no FFT wrap-around at the frame edges
    F = np.fft.fft2(g)
    A = np.log(np.abs(F) + 1e-6)
    R = A - uniform_filter(A, 3)
    S = np.abs(np.fft.ifft2(np.exp(R + 1j * np.angle(F)))) ** 2
    S = gaussian_filter(S, 2.5)[16:80, 16:80]
    S -= S.min()
    return S / (S.max() + 1e-9)


def focus_of(gray, prev):
    """Automatic focus: saliency weighted by motion and a mild centre prior; returns normalized (x, y) and confidence."""
    sal = spectral_saliency(gray)
    if prev is not None:
        mot = cv2.resize(cv2.absdiff(gray, prev), (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
        mot /= mot.max() + 1e-6
        sal = .5 * sal + .5 * mot * (mot > .15)
    yy, xx = np.mgrid[0:64, 0:64] / 63.0
    prior = np.exp(-((xx - .5) ** 2 + (yy - .5) ** 2) / .18)
    w = sal * (.6 + .4 * prior)  # mild centre preference only breaks ties; a strong off-centre subject still wins
    top = w >= max(np.percentile(w, 98), .5 * w.max())
    m = (w * top).sum()
    if m <= 1e-9:
        return .5, .5, 0.0
    return float((xx * w * top).sum() / m), float((yy * w * top).sum() / m), float(w[top].mean() / (w.mean() + 1e-9))


_CASCADES = {}


def _owl_faces(gray):
    """OpenCV 5 dropped the Haar cascades (objdetect moved them to contrib): the installed OWLv2 detector asked for
    "a face" stands in, roughly face-shaped boxes only (a hat or a back of a head is not a face)."""
    from .semantic import _detect_frames
    # OWLv2 scores faces low (.07-.26 on graded portraits; "a face" outscores "a human face"); the Haar minimum size applies
    hits = _detect_frames([np.repeat(gray[..., None], 3, axis=2)], ["a face"], .07)[0]
    h, w = gray.shape
    out = []
    for b in hits:
        x0, y0, x1, y1 = b["box"]
        if x1 - x0 >= 1 / 30 and .45 <= (x1 - x0) * w / max(1e-6, (y1 - y0) * h) <= 1.6:
            out.append((x0, y0, x1 - x0, y1 - y0))
    return sorted(out, key=lambda b: -b[2] * b[3])


def detect_faces(gray):
    """Faces in a grayscale frame as normalized (x, y, w, h) boxes, largest first: OpenCV's bundled frontal and
    profile Haar cascades (no model download), or the local OWLv2 detector where OpenCV 5 no longer ships them.
    Misses small, turned-away or heavily lit faces; not identity."""
    if not hasattr(cv2, "CascadeClassifier"):
        return _owl_faces(gray)
    if not _CASCADES:
        for k in ("frontalface_default", "profileface", "eye"):
            _CASCADES[k] = cv2.CascadeClassifier(cv2.data.haarcascades + f"haarcascade_{k}.xml")
    h, w = gray.shape
    g = cv2.equalizeHist(gray)
    found = []
    for k in ("frontalface_default", "profileface"):
        for flip in ((False, True) if k == "profileface" else (False,)):
            img = cv2.flip(g, 1) if flip else g
            for (x, y, fw, fh) in _CASCADES[k].detectMultiScale(img, scaleFactor=1.1, minNeighbors=6, minSize=(max(24, w // 30), max(24, w // 30))):
                x = w - x - fw if flip else x
                if k == "frontalface_default":  # a frontal face has an eye in its upper half (a patterned tie does not)
                    roi = g[y:y + fh // 2, x:x + fw]
                    if not len(_CASCADES["eye"].detectMultiScale(roi, 1.1, 3, minSize=(max(6, fw // 10), max(6, fw // 10)))):
                        continue
                found.append((x / w, y / h, fw / w, fh / h))
    keep = []  # merge duplicates of the same face found by both detectors
    for b in sorted(found, key=lambda b: -b[2] * b[3]):
        if not any(abs((b[0] + b[2] / 2) - (k[0] + k[2] / 2)) < k[2] * .5 and abs((b[1] + b[3] / 2) - (k[1] + k[3] / 2)) < k[3] * .5 for k in keep):
            keep.append(b)
    return keep


def face_focus(frames_gray, step=3):
    """Per-frame (x, y, confidence) of the main face: detected every `step` frames on 640-px frames, the face nearest the
    previous one wins (no jumping between two people mid-shot), gaps held then interpolated; None where no face ever."""
    xs, ys, cs, last, last_box, boxes = [], [], [], None, None, []
    for i, g in enumerate(frames_gray):
        if i % step == 0:
            faces = detect_faces(g)
            big = max((f_[2] * f_[3] for f_ in faces), default=0)
            faces = [f_ for f_ in faces if f_[2] * f_[3] >= .4 * big]  # a tie or badge is not the speaker
            if faces:
                if last is not None:
                    faces.sort(key=lambda b: abs(b[0] + b[2] / 2 - last[0]) + abs(b[1] + b[3] / 2 - last[1]) - 2 * b[2] * b[3])
                b = faces[0]
                # a far, much smaller box is a false detection, not the speaker moving: hold the last face
                if last_box is not None and b[2] * b[3] < .7 * last_box[2] * last_box[3] and (
                        abs(b[0] + b[2] / 2 - last[0]) > last_box[2] or abs(b[1] + b[3] / 2 - last[1]) > last_box[3] * .6):
                    faces = []
            if faces:
                last = (b[0] + b[2] / 2, b[1] + b[3] / 2)
                last_box = b
                boxes.append((i, b))
        xs.append(last[0] if last else None)
        ys.append(last[1] if last else None)
        cs.append(1.0 if last else 0.0)
    if not boxes:
        return None
    first = boxes[0][1]
    xs = [v if v is not None else first[0] + first[2] / 2 for v in xs]
    ys = [v if v is not None else first[1] + first[3] / 2 for v in ys]
    return xs, ys, cs, boxes


def follow_path(targets, crop, span, dead_zone, radius):
    """Virtual camera: hold while the target stays inside the dead zone, otherwise move toward it; then smooth."""
    pos, cur = [], None
    lo, hi = crop / 2, span - crop / 2
    for t in targets:
        if cur is None:
            cur = min(hi, max(lo, t))
        elif abs(t - cur) > dead_zone * crop:
            cur += (t - cur) - math.copysign(dead_zone * crop, t - cur)
        cur = min(hi, max(lo, cur))
        pos.append(cur)
    return np.clip(_smooth(np.array(pos, float), radius), lo, hi)


def reframe(task_id, request):
    from .media_tasks import folder, check, update
    q = ReframeRequest.model_validate(request)
    src = Path(q.path).resolve(strict=True)
    sw, sh, fps, duration = _video_info(src)
    end = min(q.end or duration, duration)
    dur = end - q.start
    a, b = (int(v) for v in q.aspect.split(":"))
    target_ratio = a / b
    if target_ratio < sw / sh:
        cw, ch = int(round(sh * target_ratio / 2) * 2), sh
    else:
        cw, ch = sw, int(round(sw / target_ratio / 2) * 2)
    aw = 320
    ah = int(round(aw * sh / sw / 2) * 2)
    update(task_id, progress=.05, message="Locating subject")
    fx, fy, conf, prev = [], [], [], None
    if q.focus:
        pts = sorted(q.focus, key=lambda p: p.t)
        ts = np.array([p.t for p in pts])
        n_est = int(dur * fps)
        times = np.arange(n_est) / fps
        fx = list(np.interp(times, ts, [p.x for p in pts]))
        fy = list(np.interp(times, ts, [p.y for p in pts]))
        conf = [1.0] * n_est
    faces = None
    if not q.focus and q.auto_focus == "faces":
        fh_ = int(round(640 * sh / sw / 2) * 2)
        faces = face_focus(cv2.cvtColor(f_, cv2.COLOR_BGR2GRAY) for f_ in _frames(src, q.start, dur, 640, fh_))
        check(task_id)
        if faces:
            fx, fy, conf, face_boxes = faces
    if not q.focus and not faces:
        for i, frame in enumerate(_frames(src, q.start, dur, aw, ah)):
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            x, y, c = focus_of(g, prev)
            fx.append(x)
            fy.append(y)
            conf.append(c)
            prev = g
            if i % 60 == 0:
                check(task_id)
    n = len(fx)
    if n < 2:
        raise ValueError("Too few frames to reframe")
    radius = max(1, int(q.smoothing_seconds * fps))
    if not q.focus and not faces:  # automatic focus is noisy frame to frame: median over ~0.5 s before the dead-zone follower
        from scipy.ndimage import median_filter
        k = max(3, int(fps * .5) | 1)
        fx, fy = list(median_filter(np.array(fx), size=k, mode="nearest")), list(median_filter(np.array(fy), size=k, mode="nearest"))
    px = follow_path([x * sw for x in fx], cw, sw, q.dead_zone, radius) if cw < sw else np.full(n, sw / 2)
    py = follow_path([y * sh for y in fy], ch, sh, q.dead_zone, radius) if ch < sh else np.full(n, sh / 2)
    oh = min(q.output_height, ch)
    ow = int(round(oh * target_ratio / 2) * 2)
    oh = int(round(oh / 2) * 2)
    out = folder(task_id)
    target = out / "reframed.mp4"
    enc = _encoder(target, ow, oh, fps, q.crf)
    try:
        for i, frame in enumerate(_frames(src, q.start, dur, sw, sh)):
            if i >= n:
                break
            if i % 30 == 0:
                check(task_id)
                update(task_id, progress=.3 + .65 * i / n, message=f"Cropping {i}/{n}")
            x0 = int(round(px[i] - cw / 2))
            y0 = int(round(py[i] - ch / 2))
            crop = frame[max(0, y0):max(0, y0) + ch, max(0, x0):max(0, x0) + cw]
            enc.stdin.write(cv2.resize(crop, (ow, oh), interpolation=cv2.INTER_AREA).tobytes())
    finally:
        enc.stdin.close()
        enc.wait()
    if enc.returncode:
        raise ValueError("Reframe encoder failed")
    if any(s_["codec_type"] == "audio" for s_ in probe(str(src))["streams"]):  # keep the source sound (dialogue, ambience)
        muxed = out / "reframed-av.mp4"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(target), "-ss", f"{q.start:.3f}", "-t", f"{n / fps:.3f}", "-i", str(src),
                        "-map", "0:v", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
                        "-movflags", "+faststart", str(muxed)], check=True)
        muxed.replace(target)
    moves = int(((np.abs(np.diff(px)) > 1) | (np.abs(np.diff(py)) > 1)).sum())
    report = {"source": str(src), "window": [q.start, end], "aspect": q.aspect, "crop": [cw, ch], "output": [ow, oh], "frames": n,
              "focus_source": "tracked points" if q.focus else ("faces (Haar)" if faces else "automatic saliency+motion" + (" (no face found)" if q.auto_focus == "faces" else "")),
              "mean_focus_confidence": round(float(np.mean(conf)), 3),
              **({"face_frames_fraction": round(len(face_boxes) / max(1, math.ceil(n / 3)), 3),  # sampled frames with a face found
                  # the main face in OUTPUT coordinates (for caption placement): sampled boxes, normalized x0 y0 x1 y1
                  "face_boxes_out": [{"frame": i, "box": [round(max(0.0, (b[0] * sw - (px[min(i, n - 1)] - cw / 2)) / cw), 3), round(max(0.0, (b[1] * sh - (py[min(i, n - 1)] - ch / 2)) / ch), 3),
                                                          round(min(1.0, ((b[0] + b[2]) * sw - (px[min(i, n - 1)] - cw / 2)) / cw), 3), round(min(1.0, ((b[1] + b[3]) * sh - (py[min(i, n - 1)] - ch / 2)) / ch), 3)]}
                                     for i, b in face_boxes[::max(1, len(face_boxes) // 40)]]} if faces else {}),
              "camera_moving_fraction": round(moves / max(1, n), 3), "crop_center_path": {"every": max(1, n // 60), "x": [round(float(v / sw), 4) for v in px[::max(1, n // 60)]]},
              "method": "Crop window follows the subject with a dead zone (holds while the subject stays near centre), Gaussian-smoothed. "
                        "Automatic focus = spectral-residual saliency mixed with motion and a centre prior, or the main face (auto_focus faces); for products pass tracked focus points "
                        "(track_subject/track_region) — automatic focus can pick the wrong object."}
    store.write_json(out / "reframe.json", report)
    return {"video": str(target), "artifacts": {"video": str(target), "manifest": str(out / "reframe.json")}, "report": report}
