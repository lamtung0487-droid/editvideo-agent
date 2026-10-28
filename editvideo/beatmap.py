"""Narration → picture → rhythm, sentence by sentence (a sense for direction, not a judge).

For every spoken sentence: which shots carry it (and whether they are evidence or illustration), how many visual events
happen while it is said (cuts, entrances, punches), which on-screen text repeats what is being said and how late or
early it appears, plus film-wide rhythm (shot-length variety) and motifs (styled elements that recur). The calling
model decides what to change; the numbers say where to look.
"""
import re
import statistics
import uuid
from . import agent, store

FPS = 30
END = re.compile(r"[.!?…]+[\"”')\]]*$")
STOP = {"và", "là", "của", "có", "một", "những", "các", "cho", "trong", "với", "được", "này", "đó", "thì", "mà", "để", "khi", "ta", "không",
        "the", "a", "an", "of", "to", "and", "in", "is", "on", "for"}
ENTR = ("fade_in", "rise", "drop", "slide_left", "slide_right", "pop", "spring", "blur_in", "wipe_left", "wipe_right", "wipe_up", "wipe_down", "iris",
        "word_reveal", "line_reveal", "character_reveal", "typewriter", "mask_reveal", "char_spring", "decode", "text_animate", "slide_spring",
        "tracking_in", "soft_edge_reveal", "diagonal_reveal", "diamond_reveal", "clock_wipe", "color_to")


def _tokens(text):
    t = re.sub(r"[*=_\"“”'’().,:;!?…\-–—/]", " ", str(text).lower())
    return [w for w in t.split() if len(w) > 1 and w not in STOP]


def _sentences(words):
    out, cur = [], []
    for w in words:
        cur.append(w)
        if END.search(w["text"]):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [{"start": c[0]["start"], "end": c[-1]["end"], "text": " ".join(w["text"] for w in c), "words": c} for c in out]


def _split(text):
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s.strip()]


def _by_script(words, config):
    """Group timed words into sentences by token counts of the text that was actually spoken (spoken_text when given,
    else the script); the display sentence (script) is attached when both texts have the same number of sentences."""
    spoken = config.get("spoken_text") or config.get("script") or ""
    ss, ds = _split(spoken), _split(config.get("script") or "")
    counts = [len(s.split()) for s in ss]
    if sum(counts) != len(words):
        return None
    out, i = [], 0
    for k, n in enumerate(counts):
        chunk = words[i:i + n]
        i += n
        text = ds[k] if len(ds) == len(ss) else " ".join(w["text"] for w in chunk)
        out.append({"start": chunk[0]["start"], "end": chunk[-1]["end"], "text": text, "words": chunk})
    return out


def _entered(layer):
    first = min((e.get("start_frame", 0) for e in layer.get("effects", []) if e["name"] in ENTR), default=0)
    return layer["start_frame"] + first


def _latest_render(pid, timeline):
    """Reuse only an unchanged timeline, config and authored source at the current revision.

    Source writes need no project revision, so revision alone cannot establish picture identity. Old FFmpeg jobs
    without a source snapshot cannot establish it either: fall back to a fresh snapshot instead of stale evidence.
    """
    from .media import sha256
    project = store.get_project(pid)
    code_hashes = {}
    generated = {"input.json", "input.js", "source-meta.json"}
    def authored(root):
        return {str(p.relative_to(root)): sha256(p) for p in root.rglob("*") if p.is_file()
                and p.suffix in (".tsx", ".ts", ".jsx", ".js", ".mjs", ".cjs", ".html", ".css", ".svg", ".json")
                and p.name not in generated and not any(x in ("public", "node_modules", ".cache") for x in p.relative_to(root).parts)}
    for j in store.jobs(pid):
        if j["state"] != "completed" or j["kind"] not in ("final", "preview") or j["revision"] != project["revision"]:
            continue
        folder = store.folder(pid) / "jobs" / j["id"]
        try:
            if store.read_json(folder / "timeline.json") != timeline:
                continue
            payload = store.read_json(folder / "source" / "input.json")
            if payload["config"] != project["config"]:
                continue
            engine = payload["config"]["renderer"]
            if engine not in code_hashes:
                code_hashes[engine] = authored(store.folder(pid) / "code" / engine)
            if not code_hashes[engine] or code_hashes[engine] != authored(folder / "source"):
                continue
        except (OSError, ValueError, KeyError, TypeError):
            continue
        for name in ("final.mp4", "preview.mp4"):
            if (folder / name).exists():
                return folder / name, j
    return None, None


def sentence_strip(pid, revision, rows, t):
    """One contact sheet: per sentence of this page, what the viewer sees while it is said (start / middle / end from the
    render of this revision; one middle frame per sentence from an engine snapshot when there is no such render), with
    the sentence, its shots and lags written beside it. The caller judges whether the picture explains the words."""
    import subprocess
    from PIL import Image, ImageDraw, ImageFont
    from .media import FFMPEG
    from .design_library import FONT_ROOT, font
    rows = rows[:8]
    if not rows:
        return None, "No mapped narration segments; this does not establish silence. Bind custom dialogue first."
    video, job = _latest_render(pid, t)
    W, H = t["width"], t["height"]
    th = int(min(180 if W >= H else 260, 1492 / len(rows) - 8))  # the sheet stays under ~1500 px tall (clients shrink larger images)
    tw = round(th * W / H)
    frames = {}
    if video:
        source = f"render {job['kind']} of this timeline (job revision {job['revision']})"
        for r in rows:
            a, b = r["t"]
            for k, sec in enumerate((a + .2, (a + b) / 2, max(a + .2, b - .2))):
                raw = subprocess.run([FFMPEG, "-v", "error", "-ss", str(round(sec, 3)), "-i", str(video), "-frames:v", "1", "-vf", f"scale={tw}:{th}",
                                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=60).stdout
                if len(raw) == tw * th * 3:
                    frames[(r["s"], k)] = Image.frombytes("RGB", (tw, th), raw)
    else:
        from .snapshot import snapshot
        source = "remotion snapshot (no render of this revision): middle frame only"
        mids = [min(t["total_frames"] - 1, int((r["t"][0] + r["t"][1]) / 2 * FPS)) for r in rows]
        shot = snapshot(pid, "remotion", sorted(set(mids)))
        by = {f["frame"]: f["path"] for f in shot["frames"]}
        for r, f in zip(rows, mids):
            with Image.open(by[f]) as im:
                frames[(r["s"], 1)] = im.convert("RGB").resize((tw, th))
    face = FONT_ROOT / font("inter")["faces"][0]["file"]
    big, small = ImageFont.truetype(str(face), 17), ImageFont.truetype(str(face), 14)
    text_w = 430
    sheet = Image.new("RGB", (3 * tw + 4 * 8 + text_w, len(rows) * (th + 8) + 8), (18, 20, 22))
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(rows):
        y = 8 + i * (th + 8)
        for k in range(3):
            im = frames.get((r["s"], k))
            if im:
                sheet.paste(im, (8 + k * (tw + 8), y))
        x = 8 + 3 * (tw + 8)
        d.text((x, y), f"#{r['s']}  {r['t'][0]:.1f}-{r['t'][1]:.1f}s  shots {','.join(r['shots'])}  events {r['events']}", font=small, fill=(150, 200, 180))
        words, line, yy = r["text"].split(), "", y + 22
        for w_ in words:  # wrap the sentence to the text column
            if d.textlength((line + " " + w_).strip(), font=big) > text_w - 12 and line:
                d.text((x, yy), line, font=big, fill=(240, 240, 235))
                yy += 22
                line = w_
            else:
                line = (line + " " + w_).strip()
        d.text((x, yy), line, font=big, fill=(240, 240, 235))
        if r.get("lags"):
            d.text((x, yy + 26), "  ".join(f"{q['layer']} {q['lag_s']:+.1f}s" for q in r["lags"][:4]), font=small, fill=(230, 180, 90))
    out = store.DATA / "observations" / f"beatmap-strip-{uuid.uuid4().hex[:10]}.jpg"
    sheet.save(out, quality=86)
    return str(out), source


def beat_map(pid, offset=0, limit=20, strips=False):
    p = agent.read(pid)
    t = p.get("timeline")
    if not t:
        raise ValueError("Project has no locked plan yet")
    words_doc = store.read_json(store.folder(pid) / "plan" / "words.json") if (store.folder(pid) / "plan" / "words.json").exists() else {}
    words = [w for w in words_doc.get("words") or [] if "start" in w and "end" in w]
    if words:
        sents = _sentences(words)
        timing = "timed words"
        if len(sents) == 1 and len(words) > 25:  # TTS boundaries carry no punctuation: segment by the script's sentences
            sents = _by_script(words, p["config"]) or sents
    else:  # silent or estimated plans: fall back to caption cues (estimated timing is flagged)
        sents = [{"start": c["start"], "end": c["end"], "text": c["text"], "words": []} for c in t.get("cues") or []]
        timing = "caption cues (" + str(words_doc.get("method") or t.get("timing_method")) + ")"
        if not sents:
            from . import narrative
            meaning, status = narrative.document(pid,t)
            if status == 'ready':
                sents = [{"start": b['start_frame']/30,"end": b['end_frame']/30,"text": b['text'],"words": []}
                         for b in meaning['beats'] if b['text']]
                timing = "authored narrative segments (clip/window bounds; no word alignment)"
    shots, layers = t["shots"], t.get("layers") or []
    texts = [l for l in layers if l["kind"] in ("text", "caption", "callout", "counter") and l.get("opacity", 1) > .1]
    events = sorted([s["start_frame"] for s in shots[1:]] + [_entered(l) for l in layers if l["kind"] != "caption"] +
                    [s["start_frame"] + e.get("start_frame", 0) for s in shots for e in s.get("effects", []) if e["name"] == "focus_zoom" and (e.get("params") or {}).get("cut")])
    said = []  # (token, second)
    for s in sents:
        for w in s["words"]:
            said += [(tok, w["start"]) for tok in _tokens(w["text"])]
        disp = _tokens(s["text"])  # display tokens (digits like 432.210 the TTS spoke as words): time by position
        spoken = {tok for w in s["words"] for tok in _tokens(w["text"])}
        if s["words"] and disp and set(disp) - spoken:
            span = s["end"] - s["start"]
            said += [(tok, s["start"] + span * k / max(1, len(disp))) for k, tok in enumerate(disp) if tok not in spoken]
    rows, findings = [], []
    for i, s in enumerate(sents):
        a, b = int(s["start"] * FPS), int(s["end"] * FPS) + 1
        on = [sh for sh in shots if sh["start_frame"] < b and sh["end_frame"] > a]
        ev = sum(1 for f in events if a <= f < b)
        vis = [l for l in texts if l["start_frame"] < b and l["end_frame"] > a]
        lags = []
        for l in vis:
            if not a - 30 <= _entered(l) < b:  # judge a layer against the sentence it arrives in (or just before)
                continue
            toks = set(_tokens(l.get("text") or (l.get("data") or {}).get("suffix", "")))
            hit = [sec for tok, sec in said if tok in toks and s["start"] - .5 <= sec <= s["end"] + .5]
            if toks and hit:
                lag = round(_entered(l) / FPS - min(hit), 2)
                lags.append({"layer": l["id"], "lag_s": lag})
                if lag > 1.0:
                    findings.append({"code": "late_visual", "sentence": i, "layer": l["id"], "lag_s": lag,
                                     "note": "Text echoing the narration appears after the words are said; bring it in on (or just before) the word."})
                elif lag < -2.5 and l["start_frame"] >= a:
                    findings.append({"code": "early_visual", "sentence": i, "layer": l["id"], "lag_s": lag,
                                     "note": "Text appears long before it is said; viewers read ahead of the narration."})
        dur = s["end"] - s["start"]
        if dur >= 4 and ev == 0:
            findings.append({"code": "no_visual_change", "sentence": i, "seconds": round(dur, 1),
                             "note": "A long sentence over an unchanging picture; motivate a cut, reveal or move on its key word."})
        claim = bool(re.search(r"\d", s["text"]))
        roles = sorted({sh.get("role", "illustration") for sh in on})
        if claim and roles and "evidence" not in roles and not any(re.search(r"\d", str(l.get("text", ""))) for l in vis):
            findings.append({"code": "claim_without_support", "sentence": i,
                             "note": "A figure or date is spoken over illustration only; show the number, its source or evidence footage."})
        rows.append({"s": i, "t": [round(s["start"], 2), round(s["end"], 2)], "text": s["text"][:70], "shots": [sh["id"] for sh in on], "roles": roles,
                     "events": ev, "on_screen": [l["id"] for l in vis][:6], **({"lags": lags} if lags else {})})
    from .voices import narration_finding
    nf = narration_finding(pid)
    if nf:  # the map assumes the words are understood; say so when they may not be
        findings.append({"code": nf[1], "level": nf[0], **nf[2], "note": nf[3]})
    lengths = [(sh["end_frame"] - sh["start_frame"]) / FPS for sh in shots]
    rhythm = {"shots": len(lengths)}
    if len(lengths) >= 3:
        mean = statistics.mean(lengths)
        cv = statistics.pstdev(lengths) / mean if mean else 0
        rhythm.update(mean_s=round(mean, 2), cv=round(cv, 2), shortest_s=round(min(lengths), 2), longest_s=round(max(lengths), 2))
        if len(lengths) >= 5 and cv < .25:
            findings.append({"code": "uniform_rhythm", "cv": round(cv, 2),
                             "note": "Shot lengths are nearly equal; vary them with the content (short beats around a long held one)."})
    # Motifs: styled elements that come back (same kind, font, size, colour) — the callbacks a film can build on.
    groups = {}
    for l in texts + [l for l in layers if l["kind"] in ("shape", "svg", "icon")]:
        sig = (l["kind"], l.get("font_id"), l.get("font_size"), l.get("color"))
        groups.setdefault(sig, []).append(l)
    motifs = []
    for sig, ls in groups.items():
        spans = sorted({(l["start_frame"], l["end_frame"]) for l in ls})
        if len(spans) >= 2 and spans[-1][0] - spans[0][1] > 60:
            corners = {("L" if l["x"] + l["width"] / 2 < .5 else "R") + ("T" if l["y"] + l["height"] / 2 < .5 else "B") for l in ls}
            motifs.append({"kind": sig[0], "font": sig[1], "size": sig[2], "color": sig[3], "times_s": [round(a / FPS, 1) for a, _ in spans][:8],
                           "layers": [l["id"] for l in ls][:6], "regions": sorted(corners)})
    out_path = store.DATA / "observations" / f"beatmap-{uuid.uuid4().hex[:10]}.json"
    store.write_json(out_path, {"project_id": pid, "timing": timing, "beats": rows, "findings": findings, "rhythm": rhythm, "motifs": motifs})
    note_strip = None
    if strips:  # one sheet per page, at most 8 sentences (an image block costs tokens; page through for more)
        limit = min(limit, 8)
        page = [{**r, "text": sents[r["s"]]["text"]} for r in rows[offset:offset + limit]]  # full sentences on the sheet
        strip, strip_source = sentence_strip(pid, p["revision"], page, t)
        if strip is None:
            strips = False
            note_strip = strip_source
    return {"timing": timing, "sentences": len(rows), "beats": rows[offset:offset + limit], "next_offset": offset + limit if offset + limit < len(rows) else None,
            **({"strip": strip, "strip_source": strip_source} if strips else {}), **({"strip_note": note_strip} if note_strip else {}),
            "findings": findings[:30], "rhythm": rhythm, "motifs": motifs[:8], "manifest": str(out_path),
            "note": "Measurements of narration-picture alignment; whether a picture explains the sentence is your call (inspect the frames)."}
