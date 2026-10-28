"""Trailer grammar: a structure planner aligned to the music, and an audit of a cut against measured trailer practice.

Measured (round-3 study of trailer-editing tutorials and the trailers they dissect, local analysis only):
cold opens ~10.5-11.8 s; median shot length by act 1.22 s (cold open) / 0.73 / 0.65 (act 2, tightest) / 1.00 (act 3,
held lines mixed with fast bursts); act changes land on a cut with a level step; a 0.3-0.9 s dip precedes act cards
and the climax hit; the climax holds ~9 s of steady loud music; the title starts on the last hit and holds ~2.3 s while
the tail decays; a dialogue-led button of 6-8 s follows. Orchestral beds have a weak pulse: cut to hits, section changes
and quiet gaps, not to a beat grid.
"""
import statistics
from .music import FPS

ACT_MEDIAN_S = {"cold_open": 1.22, "act1": .73, "act2": .65, "act3": 1.0}
DIALOGUE = {"cold_open": "a hook line with little context", "act1": "exposition or an open question",
            "act2": "conflict plus doubt (do not spoil the answer)", "act3": "broad thematic lines that fit almost any picture (stakes, certainty)",
            "button": "one last joke or tease"}


def plan(duration_s, music_path=None, bpm_range=None, bumper=True, logos=True):
    """Section plan for a trailer of duration_s seconds. With music_path the act changes move to section entries or hits,
    the title lands on the strongest hit after the loudest stretch, and dips are taken from real quiet gaps."""
    if not 20 <= duration_s <= 300:
        raise ValueError("duration_s is 20..300 seconds")
    D = float(duration_s)
    use_bumper = bumper and D >= 60
    seg = []
    t = 0.0
    def add(name, length, **kw):
        nonlocal t
        seg.append({"section": name, "start": round(t, 2), "end": round(t + length, 2), **kw})
        t += length
    if use_bumper:
        add("bumper", 4.0, purpose="3-6 s of the best moments before the trailer proper (YouTube)", median_shot_s=.5)
    add("cold_open", min(15.0, max(8.0, .12 * D)), purpose="hook with little context; dialogue-led, music low or absent",
        median_shot_s=ACT_MEDIAN_S["cold_open"], dialogue=DIALOGUE["cold_open"], sound="after the punchline ~0.9 s of quiet, then logos/music ~20 dB louder")
    if logos and D >= 75:
        add("logos", 3.5, purpose="studio/brand cards on the first music entry")
    title, button = 2.5, min(10.0, max(5.0, .07 * D))
    rest = D - t - title - button
    if rest < 9:
        raise ValueError("duration too short for three acts after the cold open; drop bumper/logos or lengthen")
    for name, share in (("act1", .3), ("act2", .33), ("act3", .37)):
        add(name, rest * share, purpose={"act1": "premise and world; music builds anticipation without drawing attention",
                                          "act2": "conflict or antagonist enters on a level step; the tightest cutting",
                                          "act3": "climax: the big cue; held lines mixed with bursts of 0.4-0.8 s shots, ≥6 s of steady loud music"}[name],
            median_shot_s=ACT_MEDIAN_S[name], dialogue=DIALOGUE[name])
    add("title", title, purpose="title on the last hit; hold while the tail decays (~2.3 s), no resolution", sound="braam or the final hit; let it ring")
    add("button", button, purpose="dialogue-led tease after the title, then credits", dialogue=DIALOGUE["button"])
    notes, music = [], None
    if music_path:
        from . import music as mu
        st = mu.structure(music_path, 0.0, None, bpm_range)
        music = {k: st[k] for k in ("bpm", "pulse", "recommended_snap", "periodicity")}
        music["sections"] = [{k: s[k] for k in ("label", "start", "end", "loudness_db")} for s in st["sections"]]
        anchors = sorted({*(s["start"] for s in st["sections"][1:]), *(h["time"] for h in st["hits"])})
        by = {s["section"]: s for s in seg}
        for name in ("act1", "act2", "act3"):
            s = by[name]
            near = min(anchors, key=lambda a: abs(a - s["start"])) if anchors else None
            if near is not None and abs(near - s["start"]) <= max(2.0, .15 * (s["end"] - s["start"])):
                s["music_anchor"] = round(near, 3)
        peaks = [s for s in st["sections"] if s["label"] == "peak"]
        loud = max(peaks, key=lambda s: (s["end"] - s["start"], s["loudness_db"])) if peaks else None
        if loud:
            hits_after = [h for h in st["hits"] if h["time"] >= loud["end"] - 2.0]
            last = max(hits_after, key=lambda h: h["rise_db"]) if hits_after else None
            by["title"]["music_anchor"] = round(last["time"] if last else loud["end"], 3)
            by["act3"]["climax_music"] = {"start": loud["start"], "end": loud["end"], "seconds": round(loud["end"] - loud["start"], 2)}
            if loud["end"] - loud["start"] < 6:
                notes.append("The loudest stretch is shorter than 6 s; the climax will feel clipped. Use music_fit to repeat a peak phrase.")
        dips = [q for q in st["quiet"] if not q["edge"] and .3 <= q["end"] - q["start"] <= 1.5]
        for name in ("act2", "act3", "title"):
            a = by[name].get("music_anchor")
            if a is not None:
                d = next((q for q in dips if abs(q["end"] - a) <= .15), None)
                by[name]["dip_before"] = {"start": d["start"], "end": d["end"]} if d else None
                if not d:
                    notes.append(f"No quiet dip before {name} at {a:.2f}s: end a suck_out exactly on it or duck the bed 0.3-0.9 s before.")
        if st["pulse"] == "weak":
            notes.append("Weak musical pulse: snap cuts with use=hits (impacts, section entries), not to beats.")
        # Re-flow: move boundaries onto the anchors when every section keeps ≥ 3 s (the button ≥ 4 s).
        order = [s["section"] for s in seg]
        for name in ("act1", "act2", "act3", "title"):
            a = by[name].get("music_anchor")
            if a is None:
                continue
            i = order.index(name)
            prev, cur = seg[i - 1], seg[i]
            new_end = a + (title if name == "title" else 0)
            ok = a - prev["start"] >= 3 and (cur["end"] - a >= 3 if name != "title" else D - new_end >= 4)
            if ok:
                prev["end"], cur["start"] = round(a, 2), round(a, 2)
                if name == "title":
                    cur["end"] = round(new_end, 2)
                    seg[i + 1]["start"] = round(new_end, 2)
            else:
                notes.append(f"{name} anchor {a:.2f}s would squeeze a neighbouring section under 3 s; kept the proportional boundary.")
    for s in seg:
        s["start_frame"], s["end_frame"] = round(s["start"] * FPS), round(s["end"] * FPS)
    return {"sections": seg, "music": music, "notes": notes,
            "rules": ["Show only a few pieces of the puzzle: questions, not answers.",
                      "Rug pull = a hard switch from light to dark on a level step (≥10 dB).",
                      "A signature sound repeats through the trailer; one silence before the climax.",
                      "Act changes and the title land on a hit (±2 frames); cut dialogue scenes to the words, not the music."]}


def _median_s(shots, a, b):
    lens = [(min(s["end_frame"], b) - max(s["start_frame"], a)) / FPS for s in shots if s["end_frame"] > a and s["start_frame"] < b]
    full = [(s["end_frame"] - s["start_frame"]) / FPS for s in shots if s["start_frame"] >= a and s["end_frame"] <= b]
    return statistics.median(full or lens) if (full or lens) else None


def audit(pid, sections, music_path=None, title_layer=None, bpm_range=None, music_start=0.0, timeline_offset_frames=0):
    """Check a trailer cut against measured practice. sections: [{section, start_frame, end_frame}] (from plan or
    your own), names cold_open/act1/act2/act3/title/button. Findings carry evidence and a suggestion; nothing is changed."""
    from . import agent
    p = agent.read(pid)
    t = p["timeline"]
    shots = t["shots"]
    total = shots[-1]["end_frame"] if shots else 0
    by = {s["section"]: s for s in sections}
    findings, table = [], []
    F = lambda level, code, where, evidence, suggestion: findings.append({"level": level, "code": code, "where": where, "evidence": evidence, "suggestion": suggestion})
    for name, target in ACT_MEDIAN_S.items():
        s = by.get(name)
        if not s:
            continue
        m = _median_s(shots, s["start_frame"], s["end_frame"])
        n = sum(1 for sh in shots if sh["start_frame"] < s["end_frame"] and sh["end_frame"] > s["start_frame"])
        table.append({"section": name, "median_shot_s": round(m, 2) if m else None, "target_s": target, "shots": n})
        if m and not .5 * target <= m <= 1.8 * target:
            F("warning", "act_pacing", name, f"median shot {m:.2f}s vs ~{target}s measured", "Trim or extend shots toward the act's pace; act 2 is the tightest.")
    meds = {r["section"]: r["median_shot_s"] for r in table}
    if meds.get("act1") and meds.get("act2") and meds["act2"] > meds["act1"] * 1.1:
        F("warning", "no_acceleration", "act2", f"act 2 median {meds['act2']}s is slower than act 1 {meds['act1']}s", "Cut act 2 tighter than act 1.")
    if "act3" in by:
        a, b = by["act3"]["start_frame"], by["act3"]["end_frame"]
        lens = [(s["end_frame"] - s["start_frame"]) / FPS for s in shots if s["start_frame"] >= a and s["end_frame"] <= b]
        run = best = 0
        for L in lens:
            run = run + 1 if L < .9 else 0
            best = max(best, run)
        if best < 3:
            F("info", "no_climax_burst", "act3", f"longest run of sub-0.9 s shots is {best}", "Mix the held lines with one burst of 3+ shots of 0.4-0.8 s before the title.")
    # Title and button.
    tl = None
    if title_layer:
        tl = next((l for l in t.get("layers") or [] if l["id"] == title_layer), None)
        if not tl:
            F("warning", "title_missing", title_layer, "layer not found", "Pass the title layer id (title_card recipe).")
    elif "title" in by:
        tl = {"start_frame": by["title"]["start_frame"], "end_frame": by["title"]["end_frame"], "id": "title(section)"}
    if tl:
        hold = tl["end_frame"] - tl["start_frame"]
        if hold < 60:
            F("warning", "short_title_hold", tl["id"], f"title holds {hold / FPS:.2f}s", "Hold the title ~2.3 s while the hit decays.")
        after = total - tl["end_frame"]
        if after < 4 * FPS:
            F("info", "no_button", tl["id"], f"{after / FPS:.1f}s after the title", "End on a 5-10 s dialogue-led button (joke or tease).")
        elif after > 12 * FPS:
            F("info", "long_button", tl["id"], f"{after / FPS:.1f}s after the title", "Buttons run ~6-8 s.")
    # Dialogue spine.
    dia = [c for c in t.get("audio_clips") or [] if c.get("role") == "dialogue"]
    narr = (t.get("narration") or {}).get("words") or []
    for name in ("act1", "act2", "act3"):
        s = by.get(name)
        if not s:
            continue
        has = any(c["start_frame"] < s["end_frame"] and c["end_frame"] > s["start_frame"] for c in dia) or \
            any(s["start_frame"] <= round(w.get("start", 0) * FPS) < s["end_frame"] for w in narr if isinstance(w, dict))
        if not has:
            F("info", "act_without_dialogue", name, "no dialogue clip or narration word in the act", "Dialogue is the spine of most trailers; music-only acts need very strong picture.")
    # Music alignment.
    music = None
    if music_path:
        from . import music as mu
        st = mu.structure(music_path, music_start, None, bpm_range)
        to_f = lambda x: round((x - music_start) * FPS) + timeline_offset_frames
        hits = [to_f(h["time"]) for h in st["hits"]] + [to_f(s["start"]) for s in st["sections"][1:]]
        cuts = [s["end_frame"] for s in shots[:-1]]
        music = {"bpm": st["bpm"], "pulse": st["pulse"], "hits": len(st["hits"])}
        for name in ("act2", "act3", "title"):
            s = by.get(name)
            if not s:
                continue
            f0 = tl["start_frame"] if name == "title" and tl else s["start_frame"]
            near = min(hits, key=lambda h: abs(h - f0)) if hits else None
            if near is None or abs(near - f0) > 2:
                F("warning", "change_off_hit", name, f"starts at frame {f0}; nearest hit/section entry {near}", "Move the change onto the hit (snap_cuts use=hits) or place a hit (design_sound impact/braam).")
            if not any(abs(c - f0) <= 1 for c in cuts) and name != "title":
                F("info", "change_without_cut", name, f"no cut at frame {f0}", "Act changes land on a cut with a level step.")
            q = [x for x in st["quiet"] if not x["edge"] and abs(to_f(x["end"]) - f0) <= 4]
            if name in ("act3", "title") and not q:
                F("info", "no_dip_before_hit", name, "no quiet gap (< -35 dBFS) ends at the change", "A 0.3-0.9 s dip (or a suck_out) before the hit makes it land.")
        peaks = [s for s in st["sections"] if s["label"] == "peak"]
        if "act3" in by and not any(to_f(s["end"]) > by["act3"]["start_frame"] and to_f(s["start"]) < by["act3"]["end_frame"] and s["end"] - s["start"] >= 6 for s in peaks):
            F("warning", "short_climax", "act3", "no loud section of ≥ 6 s under act 3", "Use music_fit to extend the peak phrase or move act 3 onto the loudest stretch.")
        music["dead_air_exempt"] = [{"start": x["start"], "end": x["end"]} for x in st["quiet"] if not x["edge"] and .3 <= x["end"] - x["start"] <= .9]
    return {"findings": findings, "pacing": table, "music": music,
            "note": "Measured trailer practice, not a quality score: deliberate departures (a long oner, a music-only teaser) are valid; say why."}
