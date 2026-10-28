"""learnkit through EditVideo: the video sense (study_video + inspect_window) and the single learn MCP tool."""
import json
from editvideo import store
from editvideo.media import FFMPEG, command

VTT = """WEBVTT

00:00:00.500 --> 00:00:02.000
Stop scrolling: this tag finds your keys

00:00:05.200 --> 00:00:07.000
Order today and get twenty percent off
"""


def clip(tmp_path, name="ad"):
    parts = []
    for i, colour in enumerate(("red", "blue", "white", "green")):
        part = tmp_path / f"{name}{i}.mp4"
        command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=320x180:r=30:d=2", "-pix_fmt", "yuv420p", part])
        parts.append(part)
    (tmp_path / f"{name}.txt").write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    folder = tmp_path / name
    folder.mkdir()
    out = folder / "video.mp4"
    command([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", tmp_path / f"{name}.txt", "-c", "copy", out])
    (folder / "video.en.vtt").write_text(VTT, encoding="utf-8")
    return out


def call(m, action, request=None):
    blocks = m.editvideo_learn(action, request)
    return json.loads(blocks[0].text), blocks[1:]


def test_video_works_are_measured_labelled_shown_and_conformed(tmp_path, monkeypatch):
    from editvideo import mcp_server as m, agent_interface
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    video = clip(tmp_path)
    contract, _ = call(m, "")
    assert "video" in contract["kinds"] and "register" in contract["actions"]
    r, _ = call(m, "register", {"path": str(video), "domain": "vertical product ad"})
    assert r["kind"] == "video" and r["features"]["duration_s"] == 8 and r["features"]["cuts_per_min"] == 22.5
    assert r["features"]["words_per_min"] > 0 and r["parts_detected"] == 2 and r["missing"]
    assert (store.DATA / "learnkit" / "exemplars" / (r["id"] + ".json")).is_file()  # kept under EditVideo's data folder
    parts, _ = call(m, "anatomy", {"exemplar_id": r["id"], "parts": [{"role": "hook", "span": {"t": [0, 2]}}, {"role": "offer", "span": {"t": [4, 8]}}]})
    hook = parts["parts"][0]
    assert hook["share"] == .25 and hook["features"]["words_per_min"] > 100 and parts["parts"][1]["start_share"] == .5
    ev, images = call(m, "evidence", {"exemplar_id": r["id"], "span": {"t": [0, 4]}})
    assert len(ev["items"]) == 8 and len(images) == 8 and images[0].type == "image"
    call(m, "signals", {"exemplar_id": r["id"], "signals": [{"metric": "views", "value": 9000, "baseline": 3000,
                                                             "baseline_note": "channel median views", "source": "caller_report"}]})
    bp, _ = call(m, "distill", {"blueprint": {"title": "Hook in two seconds", "kind": "video", "domain": "vertical product ad",
                                              "purpose": "Stop the scroll, then make the offer.", "structure": [{"role": "hook", "start": [0, .05]}, {"role": "offer"}],
                                              "targets": [{"feature": "cuts_per_min", "range": [15, 40], "provenance": "exemplars"}],
                                              "steps": ["Say the promise in the first two seconds."], "when_to_use": "Short product ads.",
                                              "avoid": "Slow brand films.", "exemplars": [r["id"]]}})
    assert bp["level"] == "observation" and "3+ distinct exemplars" in bp["next_level"]["needs"][0]
    other = clip(tmp_path, "mine")
    report, _ = call(m, "conform", {"blueprint_id": bp["id"], "path": str(other),
                                    "anatomy": [{"role": "hook", "span": {"t": [0, 2]}}, {"role": "offer", "span": {"t": [5, 8]}}]})
    assert report["conformance"] == 1 and report["order_ok"] and report["structure"][0]["start_ok"]
    assert "editvideo_learn" in agent_interface.bootstrap("học từ thành phẩm thành công")["start_here"][0]["tools"]
