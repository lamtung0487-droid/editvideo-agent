"""Multicam: sync angles by audio, then switch to the active speaker with measured podcast/interview rules.

Measured (round-4 study of a live podcast switch and film dialogue): cut to the next speaker ~12-20 frames before
their turn starts; backchannels (short "yeah"/"mm" under 0.7 s) do not earn a cut; bursts of overlapping or rapid turns
go to the wide and hold ~3.5 s; shots run 3.5-4.3 s (never under ~2.5 s); in a long monologue a 1.5-3 s listener shot
(reaction) keeps the scene alive and plays as an L-cut under the speaker's voice.
"""
import math
import subprocess
import numpy as np
from . import store
from .media import FFMPEG, probe

ENV_SR = 100  # envelope samples per second for sync


def _env(path, sr=8000, max_s=600):
    raw = subprocess.run([FFMPEG, "-v", "error", "-t", str(max_s), "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, timeout=900).stdout
    x = np.frombuffer(raw, np.float32)
    if len(x) < sr:
        raise ValueError(f"{path}: no usable audio for sync")
    hop = sr // ENV_SR
    n = len(x) // hop
    e = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    e = np.log(e + 1e-4)
    d = np.maximum(np.diff(e, prepend=e[0]), 0)  # onset envelope: robust to different mic gains and room colour
    return (d - d.mean()) / (d.std() + 1e-9), x, sr


def sync_offset(master, angle, max_offset_s=30.0):
    """Seconds to add to master time to get the same moment in the angle file (angle_t = master_t + offset), with a
    confidence = best correlation peak over the runner-up outside ±0.2 s."""
    a, xa, sr = _env(master)
    b, xb, _ = _env(angle)
    n = 1 << int(math.ceil(math.log2(len(a) + len(b))))
    c = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)
    lags = np.r_[np.arange(0, len(b)), np.arange(-len(a) + 1, 0)]
    vals = np.r_[c[: len(b)], c[n - len(a) + 1:]]
    lim = int(max_offset_s * ENV_SR)
    ok = np.abs(lags) <= lim
    i = int(np.argmax(np.where(ok, vals, -np.inf)))
    coarse = lags[i] / ENV_SR
    far = ok & (np.abs(lags - lags[i]) > .2 * ENV_SR)
    conf = float(vals[i] / (vals[far].max() + 1e-9)) if far.any() else 9.0
    # Refine to the sample with raw-waveform correlation in a ±15 ms window around the coarse lag.
    seg = xa[: min(len(xa), sr * 20)]
    best, off = -1e9, coarse
    for k in range(-120, 121, 2):
        s = int(round(coarse * sr)) + k
        if s < 0 or s + len(seg) > len(xb):
            continue
        v = float(np.dot(seg, xb[s: s + len(seg)]))
        if v > best:
            best, off = v, s / sr
    return round(off, 4), round(conf, 2)


def plan_switch(segs, angles_by_speaker, wide, total_s, fps=30, lead=12, min_shot=75, backchannel_s=.7, burst_turns=3, burst_window_s=4.0,
                wide_hold=105, reaction_every_s=10.0, reaction_frames=60, establish_frames=90):
    """segs: [{start, end, speaker}] master seconds. Returns [(start_frame, angle_key, reason)]."""
    total = int(round(total_s * fps))
    turns = []
    for i, s in enumerate(segs):
        prev = segs[i - 1]["speaker"] if i else None
        if s["speaker"] != prev:
            short = s["end"] - s["start"] < backchannel_s
            nxt = segs[i + 1]["speaker"] if i + 1 < len(segs) else None
            if short and prev is not None and nxt == prev:
                continue  # a backchannel inside someone else's turn
            turns.append((s["start"], s["speaker"]))
    first = wide if wide is not None else (angles_by_speaker.get(turns[0][1]) if turns else 0)
    cuts = [(0, first, "establish")]
    k = 0
    while k < len(turns):
        t, spk = turns[k]
        # Rapid exchange: several speaker changes inside a short window → hold the wide.
        burst = [x for x in turns[k:] if x[0] - t <= burst_window_s]
        if wide is not None and len(burst) >= burst_turns:
            cuts.append((max(0, int(t * fps) - lead), wide, "crosstalk"))
            hold_to = int(t * fps) + wide_hold
            while k < len(turns) and int(turns[k][0] * fps) < hold_to:
                k += 1
            continue
        cuts.append((max(0, int(t * fps) - lead), angles_by_speaker.get(spk, wide), f"turn {spk}"))
        k += 1
    # Reaction inserts in long monologues: the listener for reaction_frames, mid-way, as an L-cut.
    out = []
    for i, (f, a, why) in enumerate(cuts):
        out.append((f, a, why))
        nf = cuts[i + 1][0] if i + 1 < len(cuts) else total
        if why.startswith("turn") and (nf - f) / fps > reaction_every_s and len(angles_by_speaker) > 1:
            listener = next((v for s_, v in angles_by_speaker.items() if v != a), None)
            if listener is not None:
                mid = f + (nf - f) // 2
                out.append((mid, listener, "reaction"))
                out.append((mid + reaction_frames, a, "back to speaker"))
    # Enforce the establishing wide and the minimum shot length (drop cuts that come too soon).
    out.sort(key=lambda c: c[0])
    clean = []
    for i, (f, a, why) in enumerate(out):
        if a is None or (clean and a == clean[-1][1]):
            continue
        until = out[i + 1][0] if i + 1 < len(out) else total
        if clean:
            need = establish_frames if clean[-1][2] == "establish" else min_shot
            if f - clean[-1][0] < need:
                f2 = clean[-1][0] + need  # hold the current shot to the minimum, then cut if this turn still runs
                if f2 > until - 30:
                    continue
                f, why = f2, why + " (held)"
        clean.append((f, a, why))
    return [c for c in clean if c[0] < total]


def build(angles, master=None, speakers=None, profile="landscape", engine="remotion", title=None, dry_run=True, **rules):
    """angles: [{path, kind: wide|single, speaker?: 'S1'}]; master: audio file (default: the wide angle).
    Syncs every angle to the master, reads who speaks when on the master, maps speakers to angles (given, or from which
    single angle hears each speaker loudest), plans the switch and (dry_run=False) builds a new project whose picture
    switches between angles over the continuous master audio."""
    from . import dialogue
    if not angles or len(angles) > 6:
        raise ValueError("1..6 angles")
    wide = next((i for i, a in enumerate(angles) if a.get("kind") == "wide"), None)
    master = master or angles[wide if wide is not None else 0]["path"]
    offsets = [sync_offset(master, a["path"]) for a in angles]
    r = dialogue.read(master, speakers=speakers)
    import json
    from pathlib import Path
    segs = json.loads(Path(r["manifest"]).read_text(encoding="utf-8"))["segments"]
    total_s = float(probe(master)["format"]["duration"])
    by_spk = {a["speaker"]: i for i, a in enumerate(angles) if a.get("speaker")}
    if not by_spk:
        # Which single angle hears each speaker loudest (lavalier / near mic): energy during that speaker's regions.
        singles = [i for i, a in enumerate(angles) if a.get("kind") != "wide"]
        energy = {}
        for i in singles:
            _, x, sr = _env(angles[i]["path"])
            for s in segs:
                a0, a1 = int((s["start"] + offsets[i][0]) * sr), int((s["end"] + offsets[i][0]) * sr)
                if 0 <= a0 < a1 <= len(x):
                    energy.setdefault((s["speaker"], i), []).append(float(np.mean(x[a0:a1] ** 2)))
        spks = sorted({s["speaker"] for s in segs})
        for spk in spks:
            cand = [(np.mean(energy.get((spk, i), [0])) / (np.mean([np.mean(v) for (s_, j), v in energy.items() if j == i]) + 1e-12), i) for i in singles]
            if cand:
                by_spk[spk] = max(cand)[1]
        if len(set(by_spk.values())) < len(by_spk) and singles:  # identical room audio: fall back to order
            by_spk = {spk: singles[k % len(singles)] for k, spk in enumerate(spks)}
    plan = plan_switch(segs, by_spk, wide, total_s, **rules)
    fps = 30
    total = int(round(total_s * fps))
    durs = [float(probe(a["path"])["format"]["duration"]) for a in angles]
    base = wide if wide is not None else 0
    covers = lambda i, f, e: f / fps + offsets[i][0] >= -1e-3 and e / fps + offsets[i][0] <= durs[i] + 1e-3
    shots = []
    for k, (f, a, why) in enumerate(plan):
        e = plan[k + 1][0] if k + 1 < len(plan) else total
        if not covers(a, f, e):  # that camera was not recording for the whole shot: fall back to one that was
            alt = next((i for i in [base, *range(len(angles))] if covers(i, f, e)), None)
            if alt is None:
                raise ValueError(f"no angle covers {f / fps:.2f}-{e / fps:.2f} s of the master; trim the master or add coverage")
            a, why = alt, why + f" (angle {a} not recording)"
        if shots and shots[-1]["angle"] == a:  # same camera continues: one shot
            shots[-1]["end_frame"] = e
            continue
        shots.append({"angle": a, "start_frame": f, "end_frame": e, "source_start": round(max(0.0, f / fps + offsets[a][0]), 4), "why": why})
    lens = [(s["end_frame"] - s["start_frame"]) / fps for s in shots]
    share = {}
    for s in shots:
        share[s["angle"]] = share.get(s["angle"], 0) + s["end_frame"] - s["start_frame"]
    summary = {"offsets_s": [o[0] for o in offsets], "sync_confidence": [o[1] for o in offsets], "speakers_to_angles": by_spk,
               "shots": len(shots), "median_shot_s": round(float(np.median(lens)), 2), "min_shot_s": round(min(lens), 2),
               "angle_share": {str(k): round(v / total, 3) for k, v in sorted(share.items())},
               "reasons": {w: sum(1 for s in shots if s["why"].startswith(w)) for w in ("establish", "turn", "crosstalk", "reaction", "back")}}
    if any(c < 1.5 for c in summary["sync_confidence"][1:]):
        summary["warning"] = "a low sync confidence: check that angle (slate clap or common sound helps)"
    if dry_run:
        return {"dry_run": True, **summary}
    from . import agent
    made = agent.from_multicam(master, [angles[i]["path"] for i in range(len(angles))], shots, profile, engine, title)
    return {**summary, **made}
