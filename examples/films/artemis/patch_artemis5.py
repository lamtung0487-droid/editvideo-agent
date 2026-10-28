"""Fix pass 5 (round 6, from the independent re-review of v2): the title mark spacing by proximity grouping, the Orion
beat split by a punch-in cut at 39 s (linear pushes, no dead tail), the distance/record lines moved off the solar
array, a longer final black, the dead launch pad trimmed, the last typed line held, the poster plate quieter.
Usage: patch_artemis5.py"""
import json, sys, copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store
store.initialize(recover=False)
ROOT = str(Path(__file__).resolve().parents[3])
PID = json.load(open(ROOT + r"\data\films\project-artemis.json"))["pid"]
rev = lambda: m.editvideo_read_project(PID)["revision"]
FOCUS = (.5695, .7667)
CUT = 1170                       # punch-in cut inside the Orion beat
Z1, PUNCH, Z2 = .45, 1.3, .18    # s6 push 1 → 1.45; cut to x1.3 (1.885); s6b push → 2.22; s7 holds that framing

# Title: re-measured with the grouping rule (a mark must sit clearly nearer its own letter than the other line).
m.editvideo_compose_title(PID, rev(), {"recipe": "title_card", "id": "title", "preset": "impact", "text": "Trở lại\nMặt Trăng", "start_frame": 240, "end_frame": 330,
                                       "hit_frame": 254, "black_before": 14, "cap": .2, "exit": "fade", "exit_frames": 10})

t = json.load(open(store.folder(PID) / "plan" / "timeline.json", encoding="utf-8"))
S = {s["id"]: s for s in t["shots"]}
L = {l["id"]: l for l in t["layers"]}
s6 = S["s6"]
a6 = s6["start_frame"]
s6b = copy.deepcopy(s6)
s6["end_frame"] = CUT
s6["effects"] = [{"name": "focus_zoom", "start_frame": 0, "end_frame": CUT - a6 - 1, "easing": "linear", "params": {"amount": Z1, "focus_x": FOCUS[0], "focus_y": FOCUS[1]}}]
n6b = S["s7"]["start_frame"] - CUT
s6b.update(id="s6b", start_frame=CUT, end_frame=S["s7"]["start_frame"], source_start=round(s6["source_start"] + (CUT - a6) / 30, 4),
           effects=[{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": round((1 + Z1) * PUNCH - 1, 4), "focus_x": FOCUS[0], "focus_y": FOCUS[1], "cut": True}},
                    {"name": "focus_zoom", "start_frame": 0, "end_frame": n6b - 1, "easing": "linear", "params": {"amount": Z2, "focus_x": FOCUS[0], "focus_y": FOCUS[1]}}])
s6b.pop("transition", None)
t["shots"].insert(t["shots"].index(s6) + 1, s6b)
end_scale = (1 + Z1) * PUNCH * (1 + Z2)
# Seamless: s7 opens on s6b's last framing (focus_zoom amount ≤ 1, so two held zooms multiply: 1.885 x 1.18).
S["s7"]["effects"] = [e for e in S["s7"]["effects"] if e["name"] != "focus_zoom"] + [
    {"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": round((1 + Z1) * PUNCH - 1, 4), "focus_x": FOCUS[0], "focus_y": FOCUS[1], "cut": True}},
    {"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": Z2, "focus_x": FOCUS[0], "focus_y": FOCUS[1], "cut": True}}]


def scale_at(g):
    if g < CUT:
        return 1 + Z1 * min(1, max(0, (g - a6) / (CUT - a6 - 1)))
    return (1 + Z1) * PUNCH * (1 + Z2 * min(1, (g - CUT) / (n6b - 1)))


def ride(layer):  # window/ring ride the same piecewise zoom about Earth (a 1-frame key step at the punch)
    a, b = layer["start_frame"], layer["end_frame"]
    frames = sorted(set(list(range(0, b - a, 15)) + [b - a - 1] + ([CUT - a - 1, CUT - a] if a < CUT < b else [])))
    layer["keyframes"]["scale"] = [{"frame": f, "value": round(scale_at(a + f), 4), "easing": "linear"} for f in frames]


ride(L["earth-window"])
ride(L["ring"])
# Distance and record lines: off the solar array, in the empty lower left, left-aligned, kept clear of Earth.
for lid, y in (("dist", .58), ("record", .665)):
    l = L[lid]
    l.update(x=.06, y=y, width=.46)
    l.setdefault("data", {})["align"] = "left"
    for e in l["effects"]:
        if e["name"] == "tracking":
            e["params"]["center"] = False
# Final black held ~16 frames; the poster plate darker so the blurred Earth does not sit between the lines.
blk = L["end-black"]
blk.update(start_frame=t["total_frames"] - 40, end_frame=t["total_frames"])
dim = L["end-dim"]
n7 = dim["end_frame"] - dim["start_frame"]
dim["keyframes"]["opacity"] = [{"frame": 0, "value": 0}, {"frame": 20, "value": .7, "easing": "ease_out"}, {"frame": n7 - 25, "value": .7}]
# Launch: start 2 s later in the source (the pad sat still for 2.7 s before ignition).
L["launch"]["source_start"] = round(L["launch"]["source_start"] + 2.0, 3)
# Telemetry: a little faster so the last line holds ~2 s before the cut.
for e in L["telemetry"]["effects"]:
    if e["name"] == "typewriter":
        e["params"]["cps"] = 26
t["layers"] = list(L.values())
m.editvideo_patch_timeline(PID, rev(), [{"op": "replace_timeline", "timeline": t}])
a = m.editvideo_audit_timeline(PID)["findings"]
print("audit", [(f["code"], f.get("where")) for f in a if f["level"] in ("likely_problem", "warning") or f["code"] in ("text_over_push", "diacritic_collision")])
print("motion", [(f["code"], f.get("where")) for f in m.editvideo_motion_quality(PID)["findings"]][:8])
m.editvideo_export_code(PID, engine="remotion", overwrite=True)
print(json.dumps({"pid": PID, "revision": rev(), "end_scale": round(end_scale, 3)}))
