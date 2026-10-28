"""Round-10 build W: a 16:9 wildlife mini-doc from six Wikimedia Commons clips shot in Uganda by Giles Laurent
(CC BY-SA 4.0, so this edit is CC BY-SA 4.0 too). Nature grammar: no flash or glitch, the place first, one slow-motion
moment on the only real action (a cuckoo taking off, found by rank_clips' local-action peak), species lower thirds
in Vietnamese, a dissolve only where time passes. The sources carry mute sound tracks (rank_clips reports them
silent), so the sound is a synthesized forest bed with rain that leads the hippo shot (J-cut) and trails it (L-cut);
the credits say it is synthesized. Usage: python examples/round10/build_wildlife.py"""
import glob, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, clips, sound
store.initialize(recover=False)
C = ROOT / "data" / "sources" / "commons"
SRC = {k: glob.glob(str(C / f"wildlife-{k}_*.webm"))[0] for k in ("002", "003", "004", "005", "006", "009")}
STATE = ROOT / "data" / "films" / "r10-wildlife.json"
N = 1170  # 39 s
rev = lambda pid: m.editvideo_read_project(pid)["revision"]


def media_task(submit, request):
    task = submit(request)
    while True:
        r = m.editvideo_get_media_task(task["id"])
        if r["state"] in ("completed", "failed", "cancelled", "interrupted"):
            assert r["state"] == "completed", r.get("error")
            return r
        time.sleep(3)


def build():
    s = json.loads(STATE.read_text()) if STATE.exists() else {}
    ranked = clips.rank(list(SRC.values()), 3.0, 20, False)
    print("audio", ranked["audio"], flush=True)
    cuckoo = next(w for w in ranked["windows"] if "002_" in w["path"] and w["start"] <= 3.6 <= w["end"])
    peak = cuckoo["peak_at"]  # the take-off (local action after following the camera)
    print("cuckoo take-off at", peak, flush=True)
    # one slow moment: real time while it sits, 0.3x through the take-off, back to real time as it leaves the frame
    ramp_req = {"path": SRC["002"], "start": 1.0, "end": 4.8, "speed": 1.0, "peaks": [peak + .1], "peak_speed": .3, "ramp_s": .3, "hold_s": .6,
                "interpolation": "flow", "motion_blur": .3}
    if s.get("ramp_req") != ramp_req:
        s.update(ramp_req=ramp_req, ramp=media_task(m.editvideo_retime_footage, ramp_req)["id"])
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(s))
    pid = agent.create_silent("landscape", N, "remotion", "Uganda wildlife")["id"]
    A = {}
    for k, path in SRC.items():
        A[k] = m.editvideo_import_media(pid, path, role="evidence", tags="Giles Laurent, Wikimedia Commons, CC BY-SA 4.0", preserve_plan=True,
                                        base_revision=rev(pid))["asset"]["id"]
    A["ramp"] = m.editvideo_attach_media_result(s["ramp"], pid, rev(pid), "video", "cuckoo-ramp", "evidence")["asset"]["id"]
    ramp_len = store.find_asset(pid, A["ramp"])["duration"]
    # the sound: a forest bed, rain around the hippo (synthesized; the clips' own tracks are silent)
    beds = {}
    for kind, dur, seed in (("forest", 40.0, 21), ("rain", 10.0, 5)):
        r = sound.design(kind, dur, seed, -14)
        beds[kind] = m.editvideo_import_media(pid, r["path"], role="decoration", tags=f"synthesized {kind} bed (sound.design)", preserve_plan=True,
                                              base_revision=rev(pid))["asset"]["id"]
    t = agent.read(pid)["timeline"]
    base = {**t["shots"][0], "fit": "cover", "text": "", "motion": "hold", "role": "evidence", "playback_rate": 1, "focus_x": .5, "focus_y": .5}
    cuck_n = round(ramp_len * 30)
    plan = [  # (asset, source start, frames, focus_y): lengths follow the content, short beats around long held ones
        ("004", 10.0, 150, .5),   # the water: a kingfisher on a reed, wide (title)
        ("004", 2.5, 105, .45),   # closer: the same bird (lower third)
        ("003", 0.3, 165, .5),    # rain: a baby hippo (J-cut rain leads it)
        ("005", 0.8, 120, .55),   # a baby baboon crosses to its mother, wide
        ("005", 8.0, 90, .5),     # cut in: it clings to her
        ("006", 0.3, 165, .45),   # the giant: a young mountain gorilla eating, held
        ("ramp", 0.0, cuck_n, .4),  # the moment: a red-chested cuckoo takes off, 0.3x through the take-off
    ]
    used = sum(f for *_, f, _ in plan)
    plan.append(("009", 1.0, N - used, .45))  # time passes (dissolve): baboons grooming, the close
    shots, at = [], 0
    for i, (k, src0, n, fy) in enumerate(plan):
        sh = {**base, "id": f"w{i}", "start_frame": at, "end_frame": at + n, "asset_id": A[k], "source_start": src0, "focus_y": fy,
              "effects": [{"name": "vignette", "start_frame": 0, "end_frame": n - 1, "params": {"amount": .22}}]}
        if k == "006":
            sh["motion"] = "push"  # the hero: a slow observational push
        if i == len(plan) - 1:
            sh["transition"] = {"name": "dissolve", "duration_frames": 24}
            sh["effects"].append({"name": "fade_out", "start_frame": n - 36, "end_frame": n - 1})
        shots.append(sh)
        at += n
    cut = {sh["id"]: sh["start_frame"] for sh in shots}
    t["shots"], t["layers"] = shots, []
    hippo, after = cut["w2"], cut["w3"]
    t["audio_clips"] = [
        {"id": "forest-a", "asset_id": beds["forest"], "start_frame": 0, "end_frame": hippo - 6, "source_start": 0.0, "volume": .9,
         "fade_in": .8, "fade_out": .6, "duck_under_voice": False},
        # J-cut: the rain is heard 18 frames before the hippo appears; L-cut: it trails 30 frames into the next shot
        {"id": "rain", "asset_id": beds["rain"], "start_frame": hippo - 18, "end_frame": after + 30, "source_start": 0.0, "volume": .8,
         "fade_in": .5, "fade_out": .9, "duck_under_voice": False},
        {"id": "forest-b", "asset_id": beds["forest"], "start_frame": after - 10, "end_frame": N, "source_start": 12.0, "volume": .9,
         "fade_in": 1.0, "fade_out": 1.4, "duck_under_voice": False},
    ]
    agent.patch(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    from editvideo.design_library import fit_size
    def T(id, text, a, b, y, size, font="notoserif", weight=600, color="#ffffff", x=.08, w=.84, outline=0, **kw):
        fs = fit_size(font, text, w, 1920, weight, size)
        return {"op": "upsert_layer", "layer": {
            "id": id, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": x, "y": y, "width": w, "height": .16, "z": 900,
            "font_id": font, "font_weight": weight, "font_size": fs, "line_height": 1.25, "color": color,
            "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 18}, {"name": "rise", "start_frame": 0, "end_frame": 18, "params": {"amount": 16}},
                        {"name": "shadow", "start_frame": 0, "end_frame": b - a - 1, "params": {"amount": 18}},
                        *([{"name": "text_outline", "start_frame": 0, "end_frame": b - a - 1, "params": {"color": "#0e1a14", "amount": max(2, round(fs * outline))}}] if outline else []),
                        {"name": "fade_out", "start_frame": b - a - 14, "end_frame": b - a - 1}], **kw}}
    agent.patch(pid, rev(pid), [
        # the title sits in the open water right of the bird (inspected frame: the kingfisher stands at x ~ .45, its beak reaches .62)
        # pale type over grey-green water measured 2.0-2.5:1 (audit low_contrast_plate): a thin dark outline carries it
        T("title", "UGANDA", 8, 138, .30, 150, x=.655, w=.31, outline=.025),
        T("subtitle", "Một ngày giữa\nthiên nhiên hoang dã", 30, 138, .45, 48, "bevietnampro", 400, "#f2e6c8", x=.655, w=.31, outline=.06),  # two lines read larger in the narrow space
        # credits together over the closing shot, long enough to read (two lines, ~5 s)
        T("credit", "Hình: Giles Laurent · Wikimedia Commons · CC BY-SA 4.0", N - 160, N - 4, .80, 32, "bevietnampro", 400, "#f0f0f0",
          w=.44, background="#14201a", height=.055),
        T("credit2", "Âm thanh: tổng hợp offline", N - 160, N - 4, .865, 32, "bevietnampro", 400, "#e9c46a", w=.44, background="#14201a", height=.055),
    ])
    species = [("w1", "Bói cá nhỏ", "Ceryle rudis · VQG Queen Elizabeth"), ("w2", "Hà mã con", "Hippopotamus amphibius · dưới mưa"),
               ("w3", "Khỉ đầu chó ô liu", "Papio anubis · mẹ và con"), ("w5", "Khỉ đột núi", "Gorilla beringei beringei · rừng Bwindi"),
               ("w6", "Cu cu ngực đỏ", "Cuculus solitarius · rừng Kibale")]
    for sid, name, latin in species:
        sh = next(x for x in shots if x["id"] == sid)
        a = sh["start_frame"] + 15
        b = min(sh["end_frame"] - 8, a + 96) if sid != "w6" else a + 66  # the cuckoo's name clears before it takes off
        m.editvideo_compose_edit(pid, rev(pid), {"recipe": "lower_third", "id": f"lt-{sid}", "start_frame": a, "end_frame": b, "text": name,
                                                 "secondary_text": latin, "background": "#14201a", "accent": "#e9c46a", "font_size": 44})
    # the recipe's type is the project default; a documentary pairing here (Be Vietnam Pro, with full Vietnamese marks)
    lay = agent.read(pid)["timeline"]["layers"]
    agent.patch(pid, rev(pid), [{"op": "upsert_layer", "layer": {**l, "font_id": "bevietnampro", "font_weight": 600 if l["id"].endswith("-name") else 400}}
                                for l in lay if l["id"].startswith("lt-")])
    # an ambience-only film: mastered quieter than speech or music would be (-20 LUFS), so the forest stays a bed
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "youtube_long", "id": "master", "start_frame": 0, "end_frame": N,
                                             "audio_mix": {"target_lufs": -20, "true_peak_db": -1.5, "loudness_range": 11}})
    au = [(f["code"], f["level"]) for f in m.editvideo_audit_timeline(pid)["findings"]]
    print(json.dumps({"pid": pid, "cuts": cut, "ramp_s": ramp_len, "audit": au}, ensure_ascii=False))


if __name__ == "__main__":
    build()
