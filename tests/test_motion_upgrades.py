import pytest
from pydantic import ValidationError
from editvideo.models import Transition
from editvideo.scene3d import Scene3D
from editvideo.retime import RetimeRequest, speed_at


def test_two_sided_transitions_validate_names_and_modes():
    t = Transition(name="whip_left", duration_frames=12, mode="live")
    assert t.mode == "live" and Transition().mode == "freeze"
    with pytest.raises(ValidationError):
        Transition(name="whip_left", mode="teleport")


def test_scene3d_partial_pose_inherits_and_new_materials_validate():
    scene = Scene3D.model_validate({
        "objects": [{"id": "glass", "geometry": "torus_knot", "position": {"x": 1.5}, "transmission": 1, "clearcoat": .5,
                     "emissive": "#65d6ff", "emissive_intensity": 2,
                     "keyframes": [{"frame": 0, "rotation": {"y": 0}}, {"frame": 10, "rotation": {"y": 1}}]}],
        "environment": "studio", "bloom": {"strength": .6}, "fog": {"near": 4, "far": 12}}).model_dump()
    key = scene["objects"][0]["keyframes"][0]
    assert key["position"] is None and key["scale"] is None  # runtime inherits object base, not origin
    with pytest.raises(ValidationError):
        Scene3D.model_validate({"objects": [{"id": "a"}], "fog": {"near": 9, "far": 3}})


def test_retime_speed_ramp_is_smooth_and_bounded():
    q = RetimeRequest(path="x.mp4", speed_keys=[{"at": 0, "speed": 1}, {"at": 1, "speed": .25}])
    assert speed_at(q, 0) == 1 and speed_at(q, 1) == .25 and .25 < speed_at(q, .5) < 1
    with pytest.raises(ValidationError):
        RetimeRequest(path="x.mp4", speed_keys=[{"at": 1, "speed": 1}, {"at": .5, "speed": 1}])
    with pytest.raises(ValidationError):
        RetimeRequest(path="x.mp4", start=0, end=90)


def test_live_transition_requires_source_handle(tmp_path, monkeypatch):
    from editvideo.planner import validate_sources
    from editvideo.models import Timeline
    t = Timeline.model_validate({"width": 1920, "height": 1080, "total_frames": 60, "audio_samples": 96000, "timing_method": "x",
        "beats": [], "cues": [], "shots": [
            {"id": "a", "beat_id": "b", "start_frame": 0, "end_frame": 30, "asset_id": "v"},
            {"id": "b", "beat_id": "b", "start_frame": 30, "end_frame": 60, "transition": {"name": "push_left", "duration_frames": 12, "mode": "live"}}]})
    validate_sources("p", t, [{"id": "v", "kind": "video", "duration": 1.4}])
    with pytest.raises(ValueError, match="source handle"):
        validate_sources("p", t, [{"id": "v", "kind": "video", "duration": 1.2}])
