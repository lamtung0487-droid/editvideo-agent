"""Evidence tools, cinematic recipes and resources: synthetic signals with known answers."""
import math
import numpy as np
import pytest
from editvideo import review, cinematic, resources
from editvideo.scene3d import Scene3D
from editvideo.models import Layer


def stripes(offsets, size=64):
    cols = np.arange(size)[None, :]
    return np.stack([np.repeat(np.sin(2 * np.pi * (cols - x) / 16) * 60 + 128, size, axis=0) for x in offsets])


def test_motion_signal_finds_judder_cadence_and_stillness_but_not_smooth_acceleration():
    smooth = np.cumsum(np.linspace(.2, 1.4, 90))
    r = review.analyze_signal(stripes(smooth))
    assert not r["periodic"] and not r["duplicate_frames"]
    steps = np.tile([.259, .482, .259], 30) * 2
    judder = review.analyze_signal(stripes(np.cumsum(steps)))
    assert any(p["period_frames"] == 3 for p in judder["periodic"])
    cadence = np.cumsum([0 if i % 6 == 5 else 1.2 for i in range(90)])
    dup = review.analyze_signal(stripes(cadence))
    assert len(dup["duplicate_frames"]) >= 10
    still = review.analyze_signal(stripes(np.concatenate([np.cumsum(np.ones(30)), np.full(30, 30.0), 30 + np.cumsum(np.ones(30))])))
    assert any(b - a >= 20 for a, b in still["static_spans"])


def keys(gap, n):
    return [{"frame": i * gap, "position": {"x": math.cos(i * .1) * 5, "y": 1, "z": math.sin(i * .1) * 5}, "target": {"x": 0, "y": 0, "z": 0}} for i in range(n)]


def test_camera_profile_flags_eased_dense_keys_only():
    dense = {"camera_keyframes": keys(3, 40)}
    assert review.camera_profile(dense, 118)["oscillation"] > .12
    assert review.camera_profile({**dense, "camera_ease": "linear"}, 118)["oscillation"] < .05
    sparse = {"camera_keyframes": keys(60, 2)}
    p = review.camera_profile(sparse, 61)
    assert p["oscillation"] < .05 and not p["stop_frames"]
    stops = review.camera_profile({"camera_keyframes": keys(10, 8)}, 71)
    assert stops["stop_frames"]


def test_label_projection_and_collision():
    layer = {"id": "s", "kind": "scene3d", "start_frame": 0, "end_frame": 30, "x": 0, "y": 0, "width": 1, "height": 1,
             "data": {"fov": 40, "label_font_size": 30, "camera_keyframes": [{"frame": 0, "position": {"x": 0, "y": 0, "z": 5}, "target": {"x": 0, "y": 0, "z": 0}}],
                      "objects": [{"id": "a", "label": "Alpha", "position": {"x": 0, "y": 0, "z": 0}, "keyframes": []},
                                  {"id": "b", "label": "Beta", "position": {"x": .02, "y": 0, "z": 0}, "keyframes": []},
                                  {"id": "c", "label": "Hidden", "position": {"x": 1, "y": 0, "z": 0}, "keyframes": [{"frame": 0, "scale": .01}]}]}}
    tr = review.label_tracks(layer, 1920, 1080)
    labs = tr[0]["labels"]
    assert {l["text"] for l in labs} == {"Alpha", "Beta"}
    a = next(l for l in labs if l["text"] == "Alpha")["box"]
    assert abs(a[0] + a[2] / 2 - .5) < .01
    assert review._overlap(labs[0]["box"], labs[1]["box"]) > .5


def test_measure_text_separates_covered_from_same_colour():
    plate = np.full((40, 80, 3), 90, np.float32)
    plate[:, 60:] = 255
    solo = np.zeros_like(plate)
    solo[10:30, 10:70] = 255
    full = plate.copy()
    full[10:30, 10:40] = 255
    m = review.measure_text(full, plate, solo)
    assert abs(m["visible_fraction"] - .5) < .02
    assert abs(m["covered_fraction"] - 1 / 3) < .02
    assert abs(m["same_as_background_fraction"] - 1 / 6) < .02


@pytest.mark.parametrize("move", ["truck_right", "truck_left", "push_in", "pull_out", "crane_up", "crane_down"])
@pytest.mark.parametrize("aspect", [9 / 16, 16 / 9])
def test_photo_3d_frustum_stays_inside_plane(move, aspect):
    g = cinematic.photo_3d_geometry(2048, 920, aspect, move, "strong", .14, 40)
    PW, PH = g["plane"]
    back = -g["displacement_bias"]
    t = math.tan(math.radians(20))
    for x, y, z in (g["start"], g["end"]):
        hy, hx = (z + back) * t, (z + back) * t * aspect
        assert abs(x) + hx <= PW / 2 and abs(y) + hy <= PH / 2
    assert g["distance"] - (g["displacement_scale"] + g["displacement_bias"]) >= .6


def base(width=1080, height=1920, frames=600, shots=None):
    return {"width": width, "height": height, "total_frames": frames, "fps": 30, "design": {}, "layers": [],
            "shots": shots or [{"id": "a", "start_frame": 0, "end_frame": 300}, {"id": "b", "start_frame": 300, "end_frame": 600, "transition": {"name": "flash", "duration_frames": 12}}]}


def test_film_finish_respects_budget_and_transitions():
    r = cinematic.film_finish(base(), cinematic.FilmFinish(recipe="film_finish"))
    leaks = [o["layer"] for o in r["ops"] if o["layer"]["data"]["type"] == "light_leak"]
    assert len(leaks) == 1 and leaks[0]["start_frame"] < 300 < leaks[0]["end_frame"]
    for o in r["ops"]:
        Layer.model_validate(o["layer"])
    tight = cinematic.film_finish(base(), cinematic.FilmFinish(recipe="film_finish", leaks=[100, 200, 300, 400, 500], max_coverage=.2))
    assert tight["measurements"]["leak_coverage"] <= .2 and tight["notes"]


def test_trajectory_recipe_builds_valid_scene_with_ordered_arrivals():
    path = [[math.cos(a) * 3, 0, math.sin(a) * 2] for a in np.linspace(0, 4, 120)]
    q = cinematic.Trajectory3D(recipe="trajectory_3d", id="tr", start_frame=0, end_frame=300, path=path,
                               bodies=[{"id": "e", "position": [3, 0, 0], "diameter": .8, "label": "Earth"}],
                               milestones=[{"index": 0, "label": "A"}, {"fraction": .5, "label": "B"}, {"index": 119, "label": "C"}],
                               establish_on="e")
    r = cinematic.trajectory_3d(base(1920, 1080, 300, [{"id": "a", "start_frame": 0, "end_frame": 300}]), q)
    f = r["measurements"]["milestone_frames"]
    assert f == sorted(f) and f[0] < f[-1]
    data = r["ops"][0]["layer"]["data"]
    sc = Scene3D.model_validate(data)
    assert sc.camera_ease == "linear" and len(sc.camera_keyframes) <= 100
    assert review.camera_profile(data, 300)["oscillation"] < .12


def test_map_journey_and_geo():
    try:
        resources._geo_file()
    except ValueError:
        pytest.skip("Natural Earth admin-0 geodata not fetched (a download that needs the user's approval)")
    g = resources.geo_outline("Vietnam")
    lon0, lat0, lon1, lat1 = g["bbox"]
    assert 101 < lon0 < 104 and 107 < lon1 < 110 and 8 < lat0 < 9 and 23 < lat1 < 24 and g["points"] <= 480
    proj = resources.MapProjection(g["bbox"], 1000)
    assert proj(23, 105)[1] < proj(10, 105)[1] and proj(15, 103)[0] < proj(15, 108)[0]
    q = cinematic.MapJourney(recipe="map_journey", id="mj", country="Vietnam",
                             cities=[{"name": "A", "lat": 10.8, "lon": 106.7}, {"name": "B", "lat": 21, "lon": 105.8}],
                             legs=[{"to": "B", "start_frame": 0, "end_frame": 120}])
    r = cinematic.map_journey(base(), q)
    for o in r["ops"]:
        Layer.model_validate(o["layer"])


def test_glyph_mask_and_matching_helpers():
    from editvideo.design_library import glyph_mask
    m, line = glyph_mask("archivo", ["HỘI AN"], 120, 700, -.04, 1.1)
    assert m.any() and m.shape[0] >= 120 and line == pytest.approx(132)
    files = {"halong_dec2024.webm": "x", "credits.jsonl": "y", "saigon_traffic.webm": "z"}
    assert resources._match_local("Ha_Long_Bay,_Vietnam_-_Dec_2024.webm", files) == "x"
    assert resources._match_local("Saigon_traffic-oVbn3HeLDA0.webm", files) == "z"


def test_register_resource_and_preview_ops(tmp_path, monkeypatch):
    monkeypatch.setattr(resources, "ROOT", tmp_path)
    monkeypatch.setattr(resources, "CATALOG", tmp_path / "catalog.json")
    f = tmp_path / "tex.png"
    from PIL import Image
    Image.new("RGB", (8, 4)).save(f)
    e = resources.register_resource(f, "texture", "Tex", "CC0", "Someone")
    assert e["resolution"] == [8, 4] and resources.library("tex")["count"] == 1
    d = resources.register_derived(f, e["id"])
    assert d["license"] == "CC0"
    with pytest.raises(ValueError):
        resources.register_resource(f, "texture", "Tex", "", "")
    t = base()
    t["layers"] = [{"id": "x"}]
    out = cinematic.preview_ops(t, [{"op": "upsert_layer", "layer": {"id": "y"}}, {"op": "delete_layer", "id": "x"},
                                    {"op": "update_shot", "shot_id": "a", "changes": {"motion": "hold"}}])
    assert [l["id"] for l in out["layers"]] == ["y"] and out["shots"][0]["motion"] == "hold" and t["layers"] == [{"id": "x"}]
