"""Round-10 build V: a vertical rally VELOCITY edit from seven Wikimedia Commons clips (Rali Ceredigion 2024 by
WillFR130, CC BY 4.0; Monte-Carlo Rally clips by Iain Cameron, CC BY 2.0) cut to a CC0 130 BPM track (SRG774,
OpenGameArt). reframe_footage follows each car into 9:16, the windows are chosen on a contact sheet of the reframed clips
(rank_clips supplies motion directions),
cuts land on beats, the hero play ramps slow around its peak on the drop, accent_sync stacks the impact there, the
edit ends on a freeze frame. Usage: python examples/round10/build_velocity.py [reframe|all]"""
import glob, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, clips, music, accents
store.initialize(recover=False)
C = ROOT / "data" / "sources" / "commons"
SRC = sorted(glob.glob(str(C / "rally-*.webm")))
MUSIC = ROOT / "data" / "sources" / "other" / "music-High-Energy_Adventure_Theme.ogg"
STATE = ROOT / "data" / "films" / "r10-velocity.json"
N = 600  # 20 s
rev = lambda pid: m.editvideo_read_project(pid)["revision"]


def media_task(submit, request):
    task = submit(request)
    while True:
        r = m.editvideo_get_media_task(task["id"])
        if r["state"] in ("completed", "failed", "cancelled", "interrupted"):
            assert r["state"] == "completed", r.get("error")
            return r
        time.sleep(3)


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s))


def reframe_all(s):
    """Each clip once into 9:16, the crop following the moving car (saliency + motion)."""
    s.setdefault("reframe", {})
    for src in SRC:
        if src not in s["reframe"]:
            r = media_task(m.editvideo_reframe_footage, {"path": src, "aspect": "9:16", "dead_zone": .08, "smoothing_seconds": .5})
            s["reframe"][src] = r["id"]
            save(s)
            print("reframed", Path(src).name, r["result"]["report"].get("camera_moving_fraction"), flush=True)
    return s


def plan_music():
    st = music.structure(str(MUSIC))
    peaks = [x for x in st["sections"] if x["label"] == "peak" and (x.get("entry_step_db") or 0) >= 3]
    drop = peaks[0]["start"] if peaks else st["phrases_8"][1]
    start = max(0.0, drop - 8.0)  # the drop lands 8 s into the edit, after the build
    return st, drop, start


def build(s):
    st, drop, m0 = plan_music()
    print("music", st["bpm"], "bpm drop at", drop, "excerpt from", m0, flush=True)
    pid = agent.create_silent("vertical", N, "remotion", "Rally velocity")["id"]
    s["pid"] = pid
    save(s)
    A = {}
    vid = {src: str(Path(m.editvideo_get_media_task(t)["result"]["video"]).resolve()) for src, t in s["reframe"].items()}
    for src, task in s["reframe"].items():
        A["rf-" + Path(src).stem] = m.editvideo_attach_media_result(task, pid, rev(pid), "video", "rf-" + Path(src).stem, "evidence")["asset"]["id"]
        # the original too: its engine sound becomes foley under the music (the reframed file keeps the timing)
        A["src-" + Path(src).stem] = m.editvideo_import_media(pid, src, role="evidence", tags="source sound", preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
    A["music"] = m.editvideo_import_media(pid, str(MUSIC), role="decoration", tags="SRG774 High-Energy Adventure Theme, CC0",
                                          preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
    key = {v: Path(src).stem for src, v in vid.items()}
    stem = lambda part: next(Path(src).stem for src in vid if part in src)
    path_of = {Path(src).stem: v for src, v in vid.items()}
    # rank_clips measures movement, direction and peaks; its strongest "action" in the Loeb clip was a spectator's hand
    # before the car arrived, so the shots below were chosen by looking at the reframed clips (a 0.5 s contact sheet):
    # the car is in frame where these windows start. rank_clips still gives each shot its motion direction (whips).
    ranked = clips.rank(list(vid.values()), 2.0, 40, False)["windows"]
    direction = lambda st_, t_: next((w["direction_deg"] for w in ranked if key[w["path"]] == st_ and w["start"] <= t_ < w["end"]), 180.0)
    BUILD = [("Moch_6", .4), ("Moch_1", 4.6), ("Moch_3", 10.4), ("Moch_2", 8.0), ("Guillaume", 2.0), ("Latvala", 5.2), ("Moch_6", 2.4),
             ("Moch_2", 9.9), ("Moch_1", 6.6)]  # wides first, the cars growing toward the drop
    AFTER = [("Guillaume", .1), ("Moch_2", 9.6), ("Moch_6", .9)]  # real time, engine sound under the music
    HERO, HERO_PEAK, FREEZE_AT = "Loeb", 3.2, 3.3  # the car mid-drift in the hairpin
    hero_stem = stem(HERO)
    # the hero play: real time as the car enters, 0.3x through the hairpin, back to speed (an S-curve ramp, flow-interpolated)
    ramp_s, hold_s, slow = .3, .7, .3
    ramp_req = {"path": path_of[hero_stem], "start": 2.3, "end": 4.5, "speed": 1.0, "peaks": [HERO_PEAK],
                "peak_speed": slow, "ramp_s": ramp_s, "hold_s": hold_s, "motion_blur": .4, "interpolation": "flow"}
    if s.get("ramp_req") != ramp_req:
        s.update(ramp_req=ramp_req, ramp=media_task(m.editvideo_retime_footage, ramp_req)["id"])
        save(s)
    A["hero-ramp"] = m.editvideo_attach_media_result(s["ramp"], pid, rev(pid), "video", "hero-ramp", "evidence")["asset"]["id"]
    ramp_in = (HERO_PEAK - ramp_req["start"]) - hold_s / 2 - ramp_s  # output seconds before the slowdown starts (real time until then)
    beats = [round((b - m0) * 30) for b in st["beats"] if 0 <= b - m0 < N / 30]
    downs = [round((b - m0) * 30) for b in st["downbeats"] if 0 <= b - m0 < N / 30]
    drop_f = round((drop - m0) * 30)
    bar = downs[1] - downs[0] if len(downs) > 1 else 56
    # cut grid: half bars in the build, the hero for two bars from the drop, bars after, a freeze to end
    cuts = sorted({0, *[f for f in downs if f < drop_f], *[f + bar // 2 for f in downs if f + bar // 2 < drop_f], drop_f,
                   *[f for f in downs if drop_f + 2 * bar - 3 <= f < N - 75 - 20], N - 75, N})  # no sliver before the freeze
    t = agent.read(pid)["timeline"]
    base = {**t["shots"][0], "fit": "cover", "text": "", "motion": "hold", "role": "evidence", "focus_x": .5, "focus_y": .5, "effects": []}
    shots, audio = [], []
    build_q, after_q = list(BUILD), list(AFTER)
    for a, b in zip(cuts, cuts[1:]):
        n = b - a
        if a == drop_f:  # the ramped hero clip: the car enters just after the drop, the slowdown follows
            name, src0, fast, dirn = "hero-ramp", max(0.0, ramp_in - .1), 1, direction(hero_stem, HERO_PEAK)
        else:
            if a == N - 75:  # the end: the hero again, frozen mid-drift 12 frames in
                st_, src0, fast = hero_stem, FREEZE_AT - 12 / 30, 1
            elif a < drop_f:
                part, src0 = build_q.pop(0)
                st_, fast = stem(part), (1 if part == "Latvala" else 2)  # velocity: fast in the build (the Latvala pass is only 1 s)
            else:
                part, src0 = after_q.pop(0)
                st_, fast = stem(part), 1
            name, dirn = "rf-" + st_, direction(st_, src0)
            dur = store.find_asset(pid, A[name])["duration"]
            assert src0 + n * fast / 30 <= dur + .01, (name, src0, n, fast, dur)
            if fast == 1:  # real-time shots carry their own engine sound (foley under the music)
                audio.append({"id": f"eng{len(audio)}", "asset_id": A["src-" + st_], "start_frame": a, "end_frame": b, "source_start": round(src0, 3),
                              "volume": .55, "fade_in": .03, "fade_out": .08, "duck_under_voice": False, "role": "foley", "normalize": True})
        sh = {**base, "id": f"s{len(shots):02d}", "start_frame": a, "end_frame": b, "asset_id": A[name], "source_start": round(src0, 3), "playback_rate": fast}
        if shots and a not in (drop_f, N - 75) and len(shots) % 3 == 2:  # a whip every third cut, in the motion's direction
            sh["transition"] = {"name": "whip_left" if abs(dirn) > 90 else "whip_right", "duration_frames": 8}
        shots.append(sh)
    t["shots"], t["layers"] = shots, []
    t["audio_clips"] = [{"id": "music", "asset_id": A["music"], "start_frame": 0, "end_frame": N, "source_start": round(m0, 3), "volume": 1.0,
                         "fade_in": .05, "fade_out": 1.0, "duck_under_voice": False, "role": "music", "normalize": True}, *audio]
    agent.patch(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    # the end: freeze the hero mid-action with its name
    agent.patch(pid, rev(pid), [{"op": "freeze_frame", "at": N - 75 + 12, "frames": 50, "zoom": .1, "focus_x": .5, "focus_y": .55}])
    from editvideo.design_library import fit_size
    T = lambda id, text, a, b, y, size, color="#ffffff", **kw: {"op": "upsert_layer", "layer": {
        "id": id, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": .08, "y": y, "width": .84, "height": .12, "z": 900,
        "font_id": "oswald", "font_weight": 700, "font_size": fit_size("oswald", text, .84, 1080, 700, size), "line_height": 1.2, "color": color,
        "effects": [{"name": "text_outline", "start_frame": 0, "end_frame": b - a - 1, "params": {"color": "#000000", "amount": 5}},
                    {"name": "fade_in", "start_frame": 0, "end_frame": 5}, {"name": "fade_out", "start_frame": b - a - 7, "end_frame": b - a - 1}], **kw}}
    agent.patch(pid, rev(pid), [
        T("title", "RALLY", 0, cuts[2] - 2, .13, 190),
        T("title2", "MONTE-CARLO · CEREDIGION", 4, cuts[2] - 2, .25, 56, "#ffd400"),
        T("name", "FULL SEND.", N - 75 + 14, N, .14, 150, "#ffd400"),
        # credits on two short lines, long enough to read
        T("credit", "Video: WillFR130 (CC BY 4.0) · Iain Cameron (CC BY 2.0)", N - 165, N, .68, 36),
        T("credit2", "Nhạc: SRG774 (CC0)", N - 160, N, .72, 36),
    ])
    agent.patch(pid, rev(pid), [{"op": "apply_combo", "target": "title", "combo": "impact_title", "start_frame": 0, "end_frame": 14},
                                {"op": "apply_combo", "target": "name", "combo": "impact_title", "start_frame": 0, "end_frame": 14}])
    r = accents.sync(pid, rev(pid), {"style": "velocity", "drops": [drop]})  # music-file seconds
    print("accents", r["counts"], r["drops"], flush=True)
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "tiktok", "id": "master", "start_frame": 0, "end_frame": N})
    au = [(f["code"], f["level"]) for f in m.editvideo_audit_timeline(pid)["findings"]]
    print(json.dumps({"pid": pid, "cuts": cuts, "drop_frame": drop_f, "audit": au}, ensure_ascii=False))


if __name__ == "__main__":
    s = reframe_all(load())
    if "reframe" not in sys.argv[1:]:
        build(s)
