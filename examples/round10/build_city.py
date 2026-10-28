"""Round-10 build C: a vertical CITY montage, "cities light up", from six Wikimedia Commons timelapses (Earth at night,
NASA Earth Observatory, public domain; Shanghai Bund day to night, Yigang Yu, CC0; the Lentos museum lights, TheRo,
CC0; the Nibelungen bridge, Linz, TheRo, CC BY-SA 4.0; Tokyo high-rises, The Nature Box, CC BY-SA 4.0; the Dan Ryan
Expressway, Chicago, AlphaBeta135, CC BY 4.0) cut to Komiku's "Mall" (CC0, 140 BPM). City grammar: orient the viewer
(the planet, then streets by day), one location per bar, whips that follow the measured motion, a light leak on each
phrase change, the most kinetic shot (Shanghai's skyline turning from day to night at 4.4x) on the strongest musical
moment, a calm wide end. A Dresden hyperlapse was left out: its creator's logo and captions are burned into the picture.
Usage: python examples/round10/build_city.py"""
import glob, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, music, accents, clips
store.initialize(recover=False)
C = ROOT / "data" / "sources" / "commons"
SRC = {k: glob.glob(str(C / f"city-*{pat}*.webm"))[0] for k, pat in
       (("earth", "Black_Marble"), ("shanghai", "Shanghai"), ("lentos", "Lentos"), ("bridge", "Nibelungen"), ("tokyo", "Tokyo"), ("chicago", "Dan_Ryan"))}
MUSIC = C / "music-Komiku_-_08_-_Mall.ogg"
N = 720  # 24 s
M0 = 0.86  # the excerpt starts on the track's first downbeat
rev = lambda pid: m.editvideo_read_project(pid)["revision"]


def build():
    st = music.structure(str(MUSIC))
    downs = [round((b - M0) * 30) for b in st["downbeats"] if 0 <= b - M0 < N / 30 + 1]
    D = lambda k: downs[k] if k < len(downs) else N
    print("music", st["bpm"], "downbeats", downs[:16], flush=True)
    rk = clips.rank(list(SRC.values()), 3.0, 30, True)
    key = {str(Path(p).resolve()): k for k, p in SRC.items()}
    direction = lambda k, t_: next((w["direction_deg"] for w in rk["windows"] if key[w["path"]] == k and w["start"] <= t_ < w["end"]), None)
    print("match cuts", [(key[p["out"]["path"]], p["out"]["at"], key[p["in"]["path"]], p["in"]["at"], p["score"]) for p in rk["match_cuts"][:3]], flush=True)
    pid = agent.create_silent("vertical", N, "remotion", "Cities light up")["id"]
    A = {k: m.editvideo_import_media(pid, p, role="evidence", tags="Wikimedia Commons", preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
         for k, p in SRC.items()}
    A["music"] = m.editvideo_import_media(pid, str(MUSIC), role="decoration", tags="Komiku - Mall, CC0", preserve_plan=True,
                                          base_revision=rev(pid))["asset"]["id"]
    # (from bar, to bar, clip, source s, focus_x, playback rate, motion): one place per bar, the climax for three
    # integer rates only: a fractional speed-up shows source frames in an uneven cadence (cut_audit: fractional_speed)
    plan = [(0, 2, "earth", 0.0, .5, 2, "push"),        # the planet at night: where we are
            (2, 3, "shanghai", 0.7, .47, 4, "hold"),    # a skyline by day, ending at 7.5 s ...
            (3, 4, "chicago", 0.0, .5, 2, "hold"),      # ... match cut (rank_clips: the skyline shape continues) to Chicago
            (4, 5, "bridge", 2.0, .45, 3, "hold"),
            (5, 6, "tokyo", 0.0, .5, 2, "push"),
            (6, 7, "tokyo", 6.0, .5, 2, "hold"),        # the lights come on
            (7, 8, "lentos", 3.0, .5, 2, "hold"),
            (8, 11, "shanghai", 14.0, .47, 4, "push"),  # the climax on the section change: day to night in 5 s
            (11, 12, "lentos", 9.0, .5, 2, "hold"),
            (12, None, "earth", 14.0, .5, 2, "pull")]   # back to the planet: a calm wide end
    t = agent.read(pid)["timeline"]
    base = {**t["shots"][0], "fit": "cover", "text": "", "role": "evidence", "focus_y": .5, "effects": []}
    shots = []
    for i, (b0, b1, k, src0, fx, rate, motion) in enumerate(plan):
        a, b = D(b0), (D(b1) if b1 is not None else N)
        sh = {**base, "id": f"c{i:02d}", "start_frame": a, "end_frame": b, "asset_id": A[k], "source_start": src0, "focus_x": fx,
              "playback_rate": rate, "motion": motion}
        d = direction(k, src0 + .5)
        if i in (4, 7, 8) and d is not None:  # a whip on three cuts (not the match cut), in the incoming shot's measured motion direction
            sh["transition"] = {"name": "whip_left" if abs(d) > 90 else "whip_right", "duration_frames": 8}
        shots.append(sh)
    t["shots"], t["layers"] = shots, []
    t["audio_clips"] = [{"id": "music", "asset_id": A["music"], "start_frame": 0, "end_frame": N, "source_start": M0, "volume": 1.0,
                         "fade_in": .05, "fade_out": 1.8, "duck_under_voice": False, "role": "music", "normalize": True}]
    agent.patch(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    from editvideo.design_library import fit_size
    def T(id, text, a, b, y, size, weight=800, color="#ffffff", x=.08, w=.84, bg=None, font="montserrat"):
        fs = fit_size(font, text, w, 1080, weight, size, tracking=.2)  # sized for the spread the tracking effect reaches
        fx = [{"name": "fade_in", "start_frame": 0, "end_frame": 8}, {"name": "tracking", "start_frame": 0, "end_frame": 16, "params": {"amount": .2}},
              {"name": "fade_out", "start_frame": b - a - 8, "end_frame": b - a - 1}]
        return {"op": "upsert_layer", "layer": {"id": id, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": x, "y": y, "width": w,
                "height": round(fs * 1.5 / 1920 + .012, 3), "z": 900, "font_id": font, "font_weight": weight, "font_size": fs, "line_height": 1.2,
                "color": color, **({"background": bg} if bg else {}), "effects": fx}}
    place = lambda id, text, i: T(id, text, shots[i]["start_frame"] + 4, shots[i]["end_frame"] - 2, .7, 44, 700, "#ffe3a3", w=.5, bg="#0b1020")
    agent.patch(pid, rev(pid), [
        T("title", "THÀNH PHỐ LÊN ĐÈN", 6, D(2) - 2, .17, 110),  # over the black of space above the globe
        place("p-shanghai", "Thượng Hải", 1), place("p-chicago", "Chicago", 2), place("p-linz", "Linz", 3), place("p-tokyo", "Tokyo", 4),
        T("end", "Mỗi đêm, hành tinh lên đèn.", D(12) + 6, N - 2, .16, 64, 700),
        # three short credit lines, entering a few frames apart, above the bottom UI band (y >= .8)
        T("credit", "Video: NASA · Yigang Yu · TheRo", D(12) + 12, N - 2, .64, 32, 400, "#d8e0f0", font="bevietnampro"),
        T("credit2", "The Nature Box · AlphaBeta135", D(12) + 17, N - 2, .675, 32, 400, "#d8e0f0", font="bevietnampro"),
        T("credit3", "Wikimedia Commons · Nhạc: Komiku (CC0)", D(12) + 23, N - 2, .71, 32, 400, "#d8e0f0", font="bevietnampro"),
    ])
    r = accents.sync(pid, rev(pid), {"style": "travel", "drops": [M0 + D(8) / 30]})  # music-file seconds of the climax cut
    print("accents", r["counts"], r["drops"], [x["frame"] for x in r["placed"]], flush=True)
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "tiktok", "id": "master", "start_frame": 0, "end_frame": N})
    au = [(f["code"], f["level"]) for f in m.editvideo_audit_timeline(pid)["findings"]]
    print(json.dumps({"pid": pid, "cuts": [sh["start_frame"] for sh in shots], "audit": au}, ensure_ascii=False))


if __name__ == "__main__":
    build()
