"""Round-12 remake, step 0: download the Pexels clips the user approved (2026-10-21: 25 files, ~691 MB; the three
optional large files were not approved). pexels_clips.json lists them as read from Pexels' pages: [id, file URL,
width, height, seconds, fps, maker, title, role, MB]. Downloads go through resources.fetch_source (provenance, licence,
size check); never add to this list without the user's approval of names, source and sizes.
Usage: python examples/round12/fetch_pexels.py"""
import json, re, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import store, resources
store.initialize(recover=False)
SKIP = {32793607, 33861471, 12742205}  # not approved
rows = [r for r in json.loads((Path(__file__).parent / "pexels_clips.json").read_text(encoding="utf-8")) if r[0] not in SKIP]
dest = ROOT / "data" / "sources" / "other"
for vid, url, w, h, dur, fps, author, title, role, mb in rows:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"px-{role}-{vid}-{title}")[:90] + ".mp4"
    if (dest / name).exists():
        continue
    try:
        r = resources.fetch_source(url, "other", title, "Pexels License", f"{author.strip()} / Pexels",
                                   f"https://www.pexels.com/video/{vid}/", "footage", name, int(mb * 1e6) if mb > 0 else None, f"round12 remake {role}")
        print(vid, "ok", r.get("path"), flush=True)
    except Exception as e:
        print(vid, "ERROR", str(e)[:200], flush=True)
    time.sleep(2)
