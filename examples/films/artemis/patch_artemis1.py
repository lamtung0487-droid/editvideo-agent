"""Fix pass 1 for the Artemis sample: calmer product lighting (no blow-out), no ground horizon, lighter archival look,
bigger telemetry, title re-composed with Vietnamese-safe line spacing."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store
store.initialize(recover=False)
ROOT = str(Path(__file__).resolve().parents[3])
PID = json.load(open(ROOT + r"\data\films\project-artemis.json"))["pid"]
rev = lambda: m.editvideo_read_project(PID)["revision"]
A = {a["tags"]: a["id"] for a in store.assets(PID)}
lm_asset = next(a["id"] for a in store.assets(PID) if a["name"].endswith(".glb"))
r = m.editvideo_compose_product(PID, rev(), 0, 240, model=lm_asset, id="lm", turn_deg_per_s=24, light=.38, ground=False, studio=False, bloom=False)
print(r["beats"])
tl = json.load(open(store.folder(PID) / "plan" / "timeline.json", encoding="utf-8"))
L = {l["id"]: l for l in tl["layers"]}
lm = L["lm"]
lm["effects"] = [{"name": "tritone", "start_frame": 0, "end_frame": 1, "params": {"amount": .45, "shadow_color": "#0d0906", "color": "#7a5c3c", "highlight_color": "#f1e2c6"}},
                 {"name": "halation", "start_frame": 0, "end_frame": 1, "params": {"amount": .45, "threshold": .82, "radius": 14}},
                 {"name": "gate_weave", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.0}},
                 {"name": "fade_in", "start_frame": 0, "end_frame": 12}]
tel = L["telemetry"]
tel.update(font_size=42, height=.08)
m.editvideo_patch_timeline(PID, rev(), [{"op": "upsert_layer", "layer": lm}, {"op": "upsert_layer", "layer": tel}])
m.editvideo_compose_title(PID, rev(), {"recipe": "title_card", "id": "title", "preset": "impact", "text": "Trở lại\nMặt Trăng", "start_frame": 240, "end_frame": 330,
                                       "hit_frame": 254, "black_before": 14, "cap": .2, "exit": "fade", "exit_frames": 10})
m.editvideo_export_code(PID, engine="remotion", overwrite=True)
print(json.dumps({"pid": PID, "revision": rev()}))
