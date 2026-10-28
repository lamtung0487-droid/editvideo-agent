"""Round-12 learning test, the remake: the same learned blueprint (bp-6dc18d8ef6abc645, revision 4) on footage that
passes the picture gate the first attempt lacked.

The first rebuild (build_travel.py) matched the exemplar's structure and rhythm and still looked worse: its Commons
footage was mostly phone clips (shaky, 720p, flat noon light) chosen by content alone. Here every shot comes from
25 Pexels clips the user approved, each window graded by editvideo.look (resolution, detail, noise, handheld jitter,
clipping) before it was used, then pulled lightly (strength .35) toward the exemplar's palette (grade_pexels.py).

90 s on Inspiring Teaser (Rafael Krux, CC BY 4.0) from its bar at 8.47 s to its drop at 98.43 s, so the music's lift
(40.8 s) lands at a third of the film as in the exemplar: cold open with the title, establishing aerials, a burst of
people with half-beat flashes into the lift and a held portrait on it, dusk, night under lanterns, a fade to black.
Usage: python examples/round12/build_travel_v2.py"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, music
store.initialize(recover=False)
MUSIC = ROOT / "data" / "sources" / "commons" / "vn-music-Rafael_Krux_-_Inspiring_Teaser_cc-by_filmmusic_.mp3"
GRADED = json.loads((ROOT / "data" / "tmp" / "r12_graded_px.json").read_text(encoding="utf-8"))
M0, M1 = 8.47, 98.43  # a downbeat to the drop
N = round((M1 - M0) * 30)
CREAM = "#ecd4c8"
rev = lambda pid: m.editvideo_read_project(pid)["revision"]

# (Pexels id, source second) per shot
COLD = [("37887206", 10.0)]                                                     # Cat Ba in morning haze, the title over it
ESTABLISH = [("35127612", 2.0), ("38178503", 4.0), ("35589587", 3.0), ("7417616", 12.0)]
BURST_A = [("27134197", 3.0), ("16051693", 2.0), ("15692758", 2.0), ("3784667", 6.0), ("10388295", 4.0), ("7217096", 1.0),
           ("38178503", 14.0), ("27102711", 1.5), ("12690271", 4.0)]
FLASH = [("16051693", 9.0), ("27134197", 12.0), ("10388295", 13.0), ("15692758", 8.0), ("7217096", 4.0), ("27102711", 7.0),
         ("16051693", 15.0), ("10388295", 20.0), ("27134197", 20.0), ("15692758", 12.0), ("35589587", 8.0)]
BREATH = [("3784667", 20.0)]                                                     # a slow blue wide in the musical breath
HERO = [("27102711", 4.3)]                                                       # her smile, held on the lift
BURST_B = [("16051693", 5.5), ("10388295", 24.0), ("27102711", 9.0), ("15692758", 13.5), ("27134197", 24.0)]  # not her again straight after
DUSK = [("40134771", .5), ("12690271", 12.0), ("36670222", 3.0), ("38224338", 3.0), ("12690271", 22.0), ("40134771", 5.5), ("38224338", 11.0)]
NIGHT = [("15843973", 3.0), ("13380372", 1.5), ("39637165", 2.0), ("15245736", 4.0), ("13514070", 3.0), ("30356704", 2.5), ("15245736", 13.0)]
OUTRO = [("39750916", 20.0)]


def cut_plan(db):
    beat = .3
    t = [db[7], db[13]]                                                # cold open from bar 7, the first cut at bar 13
    t += [db[i] for i in range(15, 22, 2)]                             # establishing: 4 shots of 2 bars
    t += [db[i] for i in range(22, 31)]                                # burst A: 9 shots of 1 bar
    t += [db[30] + beat * k for k in range(1, 12)]                     # 11 half-beat flashes into the quiet before the lift
    t += [db[34], db[37]]                                              # the breath, then the portrait on the lift (bar 34)
    t += [db[i] for i in range(38, 43)]                                # burst B: 5 shots of 1 bar
    t += [db[i] for i in range(44, 57, 2)]                             # dusk: 7 shots of 2 bars
    t += [db[i] for i in range(59, 78, 3)]                             # night: 7 shots of 3 bars
    return [x - M0 for x in t]                                         # the outro runs from bar 77 to the drop


def build():
    db = music.structure(str(MUSIC))["downbeats"]
    cuts = cut_plan(db)
    order = COLD + ESTABLISH + BURST_A + FLASH + BREATH + HERO + BURST_B + DUSK + NIGHT + OUTRO
    assert len(order) == len(cuts), (len(order), len(cuts))
    frames = [0] + [round(c * 30) - 2 for c in cuts[1:]] + [N]  # picture 2 frames ahead of the beat
    pid = agent.create_silent("landscape", N, "remotion", "Vẻ đẹp Việt Nam", color="#000000")["id"]
    assets = {}
    for key in dict.fromkeys(k for k, _ in order):
        g = GRADED[key]
        r = m.editvideo_attach_media_result(g["task"], pid, rev(pid), "video", f"{g['source']} (Pexels), graded lightly", "evidence")
        assets[key] = r.get("asset", r).get("id")
    A_music = m.editvideo_import_media(pid, str(MUSIC), role="decoration", tags="Rafael Krux, Inspiring Teaser, CC BY 4.0", preserve_plan=True,
                                       base_revision=rev(pid))["asset"]["id"]
    t = agent.read(pid)["timeline"]
    base = {**t["shots"][0], "text": "", "role": "evidence", "effects": [], "motion": "hold", "fit": "cover", "focus_x": .5, "focus_y": .5, "playback_rate": 1}
    shots = [{**base, "id": f"v{i:02d}", "start_frame": frames[i], "end_frame": frames[i + 1], "asset_id": assets[k], "source_start": s}
             for i, (k, s) in enumerate(order)]
    # conform against the blueprint measured the day footage at saturation .10-.18 (the exemplar's day: .21-.48, night alike):
    # lift colour where it is short, by section, and leave the lanterns alone
    sat = [1.3] * (len(order) - len(DUSK) - len(NIGHT) - len(OUTRO)) + [1.15] * len(DUSK) + [1.0] * (len(NIGHT) + len(OUTRO))
    for sh, k in zip(shots, sat):
        if k != 1.0:
            sh["effects"] = [{"name": "saturate", "start_frame": 0, "end_frame": sh["end_frame"] - sh["start_frame"], "params": {"amount": k}}]
    shots[0]["effects"].append({"name": "fade_in", "start_frame": 0, "end_frame": 33})
    for k, d in ((1, 5), (1 + len(ESTABLISH) + len(BURST_A), 3)):  # the exemplar's two whips: into the aerials, into the 9-frame flashes
        shots[k]["transition"] = {"name": "whip_left", "duration_frames": d}
    dz = len(order) - len(OUTRO) - 1  # one long dissolve between the last two night shots
    shots[dz]["transition"] = {"name": "dissolve", "duration_frames": 30, "mode": "live"}
    last = shots[-1]
    last["effects"] = [{"name": "fade_out", "start_frame": 45, "end_frame": last["end_frame"] - last["start_frame"] - 6}]
    t["shots"], t["layers"] = shots, []
    t["audio_clips"] = [{"id": "music", "asset_id": A_music, "start_frame": 0, "end_frame": N, "source_start": M0, "volume": 1.0, "fade_in": .3,
                         "fade_out": 2.5, "duck_under_voice": False, "role": "music", "normalize": True}]
    t["design"] = {**t.get("design", {}), "typography": {
        "display": {"font_id": "notoserif", "size": 200, "weight": 250, "tracking": .12, "line_height": 1.1, "variation_axes": {"wdth": 62.5}},
        "label": {"font_id": "notoserif", "size": 40, "weight": 600, "tracking": .04, "line_height": 1.2},
        "caption": {"font_id": "notoserif", "size": 29, "weight": 500, "tracking": .06, "line_height": 1.2},
        "source": {"font_id": "notoserif", "size": 24, "weight": 500, "tracking": .1, "line_height": 1.5}}}
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "replace_timeline", "timeline": t}])
    bar = .1218  # 2.35:1 inside 16:9

    def T(id, text, a, b, y, h, role, track=None, color=CREAM):
        size = {"display": 200, "label": 40, "caption": 29, "source": 24}[role]
        fx = [{"name": "fade_in", "start_frame": 0, "end_frame": 14}, {"name": "fade_out", "start_frame": b - a - 14, "end_frame": b - a - 1},
              {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": max(10, round(size * .2))}}]
        if track is not None:
            fx.append({"name": "tracking", "start_frame": 0, "end_frame": b - a - 1, "easing": "linear", "params": {"amount": track, "from_em": track * .6}})
        return {"op": "upsert_layer", "layer": {"id": id, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": .08, "y": y, "width": .84,
                "height": h, "z": 960, "typography_role": role, "color": color, "data": {"align": "center"}, "effects": fx}}
    # credits on the letterbox bars (black, so they read over the bright lanterns), one measured line each (<= 1500 px)
    makers = "Giste Producciones · Florian Delée · Tom Fisk · Taryn Elliott · Khanh Hoang Minh · Vincent Nguyen · Lê Cuộc"
    makers2 = "Anna Tarazevich · Toon Van Dyck · Anh Tuấn Lê · doong nhii · Chó Và Mèo · Barley Gaogao  —  trên Pexels"
    song = "Nhạc: Rafael Krux, Inspiring Teaser (CC BY 4.0)"
    o0 = frames[-2]  # the outro shot
    ops = [{"op": "upsert_layer", "layer": {"id": f"bar{k}", "kind": "shape", "start_frame": 0, "end_frame": N, "x": 0, "y": y, "width": 1, "height": bar,
                                             "z": 950, "color": "#000000", "data": {"shape": "rectangle", "corner_radius": 0}}} for k, y in ((0, 0), (1, 1 - bar))]
    ops += [T("t_small", "vẻ đẹp của", 40, frames[1] - 4, .335, .06, "label"),
            T("t_name", "VIỆT NAM", 66, frames[1] - 4, .39, .24, "display", .14),
            T("t_sub", "từ bình minh tới đêm", 96, frames[1] - 4, .635, .05, "caption"),
            T("cr1", makers, o0 + 20, N - 4, .022, .04, "source", None, "#d9cfc8"),
            T("cr2", makers2, o0 + 20, N - 4, .062, .04, "source", None, "#d9cfc8"),
            T("cr3", song, o0 + 20, N - 4, 1 - bar + .04, .04, "source", None, "#d9cfc8")]
    agent.patch(pid, rev(pid), ops)
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "tiktok", "id": "master", "start_frame": 0, "end_frame": N})
    au = [(f["code"], f["level"]) for f in m.editvideo_audit_timeline(pid)["findings"]]
    print(json.dumps({"pid": pid, "frames": N, "shots": len(shots), "audit": au}, ensure_ascii=False))


if __name__ == "__main__":
    build()
