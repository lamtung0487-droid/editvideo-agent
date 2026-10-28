"""An SVG layer is fitted inside its box and centred: the timeline audit says when its view box has another shape."""
import pytest

from editvideo import store


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.initialize()
    return tmp_path


def test_a_view_box_of_another_shape_than_its_box_is_flagged(workspace):
    """The reel's beat strip: a 1000 x 80 view box in a 1690 x 65 px box was drawn 810 px wide, mid-panel."""
    from editvideo import agent
    from editvideo.review import audit_timeline
    pid = agent.create_silent("landscape", 60, "remotion", "strip", color="#000000")["id"]
    line = [{"id": "l", "type": "line", "x1": 0, "y1": 40, "x2": 1000, "y2": 40, "stroke": "#ffffff", "stroke_width": 2}]
    strip = {"id": "strip", "kind": "svg", "start_frame": 0, "end_frame": 60, "x": .06, "y": .83, "width": .88, "height": .06, "z": 10,
             "data": {"view_box": [1000, 80], "elements": line}}
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "upsert_layer", "layer": strip}])
    hit = [f for f in audit_timeline(pid)["findings"] if f["code"] == "svg_aspect_mismatch"]
    assert hit and hit[0]["where"]["layer"] == "strip" and hit[0]["evidence"]["drawn_px"][0] == 810
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "upsert_layer", "layer": {**strip, "data": {**strip["data"], "view_box": [1690, 65]}}}])
    assert not [f for f in audit_timeline(pid)["findings"] if f["code"] == "svg_aspect_mismatch"]
