"""Beat tracking and beat-locked cutting.

Onset envelope (log-magnitude spectral flux) → tempo by autocorrelation with a log-normal prior around 120 BPM →
beats by dynamic programming (Ellis 2007: reward onset strength, penalise deviation from the beat period) →
downbeat phase from low-frequency energy, assuming 4/4. Then shot boundaries snap to the nearest beat (optionally a
few frames early, as editors often cut just before the hit) within a tolerance; boundaries without a nearby beat or
without source handles stay where they are. Measurements, not a judgement of the music.
"""
import math
import os
import subprocess
from pathlib import Path
import numpy as np
from .media import FFMPEG

SR, HOP, NFFT = 22050, 512, 2048
FPS = 30


def _audio(path, start, end):
    cmd = [FFMPEG, "-v", "error", "-ss", str(start), *(["-t", str(end - start)] if end else []), "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    x = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32)
    if len(x) < SR:
        raise ValueError("Need at least 1 s of audio")
    return x


def _spec(x):
    n = 1 + (len(x) - NFFT) // HOP
    out = np.empty((n, NFFT // 2 + 1), np.float32)
    win = np.hanning(NFFT).astype(np.float32)
    for a in range(0, n, 2048):  # chunked: a 4-minute song would otherwise allocate ~0.5 GB at once
        idx = np.arange(NFFT)[None, :] + HOP * np.arange(a, min(n, a + 2048))[:, None]
        out[a:a + len(idx)] = np.abs(np.fft.rfft(x[idx] * win, axis=1))
    return out


def _mel_bank(n_mels=64, fmin=30.0, fmax=11000.0):
    mel = lambda f: 2595 * np.log10(1 + f / 700)
    inv = lambda m: 700 * (10 ** (m / 2595) - 1)
    pts = inv(np.linspace(mel(fmin), mel(fmax), n_mels + 2))
    f = np.arange(NFFT // 2 + 1) * SR / NFFT
    fb = np.zeros((n_mels, len(f)), np.float32)
    for i in range(n_mels):
        a, c, b = pts[i], pts[i + 1], pts[i + 2]
        fb[i] = np.maximum(0, np.minimum((f - a) / (c - a), (b - f) / (b - c)))
    return fb, pts[1:-1]


MEL, MEL_HZ = _mel_bank()


def onset_envelope(x, spec=None):
    """Onset strength: normalised linear-bin log flux + 64-band mel flux (dB, 80 dB floor) + half-weight < 150 Hz flux.
    Linear flux alone tracks real pop mixes but lets bright off-beat hi-hats outvote kick and snare; the mel and kick
    terms keep the tracker on the beat (synthetic backbeat song) while a measured pop montage stays at its 95 BPM.
    Also returns the < 150 Hz flux used for the downbeat phase."""
    spec = _spec(x) if spec is None else spec
    logs = np.log1p(100 * spec)
    lin = np.maximum(logs[1:] - logs[:-1], 0).sum(axis=1)
    m = (spec.astype(np.float32) ** 2) @ MEL.T
    db = 10 * np.log10(m + 1e-10)
    db = np.maximum(db, db.max() - 80)
    flux = np.maximum(db[1:] - db[:-1], 0)
    mel = flux.mean(axis=1)
    lowf = flux[:, MEL_HZ < 150].mean(axis=1)
    env = np.concatenate([[0], lin / (lin.std() + 1e-9) + mel / (mel.std() + 1e-9) + .5 * lowf / (lowf.std() + 1e-9)])
    low = np.concatenate([[0], lowf])  # kick/bass
    k = 16
    env = np.maximum(env - np.convolve(env, np.ones(k) / k, mode="same"), 0)
    env /= env.std() + 1e-9
    return env, low


def tempo(env, lo=60, hi=200):
    """Tempo by autocorrelation of the (lightly smoothed) onset envelope with a log-normal prior around 120 BPM.
    The peak lag is refined parabolically so a beat period between two envelope frames is not split across them.
    Returns bpm, period (frames, fractional), periodicity (normalised autocorrelation at the period: ≥ .22 clear pulse,
    < .15 weak, measured on pop montages vs orchestral trailer beds) and tempo_clarity (peak over the runner-up lag)."""
    fr = SR / HOP
    lags = np.arange(max(2, int(fr * 60 / hi)), int(fr * 60 / lo) + 2)
    lags = lags[lags < len(env) - 1]
    if not len(lags):
        raise ValueError("Audio too short for the tempo range")
    es = np.convolve(env, np.array([1, 4, 6, 4, 1]) / 16, mode="same")
    e = es - es.mean()
    ac = np.array([np.dot(e[:-l], e[l:]) for l in lags]) / (np.dot(e, e) + 1e-9)
    bpm = 60 * fr / lags
    prior = np.exp(-.5 * (np.log2(bpm / 120) / .9) ** 2)
    score = ac * prior
    i = int(np.argmax(score))
    lag, peak = float(lags[i]), float(ac[i])
    if 0 < i < len(ac) - 1:
        a, c, b = ac[i - 1], ac[i], ac[i + 1]
        den = a - 2 * c + b
        if den < 0:
            d = float(np.clip(.5 * (a - b) / den, -.5, .5))
            lag, peak = lag + d, float(c - .25 * (a - b) * d)
    second = np.sort(score)[-2] if len(score) > 1 else 0
    return float(60 * fr / lag), lag, peak, float(score[i] / (abs(second) + 1e-9))


def track_beats(env, period, tightness=100.0):
    n = len(env)
    score = env.astype(float).copy()
    back = np.full(n, -1)
    p = int(round(period))
    for t in range(n):
        lo, hi = t - 2 * p, t - max(1, p // 2)
        if hi < 0:
            continue
        lo = max(0, lo)
        prev = np.arange(lo, hi + 1)
        pen = -tightness * np.log((t - prev) / period) ** 2
        cand = score[prev] + pen
        j = int(np.argmax(cand))
        if cand[j] > 0:
            score[t] = env[t] + cand[j]
            back[t] = prev[j]
    tail = max(0, n - p)
    t = tail + int(np.argmax(score[tail:]))
    beats = []
    while t >= 0:
        beats.append(t)
        t = back[t]
    return np.array(beats[::-1])


# Envelope frame t is the flux between windows starting at (t-1)*HOP and t*HOP. Log compression makes the flux peak as
# soon as an attack enters the window's leading taper, so the peak frame starts ~1600 samples before the attack.
# Calibrated on synthetic click and kick tracks at 87/100/128 BPM (tests/test_music_timing.py): mean error within ±1 ms, sd ≈ 3 ms.
ONSET_LATENCY_S = .072


def refine(env, b):
    """Sub-hop beat positions: parabolic interpolation of the onset peak at (or next to) each tracked frame."""
    out = []
    for t in b:
        t = int(t)
        lo, hi = max(1, t - 1), min(len(env) - 2, t + 1)
        if hi >= lo:
            t = lo + int(np.argmax(env[lo:hi + 1]))  # the DP grid can sit one frame off the local onset peak
        d = 0.0
        if 0 < t < len(env) - 1:
            a, c, e = env[t - 1], env[t], env[t + 1]
            den = a - 2 * c + e
            if den < 0:
                d = float(np.clip(.5 * (a - e) / den, -.5, .5))
        out.append(t + d)
    return np.array(out)


_BT = {}


def _checkpoint():
    """Where the Beat This! checkpoint is: EDITVIDEO_BEAT_CHECKPOINT (a copy fetched by hand), else the store's models."""
    from . import store
    return Path(os.environ.get("EDITVIDEO_BEAT_CHECKPOINT") or store.models_root("beat_this") / "beat_this" / "final0.ckpt")


def _beat_ready():
    """Beat This! can run without fetching or loading anything: the package is installed, its checkpoint is on disk,
    and it is not switched off (EDITVIDEO_BEAT_TRACKER=dp). Cheap: the analysis cache key asks it."""
    import importlib.util
    if os.environ.get("EDITVIDEO_BEAT_TRACKER", "auto") == "dp" or _BT.get("bad"):
        return False
    return importlib.util.find_spec("beat_this") is not None and _checkpoint().is_file()


def _beat_this():
    """Beat This! (Foscarin, Schlüter, Widmer, ISMIR 2024; MIT code and weights): beats and downbeats from a
    transformer, no DBN, any metre. Loaded once when its checkpoint is on disk; nothing is fetched here (an analysis
    inside a tool call must not wait on a host: fetch_beat_model does that). None: the DP tracker stands in."""
    if not _beat_ready():
        return None
    if _BT.get("m") is None:
        try:
            from beat_this.inference import Audio2Beats
            _BT["m"] = Audio2Beats(checkpoint_path=str(_checkpoint()), device=os.environ.get("EDITVIDEO_BEAT_DEVICE", "cpu"), dbn=False)
        except Exception as e:  # a checkpoint that will not load is set aside, not retried on every analysis
            _BT.update(m=None, bad=True, why=f"{type(e).__name__}: {str(e)[:160]}")
    return _BT.get("m")


def fetch_beat_model(timeout=120):
    """Fetch Beat This!'s final0 checkpoint into the store's models (once). Checked before it is kept: a size that can
    be a checkpoint and a torch load of its weights; anything else is set aside as .bad. Returns {"path", "bytes"}."""
    import urllib.request
    import torch
    from beat_this.inference import CHECKPOINT_URL
    ck = _checkpoint()
    if ck.is_file():
        return {"path": str(ck), "bytes": ck.stat().st_size, "fetched": False}
    ck.parent.mkdir(parents=True, exist_ok=True)
    part = ck.with_suffix(".part")
    with urllib.request.urlopen(f"{CHECKPOINT_URL}/final0.ckpt", timeout=timeout) as r, open(part, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    try:
        if part.stat().st_size < 1_000_000:
            raise ValueError(f"{part.stat().st_size} bytes is not a checkpoint")
        torch.load(part, map_location="cpu", weights_only=True)
    except Exception:
        part.replace(ck.with_suffix(".bad"))
        raise
    part.replace(ck)
    _BT.pop("bad", None)
    return {"path": str(ck), "bytes": ck.stat().st_size, "fetched": True}


def _neural(x, start):
    """(beats, downbeats) in seconds from Beat This!, or None."""
    m = _beat_this()
    if m is None:
        return None
    b, d = m(x, SR)
    b, d = np.asarray(b, float) + start, np.asarray(d, float) + start
    return (b, d) if len(b) >= 4 else None


def _bar_positions(bt, down):
    """Each beat's place in its bar (0 = downbeat) from explicit downbeats; the beats before the first downbeat (a
    pickup) count back from it in the piece's usual metre."""
    bt, down = np.asarray(bt, float), np.asarray(down, float)
    k = np.searchsorted(down, bt + .07, side="right") - 1
    idx = np.searchsorted(bt, down - .07)
    meter = int(round(float(np.median(np.diff(idx))))) if len(idx) > 1 else 4
    meter = max(2, min(12, meter))
    first = int(idx[0]) if len(idx) else 0
    return [int(i - idx[j]) if j >= 0 else int((meter - (first - i)) % meter) for i, j in enumerate(k)]


def _phase(bt, down):
    """Index (0-3) of the first downbeat among the beats: the bar phase the 4/4 code paths read."""
    if not len(down) or not len(bt):
        return 0
    return int(np.argmin(np.abs(bt - down[0]))) % 4


def _range(bpm_range):
    lo, hi = bpm_range or (60, 200)
    if not 30 <= lo < hi <= 300:
        raise ValueError("bpm_range is [low, high] within 30..300")
    return lo, hi


def beats(path, start=0.0, end=None, bpm_range=None):
    x = _audio(path, start, end)
    env, low = onset_envelope(x)
    bpm, period, strength, clarity = tempo(env, *_range(bpm_range))
    b = track_beats(env, period)
    fr = SR / HOP
    times = start + refine(env, b) / fr + ONSET_LATENCY_S
    if len(times) >= 8:
        bpm = 60 / float(np.median(np.diff(times)))
    phase = max(range(4), key=lambda ph: low[b[ph::4]].sum() if len(b) > ph else -1) if len(b) >= 4 else 0
    down = times[phase::4]
    nn = _neural(x, start) if not bpm_range else None  # a pinned tempo range is the DP tracker's to honour
    if nn:
        times, down = nn
        bpm = 60 / float(np.median(np.diff(times)))
        period = 60 / bpm * fr                          # the period it reports is the network's, like its bpm
    return {"tracker": "beat_this" if nn else "dp", "bpm": round(bpm, 2), "beat_period_s": round(period / fr, 4), "beats": [round(float(t), 4) for t in times],
            "downbeats": [round(float(t), 4) for t in down], "periodicity": round(strength, 3), "tempo_clarity": round(clarity, 3),
            "pulse": "clear" if strength >= .22 else "weak" if strength < .15 else "moderate", "alternatives_bpm": [round(bpm / 2, 2), round(bpm * 2, 2)],
            "window": [start, round(start + len(x) / SR, 3)],
            "method": "Spectral-flux onsets, autocorrelation tempo with a 120 BPM prior, dynamic-programming beat tracking (Ellis 2007), "
                      "downbeat phase from <150 Hz energy assuming 4/4; beat times calibrated to the attack (+-2 ms on click tracks). "
                      "Half/double-time ambiguity is common: check bpm against the music and pass bpm_range to pin it."}


def _rms_db(x, hop=441, win=1102):
    """Short-term RMS level in dBFS: 20 ms hop, 50 ms window."""
    n = max(1, 1 + (len(x) - win) // hop)
    c = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    k = np.arange(n) * hop
    return 10 * np.log10((c[k + win] - c[k]) / win + 1e-12), hop / SR, win / SR


def _band_feats(spec, nb=24):
    """Log energies in nb log-spaced bands, 60 Hz to 10 kHz (timbre/arrangement descriptor per STFT frame)."""
    edges = np.geomspace(60, 10000, nb + 1) / (SR / NFFT)
    p = spec.astype(np.float64) ** 2
    return np.stack([np.log10(p[:, int(a):max(int(a) + 1, int(b))].sum(1) + 1e-9) for a, b in zip(edges[:-1], edges[1:])], 1)


def _cache_key(path, start, end, bpm_range):
    import hashlib
    st = Path(path).stat()
    raw = f"{Path(path).resolve()}|{st.st_size}|{st.st_mtime_ns}|{start}|{end}|{bpm_range}|v4|{'nn' if _beat_ready() and not bpm_range else 'dp'}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def _analyse(path, start=0.0, end=None, bpm_range=None):
    """Beat/loudness/timbre analysis, cached on disk per (file, mtime, window, bpm_range): snap, fit, trailer plan and
    audit reuse one analysis instead of decoding and re-tracking the same track."""
    from . import store
    key = _cache_key(path, start, end, bpm_range)
    cdir = store.DATA / "cache" / "music"
    cf = cdir / f"{key}.npz"
    if cf.exists():
        try:
            z = np.load(cf, allow_pickle=False)
            a = {k: z[k] for k in z.files}
            for k in ("fr", "bpm", "period", "strength", "clarity", "hop_s", "win_s", "start", "end"):
                a[k] = float(a[k])
            a["phase"] = int(a["phase"])
            a["tracker"] = str(a.get("tracker", "dp"))
            return a
        except Exception:
            pass
    a = _analyse_raw(path, start, end, bpm_range)
    try:
        cdir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cf, **{k: np.asarray(v) for k, v in a.items() if k != "x"})
    except Exception:
        pass
    return a


def _analyse_raw(path, start=0.0, end=None, bpm_range=None):
    x = _audio(path, start, end)
    spec = _spec(x)
    env, low = onset_envelope(x, spec)
    bpm, period, strength, clarity = tempo(env, *_range(bpm_range))
    b = track_beats(env, period)
    fr = SR / HOP
    bt = start + refine(env, b) / fr + ONSET_LATENCY_S
    if len(bt) >= 8:
        bpm = 60 / float(np.median(np.diff(bt)))
    phase = max(range(4), key=lambda ph: low[b[ph::4]].sum() if len(b) > ph else -1) if len(b) >= 4 else 0
    down, tracker = bt[phase::4], "dp"
    nn = _neural(x, start) if not bpm_range else None
    if nn:  # Beat This!'s beats and its own downbeats (any metre); the DP tracker's periodicity still says how clear the pulse is
        bt, down, tracker = nn[0], nn[1], "beat_this"
        bpm = 60 / float(np.median(np.diff(bt)))
        period = 60 / bpm * fr
        phase = _phase(bt, down)
    db, hop_s, win_s = _rms_db(x)
    return dict(env=env, fr=fr, bpm=bpm, period=period, strength=strength, clarity=clarity, beats=bt, phase=phase, downbeats=down, tracker=tracker,
                db=db, hop_s=hop_s, win_s=win_s, start=start, end=start + len(x) / SR, feats=_band_feats(spec).astype(np.float32))


def _hits(a, rise_db=15.0, floor_db=-30.0):
    """Sudden level jumps (impacts, drops, a hit out of silence): the level 0-100 ms after exceeds the median of the
    preceding 300 ms by rise_db. Timed on the nearest spectral-flux peak (same calibration as the beats)."""
    db, h = a["db"], a["hop_s"]
    out, last = [], -1e9
    for i in range(16, len(db) - 5):
        pre = float(np.median(db[i - 16:i - 1]))
        post = float(db[i:i + 5].max())
        if post - pre >= rise_db and post > floor_db:
            t_est = a["start"] + i * h + a["win_s"]
            if t_est - last < .25:
                continue
            c = int(round((t_est - a["start"] - ONSET_LATENCY_S) * a["fr"]))
            lo, hi = max(0, c - 4), min(len(a["env"]), c + 3)
            k = lo + int(np.argmax(a["env"][lo:hi])) if hi > lo else c
            t = a["start"] + k / a["fr"] + ONSET_LATENCY_S
            out.append({"time": round(t, 3), "rise_db": round(post - pre, 1), "level_db": round(post, 1)})
            last = t_est
    return out


def _quiet(a, below_db=-35.0, min_s=.25):
    db, h = a["db"], a["hop_s"]
    q, out, i = db < below_db, [], 0
    while i < len(q):
        if q[i]:
            j = i
            while j < len(q) and q[j]:
                j += 1
            if (j - i) * h >= min_s:
                out.append({"start": round(a["start"] + i * h + a["win_s"] / 2, 3), "end": round(a["start"] + j * h + a["win_s"] / 2, 3),
                            "level_db": round(float(db[i:j].mean()), 1), "edge": i == 0 or j == len(q)})
            i = j
        else:
            i += 1
    return out


def _bar_feats(a, bars):
    F = a["feats"]
    tf = a["start"] + (np.arange(len(F)) * HOP + NFFT / 2) / SR
    out = []
    for k in range(len(bars) - 1):
        m = (tf >= bars[k]) & (tf < bars[k + 1])
        out.append(F[m].mean(0) if m.any() else F[min(len(F) - 1, max(0, int((bars[k] - a["start"]) * a["fr"])))])
    return np.array(out) if out else np.zeros((0, F.shape[1]))


def summary(st, path=None):
    """Context-light view of a structure() result: counts, phrase lines, sections, hits and inner gaps (the full arrays
    — every beat, its bar position, per-bar loudness — are written to disk)."""
    out = {k: st[k] for k in ("bpm", "beat_period_s", "periodicity", "pulse", "recommended_snap", "alternatives_bpm", "sections", "window")}
    out.update(beats=len(st["beats"]), bars=len(st["bar_starts"]), first_downbeat=st["downbeats"][0] if st["downbeats"] else None,
               phrases_4=st["phrases_4"], hits=st["hits"][:40], quiet=[q for q in st["quiet"] if not q["edge"]][:30])
    if path:
        out["full_path"] = str(path)
    return out


def structure(path, start=0.0, end=None, bpm_range=None, _a=None):
    """Bars, 4/8-bar phrases, sections (intro/build/peak/breakdown/body/outro), hits and quiet gaps.

    Section boundaries combine timbre novelty (24-band spectra, 2 bars either side), loudness steps and a phrase prior
    (boundaries on 4/8-bar lines score higher). Labels come from relative loudness and its trend, not genre knowledge.
    tempo_clarity < 1.3 means a weak pulse (orchestral/ambient beds): cut to hits, section changes and gaps instead of beats."""
    a = _a or _analyse(path, start, end, bpm_range)
    bt, ph = a["beats"], a["phase"]
    down = bt[ph::4]
    beat_in_bar = [int((i - ph) % 4) for i in range(len(bt))]
    if str(a.get("tracker")) == "beat_this" and len(a.get("downbeats", [])) >= 2:  # the network's own bars (3/4 stays 3/4)
        down = np.asarray(a["downbeats"], float)
        beat_in_bar = _bar_positions(bt, down)
    bars = list(down)
    if len(bars) and bars[-1] < a["end"] - .05:
        bars.append(a["end"])  # closing edge
    nb = max(0, len(bars) - 1)
    db, h = a["db"], a["hop_s"]

    def lvl(t0, t1):
        i0, i1 = int(max(0, (t0 - a["start"]) / h)), int(max(1, (t1 - a["start"]) / h))
        seg = db[i0:max(i0 + 1, i1)]
        return float(10 * np.log10(np.mean(10 ** (seg / 10)) + 1e-12)) if len(seg) else -120.0
    bar_db = np.array([lvl(bars[k], bars[k + 1]) for k in range(nb)])
    bf = _bar_feats(a, bars)
    sections = []
    if nb >= 4:
        z = (bf - bf.mean(0)) / (bf.std(0) + 1e-6)
        nov, step = np.zeros(nb), np.zeros(nb)
        for k in range(2, nb - 1):
            A, B = z[max(0, k - 2):k].mean(0), z[k:k + 2].mean(0)
            nov[k] = np.linalg.norm(A - B) / math.sqrt(z.shape[1])
            step[k] = bar_db[k:k + 2].mean() - bar_db[max(0, k - 2):k].mean()
        med = float(np.median(nov[2:nb - 1])) + 1e-6 if nb > 3 else 1.0
        score = .6 * nov / med + np.maximum(0, np.abs(step) - 2) / 4 + np.array([.5 * (k % 4 == 0) + .3 * (k % 8 == 0) for k in range(nb)])
        cand = sorted([k for k in range(2, nb - 1) if score[k] >= 1.6 or abs(step[k]) >= 6], key=lambda k: -score[k])
        cuts = []
        for k in cand:
            if all(abs(k - c) >= 4 for c in cuts):
                cuts.append(k)
        edges = [0, *sorted(cuts), nb]
        for i in range(len(edges) - 1):
            k0, k1 = edges[i], edges[i + 1]
            y = bar_db[k0:k1]
            slope = float(np.polyfit(np.arange(len(y)), y, 1)[0] * max(1, len(y) - 1)) if len(y) > 1 else 0.0
            sections.append({"start": round(float(bars[k0]), 3), "end": round(float(bars[k1]), 3), "bars": [k0, k1],
                             "loudness_db": round(lvl(bars[k0], bars[k1]), 1), "trend_db": round(slope, 1),
                             "entry_step_db": round(float(step[k0]), 1) if k0 else None, "novelty": round(float(score[k0]), 2) if k0 else None})
        top = max(s_["loudness_db"] for s_ in sections)
        seen_peak = False
        for i, s_ in enumerate(sections):
            nxt = sections[i + 1] if i + 1 < len(sections) else None
            if len(sections) == 1:
                lab = "body"
            elif s_["loudness_db"] >= top - 3:
                lab = "peak"
            elif i == 0:
                lab = "intro"
            elif i == len(sections) - 1 and (s_["loudness_db"] < sections[i - 1]["loudness_db"] - 2 or s_["trend_db"] < -4):
                lab = "outro"
            elif seen_peak and s_["loudness_db"] <= top - 6 and s_["trend_db"] < 3:
                lab = "breakdown"
            elif nxt and nxt["loudness_db"] >= top - 3 and (s_["trend_db"] >= 3 or (not seen_peak and s_["loudness_db"] < nxt["loudness_db"] - 3)):
                lab = "build"
            else:
                lab = "body"
            seen_peak = seen_peak or lab == "peak"
            s_["label"] = lab
    elif nb:
        sections = [{"start": round(float(bars[0]), 3), "end": round(float(bars[-1]), 3), "bars": [0, nb], "loudness_db": round(lvl(bars[0], bars[-1]), 1),
                     "trend_db": 0.0, "entry_step_db": None, "novelty": None, "label": "body"}]
    pulse = "clear" if a["strength"] >= .22 else "weak" if a["strength"] < .15 else "moderate"
    return {"tracker": str(a.get("tracker", "dp")), "bpm": round(a["bpm"], 2), "beat_period_s": round(a["period"] / a["fr"], 4), "periodicity": round(a["strength"], 3),
            "tempo_clarity": round(a["clarity"], 3), "pulse": pulse, "recommended_snap": "hits" if pulse == "weak" else "priority",
            "alternatives_bpm": [round(a["bpm"] / 2, 2), round(a["bpm"] * 2, 2)],
            "beats": [round(float(t), 4) for t in bt], "beat_in_bar": beat_in_bar, "downbeats": [round(float(t), 4) for t in down],
            "bar_starts": [round(float(t), 4) for t in bars[:nb]], "bar_loudness_db": [round(float(v), 1) for v in bar_db],
            "phrases_4": [round(float(bars[k]), 4) for k in range(0, nb, 4)], "phrases_8": [round(float(bars[k]), 4) for k in range(0, nb, 8)],
            "sections": sections, "hits": _hits(a), "quiet": _quiet(a), "window": [a["start"], round(a["end"], 3)],
            "method": "Beats and downbeats from Beat This! (any metre) when installed, else a calibrated DP tracker (bars assume 4/4 from "
                      "low-frequency downbeat phase); sections from 24-band timbre novelty + "
                      "loudness steps + 4/8-bar prior; hits = >=15 dB rise over the previous 300 ms; quiet = below -35 dBFS for >=0.25 s. "
                      "Labels describe relative energy, not genre form; listen to the boundaries before relying on them."}


def fit(path, target_s, start=0.0, end=None, ending="natural", crossfade_beats=.5, bpm_range=None, max_joins=1, exact=False):
    """Plan a music edit to target_s seconds by removing (or repeating) whole bars between two similar-sounding bar
    lines, so the jump is musically invisible, then ending naturally, on a one-bar fade, or on a hit.

    max_joins > 1 (natural ending): the cheapest path through the bars with up to that many joins, at least a phrase
    (4 bars) between two (Scalable Music, Eurographics 2013: invisible jumps between similar bars, a length-constrained
    shortest path). exact: the plan is played 3 % faster or slower at most (playback_rate, pitch kept) so it lands on
    target_s to the frame; beyond 3 % it is left as it is and said so.

    Returns segments (source in/out, timeline offset, fades) that become AudioClips. Crossfades are crossfade_beats long,
    centred on the bar line, so the downbeat after the join lands exactly where the bar before it would have ended."""
    if ending not in ("natural", "fade", "hit"):
        raise ValueError("ending is natural, fade or hit")
    if not 0 <= crossfade_beats <= 2:
        raise ValueError("crossfade_beats is 0..2")
    a = _analyse(path, start, end, bpm_range)
    st = structure(path, start, end, _a=a)
    bars = [*st["bar_starts"], a["end"]]
    nb = len(bars) - 1
    if nb < 4:
        raise ValueError("Need at least 4 bars of music to edit on bar lines")
    bar_len = float(np.median(np.diff(bars[:-1]))) if nb > 2 else float(bars[1] - bars[0])
    beat = st["beat_period_s"]
    xf = crossfade_beats * beat
    total = a["end"] - a["start"]
    if target_s < 2 * bar_len:
        raise ValueError("target is shorter than two bars")
    z = _bar_feats(a, bars)
    z = (z - z.mean(0)) / (z.std(0) + 1e-6)
    lv = np.array(st["bar_loudness_db"])

    def join_cost(i, j):  # play up to bar line i, continue from bar line j: bars i/j and i-1/j-1 should sound alike
        d = np.linalg.norm(z[min(i, nb - 1)] - z[min(j, nb - 1)]) + .5 * np.linalg.norm(z[i - 1] - z[j - 1])
        d = d / math.sqrt(z.shape[1]) + abs(lv[min(i, nb - 1)] - lv[min(j, nb - 1)]) / 6
        return d + (0 if i % 4 == 0 and j % 4 == 0 else .35 if i % 2 == 0 and j % 2 == 0 else .8)
    plans = []
    if ending == "natural":
        for i in range(1, nb):
            for j in range(1, nb):
                if i == j:
                    continue
                length = total - (bars[j] - bars[i])
                if abs(length - target_s) <= bar_len * 1.01:
                    plans.append((join_cost(i, j) + abs(length - target_s) / bar_len * .3, i, j, length))
    if ending != "natural" or not plans:
        if target_s >= total:
            raise ValueError("No bar-aligned edit reaches the target within one bar; the track is shorter than the target")
        # Keep the opening, cut at the bar line nearest the target (fade) or just after the last strong hit before it (hit).
        k = int(np.argmin([abs((bars[k] - a["start"]) - target_s) for k in range(1, nb + 1)])) + 1
        out_t, fade = bars[k], bar_len
        if ending == "hit":
            hits = [hh["time"] for hh in st["hits"] if a["start"] + bar_len < hh["time"] <= a["start"] + target_s + .25 * bar_len]
            out_t = (max(hits) + .9 * beat) if hits else bars[k]
            fade = min(.35, beat)
        out_t = float(min(a["end"], out_t))
        seg = [{"source_start": round(a["start"], 4), "source_end": round(out_t, 4), "at_s": 0.0, "fade_in": 0.0, "fade_out": round(fade, 3)}]
        return {"segments": seg, "length_s": round(out_t - a["start"], 3), "target_s": target_s, "ending": "hit" if ending == "hit" else "fade",
                "join": None, "bpm": st["bpm"], "sections": st["sections"],
                "note": "Ends on the last hit before the target with a short tail; a stinger or design_sound braam can finish it." if ending == "hit"
                        else "Trimmed at the bar line nearest the target with a one-bar fade."}
    if max_joins > 1:
        best = _join_path(bars, join_cost, target_s, bar_len, max_joins, pickup=max(0.0, bars[0] - a["start"]))
        if best:
            cost, runs = best
            plan = _runs_plan(runs, bars, a, xf, join_cost)
            plan.update(target_s=target_s, ending="natural", bpm=st["bpm"], sections=st["sections"], cost=round(float(cost), 3),
                        note="Each join's cost: < 1 is usually seamless, > 1.5 may be audible. Listen across every join.")
            return _exact(plan, target_s) if exact else plan
    cost, i, j, length = min(plans)
    t_i, t_j = bars[i], bars[j]
    segs = [{"source_start": round(a["start"], 4), "source_end": round(t_i + xf / 2, 4), "at_s": 0.0, "fade_in": 0.0, "fade_out": round(xf, 3)},
            {"source_start": round(t_j - xf / 2, 4), "source_end": round(a["end"], 4), "at_s": round(t_i - a["start"] - xf / 2, 4), "fade_in": round(xf, 3), "fade_out": .15}]
    plan = {"segments": segs, "length_s": round(length, 3), "target_s": target_s, "ending": "natural",
            "join": {"from_bar": i, "to_bar": j, "from_s": round(t_i, 3), "to_s": round(t_j, 3), "cost": round(float(cost), 3),
                     ("removed_s" if j > i else "repeated_s"): round(abs(t_j - t_i), 3)},
            "bpm": st["bpm"], "sections": st["sections"],
            "note": "Join cost < 1 is usually seamless; > 1.5 may be audible (different arrangement or level). Listen across the join."}
    return _exact(plan, target_s) if exact else plan


def _join_path(bars, join_cost, target_s, bar_len, max_joins, min_run=4, k_best=6, penalty=.35, pickup=0.0):
    """(cost, [(first bar, end bar), ...]): from bar 0 to the track's end through whole bars, about target_s long,
    each join a jump from bar line i to bar line j among the k_best cheapest from i, at least min_run bars played
    between two joins, every join costing its dissimilarity plus a penalty (fewer joins win a tie). None if none fits."""
    nb = len(bars) - 1
    T = int(round((target_s - pickup) / bar_len))
    if T < 2 or nb < 2 * min_run:
        return None
    cand = {i: sorted((join_cost(i, j), j) for j in range(1, nb) if j != i)[:k_best] for i in range(min_run, nb)}
    INF = float("inf")
    cost, back = {(0, 0, min_run, 0): 0.0}, {}
    for u in range(T + 2):
        # joins at this length (they play nothing), then one bar played from every state
        for (k, uu, since, n), c in list(cost.items()):
            if uu != u or since < min_run or n >= max_joins or k not in cand:
                continue
            for jc, j in cand[k]:
                key = (j, u, 0, n + 1)
                if c + jc + penalty < cost.get(key, INF):
                    cost[key], back[key] = c + jc + penalty, (k, u, since, n)
        for (k, uu, since, n), c in list(cost.items()):
            if uu != u or k >= nb:
                continue
            key = (k + 1, u + 1, min(min_run, since + 1), n)
            if c < cost.get(key, INF):
                cost[key], back[key] = c, (k, u, since, n)
    best = None
    for key, c in cost.items():
        if key[0] != nb or abs(key[1] - T) > 1 or (key[3] and key[2] < min_run):  # after a join, a phrase at least before the end
            continue
        path, cur = [key], key
        while cur in back:
            cur = back[cur]
            path.append(cur)
        path.reverse()
        runs, s0 = [], 0
        for x, y in zip(path, path[1:]):
            if y[1] == x[1]:  # a join: the run so far ends at x's bar line, the next starts at y's
                runs.append((s0, x[0]))
                s0 = y[0]
        runs.append((s0, nb))
        length = sum(bars[e] - bars[s_] for s_, e in runs) + pickup
        score = c + abs(length - target_s) / bar_len * .3
        if best is None or score < best[0]:
            best = (score, runs)
    return best


def _runs_plan(runs, bars, a, xf, join_cost):
    """Segments for runs of bars: each join crossfaded over xf, centred on the bar line."""
    segs, at, joins = [], 0.0, []
    for k, (s_, e) in enumerate(runs):
        t0 = a["start"] if s_ == 0 else bars[s_]
        t1 = a["end"] if e == len(bars) - 1 else bars[e]
        src0 = t0 - (xf / 2 if k else 0)
        src1 = t1 + (xf / 2 if k < len(runs) - 1 else 0)
        segs.append({"source_start": round(src0, 4), "source_end": round(src1, 4), "at_s": round(at - (xf / 2 if k else 0), 4),
                     "fade_in": round(xf, 3) if k else 0.0, "fade_out": round(xf, 3) if k < len(runs) - 1 else .15})
        at += t1 - t0
        if k < len(runs) - 1:
            n_ = runs[k + 1][0]
            joins.append({"from_bar": e, "to_bar": n_, "from_s": round(bars[e], 3), "to_s": round(bars[n_], 3), "cost": round(float(join_cost(e, n_)), 3)})
    return {"segments": segs, "length_s": round(at, 3), "joins": joins, "join": joins[0] if joins else None}


def _exact(plan, target_s):
    """Play the plan up to 3 % faster or slower (pitch kept) so it ends on target_s."""
    rate = plan["length_s"] / target_s
    if abs(rate - 1) > .03:
        plan["note"] += f" Not stretched: {plan['length_s']:.2f} s is {abs(rate - 1) * 100:.1f} % from the target (3 % at most)."
        return plan
    for sg in plan["segments"]:
        sg["playback_rate"] = round(rate, 5)
        sg["at_s"] = round(sg["at_s"] / rate, 4)
        sg["fade_in"], sg["fade_out"] = round(sg["fade_in"] / rate, 3), round(sg["fade_out"] / rate, 3)
    plan.update(stretch=round(rate, 5), length_s=round(target_s, 3))
    return plan


def apply_fit(pid, base_revision, asset_id, plan, timeline_start_frame=0, volume=.5, clip_prefix="music-fit", role="music"):
    """Write a fit() plan as AudioClips (replacing earlier clips with the same prefix)."""
    from . import agent
    p = agent.read(pid)
    if p["revision"] != base_revision:
        raise ValueError("Read the current project revision before placing music")
    t = p["timeline"]
    total = t["shots"][-1]["end_frame"] if t.get("shots") else None
    ops = [{"op": "delete_audio", "id": c["id"]} for c in t.get("audio_clips") or [] if c["id"].startswith(clip_prefix + "-")]
    for k, sg in enumerate(plan["segments"]):
        rate = sg.get("playback_rate", 1.0)
        s0 = timeline_start_frame + round(sg["at_s"] * FPS)
        e0 = s0 + int((sg["source_end"] - sg["source_start"]) / rate * FPS)
        if total:
            e0 = min(e0, total)
        if e0 - s0 < 2:
            continue
        ops.append({"op": "upsert_audio", "audio": {"id": f"{clip_prefix}-{k}", "asset_id": asset_id, "start_frame": s0, "end_frame": e0,
                                                    "source_start": sg["source_start"], "volume": volume, "fade_in": sg["fade_in"], "playback_rate": rate,
                                                    "fade_out": sg["fade_out"], "duck_under_voice": True, "role": role}})
    return {"revision": agent.patch(pid, base_revision, ops)["revision"], "clips": len([o for o in ops if o["op"] == "upsert_audio"])}


def momentary(path, start=0.0, seconds=None):
    """EBU R128 momentary loudness (400 ms window) every 100 ms over a stretch of a file: (times from start, LUFS)."""
    import re
    cmd = [FFMPEG, "-v", "info", "-ss", f"{start:.3f}", *(["-t", f"{seconds:.3f}"] if seconds else []), "-i", str(path), "-vn", "-af", "ebur128", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True, errors="replace").stderr
    m = [(float(a), float(b)) for a, b in re.findall(r"t:\s*([\d.]+)\s+TARGET.*?M:\s*([-\d.]+)", err)]
    return np.array([t for t, _ in m]), np.array([v for _, v in m])


def _energy_db(v):
    v = np.asarray(v, float)
    v = v[v > -70]
    return float(10 * np.log10(np.mean(10 ** (v / 10)))) if len(v) else -70.0


def duck(clips, music_path, voice_path, voice_start_s=0.0, gap_lu=13.0, pause_s=None, downbeats=None, ramp_s=.35, fps=FPS):
    """Music under a voice by measured loudness, not by a compressor's threshold. Within each spoken phrase the music
    sits gap_lu under the voice's own level (Torcoli et al., JAES 2019: speech at least 10 LU over music, and lay
    listeners want about 4 LU more than mixers; 12-14 LU recommended); through a pause of pause_s or longer (default:
    one bar of the music, else 1.2 s) it returns to its bed level. A dip starts on the downbeat before the phrase when
    one is near and is down before the first word; the swell lands on the downbeat after it.

    clips: placed music [{start_frame, end_frame, source_start, volume, playback_rate?, fade_in, fade_out}] (one clip,
    or fit()/apply_fit()'s segments) on the timeline; voice_path starts at voice_start_s; downbeats: music downbeats in
    timeline seconds. Returns {"clips": the same music re-cut into constant-gain pieces crossfaded over each ramp
    (duck_under_voice off: the gains are the ducking), "phrases": [{start, end, voice_lufs, music_lufs, gain_db, gap_lu}],
    "min_gap_lu"}. Phrases the music never reaches more quietly than gap_lu keep their gain at 0 (never boosted)."""
    tv, mv = momentary(voice_path)  # a mono voice measures as the mix plays it: ffmpeg's upmix to stereo keeps its loudness
    if not len(tv):
        raise ValueError("the voice could not be measured")
    tv = tv + voice_start_s - .2                          # ebur128 stamps a 400 ms window at its end
    live = mv[mv > -70]
    gate = max(-50.0, (float(np.percentile(live, 90)) if len(live) else -30.0) - 18)
    on = mv > gate
    if pause_s is None:
        bar = float(np.median(np.diff(downbeats))) if downbeats is not None and len(downbeats) > 2 else 1.2
        pause_s = min(2.5, max(.8, bar))
    runs, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j + 1 < len(on) and on[j + 1]:
                j += 1
            runs.append([tv[i], tv[j] + .1])
            i = j + 1
        else:
            i += 1
    phrases = []
    for a, b in runs:  # pauses shorter than pause_s stay ducked: the music does not pump between words
        if phrases and a - phrases[-1][1] < pause_s:
            phrases[-1][1] = b
        elif b - a >= .3:
            phrases.append([a, b])
    tm, mm = momentary(music_path)
    tm = tm - .2
    cl = sorted(clips, key=lambda c: c["start_frame"])

    def music_at(t):  # the music's level (LUFS, its clip volume included) heard at timeline second t
        c = next((c for c in cl if c["start_frame"] / fps <= t < c["end_frame"] / fps), None)
        if c is None:
            return None
        src = c.get("source_start", 0.0) + (t - c["start_frame"] / fps) * c.get("playback_rate", 1.0)
        k = int(np.searchsorted(tm, src))
        return float(mm[min(max(k, 0), len(mm) - 1)]) + 20 * math.log10(max(1e-6, c.get("volume", 1.0)))
    report, gains = [], []
    for a, b in phrases:
        vv = mv[(tv >= a) & (tv < b) & on]
        lv = _energy_db(vv)
        ml = [x for x in (music_at(t) for t in np.arange(a, b, .1)) if x is not None]
        if not ml:
            continue
        lm = _energy_db(ml)
        g = min(0.0, round(lv - gap_lu - lm, 1))
        gains.append((a, b, g))
        report.append({"start": round(float(a), 2), "end": round(float(b), 2), "voice_lufs": round(lv, 1), "music_lufs": round(lm + g, 1), "gain_db": g,
                       "gap_lu": round(lv - lm - g, 1)})
    db = np.asarray(downbeats if downbeats is not None else [], float)
    # gain changes: (ramp start, ramp end, gain after)
    marks = []
    for a, b, g in gains:
        before = db[(db >= a - 1.0) & (db <= a - .15)]
        r0 = float(before[-1]) if len(before) else a - .05 - ramp_s
        marks.append((r0, a - .05, g))
        after = db[(db >= b + .35) & (db <= b + 1.4)]
        r1 = float(after[0]) if len(after) else b + .15 + ramp_s
        marks.append((b + .15, r1, 0.0))
    out = []
    for c in cl:
        c0, c1 = c["start_frame"] / fps, c["end_frame"] / fps
        inside = [m for m in marks if c0 < m[0] and m[1] < c1]
        # the gain in force where this clip starts: a phrase running across a join stays down in the next clip
        g = next((m[2] for m in reversed(marks) if m[0] <= c0), 0.0)
        pieces, t0 = [], c0
        for r0, r1, g1 in inside:  # each piece runs from the previous ramp's start to the end of the next ramp
            pieces.append((t0, r1, g, r1 - r0))
            t0, g = r0, g1
        pieces.append((t0, c1, g, None))
        for k, (a, b, g, ramp_out) in enumerate(pieces):
            fi = c.get("fade_in", 0.0) if k == 0 else pieces[k - 1][3]
            fo = c.get("fade_out", .15) if k == len(pieces) - 1 else ramp_out
            rate = c.get("playback_rate", 1.0)
            sf = round(a * fps)
            out.append({**{x: y for x, y in c.items() if x not in ("id",)}, "start_frame": sf, "end_frame": round(b * fps),
                        "source_start": round(c.get("source_start", 0.0) + (sf / fps - c0) * rate, 4), "volume": round(c.get("volume", 1.0) * 10 ** (g / 20), 4),
                        "fade_in": round(min(fi, (b - a) / 2), 3), "fade_out": round(min(fo, (b - a) / 2), 3), "duck_under_voice": False})
    return {"clips": out, "phrases": report, "min_gap_lu": min((r["gap_lu"] for r in report), default=None), "pause_s": round(pause_s, 2)}


def apply_duck(pid, base_revision, clip_prefix="music-fit", gap_lu=13.0, voice_asset_id=None):
    """duck() over a project's music clips (ids starting clip_prefix) under its narration (or voice_asset_id, from
    frame 0), written back in place of those clips."""
    from . import agent
    from .media import safe_asset_path
    p = agent.read(pid)
    if p["revision"] != base_revision:
        raise ValueError("Read the current project revision before ducking music")
    t = p["timeline"]
    clips = [c for c in t.get("audio_clips") or [] if c["id"].startswith(clip_prefix + "-")]
    vid = voice_asset_id or (p.get("config") or {}).get("narration_id")
    if not clips or not vid:
        raise ValueError("needs music clips with the prefix and a narration (or voice_asset_id)")
    mpath = safe_asset_path(pid, clips[0]["asset_id"])
    st = structure(str(mpath))
    down = []
    for c in clips:  # the music's downbeats where the clips play them, in timeline seconds
        rate = c.get("playback_rate", 1.0)
        for d in st["downbeats"]:
            t_ = c["start_frame"] / FPS + (d - c.get("source_start", 0.0)) / rate
            if c["start_frame"] / FPS <= t_ < c["end_frame"] / FPS:
                down.append(t_)
    r = duck(clips, str(mpath), str(safe_asset_path(pid, vid)), 0.0, gap_lu, downbeats=sorted(down))
    ops = [{"op": "delete_audio", "id": c["id"]} for c in clips]
    ops += [{"op": "upsert_audio", "audio": {**c, "id": f"{clip_prefix}-{k}"}} for k, c in enumerate(r["clips"])]
    return {"revision": agent.patch(pid, base_revision, ops)["revision"], "phrases": len(r["phrases"]), "min_gap_lu": r["min_gap_lu"], "clips": len(r["clips"])}


def _source_fps(path):
    from .media import probe
    try:
        v = next(s for s in probe(path)["streams"] if s["codec_type"] == "video")
        num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
        f = float(num) / float(den or 1)
        return f if 5 <= f <= 240 else FPS
    except Exception:
        return FPS


def _best_lead(phase, tol):
    """phase: offsets as fractions of a beat in [-.5, .5). Best lead (fraction) and the share within ±tol of it."""
    grid = np.linspace(-.5, .5, 101)[:-1]
    shares = [float(np.mean(np.abs(((phase - g + .5) % 1) - .5) <= tol)) for g in grid]
    i = int(np.argmax(shares))
    best = max(shares)
    plateau = [g for g, s_ in zip(grid, shares) if s_ == best]
    g = plateau[len(plateau) // 2]  # centre of the plateau, then the mean phase of the cuts it captures
    d = ((phase - g + .5) % 1) - .5
    inside = np.abs(d) <= tol
    lead = g + float(d[inside].mean()) if inside.any() else g
    return float(((lead + .5) % 1) - .5), best


def cut_alignment(path, cuts, start=0.0, end=None, window_s=30.0, fps=None, bpm_range=None, min_periodicity=.2, sims=500):
    """How an edit sits on its music: per window (tempo can change), each cut's signed offset to the nearest beat in
    source frames (negative = picture before the beat) and its position in the bar. The editor's habitual lead is
    searched over ±half a beat; cuts within ±2 frames of (beat + lead) count as on the beat. Significance is a
    permutation test: the same lead search on random cut phases (p95 of `sims` runs) — a beat-locked edit must beat it,
    so a lead found by chance on few cuts is not reported as cutting to the beat. Windows with periodicity under
    `min_periodicity` (speech-only beds, weak pulse) are reported but not counted."""
    cuts = sorted(float(c) for c in cuts)
    fps = fps or _source_fps(path)
    end = end if end is not None else (max(cuts) + 1.0 if cuts else start + window_s)
    wins, phases, tols, bars, pers = [], [], [], [], []
    found = []
    t = start
    while t < end - 2:
        t1 = min(end, t + window_s)
        cs = [c for c in cuts if t + .3 < c < t1 - .3]
        if len(cs) >= 2 and t1 - t >= 6:
            try:
                found.append((t, t1, cs, _analyse(path, t, t1, bpm_range)))
            except ValueError:
                pass
        t = t1
    # A song keeps its tempo: a window whose pulse is much weaker than the clearest window's and whose tempo differs
    # from it is read again near that tempo (a 100 BPM track had been read as 133 BPM after its intro, and an edit cut
    # on every other beat measured as independent of the beat).
    anchor = max(found, key=lambda f: f[3]["strength"], default=None)
    if anchor and not bpm_range and anchor[3]["strength"] >= .5:
        ab = anchor[3]["bpm"]
        for i, (t, t1, cs, a) in enumerate(found):
            if all(abs(a["bpm"] / (ab * m) - 1) > .08 for m in (.5, 1, 2)) and a["strength"] < .7 * anchor[3]["strength"]:
                tries = []
                for m in (1, 2, .5):  # the anchor's tempo, or its double/half (a busy section pulses in eighths)
                    try:
                        tries.append(_analyse(path, t, t1, (ab * m * .92, ab * m * 1.08)))
                    except ValueError:
                        pass
                b = max(tries, key=lambda x: x["strength"], default=None)
                # only a clearer reading replaces it (measured: .77 at 50 BPM against .50 at 133 BPM), never a forced weaker one
                if b and b["strength"] >= max(min_periodicity, a["strength"]):
                    found[i] = (t, t1, cs, b)
    for t, t1, cs, a in found:
        bt, ph = a["beats"], a["phase"]
        per_s = a["period"] / a["fr"]
        pos = _bar_positions(bt, a["downbeats"]) if str(a.get("tracker")) == "beat_this" and len(a.get("downbeats", [])) >= 2 \
            else [int((i - ph) % 4) for i in range(len(bt))]
        rows = []
        for c in cs:
            i = int(np.argmin(np.abs(bt - c)))
            rows.append((float(round((c - bt[i]) * fps, 1)), pos[i], ((c - bt[i]) / per_s + .5) % 1 - .5))
        pulse = a["strength"]
        wins.append({"start": round(t, 2), "end": round(t1, 2), "bpm": round(a["bpm"], 1), "periodicity": round(pulse, 3), "cuts": len(cs),
                     "counted": pulse >= min_periodicity, "offsets_frames": [r[0] for r in rows], "beat_in_bar": [r[1] for r in rows]})
        if pulse >= min_periodicity:
            phases += [r[2] for r in rows]
            bars += [r[1] for r in rows]
            tols += [2 / (per_s * fps)] * len(rows)
            pers.append(per_s * fps)
    base = {"windows": wins, "fps": round(fps, 3)}
    if len(phases) < 4:
        return {**base, "reading": "no clear musical pulse under enough cuts", "cuts_on_beat": None, "lead_frames": None, "cuts_counted": len(phases)}
    P = np.array(phases)
    tol = float(np.mean(tols))
    lead, share = _best_lead(P, tol)
    rng = np.random.default_rng(1)
    null = [_best_lead(rng.uniform(-.5, .5, len(P)), tol)[1] for _ in range(sims)]
    p95 = float(np.percentile(null, 95))
    p_value = float((np.sum(np.array(null) >= share) + 1) / (sims + 1))
    per = float(np.median(pers))
    lead_f = round(lead * per, 1)
    on_mask = np.abs(((P - lead + .5) % 1) - .5) <= tol
    down = float(np.mean([b == 0 for b, m in zip(bars, on_mask) if m])) if on_mask.any() else 0.0
    locked = share > p95 and len(P) >= 8
    reading = "cut to the beat" if locked else ("too few cuts to tell" if len(P) < 8 else "cuts independent of the beat")
    if locked and lead_f:
        reading += f", picture {abs(lead_f):g} frames {'before' if lead_f < 0 else 'after'} the beat"
    return {**base, "cuts_counted": len(P), "lead_frames": lead_f, "cuts_on_beat": round(share, 3), "chance_p95": round(p95, 3), "p_value": round(p_value, 4),
            "downbeat_share_of_on_beat": round(down, 3), "reading": reading,
            "method": "Per-window calibrated beats (periodicity ≥ min_periodicity); lead searched over ±½ beat; on-beat = within 2 source "
                      "frames of beat + lead; significance by permutation (random cut phases, same lead search)."}


def snap_cuts(pid, base_revision, music_path=None, beat_times=None, use="beats", tolerance_frames=6, lead_frames=2, music_start=0.0,
              timeline_offset_frames=0, dry_run=False, protect=None, bpm_range=None):
    """Move shot boundaries onto the music (minus lead_frames) when within tolerance; each move is applied separately
    so one boundary without source handles does not block the others.

    use: beats | downbeats | priority (downbeat 1.0 > beat 3 0.7 > other beats 0.4, nearer wins among equals) | hits
    (impacts and section entries, for weak-pulse beds) | phrases (4-bar lines and section entries) | against (the off-beat
    "and", for tension). protect: [[start_frame, end_frame), ...] timeline ranges (dialogue) where cuts stay put."""
    if use not in ("beats", "downbeats", "priority", "hits", "phrases", "against"):
        raise ValueError("use is beats, downbeats, priority, hits, phrases or against")
    if not 0 <= lead_frames <= 5 or not 1 <= tolerance_frames <= 30:
        raise ValueError("lead_frames 0..5, tolerance_frames 1..30")
    from . import agent
    p = agent.read(pid)
    t = p.get("timeline")
    if not t or p["revision"] != base_revision:
        raise ValueError("Read the current project revision before snapping cuts")
    info, st = None, None
    to_f = lambda bt: round((bt - music_start) * FPS) + timeline_offset_frames - lead_frames
    if beat_times is None:
        if not music_path:
            raise ValueError("Pass music_path or beat_times")
        # the whole track, as music_structure reads it: analysed from music_start the same bed came out at 133 BPM where
        # music_structure said 200, and a reel cut to one grid while drawing the other
        st = structure(music_path, 0.0, bpm_range=bpm_range)
        info = {k: st[k] for k in ("bpm", "beat_period_s", "periodicity", "tempo_clarity", "pulse", "recommended_snap", "alternatives_bpm")}
        info["analysis"] = "whole track (the grid music_structure returns)"
        bt, bib = st["beats"], st["beat_in_bar"]
    else:
        if use in ("priority", "hits", "phrases"):
            raise ValueError(f"use={use} needs music_path (bars, hits and sections come from the analysis)")
        bt, bib = list(beat_times), [0] * len(beat_times)
    # (timeline frame, weight, music seconds): the target's time travels with each move, so a picture can draw the grid
    # the cuts went to
    if use == "beats":
        grid = [(to_f(b), 1.0, b) for b in bt]
    elif use == "downbeats":
        grid = [(to_f(b), 1.0, b) for b in (st["downbeats"] if st else bt)]
    elif use == "priority":
        grid = [(to_f(b), {0: 1.0, 2: .7}.get(k, .4), b) for b, k in zip(bt, bib)]
    elif use == "against":
        grid = [(to_f((x + y) / 2), 1.0, (x + y) / 2) for x, y in zip(bt, bt[1:])]
    elif use == "hits":
        grid = [(to_f(h["time"]), 1.0, h["time"]) for h in st["hits"]] + [(to_f(s_["start"]), .9, s_["start"]) for s_ in st["sections"][1:]]
    else:
        grid = [(to_f(x), .8, x) for x in st["phrases_4"]] + [(to_f(s_["start"]), 1.0, s_["start"]) for s_ in st["sections"][1:]]
    prot = [tuple(r) for r in (protect or [])]
    if any(len(r) != 2 or r[0] >= r[1] for r in prot):
        raise ValueError("protect ranges are [start_frame, end_frame)")
    inside = lambda fr: any(a0 <= fr < a1 for a0, a1 in prot)
    shots = t["shots"]
    plan, skipped = [], []
    for i in range(len(shots) - 1):
        cut = shots[i]["end_frame"]
        if inside(cut):
            skipped.append({"after_shot": shots[i]["id"], "cut": cut, "reason": "protected range"})
            continue
        cands = [(w - .6 * abs(g - cut) / tolerance_frames, -abs(g - cut), g, w, tm) for g, w, tm in grid if abs(g - cut) <= tolerance_frames and not inside(g)]
        if not cands:
            near = min(grid, key=lambda gw: abs(gw[0] - cut))[0] if grid else None
            if near is not None:
                skipped.append({"after_shot": shots[i]["id"], "cut": cut, "nearest_target_frame": near, "reason": "outside tolerance"})
            continue
        _, _, near, w, tm = max(cands)
        if near == cut:
            continue
        if not shots[i]["start_frame"] + 6 < near < shots[i + 1]["end_frame"] - 6:
            skipped.append({"after_shot": shots[i]["id"], "cut": cut, "nearest_target_frame": near, "reason": "would make a shot shorter than 6 frames"})
            continue
        plan.append({"after_shot": shots[i]["id"], "from": cut, "to": near, "delta": near - cut, "weight": w, "music_s": round(float(tm), 3)})
    moved, rev = [], base_revision
    if not dry_run:
        for mv in plan:
            try:
                rev = agent.patch(pid, rev, [{"op": "move_boundary", "shot_id": mv["after_shot"], "frame": mv["to"]}])["revision"]
                moved.append(mv)
            except Exception as e:  # e.g. not enough source handle for the incoming shot
                skipped.append({**mv, "reason": str(e)[:160]})
    final = {mv["after_shot"]: mv["to"] for mv in (plan if dry_run else moved)}
    cuts = [final.get(s_["id"], s_["end_frame"]) for s_ in shots[:-1]]
    on_grid = sum(1 for c in cuts if any(abs(g - c) <= 1 for g, *_ in grid))
    missing = []
    if st:
        end_f = shots[-1]["end_frame"] if shots else 0
        for s_ in st["sections"][1:]:
            f0 = to_f(s_["start"])
            if 0 < f0 < end_f and not any(abs(c - f0) <= 2 for c in cuts):
                missing.append({"section": s_["label"], "time": s_["start"], "frame": f0, "entry_step_db": s_["entry_step_db"]})
    end_f = shots[-1]["end_frame"] if shots else 0
    return {"revision": None if dry_run else rev, "planned": plan, "moved": moved if not dry_run else [], "skipped": skipped,
            "cuts_on_target": on_grid, "cuts": len(cuts), "section_entries_without_cut": missing, "beat_info": info,
            "targets": [{"frame": g, "music_s": round(float(tm), 3), "weight": w} for g, w, tm in sorted(grid) if 0 <= g <= end_f + lead_frames][:400],
            "note": "Cut on the beat for energy, against it for tension; with a weak pulse cut to hits and section entries. "
                    "lead_frames=1-2 lands the picture change just before the hit. Section entries without a cut are the strongest "
                    "places to add one. Inspect each moved cut for action continuity (motion_audit / cut_audit)."}
