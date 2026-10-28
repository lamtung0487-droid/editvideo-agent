"""Render-check for round-6 runtime: a two-bone IK arm reaching for a moving target (hand inherits the solve), a wheel
rolled by a driver on its car's x, and evidence_3d on an original synthetic document (a known red region checks the
projected mark). Usage: python examples/rig_ik_drivers_evidence3d.py  → prints the project id; then snapshot or render it."""
import json, sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image, ImageDraw, ImageFont
from editvideo import mcp_server as m, store
store.initialize(recover=False)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/examples"
OUT.mkdir(parents=True, exist_ok=True)
carrier = OUT / "carrier-10s.mp4"
if not carrier.exists():  # a plain dark 10 s carrier; the project is built on it
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x0b0c0e:s=1920x1080:r=30:d=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(carrier)], check=True)
doc = OUT / "r6-document.png"
if not doc.exists():  # original synthetic page: typed lines, one red-boxed paragraph at a known place
    W, H = 1500, 1000
    im = Image.new("RGB", (W, H), "#efe6d2")
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(str(ROOT / "assets/fonts/ibmplexmono/IBMPlexMono-Regular.ttf"), 30)
    d.text((90, 70), "BIÊN BẢN KỸ THUẬT · 14/10", font=f, fill="#26221c")
    for i in range(14):
        y = 150 + i * 52
        d.text((90, y), ("Dòng dữ liệu đo số %02d  ......  %4.1f" % (i + 1, 12.5 + i * 3.7)), font=f, fill="#3a342a")
    d.rectangle([840, 560, 1340, 720], outline="#c0392b", width=6)
    d.text((870, 610), "KẾT LUẬN: ĐẠT", font=f, fill="#c0392b")
    im.save(doc)
cfg = OUT / "project-r6.json"
if cfg.exists():
    PID = json.loads(cfg.read_text())["pid"]
else:
    prior = [x for x in m.editvideo_list_projects(100)["items"] if x["title"] == "r6 runtime check"]
    PID = prior[0]["id"] if prior else m.editvideo_project_from_video(str(carrier), title="r6 runtime check")["id"]
    cfg.write_text(json.dumps({"pid": PID}))
rev = lambda: m.editvideo_read_project(PID)["revision"]
assets = {a["name"]: a["id"] for a in store.assets(PID)}
if "r6-document.png" not in assets:
    assets["r6-document.png"] = m.editvideo_import_media(PID, str(doc), role="evidence", preserve_plan=True, base_revision=rev())["asset"]["id"]
L = lambda **kw: {"op": "upsert_layer", "layer": {"z": 50, "start_frame": 0, "end_frame": 150, **kw}}
circle = [{"frame": f, "value": round(v, 1), "easing": "linear"} for f, v in zip(range(0, 150, 10), [0, 120, 200, 220, 170, 60, -60, -170, -220, -200, -120, 0, 120, 200, 220])]
circle_y = [{"frame": f, "value": round(v, 1), "easing": "linear"} for f, v in zip(range(0, 150, 10), [0, -60, -150, -230, -290, -310, -290, -230, -150, -60, 0, 40, 0, -60, -150])]
ops = [
    L(id="shoulder", kind="shape", x=.3, y=.38, width=.02, height=.035, color="#e8b04a", data={"shape": "ellipse"}, z=60),
    L(id="upper", kind="shape", x=.304, y=.4, width=.012, height=.2, color="#d8d2c4", anchor=[.5, 0], data={"shape": "rectangle", "corner_radius": 6}),
    L(id="lower", kind="shape", x=.304, y=.6, width=.010, height=.2, color="#a9b8c6", anchor=[.5, 0], parent="upper", data={"shape": "rectangle", "corner_radius": 6},
      ik={"target": "goal", "tip": [.5, 1], "bend": "cw"}),
    L(id="hand", kind="shape", x=.302, y=.79, width=.014, height=.025, color="#ff6b3d", parent="lower", data={"shape": "ellipse"}),
    L(id="goal", kind="shape", x=.42, y=.72, width=.016, height=.028, color="#5ad1ff", data={"shape": "ellipse"}, opacity=.7,
      keyframes={"x": circle, "y": circle_y}),
    L(id="car", kind="shape", x=.55, y=.8, width=.12, height=.05, color="#81e6be", data={"shape": "rectangle", "corner_radius": 8},
      keyframes={"x": [{"frame": 0, "value": 0}, {"frame": 149, "value": 600, "easing": "ease_in_out"}]}),
    L(id="wheel", kind="shape", x=.565, y=.84, width=.022, height=.039, color="#ffffff", data={"shape": "rectangle", "corner_radius": 3},
      drivers={"x": {"source": "car"}, "rotate": {"source": "car", "track": "x", "mul": round(180 / 3.14159 / 21, 4)}}),
]
r = m.editvideo_patch_timeline(PID, rev(), ops)
print("rig", r.get("revision"))
r = m.editvideo_compose_explainer(PID, rev(), {"recipe": "evidence_3d", "id": "ev", "start_frame": 150, "end_frame": 299, "asset_id": assets["r6-document.png"],
                                              "focus": [840 / 1500, 560 / 1000, 1340 / 1500, 720 / 1000], "caption": "Kết luận ghi ở cuối biên bản",
                                              "source": "Tài liệu minh hoạ tự tạo (EditVideo)"})
print("evidence", {k: r.get(k) for k in ("mark_box", "camera", "notes", "layers")})
print(json.dumps({"pid": PID, "revision": rev()}))
