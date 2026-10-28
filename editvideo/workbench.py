"""Compact actionable scene context: a directing aid, not a beauty judge or a studio."""
from collections import Counter
import shutil
from . import store, agent_interface

CARDS = [
    ("data_story", "số liệu number data so sanh compare", "Make quantities visible with sourced grids, pictograms or a chart; keep disputed sources separate."),
    ("document_highlight", "tài liệu document letter thư điện quotation quote", "Show the original passage/source; underline only the words supporting the spoken point."),
    ("history_map", "địa điểm place map bản đồ chiến dịch đường hành trình", "Orient the viewer, then reveal a route/date or place footage. Label simulations clearly."),
    ("archive_montage", "montage dồn dập leo thang escalation thảm họa sắp đến dread blockbuster godzilla tư liệu nhạc", "Real archive cut tighter and tighter over a driving cue (WWZ 2.4 -> 0.6 s), dates and a few hard cards, a silent black, the hit, a white-out; score() gives the sound."),
    ("map_matte", "bản đồ lan rộng spread map matte dawn tư liệu trong lãnh thổ sự kiện theo ngày", "No cut: one camera move over a map, archive playing inside the land it was shot in, sourced events lighting up as a date clock walks, then the map drains."),
    ("dossier", "hồ sơ tài liệu giải mật document dossier godzilla se7en điện mật ảnh", "The story's own documents and photographs on a desk, 2-2.5 s each through dissolves and pushes, pencil marks and withheld passages, a white-out."),
    ("news_montage", "bản tin news bulletin montage truyền hình", "Begin with a readable broadcast, then vary density, resolve on a held picture or deliberate silence."),
    ("credibility_gap", "tuyên bố claim record hồ sơ hai phía mâu thuẫn", "Let the viewer read a dated claim, then bring in the sourced record alongside it."),
    ("photo_3d", "ảnh photo still chiều sâu parallax", "Give a still a motivated move toward the subject; restrained parallax and honest reconstruction label."),
    ("night_log", "đêm night campaign diễn tiến progression", "Carry a dated progression in a reserved corner; hide/delay it over full-screen dates and subtitles."),
]


def scene(project_id, start=0, end=8, purpose="", recipe=None):
    from . import agent, cinematic
    p = agent.read(project_id)
    t = p.get("timeline")
    if not t: raise ValueError("A locked timeline is required")
    if not 0 <= start < end <= min(start + 15, t["total_frames"] / 30): raise ValueError("Scene window must fit timeline and be <=15s")
    a, b = int(start * 30), min(t["total_frames"], round(end * 30))
    shots = [s for s in t["shots"] if s["start_frame"] < b and s["end_frame"] > a]
    layers = [l for l in t["layers"] if l["start_frame"] < b and l["end_frame"] > a]
    norm = agent_interface.normalized(purpose)
    terms = set(norm.split())
    ranked = sorted(CARDS, key=lambda c: -len(terms.intersection(agent_interface.normalized(c[1]).split())))
    cards = [{"recipe": key, "use": why, "schema": "workbench(recipe='" + key + "')"} for key, _, why in ranked[:3]]
    from .code_engine import available_memory_mb
    used = Counter(l["kind"] for l in t["layers"])
    from . import narrative, directing
    meaning = narrative.context(project_id,t,start,end)
    result = {"project_id": project_id, "revision": p["revision"], "window_frames": [a, b],
              "canvas": [t["width"], t["height"]], "purpose": purpose,
              "shots": [{**{k: s.get(k) for k in ("id", "start_frame", "end_frame", "asset_id", "source_start", "role")},
                         "reason": str(s.get("reason") or "")[:180]} for s in shots[:24]],
              "shot_count": len(shots),
              "layers": [{"id": l["id"], "kind": l["kind"], "frames": [l["start_frame"], l["end_frame"]], "text": l.get("text", "")[:120],
                          "box": [l["x"], l["y"], l["width"], l["height"]]} for l in layers[:16]],
              "layer_count": len(layers), "full_context": "read_edit_context for paged exact layer properties",
              "captions": [c for c in t["cues"] if c["start"] < end and c["end"] > start][:6],
              "project_inventory": dict(used), "techniques": cards,
              "meaning": meaning,
              "craft": directing.craft([b.get('role') for b in meaning['beats']])[:3],
              "delivery_subtitles": {f.stem: str(f) for f in sorted((store.folder(project_id) / "plan/subtitles").glob("*.json"))[:8]},
              "inspect_frames": sorted(set([a, min(b - 1, (a + b) // 2), b - 1])),
              "resources": {"data_root": str(store.DATA), "free_gb": round(shutil.disk_usage(store.DATA).free / 1e9, 1), "available_commit_mb": available_memory_mb()},
              "next": ["State what this scene must communicate; inspect the frame/audio windows.",
                       "Read one exact recipe schema, compose dry_run, inspect only touched frames, then patch at this revision.",
                       "Use finish_video for verified-base layer repairs and subtitle/audio delivery; poll task instead of rerendering the whole film."],
              "limits": "Suggestions match declared purpose only. No model loaded, no whole-film audit, no automatic semantic or aesthetic judgment. Use one motivated technique, not every effect."}
    if recipe:
        if recipe not in cinematic.RECIPES: raise ValueError("Use a recipe in cinematic_catalog")
        result["recipe_schema"] = cinematic.RECIPES[recipe].model_json_schema()
    return result
