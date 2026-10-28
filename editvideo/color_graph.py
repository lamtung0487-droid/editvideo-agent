"""Scene-referred colour node graph (colour-managed, ACES-style), baked for FFmpeg.

input transform (camera log decode + gamut, or BT.1886 decode for display footage) → scene-linear Rec.709 → grade nodes
in a log working space (the ACEScct curve on Rec.709-linear: exposure, white balance, ASC CDL, contrast about 18 % grey,
saturation) → a look *under* the output transform (a print-film LUT that expects Cineon log, or a cct/display LUT) →
output transform (filmic shoulder for log footage, BT.1886 for display footage so an empty graph is an identity) →
display Rec.709.

Every per-pixel stage bakes into one 3D LUT over the source's code values (applied tetrahedrally in float). A tracked
window adds a second graph (its inner nodes at its position in the chain) and a feathered moving mask; the two results
merge after the chain, which is exact inside and outside the window (the feather zone mixes final results).
"""
import subprocess
from pathlib import Path
from typing import Literal
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .color_log import LOG_SPACES, decode, matrix, to_display

LUMA = np.array([.2126, .7152, .0722])
CINEON_BLACK = 10 ** ((95 - 685) * .002 / .6)


def cct(lin):
    lin = np.asarray(lin, float)
    return np.where(lin <= .0078125, 10.5402377416545 * lin + .0729055341958355, (np.log2(np.maximum(lin, 1e-10)) + 9.72) / 17.52)


def cct_inv(c):
    c = np.asarray(c, float)
    return np.where(c <= .155251141552511, (c - .0729055341958355) / 10.5402377416545, np.power(2.0, c * 17.52 - 9.72))


def cineon(lin):
    """Scene-linear → Cineon printing density code (0..1 of 10-bit; 18 % grey ≈ 0.457, the print-LUT input)."""
    return (685 + 300 * np.log10(np.maximum(lin, 0) * (1 - CINEON_BLACK) + CINEON_BLACK)) / 1023


def cineon_inv(c):
    return (np.power(10.0, (np.asarray(c, float) * 1023 - 685) * .002 / .6) - CINEON_BLACK) / (1 - CINEON_BLACK)


class Node(BaseModel):
    """One graph node. op picks the fields that matter; mix blends the node's result with its input (in cct)."""
    model_config = ConfigDict(extra="forbid")
    op: Literal["exposure", "white_balance", "cdl", "contrast", "saturation", "look", "window"]
    mix: float = Field(default=1, ge=0, le=1)
    stops: float = Field(default=0, ge=-6, le=6)  # exposure
    temp: float = Field(default=0, ge=-1, le=1)  # white_balance: + warmer
    tint: float = Field(default=0, ge=-1, le=1)  # white_balance: + magenta
    gains: list[float] | None = Field(default=None, min_length=3, max_length=3)  # white_balance: explicit linear RGB gains
    slope: list[float] = Field(default_factory=lambda: [1, 1, 1], min_length=3, max_length=3)  # cdl (in cct)
    offset: list[float] = Field(default_factory=lambda: [0, 0, 0], min_length=3, max_length=3)
    power: list[float] = Field(default_factory=lambda: [1, 1, 1], min_length=3, max_length=3)
    sat: float = Field(default=1, ge=0, le=3)  # cdl saturation
    amount: float = Field(default=1, ge=0, le=3)  # contrast (≥ .2) or saturation amount
    pivot: float = Field(default=.18, ge=.005, le=2)  # contrast pivot, scene-linear
    lut_id: str | None = None  # look
    lut_path: str | None = None
    input: Literal["cineon", "cct", "display"] = "cineon"  # look: the encoding the LUT expects
    output: Literal["display", "cineon", "cct"] = "display"  # look: display = the LUT includes the output transform
    strength: float = Field(default=1, ge=0, le=1)
    shape: Literal["ellipse", "rect"] = "ellipse"  # window
    box: list[float] | None = Field(default=None, min_length=4, max_length=4)  # window: x0, y0, x1, y1 source-normalised
    keys: list[dict] = Field(default_factory=list, max_length=200)  # window: [{t: source seconds, box}]
    track: dict | str | None = None  # window: track_region result, plane track or plane track_id
    track_start_s: float = Field(default=0, ge=0)
    track_fps: float | None = Field(default=None, gt=0, le=240)
    pad: float = Field(default=.15, ge=0, le=2)
    feather_px: float = Field(default=40, ge=6, le=400)
    invert: bool = False
    nodes: list["Node"] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def check(self):
        if any(v <= 0 for v in self.slope + self.power) or (self.gains and any(not .25 <= v <= 4 for v in self.gains)):
            raise ValueError("cdl slope/power > 0; white-balance gains .25..4")
        if self.op == "contrast" and self.amount < .2:
            raise ValueError("contrast amount ≥ .2")
        if self.op == "look" and bool(self.lut_id) == bool(self.lut_path):
            raise ValueError("look needs exactly one of lut_id or lut_path")
        if self.op == "window":
            if sum(x is not None and x != [] for x in (self.box, self.keys or None, self.track)) != 1:
                raise ValueError("window needs exactly one of box, keys or track")
            if not self.nodes:
                raise ValueError("window needs inner nodes (the grade inside it)")
            if any(n.op in ("look", "window") for n in self.nodes):
                raise ValueError("window inner nodes are grade nodes (no look or nested window)")
            for k in self.keys:
                if set(k) != {"t", "box"} or len(k["box"]) != 4:
                    raise ValueError("window keys are {t, box: [x0, y0, x1, y1]}")
        elif self.nodes:
            raise ValueError("only a window has inner nodes")
        return self


class Graph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: list[Node] = Field(min_length=1, max_length=24)
    output: Literal["auto", "filmic", "display"] = "auto"  # auto: filmic for log sources, display (BT.1886) otherwise
    grey_display: float = Field(default=.42, ge=.3, le=.55)  # filmic: display code of 18 % grey

    @model_validator(mode="after")
    def check(self):
        if sum(n.op == "window" for n in self.nodes) > 3:
            raise ValueError("at most 3 windows")
        for i, n in enumerate(self.nodes):
            if n.op == "look" and n.output == "display" and i != len(self.nodes) - 1:
                raise ValueError("a look that outputs display replaces the output transform and must be the last node")
        return self


def sample_cube(size, table, rgb):
    """Trilinear lookup in a .cube table (red fastest) for (N, 3) inputs in 0..1."""
    t = np.asarray(table, float).reshape(size, size, size, 3)
    x = np.clip(rgb, 0, 1) * (size - 1)
    i0 = np.clip(np.floor(x).astype(int), 0, size - 2)
    f = x - i0
    out = np.zeros_like(x)
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = (f[:, 0] if dr else 1 - f[:, 0]) * (f[:, 1] if dg else 1 - f[:, 1]) * (f[:, 2] if db else 1 - f[:, 2])
                out += w[:, None] * t[i0[:, 2] + db, i0[:, 1] + dg, i0[:, 0] + dr]
    return out


def _look_table(n):
    from .color_pipeline import LUT_ROOT, read_cube
    return read_cube(n.lut_path or LUT_ROOT / f"{n.lut_id}.cube")


class Evaluator:
    """Runs a node list on (N, 3) scene-linear Rec.709 values; returns display code values."""

    def __init__(self, graph: Graph, source_space: str):
        self.g = graph
        self.filmic = graph.output == "filmic" or (graph.output == "auto" and source_space in LOG_SPACES)
        self.tables = {}

    def odt(self, lin):
        return to_display(lin, self.g.grey_display) if self.filmic else np.clip(np.maximum(lin, 0) ** (1 / 2.4), 0, 1)

    def node(self, n, lin):
        if n.op == "exposure":
            out = lin * 2.0 ** n.stops
        elif n.op == "white_balance":
            g = np.array(n.gains) if n.gains else np.array([2 ** (.5 * n.temp + .1 * n.tint), 2 ** (-.25 * n.tint), 2 ** (-.5 * n.temp + .1 * n.tint)])
            out = lin * (g / (g @ LUMA))
        elif n.op == "cdl":
            c = np.maximum(cct(lin) * n.slope + n.offset, 0) ** np.array(n.power)
            y = (c @ LUMA)[:, None]
            out = cct_inv(y + n.sat * (c - y))
        elif n.op == "contrast":
            p = cct(n.pivot)
            out = cct_inv(p + (cct(lin) - p) * n.amount)
        elif n.op == "saturation":
            y = (lin @ LUMA)[:, None]
            out = y + n.amount * (lin - y)
        elif n.op == "look":
            key = n.lut_id or n.lut_path
            if key not in self.tables:
                self.tables[key] = _look_table(n)
            size, table = self.tables[key]
            enc = {"cineon": cineon, "cct": cct, "display": self.odt}[n.input](lin)
            y = sample_cube(size, table, enc)
            y = enc + n.strength * (y - enc)
            if n.output == "display":
                return y, True
            out = (cineon_inv if n.output == "cineon" else cct_inv)(y)
        else:
            return lin, False
        if n.mix < 1:
            out = cct_inv(cct(lin) + n.mix * (cct(out) - cct(lin)))
        return out, False

    def run(self, nodes, lin):
        for n in nodes:
            lin, done = self.node(n, lin)
            if done:
                return np.clip(lin, 0, 1)
        return self.odt(lin)


def input_linear(space, code):
    """Source code values (normalised full-range RGB) → scene-linear Rec.709."""
    if space in LOG_SPACES:
        return decode(space, code) @ matrix(space).T
    if space == "srgb":
        return np.where(code <= .04045, code / 12.92, ((code + .055) / 1.055) ** 2.4)
    if space == "bt709":
        return np.clip(code, 0, 1) ** 2.4
    if space in PRIMARIES:  # Rec.601: the same display gamma, its own primaries brought to Rec.709
        return (np.clip(code, 0, 1) ** 2.4) @ np.linalg.solve(_rgb_to_xyz(PRIMARIES["bt709"]), _rgb_to_xyz(PRIMARIES[space])).T
    raise ValueError("The colour graph grades log or SDR display sources; tone-map HDR to SDR first (process_color without graph)")


PRIMARIES = {"bt709": ((.64, .33), (.30, .60), (.15, .06)), "bt601_625": ((.64, .33), (.29, .60), (.15, .06)),
             "bt601_525": ((.630, .340), (.310, .595), (.155, .070))}


def _rgb_to_xyz(xy, white=(.3127, .3290)):
    """RGB -> XYZ for primaries (xy chromaticities) and a white point (D65)."""
    P = np.array([[x / y, 1.0, (1 - x - y) / y] for x, y in xy]).T
    W = np.array([white[0] / white[1], 1.0, (1 - white[0] - white[1]) / white[1]])
    return P * np.linalg.solve(P, W)


def chains(graph: Graph):
    """The outside chain (windows removed) and one chain per window (its inner nodes at its position)."""
    base = [n for n in graph.nodes if n.op != "window"]
    wins = []
    for i, w in enumerate(graph.nodes):
        if w.op == "window":
            wins.append((w, [m for m in graph.nodes[:i] if m.op != "window"] + list(w.nodes) + [m for m in graph.nodes[i + 1:] if m.op != "window"]))
    return base, wins


def bake(graph: Graph, space: str, exposure=0.0, size=None):
    """→ (outside .cube text, [window .cube text], checks). Grid over source code values."""
    size = size or (65 if space in LOG_SPACES else 33)
    g = np.linspace(0, 1, size)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")
    code = np.stack([r, gg, b], -1).reshape(-1, 3)
    lin = input_linear(space, code) * 2.0 ** exposure
    ev = Evaluator(graph, space)
    base, wins = chains(graph)
    text = lambda out, title: f'TITLE "{title}"\nLUT_3D_SIZE {size}\n' + "\n".join(f"{a:.6f} {c:.6f} {d:.6f}" for a, c, d in np.clip(out, 0, 1)) + "\n"
    cubes = [text(ev.run(base, lin), "EditVideo colour graph")] + [text(ev.run(ch, lin), f"EditVideo window {k}") for k, (_, ch) in enumerate(wins)]
    probe = np.array([[.18] * 3, [.0] * 3, [1.0] * 3, [4.0] * 3])  # scene-linear grey, black, diffuse white, +2 stops
    out = ev.run(base, probe.copy())
    checks = {"grey18_display": round(float(out[0] @ LUMA), 4), "black_display": round(float(out[1] @ LUMA), 4),
              "white_display": round(float(out[2] @ LUMA), 4), "plus2_stops_display": round(float(out[3] @ LUMA), 4),
              "output_transform": "filmic" if ev.filmic else "BT.1886 inverse (empty graph = identity)"}
    return cubes, [w for w, _ in wins], checks


def _boxes_at(w: Node, times):
    """Window box (x0, y0, x1, y1) per output time, padded; linear between samples, held outside them."""
    if w.box:
        arr = np.tile(np.array(w.box, float), (len(times), 1))
    else:
        if w.keys:
            ts = np.array([k["t"] for k in w.keys], float)
            bx = np.array([k["box"] for k in w.keys], float)
        else:
            from .windows import _boxes
            rows = _boxes(w.track)
            fps = w.track_fps or 30
            ts = w.track_start_s + np.array([r[0] for r in rows], float) / fps
            bx = np.array([r[1:] for r in rows], float)
        order = np.argsort(ts)
        ts, bx = ts[order], bx[order]
        arr = np.stack([np.interp(times, ts, bx[:, j]) for j in range(4)], 1)
    c, h = (arr[:, :2] + arr[:, 2:]) / 2, (arr[:, 2:] - arr[:, :2]) / 2 * (1 + w.pad)
    return np.concatenate([c - h, c + h], 1)


def write_mask(w: Node, path: Path, n_frames, rate, start_s, W, H, ffmpeg):
    """Feathered window mask (rgb24, R=G=B) at quarter resolution, encoded lossless (FFV1); scaled up in the merge.
    rate: the source frame rate as ffprobe reports it (e.g. "30000/1001")."""
    from fractions import Fraction
    fps = float(Fraction(str(rate)))
    mw, mh = max(16, W // 4 // 2 * 2), max(16, H // 4 // 2 * 2)
    times = start_s + np.arange(n_frames) / fps
    boxes = _boxes_at(w, times)
    ys, xs = (np.mgrid[0:mh, 0:mw] + .5)
    xs, ys = xs / mw * W, ys / mh * H
    feather = w.feather_px
    proc = subprocess.Popen([ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{mw}x{mh}", "-r", str(rate), "-i", "-",
                             "-c:v", "ffv1", str(path)], stdin=subprocess.PIPE)
    try:
        for x0, y0, x1, y1 in boxes:
            cx, cy, rx, ry = (x0 + x1) / 2 * W, (y0 + y1) / 2 * H, max(1, (x1 - x0) / 2 * W), max(1, (y1 - y0) / 2 * H)
            if w.shape == "ellipse":
                d = (np.hypot((xs - cx) / rx, (ys - cy) / ry) - 1) * min(rx, ry)
            else:
                qx, qy = np.abs(xs - cx) - rx, np.abs(ys - cy) - ry
                d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0)
            a = np.clip(.5 - d / feather, 0, 1)
            a = a * a * (3 - 2 * a)
            if w.invert:
                a = 1 - a
            v = (a * 255 + .5).astype(np.uint8)
            proc.stdin.write(np.repeat(v[:, :, None], 3, 2).tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode:
        raise RuntimeError("window mask encode failed")
    return {"mask": str(path), "frames": n_frames, "first_box": [round(float(v), 4) for v in boxes[0]], "last_box": [round(float(v), 4) for v in boxes[-1]]}


def filter_complex(m, r, cubes, masks_inputs, W, H, display_lut=None, spatial=()):
    """[0:v] source (+ [k:v] masks) → graded [out]. m/r: source matrix and range for the code-value decode."""
    head = f"[0:v]zscale=min={m}:rin={r}:m=gbr:r=full,format=gbrpf32le"
    tail = (f",lut3d=file={display_lut}:interp=tetrahedral" if display_lut else "") + \
        ",zscale=pin=bt709:tin=bt709:min=gbr:rin=full:p=bt709:t=bt709:m=bt709:r=limited:dither=error_diffusion,format=yuv420p" + \
        "".join("," + s for s in spatial) + "[out]"
    if len(cubes) == 1:
        return head + f",lut3d=file={cubes[0]}:interp=tetrahedral" + tail
    n = len(cubes)
    parts = [head + f",split={n}" + "".join(f"[s{i}]" for i in range(n)), f"[s0]lut3d=file={cubes[0]}:interp=tetrahedral[o0]"]
    for k in range(1, n):
        parts.append(f"[s{k}]lut3d=file={cubes[k]}:interp=tetrahedral[w{k}]")
        parts.append(f"[{masks_inputs[k - 1]}:v]scale={W}:{H}:flags=bicubic,format=gbrpf32le[m{k}]")
        parts.append(f"[o{k - 1}][w{k}][m{k}]maskedmerge[o{k}]")
    parts.append(f"[o{n - 1}]null" + tail)
    return ";".join(parts)


PRINT_LOOK = "print_film_cineon"


def build_print_look(size=33):
    """Original procedural print-film emulation (Cineon in → display Rec.709 out): a steeper print S-curve (grey ≈ .40),
    dense blacks, subtractive saturation roll-off in the highlights and a gentle cool-shadow / warm-highlight crossover."""
    from . import store
    from .color_pipeline import LUT_ROOT
    from .media import sha256
    g = np.linspace(0, 1, size)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")
    lin = cineon_inv(np.stack([r, gg, b], -1).reshape(-1, 3))
    lin = .18 * np.power(np.maximum(lin, 0) / .18, 1.12)
    v = to_display(lin, .40)
    y = (v @ LUMA)[:, None]
    sat = 1.04 - .4 * np.clip((y - .62) / .38, 0, 1) ** 2
    v = y + sat * (v - y)
    v = v + (y - .40) * np.array([.035, .004, -.03]) * (1 - np.abs(y - .40) * 1.2)
    path = LUT_ROOT / f"{PRINT_LOOK}.cube"
    path.write_text(f'TITLE "EditVideo print film (Cineon in)"\nLUT_3D_SIZE {size}\n' + "\n".join(f"{a:.6f} {c:.6f} {d:.6f}" for a, c, d in np.clip(v, 0, 1)) + "\n", encoding="ascii")
    manifest = store.read_json(LUT_ROOT / "manifest.json")
    entry = {"id": PRINT_LOOK, "description": "Print-film emulation: S-curve, dense blacks, highlight saturation roll-off, cool/warm crossover",
             "file": path.name, "sha256": sha256(path), "size": size, "input": "cineon",
             "domain": "Cineon log (printing density) in → display BT.709 out; use as a colour-graph look with input cineon",
             "origin": "Original procedural EditVideo transform; no third-party look pack"}
    manifest["luts"] = [l for l in manifest["luts"] if l["id"] != PRINT_LOOK] + [entry]
    store.write_json(LUT_ROOT / "manifest.json", manifest)
    return entry
