"""Audio (music, voice-over, podcasts, sound logos): level and dynamics, silence, onsets and tempo, brightness, how
long the intro takes, the energy arc and where it peaks, and sections where the energy or timbre changes.

Decoded with ffmpeg (FFMPEG_BINARY, imageio-ffmpeg, or ffmpeg on PATH) to mono 22.05 kHz. Levels are RMS dBFS, not
LUFS (no K-weighting); tempo is an onset-autocorrelation estimate with its confidence. Listen before concluding.
"""
import math
import os
import shutil
import subprocess
from pathlib import Path
import numpy as np
from . import feature, register

RATE = 22050
HOP = 512


def ffmpeg():
    exe = os.environ.get("FFMPEG_BINARY")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return shutil.which("ffmpeg") or "ffmpeg"


def decode(path, start=None, end=None, channels=1):
    cmd = [ffmpeg(), "-v", "error", *(["-ss", f"{start:.3f}"] if start else []), "-i", str(path),
           *(["-t", f"{end - (start or 0):.3f}"] if end else []), "-vn", "-ac", str(channels), "-ar", str(RATE), "-f", "f32le", "-"]
    p = subprocess.run(cmd, capture_output=True, timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode:
        raise ValueError(f"Could not decode audio: {p.stderr.decode(errors='replace')[:160]}")
    return np.frombuffer(p.stdout, dtype=np.float32)


def _db(x):
    return 20 * math.log10(max(float(x), 1e-9))


def _frames(y, size):
    n = len(y) // size
    return y[:n * size].reshape(n, size) if n else np.zeros((0, size), dtype=np.float32)


CHUNK = 2048  # STFT frames per block: memory stays flat for an hour of audio


def _onsets(y):
    """Spectral-flux onset envelope at RATE/HOP frames per second (computed block by block, float32)."""
    if len(y) < 2048:
        return np.zeros(0)
    win = np.hanning(1024).astype(np.float32)
    n = 1 + (len(y) - 1024) // HOP
    flux, prev = [np.float32(0)], None
    for start in range(0, n, CHUNK):
        k = np.arange(start, min(n, start + CHUNK))
        idx = np.arange(1024)[None, :] + HOP * k[:, None]
        mag = np.log1p(np.abs(np.fft.rfft(y[idx] * win, axis=1)).astype(np.float32))
        if prev is not None:
            mag = np.vstack([prev, mag])
        flux.extend(np.maximum(0, np.diff(mag, axis=0)).sum(axis=1))
        prev = mag[-1:]
    return np.asarray(flux, dtype=np.float32)


def _tempo(env):
    """Onset autocorrelation over 60-200 BPM -> (bpm, confidence, half-time, double-time). A period between two whole
    frames splits its peak over both lags, so each lag is scored with its stronger neighbour and the period is
    interpolated. A steady pulse correlates at every multiple of its period: the shortest period within 90 % of the
    best is taken, and the half/double readings are reported because backbeats and swing make either plausible.
    No clear pulse (a sustained tone, silence) gives no tempo."""
    fps = RATE / HOP
    # A pulse stands out of its onset envelope: p99/mean was 14-37 on clicks and kick/snare, 2.0 on a sine, 1.2 on noise.
    if len(env) < fps * 4 or _peaks(env, fps) < 8 or np.percentile(env, 99) < 4 * (env.mean() + 1e-9):
        return None, 0.0, None, None
    smooth = np.convolve(env.astype(np.float64), [.25, .5, .25], mode="same")
    e = smooth - smooth.mean()
    n = 1 << int(np.ceil(np.log2(2 * len(e))))
    spec = np.fft.rfft(e, n)
    ac = np.fft.irfft(spec * np.conj(spec), n)[:len(e)]
    lo, hi = int(fps * 60 / 200), int(fps * 60 / 60) + 1
    if hi + 1 >= len(ac) or ac[0] <= 0:
        return None, 0.0, None, None
    lags = np.arange(lo, hi + 1)
    pair = ac[lags] + np.maximum(ac[lags - 1], ac[lags + 1])
    if pair.max() <= 0:
        return None, 0.0, None, None
    lag = int(lags[np.flatnonzero(pair >= .9 * pair.max())[0]])
    nb = lag + 1 if ac[lag + 1] >= ac[lag - 1] else lag - 1
    w0, w1 = max(ac[lag], 0.0), max(ac[nb], 0.0)
    period = (lag * w0 + nb * w1) / (w0 + w1) if w0 + w1 > 0 else float(lag)
    bpm = 60 * fps / period
    conf = float(max(ac[lag], ac[nb]) / ac[0])
    return bpm, max(0.0, min(1.0, conf)), (bpm / 2 if bpm / 2 >= 50 else None), (bpm * 2 if bpm * 2 <= 240 else None)


def _peaks(env, fps):
    if len(env) < 3:
        return 0
    thr = np.median(env) + 1.5 * env.std()
    return int(np.sum((env[1:-1] > thr) & (env[1:-1] >= env[:-2]) & (env[1:-1] > env[2:])))


def _centroid(y):
    if len(y) < 2048:
        return 0.0
    frames, freqs, win, out = _frames(y, 2048), np.fft.rfftfreq(2048, 1 / RATE).astype(np.float32), np.hanning(2048).astype(np.float32), []
    for start in range(0, len(frames), CHUNK):
        mag = np.abs(np.fft.rfft(frames[start:start + CHUNK] * win, axis=1)).astype(np.float32)
        out.extend((mag * freqs).sum(axis=1) / (mag.sum(axis=1) + 1e-9))
    return float(np.median(out))


def _phase_note(path):
    """Channels in opposite phase cancel in the mono downmix every measurement uses: say so instead of 'silence'."""
    try:
        st = decode(path, end=30, channels=2)
    except ValueError:
        return None
    if len(st) < 4 * RATE:
        return None
    left, right = st[0::2], st[1::2]
    if left.std() < 1e-6 or right.std() < 1e-6:
        return None
    corr = float(np.corrcoef(left, right)[0, 1])
    if corr < -.5:
        return f"stereo channels are out of phase (correlation {corr:.2f}): the mono downmix cancels; levels read too low"
    return None


def _basic(y):
    if not len(y):
        raise ValueError("No audio samples in this span")
    rms = float(np.sqrt(np.mean(y ** 2)))
    win = _frames(y, int(.4 * RATE))
    short = np.array([_db(np.sqrt(np.mean(w ** 2))) for w in win]) if len(win) else np.array([_db(rms)])
    audible = short[short > -60]
    env = _onsets(y)
    dur = len(y) / RATE
    return {"duration_s": feature(dur, "s"), "rms_dbfs": feature(_db(rms), "dBFS (RMS, not LUFS)"),
            "peak_dbfs": feature(_db(np.abs(y).max()), "dBFS"), "crest_db": feature(_db(np.abs(y).max()) - _db(rms), "dB"),
            "loudness_range_db": feature(float(np.percentile(audible, 95) - np.percentile(audible, 10)) if len(audible) > 2 else 0.0, "dB (p95-p10 of 0.4 s RMS)"),
            "silence_share": feature(float((short < -50).mean()), "share of 0.4 s windows below -50 dBFS"),
            "onsets_per_s": feature(_peaks(env, RATE / HOP) / max(dur, 1e-6), "onsets/s"),
            "brightness_hz": feature(_centroid(y), "Hz (median spectral centroid)")}, short, env


def _sections(short, min_s=6.0):
    """Boundaries (s) where the 0.4 s level changes most, as a novelty curve over 4 s on each side."""
    k = 10  # 4 s of 0.4 s windows
    if len(short) < 2 * k + 2:
        return []
    nov = np.array([abs(short[i:i + k].mean() - short[i - k:i].mean()) for i in range(k, len(short) - k)])
    cuts, order = [], np.argsort(-nov)
    for i in order:
        t = (i + k) * .4
        if nov[i] < 3:  # dB: smaller changes are texture, not a new section
            break
        if all(abs(t - c) >= min_s for c in cuts):
            cuts.append(t)
        if len(cuts) >= 12:
            break
    return sorted(cuts)


class AudioSense:
    kind = "audio"
    version = "3"
    extensions = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma")
    spans = ("t",)

    def measure(self, path, options=None):
        y = decode(path)
        feats, short, env = _basic(y)
        dur = feats["duration_s"]["value"]
        bpm, conf, half, double = _tempo(env)
        feats["tempo_bpm"] = feature(bpm, "BPM (estimate; none without a clear pulse)")
        feats["tempo_confidence"] = feature(conf, "0..1 onset autocorrelation at that period")
        if half:
            feats["tempo_half_bpm"] = feature(half, "BPM (half-time reading of the same pulse)")
        if double:
            feats["tempo_double_bpm"] = feature(double, "BPM (double-time reading of the same pulse)")
        median = np.median(short) if len(short) else -60
        rise = next((i * .4 for i, v in enumerate(short) if v >= median), 0.0)
        feats["intro_s"] = feature(rise, "s until the level first reaches its median")
        if len(short) >= 10:
            smooth = np.convolve(short, np.ones(10) / 10, mode="same")
            feats["peak_energy_at_share"] = feature(float(np.argmax(smooth) / len(smooth)), "position of the loudest 4 s (0..1)")
            for q in (25, 50, 75):
                feats[f"level_at_{q}pct_db"] = feature(float(smooth[min(len(smooth) - 1, int(len(smooth) * q / 100))]), "dBFS (4 s average)")
        bounds = [0.0, *_sections(short), dur]
        parts = []
        for a, b in zip(bounds, bounds[1:]):
            if b - a >= 1:
                seg = y[int(a * RATE):int(b * RATE)]
                f, _, _ = _basic(seg)
                parts.append({"span": {"t": [round(a, 2), round(b, 2)]}, "features": {k: f[k] for k in ("rms_dbfs", "onsets_per_s", "brightness_hz")}})
        notes = ["levels are RMS dBFS, not LUFS; tempo is an estimate (see confidence and the half-time reading)"]
        phase = _phase_note(path)
        if phase:
            notes.append(phase)
        return {"features": feats, "parts": parts, "notes": notes}

    def fingerprint(self, path, options=None):
        from .. import fingerprint
        return fingerprint.audio(decode(path), RATE)

    def geometry(self, path, span, features, options=None):
        a, b = span["t"]
        total = features.get("duration_s")
        if not total or b > total + 1e-6:
            raise ValueError(f"span ends after the audio ({total} s)")
        return {"share": round((b - a) / total, 4), "start_share": round(a / total, 4)}

    def measure_span(self, path, span, options=None):
        a, b = span["t"]
        f, _, _ = _basic(decode(path, a, b))
        return {"features": f}

    def evidence(self, path, span, out_dir, options=None):
        a, b = span["t"]
        b = min(b, a + 30)
        out = Path(out_dir) / f"clip-{a:.2f}-{b:.2f}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        p = subprocess.run([ffmpeg(), "-v", "error", "-y", "-ss", f"{a:.3f}", "-i", str(path), "-t", f"{b - a:.3f}", "-vn", "-ac", "1",
                            "-ar", "24000", str(out)], capture_output=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if p.returncode:
            raise ValueError("Could not cut the audio clip")
        return [{"type": "audio", "path": str(out), "seconds": round(b - a, 2)}]


register(AudioSense())
