"""Sound design placement and audio audits learned from professional sound-design workflows.

sfx_sync places procedural accents on picture events with the right anchor: a whoosh peaks at the middle of a moving
transition, a pop starts with a graphic entrance, an impact or sub drop starts on a reveal, a reverse cymbal ends on its
cut. Density is limited (minimum gap, maximum per minute), variants rotate so no sample repeats back to back, and every
accent is an ordinary editable audio clip. audit_audio measures the mix and the accent plan against working targets.
"""
import math
import re
import numpy as np
import subprocess
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from . import agent, store, sound
from .cinematic import FPS, _timeline

MOVING = {"whip_left", "whip_right", "whip_up", "whip_down", "push_left", "push_right", "push_up", "push_down", "zoom_through", "spin",
          "pass_left", "pass_right"}
ENTRANCE_FX = {"fade_in", "pop", "rise", "drop", "slide_left", "slide_right", "spring", "mask_reveal", "word_reveal", "line_reveal",
               "character_reveal", "char_spring", "decode", "typewriter", "tracking_in", "wipe_left", "wipe_right", "wipe_up", "wipe_down", "iris",
               "progress", "slide_spring", "blur_in", "zoom_in"}
# kind: (duration s, peak dBFS of the generated file, anchor) — anchor says which moment of the sound lands on the event.
ACCENTS = {"whoosh": (.55, -20, "peak"), "pop": (.12, -24, "onset"), "tick": (.12, -26, "onset"), "shutter": (.2, -22, "onset"),
           "impact": (.8, -16, "onset"), "sub_drop": (1.4, -14, "onset"), "chime": (2.0, -24, "onset"), "crunch": (.5, -20, "onset"),
           "reverse_cymbal": (1.5, -20, "end"), "riser": (2.0, -22, "end"),
           "braam": (3.0, -12, "onset"), "suck_out": (.9, -18, "end"), "tinnitus": (4.0, -26, "onset")}
# Startle window (prepulse inhibition): a weak onset, or a short gap in the sound, 30-500 ms before a loud hit dampens the
# startle it is meant to cause. Hits and the sounds that lead into them are recognised by clip id.
_tok = lambda words: re.compile(r"(?:^|[-_])(?:" + words + r")(?=$|[-_\d])", re.I)
HIT_ID = _tok(r"impact|braam|sub[-_]?drop|blast|bombs?|explosions?|hit")
PULL_IN_ID = _tok(r"suck[-_]?out|risers?|reverse[-_]?cymbal|shepard")
LEAD_IN_ID = _tok(r"whoosh(?:es)?|suck[-_]?out|risers?|reverse[-_]?cymbal|shepard")
is_pull_in = lambda c: bool(PULL_IN_ID.search(c["id"])) or bool(c.get("reverse"))  # a reversed sound swells into its end
is_hit = lambda c: (bool(HIT_ID.search(c["id"])) and not is_pull_in(c) and c.get("role") in (None, "sfx", "foley"))
# Builds hold the listener waiting for a release (sirens, accelerating heartbeats and clocks, risers, Shepard rises). American
# war-film and documentary practice (docs/PRO_WORKFLOWS.md §31): a build lasts at most ~12 s (pulse beds ~30 s), resolves on a
# hit within a few frames of its end and never fades away unresolved, and major builds are spaced a minute or more apart.
BUILD_ID = _tok(r"risers?|reverse[-_]?cymbal|shepard|sirens?|heart(?:beat)?s?|clocks?|build")
PULSE_ID = _tok(r"heart(?:beat)?s?|clocks?")
BUILD_MAX_S, PULSE_MAX_S, BUILD_SPACING_S = 12.0, 30.0, 60.0
is_build = lambda c: (bool(BUILD_ID.search(c["id"])) or bool(c.get("reverse"))) and c.get("role") not in ("music", "dialogue", "ambience")
_ENVELOPES = {}


def _envelope(path, rate=8000, hop=.05):
    """RMS envelope (dB per 50 ms) of a sound file, cached by path and modification time."""
    from pathlib import Path
    from .media import FFMPEG
    import numpy as np
    p = Path(path)
    key = (str(p), p.stat().st_mtime_ns)
    if key not in _ENVELOPES:
        raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(p), "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"], capture_output=True, timeout=300).stdout
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        n = int(rate * hop)
        frames = x[:len(x) // n * n].reshape(-1, n) if len(x) >= n else x.reshape(1, -1)
        _ENVELOPES[key] = (20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-6), hop)
    return _ENVELOPES[key]


def tail_cut(clip, path):
    """Whether an effect clip stops while its sound is still ringing: the level at the cut (last 100 ms before the end, in
    source time) within 20 dB of the clip's peak, more sound left in the file, and a fade shorter than 1 s.
    Returns the evidence or None."""
    env, hop = _envelope(path)
    speed = float(clip.get("playback_rate") or 1)
    s0 = float(clip.get("source_start") or 0)
    s1 = s0 + (clip["end_frame"] - clip["start_frame"]) / FPS * speed
    i0, i1 = int(s0 / hop), int(s1 / hop)
    if clip.get("reverse") or i1 - i0 < 4 or i1 + 10 > len(env):  # reversed, too short to judge, or the file ends here anyway
        return None
    span, rest = env[i0:i1], env[i0:]
    peak = float(span.max())
    # only transient sounds have a tail to keep: from the clip's start to the file's end the sound peaks early and dies
    # away (a blast, a burst). A steady bed or a projector rattle stops where it is cut.
    if float(rest.max()) - float(np.median(rest)) < 6 or int(rest.argmax()) > .4 * len(rest):
        return None
    at_cut = float(env[max(i0, i1 - 2):i1].mean())
    rest = float(env[i1:i1 + 10].max())
    fade = float(clip.get("fade_out") or 0)
    if peak > -50 and at_cut > peak - 20 and rest > peak - 30 and fade < 1.0:
        return {"ringing_db_below_peak": round(peak - at_cut, 1), "fade_out_s": round(fade, 2), "source_cut_s": round(s1, 2)}
    return None


class Hit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame: int = Field(ge=0)
    kind: Literal["impact", "sub_drop", "chime", "crunch", "reverse_cymbal", "riser", "pop", "tick", "shutter", "whoosh", "braam", "suck_out", "tinnitus"] = "impact"
    seconds: float | None = Field(default=None, gt=.05, le=8)


class SfxSync(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transitions: bool = True
    entrances: Literal["auto", "none"] | list[str] = "auto"
    hits: list[Hit] = Field(default_factory=list, max_length=60)
    min_gap_s: float = Field(default=1.2, ge=0, le=10)
    max_per_min: int = Field(default=14, ge=1, le=60)
    entrance_kind: Literal["pop", "tick", "whoosh", "shutter"] = "pop"
    glitch_kind: Literal["crunch", "tick", "impact"] = "crunch"
    variants: int = Field(default=3, ge=1, le=6)
    seed: int = Field(default=11, ge=0)
    replace: bool = True  # drop earlier clips of this prefix first
    prefix: str = Field(default="sfx", max_length=24, pattern=r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")  # accent_sync uses its own


def plan(t, q: SfxSync):
    events = []
    if q.transitions:
        for s in t["shots"][1:]:
            tr = s.get("transition") or {}
            name = tr.get("name")
            if name in MOVING:
                events.append({"frame": s["start_frame"] + tr.get("duration_frames", 12) // 2, "kind": "whoosh", "why": f"{name} into {s['id']}"})
            elif name == "glitch_cut":
                events.append({"frame": s["start_frame"], "kind": q.glitch_kind, "why": f"glitch into {s['id']}"})
    if q.entrances != "none":
        wanted = set(q.entrances) if isinstance(q.entrances, list) else None
        for l in sorted(t["layers"], key=lambda l: l["start_frame"]):
            if wanted is not None:
                if l["id"] not in wanted:
                    continue
            elif l["kind"] not in ("text", "svg", "counter", "shape", "icon", "callout", "bar_chart", "line_chart", "flow") or l["start_frame"] < 3 \
                    or not any(e["name"] in ENTRANCE_FX and e.get("start_frame", 0) <= 2 for e in l.get("effects") or []):
                continue
            events.append({"frame": l["start_frame"] + 1, "kind": q.entrance_kind, "why": f"entrance {l['id']}"})
    events += [{"frame": h.frame, "kind": h.kind, "seconds": h.seconds, "why": "requested hit"} for h in q.hits]
    events.sort(key=lambda e: (e["frame"], e["why"] != "requested hit"))
    kept, skipped, recent = [], [], []
    for e in events:
        explicit = e["why"] == "requested hit"
        if not explicit and kept and e["frame"] - kept[-1]["frame"] < q.min_gap_s * FPS:
            skipped.append({**e, "reason": "closer than min_gap_s to the previous accent"})
            continue
        recent = [f for f in recent if e["frame"] - f < 60 * FPS]
        if not explicit and len(recent) >= q.max_per_min:
            skipped.append({**e, "reason": "over max_per_min"})
            continue
        kept.append(e)
        recent.append(e["frame"])
    return kept, skipped


def sync(pid, base_revision, request, dry_run=False):
    q = SfxSync.model_validate(request or {})
    t = _timeline(pid, base_revision)
    kept, skipped = plan(t, q)
    if dry_run:
        return {"dry_run": True, "accents": kept, "skipped": skipped[:30]}
    r = _prepare(pid, base_revision, t, q, kept, skipped)
    rev, ops = r["revision"], r["ops"]
    for i in range(0, len(ops), 90):
        rev = agent.patch(pid, rev, ops[i:i + 90])["revision"]
    return {"revision": rev, "placed": r["placed"], "accents": kept, "skipped": skipped[:30], "assets": r["assets"],
            "note": "Listen to the mixed render; accents sit under narration, and the audit flags density or repetition."}


def prepare(pid, base_revision, request):
    """The sound clips for a request, without placing them: imports the procedural sounds (new assets, not timeline
    edits) and returns {revision, ops, placed, skipped} for the caller's own patch (accent_sync applies its picture
    accents and their sounds in one atomic patch)."""
    q = SfxSync.model_validate(request or {})
    t = _timeline(pid, base_revision)
    kept, skipped = plan(t, q)
    r = _prepare(pid, base_revision, t, q, kept, skipped)
    return {**r, "skipped": skipped[:30]}


def _prepare(pid, base_revision, t, q, kept, skipped):
    total = t["total_frames"]
    rev, cache, clips = base_revision, {}, []
    for k, e in enumerate(kept):
        dur0, gain, anchor = ACCENTS[e["kind"]]
        dur = e.get("seconds") or dur0
        variant = k % q.variants
        key = (e["kind"], round(dur, 3), variant)
        if key not in cache:
            snd = sound.design(e["kind"], dur, q.seed + 97 * variant + len(e["kind"]), gain)
            imp = agent.import_media(pid, snd["path"], f"sfx {e['kind']} procedural", "decoration", True, rev)
            rev = imp["revision"]
            cache[key] = (imp["asset"]["id"], snd)
        asset, snd = cache[key]
        length = int(snd["duration"] * FPS + 1e-6)  # whole frames the file holds (floor: never longer than the file)
        if anchor == "end":  # a swell or pull-in ends exactly on the event frame: a 1-frame gap reads as a startle gap
            end = min(total, e["frame"])
            start = end - length
            cut_head = max(0, -start)
            start = max(0, start)
        else:
            at = {"peak": snd["peak_s"], "onset": snd["onset_s"]}[anchor]
            start = e["frame"] - round(at * FPS)
            cut_head = max(0, -start)
            start = max(0, start)
            end = min(total, start + length - cut_head)
        if end - start < 2:
            skipped.append({**e, "reason": "falls outside the timeline"})
            continue
        clips.append({"id": f"{q.prefix}-{k:03d}-{e['kind']}", "asset_id": asset, "start_frame": start, "end_frame": end, "source_start": round(cut_head / FPS, 4),
                      "volume": 1.0, "fade_in": 0, "fade_out": .03, "duck_under_voice": False, "role": "sfx"})
        e["placed"] = [start, end]
    ops = []
    if q.replace:
        ops += [{"op": "delete_audio", "id": c["id"]} for c in t.get("audio_clips") or [] if re.match(rf"^{re.escape(q.prefix)}-\d{{3}}-", c["id"])]
    ops += [{"op": "upsert_audio", "audio": c} for c in clips]
    return {"revision": rev, "ops": ops, "placed": len(clips), "assets": len(cache)}


def _loudness(path):
    """Integrated loudness, range, true peak, and the momentary (400 ms) series from FFmpeg's EBU R128 meter."""
    from .media import FFMPEG
    p = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(path), "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace", timeout=600)
    log = p.stderr
    series = [(float(a), float(b)) for a, b in re.findall(r"t:\s*([\d.]+)\s+TARGET.*?M:\s*(-?[\d.]+|-inf)", log)] if "M:" in log else []
    grab = lambda k: (lambda m: float(m.group(1)) if m else None)(re.search(k + r":\s*(-?[\d.]+)", log.split("Summary:")[-1]))
    return {"integrated_lufs": grab("I"), "range_lu": grab("LRA"), "true_peak_dbfs": grab("Peak"), "momentary": series}


def audit(pid=None, path=None):
    """Accent plan checks from the timeline and loudness checks from a rendered file."""
    findings, out = [], {}
    if pid:
        t = agent.read(pid)["timeline"]
        accents = sorted([c for c in t.get("audio_clips") or [] if c["end_frame"] - c["start_frame"] <= 3 * FPS], key=lambda c: c["start_frame"])
        dur_min = t["total_frames"] / FPS / 60
        out["accents"] = len(accents)
        out["accents_per_min"] = round(len(accents) / max(dur_min, 1e-6), 2)
        if accents and len(accents) / max(dur_min, 1 / 60) > 16:
            findings.append({"level": "check", "code": "accent_density", "evidence": out["accents_per_min"],
                             "suggestion": "More than ~16 accents per minute reads as clutter; keep the moments that matter."})
        for a, b in zip(accents, accents[1:]):
            if a["asset_id"] == b["asset_id"] and b["start_frame"] - a["start_frame"] < 10 * FPS and not re.search(r"(entrance|pop|tick)", a["id"]):
                findings.append({"level": "check", "code": "repeated_sample", "where": [a["id"], b["id"]],
                                 "suggestion": "Same sample twice within 10 s; use a variant (sfx_sync rotates seeds)."})
        risers = [c for c in t.get("audio_clips") or [] if re.search(r"(riser|reverse_cymbal)", c["id"])]
        for r in risers:
            end = r["end_frame"]
            if not any(abs(s["start_frame"] - end) <= 3 for s in t["shots"]) and not any(abs(c["start_frame"] - end) <= 3 for c in t.get("audio_clips") or [] if c is not r):
                findings.append({"level": "check", "code": "riser_without_payoff", "where": r["id"],
                                 "suggestion": "A swell should resolve on a cut or a hit within 3 frames of its end."})
        clips = t.get("audio_clips") or []
        # builds (sirens, pulses, risers) must pay off: a hit at their end, not a fade into nothing. Overlapping build clips
        # (a siren bed under a clock and a Shepard rise) are one build: the chain is judged where its last layer ends.
        builds = sorted([c for c in clips if is_build(c) and c["end_frame"] - c["start_frame"] >= 2 * FPS and not re.search(r"(riser|reverse_cymbal)", c["id"], re.I)],
                        key=lambda c: c["start_frame"])
        chains = []
        for c in builds:
            if chains and c["start_frame"] <= max(x["end_frame"] for x in chains[-1]) + 3:
                chains[-1].append(c)
            else:
                chains.append([c])
        hits = [c for c in clips if is_hit(c)]
        for ch in chains:
            end = max(x["end_frame"] for x in ch)
            last = [x for x in ch if x["end_frame"] >= end - 3]
            b = last[0]
            secs = (end - min(x["start_frame"] for x in ch)) / FPS
            fade = max(float(x.get("fade_out") or 0) for x in last)
            ids = [x["id"] for x in ch]
            # or a held silence of 0.5-3 s, then the hit (the gap is long enough not to dampen the startle; ambience may stay)
            held = any(15 <= h["start_frame"] - end <= 90 and not any(c not in ch and c is not h and c.get("role") != "ambience"
                                                                    and c["start_frame"] < h["start_frame"] - 3 and c["end_frame"] > end + 3 for c in clips)
                       for h in hits)
            if not (any(abs(h["start_frame"] - end) <= 3 for h in hits) or held) or fade >= .5:
                findings.append({"level": "check", "code": "build_without_payoff", "where": ids[0] if len(ids) == 1 else ids,
                                 "evidence": {"seconds": round(secs, 1), "fade_out_s": fade},
                                 "suggestion": "A siren, quickening pulse or riser makes the audience wait for a release; end it on a hit (impact, blast) "
                                               "within 3 frames of its last frame, without fading it out. A build that dissolves reads as a promise not kept."})
            limit = PULSE_MAX_S if all(PULSE_ID.search(x["id"]) for x in ch) else BUILD_MAX_S
            if secs > limit:
                findings.append({"level": "check", "code": "build_too_long", "where": ids[0] if len(ids) == 1 else ids,
                                 "evidence": {"seconds": round(secs, 1), "limit_s": limit},
                                 "suggestion": f"Builds over ~{limit:.0f} s tire rather than tense (8 bars is the usual length); start it later."})
        builds = [{"id": ch[0]["id"], "start_frame": min(x["start_frame"] for x in ch), "end_frame": max(x["end_frame"] for x in ch)} for ch in chains]
        major = [b for b in builds if b["end_frame"] - b["start_frame"] >= 4 * FPS]
        for a, b in zip(major, major[1:]):
            if b["end_frame"] - a["end_frame"] < BUILD_SPACING_S * FPS and b["start_frame"] >= a["end_frame"] - FPS:
                findings.append({"level": "check", "code": "builds_too_close", "where": [a["id"], b["id"]],
                                 "evidence": {"apart_s": round((b["end_frame"] - a["end_frame"]) / FPS, 1)},
                                 "suggestion": "Two major builds within a minute: the second loses its force. Strip back between them (Oliver Tarney: "
                                               "build to each event, then strip everything back) or merge them into one."})
        # effects cut while still ringing: explosions and gunfire need their natural tail (>= 1 s fade, across the next cut)
        try:
            paths = {a["id"]: a["path"] for a in store.assets(pid)}
        except Exception:  # a plan audited without its media library
            paths = {}
        for c in clips:
            if c.get("role") not in (None, "sfx", "foley") or c["end_frame"] - c["start_frame"] < 8 or c["asset_id"] not in paths or is_pull_in(c):
                continue
            try:
                ev = tail_cut(c, paths[c["asset_id"]])
            except (OSError, subprocess.SubprocessError, ValueError):
                ev = None
            if ev:
                findings.append({"level": "check", "code": "sfx_tail_cut", "where": c["id"], "evidence": ev,
                                 "suggestion": "The effect stops while it still rings. Let explosion and gunfire tails play out (>= 2.5 s close, >= 4 s "
                                               "distant), fade over >= 1 s, and carry the tail across the next picture cut."})
        # The sound must never stop by accident: a span of 1 s or more where no clip plays is digital silence in a silent
        # project (a chapter card over nothing reads as a dropout); intended silence carries room tone.
        spans = sorted((c["start_frame"], c["end_frame"]) for c in clips if float(c.get("volume") or 0) > 0)
        reach, gaps = 0, []
        for a, b in spans:
            if a - reach >= FPS:
                gaps.append([reach, a])
            reach = max(reach, b)
        if t["total_frames"] - reach >= FPS and spans:
            gaps.append([reach, t["total_frames"]])
        if gaps and spans and str(t.get("timing_method", "")).startswith(("source_video", "silent")):  # no narration track to fill them
            findings.append({"level": "check", "code": "uncovered_gap", "where": gaps[:10], "evidence": {"gaps": len(gaps), "longest_s": round(max(b - a for a, b in gaps) / FPS, 1)},
                             "suggestion": "No clip plays for 1 s or more: unless the narration track fills it, lay room tone or let the music's tail carry "
                                           "across (chapter cards and black holds especially)."})
        # A run of voices with no pause of 2 s for more than 45 s gives the viewer no time to take in what was said
        # (round 13: 155 s in the fourth film's first chapter; the script audit had passed its breaths).
        vs = sorted((c["start_frame"], c["end_frame"]) for c in clips if c.get("role") == "dialogue")
        runs, cur = [], None
        for a_, b_ in vs:
            if cur and a_ - cur[1] < 2 * FPS:
                cur[1] = max(cur[1], b_)
            else:
                if cur:
                    runs.append(cur)
                cur = [a_, b_]
        runs += [cur] if cur else []
        long_runs = [r_ for r_ in runs if r_[1] - r_[0] > 45 * FPS]
        if long_runs:
            findings.append({"level": "check", "code": "voice_run", "where": long_runs[:8],
                             "evidence": {"runs": len(long_runs), "longest_s": round(max(b_ - a_ for a_, b_ in long_runs) / FPS, 1)},
                             "suggestion": "Voices run on for more than 45 s without a 2 s pause: open a breath of picture and music "
                                           "between lines (segmenting), every 30-45 s."})
        # A voice is buried when effects or music that do not duck play under it at full level.
        voices = [c for c in clips if c.get("role") == "dialogue"]
        under = {}
        for v in voices:
            for c in clips:
                if c is v or c.get("role") == "dialogue" or c.get("duck_under_voice") or float(c.get("volume") or 0) < .3:
                    continue
                ov = min(v["end_frame"], c["end_frame"]) - max(v["start_frame"], c["start_frame"])
                if ov >= FPS:
                    under.setdefault(c["id"], v["id"])
        if under:
            findings.append({"level": "check", "code": "undimmed_under_voice", "where": list(under)[:12], "evidence": {"clips": len(under)},
                             "suggestion": "These clips play at full level under a voice: set duck_under_voice (effects and ambience with a lighter "
                                           "ratio than music) or lower them, so every line keeps >= 15 dB over its background."})
        for h in [c for c in clips if is_hit(c)]:
            hit = h["start_frame"]
            early = [c["id"] for c in clips if c is not h and c.get("role") != "music" and not LEAD_IN_ID.search(c["id"]) and not c.get("reverse")
                     and c["end_frame"] - c["start_frame"] <= 3 * FPS and 1 <= hit - c["start_frame"] <= 15]
            if early:
                findings.append({"level": "check", "code": "startle_prepulse", "where": [h["id"], *early[:4]],
                                 "suggestion": "A weak sound 30-500 ms before a hit dampens the startle it should cause (prepulse inhibition); move it after the hit or more than 0.5 s before."})
            gaps = [c["id"] for c in clips if is_pull_in(c) and 1 <= hit - c["end_frame"] <= 15]
            if gaps:
                findings.append({"level": "check", "code": "startle_gap", "where": [h["id"], *gaps[:4]],
                                 "suggestion": "The pull-in stops 30-500 ms before the hit: a short gap dampens the startle (gap prepulse inhibition). End it on the hit frame or hold the silence at least 0.5 s."})
    if path:
        L = _loudness(path)
        m = L.pop("momentary")
        out["loudness"] = L
        silent = sum(1 for _, v in m if v < -60) / max(1, len(m))
        if silent > .95:
            findings.append({"level": "info", "code": "silent_mix", "suggestion": "The render is effectively silent (picture-only delivery or voice to be added later)."})
        else:
            dead, run = [], 0
            for (tt, v) in m:
                run = run + 1 if v < -45 else 0
                if run == 5:  # 0.5 s at the 100 ms meter step
                    dead.append(round(tt - .4, 1))
            if dead:
                findings.append({"level": "check", "code": "dead_air", "where": dead[:10],
                                 "suggestion": "Momentary loudness under -45 LUFS for 0.5 s: add room tone/ambience unless the silence is intended."})
        if L.get("true_peak_dbfs") is not None and L["true_peak_dbfs"] > -1:
            findings.append({"level": "likely_problem", "code": "true_peak", "evidence": L["true_peak_dbfs"],
                             "suggestion": "True peak above -1 dBFS clips after platform encoding; lower the master or limit it."})
    return {**out, "findings": findings,
            "targets": "Speech-led mix about -16 LUFS integrated, true peak <= -1 dBFS; music 10-18 dB under speech, ambience 20-30 dB under, accents peaking near dialogue."}


def _norm_words(text):
    import unicodedata
    return re.findall(r"[\wÀ-ỹ']+", unicodedata.normalize("NFC", (text or "").lower()))


def phrase_span(words, phrase):
    """(start, end) seconds of `phrase` inside a word-timed transcript [{"word", "start", "end"}] (faster-whisper's word
    timestamps), matched on normalised words in order; None when the phrase is not heard."""
    want = _norm_words(phrase)
    heard = [(w2, x["start"], x["end"]) for x in words for w2 in _norm_words(x.get("word"))]
    for i in range(len(heard) - len(want) + 1):
        if [h[0] for h in heard[i:i + len(want)]] == want:
            return heard[i][1], heard[i + len(want) - 1][2]
    return None


def unison_offset(words_a, phrase_a, words_b, phrase_b, align="end"):
    """Voice in unison (round 13: Hồ Chí Minh's 1945 declaration and an American reading of 1776 saying the same sentence
    together): the time to place recording B relative to recording A so that B's phrase lands on A's phrase, by their
    ends (the last word together: "bình đẳng" with "equal") or their starts. Returns {"offset", "a", "b"}: start B at
    A's position + offset (seconds, in A's clock)."""
    a, b = phrase_span(words_a, phrase_a), phrase_span(words_b, phrase_b)
    if not a or not b:
        raise ValueError(f"phrase not heard in {'A' if not a else 'B'}; transcribe with word_timestamps and check the wording")
    off = (a[1] - b[1]) if align == "end" else (a[0] - b[0])
    return {"offset": round(off, 3), "a": [round(a[0], 3), round(a[1], 3)], "b": [round(b[0], 3), round(b[1], 3)]}
