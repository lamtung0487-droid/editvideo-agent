"""Visual accents placed from the music's structure: the hierarchy editors use, with a budget per level.

Music level -> what may land there (research round 10; practice, with sync evidence for the timing):
- beat: a light accent (zoom punch) at most once per bar, only in energetic sections;
- phrase (4 bars): one section accent (a flash or a light leak);
- drop (a peak section entered with a loudness step): ONE stacked accent - white flash 1-2 frames, a decaying shake
  8-12 frames, a red/blue split 2-4 frames - with an impact and a riser ending on it.
Accents land on the beat frame or on a cut up to 2 frames before it or 1 after (a lagging sound is noticed from ~45 ms),
only while the music clip plays (its start, source offset and speed map music time to frames), keep 8+ frames apart, and are marked params.accent so a re-run replaces them. Styles carry
the genre: velocity (sports/hype), travel, food, product; nature gets none (flashes and shakes cheapen a wildlife film).
"""
from . import agent, store

FPS = 30
STYLES = {
    "velocity": {"beat": [("impact_zoom", .06, 6)], "beat_sections": {"peak", "build", "body"}, "per_bar": 1,
                 "phrase": [("white_flash", .85, 2)], "drop": [("white_flash", 1.0, 2), ("impact_shake", 30, 11), ("chroma_split", 9, 3)],
                 "sfx_drop": True},
    "travel": {"beat": [], "beat_sections": set(), "per_bar": 0, "phrase": "leak", "drop": [("white_flash", .8, 2), ("impact_zoom", .05, 8)],
               "sfx_drop": True},
    "food": {"beat": [("impact_zoom", .045, 5)], "beat_sections": {"peak", "body"}, "per_bar": 1, "cuts_only": True, "phrase": [],
             "drop": [("impact_zoom", .08, 7)], "sfx_drop": False},
    "product": {"beat": [], "beat_sections": set(), "per_bar": 0, "phrase": [], "drop": [("white_flash", .7, 3), ("impact_zoom", .05, 8)],
                "sfx_drop": True},
    "nature": {"beat": [], "beat_sections": set(), "per_bar": 0, "phrase": [], "drop": [], "sfx_drop": False},
}


def _music(t, pid, music_path, clip_id=None):
    """The music and how it plays: (path, frame of music-file time s, [first, last+1) frames it sounds). The given
    file plays from frame 0 at 1x; the project's music clip (role music) from its start, source_start and speed:
    the clip named by clip_id (a film scored with several cues), else the longest."""
    if music_path:
        return music_path, (lambda s: int(round(s * FPS))), (0, t["total_frames"])
    clips = [c for c in t.get("audio_clips") or [] if c.get("role") == "music"]
    if clip_id:
        clips = [c for c in clips if c["id"] == clip_id]
        if not clips:
            raise ValueError(f"No music clip {clip_id!r} (role music) in the timeline")
    if not clips:
        raise ValueError("No music: pass music_path or add a music audio clip (role music)")
    c = max(clips, key=lambda c: c["end_frame"] - c["start_frame"])
    a = store.find_asset(pid, c["asset_id"])
    rate, s0 = float(c.get("playback_rate") or 1), float(c.get("source_start") or 0)
    return a["path"], (lambda s: int(round(c["start_frame"] + (s - s0) / rate * FPS))), (c["start_frame"], c["end_frame"])


def _target(t, f):
    """The visible item at frame f: a full-frame video layer on top, else the shot."""
    cover = [l for l in t.get("layers") or [] if l.get("kind") == "video" and l["start_frame"] <= f < l["end_frame"]
             and l.get("width", 0) * l.get("height", 0) > .5]
    if cover:
        return "layer", max(cover, key=lambda l: l.get("z", 0))
    sh = next((s for s in t["shots"] if s["start_frame"] <= f < s["end_frame"]), None)
    return ("shot", sh) if sh else (None, None)


def sync(pid, base_revision, request):
    """Place style-appropriate visual accents on beats / phrases / drops of the project's music. Returns what was placed
    (frame, level, effects, item) and what was skipped; dry_run plans only."""
    style = request.get("style", "velocity")
    if style not in STYLES:
        raise ValueError("style velocity|travel|food|product|nature")
    S = STYLES[style]
    p = agent.read(pid)
    if p["revision"] != base_revision:
        raise ValueError("Read the current project revision before placing accents")
    import copy
    t = copy.deepcopy(p["timeline"])
    N = t["total_frames"]
    path, fr, (m0, m1) = _music(t, pid, request.get("music_path"), request.get("music_clip"))
    a0, a1 = max(int(request.get("start_frame", 0)), m0), min(int(request.get("end_frame", N)), m1)  # only while the music plays
    from .music import structure
    st = structure(path, 0, None, tuple(request["bpm_range"]) if request.get("bpm_range") else None)
    # fr: absolute music time to frames, never summed beat lengths (no drift)
    cuts = sorted({s_["start_frame"] for s_ in t["shots"][1:]} | {l[k] for l in t.get("layers") or [] if l.get("kind") == "video"
                                                                for k in ("start_frame", "end_frame") if 0 < l[k] < N})
    # onto a cut up to 2 frames before the beat or 1 after (sound may lead the picture by ~45 ms, never lag far)
    snap = lambda f: min((c for c in cuts if -2 <= c - f <= 1), key=lambda c: abs(c - f), default=f)
    for it in [*t["shots"], *(t.get("layers") or [])]:  # replace earlier accents
        if it.get("effects"):
            it["effects"] = [e for e in it["effects"] if not (e.get("params") or {}).get("accent")]
    placed, skipped, taken = [], [], []
    secs = st.get("sections") or []
    lab = lambda s: next((x["label"] for x in secs if x["start"] <= s < x["end"]), "body")
    drops = request.get("drops")
    if drops is None:  # peak sections entered with a step up in loudness
        drops = [x["start"] for x in secs if x.get("label") == "peak" and (x.get("entry_step_db") or 0) >= 3][:2]

    def place(f, level, stack):
        if not a0 <= f < a1 or not stack:
            return False
        if any(abs(f - g) < 8 for g in taken):
            skipped.append({"frame": f, "level": level, "reason": "within 8 frames of another accent"})
            return False
        kind, item = _target(t, f)
        if not item:
            return False
        local = f - item["start_frame"]
        span = item["end_frame"] - item["start_frame"]
        effs = []
        for name, amount, n in stack:
            if local + 1 >= span:
                break
            effs.append({"name": name, "start_frame": local, "end_frame": min(span - 1, local + n), "params": {"amount": amount, "accent": level}})
        if not effs:
            return False
        if len((item.get("effects") or [])) + len(effs) > 16:
            skipped.append({"frame": f, "level": level, "reason": "item already has 16 effects"})
            return False
        item.setdefault("effects", []).extend(effs)
        taken.append(f)
        placed.append({"frame": f, "level": level, "on": f"{kind}:{item['id']}", "effects": [e["name"] for e in effs]})
        return True

    drop_frames = []
    for s in drops:  # drops are seconds in the music file (as music_structure reports them), mapped through the music clip
        f = snap(fr(s))
        if a0 <= f < a1:
            drop_frames.append(f)
        else:
            skipped.append({"frame": f, "level": "drop", "reason": f"music {s:.2f} s plays outside frames {a0}-{a1} (drops are music-file seconds)"})
    for f in drop_frames:
        place(f, "drop", S["drop"])
    ops_extra = []
    for k, s in enumerate(st.get("phrases_4") or []):
        f = snap(fr(s))
        if f <= a0 + 2 or any(abs(f - d) < 30 for d in drop_frames):
            continue
        if S["phrase"] == "leak":  # a light leak washes over the phrase change (Screen blend, eased)
            if a0 <= f < a1 and not any(abs(f - g) < 8 for g in taken):
                a, b = max(0, f - 6), min(N, f + 12)
                ops_extra.append({"op": "upsert_layer", "layer": {"id": f"accent-leak{k}", "kind": "film", "start_frame": a, "end_frame": b, "x": 0, "y": 0,
                                                                  "width": 1, "height": 1, "z": 890, "blend": "screen",
                                                                  "data": {"type": "light_leak", "intensity": .75, "color": "#ff9a3c", "secondary_color": "#ffd27a",
                                                                           "speed": 2, "seed": 5 + 3 * k},
                                                                  "effects": [{"name": "fade_in", "end_frame": 4}, {"name": "fade_out", "start_frame": b - a - 8, "end_frame": b - a - 1}]}})
                taken.append(f)
                placed.append({"frame": f, "level": "phrase", "on": "layer:light_leak", "effects": ["light_leak"]})
        else:
            place(f, "phrase", S["phrase"])
    if S["per_bar"] and S["beat"]:
        for s in st.get("bar_starts") or []:
            if lab(s) not in S["beat_sections"]:
                continue
            f = fr(s)
            if S.get("cuts_only"):
                c = min((c for c in cuts if -3 <= c - f <= 1), key=lambda c: abs(c - f), default=None)
                if c is None:
                    continue
                f = c
            place(snap(f), "beat", S["beat"])
    ids = {l["id"] for l in t.get("layers") or []}
    t["layers"] = [l for l in t.get("layers") or [] if not l["id"].startswith("accent-leak")]
    result = {"style": style, "bpm": st["bpm"], "pulse": st["pulse"], "drops": drop_frames, "placed": sorted(placed, key=lambda x: x["frame"]),
              "skipped": skipped[:20], "counts": {lv: sum(1 for x in placed if x["level"] == lv) for lv in ("drop", "phrase", "beat")}}
    if style == "nature":
        result["note"] = "No visual accents for a wildlife film: cut on action, let ambience lead, ramp only into the strike."
    if request.get("dry_run"):
        return {**result, "dry_run": True}
    rev, sound_ops = base_revision, []
    if S.get("sfx_drop") and drop_frames and request.get("sfx", True):  # the sound that goes with the stacked accent
        from .audiofx import prepare
        r = prepare(pid, rev, {"hits": [{"frame": f, "kind": "impact"} for f in drop_frames] + [{"frame": f, "kind": "riser"} for f in drop_frames],
                               "replace": True, "prefix": "accent-sfx"})  # its own sounds: earlier sfx_sync clips stay
        rev, sound_ops = r["revision"], r["ops"]  # importing the sounds adds assets; the timeline is untouched until the patch
        result["sfx"] = r["placed"]
    # one atomic patch: the accents, the leaks and their sounds land together or not at all
    rev = agent.patch(pid, rev, [{"op": "replace_timeline", "timeline": t}, *ops_extra, *sound_ops])["revision"]
    return {**result, "revision": rev, "removed_leaks": sorted(i for i in ids if i.startswith("accent-leak"))}
