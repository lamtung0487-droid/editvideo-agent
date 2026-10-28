"""Aspect adaptation: clone a project to another canvas (9:16, 4:5, 1:1, 16:9) and re-lay out what is on it.

Footage shots switch to cover with their focus point kept (the subject stays in frame). Layers keep their relative
centre, sizes scale by the short-side ratio (type stays readable instead of shrinking with the width), boxes are
clamped into the target's safe region, pixel keyframes scale per axis, and full-frame layers stay full-frame.
Layers that read as one unit (a panel with its caption and value, a timecard's rows: on screen together, boxes touching)
move as a group: their pixel spacing scales with the type, so a 16:9 card does not come apart on a 9:16 canvas.
The result is audited (audit_timeline) so overflow or UI-zone collisions show up before rendering.
"""
import copy
import shutil
from . import store, platforms

SAFE = {"vertical": platforms.ORGANIC_SAFE, "portrait45": (.06, .06, .94, .90), "square": (.06, .06, .94, .94), "landscape": (.05, .07, .95, .93)}


def _full(l):
    return l.get("x", 0) <= 0 and l.get("y", 0) <= 0 and l.get("width", 0) >= 1 and l.get("height", 0) >= 1


def _place(box, W1, H1, W2, H2, safe, s):
    """Target (x, y, w, h, moved) in frame shares for a source box in frame shares whose pixel size scales by s."""
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    # Proportional placement into the target safe area keeps order and spacing between elements (no pile-ups at
    # the edge); layers already inside the old safe area stay close to where they were.
    cx = safe[0] + cx * (safe[2] - safe[0]) if not (safe[0] <= cx <= safe[2]) else cx
    cy = safe[1] + cy * (safe[3] - safe[1])
    w, h = min(box[2] * W1 * s / W2, safe[2] - safe[0]), min(box[3] * H1 * s / H2, safe[3] - safe[1])
    x = min(max(cx - w / 2, safe[0]), safe[2] - w)
    y = min(max(cy - h / 2, safe[1]), safe[3] - h)
    return x, y, w, h, abs(x - (cx - w / 2)) > .01 or abs(y - (cy - h / 2)) > .01


def _groups(layers, W1, H1):
    """Connected sets of layers that read as one unit: on screen together (overlap ≥ half the shorter span) and boxes
    touching within ~4% of the short side. Full-frame and large (> 35% of frame) layers never glue others together."""
    gap = .04 * min(W1, H1)
    cand = [i for i, l in enumerate(layers) if not _full(l) and l.get("width", 1) * l.get("height", 1) <= .35 and "width" in l]
    parent = {i: i for i in cand}

    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for n, i in enumerate(cand):
        a = layers[i]
        for j in cand[n + 1:]:
            b = layers[j]
            span = min(a["end_frame"], b["end_frame"]) - max(a["start_frame"], b["start_frame"])
            if span < .5 * min(a["end_frame"] - a["start_frame"], b["end_frame"] - b["start_frame"]):
                continue
            dx = max(b["x"] - (a["x"] + a["width"]), a["x"] - (b["x"] + b["width"]), 0) * W1
            dy = max(b["y"] - (a["y"] + a["height"]), a["y"] - (b["y"] + b["height"]), 0) * H1
            if dx <= gap and dy <= gap:
                parent[root(j)] = root(i)
    out = {}
    for i in cand:
        out.setdefault(root(i), []).append(i)
    return [g for g in out.values() if len(g) > 1]


def _relayout(layer, W1, H1, W2, H2, safe, place=None):
    """place: (x, y, w, h, moved, scale) decided for the layer's group; otherwise the layer is placed on its own."""
    l = copy.deepcopy(layer)
    sx, sy, s = W2 / W1, H2 / H1, min(W2, H2) / min(W1, H1)
    for k, pts in (l.get("keyframes") or {}).items():
        f = sx if k == "x" else sy if k == "y" else None
        if f is not None:
            for p in pts:
                p["value"] = round(p["value"] * f, 2)
    if _full(l):
        return l, False
    if place:
        x, y, w, h, moved, s = place
    else:
        x, y, w, h, moved = _place([l["x"], l["y"], l["width"], l["height"]], W1, H1, W2, H2, safe, s)
    l.update(x=round(x, 4), y=round(y, 4), width=round(w, 4), height=round(h, 4))
    if "font_size" in l:
        l["font_size"] = max(12, min(900, round(l["font_size"] * s)))
        txt = (l.get("text") or "").replace("**", "").replace("==", "")
        if l.get("kind") == "text" and txt.strip():
            # A single word cannot wrap: shrink the type until the longest word fits the box (FreeType metrics).
            try:
                from .design_library import layout_text
                font = l.get("font_id") or "bevietnampro"
                longest = max(txt.split(), key=len)
                wpx = layout_text(font, longest, 100, 4000, l.get("font_weight") or 700)["line_widths"][0] * l["font_size"] / 100
                track = next((e["params"].get("amount", 0) for e in l.get("effects") or [] if e["name"] == "tracking"), 0)
                wpx += track * l["font_size"] * len(longest)
                box = l["width"] * W2 * .96
                if wpx > box:
                    l["font_size"] = max(12, int(l["font_size"] * box / wpx))
            except Exception:
                pass
    return l, moved


def adapt(pid, profile, title=None):
    from . import agent
    from .models import PROFILES, Timeline
    if profile not in PROFILES:
        raise ValueError(f"profile is one of {sorted(PROFILES)}")
    src = agent.read(pid)
    t = src.get("timeline")
    if not t:
        raise ValueError("Project has no locked plan to adapt")
    W1, H1 = t["width"], t["height"]
    W2, H2 = PROFILES[profile]
    cfg = {**src["config"], "profile": profile, "title": title or f"{src['config']['title']} ({profile})"}
    cfg.pop("narration_id", None)
    cfg.pop("music_id", None)
    new = agent.create({k: v for k, v in cfg.items() if k in ("title", "script", "spoken_text", "profile", "style", "voice", "voice_rate", "music_volume", "captions", "renderer")})
    nid = new["id"]
    ids = {}
    for a in store.assets(pid):
        path = store.folder(pid) / "assets" / a["file"] if a.get("file") else None
        from .media import safe_asset_path
        try:
            p = safe_asset_path(pid, a["id"])
        except Exception:
            p = path
        if p and p.exists():
            ids[a["id"]] = agent.import_media(nid, str(p), a.get("tags", ""), a.get("role", "illustration") if a.get("role") in ("illustration", "evidence", "metaphor", "reconstruction", "decoration") else "illustration")["id"]
            # Keep the human name and provenance (the stored file is named by its id).
            store.update_asset(nid, ids[a["id"]], {k: a[k] for k in ("name", "source_url") if a.get(k)})
    c = store.get_project(nid)["config"]
    old_cfg = src["config"]
    store.update_project(nid, {**c, **{k: ids[old_cfg[k]] for k in ("narration_id", "music_id") if old_cfg.get(k) in ids}})
    nt = copy.deepcopy(t)
    nt["width"], nt["height"] = W2, H2
    safe = SAFE.get(profile, (.05, .05, .95, .95))
    remap = lambda v: ids.get(v, v)
    src_assets = {a["id"]: a for a in store.assets(pid)}
    from .review import max_magnification
    import math
    for sh in nt["shots"]:
        if sh.get("asset_id"):
            a = src_assets.get(sh["asset_id"]) or {}
            if a.get("width") and a.get("height") and a.get("kind") in ("video", "image"):
                # Cover on the new canvas already enlarges the source (720p on 9:16 ≈ 2.7x): inherited zooms are scaled
                # down in log space (shape and direction kept) so the tightest moment stays near 3x source pixels,
                # keeping at least an 8% move.
                fit = max(W2 / a["width"], H2 / a["height"])
                mag = max_magnification({**sh, "motion": "hold"})
                cap = max(1.08, 3.0 / fit)
                if mag > cap:
                    r = math.log(cap) / math.log(mag)
                    for e in sh.get("effects") or []:
                        if e["name"] in ("focus_zoom", "zoom_in", "zoom_out"):
                            P = e.setdefault("params", {})
                            amt = float(P.get("amount", .08 if e["name"] == "focus_zoom" else .1))
                            if amt > 0:
                                P["amount"] = round((1 + amt) ** r - 1, 4)
            sh["asset_id"] = remap(sh["asset_id"])
            sh["fit"] = "cover"
    # Capping can shrink a punch (a deliberate size change across a cut on one camera) below a readable step: where
    # the source cut changed size by ≥ 8% and the adapted one no longer does, the incoming shot steps out to the
    # plain cover framing instead (a step out is as clear as a step in, and costs no pixels).
    from .review import edge_scale, scale_step
    for i in range(1, len(nt["shots"])):
        a, b = nt["shots"][i - 1], nt["shots"][i]
        a0, b0 = t["shots"][i - 1], t["shots"][i]
        if not a.get("asset_id") or a.get("asset_id") != b.get("asset_id"):
            continue
        if b.get("transition"):
            # A time-passing dissolve on one camera was scale-matched (fixed structures stay put): keep it matched.
            if scale_step(edge_scale(a0, True), edge_scale(b0, False)) < 1.03 and scale_step(edge_scale(a, True), edge_scale(b, False)) >= 1.03:
                b["effects"] = [e for e in b.get("effects") or [] if not (e["name"] == "focus_zoom" and (e.get("params") or {}).get("cut"))]
                if edge_scale(a, True) / edge_scale(b, False) > 1.001:
                    b["effects"].append({"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {
                        "amount": round(edge_scale(a, True) / edge_scale(b, False) - 1, 4), "focus_x": b.get("focus_x", .5), "focus_y": b.get("focus_y", .5), "cut": True}})
            continue
        # Each cut keeps the direction it had (a punch in stays a punch in), judged against the already adapted
        # outgoing shot so the decision runs once, left to right, without rippling.
        was = edge_scale(b0, False) / edge_scale(a0, True)
        now = edge_scale(b, False) / edge_scale(a, True)
        if scale_step(was, 1) < 1.08 or (scale_step(now, 1) >= 1.08 and (now > 1) == (was > 1)):
            continue
        b["effects"] = [e for e in b.get("effects") or [] if not (e["name"] == "focus_zoom" and (e.get("params") or {}).get("cut"))]
        out_end, base = edge_scale(a, True), edge_scale(b, False)
        if was < 1 and out_end / base >= 1.08:
            continue  # step out: the plain cover framing is wide enough
        # step in (or a step out with nowhere wider to go): the smallest readable punch over the outgoing scale, held
        # (the punch is the move; a push on top would take the source past ~3x)
        b["effects"] = [e for e in b["effects"] if e["name"] not in ("focus_zoom", "zoom_in", "zoom_out")]
        b["effects"].append({"name": "focus_zoom", "start_frame": 0, "end_frame": 1,
                             "params": {"amount": round(out_end * 1.081 - 1, 4), "focus_x": b.get("focus_x", .5), "focus_y": b.get("focus_y", .5), "cut": True}})
    moved = []
    layers = []
    s = min(W2, H2) / min(W1, H1)
    place = {}
    for g in _groups(nt.get("layers") or [], W1, H1):
        ls = [nt["layers"][i] for i in g]
        x0, y0 = min(l["x"] for l in ls), min(l["y"] for l in ls)
        x1, y1 = max(l["x"] + l["width"] for l in ls), max(l["y"] + l["height"] for l in ls)
        # The group scales as one unit; if it would not fit the safe area it shrinks uniformly (type included).
        k = min(1, (safe[2] - safe[0]) * W2 / ((x1 - x0) * W1 * s), (safe[3] - safe[1]) * H2 / ((y1 - y0) * H1 * s))
        gx, gy, _, _, mv = _place([x0, y0, x1 - x0, y1 - y0], W1, H1, W2, H2, safe, s * k)
        for l in ls:
            place[l["id"]] = (gx + (l["x"] - x0) * W1 * s * k / W2, gy + (l["y"] - y0) * H1 * s * k / H2,
                              l["width"] * W1 * s * k / W2, l["height"] * H1 * s * k / H2, mv, s * k)
    for l in nt.get("layers") or []:
        if l.get("asset_id"):
            l["asset_id"] = remap(l["asset_id"])
        if l.get("kind") == "scene3d":  # textures/models/backgrounds inside the 3D scene are asset references too
            d = l.get("data") or {}
            for o in d.get("objects") or []:
                for k in ("texture", "bump_texture", "emissive_texture", "alpha_texture", "displacement_texture", "model"):
                    if o.get(k):
                        o[k] = remap(o[k])
            for k in ("background_texture", "environment_texture"):
                if d.get(k):
                    d[k] = remap(d[k])
        nl, mv = _relayout(l, W1, H1, W2, H2, safe, place.get(l["id"]))
        if mv:
            moved.append(l["id"])
        layers.append(nl)
    nt["layers"] = layers
    for a in nt.get("audio_clips") or []:
        a["asset_id"] = remap(a["asset_id"])
    from .planner import validate_sources
    validate_sources(nid, Timeline.model_validate(nt), store.assets(nid))
    plan_src, plan_dst = store.folder(pid) / "plan", store.folder(nid) / "plan"
    plan_dst.mkdir(exist_ok=True)
    for name in ("voice.wav", "words.json"):
        if (plan_src / name).exists():
            shutil.copyfile(plan_src / name, plan_dst / name)
    store.write_json(plan_dst / "timeline.json", nt)
    from .media import sha256
    p = store.get_project(nid)
    store.write_json(plan_dst / "plan-meta.json", {"revision": p["revision"], "audio_hash": sha256(plan_dst / "voice.wav") if (plan_dst / "voice.wav").exists() else None,
                                                   "timeline_hash": sha256(plan_dst / "timeline.json")})
    from .review import audit_timeline
    findings = audit_timeline(nid)["findings"]
    serious = [f for f in findings if f.get("level") in ("likely_problem", "warning")]
    return {"project_id": nid, "profile": profile, "canvas": [W2, H2], "assets": len(ids), "layers_clamped_into_safe_area": moved[:20],
            "groups_kept_together": [[t["layers"][i]["id"] for i in g] for g in _groups(t.get("layers") or [], W1, H1)][:12],
            "audit": {"findings": len(findings), "serious": serious[:8]},
            "next": "snapshot_code a few frames of the new project (text wrapping, faces in frame), then render."}
