"""Fix pass 2: 1969 time card above the opaque 3D scene; a larger Lunar Module; brighter embers at liftoff."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store
store.initialize(recover=False)
ROOT = str(Path(__file__).resolve().parents[3])
PID = json.load(open(ROOT + r"\data\films\project-artemis.json"))["pid"]
rev = lambda: m.editvideo_read_project(PID)["revision"]
m.editvideo_compose_explainer(PID, rev(), {"recipe": "doc_timecard", "id": "tc69", "start_frame": 70, "end_frame": 236, "year": 1969, "label": "Quá khứ",
                                           "detail": "Biển Tĩnh Lặng · Mặt Trăng", "z": 700})
tl = json.load(open(store.folder(PID) / "plan" / "timeline.json", encoding="utf-8"))
L = {l["id"]: l for l in tl["layers"]}
lm = L["lm"]
lm["data"]["objects"][0]["size"][0] = 3.3
em = L["embers"]
em.update(opacity=1.0, y=.3, height=.7)
m.editvideo_patch_timeline(PID, rev(), [{"op": "upsert_layer", "layer": lm}, {"op": "upsert_layer", "layer": em}])
print(m.editvideo_audit_timeline(PID)["findings"][:6])
print(m.editvideo_motion_quality(PID)["findings"][:6])
m.editvideo_export_code(PID, engine="remotion", overwrite=True)
print(json.dumps({"pid": PID, "revision": rev()}))
