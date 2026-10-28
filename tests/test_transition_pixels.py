"""A shot-attached graphic must dissolve, not cover the incoming stacking context until the overlap ends."""
import pytest
from PIL import Image
from editvideo import agent, store
from editvideo.code_engine import scaffold, ENGINES
from editvideo.snapshot import snapshot


@pytest.mark.parametrize("engine", ["remotion", "hyperframes"])
@pytest.mark.skipif(not (ENGINES / "node_modules").is_dir(), reason="Local rendering dependencies not installed")
def test_attached_graphics_blend_at_the_middle_of_a_live_dissolve(tmp_path, monkeypatch, engine):
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    pid = agent.create_silent("landscape", 60, engine, "Transition regression")["id"]
    p = agent.read(pid)
    t = p["timeline"]
    base = t["shots"][0]
    t["shots"] = [{**base, "id": "red", "start_frame": 0, "end_frame": 30, "text": ""},
                  {**base, "id": "blue", "start_frame": 30, "end_frame": 60, "source_start": 0,
                   "text": "", "transition": {"name": "dissolve", "duration_frames": 18, "mode": "live"}}]
    t["layers"] = [{"id": shot, "kind": "shape", "attach_shot": shot, "start_frame": start, "end_frame": start + 30,
                    "x": 0, "y": 0, "width": 1, "height": 1, "z": 30, "color": colour,
                    "data": {"shape": "rectangle", "corner_radius": 0}}
                   for shot, start, colour in [("red", 0, "#ff0000"), ("blue", 30, "#0000ff")]]
    agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
    scaffold(pid, engine, False)
    result = snapshot(pid, engine, [28, 39, 49])
    colours = []
    for frame in result["frames"]:
        with Image.open(frame["path"]) as im:
            colours.append(im.convert("RGB").getpixel((im.width // 2, im.height // 2)))
    a, middle, b = colours
    assert a[0] > 245 and a[2] < 5, colours
    assert 80 < middle[0] < 175 and 80 < middle[2] < 175 and middle[1] < 5, colours
    assert b[2] > 245 and b[0] < 5, colours
