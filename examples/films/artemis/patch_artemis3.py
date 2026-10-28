"""Fix pass 3: Lunar Module scale 3.0 (feet clear of the frame edge); time cards re-composed with readable label sizes."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store
store.initialize(recover=False)
ROOT = str(Path(__file__).resolve().parents[3])
PID = json.load(open(ROOT + r"\data\films\project-artemis.json"))["pid"]
rev = lambda: m.editvideo_read_project(PID)["revision"]
X = lambda req: m.editvideo_compose_explainer(PID, rev(), req)
X({"recipe": "doc_timecard", "id": "tc69", "start_frame": 70, "end_frame": 236, "year": 1969, "label": "Quá khứ", "detail": "Biển Tĩnh Lặng · Mặt Trăng", "z": 700})
X({"recipe": "doc_timecard", "id": "tc22", "start_frame": 350, "end_frame": 596, "year": 2022, "roll_from": 1969, "roll_frames": 50, "label": "Hiện tại", "detail": "Kennedy, Florida"})
X({"recipe": "doc_timecard", "id": "tclaunch", "start_frame": 678, "end_frame": 954, "year": 2022, "label": "Phóng · 16.11", "detail": "Bệ phóng 39B"})
tl = json.load(open(store.folder(PID) / "plan" / "timeline.json", encoding="utf-8"))
lm = next(l for l in tl["layers"] if l["id"] == "lm")
lm["data"]["objects"][0]["size"][0] = 3.0
m.editvideo_patch_timeline(PID, rev(), [{"op": "upsert_layer", "layer": lm}])
print([f["code"] for f in m.editvideo_audit_timeline(PID)["findings"]])
m.editvideo_export_code(PID, engine="remotion", overwrite=True)
print(json.dumps({"pid": PID, "revision": rev()}))
