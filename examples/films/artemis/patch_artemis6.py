"""Fix pass 6 (round 6, from the independent review of v3): the end card was a still picture for ~7.5 s and the push
slowed after the 39 s punch. The Orion beat now runs to 50 s with a second punch at 45 s (constant-ratio pushes at one
speed, the runtime zooms geometrically), the poster gets 6 s on an abstract plate (the solar array, Earth out of the
text column) with a visible push, and the thrust card staggers. Usage: patch_artemis6.py"""
import json, sys, copy, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store
store.initialize(recover=False)
ROOT = str(Path(__file__).resolve().parents[3])
PID = json.load(open(ROOT + r"\data\films\project-artemis.json"))["pid"]
rev = lambda: m.editvideo_read_project(PID)["revision"]
FOCUS = (.5695, .7667)
A6, C1, C2, C7 = 960, 1170, 1350, 1500       # s6 | punch x1.3 | punch x1.25 | poster
RATE = math.log(1.45) / (C1 - A6 - 1)         # one push speed (log scale per frame) for all three pieces
P1, P2 = 1.3, 1.25
seg = lambda a, b: math.exp(RATE * (b - a - 1))  # push factor over a piece [a, b)

t = json.load(open(store.folder(PID) / "plan" / "timeline.json", encoding="utf-8"))
S = {s["id"]: s for s in t["shots"]}
L = {l["id"]: l for l in t["layers"]}
s6, s6b, s7 = S["s6"], S["s6b"], S["s7"]
src0 = s6["source_start"]
fz = lambda amt, cut=False, end=1: {"name": "focus_zoom", "start_frame": 0, "end_frame": end, **({} if cut else {"easing": "linear"}),
                                    "params": {"amount": round(amt, 4), "focus_x": FOCUS[0], "focus_y": FOCUS[1], **({"cut": True} if cut else {})}}
k1 = seg(A6, C1)                              # 1.45
k2 = seg(C1, C2)
k3 = seg(C2, C7)
s6["effects"] = [fz(k1 - 1, end=C1 - A6 - 1)]
s6b.update(end_frame=C2, effects=[fz(k1 * P1 - 1, True), fz(k2 - 1, end=C2 - C1 - 1)])
s6c = copy.deepcopy(s6b)
held = k1 * P1 * k2 * P2                      # framing at the start of s6c (two held zooms, each amount <= 1)
s6c.update(id="s6c", start_frame=C2, end_frame=C7, source_start=round(src0 + (C2 - A6) / 30, 4),
           effects=[fz(k1 * P1 - 1, True), fz(k2 * P2 - 1, True), fz(k3 - 1, end=C7 - C2 - 1)])
t["shots"].insert(t["shots"].index(s6b) + 1, s6c)
# Poster plate: same clip later on, framed on the solar array (Earth below the frame), blurred and dimmed, pushing in.
n7 = t["total_frames"] - C7
s7.update(start_frame=C7, source_start=round(src0 + (C7 - A6) / 30, 4),
          effects=[{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .65, "focus_x": .57, "focus_y": .3, "cut": True}}],
          keyframes={"blur": [{"frame": 0, "value": 3}, {"frame": 24, "value": 10, "easing": "ease_out"}],
                     "scale": [{"frame": 0, "value": 1}, {"frame": n7 - 1, "value": 1.14, "easing": "linear"}]})


def scale_at(g):
    if g < C1:
        return math.exp(RATE * (g - A6))
    if g < C2:
        return k1 * P1 * math.exp(RATE * (g - C1))
    return k1 * P1 * k2 * P2 * math.exp(RATE * (g - C2))


def ride(layer):  # window/ring follow the zoom about Earth, with a one-frame step at each punch
    a, b = layer["start_frame"], layer["end_frame"]
    fr = set(list(range(0, b - a, 15)) + [b - a - 1])
    for c in (C1, C2):
        if a < c < b:
            fr |= {c - a - 1, c - a}
    layer["keyframes"]["scale"] = [{"frame": f, "value": round(scale_at(a + f), 4), "easing": "linear"} for f in sorted(fr)]


w = L["earth-window"]
w["end_frame"] = C7
w["masks"][0]["keyframes"] = [k for k in w["masks"][0]["keyframes"] if k["frame"] < C7 - w["start_frame"]]
ride(w)
ride(L["ring"])
dim = L["end-dim"]
dim.update(start_frame=C7, end_frame=t["total_frames"])
dim["keyframes"] = {"opacity": [{"frame": 0, "value": 0}, {"frame": 18, "value": .62, "easing": "ease_out"}, {"frame": n7 - 25, "value": .62}]}
for lid in ("dist", "record"):  # end with the Orion beat, before the poster
    L[lid]["end_frame"] = min(L[lid]["end_frame"], C7 - 4)
# Thrust card: panel, caption, value enter in turn.
for k, lid in enumerate(("thrust-panel", "thrust-caption", "thrust-value")):
    for e in L[lid]["effects"]:
        if e["name"] == "fade_in":
            e["start_frame"], e["end_frame"] = 5 * k, 5 * k + (e["end_frame"] - e["start_frame"])
# Poster lockup layers are re-composed at the new start below.
for lid in [l for l in L if l.startswith("poster-")]:
    del L[lid]
t["layers"] = list(L.values())
m.editvideo_patch_timeline(PID, rev(), [{"op": "replace_timeline", "timeline": t}])
m.editvideo_compose_title(PID, rev(), {"recipe": "type_lockup", "id": "poster", "mode": "poster", "top": "NASA · Chương trình", "main": "Artemis",
                                       "sub": "Đưa con người trở lại Mặt Trăng", "footer": ["Tư liệu: NASA · Mô hình 3D Apollo LM: NASA 3D Resources"],
                                       "start_frame": C7 + 14, "end_frame": t["total_frames"], "y": .46})
# The poster title drifts open through its span (tracking), as in pass 4.
tl = json.load(open(store.folder(PID) / "plan" / "timeline.json", encoding="utf-8"))
pm = next(l for l in tl["layers"] if l["id"] == "poster-main")
for e in pm["effects"]:
    if e["name"] == "tracking":
        e["start_frame"], e["end_frame"], e["easing"] = 0, pm["end_frame"] - pm["start_frame"] - 1, "linear"
        e["params"]["from_em"] = e["params"].get("amount", .02)
        e["params"]["amount"] = round(e["params"]["from_em"] + .06, 3)
m.editvideo_patch_timeline(PID, rev(), [{"op": "upsert_layer", "layer": pm}])
a = m.editvideo_audit_timeline(PID)["findings"]
print("audit", [(f["code"], f.get("where")) for f in a if f["level"] in ("likely_problem", "warning")])
print("motion", [(f["code"], f.get("where")) for f in m.editvideo_motion_quality(PID)["findings"]][:8])
m.editvideo_export_code(PID, engine="remotion", overwrite=True)
print(json.dumps({"pid": PID, "revision": rev(), "held_scale_s6c": round(held, 3), "end_scale": round(held * k3, 3)}))
