"""Fix pass 4 (round 6, from the independent review): fused Vietnamese marks in the title (ink-measured line height),
Lunar Module framed for the whole turn, letterbox bars on the VAB plate hidden (projection re-mapped), Orion beat
given motion (a larger push about Earth, window/ring riding the same zoom, a spotlight instead of an invisible lift),
the same-clip dissolve replaced by a seamless cut + animated blur/dim, an ending that resolves to black, readable time
cards, reading-time typewriter holds. Usage: patch_artemis4.py"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store
store.initialize(recover=False)
ROOT = str(Path(__file__).resolve().parents[3])
PID = json.load(open(ROOT + r"\data\films\project-artemis.json"))["pid"]
rev = lambda: m.editvideo_read_project(PID)["revision"]
tl = lambda: {l["id"]: l for l in json.load(open(store.folder(PID) / "plan" / "timeline.json", encoding="utf-8"))["layers"]}
shots = lambda: {s["id"]: s for s in json.load(open(store.folder(PID) / "plan" / "timeline.json", encoding="utf-8"))["shots"]}
up = lambda l: {"op": "upsert_layer", "layer": l}
FOCUS = (.5695, .7667)  # Earth in the Orion frame (the focus_zoom fixed point)
ZOOM = .7

# 1969: Lunar Module re-composed at its scale with a camera fitted to the whole turn, archival look re-applied.
lm_asset = next(a["id"] for a in store.assets(PID) if a["name"].endswith(".glb"))
r = m.editvideo_compose_product(PID, rev(), 0, 240, model=lm_asset, id="lm", turn_deg_per_s=24, light=.38, ground=False, studio=False, bloom=False, size=3.0)
print("lm camera", r["beats"].get("camera_distance"))
L = tl()
lm = L["lm"]
lm["effects"] = [{"name": "tritone", "start_frame": 0, "end_frame": 1, "params": {"amount": .45, "shadow_color": "#0d0906", "color": "#7a5c3c", "highlight_color": "#f1e2c6"}},
                 {"name": "halation", "start_frame": 0, "end_frame": 1, "params": {"amount": .45, "threshold": .82, "radius": 14}},
                 {"name": "gate_weave", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.0}},
                 {"name": "fade_in", "start_frame": 0, "end_frame": 12}]
tel = L["telemetry"]
for e in tel["effects"]:
    if e["name"] == "typewriter":
        e["params"].pop("hold", None)  # reading-time holds (the 6-word line now stays ~2.4 s)
        e["params"]["cps"] = 22
m.editvideo_patch_timeline(PID, rev(), [up(lm), up(tel)])

# Title: the recipe now measures the ink of "TRỞ LẠI / MẶT TRĂNG" (needs 1.3, was 1.2: the dot fused with the breve).
m.editvideo_compose_title(PID, rev(), {"recipe": "title_card", "id": "title", "preset": "impact", "text": "Trở lại\nMặt Trăng", "start_frame": 240, "end_frame": 330,
                                       "hit_frame": 254, "black_before": 14, "cap": .2, "exit": "fade", "exit_frames": 10})
# Time cards: 30 px detail with a shadow (readable over street lights).
X = lambda req: m.editvideo_compose_explainer(PID, rev(), req)
X({"recipe": "doc_timecard", "id": "tc69", "start_frame": 70, "end_frame": 236, "year": 1969, "label": "Quá khứ", "detail": "Biển Tĩnh Lặng · Mặt Trăng", "z": 700})
X({"recipe": "doc_timecard", "id": "tc22", "start_frame": 350, "end_frame": 596, "year": 2022, "roll_from": 1969, "roll_frames": 50, "label": "Hiện tại", "detail": "Kennedy, Florida"})
X({"recipe": "doc_timecard", "id": "tclaunch", "start_frame": 678, "end_frame": 954, "year": 2022, "label": "Phóng · 16.11", "detail": "Bệ phóng 39B"})

# VAB plate: the source is letterboxed (22 px bars in 720p): punch 7 % about the centre and re-map the projection's
# corner-pin track by the same scale so ARTEMIS stays on the facade.
S = shots()
s3 = S["s3"]
s3["effects"] = [e for e in s3.get("effects", []) if e["name"] != "focus_zoom"] + [
    {"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .07, "focus_x": .5, "focus_y": .5, "cut": True}}]
L = tl()
vab = L["vab-title"]
k = 1.07
for smp in vab["corner_pin"]["track"]:
    smp["corners"] = [[round(.5 + (x - .5) * k, 5), round(.5 + (y - .5) * k, 5)] for x, y in smp["corners"]]

# Orion: a larger push about Earth (1.0 → 1.7) so the beat moves and Earth reads; window and ring ride the same zoom
# (scale keys about the focus point, sampled from the shot's ease_in_out curve); the window darkens the surround.
s6 = S["s6"]
s6_len = s6["end_frame"] - s6["start_frame"]
for e in s6["effects"]:
    if e["name"] == "focus_zoom":
        e["params"]["amount"] = ZOOM
        e["start_frame"], e["end_frame"] = 0, s6_len - 1
ease = lambda p: 2 * p * p if p < .5 else 1 - (-2 * p + 2) ** 2 / 2  # ease_in_out (power2.inOut, as effects.js)


def ride(layer):
    a, b = layer["start_frame"], layer["end_frame"]
    keys = []
    for f in list(range(0, b - a, 15)) + [b - a - 1]:
        g = a + f - s6["start_frame"]
        keys.append({"frame": f, "value": round(1 + ZOOM * ease(min(1, max(0, g / (s6_len - 1)))), 4), "easing": "linear"})
    layer["keyframes"] = {**layer.get("keyframes", {}), "scale": keys}
    layer["anchor"] = [round((FOCUS[0] - layer["x"]) / layer["width"], 4), round((FOCUS[1] - layer["y"]) / layer["height"], 4)]
    return layer


win = L["earth-window"]
win["data"] = {"exposure": -.55, "saturation": .75}
win["mask_invert"] = True  # spotlight: Earth is already a highlight, so the surround goes down instead
ride(win)
ring = ride(L["ring"])
for name in ("dist", "record"):
    L[name]["effects"] = [e for e in L[name]["effects"] if e["name"] != "shadow"] + [{"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 12}}]

# s7: no same-clip dissolve. A seamless cut (s7 starts at s6's final framing), then blur and a dim ramp in; a slow push;
# the poster title drifts open; everything resolves to black over the last 24 frames.
s7 = S["s7"]
s7.pop("transition", None)
s7_len = s7["end_frame"] - s7["start_frame"]
s7["effects"] = [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": ZOOM, "focus_x": FOCUS[0], "focus_y": FOCUS[1], "cut": True}}]
s7["keyframes"] = {"blur": [{"frame": 0, "value": 0}, {"frame": 20, "value": 8, "easing": "ease_out"}],
                   "scale": [{"frame": 0, "value": 1}, {"frame": s7_len - 1, "value": 1.06, "easing": "linear"}]}
dim = {"id": "end-dim", "kind": "shape", "start_frame": s7["start_frame"], "end_frame": s7["end_frame"], "x": 0, "y": 0, "width": 1, "height": 1, "z": 850,
       "color": "#000000", "data": {"shape": "rectangle", "corner_radius": 0},
       "keyframes": {"opacity": [{"frame": 0, "value": 0}, {"frame": 20, "value": .55, "easing": "ease_out"}, {"frame": s7_len - 25, "value": .55}]}}
black = {"id": "end-black", "kind": "shape", "start_frame": s7["end_frame"] - 26, "end_frame": s7["end_frame"], "x": 0, "y": 0, "width": 1, "height": 1, "z": 990,
         "color": "#000000", "data": {"shape": "rectangle", "corner_radius": 0}, "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 24, "easing": "ease_in"}]}
pm = L["poster-main"]
for e in pm["effects"]:
    if e["name"] == "tracking":
        e["start_frame"], e["end_frame"], e["easing"] = 0, pm["end_frame"] - pm["start_frame"] - 1, "linear"
        e["params"]["from_em"] = e["params"].get("amount", .02)
        e["params"]["amount"] = round(e["params"]["from_em"] + .06, 3)
upd = lambda sid, sh: {"op": "update_shot", "shot_id": sid, "changes": {k: v for k, v in sh.items() if k in ("effects", "keyframes", "transition")}}
s7_changes = upd("s7", s7)
s7_changes["changes"]["transition"] = None
m.editvideo_patch_timeline(PID, rev(), [upd("s3", s3), upd("s6", s6), s7_changes, up(vab), up(win), up(ring), up(L["dist"]), up(L["record"]), up(dim), up(black), up(pm)])
a = m.editvideo_audit_timeline(PID)["findings"]
print("audit", [(f["code"], f.get("where")) for f in a if f["level"] in ("likely_problem", "warning")])
print("motion", [(f["code"], f.get("where")) for f in m.editvideo_motion_quality(PID)["findings"]][:8])
m.editvideo_export_code(PID, engine="remotion", overwrite=True)
print(json.dumps({"pid": PID, "revision": rev()}))
