"""Smooth slow motion, speed ramps and shutter motion blur by bidirectional optical-flow interpolation.

Classical Farneback flow (OpenCV), not a learned frame interpolator: occlusions, thin structures and
large motion can ghost. The worker streams decoded frames, so memory stays bounded for long windows.
"""
import json
import math
import subprocess
from pathlib import Path
import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store
from .media import FFMPEG, probe


class SpeedKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at: float = Field(ge=0, allow_inf_nan=False)  # source seconds from window start
    speed: float = Field(ge=.05, le=8, allow_inf_nan=False)  # source seconds per output second


class RetimeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    end: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    speed: float = Field(default=.5, ge=.05, le=8, allow_inf_nan=False)
    speed_keys: list[SpeedKey] = Field(default_factory=list, max_length=32)
    interpolation: str = Field(default="flow", pattern="^(flow|blend|nearest)$")
    motion_blur: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)  # shutter fraction of output frame
    blur_samples: int = Field(default=5, ge=2, le=12)
    fps: int = Field(default=30, ge=12, le=60)
    max_width: int = Field(default=1920, ge=256, le=3840)
    crf: int = Field(default=17, ge=12, le=28)
    # Speed ramp around action peaks (absolute source seconds, as rank_clips reports peak_at; speed_keys count from
    # `start`): `speed` between peaks, `peak_speed` held for `hold_s` around each
    # peak, `ramp_s` S-curves in and out (practice: 100% -> 10-20% over 0.5-1 s; velocity edits run fast between beats).
    peaks: list[float] = Field(default_factory=list, max_length=8)
    peak_speed: float = Field(default=.25, ge=.05, le=1, allow_inf_nan=False)
    ramp_s: float = Field(default=.35, ge=.08, le=2, allow_inf_nan=False)
    hold_s: float = Field(default=.6, ge=0, le=3, allow_inf_nan=False)
    # play the result backwards (bombs rising back into the bay, as The Vietnam War opens); the reversal buffers the
    # whole output, so it is limited to 20 s of output
    reverse: bool = False

    @model_validator(mode="after")
    def window(self):
        if self.end is not None and not self.start < self.end <= self.start + 60:
            raise ValueError("Retime window must be within 60 source seconds")
        if self.peaks:
            if self.speed_keys:
                raise ValueError("pass peaks or speed_keys, not both")
            keys = []
            if any(not self.start <= pk <= (self.end if self.end is not None else 1e9) for pk in self.peaks):
                raise ValueError("peaks are source seconds inside [start, end]")
            for pk in sorted(x - self.start for x in self.peaks):
                a, b = pk - self.hold_s / 2, pk + self.hold_s / 2
                for at, sp in ((a - self.ramp_s, self.speed), (a, self.peak_speed), (b, self.peak_speed), (b + self.ramp_s, self.speed)):
                    if keys and at <= keys[-1][0] + .02:  # peaks closer than their ramps: stay slow between them
                        keys[-1] = (keys[-1][0], min(keys[-1][1], sp))
                        continue
                    keys.append((round(at, 3), sp))
            self.speed_keys = [SpeedKey(at=max(0.0, at), speed=sp) for at, sp in keys if at >= 0]
            self.peaks = []  # converted: the stored request re-validates in the worker as plain speed_keys
        if any(a.at >= b.at for a, b in zip(self.speed_keys, self.speed_keys[1:])):
            raise ValueError("speed_keys must have increasing 'at'")
        return self


def speed_at(q, s):
    keys = q.speed_keys
    if not keys:
        return q.speed
    if s <= keys[0].at:
        return keys[0].speed
    for a, b in zip(keys, keys[1:]):
        if s <= b.at:
            p = (s - a.at) / (b.at - a.at)
            p = p * p * (3 - 2 * p)
            return a.speed + (b.speed - a.speed) * p
    return keys[-1].speed


class FrameSource:
    """Sequential decoder with a tiny cache and per-pair bidirectional flow."""

    def __init__(self, path, start, duration, width, height, fps):
        self.w, self.h, self.fps = width, height, fps
        self.proc = subprocess.Popen([FFMPEG, "-v", "error", "-ss", str(start), "-i", str(path), "-t", str(duration),
                                      "-vf", f"scale={width}:{height}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                                     stdout=subprocess.PIPE)
        self.frames, self.base, self.flows, self.done = [], 0, {}, False

    def _read(self):
        raw = self.proc.stdout.read(self.w * self.h * 3)
        if len(raw) < self.w * self.h * 3:
            self.done = True
            return None
        return np.frombuffer(raw, np.uint8).reshape(self.h, self.w, 3)

    def frame(self, i):
        while not self.done and self.base + len(self.frames) <= i:
            f = self._read()
            if f is None:
                break
            self.frames.append(f)
            if len(self.frames) > 24:  # bounded cache; covers motion-blur taps behind the playhead
                self.frames.pop(0)
                self.flows.pop(self.base, None)
                self.base += 1
        i = min(max(i, self.base), self.base + len(self.frames) - 1)
        return self.frames[i - self.base], i

    @property
    def last(self):
        return self.base + len(self.frames) - 1

    def flow(self, i):
        if i not in self.flows:
            a, b = self.frame(i)[0], self.frame(i + 1)[0]
            scale = min(1, 640 / self.w)
            ga = cv2.cvtColor(cv2.resize(a, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            gb = cv2.cvtColor(cv2.resize(b, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            args = (None, .5, 4, 25, 3, 7, 1.5, 0)
            f01 = cv2.calcOpticalFlowFarneback(ga, gb, *args)
            f10 = cv2.calcOpticalFlowFarneback(gb, ga, *args)
            up = lambda f: cv2.resize(f, (self.w, self.h), interpolation=cv2.INTER_LINEAR) / scale
            self.flows[i] = (up(f01), up(f10))
        return self.flows[i]

    def close(self):
        self.proc.stdout.close()
        self.proc.kill()
        self.proc.wait()


def sample(src, q, t, grid):
    """Frame at fractional source time t (seconds from window start)."""
    x = t * src.fps
    i = int(math.floor(x))
    a = x - i
    f0, i0 = src.frame(i)
    if q.interpolation == "nearest" or a < 1e-3 or src.done and i0 >= src.last:
        return f0.astype(np.float32)
    f1, i1 = src.frame(i + 1)
    if i1 == i0:
        return f0.astype(np.float32)
    if q.interpolation == "blend":
        return (1 - a) * f0.astype(np.float32) + a * f1.astype(np.float32)
    f01, f10 = src.flow(i0)
    m0 = grid - a * f01
    m1 = grid - (1 - a) * f10
    w0 = cv2.remap(f0, m0[..., 0], m0[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    w1 = cv2.remap(f1, m1[..., 0], m1[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return (1 - a) * w0.astype(np.float32) + a * w1.astype(np.float32)


def process(task_id, request):
    from .media_tasks import folder, check, update
    q = RetimeRequest.model_validate(request)
    source = Path(q.path).resolve(strict=True)
    info = probe(source)
    stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = (stream.get("r_frame_rate") or "30/1").split("/")
    fps_src = float(num) / float(den or 1)
    duration_src = float(info["format"]["duration"])
    end = min(q.end or duration_src, duration_src)
    window = end - q.start
    if window <= 0:
        raise ValueError("Empty retime window")
    sw, sh = int(stream["width"]), int(stream["height"])
    scale = min(1, q.max_width / sw)
    w, h = int(round(sw * scale / 2) * 2), int(round(sh * scale / 2) * 2)
    out = folder(task_id)
    target = out / "retimed.mp4"
    src = FrameSource(source, q.start, window, w, h, fps_src)
    grid = np.dstack(np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32)))
    enc = subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(q.fps), "-i", "-",
                            "-c:v", "libx264", "-preset", "medium", "-crf", str(q.crf), "-g", "30", "-pix_fmt", "yuv420p",
                            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", str(target)],
                           stdin=subprocess.PIPE)
    times, s, n = [], 0.0, 0
    last_time = window - 1 / fps_src
    try:
        while s <= last_time + 1e-6:
            if n % 15 == 0:
                check(task_id)
                update(task_id, progress=min(.95, s / max(window, 1e-6)), message=f"Retiming {s:.2f}/{window:.2f}s")
            v = speed_at(q, s)
            if q.motion_blur > 0:
                span = q.motion_blur * v / q.fps
                taps = [min(last_time, max(0.0, s + span * (k / (q.blur_samples - 1) - .5))) for k in range(q.blur_samples)]
                img = sum(sample(src, q, t, grid) for t in sorted(taps)) / len(taps)
            else:
                img = sample(src, q, s, grid)
            enc.stdin.write(np.clip(img + .5, 0, 255).astype(np.uint8).tobytes())
            times.append(round(s, 5))
            s += v / q.fps
            n += 1
    finally:
        src.close()
        enc.stdin.close()
        enc.wait()
    if enc.returncode or not n:
        raise ValueError("Retime encoder failed")
    if q.reverse:
        if n / q.fps > 20:
            raise ValueError("reverse is limited to 20 s of output; shorten the window or raise the speed")
        if n * w * h * 1.5 > 3e9:  # FFmpeg's reverse filter holds every decoded frame (yuv420p) before writing the first
            raise ValueError(f"reverse would hold {n * w * h * 1.5 / 1e9:.1f} GB of frames; lower max_width or shorten the window")
        rev = out / "retimed.rev.mp4"
        p = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(target), "-vf", "reverse", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", str(q.crf),
                            "-g", "30", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                            "-movflags", "+faststart", str(rev)], capture_output=True, text=True, timeout=900)
        if p.returncode:
            raise ValueError("reverse failed: " + p.stderr[-200:])
        rev.replace(target)
        times = times[::-1]
    actual = probe(target)
    report = {"source": str(source), "window": [q.start, end], "source_fps": fps_src, "output_fps": q.fps, "output_frames": n,
              "output_duration": n / q.fps, "dimensions": [w, h], "interpolation": q.interpolation,
              "motion_blur": q.motion_blur, "speed": q.speed, "speed_keys": [k.model_dump() for k in q.speed_keys], "reverse": q.reverse,
              "first_source_times": times[:5], "last_source_time": times[-1],
              "method": "Bidirectional Farneback optical flow warp + blend; classical interpolation, not a learned model. "
                        "Inspect occlusions, thin structures and fast motion for ghosting. Output is silent; place source audio separately.",
              "probe_duration": float(actual["format"]["duration"])}
    store.write_json(out / "retime.json", report)
    return {"video": str(target), "manifest": str(out / "retime.json"),
            "artifacts": {"video": str(target), "manifest": str(out / "retime.json")}, "report": report}
