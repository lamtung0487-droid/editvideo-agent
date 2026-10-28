"""Synthetic two-speaker dialogue with known ground truth: speech-like phrases (harmonic voiced syllables with moving
pitch and formants, fricative bursts), known pauses, flat-pitch fillers, a noise floor and optional mains hum."""
import subprocess
import numpy as np

SR = 16000


def _formant_filter(x, formants, sr=SR):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    H = sum(np.exp(-.5 * ((f - fc) / bw) ** 2) for fc, bw in formants) + .02
    return np.fft.irfft(X * H, len(x))


def _syllable(f0, dur, rng, flat=False, sr=SR):
    n = int(dur * sr)
    t = np.arange(n) / sr
    contour = np.full(n, f0) if flat else f0 * (1 + .12 * np.sin(2 * np.pi * rng.uniform(1.5, 3) * t + rng.uniform(0, 6)) + .02 * rng.normal(0, 1) )
    phase = 2 * np.pi * np.cumsum(contour) / sr
    src = sum(np.sin(k * phase) / k for k in range(1, 30))
    vowels = [[(730, 90), (1090, 110), (2440, 160)], [(270, 60), (2290, 120), (3010, 180)], [(530, 80), (1840, 120), (2480, 160)], [(570, 80), (840, 100), (2410, 160)]]
    v = vowels[3] if flat else vowels[rng.integers(0, 3)]
    y = _formant_filter(src, v)
    env = np.minimum(1, np.minimum(t / .02, (dur - t) / .03)) if flat else np.sin(np.pi * t / dur) ** .6
    return y * env


def make(path, seed=1, hum=False):
    rng = np.random.default_rng(seed)
    out, truth, t = [], {"regions": [], "fillers": [], "pauses": []}, 0.3
    out.append(np.zeros(int(.3 * SR)))
    speakers = {"A": 115.0, "B": 215.0}
    plan = ["A", "A", "B", "A", "B", "B", "A", "B"]
    for k, spk in enumerate(plan):
        phrase = []
        for s in range(rng.integers(5, 9)):
            d = rng.uniform(.14, .24)
            phrase.append(_syllable(speakers[spk] * rng.uniform(.95, 1.05), d, rng))
            if rng.random() < .3:
                phrase.append(rng.normal(0, .08, int(.04 * SR)) * np.hanning(int(.04 * SR)))  # fricative
        y = np.concatenate(phrase)
        out.append(y / (np.abs(y).max() + 1e-9) * .5)
        truth["regions"].append({"start": t, "end": t + len(y) / SR, "speaker": spk})
        t += len(y) / SR
        if k in (2, 5):  # a filler after a short gap
            gap = .25
            out.append(np.zeros(int(gap * SR)))
            t += gap
            f = _syllable(speakers[spk], .42, rng, flat=True)
            out.append(f / (np.abs(f).max() + 1e-9) * .4)
            truth["fillers"].append({"start": t, "end": t + .42, "speaker": spk})
            t += .42
        pause = [.3, 1.4, .6, 2.1, .25, .9, 1.2, .4][k]
        out.append(np.zeros(int(pause * SR)))
        truth["pauses"].append(pause)
        t += pause
    x = np.concatenate(out)
    x = x + rng.normal(0, 10 ** (-58 / 20), len(x))
    if hum:
        x = x + 10 ** (-38 / 20) * np.sin(2 * np.pi * 50 * np.arange(len(x)) / SR)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f64le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "pcm_s16le", str(path)], input=x.astype(np.float64).tobytes(), check=True)
    truth["duration"] = len(x) / SR
    return truth
