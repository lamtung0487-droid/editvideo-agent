"""Subtitles in another language for a narrated film (round 13: the owner chose English subtitles for the Vietnamese
documentary rather than a dub). A translation written sentence for sentence is timed on the narration it translates:
each translated sentence is shown while its source sentence is spoken (time shared by the source's syllables, which a
steady narrator speaks at a near-constant rate), long sentences split at a clause into cues of two lines at most.

Delivered as a sidecar (SRT for platforms, ASS with the film's type) and, when asked, burned into a finished render with
FFmpeg, so a subtitled version costs one encode instead of a second edit. Reading speed is reported per cue against
Netflix's 17 characters a second; the timing never moves a cue off its sentence to make it readable, it says so instead.
"""
import re
import subprocess
from pathlib import Path
from .media import FFMPEG

ABBREVIATIONS = ("Dr", "Mr", "Mrs", "Ms", "St", "Gen", "Lt", "Col", "Sgt", "Capt", "No", "U.S", "U.N")
CPS = 17.0          # characters a second a viewer reads (Netflix)
LINE_CHARS = 42     # characters a line
MIN_CUE = 1.0       # seconds


def sentences(text):
    """Sentences of `text`: split after . ! ? … followed by a space, not after an abbreviation ("Dr.") and not at a colon."""
    parts, cur = [], ""
    for tok in re.split(r"(?<=[.!?…])\s+", (text or "").strip()):
        cur = f"{cur} {tok}".strip() if cur else tok
        if re.search(r"(?:^|\s)(?:%s)\.$" % "|".join(re.escape(a) for a in ABBREVIATIONS), cur):
            continue
        parts.append(cur)
        cur = ""
    if cur:
        parts.append(cur)
    return [p for p in parts if p]


def chunks(sentence, max_chars=2 * LINE_CHARS):
    """A sentence as cues of at most max_chars, split at the clause mark (, ; : —) nearest the middle, else at a space."""
    s = sentence.strip()
    if len(s) <= max_chars:
        return [s]
    mid = len(s) / 2
    marks = [m.end() for m in re.finditer(r"[,;:—]\s", s)]
    cut = min(marks, key=lambda i: abs(i - mid)) if marks and min(abs(i - mid) for i in marks) < len(s) * .3 else None
    if cut is None:
        spaces = [m.start() for m in re.finditer(r"\s", s)]
        cut = min(spaces, key=lambda i: abs(i - mid)) if spaces else int(mid)
    return chunks(s[:cut], max_chars) + chunks(s[cut:], max_chars)


def timed(source, translation, start, end, max_chars=2 * LINE_CHARS, min_cue=MIN_CUE):
    """Cues [{"start", "end", "text", "cps"}] (seconds, the narration's own clock) for `translation` over the span the
    source line is spoken, [start, end). Sentences pair up in order; when the counts differ the whole line is one unit."""
    vs, es = sentences(source), sentences(translation)
    if len(vs) != len(es):
        vs, es = [source], [translation]
    w = [max(1, len(v.split())) for v in vs]
    total = sum(w)
    cues, t = [], float(start)
    for v, e, wi in zip(vs, es, w):
        span = (end - start) * wi / total
        parts = chunks(e, max_chars)
        n = sum(len(p) for p in parts)
        tt = t
        for p in parts:
            d = span * len(p) / n
            cues.append({"start": tt, "end": tt + d, "text": p})
            tt += d
        t += span
    k = 0
    while k < len(cues) - 1:  # a cue too short to read joins its neighbour when the pair still fits in two lines
        a, b = cues[k], cues[k + 1]
        if (a["end"] - a["start"] < min_cue or b["end"] - b["start"] < min_cue) and len(a["text"]) + len(b["text"]) + 1 <= max_chars:
            cues[k] = {"start": a["start"], "end": b["end"], "text": f"{a['text']} {b['text']}"}
            cues.pop(k + 1)
        else:
            k += 1
    for c in cues:
        c["start"], c["end"] = round(c["start"], 3), round(c["end"], 3)
        c["cps"] = round(len(c["text"]) / max(.3, c["end"] - c["start"]), 1)
    return cues


def _ts(s, sep=","):
    s = max(0.0, s)
    h, m = int(s // 3600), int(s % 3600 // 60)
    return f"{h:02d}:{m:02d}:{s % 60:06.3f}".replace(".", sep)


def to_srt(cues):
    return "\n".join(f"{k}\n{_ts(c['start'])} --> {_ts(c['end'])}\n{c['text']}\n" for k, c in enumerate(sorted(cues, key=lambda c: c["start"]), 1))


def to_ass(cues, width=1920, height=1080, font="Be Vietnam Pro", size=46, margin=56, raised=220):
    """ASS with the film's look: white text, a dark outline and soft shadow, two lines at most. A cue with "raise": True sits
    higher (over a burned-in subtitle in the source language, e.g. under an archival voice)."""
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Sub,{font},{size},&H00F4F4F4,&H000000FF,&H00101010,&H64000000,0,0,0,0,100,100,0,0,1,2.6,1.2,2,{int(width * .1)},{int(width * .1)},{margin},1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    rows = []
    for c in sorted(cues, key=lambda c: c["start"]):
        mv = raised if c.get("raise") else 0
        text = c["text"].replace("\n", "\\N")
        rows.append(f"Dialogue: 0,{_ts(c['start'], '.')[1:-1]},{_ts(c['end'], '.')[1:-1]},Sub,,0,0,{mv},,{text}")
    return head + "\n".join(rows) + "\n"


def burn(video, ass_path, out, fonts_dir=None, crf=18):
    """The subtitles burned into a finished render (video re-encoded, audio copied)."""
    vf = "ass=" + str(Path(ass_path)).replace("\\", "/").replace(":", r"\:")
    if fonts_dir:
        vf += ":fontsdir=" + str(Path(fonts_dir)).replace("\\", "/").replace(":", r"\:")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(video), "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                    "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(out)], check=True)
    return str(out)


def relax(cues, cps=CPS, hold=1.5, lead=.3, gap=.08):
    """Give a cue too fast to read the quiet around it (round 13: English runs longer than the Vietnamese it translates;
    26 of 156 cues were over 17 characters a second): its end stays up to `hold` seconds into the pause after its
    sentence, its start comes up to `lead` seconds early, never into a neighbouring cue. Cues sorted by start; in place."""
    cues.sort(key=lambda c: c["start"])
    for k, c in enumerate(cues):
        need = len(c["text"]) / cps
        if c["end"] - c["start"] >= need:
            c["cps"] = round(len(c["text"]) / max(.001, c["end"] - c["start"]), 1)
            continue
        nxt = cues[k + 1]["start"] - gap if k + 1 < len(cues) else c["end"] + hold
        c["end"] = round(max(c["end"], min(c["end"] + hold, nxt, c["start"] + need)), 3)
        if c["end"] - c["start"] < need:
            prv = cues[k - 1]["end"] + gap if k else c["start"] - lead
            c["start"] = round(max(0.0, min(c["start"], max(c["start"] - lead, prv, c["end"] - need))), 3)
        c["cps"] = round(len(c["text"]) / max(.3, c["end"] - c["start"]), 1)
    return cues


def report(cues, cps=CPS):
    """Cues a viewer cannot read in their time (characters a second over `cps`) and the overall rate."""
    measured = [{**c, "cps": len(c["text"]) / max(.001, c["end"] - c["start"])} for c in cues]
    fast = [c for c in measured if c["cps"] > cps + .05]
    return {"cues": len(cues), "too_fast": len(fast), "worst": sorted(fast, key=lambda c: -c["cps"])[:5],
            "median_cps": sorted(c["cps"] for c in measured)[len(cues) // 2] if cues else 0}


def readable(cues, duration, cps=CPS, lead=.5, hold=2.0):
    """Reflow words over adjacent translation cues, retaining every word and authored raise/position groups.

    Only contiguous cues (<=.35 s gaps, same raise flag) share their time. Real pauses are borrowed at most lead/hold;
    groups never overlap. This is a reading-time allocation, not English forced alignment to Vietnamese audio.
    """
    import copy, math
    source = sorted(copy.deepcopy(cues), key=lambda c: c["start"])
    if not math.isfinite(duration) or duration <= 0 or not 5 <= cps <= 30:
        raise ValueError("Finite positive duration and cps=5..30 required")
    for c in source:
        if not isinstance(c.get("text"), str) or not c["text"].strip() or not all(math.isfinite(c[k]) for k in ("start", "end")) or not 0 <= c["start"] < c["end"] <= duration + .01:
            raise ValueError("Nonempty captions with finite in-range start/end required")
    groups = []
    for c in source:
        if groups and c["start"] < groups[-1][-1]["end"] - .001:
            raise ValueError("Overlapping input captions must be resolved before reflow")
        if groups and c["start"] - groups[-1][-1]["end"] <= .35 and bool(c.get("raise")) == bool(groups[-1][-1].get("raise")):
            groups[-1].append(c)
        else:
            groups.append([c])
    out = []
    for i, group in enumerate(groups):
        text = " ".join(c["text"] for c in group)
        words = text.split()
        # Keep original sentences/clauses when short; otherwise wrap into readable <=76-char pages.
        pages, cur = [], []
        for w in words:
            if cur and len(" ".join(cur + [w])) > 76:
                pages.append(" ".join(cur)); cur = []
            cur.append(w)
            if w.endswith((".", "!", "?", ";", ":")) and len(" ".join(cur)) >= 32:
                pages.append(" ".join(cur)); cur = []
        if cur: pages.append(" ".join(cur))
        a, b = group[0]["start"], group[-1]["end"]
        need = sum(len(p) / cps for p in pages) + .04 * max(0, len(pages) - 1)
        next_start = groups[i + 1][0]["start"] if i + 1 < len(groups) else duration + .08
        b = min(duration, next_start - .08, b + min(hold, max(0, need - (b - a))))
        a = max(out[-1]["end"] + .08 if out else 0, a - min(lead, max(0, need - (b - a))))
        available = b - a - .04 * max(0, len(pages) - 1)
        total = sum(len(p) for p in pages)
        cursor = a
        for text in pages:
            length = available * len(text) / max(1, total)
            row = {"start": round(cursor, 3), "end": round(cursor + length, 3), "text": text}
            if group[0].get("raise"): row["raise"] = True
            row["cps"] = len(text) / max(.001, length)
            out.append(row)
            cursor += length + .04
    return out
