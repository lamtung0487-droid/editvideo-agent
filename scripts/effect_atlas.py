"""Effect atlas v2: every catalog effect (and every combination recipe) rendered on its own stage with content that
shows it (a scene with highlights for light effects, text for text effects, a cut-out for keying/wrap effects, fire on
black for luma keys, a moving card for motion blur), side by side with the untouched source, in both engines.

Each preview is a strip: [source | t+10 | t+30 | t+52] frames of the stage, so a model sees what the effect does over
time, not one frame. Strips and assets/previews/effect-atlas.json (version 2, repo-relative paths) are written into the
repository. Usage: python scripts/effect_atlas.py [--missing]  (--missing: only effects/combos without strips, merged in)
"""
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFilter
from editvideo import agent, store
from editvideo.effects import CATALOG
from editvideo.effect_guide import COMBOS
from editvideo.code_engine import scaffold
from editvideo.jobs import Worker
from editvideo.media import command, FFMPEG

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "previews"
STAGE, COMBO_STAGE = 60, 90
BEFORE = (.03, .2, .45, .62)   # x, y, w, h of the untouched source panel
AFTER = (.52, .2, .45, .62)    # the panel with the effect
LOOP = {"float", "pulse", "shake", "orbit", "spin", "handheld", "gate_weave", "boil", "jitter", "glitch", "heat_distortion",
        "defocus_pulse", "fade_pulse", "light_sweep"}
LOOK_FAMILIES = {"grade", "light", "texture", "frame"}
TUNED = {  # parameters that make each effect readable at preview size
    "halation": {"amount": 1.6, "threshold": .68, "radius": 22}, "highlight_glow": {"amount": 1.2, "threshold": .7, "radius": 24},
    "bloom": {"amount": 18, "color": "#ffb35a"}, "glow": {"amount": 22, "color": "#5ad1ff"}, "light_wrap": {"amount": .85, "radius": 16, "color": "#ffd7a0"},
    "tint_fill": {"amount": 1, "color": "#5ad1ff"}, "luma_alpha": {"amount": 1, "clip_black": .05, "clip_white": .6},
    "heat_distortion": {"amount": 8}, "rgb_split": {"amount": 5}, "tracking": {"amount": .02, "from_em": .35},
    "color_to": {"amount": 1, "color": "#ffd166"}, "focus_zoom": {"amount": .25, "focus_x": .7, "focus_y": .35},
}


def make_media(folder):
    """Original procedural images (no third-party rights)."""
    folder.mkdir(parents=True, exist_ok=True)
    W, H = 1280, 720
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):  # dusk sky: deep blue → orange near the horizon
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(20 + 220 * t ** 2), int(30 + 90 * t ** 1.5), int(70 + 40 * (1 - t))))
    d.ellipse((860, 300, 980, 420), fill=(255, 244, 214))  # sun: a real highlight for glow/halation
    d.polygon([(0, 560), (220, 430), (420, 520), (640, 400), (900, 540), (1280, 450), (1280, 720), (0, 720)], fill=(18, 22, 30))
    for i, (x, y) in enumerate([(120, 600), (260, 640), (410, 610), (560, 650), (700, 600), (1080, 620)]):
        d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(255, 236, 190))  # lamps
    for i, c in enumerate([(220, 60, 60), (60, 180, 90), (60, 110, 230)]):
        d.rectangle((60 + i * 110, 60, 150 + i * 110, 150), fill=c)  # colour patches for grades
    im.save(folder / "scene.png")
    card = Image.new("RGB", (640, 480), "#204658")
    cd = ImageDraw.Draw(card)
    for i, color in enumerate(("#81e6be", "#ffbd68", "#e077a4")):
        cd.ellipse((50 + i * 190, 140, 230 + i * 190, 320), fill=color)
    card.save(folder / "card.png")
    cut = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
    cc = ImageDraw.Draw(cut)
    cc.polygon([(300, 40), (380, 200), (380, 450), (220, 450), (220, 200)], fill=(226, 230, 236, 255))  # rocket
    cc.polygon([(220, 360), (140, 470), (220, 450)], fill=(200, 60, 60, 255))
    cc.polygon([(380, 360), (460, 470), (380, 450)], fill=(200, 60, 60, 255))
    cc.ellipse((265, 220, 335, 290), fill=(60, 110, 230, 255))
    cut.save(folder / "cutout.png")
    back = Image.new("RGB", (1280, 720))
    bd = ImageDraw.Draw(back)
    for x in range(1280):
        t = x / 1280
        bd.line([(x, 0), (x, 720)], fill=(int(255 - 60 * t), int(200 - 80 * t), int(140 + 60 * t)))
    back.save(folder / "backdrop.png")
    fire = Image.new("RGB", (960, 640), "black")
    fd = ImageDraw.Draw(fire)
    for r, c in [(240, (90, 25, 5)), (170, (200, 70, 10)), (110, (255, 150, 40)), (55, (255, 230, 170))]:
        fd.ellipse((480 - r, 420 - r * 1.3, 480 + r, 420 + r * .4), fill=c)
    for i in range(40):
        x, y = 300 + (i * 97) % 360, 80 + (i * 53) % 260
        fd.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 200, 120))
    fire.filter(ImageFilter.GaussianBlur(6)).save(folder / "fire.png")
    return {k: folder / f"{k}.png" for k in ("scene", "card", "cutout", "backdrop", "fire")}


def content(name, spec):
    """(subject kind, backdrop or None) that shows this effect."""
    if name in ("light_wrap", "tint_fill", "shadow"):
        return "cutout", "backdrop"
    if name == "glow":
        return "cutout", None
    if name == "luma_alpha":
        return "fire", "scene"
    if name == "progress":
        return "chart", None
    if name == "motion_blur":
        return "moving_card", None
    if spec["family"] == "text" or name == "color_to":
        return "text", None
    if spec["family"] in ("grade", "light", "texture", "mask", "frame", "camera"):
        return "scene", None
    return "card", None


def panel(box, start, end, lid, kind, A, effects=(), keyframes=None, blend="normal", z=20):
    x, y, w, h = box
    base = {"id": lid, "start_frame": start, "end_frame": end, "x": x, "y": y, "width": w, "height": h, "z": z, "effects": list(effects), "blend": blend}
    if keyframes:
        base["keyframes"] = keyframes
    if kind == "text":
        return {**base, "kind": "text", "text": "Tri thức\nchuyển động", "font_id": "inter", "font_weight": 700, "font_size": 92, "line_height": 1.3,
                "color": "#f2f2ee", "data": {"align": "center"}}
    if kind == "chart":
        return {**base, "kind": "bar_chart", "data": {"values": [35, 80, 55], "labels": ["A", "B", "C"], "max": 100}, "color": "#81e6be"}
    asset = {"moving_card": "card", "fire": "fire"}.get(kind, kind)
    return {**base, "kind": "image", "asset_id": A[asset], "fit": "contain" if kind in ("cutout", "fire") else "cover"}


def stage(name, spec, i0, n, A):
    kind, back = content(name, spec)
    params = {**(spec["example"].get("params") or {}), **TUNED.get(name, {})}
    if spec["family"] in LOOK_FAMILIES and name not in LOOP and name not in ("flash", "white_flash", "chroma_split"):  # impact accents decay: show them over time
        s, e = 0, 1
    elif name in LOOP:
        s, e = 0, n
    else:
        s, e = 6, 42
    fx = [{"name": name, "start_frame": s, "end_frame": e, "params": params, "easing": spec["example"].get("easing", "smooth")}]
    return layers_for(name, kind, back, i0, n, A, fx)


def layers_for(lid, kind, back, i0, n, A, fx):
    out = []
    keys = {"x": [{"frame": 6, "value": -200}, {"frame": 40, "value": 200, "easing": "linear"}]} if kind == "moving_card" else None
    for side, box in (("before", BEFORE), ("after", AFTER)):
        if back:
            out.append(panel(box, i0, i0 + n, f"{lid}-{side}-back", back, A, z=10))
        out.append(panel(box, i0, i0 + n, f"{lid}-{side}", kind, A, fx if side == "after" else [], keys, "add" if kind == "fire" and side == "after" else "normal"))
    out.append({"id": f"{lid}-label", "kind": "text", "start_frame": i0, "end_frame": i0 + n, "x": .03, "y": .06, "width": .9, "height": .08, "z": 30,
                "text": lid, "font_id": "ibmplexmono", "font_size": 44, "color": "#ffffff"})
    for tag, x in (("gốc", BEFORE[0]), ("hiệu ứng", AFTER[0])):
        out.append({"id": f"{lid}-tag-{'a' if x > .5 else 'b'}", "kind": "text", "start_frame": i0, "end_frame": i0 + n, "x": x, "y": .84, "width": .3,
                    "height": .06, "z": 30, "text": tag, "font_id": "inter", "font_size": 30, "color": "#9fb3c0"})
    return out


def combo_stage(cid, combo, i0, n, A):
    target = combo.get("target", "scene" if cid in ("archival_film", "documentary_push") else "card")
    back = {"fire": "scene", "cutout": "backdrop"}.get(target)
    fx = [{"name": e["name"], "start_frame": 0 if e["name"] in LOOP or CATALOG[e["name"]]["family"] in LOOK_FAMILIES else 8,
           "end_frame": n if e["name"] in LOOP else (1 if CATALOG[e["name"]]["family"] in LOOK_FAMILIES else 50), "params": e.get("params", {}), "easing": "smooth"}
          for e in combo["stack"]]
    if cid == "neon_tech":
        target = "text"
    out = layers_for(cid, target, back, i0, n, A, fx)
    if cid == "neon_tech":
        for l in out:
            if l["id"] in (f"{cid}-before", f"{cid}-after"):
                l["text"] = "DATA 2026"
    return out


def main():
    store.initialize(recover=False)
    names = list(CATALOG)
    combos = list(COMBOS)
    old = None
    if "--missing" in sys.argv and (OUT / "effect-atlas.json").is_file():  # render only what has no strip yet
        old = json.loads((OUT / "effect-atlas.json").read_text(encoding="utf-8"))
        names = [n for n in names if n not in old.get("effects", {})]
        combos = [c for c in combos if c not in old.get("combos", {})]
        if not names and not combos:
            print("atlas complete")
            return
    total = len(names) * STAGE + len(combos) * COMBO_STAGE
    p = agent.create({"title": "EditVideo · Effect Atlas v2", "script": "Thư viện hiệu ứng cho AI.", "profile": "landscape", "captions": False})
    pid = p["id"]
    signal = store.folder(pid) / "signal.wav"
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=180:sample_rate=48000:duration={total / 30}", signal])  # renders require an audible track
    a = agent.import_media(pid, str(signal))
    p = store.get_project(pid)
    store.update_project(pid, {**p["config"], "narration_id": a["id"]})
    media = make_media(store.folder(pid) / "atlas-media")
    A = {k: agent.import_media(pid, str(v))["id"] for k, v in media.items()}
    j = store.create_job(pid, "plan")
    Worker().run(j["id"])
    assert store.get_job(j["id"])["state"] == "completed"
    p = agent.read(pid)
    t = p["timeline"]
    assert t["total_frames"] == total, (t["total_frames"], total)
    shots, layers, index = [], [], {}
    f = 0
    for name in names:
        shots.append({"id": f"st-{name}", "beat_id": "atlas", "start_frame": f, "end_frame": f + STAGE, "text": "", "motion": "hold"})
        layers += stage(name, CATALOG[name], f, STAGE, A)
        index[name] = {"start": f, "n": STAGE}
        f += STAGE
    for cid in combos:
        shots.append({"id": f"st-{cid}", "beat_id": "atlas", "start_frame": f, "end_frame": f + COMBO_STAGE, "text": "", "motion": "hold"})
        layers += combo_stage(cid, COMBOS[cid], f, COMBO_STAGE, A)
        index[cid] = {"start": f, "n": COMBO_STAGE, "combo": True}
        f += COMBO_STAGE
    t["shots"], t["layers"], t["cues"] = shots, layers, []
    t.setdefault("design", {})["background"] = "#0d1418"
    agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
    if "--check" in sys.argv:  # quick look at a few stages before the full renders
        from editvideo import snapshot
        from editvideo.code_engine import scaffold as _sc
        _sc(pid, "remotion")
        keys = ["halation", "light_wrap", "luma_alpha", "motion_blur", "text_animate", "tritone", "impact_title", "fire_composite"]
        r = snapshot.snapshot(pid, "remotion", [index[k]["start"] + 30 for k in keys])
        print(json.dumps({"pid": pid, "frames": [f["path"] for f in r["frames"]]}))
        return
    tmp = store.DATA / "tmp" / "atlas-render"
    tmp.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = os.environ["TMP"] = str(tmp)  # renderer scratch on the data drive, not a full system drive
    manifest = old or {"version": 2, "panels": ["source", "t+10", "t+30", "t+52"], "effects": {}, "combos": {}}
    W, H = 1920, 1080
    crop = lambda box: (round(box[0] * W), round(box[1] * H), round((box[0] + box[2]) * W), round((box[1] + box[3]) * H))
    for engine in ("remotion", "hyperframes"):
        p = store.get_project(pid)
        store.update_project(pid, {**p["config"], "renderer": engine})
        scaffold(pid, engine)
        j = store.create_job(pid, "final")
        Worker().run(j["id"])
        r = agent.result(j["id"])
        assert r["state"] == "completed", r["error"]
        video = store.folder(pid) / "jobs" / j["id"] / "final.mp4"
        frames_dir = tmp / f"frames-{engine}"
        frames_dir.mkdir(exist_ok=True)
        dst = OUT / "effects" / engine
        dst.mkdir(parents=True, exist_ok=True)
        for key, ix in index.items():
            n = ix["n"]
            picks = [10, 30, 52] if n == STAGE else [15, 45, 80]
            shots_png = []
            for k, lf in enumerate(picks):
                out = frames_dir / f"{key}-{k}.png"
                subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{(ix['start'] + lf + .5) / 30:.4f}", "-i", str(video), "-frames:v", "1", str(out)], check=True)
                shots_png.append(out)
            tiles = []
            with Image.open(shots_png[1]) as mid:
                tiles.append(mid.crop(crop(BEFORE)).resize((320, 248)))
            for pth in shots_png:
                with Image.open(pth) as fr:
                    tiles.append(fr.crop(crop(AFTER)).resize((320, 248)))
            strip = Image.new("RGB", (4 * 320 + 3 * 4, 248), "#0d1418")
            for k, tile in enumerate(tiles):
                strip.paste(tile, (k * 324, 0))
            path = dst / f"{key}.jpg"
            strip.save(path, quality=82, optimize=True)
            rel = path.relative_to(ROOT).as_posix()
            slot = manifest["combos" if ix.get("combo") else "effects"].setdefault(key, {"frames": [ix["start"] + q for q in picks], "strip": {}})
            slot["strip"][engine] = rel
        print(json.dumps({"engine": engine, "job": j["id"], "frames": total}), flush=True)
    (OUT / "effect-atlas.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("atlas", len(manifest["effects"]), "effects,", len(manifest["combos"]), "combos", flush=True)


if __name__ == "__main__":
    main()
