"""Render one project in both engines and measure how closely they agree (SSIM on every frame at 480 px).
Usage: python examples/round7/render_both.py <project_id> <name> [--out=r8] [--measure-only]  → outputs/<out>/<name>-{remotion,hyperframes}.mp4"""
import json, subprocess, sys, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store
store.initialize(recover=False)
pid, name = sys.argv[1], sys.argv[2]
out = ROOT / "outputs" / next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--out=")), "r7")  # --out=r8 for later rounds
out.mkdir(parents=True, exist_ok=True)
if "--measure-only" not in sys.argv:
    m.worker.start()
paths = {e: out / f"{name}-{e}.mp4" for e in ("remotion", "hyperframes")}
for a in sys.argv:  # --remotion=<file> / --hyperframes=<file>: measure files rendered elsewhere (a repaired master, a job's visual)
    for e in ("remotion", "hyperframes"):
        if a.startswith(f"--{e}="):
            paths[e] = Path(a.split("=", 1)[1])
only = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")), None)  # --only=hyperframes re-renders one engine
for engine in (() if "--measure-only" in sys.argv else ((only,) if only else ("remotion", "hyperframes"))):
    p = store.get_project(pid)
    store.update_project(pid, {**p["config"], "renderer": engine})
    m.editvideo_export_code(pid, engine=engine, overwrite=True)
    j = m.editvideo_submit_job(pid, "final")
    import time
    while True:
        r = m.editvideo_get_job(j["id"])
        if r.get("state") in ("completed", "failed", "cancelled", "interrupted"):
            break
        time.sleep(10)
    assert r["state"] == "completed", r.get("error")
    files = {a["name"]: a["path"] for a in r.get("artifacts") or []}
    paths[engine] = out / f"{name}-{engine}.mp4"
    shutil.copy(files["final.mp4"], paths[engine])
    if "delivery.zip" in files and engine == "remotion":
        shutil.copy(files["delivery.zip"], out / f"{name}-source.zip")
if "--measure-only" not in sys.argv:
    p = store.get_project(pid)
    store.update_project(pid, {**p["config"], "renderer": "remotion"})
if not all(p_.is_file() for p_ in paths.values()):  # --only=<engine>: one render, nothing to compare
    print(json.dumps({e: str(p_) for e, p_ in paths.items() if p_.is_file()}), flush=True)
    sys.exit(0)
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(paths["remotion"])], capture_output=True, text=True).stdout)
# Timestamps first: a render whose frames repeat or skip a timestamp slides out of step against the other and every
# later cut reads as a divergence (round 13: three repeated timestamps in a Remotion render). Reported apart.
from editvideo.media import frame_grid
grids = {e: frame_grid(str(p), 30) for e, p in paths.items()}
# Every frame, not a sample: 12 evenly spaced frames missed a one-frame glitch at a cut and a 5-frame dissolve dip.
stats, pstats = out / f"{name}-ssim.txt", out / f"{name}-psnr.txt"
subprocess.run(["ffmpeg", "-v", "error", "-i", str(paths["remotion"]), "-i", str(paths["hyperframes"]), "-lavfi",
                "[0:v]setpts=PTS-STARTPTS,scale=480:-2,format=gray,split[a1][a2];[1:v]setpts=PTS-STARTPTS,scale=480:-2,format=gray,split[b1][b2];"
                f"[a1][b1]ssim=stats_file='{stats.name}';[a2][b2]psnr=stats_file='{pstats.name}'", "-f", "null", "-"], cwd=out, check=True)


def column(path, key):
    vals = []
    for line in path.read_text().splitlines():
        try:
            v = line.split(key)[1].split()[0]
            vals.append(99.0 if v == "inf" else float(v))
        except (IndexError, ValueError):
            vals.append(None)
    return vals


per, psnr = column(stats, "All:"), column(pstats, "psnr_avg:")
ok = [x for x in per if x is not None]
# A divergence is an SSIM dip (against its neighbours, or absolute) that PSNR confirms: on dark, noisy or near-black
# frames SSIM swings on encoder noise alone while the pictures match (PSNR stays above ~35 dB).
import statistics
med = lambda i: statistics.median([x for x in per[max(0, i - 15):i + 16] if x is not None])
low = [i for i, x in enumerate(per) if x is not None and (x < .75 or x < med(i) - .08) and (psnr[i] or 99) < 35]
spans = []
for i in low:  # consecutive low frames as [first, last]
    if spans and i == spans[-1][1] + 1:
        spans[-1][1] = i
    else:
        spans.append([i, i])
# Typography at full size: whole-frame SSIM at 480 px cannot see a clipped diacritic. Each text layer's ink box is
# compared at its middle frame in both renders; ink present in one engine and absent in the other (|diff| > 120)
# is counted in pixels (antialiasing differences stay far below; a clipped mark above Â/Ô measured ~1300 px).
import numpy as np
from editvideo import agent
from editvideo.review import _ink_box
t = agent.read(pid)["timeline"]
W, H = t["width"], t["height"]


def grab(path, at):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", at, "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(H, W).astype(np.int16) if len(raw) == W * H else None


ink = {}
for l in [l for l in t.get("layers") or [] if l["kind"] == "text" and l.get("text")][:40]:
    x, y, w, h = _ink_box(l, t.get("design") or {}, W, H)
    at = str(round((l["start_frame"] + l["end_frame"]) // 2 / 30, 4))
    fa, fb = grab(paths["remotion"], at), grab(paths["hyperframes"], at)
    if fa is None or fb is None:
        continue
    x0, y0, x1, y1 = max(0, int((x - .02) * W)), max(0, int((y - .04) * H)), min(W, int((x + w + .02) * W)), min(H, int((y + h + .04) * H))
    ink[l["id"]] = int((np.abs(fa[y0:y1, x0:x1] - fb[y0:y1, x0:x1]) > 120).sum())
# Frame edges at full size: a capture that misses the last columns (HyperFrames portrait on Windows lost 8 px) is a
# thin strip the 480-px comparison averages away. 8-px strips on all four sides, every 15th frame.
edges = {"left": 0, "right": 0, "top": 0, "bottom": 0}
sampled = 0
for f in range(0, len(per), 15):
    fa, fb = grab(paths["remotion"], str(round(f / 30, 4))), grab(paths["hyperframes"], str(round(f / 30, 4)))
    if fa is None or fb is None:
        continue
    sampled += 1
    for side, sl in (("left", np.s_[:, :8]), ("right", np.s_[:, -8:]), ("top", np.s_[:8, :]), ("bottom", np.s_[-8:, :])):
        if np.abs(fa[sl] - fb[sl]).mean() > 12:
            edges[side] += 1
print(json.dumps({"name": name, "duration_s": round(dur, 2), "frames": len(per),
                  "timestamp_defects": {e: g["irregular"][:10] for e, g in grids.items() if g["irregular_count"]} or 0,
                  "edge_mismatch_frames": {k: v for k, v in edges.items() if v} or 0, "edge_frames_checked": sampled,
                  "text_ink_mismatch_px": {k: v for k, v in sorted(ink.items(), key=lambda kv: -kv[1]) if v > 200} or 0, "ssim_min": round(min(ok), 3) if ok else None,
                  "ssim_mean": round(sum(ok) / len(ok), 3) if ok else None, "psnr_min_db": round(min(x for x in psnr if x is not None), 1) if any(x is not None for x in psnr) else None, "divergent_frames": len(low), "divergent_spans": spans[:20],
                  "worst": sorted(((round(x, 3), i) for i, x in enumerate(per) if x is not None))[:5],
                  "files": {k: str(v) for k, v in paths.items()}}, ensure_ascii=False))
