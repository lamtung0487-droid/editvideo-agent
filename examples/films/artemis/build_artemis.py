"""Sample film "Trở lại Mặt Trăng" (Apollo 1969 → Artemis I 2022): showcases the round 3-5 capabilities on real NASA
footage. Silent (voice added later), 16:9, 56 s. Usage: build_artemis.py"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, planar, windows
store.initialize(recover=False)
ROOT = str(Path(__file__).resolve().parents[3])
NS = ROOT + r"\data\sources\nasa"
SP = ROOT + r"\data\films"  # vab_track.json / earth_track.json: outputs of track_plane / track_region (see README)
N = 1680
CUT = {"s2": 240, "s3": 330, "s4": 600, "s5": 648, "s6": 960, "s7": 1380}

carrier = ROOT + r"\data\films\carrier-artemis.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x060607:s=1920x1080:r=30:d={N / 30}", "-c:v", "libx264", "-crf", "30",
                "-pix_fmt", "yuv420p", "-an", carrier], check=True)
PID = m.editvideo_project_from_video(carrier, profile="landscape", engine="remotion", title="Trở lại Mặt Trăng")["id"]
rev = lambda: m.editvideo_read_project(PID)["revision"]
json.dump({"pid": PID}, open(ROOT + r"\data\films\project-artemis.json", "w"))

# Brief: the voice-over script (≈2-3 words/s) is kept for later TTS; on-screen text carries the film until then.
m.editvideo_creative_brief({"title": "Trở lại Mặt Trăng", "audience": "người xem phổ thông yêu khoa học", "promise": "từ Apollo 1969 đến Artemis I 2022 trong một phút",
                            "payoff": "con người đang quay lại Mặt Trăng", "beats": [
    {"id": "b1", "narration": "Tháng Bảy năm 1969, con người lần đầu đặt chân lên Mặt Trăng.", "visual_idea": "mô hình tàu đổ bộ Apollo trong bóng tối, telemetry đánh máy", "shot_choice": "3d"},
    {"id": "b2", "narration": "Năm mươi ba năm sau, tên lửa SLS rời nhà lắp ráp ở Florida.", "visual_idea": "chữ ARTEMIS chiếu lên mặt tiền nhà lắp ráp", "shot_choice": "footage"},
    {"id": "b3", "narration": "Ngày mười sáu tháng Mười Một năm 2022, Artemis I rời bệ với lực đẩy khoảng ba mươi chín triệu newton.", "visual_idea": "đếm ngược, đánh lửa, cột lửa", "shot_choice": "footage"},
    {"id": "b4", "narration": "Tàu Orion bay xa Trái Đất hơn bốn trăm ba mươi hai nghìn ki-lô-mét, kỷ lục của một con tàu được thiết kế chở người.", "visual_idea": "Trái Đất sau cánh pin của Orion", "shot_choice": "footage"},
    {"id": "b5", "narration": "Đây mới là bước đầu: Artemis sẽ đưa con người trở lại Mặt Trăng.", "visual_idea": "poster ARTEMIS", "shot_choice": "footage"}]})

m.editvideo_apply_design(PID, rev(), {"style_id": "monochrome_focus", "palette_id": "amber", "heading_font_id": "oswald", "body_font_id": "inter"})

A = {}
def imp(key, path, role="evidence", tags=""):
    A[key] = m.editvideo_import_media(PID, path, preserve_plan=True, base_revision=rev(), role=role, tags=tags or key)["asset"]["id"]
imp("lm", ROOT + r"\data\sources\models\apollo_lunar_module.glb", "illustration", "Apollo Lunar Module model, NASA 3D Resources")
imp("rollout", NS + r"\rollout_aerials.mp4", tags="NASA Artemis I rollout aerials")
imp("launch", NS + r"\launch_tracking.mp4", tags="NASA Artemis I launch tracking")
imp("earth", NS + r"\earthrise_saw4.mp4", tags="NASA Orion solar array camera")

# Shots.
prev, ops = "source-001", []
for sid, f in CUT.items():
    ops.append({"op": "split_shot", "shot_id": prev, "frame": f, "new_id": sid}); prev = sid
m.editvideo_patch_timeline(PID, rev(), ops)
upd = lambda sid, **ch: {"op": "update_shot", "shot_id": sid, "changes": ch}
m.editvideo_patch_timeline(PID, rev(), [
    upd("source-001", motion="hold"), upd("s2", motion="hold"),
    upd("s3", asset_id=A["rollout"], source_start=12.0, fit="cover", motion="hold",
        effects=[{"name": "brightness", "end_frame": 1, "params": {"amount": 1.18}}, {"name": "contrast", "end_frame": 1, "params": {"amount": 1.06}}]),
    upd("s4", asset_id=A["launch"], source_start=33.0, fit="cover", motion="hold"),
    upd("s5", motion="hold"),
    upd("s6", asset_id=A["earth"], source_start=18.0, fit="cover", motion="hold", transition={"name": "dip_black", "duration_frames": 18, "hold_frames": 4},
        effects=[{"name": "focus_zoom", "start_frame": 0, "end_frame": 419, "easing": "ease_in_out", "params": {"amount": .32, "focus_x": .5695, "focus_y": .7667}}]),
    upd("s7", asset_id=A["earth"], source_start=32.0, fit="cover", motion="hold", transition={"name": "dissolve", "duration_frames": 24},
        effects=[{"name": "blur", "end_frame": 1, "params": {"amount": 5}}, {"name": "brightness", "end_frame": 1, "params": {"amount": .5}}]),
])

# 1969: the Lunar Module as a lit product shot, archival look (tritone, halation, 16 mm grain), telemetry typed in.
r = m.editvideo_compose_product(PID, rev(), 0, CUT["s2"], model=A["lm"], id="lm", turn_deg_per_s=24)
print("product", r)
lay = lambda **kw: {"op": "upsert_layer", "layer": kw}
p = m.editvideo_read_project(PID)
L = {l["id"]: l for l in json.load(open(store.folder(PID) / "plan" / "timeline.json", encoding="utf-8"))["layers"]}
lm = L["lm"]
lm["effects"] = [{"name": "tritone", "start_frame": 0, "end_frame": 1, "params": {"amount": .62, "shadow_color": "#120c07", "color": "#8a6a46", "highlight_color": "#f3e4c8"}},
                 {"name": "halation", "start_frame": 0, "end_frame": 1, "params": {"amount": .7, "threshold": .72, "radius": 16}},
                 {"name": "gate_weave", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.2}},
                 {"name": "fade_in", "start_frame": 0, "end_frame": 12}]
m.editvideo_patch_timeline(PID, rev(), [
    {"op": "upsert_layer", "layer": lm},
    lay(id="grain69", kind="film", start_frame=0, end_frame=CUT["s2"], x=0, y=0, width=1, height=1, z=600, blend="overlay",
        data={"type": "grain", "gauge": 16, "intensity": .5}),
    lay(id="telemetry", kind="text", text="HOUSTON", start_frame=18, end_frame=CUT["s2"], x=.06, y=.07, width=.7, height=.07, z=620,
        font_id="ibmplexmono", font_weight=500, font_size=34, color="#eadcc0",
        effects=[{"name": "typewriter", "start_frame": 0, "end_frame": 200,
                  "params": {"script": ["HOUSTON…", "ĐÂY LÀ CĂN CỨ TĨNH LẶNG.", "ĐẠI BÀNG ĐÃ HẠ CÁNH."], "cps": 18, "hold": 22, "cursor": True, "cursor_color": "#ffb347"}}]),
])
X = lambda req: m.editvideo_compose_explainer(PID, rev(), req)
X({"recipe": "doc_timecard", "id": "tc69", "start_frame": 70, "end_frame": CUT["s2"] - 4, "year": 1969, "label": "Quá khứ", "detail": "Biển Tĩnh Lặng · Mặt Trăng"})

# Title on a hit after black.
T = lambda req: m.editvideo_compose_title(PID, rev(), req)
T({"recipe": "title_card", "id": "title", "preset": "impact", "text": "Trở lại\nMặt Trăng", "start_frame": CUT["s2"], "end_frame": CUT["s3"], "hit_frame": CUT["s2"] + 14,
   "black_before": 14, "cap": .2, "exit": "fade", "exit_frames": 10})

# 2022: ARTEMIS projected onto the Vehicle Assembly Building, riding a planar track of the facade.
trk = planar.load_track(json.load(open(SP + r"\vab_track.json"))["track_id"])
trk = {**trk, "track": [s for s in trk["track"] if s["frame"] <= 180]}
r = m.editvideo_screen_replace(PID, rev(), trk, {
    "id": "vab-title", "kind": "text", "text": "A\nR\nT\nE\nM\nI\nS", "font_id": "oswald", "font_weight": 600, "font_size": 96, "line_height": 1.04,
    "color": "#fff0d2", "blend": "screen", "z": 300, "data": {"align": "center"},
    "effects": [{"name": "text_animate", "start_frame": 8, "end_frame": 44, "easing": "ease_out",
                 "params": {"unit": "char", "mode": "in", "order": "forward", "window": .4, "opacity": 0, "amount": 0, "blur": 10}},
                {"name": "bloom", "start_frame": 0, "end_frame": 1, "params": {"amount": 10, "color": "#ffd9a0"}},
                {"name": "fade_out", "start_frame": 160, "end_frame": 179}]}, CUT["s3"])
print("screen", r)
X({"recipe": "doc_timecard", "id": "tc22", "start_frame": CUT["s3"] + 20, "end_frame": CUT["s4"] - 4, "year": 2022, "roll_from": 1969, "roll_frames": 50,
   "label": "Hiện tại", "detail": "Kennedy, Florida"})

# Countdown cards on the beat into ignition.
T({"recipe": "word_cards", "id": "count", "words": ["3", "2", "1"], "hit_frames": [CUT["s4"] + 6, CUT["s4"] + 22, CUT["s4"] + 38], "card_frames": 12, "cap": .28})

# Launch: highlight bloom and halation on the flame, embers, a live thrust readout.
m.editvideo_patch_timeline(PID, rev(), [
    lay(id="launch", kind="video", asset_id=A["launch"], source_start=41.0, start_frame=CUT["s5"], end_frame=CUT["s6"], x=0, y=0, width=1, height=1, fit="cover", z=20,
        effects=[{"name": "highlight_glow", "start_frame": 0, "end_frame": 1, "params": {"amount": .9, "threshold": .8, "radius": 34, "anamorphic": .55}},
                 {"name": "halation", "start_frame": 0, "end_frame": 1, "params": {"amount": .55, "threshold": .75, "radius": 18}}]),
    lay(id="embers", kind="particles", start_frame=CUT["s5"] + 90, end_frame=CUT["s6"] - 10, x=.25, y=.35, width=.5, height=.65, z=40, blend="add", opacity=.75,
        data={"mode": "system", "preset": "embers", "seed": 11}),
])
X({"recipe": "doc_timecard", "id": "tclaunch", "start_frame": CUT["s5"] + 30, "end_frame": CUT["s6"] - 6, "year": 2022, "label": "Phóng · 16.11", "detail": "Bệ phóng 39B"})
X({"recipe": "hud_card", "id": "thrust", "start_frame": CUT["s5"] + 110, "end_frame": CUT["s6"] - 6, "caption": "LỰC ĐẨY KHI RỜI BỆ", "value_to": 39, "suffix": " triệu newton",
   "style": "roll", "count_frames": 45, "x": .69, "y": .08, "width": .27, "panel": "#1b1510", "color": "#fff3e0"})

# Orion: Earth behind the solar array; a gentle tracked colour window lifts it, a hand-drawn ring marks it.
etrack = json.load(open(SP + r"\earth_track.json"))
windows.tracked_window(PID, rev(), etrack, CUT["s6"] + 60, mode="color", shape="ellipse", pad=1.2, feather_px=60,
                       adjust={"exposure": .45, "saturation": 1.45}, layer_id="earth-window")
X({"recipe": "annotate", "id": "ring", "start_frame": CUT["s6"] + 70, "end_frame": CUT["s6"] + 300, "shape": "ellipse", "region": [.5355, .715, .068, .105]})
X({"recipe": "stat_line", "id": "dist", "start_frame": CUT["s6"] + 110, "end_frame": CUT["s7"] - 10, "text": "Xa Trái Đất **432.210 km**", "y": .1})
m.editvideo_patch_timeline(PID, rev(), [
    lay(id="record", kind="text", text="kỷ lục của một con tàu được thiết kế để chở người", start_frame=CUT["s6"] + 140, end_frame=CUT["s7"] - 10,
        x=.2, y=.19, width=.6, height=.05, font_id="inter", font_weight=400, font_size=30, color="#d9dde6", data={"align": "center"},
        effects=[{"name": "fade_in", "end_frame": 14}, {"name": "tracking", "start_frame": 0, "end_frame": 40, "easing": "ease_out", "params": {"amount": .04, "from_em": .14, "center": True}},
                 {"name": "fade_out", "start_frame": 220, "end_frame": 230}]),
])

# Close: poster lockup over the dimmed Orion view.
T({"recipe": "type_lockup", "id": "poster", "mode": "poster", "top": "NASA · Chương trình", "main": "Artemis", "sub": "Đưa con người trở lại Mặt Trăng",
   "footer": ["Tư liệu: NASA · Mô hình 3D Apollo LM: NASA 3D Resources"], "start_frame": CUT["s7"] + 18, "end_frame": N, "y": .46})

m.editvideo_export_code(PID, engine="remotion", overwrite=True)
print(json.dumps({"pid": PID, "revision": rev()}))
