"""Round 13, American war-film and documentary craft as checks (docs/PRO_WORKFLOWS.md §31): builds pay off, effect tails
ring out, and footage is not shaken by effects; the render-level shake reading tells a jittered picture from a still one."""
import sys, wave
from pathlib import Path
import numpy as np
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from editvideo import audiofx, agent, store, review
from editvideo.media import FFMPEG, command

clip = lambda i, a, b, **k: {"id": i, "asset_id": "s", "start_frame": a, "end_frame": b, **k}


def _codes(monkeypatch, clips, assets=()):
    t = {"total_frames": 6000, "shots": [{"id": "s1", "start_frame": 0, "end_frame": 6000}], "audio_clips": clips}
    monkeypatch.setattr(agent, "read", lambda pid: {"timeline": t})
    monkeypatch.setattr(store, "assets", lambda pid: list(assets))
    return {(f["code"], f["where"] if isinstance(f["where"], str) else f["where"][0]) for f in audiofx.audit("p")["findings"]}


def test_a_siren_that_fades_away_is_a_promise_not_kept(monkeypatch):
    codes = _codes(monkeypatch, [clip("siren-1972", 300, 600, fade_out=1.5), clip("bomb-hit", 900, 990)])
    assert ("build_without_payoff", "siren-1972") in codes
    codes = _codes(monkeypatch, [clip("siren-1972", 300, 600, fade_out=0), clip("bomb-hit", 600, 690)])
    assert not any(c == "build_without_payoff" for c, _ in codes)


def test_builds_are_short_and_spaced(monkeypatch):
    codes = _codes(monkeypatch, [clip("siren-a", 0, 450), clip("impact-a", 450, 480), clip("heartbeat-b", 600, 1200), clip("blast-b", 1200, 1260),
                                 clip("clock-c", 3000, 3150), clip("impact-c", 3150, 3180)])
    assert ("build_too_long", "siren-a") in codes          # 15 s siren
    assert ("build_too_long", "heartbeat-b") not in codes  # a 20 s pulse bed is within its 30 s
    assert ("builds_too_close", "siren-a") in codes        # 25 s between the two releases
    assert ("builds_too_close", "heartbeat-b") not in codes  # the third resolves 65 s later


def _tone(path, seconds, decay_s):
    t = np.arange(int(seconds * 8000)) / 8000
    x = (np.random.default_rng(1).standard_normal(len(t)) * np.exp(-t / decay_s) * .5 * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(x.tobytes())
    return str(path)


def test_an_explosion_cut_while_ringing_is_flagged(monkeypatch, tmp_path):
    p = _tone(tmp_path / "blast.wav", 8, 1.5)  # rings for seconds
    assets = [{"id": "s", "path": p}]
    codes = _codes(monkeypatch, [clip("bomb-a", 0, 24, fade_out=.15)], assets)        # 0.8 s of an 8 s blast
    assert ("sfx_tail_cut", "bomb-a") in codes
    codes = _codes(monkeypatch, [clip("bomb-a", 0, 210, fade_out=1.2)], assets)       # the tail plays and fades
    assert not any(c == "sfx_tail_cut" for c, _ in codes)
    codes = _codes(monkeypatch, [clip("music-a", 0, 24, role="music")], assets)       # music edits are not effects
    assert not any(c == "sfx_tail_cut" for c, _ in codes)


def test_added_shake_on_footage_is_flagged_not_on_graphics(monkeypatch):
    from editvideo.models import Shot
    fx = lambda n, a: {"name": n, "start_frame": 0, "end_frame": 10, "params": {"amount": a}}
    shots = [Shot(id="war", beat_id="b", start_frame=0, end_frame=60, asset_id="v").model_dump(),
             Shot(id="weave", beat_id="b", start_frame=60, end_frame=120, asset_id="v").model_dump(),
             Shot(id="card", beat_id="b", start_frame=120, end_frame=180, asset_id="i").model_dump()]
    shots[0]["effects"] = [fx("impact_shake", 28)]
    shots[1]["effects"] = [fx("gate_weave", .4)]
    shots[2]["effects"] = [fx("impact_shake", 28)]
    t = {"width": 1920, "height": 1080, "total_frames": 180, "shots": shots, "layers": [], "audio_clips": [], "design": {}, "cues": []}
    monkeypatch.setattr(agent, "read", lambda pid: {"timeline": t, "revision": 1})
    monkeypatch.setattr(store, "assets", lambda pid: [{"id": "v", "kind": "video", "path": "v.mp4", "width": 1920, "height": 1080, "duration": 10},
                                                      {"id": "i", "kind": "image", "path": "i.png", "width": 1920, "height": 1080}])
    f = [x for x in review.audit_timeline("p", t)["findings"] if x["code"] == "added_shake"]
    assert len(f) == 1 and f[0]["where"]["shots"] == ["war"] and f[0]["evidence"]["max_pp_percent"] > 3


def _jitter_video(path, amp_px):
    """A textured still moved by a random per-frame offset of up to +-amp_px (1080p reference), 2 s at 30 fps."""
    rng = np.random.default_rng(3)
    tex = (rng.random((360, 640)) * 255).astype(np.uint8)
    import cv2
    tex = cv2.GaussianBlur(tex, (0, 0), 2)
    frames = []
    for k in range(60):
        dx, dy = rng.uniform(-amp_px, amp_px, 2) / 3  # 1080p px -> 360p px
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        frames.append(cv2.warpAffine(tex, M, (640, 360), borderMode=cv2.BORDER_REFLECT))
    raw = path.with_suffix(".gray")
    raw.write_bytes(b"".join(f.tobytes() for f in frames))
    command([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "640x360", "-r", "30", "-i", str(raw),
             "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(path)])
    return path


def test_shake_profile_reads_jitter_from_pixels(tmp_path):
    shot = [{"id": "s", "start_frame": 0, "end_frame": 60}]
    still = review.shake_profile(_jitter_video(tmp_path / "still.mp4", 0), shot)[0]["shake_pp_percent"]
    shaky = review.shake_profile(_jitter_video(tmp_path / "shaky.mp4", 12), shot)[0]["shake_pp_percent"]
    assert still < .1 and shaky > 1.0


def test_a_build_may_end_in_a_held_silence_before_the_hit(monkeypatch):
    held = [clip("heartbeat-1975", 300, 600), clip("room-hush", 590, 640, role="ambience"), clip("braam-1975", 635, 700)]
    assert not any(c == "build_without_payoff" for c, _ in _codes(monkeypatch, held))
    filled = held + [clip("crowd-a", 610, 700)]  # the 'silence' is not silent
    assert ("build_without_payoff", "heartbeat-1975") in _codes(monkeypatch, filled)


def test_a_steadied_clip_keeps_its_sound(tmp_path, monkeypatch):
    """A steadied statement keeps its voice: the source's audio for the window is muxed into the result."""
    import subprocess, cv2
    from editvideo import media_tasks
    from editvideo.footage_pro import stabilize
    rng = np.random.default_rng(5)
    scene = cv2.GaussianBlur((rng.random((300, 440, 3)) * 255).astype(np.uint8), (0, 0), 1.5)
    video = tmp_path / "v.mp4"
    enc = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "320x180", "-r", "30", "-i", "-",
                            "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(video)], stdin=subprocess.PIPE)
    for i in range(60):
        dx, dy = int(60 + 10 * np.sin(i * 1.9)), int(60 + 7 * np.sin(i * 2.7 + 1))
        enc.stdin.write(np.ascontiguousarray(scene[dy:dy + 180, dx:dx + 320]).tobytes())
    enc.stdin.close(); enc.wait()
    clip = tmp_path / "with_sound.mp4"
    command([FFMPEG, "-y", "-v", "error", "-i", str(video), "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "copy", "-c:a", "aac", "-shortest", str(clip)])
    out = tmp_path / "task"; out.mkdir()
    monkeypatch.setattr(media_tasks, "folder", lambda tid: out)
    monkeypatch.setattr(media_tasks, "check", lambda tid: None)
    monkeypatch.setattr(media_tasks, "update", lambda tid, **kw: None)
    r = stabilize("t", {"path": str(clip), "mode": "smooth"})
    kinds = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", r["video"]], capture_output=True, text=True).stdout.split()
    assert kinds == ["video", "audio"] and r["report"]["source_audio"] is True
    r = stabilize("t", {"path": str(video), "mode": "smooth"})  # a silent source stays silent
    assert r["report"]["source_audio"] is False


def test_a_documentary_can_carry_its_sound_design():
    """A 14 minute documentary used ~150 clips (narration, reporters, songs, music, effects with tails, ambience)."""
    from editvideo.models import Timeline
    assert any(getattr(m, "max_length", 0) >= 300 for m in Timeline.model_fields["audio_clips"].metadata)


def _logo_video(path, logo=True):
    """Moving texture (a pan) with a static white mark in the bottom-right corner, 2 s at 30 fps, 640x360."""
    import cv2
    rng = np.random.default_rng(2)
    tex = cv2.GaussianBlur((rng.random((420, 900)) * 255).astype(np.uint8), (0, 0), 2)
    raw = path.with_suffix(".gray")
    with open(raw, "wb") as fh:
        for k in range(60):
            f = np.ascontiguousarray(tex[20:380, 4 * k:4 * k + 640])
            if logo:
                cv2.rectangle(f, (540, 300), (610, 330), 255, 2)
                cv2.putText(f, "TV", (552, 324), cv2.FONT_HERSHEY_SIMPLEX, .7, 255, 2)
            fh.write(f.tobytes())
    command([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "640x360", "-r", "30", "-i", str(raw),
             "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(path)])
    return path


def test_a_burned_in_corner_logo_is_found_and_removed(tmp_path):
    from editvideo import overlays
    r = overlays.find(_logo_video(tmp_path / "logo.mp4"))
    assert len(r["boxes"]) == 1
    x0, y0, x1, y1 = r["boxes"][0]
    assert x0 < 540 / 640 < 610 / 640 < x1 and y0 < 300 / 360 < 330 / 360 < y1
    assert overlays.find(_logo_video(tmp_path / "clean.mp4", logo=False))["boxes"] == []
    out = overlays.clean(tmp_path / "logo.mp4", tmp_path / "cleaned.mp4", r["boxes"])
    assert out["filter"].startswith("delogo=") and overlays.find(out["path"])["boxes"] == []


def test_a_cut_inside_a_shot_is_not_read_as_shake(tmp_path):
    """Archive clips often hold a cut; the jump between two takes is not camera motion."""
    import cv2
    rng = np.random.default_rng(4)
    a = cv2.GaussianBlur((rng.random((360, 640)) * 255).astype(np.uint8), (0, 0), 2)
    b = cv2.GaussianBlur((rng.random((360, 640)) * 255).astype(np.uint8), (0, 0), 2)
    raw = tmp_path / "cut.gray"
    raw.write_bytes(b"".join((a if k < 30 else b).tobytes() for k in range(60)))
    path = tmp_path / "cut.mp4"
    command([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "640x360", "-r", "30", "-i", str(raw),
             "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(path)])
    r = review.shake_profile(path, [{"id": "s", "start_frame": 0, "end_frame": 60}])
    assert r and r[0]["shake_pp_percent"] < .1


def test_a_layered_build_is_judged_where_its_last_layer_ends(monkeypatch):
    chain = [clip("siren-1972", 300, 500), clip("clock-1972", 350, 600), clip("Shepard-1972", 420, 600), clip("impact-sam", 600, 630),
             clip("amb-city-sirens", 0, 1200, role="ambience")]
    codes = _codes(monkeypatch, chain)
    assert not any(c in ("build_without_payoff", "build_too_long") for c, _ in codes)  # the siren hands over to the clock
    codes = _codes(monkeypatch, chain[:3] + [clip("impact-sam", 700, 730)])
    assert any(c == "build_without_payoff" for c, _ in codes)


def test_tail_reading_follows_playback_rate_and_ignores_steady_beds(monkeypatch, tmp_path):
    import wave
    t = np.arange(8000 * 3) / 8000
    x = np.where(t < 1.0, .5, 0.0) * np.random.default_rng(3).standard_normal(len(t))
    burst = tmp_path / "burst.wav"
    with wave.open(str(burst), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes((x * 32767).astype("<i2").tobytes())
    assets = [{"id": "s", "path": str(burst)}]
    # 0.8 s at 2x reads 1.6 s of source: the cut falls in the silence, nothing rings
    assert not any(c == "sfx_tail_cut" for c, _ in _codes(monkeypatch, [clip("blast-a", 0, 24, playback_rate=2.0, fade_out=.1)], assets))
    steady = tmp_path / "steady.wav"
    _tone(steady, 8, 1000.0)  # no decay: a bed, not a transient
    assert not any(c == "sfx_tail_cut" for c, _ in _codes(monkeypatch, [clip("projector-open", 0, 90, fade_out=.4)], [{"id": "s", "path": str(steady)}]))


def test_retime_can_play_a_moment_backwards(tmp_path, monkeypatch):
    """A Burns-style open runs archive backwards (bombs rising into the bay): the last source frame comes first."""
    import subprocess
    from editvideo import media_tasks
    from editvideo.retime import process
    raw = tmp_path / "ramp.gray"
    raw.write_bytes(b"".join(bytes([k * 8]) * (64 * 48) for k in range(30)))  # brightness rises frame by frame
    src = tmp_path / "ramp.mp4"
    command([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "64x48", "-r", "30", "-i", str(raw),
             "-c:v", "libx264", "-crf", "1", "-pix_fmt", "yuv420p", str(src)])
    out = tmp_path / "task"; out.mkdir()
    monkeypatch.setattr(media_tasks, "folder", lambda tid: out)
    monkeypatch.setattr(media_tasks, "check", lambda tid: None)
    monkeypatch.setattr(media_tasks, "update", lambda tid, **kw: None)
    r = process("t", {"path": str(src), "speed": 1.0, "interpolation": "nearest", "reverse": True})
    mean = lambda t: float(np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", r["video"], "-frames:v", "1", "-f", "rawvideo",
                                                         "-pix_fmt", "gray", "-"], capture_output=True).stdout, np.uint8).mean())
    assert mean(0) > mean(.8) + 100 and r["report"]["reverse"] is True


def test_music_dips_under_a_dialogue_clip_and_swells_back(tmp_path, monkeypatch):
    """A silent project's narrator lives in dialogue clips: music marked duck_under_voice dips under them (the voice bus is the
    narration track plus every dialogue clip) and comes back up in the pause, so the score can breathe between lines."""
    import shutil
    from editvideo import renderer
    from editvideo.jobs import Worker
    from test_agent import planned
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.initialize()
    pid = planned()
    music, voice = tmp_path / "music.wav", tmp_path / "voice.wav"
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000:duration=3", str(music)])
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000:duration=1", "-af", "volume=4", str(voice)])
    am, av = agent.import_media(pid, str(music)), agent.import_media(pid, str(voice))
    Worker().run(store.create_job(pid, "plan")["id"])  # importing media makes the plan stale
    p = agent.read(pid)
    T = p["timeline"]["total_frames"]
    a, b = round(T * .35), round(T * .6)
    ops = [{"op": "upsert_audio", "audio": {"id": "score", "asset_id": am["id"], "start_frame": 0, "end_frame": min(T, 90), "volume": .5, "fade_in": .01, "fade_out": .01,
                                            "duck_under_voice": True, "role": "music", "ducking": {"threshold": .02, "ratio": 6, "attack_ms": 20, "release_ms": 300}}},
           {"op": "upsert_audio", "audio": {"id": "narrator", "asset_id": av["id"], "start_frame": a, "end_frame": min(b, a + 30), "volume": 1, "fade_in": .01, "fade_out": .01,
                                            "duck_under_voice": False, "role": "dialogue"}}]
    result = agent.patch(pid, p["revision"], ops)
    work = tmp_path / "mix-duck"; work.mkdir()
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(result["timeline"]["total_frames"] / 30), str(work / "voice.wav")])
    store.write_json(work / "timeline.json", result["timeline"])
    renderer.mix_audio(pid, p["config"], work, result["timeline"]["total_frames"] / 30, lambda: False)
    with wave.open(str(work / "mix.wav")) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, 2).mean(axis=1)

    def at_1k(t):
        s = x[round(t * 48000):round((t + .2) * 48000)]
        f = np.abs(np.fft.rfft(s * np.hanning(len(s))))
        return f[200]  # 1000 Hz bin at 5 Hz resolution
    e = min(T, 90) / 30
    before, during, after = at_1k(a / 30 - .45), at_1k((a + min(b, a + 30)) / 60 - .1), at_1k(min(b, a + 30) / 30 + .6)
    assert e > min(b, a + 30) / 30 + .85
    assert during < before / 2.5 and after > during * 2.5  # about 8 dB under the voice, back up within a second


def test_a_talking_head_out_of_sync_with_its_own_voice_is_flagged(monkeypatch):
    """The third cut put McNamara's words 5.3 s ahead of his face (the voice began over B-roll, the face shot restarted its
    source) and shot fitting slowed two talking heads to fill their spans: picture and sound of one recording must agree."""
    from editvideo.models import Shot
    shots = [Shot(id="broll", beat_id="b", start_frame=0, end_frame=150, asset_id="w").model_dump(),
             Shot(id="face", beat_id="b", start_frame=150, end_frame=450, asset_id="v", source_start=.3).model_dump(),
             Shot(id="slow", beat_id="b", start_frame=450, end_frame=750, asset_id="u", source_start=0.0, playback_rate=.95).model_dump(),
             Shot(id="ok", beat_id="b", start_frame=750, end_frame=1050, asset_id="x", source_start=5.0).model_dump()]
    clip = lambda i, aid, a, b, src: {"id": i, "asset_id": aid, "start_frame": a, "end_frame": b, "source_start": src, "volume": 1, "fade_in": .05,
                                      "fade_out": .1, "duck_under_voice": False, "role": "dialogue", "playback_rate": 1}
    t = {"width": 1920, "height": 1080, "total_frames": 1050, "shots": shots, "layers": [], "design": {}, "cues": [],
         "audio_clips": [clip("voice-face", "v", 10, 440, .3), clip("voice-slow", "u", 450, 740, 0.0), clip("voice-ok", "x", 760, 1040, 5.333)]}
    monkeypatch.setattr(agent, "read", lambda pid: {"timeline": t, "revision": 1})
    monkeypatch.setattr(store, "assets", lambda pid: [{"id": k, "kind": "video", "path": f"{k}.mp4", "width": 1920, "height": 1080, "duration": 60}
                                                      for k in "wvux"])
    f = {x["where"]["shot"]: x for x in review.audit_timeline("p", t)["findings"] if x["code"] == "av_sync"}
    assert set(f) == {"face", "slow"}
    assert f["face"]["evidence"]["sound_lead_s"][0] == pytest.approx(4.667, abs=.01)  # 140 frames of B-roll ahead
    assert f["slow"]["evidence"]["picture_rate"] == .95


def test_a_dialogue_bed_still_ducks_under_the_narration(tmp_path, monkeypatch):
    """An interview bed (dialogue, duck_under_voice) under the narration track dips as before the voice bus existed, and does
    not key the music with itself while it is ducked."""
    from editvideo import renderer
    from editvideo.jobs import Worker
    from test_agent import planned
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.initialize()
    pid = planned()
    bed = tmp_path / "bed.wav"
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=700:sample_rate=48000:duration=3", str(bed)])
    ab = agent.import_media(pid, str(bed))
    Worker().run(store.create_job(pid, "plan")["id"])
    p = agent.read(pid)
    T = p["timeline"]["total_frames"]
    ops = [{"op": "upsert_audio", "audio": {"id": "interview-bed", "asset_id": ab["id"], "start_frame": 0, "end_frame": min(T, 90), "volume": .5, "fade_in": .01,
                                            "fade_out": .01, "duck_under_voice": True, "role": "dialogue",
                                            "ducking": {"threshold": .01, "ratio": 8, "attack_ms": 10, "release_ms": 200}}}]
    result = agent.patch(pid, p["revision"], ops)
    work = tmp_path / "mix-bed"; work.mkdir()
    a, b = round(T * .4), round(T * .6)
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=300:sample_rate=48000:duration={T / 30}", "-af",
             f"volume='if(between(t,{a / 30},{b / 30}),4,0)':eval=frame", str(work / "voice.wav")])
    store.write_json(work / "timeline.json", result["timeline"])
    renderer.mix_audio(pid, p["config"], work, T / 30, lambda: False)
    with wave.open(str(work / "mix.wav")) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, 2).mean(axis=1)

    def at_700(t0):
        s = x[round(t0 * 48000):round((t0 + .2) * 48000)]
        return np.abs(np.fft.rfft(s * np.hanning(len(s))))[140]  # 700 Hz bin at 5 Hz resolution
    assert at_700((a + b) / 60 - .1) < at_700(a / 30 - .4) / 2.5  # the bed dips while the narrator speaks


def test_a_clip_can_ask_for_its_own_loudness_target(monkeypatch):
    """A score that ducks under every voice sits near -22 LUFS instead of the -30 of a bed that never moves."""
    from editvideo import renderer
    monkeypatch.setattr(renderer, "clip_level", lambda path, start, seconds: (-34.0, -12.0))
    monkeypatch.setattr(renderer, "safe_asset_path", lambda pid, aid: "x.wav")
    c = {"asset_id": "m", "source_start": 0, "playback_rate": 1, "normalize": True, "role": "music"}
    assert renderer.role_gain_db("p", c, 10) == pytest.approx(4.0)            # role default -30
    assert renderer.role_gain_db("p", {**c, "target_lufs": -22}, 10) == pytest.approx(12.0)


def test_a_punch_in_clears_each_mark_and_keeps_the_free_axis_centred():
    from editvideo import overlays
    z = overlays.zoom_past([[.955, 0, 1, .07]], margin=.04)  # a corner mark top right: cleared sideways, height untouched
    assert z == {"amount": pytest.approx(.093, abs=.002), "focus_x": 0.0, "focus_y": .5, "cut": True}
    z = overlays.zoom_past([[.74, .09, .93, .23]], margin=.04)  # a wide logo high up: cleared by height, centred across
    assert z["focus_y"] == 1.0 and z["focus_x"] == .5 and 1 / (1 + z["amount"]) <= 1 - .23 - .04 + 1e-3
    z = overlays.zoom_past([[0, 0, .06, .07], [.9, .9, 1, 1]])  # opposite corners: no axis is free
    assert z["focus_x"] in (0.0, 1.0) and z["focus_y"] in (0.0, 1.0)


def _still(path, seed, logo=True):
    """One second of a still textured frame (a different scene per seed), optionally with a white mark top right."""
    import cv2
    f = cv2.GaussianBlur((np.random.default_rng(seed).random((360, 640)) * 255).astype(np.uint8), (0, 0), 3)
    if logo:
        cv2.rectangle(f, (560, 20), (624, 50), 255, 2)
        cv2.putText(f, "TV", (572, 44), cv2.FONT_HERSHEY_SIMPLEX, .7, 255, 2)
    raw = path.with_suffix(".gray")
    raw.write_bytes(np.ascontiguousarray(f).tobytes() * 30)
    command([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "640x360", "-r", "30", "-i", str(raw),
             "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(path)])
    return path


def test_a_mark_on_still_clips_is_found_by_pooling_a_sources_clips(tmp_path):
    """One still clip cannot tell a logo from the scene; three clips of the same channel can, and each clip is then tested."""
    from editvideo import overlays
    clips = [_still(tmp_path / f"c{k}.mp4", k) for k in range(3)]
    r = overlays.find_family(clips, samples_per_clip=6)
    assert len(r["boxes"]) == 1
    x0, y0, x1, y1 = r["boxes"][0]
    assert x0 < 570 / 640 and x1 > 615 / 640 and y0 < 25 / 360 and y1 > 45 / 360
    assert overlays.present(_still(tmp_path / "d.mp4", 7), r["boxes"][0], r)
    assert not overlays.present(_still(tmp_path / "e.mp4", 8, logo=False), r["boxes"][0], r)


def _black_mid(path):
    """Three seconds of grey with a black run from 1.0 to 1.5 s (a cut through black inside an archive clip)."""
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x808080:s=320x180:d=3:r=30", "-vf",
             "drawbox=enable='between(t,1,1.5)':x=0:y=0:w=iw:h=ih:color=black:t=fill", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])
    return str(path)


def test_a_shot_is_moved_off_a_black_run_in_its_file(tmp_path, monkeypatch):
    p = _black_mid(tmp_path / "b.mp4")
    runs = review.black_runs(p)
    assert len(runs) == 1 and runs[0][0] == pytest.approx(1.0, abs=.05) and runs[0][1] == pytest.approx(1.5, abs=.05)
    s0 = review.avoid_black(.8, 1.0, runs, 3.0)
    assert not any(a < s0 + 1.0 and b > s0 for a, b in runs)
    assert review.avoid_black(.5, 2.6, runs, 3.0) == .5  # no clear 2.6 s window: left for black_in_shots to report
    monkeypatch.setattr(store, "assets", lambda pid: [{"id": "v", "kind": "video", "path": p}])
    t = {"shots": [{"id": "a", "asset_id": "v", "start_frame": 0, "end_frame": 45, "source_start": .5},
                   {"id": "b", "asset_id": "v", "start_frame": 45, "end_frame": 75, "source_start": 1.8}]}
    found = review.black_in_shots("p", t)
    assert [f["shot"] for f in found] == ["a"] and found[0]["black"][0][0] == pytest.approx(.5, abs=.05)


def test_silence_and_a_voice_buried_under_effects_are_reported(monkeypatch):
    def codes(clips):
        t = {"total_frames": 900, "timing_method": "silent", "shots": [{"id": "s1", "start_frame": 0, "end_frame": 900}], "audio_clips": clips}
        monkeypatch.setattr(agent, "read", lambda pid: {"timeline": t})
        monkeypatch.setattr(store, "assets", lambda pid: [])
        return {f["code"] for f in audiofx.audit("p")["findings"]}
    vo = clip("vo-a", 0, 300, role="dialogue", volume=1.0)
    room = clip("room-a", 0, 300, role="ambience", volume=.6)
    c = codes([vo, room, clip("music-b", 600, 900, role="music", volume=1.0)])
    assert {"uncovered_gap", "undimmed_under_voice"} <= c  # 10 s of nothing under a card; room tone at full level under a voice
    c = codes([vo, {**room, "duck_under_voice": True}, clip("drone-c", 290, 610, role="ambience", volume=.6), clip("music-b", 600, 900, role="music", volume=1.0)])
    assert not {"uncovered_gap", "undimmed_under_voice"} & c
