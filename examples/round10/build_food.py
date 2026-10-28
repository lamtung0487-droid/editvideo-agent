"""Round-10 build F: a vertical FOOD short, "fire and hands", from six Wikimedia Commons kitchen clips (teppanyaki,
Singapore, Jacklee, CC BY-SA 4.0; wok, Beynost, and skewers, Lyon, Benoît Prieur, CC0; pitas, Pittsburgh, Cbaile19,
CC0; tortellini, Valeggio, Reinhard Müller, CC BY-SA 4.0; sushi by chef Seijun Okano, Bobak Ha'Eri, CC BY 3.0) cut to
Better Days (Uederson, CC0, 120 BPM). Food grammar: the most striking image first, steps cut on the beat and on
contact, a run of quick repeated hand shots, two crafts side by side (split screen), one slow payoff (the wok flame,
ramped around its burst) with a small punch on the section change, the finished piece last. The kitchens' own sound
plays as foley under the music where a clip has it. Labels name only what the source titles state.
Windows and 9:16 crop positions were chosen on contact sheets of the clips. Usage: python examples/round10/build_food.py"""
import glob, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, music, accents, clips
store.initialize(recover=False)
C = ROOT / "data" / "sources" / "commons"
SRC = {k: glob.glob(str(C / f"food-*{pat}*.webm"))[0] for k, pat in
       (("sushi", "Hiden_sushi"), ("wok", "wok"), ("pita", "Pitas"), ("skewer", "brochettes"), ("teppan", "Teppanyaki"), ("tortellini", "Tortellini"))}
MUSIC = ROOT / "data" / "sources" / "other" / "music-Better_Days.ogg"
STATE = ROOT / "data" / "films" / "r10-food.json"
N = 750  # 25 s: the last 5 s hold the plate, the line and the credits
M0 = 2.01  # the excerpt starts on the track's first downbeat
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
    st = music.structure(str(MUSIC))
    beats = [round((b - M0) * 30) for b in st["beats"] if 0 <= b - M0 < N / 30 + 1]
    print("music", st["bpm"], "beats", beats[:12], flush=True)
    has_sound = {k: clips.audio_presence(p) not in ("silent", "none") for k, p in SRC.items()}  # which kitchens have sound to keep
    print("sound", has_sound, flush=True)
    # the payoff: the wok flame bursting at 6.3 s, 0.35x through the burst
    ramp_req = {"path": SRC["wok"], "start": 5.2, "end": 8.4, "speed": 1.0, "peaks": [6.4], "peak_speed": .35, "ramp_s": .3, "hold_s": .8,
                "interpolation": "flow", "motion_blur": .3}
    if s.get("ramp_req") != ramp_req:
        s.update(ramp_req=ramp_req, ramp=media_task(m.editvideo_retime_footage, ramp_req)["id"])
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(s))
    pid = agent.create_silent("vertical", N, "remotion", "Fire and hands")["id"]
    A = {k: m.editvideo_import_media(pid, p, role="evidence", tags="Wikimedia Commons", preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
         for k, p in SRC.items()}
    A["ramp"] = m.editvideo_attach_media_result(s["ramp"], pid, rev(pid), "video", "wok-ramp", "evidence")["asset"]["id"]
    A["music"] = m.editvideo_import_media(pid, str(MUSIC), role="decoration", tags="Better Days by Uederson, CC0", preserve_plan=True,
                                          base_revision=rev(pid))["asset"]["id"]
    B = lambda k: beats[k] if k < len(beats) else N  # timeline frame of beat k (absolute times, no drift)
    ramp_in = (6.4 - 5.2) - .4 - .3
    # (from beat, to beat, clip, source s, focus_x, playback rate)
    plan = [(0, 4, "teppan", 1.3, .6, 1),        # the hook: a teppanyaki flame bursts toward the lens
            (4, 6, "skewer", 2.0, .6, 1),        # skewers over the coals (before 1 s an arm blurs across the lens)
            (6, 8, "tortellini", 2.0, .62, 1),
            (8, 12, "tortellini", 5.0, .6, 1),   # under the split screen (tortellini over sushi hands)
            (12, 14, "pita", 4.0, .28, 1),
            (14, 16, "wok", 2.6, .5, 1),
            (16, 17, "sushi", 13.0, .52, 1),     # a run of repeated steps, one per beat
            (17, 18, "tortellini", 7.4, .62, 1),
            (18, 19, "sushi", 15.4, .52, 1),
            (19, 20, "tortellini", 9.0, .6, 1),
            (20, 24, "skewer", 8.0, .62, 1),
            (24, 28, "sushi", 3.0, .3, 1),       # the chef at the counter: a breath before the payoff
            (28, 34, "ramp", max(0.0, ramp_in - .1), .55, 1),  # the payoff on the section change (music 16 s)
            (34, 40, "sushi", 22.6, .36, .85),   # the finished nigiri on its plate, slightly slowed
            (40, None, "sushi", 25.05, .36, 1)]  # held: the end card over the last frame
    t = agent.read(pid)["timeline"]
    base = {**t["shots"][0], "fit": "cover", "text": "", "motion": "hold", "role": "evidence", "focus_y": .5, "effects": []}
    shots, audio = [], []
    for i, (b0, b1, k, src0, fx, rate) in enumerate(plan):
        a, b = B(b0), (B(b1) if b1 is not None else N)
        sh = {**base, "id": f"f{i:02d}", "start_frame": a, "end_frame": b, "asset_id": A[k], "source_start": src0, "focus_x": fx, "playback_rate": rate}
        if k == "ramp":  # the flame fills the top half of the frame, blank steel the bottom: punch in on the fire
            sh["effects"] = [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .3, "cut": True, "focus_x": .5, "focus_y": .3}}]
        if b1 is None:
            sh.update(freeze=True, motion="push")  # a still of the plate, slowly pushed in
        shots.append(sh)
        if k in SRC and has_sound[k] and rate == 1 and b1 is not None:  # the kitchen's own sound under the music
            audio.append({"id": f"kit{i:02d}", "asset_id": A[k], "start_frame": a, "end_frame": b, "source_start": src0, "volume": .45,
                          "fade_in": .03, "fade_out": .08, "duck_under_voice": False, "role": "foley", "normalize": True})
    t["shots"], t["layers"] = shots, []
    t["audio_clips"] = [{"id": "music", "asset_id": A["music"], "start_frame": 0, "end_frame": N, "source_start": M0, "volume": 1.0,
                         "fade_in": .05, "fade_out": 1.5, "duck_under_voice": False, "role": "music", "normalize": True}, *audio]
    agent.patch(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    # two crafts at once: tortellini over sushi hands (rows in 9:16)
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "split_screen", "id": "hands", "start_frame": B(8), "end_frame": B(12), "platform": "tiktok",
                                             "asset_ids": [A["tortellini"], A["sushi"]], "source_starts": [5.0, 11.0], "layout": "rows", "background": "#1b1410"})
    from editvideo.design_library import fit_size
    def T(id, text, a, b, y, size, weight=700, color="#ffffff", x=.08, w=.74, bg=None, **kw):
        fx = [{"name": "fade_in", "start_frame": 0, "end_frame": 6}, {"name": "rise", "start_frame": 0, "end_frame": 8, "params": {"amount": 24}},
              {"name": "fade_out", "start_frame": b - a - 7, "end_frame": b - a - 1}]
        if not bg:
            fx.append({"name": "text_outline", "start_frame": 0, "end_frame": b - a - 1, "params": {"color": "#1b1410", "amount": 4}})
        fs = fit_size("bevietnampro", text, w, 1080, weight, size)
        return {"op": "upsert_layer", "layer": {"id": id, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": x, "y": y, "width": w,
                "height": round(fs * 1.5 / 1920 + .012, 3), "z": 900, "font_id": "bevietnampro", "font_weight": weight, "font_size": fs, "line_height": 1.2,
                "color": color, **({"background": bg} if bg else {}), "effects": fx, **kw}}
    chip = lambda id, text, a, b, y=.64: T(id, text, a, b, y, 40, 600, "#ffcf8a", w=.6, bg="#1b1410")
    agent.patch(pid, rev(pid), [
        # over a white-hot flame: the title needs its own dark plate to read (inspected frame)
        T("title", "LỬA & ĐÔI TAY", 2, B(4) - 1, .16, 120, bg="#1b1410"),
        T("subtitle", "6 căn bếp, một nhịp", 8, B(4) - 1, .245, 52, 600, "#ffcf8a", bg="#1b1410"),
        # (the hook carries only the title: one idea in the first seconds)
        chip("c-split1", "Tortellini · Valeggio", B(8) + 3, B(12) - 1, .2),
        chip("c-split2", "Sushi · Seijun Okano", B(8) + 3, B(12) - 1, .7),
        chip("c-skewer", "Xiên nướng than · Lyon", B(20) + 4, B(24) - 1),
        chip("c-wok", "Wok lửa lớn · Beynost", B(28) + 8, B(34) - 1),
        T("end", "Ngon bắt đầu từ lửa.", B(40) + 4, N - 2, .2, 84, color="#2a1708", bg=None),  # dark ink on the pale counter
        T("credit", "Video: Jacklee · Benoît Prieur · Cbaile19", B(40) + 10, N - 2, .6, 32, 400, "#f3e6d8", w=.84),
        T("credit2", "Reinhard Müller · Bobak Ha'Eri · Wikimedia Commons", B(40) + 10, N - 2, .645, 32, 400, "#f3e6d8", w=.84),
        T("credit3", "Nhạc: Better Days (Uederson, CC0)", B(40) + 10, N - 2, .69, 32, 400, "#f3e6d8", w=.84),
    ])
    r = accents.sync(pid, rev(pid), {"style": "food", "drops": [16.0]})  # music-file seconds: the section entry at 16 s
    print("accents", r["counts"], r["drops"], flush=True)
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "tiktok", "id": "master", "start_frame": 0, "end_frame": N})
    au = [(f["code"], f["level"]) for f in m.editvideo_audit_timeline(pid)["findings"]]
    print(json.dumps({"pid": pid, "cuts": [sh["start_frame"] for sh in shots], "audit": au}, ensure_ascii=False))


if __name__ == "__main__":
    build()
