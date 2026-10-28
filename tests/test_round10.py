"""Round 10: effect combinations for attractive edits - music-driven accents, impact effects that read on footage,
speed ramps around action peaks, freeze frames, combos in one call, split screens, clip ranking and match cuts."""
import json
import subprocess
from pathlib import Path
import numpy as np
import pytest
from editvideo import store
from editvideo.media import FFMPEG

ENGINES_READY = (Path(__file__).parents[1] / "engines" / "node_modules").is_dir()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.initialize()
    return tmp_path


def _clip(path, src, seconds=3):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", src, "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_peak_ramps_become_s_curve_speed_keys():
    from editvideo.retime import RetimeRequest, speed_at
    q = RetimeRequest(path="x", start=0, end=20, speed=2.5, peaks=[6.0], peak_speed=.25, ramp_s=.35, hold_s=.6)
    assert [(k.at, k.speed) for k in q.speed_keys] == [(5.35, 2.5), (5.7, .25), (6.3, .25), (6.65, 2.5)]
    assert speed_at(q, 6.0) == pytest.approx(.25) and speed_at(q, 3.0) == pytest.approx(2.5)
    close = RetimeRequest(path="x", start=0, end=20, speed=2, peaks=[6.0, 6.8])  # ramps overlap: stays slow between them
    assert all(k.speed < 2 for k in close.speed_keys if 6.0 <= k.at <= 6.8)
    with pytest.raises(ValueError):
        RetimeRequest(path="x", peaks=[1.0], speed_keys=[{"at": 0, "speed": 1}])
    later = RetimeRequest(path="x", start=10, end=14, speed=1, peaks=[12.0], peak_speed=.3, ramp_s=.3, hold_s=.6)  # peaks are source time
    assert [k.at for k in later.speed_keys] == [1.4, 1.7, 2.3, 2.6]  # keys count from start
    assert RetimeRequest.model_validate(later.model_dump()).speed_keys == later.speed_keys  # the worker re-validates the stored request
    with pytest.raises(ValueError):
        RetimeRequest(path="x", start=10, end=14, peaks=[2.0])


def _project(workspace, engine="remotion", seconds=None, frames=120):
    from editvideo import agent
    clip = _clip(workspace / "src.mp4", "testsrc2=s=640x360:r=30", seconds or frames / 30 + 1)  # longer than the timeline
    pid = agent.create_silent("landscape", frames, engine, "r10")["id"]
    aid = agent.import_media(pid, str(clip), "src", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
    p = agent.read(pid)
    t = p["timeline"]
    t["shots"] = [{**t["shots"][0], "asset_id": aid, "fit": "cover", "source_start": 0, "text": "", "motion": "hold"}]
    agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
    return pid, aid


def test_freeze_frame_holds_then_resumes_where_it_paused(workspace):
    from editvideo import agent
    pid, _ = _project(workspace)
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "freeze_frame", "at": 30, "frames": 20, "zoom": .1}])
    sh = agent.read(pid)["timeline"]["shots"]
    assert [(s["start_frame"], s["end_frame"], s.get("freeze")) for s in sh] == [(0, 30, False), (30, 50, True), (50, 120, False)]
    assert sh[1]["source_start"] == sh[2]["source_start"] == pytest.approx(1.0)  # the action continues from the paused frame
    assert {e["name"] for e in sh[1]["effects"]} == {"white_flash", "focus_zoom"} and sh[1]["motion"] == "hold"  # a still does not re-push
    with pytest.raises(ValueError):
        agent.patch(pid, agent.read(pid)["revision"], [{"op": "freeze_frame", "at": 110, "frames": 20}])
    looked, _ = _project(workspace)  # the shot's look survives the split, on every part
    t = agent.read(looked)["timeline"]
    t["shots"][0]["effects"] = [{"name": "vignette", "start_frame": 0, "end_frame": 119, "params": {"amount": .3}}]
    agent.patch(looked, agent.read(looked)["revision"], [{"op": "replace_timeline", "timeline": t}])
    agent.patch(looked, agent.read(looked)["revision"], [{"op": "freeze_frame", "at": 40, "frames": 20}])
    parts = agent.read(looked)["timeline"]["shots"]
    assert all(any(e["name"] == "vignette" for e in x["effects"]) for x in parts)
    assert [next(e for e in x["effects"] if e["name"] == "vignette")["end_frame"] for x in parts] == [39, 19, 59]
    t = agent.read(pid)["timeline"]  # a held last frame: a freeze needs only its one source frame, not the shot's span
    t["shots"][-1] = {**t["shots"][-1], "freeze": True, "source_start": 4.9}
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "replace_timeline", "timeline": t}])


def test_apply_combo_stacks_a_curated_look_in_one_operation(workspace):
    from editvideo import agent
    from editvideo.effect_guide import COMBOS
    pid, _ = _project(workspace)
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "apply_combo", "target": agent.read(pid)["timeline"]["shots"][0]["id"],
                                                    "combo": "documentary_push", "start_frame": 0, "end_frame": 100}])
    eff = agent.read(pid)["timeline"]["shots"][0]["effects"]
    assert [e["name"] for e in eff] == [e["name"] for e in COMBOS["documentary_push"]["stack"]]
    with pytest.raises(ValueError):
        agent.patch(pid, agent.read(pid)["revision"], [{"op": "apply_combo", "target": "nope", "combo": "documentary_push"}])


def test_split_screen_lays_out_panels(workspace):
    from editvideo import agent, professional
    pid, aid = _project(workspace)
    r = professional.compose(pid, agent.read(pid)["revision"], {"recipe": "split_screen", "start_frame": 0, "end_frame": 90, "asset_ids": [aid, aid],
                                                                 "source_starts": [0, 1.0]}, dry_run=True)
    panels = [o["layer"] for o in r["operations"] if o["op"] == "upsert_layer" and "panel" in o["layer"]["id"]]
    assert len(panels) == 2 and panels[0]["x"] < .5 <= panels[1]["x"]  # landscape: side by side
    assert panels[1]["source_start"] == 1.0 and all(p["fit"] == "cover" for p in panels)


def _beat_music(workspace, bpm=120, seconds=16):
    from editvideo import sound
    r = sound.design("beat", float(seconds), 3, -12, bpm)
    return r["path"]


def test_accent_sync_places_a_budgeted_hierarchy(workspace):
    from editvideo import agent, accents
    pid, _ = _project(workspace, frames=450)
    music = _beat_music(workspace, 120, 15)
    t = agent.read(pid)["timeline"]
    sh = t["shots"][0]
    t["shots"] = [{**sh, "id": f"s{k}", "start_frame": k * 60, "end_frame": min(450, k * 60 + 60), "source_start": 0} for k in range(8)]
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "replace_timeline", "timeline": t}])
    r = accents.sync(pid, agent.read(pid)["revision"], {"style": "velocity", "music_path": music, "drops": [8.0], "sfx": False})
    frames = [x["frame"] for x in r["placed"]]
    assert r["counts"]["drop"] == 1 and 240 in r["drops"]  # 8 s on frame 240, snapped onto the cut there
    assert all(b - a >= 8 for a, b in zip(sorted(frames), sorted(frames)[1:]))
    drop = next(x for x in r["placed"] if x["level"] == "drop")
    assert drop["effects"] == ["white_flash", "impact_shake", "chroma_split"]
    assert r["counts"]["beat"] <= 450 / 60 + 1  # at most one beat accent per bar (2 s at 120 BPM)
    again = accents.sync(pid, r["revision"], {"style": "velocity", "music_path": music, "drops": [8.0], "sfx": False})
    t2 = agent.read(pid)["timeline"]
    n_acc = sum(1 for s in t2["shots"] for e in s.get("effects") or [] if (e.get("params") or {}).get("accent"))
    assert n_acc == sum(len(x["effects"]) for x in again["placed"])  # a re-run replaces, never stacks
    late = accents.sync(pid, again["revision"], {"style": "velocity", "music_path": music, "drops": [40.0], "dry_run": True})
    assert late["counts"]["drop"] == 0 and "music-file seconds" in late["skipped"][0]["reason"]  # outside the edit: reported, not a crash
    calm = accents.sync(pid, again["revision"], {"style": "nature", "music_path": music, "sfx": False, "dry_run": True})
    assert not calm["placed"] and "wildlife" in calm["note"]


def test_rank_clips_prefers_motion_and_suggests_cross_clip_match_cuts(workspace):
    from editvideo import clips
    still = _clip(workspace / "still.mp4", "color=c=gray:s=320x180:r=30", 4)
    moving = _clip(workspace / "moving.mp4", "testsrc2=s=320x180:r=30", 4)
    pan = _clip(workspace / "pan.mp4", "testsrc2=s=640x180:r=30,crop=320:180:'t*80':0", 4)
    mute = workspace / "mute.mp4"  # a picture with a silent sound track, as many Commons uploads have
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                    "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(mute)], check=True)
    r = clips.rank([str(still), str(moving), str(pan), str(mute)], 2.0, 8, True)
    assert Path(r["windows"][0]["path"]).name in ("moving.mp4", "pan.mp4", "mute.mp4") and Path(r["windows"][-1]["path"]).name == "still.mp4"
    assert all(p["out"]["path"] != p["in"]["path"] for p in r["match_cuts"])  # one take cut against itself is a jump cut
    assert r["audio"] == {"still": "none", "moving": "none", "pan": "none", "mute": "silent"}
    assert Path(r["sheet"]).is_file()


def test_rank_clips_finds_small_fast_action_and_a_cut_between_similar_shots(workspace):
    from editvideo import clips
    # a small square darts across a still frame at 2.5 s; at 4 s the same scene cuts to a slightly brighter take
    src = workspace / "dart.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x406040:s=320x180:r=30:d=6", "-f", "lavfi", "-i", "color=c=white:s=16x16:r=30:d=6",
                    "-filter_complex", "[0][1]overlay=x='if(between(t,2.4,2.8),(t-2.4)*600,-40)':y=80,eq=brightness='if(gte(t,4),0.12,0)':eval=frame",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    r = clips.rank([str(src)], 3.0, 4, False)
    first = next(w for w in r["windows"] if w["start"] == 0)
    assert 2.3 <= first["peak_at"] <= 2.9 and first["action"] > 0
    assert any(w["cuts_inside"] for w in r["windows"] if w["start"] < 4 < w["end"])


def test_nature_beds_run_long(workspace):
    from editvideo import sound
    for kind in ("rain", "forest"):
        r = sound.design(kind, 40.0, 3, -18)
        assert r["duration"] == pytest.approx(40.0)
    with pytest.raises(ValueError):
        sound.design("impact", 40.0)


def test_fetch_source_waits_when_rate_limited(workspace, monkeypatch):
    import io
    import urllib.error
    from editvideo import resources
    calls = []

    class Resp(io.BytesIO):
        headers = {"Content-Length": "5"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=60):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "Too many requests", {"Retry-After": "0"}, None)
        return Resp(b"hello")
    monkeypatch.setattr(resources.urllib.request, "urlopen", fake)
    monkeypatch.setattr(resources, "ROOT", workspace)
    monkeypatch.setattr(resources, "register_resource", lambda *a, **k: {"id": "x"})
    r = resources.fetch_source("https://example.org/a.mp3", "other", "t", "CC0", "c", "https://example.org", "audio", "a.mp3", 5)
    assert len(calls) == 2 and (workspace / "data" / "sources" / "other" / "a.mp3").read_bytes() == b"hello"


@pytest.mark.skipif(not ENGINES_READY, reason="Local rendering dependencies not installed")
def test_impact_effects_read_on_footage_in_both_engines(tmp_path, monkeypatch):
    from PIL import Image
    from editvideo import agent
    from editvideo.code_engine import scaffold
    from editvideo.snapshot import snapshot
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    bar = _clip(tmp_path / "bar.mp4", "color=c=black:s=640x360:r=30,drawbox=x=300:y=0:w=40:h=360:color=white:t=fill", 2)
    for engine in ("remotion", "hyperframes"):
        pid = agent.create_silent("landscape", 40, engine, "fx")["id"]
        aid = agent.import_media(pid, str(bar), "bar", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
        p = agent.read(pid)
        t = p["timeline"]
        base = {**t["shots"][0], "asset_id": aid, "fit": "cover", "source_start": 0, "text": "", "motion": "hold"}
        t["shots"] = [{**base, "id": "a", "start_frame": 0, "end_frame": 20, "effects": [{"name": "white_flash", "start_frame": 5, "end_frame": 12, "params": {"amount": 1}}]},
                      {**base, "id": "b", "start_frame": 20, "end_frame": 40, "effects": [{"name": "chroma_split", "start_frame": 5, "end_frame": 15, "params": {"amount": 18}}]}]
        agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
        scaffold(pid, engine, False)
        fr = snapshot(pid, engine, [5, 26])["frames"]
        flash = np.asarray(Image.open(fr[0]["path"]).convert("RGB"), np.float32)
        assert flash.mean() > 250  # every pixel white at the flash peak, the black ones too
        split = np.asarray(Image.open(fr[1]["path"]).convert("RGB"), np.float32)
        row = split[split.shape[0] // 2]
        edges = [int(np.argmax(row[:, c] > 128)) for c in range(3)]
        assert edges[0] < edges[1] < edges[2], (engine, edges)  # red left, blue right of the green plane


@pytest.mark.skipif(not ENGINES_READY, reason="Local rendering dependencies not installed")
def test_pushed_video_shot_moves_in_both_engines(tmp_path, monkeypatch):
    from PIL import Image
    from editvideo import agent
    from editvideo.code_engine import scaffold
    from editvideo.snapshot import snapshot
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    bar = _clip(tmp_path / "bar.mp4", "color=c=black:s=640x360:r=30,drawbox=x=260:y=0:w=120:h=360:color=white:t=fill", 2)
    widths = {}
    for engine in ("remotion", "hyperframes"):
        pid = agent.create_silent("landscape", 45, engine, "push")["id"]
        aid = agent.import_media(pid, str(bar), "bar", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
        p = agent.read(pid)
        t = p["timeline"]
        a = {**t["shots"][0], "asset_id": aid, "fit": "cover", "source_start": 0, "text": "", "effects": []}
        t["shots"] = [{**a, "id": "a", "start_frame": 0, "end_frame": 30, "motion": "push"},  # then a dissolve: the outgoing still keeps the push
                      {**a, "id": "b", "start_frame": 30, "end_frame": 45, "motion": "hold", "source_start": .5,
                       "transition": {"name": "dissolve", "duration_frames": 12}}]
        agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
        scaffold(pid, engine, False)
        fr = snapshot(pid, engine, [0, 29, 30])["frames"]
        row = lambda k: np.asarray(Image.open(fr[k]["path"]).convert("L"), np.float32)[180]
        widths[engine] = [int((row(k) > 128).sum()) for k in (0, 1, 2)]
    assert all(abs(c / b - 1) < .03 for a, b, c in widths.values()), widths  # the dissolve's first frame: the held still, still pushed
    ratio = {e: b / a for e, (a, b, c) in widths.items()}  # snapshots may differ in size; the push is relative
    assert all(r >= 1.05 for r in ratio.values()) and abs(ratio["remotion"] - ratio["hyperframes"]) < .02, widths  # ~7.5 % closer in both


@pytest.mark.skipif(not ENGINES_READY, reason="Local rendering dependencies not installed")
def test_engines_show_the_same_source_frame_off_the_30fps_grid(tmp_path, monkeypatch):
    """A 25 fps source whose every frame has its own grey level: a freeze still, a shot starting between two frames and
    the poster for its outgoing dissolve must show the same source frame in both engines."""
    from PIL import Image
    from editvideo import agent
    from editvideo.code_engine import scaffold
    from editvideo.snapshot import snapshot
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    src = tmp_path / "count.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=25:d=3", "-vf", r"geq=lum='16+mod(N*9\,220)':cb=128:cr=128",
                    "-c:v", "libx264", "-qp", "0", "-g", "1", "-pix_fmt", "yuv420p", str(src)], check=True)
    level = {}
    for engine in ("remotion", "hyperframes"):
        pid = agent.create_silent("landscape", 60, engine, "frames")["id"]
        aid = agent.import_media(pid, str(src), "count", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
        p = agent.read(pid)
        t = p["timeline"]
        base = {**t["shots"][0], "asset_id": aid, "fit": "cover", "text": "", "motion": "hold", "effects": []}
        t["shots"] = [{**base, "id": "a", "start_frame": 0, "end_frame": 20, "source_start": .25},   # frame 7.5 of the 30 fps grid
                      {**base, "id": "b", "start_frame": 20, "end_frame": 40, "source_start": 1.3, "freeze": True},
                      {**base, "id": "c", "start_frame": 40, "end_frame": 60, "source_start": .15}]  # 4.5 frames: halves round up in both
        agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
        scaffold(pid, engine, False)
        fr = snapshot(pid, engine, [0, 10, 25, 50])["frames"]
        level[engine] = [round(float(np.asarray(Image.open(f["path"]).convert("L"), np.float32)[60:120, 100:220].mean())) for f in fr]
    assert all(abs(a - b) <= 3 for a, b in zip(level["remotion"], level["hyperframes"])), level  # one source frame = 9 levels


def test_shortform_audit_tells_authored_flashes_from_cuts_and_reads_freeze_plates(workspace):
    from editvideo import agent, shortform
    src = _clip(workspace / "v.mp4", "testsrc2=s=1080x1920:r=30", 3)
    flashed = workspace / "render.mp4"  # a render with a 2-frame white flash at frame 30 and nothing else cutting
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(n,30,31)'",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(flashed)], check=True)
    pid = agent.create_silent("vertical", 90, "remotion", "flash")["id"]
    aid = agent.import_media(pid, str(src), "v", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
    p = agent.read(pid)
    t = p["timeline"]
    base = {**t["shots"][0], "asset_id": aid, "fit": "cover", "text": "", "motion": "hold"}
    t["shots"] = [{**base, "id": "a", "start_frame": 0, "end_frame": 60, "source_start": 0,
                   "effects": [{"name": "white_flash", "start_frame": 30, "end_frame": 32, "params": {"amount": 1}}]},
                  {**base, "id": "b", "start_frame": 60, "end_frame": 90, "source_start": 2.95, "freeze": True, "effects": []}]  # the clip's last frame
    t["layers"] = [{"id": "txt", "kind": "text", "text": "Hello there", "start_frame": 62, "end_frame": 90, "x": .1, "y": .3, "width": .8, "height": .1,
                    "font_size": 64, "color": "#ffffff", "z": 900}]
    agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
    plain = shortform.audit(str(flashed), None, "tiktok")
    known = shortform.audit(str(flashed), pid, "tiktok")  # reads the freeze plate at 2.95 s without seeking past the end
    codes = lambda r: {f["code"] for f in r["findings"]}
    assert "flash_cut" in codes(plain) and "flash_cut" not in codes(known)
    assert known["measurements"]["accent_changes_excluded"] >= 1


def test_credits_cover_music_and_skip_procedural_sound(workspace, monkeypatch):
    from editvideo import agent, resources, sound
    monkeypatch.setattr(resources, "ROOT", workspace)
    pid, _ = _project(workspace)
    song = workspace / "song.wav"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=330:d=4", str(song)], check=True)
    resources.register_resource(str(song), "audio", "Song", "CC0", "Some Composer", "https://example.org/song")
    sid = agent.import_media(pid, str(song), "song", "decoration", True, agent.read(pid)["revision"])["asset"]["id"]
    bed = sound.design("rain", 4.0, 1, -18)
    bid = agent.import_media(pid, bed["path"], "rain", "decoration", True, agent.read(pid)["revision"])["asset"]["id"]
    p = agent.read(pid)
    t = p["timeline"]
    t["audio_clips"] = [{"id": "music", "asset_id": sid, "start_frame": 0, "end_frame": 100, "role": "music"},
                        {"id": "rain", "asset_id": bid, "start_frame": 0, "end_frame": 100}]
    agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
    r = resources.project_credits(pid)
    assert "Some Composer (CC0)" in r["text"]  # music is a credited work, not only the pictures
    # only the unregistered test clip: the synthesized rain and the silent project's generated narration are EditVideo's own
    assert [x["name"] for x in r["unrecorded_assets"]] == ["src.mp4"]
    assert any("procedural" in x["origin"] for x in r["traced_assets"])


def test_tracking_spread_is_measured_when_fitting_and_auditing_text(workspace):
    from editvideo import agent
    from editvideo.design_library import fit_size, fit_width
    from editvideo.review import audit_timeline
    text = "THÀNH PHỐ LÊN ĐÈN"
    plain, spread = fit_size("montserrat", text, .84, 1080, 800, 110), fit_size("montserrat", text, .84, 1080, 800, 110, tracking=.2)
    assert spread < plain and fit_width("montserrat", text, spread, 1080, 800, tracking=.2) <= .84
    pid = agent.create_silent("vertical", 60, "remotion", "tracking")["id"]
    p = agent.read(pid)
    layer = {"id": "title", "kind": "text", "text": text, "start_frame": 0, "end_frame": 60, "x": .08, "y": .2, "width": .84, "height": .07,
             "font_id": "montserrat", "font_weight": 800, "font_size": plain, "line_height": 1.2, "z": 900,
             "effects": [{"name": "tracking", "start_frame": 0, "end_frame": 16, "params": {"amount": .2}}]}
    agent.patch(pid, p["revision"], [{"op": "upsert_layer", "layer": layer}])
    codes = lambda: {f["code"] for f in audit_timeline(pid)["findings"]}
    assert "text_wraps" in codes()  # fits at rest, wraps once the letters spread
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "upsert_layer", "layer": {**layer, "font_size": spread}}])
    assert "text_wraps" not in codes()


@pytest.mark.skipif(not ENGINES_READY, reason="Local rendering dependencies not installed")
def test_plated_text_is_inset_and_centred_in_both_engines(tmp_path, monkeypatch):
    from PIL import Image
    from editvideo import agent
    from editvideo.code_engine import scaffold
    from editvideo.snapshot import snapshot
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    for engine in ("remotion", "hyperframes"):
        pid = agent.create_silent("landscape", 30, engine, "plate", color="#000000")["id"]
        p = agent.read(pid)
        layer = {"id": "lt", "kind": "text", "text": "Bói cá nhỏ", "start_frame": 0, "end_frame": 30, "x": .1, "y": .4, "width": .4, "height": .2,
                 "font_id": "bevietnampro", "font_weight": 700, "font_size": 60, "color": "#ffffff", "background": "#204060", "z": 900}
        agent.patch(pid, p["revision"], [{"op": "upsert_layer", "layer": layer}])
        scaffold(pid, engine, False)
        img = np.asarray(Image.open(snapshot(pid, engine, [10])["frames"][0]["path"]).convert("RGB"), np.float32)
        h, w = img.shape[:2]
        ink = (img.min(axis=2) > 200)  # white glyphs; the plate is blue, the canvas black
        ys, xs = np.nonzero(ink)
        box_x0, box_y0, box_y1 = .1 * w, .4 * h, .6 * h
        assert xs.min() - box_x0 >= .012 * w, (engine, xs.min(), box_x0)  # inset from the plate's left edge
        centre = (ys.min() + ys.max()) / 2
        assert abs(centre - (box_y0 + box_y1) / 2) < .03 * h, (engine, centre, (box_y0 + box_y1) / 2)  # centred in its height


def test_accent_sync_follows_the_music_clip_and_keeps_other_sounds(workspace):
    from editvideo import agent, accents, audiofx
    pid, _ = _project(workspace, frames=450)
    music = _beat_music(workspace, 120, 16)
    mid = agent.import_media(pid, music, "beat", "decoration", True, agent.read(pid)["revision"])["asset"]["id"]
    t = agent.read(pid)["timeline"]
    sh = t["shots"][0]
    t["shots"] = [{**sh, "id": f"s{k}", "start_frame": k * 60, "end_frame": min(450, k * 60 + 60), "source_start": 0} for k in range(8)]
    t["audio_clips"] = [{"id": "music", "asset_id": mid, "start_frame": 30, "end_frame": 300, "source_start": 2.0, "playback_rate": 1.25, "role": "music"}]
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "replace_timeline", "timeline": t}])
    rev = audiofx.sync(pid, agent.read(pid)["revision"], {"transitions": False, "entrances": "none", "hits": [{"frame": 400, "kind": "whoosh"}]})["revision"]
    r = accents.sync(pid, rev, {"style": "velocity", "drops": [6.0]})
    assert r["drops"] == [126]  # 30 + (6 - 2) / 1.25 s: the clip's start, offset and speed
    assert all(30 <= x["frame"] < 300 for x in r["placed"])  # only while the music sounds
    ids = [c["id"] for c in agent.read(pid)["timeline"]["audio_clips"]]
    assert any(i.startswith("sfx-") for i in ids) and any(i.startswith("accent-sfx-") for i in ids)  # the earlier whoosh stays


def test_audit_reads_text_contrast_against_the_footage_under_it(workspace):
    from PIL import Image
    from editvideo import agent
    from editvideo.review import audit_timeline
    pale = workspace / "pale.png"
    Image.new("RGB", (640, 360), (225, 222, 210)).save(pale)
    pid = agent.create_silent("landscape", 60, "remotion", "contrast")["id"]
    aid = agent.import_media(pid, str(pale), "pale", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
    p = agent.read(pid)
    t = p["timeline"]
    t["shots"] = [{**t["shots"][0], "asset_id": aid, "fit": "cover", "source_start": 0, "text": "", "motion": "hold"}]
    t["layers"] = [{"id": "t", "kind": "text", "text": "Một ngày", "start_frame": 0, "end_frame": 60, "x": .1, "y": .4, "width": .5, "height": .12,
                    "font_size": 48, "color": "#f2e6c8", "z": 900}]
    agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
    hit = [f for f in audit_timeline(pid)["findings"] if f["code"] == "low_contrast_plate"]
    assert hit and hit[0]["evidence"]["contrast"] < 1.5  # cream on a pale plate
    outlined = {**t["layers"][0], "effects": [{"name": "text_outline", "start_frame": 0, "end_frame": 59, "params": {"color": "#10140f", "amount": 3}}]}
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "upsert_layer", "layer": outlined}])
    assert not [f for f in audit_timeline(pid)["findings"] if f["code"] == "low_contrast_plate"]
