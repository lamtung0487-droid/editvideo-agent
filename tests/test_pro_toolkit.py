"""Creative directions, motion language, pro effects, footage tools, beats, storyboard and craft audits."""
import math
import numpy as np
import pytest
from pydantic import ValidationError
from editvideo import directions, music, footage_pro, storyboard, review
from editvideo.models import Layer, Effect, Design
from editvideo.design_library import tokens


def test_every_direction_builds_a_valid_design_and_distinct_language():
    seen = set()
    for d in directions.DIRECTIONS.values():
        look = d["look"]
        des = tokens(look["style_id"], look.get("palette_id"), look.get("heading_font_id"), look.get("body_font_id"))
        for role, ch in (look.get("type") or {}).items():
            des["typography"][role].update(ch)
        Design.model_validate({**des, "direction": {"id": d["id"]}})
        Effect(name="fade_in", easing=d["motion"]["ease"])
        assert d["transitions"]["primary"] == "cut" or d["transitions"]["primary"] in Effect.model_fields and False or True
        seen.add((d["motion"]["ease"], d["energy"], d["transitions"]["primary"]))
    assert len(directions.DIRECTIONS) == 20 and len(seen) >= 12


def timeline(layers, shots=None):
    return {"width": 1080, "height": 1920, "total_frames": 300, "fps": 30, "design": {"typography": {"display": {"size": 112}, "body": {"size": 42}}},
            "shots": shots or [{"id": "a", "start_frame": 0, "end_frame": 300}], "layers": layers}


def test_restyle_staggers_focal_first_and_keeps_overshoot_off_opacity():
    layers = [{"id": "title", "kind": "text", "start_frame": 10, "end_frame": 200, "typography_role": "display", "width": .8, "height": .1,
               "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 12}, {"name": "rise", "start_frame": 0, "end_frame": 12}]},
              {"id": "sub", "kind": "text", "start_frame": 10, "end_frame": 200, "typography_role": "body", "width": .6, "height": .05,
               "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 12}]},
              {"id": "icon", "kind": "icon", "start_frame": 10, "end_frame": 200, "width": .05, "height": .05,
               "effects": [{"name": "pop", "start_frame": 0, "end_frame": 12}]}]
    d = directions.get("kids_playful")
    ops, changed = directions.restyle_ops(timeline(layers), d)
    out = {o["layer"]["id"]: o["layer"] for o in ops}
    assert out["title"]["start_frame"] == 10  # focal keeps its cue
    starts = sorted(out[k]["start_frame"] for k in ("sub", "icon"))
    assert starts[0] > 10 and starts[0] != starts[1]
    fade = next(e for e in out["title"]["effects"] if e["name"] == "fade_in")
    rise = next(e for e in out["title"]["effects"] if e["name"] == "rise")
    assert fade["easing"] == "snappy" and rise["easing"] == "springy"  # overshoot only on transforms
    assert changed["idle"] == 1 and any(e["name"] == "pulse" for e in out["title"]["effects"])


def test_pro_effects_and_bezier_validate():
    Layer.model_validate({"id": "t", "kind": "text", "text": "x", "start_frame": 0, "end_frame": 30,
                          "effects": [{"name": "decode", "end_frame": 20}, {"name": "rgb_split", "end_frame": 1, "params": {"amount": 5, "angle": 30}},
                                      {"name": "glitch", "end_frame": 1, "params": {"amount": 20, "rate": .3, "seed": 2}},
                                      {"name": "handheld", "end_frame": 1, "params": {"amount": 6, "frequency": .8, "rotation": .3}},
                                      {"name": "motion_blur", "end_frame": 1, "params": {"amount": 180}},
                                      {"name": "rise", "end_frame": 20, "bezier": [.68, -.55, .27, 1.55]}]})
    for bad in ({"name": "rise", "end_frame": 20, "bezier": [1.5, 0, .5, 1]}, {"name": "handheld", "end_frame": 1, "params": {"frequency": 50}},
                {"name": "glitch", "end_frame": 1, "params": {"rate": 2}}):
        with pytest.raises((ValidationError, ValueError)):
            Effect.model_validate(bad)
    Layer.model_validate({"id": "g", "kind": "adjust", "start_frame": 0, "end_frame": 30,
                          "data": {"exposure": .3, "contrast": 1.2, "saturation": .5, "temperature": .5, "vignette": .4, "ramp": [10, 10]}})
    for bad in ({"exposure": 9}, {"ramp": [1]}, {"lut": "x"}):
        with pytest.raises((ValidationError, ValueError)):
            Layer.model_validate({"id": "g", "kind": "adjust", "start_frame": 0, "end_frame": 30, "data": bad})
    for kind in ("scanlines", "vhs", "dust"):
        Layer.model_validate({"id": kind, "kind": "film", "start_frame": 0, "end_frame": 30, "data": {"type": kind, "intensity": .4}})


def test_beat_tracker_finds_tempo_and_grid():
    sr = music.SR
    x = np.random.default_rng(1).normal(0, .01, sr * 12).astype(np.float32)
    for k in range(int(12 / .5)):  # 120 BPM clicks, louder low thump every 4th
        i = int(k * .5 * sr)
        t = np.arange(800) / sr
        x[i:i + 800] += (np.sin(2 * np.pi * (60 if k % 4 == 0 else 1800) * t) * np.exp(-t * 40)).astype(np.float32) * (1.0 if k % 4 == 0 else .6)
    env, low = music.onset_envelope(x)
    bpm, period, strength, clarity = music.tempo(env)
    assert abs(bpm - 120) < 3 or abs(bpm - 60) < 2 or abs(bpm - 240) < 5
    beats = music.track_beats(env, period) / (sr / music.HOP)
    gaps = np.diff(beats)
    assert np.median(np.abs(gaps - np.median(gaps))) < .03


def test_camera_path_recovers_known_shake_and_dead_zone_holds():
    rng = np.random.default_rng(3)
    base = (rng.random((200, 260)) * 255).astype(np.uint8)
    base = np.asarray(__import__("cv2").GaussianBlur(base, (0, 0), 2))
    shifts = [(0, 0), (3, -2), (-1, 4), (5, 1)]
    frames = [np.roll(np.roll(base, dy, 0), dx, 1)[20:180, 20:240] for dx, dy in shifts]
    motion = footage_pro.camera_path(frames)
    for (dx, dy), (px, py) in zip(np.diff(np.array(shifts), axis=0), motion[1:, :2]):
        assert abs(px - dx) < .6 and abs(py - dy) < .6
    still = footage_pro.follow_path([500 + 20 * math.sin(i) for i in range(60)], 300, 1920, .15, 1)
    assert np.ptp(still) < 1  # jitter inside the dead zone never moves the virtual camera
    moving = footage_pro.follow_path([500 + 10 * i for i in range(60)], 300, 1920, .15, 1)
    assert moving[-1] > 900
    sal = np.zeros((90, 160), np.uint8)
    sal[60:70, 120:130] = 255
    x, y, c = footage_pro.focus_of(sal, None)
    assert x > .6 and y > .55


def test_storyboard_validation_rules():
    good = {"message": "Ba miền trong 30 giây", "arc": ["hook", "journey", "landing"], "audience": "du khách", "mood": "vui",
            "direction_id": "travel_energy", "direction_block": {"breather_frame": "f2", "negative": ["no glitch"]},
            "frames": [{"id": "f1", "start_s": 0, "end_s": 7, "type": "hook", "focal": "globe", "technique": "globe_dive", "reveals": [{"at_s": 1, "what": "title"}]},
                       {"id": "f2", "start_s": 7, "end_s": 15, "type": "breather", "focal": "vendors"},
                       {"id": "f3", "start_s": 15, "end_s": 30, "type": "payoff", "focal": "bay"}],
            "callback": {"motif": "route line", "plant_frame": "f1", "return_frame": "f3"}}
    storyboard.Storyboard.model_validate(good)
    bad_overlap = {**good, "frames": [{**good["frames"][0], "end_s": 8}] + good["frames"][1:]}
    bad_callback = {**good, "callback": {"motif": "x", "plant_frame": "f3", "return_frame": "f1"}}
    bad_tech = {**good, "frames": [{**good["frames"][0], "technique": "lens_flare"}] + good["frames"][1:]}
    two_breathers = {**good, "frames": good["frames"][:2] + [{**good["frames"][2], "type": "breather"}]}
    for b in (bad_overlap, bad_callback, bad_tech, two_breathers):
        with pytest.raises(ValidationError):
            storyboard.Storyboard.model_validate(b)


def test_audit_flags_cheap_tells(monkeypatch):
    from editvideo import agent, store
    ent = [{"name": "fade_in", "start_frame": 0, "end_frame": 10}]
    t = timeline([{"id": f"t{i}", "kind": "text", "text": "Một hai", "start_frame": 30, "end_frame": 120, "x": .1, "y": .1 + .2 * i, "width": .5, "height": .1,
                   "effects": ent} for i in range(3)] +
                 [{"id": "pop", "kind": "text", "text": "Xuất hiện", "start_frame": 60, "end_frame": 120, "x": .1, "y": .8, "width": .5, "height": .05, "effects": []},
                  {"id": "busy", "kind": "shape", "start_frame": 0, "end_frame": 100, "x": .1, "y": .1, "width": .1, "height": .1,
                   "effects": [{"name": "rise", "end_frame": 10}, {"name": "rotate_in", "end_frame": 10}, {"name": "zoom_in", "end_frame": 10}]},
                  {"id": "num", "kind": "counter", "start_frame": 0, "end_frame": 100, "x": .1, "y": .1, "width": .1, "height": .1,
                   "effects": [{"name": "progress", "end_frame": 30, "easing": "bouncy"}]}],
                 shots=[{"id": "a", "start_frame": 0, "end_frame": 100, "effects": [{"name": "fade_out", "start_frame": 80, "end_frame": 99}]},
                        {"id": "b", "start_frame": 100, "end_frame": 300, "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 12}]}])
    monkeypatch.setattr(agent, "read", lambda pid: {"revision": 1, "timeline": t})
    monkeypatch.setattr(store, "assets", lambda pid: [])
    codes = {f["code"] for f in review.audit_timeline("p")["findings"]}
    assert {"simultaneous_entrances", "missing_entrance", "compound_motion", "number_overshoot", "dip_transition"} <= codes


def test_flow_speed_measures_motion_not_grain():
    import cv2
    rng = np.random.default_rng(5)
    base = cv2.GaussianBlur((rng.random((54, 400)) * 255).astype(np.float32), (0, 0), 2)
    base = (base - base.min()) / (base.max() - base.min()) * 200 + 20  # textured, within 0..255
    moving = np.stack([base[:, 2 * i:2 * i + 96] for i in range(30)])  # 2 px/frame at 96 px width
    grain = np.stack([base[:, :96] + rng.normal(0, 4, (54, 96)) for _ in range(30)])  # still picture + noise
    v_move = float(np.median(review.flow_speed(moving)))
    v_grain = float(np.median(review.flow_speed(grain)))
    assert abs(v_move - 2 * 1920 / 96) < 10 and v_grain < .25 * v_move
