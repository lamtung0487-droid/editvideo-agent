"""Round-9 real build A: a vertical TikTok talking-head short cut from NASA's Artemis interview soundbites (public
domain): the speaker's most surprising line as a cold open, pauses condensed, the 16:9 interview reframed to 9:16 on
the speaker's face, word-by-word pop captions from the measured words, SLS launch B-roll on the line about the
rocket, a 124 BPM bed under the voice, a CTA, mastered to -14 LUFS. Usage: python examples/round9/build_talking_head.py"""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, perception, dialogue, sound
store.initialize(recover=False)
NS = ROOT / "data" / "sources" / "nasa"
SRC = NS / "artemis_interview_soundbites.mp4"
STATE = ROOT / "data" / "films" / "r9-talking-head.json"
W0, W1 = 112.0, 161.0  # Jim Bridenstine (NASA Administrator) on the lunar south pole, water ice and SLS
REFRAME = {"path": str(SRC), "start": W0, "end": W1, "aspect": "9:16", "auto_focus": "faces", "dead_zone": .12, "smoothing_seconds": 1.0}
# Selects in source seconds (from the transcript), in the order of the short: the surprising line opens it.
SELECTS = [(133.0, 139.6),   # "Water ice, of course, is life support... but it's also rocket fuel."
           (114.7, 128.2),   # "...almost permanent sunlight on the south pole... water ice resides in mass volumes."
           (146.6, 159.4)]   # "It's the same rocket fuel that will power the space launch system... the south pole of the moon."
rev = lambda pid: m.editvideo_read_project(pid)["revision"]
# The Vietnamese line under the English words (written for this short; anchors are the English phrase it starts at).
TRANSLATIONS = [("water ice", "Băng nước, dĩ nhiên, là nguồn sống."), ("it's water to drink", "Là nước để uống, không khí để thở,"),
                ("but it's also", "nhưng còn là nhiên liệu tên lửa."),  # anchors avoid words ASR may add or drop ("also a rocket")
                ("opportunities to have", "Ở cực nam Mặt Trăng có nơi gần như luôn có nắng,"), ("which means", "nghĩa là có năng lượng, có điện."),
                ("also on the south pole", "Cực nam cũng là nơi có rất nhiều băng nước."),
                ("it's the same rocket fuel", "Chính nhiên liệu ấy sẽ đẩy tên lửa SLS,"), ("which is going to be the largest", "tên lửa lớn nhất, mạnh nhất từng được phóng,"),
                ("and it's going to be the rocket", "sẽ đưa phi hành gia trở lại Mặt Trăng,"), ("in fact", "chính xác là cực nam Mặt Trăng.")]


def media_task(submit, request):
    task = submit(request)
    while True:
        r = m.editvideo_get_media_task(task["id"])
        if r["state"] in ("completed", "failed", "cancelled", "interrupted"):
            assert r["state"] == "completed", r.get("error")
            return r
        time.sleep(3)


def state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s))


def build():
    s = state()
    if s.get("reframe_req") != {**REFRAME, "_v": 2}:  # 1. face-following 9:16 crop with its sound (v2: eye check, no-jump guard)
        s.update(reframe_req={**REFRAME, "_v": 2}, reframe=media_task(m.editvideo_reframe_footage, REFRAME)["id"], pid=None, transcript=None)
        save(s)
    rf = m.editvideo_get_media_task(s["reframe"])["result"]
    clip = rf["video"]
    print("reframe:", {k: rf["report"].get(k) for k in ("focus_source", "face_frames_fraction", "camera_moving_fraction", "crop")})
    if not s.get("transcript"):  # 2. measured words of the reframed clip (Whisper small, offline)
        s["transcript"] = perception.transcribe(clip, "small", "en", False, "Artemis, NASA, Moon, SLS, space launch system")["manifest"]
        save(s)
    if not s.get("pid") or s.get("selects") != [list(x) for x in SELECTS] or s.get("condense_v") != 6:  # 3. selects in order, pauses condensed, words carried into the cut
        # No jump-cut cover here: punch_in below alternates in/out at phrase starts (two punches would multiply the
        # zoom on a 720p source already enlarged 2.7x).
        r = dialogue.condense(clip, max_pause_s=.45, target_pause_s=.22, remove_fillers=True, cover="none",
                              profile="vertical", title="Nước trên Mặt Trăng", dry_run=False,
                              windows=[[a - W0, b - W0] for a, b in SELECTS], transcript=s["transcript"])
        s.update(pid=r["project_id"], selects=[list(x) for x in SELECTS], frames=r["frames"], punched=False, condense_v=6)
        save(s)
        print("condense:", {k: r.get(k) for k in ("kept_s", "removed_s", "cuts", "captions_timing")})
    return s


def fit_size(lines, width=.84, start=84, font="archivo", weight=700):
    """Largest size (<= start) at which every line fits the width on one line (measured on the bundled font)."""
    from editvideo.design_library import fit_width
    size = start
    while size > 30 and any(fit_width(font, ln, size, 1080, weight) > width for ln in lines):  # 24 px layer padding
        size -= 2
    return size


def words_of(pid):
    return store.read_json(store.folder(pid) / "plan/words.json")["words"]


def compose(s):
    pid = s["pid"]
    if not (agent.read(pid)["timeline"].get("design") or {}).get("typography"):
        m.editvideo_apply_design(pid, rev(pid), {"style_id": "short_bold"})  # bold condensed headings for a phone screen
    t = agent.read(pid)["timeline"]
    N = t["total_frames"]
    words = words_of(pid)
    A = {a["name"]: a["id"] for a in store.assets(pid)}
    if "launch_tracking.mp4" not in A:
        A["launch_tracking.mp4"] = m.editvideo_import_media(pid, str(NS / "launch_tracking.mp4"), role="evidence", tags="NASA Artemis I launch tracking (SLS)",
                                                            preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
    # B-roll: the SLS launch over "space launch system ... ever launched" (the line names the rocket on screen).
    w = [x["text"].lower().strip(".,") for x in words]
    a_i = next(i for i, x in enumerate(w) if x == "space")
    b_i = next(i for i, x in enumerate(w) if x.startswith("launched"))
    b0, b1 = int(words[a_i]["start"] * 30) - 3, int(words[b_i]["end"] * 30) + 6
    hook_end = next(x["start_frame"] for x in t["shots"] if not x["id"].startswith("seg-001"))  # the whole opening select (punch_in splits it)
    # The face fills the upper half of the 9:16 crop (eyes from y ~.26): titles stay on the hair line above them, each
    # line on one line at a measured size (the display role's 112 px wrapped the hook to 4 lines over the eyes; a role
    # sets the size and overrides font_size, so these layers set font_id/font_size themselves).
    hook_lines = ["NƯỚC TRÊN MẶT TRĂNG", "= NHIÊN LIỆU TÊN LỬA"]
    hook_size, cta_size = fit_size(hook_lines), fit_size(["THEO DÕI ĐỂ XEM PHẦN 2"])
    layers = [
        {"id": "hook", "kind": "text", "text": "\n".join(hook_lines), "start_frame": 0, "end_frame": hook_end,  # on frame 0: the feed's thumbnail
         "x": .08, "y": .125, "width": .84, "height": .11, "z": 900, "font_id": "archivo", "font_weight": 700, "font_size": hook_size, "color": "#ffffff", "line_height": 1.36,
         "effects": [{"name": "rise", "start_frame": 0, "end_frame": 6, "params": {"amount": 30}}, {"name": "text_outline", "start_frame": 0, "end_frame": hook_end - 3,
                                                                                                     "params": {"color": "#000000", "amount": 4}}]},
        {"id": "who", "kind": "text", "text": "Jim Bridenstine · Giám đốc NASA 2018–2021", "start_frame": hook_end + 4, "end_frame": hook_end + 100,
         "x": .08, "y": .135, "width": .7, "height": .05, "z": 900, "font_size": 34, "typography_role": "label", "color": "#ffd400",
         "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 6}, {"name": "fade_out", "start_frame": 88, "end_frame": 96},
                     {"name": "text_outline", "start_frame": 0, "end_frame": 95, "params": {"color": "#000000", "amount": 3}}]},
        # two angles of the launch, not one 5 s hold: on the pad at liftoff, then the climb
        {"id": "broll-sls", "kind": "video", "asset_id": A["launch_tracking.mp4"], "source_start": 43.0, "start_frame": b0, "end_frame": (b0 + b1) // 2,
         "x": 0, "y": 0, "width": 1, "height": 1, "z": 60, "fit": "cover"},
        {"id": "broll-sls2", "kind": "video", "asset_id": A["launch_tracking.mp4"], "source_start": 47.0, "start_frame": (b0 + b1) // 2, "end_frame": b1,
         "x": 0, "y": 0, "width": 1, "height": 1, "z": 60, "fit": "cover"},
        {"id": "cta", "kind": "text", "text": "THEO DÕI ĐỂ XEM PHẦN 2", "start_frame": N - 90, "end_frame": N,
         "x": .08, "y": .13, "width": .84, "height": .06, "z": 900, "font_id": "archivo", "font_weight": 700, "font_size": cta_size, "color": "#ffd400", "line_height": 1.36,
         "effects": [{"name": "rise", "start_frame": 0, "end_frame": 6, "params": {"amount": 24}}, {"name": "text_outline", "start_frame": 0, "end_frame": 89, "params": {"color": "#000000", "amount": 4}}]},
        {"id": "source", "kind": "text", "text": "Video: NASA (public domain)", "start_frame": N - 90, "end_frame": N, "x": .08, "y": .205, "width": .6, "height": .03,
         "z": 900, "font_size": 26, "typography_role": "source", "color": "#ffffff", "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 6},
                                                                                              {"name": "text_outline", "start_frame": 0, "end_frame": 89, "params": {"color": "#000000", "amount": 2}}]},
    ]
    p = agent.read(pid)
    ops = [{"op": "upsert_layer", "layer": l} for l in layers]
    agent.patch(pid, p["revision"], ops)
    # Talking heads in top short-form run ~0.2-0.5 cuts/s: alternate in/out punch cuts at phrase starts, >= 3 s apart
    # (once: punch_in splits the shots, so a rebuild starts from condense again).
    if not s.get("punched"):
        pr = m.editvideo_punch_in(pid, rev(pid), words=[{"word": x["text"], "start": x["start"], "end": x["end"]} for x in words], scale=1.12,
                                  anchor=[.5, .3], min_pause_s=.18, min_gap_s=3.0, ladder=True)
        s["punched"] = True
        save(s)
        print("punch:", {k: pr.get(k) for k in ("placed", "skipped")})
    # Captions: 1-3 words per page, the spoken word pops; key words in yellow; the Vietnamese line under them.
    norm = lambda x: "".join(ch for ch in x.lower() if ch.isalnum() or ch in " '")
    seq, tr, at = [norm(x["text"]) for x in words], [], 0
    for k, (anchor, line) in enumerate(TRANSLATIONS):
        n_ = len(anchor.split())
        hit = next((i for i in range(at, len(seq) - n_ + 1) if " ".join(seq[i:i + n_]) == anchor), None)
        if hit is None:
            print("translation anchor not found:", anchor)
            continue
        tr.append([hit, line])
        at = hit + n_
    translations = [{"start": words[i]["start"], "end": (words[tr[j + 1][0]]["start"] if j + 1 < len(tr) else words[-1]["end"] + .3), "text": line}
                    for j, (i, line) in enumerate(tr)]
    r = m.editvideo_compose_edit(pid, rev(pid), {"recipe": "word_captions", "platform": "tiktok", "id": "cap", "start_frame": 0, "end_frame": N,
                                                 "caption_style": "karaoke", "mode": "color", "accent": "#ffd400", "color": "#ffffff", "uppercase": True,
                                                 "emphasis": ["rocket", "fuel", "water", "moon", "power", "electricity", "largest", "powerful", "astronauts", "ice"],
                                                 "word_animation": "pop", "outline": .07, "font_size": 70, "caption_y": .62, "translations": translations})
    print("captions:", r.get("notes", [])[:1])
    # A 124 BPM bed under the voice (music role sits ~14 LU below dialogue), ducked.
    if "bed-124.wav" not in A:
        bed = sound.design("beat", round(N / 30 + 1, 2), 3, -12, 124)
        Path(bed["path"]).replace(Path(bed["path"]).with_name("bed-124.wav"))
        A["bed-124.wav"] = m.editvideo_import_media(pid, str(Path(bed["path"]).with_name("bed-124.wav")), role="decoration", tags="procedural beat bed 124 BPM",
                                                    preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
    agent.patch(pid, rev(pid), [{"op": "upsert_audio", "audio": {"id": "bed", "asset_id": A["bed-124.wav"], "start_frame": 0, "end_frame": N, "volume": .6,
                                                                  "fade_in": .3, "fade_out": .8, "duck_under_voice": True, "role": "music", "normalize": True}}])
    sfx = m.editvideo_sfx_sync(pid, rev(pid), {"replace": True}, dry_run=False)
    print("sfx:", {k: sfx.get(k) for k in ("placed", "accents")})
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "tiktok", "id": "master", "start_frame": 0, "end_frame": N})
    return pid


if __name__ == "__main__":
    s = build()
    pid = compose(s)
    a = m.editvideo_audit_timeline(pid)
    print("audit:", [(f["code"], f["level"]) for f in a["findings"]])
    print(json.dumps({"pid": pid, "frames": agent.read(pid)["timeline"]["total_frames"]}))
