"""The series bible: one palette, one type pair, one label scale, one camera language, one light and one finish that
every generator reads, so a film keeps one look across hours (the lesson of Antenna's Turning Point and Elastic's
WWII: From the Frontlines; reports/Nâng cấp 3D phim tài liệu.md, P0-2). Bibles live in assets/style/<id>.json;
EDITVIDEO_STYLE picks another. A scene's explicit values still win: the bible supplies defaults, not orders."""
import json, os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "assets" / "style"
DEFAULT = "documentary_vn"


@lru_cache(maxsize=8)
def load(name=None):
    name = name or os.environ.get("EDITVIDEO_STYLE") or DEFAULT
    p = ROOT / f"{name}.json"
    if not p.is_file():
        raise ValueError(f"No style bible {name}; have {sorted(x.stem for x in ROOT.glob('*.json'))}")
    return json.loads(p.read_text(encoding="utf-8"))


def get(path, name=None, default=None):
    """A value by dotted path, e.g. get("palette.sides.socialist_bloc")."""
    v = load(name)
    for k in path.split("."):
        if not isinstance(v, dict) or k not in v:
            return default
        v = v[k]
    return v


def typography(role="label", name=None):
    """The design tokens of one text role in the bible's type style."""
    from .design_library import tokens
    return tokens(load(name)["typography_style"])["typography"][role]


def blender_defaults(template, name=None):
    """Template parameters the bible fixes, under whatever a scene sets explicitly."""
    s = load(name)
    L, R, P = s["light"], s["render"], s["palette"]
    common = {"color_depth": R["color_depth"]}
    if template == "terrain_shot":
        return {**common, "sun": {"azimuth": L["sun_azimuth"], "elevation": L["sun_elevation"], "strength": L["sun_strength"], "color": L["sun_color"]},
                "shadow_tint": L.get("shadow_tint", "#5a6a80"),
                "sky": dict(L["sky"]), "haze": dict(s["atmosphere"]["haze"]), "shutter": s["camera"]["shutter"],
                "view": R["terrain_view_transform"], "look": R["terrain_look"], "samples": R["samples"]}
    if template == "bloc_map":
        return {**common, "land": P["land"], "sea": P["sea"], "table": P["table"], "view": s["map"]["view_transform"], "look": "None",
                "flow_glow": s["map"]["flow_glow"], "bead_glow": s["map"]["bead_glow"], "flow_style": s["map"]["flow_style"]}
    if template in ("domino_shot", "globe_shot"):
        return dict(common)
    return {}


def hold_frames(text, lang="vi", fps=30, busy=False, over_narration=False, name=None):
    """Frames a line of on-screen text must stay to be read (reading speed by language, a floor, extras for busy
    ground or competing narration); fades in and out do not count."""
    lb = load(name)["label"]
    cps = lb["cps_vi"] if lang == "vi" else lb["cps_en"]
    s_ = max(lb["min_hold_s"], len(text.strip()) / cps)
    s_ += lb["busy_ground_extra_s"] if busy else 0.0
    s_ += lb["over_narration_extra_s"] if over_narration else 0.0
    return int(round(s_ * fps))
