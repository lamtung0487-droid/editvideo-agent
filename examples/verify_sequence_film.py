"""Offline integration evidence for new short-form/film tools (test patterns, not a diffusion-generated film).

Two local source videos, known colours/tones, multi-source edit, both engines, real audio and frame checks;
plus a persistent film world -> valid generation request round trip without calling a provider.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from editvideo import store, agent, mcp_server as m
from editvideo.media import FFMPEG, command, probe, sha256


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    store.initialize(recover=False)
    out = ROOT / "outputs" / "shortform-film-research"
    out.mkdir(parents=True, exist_ok=True)
    clips = []
    for name, colour, hz in [("a", "0x1b4761", 440), ("b", "0x854f42", 880)]:
        path = out / (name + ".mp4")
        command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=640x360:r=30:d=5",
                 "-f", "lavfi", "-i", f"sine=frequency={hz}:sample_rate=48000:duration=5", "-c:v", "libx264",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path])
        clips.append(path)
    candidate = lambda name, p, a, b, rel=1: {"id": name, "path": str(p), "start": a, "end": b,
                                            "relevance": rel, "reason": "Known synthetic source for integration verification.", "fit": "cover"}
    request = {"title": "Short-form integration test", "budget_seconds": 4, "minimum_seconds": 4,
               "profile": "vertical", "beats": [
                   {"id": "hook", "purpose": "Question", "candidates": [candidate("long", clips[0], 0, 4), candidate("compact", clips[0], 1, 3, .8)]},
                   {"id": "payoff", "purpose": "Answer", "candidates": [candidate("answer", clips[1], 2, 4)]}]}
    planned = m.editvideo_sequence_plan(request=request)
    built = m.editvideo_sequence_plan(plan_id=planned["plan_id"], build=True)
    pid = built["project_id"]
    p = agent.read(pid)
    layers = []
    for i, label in enumerate(("CÂU HỎI", "LỜI GIẢI")):
        layers.append({"op": "upsert_layer", "layer": {"id": "label-" + str(i), "kind": "text", "text": label,
                       "start_frame": i * 60, "end_frame": (i + 1) * 60, "x": .08, "y": .38, "width": .78, "height": .15,
                       "font_id": "inter", "font_size": 88, "font_weight": 700, "color": "#ffffff", "z": 100}})
    m.editvideo_patch_timeline(pid, p["revision"], layers)
    evidence = {}
    for engine in ("remotion", "hyperframes"):
        rev = store.get_project(pid)["revision"]
        if store.get_project(pid)["config"]["renderer"] != engine:
            m.editvideo_configure_project(pid, rev, {"renderer": engine})
        m.editvideo_export_code(pid, engine)
        job = store.create_job(pid, "final")
        m.worker.run(job["id"])
        state = store.get_job(job["id"])
        if state["state"] != "completed":
            raise RuntimeError(state)
        final = out / f"sequence-{engine}.mp4"
        shutil.copy2(store.folder(pid) / "jobs" / job["id"] / "final.mp4", final)
        command([FFMPEG, "-v", "error", "-i", final, "-f", "null", "-"], timeout=120)
        raw = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(final), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"])
        audio = np.frombuffer(raw, np.float32)
        tones = []
        for at in (.5, 2.5):
            window = audio[int(at * 48000):int((at + .5) * 48000)]
            spectrum = abs(np.fft.rfft(window * np.hanning(len(window))))
            tones.append(float(np.fft.rfftfreq(len(window), 1 / 48000)[int(spectrum.argmax())]))
        assert abs(tones[0] - 440) < 5 and abs(tones[1] - 880) < 5, tones
        colours = []
        for at in (.5, 2.5):
            raw = subprocess.check_output([FFMPEG, "-v", "error", "-ss", str(at), "-i", str(final), "-frames:v", "1", "-vf", "scale=108:192", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
            frame = np.frombuffer(raw, np.uint8).reshape(192, 108, 3)
            colours.append(frame[25, 25].tolist())
        assert colours[0][2] > colours[0][0] + 30 and colours[1][0] > colours[1][2] + 30, colours
        info = probe(final)
        evidence[engine] = {"path": str(final), "sha256": sha256(final), "audio_peak_hz": tones,
                            "sample_colours": colours, "duration_s": float(info["format"]["duration"]), "decoded": True}
    world = {"title": "The key", "premise": "A courier finds an unexpected door.", "look": "Warm natural light, quiet camera, original fictional characters",
             "entities": [{"id": "linh", "kind": "character", "description": "Short black hair, green coat", "initial_state": {"holds": "nothing"}},
                          {"id": "key", "kind": "prop", "description": "Brass key"}],
             "shots": [{"id": "pick", "scene": "room", "purpose": "Discovery", "action": "Linh picks up a brass key from a table.",
                        "seconds": 3, "entities": ["linh", "key"], "framing": "insert", "changes": {"linh": {"holds": "key"}}},
                       {"id": "door", "scene": "room", "purpose": "A choice", "action": "Linh approaches a closed door, still holding the brass key.",
                        "seconds": 3, "entities": ["linh", "key"], "requires": {"linh": {"holds": "key"}}}]}
    saved = m.editvideo_film_world(request=world)
    packet = m.editvideo_film_world(world_id=saved["world_id"], shot_id="door")
    assert packet["state_before"]["linh"]["holds"] == "key" and packet["generation_call"]
    store.write_json(out / "shot-packet.json", packet)
    result = {"plan": planned, "built": built, "renders": evidence, "film_world": saved, "packet": str(out / "shot-packet.json"),
              "limits": "Synthetic source edits verify engineering only; no provider invoked, no identity or film-quality claim."}
    store.write_json(out / "integration.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
