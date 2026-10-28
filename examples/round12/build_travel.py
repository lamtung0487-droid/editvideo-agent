"""Round-12 learning test, step 3: rebuild a studied film's craft with our own licensed footage.

The blueprint bp-6dc18d8ef6abc645 was distilled by learnkit from one exemplar ("THE BEAUTY OF VIETNAM", Kirk Mihelakos,
studied locally only): a silent cinematic travel film that moves from dawn to night. What this build takes from it:
- structure: cold open on one long low aerial with a two-size title, establishing aerials, a montage burst of people,
  a dusk turn, a night section and a slow fade to black (the same shares of the running time);
- rhythm: a shot is a bar of the music (here 2 bars at 100 BPM = 2.4 s, 1 bar in the bursts), cut on the downbeat with
  the picture 2 frames early; a staccato burst of half-beat flashes lands on the music's lift (the exemplar's most
  replayed moment), shorter bursts later; two whips, one long dissolve, otherwise hard cuts;
- look: 2.35:1 letterbox, every piece colour-matched to frames of the exemplar at the same time of day
  (examples/round12/grade_pieces.py), a luxurious condensed serif title in the sampled cream (#ecd4c8).
Nothing of the exemplar's picture or sound is used. Usage: python examples/round12/build_travel.py"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, music, media_tasks
store.initialize(recover=False)
MUSIC = ROOT / "data" / "sources" / "commons" / "vn-music-Rafael_Krux_-_Inspiring_Teaser_cc-by_filmmusic_.mp3"
GRADED = json.loads((ROOT / "data" / "tmp" / "r12_graded.json").read_text(encoding="utf-8"))
N = 3837  # the whole track (127.999 s), its last frames inside the file
CREAM = "#ecd4c8"  # sampled from the exemplar's title
rev = lambda pid: m.editvideo_read_project(pid)["revision"]

# (piece, absolute source second) per shot, in order; lengths come from the cut plan below
COLD = [("dawn", 30.0)]
ESTABLISH = [("karst", .5), ("hue", 72.0), ("hn_day", 49.8), ("karst", 9.0), ("exp", 4.0), ("hn_day", 53.5)]
BURST_A = [("market", 10.0), ("traffic", 35.0), ("basket", 8.0), ("exp", 36.2), ("market", 40.0), ("buffalo", 6.0), ("moto", 14.0),
           ("market", 80.0), ("dacau", 1.0), ("exp", 40.2)]
FLASH_1 = [("market", 26.0), ("traffic", 28.0), ("basket", 14.0), ("market", 58.0), ("moto", 22.0), ("exp", 44.5), ("buffalo", 9.0),
           ("market", 110.0), ("traffic", 43.0), ("basket", 44.0), ("exp", 81.0)]
BREATH = [("dawn", 42.0)]
HERO = [("exp", 58.2)]  # ao dai graduates on the steps: the held human moment after the lift
BURST_B = [("exp", 82.2), ("market", 100.0), ("basket", 53.0), ("exp", 68.5), ("traffic", 40.0), ("moto", 30.0), ("market", 66.0)]
DUSK_A = [("hn_sunset", .2), ("cruise", 2.0), ("hn_dusk", 71.0), ("cruise", 10.0), ("hn_dusk", 81.6), ("hn_sunset", 4.0)]
FLASH_2 = [("hn_dusk", 74.5), ("hn_dusk", 79.2), ("hn_dusk", 97.0), ("cruise", 17.0)]
DUSK_B = [("hn_dusk", 96.5), ("hn_dusk", 104.0), ("cruise", 15.0), ("hn_dusk", 109.5), ("hn_dusk", 114.5), ("cruise", 5.0)]
# sources alternate so no two neighbours come from one continuous take (the audit had found a 0.2 s jump cut); the
# dragon's fire lands on the music's hit (bar 84)
NIGHT_A = [("hcm_night", 23.0), ("puppets", 1.0), ("hcm_night", 28.0), ("fire", .3), ("hcm_night", 34.0), ("fire", 5.6),
           ("puppets", 5.0), ("hcm_night", 40.0)]
FLASH_3 = [("hcm_night", 45.2), ("puppets", 12.0), ("fire", 9.8)]
NIGHT_B = [("puppets", 9.0), ("fire", 13.0)]
OUTRO = [("hn_dusk", 118.6)]


def cut_plan(db):
    """Cut times (s) from the music's downbeats db (1.2 s apart): 2-bar shots, 1-bar bursts, 0.3 s flashes."""
    beat = .3
    t = [0.0, db[8]]                                                     # cold open, then the first cut at bar 8
    t += [db[i] for i in range(10, 21, 2)]                               # establishing: 6 shots of 2 bars
    t += [db[i] for i in range(21, 31)]                                  # burst A: 10 shots of 1 bar
    t += [db[30] + beat * k for k in range(1, 12)]                       # flash 1: 11 half-beat flashes into the quiet gap
    t += [db[34], db[37]]                                                # breath, then the hero on the lift (bar 34)
    t += [db[i] for i in range(38, 45)]                                  # burst B: 7 shots of 1 bar
    t += [db[i] for i in range(46, 57, 2)]                               # dusk A: 6 shots of 2 bars
    t += [db[56] + beat * k for k in range(1, 4)] + [db[57]]             # flash 2: 4 flashes
    t += [db[i] for i in range(59, 70, 2)]                               # dusk B: 6 shots of 2 bars
    t += [db[i] for i in range(72, 94, 3)]                               # night A: 8 shots of 3 bars
    t += [db[93] + beat * k for k in range(1, 4)]                        # flash 3: 3 flashes
    t += [db[96], db[99]]                                                # night B, then the outro from bar 99
    return t


def build():
    st = music.structure(str(MUSIC))
    db = st["downbeats"]
    cuts = cut_plan(db)
    order = COLD + ESTABLISH + BURST_A + FLASH_1 + BREATH + HERO + BURST_B + DUSK_A + FLASH_2 + DUSK_B + NIGHT_A + FLASH_3 + NIGHT_B + OUTRO
    assert len(order) == len(cuts), (len(order), len(cuts))
    frames = [0] + [round(c * 30) - 2 for c in cuts[1:]] + [N]  # picture 2 frames ahead of the beat (the exemplar led by 1.7 at 24 fps)
    pid = agent.create_silent("landscape", N, "remotion", "Vẻ đẹp Việt Nam", color="#000000")["id"]
    assets = {}
    for key in dict.fromkeys(k for k, _ in order):
        g = GRADED[key]
        r = m.editvideo_attach_media_result(g["task"], pid, rev(pid), "video", f"{g['source']} graded ({g['look']})", "evidence")
        assets[key] = r.get("asset", r).get("id")
    A_music = m.editvideo_import_media(pid, str(MUSIC), role="decoration", tags="Rafael Krux, Inspiring Teaser, CC BY 4.0", preserve_plan=True,
                                       base_revision=rev(pid))["asset"]["id"]
    t = agent.read(pid)["timeline"]
    base = {**t["shots"][0], "text": "", "role": "evidence", "effects": [], "motion": "hold", "fit": "cover", "focus_x": .5, "focus_y": .5, "playback_rate": 1}
    shots = []
    for i, (key, src) in enumerate(order):
        a, b = frames[i], frames[i + 1]
        g = GRADED[key]
        sh = {**base, "id": f"v{i:02d}", "start_frame": a, "end_frame": b, "asset_id": assets[key], "source_start": round(src - g["start"], 3)}
        if key in ("hn_day", "hn_dusk", "hn_sunset", "hcm_night"):
            # the aerial reel's logo sits bottom right: a held 1.25x zoom from the top left carries it out of the frame
            sh["effects"] = [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .25, "focus_x": .15, "focus_y": .1, "cut": True}}]
        shots.append(sh)
    shots[0]["effects"] = [{"name": "fade_in", "start_frame": 0, "end_frame": 33}]  # from black, as the exemplar opens
    for k in (1, 1 + len(ESTABLISH) + len(BURST_A)):  # the two whips: into the establishing aerials and into the first burst
        shots[k]["transition"] = {"name": "whip_left", "duration_frames": 5}  # shorter than the 9-frame flashes around it
    dz = len(order) - len(OUTRO) - len(NIGHT_B) - len(FLASH_3) - 1  # the long dissolve between two night shots (live: both move)
    shots[dz]["transition"] = {"name": "dissolve", "duration_frames": 38, "mode": "live"}
    last = shots[-1]
    last["effects"] = [*last.get("effects", []), {"name": "fade_out", "start_frame": 60, "end_frame": last["end_frame"] - last["start_frame"] - 8}]
    t["shots"], t["layers"] = shots, []
    t["audio_clips"] = [{"id": "music", "asset_id": A_music, "start_frame": 0, "end_frame": N, "source_start": 0, "volume": 1.0, "fade_in": 0, "fade_out": 1.5,
                         "duck_under_voice": False, "role": "music", "normalize": True}]
    t["design"] = {**t.get("design", {}), "typography": {
        "display": {"font_id": "notoserif", "size": 200, "weight": 250, "tracking": .12, "line_height": 1.1, "variation_axes": {"wdth": 62.5}},
        "headline": {"font_id": "notoserif", "size": 110, "weight": 250, "tracking": .1, "line_height": 1.1, "variation_axes": {"wdth": 62.5}},
        "label": {"font_id": "notoserif", "size": 40, "weight": 600, "tracking": .04, "line_height": 1.2},
        "caption": {"font_id": "notoserif", "size": 29, "weight": 500, "tracking": .06, "line_height": 1.2},
        "source": {"font_id": "notoserif", "size": 20, "weight": 500, "tracking": .18, "line_height": 1.3}}}  # a role sets the size
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "replace_timeline", "timeline": t}])
    bar = .1218  # 2.35:1 inside 16:9
    def T(id, text, a, b, y, h, role, track=None, color=CREAM):
        size = {"display": 200, "headline": 110, "label": 40, "caption": 29, "source": 20}[role]
        # a soft shadow wide for the size keeps cream type apart from pale water and sky (the audit measured 1.0-2.3:1)
        fx = [{"name": "fade_in", "start_frame": 0, "end_frame": 14}, {"name": "fade_out", "start_frame": b - a - 14, "end_frame": b - a - 1},
              {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": max(10, round(size * .2))}}]
        if track is not None:  # letters breathe apart as they appear
            fx.append({"name": "tracking", "start_frame": 0, "end_frame": b - a - 1, "easing": "linear", "params": {"amount": track, "from_em": track * .6}})
        return {"op": "upsert_layer", "layer": {"id": id, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": .1, "y": y, "width": .8,
                "height": h, "z": 960, "typography_role": role, "color": color, "data": {"align": "center"}, "effects": fx}}
    e0, e1 = frames[1], frames[3]  # the establishing credit sits over its first two aerials
    ops = [{"op": "upsert_layer", "layer": {"id": f"bar{k}", "kind": "shape", "start_frame": 0, "end_frame": N, "x": 0, "y": y, "width": 1, "height": bar,
                                             "z": 950, "color": "#000000", "data": {"shape": "rectangle", "corner_radius": 0}}} for k, y in ((0, 0), (1, 1 - bar))]
    ops += [T("t_small", "vẻ đẹp của", 54, frames[1] - 4, .335, .06, "label"),
            T("t_name", "VIỆT NAM", 84, frames[1] - 4, .39, .24, "display", .14),
            T("t_sub", "từ bình minh tới đêm", 120, frames[1] - 4, .635, .05, "caption"),
            T("c_small", "tư liệu mở từ", e0 + 16, e1 - 6, .36, .05, "caption"),  # the credit block enters as one
            T("c_name", "WIKIMEDIA COMMONS", e0 + 16, e1 - 6, .41, .13, "headline", .1),
            T("c_sub", "dựng lại bởi EditVideo Agent", e0 + 16, e1 - 6, .55, .05, "caption"),
            T("cr1", "TƯ LIỆU: WIKIMEDIA COMMONS (CC BY · CC BY-SA · CC0) — NHẠC: RAFAEL KRUX, INSPIRING TEASER (CC BY 4.0)",
              round(121.5 * 30), N - 6, .47, .045, "source", None, "#cfc3bb")]
    agent.patch(pid, rev(pid), ops)
    # -14 LUFS (the tiktok preset's target, YouTube's reference level too)
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "tiktok", "id": "master", "start_frame": 0, "end_frame": N})
    au = [(f["code"], f["level"]) for f in m.editvideo_audit_timeline(pid)["findings"]]
    print(json.dumps({"pid": pid, "shots": len(shots), "cuts_per_min": round((len(shots) - 1) / (N / 30 / 60), 1), "audit": au}, ensure_ascii=False))


if __name__ == "__main__":
    build()
