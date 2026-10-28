"""Round-7 real build A: a narrated documentary cut from footage (NASA, public domain), 16:9.
Built the way an AI client works: script → timed narration → shots on sentence bounds → recipes → beat_map/audits →
fixes → render in both engines. Usage: python examples/round7/build_doc.py [--render]"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, beatmap
store.initialize(recover=False)
NS = ROOT / "data" / "sources" / "nasa"
STATE = ROOT / "data" / "films" / "r7-doc.json"
SENT = [  # display text (captions) | spoken text (numbers read naturally)
    ("Kennedy, Florida. Rạng sáng 16.11.2022.", "Kennedy, Florida. Rạng sáng ngày mười sáu tháng mười một năm hai nghìn không trăm hai mươi hai."),
    ("Tên lửa SLS cao gần 100 mét đứng trên bệ phóng 39B.", "Tên lửa SLS cao gần một trăm mét đứng trên bệ phóng ba mươi chín B."),
    ("1 giờ 47 phút sáng, bốn động cơ chính và hai tầng đẩy phụ cùng khai hỏa.", "Một giờ bốn mươi bảy phút sáng, bốn động cơ chính và hai tầng đẩy phụ cùng khai hỏa."),
    ("Lực đẩy khi rời bệ khoảng 39 triệu newton.", "Lực đẩy khi rời bệ khoảng ba mươi chín triệu niu-tơn."),
    ("Từ camera trên cánh pin, Orion nhìn lại Trái Đất.", "Từ camera trên cánh pin, Orion nhìn lại Trái Đất."),
    ("Ngày 28.11, con tàu cách Trái Đất 432.210 km, xa nhất với một tàu thiết kế để chở người.",
     "Ngày hai mươi tám tháng mười một, con tàu cách Trái Đất bốn trăm ba mươi hai nghìn hai trăm mười ki-lô-mét, xa nhất với một tàu thiết kế để chở người."),
    ("25,5 ngày sau khi phóng, Orion hạ cánh xuống Thái Bình Dương.", "Hai mươi lăm ngày rưỡi sau khi phóng, Orion hạ cánh xuống Thái Bình Dương."),
]
SCRIPT, SPOKEN = " ".join(a for a, _ in SENT), " ".join(b for _, b in SENT)
rev = lambda pid: m.editvideo_read_project(pid)["revision"]


def project():
    if STATE.exists():
        return json.loads(STATE.read_text())["pid"]
    pid = m.editvideo_create_project({"title": "Artemis I · Ngày phóng", "script": SCRIPT, "spoken_text": SPOKEN, "profile": "landscape",
                                      "renderer": "remotion", "captions": False, "voice": "vi-VN-NamMinhNeural", "voice_rate": 4})["id"]
    STATE.write_text(json.dumps({"pid": pid}))
    return pid


def main():
    pid = project()
    A = {a["name"]: a["id"] for a in store.assets(pid)}
    for name in ("rollout_aerials.mp4", "launch_tracking.mp4", "earthrise_saw4.mp4"):
        if name not in A:
            A[name] = m.editvideo_import_media(pid, str(NS / name), role="evidence", tags="NASA Artemis I")["id"]
    if not agent.read(pid).get("timeline"):
        j = store.create_job(pid, "plan")
        m.worker.run(j["id"])
        assert m.editvideo_get_job(j["id"])["state"] == "completed", m.editvideo_get_job(j["id"])
    bm = beatmap.beat_map(pid, 0, 40)
    sents = bm["beats"]
    beat_sent = [0, 1, 2, 3, 4, 5, 6, 7]  # first sentence of each visual beat
    assert len(sents) == 8, (len(sents), [b["text"] for b in sents])
    f = lambda sec: int(round(sec * 30))
    t = agent.read(pid)["timeline"]
    N = t["total_frames"]
    starts = [0] + [f(sents[k]["t"][0]) - 6 for k in beat_sent[1:]]  # cut ~6 frames before the sentence (the eye leads the ear)
    bounds = starts + [N]
    # Launch-day footage only for launch-day claims: the rollout aerials carry an 08/16/2022 slate (the August rollout),
    # so they cannot illustrate "16.11.2022" as evidence. Cold open: two seconds of the climb (the brightest, most
    # kinetic moment, 62 s into the clip) under "Kennedy, Florida.", then back to the dark pad (a pre-dawn pad held
    # for 10 s read as a black, static opening).
    plan = [("launch_tracking.mp4", 62.0), ("launch_tracking.mp4", 4.0), ("launch_tracking.mp4", 26.0), ("launch_tracking.mp4", 41.5),
            ("launch_tracking.mp4", 49.0), ("earthrise_saw4.mp4", 18.0), ("earthrise_saw4.mp4", 26.0), ("earthrise_saw4.mp4", 34.0)]
    shots = []
    for i, ((asset, src), a, b) in enumerate(zip(plan, bounds, bounds[1:])):
        sh = {"id": f"s{i}", "beat_id": f"b{i}", "start_frame": a, "end_frame": b, "asset_id": A[asset], "source_start": src, "fit": "cover",
              "motion": "hold", "role": "evidence"}
        if i in (1, 2):  # the pad before dawn is nearly black: lift it and keep it moving; s2 frames the rocket itself
            sh["effects"] = [{"name": "exposure", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.2}}]
            if i == 1:
                sh["effects"] += [{"name": "focus_zoom", "start_frame": 0, "end_frame": b - a - 1, "easing": "linear", "params": {"amount": .1, "focus_x": .5, "focus_y": .4}}]
            if i == 2:
                sh["effects"] += [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .6, "focus_x": .5, "focus_y": .32, "cut": True}},
                                  {"name": "focus_zoom", "start_frame": 0, "end_frame": b - a - 1, "easing": "linear", "params": {"amount": .08, "focus_x": .5, "focus_y": .25}}]
        if i in (5, 6, 7):  # space views: a slow push keeps the still picture alive
            sh["effects"] = [{"name": "focus_zoom", "start_frame": 0, "end_frame": b - a - 1, "easing": "linear", "params": {"amount": .12, "focus_x": .57, "focus_y": .77}}]
        if i == 4:  # time passes on the same locked-off camera: dissolve at the punch's scale, so the tower does not double
            sh["transition"] = {"name": "dissolve", "duration_frames": 8}
            sh["effects"] = [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .12, "focus_x": .5, "focus_y": .45, "cut": True}}]
        if i == 7:  # continuous clip after s6: a tighter framing, so the cut reads as a new view, not a jump
            sh["effects"] = [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .45, "focus_x": .57, "focus_y": .77, "cut": True}},
                             {"name": "focus_zoom", "start_frame": 0, "end_frame": b - a - 1, "easing": "linear", "params": {"amount": .1, "focus_x": .57, "focus_y": .77}}]
        shots.append(sh)
    t["shots"], t["layers"] = shots, []
    m.editvideo_patch_timeline(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    m.editvideo_apply_design(pid, rev(pid), {"style_id": "monochrome_focus", "palette_id": "amber", "heading_font_id": "oswald", "body_font_id": "inter"})
    word = lambda i, needle: next((f(w["start"]) for w in agent_words(pid) if needle in w["text"].lower() and f(w["start"]) >= bounds[i]), bounds[i] + 8)
    X = lambda req: m.editvideo_compose_explainer(pid, rev(pid), req)
    # The place/date card arrives on the pad, after the two-second cold open (amber over the bright booster read poorly).
    X({"recipe": "doc_timecard", "id": "tc1", "start_frame": bounds[1] + 4, "end_frame": bounds[3] - 4, "year": 2022, "label": "Kennedy · Florida", "detail": "16.11 · rạng sáng"})
    X({"recipe": "hud_card", "id": "thrust", "start_frame": word(4, "lực"), "end_frame": bounds[5] - 2, "caption": "LỰC ĐẨY KHI RỜI BỆ", "value_to": 39,
       "suffix": " triệu N", "style": "roll", "count_frames": 30, "x": .66, "y": .08, "width": .3})
    X({"recipe": "stat_line", "id": "far", "start_frame": word(6, "bốn"), "end_frame": bounds[7] - 4, "text": "Xa Trái Đất **432.210 km**", "y": .1, "entrance": "fade"})
    # The Orion clip has no recorded date: the card names the camera and mission, the date stays in the narration.
    X({"recipe": "doc_timecard", "id": "tc2", "start_frame": bounds[6] + 4, "end_frame": bounds[7] - 4, "year": 2022, "label": "Orion · Artemis I", "detail": "camera trên cánh pin"})
    X({"recipe": "stat_line", "id": "days", "start_frame": word(7, "hai"), "end_frame": N - 2, "text": "**25,5 ngày** · 16.11 – 11.12.2022", "y": .1, "entrance": "fade"})
    L = {l["id"]: l for l in agent.read(pid)["timeline"]["layers"]}
    days = L["days"]  # over the solar array at the top; the empty lower left reads cleanly
    days.update(x=.06, y=.56, width=.6)
    days["data"]["align"] = "left"
    m.editvideo_patch_timeline(pid, rev(pid), [{"op": "upsert_layer", "layer": days}])
    m.editvideo_punch_in(pid, rev(pid), frames=[word(3, "khai") + 4], scale=1.12, anchor=[.5, .45])
    # The film resolves to black after the last line instead of stopping on a held frame.
    last = agent.read(pid)["timeline"]["shots"][-1]
    last["effects"] = (last.get("effects") or []) + [{"name": "fade_out", "start_frame": last["end_frame"] - last["start_frame"] - 18,
                                                      "end_frame": last["end_frame"] - last["start_frame"] - 1}]
    m.editvideo_patch_timeline(pid, rev(pid), [{"op": "update_shot", "shot_id": last["id"], "changes": {"effects": last["effects"]}}])
    print(json.dumps({"pid": pid, "revision": rev(pid), "frames": N}))
    out = {"beat_map": {k: beatmap.beat_map(pid, 0, 40)[k] for k in ("findings", "rhythm")},
           "audit": [(x["code"], x.get("where")) for x in m.editvideo_audit_timeline(pid)["findings"] if x["level"] != "info"]}
    print(json.dumps(out, ensure_ascii=False)[:3000])
    m.editvideo_export_code(pid, engine="remotion", overwrite=True)


def agent_words(pid):
    return store.read_json(store.folder(pid) / "plan" / "words.json").get("words") or []


if __name__ == "__main__":
    main()
