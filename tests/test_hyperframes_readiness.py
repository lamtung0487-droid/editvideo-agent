"""Round 13: a HyperFrames snapshot whose first requested frame lay inside a freeze shot came out black (frame 706 of a
104-shot film; 700 then 706 were both right). The CLI seeked before hyper-runtime.js had built its timeline."""
import subprocess
from pathlib import Path
import numpy as np
import pytest
from editvideo import store
from editvideo.media import FFMPEG

ENGINES_READY = (Path(__file__).parents[1] / "engines" / "node_modules").is_dir()


@pytest.mark.skipif(not ENGINES_READY, reason="Local rendering dependencies not installed")
def test_first_hyperframes_snapshot_waits_for_a_slow_build(tmp_path, monkeypatch):
    """The page's build is slowed past the CLI's 5 s readiness wait (loadFonts held 8 s, as a long film's fonts, 3D
    assets and held frames take): the only frame asked for, inside a freeze shot, still shows the frozen picture, as in
    Remotion. Without the build holding HyperFrames' readiness, or with the CLI's default wait, it was black."""
    from PIL import Image
    from editvideo import agent
    from editvideo.code_engine import scaffold
    from editvideo.snapshot import snapshot
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    clip = tmp_path / "clip.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    seen = {}
    for engine in ("remotion", "hyperframes"):
        pid = agent.create_silent("landscape", 30, engine, "ready")["id"]
        aid = agent.import_media(pid, str(clip), "clip", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
        p = agent.read(pid)
        t = p["timeline"]
        base = {**t["shots"][0], "asset_id": aid, "fit": "cover", "text": "", "motion": "hold", "effects": []}
        t["shots"] = [{**base, "id": "a", "start_frame": 0, "end_frame": 15, "source_start": .5, "freeze": True},
                      {**base, "id": "b", "start_frame": 15, "end_frame": 30, "source_start": 1}]
        agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
        scaffold(pid, engine, False)
        if engine == "hyperframes":
            with open(store.folder(pid) / "code" / engine / "design.js", "a", encoding="utf-8") as f:
                f.write("\n;(()=>{const D=window.EditVideoDesign,load=D.loadFonts;"
                        "D.loadFonts=async(...a)=>{await new Promise(r=>setTimeout(r,8000));return load.apply(D,a);};})();\n")
        with Image.open(snapshot(pid, engine, [5])["frames"][0]["path"]) as im:
            seen[engine] = np.asarray(im.convert("RGB").resize((160, 90)), np.float32)
    assert seen["hyperframes"].mean() > 60, seen["hyperframes"].mean()  # an unbuilt page is black (mean 0)
    assert np.abs(seen["hyperframes"] - seen["remotion"]).mean() < 12  # the same frozen frame
    monkeypatch.setattr("editvideo.snapshot.READY_TIMEOUT_MS", 2000)  # a page still building when the wait ends is an error,
    with pytest.raises(ValueError, match="not ready"):                # not a black frame returned as evidence
        snapshot(pid, "hyperframes", [5])
