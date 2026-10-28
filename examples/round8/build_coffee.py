"""Round-8 real build E: a square (1:1) how-it-works explainer cut from one handheld take of a drip coffee maker
(Wikimedia Commons, CC BY 3.0, Erik Pålsson), narrated OFFLINE with Piper (vi_VN vais1000) and word timings measured
from the audio, part labels pinned to the handheld footage with track_region + pin_to_track, a fast-forward (x8) for
the tank emptying. Usage: python examples/round8/build_coffee.py [--replan]  (--replan: narrate again, e.g. after a voice change)"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, beatmap
store.initialize(recover=False)
SRC = ROOT / "data" / "sources" / "commons" / "moccamaster_coffee_maker.webm"
STATE = ROOT / "data" / "films" / "r8-coffee.json"
SENT = [  # display | spoken. Every observation is visible in the take (tank scale, falling level, the drip, steam on the glass).
    ("Máy pha cà phê nhỏ giọt làm việc thế nào?", "Máy pha cà phê nhỏ giọt làm việc thế nào?"),
    ("Bình chứa trong suốt có vạch chia theo số cốc.", "Bình chứa trong suốt có vạch chia theo số cốc."),
    ("Khi máy chạy, mực nước hạ dần.", "Khi máy chạy, mực nước hạ dần."),
    ("Nước nóng nhỏ xuống phễu lọc chứa bột cà phê.", "Nước nóng nhỏ xuống phễu lọc chứa bột cà phê."),
    ("Cà phê chảy thành một dòng nhỏ, đều, xuống bình thủy tinh đặt trên đế giữ nhiệt.",
     "Cà phê chảy thành một dòng nhỏ, đều, xuống bình thủy tinh đặt trên đế giữ nhiệt."),
    ("Hơi nước đọng kín thành bình.", "Hơi nước đọng kín thành bình."),
    ("Toàn bộ đoạn quay dài 2 phút 21 giây, liền một cảnh.", "Toàn bộ đoạn quay dài hai phút hai mươi mốt giây, liền một cảnh."),
]
rev = lambda pid: m.editvideo_read_project(pid)["revision"]
# The tank emptying takes ~100 s of a handheld take: lock it like a tripod first (a fast-forward multiplies shake by
# its rate), then retime x8 with motion blur; the shot plays that clip at an integer rate on top.
STAB = {"path": str(SRC), "start": 10.0, "end": 70.0, "mode": "lock", "max_zoom": 1.35, "region": [.27, .37, .50, .90]}  # rigid body + base: not the draining tank or the filling carafe
RET = {"start": 0, "end": 60, "speed": 8, "motion_blur": .5, "interpolation": "blend", "crf": 16}


def media_task(submit, request):
    import time
    task = submit(request)
    while True:
        r = m.editvideo_get_media_task(task["id"])
        if r["state"] in ("completed", "failed", "cancelled", "interrupted"):
            assert r["state"] == "completed", r.get("error")
            return r
        time.sleep(3)


def timelapse(pid):
    """Stabilized + retimed tank clip, made once (task ids kept in the state file) and attached to the project."""
    state = json.loads(STATE.read_text())
    key = {**STAB, "_algorithm": "register-9"}  # the stabilizer changed (leashed lock): earlier results are not reused
    if state.get("stab_req") != key:
        state.update(stab_req=key, stab=media_task(m.editvideo_stabilize_footage, STAB)["id"], ret_req=None)
    if state.get("ret_req") != RET:
        stab_video = m.editvideo_get_media_task(state["stab"])["result"]["video"]
        state.update(ret_req=RET, ret=media_task(m.editvideo_retime_footage, {**RET, "path": stab_video})["id"], asset=None)
    if not state.get("asset") or not any(a["id"] == state["asset"] for a in store.assets(pid)):
        state["asset"] = m.editvideo_attach_media_result(state["ret"], pid, rev(pid), "video", "tank time-lapse (stabilized, retimed x8)", "evidence")["asset"]["id"]
    STATE.write_text(json.dumps(state))
    report = m.editvideo_get_media_task(state["ret"])["result"]["report"]
    return state["asset"], report["output_frames"] / 30


def project():
    if STATE.exists():
        return json.loads(STATE.read_text())["pid"]
    pid = m.editvideo_create_project({"title": "Máy pha nhỏ giọt", "script": " ".join(a for a, _ in SENT), "spoken_text": " ".join(b for _, b in SENT),
                                      "profile": "square", "renderer": "remotion", "captions": False, "voice": "vi-VN-NamMinhNeural",
                                      "voice_backend": "piper"})["id"]
    STATE.write_text(json.dumps({"pid": pid}))
    return pid


def main():
    pid = project()
    A = {a["name"]: a["id"] for a in store.assets(pid)}
    if SRC.name not in A:
        A[SRC.name] = m.editvideo_import_media(pid, str(SRC), role="evidence", tags="Moccamaster brewing, handheld, CC BY 3.0 Erik Pålsson")["id"]
    cfg = store.get_project(pid)["config"]
    script, spoken = " ".join(a for a, _ in SENT), " ".join(b for _, b in SENT)
    changed = cfg.get("script") != script or cfg.get("spoken_text") != spoken
    if changed:  # the script is part of the plan: a new script means new narration
        store.update_project(pid, {**cfg, "script": script, "spoken_text": spoken})
    if not agent.read(pid).get("timeline") or changed or "--replan" in sys.argv:
        j = store.create_job(pid, "plan")
        m.worker.run(j["id"])
        assert m.editvideo_get_job(j["id"])["state"] == "completed", m.editvideo_get_job(j["id"])
    words = store.read_json(store.folder(pid) / "plan" / "words.json")
    bm = beatmap.beat_map(pid, 0, 40)
    sents = bm["beats"]
    assert len(sents) == len(SENT), (len(sents), [b["text"] for b in sents], words.get("method"))
    f = lambda sec: int(round(sec * 30))
    t = agent.read(pid)["timeline"]
    N = t["total_frames"]
    bounds = [0] + [f(s["t"][0]) - 6 for s in sents[1:]] + [N]
    tl_asset, tl_secs = timelapse(pid)
    tl_rate = max(1, min(4, int(tl_secs * 30 // (bounds[3] - bounds[2]))))  # integer: no judder
    # (source s, focus x, focus y, held zoom, playback rate) per sentence; the 16:9 take is cropped to a square by cover.
    plan = [(2.0, .40, .5, 0, 1), (6.0, .40, .5, .5, 1), (10.0, .40, .5, .15, 8), (55.0, .55, .5, .5, 1), (62.0, .55, .5, .6, 1),
            (131.0, .55, .5, .7, 1), (100.0, .40, .5, 0, 1)]
    zoom_at = {1: (.36, .22), 2: (.40, .30), 3: (.62, .25), 4: (.66, .62), 5: (.64, .66)}
    shots = []
    for i, ((src, fx, fy, zoom, rate), a, b) in enumerate(zip(plan, bounds, bounds[1:])):
        sh = {"id": f"s{i}", "beat_id": f"b{i}", "start_frame": a, "end_frame": b, "asset_id": A[SRC.name], "source_start": src, "fit": "cover",
              "focus_x": fx, "focus_y": fy, "motion": "hold", "role": "evidence", "playback_rate": rate, "effects": []}
        if i == 2:  # the time-lapse: its own clip, already locked; no extra zoom on top of the stabilizer's crop
            sh.update(asset_id=tl_asset, source_start=0, playback_rate=tl_rate)
            shots.append(sh)
            continue
        if zoom:
            zx, zy = zoom_at[i]
            sh["effects"].append({"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": zoom, "focus_x": zx, "focus_y": zy, "cut": True}})
        sh["effects"].append({"name": "focus_zoom", "start_frame": 0, "end_frame": b - a - 1, "easing": "linear",
                              "params": {"amount": .05, "focus_x": (zoom_at.get(i) or (.5, .5))[0], "focus_y": (zoom_at.get(i) or (.5, .5))[1]}})
        shots.append(sh)
    t["shots"], t["layers"] = shots, []
    m.editvideo_patch_timeline(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    m.editvideo_apply_design(pid, rev(pid), {"style_id": "monochrome_focus", "palette_id": "amber", "heading_font_id": "oswald", "body_font_id": "inter"})
    L = lambda **kw: {"op": "upsert_layer", "layer": {"z": 300, **kw}}
    sh = lambda i: shots[i]
    from editvideo.design_library import stack_line_height, fit_width
    lh = lambda text, w=700: max(1.05, stack_line_height("oswald", text.split("\n"), w)["line_height"])
    out = lambda d: [{"name": "fade_out", "start_frame": d - 9, "end_frame": d - 1}]
    ops = [
        L(id="title", kind="text", text="MÁY PHA\nNHỎ GIỌT", start_frame=8, end_frame=bounds[1] - 2, x=.06, y=.07, width=.6, height=.3,
          font_id="oswald", font_weight=700, font_size=96, line_height=lh("MÁY PHA\nNHỎ GIỌT"), color="#ffffff",
          effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 10}, {"name": "rise", "start_frame": 0, "end_frame": 12, "params": {"amount": 24}},
                   {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 22}}] + out(bounds[1] - 10)),
        L(id="speed", kind="text", text=f"TUA NHANH ×{8 * tl_rate}", start_frame=bounds[2] + 4, end_frame=bounds[3] - 2,
          x=round(.94 - fit_width("inter", f"TUA NHANH ×{8 * tl_rate}", 34, 1080, 700, 16), 4), y=.06,
          width=fit_width("inter", f"TUA NHANH ×{8 * tl_rate}", 34, 1080, 700, 16), height=.06,
          font_id="inter", font_weight=700, font_size=34, color="#ffffff", background="#000000aa", data={"align": "center"},
          effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 8}, {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 16}}]
          + out(bounds[3] - bounds[2] - 6)),
        L(id="end", kind="text", text="2 PHÚT 21 GIÂY\nMỘT CẢNH QUAY", start_frame=bounds[6] + 4, end_frame=N - 1, x=.06, y=.08, width=.7, height=.2,
          font_id="oswald", font_weight=700, font_size=72, line_height=lh("2 PHÚT 21 GIÂY\nMỘT CẢNH QUAY"), color="#ffffff",
          effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 10}, {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 20}}]
          + out(N - 1 - bounds[6] - 4)),
        # Source credit with the opening and again at the end (it is read twice, never in a rush).
        *[L(id=f"credit{k}", kind="text", text="Video: Erik Pålsson · Wikimedia Commons · CC BY 3.0", start_frame=a, end_frame=b,
            x=.06, y=.92, width=.88, height=.04, font_id="inter", font_size=28, color="#d8d2c4", typography_role="source",
            effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 10}, {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 12}}]
            + out(b - a)) for k, (a, b) in enumerate(((8, bounds[1] - 2), (bounds[6] + 4, N - 1)))],
    ]
    # Part labels: placed beside the part on their first frame, then pinned to it so they ride the handheld camera.
    parts = [(1, "tank", "Bình chứa nước", (.08, .48), [.30, .12, .42, .30]), (3, "filter", "Phễu lọc", (.60, .52), [.47, .14, .58, .32]),
             (4, "carafe", "Bình thủy tinh", (.40, .76), [.47, .52, .60, .70])]
    spoken_words = words.get("words") or []

    def said_at(i, needle):  # first frame the narration says `needle` inside sentence i (labels land on their word)
        a0, b0 = sents[i]["t"]
        hit = next((w["start"] for w in spoken_words if a0 - .05 <= w["start"] <= b0 and needle in w["text"].lower()), None)
        return f(hit) - 4 if hit is not None else None

    for i, lid, text, (lx, ly), region in parts:
        a, b = max(bounds[i] + 6, said_at(i, text.split()[0].lower()) or 0), bounds[i + 1] - 2
        ops.append(L(id=f"{lid}-label", kind="text", text=text, start_frame=a, end_frame=b, x=lx, y=ly, width=fit_width("inter", text, 40, 1080, 700, 16),
                     height=.06, font_id="inter", data={"align": "center"},
                     font_weight=700, font_size=40, color="#ffffff", background="#00000099",
                     effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 8}, {"name": "fade_out", "start_frame": b - a - 8, "end_frame": b - a - 1}]))
    m.editvideo_patch_timeline(pid, rev(pid), ops)
    # Track each part in the source seconds its shot plays, then pin the label to it.
    pins = []
    starts = {o["layer"]["id"]: o["layer"]["start_frame"] for o in ops}
    for i, lid, text, _, region in parts:
        s = sh(i)
        t0 = s["source_start"] + (starts[f"{lid}-label"] - s["start_frame"]) / 30 * s["playback_rate"]  # from the label's first frame
        secs = (s["end_frame"] - starts[f"{lid}-label"]) / 30 * s["playback_rate"]
        tr = m.editvideo_track_region(str(SRC), t0, t0 + min(29.5, secs), region, 12, 1080, 1080)
        r = m.editvideo_pin_to_track(pid, rev(pid), tr["manifest"], s["id"], [f"{lid}-label"])
        pins.append(r["pinned"][0])
    au = [(x["code"], x["level"], x.get("where")) for x in m.editvideo_audit_timeline(pid)["findings"] if x["level"] != "info"]
    bm = beatmap.beat_map(pid, 0, 40)
    vb = store.folder(pid) / "plan" / "voice-backend.json"
    asr = store.read_json(vb).get("asr_check") if vb.exists() else None
    stab = m.editvideo_get_media_task(json.loads(STATE.read_text())["stab"])["result"]["report"]
    print(json.dumps({"pid": pid, "timing": words.get("method"), "frames": N, "timelapse_rate": tl_rate,
                      "stabilize": {k: stab.get(k) for k in ("correction_capped", "zoom", "residual_coverage", "residual_drift_px", "residual_step_px")},
                      "pins": pins, "beat_findings": bm["findings"],
                      "rhythm": bm["rhythm"], "audit": au, "asr_check": asr},
                     ensure_ascii=False)[:4000])
    m.editvideo_export_code(pid, engine="remotion", overwrite=True)


if __name__ == "__main__":
    main()
