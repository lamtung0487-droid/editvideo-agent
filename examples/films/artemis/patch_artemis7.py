"""Fix pass 7 (round 6, P2 polish from the final independent review of v4): the ring leaves on the 45 s punch instead of
vanishing mid-shot, the distance headline fades out by the punch, the thrust card fades instead of vanishing, the poster
plate opens already blurred and dimmed (no sharp flash at the 50 s cut) and a touch brighter so its push reads, and the
45-50 s beat carries one verified line (Artemis I lasted 25.5 days, 16 Nov - 11 Dec 2022). Usage: patch_artemis7.py"""
import json, sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store
store.initialize(recover=False)
ROOT = str(Path(__file__).resolve().parents[3])
PID = json.load(open(ROOT + r"\data\films\project-artemis.json"))["pid"]
rev = lambda: m.editvideo_read_project(PID)["revision"]
A6, C1, C2, C7 = 960, 1170, 1350, 1500
RATE, P1, P2 = math.log(1.45) / (C1 - A6 - 1), 1.3, 1.25
k1, k2 = math.exp(RATE * (C1 - A6 - 1)), math.exp(RATE * (C2 - C1 - 1))


def scale_at(g):  # same piecewise constant-ratio zoom as patch_artemis6
    if g < C1:
        return math.exp(RATE * (g - A6))
    if g < C2:
        return k1 * P1 * math.exp(RATE * (g - C1))
    return k1 * P1 * k2 * P2 * math.exp(RATE * (g - C2))


X = lambda req: m.editvideo_compose_explainer(PID, rev(), req)
X({"recipe": "stat_line", "id": "days", "start_frame": C2 + 8, "end_frame": C7 - 4, "text": "Hành trình **25,5 ngày** · 16.11 – 11.12.2022", "entrance": "fade"})
t = json.load(open(store.folder(PID) / "plan" / "timeline.json", encoding="utf-8"))
L = {l["id"]: l for l in t["layers"]}
ring = L["ring"]
ring["end_frame"] = C2  # leaves on the punch cut
d = ring["end_frame"] - ring["start_frame"]
fr = sorted(set(list(range(0, d, 15)) + [d - 1]))
ring["keyframes"]["scale"] = [{"frame": f, "value": round(scale_at(ring["start_frame"] + f), 4), "easing": "linear"} for f in fr]
ring["effects"] = [e for e in ring["effects"] if e["name"] != "fade_out"]


def fade_by(layer, end):
    layer["end_frame"] = end
    n = end - layer["start_frame"]
    layer["effects"] = [e for e in layer["effects"] if e["name"] != "fade_out"] + [{"name": "fade_out", "start_frame": n - 10, "end_frame": n - 1}]


fade_by(L["dist"], C2)
fade_by(L["record"], min(L["record"]["end_frame"], C2))
for lid in ("thrust-panel", "thrust-caption", "thrust-value"):
    fade_by(L[lid], L[lid]["end_frame"])
# The new line sits where the distance line was: lower left, clear of Earth, left-aligned.
days = L["days"]
days.update(x=.06, y=.54, width=.68)
days["data"]["align"] = "left"
s7 = next(s for s in t["shots"] if s["id"] == "s7")
s7["keyframes"]["blur"] = [{"frame": 0, "value": 8}, {"frame": 24, "value": 10, "easing": "ease_out"}]
n7 = t["total_frames"] - C7
L["end-dim"]["keyframes"] = {"opacity": [{"frame": 0, "value": .45}, {"frame": 18, "value": .52, "easing": "ease_out"}, {"frame": n7 - 25, "value": .52}]}
t["layers"] = list(L.values())
m.editvideo_patch_timeline(PID, rev(), [{"op": "replace_timeline", "timeline": t}])
a = m.editvideo_audit_timeline(PID)["findings"]
print("audit", [(f["code"], f.get("where")) for f in a if f["level"] in ("likely_problem", "warning") or f["code"] in ("abrupt_exit", "diacritic_collision")])
m.editvideo_export_code(PID, engine="remotion", overwrite=True)
print(json.dumps({"pid": PID, "revision": rev()}))
