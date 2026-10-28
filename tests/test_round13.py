"""Round 13: an independent review of round 12 found three senses blind where it mattered: noise on night footage,
a scene shown again from another moment, and motion interpolation ghosting a fast foreground."""
import subprocess
import numpy as np
import pytest
from editvideo import store
from editvideo.media import FFMPEG, FFPROBE


def _clip(path, vf=None, size="1920x1080", d=2, fps=30):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={size}:r={fps}:d={d}", *(["-vf", vf] if vf else []),
                    "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def _texture(seed, w=3200, h=1080):
    """A scene with structure at every scale (clouds for the thumbnails, 300 shapes a little lighter or darker than
    their ground for ORB's corners), RGB uint8."""
    import cv2
    rng = np.random.default_rng(seed)
    g = np.zeros((h, w), np.float32)
    for div, amp in ((256, 1.0), (64, .5), (16, .25), (4, .12)):
        g += amp * cv2.resize(rng.random((max(2, h // div), max(2, w // div))).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    g = (g - g.min()) / (g.max() - g.min()) * 140 + 50
    for _ in range(300):
        x, y, s = int(rng.integers(0, w - 100)), int(rng.integers(0, h - 100)), int(rng.integers(20, 90))
        v = float(g[y + s // 2, x + s // 2] + rng.choice([-1, 1]) * rng.uniform(25, 60))
        if rng.random() < .5:
            cv2.rectangle(g, (x, y), (x + s, y + int(s * rng.uniform(.4, 1.6))), v, -1)
        else:
            cv2.circle(g, (x + s // 2, y + s // 2), s // 2, v, -1)
    return np.clip(np.stack([g, np.roll(g, 37, 0) * .8 + 20, 255 - g * .7], -1), 0, 255).astype(np.uint8)


def _film(path, pngs, seconds, speed=600):
    """Scenes panned at speed px/s (1920x1080 crops of 3200-px textures), cut together: one shot per png."""
    args = sum(([ "-loop", "1", "-framerate", "30", "-t", str(s), "-i", str(p)] for p, s in zip(pngs, seconds)), [])
    graph = ";".join(f"[{i}]crop=1920:1080:x='100+{speed}*t':y=0[v{i}]" for i in range(len(pngs)))
    graph += ";" + "".join(f"[v{i}]" for i in range(len(pngs))) + f"concat=n={len(pngs)}:v=1:a=0"
    subprocess.run([FFMPEG, "-v", "error", "-y", *args, "-filter_complex", graph, "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_temporal_noise_reads_grain_through_camera_motion():
    """Two consecutive frames of a moving camera, aligned, differ by sqrt 2 x the grain; a clean pair by nothing."""
    import cv2
    from editvideo import look
    rng = np.random.default_rng(0)
    base = cv2.GaussianBlur(np.clip(np.cumsum(np.cumsum(rng.standard_normal((900, 1500)), 0), 1) * .002 + 128, 20, 230).astype(np.float32), (0, 0), 12)
    a, b = base[60:780, 70:1350], base[63:783, 75:1355]  # the camera moved 5 px right and 3 px down
    assert look._temporal_noise(a, b) < .3
    assert look._temporal_noise(a + rng.normal(0, 5, a.shape), b + rng.normal(0, 5, b.shape)) == pytest.approx(5, abs=.5)
    assert look._temporal_noise(a, a) is None  # one frame shown twice says nothing


def test_look_reads_noise_on_dark_footage_and_never_grades_an_unmeasured_frame_a(tmp_path, monkeypatch):
    """The review's grained Pexels night clips read noise None and grade A: the spatial measure wants flat pixels above
    luma 16, which a night frame (or a textured one) hardly has. The temporal measure reads them; where neither can
    look, the grade is capped at B and says so."""
    from PIL import Image
    from editvideo import look
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    grainy = look.measure(str(_clip(tmp_path / "grainy.mp4", vf="eq=brightness=-0.35,noise=alls=20:allf=t")), 0, 2)
    assert grainy["grade"] == "C" and any(f.startswith("noisy") for f in grainy["flags"])
    clean = look.measure(str(_clip(tmp_path / "dark.mp4", vf="eq=brightness=-0.35")), 0, 2)
    assert clean["noise"] is not None and clean["noise"] < 1 and not any(f.startswith("noisy") for f in clean["flags"])
    # the temporal reading sees the grain too (x264's quantised residual makes it non-Gaussian: the MAD reads it under
    # the spatial measure, which leads where it can look)
    assert clean["noise_temporal"] < 1 < 2 < grainy["noise_temporal"] < grainy["noise_spatial"] * 1.2
    # a night frame, mostly under luma 16 (darkened in RGB: crushing Y alone leaves saturated chroma, which the RGB
    # conversion clips back into light): clean, it is only dark; grained, the temporal reading leads and says noisy
    dark = "format=gbrp,lutrgb=r=val*0.08:g=val*0.08:b=val*0.08,format=yuv420p"
    night = look.measure(str(_clip(tmp_path / "night.mp4", vf=dark)), 0, 2)
    assert night["mean"] < .06 and night["noise"] < 1 and night["flags"] == [f"dark (mean {night['mean']:.2f})"]
    night = look.measure(str(_clip(tmp_path / "night-grain.mp4", vf=dark + ",noise=c0s=20:c0f=t")), 0, 2)
    assert night["noise"] == night["noise_temporal"] and night["noise"] > look.NOISE_NOISY and night["grade"] == "C"
    # a still of fine texture: no flat pixels for the spatial measure, no second frame for the temporal one
    rng = np.random.default_rng(2)
    import cv2
    tex = cv2.GaussianBlur(rng.integers(0, 256, (1080, 1920), np.uint8).astype(np.float32), (0, 0), 1.5)
    Image.fromarray(np.clip((tex - tex.mean()) * 3 + 128, 0, 255).astype(np.uint8)).convert("RGB").save(tmp_path / "tex.png")
    still = look.measure(str(tmp_path / "tex.png"))
    assert still["noise"] is None and "noise unmeasured" in still["flags"] and still["grade"] == "B"
    with pytest.raises(ValueError):  # a window shorter than a frame at the tail had raised IndexError
        look.measure(str(tmp_path / "dark.mp4"), 1.9, 2.0)


def test_scene_similarity_sees_a_pan_again_from_another_moment(tmp_path):
    """Thumbnails miss the same scene a second later in a pan (600 px of 1920); ORB with a RANSAC homography keeps
    hundreds of inliers there and none across two different scenes."""
    from PIL import Image
    from editvideo import scene_sim
    for seed in (1, 2):
        Image.fromarray(_texture(seed)).save(tmp_path / f"tex{seed}.png")
        _film(tmp_path / f"pan{seed}.mp4", [tmp_path / f"tex{seed}.png"], [2])
    f = {(s, t): scene_sim.features(str(tmp_path / f"pan{s}.mp4"), t) for s in (1, 2) for t in (.2, 1.2)}
    assert float(f[1, .2][0] @ f[1, 1.2][0]) < scene_sim.THUMB_MATCH  # 1 s on (600 px of 1920): the thumbnails do not match
    assert scene_sim.inliers(f[1, .2], f[1, 1.2]) >= scene_sim.MIN_INLIERS and scene_sim.same_scene(f[1, .2], f[1, 1.2])
    assert scene_sim.inliers(f[1, .2], f[2, .2]) < scene_sim.MIN_INLIERS and not scene_sim.same_scene(f[1, .2], f[2, 1.2])
    dup, pairs = scene_sim.repeats([f[1, .2], f[2, .2], f[1, 1.2], f[2, 1.2]])
    assert dup.tolist() == [True, True, True, True] and pairs == [(0, 2, "orb"), (1, 3, "orb")]
    again = scene_sim.features(str(tmp_path / "pan1.mp4"), .2)  # cached per file state and time; the same picture is a thumbnail match
    assert again is f[1, .2] and scene_sim.repeats([f[1, .2], again, f[2, 1.2]])[1] == [(0, 1, "thumb")]


def test_repeat_share_and_the_audit_count_a_scene_shown_again(tmp_path, monkeypatch):
    """A film of one scene panned for 2 s then two other scenes: by thumbnails no shot repeats, by scene half do. The
    plan-time audit fires repeated_source on two visits of one source inside 20 s that show the same scene, and
    repeated_picture on the shots' middle frames."""
    from PIL import Image
    from editvideo import agent, learn_video, review, scene_sim
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    for seed in (1, 2, 3):
        Image.fromarray(_texture(seed)).save(tmp_path / f"tex{seed}.png")
    film = _film(tmp_path / "film.mp4", [tmp_path / f"tex{s}.png" for s in (1, 2, 3)], [2, 1, 1])
    segs = [{"start": k, "end": k + 1} for k in range(4)]
    feats = [scene_sim.features(str(film), k + .5) for k in range(4)]
    x = np.stack([f[0] for f in feats])
    assert (x @ x.T - np.eye(4)).max() < scene_sim.THUMB_MATCH  # the thumbnail measure of round 12 saw no repeat
    assert learn_video.repeat_share(str(film), segs, 4.0) == .5 and learn_video.VideoSense.version == "7"  # 7: source mix, black cuts, frozen time
    b = _clip(tmp_path / "b.mp4", d=4)

    def audit(order):  # half-second shots covering a project of their own (f: the film, b: testsrc2)
        pid = agent.create_silent("landscape", 15 * len(order), "remotion", f"again{len(order)}")["id"]
        ids = {k: agent.import_media(pid, str(src), k, "evidence", True, agent.read(pid)["revision"])["asset"]["id"] for k, src in (("f", film), ("b", b))}
        p = agent.read(pid)
        t = p["timeline"]
        base = {**t["shots"][0], "text": "", "motion": "hold", "effects": [], "fit": "cover"}
        tl = {**t, "shots": [{**base, "id": f"s{i}", "asset_id": ids[a], "source_start": s0, "start_frame": i * 15, "end_frame": (i + 1) * 15}
                             for i, (a, s0) in enumerate(order)], "layers": []}
        agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": tl}])
        return {f["code"]: f for f in review.audit_timeline(pid)["findings"] if f["where"].get("shots", [None])[0] == "s0" or f["code"] == "repeated_picture"}
    # two visits of the film 1 s apart, windows [.2, .7) and [1.2, 1.7): not the same moment, the same scene (the film
    # under 40 % of the edit: a spine returns by design)
    f = audit([("f", .2), ("b", 0), ("f", 1.2), ("b", 2), ("b", 1), ("b", 3)])
    rs = f["repeated_source"]["evidence"]
    assert [list(x) for x in rs["same_scene_in_20s"]] == [["s0", "s2"]] and not rs["same_moment_twice"] and rs["most_in_20s"] == 2
    assert "repeated_source" not in audit([("f", .2), ("b", 0), ("f", 2.2), ("b", 2), ("b", 1), ("b", 3)])  # the second visit shows another scene
    f = audit([("f", .2), ("b", 0), ("f", 1.2), ("b", 2), ("b", 1), ("b", 3), ("b", .5), ("b", 1.5)])
    rp = f["repeated_picture"]["evidence"]
    assert rp["share"] >= .25 and ["s0", "s2", "orb"] in [list(x) for x in rp["pairs"]] and "ORB" in rp["method"]


def test_flow_falls_back_to_blended_frames_where_a_fast_foreground_would_ghost(tmp_path, monkeypatch):
    """A 200 px square crossing a textured background at 18 px per frame (at 1920 wide) would be blended with what is
    behind it by minterpolate (round 12: a walking man wearing a hat from the background). In slow motion the proxy
    blends the two source frames around each output time instead (nearest frames repeat 1-2-1-2 there, read as
    judder) and records why; at 1x it makes no proxy and the shot plays its own frames (the fifth cut's blends cost 40 %
    of the sharpness, which the owner saw as blur). The slow bar of round 12 still interpolates."""
    import cv2
    from PIL import Image
    from editvideo import code_engine
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    rng = np.random.default_rng(1)
    bg = cv2.GaussianBlur(rng.integers(0, 256, (360, 640), np.uint8).astype(np.float32), (0, 0), 1.5)
    Image.fromarray(np.clip((bg - bg.mean()) * 2 + 90, 30, 150).astype(np.uint8)).save(tmp_path / "bg.png")  # textured, never bright
    rect = tmp_path / "rect25.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-loop", "1", "-framerate", "25", "-i", str(tmp_path / "bg.png"), "-f", "lavfi", "-i",
                    "color=c=white:s=200x200:r=25:d=4", "-filter_complex", "[0][1]overlay=x='20+150*t':y=80", "-t", "4", "-c:v", "libx264",
                    "-crf", "10", "-pix_fmt", "yuv420p", str(rect)], check=True)
    risk = code_engine.cadence_risk(rect, 1.0, 1.0)
    assert risk["top_motion_px"] > code_engine.FLOW_MAX_MOTION and risk["pairs"] >= 20
    assert code_engine.cadence_proxy(rect, {"sha256": "f" * 64}, 1.0, 30) is None  # 1x: its own frames, no blur
    assert code_engine.cadence_proxy(rect, {"sha256": "f" * 64}, 1.0, 30) is None  # the decision is cached
    out = code_engine.cadence_proxy(rect, {"sha256": "f" * 64}, 1.0, 36, rate=.6)  # slow motion: blended
    d = code_engine.cadence_decision(out)
    assert d["mode"] == "blend" and d["top_motion_px"] >= code_engine.FLOW_MAX_MOTION
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(out), "-vf", "format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, 360, 640).astype(int)
    assert len(f) == 36
    assert min(np.abs(f[k + 1] - f[k]).mean() for k in range(35)) > .3  # no output frame repeats the one before
    for k in range(0, 36, 6):  # on the source's own frame times (1 + k*0.6/30 s, k a multiple of 6... at 0.6x every 6th output frame
        shown = (int(np.argmax(f[k, 180] > 220)) - 20) / 6   # lands on a 25 fps frame time) the square is crisp, in place
        assert abs(shown - (1 + k * .6 / 30) * 25) <= .75, (k, shown)
    bar = tmp_path / "bar25.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=25:d=4", "-f", "lavfi", "-i", "color=c=white:s=24x60:r=25:d=4",
                    "-filter_complex", "[0][1]overlay=x='40+120*t':y=150", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(bar)], check=True)
    assert code_engine.cadence_risk(bar, 1.0, 1.0)["top_motion_px"] < code_engine.FLOW_MAX_MOTION
    flow = code_engine.cadence_proxy(bar, {"sha256": "c" * 64}, 1.0, 30)
    assert code_engine.cadence_decision(flow)["mode"] == "flow"
    msg = code_engine.cadence_log("s1", out)  # the render log says so, once per shot; a flow proxy has nothing to say
    assert msg and "fell back to blended" in msg and " px/frame" in msg and code_engine.cadence_log("s1", out) is None
    assert code_engine.cadence_log("s2", flow) is None
    assert "plays its own frames" in code_engine.cadence_log("s3", None)


def test_a_slowed_blend_writes_every_frame_and_an_empty_cache_entry_is_remade(tmp_path, monkeypatch):
    """At 0.957x the blend ran at 31.347962 fps, which FFmpeg's framerate filter took as 772163/24632 and wrote one frame:
    ten shots of the fifth cut had empty proxies and the export failed on their posters. The rate is now an exact fraction,
    the proxy's frame count is checked, and an empty file in the cache is made again. (0.957x now plays its own frames;
    0.7x, 42.857 fps, is the same repeating decimal.)"""
    from editvideo import code_engine
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    src = tmp_path / "fast25.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=4", "-f", "lavfi", "-i", "color=c=white:s=200x200:r=25:d=4",
                    "-filter_complex", "[0][1]overlay=x='20+150*t':y=80", "-t", "4", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(src)], check=True)
    monkeypatch.setattr(code_engine, "cadence_risk", lambda *a: {"top_motion_px": 99.0, "occlusion_share": 0.0, "pairs": 20})  # force the blend
    count = lambda p: int(subprocess.run([FFPROBE, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames",
                                          "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True).stdout.strip())
    out = code_engine.cadence_proxy(src, {"sha256": "b" * 64}, 0.0, 60, rate=.7)
    assert code_engine.cadence_decision(out)["mode"] == "blend" and count(out) == 60
    out.write_bytes(b"\0" * 262)  # what the old recipe left in the cache
    assert code_engine.cadence_proxy(src, {"sha256": "b" * 64}, 0.0, 60, rate=.7) == out and count(out) == 60
    assert code_engine.cadence_proxy(src, {"sha256": "b" * 64}, 0.0, 60, rate=.957) is None  # near 1x: its own frames


def test_video_sense_carries_the_exposure_level(tmp_path, monkeypatch):
    """look_mean per part lets a blueprint carry a day-dusk-night arc."""
    from editvideo import learn_video
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    f = learn_video._look(str(_clip(tmp_path / "dark.mp4", vf="eq=brightness=-0.35")), [(0, 2)])
    assert .1 < f["look_mean"]["value"] < .4 and f["look_mean"]["unit"].startswith("exposure level")
    assert learn_video._look(str(_clip(tmp_path / "day.mp4")), [(0, 2)])["look_mean"]["value"] > f["look_mean"]["value"]


def test_slow_motion_is_interpolated_not_repeated(tmp_path, monkeypatch):
    """At 0.4x a nearest-frame player shows each 25 fps frame 2.5 times (a 6 px jump, then the same picture twice: a
    stutter on any glide). With frame_sampling flow the proxy interpolates 75 source-time frames per second and spreads
    them at 1/30 s, so a bar moving 6 px per source frame advances every output frame (about 2 px; minterpolate's whole-
    pixel vectors give 1.3-2.3)."""
    from editvideo import code_engine
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    bar = tmp_path / "bar25.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=25:d=4", "-f", "lavfi", "-i", "color=c=white:s=24x60:r=25:d=4",
                    "-filter_complex", "[0][1]overlay=x='40+150*t':y=150", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(bar)], check=True)

    def centres(path):
        raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-vf", "format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        rows = np.frombuffer(raw, np.uint8).reshape(-1, 360, 640)[:, 170:200, :].astype(float).mean(axis=1)
        return np.array([(r * np.arange(640)).sum() / max(r.sum(), 1) for r in rows])
    out = code_engine.cadence_proxy(bar, {"sha256": "d" * 64}, 1.0, 40, rate=.4)
    assert code_engine.cadence_decision(out)["mode"] == "flow"
    c = centres(out)
    assert len(c) == 40 and abs(c[0] - (52 + 150 * 1.0)) <= 3  # frame 0 shows source time 1.0 s
    steps = np.diff(c)
    assert steps.min() > 1 and steps.max() < 3 and abs(steps.mean() - 2) < .15  # never held, never jumping
    near = code_engine.cadence_proxy(bar, {"sha256": "d" * 64}, 1.0, 40)  # the 1x proxy keeps its own cache entry
    assert near != out and len(centres(near)) == 40


def test_a_conformed_clip_loses_its_repeats_before_interpolation(tmp_path, monkeypatch):
    """A 25 fps clip conformed to 30 fps by duplication repeats every sixth frame inside a file that reads 30 fps (round 13:
    archive re-broadcasts). The proxy drops the repeats and interpolates between true frames: the bar moves every frame."""
    from editvideo import code_engine, review
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    src = tmp_path / "bar25.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=25:d=4", "-f", "lavfi", "-i", "color=c=white:s=24x60:r=25:d=4",
                    "-filter_complex", "[0][1]overlay=x='40+150*t':y=150", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(src)], check=True)
    conf = tmp_path / "bar30.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-vf", "fps=30", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(conf)], check=True)
    assert review.repeated_frames(str(conf), 1.0) > .12 and review.repeated_frames(str(src), 1.0) < .02

    def steps(path):
        raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-vf", "format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        rows = np.frombuffer(raw, np.uint8).reshape(-1, 360, 640)[:, 170:200, :].astype(float).mean(axis=1)
        return np.diff([(r * np.arange(640)).sum() / max(r.sum(), 1) for r in rows])
    plain = steps(code_engine.cadence_proxy(conf, {"sha256": "e" * 64}, 1.0, 40))  # 30 fps file, no dedupe: the repeats stay
    fixed = steps(code_engine.cadence_proxy(conf, {"sha256": "e" * 64}, 1.0, 40, dedupe=True))
    assert plain.min() < .5  # a held frame
    assert fixed.min() > 2.5 and abs(fixed.mean() - 5) < .3  # 150 px/s at 30 fps, every frame moving


def test_a_deduped_proxy_keeps_its_length_when_the_shot_ends_still(tmp_path, monkeypatch):
    """The last second of this conformed clip is still: mpdecimate drops all of it as repeats, and without padding the
    interpolated proxy would end early (the render's still at the shot's end then has no frame)."""
    from editvideo import code_engine
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    src = tmp_path / "stop25.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=25:d=3", "-f", "lavfi", "-i", "color=c=white:s=16x40:r=25:d=3",
                    "-filter_complex", "[0][1]overlay=x='20+40*min(t,1.5)':y=70,fps=30", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(src)], check=True)
    # 1.0-3.0 s: moves until 1.5 s (slowly enough to interpolate: a fast one plays its own frames), then still
    out = code_engine.cadence_proxy(src, {"sha256": "a" * 64}, 1.0, 60, dedupe=True)
    n = subprocess.run([FFPROBE, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(out)],
                       capture_output=True, text=True).stdout.strip()
    assert int(n) == 60
