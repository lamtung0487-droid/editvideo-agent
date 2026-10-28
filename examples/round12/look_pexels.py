"""Round-12 remake, step 1: grade the picture of every downloaded Pexels clip with editvideo.look, a 2.4 s window about
every twelfth of the clip (at most 14), and print each clip's grades (A keep, B usable, C reject) with its median
shake and warmth. Writes data/tmp/r12_px_look.json. Usage: python examples/round12/look_pexels.py"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import store
from editvideo.look import measure
from editvideo.media import probe
store.initialize(recover=False)
out = {}
for p in sorted((ROOT / "data" / "sources" / "other").glob("px-*.mp4")):
    dur = float(probe(str(p))["format"]["duration"])
    rows, t = [], 0.3
    while t + 2.4 <= dur - .2 and len(rows) < 14:
        r = measure(str(p), t, t + 2.4, samples=2)
        rows.append({"t": round(t, 1), "grade": r["grade"], "shake": r["shake_px"], "detail": round(r["detail"], 3), "iso": round(r["isolation"], 2),
                     "warm": round(r["warmth"], 3), "sat": round(r["saturation"], 2), "mean": round(r["mean"], 2), "flags": r["flags"]})
        t += max(2.4, (dur - 2.6) / 12)
    out[p.name] = {"dur": round(dur, 1), "windows": rows}
    g = "".join(w["grade"] for w in rows)
    print(f"{p.name[:60]:60} {dur:5.1f}s {g:14} shake~{sorted(w['shake'] for w in rows)[len(rows) // 2]:.2f} "
          f"warm~{sorted(w['warm'] for w in rows)[len(rows) // 2]:+.3f}", flush=True)
(ROOT / "data" / "tmp").mkdir(parents=True, exist_ok=True)
(ROOT / "data" / "tmp" / "r12_px_look.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
