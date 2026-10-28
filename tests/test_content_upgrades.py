import json
import struct
import pytest
from pydantic import ValidationError
from editvideo.models import Layer, Timeline
from editvideo.scene3d import Scene3D


def svg_layer(elements, **kw):
    return Layer.model_validate({"id": "map", "kind": "svg", "start_frame": 0, "end_frame": 60,
                                 "data": {"view_box": [100, 100], "elements": elements}, **kw})


def test_svg_layer_validates_drawable_elements_and_rejects_markup():
    layer = svg_layer([{"id": "r", "type": "polyline", "points": [[0, 0], [50, 50]], "draw": [0, 20]},
                       {"id": "o", "type": "follower", "route": "r", "progress": [0, 20]},
                       {"id": "t", "type": "text", "x": 5, "y": 5, "text": "Hội An", "appear": [10, 20]}])
    assert layer.data["elements"][0]["draw"] == [0, 20]
    with pytest.raises(ValidationError):  # raw markup/script cannot hide in a path
        svg_layer([{"id": "p", "type": "path", "d": "M0 0 L10 10\"/><script>alert(1)</script>"}])
    with pytest.raises(ValidationError):  # follower must ride an existing polyline
        svg_layer([{"id": "o", "type": "follower", "route": "missing", "progress": [0, 10]}])
    with pytest.raises(ValidationError):
        svg_layer([{"id": "r", "type": "polyline", "points": [[0, 0], [1, 1]], "draw": [20, 5]}])


def base_timeline(layers):
    return {"width": 1920, "height": 1080, "total_frames": 120, "audio_samples": 192000, "timing_method": "x", "beats": [], "cues": [],
            "shots": [{"id": "a", "beat_id": "b", "start_frame": 0, "end_frame": 60},
                      {"id": "b", "beat_id": "b", "start_frame": 60, "end_frame": 120, "transition": {"name": "push_left", "duration_frames": 12}}],
            "layers": layers}


def test_attach_shot_must_reference_a_shot_and_stay_inside_it():
    ok = {"id": "t", "kind": "text", "text": "x", "start_frame": 10, "end_frame": 60, "attach_shot": "a"}
    assert Timeline.model_validate(base_timeline([ok])).layers[0].attach_shot == "a"
    with pytest.raises(ValidationError, match="not found"):
        Timeline.model_validate(base_timeline([{**ok, "attach_shot": "zz"}]))
    with pytest.raises(ValidationError, match="inside shot"):
        Timeline.model_validate(base_timeline([{**ok, "end_frame": 80}]))


def glb(json_obj, binary=b""):
    body = json.dumps(json_obj).encode()
    body += b" " * (-len(body) % 4)
    chunks = struct.pack("<II", len(body), 0x4E4F534A) + body
    if binary:
        binary += b"\0" * (-len(binary) % 4)
        chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


def test_glb_registration_requires_self_contained_binary(tmp_path, monkeypatch):
    from editvideo import media, store
    monkeypatch.setattr(store, "add_asset", lambda pid, meta: None)
    good = tmp_path / "m.glb"
    good.write_bytes(glb({"asset": {"version": "2.0"}, "meshes": [{}], "animations": [{"name": "spin"}], "buffers": [{"byteLength": 4}]}, b"\0\0\0\0"))
    meta = media.register("p", good, "m.glb")
    assert meta["kind"] == "model" and meta["model"]["animations"] == ["spin"]
    ext = tmp_path / "e.glb"
    ext.write_bytes(glb({"asset": {"version": "2.0"}, "buffers": [{"uri": "outside.bin", "byteLength": 4}]}))
    with pytest.raises(ValueError, match="external"):
        media.register("p", ext, "e.glb")
    bad = tmp_path / "b.glb"
    bad.write_bytes(b"notglTF" * 4)
    with pytest.raises(ValueError):
        media.register("p", bad, "b.glb")


def test_scene3d_texture_model_fields_and_sources(monkeypatch):
    from editvideo.planner import validate_sources
    scene = Scene3D.model_validate({"objects": [{"id": "earth", "geometry": "sphere", "texture": "tex", "bump_texture": "tex"},
                                                {"id": "lm", "model": "glb", "animation": "spin"}],
                                    "background_texture": "tex"}).model_dump()
    layer = {"id": "s", "kind": "scene3d", "start_frame": 0, "end_frame": 60, "data": scene}
    t = Timeline.model_validate(base_timeline([layer]))
    lib = [{"id": "tex", "kind": "image"}, {"id": "glb", "kind": "model", "model": {"animations": ["spin"]}}]
    validate_sources("p", t, lib)
    with pytest.raises(ValueError, match="must be an imported model"):
        validate_sources("p", t, [{"id": "tex", "kind": "image"}, {"id": "glb", "kind": "image"}])
    lib[1]["model"]["animations"] = ["walk"]
    with pytest.raises(ValueError, match="animation clip"):
        validate_sources("p", t, lib)
