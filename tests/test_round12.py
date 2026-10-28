"""Round 12: the learning loop end to end (study, register, blueprint, rebuild) exposed two system gaps."""
import subprocess
import pytest
from editvideo import store
from editvideo.media import FFMPEG


def test_rec601_tagged_sdr_is_read_without_a_declaration(tmp_path):
    """Web encoders still tag SDR video as Rec.601 (bt470bg/smpte170m); the colour pipeline had refused it as untagged."""
    from editvideo.color_pipeline import ColorRequest, input_color
    from editvideo.media import probe
    clip = tmp_path / "pal.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-bsf:v", "h264_metadata=colour_primaries=5:transfer_characteristics=6:matrix_coefficients=5:video_full_range_flag=0", str(clip)], check=True)
    v = next(s for s in probe(str(clip))["streams"] if s["codec_type"] == "video")
    space, primaries, trc, matrix, rng = input_color(ColorRequest(path=str(clip)), v)
    assert (space, primaries, trc, matrix, rng) == ("bt601_625", "bt470bg", "601", "470bg", "limited")
    with pytest.raises(ValueError):  # untagged still has to be declared
        input_color(ColorRequest(path=str(clip)), {"pix_fmt": "yuv420p"})


def test_text_audits_measure_a_condensed_role_at_its_width():
    """A role at wdth 62.5 draws a fifth narrower; the wrap audit had measured it at the default width and predicted
    two lines for one."""
    from editvideo.review import _axes
    from editvideo.design_library import layout_text
    design = {"typography": {"headline": {"font_id": "notoserif", "size": 110, "weight": 250, "tracking": .1, "line_height": 1.1,
                                          "variation_axes": {"wdth": 62.5}}}}
    layer = {"typography_role": "headline", "text": "WIKIMEDIA COMMONS"}
    ax = _axes(layer, design)
    assert ax == {"wdth": 62.5}
    narrow = layout_text("notoserif", layer["text"], 110, 4000, 250, variation_axes=ax)["line_widths"][0]
    wide = layout_text("notoserif", layer["text"], 110, 4000, 250)["line_widths"][0]
    assert narrow < .85 * wide
    assert _axes({**layer, "font_id": "oswald"}, design) is None  # a layer naming another font does not inherit the axes


def test_variable_frame_rate_video_plays_from_a_constant_rate_proxy(tmp_path, monkeypatch):
    """A phone clip's variable rate (frames 1.3 and 0.7 of 1/30 s apart, no gaps): HyperFrames failed to normalise it
    and refused the render; both engines now play a constant 30 fps proxy."""
    from editvideo.code_engine import engine_media, frame_gaps, frame_jitter
    from editvideo.media import probe
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    src = tmp_path / "vfr.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=2", "-vf", r"settb=1/3000,setpts='(N+0.3*mod(N\,2))/30/TB'",
                    "-fps_mode", "passthrough", "-enc_time_base", "1/3000", "-video_track_timescale", "3000", "-c:v", "libx264", "-g", "30",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    v = next(s for s in probe(str(src))["streams"] if s["codec_type"] == "video")
    assert frame_gaps(src) == 0 and frame_jitter(src) > .1  # no gap, yet not constant (ffprobe still says 30/1)
    out, why = engine_media(src, {"kind": "video", "sha256": "d" * 64})
    w = next(s for s in probe(str(out))["streams"] if s["codec_type"] == "video")
    assert why and "variable frame rate" in why and w["r_frame_rate"] == w["avg_frame_rate"] == "30/1"


def test_hyperframes_video_elements_preload_metadata_only():
    """With preload="auto" every <video> held a streaming connection; past six distinct sources Chrome's per-host limit
    ran out and HyperFrames' player never became ready (measured: 5 shots ready, 10 shots hung for 600 s, the same 10
    with preload metadata ready in 89 s)."""
    from pathlib import Path
    import inspect
    from editvideo import code_engine
    assert 'preload="metadata"' in inspect.getsource(code_engine) and 'preload="auto"' not in inspect.getsource(code_engine)
    js = (Path(__file__).parents[1] / "engines" / "hyper-runtime.js").read_text(encoding="utf-8")
    assert "n.preload='metadata'" in js and "n.preload='auto'" not in js


def _clip(path, vf=None, size="1920x1080", d=2):
    src = f"testsrc2=s={size}:r=30:d={d}"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", src, *(["-vf", vf] if vf else []), "-c:v", "libx264", "-crf", "14",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_look_grades_the_picture_not_the_content(tmp_path, monkeypatch):
    """The remake's first footage passed a content-and-motion selection while shaky, upscaled and noisy; the look sense
    grades those C and keeps a sharp, steady picture (and a smooth pan) usable."""
    from editvideo import look
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    big = "testsrc2=s=2400x1350:r=30:d=2"
    clean = look.measure(str(_clip(tmp_path / "clean.mp4")), 0, 2)
    assert clean["grade"] == "A" and not clean["flags"] and clean["upscale"] == 1.0
    small = look.measure(str(_clip(tmp_path / "small.mp4", size="640x360")), 0, 2)
    assert small["grade"] == "C" and small["flags"][0].startswith("upscaled x3.00")
    shaky = tmp_path / "shaky.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", big, "-vf", "crop=1920:1080:x='240+6*sin(t*31)+4*sin(t*47)':y='135+5*sin(t*41)+3*sin(t*59)'",
                    "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(shaky)], check=True)
    sh = look.measure(str(shaky), 0, 2)
    assert sh["grade"] == "C" and sh["shake_px"] > look.SHAKE_SHAKY
    pan = tmp_path / "pan.mp4"  # a drone's smooth move is not shake
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", big, "-vf", "crop=1920:1080:x='100+60*t':y=135",
                    "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(pan)], check=True)
    pn = look.measure(str(pan), 0, 2)
    assert pn["grade"] != "C" and pn["shake_px"] < look.SHAKE_SLIGHT
    noisy = look.measure(str(_clip(tmp_path / "noisy.mp4", vf="noise=alls=30:allf=t")), 0, 2)
    assert noisy["grade"] == "C" and any(f.startswith("noisy") for f in noisy["flags"])
    assert look.measure(str(tmp_path / "clean.mp4"), 0, 2) == clean  # cached per file state and window


def test_rank_clips_passes_over_windows_below_the_look_grade(tmp_path, monkeypatch):
    from editvideo import clips
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    good, bad = _clip(tmp_path / "good.mp4", d=3), _clip(tmp_path / "bad.mp4", size="640x360", d=3)
    r = clips.rank([str(good), str(bad)], window_s=1.5, top=4, match_cuts=False, min_look="B")
    assert r["windows"] and all(w["path"] == str(good) and w["look"]["grade"] in "AB" for w in r["windows"])
    assert r["look_rejected"] >= 1
    with pytest.raises(ValueError):
        clips.rank([str(good)], window_s=1.5, top=2, match_cuts=False, min_look="C")


def test_audit_flags_a_letterbox_bar_across_a_face_or_a_medium_shot_head(tmp_path, monkeypatch):
    """The remake's portrait lost the top of a conical hat under its 2.35 matte; nothing in the plan showed it."""
    from editvideo import agent, review
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    pid = agent.create_silent("landscape", 60, "remotion", "matte")["id"]
    aid = agent.import_media(pid, str(_clip(tmp_path / "s.mp4")), "s", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
    p = agent.read(pid)
    t = p["timeline"]
    t["shots"] = [{**t["shots"][0], "asset_id": aid, "fit": "cover", "source_start": 0, "text": "", "motion": "hold", "effects": [],
                   "start_frame": 0, "end_frame": 60}]
    t["layers"] = []
    agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])

    def run(face, bars=True):
        monkeypatch.setattr(review, "_faces", lambda path, tt: [face])
        tl = agent.read(pid)["timeline"]
        tl["layers"] = [{"id": f"bar{k}", "kind": "shape", "start_frame": 0, "end_frame": 60, "x": 0, "y": y, "width": 1, "height": .1218,
                         "z": 950, "color": "#000000", "data": {"shape": "rectangle"}} for k, y in ((0, 0), (1, 1 - .1218))] if bars else []
        return [(f["level"], f["where"]["layer"]) for f in review.audit_timeline(pid, tl)["findings"] if f["code"] == "matte_cuts_subject"]
    assert run((.45, .13, .08, .16)) == [("check", "bar0")]          # a medium shot: the hat above the face is under the bar
    assert run((.45, .05, .08, .16)) == [("likely_problem", "bar0")]  # the bar across the forehead
    assert run((.40, .55, .1, .4)) == [("likely_problem", "bar1")]    # the chin under the bottom bar
    assert run((.40, .20, .2, .45)) == []                             # a close-up may crop the hair
    assert run((.45, .05, .08, .16), bars=False) == []


def test_faces_fall_back_to_the_local_detector_without_haar(monkeypatch):
    """OpenCV 5 no longer ships the Haar cascades; face detection (text-over-face, face reframing, the matte check) used
    to raise there. The installed OWLv2 detector stands in, keeping face-shaped boxes of a usable size."""
    import numpy as np
    from editvideo import footage_pro, semantic
    monkeypatch.delattr(footage_pro.cv2, "CascadeClassifier", raising=False)
    monkeypatch.setattr(semantic, "_detect_frames", lambda imgs, qs, thr: [[
        {"q": 0, "score": .1, "box": [.4, .2, .5, .38]}, {"q": 0, "score": .1, "box": [.1, .1, .12, .6]},  # a face; a pole
        {"q": 0, "score": .1, "box": [.7, .7, .71, .71]}]])                                                 # a speck
    got = footage_pro.detect_faces(np.zeros((360, 640), np.uint8))
    assert len(got) == 1 and got[0] == pytest.approx((.4, .2, .1, .18))


def test_owl_post_processing_works_with_transformers_5(monkeypatch):
    """transformers 5 moved post_process_object_detection from the OWLv2 processor to its image processor."""
    import numpy as np
    torch = pytest.importorskip("torch")  # the vision extras
    from editvideo import semantic

    class ImageProcessor:
        def post_process_object_detection(self, outputs, threshold, target_sizes):
            return [{"labels": torch.tensor([0]), "boxes": torch.tensor([[10., 20., 50., 60.]]), "scores": torch.tensor([.5])} for _ in target_sizes]

    class Processor:
        image_processor = ImageProcessor()

        def __call__(self, text, images, return_tensors):
            return {"pixel_values": torch.zeros(len(images), 3, 4, 4), "input_ids": torch.zeros(len(images), 1, dtype=torch.long)}
    monkeypatch.setattr(semantic, "_owl", lambda: (Processor(), lambda **k: None))
    monkeypatch.setattr(semantic, "_device", lambda: ("cpu", torch.float32))
    hits = semantic._detect_frames([np.zeros((100, 200, 3), np.uint8)], ["x"], .1)
    assert hits[0][0]["box"] == [.05, .2, .25, .6]


def test_cut_alignment_rereads_a_weak_window_at_the_songs_tempo(monkeypatch):
    """A 100 BPM track read as 133 BPM after its intro made an edit cut on the beat measure as off the beat."""
    import numpy as np
    from editvideo import music
    calls = []

    def fake(path, t, t1, bpm_range):
        calls.append((t, bpm_range))
        bpm, strength = (100.0, .8) if t == 0 else ((133.0, .3) if not bpm_range else (100.0, .5))
        per = 60 / bpm
        return {"bpm": bpm, "strength": strength, "beats": np.arange(t, t1, per), "phase": 0, "period": per * 100, "fr": 100}
    monkeypatch.setattr(music, "_analyse", fake)
    cuts = [round(k * .6, 2) for k in range(1, 100) if k % 2 == 0]  # every other beat at 100 BPM, 0..60 s
    r = music.cut_alignment("song.mp3", cuts, 0, 60, window_s=30, fps=30)
    assert [w["bpm"] for w in r["windows"]] == [100.0, 100.0] and all(w["counted"] for w in r["windows"])
    assert any(br and br[0] < 100 < br[1] for _, br in calls)  # re-read near the anchor's tempo
    assert r["cuts_on_beat"] > .9

    def real_section(path, t, t1, bpm_range):  # a section really at 133 BPM: a forced, weaker 100 BPM reading must not win
        bpm, strength = (100.0, .8) if t == 0 else ((133.0, .45) if not bpm_range else (100.0, .22))
        return {"bpm": bpm, "strength": strength, "beats": np.arange(t, t1, 60 / bpm), "phase": 0, "period": 60 / bpm * 100, "fr": 100}
    monkeypatch.setattr(music, "_analyse", real_section)
    assert [w["bpm"] for w in music.cut_alignment("song.mp3", cuts, 0, 60, window_s=30, fps=30)["windows"]] == [100.0, 133.0]


def test_learning_reads_the_look_of_a_film(tmp_path, monkeypatch):
    """VideoSense 3 carries the look into blueprints: medians over sampled windows plus the shares graded A and C, so a
    rebuild on shaky phone clips misses targets its rhythm alone would meet."""
    from editvideo import learn_video
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    clean, small = _clip(tmp_path / "clean.mp4"), _clip(tmp_path / "small.mp4", size="640x360")
    calls = iter([str(clean), str(small)])
    from editvideo import look
    real = look.measure
    monkeypatch.setattr(look, "measure", lambda p, a, b: real(next(calls), a, b))  # one window per clip
    f = learn_video._look("film.mp4", [(0, 2), (0, 2)])
    assert f["look_a_share"]["value"] == .5 and f["look_c_share"]["value"] == .5
    assert f["look_upscale"]["value"] == 2.0 and learn_video.VideoSense.version == "7"


def _pan(path, fps, vf="crop=1920:1080:x='100+300*t':y=135", size="2400x1350", d=2):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={size}:r={fps}:d={d}", "-vf", vf, "-c:v", "libx264", "-crf", "14",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_look_reads_shake_at_the_source_rate_noise_inside_bars_and_the_canvas_orientation(tmp_path, monkeypatch):
    """The review found a smooth 300 px/s pan graded C at 24 and 25 fps (resampled to 15 fps, steps alternated 1 and
    2 frames), grain hidden by letterbox bars (the flattest tenth was the bars), a vertical clip graded "upscaled"
    and the canvas missing from the cache key."""
    from editvideo import look
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    for fps in (24, 25, 50):
        r = look.measure(str(_pan(tmp_path / f"pan{fps}.mp4", fps)), 0, 2)
        assert r["shake_px"] < look.SHAKE_SLIGHT and r["grade"] != "C", (fps, r["shake_px"])
    bars = "noise=alls=30:allf=t,drawbox=y=0:w=iw:h=132:color=black:t=fill,drawbox=y=ih-132:w=iw:h=132:color=black:t=fill"
    boxed = look.measure(str(_clip(tmp_path / "boxed.mp4", vf=bars)), 0, 2)
    assert boxed["grade"] == "C" and any(f.startswith("noisy") for f in boxed["flags"]) and boxed["letterbox"][0] > 0
    tall = str(_clip(tmp_path / "tall.mp4", size="1080x1920"))
    assert look.measure(tall, 0, 2)["upscale"] == 1.0
    assert look.measure(tall, 0, 2, canvas=(1920, 1080))["flags"][0].startswith("upscaled")  # another canvas, another reading
    with pytest.raises(ValueError):
        look.measure(tall, 5, 7)


def test_rank_rejects_an_upscaled_file_without_measuring_its_windows(tmp_path, monkeypatch):
    from editvideo import clips, look
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    calls = []
    real = look.measure
    monkeypatch.setattr(look, "measure", lambda p, a, b, **k: calls.append(p) or real(p, a, b, **k))
    good, bad = _clip(tmp_path / "good.mp4", d=3), _clip(tmp_path / "bad.mp4", size="640x360", d=3)
    r = clips.rank([str(good), str(bad)], window_s=1.5, top=4, match_cuts=False, min_look="B")
    assert str(bad) not in calls and r["look_rejected"] >= 1 and r["windows"]


def test_proxy_width_counts_every_zoom(monkeypatch):
    """A 4K source under zoom_out 1.0 or a scale key of 2 is drawn at 3840 px; the proxy had been cut to 1920."""
    from editvideo import code_engine
    monkeypatch.setattr(code_engine.store, "find_asset", lambda pid, aid: {"kind": "video", "width": 3840, "height": 2160})
    monkeypatch.setattr(code_engine.store, "assets", lambda pid: [{"id": "a", "kind": "video", "width": 3840, "height": 2160}])
    shot = {"beat_id": "b", "asset_id": "a", "fit": "cover", "motion": "hold", "effects": []}
    t = {"width": 1920, "height": 1080, "shots": [shot], "layers": []}
    assert code_engine.drawn_widths(t, "p")["a"] == pytest.approx(1920)
    shot["effects"] = [{"name": "zoom_out", "params": {"amount": 1.0}}]
    assert code_engine.drawn_widths(t, "p")["a"] == pytest.approx(3840)
    shot["effects"], shot["keyframes"] = [], {"scale": [{"frame": 0, "value": 1.0}, {"frame": 30, "value": 2.0}]}
    assert code_engine.drawn_widths(t, "p")["a"] == pytest.approx(3840)


def test_variable_rate_60fps_phone_clip_keeps_its_frames(tmp_path, monkeypatch):
    """Slow motion is built from the constant-rate proxy: a 60 fps phone clip proxied at 30 had shown each frame twice at 0.5x."""
    from editvideo.code_engine import engine_media
    from editvideo.media import probe
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    src = tmp_path / "vfr60.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=60:d=2", "-vf", r"settb=1/6000,setpts='(N+0.3*mod(N\,2))/60/TB'",
                    "-fps_mode", "passthrough", "-enc_time_base", "1/6000", "-video_track_timescale", "6000", "-c:v", "libx264", "-g", "60",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    out, why = engine_media(src, {"kind": "video", "sha256": "e" * 64})
    w = next(s for s in probe(str(out))["streams"] if s["codec_type"] == "video")
    assert "variable frame rate" in why and w["avg_frame_rate"] == "60/1"


def test_rec601_is_graded_like_rec709():
    """Round 12 accepted Rec.601 sources; HDR10 output still skipped their paper-white lift, white balance and the colour
    graph refused them, and the matrix ignored the stream's own tag."""
    import numpy as np
    from editvideo.color_graph import input_linear
    from editvideo.color_pipeline import ColorRequest, filter_graph, input_color
    stream = {"color_primaries": "bt470bg", "color_transfer": "smpte170m", "color_range": "tv", "color_space": "bt470bg", "pix_fmt": "yuv420p"}
    graph, _ = filter_graph(ColorRequest(path="x.mp4", output="hdr10"), stream)
    assert "exposure=exposure=" in graph
    lin = input_linear("bt601_625", np.array([[1.0, 1.0, 1.0], [.5, .5, .5]]))
    assert lin[0] == pytest.approx([1, 1, 1], abs=1e-6) and np.ptp(lin[1]) < 1e-6  # neutrals stay neutral
    hd601 = {**stream, "color_primaries": "bt709", "color_transfer": "bt709", "color_space": "smpte170m"}
    assert input_color(ColorRequest(path="x.mp4"), hd601)[3] == "170m"  # HD primaries over a 601 matrix


def test_audit_flags_off_cadence_footage_and_a_source_on_a_loop(tmp_path, monkeypatch):
    """Round 12's film: 13 of 23 clips at 24/25/50 fps repeated a frame every few frames, and five people came back
    four times each in 25 s; neither had a finding."""
    from editvideo import agent, review
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    pid = agent.create_silent("landscape", 480, "remotion", "loop")["id"]
    aid = agent.import_media(pid, str(_pan(tmp_path / "p25.mp4", 25, vf="null", size="1920x1080", d=4)), "p", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
    bid = agent.import_media(pid, str(_clip(tmp_path / "b.mp4", d=4)), "b", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
    p = agent.read(pid)
    t = p["timeline"]
    base = {**t["shots"][0], "text": "", "motion": "hold", "effects": [], "fit": "cover"}
    cid = agent.import_media(pid, str(_clip(tmp_path / "c.mp4", d=4)), "c", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
    p = agent.read(pid)
    t = p["timeline"]
    # the 25 fps clip three times in 10 s (under 40 % of the film: not the spine of an interview), its first moment twice
    order = [(aid, 0), (bid, 0), (aid, .5), (cid, 0), (aid, .2), (bid, 2), (cid, 2), (bid, 0)]
    t["shots"] = [{**base, "id": f"s{i}", "asset_id": a, "source_start": s0, "start_frame": i * 60, "end_frame": (i + 1) * 60}
                  for i, (a, s0) in enumerate(order)]
    t["layers"] = []
    agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
    found = review.audit_timeline(pid)["findings"]
    f = {x["code"]: x for x in found}
    assert f["off_cadence_footage"]["evidence"]["source_fps"] == {"25.0": 3}
    rep = next(x["evidence"] for x in found if x["code"] == "repeated_source" and x["evidence"]["asset"] == aid)
    assert rep["uses"] == 3 and rep["most_in_20s"] == 3 and rep["same_moment_twice"]
    tl = agent.read(pid)["timeline"]
    for sh in tl["shots"]:
        sh["frame_sampling"] = "flow"
    assert "off_cadence_footage" not in {x["code"] for x in review.audit_timeline(pid, tl)["findings"]}


def test_flow_sampling_plays_an_off_cadence_clip_at_its_true_time(tmp_path, monkeypatch):
    """frame_sampling "flow": a 25 fps clip re-timed by motion interpolation, frame k showing the picture at
    source_start + k/30 (a bar moving 4 px a frame is within 2 px of its true place; repeating frames is off by up to 4.8)."""
    import numpy as np
    from editvideo import code_engine
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    src = tmp_path / "bar25.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=25:d=4", "-f", "lavfi", "-i", "color=c=white:s=24x60:r=25:d=4",
                    "-filter_complex", "[0][1]overlay=x='40+120*t':y=150", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(src)], check=True)
    assert code_engine.off_cadence(25) and not code_engine.off_cadence(60) and not code_engine.off_cadence(15)
    out = code_engine.cadence_proxy(src, {"sha256": "c" * 64}, 1.0, 30)
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(out), "-vf", "format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, 360, 640)
    assert len(f) == 30
    for k in range(30):
        row = np.clip(f[k, 180].astype(float) - 20, 0, None)
        x = (row * np.arange(640)).sum() / row.sum() - 11.5
        assert abs(x - (40 + 120 * (1.0 + k / 30))) < 2.5, k


def test_matte_check_skips_faces_cropped_off_the_canvas(tmp_path, monkeypatch):
    from editvideo import agent, review
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    pid = agent.create_silent("vertical", 60, "remotion", "matte9")["id"]
    aid = agent.import_media(pid, str(_clip(tmp_path / "w.mp4")), "w", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
    p = agent.read(pid)
    t = p["timeline"]
    t["shots"] = [{**t["shots"][0], "asset_id": aid, "fit": "cover", "source_start": 0, "text": "", "motion": "hold", "effects": [],
                   "start_frame": 0, "end_frame": 60}]
    t["layers"] = [{"id": "bar0", "kind": "shape", "start_frame": 0, "end_frame": 60, "x": 0, "y": 0, "width": 1, "height": .12, "z": 950,
                    "color": "#000000", "data": {"shape": "rectangle"}}]
    agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
    monkeypatch.setattr(review, "_faces", lambda path, tt: [(.03, .05, .06, .1)])  # at the source's left edge: off a 9:16 cover
    assert not [f for f in review.audit_timeline(pid)["findings"] if f["code"] == "matte_cuts_subject"]
    monkeypatch.setattr(review, "_faces", lambda path, tt: [(.47, .05, .06, .1)])  # centred: on the canvas, under the bar
    assert [f["level"] for f in review.audit_timeline(pid)["findings"] if f["code"] == "matte_cuts_subject"] == ["likely_problem"]
