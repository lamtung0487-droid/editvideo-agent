"""Animation quality from the runtime's own transforms (exactly what both engines draw): spacing, stops, arcs, twins.

Measured references (round-4 study): an eased move peaks at ~1.5-2.3x its mean speed (power2 in-out ≈ 2.3x); a linear
move is 1.0x and reads mechanical. Organic moves travel on arcs; mechanical UI moves may be straight on purpose. A move
that stops at more than ~35 % of its peak speed without overshoot reads as a collision. Siblings that start on the
same frame with the same curve ("twins") look robotic; stagger them by 2-4 frames.
"""
import json
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from . import store

JS = r"""const FX=require(process.argv[1]);const items=JSON.parse(require('fs').readFileSync(process.argv[2],'utf8'));const out={};
for(const L of items){const n=Math.max(1,L.end_frame-L.start_frame),rows=[];for(let f=0;f<n;f++){const r=FX.styleAt(L,f,true);rows.push([r.x,r.y,r.scale,r.rot,r.sx||1,r.sy||1]);}out[L.id]=rows;}
console.log(JSON.stringify(out));"""


def sample(layers):
    with tempfile.TemporaryDirectory() as tmp:
        fx = Path(tmp) / "fx.cjs"
        fx.write_bytes((store.ROOT / "engines/effects.js").read_bytes())
        data = Path(tmp) / "layers.json"
        data.write_text(json.dumps(layers), encoding="utf-8")
        out = subprocess.run(["node", "-e", JS, str(fx), str(data)], capture_output=True, text=True, encoding="utf-8", timeout=120, check=True).stdout
    return {k: np.array(v, float) for k, v in json.loads(out).items()}


def _moves(speed, thresh=.5, min_len=6):
    m, i, n = [], 0, len(speed)
    while i < n:
        if speed[i] > thresh:
            j = i
            while j < n and speed[j] > thresh * .5:
                j += 1
            if j - i >= min_len:
                m.append((i, j))
            i = j
        else:
            i += 1
    return m


def audit(pid, layer_ids=None, W=None, H=None):
    from . import agent
    t = agent.read(pid)["timeline"]
    W, H = W or t["width"], H or t["height"]
    pool = [l for l in t.get("layers") or [] if (not layer_ids or l["id"] in layer_ids) and (l.get("keyframes") or any(
        e["name"] in ("slide_left", "slide_right", "rise", "drop", "pop", "spring", "slide_spring", "orbit", "float") for e in l.get("effects") or []))]
    if not pool:
        return {"layers": 0, "findings": [], "note": "No animated layers."}
    S = sample(pool[:40])
    findings, rows = [], []
    F = lambda level, code, where, ev, sug: findings.append({"level": level, "code": code, "where": where, "evidence": ev, "suggestion": sug})
    for l in pool[:40]:
        a = S[l["id"]]
        pos = a[:, :2]
        v = np.r_[0, np.hypot(*np.diff(pos, axis=0).T)]
        mods = l.get("track_mods") or {}
        info = {"layer": l["id"], "moves": 0}
        for s, e in _moves(v):
            seg = v[s:e]
            travel = float(np.hypot(*(pos[e - 1] - pos[s])))
            if travel < 30:
                continue
            info["moves"] += 1
            ratio = float(seg.max() / max(1e-6, seg.mean()))
            frame0 = l["start_frame"] + s
            if ratio < 1.15 and e - s >= 8:
                F("check", "mechanical_move", l["id"], f"frames {frame0}-{l['start_frame'] + e}: peak/mean speed {ratio:.2f} (linear)",
                  "Ease it (eased moves peak at 1.5-2.3x mean) unless constant speed is the point.")
            end_ratio = float(seg[-1] / max(1e-6, seg.max()))
            overshoot = e + 2 < len(v) and np.any(v[e:e + 6] > .3)
            if end_ratio > .35 and not overshoot and not any(k in mods for k in ("x", "y")):
                F("check", "abrupt_stop", l["id"], f"stops at {end_ratio:.0%} of peak speed at frame {l['start_frame'] + e}",
                  "Ease out, or let it overshoot and settle (track_mods inertia) unless it hits something.")
            dx, dy = np.ptp(pos[s:e, 0]), np.ptp(pos[s:e, 1])
            if dx > 20 and dy > 20:
                p0, p1 = pos[s], pos[e - 1]
                q = pos[s:e] - p0
                d = np.abs((p1 - p0)[0] * q[:, 1] - (p1 - p0)[1] * q[:, 0]) / max(1e-6, np.hypot(*(p1 - p0)))
                if d.max() / max(1e-6, np.hypot(*(p1 - p0))) < .02:
                    F("info", "straight_path", l["id"], f"move at frame {frame0} travels a straight chord", "Organic moves arc: ease x and y differently.")
        sq = a[:, 4] * a[:, 5]
        if np.ptp(a[:, 4]) > .02 and np.max(np.abs(sq - 1)) > .08 and "squash" in (l.get("keyframes") or {}):
            F("check", "volume_change", l["id"], f"area changes by {np.max(np.abs(sq - 1)):.0%}", "Squash keeps area: use the squash track, not scale_x/scale_y alone.")
        rows.append(info)
    sig = {}
    for l in pool:
        kf = l.get("keyframes") or {}
        key = (l["start_frame"], json.dumps({k: [(p["frame"], p.get("easing"), p.get("bezier")) for p in v] for k, v in sorted(kf.items())}))
        if kf:
            sig.setdefault(key, []).append(l["id"])
    for ids in sig.values():
        if len(ids) > 1:
            F("info", "twinning", ",".join(ids[:6]), f"{len(ids)} layers start together with identical curves", "Stagger by 2-4 frames or vary the curve.")
    return {"layers": len(pool), "summary": rows[:20], "findings": findings[:12],
            "note": "Sampled from effects.js styleAt (the shared runtime). Intent may overrule a heuristic: say why."}
