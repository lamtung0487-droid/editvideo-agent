"""Round 9: short-form (TikTok / Reels / Shorts) — one platform table, the rendered-video audit, word motion in
captions, face-aware reframing, ordered talking-head selects with words carried through the cuts, the beat bed."""
import importlib.util
import json
import subprocess
from pathlib import Path
import numpy as np
import pytest
from editvideo import store
from editvideo.media import FFMPEG


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.initialize()
    return tmp_path


def test_one_platform_table_feeds_every_audit():
    from editvideo import platforms, review, aspect, ads
    assert review.SAFE["vertical"] == aspect.SAFE["vertical"] == platforms.ORGANIC_SAFE
    assert ads.PROFILES_UI is platforms.ORGANIC
    # the area clear on TikTok, Reels and Shorts ADS at once (published zones): x 120-888, y 288-1248 at 1080x1920
    assert platforms.safe_area("all", "ads") == (.1111, .15, .8222, .65)
    z = platforms.zones("tiktok", "ads")
    assert z["right_rail"][0] == pytest.approx(900 / 1080) and z["bottom"][1] == pytest.approx(1 - 660 / 1920)
    assert set(platforms.covered((.86, .6, .98, .7), "tiktok")) == {"right_rail"}
    assert platforms.covered((.2, .2, .7, .5), "tiktok") == {}
    from PIL import Image
    im = platforms.draw_ui(Image.new("RGB", (270, 480), (0, 0, 0)), "tiktok")
    px = np.asarray(im)
    assert im.size == (270, 480) and px[470, 135, 0] > px[470, 135, 2]  # the bottom block is tinted


def test_cut_detection_counts_hard_cuts_not_fades():
    from editvideo.shortform import cuts_of
    a, b = np.zeros((40, 54, 96, 3), np.uint8), np.zeros((40, 54, 96, 3), np.uint8)
    a[..., 2], b[..., 0] = 220, 220  # red then blue: one hard cut
    fade = np.stack([((1 - k / 39) * a[0] + k / 39 * b[0]).astype(np.uint8) for k in range(40)])  # a 40-frame dissolve
    cuts, _ = cuts_of(np.concatenate([a, b, fade[::-1]]))
    assert cuts == [40]


def _mp4(path, video, audio=None, seconds=4):
    cmd = [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", video]
    if audio:
        cmd += ["-f", "lavfi", "-i", audio]
    cmd += ["-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-ar", "48000"] if audio else []) + [str(path)]
    subprocess.run(cmd, check=True)
    return path


def test_shortform_audit_reads_the_encoded_file(workspace):
    from editvideo import shortform
    bad = _mp4(workspace / "bad.mp4", "color=c=black:s=720x1280:r=30:d=1[a];testsrc2=s=720x1100:r=30:d=3,pad=720:1280:0:90[b];[a][b]concat=n=2:v=1")
    r = shortform.audit(path=str(bad))
    codes = {f["code"] for f in r["findings"]}
    assert {"black_first_frame", "silent_video", "letterboxed"} <= codes
    assert all("evidence" in f["evidence"] for f in r["findings"] if f["code"] in ("black_first_frame", "silent_video"))
    good = _mp4(workspace / "good.mp4", "testsrc2=s=720x1280:r=30", "sine=f=330:sample_rate=48000,volume=0.6,loudnorm=I=-14:TP=-1.5")
    g = shortform.audit(path=str(good))
    gc = {f["code"] for f in g["findings"]}
    assert not gc & {"black_first_frame", "silent_video", "letterboxed", "not_native_vertical", "late_first_change", "delivery_spec"}
    assert abs(g["measurements"]["loudness"]["integrated_lufs"] + 14) < 1.6 and g["measurements"]["first_change_s"] <= .1
    assert Path(g["ui_sheet"]).is_file() and len(g["cover_candidates"]) == 3
    wide = _mp4(workspace / "wide.mp4", "testsrc2=s=640x360:r=30", seconds=2)
    assert "not_native_vertical" in {f["code"] for f in shortform.audit(path=str(wide))["findings"]}


def test_hook_audit_wants_a_first_change_by_one_second_not_an_event_quota(monkeypatch):
    from editvideo import agent, review
    def audit(layers, shots):
        t = {"width": 1080, "height": 1920, "total_frames": 600, "fps": 30, "cues": [], "design": {}, "shots": shots, "layers": layers}
        monkeypatch.setattr(agent, "read", lambda pid: {"revision": 1, "timeline": t})
        monkeypatch.setattr(store, "assets", lambda pid: [])
        return {f["code"]: f for f in review.audit_timeline("p")["findings"]}
    hook = {"id": "hook", "kind": "text", "text": "Nước là nhiên liệu", "start_frame": 12, "end_frame": 120, "x": .1, "y": .18, "width": .8, "height": .1}
    one = [{"id": "a", "start_frame": 0, "end_frame": 600, "motion": "hold"}]
    assert "sparse_open" not in audit([hook], one)  # one change at 0.4 s is enough
    assert "sparse_open" in audit([{**hook, "start_frame": 45}], one)
    fast = [{"id": f"s{i}", "start_frame": i * 30, "end_frame": i * 30 + 30, "motion": "hold"} for i in range(20)]
    assert audit([hook], fast)["fast_pace"]["evidence"]["cuts_per_s"] > .6  # a cut every second for 20 s


def test_map_words_follows_the_kept_ranges():
    from editvideo.dialogue import map_words
    words = [{"start": 1.0, "end": 1.3, "text": "a"}, {"start": 5.0, "end": 5.4, "text": "b"}, {"start": 9.0, "end": 9.5, "text": "c"}]
    tmap = [{"src": [8.8, 9.8], "frames": [0, 30]}, {"src": [0.9, 1.5], "frames": [30, 48]}]  # c opens, then a; b is cut
    out = map_words(words, tmap)
    assert [w["text"] for w in out] == ["c", "a"]
    assert out[0]["start"] == pytest.approx(.2) and out[1]["start"] == pytest.approx(1 + .1)


def _mod(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_condense_keeps_ordered_windows_and_carries_words(workspace):
    from editvideo import dialogue, agent
    from editvideo.media import sha256
    wav = workspace / "s.wav"
    truth = _mod("synth_speech").make(str(wav), seed=2, hum=False)
    mp4 = workspace / "s.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s=320x180:r=30:d={truth['duration']:.3f}", "-i", str(wav),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(mp4)], check=True)
    regs = truth["regions"]
    late, early = regs[-2], regs[0]
    words = [{"start": r_["start"] + .05, "end": r_["end"] - .05, "text": f"w{i}"} for i, r_ in enumerate(regs)]
    tr = workspace / "transcript.json"
    tr.write_text(json.dumps({"source_sha256": sha256(mp4), "words": words}), encoding="utf-8")
    windows = [[late["start"] - .1, late["end"] + .1], [early["start"] - .1, early["end"] + .1]]
    r = dialogue.condense(str(mp4), dry_run=False, profile="vertical", windows=windows, transcript=str(tr), fill_room_tone=False)
    t = agent.read(r["project_id"])["timeline"]
    assert t["shots"][0]["source_start"] >= late["start"] - .11 and t["shots"][-1]["source_start"] < early["end"]  # the late line opens
    plan = store.read_json(store.folder(r["project_id"]) / "plan/words.json")
    assert [w["text"] for w in plan["words"]] == [f"w{len(regs) - 2}", "w0"] and t["cues"] and r["captions_timing"]["words"] == 2
    bad = workspace / "other.json"
    bad.write_text(json.dumps({"source_sha256": "0" * 64, "words": words}), encoding="utf-8")
    with pytest.raises(ValueError, match="another file"):
        dialogue.condense(str(mp4), dry_run=True, transcript=str(bad))


def test_face_focus_holds_the_main_face_and_ignores_small_boxes(monkeypatch):
    from editvideo import footage_pro
    seq = [[(.40, .2, .2, .3), (.45, .55, .05, .06)], [], [(.42, .2, .2, .3)], [(.10, .2, .1, .14), (.44, .21, .2, .3)]]
    monkeypatch.setattr(footage_pro, "detect_faces", lambda g: seq.pop(0) if seq else [])
    xs, ys, cs, boxes = footage_pro.face_focus([np.zeros((10, 10), np.uint8)] * 4, step=1)
    assert xs[0] == pytest.approx(.5) and xs[1] == pytest.approx(.5) and cs[1] == 1.0  # a missed frame holds the face
    assert xs[3] == pytest.approx(.54)  # the face nearest the last one, not a new small face elsewhere
    assert len(boxes) == 3


def test_beat_bed_has_the_tempo_it_reports(workspace):
    from editvideo import sound, music
    r = sound.design("beat", 12.0, 3, -12, 124)
    assert r["bpm"] == 124 and r["beat_times"][1] == pytest.approx(60 / 124, abs=1e-3)
    b = music.beats(r["path"], 0, None, None)
    assert abs(b["bpm"] - 124) < 2 and abs(b["beats"][1] - min(r["beat_times"], key=lambda x: abs(x - b["beats"][1]))) < .03


def test_short_form_toolkit_and_loud_master(workspace):
    from editvideo import professional
    k = professional.toolkit("tiktok", "")
    assert {"talking_head", "how_to", "listicle", "before_after", "pov", "product_demo"} <= set(k["short_form"]["templates"])
    assert k["short_form"]["safe_area"]["ads_all_platforms"] == (.1111, .15, .8222, .65)
    assert "short_form" not in professional.toolkit("youtube_long", "")
    assert professional.toolkit("reels", "listicle")["short_form"]["templates"].keys() == {"listicle"}


@pytest.mark.skipif(not (Path(__file__).parents[1] / "engines" / "node_modules").is_dir(), reason="Local rendering dependencies not installed")
def test_caption_word_pop_is_the_same_in_both_engines(tmp_path, monkeypatch):
    from PIL import Image
    from editvideo import agent
    from editvideo.code_engine import scaffold
    from editvideo.snapshot import snapshot
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    shots = {}
    for engine in ("remotion", "hyperframes"):
        pid = agent.create_silent("vertical", 40, engine, "caption pop")["id"]
        p = agent.read(pid)
        t = p["timeline"]
        t["shots"] = [{**t["shots"][0], "text": ""}]
        t["layers"] = [{"id": "cap", "kind": "caption", "start_frame": 0, "end_frame": 40, "x": .08, "y": .55, "width": .84, "height": .15, "z": 950,
                        "font_size": 90, "color": "#ffffff", "background": "transparent",
                        "data": {"pages": [{"start_frame": 0, "end_frame": 40, "words": [{"text": "POP", "start_frame": 10, "end_frame": 40}]}],
                                 "mode": "color", "active_color": "#ffd400", "active_background": "#ffd400", "animation": "pop", "outline": .06,
                                 "outline_color": "#000000", "future_opacity": 0}}]
        agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
        scaffold(pid, engine, False)
        shots[engine] = [np.asarray(Image.open(f["path"]).convert("RGB").resize((360, 640), Image.LANCZOS), np.int16)
                         for f in snapshot(pid, engine, [10, 30])["frames"]]  # the engines snapshot at different sizes
    for a, b in zip(shots["remotion"], shots["hyperframes"]):
        assert np.abs(a - b).mean() < 2.5  # same pixels from both engines
    yellow = [((im[..., 0] > 200) & (im[..., 1] > 170) & (im[..., 2] < 90)).sum() for im in shots["remotion"]]
    assert 0 < yellow[0] < .7 * yellow[1]  # on its onset frame the word is small (x0.78), then it lands full size
    dark = (shots["remotion"][1].sum(axis=2) < 60) & (np.arange(shots["remotion"][1].shape[0])[:, None] > shots["remotion"][1].shape[0] * .5)
    assert dark.sum() > 50  # the outline ring is drawn


@pytest.mark.skipif(not (Path(__file__).parents[1] / "engines" / "node_modules").is_dir(), reason="Local rendering dependencies not installed")
def test_video_layer_cover_fills_the_canvas_in_both_engines(tmp_path, monkeypatch):
    from PIL import Image
    from editvideo import agent
    from editvideo.code_engine import scaffold
    from editvideo.snapshot import snapshot
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    clip = _mp4(tmp_path / "blue.mp4", "color=c=0x0000ff:s=320x180:r=30", seconds=2)
    for engine in ("remotion", "hyperframes"):
        pid = agent.create_silent("vertical", 30, engine, "cover layer")["id"]
        aid = agent.import_media(pid, str(clip), "b-roll", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
        p = agent.read(pid)
        t = p["timeline"]
        t["shots"] = [{**t["shots"][0], "text": ""}]
        t["layers"] = [{"id": "broll", "kind": "video", "asset_id": aid, "source_start": 0, "start_frame": 0, "end_frame": 30,
                        "x": 0, "y": 0, "width": 1, "height": 1, "z": 60, "fit": "cover"}]
        agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
        scaffold(pid, engine, False)
        with Image.open(snapshot(pid, engine, [10])["frames"][0]["path"]) as im:
            im = im.convert("RGB")
            top = im.getpixel((im.width // 2, im.height // 10))
        assert top[2] > 200 and top[0] < 40, (engine, top)  # a 16:9 clip covering 9:16 fills the top too (contain would not)


def test_ink_box_follows_wrapped_lines_below_the_layer_box():
    from editvideo.shortform import ink_box
    img = np.zeros((960, 540, 3), np.uint8)
    for y in (120, 175, 230):  # three wrapped lines of white text under a layer box one line tall
        img[y:y + 30, 60:420] = 255
    img[800:830, 60:420] = 255  # a white shirt far below is not text
    box = ink_box(img, {"x": .1, "y": .12, "width": .8, "height": .04, "color": "#ffffff", "font_size": 60}, {})
    assert box[1] == pytest.approx(120 / 960, abs=.003) and box[3] == pytest.approx(260 / 960, abs=.003)
    assert box[0] == pytest.approx(60 / 540, abs=.003) and box[2] == pytest.approx(420 / 540, abs=.003)


def test_visual_cuts_count_punch_ins_but_not_motion():
    from editvideo.shortform import visual_cuts
    d = np.full(120, 1.0)
    d[40] = d[80] = 14  # two punch-ins: one-frame spikes
    d[95:110] = 20  # fast motion: high but steady
    assert visual_cuts(d, []) == [40, 80]


def test_plate_faces_map_through_cover_focus_and_punch(monkeypatch):
    from editvideo import shortform, footage_pro
    from PIL import Image
    monkeypatch.setattr(footage_pro, "detect_faces", lambda g: [(.4, .2, .2, .2)])
    monkeypatch.setattr(shortform, "_frame_at", lambda path, t, width=540: Image.new("RGB", (64, 36)))
    t = {"width": 1080, "height": 1920, "layers": [],
         "shots": [{"id": "a", "start_frame": 0, "end_frame": 60, "asset_id": "v", "fit": "cover", "focus_x": .5, "focus_y": .5, "source_start": 0,
                    "effects": [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.0, "focus_x": .5, "focus_y": .5, "cut": True}}]}]}
    assets = {"v": {"kind": "video", "path": "x.mp4", "width": 1920, "height": 1080}}
    (x, y, w, h), = shortform._plate_faces(t, assets, 10)
    # cover: 1920x1080 -> 3413x1920, centred (offset -1167); the face at x .4-.6 of the source is .1-.6 of... then x2 about the centre
    sx0 = -1166.67 + .4 * 3413.33
    assert x == pytest.approx((540 + (sx0 - 540) * 2) / 1080, abs=.002) and w == pytest.approx(.2 * 3413.33 * 2 / 1080, abs=.002)
    t["layers"] = [{"kind": "video", "start_frame": 0, "end_frame": 60, "width": 1, "height": 1}]
    assert shortform._plate_faces(t, assets, 10) == []  # full-frame B-roll hides the speaker


def test_short_form_master_leaves_headroom_for_aac(workspace):
    from editvideo import agent, professional
    pid = agent.create_silent("vertical", 60, "remotion", "master")["id"]
    r = professional.compose(pid, agent.read(pid)["revision"], {"recipe": "audio_finish", "platform": "tiktok", "start_frame": 0, "end_frame": 60}, dry_run=True)
    mix = next(o["audio_mix"] for o in r["operations"] if o["op"] == "set_audio_mix")
    assert mix["target_lufs"] == -14 and mix["true_peak_db"] == -2.0


def test_audit_predicts_wrapping_and_names_the_role_that_sets_the_size(monkeypatch):
    from editvideo import agent, review
    def audit(layer):
        t = {"width": 1080, "height": 1920, "total_frames": 300, "fps": 30, "cues": [], "shots": [{"id": "a", "start_frame": 0, "end_frame": 300, "motion": "hold"}],
             "design": {"typography": {"display": {"font_id": "archivo", "size": 112, "weight": 700, "line_height": 1.18, "tracking": -.02}}}, "layers": [layer]}
        monkeypatch.setattr(agent, "read", lambda pid: {"revision": 1, "timeline": t})
        monkeypatch.setattr(store, "assets", lambda pid: [])
        return {f["code"]: f for f in review.audit_timeline("p")["findings"]}
    hook = {"id": "hook", "kind": "text", "text": "NƯỚC TRÊN MẶT TRĂNG\n= NHIÊN LIỆU TÊN LỬA", "start_frame": 0, "end_frame": 120,
            "x": .08, "y": .125, "width": .84, "height": .11, "font_size": 68, "line_height": 1.36}
    f = audit({**hook, "typography_role": "display"})["text_wraps"]
    assert f["evidence"]["predicted_lines"] == 4 and "overrides font_size" in f["suggestion"]  # the role's 112 px wins
    assert "text_wraps" not in audit({**hook, "font_id": "archivo", "font_weight": 700})  # 68 px: each line fits


def test_engines_get_an_sdr_proxy_for_hdr_and_sparse_keyframe_sources(workspace):
    from editvideo.code_engine import engine_media, keyframe_gap
    from editvideo.media import probe

    def clip(name, extra):
        path = workspace / name
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", *extra, str(path)], check=True)
        return path
    hlg = clip("hlg.mp4", ["-g", "30", "-vf", "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc"])  # flags alone tag only the matrix
    sparse = clip("sparse.mp4", ["-g", "150", "-keyint_min", "150", "-sc_threshold", "0"])
    plain = clip("plain.mp4", ["-g", "30"])
    assert keyframe_gap(sparse) == pytest.approx(5.0, abs=.05) and keyframe_gap(plain) == pytest.approx(1.0, abs=.05)
    out, why = engine_media(hlg, {"kind": "video", "sha256": "a" * 64})
    v = next(s for s in probe(str(out))["streams"] if s["codec_type"] == "video")
    assert why == "HDR arib-std-b67" and v["color_transfer"] == "bt709" and keyframe_gap(out) <= 1.05
    out2, why2 = engine_media(sparse, {"kind": "video", "sha256": "b" * 64})
    assert why2.startswith("keyframes") and keyframe_gap(out2) <= 1.05
    assert engine_media(plain, {"kind": "video", "sha256": "c" * 64}) == (plain, None)
    assert engine_media(hlg, {"kind": "video", "sha256": "a" * 64})[0] == out  # cached


def test_short_pages_keep_names_and_compounds_and_never_end_on_a_function_word():
    from editvideo.professional import short_pages
    timed = lambda s: [{"text": w, "start_frame": i * 8, "end_frame": i * 8 + 7} for i, w in enumerate(s.split())]
    pages = lambda s: [" ".join(w["text"] for w in c) for c in short_pages(timed(s))]
    assert pages("3 cảnh Việt Nam bạn nên thấy tận mắt một lần.")[0] == "3 cảnh Việt Nam"
    assert all(not p.endswith(("Hội", "Hạ", "trái")) for p in pages("Số 3: chợ sáng ở Hội An. Số 2: vịnh Hạ Long. Rau xanh, trái cây bày kín."))
    assert not any(p.split()[-1] in ("of", "the", "to") for p in pages("Water ice, of course, is life support and the same rocket fuel"))


def test_word_captions_add_a_translation_line(workspace):
    from editvideo import agent, professional
    pid = agent.create_silent("vertical", 90, "remotion", "bilingual")["id"]
    words = [{"text": "Water", "start": .1, "end": .4}, {"text": "ice", "start": .45, "end": .8}, {"text": "is", "start": 1.0, "end": 1.2}, {"text": "life.", "start": 1.25, "end": 1.7}]
    p = agent.read(pid)
    agent.patch(pid, p["revision"], [{"op": "replace_cues", "cues": [{"start": .1, "end": 1.7, "text": "Water ice is life."}]}])
    r = professional.compose(pid, agent.read(pid)["revision"], {"recipe": "word_captions", "platform": "tiktok", "start_frame": 0, "end_frame": 90,
                                                                 "word_timings": words, "word_animation": "pop", "outline": .07,
                                                                 "translations": [{"start": .1, "end": 1.0, "text": "Băng nước"}, {"start": 1.0, "end": 2.0, "text": "là nguồn sống."}]},
                             dry_run=True)
    layers = {o["layer"]["id"]: o["layer"] for o in r["operations"] if o["op"] == "upsert_layer"}
    tr = layers["professional-caption-tr"]
    assert [pg["words"][0]["text"] for pg in tr["data"]["pages"]] == ["Băng nước", "là nguồn sống."]
    assert tr["y"] > layers["professional-caption"]["y"] and tr["font_size"] < layers["professional-caption"]["font_size"]


def test_a_b_roll_ending_is_a_cut_and_a_flash_shot_beside_it_is_flagged(monkeypatch):
    from editvideo import agent, review
    t = {"width": 1080, "height": 1920, "total_frames": 300, "fps": 30, "cues": [], "design": {},
         "shots": [{"id": "a", "start_frame": 0, "end_frame": 150, "motion": "hold"}, {"id": "b", "start_frame": 150, "end_frame": 300, "motion": "hold"}],
         "layers": [{"id": "broll", "kind": "video", "start_frame": 60, "end_frame": 144, "x": 0, "y": 0, "width": 1, "height": 1}]}
    monkeypatch.setattr(agent, "read", lambda pid: {"revision": 1, "timeline": t})
    monkeypatch.setattr(store, "assets", lambda pid: [])
    f = {x["code"]: x for x in review.audit_timeline("p")["findings"]}
    assert f["flash_shot"]["where"]["frames"] == [144, 150]  # 6 frames of the speaker between the B-roll and the next cut


def test_punch_in_stays_clear_of_full_frame_b_roll(workspace):
    from editvideo import agent, ads
    pid = agent.create_silent("vertical", 300, "remotion", "punch")["id"]
    clip = _mp4(workspace / "take.mp4", "testsrc2=s=1080x1920:r=30", seconds=10)
    aid = agent.import_media(pid, str(clip), "take", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
    p = agent.read(pid)
    t = p["timeline"]
    t["shots"] = [{**t["shots"][0], "asset_id": aid, "fit": "cover", "source_start": 0, "text": ""}]
    t["layers"] = [{"id": "broll", "kind": "video", "asset_id": aid, "start_frame": 100, "end_frame": 160, "x": 0, "y": 0, "width": 1, "height": 1, "z": 60}]
    agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
    r = ads.punch_in(pid, agent.read(pid)["revision"], frames=[130, 166, 220], min_gap_s=1, dry_run=True)
    assert [x["frame"] for x in r["placed"]] == [220]
    assert {x["frame"] for x in r["skipped"]} == {130, 166}


def test_words_cut_off_by_a_select_are_not_captioned():
    from editvideo.dialogue import map_words
    words = [{"start": 1.0, "end": 1.4, "word": "south"}, {"start": 1.9, "end": 2.4, "text": "thank"}]
    out = map_words(words, [{"src": [0.8, 2.05], "frames": [0, 38]}])  # "thank" is 30% inside the kept range
    assert [w["text"] for w in out] == ["south"]


def test_keyframe_gap_counts_the_tail(workspace):
    from editvideo.code_engine import keyframe_gap
    one = _mp4(workspace / "one.mp4", "testsrc2=s=160x90:r=30", seconds=4)  # x264 default GOP 250 > 120 frames: one keyframe
    assert keyframe_gap(one) == pytest.approx(4.0, abs=.1)
