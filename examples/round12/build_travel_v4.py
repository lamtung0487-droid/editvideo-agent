"""Round-12 learning test, the remake after two independent reviews: the same blueprint and cut plan as
build_travel_v2.py, with every window chosen by the system's senses instead of by hand.

The v3 review found three things a viewer sees first and the blueprint did not measure: the same five people four
times each in 25 s (61 % of shots nearly repeated another, the exemplar 9 %), judder from 24/25/50 fps clips on the
30 fps timeline (264 repeated frames), and a soft-drink sign on screen for 3.6 s. Here, slot by slot in film order:
- look: the window is graded by editvideo.look (A or B only);
- variety: its middle frame may not correlate above .85 with any shot already chosen (review._thumb, the measure
  behind audit_timeline's repeated_picture and learnkit's repeat_share), no clip twice in a row, at most two visits of
  a clip in 20 s, windows of one clip 2 s apart;
- brands: windows where find_subjects (OWLv2) sees "a brand logo" or "a soft drink advertisement sign" are skipped;
- cadence: shots from off-cadence sources play with frame_sampling "flow" (motion-interpolated to 30 fps);
- colour: saturation lifted per shot toward the exemplar's day level (.30), dusk darkened (the exemplar drops from 95
  to 72 in mean level at dusk), night left alone;
- the credits sit on black after the last shot fades, centred, at 26 px.
Usage: python examples/round12/build_travel_v4.py"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
from editvideo import mcp_server as m, store, agent, music, look, semantic
from editvideo.review import _thumb
from editvideo.code_engine import _fps, off_cadence
store.initialize(recover=False)
MUSIC = ROOT / "data" / "sources" / "commons" / "vn-music-Rafael_Krux_-_Inspiring_Teaser_cc-by_filmmusic_.mp3"
GRADED = json.loads((ROOT / "data" / "tmp" / "r12_graded_px.json").read_text(encoding="utf-8"))
M0, M1 = 8.47, 98.43
N = round((M1 - M0) * 30)
CREAM = "#ecd4c8"
rev = lambda pid: m.editvideo_read_project(pid)["revision"]
P = lambda k: GRADED[k]["path"]

DAY = ["35127612", "38178503", "35589587", "7417616", "3784667", "37887206"]
PEOPLE = ["27134197", "16051693", "15692758", "10388295", "7217096", "27102711", "15809400"]
DUSK = ["40134771", "12690271", "36670222", "38224338"]
NIGHT = ["15843973", "13380372", "15245736", "13514070", "30356704"]  # 39637165: a soft-drink sign in every frame
# section, number of slots, pools in order of preference, fixed (clip, second) where the shot is chosen by eye
PLAN = [("cold", 1, [], [("37887206", 10.0)]), ("establish", 4, [DAY], None), ("burst", 9, [PEOPLE, DAY], None),
        ("flash", 8, [PEOPLE + ["27275713"], DAY, NIGHT], None),  # out of fresh people, a flash previews the night
        ("breath", 1, [], [("3784667", 20.0)]), ("hero", 1, [], [("27102711", 4.3)]),
        ("burst", 3, [PEOPLE, DAY], None), ("dusk", 5, [DUSK], None),  # four dusk clips carry five shots: none spent earlier
        ("night", 5, [NIGHT], None), ("night_last", 1, [NIGHT], None),
        ("outro", 1, [], [("39750916", 20.0)])]


def cut_plan(db):
    """Shot starts (film seconds), section by section: build_travel_v2's bars with fewer people shots (8 people clips
    could not carry 25 without near-repeats) and fewer dusk shots (four mostly still cameras)."""
    t = [db[7]]                                    # cold open, title over it
    t += [db[i] for i in range(13, 21, 2)]         # establishing: 4 shots of 2 bars
    t += [db[i] for i in range(21, 30)]            # burst A: 9 shots of 1 bar
    t += [db[30] + (db[32] - db[30]) * k / 8 for k in range(8)]  # 8 half-beat flashes into the quiet before the lift
    t += [db[32], db[34]]                          # the breath, then the portrait on the lift (bar 34)
    t += [db[37], db[39], db[41]]                  # burst B: 3 shots of 2 bars (the last runs 3)
    t += [db[i] for i in range(44, 57, 3)]         # dusk: 5 shots of 3 bars
    t += [db[i] for i in range(59, 77, 3)]         # night: 6 shots of 3 bars
    t += [db[77]]                                  # the outro to the drop
    return [x - M0 for x in t]


def brands():
    """Spans (source seconds) where OWLv2 sees a logo or an advertisement sign, per clip (cached by semantic.detect)."""
    keys = sorted({k for _, _, pools, _ in PLAN for pool in pools for k in pool})
    r = semantic.detect([P(k) for k in keys], ["a brand logo", "a soft drink advertisement sign"], fps=1, threshold=.15)
    out = {}
    for k in keys:
        per = r["clips"].get(P(k)) or next((v for c, v in r["clips"].items() if Path(c).resolve() == Path(P(k)).resolve()), {})
        out[k] = [s for q in per.values() for s in (q.get("spans") or [])]
    return out


def choose(lengths, starts):
    """Each slot's (clip, second) in film order; lengths in seconds (with the dissolve's extra frames), starts the
    slots' film seconds."""
    from editvideo.media import probe
    banned, picked, thumbs, uses = brands(), [], [], {}
    fixed_at = [f[j] if f else None for _, n, _, f in PLAN for j in range(n)]
    # shots chosen by eye are known before the picker runs: an earlier slot must not repeat them either
    thumbs = [_thumb(P(f[0]), round(f[1] + lengths[x] / 2, 1)) for x, f in enumerate(fixed_at) if f]
    i = 0
    for section, n, pools, fixed in PLAN:
        for j in range(n):
            need = lengths[i]
            if fixed:
                k, s = fixed[j]
            else:
                best, fallback = None, None
                for pool in pools:
                    for k in sorted(pool, key=lambda c: (len(uses.get(c, [])), pool.index(c))):
                        if (picked and picked[-1][0] == k) or (i + 1 < len(fixed_at) and (fixed_at[i + 1] or [None])[0] == k):
                            continue  # never one clip on both sides of a cut
                        mine = uses.get(k, [])
                        if sum(1 for at, _ in mine if starts[i] - starts[at] < 20) >= 2:
                            continue  # two visits of this clip in the last 20 s
                        dur = float(probe(P(k))["format"]["duration"])
                        for s in np.arange(.5, dur - need - .3, 1.0):
                            s = round(float(s), 2)
                            if any(s < s2 + n2 + 2 and s2 < s + need + 2 for _, (s2, n2) in mine):
                                continue  # windows of one clip at least 2 s apart
                            if any(a <= s + need and s <= b for a, b in banned.get(k, [])):
                                continue
                            th = _thumb(P(k), round(s + need / 2, 1))
                            if th is None:
                                continue
                            corr = max((float(th @ t2) for t2 in thumbs), default=-1)
                            if corr > .85 and fallback and corr >= fallback[0]:  # the threshold repeat_share and repeated_picture count
                                continue
                            g = look.measure(P(k), s, s + max(need, 1.0))
                            if g["grade"] == "C":
                                continue
                            if corr > .85:  # the least repeated window, if nothing fresh is left
                                fallback = (corr, k, s)
                                continue
                            best = (k, s, th, g)
                            break
                        if best:
                            break
                    if best:
                        break
                if not best and not fallback:
                    raise RuntimeError(f"no window for slot {i} ({section})")
                if not best:
                    print(f"slot {i} ({section}): nothing fresh left, {fallback[1]} at {fallback[2]} s repeats at r={fallback[0]:.2f}", flush=True)
                k, s = best[:2] if best else fallback[1:]
            picked.append((k, s))
            if not fixed:
                thumbs.append(_thumb(P(k), round(s + need / 2, 1)))
            uses.setdefault(k, []).append((i, (s, need)))
            i += 1
    return picked


def build():
    db = music.structure(str(MUSIC))["downbeats"]
    cuts = cut_plan(db)
    frames = [0] + [round(c * 30) - 2 for c in cuts[1:]] + [N]
    # the shot before the last night shot plays on under the live dissolve: 30 frames more source
    lengths = [(frames[i + 1] - frames[i] + (30 if i == len(frames) - 4 else 0)) / 30 for i in range(len(frames) - 1)]
    order = choose(lengths, [f / 30 for f in frames[:-1]])
    assert len(order) == len(cuts), (len(order), len(cuts))
    sections = [sec for sec, n, _, _ in PLAN for _ in range(n)]
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
    shots = []
    for i, (k, s) in enumerate(order):
        sh = {**base, "id": f"v{i:02d}", "start_frame": frames[i], "end_frame": frames[i + 1], "asset_id": assets[k], "source_start": s}
        if off_cadence(_fps(P(k))):
            sh["frame_sampling"] = "flow"  # 24/25/50 fps: interpolated to the timeline instead of repeating frames
        span = frames[i + 1] - frames[i]
        sat = look.measure(P(k), s, s + max(1.0, span / 30))["saturation"]
        if sections[i] not in ("dusk", "night", "night_last", "outro"):
            amount = round(min(1.35, max(1.0, .30 / max(sat, .05))), 2)  # toward the exemplar's day saturation, never past 1.35
        elif sections[i] == "dusk":
            amount = round(min(1.2, max(1.0, .28 / max(sat, .05))), 2)
        else:
            amount = 1.0
        fx = [{"name": "saturate", "start_frame": 0, "end_frame": span, "params": {"amount": amount}}] if amount > 1.0 else []
        if sections[i] == "dusk":  # the light falls: the exemplar's level drops from day to dusk
            fx.append({"name": "brightness", "start_frame": 0, "end_frame": span, "params": {"amount": .88}})
        sh["effects"] = fx
        shots.append(sh)
    shots[0]["effects"].append({"name": "fade_in", "start_frame": 0, "end_frame": 33})
    for k, d in ((1, 5), (1 + 4 + 9, 3)):  # into the aerials, into the flashes
        shots[k]["transition"] = {"name": "whip_left", "duration_frames": d}
    shots[-2]["transition"] = {"name": "dissolve", "duration_frames": 30, "mode": "live"}
    last = shots[-1]
    last["effects"] = [{"name": "fade_out", "start_frame": 15, "end_frame": 80}]  # black from here: the credits' card
    t["shots"], t["layers"] = shots, []
    t["audio_clips"] = [{"id": "music", "asset_id": A_music, "start_frame": 0, "end_frame": N, "source_start": M0, "volume": 1.0, "fade_in": .3,
                         "fade_out": 2.5, "duck_under_voice": False, "role": "music", "normalize": True}]
    t["design"] = {**t.get("design", {}), "typography": {
        "display": {"font_id": "notoserif", "size": 200, "weight": 250, "tracking": .12, "line_height": 1.1, "variation_axes": {"wdth": 62.5}},
        "label": {"font_id": "notoserif", "size": 40, "weight": 600, "tracking": .04, "line_height": 1.2},
        "caption": {"font_id": "notoserif", "size": 29, "weight": 500, "tracking": .06, "line_height": 1.2},
        "source": {"font_id": "notoserif", "size": 26, "weight": 500, "tracking": .1, "line_height": 1.5}}}
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "replace_timeline", "timeline": t}])
    bar = .1218

    def T(id, text, a, b, y, h, role, track=None, color=CREAM):
        size = {"display": 200, "label": 40, "caption": 29, "source": 26}[role]
        fx = [{"name": "fade_in", "start_frame": 0, "end_frame": 14}, {"name": "fade_out", "start_frame": b - a - 14, "end_frame": b - a - 1},
              {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": max(10, round(size * .2))}}]
        if track is not None:
            fx.append({"name": "tracking", "start_frame": 0, "end_frame": b - a - 1, "easing": "linear", "params": {"amount": track, "from_em": track * .6}})
        return {"op": "upsert_layer", "layer": {"id": id, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": .08, "y": y, "width": .84,
                "height": h, "z": 960, "typography_role": role, "color": color, "data": {"align": "center"}, "effects": fx}}
    # the makers of the clips actually used, in order of first appearance (Pexels API records in r12_pexels.json)
    rec = {str(r[0]): r[6] for r in json.loads((Path(__file__).parent / "pexels_clips.json").read_text(encoding="utf-8"))}
    names = list(dict.fromkeys(rec[k] for k, _ in order))
    third = -(-len(names) // 3)  # three lines of names (two at 26 px had wrapped)
    o0 = frames[-2]
    ops = [{"op": "upsert_layer", "layer": {"id": f"bar{k}", "kind": "shape", "start_frame": 0, "end_frame": N, "x": 0, "y": y, "width": 1, "height": bar,
                                             "z": 950, "color": "#000000", "data": {"shape": "rectangle", "corner_radius": 0}}} for k, y in ((0, 0), (1, 1 - bar))]
    ops += [T("t_small", "vẻ đẹp của", 40, frames[1] - 4, .335, .06, "label"),
            T("t_name", "VIỆT NAM", 66, frames[1] - 4, .39, .24, "display", .14),
            T("t_sub", "từ bình minh tới đêm", 96, frames[1] - 4, .635, .05, "caption"),
            T("cr1", " · ".join(names[:third]), o0 + 70, N - 4, .37, .045, "source", None, "#d9cfc8"),
            T("cr2", " · ".join(names[third:2 * third]), o0 + 70, N - 4, .42, .045, "source", None, "#d9cfc8"),
            T("cr3", " · ".join(names[2 * third:]) + "  —  Pexels", o0 + 70, N - 4, .47, .045, "source", None, "#d9cfc8"),
            T("cr4", "Nhạc: Rafael Krux, Inspiring Teaser (CC BY 4.0)", o0 + 70, N - 4, .55, .045, "source", None, "#d9cfc8")]
    agent.patch(pid, rev(pid), ops)
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "tiktok", "id": "master", "start_frame": 0, "end_frame": N})
    au = [(f["code"], f["level"]) for f in m.editvideo_audit_timeline(pid)["findings"]]
    print(json.dumps({"pid": pid, "frames": N, "shots": len(shots), "order": order, "audit": au}, ensure_ascii=False))


if __name__ == "__main__":
    build()
