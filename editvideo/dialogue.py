"""Dialogue senses and hands: audio profile (floor, SNR, hum, sibilance, band balance), dialogue reading (speech regions,
pauses, speakers, filler candidates), condensing (pause/filler removal with picture and sound cut together) and a
measured cleanup chain.

Targets come from measured edits (round-4 study, local analysis only): finished talking edits keep 16-29 pauses ≥120 ms
per minute, median 0.16-0.39 s, p90 0.29-0.50 s, longest 0.57-0.80 s, no pause ≥1 s, 8.5-13.7 % silence, ≈0.1
fillers/min. A dialogue chain measured on screen: HPF ~100-124 Hz, mud cut 250-450 Hz, presence 2-8 kHz, compressor
-23 dB 2.5:1 7 ms/85 ms, de-ess ~4.5 kHz. Its failure mode was measured too: a big presence boost plus make-up gain raised
the noise floor 16 dB while speech rose 7.8 dB, so every cleanup reports floor and SNR before and after.
"""
import json
import math
import subprocess
import uuid
from pathlib import Path
import numpy as np
from . import store
from .media import FFMPEG, probe, sha256

SR = 16000
HOP = 320    # 20 ms
WIN = 480    # 30 ms
FILLER_WORDS = {"um", "uh", "erm", "er", "ah", "uhm", "hmm", "mm", "ờ", "ừ", "ừm", "à", "ơ", "ạ"}


def _audio(path, start=0.0, end=None, sr=SR, channels=1):
    cmd = [FFMPEG, "-v", "error", "-ss", str(start), *(["-t", str(end - start)] if end else []), "-i", str(path), "-vn", "-ac", str(channels),
           "-ar", str(sr), "-f", "f32le", "-"]
    x = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True, timeout=600).stdout, np.float32)
    if channels > 1:
        x = x[: len(x) // channels * channels].reshape(-1, channels)
    if len(x) < sr // 2:
        raise ValueError("Need at least 0.5 s of audio")
    return x


def _frames_db(x):
    n = max(1, 1 + (len(x) - WIN) // HOP)
    c = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    k = np.arange(n) * HOP
    return 10 * np.log10((c[k + WIN] - c[k]) / WIN + 1e-12)


def _bands_db(x, bands, sr=SR, n=2048, hop=HOP, chunk=512):
    """Per-frame energy (dB) in several bands from ONE short-time spectrum, computed in float32 chunks so memory stays
    constant with duration (was four full float64 spectrograms: ~2.6 MB per second of audio)."""
    xs = np.asarray(x, np.float32)
    nfr = max(1, 1 + (len(xs) - n) // hop)
    f = np.fft.rfftfreq(n, 1 / sr)
    win = np.hanning(n).astype(np.float32)
    masks = [(f >= lo) & (f < hi) for lo, hi in bands]
    out = np.empty((len(bands), nfr))
    for a in range(0, nfr, chunk):
        k = np.arange(a, min(nfr, a + chunk))
        idx = np.clip(np.arange(n)[None, :] + hop * k[:, None], 0, len(xs) - 1)
        spec = np.abs(np.fft.rfft(xs[idx] * win, axis=1)) ** 2
        for j, m in enumerate(masks):
            out[j, a:a + len(k)] = 10 * np.log10(spec[:, m].sum(1) + 1e-12)
    return out


def _band_db(x, lo, hi, sr=SR, n=2048):
    """Per-frame energy (dB) in a band from a short-time spectrum (frames of HOP)."""
    return _bands_db(x, [(lo, hi)], sr, n)[0]


def profile(path, start=0.0, end=None):
    """Compact dialogue audio measurement: noise floor (p5 of 20 ms RMS), speech level (p90), SNR, 50/60 Hz hum,
    band balance, sibilance index (p95 of 5-9 kHz over 1-4 kHz energy), clipped samples, loudness."""
    x = _audio(path, start, end, 32000)
    fr = HOP * 2  # 20 ms at 32 kHz
    n = len(x) // fr
    rms = 10 * np.log10((x[: n * fr].reshape(n, fr) ** 2).mean(1) + 1e-12)
    floor, speech = float(np.percentile(rms, 5)), float(np.percentile(rms, 90))
    spec_n = 1 << 16
    seg = x[: min(len(x), 32000 * 30)]
    sp = np.abs(np.fft.rfft(seg[: spec_n] * np.hanning(min(spec_n, len(seg))) if len(seg) >= spec_n else seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(min(spec_n, len(seg)), 1 / 32000)
    def peak_db(fc):
        m = (f > fc - 1.5) & (f < fc + 1.5)
        ring = ((f > fc - 12) & (f < fc - 4)) | ((f > fc + 4) & (f < fc + 12))
        return 10 * np.log10(sp[m].max() / (np.median(sp[ring]) + 1e-20) + 1e-12) if m.any() and ring.any() else 0.0
    hum = {str(base): round(max(peak_db(base * k) for k in (1, 2, 3)), 1) for base in (50, 60)}
    tot = sp.sum() + 1e-20
    band = lambda lo, hi: round(10 * np.log10(sp[(f >= lo) & (f < hi)].sum() / tot + 1e-12), 1)
    # At the 32 kHz capture rate directly (20 ms hop, 128 ms window): no decimation, so nothing above 8 kHz folds into
    # the sibilance band.
    hi, mid, voice = _bands_db(x, [(5000, 8000), (1000, 4000), (100, 4000)], 32000, 4096, 640)
    sib = hi - mid
    voiced = voice > np.percentile(voice, 50)
    from .audiofx import _loudness
    tmp = store.DATA / "observations" / f"prof-{uuid.uuid4().hex[:8]}.wav"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "f32le", "-ar", "32000", "-ac", "1", "-i", "-", str(tmp)], input=x.tobytes(), check=True)
    try:
        L = _loudness(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    return {"floor_db": round(floor, 1), "speech_db": round(speech, 1), "snr_db": round(speech - floor, 1),
            "hum_db_over_neighbours": hum, "hum": bool(max(hum.values()) > 15),
            "bands_db": {"low_<120": band(20, 120), "mud_250-500": band(250, 500), "presence_2-4k": band(2000, 4000), "air_4-9k": band(4000, 9000)},
            "sibilance_index_db": round(float(np.percentile(sib[voiced[: len(sib)]] if voiced[: len(sib)].any() else sib, 95)), 1),
            "clipped_samples": int((np.abs(x) > .999).sum()), "lufs": L.get("integrated_lufs"), "true_peak_dbfs": L.get("true_peak_dbfs"),
            "window": [start, round(start + len(x) / 32000, 3)]}


def compare(a, b):
    """Deltas between two profiles (after - before), the shape an AI needs to judge a cleanup."""
    d = lambda k: round(b[k] - a[k], 1) if a.get(k) is not None and b.get(k) is not None else None
    out = {"floor_db": d("floor_db"), "speech_db": d("speech_db"), "snr_db": d("snr_db"), "sibilance_index_db": d("sibilance_index_db"), "lufs": d("lufs"),
           "hum_db": round(max(b["hum_db_over_neighbours"].values()) - max(a["hum_db_over_neighbours"].values()), 1),
           "bands_db": {k: round(b["bands_db"][k] - a["bands_db"][k], 1) for k in a["bands_db"]}}
    warn = []
    if (out["floor_db"] or 0) > (out["speech_db"] or 0) + 1:
        warn.append("noise floor rose more than speech: add denoise or an expander, or reduce presence/make-up gain")
    if (out["sibilance_index_db"] or 0) > 3:
        warn.append("sibilance up > 3 dB: de-ess or reduce the presence boost")
    out["warnings"] = warn
    return out


# ---------------------------------------------------------------- dialogue reading
def _pitch(x, sr=SR):
    """Median F0 (Hz) of voiced 40 ms frames by normalised autocorrelation, 70-400 Hz; None if mostly unvoiced."""
    n, hop = 640, 320
    lo, hi = sr // 400, sr // 70
    f0 = []
    for i in range(0, len(x) - n, hop):
        fr = x[i:i + n] - x[i:i + n].mean()
        e = float((fr * fr).sum())
        if e < 1e-6:
            continue
        ac = np.correlate(fr, fr, "full")[n - 1:]
        ac = ac / (ac[0] + 1e-12)
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > .45:
            f0.append(sr / lag)
    return f0


def _mel_feats(x, sr=SR, nb=20):
    n = 512
    nfr = max(1, 1 + (len(x) - n) // 160)
    idx = np.clip(np.arange(n)[None, :] + 160 * np.arange(nfr)[:, None], 0, len(x) - 1)
    spec = np.abs(np.fft.rfft(x[idx] * np.hanning(n), axis=1)) ** 2
    edges = np.geomspace(100, 7000, nb + 1) / (sr / n)
    bands = np.stack([spec[:, int(a):max(int(a) + 1, int(b))].sum(1) for a, b in zip(edges[:-1], edges[1:])], 1)
    lb = np.log10(bands + 1e-10)
    return lb.mean(0) - lb.mean(), spec


def _regions(db, floor_pad=None):
    floor = float(np.percentile(db, 10))
    top = float(np.percentile(db, 95))
    th = floor + max(8.0, .35 * (top - floor))
    on = db > th
    # Hangover: fill gaps under 120 ms, drop blips under 80 ms (20 ms frames).
    regs, i, n = [], 0, len(on)
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]:
                j += 1
            regs.append([i, j])
            i = j
        else:
            i += 1
    merged = []
    for r in regs:
        if merged and r[0] - merged[-1][1] < 6:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [r for r in merged if r[1] - r[0] >= 4], floor, th


def _kmeans(X, k, seed=0, iters=50):
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False)]
    for _ in range(iters):
        lab = np.argmin(((X[:, None] - C[None]) ** 2).sum(-1), 1)
        newC = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC
    return lab, C


def _silhouette(X, lab):
    if len(set(lab)) < 2:
        return -1
    D = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1))
    s = []
    for i in range(len(X)):
        same = lab == lab[i]
        a = D[i, same].sum() / max(1, same.sum() - 1)
        b = min(D[i, lab == j].mean() for j in set(lab) if j != lab[i])
        s.append((b - a) / max(a, b, 1e-9))
    return float(np.mean(s))


def read(path, start=0.0, end=None, speakers=None, words=None, max_list=10):
    """Speech regions, pauses, speakers and filler candidates. Compact result; full lists in the manifest."""
    source = Path(path).resolve(strict=True)
    x = _audio(source, start, end)
    db = _frames_db(x)
    regs, floor, th = _regions(db)
    if not regs:
        raise ValueError("No speech found above the noise floor")
    t = lambda fr: round(start + fr * HOP / SR, 3)
    segs = [{"start": t(a), "end": t(b)} for a, b in regs]
    pauses = [round(b["start"] - a["end"], 3) for a, b in zip(segs, segs[1:])]
    # Filler candidates: short isolated voiced regions with a flat pitch and a steady spectrum ("uh", "um", "ờ").
    fillers, filler_idx = [], set()
    for i, (a, b) in enumerate(regs):
        dur = (b - a) * HOP / SR
        gap_before = (a - regs[i - 1][1]) * HOP / SR if i else 1
        gap_after = (regs[i + 1][0] - b) * HOP / SR if i + 1 < len(regs) else 1
        if not (.15 <= dur <= 1.0 and gap_before >= .12 and gap_after >= .12):
            continue
        seg = x[a * HOP: b * HOP + WIN]
        f0 = _pitch(seg)
        if len(f0) < 3:
            continue
        flat = np.std(f0) / (np.median(f0) + 1e-9) < .06
        _, spec = _mel_feats(seg)
        P = spec / (spec.sum(1, keepdims=True) + 1e-12)
        flux = float(np.median(np.abs(np.diff(P, axis=0)).sum(1))) if len(P) > 2 else 1.0
        if flat and flux < .06:
            fillers.append({"id": f"f{len(fillers)}", "start": t(a), "end": t(b), "why": "flat pitch, steady vowel"})
            filler_idx.add(i)
    # Speakers: pitch (dominant) + spectral envelope per region ≥ 250 ms, k-means; k grows only when the silhouette
    # improves clearly (fillers are left out of the clustering and inherit a neighbour's speaker).
    feats, keep = [], []
    for i, (a, b) in enumerate(regs):
        if b - a < 12 or i in filler_idx:
            continue
        seg = x[a * HOP: b * HOP + WIN]
        f0 = _pitch(seg)
        env, _ = _mel_feats(seg)
        if len(f0) < 3:
            continue
        feats.append(np.r_[np.log2(np.median(f0)), env])
        keep.append(i)
    lab_all = [None] * len(segs)
    k_used = 1
    if len(feats) >= 4:
        X = np.array(feats)
        X = (X - X.mean(0)) / (X.std(0) + 1e-6)
        X[:, 0] *= 3.0  # pitch carries speaker identity; the envelope mostly carries vowel content
        X[:, 1:] *= 1.0 / math.sqrt(X.shape[1] - 1)
        if speakers:
            k_used = min(speakers, len(X))
            lab, _ = _kmeans(X, k_used)
        else:
            best = (0.35, 1, np.zeros(len(X), int))
            for k in (2, 3, 4):
                if len(X) > k * 2:
                    lab_k, _ = _kmeans(X, k)
                    sc = _silhouette(X, lab_k)
                    if sc > best[0] + (0 if best[1] == 1 else .1):
                        best = (sc, k, lab_k)
            _, k_used, lab = best
        for i, l in zip(keep, lab):
            lab_all[i] = int(l)
    # Unlabelled short regions take the nearest labelled neighbour's speaker.
    for i in range(len(lab_all)):
        if lab_all[i] is None:
            near = min((j for j in range(len(lab_all)) if lab_all[j] is not None), key=lambda j: abs(j - i), default=None)
            lab_all[i] = lab_all[near] if near is not None else 0
    for s_, l in zip(segs, lab_all):
        s_["speaker"] = f"S{l + 1}"
    for fl in fillers:
        fl["speaker"] = next((s_["speaker"] for s_ in segs if s_["start"] == fl["start"]), None)
    for w in words or []:
        token = str(w.get("word", w.get("text", ""))).strip(" ,.!?").casefold()
        if token in FILLER_WORDS:
            fillers.append({"id": f"f{len(fillers)}", "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3), "why": "asr filler word"})
    dur_total = len(x) / SR
    talk = {}
    for s_ in segs:
        talk[s_["speaker"]] = talk.get(s_["speaker"], 0) + s_["end"] - s_["start"]
    turns = sum(1 for a, b in zip(segs, segs[1:]) if a["speaker"] != b["speaker"])
    P = np.array([p for p in pauses if p >= .12]) if pauses else np.array([])
    stats = {"pauses_per_min": round(len(P) / dur_total * 60, 1), "median_s": round(float(np.median(P)), 3) if len(P) else None,
             "p90_s": round(float(np.percentile(P, 90)), 3) if len(P) else None, "max_s": round(float(P.max()), 3) if len(P) else None,
             "over_1s": int((P >= 1).sum()) if len(P) else 0, "silence_share": round(1 - sum(s_["end"] - s_["start"] for s_ in segs) / dur_total, 3)}
    manifest = store.DATA / "observations" / f"dialogue-{uuid.uuid4().hex[:10]}.json"
    store.write_json(manifest, {"source": str(source), "sha256": sha256(source), "window": [start, round(start + dur_total, 3)], "floor_db": floor,
                                "threshold_db": th, "segments": segs, "pauses": pauses, "fillers": fillers})
    return {"duration_s": round(dur_total, 2), "speakers": [{"id": k, "talk_s": round(v, 1), "share": round(v / max(1e-6, sum(talk.values())), 3)} for k, v in sorted(talk.items())],
            "speaker_model": "pitch + spectral envelope clustering (no identity)" if k_used > 1 else "one voice detected",
            "regions": len(segs), "turns": turns, "pause_stats": stats, "fillers": {"count": len(fillers), "first": fillers[:max_list]},
            "targets": "finished talking edits: p90 pause 0.29-0.50 s, max < 0.8 s, no pause ≥ 1 s, silence 8.5-13.7 %",
            "manifest": str(manifest)}


# ---------------------------------------------------------------- hands: condense and clean
def plan_condense(manifest, max_pause_s=.5, target_pause_s=.3, remove_fillers=True, edge_s=.2):
    """Keep ranges after shortening long pauses and removing filler candidates (source seconds)."""
    segs, fillers = manifest["segments"], manifest["fillers"]
    dropped = list(fillers) if remove_fillers is True else [f for f in fillers if f.get("id") in (remove_fillers or [])]
    # Speech minus the dropped fillers (a filler may be a whole region or an ASR word inside one), so every filler
    # becomes a forced cut whatever the pause length around it.
    speech = []
    for sg in segs:
        pieces = [(sg["start"], sg["end"])]
        for f in dropped:
            pieces = [q for a, b in pieces for q in (((a, b),) if f["end"] <= a or f["start"] >= b else
                                                    tuple(x for x in ((a, f["start"]), (f["end"], b)) if x[1] - x[0] > .04))]
        speech += [{"start": a, "end": b} for a, b in pieces if b - a > .04]
    speech.sort(key=lambda r: r["start"])
    t0, t1 = manifest["window"]
    if not speech:
        raise ValueError("No speech left to keep")
    keep, cur = [], max(t0, speech[0]["start"] - edge_s)
    for a, b in zip(speech, speech[1:]):
        gap = b["start"] - a["end"]
        forced = any(f["start"] < b["start"] and f["end"] > a["end"] for f in dropped)
        if forced:
            keep.append([cur, a["end"]])
            cur = b["start"]
        elif gap > max_pause_s:
            tail = min(.15, target_pause_s / 2)
            keep.append([cur, a["end"] + tail])
            cur = b["start"] - (target_pause_s - tail)
    keep.append([cur, min(t1, speech[-1]["end"] + edge_s)])
    keep = [[round(a, 3), round(b, 3)] for a, b in keep if b - a > .05]
    inside = lambda f: sum(max(0.0, min(b, f["end"]) - max(a, f["start"])) for a, b in keep) / max(1e-6, f["end"] - f["start"])
    return keep, sum(1 for f in dropped if inside(f) < .3)  # fillers actually cut, not merely marked


def _transcript_words(transcript, path):
    """Words of a transcribe manifest (or any JSON with "words"), checked to belong to this exact file."""
    data = json.loads(Path(transcript).read_text(encoding="utf-8"))
    sha = data.get("source_sha256")
    if sha and sha != sha256(Path(path).resolve(strict=True)):
        raise ValueError("transcript belongs to another file: transcribe this path")
    return [{"start": float(w["start"]), "end": float(w["end"]), "text": str(w["text"]).strip()} for w in data.get("words") or []
            if w.get("end", 0) > w.get("start", 0) and str(w.get("text", "")).strip()]


def map_words(words, tmap):
    """Source-timed words carried into a cut timeline: each word inside a kept range moves with it (time_map rows
    {src: [a, b], frames: [f0, f1]}); words cut out are dropped. Seconds in the new timeline, sorted."""
    out = []
    for row in tmap:
        a, b = row["src"]
        f0, f1 = row["frames"]
        for w in words:
            text = w.get("text", w.get("word", ""))
            inside = min(w["end"], b) - max(w["start"], a)
            if w["start"] >= a - .02 and w["start"] < b - .03 and inside >= .6 * max(.01, w["end"] - w["start"]):  # a word cut off is not shown
                s = f0 / 30 + max(0.0, w["start"] - a)
                e = min(f1 / 30, f0 / 30 + (w["end"] - a))
                if e - s >= .03:
                    out.append({"start": round(s, 3), "end": round(e, 3), "text": text})
    return sorted(out, key=lambda w: w["start"])


def condense(path, max_pause_s=.5, target_pause_s=.3, remove_fillers=True, cover="none", punch_scale=1.12, anchor=(.51, .31),
             profile="landscape", engine="remotion", title=None, clean_preset=None, dry_run=True, words=None, fill_room_tone=True,
             windows=None, transcript=None):
    """Tighten talking footage: pauses longer than max_pause_s become target_pause_s, filler candidates go, picture
    and sound cut together into a new editable project (one shot per kept range). cover="punch_in" alternates a
    punch (x punch_scale at the eye line) on every other shot to hide the jump cuts.
    windows: ordered [start, end] source selects; only speech inside them is kept, in THEIR order (the strongest line
    can open a short). transcript: a transcribe manifest of this file; its words time the pauses and are mapped into
    the new timeline (plan words + caption cues), so word_captions works without transcribing again."""
    if not .15 <= target_pause_s <= max_pause_s <= 3:
        raise ValueError("0.15 <= target_pause_s <= max_pause_s <= 3")
    if transcript:
        words = _transcript_words(transcript, path)
    r = read(path, words=words)
    m = json.loads(Path(r["manifest"]).read_text(encoding="utf-8"))
    keep, n_fill = plan_condense(m, max_pause_s, target_pause_s, remove_fillers)
    t0, t1 = m["window"]
    if windows:
        if any(len(w) != 2 or not t0 <= w[0] < w[1] <= t1 + .05 for w in windows):
            raise ValueError("windows are [start, end] source seconds inside the file")
        if words:  # a window edge never cuts a word: a word across the start is kept whole, one across the end is left out
            snapped = []
            for w0, w1 in windows:
                head = next((w for w in words if w["start"] < w0 < w["end"]), None)
                tail = next((w for w in words if w["start"] < w1 < w["end"]), None)
                w0 = head["start"] - .05 if head else w0
                w1 = tail["start"] - .05 if tail else w1
                if w1 > w0:
                    snapped.append([max(t0, w0), w1])
            windows = snapped or windows
        keep = [[max(a, w0), min(b, w1)] for w0, w1 in windows for a, b in keep if min(b, w1) - max(a, w0) >= 1 / 30]
        if not keep:
            raise ValueError("No speech inside the windows")
        t0, t1 = 0.0, sum(w1 - w0 for w0, w1 in windows)
    kept = sum(b - a for a, b in keep)
    out_pauses = []
    filler_starts = {f["start"] for f in m["fillers"]}
    segs = [s for s in m["segments"] if not (remove_fillers is True and s["start"] in filler_starts)]
    for a, b in zip(segs, segs[1:]):
        g = b["start"] - a["end"]
        out_pauses.append(min(g, target_pause_s) if g > max_pause_s else g)
    P = np.array([p for p in out_pauses if p >= .12]) if out_pauses else np.array([])
    summary = {"source_s": round(t1 - t0, 2), "kept_s": round(kept, 2), "removed_s": round(t1 - t0 - kept, 2), "cuts": len(keep) - 1, "fillers_removed": n_fill,
               "pauses_after": {"p90_s": round(float(np.percentile(P, 90)), 3) if len(P) else None, "max_s": round(float(P.max()), 3) if len(P) else None,
                                "per_min": round(len(P) / max(1e-6, kept) * 60, 1)},
               "first_cuts_src_s": [round(b, 2) for (a, b) in keep[:-1]][:10], "dialogue": {k: r[k] for k in ("speakers", "pause_stats")}}
    if dry_run:
        return {"dry_run": True, **summary, "keep_ranges": len(keep)}
    audio_path, cleaned = None, None
    if clean_preset:
        cleaned = clean(path, clean_preset)
        audio_path = cleaned["path"]
    fx = None
    if cover == "punch_in":
        fx = [None if i % 2 == 0 else [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1,
                                         "params": {"amount": round(punch_scale - 1, 3), "focus_x": anchor[0], "focus_y": anchor[1], "cut": True}}] for i in range(len(keep))]
    from . import agent
    made = agent.from_segments(path, keep, profile, engine, title, audio_path, 8, fx)
    tone = None
    if fill_room_tone and len(keep) > 1:
        # Room tone under every join (12 frames, 4-frame fades) hides the micro-fade where two takes meet.
        try:
            tone = room_tone(path, 2.0)
            pid = made["project_id"]
            p = agent.read(pid)
            imp = agent.import_media(pid, tone["path"], "room tone (sampled)", "decoration", True, p["revision"])
            joins = [s_["end_frame"] for s_ in p["timeline"]["shots"][:-1]]
            clips = [{"id": f"roomtone-{k:03d}", "asset_id": imp["asset"]["id"], "start_frame": max(0, j - 6), "end_frame": j + 6, "source_start": round((k % 8) * .2, 2),
                      "volume": 1.0, "fade_in": .13, "fade_out": .13, "duck_under_voice": False, "role": "ambience"} for k, j in enumerate(joins)]
            rev = imp["revision"]
            for i in range(0, len(clips), 90):
                rev = agent.patch(pid, rev, [{"op": "upsert_audio", "audio": c} for c in clips[i:i + 90]])["revision"]
            tone = {**{k: tone[k] for k in ("level_db", "floor_db", "loop_correlation")}, "clips": len(clips)}
        except ValueError as e:
            tone = {"skipped": str(e)[:120]}
    timed = None
    if words:  # carry the measured words into the new timeline: word_captions can run at once
        pid = made["project_id"]
        tm = json.loads(Path(made["time_map"]).read_text(encoding="utf-8"))["map"]
        moved = map_words(words, tm)
        if moved:
            from .audio import group_words
            cues = [c for c in group_words(moved, max_words=7 if profile == "vertical" else 9)]
            store.write_json(store.folder(pid) / "plan/words.json", {"method": "asr_words_mapped_through_cuts", "words": moved, "cues": cues})
            p = agent.read(pid)
            agent.patch(pid, p["revision"], [{"op": "replace_cues", "cues": [{k: c[k] for k in ("start", "end", "text")} for c in cues]}])
            timed = {"words": len(moved), "cues": len(cues)}
    return {**summary, **made, **({"room_tone": tone} if tone else {}), **({"clean": {"delta": cleaned["delta"], "path": cleaned["path"]}} if cleaned else {}),
            **({"captions_timing": timed} if timed else {}),
            "next": "snapshot the joins; " + ("word_captions can use the mapped words; " if timed else "transcribe the new voice for captions; ")
                    + "time_map maps source seconds to new frames."}


PRESETS = {"light": dict(nr=10, mud=-2, presence=2, hpf=90, deess=.3), "medium": dict(nr=16, mud=-3, presence=3, hpf=100, deess=.4),
           "strong": dict(nr=22, mud=-5, presence=4, hpf=120, deess=.5)}


def _chain(prof, P, expander=None):
    f = [f"highpass=f={P['hpf']}:poles=2"]
    if prof["hum"]:
        base = 50 if prof["hum_db_over_neighbours"]["50"] >= prof["hum_db_over_neighbours"]["60"] else 60
        f += [f"bandreject=f={base * k}:width_type=h:width=4" for k in (1, 2, 3)]
    nf = int(min(-20, max(-80, prof["floor_db"])))
    f.append(f"afftdn=nr={P['nr']}:nf={nf}:tn=1")
    f.append(f"equalizer=f=350:t=q:w=1:g={P['mud']}")
    f.append(f"equalizer=f=3500:t=q:w=1:g={P['presence']}")
    f.append(f"deesser=i={P['deess']}:m=0.5:f=0.5")
    f.append("acompressor=threshold=-23dB:ratio=2.5:attack=7:release=85:knee=4:makeup=1.26")
    if expander:
        thr = 10 ** ((prof["floor_db"] + expander["above_floor_db"]) / 20)
        f.append(f"agate=threshold={thr:.5f}:ratio={expander['ratio']}:range={10 ** (-expander['range_db'] / 20):.4f}:attack=10:release=120")
    return ",".join(f)


def clean(path, preset="auto", start=0.0, end=None):
    """Dialogue cleanup with before/after measurement: HPF, de-hum (when hum is measured), spectral denoise at the
    measured floor, mud cut, presence lift (at most +4 dB), de-ess, 2.5:1 compression; an expander is added when the
    floor rose more than speech. Returns the cleaned WAV and the deltas (floor, speech, SNR, hum, sibilance, bands)."""
    source = Path(path).resolve(strict=True)
    before = profile(source, start, end)
    if preset == "auto":
        preset = "strong" if before["snr_db"] < 20 else "medium" if before["snr_db"] < 30 else "light"
    if preset not in PRESETS:
        raise ValueError("preset auto|light|medium|strong")
    out = store.DATA / "audio-clean" / uuid.uuid4().hex[:12]
    out.mkdir(parents=True, exist_ok=True)
    target = out / "dialogue-clean.wav"
    attempts = [None, {"above_floor_db": 8, "ratio": 2, "range_db": 8}, {"above_floor_db": 10, "ratio": 3, "range_db": 12}]
    for exp in attempts:
        af = _chain(before, PRESETS[preset], exp)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", str(start), *(["-t", str(end - start)] if end else []), "-i", str(source), "-vn", "-af", af,
                        "-ar", "48000", "-ac", "1", str(target)], check=True, timeout=1200)
        after = profile(target)
        d = compare(before, after)
        if not any("floor" in w for w in d["warnings"]):
            break
    store.write_json(out / "clean.json", {"source": str(source), "preset": preset, "filters": af, "before": before, "after": after, "delta": d})
    return {"path": str(target), "preset": preset, "filters": af, "delta": d, "after": {k: after[k] for k in ("floor_db", "speech_db", "snr_db", "lufs")},
            "manifest": str(out / "clean.json")}


# ---------------------------------------------------------------- room tone
def room_tone(path, seconds=10.0, min_len=.5):
    """Sample the recording's own room tone: the longest stretch ≥ min_len that stays within ±3 dB of the noise floor
    (no speech), looped with 120 ms equal-power crossfades to `seconds`. Returns the WAV and its level."""
    x = _audio(path, 0, None, 48000)
    hop = 960  # 20 ms
    n = len(x) // hop
    db = 10 * np.log10((x[: n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    floor = float(np.percentile(db, 5))
    quiet = np.abs(db - floor) <= 3
    best, i = (0, 0), 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if j - i > best[1] - best[0]:
                best = (i, j)
            i = j
        else:
            i += 1
    if (best[1] - best[0]) * hop / 48000 < min_len:
        raise ValueError("No stretch of room tone ≥ 0.5 s near the noise floor; record 5 s of silence on set")
    seg = x[best[0] * hop + 480: best[1] * hop - 480].astype(np.float64)
    xf = min(int(.12 * 48000), len(seg) // 3)
    fade_in, fade_out = np.sqrt(np.linspace(0, 1, xf)), np.sqrt(np.linspace(1, 0, xf))
    out, need = seg.copy(), int(seconds * 48000)
    while len(out) < need:
        nxt = seg.copy()
        out[-xf:] = out[-xf:] * fade_out + nxt[:xf] * fade_in
        out = np.concatenate([out, nxt[xf:]])
    out = out[:need]
    folder = store.DATA / "audio-clean" / uuid.uuid4().hex[:12]
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "room-tone.wav"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "f64le", "-ar", "48000", "-ac", "1", "-i", "-", "-c:a", "pcm_s16le", str(target)], input=out.tobytes(), check=True)
    lvl = 10 * np.log10((out ** 2).mean() + 1e-12)
    # Loop seam check: correlation of the loop with itself one segment later (low = no audible repetition pattern).
    seglen = len(seg) - xf
    corr = float(np.corrcoef(out[: min(seglen, len(out) - seglen)], out[seglen: seglen + min(seglen, len(out) - seglen)])[0, 1]) if len(out) > 2 * seglen else None
    return {"path": str(target), "source_window_s": [round(best[0] * hop / 48000, 2), round(best[1] * hop / 48000, 2)], "level_db": round(float(lvl), 1),
            "floor_db": round(floor, 1), "seconds": round(len(out) / 48000, 2), "loop_correlation": None if corr is None else round(corr, 3)}
