"""Round-12 remake, step 2: the same learned grade as grade_pieces.py, applied lightly (strength .35) to the approved
Pexels clips: they arrive already graded by their makers, so the match only pulls them toward one palette.
Cached in data/tmp/r12_graded_px.json. Usage: python examples/round12/grade_pexels.py"""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, media_tasks
from editvideo.media import probe
store.initialize(recover=False)
REF = ROOT / "data" / "references" / "beauty-of-vietnam" / "reference.mp4"
LOOK = {"dawn": [10.3, 21.0], "day": [21.0, 26.0, 31.0], "people": [41.0, 44.0, 46.3], "dusk": [67.0, 72.0, 87.0], "night": [103.0, 107.0, 118.0]}
cache_f = ROOT / "data" / "tmp" / "r12_graded_px.json"
cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.is_file() else {}
for p in sorted((ROOT / "data" / "sources" / "other").glob("px-*.mp4")):
    key = p.name.split("-")[2]  # the Pexels id
    if key in cache and Path(cache[key]["path"]).is_file():
        continue
    role = p.name.split("-")[1]
    info = probe(str(p))
    v = next(x for x in info["streams"] if x["codec_type"] == "video")
    dur = float(info["format"]["duration"])
    times = [round(dur * f, 2) for f in (.2, .5, .8)]
    mt = m.editvideo_color_match(str(p), times, str(REF), LOOK[role], .35)
    tags = {} if v.get("color_transfer") or v.get("color_primaries") else {"input_space": "bt709"}
    if v.get("color_range") not in ("tv", "pc"):
        tags["input_range"] = "limited"
    task = m.editvideo_process_color({"path": str(p), "start": 0, "end": min(dur - .05, 120), "grade": mt["grade"], **tags})
    tid = task.get("id") or task.get("task_id")
    while True:
        st = media_tasks.get(tid)
        if st["state"] in media_tasks.TERMINAL:
            break
        time.sleep(4)
    if st["state"] != "completed":
        print(key, "FAILED", st.get("error", "")[-200:], flush=True)
        continue
    arts = (st.get("result") or {}).get("artifacts") or {}
    cache[key] = {"path": arts.get("video"), "source": p.name, "role": role, "task": tid, "residual": mt.get("residual")}
    cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(key, role, "graded", flush=True)
print("done", len(cache))
