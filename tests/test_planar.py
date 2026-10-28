"""Planar tracking: perspective motion with a crossing occluder, mapping into the frame, and the pinned layer."""
import subprocess
import numpy as np
import pytest
cv2 = pytest.importorskip("cv2")
from editvideo import planar


def _clip(path, n=40, W=640, H=360):
    rng = np.random.default_rng(2)
    poster = cv2.GaussianBlur((rng.random((200, 300, 3)) * 255).astype(np.uint8), (0, 0), 2)
    for k in range(30):
        cv2.putText(poster, chr(65 + k % 26), (int(rng.uniform(0, 270)), int(rng.uniform(20, 190))), cv2.FONT_HERSHEY_SIMPLEX, rng.uniform(.5, 1.4),
                    tuple(int(v) for v in rng.integers(0, 255, 3)), 2)
    bg = cv2.GaussianBlur((rng.random((H, W, 3)) * 255).astype(np.uint8), (0, 0), 5)
    src = np.float32([[0, 0], [300, 0], [300, 200], [0, 200]])
    truth, frames = [], []
    for i in range(n):
        a = i / (n - 1)
        dst = np.float32([[150 + 60 * a, 75 + 15 * np.sin(3 * a)], [425 + 30 * a, 60 + 25 * a], [450 - 10 * a, 280 + 10 * a], [140 + 45 * a, 300 - 20 * a]])
        M = cv2.getPerspectiveTransform(src, dst)
        fr = bg.copy()
        m = cv2.warpPerspective(np.full((200, 300), 255, np.uint8), M, (W, H))
        fr[m > 0] = cv2.warpPerspective(poster, M, (W, H))[m > 0]
        x = int(100 + 450 * a)
        cv2.rectangle(fr, (x, 125), (x + 45, 260), (20, 20, 20), -1)  # occluder crossing the plane
        frames.append(fr)
        truth.append(dst / [W, H])
    raw = np.stack(frames)[..., ::-1].tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "30", "-i", "-", "-c:v", "libx264", "-crf", "14",
                    "-pix_fmt", "yuv420p", str(path)], input=raw, check=True)
    return truth


def test_plane_track_is_subpixel_through_an_occluder(tmp_path):
    truth = _clip(tmp_path / "p.mp4")
    r = planar.track_plane(str(tmp_path / "p.mp4"), truth[0].tolist(), 0, 40 / 30, work_width=640, exclude=[[100 / 640, 125 / 360, 145 / 640, 260 / 360]])
    assert r["lost_at_frame"] is None and r["frames_tracked"] == 40
    err = max(np.abs((np.array(s["corners"]) - truth[s["frame"]]) * [640, 360]).max() for s in r["track"])
    assert err < 2.0
    with pytest.raises(ValueError):
        planar.track_plane(str(tmp_path / "p.mp4"), [[.3, .2], [.25, .8], [.7, .2], [.7, .8]], 0, 1)  # crossed quad


def test_to_frame_maps_cover_and_contain():
    track = [{"frame": 0, "corners": [[0, 0], [1, 0], [1, 1], [0, 1]]}, {"frame": 5, "corners": [[.5, .5], [.6, .5], [.6, .6], [.5, .6]]}]
    full = planar.to_frame(track, (1920, 1080))
    assert full[0]["corners"] == [[0, 0], [1, 0], [1, 1], [0, 1]]
    sq = planar.to_frame(track, (1000, 1000), fit="contain")  # square source letterboxed in 16:9: x from 420 to 1500
    assert abs(sq[0]["corners"][0][0] - 420 / 1920) < 1e-4 and sq[0]["corners"][2] == [round(1500 / 1920, 5), 1.0]
    shifted = planar.to_frame(track, (1920, 1080), source_start_frame=3)
    assert [s["frame"] for s in shifted] == [2]
