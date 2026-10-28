"""Text contrast, read where the viewer reads it: in the timeline audit (low_contrast_plate, from the source frames) and
in the delivery gate (text_contrast, from the render)."""
import subprocess

import pytest
from PIL import Image

from editvideo import store


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.initialize()
    return tmp_path


def _plates(pid):
    from editvideo.review import audit_timeline
    return [f for f in audit_timeline(pid)["findings"] if f["code"] == "low_contrast_plate"]


def test_a_translucent_wash_is_read_through_its_opacity(workspace):
    """A pale picture at 25 % over a black slate is a dark backdrop for white type; the same picture at full opacity is not.
    A black scrim at 60 % between pale footage and the type is read too. (The capability reel's titles had been measured
    at 1.1:1 against the full-brightness wash under them, and rendered at about 12:1.)"""
    from editvideo import agent
    pale = workspace / "pale.png"
    Image.new("RGB", (640, 360), (236, 232, 222)).save(pale)
    pid = agent.create_silent("landscape", 60, "remotion", "wash", color="#000000")["id"]
    aid = agent.import_media(pid, str(pale), "pale", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
    wash = {"id": "wash", "kind": "image", "asset_id": aid, "start_frame": 0, "end_frame": 60, "x": 0, "y": 0, "width": 1, "height": 1, "z": 5,
            "fit": "cover", "opacity": .25}
    title = {"id": "title", "kind": "text", "text": "Reads the footage", "start_frame": 0, "end_frame": 60, "x": .1, "y": .4, "width": .6, "height": .1,
             "font_size": 48, "color": "#e8e4dc", "z": 600}
    p = agent.read(pid)
    agent.patch(pid, p["revision"], [{"op": "upsert_layer", "layer": wash}, {"op": "upsert_layer", "layer": title}])
    assert not _plates(pid)
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "upsert_layer", "layer": {**wash, "opacity": 1}}])
    hit = _plates(pid)
    assert hit and hit[0]["evidence"]["contrast"] < 1.5
    scrim = {"id": "scrim", "kind": "shape", "start_frame": 0, "end_frame": 60, "x": 0, "y": 0, "width": 1, "height": 1, "z": 30, "color": "#000000",
             "opacity": .6, "data": {"shape": "rectangle", "corner_radius": 0}}
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "upsert_layer", "layer": scrim}])
    assert not _plates(pid)


def test_text_contrast_reads_a_downscaled_preview_where_the_text_is(tmp_path):
    """A 720p preview of a 1080p timeline: the boxes are cropped at the preview's own size (cropped at 1080p coordinates
    they read the footage beside a label, and failed a dark chip on its plate)."""
    from editvideo import media, review
    # left half white, right half a dark plate where the label sits
    graph = "color=c=white:s=1920x1080:d=1:r=30[a];color=c=0x18202a:s=960x1080:d=1:r=30[b];[a][b]overlay=x=960:y=0"
    timeline = {"width": 1920, "height": 1080, "layers": [{"id": "chip", "kind": "text", "text": "track_region", "start_frame": 0, "end_frame": 30,
                                                           "x": .55, "y": .4, "width": .4, "height": .2, "color": "#d8dee5", "font_size": 24}]}
    for size in ("1920:1080", "1280:720"):
        clip = tmp_path / f"c{size[:4]}.mp4"
        subprocess.run([media.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", graph, "-vf", f"scale={size}", "-pix_fmt", "yuv420p", str(clip)], check=True)
        assert review.text_contrast(str(clip), timeline) == [], size


def test_text_contrast_reads_a_moving_label_where_it_is(tmp_path):
    """A label keyframed from the white half onto the dark half is read where it sits at the sampled frame; so is a
    label riding a moving parent. (The reel's label riding a tracked car had been read at its authored box: 1.7:1.)"""
    from editvideo import media, review
    graph = "color=c=white:s=1920x1080:d=2:r=30[a];color=c=0x18202a:s=960x1080:d=2:r=30[b];[a][b]overlay=x=960:y=0"
    clip = tmp_path / "c.mp4"
    subprocess.run([media.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", graph, "-pix_fmt", "yuv420p", str(clip)], check=True)
    moving = {"id": "label", "kind": "text", "text": "rally car", "start_frame": 0, "end_frame": 60, "x": .1, "y": .4, "width": .3, "height": .1,
              "color": "#d8dee5", "font_size": 24, "keyframes": {"x": [{"frame": 0, "value": 0}, {"frame": 20, "value": 1000}]}}
    assert review.text_contrast(str(clip), {"width": 1920, "height": 1080, "layers": [moving]}) == []
    still = {**moving, "keyframes": {}}
    assert [r["id"] for r in review.text_contrast(str(clip), {"width": 1920, "height": 1080, "layers": [still]})] == ["label"]
    parent = {"id": "rig", "kind": "null", "start_frame": 0, "end_frame": 60, "x": 0, "y": 0, "width": 1, "height": 1,
              "keyframes": {"x": [{"frame": 0, "value": 0}, {"frame": 20, "value": 1000}]}}
    rider = {**still, "parent": "rig"}
    assert review.text_contrast(str(clip), {"width": 1920, "height": 1080, "layers": [parent, rider]}) == []
