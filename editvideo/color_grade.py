"""Primary grade chain in the order colourists use, baked to a display-domain 3D LUT (exact for per-pixel operations)
plus FFmpeg spatial filters (sharpen, vignette) that a LUT cannot express.

Order: levels (lift / gamma / gain / offset per channel) -> white balance (neutral region gains) -> contrast around a
pivot -> luma curve -> saturation (luma preserving) -> split tone (shadow / highlight offsets) -> HSL secondaries ->
skin protection (blend skin back toward the balanced image) -> [creative LUT] -> sharpen -> vignette. Values follow grading-panel conventions on display-referred 0..1 code values.
"""
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

LUMA = np.array([.2126, .7152, .0722])


def _rgb(v, lo, hi, name):
    if isinstance(v, (int, float)):
        v = [v, v, v]
    if len(v) != 3 or not all(lo <= x <= hi for x in v):
        raise ValueError(f"{name} needs a number or [r, g, b] within {lo}..{hi}")
    return [float(x) for x in v]


SKIN_DEG = 123.0  # vectorscope angle of the skin-tone line (atan2(Cr, Cb), degrees)


class Secondary(BaseModel):
    """HSL qualifier: a soft key on hue (vectorscope degrees, Cb→Cr), chroma (% of full scale) and luma (0..1), then an
    adjustment inside the key. Soft edges are cosine ramps, so the result bakes exactly into the 3D LUT."""
    model_config = ConfigDict(extra="forbid")
    hue_deg: float = Field(ge=0, lt=360)
    width_deg: float = Field(default=40, gt=0, le=180)  # full width of the fully-keyed band
    soft_deg: float = Field(default=20, ge=0, le=90)  # ramp on each side
    sat: list[float] = Field(default=[2, 100], min_length=2, max_length=2)  # chroma % range (0..100)
    luma: list[float] = Field(default=[0, 1], min_length=2, max_length=2)
    soft: float = Field(default=.08, ge=0, le=.5)  # ramp for luma (0..1) and chroma (fraction of 100 %)
    invert: bool = False
    hue_shift_deg: float = Field(default=0, ge=-60, le=60)
    sat_gain: float = Field(default=1, ge=0, le=2)
    luma_offset: float = Field(default=0, ge=-.2, le=.2)
    mix: float = Field(default=1, ge=0, le=1)


class Grade(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lift: float | list[float] = 0  # -0.3..0.3: moves blacks, white fixed
    gamma: float | list[float] = 1  # 0.5..2: midtones (>1 brighter)
    gain: float | list[float] = 1  # 0.5..2: moves whites, black fixed
    offset: float | list[float] = 0  # -0.2..0.2: everything
    neutral_region: list[float] | None = Field(default=None, min_length=4, max_length=4)  # normalized x,y,w,h of something white/grey
    neutral_gains: list[float] | None = Field(default=None, min_length=3, max_length=3)  # filled in from neutral_region
    contrast: float = Field(default=1, ge=.5, le=2)
    pivot: float = Field(default=.435, ge=.1, le=.9)
    curve: list[list[float]] | None = Field(default=None, max_length=12)  # luma curve [[in, out], ...] in 0..1
    saturation: float = Field(default=1, ge=0, le=2)
    shadow_tint: list[float] = Field(default=[0, 0, 0], min_length=3, max_length=3)  # rgb offsets, |x| <= .08, weighted (1-Y)^2
    highlight_tint: list[float] = Field(default=[0, 0, 0], min_length=3, max_length=3)  # weighted Y^2
    sharpen: float = Field(default=0, ge=0, le=1.5)  # unsharp amount (radius 5 px)
    vignette: float = Field(default=0, ge=0, le=1)  # edge darkening strength
    secondaries: list[Secondary] = Field(default_factory=list, max_length=6)
    # Keep skin out of the look: inside a soft skin key (hue 123° ± 25°, chroma 3-35 %, luma 12-90 %) saturation,
    # split tone and secondaries are blended back toward the balanced image by this amount (0..1).
    protect_skin: float = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def check(self):
        self.lift = _rgb(self.lift, -.3, .3, "lift")
        self.gamma = _rgb(self.gamma, .5, 2, "gamma")
        self.gain = _rgb(self.gain, .5, 2, "gain")
        self.offset = _rgb(self.offset, -.2, .2, "offset")
        if any(abs(v) > .08 for v in self.shadow_tint + self.highlight_tint):
            raise ValueError("split tone offsets are subtle: |value| <= 0.08")
        if self.curve:
            pts = sorted(self.curve)
            if any(len(p) != 2 or not (0 <= p[0] <= 1 and 0 <= p[1] <= 1) for p in pts) or len({p[0] for p in pts}) != len(pts):
                raise ValueError("curve points are distinct [in, out] pairs in 0..1")
            if any(b[1] < a[1] for a, b in zip(pts, pts[1:])):
                raise ValueError("curve must be non-decreasing (no solarisation)")
            self.curve = pts
        if self.neutral_region and not all(0 <= v <= 1 for v in self.neutral_region):
            raise ValueError("neutral_region is normalized [x, y, w, h]")
        return self


def _pchip(xs, ys, x):
    """Monotone cubic interpolation through curve points (no overshoot)."""
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if xs[0] > 0:
        xs, ys = np.r_[0, xs], np.r_[0, ys]
    if xs[-1] < 1:
        xs, ys = np.r_[xs, 1], np.r_[ys, 1]
    h, d = np.diff(xs), np.diff(ys) / np.diff(xs)
    m = np.zeros_like(xs)
    for i in range(1, len(xs) - 1):
        if d[i - 1] * d[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    m[0], m[-1] = d[0], d[-1]
    i = np.clip(np.searchsorted(xs, x) - 1, 0, len(h) - 1)
    t = (x - xs[i]) / h[i]
    h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
    return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]


def _ycc(v):
    y = v @ LUMA
    return y, (v[..., 2] - y) / 1.8556, (v[..., 0] - y) / 1.5748


def _rgb_from(y, cb, cr):
    r = y + 1.5748 * cr
    b = y + 1.8556 * cb
    g = (y - .2126 * r - .0722 * b) / .7152
    return np.stack([r, g, b], -1)


def _ramp(x, lo, hi, soft):
    """1 inside [lo, hi], cosine falloff over `soft` outside."""
    if soft <= 0:
        return ((x >= lo) & (x <= hi)).astype(float)
    d = np.maximum(lo - x, x - hi)
    t = np.clip(d / soft, 0, 1)
    return np.where(d <= 0, 1.0, .5 + .5 * np.cos(np.pi * t))


def key(sec, v):
    """Soft HSL key in 0..1 for display RGB v."""
    y, cb, cr = _ycc(v)
    chroma = np.hypot(cb, cr) * 100
    hue = np.degrees(np.arctan2(cr, cb)) % 360
    dh = np.abs((hue - sec.hue_deg + 180) % 360 - 180)
    k = _ramp(dh, -1, sec.width_deg / 2, sec.soft_deg)
    k = k * _ramp(chroma, sec.sat[0], sec.sat[1], sec.soft * 100) * _ramp(y, sec.luma[0], sec.luma[1], sec.soft)
    return 1 - k if sec.invert else k


SKIN = Secondary(hue_deg=SKIN_DEG, width_deg=30, soft_deg=20, sat=[3, 35], luma=[.12, .9], soft=.06)


def _secondary(sec, v):
    k = key(sec, v)[..., None] * sec.mix
    y, cb, cr = _ycc(v)
    a = np.radians(sec.hue_shift_deg)
    ncb, ncr = (cb * np.cos(a) - cr * np.sin(a)) * sec.sat_gain, (cb * np.sin(a) + cr * np.cos(a)) * sec.sat_gain
    adj = _rgb_from(y + sec.luma_offset, ncb, ncr)
    return v + (adj - v) * k


def apply(g: Grade, rgb):
    """rgb: (..., 3) display code values 0..1 → graded values. Same math is baked into the LUT."""
    v = np.asarray(rgb, float)
    lift, gamma, gain, offset = (np.array(x) for x in (g.lift, g.gamma, g.gain, g.offset))
    v = lift + v * (gain - lift)  # black moves with lift, white with gain
    v = np.clip(v, 0, None) ** (1 / gamma)
    v = v + offset
    if g.neutral_gains:
        v = v * np.array(g.neutral_gains)
    v = (v - g.pivot) * g.contrast + g.pivot
    if g.curve:
        y = np.clip(v @ LUMA, 0, 1)
        ny = _pchip([p[0] for p in g.curve], [p[1] for p in g.curve], y)
        v = v + (ny - y)[..., None]  # luma curve, hue and saturation kept
    base = v
    y = v @ LUMA
    v = y[..., None] + (v - y[..., None]) * g.saturation
    y = np.clip(v @ LUMA, 0, 1)[..., None]
    v = v + np.array(g.shadow_tint) * (1 - y) ** 2 + np.array(g.highlight_tint) * y ** 2
    for sec in g.secondaries:
        v = _secondary(sec, v)
    if g.protect_skin:
        k = key(SKIN, np.clip(base, 0, 1))[..., None] * g.protect_skin
        v = v + (base - v) * k
    return np.clip(v, 0, 1)


def cube(g: Grade, size=33):
    grid = np.linspace(0, 1, size)
    b, gg, r = np.meshgrid(grid, grid, grid, indexing="ij")  # .cube order: red fastest
    rgb = np.stack([r, gg, b], -1).reshape(-1, 3)
    out = apply(g, rgb)
    return f"LUT_3D_SIZE {size}\n" + "\n".join(f"{a:.6f} {c:.6f} {d:.6f}" for a, c, d in out) + "\n"


def neutral_gains(rgb_frame, region):
    """Per-channel gains that make the region's mean neutral at its own luma (green kept)."""
    h, w = rgb_frame.shape[:2]
    x0, y0, rw, rh = region
    patch = rgb_frame[int(y0 * h):max(int(y0 * h) + 1, int((y0 + rh) * h)), int(x0 * w):max(int(x0 * w) + 1, int((x0 + rw) * w))].reshape(-1, 3)
    mean = patch.mean(0)
    if mean.min() < .03 or mean.max() > .985:
        raise ValueError("neutral_region is too dark or clipped to measure a cast; pick a lit white/grey area")
    gains = mean[1] / mean
    return [round(float(x), 5) for x in np.clip(gains, .6, 1.6)]


def spatial_filters(g: Grade):
    f = []
    if g.sharpen:
        f.append(f"unsharp=5:5:{g.sharpen:.3f}:5:5:0")
    if g.vignette:
        f.append(f"vignette=angle={0.2 + 0.5 * g.vignette:.3f}:mode=forward")
    return f
