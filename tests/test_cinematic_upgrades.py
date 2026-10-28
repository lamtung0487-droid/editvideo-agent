import math
import pytest
from pydantic import ValidationError
from editvideo.globe import GlobeRequest, euler_facing, globe_scene, latlon_dir, simplify
from editvideo.models import Layer
from editvideo.scene3d import Scene3D


def globe(**kw):
    base = {"end_frame": 120, "earth_texture": "tex", "camera": [{"frame": 0, "lat": 10, "lon": 100, "altitude": 3},
                                                              {"frame": 100, "lat": 16, "lon": 106, "altitude": 1, "look": .5}]}
    return GlobeRequest.model_validate({**base, **kw})


def test_latlon_matches_equirect_sphere_and_ring_lies_flat():
    assert all(abs(a - b) < 1e-9 for a, b in zip(latlon_dir(0, 0), (1, 0, 0)))
    assert all(abs(a - b) < 1e-9 for a, b in zip(latlon_dir(0, 90), (0, 0, -1)))
    for lat, lon in ((15.9, 108.3), (-40, -70), (80, 10), (-89, 5), (0, 0)):
        v = latlon_dir(lat, lon)
        x, y, _ = euler_facing(v)  # three.js XYZ order: R*(0,0,1) = (sin y, -sin x cos y, cos x cos y)
        n = (math.sin(y), -math.sin(x) * math.cos(y), math.cos(x) * math.cos(y))
        assert all(abs(a - b) < 1e-6 for a, b in zip(v, n))


def test_simplify_keeps_closed_rings_under_limit():
    ring = [[math.cos(t / 300 * 2 * math.pi) + .01 * math.sin(t), math.sin(t / 300 * 2 * math.pi)] for t in range(900)]
    ring.append(ring[0])
    out = simplify(ring, 200)
    assert 20 < len(out) <= 200 and out[0] == out[-1] == ring[0]


def test_globe_scene_markers_outlines_arcs_and_sun():
    q = globe(markers=[{"id": "a", "lat": 10.8, "lon": 106.7, "label": "Sài Gòn", "appear": 30},
                       {"id": "b", "lat": 21, "lon": 107, "label": "Hạ Long", "appear": 40}],
              arcs=[{"id": "ab", "start": "a", "end": "b", "grow": [50, 80]}],
              outlines=[{"id": "vn", "points": [[100 + i * .01, 10 + math.sin(i) * .1] for i in range(1200)], "grow": [10, 40]}],
              sun_lat=10, sun_lon=90, clouds_texture="clouds")
    scene = Scene3D.model_validate(globe_scene(q))
    ids = {o.id: o for o in scene.objects}
    assert {"mk-a", "ring-a", "arc-ab", "tr-ab", "ol-vn", "clouds"} <= set(ids)
    assert len(ids["ol-vn"].path) <= 480 and ids["ol-vn"].grow == [10, 40]
    ring = ids["ring-a"].keyframes
    assert ring[0].opacity == 0 and any(k.opacity and k.opacity > .9 for k in ring)
    tr = ids["tr-ab"].keyframes  # traveler invisible until its arc starts growing
    assert tr[0].scale == .01 and any(k.frame == 50 and k.scale == .01 for k in tr)
    clouds = ids["clouds"].keyframes
    assert clouds[-1].opacity < clouds[0].opacity  # thinner clouds once the camera is low
    sun = next(l for l in scene.lights if l.kind == "directional").position
    s = latlon_dir(10, 90)
    assert abs(sun.x - s[0] * 10) < 1e-2 and abs(sun.z - s[2] * 10) < 1e-2
    assert len(scene.camera_keyframes) <= 100
    with pytest.raises(ValidationError):  # outlines are [lon, lat]
        globe(outlines=[{"id": "x", "points": [[10, 95], [11, 20]]}])
    with pytest.raises(ValidationError):
        globe(arcs=[{"id": "x", "start": "a", "end": "missing", "grow": [0, 10]}], markers=[{"id": "a", "lat": 0, "lon": 0}])


def test_globe_camera_glides_through_middle_keys_and_plays_back_linearly():
    q = globe(camera=[{"frame": 0, "lat": 22, "lon": 48, "altitude": 5.2}, {"frame": 90, "lat": 15, "lon": 100, "altitude": 2.2},
                      {"frame": 115, "lat": 15.6, "lon": 106.4, "altitude": 1.0}])
    scene = Scene3D.model_validate(globe_scene(q))
    assert scene.camera_ease == "linear"  # dense pre-eased keys; per-key smoothstep would stop the camera every few frames
    pos = [(k.frame, (k.position.x, k.position.y, k.position.z)) for k in scene.camera_keyframes]
    speed = [math.dist(a[1], b[1]) / (b[0] - a[0]) for a, b in zip(pos, pos[1:])]
    near90 = [s for (f, _), s in zip(pos, speed) if 84 <= f <= 93]
    assert min(near90) > .3 * max(speed)  # no stop at the middle key
    assert speed[0] < .4 * max(speed) and speed[-1] < .1 * max(speed)  # eases out of the first key and into the last
    assert all(math.dist(p, (0, 0, 0)) > q.radius for _, p in pos)
    assert Scene3D.model_validate({"objects": [{"id": "a"}]}).camera_ease == "smooth"


def test_scene3d_pose_opacity_tube_follow_and_displacement():
    scene = Scene3D.model_validate({"objects": [
        {"id": "route", "geometry": "tube", "path": [[0, 0, 0], [1, 1, 0], [2, 0, 0]], "grow": [0, 30]},
        {"id": "dot", "geometry": "sphere", "size": [.002, .002, .002], "follow": "route", "follow_range": [0, 30],
         "keyframes": [{"frame": 0, "opacity": 0}, {"frame": 10, "opacity": 1}]},
        {"id": "photo", "geometry": "plane", "segments": 256, "emissive_texture": "img", "displacement_texture": "depth", "displacement_scale": 1.2}]})
    assert scene.objects[1].keyframes[0].opacity == 0 and scene.objects[1].keyframes[0].position is None
    with pytest.raises(ValidationError):
        Scene3D.model_validate({"objects": [{"id": "t", "geometry": "tube", "path": [[0, 0, 0]]}]})
    with pytest.raises(ValidationError):
        Scene3D.model_validate({"objects": [{"id": "d", "keyframes": [{"frame": 0, "opacity": 1.5}]}]})


def test_film_layer_and_new_text_effects_validate():
    grain = Layer.model_validate({"id": "g", "kind": "film", "start_frame": 0, "end_frame": 30, "data": {"type": "grain", "intensity": .2}})
    assert grain.data["type"] == "grain"
    Layer.model_validate({"id": "l", "kind": "film", "start_frame": 0, "end_frame": 30,
                          "data": {"type": "light_leak", "color": "#ff9a3c", "secondary_color": "#ff3c6e", "speed": 2}})
    for bad in ({"type": "hologram"}, {"type": "grain", "intensity": 3}, {"type": "grain", "script": "x"}):
        with pytest.raises((ValidationError, ValueError)):
            Layer.model_validate({"id": "b", "kind": "film", "start_frame": 0, "end_frame": 30, "data": bad})
    text = Layer.model_validate({"id": "t", "kind": "text", "text": "HỘI AN", "start_frame": 0, "end_frame": 30,
                                 "effects": [{"name": "mask_reveal", "end_frame": 20}, {"name": "char_spring", "end_frame": 20}]})
    assert [e.name for e in text.effects] == ["mask_reveal", "char_spring"]
