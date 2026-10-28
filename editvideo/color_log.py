"""Camera log inputs → display Rec.709, the first node of every log grade.

Published transfer functions (Sony S-Log3, ARRI LogC3 EI800, Panasonic V-Log) decode code values to scene-linear
camera RGB; gamut matrices are derived from the published primaries (D65 white for all) instead of copied constants;
a filmic shoulder (Hable) maps scene-linear to display, normalised so 18 % grey lands at `grey_display`, then the
BT.1886 inverse (gamma 2.4) encodes display Rec.709. Everything is baked into one 3D LUT applied to normalised
full-range RGB decoded without any transfer conversion.
"""
import numpy as np

PRIMARIES = {  # (R, G, B) xy, white D65
    "slog3": ((0.766, 0.275), (0.225, 0.800), (0.089, -0.087)),   # S-Gamut3.Cine
    "logc3": ((0.6840, 0.3130), (0.2210, 0.8480), (0.0861, -0.1020)),  # ARRI Wide Gamut 3
    "vlog": ((0.730, 0.280), (0.165, 0.840), (0.100, -0.030)),    # V-Gamut
    "logc4": ((0.7347, 0.2653), (0.1424, 0.8576), (0.0991, -0.0308)),  # ARRI Wide Gamut 4
    "log3g10": ((0.780308, 0.304253), (0.121595, 1.493994), (0.095612, -0.084589)),  # REDWideGamutRGB
    "applelog": ((0.708, 0.292), (0.170, 0.797), (0.131, 0.046)),  # Rec.2020
    "flog2": ((0.708, 0.292), (0.170, 0.797), (0.131, 0.046)),     # F-Gamut (= Rec.2020)
    "bmdfilm5": ((0.7177215, 0.3171181), (0.2280410, 0.8615690), (0.1005841, -0.0820452)),  # Blackmagic Wide Gamut Gen5
    "rec709": ((0.64, 0.33), (0.30, 0.60), (0.15, 0.06)),
}
D65 = (0.3127, 0.3290)
NAMES = {"slog3": "Sony S-Log3 / S-Gamut3.Cine", "logc3": "ARRI LogC3 (EI 800) / Wide Gamut 3", "vlog": "Panasonic V-Log / V-Gamut",
         "logc4": "ARRI LogC4 / Wide Gamut 4", "log3g10": "RED Log3G10 / REDWideGamutRGB", "applelog": "Apple Log / Rec.2020",
         "flog2": "Fujifilm F-Log2 / F-Gamut", "bmdfilm5": "Blackmagic Film Gen 5 / Wide Gamut Gen 5"}
LOG_SPACES = tuple(NAMES)
# 18 % grey code value of each encoding (published landmarks; tests check decode(grey) == 0.18).
GREY_CODE = {"slog3": 420 / 1023, "logc3": 0.391007, "vlog": 0.423311, "logc4": 0.278396, "log3g10": 1 / 3, "applelog": 0.488271,
             "flog2": 0.391007, "bmdfilm5": 0.383562}


def decode(name, v):
    """Normalised code value (0..1 of full range) → scene-linear reflectance (0.18 = mid grey)."""
    v = np.asarray(v, float)
    if name == "slog3":
        code = v * 1023
        return np.where(code >= 171.2102946929, np.power(10, (code - 420) / 261.5) * (0.18 + 0.01) - 0.01,
                        (code - 95) * 0.01125 / (171.2102946929 - 95))
    if name == "logc3":
        cut, a, b, c, d, e, f = 0.010591, 5.555556, 0.052272, 0.247190, 0.385537, 5.367655, 0.092809
        return np.where(v > e * cut + f, (np.power(10, (v - d) / c) - b) / a, (v - f) / e)
    if name == "vlog":
        cut2, b, c, d = 0.181, 0.00873, 0.241514, 0.598206
        return np.where(v < cut2, (v - 0.125) / 5.6, np.power(10, (v - d) / c) - b)
    if name == "logc4":
        a, b, c = (2 ** 18 - 16) / 117.45, (1023 - 95) / 1023, 95 / 1023
        s_ = (7 * np.log(2) * 2 ** (7 - 14 * c / b)) / (a * b)
        t = (2 ** (14 * (-c / b) + 6) - 64) / a
        return np.where(v >= c, (np.power(2, 14 * (v - c) / b + 6) - 64) / a, v * s_ + t)
    if name == "log3g10":
        return np.where(v < 0, v / 15.1927, (np.power(10, v / 0.224282) - 1) / 155.975327) - 0.01
    if name == "applelog":
        R0, Rt, c, b, g, d = -0.05641088, 0.01, 47.28711236, 0.00964052, 0.08550479, 0.69336945
        Pt = c * (Rt - R0) ** 2
        return np.where(v >= Pt, np.power(2, (v - d) / g) - b, np.where(v > 0, np.sqrt(np.clip(v, 0, None) / c) + R0, R0))
    if name == "flog2":
        a, b, c, d, e, f, cut2 = 5.555556, 0.064829, 0.245281, 0.384316, 8.799461, 0.092864, 0.100686
        return np.where(v >= cut2, (np.power(10, (v - d) / c) - b) / a, (v - f) / e)
    if name == "bmdfilm5":
        A, B, C, D, E, lin_cut = 0.08692876065491224, 0.005494072432257808, 0.5300133392291939, 8.283605932402494, 0.09246575342465753, 0.005
        log_cut = D * lin_cut + E
        return np.where(v < log_cut, (v - E) / D, np.exp((v - C) / A) - B)
    raise ValueError(f"Unknown log space {name}")


def rgb_to_xyz(primaries, white=D65):
    xyz = lambda x, y: np.array([x / y, 1.0, (1 - x - y) / y])
    P = np.stack([xyz(*p) for p in primaries], 1)
    S = np.linalg.solve(P, xyz(*white))
    return P * S


def matrix(name):
    """Camera-gamut linear RGB → Rec.709 linear RGB."""
    return np.linalg.inv(rgb_to_xyz(PRIMARIES["rec709"])) @ rgb_to_xyz(PRIMARIES[name])


def _hable(x):
    A, B, C, D, E, F = .15, .50, .10, .20, .02, .30
    return ((x * (A * x + C * B) + D * E) / (x * (A * x + B) + D * F)) - E / F


def to_display(lin, grey_display=.42, white=11.2):
    """Scene-linear Rec.709 → display code values with a filmic shoulder; 18 % grey → grey_display."""
    target = grey_display ** 2.4  # display-linear level of grey
    lo, hi = .01, 100.0
    for _ in range(60):  # exposure k so tonemapped grey hits the target
        k = (lo * hi) ** .5
        if _hable(.18 * k) / _hable(white) < target:
            lo = k
        else:
            hi = k
    y = _hable(np.clip(lin, 0, None) * k) / _hable(white)
    return np.clip(y, 0, 1) ** (1 / 2.4)


def cube(name, exposure=0.0, size=33, grey_display=.42):
    g = np.linspace(0, 1, size)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")  # red fastest
    code = np.stack([r, gg, b], -1).reshape(-1, 3)
    lin = decode(name, code) @ matrix(name).T * (2.0 ** exposure)
    out = to_display(lin, grey_display)
    return f"TITLE \"{NAMES[name]} to Rec.709\"\nLUT_3D_SIZE {size}\n" + "\n".join(f"{a:.6f} {c:.6f} {d:.6f}" for a, c, d in out) + "\n"
