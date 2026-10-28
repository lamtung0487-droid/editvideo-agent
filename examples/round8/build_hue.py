"""Round-8 real build F: a vertical (9:16) travel reel from one drone take over the Huế Imperial City (Wikimedia
Commons, CC BY 4.0, Gaodanielbo), silent, on-screen text only. The drone flies backwards along the main axis, so the
reel is one long pull-back reveal: Điện Thái Hòa → Ngọ Môn → Kỳ Đài, then the moat. The flight is retimed once with
smooth speed ramps (x1 at each landmark, x2 between them; flow interpolation + motion blur) instead of cut into shots
at different playback rates (instant x1→x2 steps read as jolts, x1.5 judders). Landmark names are pinned to the
buildings with track_region + pin_to_track on the retimed clip.
Usage: python examples/round8/build_hue.py"""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent
from editvideo.retime import RetimeRequest, speed_at
from editvideo.design_library import fit_width, stack_line_height
store.initialize(recover=False)
SRC = ROOT / "data" / "sources" / "commons" / "hue_citadel_aerial_1080p.webm"
STATE = ROOT / "data" / "films" / "r8-hue.json"
rev = lambda pid: m.editvideo_read_project(pid)["revision"]
W0 = 42.0  # flight window start (source s); keys are seconds from here
RETIME = {"path": str(SRC), "start": W0, "end": 75.0, "interpolation": "flow", "motion_blur": .5, "crf": 16,
          "speed_keys": [{"at": 0, "speed": 1}, {"at": 5.4, "speed": 1}, {"at": 7.0, "speed": 2}, {"at": 12.4, "speed": 2}, {"at": 14.0, "speed": 1},
                         {"at": 17.0, "speed": 1}, {"at": 18.5, "speed": 2}, {"at": 23.5, "speed": 2}, {"at": 25.0, "speed": 1}, {"at": 33.0, "speed": 1}]}
END_FRAMES = 150
# name, source second of its first frame, source second it leaves (the next speed-up), placement (x anchor, y),
# tracked region [l, t, r, b] at its first frame
LANDMARKS = [("thaihoa", "Điện Thái Hòa", 44.6, 47.3, ("center", .62), [.40, .70, .60, .90]),
             ("thaidich", "Hồ Thái Dịch", 51.6, 54.2, ("center", .80), [.40, .76, .60, .92]),  # the lotus lake between them
             ("ngomon", "Ngọ Môn", 56.1, 58.9, ("center", .735), [.40, .70, .60, .86]),
             ("kydai", "Kỳ Đài", 67.2, 71.8, ("left-of-pole", .70), [.36, .77, .64, .95])]


def out_time(src_s):
    """Output seconds at which the retimed clip shows source second src_s (same stepping as retime.py)."""
    q = RetimeRequest(**RETIME)
    s, n, target = 0.0, 0, src_s - W0
    while s < target:
        s += speed_at(q, s) / 30
        n += 1
    return n / 30


def media_task(submit, request):
    task = submit(request)
    while True:
        r = m.editvideo_get_media_task(task["id"])
        if r["state"] in ("completed", "failed", "cancelled", "interrupted"):
            assert r["state"] == "completed", r.get("error")
            return r
        time.sleep(3)


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if state.get("retime") != RETIME:  # retime once per request; reused on later runs
        r = media_task(m.editvideo_retime_footage, RETIME)
        state = {"retime": RETIME, "task": r["id"]}
        STATE.write_text(json.dumps(state))
    task = m.editvideo_get_media_task(state["task"])
    clip = task["result"]["video"]
    flight = round(task["result"]["report"]["output_frames"])
    N = flight + END_FRAMES
    if not state.get("pid") or agent.read(state["pid"])["timeline"]["total_frames"] != N:
        state["pid"] = m.editvideo_create_silent_project("vertical", N / 30, "remotion", "Hoàng thành Huế · reel dọc")["id"]
        STATE.write_text(json.dumps(state))
    pid = state["pid"]
    tags = {a.get("tags"): a["id"] for a in store.assets(pid)}
    flight_id = tags.get("flight") or m.editvideo_attach_media_result(state["task"], pid, rev(pid), "video", "flight", "evidence")["asset"]["id"]
    names = {a["name"]: a["id"] for a in store.assets(pid)}
    src_id = names.get(SRC.name) or m.editvideo_import_media(pid, str(SRC), role="evidence", tags="Huế Imperial City aerial, CC BY 4.0 Gaodanielbo",
                                                            preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
    t = agent.read(pid)["timeline"]
    base = {"fit": "cover", "focus_x": .5, "focus_y": .5, "motion": "hold", "role": "evidence", "text": "", "effects": [], "playback_rate": 1}
    t["shots"] = [{**base, "id": "flight", "beat_id": "flight", "start_frame": 0, "end_frame": flight, "asset_id": flight_id, "source_start": 0},
                  {**base, "id": "end", "beat_id": "end", "start_frame": flight, "end_frame": N, "asset_id": src_id, "source_start": 146.0}]
    t["layers"] = []
    m.editvideo_patch_timeline(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    m.editvideo_apply_design(pid, rev(pid), {"style_id": "monochrome_focus", "palette_id": "amber", "heading_font_id": "oswald", "body_font_id": "inter"})
    lh = lambda text, w=700: max(1.05, stack_line_height("oswald", text.split("\n"), w)["line_height"])
    out = lambda d: [{"name": "fade_out", "start_frame": d - 9, "end_frame": d - 1}]
    L = lambda **kw: {"op": "upsert_layer", "layer": {"z": 300, **kw}}
    e0 = flight
    ops = [
        L(id="title", kind="text", text="HOÀNG THÀNH\nHUẾ", start_frame=6, end_frame=74, x=.08, y=.10, width=.84, height=.22,
          font_id="oswald", font_weight=700, font_size=150, line_height=lh("HOÀNG THÀNH\nHUẾ"), color="#ffffff", data={"align": "center"},
          effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 10}, {"name": "rise", "start_frame": 0, "end_frame": 14, "params": {"amount": 30}},
                   {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 26}}] + out(68)),
        L(id="subtitle", kind="text", text="bay lùi dọc trục chính", start_frame=14, end_frame=74, x=.08, y=.30, width=.84, height=.05,
          font_id="inter", font_weight=600, font_size=46, color="#ffd27a", data={"align": "center"},
          effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 10}, {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 18}}] + out(60)),
        L(id="end-title", kind="text", text="QUẦN THỂ DI TÍCH\nCỐ ĐÔ HUẾ", start_frame=e0 + 8, end_frame=N - 1, x=.08, y=.12, width=.84, height=.2,
          font_id="oswald", font_weight=700, font_size=104, line_height=lh("QUẦN THỂ DI TÍCH\nCỐ ĐÔ HUẾ"), color="#ffffff", data={"align": "center"},
          effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 12}, {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 24}}]
          + out(N - 1 - e0 - 8)),
        L(id="end-sub", kind="text", text="Di sản thế giới UNESCO · 1993", start_frame=e0 + 20, end_frame=N - 1, x=.08, y=.30, width=.84, height=.05,
          font_id="inter", font_weight=600, font_size=46, color="#ffd27a", data={"align": "center"},
          effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 10}, {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 18}}]
          + out(N - 1 - e0 - 20)),
        L(id="credit", kind="text", text="Video: Gaodanielbo · Wikimedia Commons · CC BY 4.0", start_frame=e0 + 20, end_frame=N - 1,
          x=.08, y=.40, width=.76, height=.03, font_id="inter", font_size=30, color="#e6e0d4", typography_role="source", data={"align": "center"},
          effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 10}, {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 14}}]
          + out(N - 1 - e0 - 20)),
        L(id="end-dim", kind="shape", start_frame=e0, end_frame=N, x=0, y=0, width=1, height=1, z=250, color="#000000",
          data={"shape": "rectangle", "corner_radius": 0},
          keyframes={"opacity": [{"frame": 0, "value": 0}, {"frame": 12, "value": .45}, {"frame": N - e0 - 14, "value": .45}, {"frame": N - e0 - 1, "value": 1}]}),
    ]
    spans = {}
    for lid, text, s_in, s_out, (anchor, y), region in LANDMARKS:
        a, b = int(round(out_time(s_in) * 30)), int(round(out_time(s_out) * 30))
        w = fit_width("oswald", text, 64, 1080, 600, 22)  # the dark plate hugs the name
        x = .5 - w / 2 if anchor == "center" else .44 - w
        spans[lid] = (a, b, region)
        ops.append(L(id=f"{lid}-label", kind="text", text=text, start_frame=a, end_frame=b, x=round(x, 4), y=y, width=w, height=.05, font_id="oswald",
                     font_weight=600, font_size=64, color="#ffffff", background="#000000a0", data={"align": "center"},
                     effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 8}, {"name": "drop", "start_frame": 0, "end_frame": 10, "params": {"amount": 18}}]
                     + out(b - a)))
    m.editvideo_patch_timeline(pid, rev(pid), ops)
    pins = []
    for lid, (a, b, region) in spans.items():
        tr = m.editvideo_track_region(clip, a / 30, b / 30, region, 12, 1080, 1920)
        pins.append({**m.editvideo_pin_to_track(pid, rev(pid), tr["manifest"], "flight", [f"{lid}-label"])["pinned"][0], "lost_at": tr.get("lost_at")})
    au = [(x["code"], x["level"], x.get("where")) for x in m.editvideo_audit_timeline(pid)["findings"] if x["level"] != "info"]
    ad = m.editvideo_ad_audit(pid, cta_layer="end-title", platform="reels")
    print(json.dumps({"pid": pid, "frames": N, "flight_frames": flight, "pins": pins, "audit": au,
                      "ui": [f for f in ad.get("findings") or [] if f["level"] != "info"]}, ensure_ascii=False)[:4000])
    m.editvideo_export_code(pid, engine="remotion", overwrite=True)


if __name__ == "__main__":
    main()
