"""Distillation worklist: which studied windows are worth looking at before writing a lesson.

Built from what a study already holds, with no decoding and no model: technique words said in their craft sense,
weighted by how rare they are across the library, then corroborated by what the study measured in the same seconds
(gradual transitions, edit events, dense cutting). A window is a place to look, not a claim that the technique is shown
there; the caller inspects it (inspect_window) and writes the lesson in its own words.
"""
import math
import re
from pathlib import Path
from . import store
from .study import GLOSSARY, craft_sense

LEAD, TAIL = 4.0, 18.0  # a demonstration usually follows the sentence that names it
MAX_WINDOW = 30.0  # inspect_window reads at most 30 s
MIN_WINDOW = 6.0
INSPECT = "editvideo_inspect_window(path=source, start, end, frames=8): look at the result on screen, not the UI clicks"


def _pattern(term):
    return " " + " ".join(re.findall(r"[a-z0-9]+", term)) + " "


TERMS, CATEGORY = {}, {}
for _cat, _terms in GLOSSARY.items():
    for _t in _terms:
        TERMS.setdefault(_pattern(_t), _t)  # "j cut" and "j-cut" are one term
        CATEGORY.setdefault(_t, _cat)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _clock(text):
    m = re.fullmatch(r"(\d+):(\d\d)", str(text))
    return int(m[1]) * 60 + int(m[2]) if m else None


def term_hits(record):
    """[(cue index, {terms})] said in their craft sense; cached on the (file-signature cached) record."""
    if "gloss" not in record:
        cues = record["cues"]
        hits = []
        for i, (_, line, words, _) in enumerate(cues):
            around = " ".join(c[1] for c in cues[max(0, i - 1):i + 2])
            found = {term for pat, term in TERMS.items() if pat in words and craft_sense(term, line, around)}
            if found:
                hits.append((i, found))
        record["gloss"] = hits
    return record["gloss"]


def techniques(record, per_category=8):
    """Technique mentions recounted from the transcript with today's craft-sense rules (stored counts may be older)."""
    counts = {}
    for _, found in term_hits(record):
        for t in found:
            counts[t] = counts.get(t, 0) + 1
    out = {}
    for t, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        out.setdefault(CATEGORY[t], [])
        if len(out[CATEGORY[t]]) < per_category:
            out[CATEGORY[t]].append(t)
    return out


def _weights(records):
    """Rarer terms say more about what a tutorial teaches: idf over the studies that say each term."""
    df = {}
    for r in records:
        for term in {t for _, found in term_hits(r) for t in found}:
            df[term] = df.get(term, 0) + 1
    n = max(1, len(records))
    return {t: math.log(1 + n / d) for t, d in df.items()}


def _events(record):
    """Edit events (punch-ins, overlay pops, cuts) a newer study keeps beside its report."""
    path = Path(record["path"]).parent / "events.json"
    try:
        data = store.read_json(path) if path.is_file() else {}
    except (OSError, ValueError):
        data = {}
    rows = data.get("events") if isinstance(data, dict) else None
    return [e for e in rows if isinstance(e, dict) and _num(e.get("t")) and isinstance(e.get("kind"), str)] if isinstance(rows, list) else []


def _subtract(pieces, holes):
    for x, y in holes:
        pieces = [p for a, b in pieces for p in ((a, min(b, x)), (max(a, y), b)) if p[1] - p[0] > 0]
    return pieces


def candidate_windows(record, weights, concepts=(), exclude=()):
    """All windows worth inspecting in one study, best first. Nearby mentions are grouped and split into windows of at
    most 30 s, so every scored mention lies in exactly one window. With query concepts only cues matching one count;
    `exclude` holds (start, end) windows a lesson already uses."""
    from .learning import _matches
    doc = record["doc"]
    duration = doc.get("duration_s")
    if not _num(duration) or duration < 2:
        return []
    gloss = dict(term_hits(record))
    cues = []
    for i, (sec, _, words, vwords) in enumerate(record["cues"]):
        if not (_num(sec) and 0 <= sec < duration):
            continue
        q = sum(any(_matches(words, vwords, t) for t in c) for c in concepts)
        if concepts and not q:
            continue
        terms = gloss.get(i, set())
        score = sum(weights.get(t, 0) for t in terms) + 2.0 * q
        if score > 0:
            cues.append((sec, score, terms, q))
    if not cues:
        return []
    cues.sort(key=lambda c: c[0])
    # Spans around mentions, merged where they touch, minus what a lesson already covers.
    spans = []
    for sec, *_ in cues:
        a, b = max(0.0, sec - LEAD), min(float(duration), sec + TAIL)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    pieces = _subtract([tuple(s) for s in spans], [(float(x), float(y)) for x, y in exclude])
    segs = [g for g in doc.get("segments") or [] if isinstance(g, dict) and _num(g.get("start"))]
    cut_rate = max(0, len(segs) - 1) / duration
    transitions = [e for e in (doc.get("transitions") or {}).get("events") or []
                   if isinstance(e, dict) and _num(e.get("start")) and _num(e.get("end")) and isinstance(e.get("type"), str)]
    events = _events(record)
    ui, sheet = _sheet_flags(doc)
    windows = []
    for pa, pb in pieces:
        inside = [c for c in cues if pa <= c[0] < pb]
        i, prev = 0, pa
        while i < len(inside):
            ws = max(pa, prev, inside[i][0] - LEAD)
            we = min(pb, ws + MAX_WINDOW)
            j = i
            while j < len(inside) and inside[j][0] < we:
                j += 1
            we = min(we, inside[j - 1][0] + TAIL)
            if we - ws < MIN_WINDOW:  # a mention near a boundary: widen backwards rather than show a sliver
                ws = max(pa, prev, we - MIN_WINDOW)
            windows.append(_window(ws, we, inside[i:j], duration, weights, concepts, segs, cut_rate, transitions, events, ui, sheet))
            prev, i = we, j
    return sorted((w for w in windows if w), key=lambda w: (-w["score"], w["start"]))


def _sheet_flags(doc):
    """(UI-flagged times, sampled times) of the overview sheet, the only frames the text/UI flag was measured on.
    Newer reports store every sample; older ones only the flagged clocks, which are trusted only when they all fall on
    the default 30-frame grid (else nothing is claimed)."""
    rows = doc.get("sheet_samples")
    if isinstance(rows, list) and rows:
        pairs = [(r[0], bool(r[1])) for r in rows if isinstance(r, list) and len(r) == 2 and _num(r[0])]
        return [t for t, f in pairs if f], [t for t, _ in pairs]
    d = doc.get("duration_s")
    if not _num(d) or d <= 0:
        return [], []
    first = min(1.0, d * .01)
    grid = [first + k * (d - .5 - first) / 29 for k in range(30)]
    clocks = {f"{int(t // 60):02d}:{int(t % 60):02d}": t for t in grid}
    flagged = [str(x) for x in doc.get("on_screen_text_or_ui") or []]
    if any(c not in clocks for c in flagged):
        return [], []
    return [clocks[c] for c in flagged], grid


def _window(a, b, cues, duration, weights, concepts, segs, cut_rate, transitions, events, ui, sheet):
    # Work in whole tenths and round inwards, so the window fits the video and never exceeds 30 s
    # (inspect_window refuses either). At the very end of the video keep its last fraction of a second.
    ta, tb = math.ceil(a * 10 - 1e-6), math.floor(min(b, duration) * 10 + 1e-6)
    tb = min(tb, ta + int(MAX_WINDOW * 10))
    a = ta / 10
    b = tb / 10 if not (b >= duration - 1e-6 and tb - ta < int(MAX_WINDOW * 10)) else math.floor(duration * 1000) / 1000
    if b - a < 1:
        return None
    counts = {}
    for c in cues:
        for t in c[2]:
            counts[t] = counts.get(t, 0) + 1
    tr = [e for e in transitions if e["start"] < b and e["end"] > a]
    ev = [e["kind"] for e in events if a <= e["t"] < b]
    cuts = sum(1 for g in segs[1:] if a <= g["start"] < b)
    score = sum(c[1] for c in cues) + .75 * min(3, len(tr)) + .25 * min(4, len(ev)) + (.5 if cut_rate and cuts >= 1.5 * cut_rate * (b - a) else 0)
    out = {"start": a, "end": b, "score": round(score, 1), "mentions": len(cues),
           "terms": [t for t, _ in sorted(counts.items(), key=lambda kv: (-kv[1] * weights.get(kv[0], 0), kv[0]))][:4], "cuts": cuts}
    if concepts:
        out["query_hits"] = sum(c[3] for c in cues)
    if tr:
        out["transitions"] = [{"type": e["type"], "at": round(e["start"], 1)} for e in tr[:4]]  # sample ~1 s around each join
    if ev:
        out["events"] = {k: ev.count(k) for k in sorted(set(ev))}
    # Text/UI was measured only on the overview sheet's 30 frames: say so when none fell inside this window.
    out["ui_on_screen"] = any(a <= t < b for t in ui) if any(a <= t < b for t in sheet) else None
    return out


def _unmeasured(record):
    doc = record["doc"]
    tr = doc.get("transitions")
    out = []
    if not isinstance(tr, dict):
        out.append("transitions")
    else:
        events, total = tr.get("events") or [], sum((tr.get("counts") or {}).values())
        if len(events) < total and events and _num(events[-1].get("end") if isinstance(events[-1], dict) else None):
            out.append(f"transitions after {round(events[-1]['end'])} s (older report kept {len(events)} of {total})")
    if not (Path(record["path"]).parent / "events.json").is_file():
        out.append("edit events")
    elif _num((doc.get("events") or {}).get("measured_until_s")) and doc["events"]["measured_until_s"] < (doc.get("duration_s") or 0):
        out.append(f"edit events after {round(doc['events']['measured_until_s'])} s")
    if not doc.get("sheet_samples") and not _sheet_flags(doc)[1]:
        out.append("text/UI on screen")
    return out


def lesson_index(lessons):
    """study id -> ([covered windows], number of lessons citing it)."""
    covered, cited = {}, {}
    for row in lessons:
        for s in row["doc"]["sources"]:
            covered.setdefault(s["study_id"], []).append((float(s["start"]), float(s["end"])))
            cited.setdefault(s["study_id"], set()).add(row["id"])
    return covered, {k: len(v) for k, v in cited.items()}


def study_entry(record, weights, concepts, covered, cited, offset=0, limit=2):
    doc = record["doc"]
    windows = candidate_windows(record, weights, concepts, covered.get(record["id"], []))
    out = {"id": record["id"], **{k: record["meta"][k] for k in ("title", "channel") if record["meta"].get(k)},
           "source": doc["source"], "source_available": Path(doc["source"]).is_file(), "duration_s": doc.get("duration_s"),
           "lessons": cited.get(record["id"], 0), "windows": windows[offset:offset + limit], "windows_total": len(windows),
           "next_offset": offset + limit if offset + limit < len(windows) else None}
    unmeasured = _unmeasured(record)
    if unmeasured:
        out["unmeasured"] = unmeasured  # absent signals here mean "not measured", not "none"
    if not record["cues"]:
        out["no_transcript"] = "No narration to locate techniques; use the overview sheet or index_video, or transcribe first."
    return out


def worklist(studies, lessons, concepts, ranked_ids=None, offset=0, limit=5, per_study=2):
    """Studies not yet distilled into an active lesson that have windows to inspect, best first (by query relevance
    when given). A study whose only match is its title or tags, with no matching narration, is counted, not listed."""
    weights = _weights(studies)
    covered, cited = lesson_index(lessons)
    todo = [r for r in studies if r["id"] not in covered]
    if ranked_ids is not None:
        order = {sid: i for i, sid in enumerate(ranked_ids)}
        todo = sorted((r for r in todo if r["id"] in order), key=lambda r: order[r["id"]])
    rows, skipped = [], []
    for r in todo:
        try:
            windows = candidate_windows(r, weights, concepts, ())
        except (TypeError, ValueError, KeyError, AttributeError) as e:  # one damaged report must not hide the others
            skipped.append({"path": r["path"], "error": str(e)[:160]})
            continue
        if windows:
            rows.append((sum(w["score"] for w in windows[:3]), r))
    if ranked_ids is None:
        rows.sort(key=lambda x: (-x[0], x[1]["id"]))  # without a query: how much each study offers to look at
    no_window = len(todo) - len(rows) - len(skipped)
    entries = [study_entry(r, weights, concepts, covered, cited, 0, per_study) for _, r in rows[offset:offset + limit]]
    out = {"total": len(rows), "offset": offset, "items": entries, "next_offset": offset + limit if offset + limit < len(rows) else None,
           "already_distilled": sum(1 for r in studies if r["id"] in covered), "inspect": INSPECT,
           "next": "Inspect a window, then remember_lesson with what you observed there (sources[].observed); "
                   "learning_library(item_id=study, view='candidates', offset=...) pages one study's windows."}
    if no_window:
        out["without_windows"] = no_window  # title/tag matches or no narration: nothing located to look at
    if skipped:
        out["skipped"] = skipped[:5]
    return out
