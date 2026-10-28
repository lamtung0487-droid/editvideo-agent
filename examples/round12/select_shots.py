"""Round-12 learning test, step 1: find candidate windows for each part of the learned blueprint across every Vietnam
clip, with the system's own senses (SigLIP text search over the footage, brightness per window for time of day).
Writes data/tmp/r12_candidates.json and one contact sheet per query. Usage: python examples/round12/select_shots.py"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
from editvideo import store, semantic
store.initialize(recover=False)
C = ROOT / "data" / "sources" / "commons"
CLIPS = [p for p in sorted(C.glob("*")) if p.suffix.lower() in (".webm", ".ogv", ".mp4")
         and (p.name.startswith("vn-") or p.stem in ("halong_cruise", "halong_dec2024", "hoian_market", "hue_citadel_aerial_1080p", "saigon_traffic"))]
QUERIES = {
    "cold_open": ["aerial view gliding low over calm water at sunrise", "limestone karst islands in a misty bay"],
    "establishing": ["aerial view of karst islands and boats in a bay", "aerial view of a city with a lake", "aerial view of an ancient citadel"],
    "montage_burst": ["hands weaving a basket", "a market full of people", "a busy street with motorbikes", "traditional water puppets",
                      "a water buffalo in a field", "people playing in a park", "a portrait of a person looking at the camera"],
    "dusk_turn": ["a city skyline at sunset", "an airplane window view of clouds and land", "an aerial view of a city at dusk"],
    "night": ["a bridge lit up at night", "city lights at night", "fire at night", "rain on a street at night", "riding through a city at night"],
}


def brightness(path, t):
    _, imgs = semantic.frames(str(path), 1.0, 160, max(0.0, t - .5), t + .5)
    return round(float(np.mean(imgs[0])) / 255, 3) if imgs else None


out = {"clips": [str(p) for p in CLIPS], "roles": {}}
for role, qs in QUERIES.items():
    out["roles"][role] = {}
    for q in qs:
        r = semantic.search([str(p) for p in CLIPS], text=q, window_s=2.0, top=8, fps=1.0)
        rows = []
        for w in r["windows"]:
            at = w["at"]
            rows.append({**{k: v for k, v in w.items() if k != "path"}, "clip": Path(w["path"]).name, "luma": brightness(w["path"], at)})
        out["roles"][role][q] = {"windows": rows, "sheet": r["sheet"]}
        print(role, "|", q, "|", [(x["clip"][:28], x.get("start"), x.get("score")) for x in rows[:4]], flush=True)
(ROOT / "data" / "tmp" / "r12_candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("clips", len(CLIPS))
