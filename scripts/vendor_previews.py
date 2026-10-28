"""Vendor the library previews into the repository (assets/previews/) with repo-relative paths.

The atlas builders (design_atlas.py, build_lut_atlas.py, the effect atlas) write into outputs/, which is not shipped.
This copies the preview images the catalogs serve (downscaled JPEG, ≤ 960 px) and writes compact atlas JSON files whose
paths are relative to the repository root, so read_design_preview / effect_catalog work from any clone location.
Usage: python scripts/vendor_previews.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "previews"
sys.path.insert(0, str(ROOT))


def vendor(src, sub, name=None):
    """Copy one preview image (downscaled JPEG) and return its repo-relative path, or None when missing."""
    p = Path(src)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return None
    dst = OUT / sub / ((name or p.stem) + ".jpg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        with Image.open(p) as im:
            im = im.convert("RGB")
            im.thumbnail((960, 960))
            im.save(dst, quality=85, optimize=True)
    return dst.relative_to(ROOT).as_posix()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    src = ROOT / "outputs"
    d = json.loads((src / "design-atlas.json").read_text(encoding="utf-8"))
    previews = {}
    for key, v in d.get("previews", {}).items():
        rel = vendor(v["path"], "design")
        if rel:
            previews[key] = {k: val for k, val in v.items() if k != "path"} | {"path": rel}
    (OUT / "design-atlas.json").write_text(json.dumps({"entries": d.get("entries", []), "previews": previews, "scope": d.get("scope")},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
    lut = json.loads((src / "color-lut-atlas.json").read_text(encoding="utf-8"))
    entries = []
    for e in lut["entries"]:
        rel = vendor(e["path"], "lut", e["id"])
        if rel:
            entries.append({"id": e["id"], "path": rel, "lut_sha256": e.get("lut_sha256")})
    (OUT / "color-lut-atlas.json").write_text(json.dumps({"entries": entries, "scope": lut.get("scope")}, ensure_ascii=False, indent=1), encoding="utf-8")
    current = OUT / "effect-atlas.json"
    if current.exists() and json.loads(current.read_text(encoding="utf-8")).get("version") == 2:
        print(f"vendored {len(previews)} design previews, {len(entries)} LUT previews; effect atlas v2 is built in place by scripts/effect_atlas.py")
        return
    fx = json.loads((src / "effect-atlas.json").read_text(encoding="utf-8"))
    engines = {}
    for eng, v in fx.get("engines", {}).items():
        frames = []
        for i, f in enumerate(v.get("frames", [])):
            rel = vendor(f["path"], f"effects/{eng}", f"page-{i:02d}")
            video = src / f"effects-{eng}.mp4"
            if not rel and video.exists():  # observation frames are temporary: re-read the page from the atlas video
                tmp = Path(tempfile.gettempdir()) / f"editvideo-{eng}-page-{i:02d}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(f["timestamp"]), "-i", str(video), "-frames:v", "1", str(tmp)], check=True)
                rel = vendor(tmp, f"effects/{eng}", f"page-{i:02d}")
                tmp.unlink()
            frames.append({"index": f["index"], "timestamp": f["timestamp"], "path": rel})
        engines[eng] = {"frames": frames, "video": None}  # the atlas videos are release assets, not repository files
    (OUT / "effect-atlas.json").write_text(json.dumps({"effects": fx["effects"], "engines": engines}, ensure_ascii=False, indent=1), encoding="utf-8")
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"vendored {len(previews)} design previews, {len(entries)} LUT previews, {sum(len(v['frames']) for v in engines.values())} effect pages; {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
