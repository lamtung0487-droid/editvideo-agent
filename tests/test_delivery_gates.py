"""The delivery gates reach an MCP client: motion_audit(gates=true) reads them on any encoded file."""
import subprocess


def test_motion_audit_returns_the_delivery_gates_on_request(tmp_path):
    import editvideo.mcp_server as m
    from editvideo.media import FFMPEG
    clip = tmp_path / "c.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=2:r=30", "-pix_fmt", "yuv420p", str(clip)], check=True)
    plain = m.editvideo_motion_audit(str(clip))
    assert "delivery_gates" not in plain
    r = m.editvideo_motion_audit(str(clip), gates=True)["delivery_gates"]
    assert {"legal_levels", "flashes", "still", "black", "banding"} <= set(r["gates"]) and isinstance(r["pass"], bool)
